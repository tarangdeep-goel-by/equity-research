"""Tests for telemetry dataclasses and Pydantic model extensions in briefing.py.

Covers TurnEvent, RetryEvent, ComplianceGateTrace (dataclasses), and the
telemetry-extension fields on ToolEvidence and AgentTrace (Pydantic models).
"""

from __future__ import annotations

import dataclasses

import pytest

from flowtracker.research.briefing import (
    AgentCost,
    AgentTrace,
    ComplianceGateTrace,
    RetryEvent,
    ToolEvidence,
    TurnEvent,
)


# ---------------------------------------------------------------------------
# TurnEvent
# ---------------------------------------------------------------------------


class TestTurnEvent:
    """TurnEvent is a plain dataclass for per-turn token accounting."""

    def test_construction_all_fields(self):
        """Construct with every field explicitly set."""
        ev = TurnEvent(
            turn_index=0,
            started_at="2026-04-15T10:00:00Z",
            duration_ms=1200,
            model="claude-sonnet-4-20250514",
            input_tokens=500,
            output_tokens=300,
            cache_read_tokens=100,
            cache_write_tokens=50,
            reasoning_chars=800,
            tool_call_ids=["tc_1", "tc_2"],
        )
        assert ev.turn_index == 0
        assert ev.model == "claude-sonnet-4-20250514"
        assert ev.tool_call_ids == ["tc_1", "tc_2"]

    def test_defaults(self):
        """input_tokens defaults to 0 and tool_call_ids defaults to []."""
        ev = TurnEvent(
            turn_index=1,
            started_at="2026-04-15T10:00:00Z",
            duration_ms=500,
            model="gemini-3.1-pro-preview",
        )
        assert ev.input_tokens == 0
        assert ev.output_tokens == 0
        assert ev.cache_read_tokens == 0
        assert ev.cache_write_tokens == 0
        assert ev.reasoning_chars == 0
        assert ev.tool_call_ids == []

    def test_asdict_shape(self):
        """dataclasses.asdict produces the expected dict keys."""
        ev = TurnEvent(
            turn_index=2,
            started_at="2026-04-15T10:01:00Z",
            duration_ms=800,
            model="claude-sonnet-4-20250514",
            output_tokens=100,
            tool_call_ids=["tc_x"],
        )
        d = dataclasses.asdict(ev)
        assert d["turn_index"] == 2
        assert d["output_tokens"] == 100
        assert d["tool_call_ids"] == ["tc_x"]
        expected_keys = {
            "turn_index", "started_at", "duration_ms", "model",
            "input_tokens", "output_tokens", "cache_read_tokens",
            "cache_write_tokens", "reasoning_chars", "tool_call_ids",
        }
        assert set(d.keys()) == expected_keys

    def test_mutable_default_isolation(self):
        """Each instance gets its own tool_call_ids list."""
        a = TurnEvent(turn_index=0, started_at="", duration_ms=0, model="m")
        b = TurnEvent(turn_index=1, started_at="", duration_ms=0, model="m")
        a.tool_call_ids.append("tc_a")
        assert b.tool_call_ids == []


# ---------------------------------------------------------------------------
# RetryEvent
# ---------------------------------------------------------------------------


class TestRetryEvent:
    """RetryEvent captures tool-call retries classified by cause."""

    @pytest.mark.parametrize("cause", [
        "truncation", "rate_limit", "network", "validation", "empty_result", "other",
    ])
    def test_all_valid_causes(self, cause):
        """All six literal cause values are accepted."""
        ev = RetryEvent(tool_name="get_fundamentals", attempt=1, cause=cause)
        assert ev.cause == cause

    def test_defaults(self):
        """wait_ms defaults to 0 and at defaults to empty string."""
        ev = RetryEvent(tool_name="get_peers", attempt=2, cause="network")
        assert ev.wait_ms == 0
        assert ev.at == ""

    def test_asdict_serialization(self):
        """Round-trip through asdict preserves all fields."""
        ev = RetryEvent(
            tool_name="get_shareholding",
            attempt=3,
            cause="rate_limit",
            wait_ms=5000,
            at="2026-04-15T10:05:00Z",
        )
        d = dataclasses.asdict(ev)
        assert d["tool_name"] == "get_shareholding"
        assert d["attempt"] == 3
        assert d["wait_ms"] == 5000
        assert d["at"] == "2026-04-15T10:05:00Z"


