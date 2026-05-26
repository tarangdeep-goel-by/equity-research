"""Pydantic models for market breadth metrics.

Market breadth is a participation indicator — instead of looking at the
index level alone, we measure what fraction of constituents are
participating in a move (above/below 200DMA, advancing vs declining,
making new 52-week highs/lows). Used to validate or refute bear-bottom
and bull-top index signals.
"""

from __future__ import annotations

from pydantic import BaseModel


class BreadthSnapshot(BaseModel):
    """Daily market-breadth snapshot for a single index.

    Computed from `daily_stock_data` + `index_constituents`. One row per
    (date, index_name). Stored in `market_breadth_daily`.
    """

    date: str                      # "YYYY-MM-DD"
    index_name: str                # e.g. "NIFTY 500", "NIFTY 50"
    total: int                     # constituents with a price on this date
    pct_above_200dma: float | None # 0-100 form (25.0 = 25%); None if <150 history days
    advance: int                   # close > prev_close
    decline: int                   # close < prev_close
    unchanged: int                 # close == prev_close (or prev_close missing)
    new_52w_highs: int             # close >= rolling 252-day high ending today
    new_52w_lows: int              # close <= rolling 252-day low ending today
    ad_ratio: float | None         # advance / decline; None if decline == 0
