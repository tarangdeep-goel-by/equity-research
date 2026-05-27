"""Pydantic models for daily MF scheme NAV history (mfapi.in).

NAVs are per-unit values in rupees (no unit conversion needed). The
scheme code is AMFI's integer identifier, used as the path segment in
``https://api.mfapi.in/mf/{scheme_code}``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MFSchemeNav(BaseModel):
    """Daily NAV observation for a single mutual-fund scheme.

    - ``date`` is ISO ``YYYY-MM-DD`` (mfapi delivers ``DD-MM-YYYY``; the
      client normalises before instantiating).
    - ``nav`` is the per-unit value in rupees.
    - ``scheme_name`` is denormalised so a single-table query is
      sufficient for display; the canonical name is what mfapi returned
      at fetch time.
    """

    model_config = ConfigDict(extra="ignore")

    scheme_code: int
    scheme_name: str
    date: str
    nav: float
