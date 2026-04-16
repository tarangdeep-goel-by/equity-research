"""Tests for format_agent_evidence() — the Gemini "Agent Execution Log" formatter.

Covers backward-compat for old traces (no telemetry fields) AND the new
turn-level / retry / compliance-gate / completeness rendering that C-3
adds.

The formatter is a pure function (dict in -> str out); no IO, no env
dependencies, so these tests are fast and deterministic.
"""

from __future__ import annotations

import pytest

pytest.importorskip("yaml", reason="pyyaml required for autoeval evaluate")

from flowtracker.research.autoeval import evaluate as ev  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers — build realistic trace fixtures
# ---------------------------------------------------------------------------


def _old_style_trace() -> dict:
    """AgentTrace with no telemetry fields — pre-C-3 shape."""
    return {
        "agent": "business",
        "symbol": "SBIN",
        "status": "success",
        "duration_seconds": 42.0,
        "tools_available": ["get_fundamentals", "get_price_history", "get_news"],
        "tool_calls": [
            {"tool": "get_fundamentals", "args": {"symbol": "SBIN"}, "is_error": False},
            {"tool": "get_price_history", "args": {}, "is_error": False},
        ],
        "cost": {
            "total_cost_usd": 0.25,
            "input_tokens": 5000,
            "output_tokens": 2000,
            "model": "claude-sonnet",
        },
        # No turns, no retries, no compliance traces, no time_to_first_token_ms.
        # No turn_index / completeness on tool calls.
    }


