"""Pydantic models for NSE shareholding pattern data."""

from __future__ import annotations

from pydantic import BaseModel


class WatchlistEntry(BaseModel):
    """Stock in watchlist."""
    symbol: str  # "RELIANCE"
    company_name: str | None
    added_at: str  # ISO datetime string


class ShareholdingRecord(BaseModel):
    """Single category for one quarter."""
    symbol: str  # "RELIANCE"
    quarter_end: str  # "2025-12-31"
    category: str  # "Promoter", "FII", "DII", "MF", "Insurance", "Public"
    percentage: float  # 50.30


class ShareholdingSnapshot(BaseModel):
    """All categories for one quarter."""
    symbol: str
    quarter_end: str
    records: list[ShareholdingRecord]

    @property
    def promoter_pct(self) -> float | None:
        """Promoter holding percentage."""
        return next((r.percentage for r in self.records if r.category == "Promoter"), None)

    @property
    def fii_pct(self) -> float | None:
        """FII holding percentage."""
        return next((r.percentage for r in self.records if r.category == "FII"), None)

    @property
    def dii_pct(self) -> float | None:
        """DII holding percentage."""
        return next((r.percentage for r in self.records if r.category == "DII"), None)

    @property
    def public_pct(self) -> float | None:
        """Public holding percentage."""
        return next((r.percentage for r in self.records if r.category == "Public"), None)

    @property
    def mf_pct(self) -> float | None:
        """MF holding percentage."""
        return next((r.percentage for r in self.records if r.category == "MF"), None)


class ShareholdingChange(BaseModel):
    """Quarter-over-quarter change."""
    symbol: str
    category: str
    prev_quarter_end: str
    curr_quarter_end: str
    prev_pct: float
    curr_pct: float
    change_pct: float  # curr - prev


class NSEShareholdingMaster(BaseModel, extra="ignore"):
    """Raw NSE API response item for shareholding data."""
    symbol: str
    company_name: str
    quarter_end: str  # date from API
    xbrl_url: str
