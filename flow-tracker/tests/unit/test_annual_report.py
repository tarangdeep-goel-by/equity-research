"""Unit tests for ResearchDataAPI.get_annual_report + ar_downloader.

Mirrors the shape of test_data_api_pagination.py and test_deck_insights.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.annual_report_extractor import (
    _atomic_write_json,
    _merge_chunk_payloads,
    _section_is_complete,
    _split_section_text,
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

        async def fake_extract_section(sec, slice_text, sym, fy, model, industry=None):
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

        async def fake_extract_section_v2(sec, slice_text, sym, fy, model, industry=None):
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


class TestEnsureAnnualReportDataCacheSkip:
    """Verify ensure_annual_report_data short-circuits when every requested year
    already has a complete cached JSON — Claude must NOT be invoked."""

    def test_ensure_annual_report_data_cached_returns_zero_new(
        self, vault_home, monkeypatch
    ):
        import asyncio

        import flowtracker.research.annual_report_extractor as ar_mod

        symbol = "TESTCO"
        # Point module-level _VAULT_BASE at the tmp vault (set at import time).
        tmp_vault_stocks = vault_home / "vault" / "stocks"
        monkeypatch.setattr(ar_mod, "_VAULT_BASE", tmp_vault_stocks)

        # Seed PDF (find_ar_pdfs uses Path.home() at call-time).
        pdf_path = tmp_vault_stocks / symbol / "filings" / "FY25" / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake pdf")

        # Seed cached AR JSON with extraction_status=complete.
        _write_ar_year(vault_home / "vault", symbol, "FY25")
        # Force the cached JSON status to "complete" (the helper writes "complete"
        # already, but be explicit so the test's intent is obvious).
        cached = vault_home / "vault" / "stocks" / symbol / "fundamentals" / "annual_report_FY25.json"
        data = json.loads(cached.read_text())
        assert data["extraction_status"] == "complete"

        # Seed cross-year file so _generate_cross_year_narrative isn't invoked.
        _write_cross_year(vault_home / "vault", symbol, ["FY25"])

        # Any Claude call must blow up loudly — cache path must skip extraction.
        async def boom(*args, **kwargs):
            raise AssertionError("Claude called for cached year")

        monkeypatch.setattr(ar_mod, "_call_claude", boom)

        result = asyncio.run(
            ar_mod.ensure_annual_report_data(
                symbol, years=1, industry="Banks - Private Sector",
            )
        )

        assert result is not None
        assert result["_new_years_extracted"] == 0
        assert "FY25" in result["years_analyzed"]


# --- Retry + chunking + _meta (post-eval v2 E14) ---------------------------


def _fake_md_with_canonical_sections(auditor_body: str = None, cg_body: str = None) -> str:
    """Build a small fake AR markdown with auditor + CG sections that the
    heading_toc recognizes as canonical. Bodies can be sized by the caller.
    """
    auditor_body = auditor_body or ("auditor body " * 100)
    cg_body = cg_body or ("cg body " * 100)
    return (
        "## INDEPENDENT AUDITOR'S REPORT\n\n"
        + auditor_body + "\n\n"
        "## CORPORATE GOVERNANCE REPORT\n\n"
        + cg_body + "\n\n"
    )


def _seed_fake_docling(monkeypatch, ar_mod, markdown: str) -> None:
    """Patch extract_to_markdown to return a fake Docling result."""
    from flowtracker.research.doc_extractor import ExtractionResult, _scan_headings
    headings = _scan_headings(markdown)
    monkeypatch.setattr(
        ar_mod, "extract_to_markdown",
        lambda pdf, cache_dir: ExtractionResult(
            markdown=markdown, headings=headings,
            backend="docling", degraded=False, elapsed_s=0.0, from_cache=True,
        ),
    )


class TestSectionRetry:
    """E14: per-section retry on transient SDK/connection failures."""

    @pytest.mark.asyncio
    async def test_section_retry_on_transient_failure(self, vault_home, monkeypatch):
        """Mock extractor raises ProcessError twice then succeeds — expect final
        success, section listed in _meta.retried_sections."""
        import flowtracker.research.annual_report_extractor as ar_mod
        from claude_agent_sdk import ProcessError

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        _seed_fake_docling(monkeypatch, ar_mod, _fake_md_with_canonical_sections())

        # No real sleep — retry delays become instant.
        async def no_sleep(_delay):
            return None
        monkeypatch.setattr(ar_mod.asyncio, "sleep", no_sleep)

        call_counts = {"auditor_report": 0, "corporate_governance": 0}

        async def flaky_extract_section(sec, slice_text, sym, fy, model, industry=None):
            call_counts[sec] = call_counts.get(sec, 0) + 1
            if sec == "auditor_report" and call_counts[sec] <= 2:
                raise ProcessError(f"simulated SDK exit 1 (attempt {call_counts[sec]})")
            return {"ok": True, "section": sec, "attempts": call_counts[sec]}

        monkeypatch.setattr(ar_mod, "_extract_section", flaky_extract_section)

        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report", "corporate_governance"),
        )

        # Auditor succeeded on attempt 3.
        assert call_counts["auditor_report"] == 3
        assert result["auditor_report"]["ok"] is True
        # CG succeeded first try — not retried.
        assert call_counts["corporate_governance"] == 1
        # Retry metadata.
        assert "auditor_report" in result["_meta"]["retried_sections"]
        assert "corporate_governance" not in result["_meta"]["retried_sections"]
        assert result["_meta"]["missing_sections"] == []
        assert result["_meta"]["degraded_quality"] is True  # any retry => degraded
        # Final status is complete because every section ultimately succeeded.
        assert result["extraction_status"] == "complete"

    @pytest.mark.asyncio
    async def test_section_gives_up_after_all_retries(self, vault_home, monkeypatch):
        """Extractor always raises — section lands in _meta.missing_sections."""
        import flowtracker.research.annual_report_extractor as ar_mod
        from claude_agent_sdk import CLIConnectionError

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        _seed_fake_docling(monkeypatch, ar_mod, _fake_md_with_canonical_sections())

        async def no_sleep(_delay):
            return None
        monkeypatch.setattr(ar_mod.asyncio, "sleep", no_sleep)

        call_counts = {"auditor_report": 0}

        async def always_fail(sec, slice_text, sym, fy, model, industry=None):
            if sec == "auditor_report":
                call_counts[sec] += 1
                raise CLIConnectionError("stream never opened")
            return {"ok": True, "section": sec}

        monkeypatch.setattr(ar_mod, "_extract_section", always_fail)

        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report", "corporate_governance"),
        )

        # 1 initial + 3 retries = 4 attempts.
        assert call_counts["auditor_report"] == 4
        assert "auditor_report" in result["_meta"]["missing_sections"]
        assert result["_meta"]["degraded_quality"] is True
        assert "extraction_error" in result["auditor_report"]
        # CG succeeded normally.
        assert result["corporate_governance"]["ok"] is True
        assert result["extraction_status"] == "partial"


class TestSectionChunking:
    """E14: large sections split before extraction, results merged."""

    def test_split_section_text_small_stays_one_chunk(self):
        """Sections at or under the chunk size stay as a single chunk."""
        text = "a" * 40_000
        chunks = _split_section_text(text, chunk_size=60_000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_section_text_respects_paragraph_boundaries(self):
        """200KB of paragraphs split into >=3 chunks on paragraph boundaries."""
        paragraphs = [("word " * 2000).strip() for _ in range(30)]  # ~10KB each => ~300KB
        text = "\n\n".join(paragraphs)
        chunks = _split_section_text(text, chunk_size=60_000)
        assert len(chunks) >= 3
        for chunk in chunks:
            assert len(chunk) <= 60_000

    def test_merge_chunk_payloads_concatenates_lists(self):
        """List-valued fields concatenate across chunks."""
        payloads = [
            {"top_risks": [{"risk": "A"}], "_chars_extracted_from": 100},
            {"top_risks": [{"risk": "B"}, {"risk": "C"}], "_chars_extracted_from": 200},
            {"top_risks": [{"risk": "D"}], "_chars_extracted_from": 50},
        ]
        merged = _merge_chunk_payloads(payloads)
        assert [r["risk"] for r in merged["top_risks"]] == ["A", "B", "C", "D"]
        # _chars_extracted_from sums across chunks.
        assert merged["_chars_extracted_from"] == 350

    def test_merge_chunk_payloads_scalars_take_latest_non_null(self):
        """Scalar fields: latest non-null wins; dicts shallow-merge."""
        payloads = [
            {"tone": "confident", "summary": "first"},
            {"tone": None, "summary": "second"},
            {"tone": "defensive"},
        ]
        merged = _merge_chunk_payloads(payloads)
        assert merged["tone"] == "defensive"
        assert merged["summary"] == "second"

    @pytest.mark.asyncio
    async def test_large_section_chunks_and_merges(self, vault_home, monkeypatch):
        """A 200KB section splits into 3+ chunks; results merged end-to-end."""
        import flowtracker.research.annual_report_extractor as ar_mod

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        # Build auditor body that totals ~200KB with paragraph breaks.
        big_paragraphs = [("audit-para-" + "x" * 2000) for _ in range(100)]  # ~200KB
        big_body = "\n\n".join(big_paragraphs)
        small_body = "cg body " * 100
        fake_md = (
            "## INDEPENDENT AUDITOR'S REPORT\n\n"
            + big_body + "\n\n"
            "## CORPORATE GOVERNANCE REPORT\n\n"
            + small_body + "\n\n"
        )
        _seed_fake_docling(monkeypatch, ar_mod, fake_md)

        call_log: list[tuple[str, int]] = []

        async def fake_extract_section(sec, slice_text, sym, fy, model, industry=None):
            call_log.append((sec, len(slice_text)))
            # Return a dict with a list field so we can verify concatenation.
            return {
                "section": sec,
                "key_audit_matters": [{"matter": f"{sec}-chunk-{len(call_log)}"}],
            }

        monkeypatch.setattr(ar_mod, "_extract_section", fake_extract_section)

        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report", "corporate_governance"),
        )

        # Auditor was chunked into 3+ calls, CG as a single call.
        auditor_calls = [c for c in call_log if c[0] == "auditor_report"]
        cg_calls = [c for c in call_log if c[0] == "corporate_governance"]
        assert len(auditor_calls) >= 3, f"expected >=3 chunks, got {len(auditor_calls)}"
        assert len(cg_calls) == 1
        # Each chunk respected the configured max.
        for _, size in auditor_calls:
            assert size <= ar_mod.CHUNK_SIZE_BYTES
        # Merged output has concatenated list entries (one per chunk).
        assert len(result["auditor_report"]["key_audit_matters"]) == len(auditor_calls)
        assert result["auditor_report"]["_chunked"] == len(auditor_calls)

    @pytest.mark.asyncio
    async def test_small_section_no_chunking(self, vault_home, monkeypatch):
        """A 40KB section stays a single extraction call."""
        import flowtracker.research.annual_report_extractor as ar_mod

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        # ~40KB auditor body (below CHUNK_TRIGGER_BYTES=80KB).
        small_body = ("audit-word " * 3500)  # ~38KB
        fake_md = (
            "## INDEPENDENT AUDITOR'S REPORT\n\n"
            + small_body + "\n\n"
        )
        _seed_fake_docling(monkeypatch, ar_mod, fake_md)

        call_log: list[tuple[str, int]] = []

        async def fake_extract_section(sec, slice_text, sym, fy, model, industry=None):
            call_log.append((sec, len(slice_text)))
            return {"section": sec, "ok": True}

        monkeypatch.setattr(ar_mod, "_extract_section", fake_extract_section)

        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report",),
        )

        assert len(call_log) == 1
        # Not chunked — no _chunked marker.
        assert "_chunked" not in result["auditor_report"]
        assert result["auditor_report"]["ok"] is True


class TestMetaFields:
    """E14: _meta.degraded_quality / missing_sections / retried_sections."""

    @pytest.mark.asyncio
    async def test_meta_fields_present_on_clean_run(self, vault_home, monkeypatch):
        """Clean run — every section extracts first try — degraded_quality=False,
        empty missing_sections and retried_sections."""
        import flowtracker.research.annual_report_extractor as ar_mod

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        _seed_fake_docling(monkeypatch, ar_mod, _fake_md_with_canonical_sections())

        async def clean_extract(sec, slice_text, sym, fy, model, industry=None):
            return {"ok": True, "section": sec}

        monkeypatch.setattr(ar_mod, "_extract_section", clean_extract)

        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report", "corporate_governance"),
        )

        assert "_meta" in result
        assert result["_meta"]["degraded_quality"] is False
        assert result["_meta"]["missing_sections"] == []
        assert result["_meta"]["retried_sections"] == []
        assert result["extraction_status"] == "complete"

    @pytest.mark.asyncio
    async def test_meta_does_not_break_section_iteration(self, vault_home, monkeypatch):
        """Backward compat: downstream code iterating over section names should
        still work — _meta is namespaced under a reserved prefix."""
        import flowtracker.research.annual_report_extractor as ar_mod

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        _seed_fake_docling(monkeypatch, ar_mod, _fake_md_with_canonical_sections())

        async def clean_extract(sec, slice_text, sym, fy, model, industry=None):
            return {"ok": True, "section": sec}

        monkeypatch.setattr(ar_mod, "_extract_section", clean_extract)

        sections = ("auditor_report", "corporate_governance")
        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6", sections=sections,
        )

        # Key convention: everything user-facing is a known section name or a
        # '_'-prefixed meta key (_meta, _elapsed_s, _heading_count, ...).
        for key in result.keys():
            # Meta keys start with underscore; real section payloads do not.
            if not key.startswith("_") and key in sections:
                assert isinstance(result[key], dict)
        # Iterate sections explicitly (the canonical downstream pattern).
        for sec in sections:
            assert result[sec]["ok"] is True


# --- SDK subprocess hygiene: crash retry + option isolation ---------------


class TestSubprocessCrashRetry:
    """SDK subprocess crashes (bare Exception("Command failed with exit code 1"))
    with no captured content should be wrapped in _ClaudeSubprocessCrash and
    retried by _extract_with_retry.
    """

    @pytest.mark.asyncio
    async def test_claude_subprocess_crash_triggers_retry(self, vault_home, monkeypatch):
        """Two consecutive bare-Exception crashes (via _call_claude) should be
        caught, wrapped, and retried — third attempt succeeds."""
        import flowtracker.research.annual_report_extractor as ar_mod

        symbol = "TESTCO"
        fy_label = "FY25"
        pdf_path = vault_home / "vault" / "stocks" / symbol / "filings" / fy_label / "annual_report.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake")

        _seed_fake_docling(monkeypatch, ar_mod, _fake_md_with_canonical_sections())

        # Instant retries.
        async def no_sleep(_delay):
            return None
        monkeypatch.setattr(ar_mod.asyncio, "sleep", no_sleep)

        call_counts = {"auditor_report": 0}

        async def flaky_call_claude(**kwargs):
            call_counts["auditor_report"] = call_counts.get("auditor_report", 0) + 1
            if call_counts["auditor_report"] <= 2:
                # Simulate what _call_claude does when SDK raises bare Exception
                # with no content buffered.
                raise ar_mod._ClaudeSubprocessCrash(
                    Exception("Command failed with exit code 1")
                )
            # Third attempt returns a real-looking JSON string.
            return '{"opinion": "unqualified", "key_audit_matters": []}'

        monkeypatch.setattr(ar_mod, "_call_claude", flaky_call_claude)

        result = await ar_mod._extract_single_ar(
            pdf_path, symbol, "claude-sonnet-4-6",
            sections=("auditor_report",),
        )

        assert call_counts["auditor_report"] == 3
        assert "extraction_error" not in result["auditor_report"]
        assert result["auditor_report"]["opinion"] == "unqualified"
        # Retried path is flagged on _meta.
        assert "auditor_report" in result["_meta"]["retried_sections"]
        assert result["_meta"]["degraded_quality"] is True


class TestExtractorOptionsIsolation:
    """Extractor subprocesses must set setting_sources=[""] (NOT []) and
    plugins=[] so they don't spawn with the user's hooks/plugins/skills
    loaded.

    [""] is the documented workaround for SDK #794 — an empty list is
    falsy in subprocess_cli._build_command's truthiness check, so the
    --setting-sources flag never reaches the CLI and it loads all default
    sources (including ~/.claude/settings.json hooks). [""] is truthy,
    emits --setting-sources "" which the CLI interprets as "no sources."
    https://github.com/anthropics/claude-agent-sdk-python/issues/794
    """

    def test_setting_sources_workaround_in_ar_options(self):
        import inspect
        import flowtracker.research.annual_report_extractor as ar_mod

        src = inspect.getsource(ar_mod._call_claude)
        assert 'setting_sources=[""]' in src, (
            "annual_report_extractor._call_claude must use setting_sources=[\"\"] "
            "(SDK #794 workaround — [] is silently ignored due to truthiness bug)"
        )
        assert "setting_sources=[]" not in src, (
            "setting_sources=[] is broken per SDK #794 — use [\"\"]"
        )
        assert "plugins=[]" in src

    def test_setting_sources_workaround_in_concall_options(self):
        import inspect
        from flowtracker.research import concall_extractor as ce_mod

        src = inspect.getsource(ce_mod._call_claude)
        assert 'setting_sources=[""]' in src
        assert "setting_sources=[]" not in src
        assert "plugins=[]" in src

    def test_setting_sources_workaround_in_deck_options(self):
        import inspect
        from flowtracker.research import deck_extractor as de_mod

        src = inspect.getsource(de_mod._call_claude)
        assert 'setting_sources=[""]' in src
        assert "setting_sources=[]" not in src
        assert "plugins=[]" in src


class TestThinkingDisabledForExtraction:
    """Every structured-JSON extraction call site must disable extended thinking.

    Without this guard, max_turns=1 + a ThinkingBlock response → CLI returns
    ResultMessage(subtype='error_max_turns', is_error=True) → subprocess exit
    code 1 → the SDK wraps it as "Fatal error in message reader: Command failed
    with exit code 1". Diagnosed 2026-04-23 when the HINDUNILVR/BHARTIARTL/
    SUNPHARMA re-extract failed on segmental + corporate_governance sections.
    """

    def test_ar_extractor_disables_thinking(self):
        import inspect
        from flowtracker.research import annual_report_extractor as ar_mod
        src = inspect.getsource(ar_mod._call_claude)
        assert '"type": "disabled"' in src
        assert "thinking=" in src

    def test_concall_extractor_disables_thinking(self):
        import inspect
        from flowtracker.research import concall_extractor as ce_mod
        src = inspect.getsource(ce_mod._call_claude)
        assert '"type": "disabled"' in src
        assert "thinking=" in src

    def test_deck_extractor_disables_thinking(self):
        import inspect
        from flowtracker.research import deck_extractor as de_mod
        src = inspect.getsource(de_mod._call_claude)
        assert '"type": "disabled"' in src
        assert "thinking=" in src


class TestNoDeadCmuxHooksEnv:
    """CMUX_CLAUDE_HOOKS_DISABLED=1 was dead code.

    SDK 0.1.5x uses a bundled CLI at
    .venv/.../claude_agent_sdk/_bundled/claude — it NEVER invokes the cmux
    wrapper at /Applications/cmux.app/.../claude, regardless of PATH order.
    So the env var was targeting a wrapper that wasn't in the subprocess
    spawn chain.

    The real user-hook-leak fix is setting_sources=[""] (see
    TestExtractorOptionsIsolation + SDK #794). These regression guards
    ensure the dead env doesn't creep back in via copy-paste.
    """

    def test_ar_extractor_has_no_dead_cmux_env(self):
        import inspect
        from flowtracker.research import annual_report_extractor as ar_mod
        assert "CMUX_CLAUDE_HOOKS_DISABLED" not in inspect.getsource(ar_mod._call_claude)

    def test_concall_extractor_has_no_dead_cmux_env(self):
        import inspect
        from flowtracker.research import concall_extractor as ce_mod
        assert "CMUX_CLAUDE_HOOKS_DISABLED" not in inspect.getsource(ce_mod._call_claude)

    def test_deck_extractor_has_no_dead_cmux_env(self):
        import inspect
        from flowtracker.research import deck_extractor as de_mod
        assert "CMUX_CLAUDE_HOOKS_DISABLED" not in inspect.getsource(de_mod._call_claude)

    def test_specialist_runner_has_no_dead_cmux_env(self):
        import inspect
        from flowtracker.research import agent as agent_mod
        assert "CMUX_CLAUDE_HOOKS_DISABLED" not in inspect.getsource(agent_mod._run_specialist)

    def test_verifier_has_no_dead_cmux_env(self):
        import inspect
        from flowtracker.research import verifier as vmod
        assert "CMUX_CLAUDE_HOOKS_DISABLED" not in inspect.getsource(vmod._run_verifier)


class TestSdkPostExitLogFilter:
    """SDK issue #800 — the bundled CLI occasionally exits non-zero during
    shutdown even after a successful ResultMessage landed. The SDK logs this
    at ERROR with a hard-coded stderr literal "Check stderr output for details".
    flowtracker.research.__init__ installs a log filter that demotes this
    specific log line to DEBUG so extractor runs don't look catastrophic.
    https://github.com/anthropics/claude-agent-sdk-python/issues/800
    """

    def test_filter_demotes_post_exit_error_to_debug(self):
        import logging
        import flowtracker.research  # ensures filter is installed  # noqa: F401

        logger = logging.getLogger("claude_agent_sdk._internal.query")
        record = logger.makeRecord(
            logger.name, logging.ERROR, __file__, 0,
            "Fatal error in message reader: %s", ("Command failed with exit code 1",),
            None,
        )
        # Filters run on logger.handle(); run each directly to verify outcome
        for f in logger.filters:
            f.filter(record)
        assert record.levelno == logging.DEBUG, (
            "Post-exit 'Fatal error in message reader' must be demoted to DEBUG "
            "by the filter in flowtracker.research.__init__"
        )

    def test_filter_leaves_other_errors_alone(self):
        import logging
        import flowtracker.research  # noqa: F401

        logger = logging.getLogger("claude_agent_sdk._internal.query")
        record = logger.makeRecord(
            logger.name, logging.ERROR, __file__, 0,
            "Some unrelated SDK error", (),
            None,
        )
        for f in logger.filters:
            f.filter(record)
        assert record.levelno == logging.ERROR, (
            "Filter must NOT demote unrelated SDK errors — only the known-"
            "spurious post-exit 'Fatal error in message reader' prefix"
        )


class TestSectionPromptSchemas:
    """Regression guards for the JSON schemas embedded in _SECTION_PROMPTS.

    get_adr_gdr in data_api.py reads
    notes_to_financials.share_capital.adr_gdr_details — so the prompt MUST
    instruct the extractor to surface that nested shape. Without it the
    ADR/GDR tool falls back to stubs even when the AR mentions depositary
    receipts (plan v3 item I).
    """

    def test_notes_to_financials_declares_adr_gdr_schema(self):
        from flowtracker.research.annual_report_extractor import _SECTION_PROMPTS

        prompt = _SECTION_PROMPTS["notes_to_financials"]
        # Schema field the get_adr_gdr consumer reads
        assert "share_capital" in prompt
        assert "adr_gdr_details" in prompt
        assert "outstanding_units_mn" in prompt
        assert "pct_of_total_equity" in prompt
        assert "listed_on" in prompt
        # Extraction hint keywords — what the LLM should look for in the AR
        assert "depositary" in prompt.lower()
        assert "ADR" in prompt
        assert "GDR" in prompt