def _rich_trace() -> dict:
    """AgentTrace with full C-3 telemetry populated."""
    return {
        "agent": "financials",
        "symbol": "HDFCBANK",
        "status": "success",
        "duration_seconds": 65.0,
        "tools_available": ["get_fundamentals", "get_concall_insights", "get_sector_kpis"],
        "tool_calls": [
            {
                "tool": "get_fundamentals",
                "args": {"symbol": "HDFCBANK"},
                "is_error": False,
                "turn_index": 0,
                "completeness": "full",
                "row_count": 12,
                "duration_ms": 450,
            },
            {
                "tool": "get_concall_insights",
                "args": {"symbol": "HDFCBANK", "quarters": 4},
                "is_error": False,
                "turn_index": 1,
                "completeness": "partial",
                "row_count": 3,
                "duration_ms": 1200,
                "extraction_meta": {
                    "extraction_status": "degraded",
                    "missing_periods": ["FY26-Q2"],
                    "degraded_quality": True,
                },
            },
            {
                "tool": "get_sector_kpis",
                "args": {"sector": "bfsi"},
                "is_error": False,
                "turn_index": 1,
                "completeness": "empty",
                "row_count": 0,
                "duration_ms": 200,
            },
        ],
        "cost": {
            "total_cost_usd": 0.85,
            "input_tokens": 20000,
            "output_tokens": 8000,
            "cache_read_tokens": 15000,
            "cache_write_tokens": 500,
            "model": "claude-sonnet",
        },
        "turns": [
            {
                "turn_index": 0,
                "started_at": "2026-04-15T10:00:00Z",
                "duration_ms": 2500,
                "model": "claude-sonnet",
                "input_tokens": 8000,
                "output_tokens": 3000,
                "cache_read_tokens": 7000,
                "cache_write_tokens": 200,
                "reasoning_chars": 1200,
                "tool_call_ids": ["toolu_01"],
            },
            {
                "turn_index": 1,
                "started_at": "2026-04-15T10:00:05Z",
                "duration_ms": 4500,
                "model": "claude-sonnet",
                "input_tokens": 12000,
                "output_tokens": 5000,
                "cache_read_tokens": 8000,
                "cache_write_tokens": 300,
                "reasoning_chars": 2400,
                "tool_call_ids": ["toolu_02", "toolu_03"],
            },
        ],
        "retries": [
            {
                "tool_name": "get_concall_insights",
                "attempt": 1,
                "cause": "truncation",
                "wait_ms": 500,
                "at": "2026-04-15T10:00:06Z",
            },
            {
                "tool_name": "get_sector_kpis",
                "attempt": 1,
                "cause": "empty_result",
                "wait_ms": 0,
                "at": "2026-04-15T10:00:07Z",
            },
        ],
        "time_to_first_token_ms": 1350,
        "compliance_gate_traces": [
            {
                "metric": "GNPA",
                "status": "extracted",
                "attempted_tool_use_ids": ["toolu_01"],
                "note": "",
            },
            {
                "metric": "CASA",
                "status": "attempted",
                "attempted_tool_use_ids": ["toolu_02", "toolu_03"],
                "note": "tool returned partial data",
            },
            {
                "metric": "CD_ratio",
                "status": "missing",
                "attempted_tool_use_ids": [],
                "note": "",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Backward compatibility: old-style trace
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Old traces (no turns/retries/etc.) render the legacy format."""

    def test_old_trace_uses_legacy_format(self):
        out = ev.format_agent_evidence(
            "business", "SBIN", agent_trace=_old_style_trace()
        )
        # Legacy header (no "— business on SBIN")
        assert out.startswith("## Agent Execution Log\n")
        # No turn summary line
        assert "Turns:" not in out
        assert "Time to first token" not in out
        assert "Retries:" not in out
        assert "Tool completeness" not in out
        assert "Compliance gate" not in out
        # Legacy content present
        assert "Tools available (3)" in out
        assert "Tools called (2 calls)" in out
        assert "Tools NEVER called" in out
        assert "get_news" in out  # the unused tool
        assert "Cost: $0.25" in out

    def test_empty_trace_returns_empty(self):
        assert ev.format_agent_evidence("x", "Y") == ""

    def test_legacy_evidence_fallback(self):
        """No trace, but legacy evidence list → flat "Tools called" output."""
        evidence = [
            {"tool": "get_fundamentals", "args": {}, "is_error": False},
            {"tool": "get_price_history", "args": {}, "is_error": True,
             "result_summary": "timeout after 30s"},
        ]
        out = ev.format_agent_evidence(
            "business", "SBIN", legacy_evidence=evidence
        )
        assert "## Agent Execution Log" in out
        assert "Tools called (2 total)" in out
        assert "get_fundamentals" in out
        assert "Tool errors (1)" in out
        assert "timeout" in out

    def test_legacy_briefing_cost_line(self):
        briefing = {
            "cost": {
                "total_cost_usd": 0.12,
                "input_tokens": 100,
                "output_tokens": 50,
                "duration_seconds": 8,
                "model": "test-model",
            },
            "status": "success",
        }
        out = ev.format_agent_evidence(
            "x", "Y", legacy_briefing=briefing
        )
        assert "Cost: $0.12" in out
        assert "test-model" in out


# ---------------------------------------------------------------------------
# Rich format: new telemetry sections
# ---------------------------------------------------------------------------


class TestRichFormat:
    """Traces with telemetry fields trigger the richer rendering."""

    def test_rich_header_includes_agent_and_symbol(self):
        out = ev.format_agent_evidence(
            "financials", "HDFCBANK", agent_trace=_rich_trace()
        )
        assert "Agent Execution Log — financials on HDFCBANK" in out

    def test_turns_line_present(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        # Both turns with durations 2500ms and 4500ms → p50 is the higher of
        # the two (list [2500,4500], median index 1 = 4500ms = 4.5s)
        assert "Turns: 2" in out
        assert "p50 duration" in out
        assert "max 4.5s" in out

    def test_tokens_line_aggregates_across_turns(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        # 8000+12000=20000 in => 20.0k; 3000+5000=8000 out => 8.0k
        # 7000+8000=15000 cache-read => 15.0k; 200+300=500 cache-write => 0.5k
        assert "Tokens:" in out
        assert "20.0k in" in out
        assert "8.0k out" in out
        assert "15.0k cache-read" in out
        assert "0.5k cache-write" in out
        assert "$0.85" in out

    def test_time_to_first_token_rendered(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        assert "Time to first token: 1.4s" in out  # 1350ms → 1.4s (rounded)

    def test_retries_line_present(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        assert "Retries: 2" in out
        assert "get_concall_insights × truncation" in out
        assert "get_sector_kpis × empty_result" in out

    def test_completeness_summary(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        assert "Tool completeness:" in out
        assert "1/3 full" in out
        assert "1 empty" in out
        assert "get_sector_kpis" in out

    def test_compliance_gate_section(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        assert "Compliance gate:" in out
        # 1 extracted out of 3 total, 1 attempted
        assert "1/3 metrics extracted" in out
        assert "1 attempted" in out
        assert "CASA" in out

    def test_source_data_quality_only_degraded(self):
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=_rich_trace())
        assert "Source data quality:" in out
        # Only get_concall_insights has extraction_meta flagged as degraded
        assert "get_concall_insights: extraction_status=degraded" in out
        assert "missing=['FY26-Q2']" in out
        # get_fundamentals / get_sector_kpis had no extraction_meta → must
        # not appear in this line
        src_line = [
            line for line in out.splitlines()
            if line.startswith("- Source data quality:")
        ][0]
        assert "get_fundamentals" not in src_line
        assert "get_sector_kpis" not in src_line


# ---------------------------------------------------------------------------
# Conditional omission: retries absent, etc.
# ---------------------------------------------------------------------------


class TestConditionalOmission:
    """Lines are omitted cleanly when the backing data is empty."""

    def test_retries_line_omitted_when_empty(self):
        trace = _rich_trace()
        trace["retries"] = []
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=trace)
        # Still rich mode (turns exist), but no Retries line
        assert "Turns: 2" in out
        assert "Retries:" not in out

    def test_ttft_omitted_when_none(self):
        trace = _rich_trace()
        trace["time_to_first_token_ms"] = None
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=trace)
        assert "Time to first token" not in out

    def test_compliance_gate_section_omitted_when_empty(self):
        trace = _rich_trace()
        trace["compliance_gate_traces"] = []
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=trace)
        assert "Compliance gate:" not in out

    def test_completeness_omitted_when_all_calls_lack_it(self):
        """If no tool_call has `completeness` set → no summary line."""
        trace = _rich_trace()
        for c in trace["tool_calls"]:
            c.pop("completeness", None)
        # Keep turns so we stay in rich mode
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=trace)
        assert "Tool completeness:" not in out

    def test_source_data_quality_omitted_when_no_degraded(self):
        trace = _rich_trace()
        for c in trace["tool_calls"]:
            c.pop("extraction_meta", None)
        out = ev.format_agent_evidence("financials", "HDFCBANK", agent_trace=trace)
        assert "Source data quality:" not in out


# ---------------------------------------------------------------------------
# All-full completeness edge case
# ---------------------------------------------------------------------------


class TestAllFullCompleteness:
    def test_all_full_shows_n_over_n(self):
        trace = _rich_trace()
        for c in trace["tool_calls"]:
            c["completeness"] = "full"
        out = ev.format_agent_evidence(
            "financials", "HDFCBANK", agent_trace=trace
        )
        # 3/3 full, no empty/truncated extras
        completeness_lines = [
            line for line in out.splitlines()
            if "Tool completeness:" in line
        ]
        assert len(completeness_lines) == 1
        line = completeness_lines[0]
        assert "3/3 full" in line
        assert "empty" not in line
        assert "truncated" not in line


# ---------------------------------------------------------------------------
# Turn interleaving
# ---------------------------------------------------------------------------


class TestTurnInterleaving:
    def test_turn_interleaving_lines_present(self):
        out = ev.format_agent_evidence(
            "financials", "HDFCBANK", agent_trace=_rich_trace()
        )
        assert "Tool calls (interleaved with reasoning):" in out
        # Turn 0 has one call (get_fundamentals), Turn 1 has two
        turn_lines = [
            line.strip() for line in out.splitlines()
            if line.strip().startswith("Turn ")
        ]
        # At least one Turn 0 line and two Turn 1 lines
        turn0 = [l for l in turn_lines if l.startswith("Turn 0:")]
        turn1 = [l for l in turn_lines if l.startswith("Turn 1:")]
        assert len(turn0) >= 1
        assert len(turn1) >= 2

    def test_reasoning_chars_shown_first_call(self):
        out = ev.format_agent_evidence(
            "financials", "HDFCBANK", agent_trace=_rich_trace()
        )
        # Turn 0 reasoning_chars = 1200
        assert "[reason 1200 chars]" in out
        # Turn 1 reasoning_chars = 2400
        assert "[reason 2400 chars]" in out

    def test_call_extras_rendered(self):
        out = ev.format_agent_evidence(
            "financials", "HDFCBANK", agent_trace=_rich_trace()
        )
        # full, 12 rows, 0.5s for get_fundamentals
        assert "get_fundamentals" in out
        assert "12 rows" in out
        assert "full" in out


# ---------------------------------------------------------------------------
# Compliance gate: mix of extracted + attempted
# ---------------------------------------------------------------------------


class TestComplianceGateMix:
    def test_mix_summary(self):
        out = ev.format_agent_evidence(
            "financials", "HDFCBANK", agent_trace=_rich_trace()
        )
        line = [
            l for l in out.splitlines()
            if l.startswith("- Compliance gate:")
        ][0]
        # 1 extracted / 3 total; 1 attempted
        assert "1/3 metrics extracted" in line
        assert "1 attempted" in line
        # Attempted detail for CASA mentions "tried"
        assert "CASA: tried" in line


# ---------------------------------------------------------------------------
# Integration with read_agent_evidence (end-to-end of the new path)
# ---------------------------------------------------------------------------


class TestReadAgentEvidenceWithTelemetry:
    """read_agent_evidence loads a trace file and renders rich output."""

    def test_rich_trace_file_renders_turns(self, tmp_path, monkeypatch):
        import json as _json

        monkeypatch.setenv("HOME", str(tmp_path))
        stock = "HDFCBANK"
        agent = "financials"
        traces_dir = tmp_path / "vault" / "stocks" / stock / "traces"
        traces_dir.mkdir(parents=True)
        pipeline = {"agents": {agent: _rich_trace()}}
        (traces_dir / "20260415T100000.json").write_text(_json.dumps(pipeline))

        out = ev.read_agent_evidence(agent, stock)
        assert "Agent Execution Log — financials on HDFCBANK" in out
        assert "Turns: 2" in out
        assert "Retries: 2" in out
        assert "Compliance gate:" in out
        assert "Tool completeness:" in out
