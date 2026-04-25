"""NSE F&O (futures & options) data client.

Fetches four data sources from NSE:
- Daily F&O bhavcopy (per-contract EOD OHLC, OI, volume, settle price)
- Participant-wise OI (FII/DII/Pro/Client long+short across instrument categories)
- Live option chain snapshot (per-strike CE/PE OI/IV/volume) — requires session cookies
- F&O-eligible universe (symbol list from lot-size CSV)

Mirrors the sync httpx pattern from `NSEClient` (cookie preflight + retry) and
`BhavcopyClient` (CSV parsing).
"""

from __future__ import annotations

import csv
import io
import logging
import time
import zipfile
from datetime import date, datetime
from urllib.parse import quote

import httpx

from flowtracker.fno_models import (
    FnoContract,
    FnoContractRaw,
    FnoParticipantOi,
    FnoUniverse,
    OptionChainSnapshot,
    OptionChainStrike,
)

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nseindia.com"
_ARCHIVES_URL = "https://nsearchives.nseindia.com"
_ARCHIVES_LEGACY_URL = "https://archives.nseindia.com"
_PREFLIGHT_URL = f"{_BASE_URL}/option-chain"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": f"{_BASE_URL}/option-chain",
}

_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0

# NSE FinInstrmTp → canonical instrument code
_INSTR_MAP = {
    "STF": "FUTSTK",
    "STO": "OPTSTK",
    "IDF": "FUTIDX",
    "IDO": "OPTIDX",
}

# Participant OI: (instrument_category, long_col, short_col) tuples
_PARTICIPANT_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("idx_fut", "Future Index Long", "Future Index Short"),
    ("idx_opt_ce", "Option Index Call Long", "Option Index Call Short"),
    ("idx_opt_pe", "Option Index Put Long", "Option Index Put Short"),
    ("stk_fut", "Future Stock Long", "Future Stock Short"),
    ("stk_opt_ce", "Option Stock Call Long", "Option Stock Call Short"),
    ("stk_opt_pe", "Option Stock Put Long", "Option Stock Put Short"),
)


class FnoFetchError(Exception):
    """Raised when NSE F&O endpoints fail after all retries or return malformed data."""
    pass


