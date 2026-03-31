"""Pydantic models for Financial Modeling Prep (FMP) data."""

from __future__ import annotations

from pydantic import BaseModel


class FMPDcfValue(BaseModel):
    symbol: str
    date: str
    dcf: float | None = None
    stock_price: float | None = None


class FMPTechnicalIndicator(BaseModel):
    symbol: str
    date: str
    indicator: str  # rsi, sma_50, sma_200, macd, adx
    value: float | None = None


class FMPKeyMetrics(BaseModel):
    symbol: str
    date: str
    revenue_per_share: float | None = None
    net_income_per_share: float | None = None
    operating_cash_flow_per_share: float | None = None
    free_cash_flow_per_share: float | None = None
    cash_per_share: float | None = None
    book_value_per_share: float | None = None
    tangible_book_value_per_share: float | None = None
    shareholders_equity_per_share: float | None = None
    interest_debt_per_share: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    pe_ratio: float | None = None
    price_to_sales_ratio: float | None = None
    pb_ratio: float | None = None
    ev_to_sales: float | None = None
    ev_to_ebitda: float | None = None
    ev_to_operating_cash_flow: float | None = None
    ev_to_free_cash_flow: float | None = None
    earnings_yield: float | None = None
    free_cash_flow_yield: float | None = None
    debt_to_equity: float | None = None
    debt_to_assets: float | None = None
    dividend_yield: float | None = None
    payout_ratio: float | None = None
    roe: float | None = None
    roa: float | None = None
    roic: float | None = None
    # DuPont components
    net_profit_margin_dupont: float | None = None
    asset_turnover: float | None = None
    equity_multiplier: float | None = None


class FMPFinancialGrowth(BaseModel):
    symbol: str
    date: str
    revenue_growth: float | None = None
    gross_profit_growth: float | None = None
    ebitda_growth: float | None = None
    operating_income_growth: float | None = None
    net_income_growth: float | None = None
    eps_growth: float | None = None
    eps_diluted_growth: float | None = None
    dividends_per_share_growth: float | None = None
    operating_cash_flow_growth: float | None = None
    free_cash_flow_growth: float | None = None
    asset_growth: float | None = None
    debt_growth: float | None = None
    book_value_per_share_growth: float | None = None
    revenue_growth_3y: float | None = None
    revenue_growth_5y: float | None = None
    revenue_growth_10y: float | None = None
    net_income_growth_3y: float | None = None
    net_income_growth_5y: float | None = None


class FMPAnalystGrade(BaseModel):
    symbol: str
    date: str
    grading_company: str
    previous_grade: str | None = None
    new_grade: str | None = None


class FMPPriceTarget(BaseModel):
    symbol: str
    published_date: str
    analyst_name: str | None = None
    analyst_company: str | None = None
    price_target: float | None = None
    price_when_posted: float | None = None
