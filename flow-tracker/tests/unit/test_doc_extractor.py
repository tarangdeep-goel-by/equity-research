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
