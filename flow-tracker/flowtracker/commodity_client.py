"""Gold and silver price client — yfinance for commodities, mfapi.in for ETF NAVs."""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta

import httpx
import yfinance as yf

from flowtracker.commodity_models import CommodityPrice, GoldETFNav

logger = logging.getLogger(__name__)

# yfinance tickers
_GOLD_TICKER = "GC=F"      # COMEX Gold Futures
_SILVER_TICKER = "SI=F"    # COMEX Silver Futures
_USDINR_TICKER = "INR=X"   # USD/INR exchange rate

# Industrial metals — closest yfinance proxies for LME contracts.
# HG=F is COMEX copper (USD/lb), the only liquid copper future on yfinance — LME
# copper itself is not exposed. ALI=F is the CME aluminium future tracking LME
# settlements (USD/MT). Zinc (ZNC=F) and lead (PB=F) are unavailable on yfinance
# (ZNC=F returns a stale constant; PB=F returns no data); agents should treat
# their absence as "no data" rather than zero.
_METALS_TICKERS: dict[str, tuple[str, str]] = {
    "ALUMINIUM": ("ALI=F", "USD/MT"),
    "COPPER": ("HG=F", "USD/lb"),
}

# mfapi.in scheme codes
_ETF_SCHEMES = {
    "140088": "Nippon India ETF Gold BeES",
    "149758": "Nippon India Silver ETF",
}

# Conversion constants
_OZ_TO_GRAMS = 31.1035


