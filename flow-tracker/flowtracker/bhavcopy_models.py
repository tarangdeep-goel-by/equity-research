"""Pydantic models for daily bhavcopy (OHLCV + delivery) data."""

from __future__ import annotations

from pydantic import BaseModel


class DailyStockData(BaseModel):
    """Daily OHLCV + delivery data for a single stock."""
    date: str
    symbol: str
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: int           # total traded qty
    turnover: float       # in lakhs
    delivery_qty: int | None = None
    delivery_pct: float | None = None  # THE key signal
