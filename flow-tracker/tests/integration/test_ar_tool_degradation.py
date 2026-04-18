"""Integration tests for ResearchDataAPI.get_annual_report degradation metadata.

Pins down the contract added by task #5 of the AR/deck integration plan:
- `_meta` is always present on success responses (TOC + drill).
- `_extraction_quality_warning` is emitted ONLY when degraded.
- Section-level failures (>3 sections with section_not_found_or_empty /
  extraction_error) push an otherwise "complete" file into "partial".
- Error responses (no vault, year miss) carry no `_meta`.

Mirrors the patterns in tests/unit/test_annual_report.py and
tests/unit/test_deck_insights.py: tmp HOME redirect via monkeypatch.setenv,
synthetic AR JSONs written under {HOME}/vault/stocks/{SYMBOL}/fundamentals/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# --- Fixtures ----------------------------------------------------------------


def _ar_payload(symbol: str, fy: str, *, status: str = "complete",
                fail_extra_sections: int = 0) -> dict:
    """Build a synthetic AR JSON payload.

    Default: status=complete with real content in 8 sections,
    notes_to_financials + financial_statements marked
    section_not_found_or_empty (matches TestARInsightsTOC fixture).

    fail_extra_sections: mark this many additional sections as
    section_not_found_or_empty so the section-level failure count crosses the
    >3 threshold (used for test_section_level_failures_also_degrade).
    """
    data = {
        "symbol": symbol,
        "fiscal_year": fy,
        "source_pdf": f".../{fy}/annual_report.pdf",
        "pages_chars": 1_800_000,
        "extraction_status": status,
        "extraction_date": "2026-04-17",
        "chairman_letter": {"summary": f"{fy} chairman summary", "tone": "confident"},
        "mdna": {"outlook": f"{fy} outlook narrative"},
        "risk_management": {"top_risks": [{"risk": f"{fy}-risk-1"}]},
        "auditor_report": {"opinion": "unqualified", "key_audit_matters": [{"matter": f"{fy} KAM"}]},
        "corporate_governance": {"board_size": 10, "independent_directors_pct": 60},
        "brsr": {"environmental": {"emissions": "scope 1: 100kt"}},
        "related_party": {"total_rpt_value_cr": 500},
        "segmental": {"segments": [{"name": "seg1", "revenue_cr": 1000}]},
        "notes_to_financials": {"status": "section_not_found_or_empty", "chars": 50},
        "financial_statements": {"status": "section_not_found_or_empty", "chars": 0},
        "section_index": [{"name": "mdna", "size_chars": 30000, "size_class": "med"}],
    }
    # Bump section-level failure count (default 2) past the >3 threshold.
    # Order matches data_api._AR_SECTIONS so we replace deterministic ones.
    bumpable = ["brsr", "related_party", "segmental", "corporate_governance"]
    for i in range(min(fail_extra_sections, len(bumpable))):
        data[bumpable[i]] = {"status": "section_not_found_or_empty", "chars": 0}
    return data


def _write_ar(vault_root: Path, symbol: str, fy: str, **payload_kwargs) -> None:
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / f"annual_report_{fy}.json").write_text(
        json.dumps(_ar_payload(symbol, fy, **payload_kwargs)),
        encoding="utf-8",
    )


@pytest.fixture
def vault_home(tmp_path: Path, monkeypatch) -> Path:
    """Redirect Path.home() (via $HOME) to tmp_path so AR vault is isolated."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def api(tmp_db: Path, populated_store: FlowStore, monkeypatch, vault_home: Path):
    """ResearchDataAPI bound to a tmp DB and tmp vault HOME."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# --- Tests -------------------------------------------------------------------


class TestARFullExtractionMeta:
    """All years complete + section failures within threshold => meta=full,
    no _extraction_quality_warning emitted."""

    def test_get_annual_report_emits_meta_full_when_all_complete(self, api, vault_home):
        _write_ar(vault_home / "vault", "TESTCO", "FY25")
        _write_ar(vault_home / "vault", "TESTCO", "FY24")

        # TOC path (no year, no section).
        toc = api.get_annual_report("TESTCO")
        assert "_meta" in toc
        assert toc["_meta"]["extraction_status"] == "full"
        assert toc["_meta"]["degraded_quality"] is False
        assert toc["_meta"]["missing_periods"] == []
        assert "_extraction_quality_warning" not in toc

        # Drill path (section filter).
        drill = api.get_annual_report("TESTCO", section="chairman_letter")
        assert "_meta" in drill
        assert drill["_meta"]["extraction_status"] == "full"
        assert drill["_meta"]["degraded_quality"] is False
        assert drill["_meta"]["missing_periods"] == []
        assert "_extraction_quality_warning" not in drill


class TestARPartialExtractionMeta:
    """One year flagged extraction_status=partial in the JSON file =>
    meta=partial, missing_periods includes that FY, warning emitted."""

    def test_get_annual_report_emits_warning_when_partial(self, api, vault_home):
        _write_ar(vault_home / "vault", "TESTCO", "FY25")
        _write_ar(vault_home / "vault", "TESTCO", "FY24", status="partial")

        # TOC path.
        toc = api.get_annual_report("TESTCO")
        assert toc["_meta"]["extraction_status"] == "partial"
        assert toc["_meta"]["degraded_quality"] is True
        assert "FY24" in toc["_meta"]["missing_periods"]
        assert "FY25" not in toc["_meta"]["missing_periods"]
        warning = toc.get("_extraction_quality_warning")
        assert isinstance(warning, str) and warning.strip()
        assert "degraded" in warning.lower()

        # Drill path.
        drill = api.get_annual_report("TESTCO", section="auditor_report")
        assert drill["_meta"]["extraction_status"] == "partial"
        assert drill["_meta"]["degraded_quality"] is True
        assert "FY24" in drill["_meta"]["missing_periods"]
        warning = drill.get("_extraction_quality_warning")
        assert isinstance(warning, str) and warning.strip()
        assert "degraded" in warning.lower()


class TestARSectionLevelDegradation:
    """File-level status=complete BUT >3 sections empty/errored should still
    flip the year into degraded — verifies the section-level signal."""

    def test_get_annual_report_section_level_failures_also_degrade(self, api, vault_home):
        # Default _write_ar already has 2 failed sections; +2 more => 4 total
        # which trips the > 3 threshold inside get_annual_report.
        _write_ar(vault_home / "vault", "TESTCO", "FY25", fail_extra_sections=2)

        toc = api.get_annual_report("TESTCO")
        assert toc["_meta"]["degraded_quality"] is True
        assert toc["_meta"]["extraction_status"] == "partial"
        assert "FY25" in toc["_meta"]["missing_periods"]
        warning = toc.get("_extraction_quality_warning")
        assert isinstance(warning, str) and warning.strip()


class TestARErrorPathsClean:
    """Error responses must not carry _meta or _extraction_quality_warning."""

    def test_no_vault_returns_error_without_meta(self, api, vault_home):
        result = api.get_annual_report("NOSUCHSTOCK")
        assert "error" in result
        assert "hint" in result
        assert "_meta" not in result
        assert "_extraction_quality_warning" not in result

    def test_year_filter_miss_returns_error_without_meta(self, api, vault_home):
        _write_ar(vault_home / "vault", "TESTCO", "FY25")
        result = api.get_annual_report("TESTCO", year="FY99")
        assert "error" in result
        assert "available_years" in result
        assert "_meta" not in result
        assert "_extraction_quality_warning" not in result
