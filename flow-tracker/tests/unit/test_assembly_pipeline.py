"""Tests for assembly pipeline functions (assemble_final_report + _render_html).

Covers the main public function and HTML rendering, complementing the
existing test_assembly.py which covers _strip_preamble, _split_by_headers,
and _find_section.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.assembly import (
    _render_html,
    _split_by_headers,
    assemble_final_report,
)
from flowtracker.research.briefing import AgentCost, BriefingEnvelope, ToolEvidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_NAMES = ["business", "financials", "valuation", "ownership", "risk", "technical"]


def _make_envelope(
    agent: str = "business",
    symbol: str = "SBIN",
    report: str | None = None,
    company_name: str = "",
    cost_usd: float = 0.05,
) -> BriefingEnvelope:
    """Build a minimal BriefingEnvelope for testing."""
    if report is None:
        report = (
            f"## {agent.title()} Analysis\n\n"
            f"This is the {agent} report for {symbol}.\n\n"
            f"### Key Findings\n- Finding 1\n- Finding 2\n"
        )
    briefing: dict = {"agent": agent, "signal": "bullish", "key_findings": ["Finding 1"]}
    if company_name:
        briefing["company_name"] = company_name
    return BriefingEnvelope(
        agent=agent,
        symbol=symbol,
        generated_at="2026-03-28T10:00:00",
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
            input_tokens=1000,
            output_tokens=500,
            total_cost_usd=cost_usd,
            duration_seconds=10.0,
        ),
    )


def _make_synthesis_envelope(
    symbol: str = "SBIN",
    cost_usd: float = 0.10,
) -> BriefingEnvelope:
    """Build a synthesis BriefingEnvelope with standard sections."""
    report = (
        "## Verdict\n\n**BUY** — Strong fundamentals with improving margins.\n\n"
        "## Executive Summary\n\nSBIN is a well-run bank with growing NII.\n\n"
        "## Key Signals\n\n- NII growth 18% YoY\n- NPA declining\n\n"
        "## Catalysts\n\n- Rate cut cycle\n- Credit growth\n\n"
        "## What to Watch\n\n- Asset quality\n- NIM compression\n\n"
        "## Big Question\n\nCan SBIN sustain 15%+ ROE?\n"
    )
    return BriefingEnvelope(
        agent="synthesis",
        symbol=symbol,
        generated_at="2026-03-28T11:00:00",
        report=report,
        briefing={"verdict": "BUY", "conviction": "high"},
        evidence=[],
        cost=AgentCost(
            input_tokens=5000,
            output_tokens=2000,
            total_cost_usd=cost_usd,
            duration_seconds=30.0,
        ),
    )


def _make_all_specialists(symbol: str = "SBIN") -> dict[str, BriefingEnvelope]:
    """Build envelopes for all 6 specialist agents."""
    envs = {}
    for i, name in enumerate(AGENT_NAMES):
        company = "State Bank of India" if name == "business" else ""
        envs[name] = _make_envelope(
            agent=name, symbol=symbol, company_name=company, cost_usd=0.05 + i * 0.01
        )
    return envs


# ---------------------------------------------------------------------------
# assemble_final_report
# ---------------------------------------------------------------------------
class TestAssembleFinalReport:
    """Tests for the main assembly pipeline."""

    @pytest.fixture(autouse=True)
    def _redirect_paths(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Redirect vault and reports directories to tmp_path so nothing hits disk."""
        monkeypatch.setattr(
            "flowtracker.research.assembly._VAULT_BASE", tmp_path / "vault"
        )
        monkeypatch.setattr(
            "flowtracker.research.assembly._REPORTS_DIR", tmp_path / "reports"
        )
        self.tmp_path = tmp_path

    def test_returns_two_paths(self):
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, html_path = assemble_final_report("SBIN", specialists, synthesis)
        assert isinstance(md_path, Path)
        assert isinstance(html_path, Path)
        assert md_path.exists()
        assert html_path.exists()

    def test_md_and_html_files_written(self):
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, html_path = assemble_final_report("SBIN", specialists, synthesis)
        assert md_path.suffix == ".md"
        assert html_path.suffix == ".html"
        # Check content is non-empty
        assert len(md_path.read_text()) > 100
        assert len(html_path.read_text()) > 100

    def test_synthesis_sections_before_specialists(self):
        """Verdict, Executive Summary, Key Signals must appear before specialist content."""
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        verdict_pos = md.index("Verdict")
        exec_summary_pos = md.index("Executive Summary")
        # First specialist section — Business Analysis
        business_pos = md.index("Business Analysis")

        assert verdict_pos < business_pos
        assert exec_summary_pos < business_pos

    def test_all_six_specialists_included(self):
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        for agent_name in AGENT_NAMES:
            assert f"{agent_name.title()} Analysis" in md or agent_name in md.lower(), (
                f"Specialist '{agent_name}' not found in assembled report"
            )

    def test_closing_sections_after_specialists(self):
        """Catalysts, What to Watch, Big Question appear after specialist reports."""
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        # Find last specialist mention
        last_specialist_pos = max(
            md.index(f"{name.title()} Analysis") for name in AGENT_NAMES
        )
        catalysts_pos = md.index("Catalysts")
        big_q_pos = md.index("Big Question")

        assert catalysts_pos > last_specialist_pos
        assert big_q_pos > last_specialist_pos

    def test_cost_summary_appended(self):
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        assert "Total cost: $" in md
        # Verify the cost is the sum: 6 specialists (0.05+0.06+...+0.10) + synthesis 0.10
        expected_total = sum(0.05 + i * 0.01 for i in range(6)) + 0.10
        assert f"${expected_total:.2f}" in md

    def test_preamble_stripped_from_specialist(self):
        """Agent chatter before the first heading should be removed."""
        specialists = _make_all_specialists()
        # Inject preamble into business report
        specialists["business"] = _make_envelope(
            agent="business",
            symbol="SBIN",
            report="I'll analyze the business now.\nLet me pull data.\n## Business Analysis\n\nClean content.",
            company_name="State Bank of India",
        )
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        assert "I'll analyze the business now" not in md
        assert "Let me pull data" not in md
        assert "Clean content." in md

    def test_company_name_in_title(self):
        specialists = _make_all_specialists()
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        assert "State Bank of India" in md
        assert "(SBIN)" in md

    def test_symbol_normalized_to_upper(self):
        """Symbol passed as lowercase should be uppercased."""
        specialists = _make_all_specialists(symbol="sbin")
        synthesis = _make_synthesis_envelope(symbol="sbin")
        md_path, html_path = assemble_final_report("sbin", specialists, synthesis)
        md = md_path.read_text()

        assert "(SBIN)" in md
        # Vault dir should use uppercase
        assert "SBIN" in str(md_path)

    def test_missing_specialist_gracefully_omitted(self):
        """If a specialist is missing from the dict, it's just skipped."""
        specialists = _make_all_specialists()
        del specialists["risk"]
        synthesis = _make_synthesis_envelope()
        md_path, _ = assemble_final_report("SBIN", specialists, synthesis)
        md = md_path.read_text()

        # Other specialists present
        assert "Business Analysis" in md
        assert "Financial" in md
        # Risk section absent (its report had "Risk Analysis" in the heading)
        assert "Risk Analysis" not in md


