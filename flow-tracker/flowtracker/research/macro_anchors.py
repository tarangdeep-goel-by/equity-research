"""Download + extract canonical India macro anchor documents.

Parallels ar_downloader + annual_report_extractor for India-wide macro docs
(Economic Survey, Union Budget, RBI publications, IRDAI Annual Report, IMF Article IV).

Unlike per-stock AR/concall/deck, anchors are India-wide and live at:
    ~/vault/macro/raw/<doc_type>_<period>.pdf            # downloaded PDF
    ~/vault/macro/extracted/<doc_type>_<period>/         # Docling cache dir
        _docling.md
        _heading_index.json
    ~/vault/macro/meta/catalog.json                      # freshness catalog

Usage:
    ensure_macro_anchors()              # download missing/stale, extract, update catalog
    get_anchor_content("economic_survey")                # TOC (heading list)
    get_anchor_content("economic_survey", section="...") # section text slice
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from flowtracker.research.doc_extractor import extract_to_markdown

logger = logging.getLogger(__name__)

_VAULT_MACRO = Path.home() / "vault" / "macro"
_RAW_DIR = _VAULT_MACRO / "raw"
_EXTRACTED_DIR = _VAULT_MACRO / "extracted"
_META_DIR = _VAULT_MACRO / "meta"
_CATALOG_PATH = _META_DIR / "catalog.json"

# Browser UA needed — indiabudget.gov.in and imf.org block default clients.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*",
}


@dataclass
class AnchorSpec:
    doc_type: str
    title: str
    url: str | None = None               # direct stable URL (Class A)
    scraper: str | None = None           # landing-page scraper name (Class B)
    period_hint: str = "current"
    min_bytes: int = 100_000             # sanity floor


# Class A — stable overwrite-in-place URLs. Hardcoded.
# Class B — hash-suffixed URLs requiring landing-page scrape. scraper name refers to
#           a function in this module (not yet implemented for all; see _scrape_* below).
_ANCHORS: list[AnchorSpec] = [
    AnchorSpec(
        doc_type="economic_survey",
        title="Economic Survey of India",
        url="https://www.indiabudget.gov.in/economicsurvey/doc/echapter.pdf",
        period_hint="latest_pre_budget",
    ),
    AnchorSpec(
        doc_type="budget_speech",
        title="Union Budget Speech",
        url="https://www.indiabudget.gov.in/doc/budget_speech.pdf",
        period_hint="latest_feb",
    ),
    AnchorSpec(
        doc_type="budget_at_a_glance",
        title="Union Budget at a Glance",
        url="https://www.indiabudget.gov.in/doc/Budget_at_Glance/budget_at_a_glance.pdf",
        period_hint="latest_feb",
    ),
    AnchorSpec(
        doc_type="rbi_mpr",
        title="RBI Monetary Policy Report",
        scraper="_scrape_rbi_mpr",
        period_hint="latest_biannual",
    ),
    AnchorSpec(
        doc_type="rbi_ar_assessment",
        title="RBI Annual Report — Ch 1: Assessment & Outlook",
        scraper="_scrape_rbi_ar_ch1_assessment",
        period_hint="latest_annual",
    ),
    AnchorSpec(
        doc_type="rbi_ar_economic",
        title="RBI Annual Report — Ch 2: Economic Review",
        scraper="_scrape_rbi_ar_ch2_economic",
        period_hint="latest_annual",
    ),
    AnchorSpec(
        doc_type="rbi_ar_monetary",
        title="RBI Annual Report — Ch 3: Monetary Policy Operations",
        scraper="_scrape_rbi_ar_ch3_monetary",
        period_hint="latest_annual",
    ),
    AnchorSpec(
        doc_type="imf_article_iv",
        title="IMF Article IV India Country Report",
        scraper="_scrape_imf_article_iv",
        period_hint="latest_annual",
    ),
    # IRDAI Annual Report — insurance sector regulator's annual review.
    # Critical anchor for life/general insurance evals (HDFCLIFE, POLICYBZR,
    # SBILIFE, ICICIPRULI, etc.). Landing page lists the latest FY PDF with a
    # hash-suffixed URL; scraper resolves to current.
    AnchorSpec(
        doc_type="irdai_annual_report",
        title="IRDAI Annual Report",
        scraper="_scrape_irdai_annual_report",
        period_hint="latest_annual",
    ),
    # RBI Monetary Policy Committee Statement — bi-monthly post-meeting press
    # release with GDP/inflation projections + stance rationale. Distinct from
    # the half-yearly Monetary Policy Report (which is the deeper analytical
    # document). MPC statement is the canonical source for "what RBI just
    # said" — banks/NBFCs eval need this for forward GDP/inflation calls.
    AnchorSpec(
        doc_type="rbi_mpc_statement",
        title="RBI Monetary Policy Committee Statement",
        scraper="_scrape_rbi_mpc_statement",
        period_hint="latest_bimonthly",
    ),
]


def _load_catalog() -> dict[str, Any]:
    if not _CATALOG_PATH.exists():
        return {"anchors": {}}
    try:
        return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("catalog.json corrupt, resetting")
        return {"anchors": {}}


def _save_catalog(cat: dict) -> None:
    _META_DIR.mkdir(parents=True, exist_ok=True)
    _CATALOG_PATH.write_text(json.dumps(cat, indent=2), encoding="utf-8")


def _download_pdf(url: str, dest: Path, min_bytes: int = 100_000) -> bool:
    """Download a PDF with browser headers. Returns True on success."""
    for attempt in range(2):
        try:
            with httpx.Client(follow_redirects=True, timeout=180, headers=_BROWSER_HEADERS) as client:
                resp = client.get(url)
                if resp.status_code == 200 and len(resp.content) >= min_bytes:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(resp.content)
                    return True
                if resp.status_code in (403, 404, 406):
                    logger.warning("Anchor download HTTP %s for %s", resp.status_code, url)
                    return False
        except httpx.TimeoutException:
            if attempt == 0:
                continue
        except Exception as e:
            logger.warning("Anchor download failed %s: %s", url, e)
            return False
    return False


# ---------------------------------------------------------------------------
# Class B scrapers — landing-page → latest PDF URL
# ---------------------------------------------------------------------------

def _scrape_landing(landing_url: str) -> str | None:
    """Return HTML body of a landing page or None on failure."""
    try:
        with httpx.Client(follow_redirects=True, timeout=60, headers=_BROWSER_HEADERS) as client:
            resp = client.get(landing_url)
            if resp.status_code == 200:
                return resp.text
    except Exception as e:
        logger.warning("landing scrape failed %s: %s", landing_url, e)
    return None


def _scrape_rbi_mpr() -> str | None:
    """Return the latest RBI Monetary Policy Report PDF URL.

    RBI MPR is biannual (Apr + Oct); listed under HalfYearlyPublications.
    The top link on the page is the most recent MPR.
    """
    import re as _re
    html = _scrape_landing(
        "https://www.rbi.org.in/Scripts/HalfYearlyPublications.aspx?head=Monetary+Policy+Report"
    )
    if not html:
        return None
    m = _re.search(
        r'(https?://rbidocs\.rbi\.org\.in/rdocs/Publications/PDFs/MPR[A-Z0-9]+\.PDF)',
        html, _re.IGNORECASE,
    )
    return m.group(1) if m else None


def _scrape_rbi_ar_chapter(chapter_id: int) -> str | None:
    """Scrape a specific RBI Annual Report chapter by its landing-page Id.

    RBI AR is split across ~8 chapter PDFs — each has a stable landing-page
    Id that resolves to the latest publication's PDF (hash-suffixed URL).
    """
    import re as _re
    html = _scrape_landing(
        f"https://www.rbi.org.in/Scripts/AnnualReportPublications.aspx?Id={chapter_id}"
    )
    if not html:
        return None
    m = _re.search(
        r'(https?://rbidocs\.rbi\.org\.in/rdocs/AnnualReport/PDFs/\d+[A-Z]+\d+[A-Z0-9]+\.PDF)',
        html, _re.IGNORECASE,
    )
    return m.group(1) if m else None


def _scrape_rbi_ar_ch1_assessment() -> str | None:
    """Ch 1: Assessment & Outlook — RBI's own macro assessment and forward view."""
    return _scrape_rbi_ar_chapter(1431)


