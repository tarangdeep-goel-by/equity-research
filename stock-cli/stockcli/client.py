"""yfinance-backed client with in-memory caching."""

from __future__ import annotations

import time
from typing import Any

import yfinance as yf

from stockcli.models import (
    BalanceSheet,
    CashFlowStatement,
    CompanyProfile,
    IncomeStatement,
    KeyMetricsTTM,
    MarketMover,
    RatiosTTM,
    ScreenerResult,
)

CACHE_TTL = 300  # 5 minutes


class YFinanceError(Exception):
    """Raised when yfinance returns no data or an error."""


def _safe_get(df: Any, row: str, col: Any) -> float | None:
    """Safely extract a value from a DataFrame with None fallback."""
    try:
        val = df.loc[row, col]
        if val is not None and str(val) != "nan":
            return float(val)
    except (KeyError, TypeError, ValueError):
        pass
    return None


class YFinanceClient:
    """yfinance client with ticker/info caching."""

    def __init__(self) -> None:
        self._ticker_cache: dict[str, tuple[float, yf.Ticker]] = {}
        self._info_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def _ticker(self, symbol: str) -> yf.Ticker:
        """Get a cached Ticker object."""
        if symbol in self._ticker_cache:
            ts, ticker = self._ticker_cache[symbol]
            if time.time() - ts < CACHE_TTL:
                return ticker
        ticker = yf.Ticker(symbol)
        self._ticker_cache[symbol] = (time.time(), ticker)
        return ticker

    def _info(self, symbol: str) -> dict[str, Any]:
        """Get cached .info dict for a symbol."""
        if symbol in self._info_cache:
            ts, info = self._info_cache[symbol]
            if time.time() - ts < CACHE_TTL:
                return info
        ticker = self._ticker(symbol)
        info = ticker.info or {}
        if not info or info.get("quoteType") is None:
            raise YFinanceError(f"No data found for {symbol}")
        self._info_cache[symbol] = (time.time(), info)
        return info

    # ── Profile ──────────────────────────────────────────────

    def profile(self, symbol: str) -> CompanyProfile:
        info = self._info(symbol)
        low = info.get("fiftyTwoWeekLow")
        high = info.get("fiftyTwoWeekHigh")
        range_str = f"{low:.2f} - {high:.2f}" if low and high else None
        employees = info.get("fullTimeEmployees")

        return CompanyProfile(
            symbol=symbol,
            companyName=info.get("longName") or info.get("shortName"),
            price=info.get("currentPrice") or info.get("regularMarketPrice"),
            change=info.get("regularMarketChange"),
            changePercentage=info.get("regularMarketChangePercent"),
            currency=info.get("currency"),
            exchange=info.get("exchange"),
            industry=info.get("industry"),
            sector=info.get("sector"),
            country=info.get("country"),
            marketCap=info.get("marketCap"),
            description=info.get("longBusinessSummary"),
            ceo=None,
            fullTimeEmployees=str(employees) if employees else None,
            ipoDate=None,
            website=info.get("website"),
            beta=info.get("beta"),
            averageVolume=info.get("averageVolume"),
            lastDividend=info.get("lastDividendValue"),
            range=range_str,
            isEtf=info.get("quoteType") == "ETF",
            isActivelyTrading=True,
        )

    # ── Ratios & Metrics ─────────────────────────────────────

    def ratios_ttm(self, symbol: str) -> RatiosTTM:
        info = self._info(symbol)
        mcap = info.get("marketCap")
        fcf = info.get("freeCashflow")
        p_fcf = mcap / fcf if mcap and fcf and fcf != 0 else None
        div_yield = info.get("dividendYield")

        return RatiosTTM(
            priceToEarningsRatio=info.get("trailingPE"),
            priceToEarningsGrowthRatio=info.get("pegRatio"),
            priceToBookRatio=info.get("priceToBook"),
            priceToSalesRatio=info.get("priceToSalesTrailing12Months"),
            priceToFreeCashFlowRatio=p_fcf,
            dividendYield=div_yield / 100 if div_yield else None,
            dividendYieldPercentage=div_yield,
            returnOnEquity=info.get("returnOnEquity"),
            returnOnAssets=info.get("returnOnAssets"),
            grossProfitMargin=info.get("grossMargins"),
            operatingProfitMargin=info.get("operatingMargins"),
            netProfitMargin=info.get("profitMargins"),
            debtToEquityRatio=_div100(info.get("debtToEquity")),
            currentRatio=info.get("currentRatio"),
            interestCoverageRatio=None,
            earningsYield=None,
            freeCashFlowPerShare=None,
        )

    def key_metrics_ttm(self, symbol: str) -> KeyMetricsTTM:
        info = self._info(symbol)
        fcf = info.get("freeCashflow")
        shares = info.get("sharesOutstanding")
        fcf_per_share = fcf / shares if fcf and shares and shares != 0 else None

        return KeyMetricsTTM(
            marketCap=info.get("marketCap"),
            enterpriseValue=info.get("enterpriseValue"),
            revenuePerShare=info.get("revenuePerShare"),
            netIncomePerShare=None,
            freeCashFlowPerShare=fcf_per_share,
            bookValuePerShare=info.get("bookValue"),
            returnOnInvestedCapital=None,
            returnOnEquity=info.get("returnOnEquity"),
            returnOnAssets=info.get("returnOnAssets"),
            dividendYield=info.get("dividendYield"),
            evToSales=None,
            evToFreeCashFlow=None,
            evToEBITDA=info.get("enterpriseToEbitda"),
            debtToEquity=_div100(info.get("debtToEquity")),
            debtToAssets=None,
        )

    # ── Financial Statements ─────────────────────────────────

    def income_statement(
        self, symbol: str, period: str = "annual", limit: int = 4
    ) -> list[IncomeStatement]:
        ticker = self._ticker(symbol)
        freq = "quarterly" if period == "quarter" else "yearly"
        df = ticker.get_income_stmt(freq=freq)
        if df is None or df.empty:
            raise YFinanceError(f"No income statement data for {symbol}")

        results = []
        for col in list(df.columns)[:limit]:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            results.append(IncomeStatement(
                date=date_str,
                period=period,
                revenue=_safe_get(df, "TotalRevenue", col),
                costOfRevenue=_safe_get(df, "CostOfRevenue", col),
                grossProfit=_safe_get(df, "GrossProfit", col),
                operatingExpenses=_safe_get(df, "OperatingExpense", col),
                operatingIncome=_safe_get(df, "OperatingIncome", col),
                netIncome=_safe_get(df, "NetIncome", col),
                eps=_safe_get(df, "BasicEPS", col),
                epsDiluted=_safe_get(df, "DilutedEPS", col),
                ebitda=_safe_get(df, "EBITDA", col),
                weightedAverageShsOut=_safe_get(df, "BasicAverageShares", col),
                weightedAverageShsOutDil=_safe_get(df, "DilutedAverageShares", col),
            ))
        return results

    def balance_sheet(
        self, symbol: str, period: str = "annual", limit: int = 4
    ) -> list[BalanceSheet]:
        ticker = self._ticker(symbol)
        freq = "quarterly" if period == "quarter" else "yearly"
        df = ticker.get_balance_sheet(freq=freq)
        if df is None or df.empty:
            raise YFinanceError(f"No balance sheet data for {symbol}")

        results = []
        for col in list(df.columns)[:limit]:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            results.append(BalanceSheet(
                date=date_str,
                period=period,
                totalAssets=_safe_get(df, "TotalAssets", col),
                totalCurrentAssets=_safe_get(df, "CurrentAssets", col),
                cashAndCashEquivalents=_safe_get(df, "CashAndCashEquivalents", col),
                totalLiabilities=_safe_get(df, "TotalLiabilitiesNetMinorityInterest", col),
                totalCurrentLiabilities=_safe_get(df, "CurrentLiabilities", col),
                longTermDebt=_safe_get(df, "LongTermDebt", col),
                totalDebt=_safe_get(df, "TotalDebt", col),
                totalStockholdersEquity=_safe_get(df, "StockholdersEquity", col),
                totalEquity=_safe_get(df, "StockholdersEquity", col),
                netDebt=_safe_get(df, "NetDebt", col),
                goodwill=_safe_get(df, "Goodwill", col),
                intangibleAssets=_safe_get(df, "IntangibleAssets", col),
                inventory=_safe_get(df, "Inventory", col),
                netReceivables=_safe_get(df, "Receivables", col),
            ))
        return results

    def cash_flow(
        self, symbol: str, period: str = "annual", limit: int = 4
    ) -> list[CashFlowStatement]:
        ticker = self._ticker(symbol)
        freq = "quarterly" if period == "quarter" else "yearly"
        df = ticker.get_cash_flow(freq=freq)
        if df is None or df.empty:
            raise YFinanceError(f"No cash flow data for {symbol}")

        results = []
        for col in list(df.columns)[:limit]:
            date_str = col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col)
            op_cf = _safe_get(df, "OperatingCashFlow", col)
            capex = _safe_get(df, "CapitalExpenditure", col)
            fcf = _safe_get(df, "FreeCashFlow", col)
            if fcf is None and op_cf is not None and capex is not None:
                fcf = op_cf + capex  # capex is typically negative

            results.append(CashFlowStatement(
                date=date_str,
                period=period,
                operatingCashFlow=op_cf,
                capitalExpenditure=capex,
                freeCashFlow=fcf,
                netCashProvidedByInvestingActivities=_safe_get(df, "InvestingCashFlow", col),
                netCashProvidedByFinancingActivities=_safe_get(df, "FinancingCashFlow", col),
                netChangeInCash=_safe_get(df, "ChangesInCash", col),
                commonDividendsPaid=_safe_get(df, "CommonStockDividendPaid", col),
                stockBasedCompensation=_safe_get(df, "StockBasedCompensation", col),
                depreciationAndAmortization=_safe_get(df, "DepreciationAndAmortization", col),
            ))
        return results

    # ── Screener ─────────────────────────────────────────────

    def screen(self, **filters: Any) -> list[ScreenerResult]:
        query = _build_screen_query(filters)
        try:
            result = yf.screen(query)
        except Exception as e:
            raise YFinanceError(f"Screener failed: {e}")

        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        limit = filters.get("limit", 20)
        results = []
        for q in quotes[:limit]:
            results.append(ScreenerResult(
                symbol=q.get("symbol"),
                companyName=q.get("longName") or q.get("shortName"),
                marketCap=q.get("marketCap"),
                sector=q.get("sector"),
                industry=q.get("industry"),
                beta=None,
                price=q.get("regularMarketPrice"),
                lastAnnualDividend=None,
                volume=q.get("regularMarketVolume"),
                exchange=q.get("exchange"),
                country=None,
                isEtf=q.get("quoteType") == "ETF",
                isActivelyTrading=True,
            ))
        return results

    # ── Market Movers ────────────────────────────────────────

    def gainers(self) -> list[MarketMover]:
        return self._movers("day_gainers")

    def losers(self) -> list[MarketMover]:
        return self._movers("day_losers")

    def actives(self) -> list[MarketMover]:
        return self._movers("most_actives")

    def _movers(self, key: str) -> list[MarketMover]:
        try:
            result = yf.screen(key)
        except Exception as e:
            raise YFinanceError(f"Failed to fetch {key}: {e}")

        quotes = result.get("quotes", []) if isinstance(result, dict) else []
        movers = []
        for q in quotes:
            chg = q.get("regularMarketChange")
            price = q.get("regularMarketPrice")
            chg_pct = q.get("regularMarketChangePercent")
            movers.append(MarketMover(
                symbol=q.get("symbol"),
                name=q.get("longName") or q.get("shortName"),
                change=chg,
                price=price,
                changesPercentage=chg_pct,
                exchange=q.get("exchange"),
            ))
        return movers


