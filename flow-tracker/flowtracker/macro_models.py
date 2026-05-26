"""Pydantic models for macro indicator data."""

from __future__ import annotations

from pydantic import BaseModel


class MacroSnapshot(BaseModel):
    """Daily macro indicator snapshot.

    G-sec yields are stored at four canonical tenors (1Y, 5Y, 10Y, 30Y) so
    the yield-curve module can compute slope, butterfly, and inversion
    signals without round-tripping through additional tables. All yields
    are in percent (7.15 = 7.15%, not 0.0715).
    """
    date: str          # "2026-03-20"
    india_vix: float | None = None
    usd_inr: float | None = None
    eur_inr: float | None = None
    gbp_inr: float | None = None
    brent_crude: float | None = None  # USD/barrel
    gsec_1y: float | None = None      # 1Y G-sec yield %
    gsec_5y: float | None = None      # 5Y G-sec yield %
    gsec_10y: float | None = None     # 10Y G-sec yield %
    gsec_30y: float | None = None     # 30Y G-sec yield %


class MacroSystemCredit(BaseModel):
    """Weekly system credit/deposit snapshot from RBI WSS.

    The WSS (Weekly Statistical Supplement) publishes Friday-of-week,
    but Section 4 ("Scheduled Commercial Banks - Business in India") is
    fortnight-keyed (15th and last calendar day of each month under the
    revised post-Dec-2025 definition). Hence ``as_of_date`` is the
    fortnight-end date the RBI labels in the table; ``release_date`` is
    the WSS publication date (Friday).
    """
    release_date: str               # WSS publication date "YYYY-MM-DD" (Friday)
    as_of_date: str | None = None   # Fortnight-end date the data describes (often Mar 31, Apr 15, ...)
    aggregate_deposits_cr: float | None = None       # ₹ Cr outstanding
    bank_credit_cr: float | None = None              # ₹ Cr outstanding
    deposit_growth_yoy: float | None = None          # YoY growth %
    credit_growth_yoy: float | None = None           # YoY growth %
    non_food_credit_growth_yoy: float | None = None  # YoY growth %
    cd_ratio: float | None = None                    # Credit/Deposit ratio %
    m3_growth_yoy: float | None = None               # YoY M3 growth %
    source: str = "RBI_WSS"
