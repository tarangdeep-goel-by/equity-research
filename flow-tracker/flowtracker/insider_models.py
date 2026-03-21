"""Pydantic models for insider/SAST transaction data."""

from __future__ import annotations

from pydantic import BaseModel


class InsiderTransaction(BaseModel):
    """A single insider (PIT regulation) transaction."""
    date: str                    # acquisition/disposal date
    symbol: str
    person_name: str
    person_category: str         # Promoters, Director, KMP, etc.
    transaction_type: str        # Buy, Sell, Pledge, Revoke, etc.
    quantity: int
    value: float                 # INR value
    mode: str | None = None      # Market Purchase, Off Market, ESOP, etc.
    holding_before_pct: float | None = None
    holding_after_pct: float | None = None
