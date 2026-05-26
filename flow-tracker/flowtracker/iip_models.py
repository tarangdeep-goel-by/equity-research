"""Pydantic models for India IIP (Index of Industrial Production) monthly.

One ``IIPMonth`` row = one calendar month's IIP General release, as published
by MoSPI on (typically) the 12th of two months after (e.g. April 2025 IIP
released 12 June 2025 — one-month publication lag). The ``period`` is the
**data month** in ``YYYY-MM`` form, NOT the release month.

Two numeric fields:

* ``iip_index`` — the general (all-sectors) IIP index level. The MoSPI
  native base is 2011-12 = 100; FRED's OECD-sourced mirror
  (``INDPROINDMISMEI``) uses a 2015 = 100 base. YoY% is invariant.
* ``yoy_pct`` — year-on-year growth in percent (5.4 = 5.4%). The headline
  number tracked by macro analysts as a real-time manufacturing-activity
  proxy (alongside PMI Manufacturing).

Both fields are optional — defensive parser scenario.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IIPMonth(BaseModel):
    """One month of headline India IIP (general) industrial-production growth."""

    model_config = ConfigDict(extra="ignore")

    period: str
    """Data month as ``YYYY-MM`` (e.g. ``"2025-04"`` for April 2025)."""

    iip_index: float | None = None
    """Headline IIP General index level."""

    yoy_pct: float | None = None
    """Year-on-year growth in percent (e.g. ``5.4`` = 5.4%)."""

    source: str = "seed"
    """Provenance — ``"seed"``, ``"FRED"``, ``"MoSPI"``, etc."""

    source_url: str | None = None
    """Trace URL for re-verification."""
