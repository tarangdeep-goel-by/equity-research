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
    from flowtracker.research.deck_extractor import DECK_SCHEMA_VERSION

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
                "_schema_version": DECK_SCHEMA_VERSION,
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

        c = _classify_deck_pdf(pdf)
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

        c = _classify_deck_pdf(pdf)
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

        c = _classify_deck_pdf(pdf)
        assert c.is_deck is True
        assert c.confidence == "high"
        assert c.pages == 38

    def test_image_heavy_deck_accepted_high_confidence(self, tmp_path, monkeypatch):
        """32-page glossy deck with near-zero extractable text — accept HIGH.

        Page count alone is decisive now: extraction reads page images via the
        VLM, so sparse text layer is irrelevant. (Under the old markdown rule
        this was a low-confidence accept; post-VLM it's a confident deck.)
        """
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        # Title slide only — first 3 pages are mostly images.
        first3 = "Investor Day 2026\nFY26 Results\nQ3 Business Update\n" * 5
        _mock_pdfium(monkeypatch, pages=32, first3_text=first3)

        c = _classify_deck_pdf(pdf)
        assert c.is_deck is True
        assert c.confidence == "high"
        assert c.pages == 32

    def test_short_deck_no_disclosure_accepted_low(self, tmp_path, monkeypatch):
        """5-page PDF, no disclosure signature → accept low-confidence.

        The VLM reads images, so a short deck without the cover-letter signature
        is handed through (low-confidence) rather than rejected on text density.
        """
        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")
        first3 = "AGM 2026\nQuarterly Highlights\n" * 30  # no disclosure markers
        _mock_pdfium(monkeypatch, pages=5, first3_text=first3)

        c = _classify_deck_pdf(pdf)
        assert c.is_deck is True
        # 5 pages < _DECK_LOW_CONFIDENCE_PAGES(10), so confidence must be low
        assert c.confidence == "low"

    def test_no_pdfium_fails_open_accept(self, tmp_path, monkeypatch):
        """If pypdfium2 import fails, classifier fails open → accept low-confidence.

        Without Docling there's no secondary signal, so a transient pdfium
        failure must not lose a real deck — accept and let extraction proceed.
        """
        import builtins
        import sys

        from flowtracker.research.deck_extractor import _classify_deck_pdf

        pdf = tmp_path / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pypdfium2":
                raise ImportError("blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        sys.modules.pop("pypdfium2", None)

        c = _classify_deck_pdf(pdf)
        assert c.is_deck is True
        assert c.confidence == "low"
        assert "fail-open" in c.reason


class TestBuildImageMessage:
    """The streaming-mode user message must carry an Anthropic image block per page."""

    def test_text_then_image_blocks(self):
        from flowtracker.research.deck_extractor import _build_image_message

        msg = _build_image_message("describe these slides", ["b64A", "b64B"])
        assert msg["type"] == "user"
        content = msg["message"]["content"]
        assert content[0] == {"type": "text", "text": "describe these slides"}
        imgs = [c for c in content if c.get("type") == "image"]
        assert len(imgs) == 2
        assert imgs[0]["source"] == {
            "type": "base64", "media_type": "image/png", "data": "b64A",
        }
        assert imgs[1]["source"]["data"] == "b64B"


class TestMergeDeckChunks:
    """Per-chunk partial extractions union into one deck JSON."""

    def test_unions_dedupes_and_field_merges(self):
        from flowtracker.research.deck_extractor import _merge_deck_chunks

        chunks = [
            {
                "highlights": ["rev +10%", "margin +180bps"],
                "strategic_priorities": ["premiumization"],
                "segment_performance": {"foods": {"revenue_cr": 100, "margin_pct": None}},
                "key_metrics": {"net_debt_cr": {"unit": "Cr", "values": {"Q3FY26": 1200}}},
                "charts_described": [{"slide_title": "R&D Trend", "what_it_shows": "5yr"}],
                "new_initiatives": ["new plant"],
                "slide_topics": ["highlights", "segmental"],
                "outlook_and_guidance": "Targeting double-digit growth.",
                "extraction_status": "not_a_deck",  # must be ignored
            },
            {
                "highlights": ["rev +10%", "added 120 stores"],  # dup + new
                "strategic_priorities": ["premiumization", "digital"],
                "segment_performance": {
                    "foods": {"revenue_cr": None, "margin_pct": 22.5},
                    "beverages": {"revenue_cr": 50},
                },
                "key_metrics": {
                    "net_debt_cr": {"unit": "Cr", "values": {"Q2FY26": 1100}},
                    "nim_pct": {"unit": "%", "values": {"Q3FY26": 3.5}},
                },
                "charts_described": [
                    {"slide_title": "r&d trend"},  # dup by lowercased title
                    {"slide_title": "EBITDA bridge"},
                ],
                "new_initiatives": ["new plant"],  # dup
                "slide_topics": ["guidance"],
                "outlook_and_guidance": "Capex of 500cr planned.",
            },
        ]
        m = _merge_deck_chunks(chunks)
        assert m["highlights"] == ["rev +10%", "margin +180bps", "added 120 stores"]
        assert m["strategic_priorities"] == ["premiumization", "digital"]
        assert m["new_initiatives"] == ["new plant"]
        assert m["slide_topics"] == ["highlights", "segmental", "guidance"]
        # field-wise: foods revenue from chunk1, margin from chunk2
        assert m["segment_performance"]["foods"]["revenue_cr"] == 100
        assert m["segment_performance"]["foods"]["margin_pct"] == 22.5
        assert m["segment_performance"]["beverages"]["revenue_cr"] == 50
        # key_metrics: per-metric values maps union across chunks (newest-first wins)
        assert m["key_metrics"]["net_debt_cr"]["values"] == {"Q3FY26": 1200, "Q2FY26": 1100}
        assert m["key_metrics"]["net_debt_cr"]["unit"] == "Cr"
        assert m["key_metrics"]["nim_pct"]["values"] == {"Q3FY26": 3.5}
        # charts deduped by lowercased title, order preserved
        assert [c["slide_title"] for c in m["charts_described"]] == ["R&D Trend", "EBITDA bridge"]
        assert "double-digit growth" in m["outlook_and_guidance"]
        assert "Capex of 500cr" in m["outlook_and_guidance"]
        # per-chunk status never leaks into the merged dict
        assert "extraction_status" not in m


class TestExtractSingleDeckImages:
    """_extract_single_deck renders pages and extracts images-only.

    Default is a single VLM call over the whole deck; oversized decks fall back
    to chunked extraction + merge.
    """

    @staticmethod
    def _wire(deck_mod, monkeypatch, pages: int):
        monkeypatch.setattr(
            deck_mod, "_classify_deck_pdf",
            lambda *a, **k: deck_mod._DeckClassification(True, "high", "ok", pages, 100, False),
        )
        monkeypatch.setattr(deck_mod, "_render_deck_pages", lambda p, **k: [f"img{i}" for i in range(pages)])
        calls: list = []

        async def fake_call(system_prompt, user_prompt, model, max_budget=0.40,
                            max_turns=3, output_format=None, images=None):
            calls.append(images)
            idx = len(calls)
            return json.dumps({
                "highlights": [f"h{idx}"],
                "charts_described": [{"slide_title": f"c{idx}"}],
                "key_metrics": {f"m{idx}_cr": idx * 100},
                "segment_performance": {},
                "extraction_status": "complete",
            })

        monkeypatch.setattr(deck_mod, "_call_claude", fake_call)
        return calls

    def test_single_call_by_default(self, tmp_path, monkeypatch):
        import flowtracker.research.deck_extractor as deck_mod

        qdir = tmp_path / "FY25-Q1"; qdir.mkdir()
        pdf = qdir / "investor_deck.pdf"; pdf.write_bytes(b"%PDF-stub")
        calls = self._wire(deck_mod, monkeypatch, pages=20)

        result = asyncio.run(deck_mod._extract_single_deck(pdf, "ZYDUSLIFE", "claude-sonnet-4-6"))

        # 20 <= SINGLE_CALL_MAX_PAGES -> one call with ALL 20 images
        assert len(calls) == 1
        assert calls[0] == [f"img{i}" for i in range(20)]
        assert result["_extraction_mode"] == "images"
        assert result["_pages_rendered"] == 20
        assert result["_chunks"] == 1
        assert result["extraction_status"] == "complete"
        assert result["fy_quarter"] == "FY25-Q1"
        assert result["highlights"] == ["h1"]
        assert result["key_metrics"] == {"m1_cr": 100}

    def test_chunked_fallback_for_large_deck(self, tmp_path, monkeypatch):
        import flowtracker.research.deck_extractor as deck_mod

        qdir = tmp_path / "FY25-Q1"; qdir.mkdir()
        pdf = qdir / "investor_deck.pdf"; pdf.write_bytes(b"%PDF-stub")
        calls = self._wire(deck_mod, monkeypatch, pages=20)
        # Force the chunked path: cap single-call at 8, chunk size 8.
        monkeypatch.setattr(deck_mod, "SINGLE_CALL_MAX_PAGES", 8)
        monkeypatch.setattr(deck_mod, "DECK_CHUNK_SIZE", 8)

        result = asyncio.run(deck_mod._extract_single_deck(pdf, "ZYDUSLIFE", "claude-sonnet-4-6"))

        # 20 pages / chunk 8 -> 3 chunks, each handed its slice
        assert len(calls) == 3
        assert calls[0] == [f"img{i}" for i in range(8)]
        assert calls[2] == [f"img{i}" for i in range(16, 20)]
        assert result["_chunks"] == 3
        assert result["highlights"] == ["h1", "h2", "h3"]
        assert {c["slide_title"] for c in result["charts_described"]} == {"c1", "c2", "c3"}
        assert result["key_metrics"] == {"m1_cr": 100, "m2_cr": 200, "m3_cr": 300}

    def test_rejected_deck_skips_render_and_claude(self, tmp_path, monkeypatch):
        import flowtracker.research.deck_extractor as deck_mod

        qdir = tmp_path / "FY25-Q1"
        qdir.mkdir()
        pdf = qdir / "investor_deck.pdf"
        pdf.write_bytes(b"%PDF-stub")

        monkeypatch.setattr(
            deck_mod, "_classify_deck_pdf",
            lambda *a, **k: deck_mod._DeckClassification(False, "high", "only 1 page", 1, 0, False),
        )

        def boom_render(*a, **k):
            raise AssertionError("render called for rejected deck")

        async def boom_call(*a, **k):
            raise AssertionError("claude called for rejected deck")

        monkeypatch.setattr(deck_mod, "_render_deck_pages", boom_render)
        monkeypatch.setattr(deck_mod, "_call_claude", boom_call)

        result = asyncio.run(deck_mod._extract_single_deck(pdf, "ZYDUSLIFE", "claude-sonnet-4-6"))
        assert result["extraction_status"] == "not_a_deck"


class TestEnsureDeckPdfsFromScreener:
    """JIT download from Screener concall_ppt URLs — runs as part of Phase 0b.

    Mandated as a prerequisite to extraction so every research/eval/autoeval
    self-heals deck coverage on first run for any new stock.
    """

    def test_no_db_no_error(self, vault_home, monkeypatch):
        """FlowStore unavailable → fail-soft return 0; pipeline must not break."""
        import flowtracker.research.deck_extractor as deck_mod

        # Force FlowStore() to blow up — simulate DB unreachable
        class BrokenStore:
            def __enter__(self): raise RuntimeError("db down")
            def __exit__(self, *a): pass
        monkeypatch.setattr("flowtracker.store.FlowStore", lambda *a, **kw: BrokenStore())

        assert deck_mod.ensure_deck_pdfs_from_screener("TESTCO") == 0

    def test_filters_to_fy25_and_above(self, vault_home, monkeypatch):
        """Periods like 'May 2024' (announces FY24-Q4 results) must be filtered out.
        Only FY25+ result-quarters should pass the gate to download.
        """
        import flowtracker.research.deck_extractor as deck_mod
        vault_root = vault_home / "vault"
        monkeypatch.setattr(deck_mod, "_VAULT_BASE", vault_root / "stocks")

        class FakeStore:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): pass
            _conn = MagicMock()
        fake_store = FakeStore()
        # Mix of FY24 (Apr-May 2024 announces Q4 FY24) and FY25 (Aug 2024 announces Q1 FY25)
        fake_store._conn.execute.return_value.fetchall.return_value = [
            ("May 2024", "https://example.com/fy24q4.pdf"),     # FY24 — skip
            ("Aug 2024", "https://example.com/fy25q1.pdf"),     # FY25-Q1 — keep
            ("Oct 2025", "https://example.com/fy26q2.pdf"),     # FY26-Q2 — keep
        ]
        monkeypatch.setattr("flowtracker.store.FlowStore", lambda *a, **kw: fake_store)

        downloads: list[str] = []
        def fake_download(url, dest):
            downloads.append(url)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fake-pdf")
            return True
        monkeypatch.setattr(
            "flowtracker.research.concall_extractor._download_transcript_from_url",
            fake_download,
        )
        from flowtracker.research.deck_extractor import _DeckClassification
        monkeypatch.setattr(
            deck_mod, "_classify_deck_pdf",
            lambda p: _DeckClassification(True, "high", "test", 30, 5000, False),
        )

        n = deck_mod.ensure_deck_pdfs_from_screener("TESTCO")
        assert n == 2  # FY25-Q1 + FY26-Q2; NOT the FY24-Q4 one
        assert "fy24q4.pdf" not in " ".join(downloads)
        assert any("fy25q1" in u for u in downloads)
        assert any("fy26q2" in u for u in downloads)

    def test_skips_existing_real_deck(self, vault_home, monkeypatch):
        """If a quarter already has a real deck on disk, don't re-download."""
        import flowtracker.research.deck_extractor as deck_mod
        vault_root = vault_home / "vault"
        monkeypatch.setattr(deck_mod, "_VAULT_BASE", vault_root / "stocks")

        # Pre-stage a real deck at FY26-Q2
        existing = vault_root / "stocks" / "TESTCO" / "filings" / "FY26-Q2" / "investor_deck.pdf"
        existing.parent.mkdir(parents=True, exist_ok=True)
        existing.write_bytes(b"already-here")

        class FakeStore:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): pass
            _conn = MagicMock()
        fake_store = FakeStore()
        fake_store._conn.execute.return_value.fetchall.return_value = [
            ("Oct 2025", "https://example.com/fy26q2.pdf"),
        ]
        monkeypatch.setattr("flowtracker.store.FlowStore", lambda *a, **kw: fake_store)

        # _classify_deck_pdf treats the pre-existing one as a real deck — skip download
        from flowtracker.research.deck_extractor import _DeckClassification
        monkeypatch.setattr(
            deck_mod, "_classify_deck_pdf",
            lambda p: _DeckClassification(True, "high", "test", 30, 5000, False),
        )
        called = []
        monkeypatch.setattr(
            "flowtracker.research.concall_extractor._download_transcript_from_url",
            lambda url, dest: (called.append(url) or False),
        )

        n = deck_mod.ensure_deck_pdfs_from_screener("TESTCO")
        assert n == 0
        assert called == []  # no download attempted