def _div100(val: float | None) -> float | None:
    """Divide by 100 if not None (yfinance debtToEquity is %)."""
    return val / 100 if val is not None else None


def _build_screen_query(filters: dict[str, Any]) -> Any:
    """Build a yfinance screen query from CLI filters.

    Uses EquityQuery for custom filters, falls back to predefined keys.
    """
    # Remove limit — it's not a query param
    filters = {k: v for k, v in filters.items() if k != "limit" and v is not None}

    if not filters:
        return "most_actives"

    operands = []

    # Sector filter
    if "sector" in filters:
        operands.append(yf.EquityQuery("eq", ["sector", filters.pop("sector")]))

    # Exchange filter
    if "exchange" in filters:
        operands.append(yf.EquityQuery("eq", ["exchange", filters.pop("exchange")]))

    # Country/region filter
    if "country" in filters:
        operands.append(yf.EquityQuery("eq", ["region", filters.pop("country")]))

    # Industry filter
    if "industry" in filters:
        operands.append(yf.EquityQuery("eq", ["industry", filters.pop("industry")]))

    # Numeric range filters
    range_map = {
        "marketCapMoreThan": ("gt", "intradaymarketcap"),
        "marketCapLowerThan": ("lt", "intradaymarketcap"),
        "peMoreThan": ("gt", "peratio"),
        "peLowerThan": ("lt", "peratio"),
        "priceMoreThan": ("gt", "intradayprice"),
        "priceLowerThan": ("lt", "intradayprice"),
        "dividendMoreThan": ("gt", "dividendyield"),
        "volumeMoreThan": ("gt", "dayvolume"),
    }

    for key, (op, field) in range_map.items():
        if key in filters:
            operands.append(yf.EquityQuery(op, [field, filters.pop(key)]))

    # Unsupported filters — warn but don't fail
    for key in list(filters.keys()):
        import sys
        print(f"Warning: filter '{key}' not supported by yfinance screener", file=sys.stderr)

    if not operands:
        return "most_actives"
    if len(operands) == 1:
        return operands[0]
    return yf.EquityQuery("and", operands)
