"""Unit tests for deck_extractor.ensure_deck_data cache behavior + classifier.

Sibling to test_deck_insights.py (which exercises ResearchDataAPI.get_deck_insights).
This file targets the extractor pipeline directly — verifying that fully-cached
quarters short-circuit the expensive Claude/Docling path, plus the
``_classify_deck_pdf`` heuristic that gates whether a downloaded PDF is a real
investor deck or a Reg 30 cover letter masquerading as one.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def vault_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_deck_cache(vault_root: Path, symbol: str, quarters: list[str]) -> None:
    """Write a synthetic deck_extraction.json with N quarters all marked complete.

    `vault_root` is the directory that contains `stocks/` (e.g. ``~/vault``).
    """
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "quarters_analyzed": len(quarters),
        "extraction_date": "2026-04-17",
        "quarters": [
            {
                "fy_quarter": q,
                "extraction_status": "complete",
                "highlights": [f"{q} highlight"],
            }
            for q in quarters
        ],
    }
    (fdir / "deck_extraction.json").write_text(json.dumps(payload))


def _write_deck_pdfs(vault_root: Path, symbol: str, quarters: list[str]) -> None:
    """Lay down stub investor_deck.pdf files so _find_deck_pdfs returns them."""
    base = vault_root / "stocks" / symbol / "filings"
    for q in quarters:
        d = base / q
        d.mkdir(parents=True, exist_ok=True)
        (d / "investor_deck.pdf").write_bytes(b"fake pdf")


def _mock_pdfium(monkeypatch, pages: int, first3_text: str) -> None:
    """Install a fake ``pypdfium2`` module that yields ``pages`` pages and
    ``first3_text`` when sampling the first 3 pages.

    The real classifier imports ``pypdfium2`` lazily inside the function body,
    so sys.modules patching is sufficient — no need to reload the extractor
    module.
    """
    import sys

    # Build a per-page stub. Each call to doc[i].get_textpage().get_text_range()
    # returns a slice of first3_text such that the concatenation across the
    # first 3 pages matches first3_text exactly.
    chunks = [first3_text, "", ""] if pages >= 1 else []
    page_objs = []
    for i in range(pages):
        text = chunks[i] if i < len(chunks) else ""
        textpage = MagicMock()
        textpage.get_text_range.return_value = text
        page = MagicMock()
        page.get_textpage.return_value = textpage
        page_objs.append(page)

    doc = MagicMock()
    doc.__len__ = lambda self: pages
    doc.__getitem__ = lambda self, i: page_objs[i]
    doc.close = MagicMock()

    PdfDocument = MagicMock(return_value=doc)
    fake_module = MagicMock()
    fake_module.PdfDocument = PdfDocument

    monkeypatch.setitem(sys.modules, "pypdfium2", fake_module)


class TestClassifyDeckPdf:
    """Unit tests for ``_classify_deck_pdf`` — the deck/cover-letter heuristic.

    Anchored on the real failing case: NESTLEIND FY24-Q2 / FY24-Q3 / FY25-Q3
    are 1-page Reg 30 cover letters with ``investor_deck.pdf`` filenames; the
    extractor must mark them ``not_a_deck``. FY23-Q1 is a 38-page real deck
    that must classify as a real deck even though it contains "regulation 30"
    boilerplate somewhere in the first three pages.
    """

    def test_nestleind_one_page_cover_letter_rejected(self, tmp_path, monkeypatch):
        """1-page PDF — hard reject regardless of disclosure markers / md text."""
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        # Mirror real Nestlé FY24-Q3 numbers: 1 page, ~1.3KB text, Reg 30 phrase.
        first3 = (
            "Nestl India Limited\n"
            "Regulation 30 of SEBI (Listing Obligations and Disclosure "
            "Requirements) Regulations, 2015: Update on one-on-one institutional "
            "investor meet\n" * 6
        )
        _mock_pdfium(monkeypatch, pages=1, first3_text=first3)

        markdown = "## Nestl India Limited\n\nReg 30 boilerplate\n" * 20
        c = _classify_deck_pdf(pdf, markdown=markdown, headings_count=2)
        assert c.is_deck is False
        assert c.confidence == "high"
        assert c.pages == 1
        assert "1 page" in c.reason

    def test_short_pdf_with_disclosure_markers_rejected(self, tmp_path, monkeypatch):
        """3-9 pages + Reg 30 markers + sparse first-3 text → cover letter."""
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        first3 = (
            "Sub: Disclosure under Regulation 30 — analyst / investor meet "
            "dial-in details. Audio/Video recording available on website.\n"
        ) * 10  # ~1.3KB, well under 2500 chars
        _mock_pdfium(monkeypatch, pages=4, first3_text=first3)

        c = _classify_deck_pdf(pdf, markdown="## Foo\n\nbody " * 50, headings_count=1)
        assert c.is_deck is False
        assert c.has_disclosure_marker is True
        assert "Reg 30 cover-letter signature" in c.reason

    def test_real_deck_38_pages_accepted_high_confidence(self, tmp_path, monkeypatch):
        """38-page deck with rich markdown → accept, high confidence.

        Mirrors the NESTLEIND FY23-Q1 case: page count alone is enough to
        accept, and the Docling markdown is well-structured.
        """
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        # First 3 pages contain title slides + agenda — well over 3KB.
        first3 = (
            "Nestl India Limited\nQ1 2022 Investor Update\n"
            "Volume-led growth\nPurina Petcare\nGerber Toddler Nutrition\n"
        ) * 30
        _mock_pdfium(monkeypatch, pages=38, first3_text=first3)

        markdown = "## Slide 1\n## Slide 2\n## Slide 3\n" + ("body " * 1000)
        c = _classify_deck_pdf(pdf, markdown=markdown, headings_count=39)
        assert c.is_deck is True
        assert c.confidence == "high"
        assert c.pages == 38

    def test_image_heavy_deck_low_confidence_accept(self, tmp_path, monkeypatch):
        """30-page glossy deck with sparse Docling text — accept low-confidence.

        Real-world counter-example to the previous markdown-only rule:
        page count says deck, Docling produces little text because slides
        are image-heavy. Previously this would have been rejected — now
        it's accepted with confidence='low' and a data_quality_note.
        """
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        # Title slide only — first 3 pages are mostly images.
        first3 = "Investor Day 2026\nFY26 Results\nQ3 Business Update\n" * 5
        _mock_pdfium(monkeypatch, pages=32, first3_text=first3)

        # Sparse Docling markdown — under the 2KB / 3-headings threshold.
        c = _classify_deck_pdf(
            pdf, markdown="## Cover\n\nlight content", headings_count=1
        )
        assert c.is_deck is True
        assert c.confidence == "low"
        assert c.pages == 32

    def test_short_real_deck_with_rich_markdown_accepted(self, tmp_path, monkeypatch):
        """5-page real deck (rare) with rich markdown → accept low-confidence."""
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        first3 = "AGM 2026\nQuarterly Highlights\n" * 30  # ~1.5KB, no disclosure
        _mock_pdfium(monkeypatch, pages=5, first3_text=first3)

        markdown = "## Highlights\n## Segments\n## Outlook\n## Capex\n" + (
            "body " * 500
        )
        c = _classify_deck_pdf(pdf, markdown=markdown, headings_count=4)
        assert c.is_deck is True
        # 5 pages < _DECK_LOW_CONFIDENCE_PAGES(10), so confidence must be low
        assert c.confidence == "low"

    def test_no_pdfium_falls_back_to_markdown(self, tmp_path, monkeypatch):
        """If pypdfium2 import fails, classifier uses markdown heuristic only."""
        import sys

        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")

        # Force ImportError by inserting a sentinel that raises on attribute access.
        class _RaisingModule:
            def __getattr__(self, name):
                raise ImportError("pypdfium2 not available in this env")

        # Easier: remove from sys.modules and block re-import via builtins.__import__.
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pypdfium2":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        sys.modules.pop("pypdfium2", None)

        # Rich markdown → accept low-confidence.
        c1 = _classify_deck_pdf(
            pdf, markdown="## A\n## B\n## C\n" + ("x" * 5000), headings_count=5
        )
        assert c1.is_deck is True
        assert c1.confidence == "low"

        # Sparse markdown → reject.
        c2 = _classify_deck_pdf(pdf, markdown="## A\nshort", headings_count=1)
        assert c2.is_deck is False


class TestEnsureDeckDataCacheSkip:
    def test_ensure_deck_data_cached_returns_zero_new(self, vault_home, monkeypatch):
        import flowtracker.research.deck_extractor as deck_mod

        symbol = "TESTCO"
        quarters = ["FY26-Q3", "FY26-Q2"]

        # Module-level _VAULT_BASE was bound at import via Path.home() — repoint
        # it at the tmp vault so cache reads/writes land in the right place.
        vault_root = vault_home / "vault"
        monkeypatch.setattr(deck_mod, "_VAULT_BASE", vault_root / "stocks")

        _write_deck_pdfs(vault_root, symbol, quarters)
        _write_deck_cache(vault_root, symbol, quarters)

        # Any Claude call must blow up — point of the test is cache-skip.
        async def boom(*args, **kwargs):
            raise AssertionError("Claude called for cached quarter")

        monkeypatch.setattr(deck_mod, "_call_claude", boom)

        result = asyncio.run(deck_mod.ensure_deck_data(symbol, quarters=2))

        assert result is not None
        assert result["_new_quarters_extracted"] == 0
        assert result["quarters_analyzed"] == 2
