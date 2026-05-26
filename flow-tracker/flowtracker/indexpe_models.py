"""Pydantic models for index-level valuation snapshots (PE/PB/Div Yield).

Source: niftyindices.com historical PE/PB/Div Yield endpoint
(`Backpage.aspx/getpepbHistoricaldataDBtoString`).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IndexValuation(BaseModel):
    """Daily index valuation snapshot (PE / PB / Dividend Yield).

    - `date` is an ISO date string ("YYYY-MM-DD").
    - `index_name` mirrors the canonical NSE display name
      (e.g. "NIFTY 50", "NIFTY SMALLCAP 250").
    - `dividend_yield` is in percent form (1.5 = 1.5%).
    """

    model_config = ConfigDict(extra="ignore")

    date: str
    index_name: str
    pe: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None
