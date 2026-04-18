"""Download + extract canonical India macro anchor documents.

Parallels ar_downloader + annual_report_extractor for India-wide macro docs
(Economic Survey, Union Budget, RBI publications, IMF Article IV).

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


_SCRAPERS = {
    "_scrape_rbi_mpr": _scrape_rbi_mpr,
    "_scrape_rbi_ar_ch1_assessment": _scrape_rbi_ar_ch1_assessment,
    "_scrape_rbi_ar_ch2_economic": _scrape_rbi_ar_ch2_economic,
    "_scrape_rbi_ar_ch3_monetary": _scrape_rbi_ar_ch3_monetary,
    "_scrape_imf_article_iv": _scrape_imf_article_iv,
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


def get_anchor_content(doc_type: str, section: str | None = None) -> dict:
    """Fetch extracted content for a doc_type.

    - section=None → returns TOC: heading list + metadata (compact ~2-5KB)
    - section=<str> → returns markdown slice from the matching heading to the next
      same-or-higher-level heading (case-insensitive substring match on heading text).
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
                "Match is case-insensitive substring against heading text."
            ),
        }

    # Section drill — find first heading whose text contains `section` (case-insensitive)
    needle = section.strip().lower()
    match_idx = next(
        (i for i, h in enumerate(headings) if needle in h["text"].lower()),
        None,
    )
    if match_idx is None:
        return {
            "status": "not_found",
            "doc_type": doc_type,
            "section_query": section,
            "available_headings": [h["text"] for h in headings[:30]],
        }

    h = headings[match_idx]
    start = h["char_offset"]
    # End = next heading at same or higher level (smaller level number = higher)
    end = len(md)
    for h2 in headings[match_idx + 1:]:
        if h2["level"] <= h["level"]:
            end = h2["char_offset"]
            break
    slice_md = md[start:end]
    # Cap the slice to avoid huge returns
    MAX_CHARS = 18_000
    truncated = False
    if len(slice_md) > MAX_CHARS:
        slice_md = slice_md[:MAX_CHARS] + "\n\n[... truncated — section exceeds 18KB; drill deeper with more specific section name]"
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
    }