def _scrape_rbi_ar_ch2_economic() -> str | None:
    """Ch 2: Economic Review — GDP, inflation, real sector review."""
    return _scrape_rbi_ar_chapter(1432)


def _scrape_rbi_ar_ch3_monetary() -> str | None:
    """Ch 3: Monetary Policy Operations — rates, stance rationale, liquidity."""
    return _scrape_rbi_ar_chapter(1433)


def _scrape_imf_article_iv() -> str | None:
    """Return the latest IMF Article IV India PDF URL.

    IMF's www.imf.org is fronted by Akamai WAF which blocks httpx/curl even
    with full browser headers (HTTP 403). Reliable fetch would require a
    headless browser (Playwright). For v1 we return None; the agent falls
    back to WebSearch for IMF content. Users can manually drop an IMF PDF
    into ~/vault/macro/raw/imf_article_iv.pdf to pre-populate.
    """
    return None


def _scrape_irdai_annual_report() -> str | None:
    """Return the latest IRDAI Annual Report PDF URL.

    IRDAI publishes annual reports on https://irdai.gov.in/annual-reports
    with a per-FY entry served from /documents/<id>/<id>/<title>.pdf/<uuid>
    plus a `?version=X&t=<ts>&download=true` query suffix. The full URL
    (including suffix) is REQUIRED for the download to bypass the IRDAI
    Azure CDN's anti-direct-link protection — without `?download=true` the
    response is HTTP 403/404.

    The latest FY entry appears first on the landing page; we filter for
    titles containing "Annual Report" and "2024-25" / "2025-26" first, then
    fall back to the most recent (newest `t=` timestamp) IRDAI PDF link.
    """
    import re as _re
    landing_urls = [
        "https://irdai.gov.in/annual-reports",
        "https://irdai.gov.in/web/guest/annual-reports",
    ]
    # Capture the FULL URL including the trailing /<uuid>?version=...&download=true.
    # The closing-quote stops the match at the href boundary.
    full_url_pat = _re.compile(
        r'href="(https?://irdai\.gov\.in/documents/\d+/\d+/'
        r'[^"]+?\.pdf/[a-f0-9-]+'
        r'\?[^"]*download=true)"',
        _re.IGNORECASE,
    )
    for url in landing_urls:
        html = _scrape_landing(url)
        if not html:
            continue
        candidates = [m.group(1) for m in full_url_pat.finditer(html)]
        if not candidates:
            continue
        # Prefer URLs whose path mentions "Annual Report" (English token) or
        # an explicit recent FY ending — gives stability against Hindi-only
        # titles for older reports.
        from urllib.parse import unquote
        def _score(u: str) -> tuple[int, int]:
            decoded = unquote(u).lower()
            year_score = 0
            for fy in ("2025-26", "2024-25", "2023-24"):
                if fy in decoded:
                    year_score = max(year_score, int(fy.split("-")[0]))
                    break
            ar_token = 1 if "annual report" in decoded else 0
            return (year_score, ar_token)
        candidates.sort(key=_score, reverse=True)
        return candidates[0]
    return None


