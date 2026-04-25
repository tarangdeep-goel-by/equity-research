"""Pydantic models for USFDA inspection / warning-letter records.

Wave 4-5 P2 (2026-04-25) — pharma autoeval (SUNPHARMA / DRREDDY / CIPLA)
flagged that USFDA compliance status (warning letters, Form 483s, OAI status,
ANDA pipeline) wasn't surfaced via any agent tool. This module defines the
canonical record shape; `fda_client.py` exposes the loader (CSV manual-seed
plus optional FDA datadashboard fetcher), and `store.upsert_fda_inspections`
persists records keyed by (symbol, plant_id, audit_date).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


# Canonical inspection-outcome taxonomy (USFDA terminology). Order is rough
# severity ascending → keeps `red_flag_count` sums monotonic.
INSPECTION_OUTCOMES = (
    "NAI",          # No Action Indicated — clean inspection
    "VAI",          # Voluntary Action Indicated — minor 483, no enforcement
    "OAI",          # Official Action Indicated — major 483 or warning letter likely
    "warning_letter",  # Warning Letter issued
    "import_alert",  # Import Alert (e.g. 66-40) — products blocked at port of entry
    "consent_decree",  # Consent decree — most severe enforcement
)


class FDAInspection(BaseModel, extra="ignore"):
    """A single USFDA inspection record for a manufacturing facility.

    Records are tied to symbol via plant_id (an internal FK to
    `pharma_plants` table — out of scope for this PR; we just store the
    plant_location string for now).
    """

    symbol: str
    plant_location: str         # "Halol, Gujarat, India" / "Mohali, India"
    audit_date: str             # YYYY-MM-DD inspection start date
    audit_end_date: str | None = None
    outcome: str                # one of INSPECTION_OUTCOMES
    form_483_observation_count: int | None = None
    warning_letter_active: bool = False
    warning_letter_issued_date: str | None = None
    warning_letter_resolved_date: str | None = None
    products_impacted: str | None = None  # brief description
    remediation_status: str | None = None  # "closed" | "in_progress" | etc.
    source: str = "manual"      # manual | fda_datadashboard | annual_report
    notes: str | None = None    # any caveats (e.g. "Sun Pharma — 5 day inspection")


class FDAInspectionSummary(BaseModel, extra="ignore"):
    """Aggregated FDA-compliance summary for a single symbol — what agents
    consume via `get_sector_kpis(usfda_*)` lookups when concall data is
    missing or stale.
    """

    symbol: str
    as_of_date: str             # YYYY-MM-DD when the summary was computed
    plants_audited_ttm: int = 0
    most_recent_inspection: FDAInspection | None = None
    total_form_483_observations_ttm: int = 0
    active_warning_letters: int = 0
    active_warning_letter_plants: list[str] = []
    last_warning_letter_resolved_date: str | None = None


def normalize_outcome(raw: str) -> str:
    """Normalize free-text inspection outcome to the canonical taxonomy.

    Returns the canonical token if recognized, otherwise echoes the raw
    string lowercased. Caller can choose to filter unrecognized tokens.
    """
    if not raw:
        return "unknown"
    t = raw.strip().lower()
    # Direct token matches
    for token in INSPECTION_OUTCOMES:
        if token.lower() == t:
            return token
    # Common variant prefixes
    if "warn" in t and "letter" in t:
        return "warning_letter"
    if "import" in t and "alert" in t:
        return "import_alert"
    if "consent" in t:
        return "consent_decree"
    if t.startswith("oai"):
        return "OAI"
    if t.startswith("vai"):
        return "VAI"
    if t.startswith("nai") or "no action" in t or "no observations" in t:
        return "NAI"
    return t  # echo back unknown — caller decides whether to drop
