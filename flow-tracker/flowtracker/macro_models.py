"""Pydantic models for macro indicator data."""

from __future__ import annotations

from pydantic import BaseModel


class MacroSnapshot(BaseModel):
    """Daily macro indicator snapshot."""
    date: str          # "2026-03-20"
    india_vix: float | None = None
    usd_inr: float | None = None
    brent_crude: float | None = None  # USD/barrel
    gsec_10y: float | None = None     # yield %
