"""Pydantic models for composite screening engine."""

from __future__ import annotations

from pydantic import BaseModel


class FactorScore(BaseModel):
    """Individual factor score for a stock."""
    factor: str
    score: float        # 0-100 normalized
    raw_value: float | None = None
    detail: str = ""    # human-readable explanation


class StockScore(BaseModel):
    """Composite scorecard for a single stock."""
    symbol: str
    company_name: str | None = None
    industry: str | None = None
    composite_score: float  # 0-100 weighted average
    factors: list[FactorScore]
    rank: int = 0
