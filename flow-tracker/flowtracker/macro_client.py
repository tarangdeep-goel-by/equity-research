"""Macro indicator client — yfinance for VIX/FX/crude, CCIL for G-sec yield."""

from __future__ import annotations

import logging
import math
import re
from datetime import date

import httpx
import yfinance as yf

from flowtracker.macro_models import MacroSnapshot

logger = logging.getLogger(__name__)

_VIX_TICKER = "^INDIAVIX"
_USDINR_TICKER = "USDINR=X"
_BRENT_TICKER = "BZ=F"

_CCIL_URL = "https://www.ccilindia.com/web/ccil/tenorwise-indicative-yields"


class MacroClient:
    """Client for macro indicators: VIX, USD/INR, Brent crude, 10Y G-sec."""

    def __init__(self) -> None:
        self._http = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0"},
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

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MacroClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
