"""Unit tests for ResearchDataAPI.get_annual_report + ar_downloader.

Mirrors the shape of test_data_api_pagination.py and test_deck_insights.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.annual_report_extractor import (
    _atomic_write_json,
    _section_is_complete,
)
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


# --- Resilience helpers (introduced in fix/ar-per-section-resilience) --------


class TestSectionCompleteCheck:
    def test_none_is_not_complete(self):
        assert _section_is_complete(None) is False

    def test_non_dict_is_not_complete(self):
        assert _section_is_complete("string") is False
        assert _section_is_complete(["list"]) is False

    def test_dict_without_error_is_complete(self):
        assert _section_is_complete({"opinion": "unqualified"}) is True

    def test_dict_with_extraction_error_is_not_complete(self):
        assert _section_is_complete({"extraction_error": "timeout"}) is False

    def test_section_not_found_or_empty_is_complete(self):
        """Stable 'nothing here' result — don't retry it."""
        assert _section_is_complete({"status": "section_not_found_or_empty", "chars": 0}) is True


class TestAtomicWriteJson:
    def test_writes_via_tmp_and_rename(self, tmp_path):
        target = tmp_path / "nested" / "file.json"
        _atomic_write_json(target, {"k": "v"})
        assert target.exists()
        assert json.loads(target.read_text())["k"] == "v"
        # No leftover .tmp file.
        assert not target.with_suffix(".json.tmp").exists()

    def test_overwrites_existing_atomically(self, tmp_path):
        target = tmp_path / "file.json"
        target.write_text(json.dumps({"old": True}))
        _atomic_write_json(target, {"new": True})
        assert json.loads(target.read_text()) == {"new": True}


class TestSingleARResilience:
    """Drive _extract_single_ar with a mocked section extractor + extract_to_markdown
    to verify: section crash doesn't abort others, JSON persists per section,
    re-runs skip already-complete sections and retry errored ones."""

    @pytest.mark.asyncio
    async def test_crashed_section_doesnt_wipe_others_and_rerun_retries(
        self, vault_home, monkeypatch
    ):
        import flowtracker.research.annual_report_extractor as ar_mod
        from flowtracker.research.doc_extractor import ExtractionResult

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake pdf bytes")

        # Mock Docling — return a fake markdown with two canonical headings.
        fake_md = (
            "## INDEPENDENT AUDITOR'S REPORT\n\n"
            + ("auditor body " * 100) + "\n\n"
            "## CORPORATE GOVERNANCE REPORT\n\n"
            + ("cg body " * 100) + "\n\n"
            "## RISK MANAGEMENT\n\n"
            + ("risk body " * 100) + "\n\n"
        )
        from flowtracker.research.doc_extractor import _scan_headings
        fake_headings = _scan_headings(fake_md)
        monkeypatch.setattr(
            ar_mod, "extract_to_markdown",
            lambda pdf, cache_dir: ExtractionResult(
                markdown=fake_md, headings=fake_headings,
                backend="docling", degraded=False, elapsed_s=0.0, from_cache=True,
            ),
        )

        # First run — auditor succeeds, corporate_governance crashes, risk succeeds.
        call_log: list[str] = []

        async def fake_extract_section(sec, slice_text, sym, fy, model):
            call_log.append(f"run1:{sec}")
            if sec == "corporate_governance":
                raise RuntimeError("simulated SDK subprocess crash")
            return {"ok": True, "section": sec, "first_run": True}

        monkeypatch.setattr(ar_mod, "_extract_section", fake_extract_section)

        result1 = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report", "corporate_governance", "risk_management"),
        )

        # First run partial — auditor + risk done, cg errored, JSON persisted.
        assert result1["extraction_status"] == "partial"
        assert result1["auditor_report"]["ok"] is True
        assert "extraction_error" in result1["corporate_governance"]
        assert result1["risk_management"]["ok"] is True
        assert "corporate_governance" in result1["extraction_errors"]

        out_path = vault_home / "vault" / "stocks" / symbol / "fundamentals" / f"annual_report_{fy_label}.json"
        assert out_path.exists()
        on_disk = json.loads(out_path.read_text())
        assert on_disk["extraction_status"] == "partial"

        # Second run — patch so all sections succeed. Already-complete sections
        # should be skipped; only corporate_governance should re-run.
        call_log.clear()

        async def fake_extract_section_v2(sec, slice_text, sym, fy, model):
            call_log.append(f"run2:{sec}")
            return {"ok": True, "section": sec, "first_run": False}

        monkeypatch.setattr(ar_mod, "_extract_section", fake_extract_section_v2)

        result2 = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report", "corporate_governance", "risk_management"),
        )

        # Only the errored section should have re-run.
        assert call_log == ["run2:corporate_governance"]
        # Now fully complete.
        assert result2["extraction_status"] == "complete"
        # auditor_report + risk_management preserved from run1 (first_run=True).
        assert result2["auditor_report"]["first_run"] is True
        assert result2["risk_management"]["first_run"] is True
        # corporate_governance re-extracted (first_run=False).
        assert result2["corporate_governance"]["first_run"] is False
        # No error map when all sections succeed.
        assert "extraction_errors" not in result2