def _scrape_rbi_mpc_statement() -> str | None:
    """Return the latest RBI MPC press-release PDF URL.

    The MPC statement is published as an RBI press release on
    https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx — each release has
    a numeric `prid`. The canonical index that lists MPC statements (vs all
    press releases including monetary penalties) is AnnualPolicy.aspx.

    Strategy: scrape AnnualPolicy.aspx, find the latest MPC entry, follow
    to its detail page, extract the PDF link.
    """
    import re as _re
    landing_url = "https://www.rbi.org.in/Scripts/AnnualPolicy.aspx"
    html = _scrape_landing(landing_url)
    if not html:
        return None

    # Look for prid that's near "Resolution of the Monetary Policy Committee"
    # or "Monetary Policy Statement". AnnualPolicy.aspx renders these as
    # section blocks with the heading text + a Press Releases link.
    candidate_prids: list[str] = []
    for m in _re.finditer(
        r'(?i)(?:Resolution\s+of\s+the\s+Monetary\s+Policy\s+Committee'
        r'|Bi-monthly\s+Monetary\s+Policy\s+Statement'
        r'|Monetary\s+Policy\s+Statement)',
        html,
    ):
        # Look ~600 chars after the heading for an associated prid.
        snippet = html[m.start():m.end() + 600]
        prid_match = _re.search(r"prid=(\d+)", snippet)
        if prid_match:
            candidate_prids.append(prid_match.group(1))

    # First candidate = most recent (AnnualPolicy.aspx is in reverse-chronological order).
    for prid in candidate_prids:
        detail_url = (
            f"https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid={prid}"
        )
        detail_html = _scrape_landing(detail_url)
        if not detail_html:
            continue
        pdf_m = _re.search(
            r'(https?://rbidocs\.rbi\.org\.in/rdocs/PressRelease/PDFs/[A-Z0-9]+\.PDF)',
            detail_html, _re.IGNORECASE,
        )
        if pdf_m:
            return pdf_m.group(1)
    return None


