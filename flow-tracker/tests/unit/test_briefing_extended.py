"""Extended tests for flowtracker/research/briefing.py.

Tests envelope save/load round-trips, load_all_briefings, and
parse_briefing_from_markdown edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.briefing import (
    BriefingEnvelope,
    ToolEvidence,
    AgentCost,
    VerificationResult,
    load_all_briefings,
    load_envelope,
    parse_briefing_from_markdown,
    save_envelope,
)


# ---------------------------------------------------------------------------
# Fixture: redirect vault base to tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def vault_in_tmp(tmp_path, monkeypatch):
    """Point _VAULT_BASE to a temp directory so tests don't touch the real vault."""
    monkeypatch.setattr("flowtracker.research.briefing._VAULT_BASE", tmp_path / "vault" / "stocks")


# ---------------------------------------------------------------------------
# Helper: build a fully-populated envelope
# ---------------------------------------------------------------------------

def _make_envelope(agent: str = "business", symbol: str = "SBIN") -> BriefingEnvelope:
    return BriefingEnvelope(
        agent=agent,
        symbol=symbol,
        generated_at="2026-03-28T10:00:00+00:00",
        report="# Business Report\n\nSBIN is a leading public sector bank.",
        briefing={"sector": "Banking", "moat": "branch network", "rating": "BUY"},
        evidence=[
            ToolEvidence(
                tool="get_company_info",
                args={"symbol": "SBIN"},
                result_summary="State Bank of India, Banks",
                result_hash="abc123",
            ),
            ToolEvidence(
                tool="get_quarterly_results",
                args={"symbol": "SBIN", "quarters": 8},
                result_summary="8 quarters returned",
                result_hash="def456",
                is_error=False,
            ),
        ],
        cost=AgentCost(
            input_tokens=5000,
            output_tokens=3000,
            total_cost_usd=0.045,
            duration_seconds=12.5,
            model="claude-sonnet-4-20250514",
        ),
    )


# ---------------------------------------------------------------------------
# save_envelope
# ---------------------------------------------------------------------------

class TestSaveEnvelope:
    def test_creates_all_three_files(self, tmp_path):
        env = _make_envelope()
        paths = save_envelope(env)

        assert "report" in paths
        assert "briefing" in paths
        assert "evidence" in paths

        for key, p in paths.items():
            assert p.exists(), f"{key} file not created at {p}"
            assert p.stat().st_size > 0, f"{key} file is empty"

    def test_report_contains_markdown(self, tmp_path):
        env = _make_envelope()
        paths = save_envelope(env)
        content = paths["report"].read_text(encoding="utf-8")
        assert "# Business Report" in content
        assert "SBIN" in content

    def test_briefing_is_valid_json(self, tmp_path):
        env = _make_envelope()
        paths = save_envelope(env)
        data = json.loads(paths["briefing"].read_text(encoding="utf-8"))
        assert data["sector"] == "Banking"
        assert data["moat"] == "branch network"

    def test_evidence_is_list_of_dicts(self, tmp_path):
        env = _make_envelope()
        paths = save_envelope(env)
        data = json.loads(paths["evidence"].read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["tool"] == "get_company_info"


# ---------------------------------------------------------------------------
# load_envelope — round-trip with save
# ---------------------------------------------------------------------------

class TestLoadEnvelope:
    def test_round_trip(self, tmp_path):
        env = _make_envelope()
        save_envelope(env)

        loaded = load_envelope("SBIN", "business")
        assert loaded is not None
        assert loaded.agent == "business"
        assert loaded.symbol == "SBIN"
        assert "Business Report" in loaded.report
        assert loaded.briefing["sector"] == "Banking"
        assert len(loaded.evidence) == 2

    def test_returns_none_for_missing(self, tmp_path):
        result = load_envelope("NONEXIST", "business")
        assert result is None

    def test_returns_none_for_missing_agent(self, tmp_path):
        env = _make_envelope(agent="business")
        save_envelope(env)
        result = load_envelope("SBIN", "valuation")
        assert result is None


# ---------------------------------------------------------------------------
# load_all_briefings
# ---------------------------------------------------------------------------

class TestLoadAllBriefings:
    def test_loads_multiple_agents(self, tmp_path):
        for agent in ("business", "financial", "ownership"):
            env = _make_envelope(agent=agent)
            env.briefing = {"agent": agent, "data": f"sample_{agent}"}
            save_envelope(env)

        result = load_all_briefings("SBIN")
        assert isinstance(result, dict)
        assert len(result) == 3
        assert set(result.keys()) == {"business", "financial", "ownership"}
        assert result["business"]["agent"] == "business"

    def test_empty_for_missing_symbol(self, tmp_path):
        result = load_all_briefings("NONEXIST")
        assert result == {}

    def test_skips_invalid_json(self, tmp_path):
        # Save one valid envelope
        env = _make_envelope(agent="business")
        save_envelope(env)

        # Manually write a corrupt JSON file
        briefings_dir = tmp_path / "vault" / "stocks" / "SBIN" / "briefings"
        corrupt = briefings_dir / "corrupt_agent.json"
        corrupt.write_text("not valid json{{{", encoding="utf-8")

        result = load_all_briefings("SBIN")
        # Should have business but skip corrupt
        assert "business" in result
        assert "corrupt_agent" not in result


# ---------------------------------------------------------------------------
# parse_briefing_from_markdown
# ---------------------------------------------------------------------------

class TestParseBriefingFromMarkdown:
    def test_extracts_json_from_fenced_block(self):
        text = '# Report\n\nSome analysis.\n\n```json\n{"rating": "BUY", "score": 85}\n```'
        result = parse_briefing_from_markdown(text)
        assert result == {"rating": "BUY", "score": 85}

    def test_returns_last_json_block(self):
        text = (
            '```json\n{"first": true}\n```\n'
            'More text.\n'
            '```json\n{"second": true, "final": "yes"}\n```'
        )
        result = parse_briefing_from_markdown(text)
        assert result == {"second": True, "final": "yes"}

    def test_no_json_block_returns_empty(self):
        text = "# Report\n\nJust plain markdown with no code blocks."
        result = parse_briefing_from_markdown(text)
        assert result == {}

    def test_invalid_json_returns_empty(self):
        text = '```json\n{invalid json content\n```'
        result = parse_briefing_from_markdown(text)
        assert result == {}

    def test_empty_string_returns_empty(self):
        result = parse_briefing_from_markdown("")
        assert result == {}

    def test_non_json_code_block_ignored(self):
        text = '```python\nprint("hello")\n```\n\nNo JSON here.'
        result = parse_briefing_from_markdown(text)
        assert result == {}

    def test_nested_json_structure(self):
        briefing = {
            "summary": "Strong financials",
            "metrics": {"pe": 9.5, "roe": 18.5},
            "risks": ["concentration", "npa"],
        }
        text = f'# Report\n\nAnalysis here.\n\n```json\n{json.dumps(briefing, indent=2)}\n```'
        result = parse_briefing_from_markdown(text)
        assert result == briefing


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------

class TestModels:
    def test_verification_result_defaults(self):
        vr = VerificationResult(agent_verified="business", symbol="SBIN")
        assert vr.verdict == "pass"
        assert vr.spot_checks_performed == 0
        assert vr.issues == []

    def test_agent_cost_defaults(self):
        cost = AgentCost()
        assert cost.input_tokens == 0
        assert cost.total_cost_usd == 0.0
