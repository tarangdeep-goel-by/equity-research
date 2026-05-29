"""SEC EDGAR client — CIK resolution + XBRL companyfacts → US fundamentals
(US add-on, Phase 3.1).

This is the authoritative US fundamentals source. No API key is needed, but SEC
requires a descriptive ``User-Agent`` and a polite request rate (≤10 req/s). The
HTTP/throttle/CIK plumbing lives in :class:`SecEdgarBase` so the later Form 4 /
13F work (P3.3) can reuse it without dragging in the fundamentals normalizer.

Magnitude convention (matches ``_USD_VALIDATION_RULES`` in
``store_domains/_shared.py``): companyfacts reports raw USD, but the us_* tables
store monetary values in **USD millions**, so monetary tags are divided by 1e6
at normalize time. EPS stays raw per-share USD; share counts stay raw.

Period selection:
* **Annual** — duration facts from forms in (10-K, 20-F) with ``fp == 'FY'``;
  fiscal_year = calendar year of the period ``end`` date. Balance-sheet (instant)
  tags are joined to a fiscal year by matching the ``end`` instant to that year's
  fiscal year-end.
* **Quarterly** — duration facts from 10-Q with ``fp`` in (Q1, Q2, Q3);
  quarter_end = the fact's ``end`` date, fiscal_year/fiscal_period from the fact.
* **Restatement** — when several facts cover the same period, the most recently
  ``filed`` one wins (latest filing).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# SEC requires a descriptive UA. ≤10 req/s → ≥0.12s between calls (we use 0.12).
_USER_AGENT = "flowtracker-research tarangdeepgoel2000@gmail.com"
_MIN_INTERVAL = 0.12

_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{tag}.json"

_CACHE_DIR = Path.home() / ".cache" / "flowtracker"
_TICKERS_CACHE = _CACHE_DIR / "sec_company_tickers.json"

MAX_RETRIES = 4
BACKOFF_BASE = 1.0

# RANKED us-gaap tag candidates per normalized field; first present wins.
_ANNUAL_DURATION_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "net_income": ["NetIncomeLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}
# Capex (duration) used to derive free_cash_flow = OCF − capex.
_CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment"]

# Balance-sheet (instant) tags.
_INSTANT_TAGS: dict[str, list[str]] = {
    "total_assets": ["Assets"],
    "total_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "total_cash": ["CashAndCashEquivalentsAtCarryingValue"],
    "shares_outstanding": [
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding",
    ],
}
# Debt = LongTermDebtNoncurrent + DebtCurrent if available, else LongTermDebt.
_DEBT_NONCURRENT_TAGS = ["LongTermDebtNoncurrent"]
_DEBT_CURRENT_TAGS = ["DebtCurrent", "LongTermDebtCurrent"]
_DEBT_TOTAL_TAGS = ["LongTermDebt"]

# Quarterly normalized fields (duration facts only).
_QUARTERLY_TAGS: dict[str, list[str]] = {
    "revenue": _ANNUAL_DURATION_TAGS["revenue"],
    "net_income": _ANNUAL_DURATION_TAGS["net_income"],
    "eps": _ANNUAL_DURATION_TAGS["eps"],
}

_ANNUAL_FORMS = {"10-K", "20-F"}
_QUARTERLY_FORMS = {"10-Q"}
_USD_MILLIONS = 1e6


class EdgarError(Exception):
    """Raised when an EDGAR fetch permanently fails."""


class SecEdgarBase:
    """Reusable SEC HTTP base: UA header, ≤10 req/s throttle, retry/backoff,
    and CIK helpers. Form 4 / 13F (P3.3) should import and extend this."""

    def __init__(self, *, user_agent: str = _USER_AGENT) -> None:
        self._client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json, */*",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15.0, read=60.0, write=10.0, pool=10.0),
        )
        self._last_request = 0.0

    # -- throttling + request --

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)

    def _get_json(self, url: str) -> dict:
        """GET ``url`` and return parsed JSON, throttled + retried on 429/5xx."""
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            self._throttle()
            try:
                resp = self._client.get(url)
                self._last_request = time.monotonic()
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "EDGAR %s on %s, backing off %.1fs (attempt %d)",
                        resp.status_code, url, wait, attempt + 1,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError:
                raise
            except Exception as e:  # network / decode errors → retry
                last_error = e
                logger.warning("EDGAR attempt %d failed for %s: %s", attempt + 1, url, e)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE * (2 ** attempt))
        raise EdgarError(f"Failed after {MAX_RETRIES} attempts: {url}: {last_error}")

    # -- CIK helpers --

    @staticmethod
    def pad_cik(cik: str | int) -> str:
        """Zero-pad a CIK to the 10-digit form used by the data endpoints."""
        return str(cik).strip().lstrip("0").zfill(10) if str(cik).strip() else "".zfill(10)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SecEdgarBase":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


class EdgarClient(SecEdgarBase):
    """CIK resolution + companyfacts fetch + us-gaap → US fundamentals rows."""

    def __init__(self, *, user_agent: str = _USER_AGENT) -> None:
        super().__init__(user_agent=user_agent)
        self._ticker_map: dict[str, str] | None = None  # ticker → padded CIK

    # ------------------------------------------------------------------ #
    # CIK resolution
    # ------------------------------------------------------------------ #

    def _load_ticker_map(self) -> dict[str, str]:
        """Build/return the ticker→CIK10 map (in-memory + disk cache)."""
        if self._ticker_map is not None:
            return self._ticker_map
        raw: dict | None = None
        if _TICKERS_CACHE.exists():
            try:
                raw = json.loads(_TICKERS_CACHE.read_text())
            except (OSError, json.JSONDecodeError):
                raw = None
        if raw is None:
            raw = self._get_json(_TICKERS_URL)
            try:
                _CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _TICKERS_CACHE.write_text(json.dumps(raw))
            except OSError as e:  # pragma: no cover — cache write is best-effort
                logger.debug("Could not cache company_tickers: %s", e)
        self._ticker_map = {
            str(v["ticker"]).upper(): self.pad_cik(v["cik_str"])
            for v in raw.values()
            if v.get("ticker") and v.get("cik_str") is not None
        }
        return self._ticker_map

    def cik_for(self, ticker: str) -> str | None:
        """Return the zero-padded 10-digit CIK for ``ticker``, or None."""
        return self._load_ticker_map().get(ticker.strip().upper())

    def load_ticker_map_from(self, path: str | Path) -> dict[str, str]:
        """Load the ticker→CIK map from a local file (used by offline tests)."""
        raw = json.loads(Path(path).read_text())
        self._ticker_map = {
            str(v["ticker"]).upper(): self.pad_cik(v["cik_str"])
            for v in raw.values()
            if v.get("ticker") and v.get("cik_str") is not None
        }
        return self._ticker_map

    # ------------------------------------------------------------------ #
    # companyfacts
    # ------------------------------------------------------------------ #

    def fetch_company_facts(self, cik: str | int) -> dict:
        """Fetch the raw companyfacts JSON for a CIK (padded automatically)."""
        return self._get_json(_FACTS_URL.format(cik10=self.pad_cik(cik)))

    # ------------------------------------------------------------------ #
    # normalization
    # ------------------------------------------------------------------ #

    def normalize_annual(self, facts: dict, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Normalize companyfacts into ``us_annual_financials`` rows.

        One row per fiscal_year (calendar int from the period ``end``).
        """
        gaap = self._gaap(facts)
        # Duration facts keyed by fiscal_year (latest filing wins per period).
        duration: dict[int, dict[str, float]] = {}
        for field, tags in _ANNUAL_DURATION_TAGS.items():
            for fy, val in self._pick_annual_duration(gaap, tags).items():
                duration.setdefault(fy, {})[field] = val
        # Capex for FCF derivation.
        capex = self._pick_annual_duration(gaap, _CAPEX_TAGS)

        # Instant facts keyed by fiscal_year-end. We anchor fiscal years on the
        # set discovered from durations + Assets so instants align to FY-ends.
        instant: dict[int, dict[str, float]] = {}
        for field, tags in _INSTANT_TAGS.items():
            for fy, val in self._pick_annual_instant(gaap, tags, duration).items():
                instant.setdefault(fy, {})[field] = val
        debt = self._pick_annual_debt(gaap, duration)

        self._log_unmapped(gaap, symbol)

        rows: list[dict] = []
        years = sorted(set(duration) | set(instant) | set(debt))
        for fy in years:
            d = duration.get(fy, {})
            i = instant.get(fy, {})
            ocf = d.get("operating_cash_flow")
            cap = capex.get(fy)
            fcf = (ocf - cap) if (ocf is not None and cap is not None) else None
            row = {
                "symbol": symbol.upper(),
                "market": market,
                "currency": "USD",
                "fiscal_year": fy,
                "revenue": self._to_millions(d.get("revenue")),
                "net_income": self._to_millions(d.get("net_income")),
                "total_assets": self._to_millions(i.get("total_assets")),
                "total_equity": self._to_millions(i.get("total_equity")),
                "total_debt": self._to_millions(debt.get(fy)),
                "total_cash": self._to_millions(i.get("total_cash")),
                "eps": d.get("eps"),  # per-share USD, not scaled
                "operating_cash_flow": self._to_millions(ocf),
                "free_cash_flow": self._to_millions(fcf),
                "shares_outstanding": i.get("shares_outstanding"),  # raw count
            }
            rows.append(row)
        return rows

    def normalize_quarterly(self, facts: dict, symbol: str, market: str = "NASDAQ") -> list[dict]:
        """Normalize companyfacts into ``us_quarterly_financials`` rows.

        One row per quarter_end (the fact's ``end`` date), 10-Q Q1-Q3.
        """
        gaap = self._gaap(facts)
        # Keyed by quarter_end date string; latest filing wins.
        periods: dict[str, dict] = {}
        for field, tags in _QUARTERLY_TAGS.items():
            for end, info in self._pick_quarterly_duration(gaap, tags).items():
                slot = periods.setdefault(end, {})
                slot[field] = info["val"]
                slot.setdefault("fiscal_year", info["fy"])
                slot.setdefault("fiscal_period", info["fp"])

        rows: list[dict] = []
        for end in sorted(periods):
            p = periods[end]
            if p.get("fiscal_year") is None or p.get("fiscal_period") is None:
                continue
            rows.append({
                "symbol": symbol.upper(),
                "market": market,
                "currency": "USD",
                "quarter_end": end,
                "fiscal_year": p["fiscal_year"],
                "fiscal_period": p["fiscal_period"],
                "revenue": self._to_millions(p.get("revenue")),
                "net_income": self._to_millions(p.get("net_income")),
                "eps": p.get("eps"),  # per-share USD
            })
        return rows

    # ------------------------------------------------------------------ #
    # fact selection helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _gaap(facts: dict) -> dict:
        return facts.get("facts", {}).get("us-gaap", {})

    @staticmethod
    def _units(gaap: dict, tag: str) -> list[dict]:
        """All fact entries across this tag's units (one tag has one real unit)."""
        units = gaap.get(tag, {}).get("units", {})
        out: list[dict] = []
        for entries in units.values():
            out.extend(entries)
        return out

    @staticmethod
    def _is_annual_duration(f: dict) -> bool:
        return (
            f.get("form") in _ANNUAL_FORMS
            and f.get("fp") == "FY"
            and f.get("start")
            and f.get("end")
        )

    def _pick_annual_duration(self, gaap: dict, tags: list[str]) -> dict[int, float]:
        """fiscal_year → value for the first present tag, latest filing wins.

        Annual durations are guarded to span ~a full year (>300 days) so a
        stray Q4-only or stub period can't masquerade as the annual figure.
        """
        for tag in tags:
            best: dict[int, dict] = {}  # fy → {val, filed}
            for f in self._units(gaap, tag):
                if not self._is_annual_duration(f):
                    continue
                if self._span_days(f) < 300:
                    continue
                fy = int(f["end"][:4])
                filed = f.get("filed", "")
                if fy not in best or filed > best[fy]["filed"]:
                    best[fy] = {"val": float(f["val"]), "filed": filed}
            if best:
                return {fy: v["val"] for fy, v in best.items()}
        return {}

    def _pick_annual_instant(
        self, gaap: dict, tags: list[str], duration: dict[int, dict],
    ) -> dict[int, float]:
        """fiscal_year → instant value, anchored to FY-end, latest filing wins.

        The fiscal year of an instant fact is the calendar year of its ``end``
        date. Multiple instants can land in the same calendar year (quarter-ends);
        we keep the one whose ``end`` is latest in the year (≈ fiscal year-end)
        and, among those, the latest-filed.
        """
        for tag in tags:
            best: dict[int, dict] = {}  # fy → {val, end, filed}
            for f in self._units(gaap, tag):
                end = f.get("end")
                if not end:
                    continue
                fy = int(end[:4])
                filed = f.get("filed", "")
                cur = best.get(fy)
                if cur is None or (end, filed) > (cur["end"], cur["filed"]):
                    best[fy] = {"val": float(f["val"]), "end": end, "filed": filed}
            if best:
                return {fy: v["val"] for fy, v in best.items()}
        return {}

    def _pick_annual_debt(self, gaap: dict, duration: dict[int, dict]) -> dict[int, float]:
        """Total debt per fiscal_year: noncurrent + current, else LongTermDebt."""
        noncurrent = self._pick_annual_instant(gaap, _DEBT_NONCURRENT_TAGS, duration)
        current = self._pick_annual_instant(gaap, _DEBT_CURRENT_TAGS, duration)
        if noncurrent:
            return {
                fy: noncurrent[fy] + current.get(fy, 0.0)
                for fy in noncurrent
            }
        return self._pick_annual_instant(gaap, _DEBT_TOTAL_TAGS, duration)

    def _pick_quarterly_duration(self, gaap: dict, tags: list[str]) -> dict[str, dict]:
        """quarter_end → {val, fy, fp} for the first present tag, latest filing wins.

        10-Q duration facts with fp in (Q1,Q2,Q3) spanning a single quarter
        (60-100 days) — guards against 6-/9-month cumulative durations that 10-Qs
        also report under the same tag.
        """
        for tag in tags:
            best: dict[str, dict] = {}  # end → {val, fy, fp, filed}
            for f in self._units(gaap, tag):
                if f.get("form") not in _QUARTERLY_FORMS:
                    continue
                fp = f.get("fp")
                if fp not in {"Q1", "Q2", "Q3"}:
                    continue
                if not f.get("end"):
                    continue
                # EPS/instant-ish facts have no start; durations do. For revenue/NI
                # require a single-quarter span; EPS has start too on 10-Qs.
                if f.get("start") and self._span_days(f) > 100:
                    continue
                end = f["end"]
                filed = f.get("filed", "")
                if end not in best or filed > best[end]["filed"]:
                    best[end] = {
                        "val": float(f["val"]),
                        "fy": f.get("fy"),
                        "fp": fp,
                        "filed": filed,
                    }
            if best:
                return {
                    end: {"val": v["val"], "fy": v["fy"], "fp": v["fp"]}
                    for end, v in best.items()
                }
        return {}

    @staticmethod
    def _span_days(f: dict) -> int:
        from datetime import date

        try:
            s = date.fromisoformat(f["start"])
            e = date.fromisoformat(f["end"])
            return (e - s).days
        except (KeyError, ValueError):
            return 0

    @staticmethod
    def _to_millions(val: float | None) -> float | None:
        return None if val is None else round(val / _USD_MILLIONS, 4)

    def _log_unmapped(self, gaap: dict, symbol: str) -> None:
        """Log normalized fields that found no candidate tag (diagnostics)."""
        for field, tags in {**_ANNUAL_DURATION_TAGS, **_INSTANT_TAGS}.items():
            if not any(t in gaap for t in tags):
                logger.info("EDGAR %s: no us-gaap tag for '%s' (tried %s)", symbol, field, tags)
        if not any(t in gaap for t in (_DEBT_NONCURRENT_TAGS + _DEBT_TOTAL_TAGS)):
            logger.info("EDGAR %s: no us-gaap tag for 'total_debt'", symbol)