_SCRAPERS = {
    "_scrape_rbi_mpr": _scrape_rbi_mpr,
    "_scrape_rbi_ar_ch1_assessment": _scrape_rbi_ar_ch1_assessment,
    "_scrape_rbi_ar_ch2_economic": _scrape_rbi_ar_ch2_economic,
    "_scrape_rbi_ar_ch3_monetary": _scrape_rbi_ar_ch3_monetary,
    "_scrape_imf_article_iv": _scrape_imf_article_iv,
    "_scrape_irdai_annual_report": _scrape_irdai_annual_report,
    "_scrape_rbi_mpc_statement": _scrape_rbi_mpc_statement,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_macro_anchors(force_refresh: bool = False) -> dict:
    """Download + extract all anchor docs. Skips entries already complete unless force_refresh.

    Returns summary dict:
      {
        "anchors_available": [list of doc_types with complete extraction],
        "anchors_missing": [list of doc_types that failed],
        "newly_extracted": int,
      }
    """
    _RAW_DIR.mkdir(parents=True, exist_ok=True)
    _EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    _META_DIR.mkdir(parents=True, exist_ok=True)

    catalog = _load_catalog()
    available: list[str] = []
    missing: list[str] = []
    newly_extracted = 0

    for spec in _ANCHORS:
        entry = catalog["anchors"].get(spec.doc_type, {})
        extracted_dir = _EXTRACTED_DIR / spec.doc_type
        md_path = extracted_dir / "_docling.md"

        if not force_refresh and entry.get("status") == "complete" and md_path.exists():
            available.append(spec.doc_type)
            continue

        url = spec.url
        if not url and spec.scraper:
            scraper = _SCRAPERS.get(spec.scraper)
            if scraper:
                url = scraper()

        if not url:
            logger.warning("No URL resolved for %s", spec.doc_type)
            catalog["anchors"][spec.doc_type] = {
                "title": spec.title,
                "url": None,
                "status": "url_unavailable",
            }
            missing.append(spec.doc_type)
            continue

        pdf_path = _RAW_DIR / f"{spec.doc_type}.pdf"
        ok = _download_pdf(url, pdf_path, min_bytes=spec.min_bytes)
        if not ok:
            catalog["anchors"][spec.doc_type] = {
                "title": spec.title,
                "url": url,
                "status": "download_failed",
            }
            missing.append(spec.doc_type)
            continue

        # Extract via Docling (cached by mtime)
        try:
            result = extract_to_markdown(pdf_path, extracted_dir)
            catalog["anchors"][spec.doc_type] = {
                "title": spec.title,
                "url": url,
                "pdf_path": str(pdf_path),
                "md_path": str(md_path),
                "backend": result.backend,
                "degraded": result.degraded,
                "heading_count": len(result.headings),
                "status": "complete",
            }
            available.append(spec.doc_type)
            if not result.from_cache:
                newly_extracted += 1
        except Exception as e:
            logger.warning("Extraction failed for %s: %s", spec.doc_type, e)
            catalog["anchors"][spec.doc_type] = {
                "title": spec.title,
                "url": url,
                "status": "extraction_failed",
                "error": str(e),
            }
            missing.append(spec.doc_type)

    _save_catalog(catalog)
    return {
        "anchors_available": available,
        "anchors_missing": missing,
        "newly_extracted": newly_extracted,
    }


def list_current_anchors() -> dict:
    """Return the catalog for inspection."""
    return _load_catalog()


# ---------------------------------------------------------------------------
# Heading-match heuristics
# ---------------------------------------------------------------------------
# RBI / IRDAI / Economic Survey docs frequently use:
#   - Section-prefix numbering: "I.2  Commodity Prices and Inflation",
#                               "II.1 Liquidity Conditions",
#                               "3. Prospects for 2025-26"
#   - Sub-headings at the same Docling level: a numbered parent like
#     "3. Prospects for 2025-26" is rendered L2 in the extracted heading
#     index, AND so are its sub-sections "Global Economy", "Domestic Economy",
#     "Box I.1 Bubble Dynamics in Gold Prices?". The default
#     same-or-higher-level end-rule then over-cuts the parent to ~30 chars.
# Both heuristics below address that.
#
# This is the macro-anchor analog of the auditor_report fix in
# `heading_toc.py` (PR #107) — same fuzzy-match family.

# Strips a section-prefix numbering token from the start of a heading.
# Covers:
#   "I.2 ..." / "II.1 ..." / "I.2.3 ..." (Roman + dotted decimals)
#   "3. ..."  / "4.1 ..." / "12. ..."    (Arabic + dotted decimals)
#   "(i) ..." / "(a) ..."                (parenthesised lower-letter/roman)
_SECTION_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"[IVXLC]+(?:\.[\dIVXLC]+)*\s*"          # Roman + optional sub-numbering
    r"|\d+(?:\.\d+)*\s*"                     # Arabic + optional sub-numbering
    r"|\([ivxlcdm\d]+\)\s*"                  # (i), (ii), (a), (1), …
    r"|\([a-z]\)\s*"                         # (a), (b), …
    r")[\.\)\:\-]?\s*",
    re.IGNORECASE,
)

