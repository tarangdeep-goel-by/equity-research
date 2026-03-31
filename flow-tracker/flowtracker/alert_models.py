"""Pydantic models for alert system."""

from __future__ import annotations

from pydantic import BaseModel


class Alert(BaseModel):
    """A configured alert condition."""

    id: int | None = None
    symbol: str
    condition_type: str  # price_above, price_below, pe_above, pe_below, fii_pct_below, mf_pct_above, rsi_below, rsi_above, pledge_above, dcf_upside_above
    threshold: float
    active: bool = True
    last_triggered: str | None = None
    created_at: str | None = None
    notes: str | None = None


class TriggeredAlert(BaseModel):
    """An alert that has been triggered."""

    alert: Alert
    current_value: float | None = None
    message: str = ""
