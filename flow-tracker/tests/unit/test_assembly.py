"""Tests for pure functions in flowtracker/research/assembly.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.assembly import (
    ReportAssemblyError,
    _detect_scratchpad_leak,
    _find_section,
    _split_by_headers,
    _strip_preamble,
    assemble_final_report,
)
from flowtracker.research.briefing import AgentCost, BriefingEnvelope, ToolEvidence


# ---------------------------------------------------------------------------
# _strip_preamble — strips text before first # heading or ---
# ---------------------------------------------------------------------------
class TestStripPreamble:
    def test_strips_preamble_before_heading(self):
        report = "I'll start by analyzing...\nLet me pull the data.\n# Business Overview\nGreat company."
        result = _strip_preamble(report)
        assert result == "# Business Overview\nGreat company."

    def test_strips_preamble_before_dashes(self):
        report = "Thinking about this...\n---\n# Report\nContent here."
        result = _strip_preamble(report)
        assert result == "---\n# Report\nContent here."

    def test_no_preamble_heading_first(self):
        report = "# Title\nContent."
        result = _strip_preamble(report)
        assert result == "# Title\nContent."

    def test_no_heading_returns_as_is(self):
        report = "Just some plain text without any markdown headings."
        result = _strip_preamble(report)
        assert result == report

    def test_empty_string(self):
        assert _strip_preamble("") == ""

    def test_h2_heading(self):
        report = "Preamble stuff.\n## Section One\nContent."
        result = _strip_preamble(report)
        assert result == "## Section One\nContent."

    def test_preserves_content_after_heading(self):
        report = "Preamble.\n# Title\nParagraph 1.\n## Sub\nParagraph 2."
        result = _strip_preamble(report)
        assert result.startswith("# Title")
        assert "Paragraph 2." in result

    def test_dashes_in_first_line(self):
        report = "---\nFrontmatter"
        result = _strip_preamble(report)
        assert result == "---\nFrontmatter"

    def test_whitespace_before_heading(self):
        """Heading with leading spaces should still be detected (stripped comparison)."""
        report = "Preamble.\n  # Indented Heading\nContent."
        result = _strip_preamble(report)
        assert result == "  # Indented Heading\nContent."


# ---------------------------------------------------------------------------
# _split_by_headers — splits markdown on ## headers
# ---------------------------------------------------------------------------
class TestSplitByHeaders:
    def test_basic_split(self):
        text = "## Verdict\nBuy.\n## Summary\nGood company."
        sections = _split_by_headers(text)
        assert "Verdict" in sections
        assert "Summary" in sections
        assert "Buy." in sections["Verdict"]
        assert "Good company." in sections["Summary"]

    def test_preserves_header_line_in_content(self):
        text = "## Verdict\nBuy."
        sections = _split_by_headers(text)
        assert sections["Verdict"].startswith("## Verdict")

    def test_no_headers(self):
        text = "Just plain text with no headers at all."
        sections = _split_by_headers(text)
        assert sections == {}

    def test_empty_string(self):
        sections = _split_by_headers("")
        assert sections == {}

    def test_h1_not_split(self):
        """Only ## headers are split, not # headers."""
        text = "# Title\nIntro.\n## Section\nContent."
        sections = _split_by_headers(text)
        assert "Section" in sections
        # The # Title should not create its own section
        assert "Title" not in sections

    def test_multiple_sections(self):
        text = "## A\na content\n## B\nb content\n## C\nc content"
        sections = _split_by_headers(text)
        assert len(sections) == 3
        assert "a content" in sections["A"]
        assert "b content" in sections["B"]
        assert "c content" in sections["C"]

    def test_text_before_first_header_ignored(self):
        text = "Preamble text.\n## First\nContent."
        sections = _split_by_headers(text)
        assert len(sections) == 1
        assert "First" in sections

    def test_header_with_special_chars(self):
        text = "## Key Signals & Catalysts\nBig things ahead."
        sections = _split_by_headers(text)
        assert "Key Signals & Catalysts" in sections


# ---------------------------------------------------------------------------
# _find_section — case-insensitive keyword search in section headers
# ---------------------------------------------------------------------------
class TestFindSection:
    def test_exact_match(self):
        sections = {"Verdict": "## Verdict\nBuy.", "Summary": "## Summary\nOK."}
        result = _find_section(sections, "Verdict")
        assert result is not None
        assert "Buy." in result

    def test_case_insensitive(self):
        sections = {"Executive Summary": "## Executive Summary\nContent."}
        result = _find_section(sections, "executive summary")
        assert result is not None
        assert "Content." in result

    def test_partial_keyword(self):
        sections = {"Key Signals & Catalysts": "## Key Signals & Catalysts\nBig news."}
        result = _find_section(sections, "Catalysts")
        assert result is not None
        assert "Big news." in result

    def test_not_found(self):
        sections = {"Verdict": "content"}
        result = _find_section(sections, "NonExistent")
        assert result is None

    def test_empty_sections(self):
        assert _find_section({}, "anything") is None

    def test_first_match_wins(self):
        """If multiple headers contain the keyword, the first match is returned."""
        from collections import OrderedDict
        sections = OrderedDict([
            ("Big Question for Investors", "first"),
            ("Another Big Question", "second"),
        ])
        result = _find_section(sections, "Big Question")
        assert result == "first"


# ---------------------------------------------------------------------------
# _detect_scratchpad_leak — monologue guard for eval v2 §7 E17
# ---------------------------------------------------------------------------
def test_scratchpad_leak_raises_on_thinking_tag():
    # report body that starts with a <thinking> tag
    bad = "<thinking>Let me compute the blended FV...</thinking>\n\n# Valuation Report\n..."
    from flowtracker.research.assembly import _detect_scratchpad_leak
    assert _detect_scratchpad_leak(bad) is not None


