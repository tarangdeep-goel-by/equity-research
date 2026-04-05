"""FMP (Financial Modeling Prep) API client for valuation, technicals, and analyst data."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import httpx

from flowtracker.fmp_models import (
    FMPAnalystGrade,
    FMPDcfValue,
    FMPFinancialGrowth,
    FMPKeyMetrics,
    FMPPriceTarget,
    FMPTechnicalIndicator,
)
from flowtracker.fund_client import nse_symbol

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/api/v3"
_CONFIG_PATH = Path.home() / ".config" / "flowtracker" / "fmp.env"


def _load_api_key() -> str:
    """Load FMP_API_KEY from ~/.config/flowtracker/fmp.env."""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"FMP config not found: {_CONFIG_PATH}\n"
            "Create it with: echo 'FMP_API_KEY=your_key' > ~/.config/flowtracker/fmp.env"
        )
    for line in _CONFIG_PATH.read_text().strip().splitlines():
        line = line.strip()
        if line.startswith("FMP_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise ValueError(f"FMP_API_KEY not found in {_CONFIG_PATH}")


def _safe_float(val: object) -> float | None:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # NaN check
    except (ValueError, TypeError):
        return None


def _to_cr(val: float | None) -> float | None:
    """Convert raw value to crores (÷1e7)."""
    return val / 1e7 if val is not None else None


class FMPClient:
    """Client for Financial Modeling Prep API."""

    def __init__(self) -> None:
        self._api_key = _load_api_key()
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=15, read=45, write=10, pool=10),
        )

    def _request_with_retry(self, method: str, url: str, max_retries: int = 3, **kwargs) -> httpx.Response:
        """HTTP request with exponential backoff and 429/5xx handling."""
        last_exc = None
        for attempt in range(max_retries + 1):
            try:
                resp = self._client.request(method, url, **kwargs)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else (2 ** attempt) + random.uniform(0, 1)
                    logger.warning("FMP 429 on %s — retrying in %.1fs", url, wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < max_retries:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "FMP request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1, max_retries + 1, exc, wait,
                    )
                    time.sleep(wait)
        raise last_exc or httpx.HTTPError(f"Failed after {max_retries + 1} attempts: {url}")

    def _get(self, path: str, params: dict | None = None) -> list[dict]:
        """GET request with API key, return JSON list."""
        url = f"{_FMP_BASE}{path}"
        p = {"apikey": self._api_key}
        if params:
            p.update(params)
        try:
            resp = self._request_with_retry("GET", url, params=p)
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
            return []
        except Exception as e:
            logger.warning("FMP request failed: %s %s -- %s", path, params, e)
            return []

    def fetch_dcf(self, symbol: str) -> FMPDcfValue | None:
        """Fetch current DCF intrinsic value."""
        data = self._get(f"/discounted-cash-flow/{nse_symbol(symbol)}")
        if not data:
            return None
        d = data[0]
        return FMPDcfValue(
            symbol=symbol,
            date=d.get("date", ""),
            dcf=_safe_float(d.get("dcf")),
            stock_price=_safe_float(d.get("Stock Price")),
        )

    def fetch_dcf_history(self, symbol: str, limit: int = 10) -> list[FMPDcfValue]:
        """Fetch historical DCF values."""
        data = self._get(
            f"/historical-discounted-cash-flow-statement/{nse_symbol(symbol)}",
            {"period": "annual"},
        )
        results = []
        for d in data[:limit]:
            results.append(FMPDcfValue(
                symbol=symbol,
                date=d.get("date", ""),
                dcf=_safe_float(d.get("dcf")),
                stock_price=_safe_float(d.get("Stock Price") or d.get("price")),
            ))
        return results

    def fetch_technical_indicator(
        self, symbol: str, indicator: str = "rsi", period: int = 14,
    ) -> list[FMPTechnicalIndicator]:
        """Fetch a single technical indicator series."""
        data = self._get(
            f"/technical_indicator/daily/{nse_symbol(symbol)}",
            {"type": indicator, "period": period},
        )
        results = []
        for d in data[:5]:  # latest 5 data points per indicator
            results.append(FMPTechnicalIndicator(
                symbol=symbol,
                date=d.get("date", ""),
                indicator=indicator if indicator not in ("sma",) else f"sma_{period}",
                value=_safe_float(d.get(indicator) or d.get("close")),
            ))
        return results

    def fetch_technicals_all(self, symbol: str) -> list[FMPTechnicalIndicator]:
        """Fetch RSI, SMA-50, SMA-200, MACD, ADX for a symbol."""
        all_indicators: list[FMPTechnicalIndicator] = []

        # RSI (14-period)
        all_indicators.extend(self.fetch_technical_indicator(symbol, "rsi", 14))
        time.sleep(0.5)

        # SMA 50
        data = self._get(
            f"/technical_indicator/daily/{nse_symbol(symbol)}",
            {"type": "sma", "period": 50},
        )
        for d in data[:1]:
            all_indicators.append(FMPTechnicalIndicator(
                symbol=symbol, date=d.get("date", ""),
                indicator="sma_50", value=_safe_float(d.get("sma")),
            ))
        time.sleep(0.5)

        # SMA 200
        data = self._get(
            f"/technical_indicator/daily/{nse_symbol(symbol)}",
            {"type": "sma", "period": 200},
        )
        for d in data[:1]:
            all_indicators.append(FMPTechnicalIndicator(
                symbol=symbol, date=d.get("date", ""),
                indicator="sma_200", value=_safe_float(d.get("sma")),
            ))
        time.sleep(0.5)

        # MACD
        all_indicators.extend(self.fetch_technical_indicator(symbol, "macd", 14))
        time.sleep(0.5)

        # ADX
        all_indicators.extend(self.fetch_technical_indicator(symbol, "adx", 14))

        return all_indicators

    def fetch_key_metrics(self, symbol: str, limit: int = 10) -> list[FMPKeyMetrics]:
        """Fetch key financial metrics (annual)."""
        data = self._get(
            f"/key-metrics/{nse_symbol(symbol)}",
            {"period": "annual", "limit": limit},
        )
        results = []
        for d in data:
            debt_to_equity = _safe_float(d.get("debtToEquity"))
            equity_multiplier = None
            if debt_to_equity is not None:
                equity_multiplier = 1.0 + debt_to_equity

            results.append(FMPKeyMetrics(
                symbol=symbol,
                date=d.get("date", ""),
                revenue_per_share=_safe_float(d.get("revenuePerShare")),
                net_income_per_share=_safe_float(d.get("netIncomePerShare")),
                operating_cash_flow_per_share=_safe_float(d.get("operatingCashFlowPerShare")),
                free_cash_flow_per_share=_safe_float(d.get("freeCashFlowPerShare")),
                cash_per_share=_safe_float(d.get("cashPerShare")),
                book_value_per_share=_safe_float(d.get("bookValuePerShare")),
                tangible_book_value_per_share=_safe_float(d.get("tangibleBookValuePerShare")),
                shareholders_equity_per_share=_safe_float(d.get("shareholdersEquityPerShare")),
                interest_debt_per_share=_safe_float(d.get("interestDebtPerShare")),
                market_cap=_to_cr(_safe_float(d.get("marketCap"))),
                enterprise_value=_to_cr(_safe_float(d.get("enterpriseValue"))),
                pe_ratio=_safe_float(d.get("peRatio")),
                price_to_sales_ratio=_safe_float(d.get("priceToSalesRatio")),
                pb_ratio=_safe_float(d.get("pbRatio")),
                ev_to_sales=_safe_float(d.get("evToSales")),
                ev_to_ebitda=_safe_float(d.get("enterpriseValueOverEBITDA")),
                ev_to_operating_cash_flow=_safe_float(d.get("evToOperatingCashFlow")),
                ev_to_free_cash_flow=_safe_float(d.get("evToFreeCashFlow")),
                earnings_yield=_safe_float(d.get("earningsYield")),
                free_cash_flow_yield=_safe_float(d.get("freeCashFlowYield")),
                debt_to_equity=debt_to_equity,
                debt_to_assets=_safe_float(d.get("debtToAssets")),
                dividend_yield=_safe_float(d.get("dividendYield")),
                payout_ratio=_safe_float(d.get("payoutRatio")),
                roe=_safe_float(d.get("roe")),
                roa=_safe_float(d.get("returnOnTangibleAssets")),
                roic=_safe_float(d.get("roic")),
                net_profit_margin_dupont=_safe_float(d.get("netProfitMargin")),
                asset_turnover=_safe_float(d.get("assetTurnover")),
                equity_multiplier=equity_multiplier,
            ))
        return results

    def fetch_financial_growth(self, symbol: str, limit: int = 10) -> list[FMPFinancialGrowth]:
        """Fetch financial growth rates (annual)."""
        data = self._get(
            f"/financial-growth/{nse_symbol(symbol)}",
            {"period": "annual", "limit": limit},
        )
        results = []
        for d in data:
            results.append(FMPFinancialGrowth(
                symbol=symbol,
                date=d.get("date", ""),
                revenue_growth=_safe_float(d.get("revenueGrowth")),
                gross_profit_growth=_safe_float(d.get("grossProfitGrowth")),
                ebitda_growth=_safe_float(d.get("ebitdagrowth")),
                operating_income_growth=_safe_float(d.get("operatingIncomeGrowth")),
                net_income_growth=_safe_float(d.get("netIncomeGrowth")),
                eps_growth=_safe_float(d.get("epsgrowth")),
                eps_diluted_growth=_safe_float(d.get("epsdilutedGrowth")),
                dividends_per_share_growth=_safe_float(d.get("dividendsperShareGrowth")),
                operating_cash_flow_growth=_safe_float(d.get("operatingCashFlowGrowth")),
                free_cash_flow_growth=_safe_float(d.get("freeCashFlowGrowth")),
                asset_growth=_safe_float(d.get("assetGrowth")),
                debt_growth=_safe_float(d.get("debtGrowth")),
                book_value_per_share_growth=_safe_float(d.get("bookValueperShareGrowth")),
                revenue_growth_3y=_safe_float(d.get("threeYRevenueGrowthPerShare")),
                revenue_growth_5y=_safe_float(d.get("fiveYRevenueGrowthPerShare")),
                revenue_growth_10y=_safe_float(d.get("tenYRevenueGrowthPerShare")),
                net_income_growth_3y=_safe_float(d.get("threeYNetIncomeGrowthPerShare")),
                net_income_growth_5y=_safe_float(d.get("fiveYNetIncomeGrowthPerShare")),
            ))
        return results

    def fetch_analyst_grades(self, symbol: str) -> list[FMPAnalystGrade]:
        """Fetch analyst grade changes."""
        data = self._get(f"/grade/{nse_symbol(symbol)}")
        results = []
        for d in data:
            results.append(FMPAnalystGrade(
                symbol=symbol,
                date=d.get("date", ""),
                grading_company=d.get("gradingCompany", ""),
                previous_grade=d.get("previousGrade"),
                new_grade=d.get("newGrade"),
            ))
        return results

    def fetch_price_targets(self, symbol: str) -> list[FMPPriceTarget]:
        """Fetch analyst price targets."""
        data = self._get(f"/price-target/{nse_symbol(symbol)}")
        results = []
        for d in data:
            results.append(FMPPriceTarget(
                symbol=symbol,
                published_date=d.get("publishedDate", ""),
                analyst_name=d.get("analystName"),
                analyst_company=d.get("analystCompany"),
                price_target=_safe_float(d.get("priceTarget")),
                price_when_posted=_safe_float(d.get("priceWhenPosted")),
            ))
        return results

    def fetch_all(self, symbol: str) -> dict:
        """Fetch all FMP data for a symbol. Returns dict of all data types."""
        dcf = self.fetch_dcf(symbol)
        time.sleep(0.5)

        dcf_history = self.fetch_dcf_history(symbol)
        time.sleep(0.5)

        technicals = self.fetch_technicals_all(symbol)
        time.sleep(0.5)

        key_metrics = self.fetch_key_metrics(symbol)
        time.sleep(0.5)

        financial_growth = self.fetch_financial_growth(symbol)
        time.sleep(0.5)

        analyst_grades = self.fetch_analyst_grades(symbol)
        time.sleep(0.5)

        price_targets = self.fetch_price_targets(symbol)

        return {
            "dcf": dcf,
            "dcf_history": dcf_history,
            "technicals": technicals,
            "key_metrics": key_metrics,
            "financial_growth": financial_growth,
            "analyst_grades": analyst_grades,
            "price_targets": price_targets,
        }
