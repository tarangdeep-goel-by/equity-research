"""Pydantic models for NSE/BSE surveillance flags (ASM/ESM/GSM).

A ``SurveillanceFlag`` is one surveillance designation against a single
listed scrip on a single exchange on a single effective date. The same
symbol can carry multiple concurrent flags (e.g. NSE long-term ASM Stage I
and NSE short-term ASM Stage II) — uniqueness is therefore
``(symbol, alert_type, exchange, effective_date)``.

Field shape mirrors the upstream NSE JSON (ASM, GSM) and BSE HTML (ESM),
flattened across both exchanges so the screener integration can do one
lookup per symbol regardless of which exchange surfaced the flag.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SurveillanceFlag(BaseModel):
    """One regulatory surveillance flag on a listed scrip.

    ``symbol`` is the NSE symbol for NSE flags and the BSE scrip code (or
    BSE-side ticker if available) for BSE flags. Callers that want to
    cross-reference must consult both ``symbol`` and ``exchange``.

    ``stage`` varies by alert type:
    - ASM: ``"Stage I"`` .. ``"Stage IV"`` (NSE long-term or short-term)
    - GSM: ``"I"`` .. ``"VIII"`` (NSE Graded Surveillance Measure stage)
    - ESM: ``"Stage I"`` / ``"Stage II"`` (BSE Enhanced Surveillance Measure)
    """

    model_config = ConfigDict(extra="ignore")

    symbol: str
    """NSE symbol or BSE scrip code/ticker."""

    alert_type: str
    """``"ASM"``, ``"ESM"``, or ``"GSM"``."""

    stage: str | None = None
    """Surveillance stage label as published by the exchange. ``None`` if the
    upstream feed omits the stage (rare but tolerated for forward-compat)."""

    exchange: str
    """``"NSE"`` or ``"BSE"``."""

    effective_date: str
    """ISO ``YYYY-MM-DD`` — the date the flag became effective. Defaults to
    today when the source publishes only a free-text date that fails parsing."""

    reason: str | None = None
    """Free-text reason / surveillance description as published. Optional —
    BSE's ESM feed often omits this, NSE's ASM/GSM populate ``survDesc``."""
