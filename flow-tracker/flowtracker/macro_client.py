"""Macro indicator client — yfinance for VIX/FX/crude, CCIL for G-sec yield, RBI WSS for system credit."""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timedelta

import httpx
import yfinance as yf

from flowtracker.macro_models import MacroSnapshot, MacroSystemCredit, USMacroSnapshot

logger = logging.getLogger(__name__)

_VIX_TICKER = "^INDIAVIX"
_USDINR_TICKER = "USDINR=X"
_EURINR_TICKER = "EURINR=X"
_GBPINR_TICKER = "GBPINR=X"
_BRENT_TICKER = "BZ=F"

# US macro tickers (US add-on). All free on yfinance (no API key — same as
# India). CBOE yield indices (^IRX/^FVX/^TNX/^TYX) publish Close as the yield
# in percent already, so they're stored as-is (matching India gsec_* percent).
_US_VIX_TICKER = "^VIX"          # CBOE Volatility Index
_DXY_TICKER = "DX-Y.NYB"         # US Dollar Index
_UST_3M_TICKER = "^IRX"          # 13-week T-bill yield %
_UST_5Y_TICKER = "^FVX"          # 5Y Treasury yield %
_UST_10Y_TICKER = "^TNX"         # 10Y Treasury yield %
_UST_30Y_TICKER = "^TYX"         # 30Y Treasury yield %
_WTI_TICKER = "CL=F"             # WTI crude USD/barrel
_US_BRENT_TICKER = "BZ=F"        # Brent crude USD/barrel
_GOLD_TICKER = "GC=F"            # Gold USD/oz

# Ticker → USMacroSnapshot field name.
_US_MACRO_FIELD_MAP: dict[str, str] = {
    _US_VIX_TICKER: "vix",
    _DXY_TICKER: "dxy",
    _UST_3M_TICKER: "ust_3m",
    _UST_5Y_TICKER: "ust_5y",
    _UST_10Y_TICKER: "ust_10y",
    _UST_30Y_TICKER: "ust_30y",
    _WTI_TICKER: "wti_crude",
    _US_BRENT_TICKER: "brent_crude",
    _GOLD_TICKER: "gold",
}

# Default yfinance ticker set for `fetch_index_prices`. These cover the
# broad-market and major sectoral indices that have working yfinance
# symbols (probed 2026-05-26). Tickers without working yfinance feeds
# (Healthcare, India Defence, MNC niche themes, Private Bank, etc.) are
# intentionally omitted — adding them just logs a warning + skips and
# adds no value. ^BSESN (BSE Sensex) is included as a non-Nifty broad
# benchmark.
INDEX_TICKERS: tuple[str, ...] = (
    # Broad-market
    "^NSEI",        # Nifty 50
    "^CRSLDX",      # Nifty 500
    "^CNX100",      # Nifty 100
    "^CNX200",      # Nifty 200
    "^CRSMID",      # Nifty Midcap 100 (CRSMID = CRISIL Midcap on Yahoo)
    "^NSEMDCP50",   # Nifty Midcap 50
    "^BSESN",       # BSE Sensex (non-Nifty broad benchmark)
    # Sectoral
    "^NSEBANK",     # Nifty Bank
    "^CNXIT",       # Nifty IT
    "^CNXPHARMA",   # Nifty Pharma
    "^CNXAUTO",     # Nifty Auto
    "^CNXFMCG",     # Nifty FMCG
    "^CNXMETAL",    # Nifty Metal
    "^CNXENERGY",   # Nifty Energy
    "^CNXREALTY",   # Nifty Realty
    "^CNXPSUBANK",  # Nifty PSU Bank
    "NIFTY_FIN_SERVICE.NS",  # Nifty Financial Services
    # Thematic
    "^CNXSERVICE",  # Nifty Service Sector
    "^CNXMEDIA",    # Nifty Media
    "^CNXCONSUM",   # Nifty Consumption
    "^CNXINFRA",    # Nifty Infrastructure
    "^CNXMNC",      # Nifty MNC
)

_CCIL_URL = "https://www.ccilindia.com/web/ccil/tenorwise-indicative-yields"