# ---------------------------------------------------------------------------
# ComplianceGateTrace
# ---------------------------------------------------------------------------


class TestComplianceGateTrace:
    """ComplianceGateTrace maps mandatory metrics to backing tool calls."""

    @pytest.mark.parametrize("status", [
        "extracted", "attempted", "not_applicable", "missing",
    ])
    def test_all_statuses(self, status):
        """All four literal status values construct successfully."""
        t = ComplianceGateTrace(metric="GNPA", status=status)
        assert t.status == status

    def test_default_empty_tool_use_ids(self):
        """attempted_tool_use_ids defaults to []."""
        t = ComplianceGateTrace(metric="pre_sales_value", status="missing")
        assert t.attempted_tool_use_ids == []
        assert t.note == ""

    def test_with_note_and_ids(self):
        """Construct with note and explicit tool_use_ids."""
        t = ComplianceGateTrace(
            metric="ROE",
            status="extracted",
            attempted_tool_use_ids=["tu_1", "tu_2"],
            note="extracted from quarterly results",
        )
        assert len(t.attempted_tool_use_ids) == 2
        assert t.note == "extracted from quarterly results"

    def test_mutable_default_isolation(self):
        """Each instance gets its own attempted_tool_use_ids list."""
        a = ComplianceGateTrace(metric="X", status="missing")
        b = ComplianceGateTrace(metric="Y", status="missing")
        a.attempted_tool_use_ids.append("id_1")
        assert b.attempted_tool_use_ids == []


# ---------------------------------------------------------------------------
# ToolEvidence extensions
# ---------------------------------------------------------------------------


class TestToolEvidenceExtensions:
    """Test the new telemetry fields on the ToolEvidence Pydantic model."""

    def test_new_fields_set(self):
        """Create ToolEvidence with all new extension fields."""
        te = ToolEvidence(
            tool="get_fundamentals",
            turn_index=3,
            completeness="full",
            row_count=42,
            extraction_meta={"source": "screener", "tables": 2},
        )
        assert te.turn_index == 3
        assert te.completeness == "full"
        assert te.row_count == 42
        assert te.extraction_meta == {"source": "screener", "tables": 2}

    def test_backward_compat_defaults(self):
        """Create WITHOUT new fields — all default to None."""
        te = ToolEvidence(tool="get_peers")
        assert te.turn_index is None
        assert te.completeness is None
        assert te.row_count is None
        assert te.extraction_meta is None

    def test_json_round_trip(self):
        """model_dump -> ToolEvidence(**dict) preserves new fields."""
        te = ToolEvidence(
            tool="get_shareholding",
            args={"symbol": "SBIN"},
            turn_index=1,
            completeness="partial",
            row_count=10,
            extraction_meta={"truncated_rows": 5},
        )
        d = te.model_dump()
        restored = ToolEvidence(**d)
        assert restored.turn_index == 1
        assert restored.completeness == "partial"
        assert restored.row_count == 10
        assert restored.extraction_meta == {"truncated_rows": 5}

    def test_old_json_without_new_fields(self):
        """Dict from old code (no new keys) parses fine via extra='ignore'."""
        old_dict = {
            "tool": "get_quarterly_results",
            "args": {"symbol": "INFY"},
            "result_summary": "8 quarters",
            "result_hash": "abc",
            "is_error": False,
        }
        te = ToolEvidence(**old_dict)
        assert te.tool == "get_quarterly_results"
        assert te.turn_index is None
        assert te.completeness is None


# ---------------------------------------------------------------------------
# AgentTrace extensions
# ---------------------------------------------------------------------------


