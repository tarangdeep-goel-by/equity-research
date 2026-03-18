"""Pydantic models for index scanning and batch fetch operations."""

from __future__ import annotations

from pydantic import BaseModel


class IndexConstituent(BaseModel):
    """Stock in Nifty 50/Next50/Midcap100."""
    symbol: str  # "RELIANCE"
    index_name: str  # "NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 100"
    company_name: str | None
    industry: str | None


class BatchFetchResult(BaseModel):
    """Summary of a batch fetch operation."""
    total: int
    fetched: int
    skipped: int
    failed: int
    errors: list[str]  # symbol: error message


class ScanSummary(BaseModel):
    """Coverage stats for the scanner."""
    total_symbols: int
    symbols_with_data: int
    latest_quarter: str | None
    missing_symbols: list[str]