_RBI_WSS_INDEX_URL = "https://rbi.org.in/Scripts/BS_viewWssExtract.aspx"
_RBI_WSS_DETAIL_URL = "https://rbi.org.in/Scripts/BS_viewWssExtract.aspx?SelectedDate={date}"

# Plausible-yield band — anything outside is parser confusion (likely the
# wrong column matched, e.g. the security coupon rather than YTM).
_GSEC_VALID_RANGE: tuple[float, float] = (3.0, 12.0)


def _parse_ccil_tenor(html: str, tenor_re: str, *, label: str) -> float | None:
    """Extract a single tenor's YTM from a CCIL Tenorwise Indicative Yields
    HTML page. Returns the parsed yield in percent or ``None`` if not found
    / outside [3.0, 12.0].

    Three layered patterns (most-specific first) so legacy 2-column test
    fixtures and the live 3-column site both work:

    1. ``<td>TENOR</td><td>...%...</td><td>YTM</td>`` — current CCIL.
    2. ``<td>TENOR</td><td>YTM</td>`` — simplified 2-column legacy.
    3. ``TENOR ... YTM`` — last-resort prose pattern.
    """
    match = re.search(
        tenor_re + r'\s*</td>'
        r'\s*<td[^>]*>[^<]*%[^<]*</td>'
        r'\s*<td[^>]*>\s*(\d+\.\d+)\s*</td>',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not match:
        match = re.search(
            tenor_re + r'\s*</td>\s*<td[^>]*>\s*(\d+\.\d+)\s*</td>',
            html, re.DOTALL | re.IGNORECASE,
        )
    if not match:
        match = re.search(
            tenor_re + r'[^0-9]*?(\d+\.\d+)',
            html, re.DOTALL | re.IGNORECASE,
        )
    if not match:
        logger.warning(
            "CCIL G-sec yield-curve scrape: tenor %s not found in page",
            label,
        )
        return None
    try:
        value = round(float(match.group(1)), 2)
    except (TypeError, ValueError):
        return None
    lo, hi = _GSEC_VALID_RANGE
    if not (lo <= value <= hi):
        logger.warning(
            "CCIL G-sec %s yield %.4f outside plausible [%s, %s] band — dropping",
            label, value, lo, hi,
        )
        return None
    return value


class MacroClient:
    """Client for macro indicators: VIX, USD/INR, Brent crude, 10Y G-sec."""

    def __init__(self) -> None:
        # follow_redirects=True is required for RBI WSS — every
        # ``BS_viewWssExtract.aspx?SelectedDate=...`` returns a 302 to the
        # canonical ``BS_ViewWssExtractdetails.aspx?id=...`` URL. Without
        # following, we get no body. CCIL doesn't redirect, so this is a
        # safe across-the-board default.
        self._http = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        )

    def fetch_snapshot(self, days: int = 5) -> list[MacroSnapshot]:
        """Fetch recent N days of macro data from yfinance + CCIL.

        CCIL only publishes today\'s yield-curve snapshot (1Y/5Y/10Y/30Y).
        Without carry-forward, prior-day rows get NULL yields permanently
        (this function never revisits them). G-sec yields move <5bps/day
        typically, so we carry today\'s values back to every day in the
        window — well within analytical tolerance.
        """
        period = f"{days}d"
        tickers = [
            _VIX_TICKER, _USDINR_TICKER, _EURINR_TICKER, _GBPINR_TICKER,
            _BRENT_TICKER,
        ]

        data: dict[str, dict[str, float]] = {}

        for ticker_sym in tickers:
            try:
                hist = yf.Ticker(ticker_sym).history(period=period)
                for idx, row in hist.iterrows():
                    d = idx.strftime("%Y-%m-%d")
                    close = row["Close"]
                    if math.isnan(close):
                        continue
                    data.setdefault(d, {})[ticker_sym] = round(close, 4)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", ticker_sym, e)

        # Today\'s full yield curve (also used to backfill prior days)
        curve = self._fetch_gsec_curve()

        snapshots: list[MacroSnapshot] = []
        for d in sorted(data.keys()):
            vals = data[d]
            snapshots.append(MacroSnapshot(
                date=d,
                india_vix=vals.get(_VIX_TICKER),
                usd_inr=vals.get(_USDINR_TICKER),
                eur_inr=vals.get(_EURINR_TICKER),
                gbp_inr=vals.get(_GBPINR_TICKER),
                brent_crude=vals.get(_BRENT_TICKER),
                gsec_1y=curve.get("1y"),
                gsec_5y=curve.get("5y"),
                gsec_10y=curve.get("10y"),
                gsec_30y=curve.get("30y"),
            ))

        return snapshots

    def fetch_us_macro_snapshot(self, days: int = 5) -> list[USMacroSnapshot]:
        """Fetch recent N days of US macro data from yfinance (US add-on).

        Mirrors ``fetch_snapshot`` for the US market — batch-downloads each
        ticker's recent history, one row per trading date with the fields that
        resolved. A ticker that fails or returns empty leaves its field as
        ``None`` (resilient — never aborts the whole snapshot). Treasury yields
        (^IRX/^FVX/^TNX/^TYX) are stored as-is in percent.
        """
        period = f"{days}d"
        data: dict[str, dict[str, float]] = {}

        for ticker_sym, field in _US_MACRO_FIELD_MAP.items():
            try:
                hist = yf.Ticker(ticker_sym).history(period=period)
                for idx, row in hist.iterrows():
                    d = idx.strftime("%Y-%m-%d")
                    close = row["Close"]
                    if close is None or math.isnan(close):
                        continue
                    data.setdefault(d, {})[field] = round(close, 4)
            except Exception as e:
                logger.warning("Failed to fetch US macro %s: %s", ticker_sym, e)

        snapshots: list[USMacroSnapshot] = []
        for d in sorted(data.keys()):
            vals = data[d]
            snapshots.append(USMacroSnapshot(
                date=d,
                vix=vals.get("vix"),
                dxy=vals.get("dxy"),
                ust_3m=vals.get("ust_3m"),
                ust_5y=vals.get("ust_5y"),
                ust_10y=vals.get("ust_10y"),
                ust_30y=vals.get("ust_30y"),
                wti_crude=vals.get("wti_crude"),
                brent_crude=vals.get("brent_crude"),
                gold=vals.get("gold"),
            ))

        return snapshots

    def fetch_history(self, start: str = "2008-01-01") -> list[MacroSnapshot]:
        """Fetch full history via yfinance. G-sec only assigned to most-recent row.

        Historical 10Y G-sec yields can\'t be reconstructed from CCIL (they
        only publish today\'s snapshot), so historical rows leave gsec_10y
        as None. Today\'s scraped value is assigned to the latest row.
        """
        end = date.today().isoformat()
        data: dict[str, dict[str, float]] = {}

        for ticker_sym in [
            _VIX_TICKER, _USDINR_TICKER, _EURINR_TICKER, _GBPINR_TICKER,
            _BRENT_TICKER,
        ]:
            try:
                hist = yf.Ticker(ticker_sym).history(start=start, end=end)
                for idx, row in hist.iterrows():
                    d = idx.strftime("%Y-%m-%d")
                    close = row["Close"]
                    if math.isnan(close):
                        continue
                    data.setdefault(d, {})[ticker_sym] = round(close, 4)
            except Exception as e:
                logger.warning("Failed to fetch history for %s: %s", ticker_sym, e)

        curve = self._fetch_gsec_curve()
        sorted_dates = sorted(data.keys())
        latest_date = sorted_dates[-1] if sorted_dates else None

        snapshots: list[MacroSnapshot] = []
        for d in sorted_dates:
            vals = data[d]
            is_latest = d == latest_date
            snapshots.append(MacroSnapshot(
                date=d,
                india_vix=vals.get(_VIX_TICKER),
                usd_inr=vals.get(_USDINR_TICKER),
                eur_inr=vals.get(_EURINR_TICKER),
                gbp_inr=vals.get(_GBPINR_TICKER),
                brent_crude=vals.get(_BRENT_TICKER),
                gsec_1y=curve.get("1y") if is_latest else None,
                gsec_5y=curve.get("5y") if is_latest else None,
                gsec_10y=curve.get("10y") if is_latest else None,
                gsec_30y=curve.get("30y") if is_latest else None,
            ))

        return snapshots

    def fetch_index_prices(
        self,
        tickers: list[str] | None = None,
        period: str = "3y",
    ) -> list[dict]:
        """Fetch daily closing prices for Nifty index tickers via yfinance.

        Defaults to ``INDEX_TICKERS`` (broad + sectoral + thematic Nifty
        indices that have working yfinance feeds). Tickers that return
        empty histories (delisted / unsupported) are logged + skipped —
        the call does not raise.

        Returns list of dicts:
            [{"date": "YYYY-MM-DD", "index_ticker": "^CRSLDX", "close": 12345.67}, ...]
        """
        if tickers is None:
            tickers = list(INDEX_TICKERS)

        records: list[dict] = []
        skipped: list[str] = []
        for ticker_sym in tickers:
            try:
                hist = yf.Ticker(ticker_sym).history(period=period)
            except Exception as e:
                logger.warning("Failed to fetch index prices for %s: %s", ticker_sym, e)
                skipped.append(ticker_sym)
                continue
            if hist.empty:
                logger.warning(
                    "No data for index %s on yfinance — skipping", ticker_sym,
                )
                skipped.append(ticker_sym)
                continue
            ticker_records = 0
            for idx, row in hist.iterrows():
                close = row["Close"]
                if math.isnan(close):
                    continue
                records.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "index_ticker": ticker_sym,
                    "close": round(close, 2),
                })
                ticker_records += 1
            if ticker_records == 0:
                skipped.append(ticker_sym)

        if skipped:
            logger.info("Index price fetch skipped %d ticker(s): %s",
                        len(skipped), ", ".join(skipped))
        logger.info("Fetched %d index price records across %d tickers",
                    len(records), len(tickers) - len(skipped))
        return records

    # CCIL tenor buckets we extract. The page lists ~15 buckets; we sample
    # the four that map naturally to a "yield curve" (short / belly / long /
    # ultra-long). Each is the canonical analyst comparable.
    # CCIL now publishes point-tenor range buckets (e.g. "1Y-2Y", "28Y-30Y")
    # rather than the old "0Y-1Y" / "19Y-Above" labels. Each pattern anchors on
    # the FULL bucket label so the leading digit can't accidentally match the
    # "1" inside neighbouring "10Y" / "13Y" / "15Y" buckets — the tenor regex
    # is always immediately followed by "</td>" in _parse_ccil_tenor.
    _CCIL_TENOR_BUCKETS: tuple[tuple[str, str], ...] = (
        ("1y", r"1\s*Y\s*[-–]\s*2\s*Y"),
        ("5y", r"4\s*Y\s*[-–]\s*5\s*Y"),
        ("10y", r"9\s*Y\s*[-–]\s*10\s*Y"),
        ("30y", r"28\s*Y\s*[-–]\s*30\s*Y"),
    )

    def _fetch_gsec_curve(self) -> dict[str, float | None]:
        """Scrape CCIL for the full G-sec yield curve (1Y / 5Y / 10Y / 30Y).

        Returns a dict ``{"1y": ..., "5y": ..., "10y": ..., "30y": ...}``;
        any tenor that fails parsing or validation is ``None`` in the result.
        A network failure returns all-Nones (the caller handles by emitting
        NULLs).

        CCIL Tenorwise Indicative Yields table layout (4 columns):
            Date | Tenor Bucket | Security | YTM (%)

        The Security column contains text like '6.33% GS 2035' — the leading
        coupon there must NOT be confused with the YTM. We locate the tenor
        cell, then walk past the Security cell (which contains '%') to the
        next numeric ``<td>`` cell — that is the YTM. Each parsed value is
        validated against [3.0, 12.0] (regime-wide plausible band); anything
        outside is dropped to None.
        """
        try:
            resp = self._http.get(_CCIL_URL)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error("Failed to fetch G-sec yield curve from CCIL: %s", e)
            return {key: None for key, _ in self._CCIL_TENOR_BUCKETS}

        out: dict[str, float | None] = {}
        for key, tenor_re in self._CCIL_TENOR_BUCKETS:
            out[key] = _parse_ccil_tenor(html, tenor_re, label=key)
        return out

    def _fetch_gsec_yield(self) -> float | None:
        """Legacy single-tenor 10Y wrapper retained for back-compat with the
        existing cron / tests. Equivalent to ``_fetch_gsec_curve()["10y"]``.
        """
        return self._fetch_gsec_curve().get("10y")

    def _list_wss_release_dates(self) -> list[str]:
        """Return RBI WSS release dates ('M/DD/YYYY') ordered most-recent-FIRST.

        Reads the WSS Extract index page and harvests every ``SelectedDate=...``
        link. The page itself lists the past ~4 weeks oldest-first
        (lnk2=earliest ... lnk23=latest), so we de-dupe in-place then reverse
        to return newest-first. Returns ``[]`` on failure.
        """
        try:
            resp = self._http.get(_RBI_WSS_INDEX_URL)
            resp.raise_for_status()
            dates = re.findall(r'SelectedDate=(\d+/\d+/\d+)', resp.text)
            seen: set[str] = set()
            ordered: list[str] = []
            for d in dates:
                if d not in seen:
                    seen.add(d)
                    ordered.append(d)
            # Sort by parsed date (most-recent first) so callers can
            # rely on releases[0] being the latest WSS regardless of how
            # RBI orders the index page.
            def _key(d: str) -> tuple[int, int, int]:
                try:
                    dt = datetime.strptime(d, "%m/%d/%Y")
                    return (dt.year, dt.month, dt.day)
                except Exception:
                    return (0, 0, 0)
            ordered.sort(key=_key, reverse=True)
            return ordered
        except Exception as e:
            logger.error("Failed to list RBI WSS release dates: %s", e)
            return []

    @staticmethod
    def _parse_wss_release_date(raw: str) -> str | None:
        """Convert RBI's 'M/DD/YYYY' release-date param to ISO 'YYYY-MM-DD'."""
        try:
            dt = datetime.strptime(raw, "%m/%d/%Y")
            return dt.date().isoformat()
        except Exception:
            return None

    def _fetch_rbi_wss(self, selected_date: str | None = None) -> MacroSystemCredit | None:
        """Scrape RBI WSS Section 4 (SCB Business) + Section 6 (Money Stock).

        Source: ``BS_viewWssExtract.aspx?SelectedDate=M/DD/YYYY``. Returns the
        most recent release if ``selected_date`` is ``None``. Returns ``None``
        on any failure or if extracted values fall outside plausible ranges.

        Section 4 (Scheduled Commercial Banks - Business in India) layout
        after stripping HTML to whitespace-collapsed text::

            ... Outstanding as on <Date> | Variation over Fortnight | FY 2024-25 | FY 2025-26 | YoY 2025 | YoY 2026
            2.1 Aggregate Deposits   <D_out> <D_fn> <D_fy_prev> <D_fy_curr> <D_yoy_prev> <D_yoy_curr>
            2.1a Growth (Per cent)   <%_fn>  <%_fy_prev> <%_fy_curr> <%_yoy_prev> <%_yoy_curr>
            ... 7 Bank Credit          <C_out> <C_fn> ...
            7.1a Growth (Per cent)   <%_fn>  ...
            7a.2 Non-food credit     <NFC_out> ...

        We parse:
            - Aggregate Deposits outstanding (col 1) + YoY current-year growth
              (last value on the 2.1a Growth line)
            - Bank Credit outstanding + YoY current-year growth (7.1a Growth)
            - Non-food credit outstanding (used to compute non-food YoY where
              the WSS doesn't expose a growth row — fallback)
            - CD ratio = bank_credit / aggregate_deposits

        Section 6 (Money Stock) gives M3 outstanding + YoY growth % — we pick
        the trailing "% YoY current year" cell from the M3 row.

        All values sanity-checked: deposit/credit growth in [-5, 30],
        CD ratio in [60, 95], M3 growth in [-5, 30]. Out-of-range values are
        dropped (set to None) rather than persisted.
        """
        try:
            if selected_date is None:
                releases = self._list_wss_release_dates()
                if not releases:
                    logger.warning("RBI WSS: no release dates discovered on index page")
                    return None
                selected_date = releases[0]

            url = _RBI_WSS_DETAIL_URL.format(date=selected_date)
            resp = self._http.get(url)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error("Failed to fetch RBI WSS extract: %s", e)
            return None

        try:
            # Strip tags + collapse whitespace for stable line-oriented parsing.
            clean = re.sub(r'<[^>]+>', ' ', html)
            clean = re.sub(r'\s+', ' ', clean).strip()
        except Exception as e:
            logger.error("Failed to clean WSS HTML: %s", e)
            return None

        release_iso = self._parse_wss_release_date(selected_date) or selected_date

        # As-of date (fortnight end) — appears in Section 4 header as
        # "Outstanding as on <Mon. DD, YYYY>". Best-effort capture.
        as_of_iso: str | None = None
        m = re.search(
            r'Outstanding as on\s+([A-Z][a-z]{2,3})\.?\s+(\d{1,2}),?\s+(\d{4})',
            clean,
        )
        if m:
            try:
                month_str = m.group(1).rstrip('.')
                # Try short ("Apr") and long ("April") month names
                for fmt in ("%b %d %Y", "%B %d %Y"):
                    try:
                        dt = datetime.strptime(f"{month_str} {m.group(2)} {m.group(3)}", fmt)
                        as_of_iso = dt.date().isoformat()
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Helper: pick floats out of a stretch of text.
        def _floats(s: str, n: int) -> list[float]:
            return [float(x) for x in re.findall(r'-?\d+\.\d+|-?\d+', s)[:n]]

        deposits_out: float | None = None
        credit_out: float | None = None
        non_food_credit_out: float | None = None
        deposit_growth: float | None = None
        credit_growth: float | None = None
        non_food_credit_growth: float | None = None
        m3_growth: float | None = None

        # Strategy: each labeled row contains a bounded run of numeric tokens
        # followed by the *next* labeled row. We capture the entire numeric
        # tail using a greedy match against [\d\.\-\s] up to the next label
        # (which always starts with a digit-dot pattern like "2.1.1 Demand"
        # or contains alphabetic words). Lazy capture to "2.2" or "2.1a" was
        # broken because percentage rows themselves contain values like
        # "2.2", "1.2" that prematurely terminate the regex.
        # Anchor on the FIRST occurrence of the next *non-numeric* token.
        def _row_numerics(label_pattern: str, next_label_re: str, n: int) -> list[float]:
            """Return up to n numeric tokens after `label_pattern` until
            `next_label_re` is encountered. Both patterns are matched against
            the cleaned, whitespace-collapsed text.
            """
            m_label = re.search(label_pattern, clean)
            if not m_label:
                return []
            tail = clean[m_label.end():]
            m_next = re.search(next_label_re, tail)
            stretch = tail[:m_next.start()] if m_next else tail[:400]
            return _floats(stretch, n)

        # 2.1 Aggregate Deposits — outstanding is first numeric on the row.
        # Next labeled row is "2.1a Growth (Per cent)" (always present).
        nums = _row_numerics(
            r'2\.1\s+Aggregate Deposits\b',
            r'2\.1a\s+Growth',
            6,
        )
        if nums:
            deposits_out = nums[0]

        # 2.1a Growth (Per cent) — 5 percentage values; last is YoY current year.
        # Next labeled row is "2.1.1 Demand".
        nums = _row_numerics(
            r'2\.1a\s+Growth\s*\(Per cent\)',
            r'2\.1\.1\s+Demand',
            5,
        )
        if nums:
            deposit_growth = nums[-1]

        # 7 Bank Credit — outstanding is first numeric. Next row is
        # "7.1a Growth (Per cent)".
        nums = _row_numerics(
            r'\b7\s+Bank Credit\b',
            r'7\.1a\s+Growth',
            6,
        )
        if nums:
            credit_out = nums[0]

        # 7.1a Growth (Per cent) — 5 values; last is YoY current year.
        # Next labeled row is "7a.1 Food Credit".
        nums = _row_numerics(
            r'7\.1a\s+Growth\s*\(Per cent\)',
            r'7a\.1\s+Food Credit',
            5,
        )
        if nums:
            credit_growth = nums[-1]

        # 7a.2 Non-food credit — 6 numeric values. Next is "Note:" or "8 ".
        nums = _row_numerics(
            r'7a\.2\s+Non-food credit',
            r'(?:Note:|\b8\s+[A-Z])',
            6,
        )
        if nums:
            non_food_credit_out = nums[0]
            # If WSS does not give a non-food growth row, derive it from
            # YoY-current-year variation (last numeric) and outstanding.
            if len(nums) >= 6 and nums[0]:
                yoy_var = nums[5]
                prev_year_out = nums[0] - yoy_var
                if prev_year_out > 0:
                    non_food_credit_growth = round(yoy_var / prev_year_out * 100, 1)

        # Section 6: M3 row — 12 numeric cells (alt outstanding | outstanding,
        # then 5 (Amount, %) pairs). Last value is YoY current-year %.
        # Next labeled row is "1 Components" or "1.1 Currency".
        nums = _row_numerics(
            r'\bM3\b',
            r'(?:1\s+Components|1\.1\s+Currency)',
            12,
        )
        if nums:
            if len(nums) >= 12:
                m3_growth = nums[-1]
            elif len(nums) >= 5 and abs(nums[-1]) <= 30:
                # Compact-layout fallback (last percent is YoY current).
                m3_growth = nums[-1]

        # Sanity-check ranges. Out-of-range -> drop to None (do not persist).
        def _validate(v: float | None, lo: float, hi: float, label: str) -> float | None:
            if v is None:
                return None
            if not (lo <= v <= hi):
                logger.warning(
                    "RBI WSS: %s=%s outside plausible [%s, %s] range — dropping",
                    label, v, lo, hi,
                )
                return None
            return v

        deposit_growth = _validate(deposit_growth, -5.0, 30.0, "deposit_growth_yoy")
        credit_growth = _validate(credit_growth, -5.0, 30.0, "credit_growth_yoy")
        non_food_credit_growth = _validate(
            non_food_credit_growth, -5.0, 30.0, "non_food_credit_growth_yoy",
        )
        m3_growth = _validate(m3_growth, -5.0, 30.0, "m3_growth_yoy")

        # CD ratio is computed from outstandings (more reliable than parsed)
        cd_ratio: float | None = None
        if deposits_out and credit_out and deposits_out > 0:
            cd_ratio = round(credit_out / deposits_out * 100, 2)
        cd_ratio = _validate(cd_ratio, 60.0, 95.0, "cd_ratio")

        # Outstanding sanity: in ₹ Cr, SCB deposits should be in lakhs of crores.
        # Late-2025 deposit outstanding sits ~26-30L Cr (i.e. 2.6e7 to 3.0e7).
        if deposits_out is not None and not (1_000_000 <= deposits_out <= 100_000_000):
            logger.warning(
                "RBI WSS: aggregate_deposits_cr=%s outside plausible 1e6-1e8 ₹Cr — dropping",
                deposits_out,
            )
            deposits_out = None
        if credit_out is not None and not (1_000_000 <= credit_out <= 100_000_000):
            logger.warning(
                "RBI WSS: bank_credit_cr=%s outside plausible 1e6-1e8 ₹Cr — dropping",
                credit_out,
            )
            credit_out = None

        # If literally nothing parsed, treat as a parser failure.
        any_value = any(
            v is not None for v in (
                deposits_out, credit_out, deposit_growth, credit_growth,
                non_food_credit_growth, m3_growth, cd_ratio,
            )
        )
        if not any_value:
            logger.error(
                "RBI WSS: parser extracted no values from %s — page layout may have changed",
                url,
            )
            return None

        return MacroSystemCredit(
            release_date=release_iso,
            as_of_date=as_of_iso,
            aggregate_deposits_cr=deposits_out,
            bank_credit_cr=credit_out,
            deposit_growth_yoy=deposit_growth,
            credit_growth_yoy=credit_growth,
            non_food_credit_growth_yoy=non_food_credit_growth,
            cd_ratio=cd_ratio,
            m3_growth_yoy=m3_growth,
            source="RBI_WSS",
        )

    def fetch_system_credit(self) -> MacroSystemCredit | None:
        """Public wrapper around ``_fetch_rbi_wss`` for the latest release."""
        return self._fetch_rbi_wss()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MacroClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
