"""Monthly India PMI (S&P Global) fetcher: seed + optional live URL parser.

Source authority
----------------
S&P Global publishes the India PMI Manufacturing release on the 1st-2nd
of each month and the Services release on the 3rd-5th. There is **no
clean free API** — values must be extracted from the press-release PDFs
at ``https://www.pmi.spglobal.com/Public/Home/PressRelease``.

Two ingestion paths
-------------------
1. **Bundled seed JSON** (``data/pmi_monthly_seed.json``) — verified
   historical rows back to 2014-01. Default for ``pmi fetch`` /
   ``pmi backfill``.
2. **Explicit ``source_url``** — caller supplies one of the S&P Global
   press-release URLs (Manufacturing OR Services); the parser extracts
   the headline number and the row is upserted as a partial (one of
   the two PMI fields will be NULL).
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

from flowtracker.pmi_models import PMIMonth

logger = logging.getLogger(__name__)

_SEED_PACKAGE = "flowtracker.data"
_SEED_FILE = "pmi_monthly_seed.json"

# PMI scale: 0..100, with 50 = unchanged. April 2020 lockdown printed 5.4
# Services and 27.4 Manufacturing (lowest ever); 90+ is theoretical only.
_PMI_VALID_RANGE: tuple[float, float] = (0.0, 80.0)

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _validate_period(period: str) -> tuple[int, int]:
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must match YYYY-MM, got {period!r}")
    year = int(m.group(1))
    month = int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"period month must be 1..12, got {month}")
    if not 2005 <= year <= 2100:
        # S&P Global India PMI series begins in 2005.
        raise ValueError(f"period year must be 2005..2100, got {year}")
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
# Press-release defensive regex parser
# ---------------------------------------------------------------------------

# The headline is always preceded by the canonical phrase "headline India
# Services PMI" / "headline India Manufacturing PMI" / "S&P Global India
# Services PMI" with the number 1-2 words later (e.g. "registered 58.5"
# or "stood at 58.5").

_SERVICES_PATTERNS = [
    re.compile(
        r"(?:headline\s+)?(?:s&p\s+global\s+)?india\s+services\s+pmi"
        r"[^0-9]{0,80}?(\d+(?:\.\d+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"services\s+pmi\s+(?:business\s+activity\s+index\s+)?"
        r"[^0-9]{0,40}?(\d+(?:\.\d+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
]

_MANUFACTURING_PATTERNS = [
    re.compile(
        r"(?:headline\s+)?(?:s&p\s+global\s+)?india\s+manufacturing\s+pmi"
        r"[^0-9]{0,80}?(\d+(?:\.\d+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"manufacturing\s+pmi\s*[^0-9]{0,40}?(\d+(?:\.\d+)?)",
        re.IGNORECASE | re.DOTALL,
    ),
]


def parse_pmi_release_text(text: str) -> dict[str, float | None]:
    """Extract Services + Manufacturing PMI from an S&P Global press release."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    out: dict[str, float | None] = {"services_pmi": None, "manufacturing_pmi": None}

    for pat in _SERVICES_PATTERNS:
        m = pat.search(flat)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if _PMI_VALID_RANGE[0] <= val <= _PMI_VALID_RANGE[1]:
            out["services_pmi"] = round(val, 1)
            break

    for pat in _MANUFACTURING_PATTERNS:
        m = pat.search(flat)
        if not m:
            continue
        try:
            val = float(m.group(1))
        except (TypeError, ValueError):
            continue
        if _PMI_VALID_RANGE[0] <= val <= _PMI_VALID_RANGE[1]:
            out["manufacturing_pmi"] = round(val, 1)
            break

    if all(v is None for v in out.values()):
        sample = flat[:240]
        logger.warning("PMI parser extracted zero fields. Source sample: %r", sample)
    return out


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


class PMIClientError(Exception):
    """Raised when the bundled PMI seed dataset is missing or malformed."""


class PMIClient:
    """Read monthly PMI rows from the bundled seed + optional live fetch."""

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
                raise PMIClientError(
                    f"PMI seed dataset not loadable: {exc}",
                ) from exc
        self._meta: dict[str, Any] = seed.get("_meta", {})
        raw_rows = seed.get("collections", [])
        if not isinstance(raw_rows, list):
            raise PMIClientError(
                f"Expected 'collections' to be a list, got {type(raw_rows).__name__}",
            )
        self._by_period: dict[str, PMIMonth] = {}
        for row in raw_rows:
            try:
                rec = PMIMonth(**row)
            except Exception:
                logger.warning("PMI seed row skipped (validation): %r", row, exc_info=True)
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
            raise PMIClientError(
                f"PMI seed dataset {_SEED_PACKAGE}/{_SEED_FILE} not found",
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise PMIClientError(
                f"PMI seed dataset {_SEED_FILE} is not valid JSON: {exc}",
            ) from exc

    def fetch_month(
        self,
        period: str,
        *,
        source_url: str | None = None,
    ) -> PMIMonth | None:
        _validate_period(period)
        if source_url:
            return self._fetch_from_url(period, source_url)
        return self._by_period.get(period)

    def fetch_latest(self) -> PMIMonth | None:
        if not self._by_period:
            return None
        latest_period = max(self._by_period)
        return self._by_period[latest_period]

    def fetch_backfill(self, start_period: str, end_period: str) -> list[PMIMonth]:
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

    def _fetch_from_url(self, period: str, url: str) -> PMIMonth | None:
        try:
            resp = self._http.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-pmi/1.0"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("PMI live-fetch failed for %s: %s", url, exc)
            return None

        body = resp.content
        ct = (resp.headers.get("content-type") or "").lower()
        is_pdf = "pdf" in ct or url.lower().endswith(".pdf")
        text = _pdf_to_text(body) if is_pdf else _html_to_text(body)
        parsed = parse_pmi_release_text(text)
        if all(v is None for v in parsed.values()):
            return PMIMonth(period=period, source_url=url, source="S&P Global")
        return PMIMonth(period=period, source_url=url, source="S&P Global", **parsed)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PMIClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def period_to_display(period: str) -> str:
    y, m = _validate_period(period)
    return f"{calendar.month_abbr[m]}-{y}"
