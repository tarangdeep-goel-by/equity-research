"""Monthly India CPI fetcher: bundled seed + optional live source-URL parse.

Source authority
----------------
MoSPI publishes the headline CPI (Combined) on the 12th of each month for
the prior month. The native PDF is at ``mospi.gov.in/cpi``, and FRED
mirrors the OECD series at ``INDCPIALLMINMEI``. Both are free; FRED's
CSV download URL (``https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDCPIALLMINMEI``)
works without an API key.

Two ingestion paths
-------------------
1. **Bundled seed JSON** (``data/cpi_monthly_seed.json``) — verified
   historical rows back to 2014-01. Used by ``cpi fetch`` / ``cpi backfill``
   by default. ~136 months of data ship in the seed.
2. **Explicit ``source_url``** — if a caller passes ``source_url=...`` to
   :meth:`CPIClient.fetch_month`, the client httpx-downloads the bytes,
   sniffs PDF vs HTML vs CSV, and runs the defensive parser.

Parsers
-------
* :func:`parse_mospi_release_text` — defensive regex parser for MoSPI
  press releases ("All India CPI ... 4.83 per cent" / "headline inflation
  at 4.83%").
* :func:`parse_fred_csv` — FRED CSV (two columns: date, index). YoY% is
  computed by joining the row to the same month 12 periods prior.

Both parsers are defensive — any field that fails to match is set to
``None`` rather than crashing the row.
"""

from __future__ import annotations

import calendar
import io
import json
import logging
import re
from datetime import date
from importlib import resources
from typing import Any

import httpx

from flowtracker.cpi_models import CPIMonth

logger = logging.getLogger(__name__)

_SEED_PACKAGE = "flowtracker.data"
_SEED_FILE = "cpi_monthly_seed.json"

# dbnomics: free, no-auth aggregator. The IMF International Financial
# Statistics (IFS) India CPI (All items, Index) monthly series is the
# freshest free India headline-CPI level we found on dbnomics — it runs
# meaningfully ahead of FRED's discontinued OECD mirror
# (INDCPIALLMINMEI ends 2025-03) and the bundled seed (2025-04). As of
# May 2026 it extends to 2025-06. YoY% is computed locally from the
# 12-months-prior index level in the same payload (base-invariant).
_DBNOMICS_BASE = "https://api.db.nomics.world/v22"
_DBNOMICS_CPI_SERIES = "IMF/IFS/M.IN.PCPI_IX"


# ---------------------------------------------------------------------------
# Period helpers (identical pattern to gst_client; kept private so each
# module can validate its own period domain — CPI starts 2011 vs GST 2017)
# ---------------------------------------------------------------------------

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _validate_period(period: str) -> tuple[int, int]:
    """Validate a ``YYYY-MM`` period string. Returns ``(year, month)``."""
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must match YYYY-MM, got {period!r}")
    year = int(m.group(1))
    month = int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"period month must be 1..12, got {month}")
    if not 2011 <= year <= 2100:
        # MoSPI's current CPI (Combined) series starts Jan 2011.
        raise ValueError(f"period year must be 2011..2100, got {year}")
    return year, month


def _iter_periods(start: str, end: str) -> list[str]:
    """Yield each ``YYYY-MM`` between start and end inclusive."""
    sy, sm = _validate_period(start)
    ey, em = _validate_period(end)
    if (sy, sm) > (ey, em):
        raise ValueError(f"start {start} is after end {end}")
    periods: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        periods.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return periods


# ---------------------------------------------------------------------------
# Press-release defensive regex parser (MoSPI PDFs)
# ---------------------------------------------------------------------------

# A reasonable plausible CPI YoY range — anything outside is parser confusion
# (e.g. matched the WPI value or the food-only sub-index).
_YOY_VALID_RANGE: tuple[float, float] = (-5.0, 20.0)
_INDEX_VALID_RANGE: tuple[float, float] = (50.0, 500.0)


