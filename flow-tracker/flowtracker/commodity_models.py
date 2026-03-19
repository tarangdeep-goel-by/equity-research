"""Pydantic models for commodity price and correlation data."""

from __future__ import annotations

from pydantic import BaseModel


class CommodityPrice(BaseModel):
    """Daily commodity price record."""
    date: str  # "2025-12-31"
    symbol: str  # "GOLD", "SILVER", "GOLD_INR", "SILVER_INR"
    price: float  # close price
    unit: str  # "USD/oz", "INR/10g", "INR/kg"


class GoldETFNav(BaseModel):
    """Gold/silver ETF NAV record."""
    date: str  # "2025-12-31"
    scheme_code: str  # "140088"
    scheme_name: str | None  # "Nippon India ETF Gold BeES"
    nav: float  # NAV value


class GoldCorrelation(BaseModel):
    """FII flow vs gold price for a single day."""
    date: str
    fii_net: float  # crores
    gold_close: float  # USD/oz
    gold_change_pct: float  # day-over-day %
    gold_inr: float | None  # INR/10g
