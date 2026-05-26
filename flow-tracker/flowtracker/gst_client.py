"""Monthly GST collections fetcher and defensive parser.

Source authority
----------------
The CBIC monthly press release (mirrored by PIB / GST Council) on the 1st of
every month is the canonical source. The numeric layout is consistent across
months — gross collection, CGST/SGST/IGST/cess, domestic-vs-imports split,
year-on-year growth %.

Live-scrape strategy (post-Playwright)
--------------------------------------
The discovery surface is JS-rendered: ``www.gst.gov.in/newsandupdates/``
loads its press-release list via an SPA bundle, so a plain ``httpx`` GET
returns only the shell. We use the shared
:mod:`flowtracker.js_fetch` Playwright helper to render the listing,
follow the per-month link (e.g. ``/newsandupdates/read/659`` for "Gross
and Net GST revenue collections for the month of Apr, 2026"), and then
``httpx``-download the linked PDF on ``tutorial.gst.gov.in`` (the PDF
host is *not* SPA-gated — it serves bytes to vanilla HTTP).

Two ingestion paths are supported:

1. **Live fetch via** :meth:`GSTClient.fetch_month_live` — Playwright
   discovery + httpx PDF download + tabular parser. Used by
   ``flowtrack gst fetch`` by default; falls back to the seed if either
   step fails (rendered page missing the link, PDF 404, parser yields
   nothing).
2. **Bundled seed JSON** (``data/gst_collections_seed.json``) — verified
   historical rows. Used by ``fetch_latest`` / ``fetch_month`` /
   ``fetch_backfill`` by default; remains the fallback for ``gst fetch``.
3. **Explicit ``source_url``** — if a caller passes ``source_url=...`` to
   :meth:`GSTClient.fetch_month`, the client httpx-downloads the bytes
   and runs the defensive regex parser. This is the escape hatch when
   the analyst hand-supplies a specific URL (e.g. an old PIB page that
   *does* serve full HTML for that PRID).

Parser
------
Two parsers are layered so older prose-style and newer tabular-style
releases are both supported:

* :func:`parse_press_release_text` — defensive regex parser, anchored on
  canonical CBIC prose ("Gross GST revenue collected ... ₹X crore",
  "Y% higher"). Used for legacy press-release HTML.
* :func:`parse_gst_pdf_table` — table-row parser for the new
  ``tutorial.gst.gov.in`` PDF layout where the data is presented as
  rows like ``Total Gross GST Revenue 2,23,265 2,42,702 8.7%`` with
  year-on-year side-by-side columns.

Both parsers are **defensive by design** — any field that fails to match
is set to ``None`` rather than crashing the row (the project rule that
"partial parses must persist, not crash the whole run").
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


# ---------------------------------------------------------------------------
# Tabular parser — new tutorial.gst.gov.in PDF layout
# ---------------------------------------------------------------------------

# Numbers in the new PDF look like ``48,634`` or ``1,15,259`` (Indian comma
# grouping, no currency anchor since columns are pre-labelled "Amount in
# crores"). Anchor the parser on row-leading labels so we capture the right
# year's column (Apr-25 vs Apr-26, side-by-side).
_TABULAR_NUMBER = r"((?:\d[\d,]*)(?:\.\d+)?)"
_TABULAR_PCT = r"(-?\d+(?:\.\d+)?)\s*%"

# Each pattern captures the *most recent year's* value — that's the second
# numeric token on the row, because the layout is "<label> <prior_year>
# <current_year> [pct]". For totals rows that include a "Monthly" + "Yearly"
# duplication, both pairs match the same numbers so picking the first hit
# is correct (April is always month #1 of the FY so monthly == yearly).
_TABULAR_PATTERNS: dict[str, re.Pattern[str]] = {
    "gross_collection_cr": re.compile(
        r"Total\s+Gross\s+GST\s+Revenue\s+" + _TABULAR_NUMBER + r"\s+" + _TABULAR_NUMBER,
        re.IGNORECASE,
    ),
    "domestic_cr": re.compile(
        r"Gross\s+Domestic\s+Revenue\s+" + _TABULAR_NUMBER + r"\s+" + _TABULAR_NUMBER,
        re.IGNORECASE,
    ),
    "imports_cr": re.compile(
        r"Gross\s+Import\s+Revenue\s+" + _TABULAR_NUMBER + r"\s+" + _TABULAR_NUMBER,
        re.IGNORECASE,
    ),
}

# CGST / SGST / IGST appear in multiple sub-sections (A.1 Domestic, A.3
# Gross, B.1 Refunds, C.1 Net). We want the A.3 Gross totals, which are
# the rows that appear *after* "A.3. Gross GST Revenue" and before "B.1.".
_TABULAR_GROSS_SECTION_RE = re.compile(
    r"A\.3\.\s*Gross\s+GST\s+Revenue.*?(?=B\.1\.)",
    re.IGNORECASE | re.DOTALL,
)
_TABULAR_GROSS_CGST_RE = re.compile(
    r"\bCGST\s+" + _TABULAR_NUMBER + r"\s+" + _TABULAR_NUMBER, re.IGNORECASE,
)
_TABULAR_GROSS_SGST_RE = re.compile(
    r"\bSGST\s+" + _TABULAR_NUMBER + r"\s+" + _TABULAR_NUMBER, re.IGNORECASE,
)
_TABULAR_GROSS_IGST_RE = re.compile(
    r"\bIGST\s+" + _TABULAR_NUMBER + r"\s+" + _TABULAR_NUMBER, re.IGNORECASE,
)

# YoY growth: pick the percentage on the "Total Gross GST Revenue" row.
_TABULAR_GROWTH_RE = re.compile(
    r"Total\s+Gross\s+GST\s+Revenue\s+\S+\s+\S+\s+" + _TABULAR_PCT,
    re.IGNORECASE,
)


def parse_gst_pdf_table(text: str) -> dict[str, float | None]:
    """Parse the new ``tutorial.gst.gov.in`` PDF tabular format.

    The PDF layout (verified Apr 2026 onwards) is a structured table where
    each row reads ``<label> <prior_year_value> <current_year_value> [%]``,
    e.g. ``Total Gross GST Revenue 2,23,265 2,42,702 8.7%``. This parser
    captures the current-year (right-hand) column for each canonical row.

    Returns a dict keyed by the ``GSTCollectionMonth`` numeric fields —
    same shape as :func:`parse_press_release_text` so the two are
    interchangeable downstream. Any field that cannot be matched is set
    to ``None``.
    """
    flat = re.sub(r"\s+", " ", text or "").strip()
    out: dict[str, float | None] = {
        "gross_collection_cr": None,
        "cgst_cr": None,
        "sgst_cr": None,
        "igst_cr": None,
        "cess_cr": None,  # not present in this PDF format
        "domestic_cr": None,
        "imports_cr": None,
        "growth_yoy_pct": None,
    }

    # Aggregate rows (Total Gross / Domestic / Imports)
    for field, pat in _TABULAR_PATTERNS.items():
        m = pat.search(flat)
        if m:
            # Group 2 is the current year (right-hand column).
            out[field] = _to_float(m.group(2))

    # Per-tax rows — restrict to the A.3 Gross GST Revenue subsection to
    # disambiguate from A.1 Domestic / B Refunds / C Net.
    section_match = _TABULAR_GROSS_SECTION_RE.search(flat)
    section = section_match.group(0) if section_match else flat
    for field, pat in (
        ("cgst_cr", _TABULAR_GROSS_CGST_RE),
        ("sgst_cr", _TABULAR_GROSS_SGST_RE),
        ("igst_cr", _TABULAR_GROSS_IGST_RE),
    ):
        m = pat.search(section)
        if m:
            out[field] = _to_float(m.group(2))

    # YoY growth from Total Gross row
    growth_m = _TABULAR_GROWTH_RE.search(flat)
    if growth_m:
        out["growth_yoy_pct"] = _to_float(growth_m.group(1))

    if all(v is None for v in out.values()):
        sample = flat[:240]
        logger.warning(
            "GST tabular parser extracted zero fields. Source sample: %r", sample,
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
    # Live fetch via Playwright discovery + httpx PDF download
    # ------------------------------------------------------------------

    def fetch_month_live(self, period: str) -> GSTCollectionMonth | None:
        """Fetch a single month's GST row by JS-rendering gst.gov.in.

        Three steps:

        1. JS-render ``https://www.gst.gov.in/newsandupdates/`` and find the
           ``/newsandupdates/read/<id>`` link whose title mentions
           ``<Mon, YYYY>`` (e.g. ``Apr, 2026``).
        2. JS-render that detail page and extract the
           ``tutorial.gst.gov.in/.../*.pdf`` URL.
        3. ``httpx``-download the PDF (the PDF host is *not* SPA-gated)
           and run :func:`parse_gst_pdf_table` over the extracted text.

        Returns ``None`` if any step fails or if the parser cannot extract
        a single field — callers should fall back to the seed.

        Raises
        ------
        ValueError
            If ``period`` is not a valid YYYY-MM.
        """
        _validate_period(period)

        # Lazy import — keep ``js_fetch`` (and therefore Playwright) out of
        # the seed-only happy path so seed lookups don't import Chromium.
        try:
            from flowtracker.js_fetch import JSFetchError, JSFetchSession
        except ImportError as exc:  # pragma: no cover — js_fetch is a sibling
            logger.warning("GST live fetch unavailable: %s", exc)
            return None

        listing_url = "https://www.gst.gov.in/newsandupdates/"
        target_label = period_to_release_label_short(period)  # e.g. "Apr, 2026"

        try:
            with JSFetchSession() as session:
                listing_html = session.fetch(
                    listing_url,
                    wait_for_selector="a[href*='/newsandupdates/read/']",
                    timeout_ms=30_000,
                )
                detail_path = _find_collection_link(listing_html, target_label)
                if detail_path is None:
                    logger.warning(
                        "GST live: no collection link for %s on %s",
                        target_label, listing_url,
                    )
                    return None
                detail_url = _normalise_gst_url(detail_path)
                detail_html = session.fetch(
                    detail_url,
                    wait_for_network_idle=True,
                    timeout_ms=30_000,
                )
        except JSFetchError as exc:
            logger.warning("GST live JS fetch failed: %s", exc)
            return None

        pdf_url = _extract_pdf_url(detail_html)
        if pdf_url is None:
            logger.warning(
                "GST live: detail page for %s missing PDF link", target_label,
            )
            return None

        try:
            resp = self._http.get(
                pdf_url,
                follow_redirects=True,
                headers={"User-Agent": "flowtracker-gst/1.0"},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("GST live PDF download failed (%s): %s", pdf_url, exc)
            return None

        text = _pdf_to_text(resp.content)
        parsed = parse_gst_pdf_table(text)
        if all(v is None for v in parsed.values()):
            # Tabular parser failed — try the prose parser as a last resort
            # in case the PDF reverts to the older CBIC layout.
            parsed = parse_press_release_text(text)
        if all(v is None for v in parsed.values()):
            logger.warning(
                "GST live: parser extracted zero fields for %s (PDF %s)",
                period, pdf_url,
            )
            return None

        return GSTCollectionMonth(period=period, source_url=pdf_url, **parsed)

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


def period_to_release_label_short(period: str) -> str:
    """Render ``"2026-04"`` as ``"Apr, 2026"`` — matches gst.gov.in titles.

    Used by :meth:`GSTClient.fetch_month_live` to find the matching link on
    the news-listing page. gst.gov.in's titles are formatted as
    ``"Gross and Net GST revenue collections for the month of Apr, 2026"``.
    """
    y, m = _validate_period(period)
    return f"{calendar.month_abbr[m]}, {y}"


# ---------------------------------------------------------------------------
# Live-fetch HTML helpers (used by fetch_month_live)
# ---------------------------------------------------------------------------


_NEWS_LINK_RE = re.compile(
    r"""<a[^>]+href=["'](?P<href>(?://www\.gst\.gov\.in)?/newsandupdates/read/\d+)["']"""
    r"[^>]*>(?P<text>[^<]+)</a>",
    re.IGNORECASE,
)


def _find_collection_link(html: str, target_label: str) -> str | None:
    """Find the ``/newsandupdates/read/<id>`` href whose anchor text mentions
    ``target_label`` (e.g. ``"Apr, 2026"``) and contains the word "collection".

    Returns the relative or absolute href, or ``None`` if no match. The text
    must contain both ``collection`` (to skip non-revenue advisories) AND the
    target month label.
    """
    label_lc = target_label.lower()
    for m in _NEWS_LINK_RE.finditer(html or ""):
        text = m.group("text").strip()
        text_lc = text.lower()
        if "collection" in text_lc and label_lc in text_lc:
            return m.group("href")
    return None


_PDF_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+\.pdf', re.IGNORECASE,
)


def _extract_pdf_url(html: str) -> str | None:
    """Return the first ``.pdf`` URL found in ``html``, or ``None``."""
    m = _PDF_URL_RE.search(html or "")
    return m.group(0) if m else None


def _normalise_gst_url(href: str) -> str:
    """Make a gst.gov.in href absolute (handles ``//www.gst.gov.in/...``)."""
    href = (href or "").strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://www.gst.gov.in" + href
    return href


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
