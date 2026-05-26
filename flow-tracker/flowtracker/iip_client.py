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
