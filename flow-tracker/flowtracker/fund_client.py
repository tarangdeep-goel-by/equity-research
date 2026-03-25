"""yfinance client for Indian equity fundamentals."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import yfinance as yf

from flowtracker.fund_models import LiveSnapshot, QuarterlyResult, ValuationSnapshot


class YFinanceError(Exception):
    """Raised when yfinance returns no data."""


def nse_symbol(symbol: str) -> str:
    """Convert watchlist symbol to yfinance format. TECHM -> TECHM.NS"""
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def _safe_get(df: Any, row: str, col: Any) -> float | None:
    """Safely extract a value from a DataFrame."""
    try:
        val = df.loc[row, col]
        if val is not None and str(val) != "nan":
            return float(val)
    except (KeyError, TypeError, ValueError):
        pass
    return None


def _div100(val: float | None) -> float | None:
    """yfinance debtToEquity is in %, convert to ratio."""
    return val / 100 if val is not None else None


class FundClient:
    """yfinance client for fundamentals data."""

    def __init__(self) -> None:
        self._ticker_cache: dict[str, tuple[float, yf.Ticker]] = {}
        self._info_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = 300  # 5 minutes

    def _ticker(self, symbol: str) -> yf.Ticker:
        yf_sym = nse_symbol(symbol)
        now = time.time()
        if yf_sym in self._ticker_cache:
            ts, ticker = self._ticker_cache[yf_sym]
            if now - ts < self._cache_ttl:
                return ticker
        ticker = yf.Ticker(yf_sym)
        self._ticker_cache[yf_sym] = (now, ticker)
        return ticker

    def _info(self, symbol: str) -> dict[str, Any]:
        yf_sym = nse_symbol(symbol)
        now = time.time()
        if yf_sym in self._info_cache:
            ts, info = self._info_cache[yf_sym]
            if now - ts < self._cache_ttl:
                return info
        ticker = self._ticker(symbol)
        info = ticker.info or {}
        if not info or info.get("quoteType") is None:
            raise YFinanceError(f"No data found for {symbol}")
        self._info_cache[yf_sym] = (now, info)
        return info

    # -- Live (no storage) --

    def get_live_snapshot(self, symbol: str) -> LiveSnapshot:
        """Fetch current ratios and metrics. Never stored."""
        info = self._info(symbol)
        return LiveSnapshot(
            symbol=symbol,
            company_name=info.get("longName") or info.get("shortName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            market_cap=info.get("marketCap"),
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            pb_ratio=info.get("priceToBook"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            dividend_yield=info.get("dividendYield"),
            roe=info.get("returnOnEquity"),
            roa=info.get("returnOnAssets"),
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            net_margin=info.get("profitMargins"),
            debt_to_equity=_div100(info.get("debtToEquity")),
            current_ratio=info.get("currentRatio"),
            free_cash_flow=info.get("freeCashflow"),
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
        )

    # -- Stored (fetched -> persisted) --

    def fetch_quarterly_results(self, symbol: str) -> list[QuarterlyResult]:
        """Fetch quarterly income data from yfinance (~5 quarters)."""
        ticker = self._ticker(symbol)
        df = ticker.get_income_stmt(freq="quarterly")
        if df is None or df.empty:
            return []

        results = []
        for col in df.columns:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            revenue = _safe_get(df, "TotalRevenue", col)
            gross_profit = _safe_get(df, "GrossProfit", col)
            operating_income = _safe_get(df, "OperatingIncome", col)
            net_income = _safe_get(df, "NetIncome", col)
            ebitda = _safe_get(df, "EBITDA", col)
            eps = _safe_get(df, "BasicEPS", col)
            eps_diluted = _safe_get(df, "DilutedEPS", col)

            operating_margin = None
            if operating_income is not None and revenue and revenue != 0:
                operating_margin = operating_income / revenue

            net_margin = None
            if net_income is not None and revenue and revenue != 0:
                net_margin = net_income / revenue

            results.append(QuarterlyResult(
                symbol=symbol,
                quarter_end=date_str,
                revenue=revenue,
                gross_profit=gross_profit,
                operating_income=operating_income,
                net_income=net_income,
                ebitda=ebitda,
                eps=eps,
                eps_diluted=eps_diluted,
                operating_margin=operating_margin,
                net_margin=net_margin,
            ))
        return results

    def fetch_valuation_snapshot(self, symbol: str) -> ValuationSnapshot:
        """Fetch today's valuation metrics for storage."""
        info = self._info(symbol)
        return ValuationSnapshot(
            symbol=symbol,
            date=date.today().isoformat(),
            # Price context
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            market_cap=info.get("marketCap"),
            enterprise_value=info.get("enterpriseValue"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
            beta=info.get("beta"),
            # Valuation multiples
            pe_trailing=info.get("trailingPE"),
            pe_forward=info.get("forwardPE"),
            pb_ratio=info.get("priceToBook"),
            ev_ebitda=info.get("enterpriseToEbitda"),
            ev_revenue=info.get("enterpriseToRevenue"),
            ps_ratio=info.get("priceToSalesTrailing12Months"),
            peg_ratio=info.get("pegRatio"),
            # Profitability
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            net_margin=info.get("profitMargins"),
            roe=info.get("returnOnEquity"),
            roa=info.get("returnOnAssets"),
            # Growth
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
            earnings_quarterly_growth=info.get("earningsQuarterlyGrowth"),
            # Yield
            dividend_yield=info.get("dividendYield"),
            # Balance sheet
            debt_to_equity=_div100(info.get("debtToEquity")),
            current_ratio=info.get("currentRatio"),
            total_cash=info.get("totalCash"),
            total_debt=info.get("totalDebt"),
            book_value_per_share=info.get("bookValue"),
            # Cash flow
            free_cash_flow=info.get("freeCashflow"),
            operating_cash_flow=info.get("operatingCashflow"),
            # Per-share
            revenue_per_share=info.get("revenuePerShare"),
            cash_per_share=info.get("totalCashPerShare"),
            # Liquidity
            avg_volume=info.get("averageVolume"),
            float_shares=info.get("floatShares"),
            shares_outstanding=info.get("sharesOutstanding"),
        )

    def compute_historical_pe(
        self, symbol: str, annual_eps: list, weekly_prices: list[tuple[str, float, int]] | None = None
    ) -> list:
        """Compute historical weekly P/E from annual EPS + weekly prices.

        Args:
            symbol: Stock symbol (e.g., 'TECHM')
            annual_eps: List of AnnualEPS objects with fiscal_year_end and eps fields
            weekly_prices: Optional pre-fetched list of (date_iso, close_price, volume) tuples.
                          If None, fetches from yfinance.

        Returns:
            List of ValuationSnapshot objects with date, price, and pe_trailing populated.
        """
        if not annual_eps:
            return []

        if weekly_prices is None:
            weekly_prices = self.fetch_weekly_prices(symbol)

        if not weekly_prices:
            return []

        # Sort annual EPS by fiscal year end (ascending)
        sorted_eps = sorted(annual_eps, key=lambda a: a.fiscal_year_end)

        snapshots = []
        for date_str, close_price, _volume in weekly_prices:
            if close_price <= 0:
                continue

            # Find the most recent annual EPS as of this date
            # (fiscal year end <= this date)
            applicable_eps = None
            for ae in sorted_eps:
                if ae.fiscal_year_end <= date_str:
                    applicable_eps = ae
                else:
                    break  # sorted ascending, so no need to continue

            if applicable_eps is None or applicable_eps.eps <= 0:
                continue

            pe = close_price / applicable_eps.eps

            # Sanity check: skip extreme P/E values (likely data errors)
            if pe > 200 or pe < 1:
                continue

            snapshots.append(ValuationSnapshot(
                symbol=symbol,
                date=date_str,
                price=close_price,
                pe_trailing=pe,
            ))

        return snapshots

    def fetch_weekly_prices(self, symbol: str, period: str = "10y") -> list[tuple[str, float, int]]:
        """Fetch weekly closing prices and volume for historical P/E computation.
        Returns list of (date_iso, close_price, volume) tuples.
        """
        ticker = self._ticker(symbol)
        hist = ticker.history(period=period, interval="1wk")
        if hist is None or hist.empty:
            return []
        return [
            (idx.strftime("%Y-%m-%d"), float(row["Close"]), int(row.get("Volume", 0)))
            for idx, row in hist.iterrows()
            if row["Close"] is not None and str(row["Close"]) != "nan"
        ]