class TestEnsureDeckDataCallsJit:
    """Regression: ensure_deck_data must call the JIT downloader first (Phase 0b
    prereq). Without this wire-up the data layer wouldn't self-heal."""

    def test_ensure_deck_data_calls_screener_pull(self, vault_home, monkeypatch):
        import flowtracker.research.deck_extractor as deck_mod
        vault_root = vault_home / "vault"
        monkeypatch.setattr(deck_mod, "_VAULT_BASE", vault_root / "stocks")

        called_with: dict = {}
        def fake_jit(symbol, max_quarters=6):
            called_with["symbol"] = symbol
            called_with["max_quarters"] = max_quarters
            return 0
        monkeypatch.setattr(deck_mod, "ensure_deck_pdfs_from_screener", fake_jit)

        # No PDFs on disk → ensure_deck_data short-circuits to None,
        # but the JIT call must have happened first.
        asyncio.run(deck_mod.ensure_deck_data("TESTCO", quarters=4))

        assert called_with["symbol"] == "TESTCO"
        # max_quarters bumped to DECK_MANDATED_QUARTERS (6) even when quarters=4
        assert called_with["max_quarters"] == deck_mod.DECK_MANDATED_QUARTERS


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

    def test_stale_schema_version_triggers_reextraction(self, vault_home, monkeypatch):
        """A cached 'complete' quarter from an older schema version must be
        re-extracted, not served stale — the cache is permanent only while the
        schema version matches."""
        import flowtracker.research.deck_extractor as deck_mod

        symbol = "TESTCO"
        vault_root = vault_home / "vault"
        monkeypatch.setattr(deck_mod, "_VAULT_BASE", vault_root / "stocks")
        _write_deck_pdfs(vault_root, symbol, ["FY26-Q3"])

        # Cache says complete but stamped with an OLD schema version.
        fdir = vault_root / "stocks" / symbol / "fundamentals"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "deck_extraction.json").write_text(json.dumps({
            "symbol": symbol, "quarters_analyzed": 1, "extraction_date": "2026-04-17",
            "quarters": [{"fy_quarter": "FY26-Q3", "extraction_status": "complete",
                          "_schema_version": deck_mod.DECK_SCHEMA_VERSION - 1,
                          "key_metrics": {"nim_q3fy26_pct": 3.5}}],  # old flat shape
        }))

        calls: list = []

        async def fake_extract(pdf, sym, model, industry=None):
            calls.append(pdf.parent.name)
            return {"fy_quarter": pdf.parent.name, "extraction_status": "complete",
                    "_schema_version": deck_mod.DECK_SCHEMA_VERSION,
                    "key_metrics": {"nim_pct": {"unit": "%", "values": {"Q3FY26": 3.5}}}}

        monkeypatch.setattr(deck_mod, "_extract_single_deck", fake_extract)

        result = asyncio.run(deck_mod.ensure_deck_data(symbol, quarters=1))
        assert calls == ["FY26-Q3"], "stale-version quarter should be re-extracted"
        assert result["_new_quarters_extracted"] == 1
