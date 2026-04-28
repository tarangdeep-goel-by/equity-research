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

import asyncio
import csv
import logging
from datetime import date, timedelta
from pathlib import Path

import httpx

from .fda_models import (
    FDAInspection,
    FDAInspectionSummary,
    FdaInspection,
    normalize_outcome,
)

logger = logging.getLogger(__name__)

# openFDA drug enforcement (recall) endpoint — closest free-public proxy for
# USFDA compliance signal. Free, no API key required (rate-limited per IP).
# See https://open.fda.gov/apis/drug/enforcement/
OPENFDA_DRUG_ENFORCEMENT_URL = "https://api.fda.gov/drug/enforcement.json"


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
# Live-fetch: openFDA drug enforcement
# ---------------------------------------------------------------------------
# https://datadashboard.fda.gov/ora/cd/inspections.htm renders results via
# client-side React, so a direct scrape returns only the SPA shell. We fall
# back to openFDA's `/drug/enforcement.json` — well-documented, free, no API
# key required. Records are drug RECALL events (not raw inspections) but
# this is the closest public proxy for USFDA compliance signal on Indian
# pharma firms (SUNPHARMA, DRREDDY, CIPLA, etc.). Caller passes the FDA-
# side firm name (e.g. "Sun Pharmaceutical") since NSE symbol → firm name
# is not auto-derivable.


def _parse_openfda_date(raw: str | None) -> date | None:
    """Parse openFDA's `YYYYMMDD` date format. Returns None if malformed/empty."""
    if not raw:
        return None
    s = str(raw).strip()
    # openFDA uses YYYYMMDD compact form; some fields occasionally arrive ISO.
    if len(s) == 8 and s.isdigit():
        s = f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _record_to_inspection(rec: dict) -> FdaInspection:
    """Map an openFDA drug-enforcement result row to FdaInspection."""
    return FdaInspection(
        firm_name=(rec.get("recalling_firm") or "").strip() or "unknown",
        fei_number=(rec.get("recall_number") or rec.get("event_id") or None),
        inspection_date=_parse_openfda_date(rec.get("recall_initiation_date")),
        classification=(rec.get("classification") or None),
        product_area=(rec.get("product_description") or None),
        country=(rec.get("country") or None),
        posted_date=_parse_openfda_date(rec.get("report_date")),
    )


async def fetch_inspections(
    firm_name_query: str,
    limit: int = 100,
    *,
    timeout: float = 30.0,
) -> list[FdaInspection]:
    """Fetch FDA drug-enforcement records from openFDA for a firm name.

    Hits `https://api.fda.gov/drug/enforcement.json` with a `recalling_firm`
    search filter. Retries once on 5xx. Returns [] for empty results
    (openFDA returns 404 on no-match). Malformed dates parse to None rather
    than dropping the row.

    Args:
        firm_name_query: FDA-side firm name (e.g. "Sun Pharmaceutical").
            Quoted automatically into a phrase search.
        limit: Max records to return (openFDA caps at 1000 per request).
        timeout: Per-attempt HTTP timeout in seconds.
    """
    if not firm_name_query or not firm_name_query.strip():
        return []
    # openFDA expects: recalling_firm:"<phrase>"
    quoted = firm_name_query.strip().replace('"', "")
    params = {
        "search": f'recalling_firm:"{quoted}"',
        "limit": str(min(max(int(limit), 1), 1000)),
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in (1, 2):  # initial + 1 retry
            try:
                resp = await client.get(OPENFDA_DRUG_ENFORCEMENT_URL, params=params)
            except httpx.HTTPError as exc:
                if attempt == 2:
                    logger.warning("openFDA fetch failed (network): %s", exc)
                    return []
                await asyncio.sleep(0.5)
                continue
            # openFDA returns 404 with `{"error": {"code": "NOT_FOUND"}}` on
            # zero matches — treat as empty result, not an error.
            if resp.status_code == 404:
                return []
            if resp.status_code >= 500:
                if attempt == 2:
                    logger.warning(
                        "openFDA fetch failed (HTTP %d after retry)", resp.status_code,
                    )
                    return []
                await asyncio.sleep(0.5)
                continue
            if resp.status_code != 200:
                logger.warning(
                    "openFDA fetch unexpected status %d for firm=%r",
                    resp.status_code, firm_name_query,
                )
                return []
            break
        else:  # pragma: no cover — for-else exits via break above
            return []

    try:
        payload = resp.json()
    except ValueError:
        logger.warning("openFDA returned non-JSON body for firm=%r", firm_name_query)
        return []

    results = payload.get("results") or []
    inspections: list[FdaInspection] = []
    for rec in results:
        try:
            inspections.append(_record_to_inspection(rec))
        except Exception:  # pydantic validation
            logger.warning("openFDA record skipped (validation)", exc_info=True)
            continue
    logger.info(
        "openFDA returned %d records for firm=%r", len(inspections), firm_name_query,
    )
    return inspections
