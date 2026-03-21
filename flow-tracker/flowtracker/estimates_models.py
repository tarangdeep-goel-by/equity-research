"""Pydantic models for consensus estimates and earnings surprises."""

from __future__ import annotations

from pydantic import BaseModel


class ConsensusEstimate(BaseModel):
    """Analyst consensus estimates for a stock."""
    symbol: str
    date: str                      # snapshot date
    target_mean: float | None = None
    target_median: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    num_analysts: int | None = None
    recommendation: str | None = None     # strong_buy/buy/hold/sell
    recommendation_score: float | None = None  # 1.0-5.0
    forward_pe: float | None = None
    forward_eps: float | None = None
    eps_current_year: float | None = None
    eps_next_year: float | None = None
    earnings_growth: float | None = None
    current_price: float | None = None


class EarningsSurprise(BaseModel):
    """Earnings surprise for a quarterly report."""
    symbol: str
    quarter_end: str
    eps_actual: float | None = None
    eps_estimate: float | None = None
    surprise_pct: float | None = None
