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
        """Scrape CCIL for 10Y G-sec yield. Returns None on failure."""
        try:
            resp = self._http.get(_CCIL_URL)
            resp.raise_for_status()
            html = resp.text

            # Look for the 9Y-10Y row and extract YTM value
            # Table rows have tenor and YTM columns
            match = re.search(
                r'9\s*Y?\s*[-–]\s*10\s*Y.*?(\d+\.\d+)',
                html, re.DOTALL | re.IGNORECASE,
            )
            if match:
                return round(float(match.group(1)), 2)

            logger.warning("Could not parse G-sec yield from CCIL page")
            return None
        except Exception as e:
            logger.warning("Failed to fetch G-sec yield: %s", e)
            return None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MacroClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
