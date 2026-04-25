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


class PromoterPledge(BaseModel):
    """Promoter share pledging/encumbrance for one quarter."""
    symbol: str  # "RELIANCE"
    quarter_end: str  # "2025-12-31"
    pledge_pct: float  # shares pledged as % of total shares
    encumbered_pct: float  # total encumbered (pledge + NDU + other) as % of total shares


class ShareholdingBreakdown(BaseModel):
    """Granular shareholding sub-categories for one (symbol, quarter_end).

    Wave 5 P2 — surfaces the rich sub-category map that the BSE/NSE XBRL
    already exposes but the canonical 7-bucket `shareholding` table flattens
    away. Use to drill into the Public bucket (Retail/HNI/Bodies Corporate),
    the FPI bucket (Cat-I vs Cat-II), and the ADR/GDR custodian holding.

    All percentages are stored in percent form (e.g. 12.5 = 12.5%).
    `dr_underlying_shares` is the raw count of equity shares represented
    by depositary receipts (i.e. ADR/GDR underlying), pulled from the
    `NumberOfSharesUnderlyingOutstandingDepositoryReceipts` element under
    the `CustodianOrDRHolder` context — the definitive source for ADR
    outstanding without scraping the depositary bank's website.
    """
    symbol: str
    quarter_end: str  # "2025-12-31"

    # Public sub-breakdown (Public = Institutions + Non-Institutions)
    retail_pct: float | None = None  # Resident individuals up to ₹2L nominal
    hni_pct: float | None = None  # Resident individuals > ₹2L nominal
    bodies_corporate_pct: float | None = None  # Bodies Corporate
    nri_pct: float | None = None  # Non-Resident Indians

    # FPI sub-breakdown
    fpi_cat1_pct: float | None = None  # Foreign Portfolio Investor Category I
    fpi_cat2_pct: float | None = None  # Foreign Portfolio Investor Category II

    # Public institutional sub-breakdown (sums into DII/MF/Insurance buckets)
    banks_pct: float | None = None
    other_financial_institutions_pct: float | None = None
    nbfc_pct: float | None = None
    provident_pension_funds_pct: float | None = None
    venture_capital_funds_pct: float | None = None
    sovereign_wealth_domestic_pct: float | None = None
    sovereign_wealth_foreign_pct: float | None = None

    # Other foreign / other domestic (catch-all)
    foreign_companies_pct: float | None = None
    foreign_nationals_pct: float | None = None
    foreign_dr_holder_pct: float | None = None  # CustodianOrDRHolder %
    other_foreign_pct: float | None = None
    other_indian_pct: float | None = None

    # Misc
    employee_benefit_trust_pct: float | None = None  # ESOP/EBT-held equity
    iepf_pct: float | None = None  # Investor Education & Protection Fund

    # ADR/GDR specifics — raw share counts (not percentages)
    dr_underlying_shares: int | None = None  # NumberOfSharesUnderlyingOutstandingDepositoryReceipts
    custodian_total_shares: int | None = None  # NumberOfShares under CustodianOrDRHolder

    # Bookkeeping
    fetched_at: str | None = None  # ISO datetime when ingested
