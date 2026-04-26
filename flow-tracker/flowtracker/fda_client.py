"""USFDA inspection / warning-letter loader.

Wave 4-5 P2 (2026-04-25). Scoped down to **manual-seed CSV loader** with a
hook for an optional FDA datadashboard fetcher (commented out — automated
scraping at https://datadashboard.fda.gov/ora/cd/inspections.htm is fragile
and the pages render via client-side JS, so a pure-httpx scrape returns the
SPA shell). Production use today: maintain a CSV at
`~/.config/flowtracker/fda_inspections.csv` and reload via:

    uv run flowtrack fda load-csv ~/.config/flowtracker/fda_inspections.csv

CSV schema (columns, header line required):
    symbol,plant_location,audit_date,outcome,form_483_observation_count,
    warning_letter_active,warning_letter_issued_date,products_impacted,
    remediation_status,source,notes

Empty cells = None / False (for warning_letter_active). Dates are ISO 8601.

The CLI surface for `flowtrack fda` is registered out of band; this module
provides only the parser + the load helper. Persistence lives in
`store.upsert_fda_inspections` — out of scope here unless the agent eval loop
tells us we need DB-backed history (today, agents read concall + AR + this CSV
via `aggregate_fda_summary`).
"""

from __future__ import annotations

import csv
import logging
from datetime import date, timedelta
from pathlib import Path

from .fda_models import FDAInspection, FDAInspectionSummary, normalize_outcome

logger = logging.getLogger(__name__)


def load_inspections_from_csv(csv_path: str | Path) -> list[FDAInspection]:
    """Load a CSV of FDA inspection records into typed FDAInspection rows.

    Raises FileNotFoundError if the path is missing. Ignores rows missing
    required columns (symbol, plant_location, audit_date, outcome) — they
    log a warning and are skipped.
    """
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"FDA inspections CSV not found: {path}")

    rows: list[FDAInspection] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # start=2 since header is row 1
            symbol = (raw.get("symbol") or "").strip().upper()
            plant = (raw.get("plant_location") or "").strip()
            audit_date = (raw.get("audit_date") or "").strip()
            outcome_raw = (raw.get("outcome") or "").strip()
            if not (symbol and plant and audit_date and outcome_raw):
                logger.warning(
                    "FDA CSV row %d skipped — missing required field(s): symbol=%r plant=%r audit_date=%r outcome=%r",
                    i, symbol, plant, audit_date, outcome_raw,
                )
                continue
            obs_raw = (raw.get("form_483_observation_count") or "").strip()
            try:
                obs_count = int(obs_raw) if obs_raw else None
            except ValueError:
                obs_count = None
            wl_active_raw = (raw.get("warning_letter_active") or "").strip().lower()
            wl_active = wl_active_raw in ("true", "1", "yes", "y")
            try:
                rec = FDAInspection(
                    symbol=symbol,
                    plant_location=plant,
                    audit_date=audit_date,
                    audit_end_date=(raw.get("audit_end_date") or None) or None,
                    outcome=normalize_outcome(outcome_raw),
                    form_483_observation_count=obs_count,
                    warning_letter_active=wl_active,
                    warning_letter_issued_date=(raw.get("warning_letter_issued_date") or None) or None,
                    warning_letter_resolved_date=(raw.get("warning_letter_resolved_date") or None) or None,
                    products_impacted=(raw.get("products_impacted") or None) or None,
                    remediation_status=(raw.get("remediation_status") or None) or None,
                    source=(raw.get("source") or "manual").strip() or "manual",
                    notes=(raw.get("notes") or None) or None,
                )
                rows.append(rec)
            except Exception:  # pydantic validation
                logger.warning("FDA CSV row %d failed validation", i, exc_info=True)
                continue
    logger.info("loaded %d FDA inspection rows from %s", len(rows), path)
    return rows


def aggregate_fda_summary(
    inspections: list[FDAInspection],
    symbol: str,
    *,
    as_of: date | None = None,
    ttm_window_days: int = 365,
) -> FDAInspectionSummary:
    """Compute a per-symbol summary from an unsorted list of inspections.

    - Most recent inspection wins for `most_recent_inspection`.
    - Trailing-12-month aggregation for `plants_audited_ttm` and
      `total_form_483_observations_ttm`.
    - All currently `warning_letter_active=True` rows count toward
      `active_warning_letters`. The plant set is preserved (deduped).
    """
    today = as_of or date.today()
    cutoff = today - timedelta(days=ttm_window_days)
    sym_rows = [r for r in inspections if r.symbol.upper() == symbol.upper()]
    if not sym_rows:
        return FDAInspectionSummary(symbol=symbol.upper(), as_of_date=today.isoformat())

    def _to_date(s: str | None) -> date | None:
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except (ValueError, TypeError):
            return None

    # TTM filter
    ttm_rows = [r for r in sym_rows if (d := _to_date(r.audit_date)) and d >= cutoff]
    plants_audited_ttm = len({r.plant_location for r in ttm_rows})
    total_obs_ttm = sum((r.form_483_observation_count or 0) for r in ttm_rows)

    # Active warning letters across all-time window (warning letters can
    # remain active >1yr, so don't TTM-filter these).
    wl_rows = [r for r in sym_rows if r.warning_letter_active]
    active_wl = len(wl_rows)
    active_wl_plants = sorted({r.plant_location for r in wl_rows})

    # Most recent inspection
    sym_rows_sorted = sorted(sym_rows, key=lambda r: r.audit_date or "", reverse=True)
    most_recent = sym_rows_sorted[0]

    # Last warning-letter resolved date (for "WL fully cleared" signals)
    resolved_dates = [
        r.warning_letter_resolved_date for r in sym_rows
        if r.warning_letter_resolved_date
    ]
    last_resolved = max(resolved_dates) if resolved_dates else None

    return FDAInspectionSummary(
        symbol=symbol.upper(),
        as_of_date=today.isoformat(),
        plants_audited_ttm=plants_audited_ttm,
        most_recent_inspection=most_recent,
        total_form_483_observations_ttm=total_obs_ttm,
        active_warning_letters=active_wl,
        active_warning_letter_plants=active_wl_plants,
        last_warning_letter_resolved_date=last_resolved,
    )


# ---------------------------------------------------------------------------
# Stub: FDA datadashboard fetcher
# ---------------------------------------------------------------------------
# https://datadashboard.fda.gov/ora/cd/inspections.htm renders results via
# client-side React. A direct httpx GET returns only the SPA shell. The
# real data lives behind /api/datadashboard/inspections endpoints which
# require a session cookie + CSRF token tied to the browser load. Automated
# scraping is fragile enough that we keep manual-seed as the canonical path
# and leave the live-fetch as a follow-up. If/when we wire it, the skeleton
# below is the entry point.
#
# def fetch_inspections_for_firm(firm_name: str) -> list[FDAInspection]:
#     """Live fetch from FDA datadashboard. Currently stubbed."""
#     raise NotImplementedError(
#         "FDA datadashboard live-fetch not implemented — use load_inspections_from_csv. "
#         "See module docstring for the manual-seed workflow."
#     )
