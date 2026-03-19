"""Pydantic models for fundamentals data."""

from __future__ import annotations

from pydantic import BaseModel


class QuarterlyResult(BaseModel):
    symbol: str
    quarter_end: str
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    ebitda: float | None = None
    eps: float | None = None
    eps_diluted: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None


class ValuationSnapshot(BaseModel):
    symbol: str
    date: str
    price: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    pe_trailing: float | None = None
    pe_forward: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    roa: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    free_cash_flow: float | None = None


class LiveSnapshot(BaseModel):
    """Live data — never stored, fetched on demand."""
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    price: float | None = None
    market_cap: float | None = None
    pe_trailing: float | None = None
    pe_forward: float | None = None
    pb_ratio: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    roe: float | None = None
    roa: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    free_cash_flow: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None


class AnnualEPS(BaseModel):
    """Annual EPS from Screener.in P&L — used for historical P/E computation."""
    symbol: str
    fiscal_year_end: str  # "2025-03-31"
    eps: float
    revenue: float | None = None
    net_income: float | None = None


class ValuationBand(BaseModel):
    """Computed from stored snapshots — not stored itself."""
    symbol: str
    metric: str
    min_val: float
    max_val: float
    median_val: float
    current_val: float
    percentile: float
    num_observations: int
    period_start: str
    period_end: str
