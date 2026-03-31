"""Pydantic models for portfolio tracking."""

from __future__ import annotations

from pydantic import BaseModel


class PortfolioHolding(BaseModel):
    """A single portfolio holding."""

    symbol: str
    quantity: int
    avg_cost: float
    buy_date: str | None = None
    notes: str | None = None
    added_at: str | None = None
