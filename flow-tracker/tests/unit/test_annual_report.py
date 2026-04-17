"""Unit tests for ResearchDataAPI.get_annual_report + ar_downloader.

Mirrors the shape of test_data_api_pagination.py and test_deck_insights.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.ar_downloader import _period_to_fy_label, find_ar_pdfs
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# --- Fixtures ----------------------------------------------------------------


def _write_ar_year(vault_root: Path, symbol: str, fy: str, payload_extra: dict | None = None) -> None:
    """Write a synthetic annual_report_FY??.json under a tmp vault."""
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    data = {
        "symbol": symbol,
        "fiscal_year": fy,
        "source_pdf": f".../{fy}/annual_report.pdf",
        "pages_chars": 1_800_000,
        "extraction_status": "complete",
        "extraction_date": "2026-04-17",
        "chairman_letter": {"summary": f"{fy} chairman summary", "tone": "confident"},
        "mdna": {"outlook": f"{fy} outlook narrative"},
        "risk_management": {"top_risks": [{"risk": f"{fy}-risk-1"}]},
        "auditor_report": {"opinion": "unqualified", "key_audit_matters": [{"matter": f"{fy} KAM"}]},
        "corporate_governance": {"board_size": 10, "independent_directors_pct": 60},
        "brsr": {"environmental": {"emissions": "scope 1: 100kt"}},
        "related_party": {"total_rpt_value_cr": 500},
        "segmental": {"segments": [{"name": "seg1", "revenue_cr": 1000}]},
        "notes_to_financials": {"status": "section_not_found_or_empty", "chars": 50},  # simulated empty
        "financial_statements": {"status": "section_not_found_or_empty", "chars": 0},  # not extracted
        "section_index": [{"name": "mdna", "size_chars": 30000, "size_class": "med"}],
    }
    if payload_extra:
        data.update(payload_extra)
    (fdir / f"annual_report_{fy}.json").write_text(json.dumps(data))


def _write_cross_year(vault_root: Path, symbol: str, years_analyzed: list[str]) -> None:
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "annual_report_cross_year.json").write_text(json.dumps({
        "symbol": symbol,
        "years_analyzed": years_analyzed,
        "extraction_date": "2026-04-17",
        "narrative": {
            "key_evolution_themes": ["Contingent liabilities rose ₹100→₹200Cr FY24→FY25"],
            "auditor_signals": {"kam_changes": "New KAM on revenue recognition in FY25"},
            "biggest_concern": "RPT value doubled",
        },
    }))


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


# --- ar_downloader utility -------------------------------------------------


class TestARDownloaderHelpers:
    def test_period_to_fy_label_parses_standard_formats(self):
        assert _period_to_fy_label("Financial Year 2025") == "FY25"
        assert _period_to_fy_label("Financial Year 2023") == "FY23"
        assert _period_to_fy_label("FY 2024") == "FY24"

    def test_period_to_fy_label_rejects_unparseable(self):
        assert _period_to_fy_label("Q3 FY26") is None
        assert _period_to_fy_label("") is None
        assert _period_to_fy_label("random text") is None

    def test_find_ar_pdfs_returns_newest_first(self, vault_home, tmp_path):
        base = vault_home / "vault" / "stocks" / "TESTCO" / "filings"
        for fy in ("FY23", "FY24", "FY25"):
            d = base / fy
            d.mkdir(parents=True)
            (d / "annual_report.pdf").write_bytes(b"fake")
        # Also a quarter dir that should be ignored
        (base / "FY26-Q3").mkdir(parents=True)
        (base / "FY26-Q3" / "investor_deck.pdf").write_bytes(b"fake")

        found = find_ar_pdfs("TESTCO", max_years=2)
        assert len(found) == 2
        assert found[0].parent.name == "FY25"
        assert found[1].parent.name == "FY24"


# --- get_annual_report ------------------------------------------------------


class TestARInsightsErrors:
    def test_no_extraction_returns_hint(self, api, vault_home):
        result = api.get_annual_report("NOSUCHSTOCK")
        assert "error" in result
        assert "extract-ar" in result.get("hint", "")

    def test_unknown_section_returns_valid_sections(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        result = api.get_annual_report("TESTCO", section="nonexistent")
        assert "error" in result
        assert "auditor_report" in result["valid_sections"]

    def test_unknown_year_lists_available(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        result = api.get_annual_report("TESTCO", year="FY99")
        assert "error" in result
        assert result["available_years"] == ["FY25"]


class TestARInsightsTOC:
    def test_toc_returns_compact_structure(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        _write_ar_year(vault_home / "vault", "TESTCO", "FY24")
        _write_cross_year(vault_home / "vault", "TESTCO", ["FY25", "FY24"])
        toc = api.get_annual_report("TESTCO")
        size = len(json.dumps(toc))
        assert size < 8000, f"TOC should be <8KB, got {size}"
        assert toc["years_on_file"] == ["FY25", "FY24"]  # newest first
        assert "available_sections" in toc
        # Per-year payload should NOT leak the full section content.
        for y in toc["years"]:
            assert "auditor_report" not in y  # only sections_populated summary

    def test_toc_populated_sections_exclude_not_found(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        toc = api.get_annual_report("TESTCO")
        populated = toc["years"][0]["sections_populated"]
        assert "mdna" in populated
        assert "auditor_report" in populated
        # notes_to_financials had status="section_not_found_or_empty" — should be excluded
        assert "notes_to_financials" not in populated
        assert "financial_statements" not in populated

    def test_toc_includes_cross_year_narrative_when_present(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        _write_ar_year(vault_home / "vault", "TESTCO", "FY24")
        _write_cross_year(vault_home / "vault", "TESTCO", ["FY25", "FY24"])
        toc = api.get_annual_report("TESTCO")
        assert "cross_year_narrative" in toc
        assert "key_evolution_themes" in toc["cross_year_narrative"]
        assert toc["cross_year_years"] == ["FY25", "FY24"]

    def test_toc_omits_cross_year_when_missing(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        toc = api.get_annual_report("TESTCO")
        assert "cross_year_narrative" not in toc


class TestARInsightsDrill:
    def test_section_drill_returns_slices_across_years(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        _write_ar_year(vault_home / "vault", "TESTCO", "FY24")
        result = api.get_annual_report("TESTCO", section="auditor_report")
        assert result["section"] == "auditor_report"
        assert len(result["years"]) == 2
        assert result["years"][0]["fiscal_year"] == "FY25"
        assert result["years"][0]["auditor_report"]["opinion"] == "unqualified"

    def test_year_filter_narrows_to_single(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        _write_ar_year(vault_home / "vault", "TESTCO", "FY24")
        toc = api.get_annual_report("TESTCO", year="FY25")
        assert toc["years_on_file"] == ["FY25"]
        assert len(toc["years"]) == 1

    def test_year_plus_section_combined(self, api, vault_home):
        _write_ar_year(vault_home / "vault", "TESTCO", "FY25")
        _write_ar_year(vault_home / "vault", "TESTCO", "FY24")
        result = api.get_annual_report("TESTCO", year="FY24", section="chairman_letter")
        assert len(result["years"]) == 1
        assert result["years"][0]["fiscal_year"] == "FY24"
        assert "FY24 chairman summary" in result["years"][0]["chairman_letter"]["summary"]
