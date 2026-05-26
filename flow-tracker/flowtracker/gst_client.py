"""Monthly GST collections fetcher and defensive parser.

Source authority
----------------
The CBIC monthly press release (mirrored by PIB / GST Council) on the 1st of
every month is the canonical source. The numeric layout is consistent across
months — gross collection, CGST/SGST/IGST/cess, domestic-vs-imports split,
year-on-year growth %.

Live-scrape constraints
-----------------------
PIB's ``PressReleseDetailm.aspx`` and the GST Council's ``press-release``
listing both render via client-side JavaScript — a raw HTTP fetch returns
only the SPA shell. CBIC's ``cbic-gst.gov.in`` and GST Council PDF directory
do not expose a predictable monthly URL pattern (probing 2024-04..2025-05
candidates returns 404 across all conventional naming schemes). The two
practical ingestion paths are therefore:

1. **Bundled seed JSON** (``data/gst_collections_seed.json``) — verified
   historical rows cross-referenced from the official press releases. This
   is what ``fetch_latest`` / ``fetch_month`` / ``fetch_backfill`` consume by
   default. Analysts extend the seed by appending new rows each month after
   CBIC publishes.
2. **Live URL with explicit source_url** — if the caller passes a
   ``source_url`` to ``fetch_month``, the client downloads the bytes and
   runs the defensive regex parser over the text content (PDF via
   pdfplumber, HTML via BeautifulSoup). This is the escape hatch when the
   seed lags or an analyst is processing a freshly-published release.

The parser itself is **defensive by design**: it pattern-matches canonical
phrases ("Gross GST revenue collected", "₹X crore", "Y% higher") rather
than relying on HTML structure or table position. Any field that fails to
match is set to ``None`` rather than crashing the row — the plan's
constraint that "partial parses must persist, not crash the whole run".
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

from flowtracker.gst_models import GSTCollectionMonth

logger = logging.getLogger(__name__)

_SEED_PACKAGE = "flowtracker.data"
_SEED_FILE = "gst_collections_seed.json"

# Month names used to convert e.g. "April 2025" → "2025-04" in URLs / source
# text. Both abbreviations and full names appear in CBIC releases.
_MONTH_NAMES: dict[str, int] = {
    name.lower(): idx
    for idx, name in enumerate(calendar.month_name)
    if name
}
_MONTH_ABBRS: dict[str, int] = {
    abbr.lower(): idx
    for idx, abbr in enumerate(calendar.month_abbr)
    if abbr
}


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

_PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _validate_period(period: str) -> tuple[int, int]:
    """Validate a ``YYYY-MM`` period string. Returns ``(year, month)``.

    Raises ValueError on malformed input. We are strict here because the
    period is the primary key downstream — a typoed period would silently
    create the wrong row.
    """
    m = _PERIOD_RE.match(period.strip())
    if not m:
        raise ValueError(f"period must match YYYY-MM, got {period!r}")
    year = int(m.group(1))
    month = int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"period month must be 1..12, got {month}")
    if not 2017 <= year <= 2100:
        # GST was introduced in July 2017; below that there is no data.
        raise ValueError(f"period year must be 2017..2100, got {year}")
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
# Defensive regex parser
# ---------------------------------------------------------------------------

# Numbers in CBIC releases are written with Indian comma grouping —
# "₹2,10,267 crore" → 210267. To avoid matching the year in lead-in text
# ("collected in April 2025 is ₹2,10,267 crore") we REQUIRE either the
# ``₹`` prefix or the explicit ``crore``/``cr`` suffix. The pattern is then
# OR'd into the per-field regex below; ``_NUMBER_GROUP`` is the capture
# group every regex shares.
#
# Number forms we accept:
#   ₹2,10,267 crore   ← ₹ prefix + crore suffix (common)
#   ₹2,10,267         ← ₹ prefix only
#   2,10,267 crore    ← crore suffix only
#   2,10,267 cr       ← short suffix
#
# We do NOT accept a bare ``2,10,267`` because that would also match the
# four-digit year ``2025`` in lead-in text. The currency anchor is what
# disambiguates revenue from year.
_NUMBER_GROUP = r"([\d,]+(?:\.\d+)?)"
_NUMBER_WITH_ANCHOR = (
    # Either "₹ <num> [crore]?" or "<num> crore" — anchor MUST appear.
    r"(?:"
    r"₹\s*" + _NUMBER_GROUP + r"\s*(?:crore|cr\b)?"
    r"|"
    + _NUMBER_GROUP + r"\s*(?:crore|cr\b)"
    r")"
)


def _extract_number(m: re.Match[str]) -> str | None:
    """Return whichever of the two number groups matched (₹-prefix or crore-suffix)."""
    # _NUMBER_WITH_ANCHOR has two capture groups: the ₹-form takes group 1
    # of the alternation (overall group index = 1) and the crore-form takes
    # group 2. The OR makes exactly one of them populated.
    return m.group(1) or m.group(2)


# Per-field regexes: each is `<field anchor phrase> ... <number-with-anchor>`.
# The `.{0,80}?` non-greedy gap lets the number be a few words after the
# field keyword (e.g. "CGST is ₹48,634 crore") without overflowing into the
# next field.
_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "gross_collection_cr": [
        # "Gross GST revenue collected in <Month> <Year> is ₹2,10,267 crore"
        re.compile(
            r"gross\s+GST\s+(?:revenue|collection)s?\b.{0,80}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
        # Fallback: "Gross collection ... ₹X crore"
        re.compile(
            r"gross\s+collection\b.{0,40}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "cgst_cr": [
        re.compile(
            r"\bCGST\b.{0,40}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "sgst_cr": [
        re.compile(
            r"\bSGST\b.{0,40}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "igst_cr": [
        re.compile(
            r"\bIGST\b.{0,40}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "cess_cr": [
        # Matches "Cess ₹X crore" and "compensation cess of ₹X crore".
        re.compile(
            r"\bcess\b.{0,40}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "domestic_cr": [
        # Strict: "Revenue from domestic ... ₹X cr" or "from domestic ... ₹X cr".
        # Loose form "domestic ... ₹X cr" is intentionally excluded — the word
        # "domestic" appears in unrelated boilerplate (e.g. "domestic CGST").
        re.compile(
            r"(?:revenue\s+from|from)\s+domestic\b.{0,60}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "imports_cr": [
        # Strict: "Revenue from imports ... ₹X cr" or "from imports ... ₹X cr".
        # The word "import" also appears inside the IGST parenthetical
        # ("including ₹47,069 crore collected on import of goods") which we
        # must NOT match — that's a sub-component, not the imports headline.
        # Anchoring on "revenue from" / "from imports" eliminates the false
        # match because the parenthetical reads "on import of goods".
        re.compile(
            r"(?:revenue\s+from|from)\s+imports?\b.{0,60}?" + _NUMBER_WITH_ANCHOR,
            re.IGNORECASE | re.DOTALL,
        ),
    ],
    "growth_yoy_pct": [
        # "12.6% higher than" / "growth of 12.6%" / "Y-o-Y growth of 12.6%"
        re.compile(
            r"(\d+(?:\.\d+)?)\s*%\s*(?:higher|growth|increase|rise)\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:growth|increase|rise|y-?o-?y)\s+of\s+(\d+(?:\.\d+)?)\s*%",
            re.IGNORECASE,
        ),
    ],
}

# Field-name → group-extraction strategy. Numeric currency fields use the
# OR'd _NUMBER_WITH_ANCHOR (two capture groups, one populated); the YoY
# field uses a single capture group.
_GROUP_EXTRACTORS: dict[str, "callable[[re.Match[str]], str | None]"] = {
    "gross_collection_cr": _extract_number,
    "cgst_cr": _extract_number,
    "sgst_cr": _extract_number,
    "igst_cr": _extract_number,
    "cess_cr": _extract_number,
    "domestic_cr": _extract_number,
    "imports_cr": _extract_number,
    "growth_yoy_pct": lambda m: m.group(1),
}


def _to_float(raw: str) -> float | None:
    """Strip commas / whitespace / ₹ from a captured number, return float or None."""
    cleaned = raw.replace(",", "").replace("₹", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_press_release_text(text: str) -> dict[str, float | None]:
    """Run the defensive regex parser over a press-release text body.

    Returns a dict with keys matching ``GSTCollectionMonth`` numeric fields.
    Any field that cannot be matched maps to ``None`` — the caller decides
    whether to persist a partial row (yes, per the project rule) or warn.

    Whitespace and line breaks are normalized to single spaces before
    pattern matching so PDF column-wrap and HTML formatting don't defeat
    the regexes.
    """
    flat = re.sub(r"\s+", " ", text or "").strip()
    out: dict[str, float | None] = {}
    for field, patterns in _PATTERNS.items():
        match_val: float | None = None
        extractor = _GROUP_EXTRACTORS[field]
        for pat in patterns:
            m = pat.search(flat)
            if m:
                raw = extractor(m)
                if raw is not None:
                    match_val = _to_float(raw)
                    if match_val is not None:
                        break
        out[field] = match_val
    if all(v is None for v in out.values()):
        # Surface a sample of the text so the analyst can see what we got.
        sample = flat[:240]
        logger.warning(
            "GST parser extracted zero fields. Source sample: %r", sample,
        )
    return out


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract concatenated text from a PDF using pdfplumber.

    Imported lazily so a missing pdfplumber install only fails the live-fetch
    path, not seed-mode (which is the common case).
    """
    try:
        import pdfplumber  # noqa: WPS433 (allow runtime import)
    except ImportError as exc:  # pragma: no cover — pdfplumber is a hard dep
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
    except ImportError as exc:  # pragma: no cover — bs4 is a hard dep
        logger.warning("beautifulsoup4 not installed; cannot parse HTML: %s", exc)
        return ""
    soup = BeautifulSoup(html_bytes, "html.parser")
    for s in soup(["script", "style", "noscript"]):
        s.decompose()
    return soup.get_text(" ", strip=True)


