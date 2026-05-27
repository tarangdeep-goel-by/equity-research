"""Monthly India IIP (Industrial Production) fetcher: seed + optional live URL.

Source authority
----------------
MoSPI publishes the IIP General index ~6 weeks after the data month (e.g.
April 2025 IIP released 12 June 2025). The native PDF is at
``mospi.gov.in/iip``. FRED mirrors the OECD series at
``INDPROINDMISMEI`` (base 2015=100, monthly back to 1994).

Two ingestion paths
-------------------
1. **Bundled seed JSON** (``data/iip_monthly_seed.json``) — verified
   historical rows back to 2014-01. Default for ``iip fetch`` /
   ``iip backfill``.
2. **Explicit ``source_url``** — caller-supplied URL; PDF / HTML / FRED
   CSV all supported via content-type sniffing.
"""

from __future__ import annotations

import calendar
import io
import json
import logging
import re
from importlib import resources
from typing import Any

import httpx

from flowtracker.iip_models import IIPMonth

logger = logging.getLogger(__name__)

_SEED_PACKAGE = "flowtracker.data"
_SEED_FILE = "iip_monthly_seed.json"

# dbnomics: free, no-auth aggregator. The IMF International Financial
# Statistics (IFS) India Industrial Production (Index) monthly series is
# the freshest free India IIP-general level we found on dbnomics. Note it
# is itself bounded — as of May 2026 it extends only to 2024-10, ~6 months
# behind MoSPI's real cadence (OECD KEI stops 2023-01, IMF PGI manufacturing
# stops 2017; IFS is the best free option). It still beats FRED's
# discontinued mirror (INDPROINDMISMEI ends 2023-01). YoY% is computed
# locally from the 12-months-prior index level (base-invariant).
_DBNOMICS_BASE = "https://api.db.nomics.world/v22"
_DBNOMICS_IIP_SERIES = "IMF/IFS/M.IN.AIP_IX"

# IIP YoY routinely spans wide post-COVID base-effect ranges (April 2021
# printed +134%); widen accordingly. Index level is on the 2015=100 base
# but historical FRED rows can dip below 50 (April 2020 lockdown).
_YOY_VALID_RANGE: tuple[float, float] = (-60.0, 150.0)
_INDEX_VALID_RANGE: tuple[float, float] = (40.0, 250.0)

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _validate_period(period: str) -> tuple[int, int]:
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must match YYYY-MM, got {period!r}")
    year = int(m.group(1))
    month = int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"period month must be 1..12, got {month}")
    if not 1994 <= year <= 2100:
        # FRED's INDPROINDMISMEI starts 1994.
        raise ValueError(f"period year must be 1994..2100, got {year}")
    return year, month


def _iter_periods(start: str, end: str) -> list[str]:
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

