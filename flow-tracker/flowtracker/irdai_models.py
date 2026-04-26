"""Pydantic models for IRDAI Net Premium ingestion path.

Lives outside ``fund_models`` to keep yfinance models clean of insurer-only
schema. Consumers import ``NetPremiumDatapoint`` directly from this module.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_validator


_FISCAL_PERIOD_RE = re.compile(r"^FY\d{2}(-Q[1-4])?$")


class NetPremiumDatapoint(BaseModel):
    """One Net Premium Earned observation for one insurer for one fiscal period.

    Sourced from the IRDAI Public Disclosure portal — Form L-1-A-RA Revenue
    Account, line "Premium earned (Net) = Premium - Reinsurance ceded". For
    life insurers reinsurance ceded is small (<1% of gross), so this is the
    canonical underwriting top line that the read-side
    ``ResearchDataAPI._apply_insurance_headline`` swap layer prefers.

    ``fiscal_period`` is human-friendly (``FY25``, ``FY26-Q3``);
    ``period_end`` is the canonical ISO date used by the storage layer
    (``annual_financials.fiscal_year_end`` or ``quarterly_results.quarter_end``).
    """

    model_config = ConfigDict(extra="ignore")

    symbol: str
    fiscal_period: str
    period_end: str  # YYYY-MM-DD
    net_premium_earned_cr: float
    source_url: str | None = None
    fetched_at: str | None = None

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("fiscal_period")
    @classmethod
    def _fp_format(cls, v: str) -> str:
        v = v.strip().upper()
        if not _FISCAL_PERIOD_RE.match(v):
            raise ValueError(
                f"fiscal_period must match FY<YY> or FY<YY>-Q[1-4], got {v!r}"
            )
        return v

    @field_validator("period_end")
    @classmethod
    def _date_iso(cls, v: str) -> str:
        # Accept YYYY-MM-DD only — fail loudly on US-style dates.
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"period_end must be YYYY-MM-DD, got {v!r}") from exc
        return v

    @field_validator("net_premium_earned_cr")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"net_premium_earned_cr must be > 0, got {v!r}")
        # Sanity bound: IRDAI's biggest insurer (LIC) reports ~₹4.9 lakh Cr
        # FY25 annual; quarterly tops out near ₹1.5 lakh Cr. A single value
        # >₹10 lakh Cr (10M × 10M = 100T INR) is almost certainly a unit
        # error (lakh confused for crore, or paise confused for rupee).
        if v > 1_000_000:
            raise ValueError(
                f"net_premium_earned_cr={v} > 10 lakh Cr — suspected unit error "
                "(values must be in crores)"
            )
        return v

    @property
    def is_annual(self) -> bool:
        """True for full-year datapoints (no quarter suffix)."""
        return "-Q" not in self.fiscal_period

    @property
    def is_quarterly(self) -> bool:
        return not self.is_annual

    @classmethod
    def now_utc(cls) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
