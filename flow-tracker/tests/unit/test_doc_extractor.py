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


def test_auditor_report_matches_plural_possessive_apostrophe():
    """SBIN FY25 layout: PSU bank with joint statutory auditors uses
    "Independent Auditors' Report" (plural-possessive — apostrophe AFTER
    the s). The original `auditor'?s?` regex matched only `Auditor` /
    `Auditors` / `Auditor's` (apostrophe BEFORE s) and missed `Auditors'`.
    The fixed `auditor'?s?'?` regex matches all four forms.
    """
    md = (
        "## DIRECTORS' REPORT\n\n"
        + ("dr body " * 50) + "\n\n"
        # SBIN's IAR opener is plural-possessive.
        "## Independent Auditors' Report\n\n"
        "## Report on Audit of the Standalone Financial Statements of State Bank of India\n\n"
        "## Opinion\n\n"
        "We have audited the accompanying standalone financial statements...\n\n"
        + ("opinion body " * 100) + "\n\n"
        "## Basis for Opinion\n\n"
        + ("basis body " * 50) + "\n\n"
        "## Key Audit Matters\n\n"
        + ("KAM provisioning for advances " * 100) + "\n\n"
        + ("KAM IT systems " * 100) + "\n\n"
        # Banking-layout end anchor — schedules block opens here.
        "## STANDALONE FINANCIALS\n\n"
        + ("schedules body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "auditor_report" in idx, "auditor_report must be detected for SBIN-style plural-possessive"
    aud = idx["auditor_report"]
    assert aud["size_chars"] > 5_000, (
        f"Expected IAR body >5KB, got {aud['size_chars']} — matched={aud.get('matched_heading')!r}"
    )
    text = slice_section(md, idx, "auditor_report")
    assert "Key Audit Matters" in text
    assert "Basis for Opinion" in text
    assert "We have audited" in text
    # Must NOT extend past the STANDALONE FINANCIALS schedules-block anchor.
    assert "schedules body" not in text


def test_auditor_report_substantive_score_breaks_tie_with_annexure_running_header():
    """SBIN FY25 'Annexure list of subsidiaries' running-header bug:
    PSU bank ARs repeat 'Independent Auditors' Report' as a page-running
    header on EVERY page including subsidiary-list annexure pages. With
    plural-possessive matching enabled, every running-header instance
    becomes a candidate. The largest-section-wins heuristic then picks
    the annexure-list slice (huge body of subsidiary-table rows, zero
    Opinion / KAM content).

    Fix: tie-break with `_iar_substantive_score` — count IAR-substance
    markers ('Basis for Opinion', 'Key Audit Matters', 'we have audited',
    etc.) in the first ~6KB of each candidate slice. Annexure-list slices
    score 0; real IAR slices score 3+.
    """
    md = (
        # Real IAR opener — short slice (12K) but full of substance markers.
        "## Independent Auditors' Report\n\n"
        "## Report on Audit of the Standalone Financial Statements\n\n"
        "## Opinion\n\n"
        "1. We have audited the accompanying standalone financial statements...\n\n"
        "In our opinion, the standalone financial statements give a true and fair view...\n\n"
        + ("opinion body line " * 50) + "\n\n"
        "## Basis for Opinion\n\n"
        + ("basis body " * 50) + "\n\n"
        "## Key Audit Matters\n\n"
        + ("KAM 1 advances " * 50) + "\n\n"
        + ("KAM 2 IT " * 50) + "\n\n"
        "## STANDALONE FINANCIALS\n\n"
        + ("schedule data " * 200) + "\n\n"
        # Page-running-header repeat — same heading text but the body that
        # follows is just a subsidiary-list table, no Opinion / KAM markers.
        # Without substantive scoring, this 30K slice would beat the 5K real one.
        "## Independent Auditors' Report\n\n"
        "## Annexure: List of subsidiaries consolidated as at March 31, 2025\n\n"
        + ("subsidiary co name " * 1500) + "\n\n"
        "## CONSOLIDATED BALANCE SHEET\n\n"
        + ("bs body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "auditor_report" in idx
    aud = idx["auditor_report"]
    text = slice_section(md, idx, "auditor_report")
    # Substantive scoring must pick the real IAR slice, NOT the bigger Annexure slice.
    assert "Key Audit Matters" in text, (
        f"Expected real IAR (with KAMs) to win, got annexure slice — matched={aud.get('matched_heading')!r}"
    )
    assert "Basis for Opinion" in text
    # Subsidiary list must NOT be in the chosen slice.
    assert "subsidiary co name" not in text


def test_auditor_report_excludes_independent_practitioner_assurance_report():
    """HDFCLIFE FY25 layout: insurer's separate BRSR-only filing has
    "Independent Practitioner's Reasonable Assurance Report on Identified
    Sustainability Information" — an ESG sustainability assurance report
    issued by the auditor firm but NOT the statutory IAR. It must NOT be
    picked as the auditor_report section start, because the resulting
    slice would (a) confuse the LLM with sustainability-assurance prose
    and (b) extract a fake "Opinion" that is about ESG, not financials.
    """
    md = (
        "## DIRECTORS' REPORT\n\n"
        + ("dr body " * 50) + "\n\n"
        # HDFCLIFE FY25's only audit-shaped heading is the ESG assurance
        # report. There is NO statutory IAR in this filing (it was a
        # separate BRSR-only submission to BSE).
        "## Independent Practitioner's Reasonable Assurance Report on Identified Sustainability Information in HDFC Life Insurance Company Limited\n\n"
        "## TO, The Board of Directors, HDFC Life Insurance Company Limited\n\n"
        + ("assurance body " * 100) + "\n\n"
        "## Identified Sustainability Information\n\n"
        + ("ESG metric data " * 50) + "\n\n"
        "## Opinion\n\n"
        + ("ESG opinion body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    # auditor_report must be ABSENT — the ESG assurance report is not the IAR.
    if "auditor_report" in idx:
        matched = idx["auditor_report"].get("matched_heading", "").lower()
        assert "practitioner" not in matched, (
            f"ESG sustainability assurance must not be picked as auditor_report; "
            f"got matched_heading={matched!r}"
        )


def test_auditor_report_ends_at_plural_statement_of_cash_flows():
    """HINDUNILVR FY25 layout: end anchor uses plural 'Statement of Cash
    Flows' (Ind AS / consolidated layout) — the older `cash\\s+flow\\s+statement`
    regex required singular 'Cash Flow Statement'. The IAR slice must end
    cleanly at the plural anchor.
    """
    md = (
        "## Independent Auditor's Report\n\n"
        "## REPORT ON THE AUDIT OF THE STANDALONE FINANCIAL STATEMENTS Opinion\n\n"
        "We have audited the accompanying standalone financial statements...\n\n"
        + ("opinion body " * 50) + "\n\n"
        "## Basis for Opinion\n\n"
        + ("basis body " * 30) + "\n\n"
        "## Key Audit Matters\n\n"
        + ("KAM body " * 100) + "\n\n"
        "## Standalone Statement of Cash Flows\n\n"
        + ("cf body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "auditor_report" in idx
    text = slice_section(md, idx, "auditor_report")
    assert "Key Audit Matters" in text
    # Must end at the plural Cash Flows anchor — cf body must not leak in.
    assert "cf body" not in text


def test_auditor_report_ends_at_bank_standalone_financials_block():
    """SBIN FY25 layout: Indian-bank ARs use 'STANDALONE FINANCIALS' /
    'CONSOLIDATED FINANCIALS' / 'Schedule N' as the financial-statements
    block divider rather than the standard 'Balance Sheet' / 'P&L' headings.
    The IAR slice must end at the FINANCIALS divider, not run into the
    schedules pages (which would dilute the LLM's KAM-extraction signal).
    """
    md = (
        "## Independent Auditors' Report\n\n"
        "## REPORT ON AUDIT OF THE STANDALONE FINANCIAL STATEMENTS OF STATE BANK OF INDIA\n\n"
        "## Opinion\n\n"
        "We have audited...\n\n"
        + ("opinion body " * 30) + "\n\n"
        "## Basis for Opinion\n\n"
        + ("basis " * 20) + "\n\n"
        "## Key Audit Matters\n\n"
        + ("KAM " * 200) + "\n\n"
        "## STANDALONE FINANCIALS\n\n"
        "## SCHEDULE 1 - CAPITAL\n\n"
        + ("schedule capital data " * 50) + "\n\n"
        "## SCHEDULE 2 - RESERVES & SURPLUS\n\n"
        + ("schedule reserves data " * 50) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "auditor_report" in idx
    text = slice_section(md, idx, "auditor_report")
    assert "Key Audit Matters" in text
    # IAR must end at the bank-layout STANDALONE FINANCIALS divider.
    assert "schedule capital data" not in text
    assert "schedule reserves data" not in text


def test_auditor_report_excludes_quoted_letter_annexure():
    """SBIN FY25 has 'Annexure 'A' to the Independent Auditors' Report'
    — the letter is wrapped in straight quotes. The original
    `[a-z0-9]+` token didn't match `'A'` (with quote chars), letting the
    Annexure heading slip through as a candidate IAR start. The fix
    accepts optional surrounding quote chars (', ") around the letter.
    """
    md = (
        "## DIRECTORS' REPORT\n\n"
        + ("dr " * 50) + "\n\n"
        # Only the quoted-letter Annexure is detected as audit-related.
        "## Annexure 'A' to the Independent Auditors' Report\n\n"
        + ("annexure body " * 100) + "\n\n"
        "## STANDALONE PROFIT AND LOSS ACCOUNT\n\n"
        + ("pnl body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    if "auditor_report" in idx:
        matched = idx["auditor_report"].get("matched_heading", "").lower()
        assert "annexure" not in matched, (
            f"Quoted-letter Annexure must not be picked as auditor_report start; "
            f"got matched_heading={matched!r}"
        )


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
# Wave 4-5 P2: chairman_letter / mdna / corporate_governance heading variants
# ---------------------------------------------------------------------------


def test_mdna_matches_html_entity_ampersand():
    """ICICIBANK / VEDL FY25 layout: Docling emits MD&A as the literal HTML
    entity 'MANAGEMENT DISCUSSION &amp; ANALYSIS' (uppercase, ampersand
    encoded). The bare-`&` regex didn't match — must normalize entities.
    """
    md = (
        "## MANAGEMENT DISCUSSION &amp; ANALYSIS\n\n"
        "## Industry Overview\n\n"
        + ("industry body " * 200) + "\n\n"
        "## Operating Performance\n\n"
        + ("ops body " * 100) + "\n\n"
        "## Outlook\n\n"
        + ("outlook body " * 50) + "\n\n"
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor " * 100) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "mdna" in idx, "MD&A with &amp; entity must match"
    assert idx["mdna"]["size_chars"] > 2_000


def test_chairman_letter_matches_message_from_chairman():
    """ICICIBANK FY25 / DRREDDY FY25 / many integrated-report ARs use
    'MESSAGE FROM THE CHAIRMAN' rather than 'Chairman's Message'. The new
    'message from the chairman' alias must catch these.
    """
    md = (
        "## MESSAGE FROM THE CHAIRMAN\n\n"
        "Dear Shareholders,\n\n"
        + ("Year under review chairman prose " * 200) + "\n\n"
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor " * 100) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "chairman_letter" in idx
    assert idx["chairman_letter"]["size_chars"] > 2_000


def test_chairman_letter_matches_chairman_speech():
    """VEDL FY25 layout: 'Chairman's Speech' rather than 'Chairman's Letter'."""
    md = (
        "## Chairman's Speech\n\n"
        "Dear Stakeholders,\n\n"
        + ("speech body line " * 200) + "\n\n"
        "## CEO Speak\n\n"
        + ("ceo body " * 50) + "\n\n"
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor " * 100) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "chairman_letter" in idx
    assert idx["chairman_letter"]["matched_heading"] == "Chairman's Speech"
    assert "ceo_letter" in idx


def test_chairman_letter_matches_message_from_founders():
    """POLICYBZR FY25 / startup integrated-reports use 'Message from Founders'
    rather than a chairman letter. Treat as the canonical opener.
    """
    md = (
        "## Message from Founders\n\n"
        "Dear Shareholders,\n\n"
        + ("founder prose " * 300) + "\n\n"
        "## Message from CFO\n\n"
        + ("cfo prose " * 50) + "\n\n"
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor " * 100) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "chairman_letter" in idx
    assert idx["chairman_letter"]["matched_heading"] == "Message from Founders"
    assert idx["chairman_letter"]["size_chars"] > 2_000
    text = slice_section(md, idx, "chairman_letter")
    # Must end at "Message from CFO" (a different letter type), not run into
    # the auditor report.
    assert "cfo prose" not in text
    assert "auditor" not in text


def test_chairman_letter_matches_chairman_and_md_message():
    """SUNPHARMA FY25: 'Chairman and Managing Director's Message' — joint
    title where the trailing possessive belongs to 'Director's', not
    'Chairman's'. The simple 'chairman'?s?\\s+message' alias misses it.
    """
    md = (
        "## Chairman and Managing Director's Message\n\n"
        "Dear Stakeholders,\n\n"
        + ("year under review " * 200) + "\n\n"
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor " * 100) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "chairman_letter" in idx
    assert idx["chairman_letter"]["size_chars"] > 2_000


def test_corporate_governance_matches_with_running_header_pollution():
    """ICICIBANK FY25 layout: the real CORPORATE GOVERNANCE heading is
    immediately followed by a page-running-header repeat ('BOARD'S REPORT'
    appears 48x as page header) which matches `directors_report` and would
    otherwise truncate the CG slice to 615 chars. Running-header detection
    skips these so the section extends to the real next canonical heading.
    """
    rh_count = 8  # ≥5 → triggers running-header detection
    rh_block = "## BOARD'S REPORT\n\n" + ("running-header line\n" * 5) + "\n"
    md = (
        "## CORPORATE GOVERNANCE\n\n"
        + ("Philosophy of Corporate Governance prose " * 50) + "\n\n"
        # Page-running-header repeat appears between CG body chunks.
        + (rh_block * rh_count)
        + "## Audit Committee\n\n"
        + ("audit committee body " * 100) + "\n\n"
        + "## Nomination and Remuneration Committee\n\n"
        + ("NRC body " * 50) + "\n\n"
        + "## Risk Management Committee\n\n"
        + ("RMC body " * 50) + "\n\n"
        + "## CONSOLIDATED BALANCE SHEET\n\n"
        + ("bs body " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "corporate_governance" in idx
    cg = idx["corporate_governance"]
    # Slice should span the full CG body — must NOT be truncated to a few
    # hundred chars by the running-header repeat.
    assert cg["size_chars"] > 5_000, (
        f"Expected CG body >5KB despite running-header pollution, "
        f"got {cg['size_chars']} chars"
    )
    text = slice_section(md, idx, "corporate_governance")
    assert "audit committee body" in text
    assert "NRC body" in text
    # Must end at the financial statements anchor.
    assert "bs body" not in text


def test_corporate_governance_excludes_esg_governance_report():
    """ICICIBANK FY25: only 'ENVIRONMENTAL, SOCIAL AND GOVERNANCE REPORT'
    matched the bare `governance\\s+report` alias because every real CG
    heading was running-header-truncated. ESG-governance must be excluded
    from CG candidates.
    """
    md = (
        "## CORPORATE GOVERNANCE REPORT\n\n"
        "## Audit Committee\n\n"
        + ("real CG body " * 100) + "\n\n"
        "## Nomination and Remuneration Committee\n\n"
        + ("NRC " * 50) + "\n\n"
        # ESG report — must NOT be picked as the CG section start.
        "## ENVIRONMENTAL, SOCIAL AND GOVERNANCE REPORT\n\n"
        + ("esg body " * 100) + "\n\n"
        "## CONSOLIDATED BALANCE SHEET\n\n"
        + ("bs " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "corporate_governance" in idx
    cg = idx["corporate_governance"]
    matched = cg.get("matched_heading", "").lower()
    assert "environmental" not in matched
    assert "esg" not in matched


def test_corporate_governance_excludes_nyse_compliance_certificate():
    """DRREDDY FY25 (ADR filing): contains both the SEBI 'CORPORATE
    GOVERNANCE REPORT' and a separate 'COMPLIANCE REPORT ON THE NYSE
    CORPORATE GOVERNANCE GUIDELINES'. The NYSE certificate must NOT be
    picked even though it contains audit-committee / NRC mentions in its
    body — those describe NYSE compliance, not the actual SEBI governance
    structure.
    """
    md = (
        "## CORPORATE GOVERNANCE REPORT\n\n"
        "## Audit Committee\n\n"
        + ("audit body " * 100) + "\n\n"
        "## Nomination and Remuneration Committee\n\n"
        + ("nrc " * 50) + "\n\n"
        "## CSR Committee\n\n"
        + ("csr " * 50) + "\n\n"
        # NYSE certificate appears later — must be excluded.
        "## COMPLIANCE REPORT ON THE NYSE CORPORATE GOVERNANCE GUIDELINES\n\n"
        + ("Audit Committee composition under NYSE compliance " * 100) + "\n\n"
        "## CONSOLIDATED BALANCE SHEET\n\n"
        + ("bs " * 30) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "corporate_governance" in idx
    matched = idx["corporate_governance"]["matched_heading"].lower()
    assert "nyse" not in matched
    assert "compliance report on" not in matched


def test_mdna_ends_at_next_canonical_section_not_first_subheading():
    """MD&A and CG sections contain dozens of L2 sub-headings of their own
    (Industry Overview, Outlook, Operating Performance for MD&A; Audit
    Committee / NRC / RMC for CG). Default same-or-higher-level end
    heuristic over-cuts to the first sub-heading. Smart end-detection ends
    at the next financial-statements anchor or a different canonical
    section instead.
    """
    md = (
        "## MANAGEMENT DISCUSSION AND ANALYSIS\n\n"
        # Many same-level (L2) sub-headings — these must NOT terminate the section.
        "## Industry Overview\n\n"
        + ("industry body " * 500) + "\n\n"
        "## Operating Performance\n\n"
        + ("ops body " * 500) + "\n\n"
        "## Outlook\n\n"
        + ("outlook body " * 200) + "\n\n"
        "## Risks and Concerns\n\n"
        + ("risks body " * 100) + "\n\n"
        "## Internal Control Systems\n\n"
        + ("ic body " * 100) + "\n\n"
        # Next canonical section.
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + ("auditor body " * 100) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "mdna" in idx
    assert idx["mdna"]["size_chars"] > 10_000, (
        "Expected MD&A to span all sub-headings, not stop at first L2 sibling"
    )
    text = slice_section(md, idx, "mdna")
    assert "industry body" in text
    assert "outlook body" in text
    assert "ic body" in text
    # Must end at the auditor section, not run into it.
    assert "auditor body" not in text


def test_chairman_letter_ends_at_message_from_cfo():
    """POLICYBZR FY25 layout: chairman / founders message is followed by a
    'Message from CFO' which is a different letter, then the rest of the
    integrated report. Without a letter-end anchor, the chairman section
    runs >100K into governance content. With the anchor, it ends cleanly.
    """
    md = (
        "## Message from Founders\n\n"
        "Dear Shareholders,\n\n"
        + ("founder body " * 200) + "\n\n"
        "## Message from CFO\n\n"
        + ("cfo body " * 50) + "\n\n"
        "## Performance Review\n\n"
        + ("perf body " * 200) + "\n\n"
        "## Board of Directors\n\n"
        + ("bod body " * 200) + "\n\n"
    )
    headings = _scan_headings(md)
    idx = build_ar_section_index(md, headings)
    assert "chairman_letter" in idx
    text = slice_section(md, idx, "chairman_letter")
    assert "founder body" in text
    # Must end at the CFO letter, not run into it.
    assert "cfo body" not in text
    assert "perf body" not in text


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
