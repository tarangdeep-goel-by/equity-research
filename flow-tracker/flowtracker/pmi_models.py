"""Pydantic models for India PMI (Purchasing Managers' Index) monthly.

One ``PMIMonth`` row = one calendar month's S&P Global India PMI release.
S&P Global publishes Manufacturing PMI on the 1st-2nd of the next month
and Services PMI on the 3rd-5th. The ``period`` is the **data month** in
``YYYY-MM`` form.

Both headline series are stored alongside on the same row because they
share a publication cadence and analysts cross-reference them constantly
(Services vs Manufacturing divergence is itself a sector-rotation signal).

PMI readings:
* ``> 50`` — expansion
* ``= 50`` — unchanged
* ``< 50`` — contraction

Both fields are optional because Services PMI is occasionally released
later than Manufacturing — a partial row (Manufacturing only) is valid
and gets backfilled on the Services release date.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PMIMonth(BaseModel):
    """One month of headline India Services + Manufacturing PMI."""

    model_config = ConfigDict(extra="ignore")

    period: str
    """Data month as ``YYYY-MM`` (e.g. ``"2025-04"`` for April 2025)."""

    services_pmi: float | None = None
    """Headline S&P Global India Services PMI. Above 50 = expansion."""

    manufacturing_pmi: float | None = None
    """Headline S&P Global India Manufacturing PMI. Above 50 = expansion."""

    source: str = "seed"
    """Provenance — ``"seed"``, ``"S&P Global"``, etc."""

    source_url: str | None = None
    """Trace URL for re-verification."""
