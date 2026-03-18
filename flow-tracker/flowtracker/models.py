"""Pydantic models for FII/DII flow data."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class NSEApiResponse(BaseModel, extra="ignore"):
    """Raw API response item from NSE fiidiiTradeReact endpoint."""
    category: str
    date: str  # "17-Mar-2026"
    buyValue: str  # crores, as string
    sellValue: str  # crores, as string
    netValue: str  # crores, as string


class DailyFlow(BaseModel):
    """Single day's flow for one category (FII or DII)."""
    date: date
    category: str  # "FII" or "DII"
    buy_value: float  # crores
    sell_value: float  # crores
    net_value: float  # crores


class DailyFlowPair(BaseModel):
    """FII + DII flows for a single day."""
    date: date
    fii: DailyFlow
    dii: DailyFlow

    @property
    def fii_dii_net_diff(self) -> float:
        """FII net minus DII net — shows relative positioning."""
        return self.fii.net_value - self.dii.net_value


class StreakInfo(BaseModel):
    """Consecutive buying/selling streak for a category."""
    category: str  # "FII" or "DII"
    direction: str  # "buying" or "selling"
    days: int
    cumulative_net: float  # crores
    start_date: date
    end_date: date
