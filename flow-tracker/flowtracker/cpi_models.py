"""Pydantic models for India CPI (Consumer Price Index) monthly inflation.

One ``CPIMonth`` row = one calendar month's headline All-India CPI (Combined)
release, as published by MoSPI on (typically) the 12th of the following
month. The ``period`` string is ``YYYY-MM`` and refers to the **data month**
— i.e. the month for which CPI was *measured*, NOT the publication month.
MoSPI publishes the April 2025 CPI on 12 May 2025, but the row carries
``period = "2025-04"``.

Two numeric fields:

* ``cpi_index`` — the index level (base 2012=100 for the All-India CPI
  Combined series; FRED's OECD mirror normalizes to 2010=100 but the YoY%
  is invariant to base).
* ``yoy_pct`` — headline year-on-year inflation in percent (5.1 = 5.1%).

Both fields are optional because a defensive parser (live re-fetch from a
MoSPI PDF) may resolve only one. The store rule is "persist partial rather
than crash" — see ``flow-tracker/CLAUDE.md`` for the project-wide standard.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CPIMonth(BaseModel):
    """One month of headline India CPI inflation."""

    model_config = ConfigDict(extra="ignore")

    period: str
    """Data month as ``YYYY-MM`` (e.g. ``"2025-04"`` for April 2025).
    Note: April 2025 CPI is *released* on 12 May 2025 but ``period``
    refers to the data month, not the release date."""

    cpi_index: float | None = None
    """Headline All-India CPI (Combined) index level. The OECD/FRED
    mirror uses a 2010=100 base; the MoSPI native series uses 2012=100.
    YoY% computed from either base is identical."""

    yoy_pct: float | None = None
    """Year-on-year headline inflation in percent (e.g. ``4.83`` for
    April 2025 CPI of 4.83%). This is the headline number that drives
    the RBI's MPC inflation-targeting decisions and the bond market's
    real-rate expectations."""

    source: str = "seed"
    """Provenance string. ``"seed"`` for bundled historical rows;
    ``"FRED"`` / ``"MoSPI"`` / etc. when live-fetched."""

    source_url: str | None = None
    """The URL the row was scraped from (MoSPI PDF, FRED CSV, etc.).
    Kept for traceability so verifying a row only needs re-fetching this
    URL and re-running the parser."""