# ---------------------------------------------------------------------------
# GSTClient
# ---------------------------------------------------------------------------


class GSTClientError(Exception):
    """Raised when the bundled GST seed dataset is missing or malformed."""


class GSTClient:
    """Read monthly GST collection rows from the bundled seed + optional live fetch.

    Use as a context manager so the underlying HTTP client (used only when a
    caller passes an explicit ``source_url``) is closed on exit::

        with GSTClient() as client:
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
                raise GSTClientError(
                    f"GST seed dataset not loadable: {exc}",
                ) from exc
        self._meta: dict[str, Any] = seed.get("_meta", {})
        raw_rows = seed.get("collections", [])
        if not isinstance(raw_rows, list):
            raise GSTClientError(
                f"Expected 'collections' to be a list, got {type(raw_rows).__name__}",
            )
        # Validate every row up front so a malformed seed fails at startup,
        # not mid-backfill.
        self._by_period: dict[str, GSTCollectionMonth] = {}
        for row in raw_rows:
            try:
                rec = GSTCollectionMonth(**row)
            except Exception:  # pydantic validation
                logger.warning("GST seed row skipped (validation): %r", row, exc_info=True)
                continue
            self._by_period[rec.period] = rec
        self._http = httpx.Client(timeout=timeout)

    # ------------------------------------------------------------------
    # Seed loading
    # ------------------------------------------------------------------

    @staticmethod
    def _load_bundled_seed() -> dict[str, Any]:
        """Load the JSON fixture shipped inside ``flowtracker.data``."""
        try:
            text = (
                resources.files(_SEED_PACKAGE)
                .joinpath(_SEED_FILE)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise GSTClientError(
                f"GST seed dataset {_SEED_PACKAGE}/{_SEED_FILE} not found",
            ) from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise GSTClientError(
                f"GST seed dataset {_SEED_FILE} is not valid JSON: {exc}",
            ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_month(
        self,
        period: str,
        *,
        source_url: str | None = None,
    ) -> GSTCollectionMonth | None:
        """Return a single month's GST collection row.

        Resolution order:

        1. If ``source_url`` is supplied, download + parse it (PDF or HTML).
        2. Otherwise look up the bundled seed for ``period``.

        Returns ``None`` if neither path yields data. A *partial* parse
        (some fields ``None``) is still returned — the project rule is
        "persist partial rather than crash".
        """
        _validate_period(period)

        if source_url:
            return self._fetch_from_url(period, source_url)

        return self._by_period.get(period)

    def fetch_latest(self) -> GSTCollectionMonth | None:
        """Return the row with the most recent ``period`` in the seed.

        Useful for ``flowtrack gst latest`` and for cron jobs that want
        "whatever is freshest, no questions asked".
        """
        if not self._by_period:
            return None
        latest_period = max(self._by_period)
        return self._by_period[latest_period]

    def fetch_backfill(
        self,
        start_period: str,
        end_period: str,
    ) -> list[GSTCollectionMonth]:
        """Return every seed row whose ``period`` falls in ``[start, end]``.

        Periods missing from the seed are silently skipped — bulk backfill is
        a best-effort operation. The caller (CLI) reports the
        resolved-vs-requested count so the user can see gaps.
        """
        wanted = set(_iter_periods(start_period, end_period))
        rows = [
            self._by_period[p]
            for p in sorted(wanted)
            if p in self._by_period
        ]
        return rows

    @property
    def meta(self) -> dict[str, Any]:
        """Seed-dataset metadata (source authority, last_updated, etc.)."""
        return dict(self._meta)

    @property
    def known_periods(self) -> list[str]:
        """All periods present in the seed, sorted ascending."""
        return sorted(self._by_period)

    # ------------------------------------------------------------------
    # Live fetch (escape-hatch path)
    # ------------------------------------------------------------------

    def _fetch_from_url(
        self,
        period: str,
        url: str,
    ) -> GSTCollectionMonth | None:
        """Download a PDF or HTML release and run the defensive parser."""
        try:
            resp = self._http.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-gst/1.0"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("GST live-fetch failed for %s: %s", url, exc)
            return None

        body = resp.content
        ct = (resp.headers.get("content-type") or "").lower()
        if "pdf" in ct or url.lower().endswith(".pdf"):
            text = _pdf_to_text(body)
        else:
            text = _html_to_text(body)

        parsed = parse_press_release_text(text)
        if all(v is None for v in parsed.values()):
            # Already warned inside parse_press_release_text; persist a row
            # with everything-None so the analyst can see that we attempted
            # this period and failed.
            return GSTCollectionMonth(period=period, source_url=url)

        return GSTCollectionMonth(period=period, source_url=url, **parsed)

    # ------------------------------------------------------------------
    # Context manager plumbing
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GSTClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Helpers reused by tests and CLI
# ---------------------------------------------------------------------------


def period_to_display(period: str) -> str:
    """Render ``"2025-04"`` as ``"Apr-2025"`` for table headers."""
    y, m = _validate_period(period)
    return f"{calendar.month_abbr[m]}-{y}"


def period_to_release_label(period: str) -> str:
    """Render ``"2025-04"`` as ``"April 2025"`` — matches CBIC press-release language."""
    y, m = _validate_period(period)
    return f"{calendar.month_name[m]} {y}"


def previous_period(period: str) -> str:
    """Return the period immediately before ``period`` (YoY ÷12, MoM = -1)."""
    y, m = _validate_period(period)
    m -= 1
    if m < 1:
        m = 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def same_period_prior_year(period: str) -> str:
    """Return the period exactly 12 months earlier — used for YoY computations."""
    y, m = _validate_period(period)
    return f"{y - 1:04d}-{m:02d}"


def is_period_in_future(period: str, today: date | None = None) -> bool:
    """True if the period is later than the current month (no collection yet)."""
    y, m = _validate_period(period)
    today = today or date.today()
    return (y, m) > (today.year, today.month)
