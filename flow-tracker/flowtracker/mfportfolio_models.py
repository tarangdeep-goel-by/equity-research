"""Pydantic models for MF scheme-level portfolio holdings."""

from __future__ import annotations

from pydantic import BaseModel


class MFSchemeHolding(BaseModel):
    """A single stock holding within a MF scheme."""
    month: str              # "2026-02"
    amc: str                # "SBI", "ICICI", "PPFAS", "QUANT", "UTI"
    scheme_name: str
    isin: str
    stock_name: str
    quantity: int
    market_value_lakhs: float
    pct_of_nav: float


class MFHoldingChange(BaseModel):
    """Month-over-month change in a holding."""
    stock_name: str
    isin: str
    amc: str
    scheme_name: str
    prev_month: str
    curr_month: str
    prev_qty: int
    curr_qty: int
    qty_change: int
    prev_value: float
    curr_value: float
    change_type: str  # "NEW", "EXIT", "INCREASE", "DECREASE"
