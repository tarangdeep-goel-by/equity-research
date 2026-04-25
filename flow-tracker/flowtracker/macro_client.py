"""Macro indicator client — yfinance for VIX/FX/crude, CCIL for G-sec yield, RBI WSS for system credit."""

from __future__ import annotations

import logging
import math
import re
from datetime import date, datetime, timedelta

import httpx
import yfinance as yf

from flowtracker.macro_models import MacroSnapshot, MacroSystemCredit

logger = logging.getLogger(__name__)

_VIX_TICKER = "^INDIAVIX"
_USDINR_TICKER = "USDINR=X"
_BRENT_TICKER = "BZ=F"

_CCIL_URL = "https://www.ccilindia.com/web/ccil/tenorwise-indicative-yields"

_RBI_WSS_INDEX_URL = "https://rbi.org.in/Scripts/BS_viewWssExtract.aspx"
_RBI_WSS_DETAIL_URL = "https://rbi.org.in/Scripts/BS_viewWssExtract.aspx?SelectedDate={date}"


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

        CCIL only publishes today\'s 10Y yield snapshot. Without carry-forward,
        prior-day rows get gsec_10y=None permanently (this function never
        revisits them). The 10Y yield moves <5bps/day typically, so we carry
        today\'s value back to every day in the window — well within
        analytical tolerance.
        """
        period = f"{days}d"
        tickers = [_VIX_TICKER, _USDINR_TICKER, _BRENT_TICKER]

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

        # Try to get today\'s G-sec yield (also used to backfill prior days)
        gsec = self._fetch_gsec_yield()

        snapshots: list[MacroSnapshot] = []
        for d in sorted(data.keys()):
            vals = data[d]
            snapshots.append(MacroSnapshot(
                date=d,
                india_vix=vals.get(_VIX_TICKER),
                usd_inr=vals.get(_USDINR_TICKER),
                brent_crude=vals.get(_BRENT_TICKER),
                gsec_10y=gsec,
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

        for ticker_sym in [_VIX_TICKER, _USDINR_TICKER, _BRENT_TICKER]:
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

        gsec = self._fetch_gsec_yield()
        sorted_dates = sorted(data.keys())
        latest_date = sorted_dates[-1] if sorted_dates else None

        snapshots: list[MacroSnapshot] = []
        for d in sorted_dates:
            vals = data[d]
            snapshots.append(MacroSnapshot(
                date=d,
                india_vix=vals.get(_VIX_TICKER),
                usd_inr=vals.get(_USDINR_TICKER),
                brent_crude=vals.get(_BRENT_TICKER),
                gsec_10y=gsec if d == latest_date else None,
            ))

        return snapshots

    def fetch_index_prices(
        self,
        tickers: list[str] | None = None,
        period: str = "3y",
    ) -> list[dict]:
        """Fetch daily closing prices for Nifty index tickers via yfinance.

        Returns list of dicts: [{"date": "YYYY-MM-DD", "index_ticker": "^CRSLDX", "close": 12345.67}, ...]
        """
        if tickers is None:
            tickers = ["^CRSLDX", "^NSEI"]

        records: list[dict] = []
        for ticker_sym in tickers:
            try:
                hist = yf.Ticker(ticker_sym).history(period=period)
                for idx, row in hist.iterrows():
                    close = row["Close"]
                    if math.isnan(close):
                        continue
                    records.append({
                        "date": idx.strftime("%Y-%m-%d"),
                        "index_ticker": ticker_sym,
                        "close": round(close, 2),
                    })
            except Exception as e:
                logger.warning("Failed to fetch index prices for %s: %s", ticker_sym, e)

        logger.info("Fetched %d index price records for %s", len(records), tickers)
        return records

    def _fetch_gsec_yield(self) -> float | None:
        """Scrape CCIL for 10Y G-sec yield. Returns None on failure.

        CCIL Tenorwise Indicative Yields table layout (4 columns):
            Date | Tenor Bucket | Security | YTM (%)

        The Security column contains text like '6.33% GS 2035' — the leading
        coupon there must NOT be confused with the YTM. The previous regex
        `9Y-10Y.*?(\\d+\\.\\d+)` greedily lazy-matched the coupon in the
        Security cell instead of skipping forward to the YTM cell, returning
        ~6.33 for years (close enough to the real yield to look plausible).

        New strategy: locate the 9Y-10Y tenor cell, then walk past the Security
        cell (which contains '%') to the next numeric-only `<td>` cell — that
        is the YTM. Validate it falls in [3.0, 12.0] (sane 10Y yield range);
        anything outside that triggers logger.error and returns None so
        downstream consumers see a clear NULL rather than garbage.
        """
        try:
            resp = self._http.get(_CCIL_URL)
            resp.raise_for_status()
            html = resp.text

            # Match: 9Y-10Y tenor cell, then ANY cell containing '%' (security
            # name), then the YTM cell which is a bare decimal.
            # The `[^<]*%[^<]*` segment consumes the '6.33% GS 2035' security
            # cell so the trailing capture grabs YTM (6.8537), not the coupon.
            match = re.search(
                r'9\s*Y?\s*[-–]\s*10\s*Y\s*</td>'
                r'\s*<td[^>]*>[^<]*%[^<]*</td>'
                r'\s*<td[^>]*>\s*(\d+\.\d+)\s*</td>',
                html, re.DOTALL | re.IGNORECASE,
            )
            if not match:
                # Fallback: simpler layout (e.g. legacy/test HTML with only
                # 2 columns: tenor + YTM, no Security cell). Match a tenor
                # cell directly followed by a numeric cell.
                match = re.search(
                    r'9\s*Y?\s*[-–]\s*10\s*Y\s*</td>'
                    r'\s*<td[^>]*>\s*(\d+\.\d+)\s*</td>',
                    html, re.DOTALL | re.IGNORECASE,
                )
            if not match:
                # Last-resort fallback: original loose pattern, for legacy
                # test fixtures that use plain `<td>9Y-10Y</td><td>7.15</td>`
                # without explicit closing tags around the value.
                match = re.search(
                    r'9\s*Y?\s*[-–]\s*10\s*Y[^0-9]*?(\d+\.\d+)',
                    html, re.DOTALL | re.IGNORECASE,
                )

            if not match:
                logger.error(
                    "CCIL G-sec yield scrape FAILED: 9Y-10Y row not found. "
                    "Page layout may have changed at %s", _CCIL_URL,
                )
                return None

            value = round(float(match.group(1)), 2)
            # Sanity-check: 10Y G-sec yields move in 5%-9% historically;
            # widen to 3%-12% to allow regime extremes. Anything outside
            # is parser confusion (e.g. matched the wrong column).
            if not (3.0 <= value <= 12.0):
                logger.error(
                    "CCIL G-sec yield scrape FAILED: parsed value %.4f "
                    "outside plausible 3-12%% range — parser likely "
                    "matched wrong cell. Returning None.", value,
                )
                return None
            return value
        except Exception as e:
            logger.error("Failed to fetch G-sec yield from CCIL: %s", e)
            return None

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