# ---------------------------------------------------------------------------
# _render_html
# ---------------------------------------------------------------------------
class TestRenderHtml:
    """Tests for the HTML rendering function."""

    def test_basic_markdown_to_html(self):
        html = _render_html("# Hello\n\nWorld.", "SBIN", "SBI", "2026-03-28")
        assert "<!DOCTYPE html>" in html
        assert "<h1" in html
        assert "World." in html

    def test_title_in_html(self):
        html = _render_html("# Test", "SBIN", "State Bank of India", "2026-03-28")
        assert "<title>State Bank of India (SBIN)" in html

    def test_title_fallback_to_symbol(self):
        html = _render_html("# Test", "SBIN", "", "2026-03-28")
        assert "<title>SBIN (SBIN)" in html

    def test_mermaid_blocks_preserved(self):
        md = "## Chart\n\n```mermaid\ngraph TD\n  A-->B\n```\n\nMore text."
        html = _render_html(md, "TEST", "Test Co", "2026-03-28")
        assert '<pre class="mermaid">' in html
        assert "A-->B" in html
        # Mermaid JS script included
        assert "mermaid" in html
        assert "cdn.jsdelivr.net" in html

    def test_multiple_mermaid_blocks(self):
        md = (
            "```mermaid\ngraph TD\n  A-->B\n```\n\n"
            "Some text.\n\n"
            "```mermaid\npie\n  title Shares\n  \"A\": 50\n  \"B\": 50\n```\n"
        )
        html = _render_html(md, "TEST", "Test", "2026-03-28")
        assert html.count('<pre class="mermaid">') == 2

    def test_empty_markdown(self):
        """Empty markdown should still produce valid HTML shell."""
        html = _render_html("", "TEST", "", "2026-03-28")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
        assert "<body>" in html

    def test_special_characters_in_markdown(self):
        """Ampersands and angle brackets should not break HTML."""
        md = "## Revenue > ₹1000 Cr & Growing\n\nP/E < 20 is cheap."
        html = _render_html(md, "TEST", "Test", "2026-03-28")
        assert "<!DOCTYPE html>" in html
        # Should contain the content (possibly HTML-escaped)
        assert "1000" in html
        assert "Growing" in html
        assert "cheap" in html

    def test_table_markdown_rendered(self):
        md = (
            "| Metric | Value |\n"
            "|--------|-------|\n"
            "| PE     | 12.5  |\n"
            "| ROE    | 15%   |\n"
        )
        html = _render_html(md, "TEST", "Test", "2026-03-28")
        assert "<table" in html
        assert "<th" in html
        assert "12.5" in html

    def test_css_variables_present(self):
        html = _render_html("# Test", "TEST", "Test", "2026-03-28")
        assert "--bg-dark" in html
        assert "--accent-1" in html
        assert "--accent-2" in html