class CommodityClient:
    """Client for gold/silver prices and ETF NAV data."""

    def __init__(self) -> None:
        self._http = httpx.Client(timeout=30.0)

    def fetch_prices(self, days: int = 30) -> list[CommodityPrice]:
        """Fetch gold, silver, and INR prices for the last N days.

        Returns CommodityPrice records for GOLD (USD/oz), SILVER (USD/oz),
        GOLD_INR (INR/10g), and SILVER_INR (INR/kg).
        """
        period = f"{days}d"

        gold = yf.Ticker(_GOLD_TICKER).history(period=period)
        silver = yf.Ticker(_SILVER_TICKER).history(period=period)
        usdinr = yf.Ticker(_USDINR_TICKER).history(period=period)

        records: list[CommodityPrice] = []

        # Build USD/INR lookup by date string
        inr_rates: dict[str, float] = {}
        for idx, row in usdinr.iterrows():
            d = idx.strftime("%Y-%m-%d")
            val = row["Close"]
            if not math.isnan(val):
                inr_rates[d] = val

        # Gold USD
        for idx, row in gold.iterrows():
            d = idx.strftime("%Y-%m-%d")
            close = row["Close"]
            if math.isnan(close):
                continue
            close = round(close, 2)
            records.append(CommodityPrice(date=d, symbol="GOLD", price=close, unit="USD/oz"))

            # Gold INR/10g = (USD/oz * INR/USD) / 31.1035 * 10
            inr_rate = inr_rates.get(d)
            if inr_rate and not math.isnan(inr_rate):
                gold_inr = round((close * inr_rate) / _OZ_TO_GRAMS * 10, 2)
                records.append(CommodityPrice(date=d, symbol="GOLD_INR", price=gold_inr, unit="INR/10g"))

        # Silver USD
        for idx, row in silver.iterrows():
            d = idx.strftime("%Y-%m-%d")
            close = row["Close"]
            if math.isnan(close):
                continue
            close = round(close, 2)
            records.append(CommodityPrice(date=d, symbol="SILVER", price=close, unit="USD/oz"))

            # Silver INR/kg = (USD/oz * INR/USD) / 31.1035 * 1000
            inr_rate = inr_rates.get(d)
            if inr_rate and not math.isnan(inr_rate):
                silver_inr = round((close * inr_rate) / _OZ_TO_GRAMS * 1000, 2)
                records.append(CommodityPrice(date=d, symbol="SILVER_INR", price=silver_inr, unit="INR/kg"))

        return records

    def fetch_prices_history(self, start: str = "2010-01-01") -> list[CommodityPrice]:
        """Fetch full history of gold, silver, and INR prices from a start date.

        Same logic as fetch_prices but uses start/end instead of period.
        """
        end = date.today().isoformat()

        gold = yf.Ticker(_GOLD_TICKER).history(start=start, end=end)
        silver = yf.Ticker(_SILVER_TICKER).history(start=start, end=end)
        usdinr = yf.Ticker(_USDINR_TICKER).history(start=start, end=end)

        records: list[CommodityPrice] = []

        inr_rates: dict[str, float] = {}
        for idx, row in usdinr.iterrows():
            d = idx.strftime("%Y-%m-%d")
            val = row["Close"]
            if not math.isnan(val):
                inr_rates[d] = val

        for idx, row in gold.iterrows():
            d = idx.strftime("%Y-%m-%d")
            close = round(row["Close"], 2)
            records.append(CommodityPrice(date=d, symbol="GOLD", price=close, unit="USD/oz"))
            inr_rate = inr_rates.get(d)
            if inr_rate:
                gold_inr = round((close * inr_rate) / _OZ_TO_GRAMS * 10, 2)
                records.append(CommodityPrice(date=d, symbol="GOLD_INR", price=gold_inr, unit="INR/10g"))

        for idx, row in silver.iterrows():
            d = idx.strftime("%Y-%m-%d")
            close = round(row["Close"], 2)
            records.append(CommodityPrice(date=d, symbol="SILVER", price=close, unit="USD/oz"))
            inr_rate = inr_rates.get(d)
            if inr_rate:
                silver_inr = round((close * inr_rate) / _OZ_TO_GRAMS * 1000, 2)
                records.append(CommodityPrice(date=d, symbol="SILVER_INR", price=silver_inr, unit="INR/kg"))

        return records

    def fetch_metals(self, days: int = 30) -> list[CommodityPrice]:
        """Fetch industrial metals prices (aluminium / copper / zinc) for the last N days.

        Returns CommodityPrice records keyed by symbol (ALUMINIUM, COPPER, ZINC).
        Units follow yfinance contract conventions — USD/MT for ALI=F and ZNC=F,
        USD/lb for HG=F (COMEX copper). No INR conversion — LME pricing is
        conventionally USD; agents convert downstream if needed.
        """
        period = f"{days}d"
        records: list[CommodityPrice] = []

        for symbol, (ticker, unit) in _METALS_TICKERS.items():
            try:
                hist = yf.Ticker(ticker).history(period=period)
            except Exception as e:
                logger.warning("Failed to fetch %s (%s): %s", symbol, ticker, e)
                continue
            if hist.empty:
                logger.warning("No data for %s (%s) — skipping", symbol, ticker)
                continue
            for idx, row in hist.iterrows():
                d = idx.strftime("%Y-%m-%d")
                close = row["Close"]
                if math.isnan(close):
                    continue
                records.append(CommodityPrice(
                    date=d, symbol=symbol, price=round(close, 4), unit=unit,
                ))

        return records

    def fetch_metals_history(self, start: str = "2010-01-01") -> list[CommodityPrice]:
        """Fetch full metals history from a start date — same logic as fetch_metals."""
        end = date.today().isoformat()
        records: list[CommodityPrice] = []

        for symbol, (ticker, unit) in _METALS_TICKERS.items():
            try:
                hist = yf.Ticker(ticker).history(start=start, end=end)
            except Exception as e:
                logger.warning("Failed to fetch %s history (%s): %s", symbol, ticker, e)
                continue
            if hist.empty:
                logger.warning("No history for %s (%s) — skipping", symbol, ticker)
                continue
            for idx, row in hist.iterrows():
                d = idx.strftime("%Y-%m-%d")
                close = row["Close"]
                if math.isnan(close):
                    continue
                records.append(CommodityPrice(
                    date=d, symbol=symbol, price=round(close, 4), unit=unit,
                ))

        return records

    def fetch_etf_navs(self, days: int = 365) -> list[GoldETFNav]:
        """Fetch gold/silver ETF NAVs from mfapi.in."""
        records: list[GoldETFNav] = []
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        for scheme_code, scheme_name in _ETF_SCHEMES.items():
            try:
                resp = self._http.get(f"https://api.mfapi.in/mf/{scheme_code}")
                resp.raise_for_status()
                data = resp.json()

                for entry in data.get("data", []):
                    # mfapi returns date as "DD-MM-YYYY"
                    parts = entry["date"].split("-")
                    if len(parts) == 3:
                        d = f"{parts[2]}-{parts[1]}-{parts[0]}"  # YYYY-MM-DD
                    else:
                        continue

                    if d < cutoff:
                        continue

                    try:
                        nav = float(entry["nav"])
                    except (ValueError, KeyError):
                        continue

                    records.append(GoldETFNav(
                        date=d, scheme_code=scheme_code,
                        scheme_name=scheme_name, nav=nav,
                    ))

                logger.info("Fetched %s NAVs for %s", len([r for r in records if r.scheme_code == scheme_code]), scheme_name)
            except Exception as e:
                logger.warning("Failed to fetch NAVs for %s: %s", scheme_name, e)

        return records

    def fetch_etf_navs_all(self) -> list[GoldETFNav]:
        """Fetch full NAV history for all ETFs."""
        return self.fetch_etf_navs(days=36500)  # ~100 years, effectively all

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> CommodityClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