class FnoClient:
    """Client for NSE F&O bhavcopy, participant OI, option chain, and universe endpoints."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
        )
        self._has_cookies = False

    # ------------------------------------------------------------------
    # Session / retry plumbing
    # ------------------------------------------------------------------

    def _ensure_cookies(self) -> None:
        """Warm the session by hitting the option-chain page to acquire cookies."""
        resp = self._client.get(_PREFLIGHT_URL)
        resp.raise_for_status()
        self._has_cookies = True

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        needs_cookies: bool = False,
        **kw,
    ) -> httpx.Response:
        """Issue HTTP request with exponential-backoff retries and cookie refresh on 403.

        Returns the successful httpx.Response. Raises FnoFetchError after 3 attempts.
        404 is returned directly to the caller (do not retry) so caller can decide.
        """
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                if needs_cookies and (not self._has_cookies or attempt > 0):
                    self._ensure_cookies()

                resp = self._client.request(method, url, **kw)

                if resp.status_code == 403:
                    logger.warning(
                        "Got 403 from %s, refreshing cookies (attempt %d)",
                        url, attempt + 1,
                    )
                    self._has_cookies = False
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_BACKOFF_BASE * (2 ** attempt))
                    continue

                # 404 is a legitimate "no data" for archive endpoints — return as-is.
                if resp.status_code == 404:
                    return resp

                resp.raise_for_status()
                return resp

            except FnoFetchError:
                raise
            except Exception as e:
                last_error = e
                logger.warning("Attempt %d for %s failed: %s", attempt + 1, url, e)
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE * (2 ** attempt))

        raise FnoFetchError(
            f"Failed to fetch {url} after {_MAX_RETRIES} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    # 1. F&O bhavcopy (per-contract EOD)
    # ------------------------------------------------------------------

    def fetch_fno_bhavcopy(self, trade_date: date) -> list[FnoContract]:
        """Fetch per-contract EOD F&O bhavcopy for a trading day.

        Returns [] on 404 (holiday/weekend). Uses NSE's 2024+ ISO-column CSV
        format, which NSE now distributes as a single-member ZIP archive
        (`.csv.zip`) instead of plain `.csv`. The unzipped CSV schema is
        unchanged.
        """
        date_str = trade_date.strftime("%Y%m%d")
        url = (
            f"{_ARCHIVES_URL}/content/fo/"
            f"BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
        )

        resp = self._request_with_retry("GET", url)
        if resp.status_code == 404:
            logger.info("No F&O bhavcopy for %s (holiday/weekend)", trade_date)
            return []

        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                names = zf.namelist()
                if not names:
                    logger.warning("Empty F&O bhavcopy zip for %s", trade_date)
                    return []
                csv_text = zf.read(names[0]).decode("utf-8", errors="replace")
        except zipfile.BadZipFile as e:
            logger.error("F&O bhavcopy zip parse failed for %s: %s", trade_date, e)
            return []

        return self._parse_fno_bhavcopy_csv(csv_text)

    def _parse_fno_bhavcopy_csv(self, text: str) -> list[FnoContract]:
        """Parse the NSE 2024+ F&O bhavcopy CSV into FnoContract records."""
        contracts: list[FnoContract] = []
        reader = csv.DictReader(io.StringIO(text))

        # Strip whitespace from fieldnames (NSE sometimes ships trailing spaces).
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]

        for row in reader:
            row = {
                k.strip(): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
                if k is not None
            }

            symbol = row.get("TckrSymb", "").strip()
            if not symbol:
                continue

            try:
                raw = FnoContractRaw.model_validate(row)
                contracts.append(_parse_row(raw))
            except FnoFetchError:
                # Data-integrity failures (e.g. OPTSTK without strike) must
                # surface — they would otherwise silently collapse on the
                # sentinel-keyed upsert. Let the caller see them.
                raise
            except Exception as e:
                logger.debug("Skipping F&O row for %s: %s", symbol, e)
                continue

        return contracts

    # ------------------------------------------------------------------
    # 2. Participant-wise OI
    # ------------------------------------------------------------------

    def fetch_participant_oi(self, trade_date: date) -> list[FnoParticipantOi]:
        """Fetch FII/DII/Pro/Client long+short OI for a trading day.

        Returns [] on 404 (holiday/weekend). Emits 6 records per participant
        (one per instrument_category).
        """
        date_str = trade_date.strftime("%d%m%Y")
        url = (
            f"{_ARCHIVES_LEGACY_URL}/content/nsccl/"
            f"fao_participant_oi_{date_str}.csv"
        )

        resp = self._request_with_retry("GET", url)
        if resp.status_code == 404:
            logger.info("No participant-OI archive for %s", trade_date)
            return []

        return self._parse_participant_oi_csv(resp.text, trade_date)

    def _parse_participant_oi_csv(
        self, text: str, trade_date: date,
    ) -> list[FnoParticipantOi]:
        """Parse the participant-OI archive CSV into FnoParticipantOi records."""
        lines = text.splitlines()

        # The archive has a few lines of metadata/blank before the real header.
        header_idx: int | None = None
        for i, line in enumerate(lines):
            if line.lstrip().startswith("Client Type"):
                header_idx = i
                break

        if header_idx is None:
            raise FnoFetchError(
                "Participant-OI CSV has no 'Client Type' header row — malformed archive"
            )

        reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
        if reader.fieldnames:
            reader.fieldnames = [f.strip() for f in reader.fieldnames]

        # Validate expected category columns exist; missing ones will be marked
        # None rather than silently zero-filled via _parse_int fallback.
        header_set = set(reader.fieldnames or [])
        missing: list[tuple[str, str, str]] = [
            (cat, lc, sc)
            for cat, lc, sc in _PARTICIPANT_CATEGORIES
            if lc not in header_set or sc not in header_set
        ]
        if missing:
            logger.warning(
                "Participant-OI header column mismatch: %d/%d expected "
                "category columns missing (%s). Affected categories will be "
                "recorded with None long_oi/short_oi. Header: %s",
                len(missing) * 2,
                len(_PARTICIPANT_CATEGORIES) * 2,
                ",".join(cat for cat, _, _ in missing),
                reader.fieldnames,
            )
        missing_cats = {cat for cat, _, _ in missing}

        records: list[FnoParticipantOi] = []
        for row in reader:
            row = {
                k.strip(): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
                if k is not None
            }

            participant = row.get("Client Type", "").strip()
            if not participant or participant.upper() == "TOTAL":
                continue

            for category, long_col, short_col in _PARTICIPANT_CATEGORIES:
                if category in missing_cats:
                    long_oi: int | None = None
                    short_oi: int | None = None
                else:
                    long_oi = _parse_int(row.get(long_col, ""))
                    short_oi = _parse_int(row.get(short_col, ""))
                records.append(FnoParticipantOi(
                    trade_date=trade_date,
                    participant=participant,
                    instrument_category=category,
                    long_oi=long_oi,
                    short_oi=short_oi,
                    long_turnover_cr=None,
                    short_turnover_cr=None,
                ))

        return records

    # ------------------------------------------------------------------
    # 3. Live option chain (cookies required)
    # ------------------------------------------------------------------

    def fetch_option_chain(self, symbol: str) -> OptionChainSnapshot:
        """Fetch a live option-chain snapshot for an F&O-eligible equity symbol."""
        sym_upper = symbol.strip().upper()
        url = f"{_BASE_URL}/api/option-chain-equities?symbol={quote(sym_upper)}"

        resp = self._request_with_retry("GET", url, needs_cookies=True)

        try:
            payload = resp.json()
        except Exception as e:
            raise FnoFetchError(f"Option chain JSON decode failed for {sym_upper}: {e}") from e

        records = payload.get("records") or {}
        expiries = records.get("expiryDates") or []
        if not expiries:
            raise FnoFetchError(f"Option chain for {sym_upper} has no expiries")

        nearest_expiry_str = expiries[0]
        nearest_expiry = _parse_expiry_str(nearest_expiry_str)

        underlying = records.get("underlyingValue")
        if underlying is None:
            raise FnoFetchError(f"Option chain for {sym_upper} missing underlyingValue")

        strikes: list[OptionChainStrike] = []
        for item in records.get("data", []) or []:
            if item.get("expiryDate") != nearest_expiry_str:
                continue
            strike_val = item.get("strikePrice")
            if strike_val is None:
                continue
            ce = item.get("CE") or {}
            pe = item.get("PE") or {}
            strikes.append(OptionChainStrike(
                strike=float(strike_val),
                ce_oi=_int_or_zero(ce.get("openInterest")),
                ce_change_oi=_int_or_zero(ce.get("changeinOpenInterest")),
                ce_volume=_int_or_zero(ce.get("totalTradedVolume")),
                ce_iv=_float_or_none(ce.get("impliedVolatility")),
                ce_last_price=_float_or_none(ce.get("lastPrice")),
                pe_oi=_int_or_zero(pe.get("openInterest")),
                pe_change_oi=_int_or_zero(pe.get("changeinOpenInterest")),
                pe_volume=_int_or_zero(pe.get("totalTradedVolume")),
                pe_iv=_float_or_none(pe.get("impliedVolatility")),
                pe_last_price=_float_or_none(pe.get("lastPrice")),
            ))

        return OptionChainSnapshot(
            symbol=sym_upper,
            expiry_date=nearest_expiry,
            underlying_price=float(underlying),
            fetched_at=datetime.now(),
            strikes=strikes,
        )

    # ------------------------------------------------------------------
    # 4. F&O-eligible universe
    # ------------------------------------------------------------------

    def fetch_eligible_universe(self) -> list[FnoUniverse]:
        """Fetch the current list of F&O-eligible symbols from the lot-size CSV."""
        url = f"{_ARCHIVES_LEGACY_URL}/content/fo/fo_mktlots.csv"

        resp = self._request_with_retry("GET", url)
        if resp.status_code == 404:
            raise FnoFetchError(f"fo_mktlots.csv not found at {url}")

        return self._parse_universe_csv(resp.text)

    def _parse_universe_csv(self, text: str) -> list[FnoUniverse]:
        """Parse fo_mktlots.csv and extract the SYMBOL column."""
        lines = text.splitlines()

        header_idx: int | None = None
        header_cols: list[str] = []
        for i, line in enumerate(lines):
            upper = line.upper()
            if "SYMBOL" in upper:
                header_cols = [c.strip() for c in line.split(",")]
                if "SYMBOL" in [c.upper() for c in header_cols]:
                    header_idx = i
                    break

        if header_idx is None:
            raise FnoFetchError("fo_mktlots.csv has no SYMBOL header row")

        # Find the SYMBOL column index (case-insensitive).
        sym_idx = next(
            i for i, c in enumerate(header_cols) if c.upper() == "SYMBOL"
        )

        today = date.today()
        seen: set[str] = set()
        universe: list[FnoUniverse] = []
        for line in lines[header_idx + 1:]:
            if not line.strip():
                continue
            cols = [c.strip() for c in line.split(",")]
            if sym_idx >= len(cols):
                continue
            symbol = cols[sym_idx].strip().upper()
            if not symbol or symbol == "TOTAL" or symbol.startswith("#"):
                continue
            if symbol in seen:
                continue
            seen.add(symbol)
            universe.append(FnoUniverse(
                symbol=symbol,
                eligible_since=today,
                last_verified=today,
            ))

        return universe

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> FnoClient:
        return self

    def __exit__(self, *a: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_row(raw: FnoContractRaw) -> FnoContract:
    """Convert a raw bhavcopy row into a typed FnoContract."""
    instrument = _INSTR_MAP.get(raw.FinInstrmTp.strip(), raw.FinInstrmTp.strip())

    # Options MUST carry a strike — the (trade_date, symbol, instrument,
    # expiry, strike, option_type) PK uses a -1 sentinel for NULL strikes,
    # so two OPTSTK rows with blank strikes would collide under INSERT OR
    # REPLACE. Futures legitimately have no strike (NSE writes "0" or blank).
    if instrument in ("OPTSTK", "OPTIDX") and not raw.StrkPric.strip():
        raise FnoFetchError(
            f"{instrument} row missing strike price: "
            f"symbol={raw.TckrSymb.strip()} expiry={raw.XpryDt} "
            f"trade_date={raw.TradDt}"
        )

    strike: float | None = (
        float(raw.StrkPric) if raw.StrkPric.strip() else None
    )
    # NSE writes "0" for futures strikes — treat 0 as None for futures.
    if instrument in ("FUTSTK", "FUTIDX"):
        strike = None

    option_type = raw.OptnTp.strip() or None
    turnover_rupees = float(raw.TtlTrfVal) if raw.TtlTrfVal.strip() else 0.0
    turnover_cr = turnover_rupees / 1e7

    return FnoContract(
        trade_date=date.fromisoformat(raw.TradDt),
        symbol=raw.TckrSymb.strip(),
        instrument=instrument,
        expiry_date=date.fromisoformat(raw.XpryDt),
        strike=strike,
        option_type=option_type,
        open=float(raw.OpnPric) if raw.OpnPric.strip() else None,
        high=float(raw.HghPric) if raw.HghPric.strip() else None,
        low=float(raw.LwPric) if raw.LwPric.strip() else None,
        close=float(raw.ClsPric) if raw.ClsPric.strip() else None,
        settle_price=float(raw.SttlmPric) if raw.SttlmPric.strip() else None,
        contracts_traded=(
            int(float(raw.TtlTradgVol)) if raw.TtlTradgVol.strip() else 0
        ),
        turnover_cr=turnover_cr,
        open_interest=int(float(raw.OpnIntrst)) if raw.OpnIntrst.strip() else 0,
        change_in_oi=(
            int(float(raw.ChngInOpnIntrst)) if raw.ChngInOpnIntrst.strip() else 0
        ),
        implied_volatility=None,  # not present in new bhavcopy format
    )


def _parse_int(val: object) -> int:
    """Parse an int tolerant of commas, whitespace, and decimal representations."""
    if val is None:
        return 0
    s = str(val).strip().replace(",", "")
    if not s or s == "-":
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _parse_expiry_str(s: str) -> date:
    """Parse an NSE option-chain expiry string with a small format cascade.

    Accepts `%d-%b-%Y` (e.g. "24-Apr-2026"), `%d-%b-%y` (e.g. "24-Apr-26"),
    or ISO `%Y-%m-%d`. Raises FnoFetchError with a clear message if none match.
    """
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise FnoFetchError(
        f"Option chain expiry parse failed ({s}): tried formats "
        f"%d-%b-%Y, %d-%b-%y, %Y-%m-%d"
    )


def _int_or_zero(val: object) -> int:
    """Coerce an option-chain numeric field to int, returning 0 on missing/malformed."""
    if val is None:
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _float_or_none(val: object) -> float | None:
    """Coerce an option-chain numeric field to float, returning None on missing/malformed."""
    if val is None or val == "":
        return None
    try:
        f = float(val)
    except (ValueError, TypeError):
        return None
    # NSE sometimes emits 0.0 for missing IV — preserve as 0.0, caller decides.
    return f