# Detects whether a heading STARTS with a numbered section prefix — used by
# the smart end-detection rule (a numbered parent ends at the next numbered
# sibling, not the next un-numbered sub-heading).
_NUMBERED_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"[IVXLC]+(?:\.[\dIVXLC]+)*\s+\S"
    r"|\d+(?:\.\d+)*[\.\)]?\s+\S"
    r")",
    re.IGNORECASE,
)

# Box / table / figure sub-headings — never a section opener. RBI publications
# embed many "Box I.1 …", "Table II.2: …" mini-sections at the same Docling
# level as the parent, so we treat them as sub-content.
_BOX_HEADING_RE = re.compile(
    r"^\s*(?:Box|Table|Figure|Chart|Annex(?:ure)?|References?\s*:|Appendix)\b",
    re.IGNORECASE,
)


def _normalize_heading(text: str) -> str:
    """Lowercase + strip section-prefix numbering + collapse whitespace +
    normalize en/em-dashes + strip trailing punctuation.

    Used for fuzzy matching only — does NOT alter the heading_index source
    of truth.
    """
    s = text.strip().lower()
    # Drop section-prefix numbering ("i.2 ", "3. ", "(ii) ", …).
    s = _SECTION_PREFIX_RE.sub("", s)
    # Normalize unicode dashes → ascii hyphen
    s = s.replace("–", "-").replace("—", "-")
    # Drop common trailing punctuation
    s = s.rstrip(".:;,!?")
    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _match_heading(query: str, headings: list[dict]) -> int | None:
    """Return the index of the best-matching heading for `query`, or None.

    Multi-strategy search, ordered most-specific → most-permissive. The first
    pass that produces a hit wins (so existing exact-substring matches stay
    backwards-compatible).

    Strategies:
      1. Case-insensitive substring on raw heading text (legacy path).
      2. Case-insensitive substring on normalized text (handles section
         numbering, dashes, punctuation, multi-space).
      3. All query tokens present in the normalized heading (word-set match,
         word-order independent). Requires every query token of length >=3
         to appear, and at least 2 distinct tokens (or 1 token of length >=8)
         to avoid spurious matches like "the" → many headings.
    """
    if not headings:
        return None
    needle_raw = query.strip().lower()
    if not needle_raw:
        return None

    # Pass 1: raw substring (legacy)
    for i, h in enumerate(headings):
        if needle_raw in h["text"].lower():
            return i

    # Pass 2: normalized substring
    needle_norm = _normalize_heading(query)
    if needle_norm:
        for i, h in enumerate(headings):
            if needle_norm in _normalize_heading(h["text"]):
                return i

    # Pass 3: word-set match
    tokens = [t for t in re.split(r"\W+", needle_norm) if len(t) >= 3]
    # Guard: require either >=2 tokens OR a single token of length >=8.
    # Otherwise a stop-word query ("the") would match too eagerly.
    if not tokens:
        return None
    if len(tokens) < 2 and not any(len(t) >= 8 for t in tokens):
        return None
    for i, h in enumerate(headings):
        norm = _normalize_heading(h["text"])
        if all(re.search(r"\b" + re.escape(t) + r"\b", norm) for t in tokens):
            return i

    return None


