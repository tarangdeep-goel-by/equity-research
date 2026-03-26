"""Pydantic models for the research data API layer."""

from __future__ import annotations

from pydantic import BaseModel


class MacroSnapshot(BaseModel):
    """Current macro context for research."""

    vix: float | None = None
    usd_inr: float | None = None
    brent_crude: float | None = None
    gsec_10y: float | None = None
    vix_date: str | None = None


class FIIDIIStreak(BaseModel):
    """Current buying/selling streak for FII and DII."""

    fii_streak_days: int = 0
    fii_streak_direction: str = ""  # "buying" or "selling"
    fii_streak_total: float = 0  # total net during streak
    dii_streak_days: int = 0
    dii_streak_direction: str = ""
    dii_streak_total: float = 0


class DeliveryRecord(BaseModel):
    """Daily stock delivery data."""

    date: str
    close: float | None = None
    volume: int | None = None
    delivery_qty: int | None = None
    delivery_pct: float | None = None