_IIP_YOY_PATTERNS = [
    # "IIP General ... growth of 5.4 per cent" — `.{0,120}?` allows year tokens.
    re.compile(
        r"iip[\s-]+general.{0,120}?(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "General Index ... 5.4%"
    re.compile(
        r"general\s+index.{0,80}?(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
        re.IGNORECASE | re.DOTALL,
    ),
    # "Industrial production grew 5.4 per cent" / "fell -57.3 per cent"
    re.compile(
        r"industrial\s+production.{0,60}?(-?\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
        re.IGNORECASE | re.DOTALL,
    ),
]

_IIP_INDEX_PATTERNS = [
    re.compile(
        r"iip[\s-]+general.{0,80}?(\d+\.\d+)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"index\s+(?:stood|stands|is|was).{0,40}?(\d+\.\d+)",
        re.IGNORECASE | re.DOTALL,
    ),
]


def parse_mospi_iip_text(text: str) -> dict[str, float | None]:
    """Defensive regex parser for MoSPI IIP press releases."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    out: dict[str, float | None] = {"iip_index": None, "yoy_pct": None}

    for pat in _IIP_YOY_PATTERNS:
        m = pat.search(flat)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if _YOY_VALID_RANGE[0] <= val <= _YOY_VALID_RANGE[1]:
            out["yoy_pct"] = round(val, 1)
            break

    for pat in _IIP_INDEX_PATTERNS:
        m = pat.search(flat)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if _INDEX_VALID_RANGE[0] <= val <= _INDEX_VALID_RANGE[1]:
            out["iip_index"] = round(val, 1)
            break

    if all(v is None for v in out.values()):
        sample = flat[:240]
        logger.warning("IIP parser extracted zero fields. Source sample: %r", sample)
    return out


def parse_fred_csv(csv_text: str) -> list[IIPMonth]:
    """Parse the FRED CSV for ``INDPROINDMISMEI`` — same shape as the CPI CSV."""
    rows: list[IIPMonth] = []
    text = (csv_text or "").strip()
    if not text:
        return rows

    lines = text.splitlines()
    if not lines:
        return rows
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
        if not _INDEX_VALID_RANGE[0] <= value <= _INDEX_VALID_RANGE[1]:
            continue
        rows.append(IIPMonth(
            period=f"{year:04d}-{month:02d}",
            iip_index=round(value, 1),
            source="FRED",
        ))
    return rows


def parse_dbnomics_iip(payload: dict[str, Any], *, source_url: str | None = None) -> list[IIPMonth]:
    """Parse a dbnomics ``/series/{provider}/{dataset}/{code}`` JSON payload.

    dbnomics returns parallel ``period`` (``"YYYY-MM"`` for monthly) and
    ``value`` arrays under ``series.docs[0]``. Each pair maps to an
    :class:`IIPMonth`; ``yoy_pct`` is computed from the index level 12
    months prior (base-invariant). Missing observations (``"NA"`` strings
    or non-numeric entries) are skipped. Returns rows ascending by period.
    """
    rows: list[IIPMonth] = []
    docs = (payload or {}).get("series", {}).get("docs") or []
    if not docs:
        logger.warning("IIP dbnomics payload had no series docs")
        return rows
    doc = docs[0]
    periods = doc.get("period") or []
    values = doc.get("value") or []

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
                yoy = round(pct, 1)
        rows.append(IIPMonth(
            period=period,
            iip_index=round(index_by_period[period], 1),
            yoy_pct=yoy,
            source="dbnomics",
            source_url=source_url,
        ))
    return rows


def _pdf_to_text(pdf_bytes: bytes) -> str:
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
    try:
        from bs4 import BeautifulSoup  # noqa: WPS433
    except ImportError as exc:
        logger.warning("beautifulsoup4 not installed; cannot parse HTML: %s", exc)
        return ""
    soup = BeautifulSoup(html_bytes, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    return soup.get_text(" ", strip=True)


class IIPClientError(Exception):
    """Raised when the bundled IIP seed dataset is missing or malformed."""


class IIPClient:
    """Read monthly IIP rows from the bundled seed + optional live fetch."""

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
                raise IIPClientError(
                    f"IIP seed dataset not loadable: {exc}",
                ) from exc
        self._meta: dict[str, Any] = seed.get("_meta", {})
        raw_rows = seed.get("collections", [])
        if not isinstance(raw_rows, list):
            raise IIPClientError(
                f"Expected 'collections' to be a list, got {type(raw_rows).__name__}",
            )
        self._by_period: dict[str, IIPMonth] = {}
        for row in raw_rows:
            try:
                rec = IIPMonth(**row)
            except Exception:
                logger.warning("IIP seed row skipped (validation): %r", row, exc_info=True)
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
            raise IIPClientError(
                f"IIP seed dataset {_SEED_PACKAGE}/{_SEED_FILE} not found",
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise IIPClientError(
                f"IIP seed dataset {_SEED_FILE} is not valid JSON: {exc}",
            ) from exc

    def fetch_month(
        self,
        period: str,
        *,
        source_url: str | None = None,
    ) -> IIPMonth | None:
        _validate_period(period)
        if source_url:
            return self._fetch_from_url(period, source_url)
        return self._by_period.get(period)

    def fetch_latest(self) -> IIPMonth | None:
        if not self._by_period:
            return None
        latest_period = max(self._by_period)
        return self._by_period[latest_period]

    def fetch_backfill(self, start_period: str, end_period: str) -> list[IIPMonth]:
        wanted = set(_iter_periods(start_period, end_period))
        return [
            self._by_period[p]
            for p in sorted(wanted)
            if p in self._by_period
        ]

    def fetch_all_from_dbnomics(self) -> list[IIPMonth]:
        """Fetch the full IMF/IFS India IIP index series from dbnomics.

        Returns every monthly :class:`IIPMonth` (ascending by period) with
        ``yoy_pct`` computed locally. On any HTTP/parse failure returns an
        empty list (defensive — caller decides whether to fall back to seed).
        """
        url = f"{_DBNOMICS_BASE}/series/{_DBNOMICS_IIP_SERIES}?observations=1"
        try:
            resp = self._http.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-iip/1.0"},
            )
            resp.raise_for_status()
            payload = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("IIP dbnomics fetch failed: %s", exc)
            return []
        return parse_dbnomics_iip(payload, source_url=url)

    def fetch_from_dbnomics(self, period: str | None = None) -> IIPMonth | None:
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
        logger.warning("IIP dbnomics series did not contain period %s", period)
        return None

    @property
    def meta(self) -> dict[str, Any]:
        return dict(self._meta)

    @property
    def known_periods(self) -> list[str]:
        return sorted(self._by_period)

    def _fetch_from_url(self, period: str, url: str) -> IIPMonth | None:
        try:
            resp = self._http.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-iip/1.0"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("IIP live-fetch failed for %s: %s", url, exc)
            return None

        body = resp.content
        ct = (resp.headers.get("content-type") or "").lower()
        is_pdf = "pdf" in ct or url.lower().endswith(".pdf")
        is_csv = "csv" in ct or url.lower().endswith(".csv")

        if is_csv:
            rows = parse_fred_csv(body.decode("utf-8", errors="replace"))
            for r in rows:
                if r.period == period:
                    return IIPMonth(
                        period=period,
                        iip_index=r.iip_index,
                        yoy_pct=None,
                        source="FRED",
                        source_url=url,
                    )
            logger.warning("IIP FRED CSV did not contain period %s", period)
            return None

        text = _pdf_to_text(body) if is_pdf else _html_to_text(body)
        parsed = parse_mospi_iip_text(text)
        if all(v is None for v in parsed.values()):
            return IIPMonth(period=period, source_url=url, source="MoSPI")
        return IIPMonth(period=period, source_url=url, source="MoSPI", **parsed)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> IIPClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def period_to_display(period: str) -> str:
    y, m = _validate_period(period)
    return f"{calendar.month_abbr[m]}-{y}"