def _find_anchor_section_end(
    md: str, headings: list[dict], match_idx: int
) -> int:
    """Return the char offset where the matched section ends.

    Default rule: next heading at same-or-higher level (lower number = higher).

    Smart override for NUMBERED parent headings (e.g. "3. Prospects for 2025-26",
    "I.2  Commodity Prices and Inflation"): un-numbered same-level headings
    that follow ("Global Economy", "Domestic Economy") and Box/Table/Figure
    sub-headings are treated as SUB-sections of the parent. The section
    therefore ends at the next NUMBERED heading at the same level, the next
    HIGHER-level heading, or end-of-doc — whichever comes first.

    This is the macro-anchor analog of `_find_section_end` for
    auditor_report in `heading_toc.py`.
    """
    h = headings[match_idx]
    start_text = h["text"]
    is_numbered_parent = bool(_NUMBERED_HEADING_RE.match(start_text)) and not _BOX_HEADING_RE.match(start_text)

    end = len(md)
    for h2 in headings[match_idx + 1:]:
        text = h2["text"]
        # Higher-level heading → always ends the section.
        if h2["level"] < h["level"]:
            return h2["char_offset"]
        if h2["level"] == h["level"]:
            # Box/Table/Figure same-level headings are always sub-content
            # — RBI publications embed these inline at the same Docling
            # level as their parent prose section. Skip past them.
            if _BOX_HEADING_RE.match(text):
                continue
            if not is_numbered_parent:
                # Default for un-numbered parents: any other same-level
                # heading ends the section (preserves backwards-compat).
                return h2["char_offset"]
            # Numbered parent: skip un-numbered same-level headings (they're
            # really sub-sections that Docling failed to demote a level).
            # End only at the next NUMBERED same-level sibling.
            if _NUMBERED_HEADING_RE.match(text):
                return h2["char_offset"]
            # un-numbered same-level → treat as sub-section, keep scanning.
            continue
    return end


# Body-text fallback parameters — when no heading matches, fall back to a
# slice anchored on the first plausible body-text occurrence of the query.
_BODY_FALLBACK_MIN_QUERY_LEN = 6  # avoid stop-word fallbacks
_BODY_FALLBACK_BEFORE = 200       # chars of context before the match
_BODY_FALLBACK_AFTER = 12_000     # chars of content after the match


def _body_text_anchor(md: str, headings: list[dict], query: str) -> dict | None:
    """Last-resort fallback: find `query` (or its normalized form) as plain
    body text in the markdown and return a slice ending at the next heading.

    Used when no heading matches at all — covers the case where a user asks
    for a vocabulary that doesn't appear in any heading (e.g. "private
    consumption" in the Economic Survey, where the actual heading is
    "Demand side: Domestic drivers anchor GDP growth in FY26" but the body
    text discusses private consumption).
    """
    needle = query.strip().lower()
    if len(needle) < _BODY_FALLBACK_MIN_QUERY_LEN:
        return None

    md_lower = md.lower()
    # Try raw substring first.
    pos = md_lower.find(needle)
    if pos < 0:
        # Try normalized form (collapse whitespace, drop dashes).
        normalized_needle = _normalize_heading(query)
        if (
            normalized_needle
            and len(normalized_needle) >= _BODY_FALLBACK_MIN_QUERY_LEN
            and normalized_needle != needle
        ):
            pos = md_lower.find(normalized_needle)
    if pos < 0:
        return None

    # Find the heading-range that contains pos (so we can label which
    # section the user landed in).
    containing_heading = None
    for h in headings:
        if h["char_offset"] <= pos:
            containing_heading = h
        else:
            break

    # Compute the slice: from a bit before the match to the next
    # same-or-higher-level heading (or +AFTER chars cap).
    start = max(0, pos - _BODY_FALLBACK_BEFORE)
    end_cap = pos + _BODY_FALLBACK_AFTER

    # Find the next heading after `pos` that bounds the synthetic section.
    end_heading = None
    for h in headings:
        if h["char_offset"] > pos:
            # If we have a containing heading, end at the next
            # same-or-higher-level heading; otherwise just the next heading.
            if containing_heading is None or h["level"] <= containing_heading["level"]:
                end_heading = h
                break

    end = end_heading["char_offset"] if end_heading else len(md)
    end = min(end, end_cap)
    if end <= start:
        return None

    return {
        "char_start": start,
        "char_end": end,
        "containing_heading": containing_heading["text"] if containing_heading else None,
        "containing_heading_level": containing_heading["level"] if containing_heading else None,
        "matched_offset": pos,
    }


