"""Pydantic models for the ADR/GDR programmatic ingestion path.

An ``AdrProgram`` is one Indian-issuer Depositary Receipt program (ADR, GDR,
or ADS) with its custodian bank, share-conversion ratio, and venue metadata.
This is *directory* data — the static "what programs exist" — and is distinct
from the per-symbol per-date ``adr_gdr_outstanding`` table which tracks
*holdings* (units outstanding, % of equity, etc.).

``nse_symbol`` is intentionally optional: many DR programs (HDB, IBN, RDY)
trade under different US tickers than their NSE equivalents and the mapping
is curated manually by the analyst as needed. A NULL value just means
"not yet mapped to an NSE listing"; downstream code must tolerate it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AdrProgram(BaseModel):
    """One Indian Depositary Receipt program directory entry.

    All fields except ``company_name`` and ``program_type`` are optional so
    the model accepts both the curated seed records (which have everything)
    and any future scrape that may have only partial coverage.
    """

    model_config = ConfigDict(extra="ignore")

    nse_symbol: str | None = None
    """Local Indian listing symbol (e.g. INFY, ICICIBANK). May be ``None``
    until manually mapped — many DR programs do not have a 1:1 NSE listing."""

    company_name: str
    """Issuer name as it appears on the depositary's directory."""

    us_ticker: str | None = None
    """US-side ticker (NYSE, OTC, or Pink Sheets). ``None`` for unsponsored
    programs that have not been assigned a US ticker."""

    program_type: str
    """One of ``ADR``, ``GDR``, or ``ADS`` (American Depositary Share)."""

    sponsorship: str | None = None
    """``sponsored`` or ``unsponsored`` — kept as a free-text string because
    some programs are documented with mixed conventions."""

    depositary: str | None = None
    """Custodian bank — typically ``BNY Mellon``, ``Citi``, ``Deutsche Bank``,
    or ``JPMorgan``."""

    ratio: str | None = None
    """Conversion ratio as a free-text string (e.g. ``1 ADR = 1 ord. share``).
    Kept as a string because formats vary widely across depositaries and
    parsing them costs more than the analyst pulling the number out by eye."""

    country: str = "India"
    """Issuer domicile. Defaults to India because that is the only country
    this module currently covers."""
