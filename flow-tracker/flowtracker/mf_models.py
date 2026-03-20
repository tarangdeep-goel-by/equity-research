"""Pydantic models for AMFI mutual fund flow data."""

from __future__ import annotations

from pydantic import BaseModel


class AMFIReportRow(BaseModel):
    """Raw parsed row from AMFI XLS report."""
    category: str  # "Equity", "Debt", "Hybrid", "Solution", "Other"
    sub_category: str  # "Large Cap Fund", "Multi Cap Fund", etc.
    num_schemes: int | None
    funds_mobilized: float | None  # crores
    redemption: float | None  # crores
    net_flow: float  # crores
    aum: float | None  # crores


class MFMonthlyFlow(BaseModel):
    """Stored record for database — one row per sub-category per month."""
    month: str  # "2026-02"
    category: str
    sub_category: str
    num_schemes: int | None
    funds_mobilized: float | None
    redemption: float | None
    net_flow: float
    aum: float | None


class MFAUMSummary(BaseModel):
    """Monthly aggregate across all categories."""
    month: str  # "2026-02"
    total_aum: float
    equity_aum: float
    debt_aum: float
    hybrid_aum: float
    other_aum: float
    equity_net_flow: float
    debt_net_flow: float
    hybrid_net_flow: float


class MFDailyFlow(BaseModel):
    """Daily MF equity/debt flow from SEBI — one row per date per category."""
    date: str  # "2026-03-19"
    category: str  # "Equity" or "Debt"
    gross_purchase: float  # crores
    gross_sale: float  # crores
    net_investment: float  # crores