class TestAgentTraceExtensions:
    """Test the new telemetry fields on the AgentTrace Pydantic model."""

    def _base_kwargs(self) -> dict:
        return {
            "agent": "financials",
            "symbol": "SBIN",
            "started_at": "2026-04-15T10:00:00Z",
            "finished_at": "2026-04-15T10:02:00Z",
            "duration_seconds": 120.0,
        }

    def test_new_fields_populated(self):
        """Create AgentTrace with all new extension fields."""
        turn = TurnEvent(
            turn_index=0,
            started_at="2026-04-15T10:00:00Z",
            duration_ms=500,
            model="claude-sonnet-4-20250514",
            output_tokens=200,
        )
        retry = RetryEvent(
            tool_name="get_fundamentals",
            attempt=1,
            cause="truncation",
            wait_ms=1000,
        )
        gate = ComplianceGateTrace(
            metric="GNPA",
            status="extracted",
            attempted_tool_use_ids=["tu_1"],
        )
        phase_cost = AgentCost(input_tokens=300, output_tokens=150, total_cost_usd=0.01)

        trace = AgentTrace(
            **self._base_kwargs(),
            turns=[turn],
            retries=[retry],
            time_to_first_token_ms=120,
            compliance_gate_traces=[gate],
            per_phase_cost={"data_collection": phase_cost},
        )
        assert len(trace.turns) == 1
        assert trace.turns[0].turn_index == 0
        assert len(trace.retries) == 1
        assert trace.retries[0].cause == "truncation"
        assert trace.time_to_first_token_ms == 120
        assert len(trace.compliance_gate_traces) == 1
        assert trace.compliance_gate_traces[0].metric == "GNPA"
        assert "data_collection" in trace.per_phase_cost

    def test_backward_compat_defaults(self):
        """Create WITHOUT new fields — defaults to empty lists/None."""
        trace = AgentTrace(**self._base_kwargs())
        assert trace.turns == []
        assert trace.retries == []
        assert trace.time_to_first_token_ms is None
        assert trace.compliance_gate_traces == []
        assert trace.per_phase_cost == {}

    def test_json_round_trip(self):
        """model_dump -> AgentTrace(**dict) preserves nested telemetry objects."""
        turn = TurnEvent(
            turn_index=0,
            started_at="2026-04-15T10:00:00Z",
            duration_ms=600,
            model="claude-sonnet-4-20250514",
            input_tokens=400,
            output_tokens=200,
            tool_call_ids=["tc_1"],
        )
        gate = ComplianceGateTrace(
            metric="NIM",
            status="attempted",
            attempted_tool_use_ids=["tu_3"],
            note="tried but partial",
        )

        trace = AgentTrace(
            **self._base_kwargs(),
            turns=[turn],
            compliance_gate_traces=[gate],
            time_to_first_token_ms=95,
        )
        d = trace.model_dump()
        restored = AgentTrace(**d)

        assert restored.time_to_first_token_ms == 95
        assert len(restored.turns) == 1
        assert restored.turns[0].tool_call_ids == ["tc_1"]
        assert restored.compliance_gate_traces[0].note == "tried but partial"

    def test_old_trace_json_backward_compat(self):
        """Dict from old code (no telemetry keys) parses fine."""
        old_dict = {
            "agent": "ownership",
            "symbol": "HDFCBANK",
            "started_at": "2026-04-15T09:00:00Z",
            "finished_at": "2026-04-15T09:01:00Z",
            "duration_seconds": 60.0,
            "status": "success",
            "tools_available": ["get_shareholding"],
            "tool_calls": [],
            "reasoning": ["looked up shareholding"],
            "report_chars": 500,
        }
        trace = AgentTrace(**old_dict)
        assert trace.agent == "ownership"
        assert trace.turns == []
        assert trace.retries == []
        assert trace.time_to_first_token_ms is None

    def test_nested_serialization_turn_in_trace(self):
        """TurnEvent inside AgentTrace serializes correctly to dict."""
        turn = TurnEvent(
            turn_index=0,
            started_at="2026-04-15T10:00:00Z",
            duration_ms=300,
            model="gemini-3.1-pro-preview",
            reasoning_chars=150,
        )
        trace = AgentTrace(
            **self._base_kwargs(),
            turns=[turn],
        )
        d = trace.model_dump()
        turn_dict = d["turns"][0]
        assert turn_dict["turn_index"] == 0
        assert turn_dict["model"] == "gemini-3.1-pro-preview"
        assert turn_dict["reasoning_chars"] == 150
        assert turn_dict["tool_call_ids"] == []
