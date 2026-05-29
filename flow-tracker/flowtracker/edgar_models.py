"""Pydantic models for SEC EDGAR XBRL facts and normalized US fundamentals
rows (US add-on, Phase 3.1).

The normalized models mirror the dict keys consumed by the P3.0 store upserts
(``UsMarketMixin.upsert_us_annual_financials`` /
``upsert_us_quarterly_financials``). They exist mostly for typed construction +
validation in the client; the upserts take plain dicts, so callers usually pass
``model.model_dump()``. ``extra="ignore"`` keeps dict passthrough safe.

Monetary values are USD **millions** (matching ``_USD_VALIDATION_RULES`` in
``store_domains/_shared.py``); per-share (EPS) values are raw USD; share counts
are raw.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class XbrlFact(BaseModel):
    """A single XBRL fact entry from companyfacts ``units.<unit>`` lists."""

    model_config = ConfigDict(extra="ignore")

    end: str
    val: float
    accn: str
    form: str | None = None
    fy: int | None = None
    fp: str | None = None
    start: str | None = None
    frame: str | None = None
    filed: str | None = None


class UsAnnualRow(BaseModel):
    """Normalized row for ``us_annual_financials`` (one per fiscal_year)."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    market: str = "NASDAQ"
    currency: str = "USD"
    fiscal_year: int
    revenue: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_equity: float | None = None
    total_debt: float | None = None
    total_cash: float | None = None
    eps: float | None = None
    operating_cash_flow: float | None = None
    free_cash_flow: float | None = None
    shares_outstanding: float | None = None


class UsQuarterlyRow(BaseModel):
    """Normalized row for ``us_quarterly_financials`` (one per quarter_end)."""

    model_config = ConfigDict(extra="ignore")

    symbol: str
    market: str = "NASDAQ"
    currency: str = "USD"
    quarter_end: str
    fiscal_year: int
    fiscal_period: str
    revenue: float | None = None
    net_income: float | None = None
    eps: float | None = None
