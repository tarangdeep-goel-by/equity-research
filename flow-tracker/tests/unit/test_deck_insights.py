"""Unit tests for ResearchDataAPI.get_deck_insights.

Mirrors the structure of test_data_api_pagination.py::TestConcallInsightsTOC/Drill
so the deck pipeline gets the same coverage the concall pipeline has.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.research.deck_extractor import _find_deck_pdfs
from flowtracker.store import FlowStore


# --- Fixtures ----------------------------------------------------------------

def _write_decks(vault_root: Path, symbol: str, quarters: list[dict]) -> None:
    """Write a synthetic deck_extraction.json under a tmp vault."""
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "deck_extraction.json").write_text(
        json.dumps({
            "symbol": symbol,
            "quarters_analyzed": len(quarters),
            "extraction_date": "2026-04-17",
            "quarters": quarters,
        }),
        encoding="utf-8",
    )


@pytest.fixture
def vault_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def api(tmp_db: Path, populated_store: FlowStore, monkeypatch, vault_home: Path) -> ResearchDataAPI:
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


def _decks_with_topics() -> list[dict]:
    return [
        {
            "fy_quarter": "FY26-Q3",
            "period_ended": "2025-12-31",
            "extraction_status": "complete",
            "highlights": ["Revenue +10%", "EBITDA margin +180 bps"],
            "segment_performance": {
                "lifestyle_brands": {"revenue_cr": 1800, "growth_yoy_pct": 9, "margin_pct": 18.4},
            },
            "strategic_priorities": ["store_network_expansion", "digital_trade"],
            "outlook_and_guidance": "Expect FY26 growth in mid-teens",
            "new_initiatives": ["premiumization", "ecom ramp"],
            "charts_described": [
                {"slide_title": "Q3 Highlights", "what_it_shows": "revenue + margin bars", "key_takeaway": "margin expansion"},
            ],
            "slide_topics": ["highlights", "segmental", "outlook", "strategy"],
        },
        {
            "fy_quarter": "FY26-Q2",
            "period_ended": "2025-09-30",
            "extraction_status": "complete",
            "highlights": ["Revenue +7%"],
            "segment_performance": {"lifestyle_brands": {"revenue_cr": 1700, "growth_yoy_pct": 7}},
            "strategic_priorities": ["cost_discipline"],
            "outlook_and_guidance": "Cautious optimism",
            "new_initiatives": [],
            "charts_described": [],
            "slide_topics": ["highlights", "segmental", "cost"],
        },
    ]


def _decks_without_topics() -> list[dict]:
    """Pretends to be a pre-tagging extraction (no slide_topics field)."""
    qs = _decks_with_topics()
    for q in qs:
        q.pop("slide_topics", None)
    return qs


class TestFindDeckPDFs:
    def test_returns_paths_not_tuples_and_newest_first(self, vault_home):
        """Regression: _find_deck_pdfs used to return d[1] which tried to
        subscript a PosixPath — crashed with TypeError at runtime."""
        base = vault_home / "vault" / "stocks" / "TESTCO" / "filings"
        for fy_q in ("FY25-Q1", "FY25-Q2", "FY26-Q1"):
            d = base / fy_q
            d.mkdir(parents=True)
            (d / "investor_deck.pdf").write_bytes(b"fake")

        result = _find_deck_pdfs("TESTCO", quarters=4)
        assert len(result) == 3
        assert all(isinstance(p, Path) for p in result)
        assert result[0].parent.name == "FY26-Q1"
        assert result[-1].parent.name == "FY25-Q1"

    def test_truncates_to_requested_quarter_count(self, vault_home):
        base = vault_home / "vault" / "stocks" / "TESTCO" / "filings"
        for fy_q in ("FY25-Q1", "FY25-Q2", "FY25-Q3", "FY25-Q4", "FY26-Q1"):
            d = base / fy_q
            d.mkdir(parents=True)
            (d / "investor_deck.pdf").write_bytes(b"fake")

        result = _find_deck_pdfs("TESTCO", quarters=2)
        assert len(result) == 2
        assert [p.parent.name for p in result] == ["FY26-Q1", "FY25-Q4"]


# --- Error paths --------------------------------------------------------------

class TestDeckInsightsErrors:
    def test_no_extraction_returns_error_with_cli_hint(self, api, vault_home):
        result = api.get_deck_insights("NOSUCHSTOCK")
        assert "error" in result
        assert "extract-deck" in result.get("hint", "")

    def test_unknown_section_returns_valid_sections(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        result = api.get_deck_insights("TESTCO", section_filter="nonexistent")
        assert "error" in result
        assert "highlights" in result["valid_sections"]

    def test_unknown_quarter_lists_available(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        result = api.get_deck_insights("TESTCO", quarter="FY99-Q9")
        assert "error" in result
        assert "FY26-Q3" in result["available_quarters"]


# --- TOC mode -----------------------------------------------------------------

class TestDeckInsightsTOC:
    def test_toc_is_compact_and_lists_populated_sections(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        toc = api.get_deck_insights("TESTCO")
        size = len(json.dumps(toc))
        assert size < 4000, f"TOC should be <4KB, got {size}"
        assert "available_sections" in toc
        # Per-quarter payload should NOT leak into TOC.
        for q in toc["quarters"]:
            assert "highlights" not in q
            assert "sections_populated" in q

    def test_toc_includes_slide_topics_by_quarter_when_tagged(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        toc = api.get_deck_insights("TESTCO")
        assert "slide_topics_by_quarter" in toc
        assert "segmental" in toc["slide_topics_by_quarter"]["FY26-Q3"]

    def test_toc_omits_slide_topics_when_untagged(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_without_topics())
        toc = api.get_deck_insights("TESTCO")
        assert "slide_topics_by_quarter" not in toc

    def test_degraded_extraction_surfaces_warning(self, api, vault_home):
        qs = _decks_with_topics()
        qs[1]["extraction_status"] = "not_a_deck"
        _write_decks(vault_home / "vault", "TESTCO", qs)
        toc = api.get_deck_insights("TESTCO")
        assert "_extraction_quality_warning" in toc
        assert toc["_meta"]["extraction_status"] == "partial"
        assert "FY26-Q2" in toc["_meta"]["missing_periods"]


# --- Drill-down ---------------------------------------------------------------

class TestDeckInsightsDrill:
    def test_drill_returns_only_requested_section(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        drill = api.get_deck_insights("TESTCO", section_filter="segment_performance")
        assert drill["section"] == "segment_performance"
        assert len(drill["quarters"]) == 2
        for q in drill["quarters"]:
            allowed = {"fy_quarter", "period_ended", "segment_performance"}
            assert set(q.keys()) - allowed == set()

    def test_quarter_filter_narrows_to_single(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        result = api.get_deck_insights("TESTCO", quarter="FY26-Q3")
        assert len(result["quarters"]) == 1
        assert result["quarters"][0]["fy_quarter"] == "FY26-Q3"

    def test_slide_topics_filter_keeps_matching_quarters(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        # "strategy" tag only appears in FY26-Q3 in our fixture.
        drill = api.get_deck_insights("TESTCO", section_filter="strategic_priorities", slide_topics=["strategy"])
        assert drill["section"] == "strategic_priorities"
        assert len(drill["quarters"]) == 1
        assert drill["quarters"][0]["fy_quarter"] == "FY26-Q3"
        assert drill["slide_topics_requested"] == ["strategy"]

    def test_slide_topics_filter_fallback_when_untagged(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_without_topics())
        drill = api.get_deck_insights("TESTCO", section_filter="highlights", slide_topics=["outlook"])
        assert "_topic_filter_warning" in drill
        # Fallback returns ALL quarters, not filtered ones.
        assert len(drill["quarters"]) == 2

    def test_quarter_plus_section_combined(self, api, vault_home):
        _write_decks(vault_home / "vault", "TESTCO", _decks_with_topics())
        result = api.get_deck_insights("TESTCO", quarter="FY26-Q3", section_filter="outlook_and_guidance")
        assert len(result["quarters"]) == 1
        assert "mid-teens" in result["quarters"][0]["outlook_and_guidance"]
