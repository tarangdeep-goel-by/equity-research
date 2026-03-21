"""Pydantic models for bulk/block deals and short selling data."""

from __future__ import annotations

from pydantic import BaseModel


class BulkBlockDeal(BaseModel):
    """A single bulk deal, block deal, or short selling entry."""
    date: str
    deal_type: str       # "BULK", "BLOCK", "SHORT"
    symbol: str
    client_name: str | None = None
    buy_sell: str | None = None  # "BUY" or "SELL"
    quantity: int
    price: float | None = None   # weighted avg trade price
