"""US monthly macro economic series fetcher (US add-on): FRED CPI + IIP.

Sources the two headline US monthly macro series from FRED's keyless CSV
download endpoint (``https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>``):

* **CPI** — ``CPIAUCSL`` (CPI for All Urban Consumers, all items, seasonally
  adjusted, index 1982-84=100). Monthly.
* **Industrial Production** — ``INDPRO`` (Industrial Production: Total Index,
  index 2017=100). Monthly.

Both feeds share the same two-column ``date,value`` CSV shape that the India
``cpi_client.parse_fred_csv`` already handles. Here we parse the same shape but
compute ``yoy_pct`` locally (idx_t / idx_{t-12} - 1) * 100 — base-invariant — and
return plain row dicts ready for ``FlowStore.upsert_us_macro_monthly`` (keys:
``series``, ``period``, ``index_value``, ``yoy_pct``, ``source``, ``source_url``).

The ``period`` is normalized to FRED's first-of-month form ``'YYYY-MM-01'`` so it
round-trips through the ``us_macro_monthly`` table without reformatting.

India CPI/IIP code paths, tables, and clients are untouched.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"

# FRED series IDs.
_CPI_SERIES_ID = "CPIAUCSL"   # CPI-U, all items, SA, 1982-84=100
_IIP_SERIES_ID = "INDPRO"     # Industrial Production: Total Index, 2017=100


class USMacroEconClientError(Exception):
    """Raised when a FRED CSV fetch fails (HTTP) or parses to zero rows."""


def parse_fred_monthly_csv(
    csv_text: str,
    *,
    series: str,
    source_url: str | None = None,
) -> list[dict]:
    """Parse a FRED two-column ``date,value`` CSV into upsert-ready row dicts.

    ``series`` tags every row ('cpi' or 'iip'). ``yoy_pct`` is computed from
    the index level 12 months prior (base-invariant); rows with no 12-month
    predecessor get ``yoy_pct = None``. Missing observations (FRED's ``"."``
    sentinel, blanks, ``"NA"``) are skipped defensively. Returns rows ascending
    by period.
    """
    text = (csv_text or "").strip()
    if not text:
        return []

    lines = text.splitlines()
    if len(lines) < 2:
        return []

    # Build period -> index level (skip header line).
    index_by_period: dict[str, float] = {}
    for line in lines[1:]:
        parts = [c.strip() for c in line.split(",")]
        if len(parts) < 2:
            continue
        date_str, value_str = parts[0], parts[1]
        if value_str in (".", "", "NA"):
            continue
        try:
            year, month = int(date_str[:4]), int(date_str[5:7])
            value = float(value_str)
        except (ValueError, IndexError):
            continue
        if not 1 <= month <= 12:
            continue
        index_by_period[f"{year:04d}-{month:02d}"] = value

    rows: list[dict] = []
    for period in sorted(index_by_period):
        year, month = int(period[:4]), int(period[5:7])
        prior = f"{year - 1:04d}-{month:02d}"
        prior_val = index_by_period.get(prior)
        yoy = None
        if prior_val:
            yoy = round((index_by_period[period] / prior_val - 1.0) * 100.0, 2)
        rows.append({
            "series": series,
            "period": f"{period}-01",  # FRED first-of-month form
            "index_value": round(index_by_period[period], 2),
            "yoy_pct": yoy,
            "source": "FRED",
            "source_url": source_url,
        })
    return rows


def _fetch_series(series_id: str, series: str, *, timeout: float = 30.0) -> list[dict]:
    """GET the FRED CSV for ``series_id`` and parse it into ``series`` rows."""
    url = _FRED_CSV_URL.format(series_id=series_id)
    try:
        resp = httpx.get(
            url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "flowtracker-us-macro/1.0"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise USMacroEconClientError(
            f"FRED fetch failed for {series_id}: {exc}"
        ) from exc

    rows = parse_fred_monthly_csv(
        resp.text, series=series, source_url=url,
    )
    if not rows:
        raise USMacroEconClientError(
            f"FRED CSV for {series_id} parsed to zero rows"
        )
    return rows


def fetch_us_cpi(*, timeout: float = 30.0) -> list[dict]:
    """Fetch the full US CPI (``CPIAUCSL``) monthly series from FRED.

    Returns upsert-ready row dicts (series='cpi') ascending by period, with
    ``yoy_pct`` computed locally. Raises :class:`USMacroEconClientError` on any
    HTTP or empty-parse failure.
    """
    return _fetch_series(_CPI_SERIES_ID, "cpi", timeout=timeout)


def fetch_us_iip(*, timeout: float = 30.0) -> list[dict]:
    """Fetch the full US Industrial Production (``INDPRO``) series from FRED.

    Returns upsert-ready row dicts (series='iip') ascending by period, with
    ``yoy_pct`` computed locally. Raises :class:`USMacroEconClientError` on any
    HTTP or empty-parse failure.
    """
    return _fetch_series(_IIP_SERIES_ID, "iip", timeout=timeout)
