"""Pydantic models for corporate filings."""

from __future__ import annotations

from pydantic import BaseModel


class CorporateFiling(BaseModel):
    """A single corporate filing/announcement."""
    symbol: str
    bse_scrip_code: str
    filing_date: str       # YYYY-MM-DD
    category: str          # "Company Update", "Result", "Board Meeting", etc.
    subcategory: str       # "Investor Presentation", "Earnings Call Transcript", etc.
    headline: str
    attachment_name: str   # filename for PDF download
    pdf_flag: int          # 0=AttachLive, 1=AttachHis
    file_size: int | None = None
    news_id: str | None = None
    local_path: str | None = None  # path to downloaded PDF
