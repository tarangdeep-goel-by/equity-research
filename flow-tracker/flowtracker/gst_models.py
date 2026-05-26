"""Pydantic models for monthly GST (Goods & Services Tax) collections.

One ``GSTCollectionMonth`` row = one calendar month's gross GST revenue, as
published in the CBIC monthly press release (mirrored by PIB). All monetary
values are in **₹ crore** (the unit CBIC reports in), per the project-wide
monetary-units standard (see flow-tracker/CLAUDE.md → "Unit standard").

The ``period`` string follows ``YYYY-MM`` and refers to the **collection
month** — i.e. the month for which GST was *collected*, not the month the
press release was published. CBIC publishes the April-2025 collection number
on 1 May 2025, but the row carries ``period = "2025-04"``.

All numeric fields are optional because the parser is defensive: a single
unparsed line in the source PDF/HTML must not crash the whole pipeline. If
``gross_collection_cr`` is None the row is still informative (we know the
press release was scraped, just couldn't extract the headline number) and
downstream queries can surface the gap.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GSTCollectionMonth(BaseModel):
    """One month of headline GST collection data from the CBIC press release."""

    model_config = ConfigDict(extra="ignore")

    period: str
    """Collection month as ``YYYY-MM`` (e.g. ``"2025-04"`` for April 2025).
    Note: April 2025 collection is *released* on 1 May 2025 but ``period``
    refers to the collection month, not the release date."""

    gross_collection_cr: float | None = None
    """Gross GST revenue collected, ₹ crore. The headline number — equals
    cgst + sgst + igst + cess. CBIC reports this as e.g. ``₹2,10,267 crore``
    for the all-time-high in April 2025; we store it as ``210267.0``."""

    cgst_cr: float | None = None
    """Central GST component, ₹ crore."""

    sgst_cr: float | None = None
    """State GST component, ₹ crore."""

    igst_cr: float | None = None
    """Integrated GST component (domestic + imports), ₹ crore. Typically the
    largest line because it captures inter-state and import flows."""

    cess_cr: float | None = None
    """Compensation cess (luxury / sin goods), ₹ crore. Smaller absolute
    value (~9-13k cr/month) but a useful proxy for discretionary consumption."""

    domestic_cr: float | None = None
    """Gross revenue from domestic transactions, ₹ crore. Domestic + imports
    sum to the gross figure but the split is reported separately."""

    imports_cr: float | None = None
    """Gross revenue from imports (IGST + cess on imports), ₹ crore."""

    growth_yoy_pct: float | None = None
    """Year-on-year growth in gross collection vs the same month a year ago,
    in percent (e.g. ``12.6`` means 12.6% higher than April 2024). CBIC
    publishes this directly in the release; we also recompute it when
    backfilling history (see ``store.get_gst_yoy_series``)."""

    source_url: str | None = None
    """The URL the data was scraped from (CBIC PDF, GST Council PDF, or PIB
    press release page). Kept for traceability — verifying a row only needs
    re-fetching this URL and re-running the parser."""
