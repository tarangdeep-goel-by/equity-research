"""Tests for doc_extractor (Docling wrapper) and heading_toc (section indexer)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from flowtracker.research.doc_extractor import (
    ExtractionResult,
    _scan_headings,
    extract_to_markdown,
)
from flowtracker.research.heading_toc import (
    build_ar_section_index,
    deck_slide_index,
    section_size_summary,
    slice_section,
)


# ---------------------------------------------------------------------------
# _scan_headings — flat heading parser
# ---------------------------------------------------------------------------

def test_scan_headings_extracts_levels_and_offsets():
    md = "# Top\n\nbody\n\n## Sub one\n\nmore\n\n### Deep\n"
    out = _scan_headings(md)
    assert len(out) == 3
    assert out[0]["level"] == 1
    assert out[0]["text"] == "Top"
    assert out[1]["level"] == 2
    assert out[2]["level"] == 3
    assert out[0]["char_offset"] < out[1]["char_offset"] < out[2]["char_offset"]


def test_scan_headings_ignores_hashes_in_body():
    md = "# Real\n\nThis is # not a heading\n\n## Also real\n"
    out = _scan_headings(md)
    assert [h["text"] for h in out] == ["Real", "Also real"]


# ---------------------------------------------------------------------------
# extract_to_markdown — caching + fallback
# ---------------------------------------------------------------------------

def test_cache_hit_when_md_newer_than_pdf(tmp_path: Path):
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"not a real pdf")
    cache = tmp_path / "cache"
    cache.mkdir()

    md = "# Cached\n\nbody"
    (cache / "_docling.md").write_text(md)
    (cache / "_heading_index.json").write_text(json.dumps({
        "source_pdf": str(pdf),
        "backend": "docling",
        "degraded": False,
        "elapsed_s": 5.0,
        "headings": [{"level": 1, "text": "Cached", "char_offset": 0}],
    }))
    # Make cache newer than the pdf so cache wins.
    future = pdf.stat().st_mtime + 100
    os.utime(cache / "_docling.md", (future, future))
    os.utime(cache / "_heading_index.json", (future, future))

    res = extract_to_markdown(pdf, cache)
    assert res.from_cache is True
    assert res.markdown == md
    assert res.backend == "docling"
    assert res.degraded is False
    assert len(res.headings) == 1


def test_pdfplumber_fallback_on_docling_failure(tmp_path: Path, monkeypatch):
    """When Docling raises, we should fall back to pdfplumber and mark degraded=True."""
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"definitely not a pdf")
    cache = tmp_path / "cache"

    # Force Docling import to raise so the except path runs.
    def _raise(*a, **k):
        raise RuntimeError("docling exploded")

    import flowtracker.research.doc_extractor as mod

    class _FakeConv:
        def convert(self, *a, **k):
            raise RuntimeError("docling exploded")

    class _FakeDocClass:
        def __init__(self):
            pass

    monkeypatch.setattr(
        mod, "_pdfplumber_fallback",
        lambda p: "# Fallback\n\nfallback body",
    )
    # Patch DocumentConverter import inside the function via sys.modules trick.
    import sys, types
    fake_mod = types.SimpleNamespace(DocumentConverter=_FakeConv)
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_mod)

    res = extract_to_markdown(pdf, cache)
    assert res.degraded is True
    assert res.backend == "pdfplumber"
    assert "Fallback" in res.markdown
    # Cache should have been written.
    assert (cache / "_docling.md").exists()


# ---------------------------------------------------------------------------
# build_ar_section_index — canonical section detection
# ---------------------------------------------------------------------------

def _md_with_sections() -> tuple[str, list[dict]]:
    """Synthetic AR markdown with the SEBI-mandated sections in plausible order."""
    md = (
        "# COVER\n\n"
        "front matter\n\n"
        "## DIRECTORS' REPORT\n\n"
        "report body about the year\n\n"
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"
        + ("mdna content " * 300) + "\n\n"
        "## RISK MANAGEMENT\n\n"
        + ("risk body " * 100) + "\n\n"
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor body " * 200) + "\n\n"
        "## CORPORATE GOVERNANCE REPORT\n\n"
        + ("cg body " * 150) + "\n\n"
        "## BUSINESS RESPONSIBILITY AND SUSTAINABILITY REPORT\n\n"
        + ("brsr body " * 200) + "\n\n"
        "## RELATED PARTY TRANSACTIONS\n\n"
        + ("rpt body " * 80) + "\n\n"
        "## NOTES TO THE FINANCIAL STATEMENTS\n\n"
        + ("notes body " * 250) + "\n\n"
    )
    return md, _scan_headings(md)


def test_section_index_finds_all_sebi_sections():
    md, headings = _md_with_sections()
    idx = build_ar_section_index(md, headings)
    # Every section we wrote should be matched.
    expected = {
        "directors_report", "mdna", "risk_management", "auditor_report",
        "corporate_governance", "brsr", "related_party", "notes_to_financials",
    }
    assert expected <= set(idx.keys()), f"missing: {expected - set(idx.keys())}"


def test_largest_match_wins_when_section_appears_twice():
    """AR has both a forward reference ('see MD&A Report') and the real section header.
    The largest candidate should win — the real section has more content."""
    md = (
        "## DIRECTORS' REPORT\n\n"
        "Brief: see Management Discussion and Analysis below.\n\n"
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"  # forward ref, ends quickly
        "See separate section.\n\n"
        "## CORPORATE GOVERNANCE REPORT\n\n"
        "gov stuff\n\n"
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"  # the real one
        + ("real mdna content " * 500) + "\n\n"
        "## NEXT SECTION\n\n"
        "trailing\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "mdna" in idx
    # The chosen section should be the big one (the "real" one).
    assert idx["mdna"]["size_chars"] > 5000
    mdna_text = slice_section(md, idx, "mdna")
    assert "real mdna content" in mdna_text


def test_largest_gap_wins_between_two_heading_candidates():
    """Task scenario: synthetic doc with MDA at offset ~500 (body ~400 chars)
    followed by MDA at a much later offset (body ~100KB). Slicer must pick
    the second, larger-body candidate."""
    # Build a doc where the first MDA heading has only a short body (ends
    # at the next same-level heading <500 chars later) and the second MDA
    # heading has a much larger body.
    prefix = "x" * 400  # pad doc start
    small_body = "short forward-ref stuff\n\n"
    filler = "filler line\n" * 3000  # ~36KB
    big_body = "real mdna text line\n" * 5000  # ~100KB
    md = (
        prefix + "\n\n"
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"
        + small_body
        + "## CORPORATE GOVERNANCE REPORT\n\n"
        + filler
        + "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"
        + big_body
        + "## NEXT SECTION\n\n"
        + "tail\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "mdna" in idx
    # Confirm the slicer picked the large candidate — its char_start should be
    # deep into the document (after the filler), not near offset 400.
    assert idx["mdna"]["char_start"] > 30_000, (
        f"Expected the large-body MDA far into the doc, got char_start={idx['mdna']['char_start']}"
    )
    assert idx["mdna"]["size_chars"] > 50_000
    mdna_text = slice_section(md, idx, "mdna")
    assert "real mdna text line" in mdna_text
    # The small forward-ref blurb must NOT be in the chosen slice.
    assert "short forward-ref stuff" not in mdna_text


def test_body_text_fallback_when_heading_slice_is_tiny():
    """Reproduces the SUNPHARMA FY25 bug: the only `##` MD&A heading is a
    forward reference with <500 chars of body, but the real MD&A content
    appears further down as *plain-text* running-header text (Docling
    didn't recognise it as a heading). The body-text fallback should
    synthesise an anchor at the plain-text occurrence and produce a
    multi-KB slice."""
    md = (
        "## DIRECTORS' REPORT\n\n"
        "intro\n\n"
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"
        # Tiny body — only a forward-reference blurb.
        "The Management Discussion and Analysis is provided separately.\n\n"
        "## CORPORATE GOVERNANCE REPORT\n\n"
        "Governance disclosure opening...\n\n"
        # Real MD&A body, but Docling rendered the title as plain-text
        # (running header text) not as a markdown heading. Subsections
        # within MD&A are level-2 too — they don't match other canonicals.
        "Management Discussion and Analysis\n\n"
        "<!-- image -->\n\n"
        "## Global Pharmaceutical Industry\n\n"
        + ("industry commentary " * 400) + "\n\n"
        "## Developed Markets\n\n"
        + ("developed markets prose " * 300) + "\n\n"
        "## US\n\n"
        + ("US market commentary " * 300) + "\n\n"
        # A different canonical section terminates the synthetic MD&A.
        "## Independent Auditor's Report\n\n"
        "auditor opinion text\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)

    assert "mdna" in idx
    entry = idx["mdna"]
    # Body-text fallback should have fired because the heading-based slice
    # was tiny (<2KB).
    assert entry["match_source"] == "body_text", (
        f"Expected body_text fallback, got {entry['match_source']}"
    )
    # Resulting slice should be multi-KB and contain the real MD&A prose.
    assert entry["size_chars"] > 5000
    mdna_text = slice_section(md, idx, "mdna")
    assert "industry commentary" in mdna_text
    assert "developed markets prose" in mdna_text
    # Must NOT extend into the auditor report.
    assert "auditor opinion text" not in mdna_text


def test_body_text_fallback_skipped_when_heading_slice_is_large_enough():
    """Safety guard: when the heading-based match already yields a healthy
    slice, the body-text fallback must NOT replace it even if stray
    plain-text mentions exist elsewhere."""
    md = (
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"
        + ("real mdna prose " * 500) + "\n\n"  # ~8KB, well above the 2KB floor
        "## RISK MANAGEMENT\n\n"
        # A stray plain-text mention further down — fallback would pick this
        # as a synthetic anchor and produce a much longer fake section if
        # the gate were broken.
        "Management Discussion and Analysis was filed separately.\n\n"
        + ("risk prose " * 100) + "\n\n"
        "## NEXT\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert idx["mdna"]["match_source"] == "heading"
    assert idx["mdna"]["char_start"] == 0


def test_auditor_report_iar_with_annexure_a_subsection_picks_iar_body():
    """Regression for HDFCBANK FY25 bug: the IAR has many L2 sub-headings
    (Opinion, Basis for Opinion, Key Audit Matters, Other Information,
    Auditor's Responsibilities, …). The CARO sub-section appears as
    'Annexure A to Independent Auditor's Report' WITHIN the IAR body.

    Old heuristic: largest-section-wins picked the Annexure A heading
    (because it matches the auditor regex) and ended at the next L2
    heading inside it — yielding a 200-char header-only slice, missing
    the entire IAR body with KAMs.

    Fix: prefer the IAR start anchor ('Report on Audit of the
    [Standalone|Consolidated] Financial Statements'), exclude Annexure-A
    sub-headings as candidate starts, and end the auditor section at the
    next canonical-section heading or at the financial statements
    (Balance Sheet / Profit and Loss / Cash Flow), NOT at the next L2.
    """
    md = (
        "## DIRECTORS' REPORT\n\n"
        + ("dr body " * 50) + "\n\n"
        # Start of standalone IAR — this is the heading the fix must anchor on.
        "## To the Members of HDFC Bank Limited\n\n"
        "## Report on Audit of the Standalone Financial Statements\n\n"
        "## Opinion\n\n"
        + ("opinion body " * 100) + "\n\n"
        "## Basis for Opinion\n\n"
        + ("basis body " * 50) + "\n\n"
        "## Key audit matters\n\n"
        + ("KAM 1: Provisioning for advances " * 100) + "\n\n"
        + ("KAM 2: Information technology " * 100) + "\n\n"
        "## Other Information\n\n"
        + ("other info " * 50) + "\n\n"
        "## Auditor's responsibilities for the audit of the Standalone Financial Statements\n\n"
        + ("auditor resp body " * 50) + "\n\n"
        "## Other Matters\n\n"
        + ("other matters body " * 30) + "\n\n"
        "## Report on other legal and regulatory requirements\n\n"
        + ("RoLRR body " * 30) + "\n\n"
        # Annexure A — sub-section of IAR (the CARO/IFC report). The bug
        # was that this header was the only heading the OLD regex could
        # match; it then ended at the next L2 inside the annexure (~240 chars).
        "## Annexure A to Independent Auditor's Report\n\n"
        "## Report on the Internal Financial Controls\n\n"
        + ("IFC body " * 30) + "\n\n"
        "## Management's Responsibility for Internal Financial Controls\n\n"
        + ("ifc resp body " * 30) + "\n\n"
        # End boundary: financial statements.
        "## STANDALONE PROFIT AND LOSS ACCOUNT\n\n"
        + ("PnL body " * 30) + "\n\n"
        "## STANDALONE CASH FLOW STATEMENT\n\n"
        + ("CF body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)

    assert "auditor_report" in idx, "auditor_report section must be detected"
    aud = idx["auditor_report"]
    # Slice should be the full IAR body — many KB, not the 240-char annexure header.
    assert aud["size_chars"] > 5_000, (
        f"Expected IAR body >5KB, got {aud['size_chars']} chars — "
        f"matched_heading={aud.get('matched_heading')!r}"
    )
    text = slice_section(md, idx, "auditor_report")
    # Must contain the actual IAR body markers.
    assert "Opinion" in text
    assert "Key audit matters" in text or "KAM 1" in text
    assert "KAM 1: Provisioning for advances" in text
    assert "KAM 2: Information technology" in text
    # Must NOT extend into the financial statements.
    assert "STANDALONE PROFIT AND LOSS ACCOUNT" not in text
    assert "PnL body" not in text


def test_auditor_report_excludes_annexure_a_as_section_start():
    """Annexure A is a sub-section of the IAR (CARO / IFC report) — it
    should NOT be picked as the auditor_report section start, even when
    no IAR start anchor is detectable as a heading.
    """
    md = (
        "## DIRECTORS' REPORT\n\n"
        + ("dr body " * 50) + "\n\n"
        # Only the Annexure A heading is detected as auditor-related —
        # but it points at the CARO report, not the IAR. With the old
        # heuristic this would be picked. With the fix, the auditor
        # section must either be absent or come from a different anchor.
        "## Annexure A to Independent Auditor's Report\n\n"
        + ("annexure body " * 100) + "\n\n"
        "## STANDALONE PROFIT AND LOSS ACCOUNT\n\n"
        + ("pnl body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    # Either the section is absent OR (if a body-text fallback fires) it
    # comes from a non-Annexure source. The Annexure heading itself must
    # not be the matched_heading.
    if "auditor_report" in idx:
        matched = idx["auditor_report"].get("matched_heading", "").lower()
        assert "annexure" not in matched, (
            f"Annexure A must not be picked as auditor_report start; "
            f"got matched_heading={matched!r}"
        )


def test_auditor_report_anchored_on_report_on_audit_heading():
    """The 'Report on Audit of the (Standalone|Consolidated) Financial
    Statements' heading is the canonical IAR opener in Indian banks/NBFCs
    and many large issuers. It must match auditor_report.
    """
    md = (
        "## DIRECTORS' REPORT\n\n"
        + ("dr " * 50) + "\n\n"
        "## Report on Audit of the Consolidated Financial Statements\n\n"
        + ("auditor body " * 200) + "\n\n"
        "## Opinion\n\n"
        + ("opinion " * 100) + "\n\n"
        "## CONSOLIDATED BALANCE SHEET\n\n"
        + ("bs body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "auditor_report" in idx
    aud = idx["auditor_report"]
    assert aud["size_chars"] > 2_000
    text = slice_section(md, idx, "auditor_report")
    assert "auditor body" in text
    assert "CONSOLIDATED BALANCE SHEET" not in text


def test_section_not_present_is_absent_from_index():
    md = "# Just a cover\n\nNothing else here.\n"
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert idx == {}


def test_slice_section_returns_empty_for_missing():
    assert slice_section("hello", {}, "mdna") == ""


def test_section_size_summary_classifies_by_size():
    md = (
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor " * 50) + "\n\n"      # ~400 chars → small
        "## NOTES TO THE FINANCIAL STATEMENTS\n\n"
        + ("notes " * 5000) + "\n\n"      # ~30KB → large
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    summary = {s["name"]: s["size_class"] for s in section_size_summary(idx)}
    assert summary["auditor_report"] == "small"
    assert summary["notes_to_financials"] in ("large", "huge")


# ---------------------------------------------------------------------------
# deck_slide_index — slide topic index
# ---------------------------------------------------------------------------

def test_deck_slide_index_filters_short_and_deep_headings():
    headings = [
        {"level": 1, "text": "Q3 FY26", "char_offset": 0},
        {"level": 2, "text": "Market Update", "char_offset": 100},
        {"level": 3, "text": "Segmental", "char_offset": 200},
        {"level": 5, "text": "Deep heading we want to skip", "char_offset": 300},
        {"level": 2, "text": "X", "char_offset": 400},  # too short
    ]
    out = deck_slide_index(headings)
    titles = [s["slide"] for s in out]
    assert titles == ["Q3 FY26", "Market Update", "Segmental"]
