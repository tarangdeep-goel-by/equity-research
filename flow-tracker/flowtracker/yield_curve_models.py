"""Pydantic models for India G-sec yield-curve snapshots.

A ``YieldCurveSnapshot`` is one calendar-date observation of the 1Y / 5Y /
10Y / 30Y G-sec yields. The same shape (one row per date) lives in
``macro_daily`` — this model exists primarily so the seed JSON and
backfill code can round-trip through Pydantic validation before hitting
the DB.

All yields are in **percent** (7.15 = 7.15%, not 0.0715), matching the
project-wide convention for the existing ``gsec_10y`` column.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class YieldCurveSnapshot(BaseModel):
    """One calendar-date observation of the G-sec yield curve."""

    model_config = ConfigDict(extra="ignore")

    date: str
    """Calendar date as ``YYYY-MM-DD``."""

    gsec_1y: float | None = None
    """1Y G-sec yield % (short end of the curve)."""

    gsec_5y: float | None = None
    """5Y G-sec yield % (belly)."""

    gsec_10y: float | None = None
    """10Y benchmark G-sec yield %."""

    gsec_30y: float | None = None
    """30Y G-sec yield % (long end)."""

    @property
    def slope_10y_minus_1y(self) -> float | None:
        """10Y-1Y spread in basis points. Positive = normal curve;
        negative = inversion (recession signal)."""
        if self.gsec_10y is None or self.gsec_1y is None:
            return None
        return round((self.gsec_10y - self.gsec_1y) * 100, 1)

    @property
    def slope_30y_minus_10y(self) -> float | None:
        """30Y-10Y spread in basis points. Captures term premium at the
        long end."""
        if self.gsec_30y is None or self.gsec_10y is None:
            return None
        return round((self.gsec_30y - self.gsec_10y) * 100, 1)