def get_anchor_content(doc_type: str, section: str | None = None) -> dict:
    """Fetch extracted content for a doc_type.

    - section=None → returns TOC: heading list + metadata (compact ~2-5KB)
    - section=<str> → returns markdown slice for the matching heading.
      Matching is fuzzy (case-insensitive, tolerant of section-prefix
      numbering, dashes, trailing punctuation, word-order variations) and
      falls back to a body-text anchor when no heading matches.
    """
    catalog = _load_catalog()
    entry = catalog["anchors"].get(doc_type)
    if not entry or entry.get("status") != "complete":
        return {
            "status": "unavailable",
            "doc_type": doc_type,
            "reason": entry.get("status", "not_extracted") if entry else "not_in_catalog",
            "fallback": "Use WebFetch/WebSearch against T2 sources (PIB, PRS, Reuters, Mint).",
        }

    extracted_dir = _EXTRACTED_DIR / doc_type
    md_path = extracted_dir / "_docling.md"
    idx_path = extracted_dir / "_heading_index.json"
    if not md_path.exists() or not idx_path.exists():
        return {"status": "unavailable", "doc_type": doc_type, "reason": "files_missing"}

    md = md_path.read_text(encoding="utf-8")
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    headings = idx.get("headings", [])

    if section is None:
        # TOC — compact view, first 60 headings, with URL + byte count
        return {
            "status": "ok",
            "doc_type": doc_type,
            "title": entry.get("title"),
            "url": entry.get("url"),
            "heading_count": len(headings),
            "total_chars": len(md),
            "sections": [
                {"level": h["level"], "text": h["text"], "offset": h["char_offset"]}
                for h in headings[:60]
            ],
            "_hint": (
                "Call again with section='<heading substring>' to read a specific section. "
                "Match is fuzzy: case-insensitive, tolerant of section-prefix numbering "
                "(e.g. 'I.2', '3.'), dashes, and trailing punctuation. If no heading matches, "
                "a body-text occurrence is used as the anchor."
            ),
        }

    MAX_CHARS = 18_000

    # Heading match — fuzzy multi-pass.
    match_idx = _match_heading(section, headings)

    if match_idx is not None:
        h = headings[match_idx]
        start = h["char_offset"]
        end = _find_anchor_section_end(md, headings, match_idx)
        slice_md = md[start:end]
        truncated = False
        if len(slice_md) > MAX_CHARS:
            slice_md = (
                slice_md[:MAX_CHARS]
                + "\n\n[... truncated — section exceeds 18KB; drill deeper with more specific section name]"
            )
            truncated = True
        return {
            "status": "ok",
            "doc_type": doc_type,
            "title": entry.get("title"),
            "url": entry.get("url"),
            "heading": h["text"],
            "heading_level": h["level"],
            "content": slice_md,
            "chars": len(slice_md),
            "truncated": truncated,
            "match_source": "heading",
        }

    # Body-text fallback — find the phrase in the markdown body.
    fallback = _body_text_anchor(md, headings, section)
    if fallback is not None:
        slice_md = md[fallback["char_start"]:fallback["char_end"]]
        truncated = False
        if len(slice_md) > MAX_CHARS:
            slice_md = (
                slice_md[:MAX_CHARS]
                + "\n\n[... truncated — slice exceeds 18KB; refine query]"
            )
            truncated = True
        return {
            "status": "ok",
            "doc_type": doc_type,
            "title": entry.get("title"),
            "url": entry.get("url"),
            "heading": fallback["containing_heading"] or "(body-text anchor)",
            "heading_level": fallback["containing_heading_level"] or 0,
            "content": slice_md,
            "chars": len(slice_md),
            "truncated": truncated,
            "match_source": "body_text",
            "_note": (
                "No heading matched the query; returning a slice anchored at a body-text "
                "occurrence. The 'heading' field shows the containing section (if any)."
            ),
        }

    return {
        "status": "not_found",
        "doc_type": doc_type,
        "section_query": section,
        "available_headings": [h["text"] for h in headings[:30]],
    }