_MOSPI_YOY_PATTERNS = [
    # "All India CPI Combined inflation for April 2025 stood at 3.16 per cent"
    # The gap may contain digits (year, dates), so anchor on '%' / 'per cent'
    # at the end and require the captured number to have a decimal point
    # (year-like 2025 is bare integer, won't match `\d+\.\d+`).
    re.compile(
        r"all[\s-]+india\s+(?:cpi\s+)?(?:combined\s+)?"
        r"(?:inflation\b)?.{0,120}?"
        r"(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "headline (CPI) inflation at 4.83%" / "headline inflation: 4.83%"
    re.compile(
        r"headline\s+(?:cpi\s+)?inflation\s*(?:rate|at|:)?\s*"
        r"(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
        re.IGNORECASE,
    ),
    # "Y-o-Y inflation ... 4.83%"
    re.compile(
        r"y[\s-]*o[\s-]*y\s+inflation.{0,60}?"
        r"(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
        re.IGNORECASE | re.DOTALL,
    ),
]

_MOSPI_INDEX_PATTERNS = [
    # "All India CPI (Combined) ... index ... 187.3"
    re.compile(
        r"all[\s-]+india\s+(?:cpi\s+)?\(?(?:combined\s*)?\)?\s*index.{0,80}?"
        r"(\d+\.\d+)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "CPI index for ... is 187.3"
    re.compile(
        r"cpi\s+index.{0,60}?(\d+\.\d+)",
        re.IGNORECASE | re.DOTALL,
    ),
]


def parse_mospi_release_text(text: str) -> dict[str, float | None]:
    """Run the defensive regex parser over a MoSPI CPI press-release body.

    Returns ``{"cpi_index": ..., "yoy_pct": ...}`` with ``None`` for any
    field that couldn't be matched (defensive — see project rule
    "partial parses must persist, not crash the whole run").
    """
    flat = re.sub(r"\s+", " ", text or "").strip()
    out: dict[str, float | None] = {"cpi_index": None, "yoy_pct": None}

    for pat in _MOSPI_YOY_PATTERNS:
        m = pat.search(flat)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if _YOY_VALID_RANGE[0] <= val <= _YOY_VALID_RANGE[1]:
            out["yoy_pct"] = round(val, 2)
            break

    for pat in _MOSPI_INDEX_PATTERNS:
        m = pat.search(flat)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if _INDEX_VALID_RANGE[0] <= val <= _INDEX_VALID_RANGE[1]:
            out["cpi_index"] = round(val, 2)
            break

    if all(v is None for v in out.values()):
        sample = flat[:240]
        logger.warning("CPI parser extracted zero fields. Source sample: %r", sample)
    return out


# ---------------------------------------------------------------------------
# FRED CSV parser
# ---------------------------------------------------------------------------


def parse_fred_csv(csv_text: str) -> list[CPIMonth]:
    """Parse the FRED CSV download for ``INDCPIALLMINMEI`` (or equivalent).

    The CSV has a single index column. We don't have YoY in the file — that's
    derived downstream (12-month-lag join in the store). Returns a list of
    :class:`CPIMonth` rows, one per row in the file with a real numeric value.
    """
    rows: list[CPIMonth] = []
    text = (csv_text or "").strip()
    if not text:
        return rows

    lines = text.splitlines()
    # Skip header
    header = [c.strip() for c in lines[0].split(",")] if lines else []
    if len(header) < 2:
        logger.warning("CPI FRED CSV missing header — got %r", header)
        return rows

    for line in lines[1:]:
        parts = [c.strip() for c in line.split(",")]
        if len(parts) < 2:
            continue
        date_str, value_str = parts[0], parts[1]
        if value_str in (".", "", "NA"):
            continue
        try:
            # FRED dates are YYYY-MM-DD with the first of month
            year, month = int(date_str[:4]), int(date_str[5:7])
            value = float(value_str)
        except (ValueError, IndexError):
            continue
        if not _INDEX_VALID_RANGE[0] <= value <= _INDEX_VALID_RANGE[1]:
            continue
        rows.append(CPIMonth(
            period=f"{year:04d}-{month:02d}",
            cpi_index=round(value, 2),
            source="FRED",
        ))
    return rows


# ---------------------------------------------------------------------------
# dbnomics JSON parser (IMF/IFS India CPI index)
# ---------------------------------------------------------------------------


def parse_dbnomics_cpi(payload: dict[str, Any], *, source_url: str | None = None) -> list[CPIMonth]:
    """Parse a dbnomics ``/series/{provider}/{dataset}/{code}`` JSON payload.

    dbnomics returns parallel ``period`` (``"YYYY-MM"`` for monthly) and
    ``value`` arrays under ``series.docs[0]``. We map each pair to a
    :class:`CPIMonth` and compute ``yoy_pct`` from the index level 12
    months prior (CPI YoY is base-invariant). Missing observations
    (``"NA"`` strings or non-numeric entries) are skipped defensively.
    Returns rows sorted ascending by period.
    """
    rows: list[CPIMonth] = []
    docs = (payload or {}).get("series", {}).get("docs") or []
    if not docs:
        logger.warning("CPI dbnomics payload had no series docs")
        return rows
    doc = docs[0]
    periods = doc.get("period") or []
    values = doc.get("value") or []

    # Build an index-level lookup (period -> value) for YoY computation.
    index_by_period: dict[str, float] = {}
    for period, raw in zip(periods, values):
        if not isinstance(period, str):
            continue
        m = _PERIOD_RE.match(period.strip())
        if not m:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue  # "NA" strings / nulls
        if not _INDEX_VALID_RANGE[0] <= value <= _INDEX_VALID_RANGE[1]:
            continue
        index_by_period[period] = value

    for period in sorted(index_by_period):
        year, month = int(period[:4]), int(period[5:7])
        prior = f"{year - 1:04d}-{month:02d}"
        yoy = None
        prior_val = index_by_period.get(prior)
        if prior_val:
            pct = (index_by_period[period] / prior_val - 1.0) * 100.0
            if _YOY_VALID_RANGE[0] <= pct <= _YOY_VALID_RANGE[1]:
                yoy = round(pct, 2)
        rows.append(CPIMonth(
            period=period,
            cpi_index=round(index_by_period[period], 2),
            yoy_pct=yoy,
            source="dbnomics",
            source_url=source_url,
        ))
    return rows


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from a PDF (lazy import of pdfplumber)."""
    try:
        import pdfplumber  # noqa: WPS433
    except ImportError as exc:
        logger.warning("pdfplumber not installed; cannot parse PDF: %s", exc)
        return ""
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            pages.append(t)
    return "\n".join(pages)


def _html_to_text(html_bytes: bytes) -> str:
    """Strip HTML to visible text via BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup  # noqa: WPS433
    except ImportError as exc:
        logger.warning("beautifulsoup4 not installed; cannot parse HTML: %s", exc)
        return ""
    soup = BeautifulSoup(html_bytes, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    return soup.get_text(" ", strip=True)


# ---------------------------------------------------------------------------
# CPIClient
# ---------------------------------------------------------------------------


class CPIClientError(Exception):
    """Raised when the bundled CPI seed dataset is missing or malformed."""


class CPIClient:
    """Read monthly CPI rows from the bundled seed + optional live fetch.

    Use as a context manager so the underlying HTTP client is closed on
    exit::

        with CPIClient() as client:
            latest = client.fetch_latest()
            apr = client.fetch_month("2025-04")
    """

    def __init__(
        self,
        *,
        seed: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> None:
        if seed is None:
            try:
                seed = self._load_bundled_seed()
            except (FileNotFoundError, ModuleNotFoundError) as exc:
                raise CPIClientError(
                    f"CPI seed dataset not loadable: {exc}",
                ) from exc
        self._meta: dict[str, Any] = seed.get("_meta", {})
        raw_rows = seed.get("collections", [])
        if not isinstance(raw_rows, list):
            raise CPIClientError(
                f"Expected 'collections' to be a list, got {type(raw_rows).__name__}",
            )
        self._by_period: dict[str, CPIMonth] = {}
        for row in raw_rows:
            try:
                rec = CPIMonth(**row)
            except Exception:
                logger.warning("CPI seed row skipped (validation): %r", row, exc_info=True)
                continue
            self._by_period[rec.period] = rec
        self._http = httpx.Client(timeout=timeout)

    @staticmethod
    def _load_bundled_seed() -> dict[str, Any]:
        try:
            text = (
                resources.files(_SEED_PACKAGE)
                .joinpath(_SEED_FILE)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise CPIClientError(
                f"CPI seed dataset {_SEED_PACKAGE}/{_SEED_FILE} not found",
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise CPIClientError(
                f"CPI seed dataset {_SEED_FILE} is not valid JSON: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_month(
        self,
        period: str,
        *,
        source_url: str | None = None,
    ) -> CPIMonth | None:
        _validate_period(period)
        if source_url:
            return self._fetch_from_url(period, source_url)
        return self._by_period.get(period)

    def fetch_latest(self) -> CPIMonth | None:
        if not self._by_period:
            return None
        latest_period = max(self._by_period)
        return self._by_period[latest_period]

    def fetch_backfill(self, start_period: str, end_period: str) -> list[CPIMonth]:
        wanted = set(_iter_periods(start_period, end_period))
        return [
            self._by_period[p]
            for p in sorted(wanted)
            if p in self._by_period
        ]

    def fetch_all_from_dbnomics(self) -> list[CPIMonth]:
        """Fetch the full IMF/IFS India CPI index series from dbnomics.

        Returns every monthly :class:`CPIMonth` (ascending by period) with
        ``yoy_pct`` computed locally. On any HTTP/parse failure returns an
        empty list (defensive — caller decides whether to fall back to seed).
        """
        url = f"{_DBNOMICS_BASE}/series/{_DBNOMICS_CPI_SERIES}?observations=1"
        try:
            resp = self._http.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-cpi/1.0"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("CPI dbnomics fetch failed: %s", exc)
            return []
        return parse_dbnomics_cpi(payload, source_url=url)

    def fetch_from_dbnomics(self, period: str | None = None) -> CPIMonth | None:
        """Fetch one month from dbnomics — the latest available, or ``period``.

        ``period`` is an optional ``YYYY-MM`` string; when omitted the most
        recent month in the series is returned. Returns ``None`` if the fetch
        failed or the requested period is not in the series.
        """
        if period is not None:
            _validate_period(period)
        rows = self.fetch_all_from_dbnomics()
        if not rows:
            return None
        if period is None:
            return rows[-1]  # rows are ascending by period
        for row in rows:
            if row.period == period:
                return row
        logger.warning("CPI dbnomics series did not contain period %s", period)
        return None

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    @property
    def known_periods(self) -> list[str]:
        return sorted(self._by_period)

    def _fetch_from_url(self, period: str, url: str) -> CPIMonth | None:
        try:
            resp = self._http.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-cpi/1.0"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("CPI live-fetch failed for %s: %s", url, exc)
            return None

        body = resp.content
        ct = (resp.headers.get("content-type") or "").lower()
        is_pdf = "pdf" in ct or url.lower().endswith(".pdf")
        is_csv = "csv" in ct or url.lower().endswith(".csv")

        if is_csv:
            rows = parse_fred_csv(body.decode("utf-8", errors="replace"))
            for r in rows:
                if r.period == period:
                    return CPIMonth(
                        period=period,
                        cpi_index=r.cpi_index,
                        yoy_pct=None,
                        source="FRED",
                        source_url=url,
                    )
            logger.warning("CPI FRED CSV did not contain period %s", period)
            return None

        text = _pdf_to_text(body) if is_pdf else _html_to_text(body)
        parsed = parse_mospi_release_text(text)
        if all(v is None for v in parsed.values()):
            return CPIMonth(period=period, source_url=url, source="MoSPI")
        return CPIMonth(period=period, source_url=url, source="MoSPI", **parsed)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> CPIClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def period_to_display(period: str) -> str:
    """Render ``"2025-04"`` as ``"Apr-2025"``."""
    y, m = _validate_period(period)
    return f"{calendar.month_abbr[m]}-{y}"
