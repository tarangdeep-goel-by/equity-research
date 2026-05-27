"""Unit tests for the Phase 6 tool-use trace-audit (research tool-audit).

Covers the pure metrics functions in ``flowtracker.research.tool_audit``:
error/empty rates, invalid-arg + unknown-tool (hallucination) detection,
duplicate-call counting, coverage %, latency hotspots, truncation risk, the
overall roll-up, and the on-disk discovery + audit_traces path.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from flowtracker.research import tool_audit as TA


# --------------------------------------------------------------------------- #
# Synthetic trace fixtures
# --------------------------------------------------------------------------- #
def _call(tool, args=None, *, is_error=False, completeness="full",
          result_summary='{"ok": true}', duration_ms=100, payload_len=None):
    return {
        "tool": tool,
        "args": args or {},
        "result_summary": result_summary,
        "is_error": is_error,
        "completeness": completeness,
        "row_count": None,
        "payload_len": payload_len,
        "duration_ms": duration_ms,
        "turn_index": 1,
    }


def _make_trace():
    """One pipeline trace with two agents covering every metric path."""
    return {
        "symbol": "TESTCO",
        "started_at": "2026-05-20T10:00:00+00:00",
        "agents": {
            "valuation": {
                "agent": "valuation",
                "symbol": "TESTCO",
                "tools_available": ["get_valuation", "get_estimates", "calculate"],
                "tool_calls": [
                    # registered, ok
                    _call("mcp__valuation__get_valuation",
                          {"symbol": "TESTCO"}, duration_ms=8000),
                    # DUPLICATE of the above (same tool + same args)
                    _call("mcp__valuation__get_valuation",
                          {"symbol": "TESTCO"}, duration_ms=120),
                    # hallucinated tool (not in registry) + error "no such tool"
                    _call("mcp__valuation__get_fundamentals",
                          {"symbol": "TESTCO"}, is_error=True, completeness="error",
                          result_summary="<tool_use_error>Error: No such tool "
                          "available: mcp__valuation__get_fundamentals</tool_use_error>",
                          duration_ms=5),
                    # invalid-arg rejection (enum / did-you-mean)
                    _call("mcp__valuation__get_estimates",
                          {"period": "bogus"}, is_error=True, completeness="error",
                          result_summary='{"error": "Invalid period; '
                          'valid_values: [annual, quarterly]"}', duration_ms=10),
                    # empty result
                    _call("mcp__valuation__calculate", {"expr": "1-1"},
                          completeness="empty", result_summary="[]",
                          duration_ms=2),
                ],
            },
            "macro": {
                "agent": "macro",
                "symbol": "TESTCO",
                "tools_available": ["get_market_context", "get_macro_indicators"],
                "tool_calls": [
                    _call("mcp__macro__get_market_context", {},
                          duration_ms=300),
                    # truncation risk via explicit payload_len
                    _call("mcp__macro__get_macro_indicators", {},
                          payload_len=50_000, duration_ms=400),
                ],
            },
        },
    }


# Registry override so tests don't depend on the live registries matching.
_REGISTRY = {
    "valuation": {"get_valuation", "get_estimates", "calculate", "get_peer_sector"},
    "macro": {"get_market_context", "get_macro_indicators", "get_macro_anchor"},
}


def test_audit_basic_metrics():
    res = TA.audit_trace_dicts([_make_trace()], agent_registry=_REGISTRY)
    val = res["agents"]["valuation"]

    assert val["total_calls"] == 5
    # 2 of 5 calls errored (get_fundamentals + get_estimates)
    assert val["error_rate"] == round(2 / 5, 4)
    # 1 empty (calculate)
    assert val["empty_rate"] == round(1 / 5, 4)
    # invalid-arg: only the get_estimates rejection (NOT the "no such tool")
    assert val["invalid_arg_count"] == 1
    # hallucination: get_fundamentals not in registry
    assert val["unknown_tool_count"] == 1
    assert val["unknown_tools"] == ["get_fundamentals"]
    # duplicate: the repeated (get_valuation, {symbol:TESTCO})
    assert val["duplicate_calls"] == 1
    # coverage: 3 distinct registered tools called / 4 registered = 75%
    assert val["coverage_pct"] == 75.0
    assert val["registered_tool_count"] == 4


def test_latency_hotspots_sorted():
    res = TA.audit_trace_dicts([_make_trace()], agent_registry=_REGISTRY)
    hotspots = res["agents"]["valuation"]["latency_hotspots"]
    assert hotspots[0]["tool"] == "get_valuation"
    assert hotspots[0]["duration_ms"] == 8000
    # sorted descending
    durs = [h["duration_ms"] for h in hotspots]
    assert durs == sorted(durs, reverse=True)


def test_truncation_risk_from_payload_len():
    res = TA.audit_trace_dicts([_make_trace()], agent_registry=_REGISTRY)
    assert res["agents"]["macro"]["truncation_risk"] == 1
    # valuation has no oversized payloads
    assert res["agents"]["valuation"]["truncation_risk"] == 0


def test_overall_rollup():
    res = TA.audit_trace_dicts([_make_trace()], agent_registry=_REGISTRY)
    overall = res["overall"]
    assert overall["total_calls"] == 7  # 5 valuation + 2 macro
    assert overall["unknown_tool_count"] == 1
    assert overall["duplicate_calls"] == 1
    assert overall["truncation_risk"] == 1
    # weighted error rate = 2 errors / 7 calls
    assert overall["error_rate"] == round(2 / 7, 4)
    assert len(overall["latency_hotspots"]) <= 5


def test_registry_fallback_to_tools_available():
    """An agent with no static registry should fall back to per-trace
    tools_available for coverage / hallucination detection."""
    trace = {
        "symbol": "X", "started_at": "2026-05-20T10:00:00+00:00",
        "agents": {
            "mystery_agent": {
                "tools_available": ["alpha", "beta"],
                "tool_calls": [
                    _call("mcp__x__alpha"),
                    _call("mcp__x__gamma"),  # not in tools_available -> unknown
                ],
            }
        },
    }
    res = TA.audit_trace_dicts([trace], agent_registry={})
    a = res["agents"]["mystery_agent"]
    assert a["registered_tool_count"] == 2
    assert a["unknown_tool_count"] == 1
    assert a["unknown_tools"] == ["gamma"]
    # 1 of 2 registered tools called
    assert a["coverage_pct"] == 50.0


def test_builtin_tools_not_hallucinations():
    """Built-in harness tools (no mcp__ prefix, e.g. WebSearch) are counted
    separately and NOT flagged as hallucinations."""
    trace = {
        "symbol": "Z", "started_at": "2026-05-20T10:00:00+00:00",
        "agents": {
            "macro": {
                "tools_available": ["get_market_context"],
                "tool_calls": [
                    _call("mcp__macro__get_market_context"),
                    _call("WebSearch", {"q": "rbi mpr"}),       # builtin, allowed
                    _call("WebFetch", {"url": "https://x"}),     # builtin, allowed
                    _call("mcp__macro__not_a_tool"),             # real MCP hallucination
                ],
            }
        },
    }
    res = TA.audit_trace_dicts([trace], agent_registry=_REGISTRY)
    m = res["agents"]["macro"]
    assert m["builtin_tool_count"] == 2
    assert m["unknown_tool_count"] == 1
    assert m["unknown_tools"] == ["not_a_tool"]
    assert res["overall"]["builtin_tool_count"] == 2


def test_empty_and_missing_fields_graceful():
    """Older traces may lack payload_len / completeness — must not crash."""
    trace = {
        "symbol": "Y", "started_at": "2026-05-20T10:00:00+00:00",
        "agents": {
            "valuation": {
                "tools_available": ["get_valuation"],
                "tool_calls": [
                    {"tool": "mcp__valuation__get_valuation", "args": {},
                     "is_error": False, "duration_ms": 5},  # no completeness/payload_len
                ],
            }
        },
    }
    res = TA.audit_trace_dicts([trace], agent_registry=_REGISTRY)
    val = res["agents"]["valuation"]
    assert val["total_calls"] == 1
    assert val["error_rate"] == 0.0
    assert val["truncation_risk"] == 0


def test_no_traces_returns_empty():
    res = TA.audit_trace_dicts([])
    assert res["agents"] == {}
    assert res["overall"]["total_calls"] == 0
    assert res["meta"]["trace_count"] == 0


# --------------------------------------------------------------------------- #
# Discovery + on-disk audit_traces
# --------------------------------------------------------------------------- #
def test_discover_and_audit_traces(tmp_path: Path):
    stocks = tmp_path / "stocks"
    for sym, ts in [("AAA", "20260510T120000"), ("BBB", "20260601T120000")]:
        d = stocks / sym / "traces"
        d.mkdir(parents=True)
        (d / f"{ts}.json").write_text(json.dumps(_make_trace()), encoding="utf-8")

    # No filter -> both files
    all_paths = TA.discover_trace_files(stocks_dir=stocks)
    assert len(all_paths) == 2

    # since filter drops the May trace
    recent = TA.discover_trace_files(stocks_dir=stocks, since=date(2026, 5, 20))
    assert len(recent) == 1
    assert "BBB" in str(recent[0])

    # symbol filter
    only_aaa = TA.discover_trace_files(stocks_dir=stocks, symbol="aaa")
    assert len(only_aaa) == 1
    assert "AAA" in str(only_aaa[0])

    res = TA.audit_traces(all_paths, agent_registry=_REGISTRY)
    assert res["meta"]["file_count"] == 2
    assert res["meta"]["unreadable"] == []
    # two traces, each 5 valuation calls => 10
    assert res["agents"]["valuation"]["total_calls"] == 10


def test_audit_traces_handles_unreadable(tmp_path: Path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not valid json", encoding="utf-8")
    res = TA.audit_traces([bad], agent_registry=_REGISTRY)
    assert res["meta"]["unreadable"] == [str(bad)]
    assert res["agents"] == {}


def test_live_registry_map_has_known_agents():
    """Smoke: the real registry import resolves the core specialist agents."""
    mapping = TA._build_agent_registry_map()
    assert "valuation" in mapping
    assert "get_valuation" in mapping["valuation"]
    # macro agent has a distinct, smaller registry
    assert "macro" in mapping
    assert "get_market_context" in mapping["macro"]
