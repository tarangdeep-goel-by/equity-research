"""Phase 6 tool-use trace-audit.

Read-only analysis over the enriched per-call traces written by the research
pipeline (``save_trace`` in :mod:`flowtracker.research.briefing`). Produces a
per-agent tool-use scorecard so we can measure whether tool-layer hardening
worked and track it over time.

Trace schema (per ``PipelineTrace.model_dump()``), confirmed against live vault
traces under ``~/vault/stocks/<SYMBOL>/traces/<ts>.json``::

    {
      "symbol": str, "started_at": str, ...,
      "agents": {
        "<agent>": {
          "agent": str, "symbol": str,
          "tools_available": [bare tool names, no mcp__ prefix],
          "tool_calls": [
            {
              "tool": "mcp__<server>__<name>",
              "args": dict,
              "result_summary": str,   # CAPPED at 500 chars in stored traces
              "is_error": bool,
              "completeness": "full|partial|empty|truncated|error"|null,
              "row_count": int|null,
              "payload_len": int|null, # full untruncated len (None on old traces)
              "duration_ms": int,
              "turn_index": int|null,
              ...
            }, ...
          ]
        }, ...
      }
    }

Known limitations of the current stored traces (reported, not worked around):
  * ``result_summary`` is truncated to 500 chars at write time, so substring
    detection of invalid-arg rejections is best-effort (the rejection prefix
    appears early, so this is reliable in practice).
  * ``payload_len`` was added later; older traces have it ``None``. We therefore
    fall back to ``len(result_summary)`` for truncation-risk when ``payload_len``
    is absent, and note that result_summary's 500-char cap makes the
    >30000 threshold effectively unreachable from these traces.

This module only READS traces. It imports the agent tool registries from
:mod:`flowtracker.research.tools` to build the agent -> registered-tool-set map
used for hallucination / misroute detection, falling back to the per-trace
``tools_available`` list when an agent has no known registry.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Default vault location (matches briefing._VAULT_BASE).
_VAULT_STOCKS = Path.home() / "vault" / "stocks"

# Threshold above which a single tool result is considered at risk of
# truncation by the agent context window.
TRUNCATION_PAYLOAD_THRESHOLD = 30_000

# Substrings that, on an errored call, indicate the tool rejected the args with
# an enum / did-you-mean style message.
_INVALID_ARG_MARKERS = ("invalid", "valid_values", "did you mean", "suggestion")


# --------------------------------------------------------------------------- #
# Registry map (agent -> set of registered bare tool names)
# --------------------------------------------------------------------------- #
def _build_agent_registry_map() -> dict[str, set[str]]:
    """Map agent name -> set of registered (bare) tool names.

    Imports the ``*_AGENT_TOOLS_V2`` registries from
    :mod:`flowtracker.research.tools`. Each registry is a list of
    ``SdkMcpTool`` objects exposing a ``.name`` attribute. Agent keys match the
    names used in trace ``agents`` dicts (e.g. "business", "valuation").

    Best-effort: if the import or any registry is unavailable, the missing
    agents simply fall back to per-trace ``tools_available`` at audit time.
    """
    mapping: dict[str, set[str]] = {}
    try:
        from flowtracker.research import tools as T
    except Exception:  # noqa: BLE001 — registries are advisory
        return mapping

    registry_by_agent = {
        "business": "BUSINESS_AGENT_TOOLS_V2",
        "financials": "FINANCIAL_AGENT_TOOLS_V2",
        "ownership": "OWNERSHIP_AGENT_TOOLS_V2",
        "valuation": "VALUATION_AGENT_TOOLS_V2",
        "risk": "RISK_AGENT_TOOLS_V2",
        "technical": "TECHNICAL_AGENT_TOOLS_V2",
        "sector": "SECTOR_AGENT_TOOLS_V2",
        "news": "NEWS_AGENT_TOOLS_V2",
        "macro": "MACRO_AGENT_TOOLS_V2",
        "historical_analog": "HISTORICAL_ANALOG_AGENT_TOOLS_V2",
        "fno_positioning": "FNO_POSITIONING_AGENT_TOOLS_V2",
    }
    for agent, attr in registry_by_agent.items():
        registry = getattr(T, attr, None)
        if not registry:
            continue
        names = {getattr(tool, "name", None) for tool in registry}
        names.discard(None)
        if names:
            mapping[agent] = names  # type: ignore[assignment]
    return mapping


# --------------------------------------------------------------------------- #
# Trace discovery
# --------------------------------------------------------------------------- #
def _parse_trace_date(path: Path) -> date | None:
    """Best-effort date for a trace file.

    Filenames are ``YYYYMMDDTHHMMSS.json`` (e.g. ``20260527T101706.json``).
    Falls back to file mtime if the stem isn't a recognisable timestamp.
    """
    stem = path.stem
    # Expected form: 20260527T101706
    if len(stem) >= 8 and stem[:8].isdigit():
        try:
            return date(int(stem[0:4]), int(stem[4:6]), int(stem[6:8]))
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()
    except OSError:
        return None


def discover_trace_files(
    *,
    stocks_dir: Path | None = None,
    since: date | None = None,
    symbol: str | None = None,
) -> list[Path]:
    """Discover trace JSON files under ``<stocks_dir>/*/traces/*.json``.

    Args:
        stocks_dir: Root vault stocks dir. Defaults to ``~/vault/stocks``.
        since: Only include traces dated on/after this date (parsed from the
            filename timestamp, falling back to file mtime).
        symbol: Only include traces for this stock symbol (case-insensitive).

    Returns:
        Sorted list of paths (oldest first by filename).
    """
    root = stocks_dir or _VAULT_STOCKS
    if not root.exists():
        return []

    if symbol:
        glob_pat = f"{symbol.upper()}/traces/*.json"
    else:
        glob_pat = "*/traces/*.json"

    paths = sorted(root.glob(glob_pat))
    if since is not None:
        kept = []
        for p in paths:
            d = _parse_trace_date(p)
            if d is None or d >= since:
                kept.append(p)
        paths = kept
    return paths


# --------------------------------------------------------------------------- #
# Per-call classification helpers
# --------------------------------------------------------------------------- #
def _strip_prefix(tool: str) -> str:
    """``mcp__valuation__get_valuation`` -> ``get_valuation``."""
    if not tool:
        return ""
    return tool.split("__")[-1]


def _is_mcp_tool(tool: str) -> bool:
    """True for our MCP tools (``mcp__<server>__<name>``); False for built-in
    agent-harness tools like ``WebSearch`` / ``WebFetch`` / ``Read`` that have
    no ``mcp__`` prefix and are not covered by the agent tool registries."""
    return str(tool or "").startswith("mcp__")


def _is_invalid_arg(call: dict[str, Any]) -> bool:
    """Heuristic: an errored call whose result text signals an enum /
    did-you-mean rejection.

    Limitation: relies on ``result_summary`` which is capped at 500 chars in
    stored traces. The rejection message appears at the start of the payload,
    so this is reliable for real rejections.
    """
    if not call.get("is_error"):
        return False
    text = str(call.get("result_summary") or "").lower()
    if not text:
        # No result text in this trace; cannot confirm. Treat as not-invalid
        # (the caller reports this as a heuristic limitation).
        return False
    # "No such tool available" is a hallucination, not an arg rejection.
    if "no such tool available" in text:
        return False
    return any(marker in text for marker in _INVALID_ARG_MARKERS)


def _is_empty(call: dict[str, Any]) -> bool:
    """completeness == 'empty', with a result_summary fallback for older
    traces that never populated completeness.

    The fallback only fires on a *confirmed* empty container (``[]`` / ``{}``)
    captured in ``result_summary``. A wholly-absent ``result_summary`` (older
    macro/web traces never recorded the text) is treated as UNKNOWN — not
    empty — so we don't fabricate a misleading 100% empty_rate from missing
    instrumentation rather than from genuinely empty tool results.
    """
    comp = call.get("completeness")
    if comp == "empty":
        return True
    if comp is not None:
        return False
    # Fallback heuristic for traces with null completeness: only a result whose
    # captured text is an empty container counts as empty. Missing text => unknown.
    text = str(call.get("result_summary") or "").strip()
    return text in ("[]", "{}")


# --------------------------------------------------------------------------- #
# Core audit
# --------------------------------------------------------------------------- #
def _empty_agent_metrics() -> dict[str, Any]:
    return {
        "total_calls": 0,
        "error_rate": 0.0,
        "empty_rate": 0.0,
        "invalid_arg_count": 0,
        "unknown_tool_count": 0,
        "unknown_tools": [],
        "builtin_tool_count": 0,
        "duplicate_calls": 0,
        "coverage_pct": 0.0,
        "registered_tool_count": 0,
        "distinct_tools_called": 0,
        "latency_hotspots": [],
        "truncation_risk": 0,
        "traces": 0,
    }


def _audit_agent_calls(
    calls: list[dict[str, Any]],
    registered: set[str],
) -> dict[str, Any]:
    """Compute the scorecard metrics for one agent's flat list of tool calls."""
    total = len(calls)
    m = _empty_agent_metrics()
    if total == 0:
        m["registered_tool_count"] = len(registered)
        return m

    errors = 0
    empties = 0
    invalid_args = 0
    builtin = 0
    unknown = Counter()
    truncation = 0
    seen_sigs: Counter = Counter()
    called_mcp_bare: set[str] = set()
    latencies: list[tuple[str, int]] = []

    for call in calls:
        raw_tool = str(call.get("tool") or "")
        bare = _strip_prefix(raw_tool)
        is_mcp = _is_mcp_tool(raw_tool)
        if is_mcp:
            called_mcp_bare.add(bare)
        else:
            builtin += 1

        if call.get("is_error"):
            errors += 1
        if _is_empty(call):
            empties += 1
        if _is_invalid_arg(call):
            invalid_args += 1

        # Hallucination / misroute: an MCP tool not in the agent's registered
        # set. Built-in harness tools (WebSearch/WebFetch/Read/…) carry no
        # mcp__ prefix and are excluded — they're not registry-covered.
        if is_mcp and registered and bare not in registered:
            unknown[bare] += 1

        # Duplicate detection: identical (tool, args) signature seen >1 time.
        try:
            args_sig = json.dumps(call.get("args") or {}, sort_keys=True, default=str)
        except (TypeError, ValueError):
            args_sig = repr(call.get("args"))
        seen_sigs[(bare, args_sig)] += 1

        # Truncation risk: prefer full payload_len; fall back to result_summary
        # length (capped at 500, so effectively never trips the threshold —
        # surfaced as a known limitation, not a workaround).
        plen = call.get("payload_len")
        if plen is None:
            plen = len(str(call.get("result_summary") or ""))
        if plen > TRUNCATION_PAYLOAD_THRESHOLD:
            truncation += 1

        dur = call.get("duration_ms")
        if isinstance(dur, (int, float)):
            latencies.append((bare, int(dur)))

    duplicate_calls = sum(c - 1 for c in seen_sigs.values() if c > 1)
    latencies.sort(key=lambda x: x[1], reverse=True)

    # Coverage: distinct *registered* MCP tools actually called / total registered.
    if registered:
        distinct_registered_called = len(called_mcp_bare & registered)
        coverage = round(100.0 * distinct_registered_called / len(registered), 1)
    else:
        coverage = 0.0

    m.update(
        {
            "total_calls": total,
            "error_rate": round(errors / total, 4),
            "empty_rate": round(empties / total, 4),
            "invalid_arg_count": invalid_args,
            "unknown_tool_count": int(sum(unknown.values())),
            "unknown_tools": sorted(unknown.keys()),
            "builtin_tool_count": builtin,
            "duplicate_calls": duplicate_calls,
            "coverage_pct": coverage,
            "registered_tool_count": len(registered),
            "distinct_tools_called": len(called_mcp_bare),
            "latency_hotspots": [
                {"tool": t, "duration_ms": ms} for t, ms in latencies[:5]
            ],
            "truncation_risk": truncation,
        }
    )
    return m


def audit_trace_dicts(
    traces: list[dict[str, Any]],
    *,
    agent_registry: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Audit a list of already-loaded trace dicts.

    Pure function: no filesystem access. ``traces`` is a list of objects shaped
    like ``PipelineTrace.model_dump()`` (top-level ``agents`` dict).

    Args:
        traces: loaded trace dicts.
        agent_registry: optional agent -> registered-tool-name-set map. If not
            supplied, the registries from ``flowtracker.research.tools`` are used.

    Returns:
        ``{"agents": {<agent>: {...metrics...}}, "overall": {...}, "meta": {...}}``
    """
    registry = agent_registry if agent_registry is not None else _build_agent_registry_map()

    # Bucket calls per agent across all traces. Also track which agents appeared
    # in each trace (for the per-agent trace count) and their tools_available.
    agent_calls: dict[str, list[dict[str, Any]]] = {}
    agent_trace_count: Counter = Counter()
    agent_tools_available: dict[str, set[str]] = {}

    for trace in traces:
        agents = (trace or {}).get("agents") or {}
        if not isinstance(agents, dict):
            continue
        for agent_name, info in agents.items():
            if not isinstance(info, dict):
                continue
            agent_trace_count[agent_name] += 1
            calls = info.get("tool_calls") or []
            agent_calls.setdefault(agent_name, []).extend(
                c for c in calls if isinstance(c, dict)
            )
            # Accumulate per-trace tools_available (bare names) as a registry
            # fallback for agents with no static registry.
            avail = info.get("tools_available") or []
            if isinstance(avail, list):
                agent_tools_available.setdefault(agent_name, set()).update(
                    _strip_prefix(str(t)) for t in avail if t
                )

    per_agent: dict[str, Any] = {}
    for agent_name, calls in agent_calls.items():
        registered = registry.get(agent_name)
        if not registered:
            # Fall back to the per-trace tools_available set.
            registered = agent_tools_available.get(agent_name, set())
        result = _audit_agent_calls(calls, registered)
        result["traces"] = agent_trace_count[agent_name]
        per_agent[agent_name] = result

    overall = _rollup(per_agent)
    return {
        "agents": dict(sorted(per_agent.items())),
        "overall": overall,
        "meta": {
            "trace_count": len(traces),
            "agent_count": len(per_agent),
            "result_summary_capped_at": 500,
            "truncation_threshold": TRUNCATION_PAYLOAD_THRESHOLD,
        },
    }


def _rollup(per_agent: dict[str, Any]) -> dict[str, Any]:
    """Aggregate the per-agent metrics into an overall roll-up."""
    overall = _empty_agent_metrics()
    overall.pop("coverage_pct", None)
    overall.pop("registered_tool_count", None)
    overall.pop("distinct_tools_called", None)

    total = 0
    errors_w = 0.0
    empties_w = 0.0
    invalid = 0
    unknown = 0
    builtin = 0
    duplicates = 0
    truncation = 0
    all_hotspots: list[dict[str, Any]] = []
    all_unknown: Counter = Counter()

    for m in per_agent.values():
        n = m["total_calls"]
        total += n
        errors_w += m["error_rate"] * n
        empties_w += m["empty_rate"] * n
        invalid += m["invalid_arg_count"]
        unknown += m["unknown_tool_count"]
        builtin += m["builtin_tool_count"]
        duplicates += m["duplicate_calls"]
        truncation += m["truncation_risk"]
        all_hotspots.extend(m["latency_hotspots"])
        for t in m["unknown_tools"]:
            all_unknown[t] += 1

    all_hotspots.sort(key=lambda x: x["duration_ms"], reverse=True)
    overall.update(
        {
            "total_calls": total,
            "error_rate": round(errors_w / total, 4) if total else 0.0,
            "empty_rate": round(empties_w / total, 4) if total else 0.0,
            "invalid_arg_count": invalid,
            "unknown_tool_count": unknown,
            "unknown_tools": sorted(all_unknown.keys()),
            "builtin_tool_count": builtin,
            "duplicate_calls": duplicates,
            "truncation_risk": truncation,
            "latency_hotspots": all_hotspots[:5],
        }
    )
    return overall


def audit_traces(
    trace_paths: list[Path],
    *,
    agent_registry: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Load and audit the given trace files.

    Args:
        trace_paths: list of trace JSON files (see :func:`discover_trace_files`).
        agent_registry: optional override for the agent -> tool-set map.

    Returns:
        Structured scorecard dict (see :func:`audit_trace_dicts`). The ``meta``
        block additionally carries ``file_count`` and ``unreadable`` (paths that
        failed to parse).
    """
    loaded: list[dict[str, Any]] = []
    unreadable: list[str] = []
    for p in trace_paths:
        try:
            loaded.append(json.loads(Path(p).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            unreadable.append(str(p))

    result = audit_trace_dicts(loaded, agent_registry=agent_registry)
    result["meta"]["file_count"] = len(trace_paths)
    result["meta"]["unreadable"] = unreadable
    return result