def test_scratchpad_leak_raises_on_let_me_think_line():
    bad = "Let me think about what tools to call first.\n\n# Financials Report\n..."
    from flowtracker.research.assembly import _detect_scratchpad_leak
    assert _detect_scratchpad_leak(bad) is not None


def test_clean_report_passes():
    good = "# Valuation Report\n\n## Summary\n\nFair value ₹1,200 vs current ₹1,100 → 9% upside.\n"
    from flowtracker.research.assembly import _detect_scratchpad_leak
    assert _detect_scratchpad_leak(good) is None


def test_detect_ignores_leak_past_head_bytes():
    """Markers after head_bytes should not trigger."""
    pad = "# Valuation Report\n\n" + ("Clean body line.\n" * 200)
    trailing = pad + "<thinking>late scratchpad</thinking>\n"
    # Well past 2000 bytes
    assert len(pad) > 2000
    assert _detect_scratchpad_leak(trailing) is None


def test_detect_matches_scratch_marker():
    bad = "[SCRATCH] internal note before the body.\n\n# Report\n"
    assert _detect_scratchpad_leak(bad) is not None


def test_detect_matches_actually_start_of_line():
    bad = "Actually, let me revise the numbers.\n\n# Report\n"
    assert _detect_scratchpad_leak(bad) is not None


# ---------------------------------------------------------------------------
# assemble_final_report integration — raises ReportAssemblyError on leak
# ---------------------------------------------------------------------------
def _mk_env(
    agent: str,
    symbol: str = "VEDL",
    report: str | None = None,
    company_name: str = "",
) -> BriefingEnvelope:
    if report is None:
        report = (
            f"## {agent.title()} Analysis\n\n"
            f"This is the {agent} report for {symbol}.\n\n"
            f"### Key Findings\n- Finding 1\n- Finding 2\n"
        )
    briefing: dict = {"agent": agent}
    if company_name:
        briefing["company_name"] = company_name
    return BriefingEnvelope(
        agent=agent,
        symbol=symbol,
        generated_at="2026-04-22T10:00:00",
        report=report,
        briefing=briefing,
        evidence=[
            ToolEvidence(
                tool="get_quarterly_results",
                args={"symbol": symbol},
                result_hash="abc123",
                is_error=False,
            )
        ],
        cost=AgentCost(
            input_tokens=100,
            output_tokens=50,
            total_cost_usd=0.01,
            duration_seconds=1.0,
        ),
    )


def _mk_synthesis(symbol: str = "VEDL") -> BriefingEnvelope:
    report = (
        "## Verdict\n\n**HOLD**\n\n"
        "## Executive Summary\n\nOK.\n\n"
        "## Key Signals\n\n- Signal A\n\n"
        "## Catalysts\n\n- Catalyst\n\n"
        "## What to Watch\n\n- Watch\n\n"
        "## Big Question\n\nQ?\n"
    )
    return BriefingEnvelope(
        agent="synthesis",
        symbol=symbol,
        generated_at="2026-04-22T11:00:00",
        report=report,
        briefing={"verdict": "HOLD"},
        evidence=[],
        cost=AgentCost(
            input_tokens=100,
            output_tokens=50,
            total_cost_usd=0.01,
            duration_seconds=1.0,
        ),
    )


class TestAssembleFinalReportScratchpadGuard:
    """The assembly pipeline must reject scratchpad-leaked specialist reports."""

    @pytest.fixture(autouse=True)
    def _redirect_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(
            "flowtracker.research.assembly._VAULT_BASE", tmp_path / "vault"
        )
        monkeypatch.setattr(
            "flowtracker.research.assembly._REPORTS_DIR", tmp_path / "reports"
        )

    def test_raises_on_thinking_tag_leak_in_valuation(self):
        """Mirrors the VEDL metals incident: valuation agent leaks <thinking>."""
        # Build a leaked valuation report > 400 bytes so guard engages.
        leaked_body = (
            "<thinking>\n"
            "Let me compute the blended FV for VEDL.\n"
            "Step 1: pull the EV/EBITDA peer multiple...\n"
            "Step 2: adjust for net debt per plan v2.\n"
            "</thinking>\n\n"
            "# Valuation Report for VEDL\n\n"
            + ("Placeholder body content line.\n" * 20)
        )
        assert len(leaked_body) > 400

        specialists = {
            "business": _mk_env("business", company_name="Vedanta"),
            "valuation": _mk_env("valuation", report=leaked_body),
        }
        synthesis = _mk_synthesis()

        with pytest.raises(ReportAssemblyError) as excinfo:
            assemble_final_report("VEDL", specialists, synthesis)

        msg = str(excinfo.value)
        assert "valuation" in msg
        assert "VEDL" in msg

    def test_short_crashed_report_does_not_trip_guard(self):
        """Reports under 400 bytes skip the guard (different failure mode)."""
        # Very short leaked output — agent likely crashed.
        short_leaked = "<thinking>aborted</thinking>"
        assert len(short_leaked) < 400

        specialists = {
            "business": _mk_env("business", company_name="Vedanta"),
            "valuation": _mk_env("valuation", report=short_leaked),
        }
        synthesis = _mk_synthesis()

        # Should not raise ReportAssemblyError.
        md_path, _ = assemble_final_report("VEDL", specialists, synthesis)
        assert md_path.exists()

    def test_clean_specialists_do_not_trigger_guard(self):
        specialists = {
            "business": _mk_env("business", company_name="Vedanta"),
            "valuation": _mk_env("valuation"),
        }
        synthesis = _mk_synthesis()

        md_path, _ = assemble_final_report("VEDL", specialists, synthesis)
        assert md_path.exists()
