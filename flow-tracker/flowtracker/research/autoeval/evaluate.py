#!/usr/bin/env python3
"""AutoEval — Gemini eval harness for specialist agent reports.

IMMUTABLE: This file must never be modified by the autoeval orchestrator.
Changes to this file invalidate all experiment results.

Usage:
    python evaluate.py --sector bfsi                          # eval all 7 agents
    python evaluate.py --sector bfsi --agents business,risk   # eval specific agents
    python evaluate.py --sector bfsi --skip-run               # grade existing reports only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Grade scale
# ---------------------------------------------------------------------------
GRADE_MAP = {
    "A+": 97, "A": 93, "A-": 90,
    "B+": 87, "B": 83, "B-": 80,
    "C+": 77, "C": 73, "C-": 70,
    "D+": 67, "D": 63, "D-": 60,
    "F": 50,
}


@dataclass
class EvalIssue:
    type: str       # PROMPT_FIX, DATA_FIX, COMPUTATION, NOT_OUR_PROBLEM
    section: str
    issue: str
    suggestion: str


@dataclass
class ParameterGrade:
    grade: str
    numeric: int
    rationale: str


@dataclass
class AgentEvalResult:
    agent: str
    stock: str
    sector: str
    grade: str
    grade_numeric: int
    parameters: dict[str, ParameterGrade] = field(default_factory=dict)
    issues: list[EvalIssue] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    summary: str = ""
    report_length: int = 0
    run_duration_s: float = 0.0
    eval_duration_s: float = 0.0
    run_skipped: bool = False
    raw_gemini_response: str = ""


@dataclass
class LastRunResult:
    sector: str
    stock: str
    timestamp: str
    results: dict[str, AgentEvalResult] = field(default_factory=dict)
    # Convenience
    all_passing: bool = False
    failing_agents: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Eval system prompt (the immutable rubric)
# ---------------------------------------------------------------------------
EVAL_SYSTEM_TEMPLATE = """You are a senior equity research analyst with 20 years covering Indian {sector_type} companies.

Grade this AI-generated {agent} report for {stock}.

## Multi-Agent Context

This report is produced by one specialist in a 7-agent pipeline. Each agent has a defined scope:

- **Business** — Business model, moat, unit economics, revenue drivers, management quality
- **Financial** — Earnings trajectory, margin mechanics, cash flow, growth sustainability, accounting quality
- **Ownership** — Shareholding patterns, FII/DII trends, insider activity, institutional conviction
- **Valuation** — Fair value, PE/PB analysis, DCF, margin of safety, relative valuation
- **Risk** — Financial, governance, regulatory, macro, and operational risks
- **Technical** — Price action, support/resistance, volume, momentum indicators
- **Sector** — Industry dynamics, competitive landscape, regulatory environment, sector flows, TAM

Grade this {agent} report on how well it covers ITS scope, not the full investment picture.

## Evaluation Parameters (grade each independently A+ through F)

1. **Analytical Depth** — Goes beyond surface-level observation? Explains WHY, not just WHAT? Connects data to investability?
2. **Logical Consistency** — Conclusions follow from data? No contradictions? Assumptions stated?
3. **Completeness** — All important dimensions covered? Sector-specific metrics and frameworks present? No major gaps?
4. **Actionability** — Clear, evidence-backed conclusions? Bull/bear framework? Identifiable catalysts and risks?
5. **Sector Framework** — Are the RIGHT analytical frameworks applied for THIS sector type? (e.g., BFSI needs NIM/CASA/CD ratio/credit costs; metals needs EV/EBITDA/cycle positioning; platform needs unit economics/GMV)
6. **Data Sourcing** — Are claims backed by cited data? Sources attributed? Tool data used correctly?
7. **Tool-Use Discipline** — Judge from the Agent Execution Log. A: retried on truncation/empty, chose the right tool first time, ≤1 wasted call, surfaced data-quality gaps honestly. B+: mostly disciplined but one tool choice was suboptimal or one "attempted" metric had no backing tool calls. C: gave up on first empty result, called same tool ≥3× without changing args, or claimed "attempted" without evidence. F: ignored the tool layer / no tool use. **Requires the Execution Log — if absent, grade N/A (return numeric=85).**
8. **Cost Efficiency** — Judge from the Agent Execution Log. A: full-depth report with <$0.30 cost AND ≤8 turns AND cache hit rate ≥70%. B+: $0.30–$0.60 OR 9–12 turns OR cache hit rate 50–70%. C: $0.60–$1.00 OR 13–20 turns OR cache hit rate 30–50%. F: >$1.00 OR >20 turns for similar depth, or cache hit rate <30% (re-pays for context). Cache hit rate is surfaced directly on the "Cache hit rate:" line — do not re-derive from raw tokens. **Requires the Execution Log — if absent, grade N/A (return numeric=85).**

## Grade Scale
A+ (97) = Institutional quality — you would send this to a portfolio manager without edits
A  (93) = Strong — minor polish needed, no analytical gaps
A- (90) = Good — 1-2 meaningful gaps that a PM would notice
B+ (87) = Solid foundation — notable missing analysis, needs another draft
B  (83) = Adequate — multiple gaps, wouldn't circulate externally
B- (80) = Below expectations — significant gaps in frameworks or logic
C  (73) = Major deficiencies — wrong frameworks or missing critical dimensions
F  (50) = Fundamentally flawed

## Grading Calibration
- **Grade harshly.** A B+ is a good report. An A means institutional quality. Most reports should land in B to A- range.
- For EACH parameter, you MUST identify at least one weakness or gap, even if minor. No parameter gets a perfect score without explicit justification.
- Your **overall grade_numeric** must equal the arithmetic mean of the 8 parameter numeric scores (rounded to nearest integer). Do not inflate the overall above the average.
- If the Agent Execution Log is absent or shows only legacy format (no turns/retries/cost telemetry), grade tool_use_discipline and cost_efficiency as numeric=85 (B+) with rationale "legacy trace — telemetry not captured" and exclude both from your averaging.

## Critical Instructions
- Do NOT grade the accuracy of specific numbers. Your training data is outdated — the report uses live data. Focus on frameworks, logic, and completeness.
- If a number looks suspicious, classify it as "worth verifying" — do not mark it incorrect.
- Report length does NOT equal quality. A long report with shallow analysis scores lower than a concise report with deep insight.

## Issue Classification
Classify each issue into exactly ONE category:
- **PROMPT_FIX**: Agent behavior fixable by editing instructions (missing framework, wrong approach, skipped analysis, didn't call a tool it should have)
- **DATA_FIX**: Missing or broken data in the pipeline (tool returned empty/error, metric not available)
- **COMPUTATION**: Mathematical calculation error (wrong formula, unit conversion error)
- **NOT_OUR_PROBLEM**: Inherent LLM limitation (minor hallucination, inconsistent phrasing)

## Agent Execution Log
The report may include an execution log showing tools called, tools available but not called, errors, and cost. Use this to sharpen your classification:
- Missing analysis + agent never called the relevant tool → PROMPT_FIX
- Agent called a tool but it returned error/empty → DATA_FIX
- Agent called the right tools but misinterpreted data → PROMPT_FIX

## Response Format (strict JSON)
{{
  "parameters": {{
    "analytical_depth": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}},
    "logical_consistency": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}},
    "completeness": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}},
    "actionability": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}},
    "sector_framework": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}},
    "data_sourcing": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}},
    "tool_use_discipline": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<cite log evidence; if log absent, use 85 + 'legacy trace'>"}},
    "cost_efficiency": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<cite cost/turns; if log absent, use 85 + 'legacy trace'>"}}
  }},
  "overall": {{
    "grade": "<A+..F>",
    "grade_numeric": <50-97>
  }},
  "issues": [
    {{
      "type": "<PROMPT_FIX|DATA_FIX|COMPUTATION|NOT_OUR_PROBLEM>",
      "section": "<which section of the report>",
      "issue": "<specific description>",
      "suggestion": "<concrete fix>"
    }}
  ],
  "strengths": ["<strength 1>", "<strength 2>"],
  "summary": "<2-3 sentence overall assessment — lead with the most important gap>"
}}
"""


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def load_matrix() -> dict:
    """Load eval_matrix.yaml from the same directory as this script."""
    matrix_path = Path(__file__).parent / "eval_matrix.yaml"
    with open(matrix_path) as f:
        return yaml.safe_load(f)


def run_agent(agent: str, stock: str) -> tuple[float, bool]:
    """Run a specialist agent via CLI. Returns (duration_seconds, success).

    Streams stderr (tool call logs) live via line-by-line reading while
    capturing stdout. Uses Popen instead of run() for real-time output.
    """
    cwd = Path(__file__).resolve().parents[3]  # flow-tracker/
    start = time.monotonic()
    proc = subprocess.Popen(
        ["uv", "run", "flowtrack", "research", "run", agent, "-s", stock],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    # Stream stderr live (tool call logs) while process runs
    try:
        while proc.poll() is None:
            line = proc.stderr.readline()
            if line:
                print(f"  {line.rstrip()}", file=sys.stderr)
            # Check timeout
            if time.monotonic() - start > 1800:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(cmd="agent", timeout=1800)
        # Drain remaining stderr
        for line in proc.stderr:
            print(f"  {line.rstrip()}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start
        print(f"  [WARN] Agent {agent} timed out for {stock} after {duration:.0f}s", file=sys.stderr)
        return duration, False

    duration = time.monotonic() - start
    success = proc.returncode == 0
    if not success:
        print(f"  [WARN] Agent {agent} failed for {stock} (exit {proc.returncode})", file=sys.stderr)
    return duration, success


def read_report(agent: str, stock: str) -> str:
    """Read the agent's report markdown."""
    report_path = Path.home() / "vault" / "stocks" / stock / "reports" / f"{agent}.md"
    if not report_path.exists():
        return ""
    return report_path.read_text()


def format_agent_evidence(
    agent: str,
    stock: str,
    agent_trace: dict | None = None,
    legacy_evidence: list | None = None,
    legacy_briefing: dict | None = None,
) -> str:
    """Pure formatter for the Gemini "Agent Execution Log" section.

    Renders trace telemetry (turns, retries, compliance gates, tool completeness,
    source-data quality) when present, and falls back to the legacy flat
    tools-called listing when the trace has no telemetry fields.

    Old traces still deserialize because every new field defaults to None/empty;
    the formatter only emits a subsection when the underlying data is non-empty.

    Args:
        agent:              agent name (e.g. "business", "financials")
        stock:              symbol (e.g. "SBIN")
        agent_trace:        AgentTrace as a dict (from a PipelineTrace JSON)
        legacy_evidence:    fallback — list of ToolEvidence-shaped dicts
        legacy_briefing:    fallback — BriefingEnvelope-shaped dict

    Returns:
        Multi-line string starting with "## Agent Execution Log ...", or ""
        if nothing is known about the agent run.
    """
    sections: list[str] = []

    # -------------------------------------------------------------------
    # AgentTrace path (preferred)
    # -------------------------------------------------------------------
    if agent_trace:
        turns = agent_trace.get("turns") or []
        retries = agent_trace.get("retries") or []
        compliance_traces = agent_trace.get("compliance_gate_traces") or []
        ttft_ms = agent_trace.get("time_to_first_token_ms")

        calls = agent_trace.get("tool_calls") or []
        available = set(agent_trace.get("tools_available") or [])
        called = set(c.get("tool", "") for c in calls if c.get("tool"))
        unused = sorted(available - called)
        errors = [c for c in calls if c.get("is_error")]

        # Decide whether to use "rich" (telemetry-aware) or "legacy" format.
        any_turn_index = any(c.get("turn_index") is not None for c in calls)
        any_completeness = any(c.get("completeness") for c in calls)
        rich = bool(turns) or any_turn_index or any_completeness or bool(retries) or bool(compliance_traces)

        header = f"Agent Execution Log — {agent} on {stock}"

        if rich:
            # --- Turn summary ---------------------------------------------
            if turns:
                durations = sorted(t.get("duration_ms", 0) for t in turns)
                p50 = durations[len(durations) // 2] / 1000.0 if durations else 0.0
                max_s = max(durations) / 1000.0 if durations else 0.0
                sections.append(f"- Turns: {len(turns)} (p50 duration {p50:.1f}s, max {max_s:.1f}s)")

            # --- Token / cost roll-up ------------------------------------
            cost = agent_trace.get("cost") or {}
            if cost or turns:
                if turns:
                    in_tok = sum(t.get("input_tokens", 0) for t in turns)
                    out_tok = sum(t.get("output_tokens", 0) for t in turns)
                    cr_tok = sum(t.get("cache_read_tokens", 0) for t in turns)
                    cw_tok = sum(t.get("cache_write_tokens", 0) for t in turns)
                else:
                    in_tok = cost.get("input_tokens", 0)
                    out_tok = cost.get("output_tokens", 0)
                    cr_tok = cost.get("cache_read_tokens", 0)
                    cw_tok = cost.get("cache_write_tokens", 0)
                total_cost = cost.get("total_cost_usd", 0.0) if cost else 0.0
                sections.append(
                    f"- Tokens: {in_tok/1000:.1f}k in / {out_tok/1000:.1f}k out / "
                    f"{cr_tok/1000:.1f}k cache-read / {cw_tok/1000:.1f}k cache-write "
                    f"-> ${total_cost:.2f}"
                )
                # Cache hit rate: reads / (reads + fresh context written or sent)
                # High hit rate = efficient re-use of cached prompt prefix.
                # Surfaced explicitly so Gemini can reference it in cost_efficiency grading
                # without re-deriving from raw numbers.
                cache_denominator = cr_tok + cw_tok + in_tok
                if cache_denominator > 0:
                    hit_rate = 100.0 * cr_tok / cache_denominator
                    sections.append(f"- Cache hit rate: {hit_rate:.1f}%")

            # --- Time to first token -------------------------------------
            if ttft_ms is not None:
                sections.append(f"- Time to first token: {ttft_ms/1000:.1f}s")

            # --- Retries --------------------------------------------------
            if retries:
                first5 = "; ".join(
                    f"{r.get('tool_name','?')} × {r.get('cause','?')}"
                    for r in retries[:5]
                )
                sections.append(f"- Retries: {len(retries)} ({first5})")

            # --- Tool completeness ---------------------------------------
            if any_completeness:
                total_calls = len(calls)
                by_status: dict[str, list[str]] = {}
                for c in calls:
                    st = c.get("completeness")
                    if not st:
                        continue
                    by_status.setdefault(st, []).append(c.get("tool", "?"))
                full_n = len(by_status.get("full", []))
                empty_tools = by_status.get("empty", [])
                trunc_tools = by_status.get("truncated", [])
                parts = [f"{full_n}/{total_calls} full"]
                if empty_tools:
                    parts.append(f"{len(empty_tools)} empty ({', '.join(sorted(set(empty_tools)))})")
                if trunc_tools:
                    parts.append(f"{len(trunc_tools)} truncated ({', '.join(sorted(set(trunc_tools)))})")
                sections.append("- Tool completeness: " + ", ".join(parts))

            # --- Compliance gate -----------------------------------------
            if compliance_traces:
                extracted = sum(1 for cg in compliance_traces if cg.get("status") == "extracted")
                attempted = [cg for cg in compliance_traces if cg.get("status") == "attempted"]
                total_cg = len(compliance_traces)
                # Build id -> tool lookup so attempted_tool_use_ids render as tool names
                id_to_tool: dict[str, str] = {}
                for t in turns:
                    # TurnEvent only records ids, not tool names, so we need
                    # to map via tool_calls if they exposed tool_use_id. If
                    # not, fall back to raw ids.
                    pass
                # Many ToolEvidence payloads don't carry tool_use_id; do best-
                # effort by treating the IDs as opaque strings.
                detail_bits = []
                for cg in attempted[:5]:
                    tools_tried = cg.get("attempted_tool_use_ids") or []
                    # Show at most 3 IDs, rendered compactly
                    tries = ", ".join(str(x) for x in tools_tried[:3]) or "no tools"
                    note = cg.get("note", "")
                    detail_bits.append(
                        f"{cg.get('metric','?')}: tried {tries}"
                        + (f", {note}" if note else "")
                    )
                head = f"- Compliance gate: {extracted}/{total_cg} metrics extracted; {len(attempted)} attempted"
                if detail_bits:
                    head += " (" + " | ".join(detail_bits) + ")"
                sections.append(head)

            # --- Source data quality (degraded tools only) ----------------
            degraded_bits: list[str] = []
            for c in calls:
                meta = c.get("extraction_meta") or {}
                if not isinstance(meta, dict):
                    continue
                ext_status = meta.get("extraction_status")
                degraded_flag = meta.get("degraded_quality")
                missing = meta.get("missing_periods") or []
                is_degraded = (
                    (ext_status and ext_status not in ("full", "ok"))
                    or degraded_flag
                    or missing
                )
                if is_degraded:
                    bit = f"{c.get('tool','?')}: extraction_status={ext_status or 'unknown'}"
                    if missing:
                        bit += f", missing={missing}"
                    degraded_bits.append(bit)
            if degraded_bits:
                sections.append("- Source data quality: " + "; ".join(degraded_bits))

            # --- Tools available / called (for "did they call X?") ------
            sections.append(f"- Tools available ({len(available)}): {', '.join(sorted(available))}")
            sections.append(f"- Tools called ({len(calls)} calls): {', '.join(sorted(called))}")
            if unused:
                sections.append(f"- Tools NEVER called: {', '.join(unused)}")
            if errors:
                sections.append(f"- Tool errors ({len(errors)}):")
                for e in errors:
                    sections.append(
                        f"  - {e.get('tool','?')}({e.get('args',{})}) -> ERROR: "
                        f"{(e.get('result_summary','') or '')[:200]}"
                    )

            # --- Status --------------------------------------------------
            status = agent_trace.get("status", "unknown")
            if status != "success":
                sections.append(f"- Agent status: {status}")

            # --- Interleaved turn-level reasoning + tool calls -----------
            if turns or any_turn_index:
                sections.append("Tool calls (interleaved with reasoning):")
                # Build turn -> calls index
                calls_by_turn: dict[int, list[dict]] = {}
                for c in calls:
                    ti = c.get("turn_index")
                    if ti is None:
                        continue
                    calls_by_turn.setdefault(int(ti), []).append(c)
                # Emit per turn (ordered by turn_index on turns list, else by calls keys)
                turn_indices = [t.get("turn_index") for t in turns] or sorted(calls_by_turn.keys())
                for ti in turn_indices:
                    if ti is None:
                        continue
                    ti = int(ti)
                    # Find matching turn
                    t = next((t for t in turns if t.get("turn_index") == ti), None)
                    reasoning_bit = ""
                    if t is not None:
                        rc = t.get("reasoning_chars", 0)
                        if rc:
                            reasoning_bit = f"[reason {rc} chars] "
                    turn_calls = calls_by_turn.get(ti, [])
                    if not turn_calls:
                        sections.append(f"  Turn {ti}: {reasoning_bit}(no tool calls)")
                        continue
                    for c in turn_calls:
                        extras = []
                        if c.get("completeness"):
                            extras.append(str(c["completeness"]))
                        if c.get("row_count") is not None:
                            extras.append(f"{c['row_count']} rows")
                        if c.get("duration_ms"):
                            extras.append(f"{c['duration_ms']/1000:.1f}s")
                        extras_str = f" [{', '.join(extras)}]" if extras else ""
                        args_str = str(c.get("args", {}))
                        if len(args_str) > 80:
                            args_str = args_str[:77] + "..."
                        sections.append(
                            f"  Turn {ti}: {reasoning_bit}-> {c.get('tool','?')}({args_str}){extras_str}"
                        )
                        reasoning_bit = ""  # only prefix first call per turn

            return f"## {header}\n" + "\n".join(sections)

        # --- Legacy (old-style) flat rendering from AgentTrace -----------
        sections.append(f"Tools available ({len(available)}): {', '.join(sorted(available))}")
        sections.append(f"Tools called ({len(calls)} calls): {', '.join(sorted(called))}")
        if unused:
            sections.append(f"Tools NEVER called: {', '.join(unused)}")
        if errors:
            sections.append(f"Tool errors ({len(errors)}):")
            for e in errors:
                sections.append(
                    f"  - {e.get('tool','?')}({e.get('args',{})}) → ERROR: "
                    f"{(e.get('result_summary','') or '')[:200]}"
                )
        cost = agent_trace.get("cost") or {}
        if cost:
            sections.append(
                f"Cost: ${cost.get('total_cost_usd', 0):.2f}, "
                f"tokens: {cost.get('input_tokens', 0)}in/{cost.get('output_tokens', 0)}out, "
                f"duration: {agent_trace.get('duration_seconds', 0):.0f}s, "
                f"model: {cost.get('model', 'unknown')}"
            )
        status = agent_trace.get("status", "unknown")
        if status != "success":
            sections.append(f"Agent status: {status}")

        return "## Agent Execution Log\n" + "\n".join(sections)

    # -------------------------------------------------------------------
    # Legacy evidence + briefing fallback
    # -------------------------------------------------------------------
    if legacy_evidence:
        tools_called = [e.get("tool", "?") for e in legacy_evidence]
        errors = [e for e in legacy_evidence if e.get("is_error")]
        sections.append(f"Tools called ({len(legacy_evidence)} total): {', '.join(tools_called)}")
        if errors:
            sections.append(f"Tool errors ({len(errors)}):")
            for e in errors:
                sections.append(
                    f"  - {e.get('tool','?')}({e.get('args',{})}) → ERROR: "
                    f"{(e.get('result_summary','') or '')[:200]}"
                )

    if legacy_briefing:
        cost = legacy_briefing.get("cost") or {}
        if cost:
            sections.append(
                f"Cost: ${cost.get('total_cost_usd', 0):.2f}, "
                f"tokens: {cost.get('input_tokens', 0)}in/{cost.get('output_tokens', 0)}out, "
                f"duration: {cost.get('duration_seconds', 0):.0f}s, "
                f"model: {cost.get('model', 'unknown')}"
            )
        status = legacy_briefing.get("status", "unknown")
        if status != "success":
            sections.append(f"Agent status: {status} — {legacy_briefing.get('failure_reason', '')}")

    if not sections:
        return ""
    return "## Agent Execution Log\n" + "\n".join(sections)


def read_agent_evidence(agent: str, stock: str) -> str:
    """Read the agent's execution trace and format as context for the evaluator.

    Loads from the AgentTrace (preferred, includes tools_available + unused tools
    plus turn-level telemetry) or falls back to legacy evidence JSON. Returns a
    human-readable summary that helps the evaluator distinguish PROMPT_FIX from
    DATA_FIX issues and judge process quality.

    Thin wrapper: does all IO, then delegates formatting to format_agent_evidence.
    """
    vault_base = Path.home() / "vault" / "stocks" / stock

    # Try AgentTrace first (from pipeline traces — newest file)
    traces_dir = vault_base / "traces"
    if traces_dir.exists():
        trace_files = sorted(traces_dir.glob("*.json"), reverse=True)
        for tf in trace_files[:3]:  # check last 3 traces
            try:
                pipeline = json.loads(tf.read_text())
                agent_trace = pipeline.get("agents", {}).get(agent)
                if not agent_trace:
                    continue
                return format_agent_evidence(agent, stock, agent_trace=agent_trace)
            except (json.JSONDecodeError, KeyError):
                continue

    # Fallback to legacy evidence + briefing files
    legacy_evidence: list | None = None
    legacy_briefing: dict | None = None

    evidence_path = vault_base / "evidence" / f"{agent}.json"
    briefing_path = vault_base / "briefings" / f"{agent}.json"

    if evidence_path.exists():
        try:
            legacy_evidence = json.loads(evidence_path.read_text())
        except (json.JSONDecodeError, KeyError):
            legacy_evidence = None

    if briefing_path.exists():
        try:
            legacy_briefing = json.loads(briefing_path.read_text())
        except (json.JSONDecodeError, KeyError):
            legacy_briefing = None

    return format_agent_evidence(
        agent, stock,
        legacy_evidence=legacy_evidence,
        legacy_briefing=legacy_briefing,
    )


async def eval_with_gemini(agent: str, stock: str, sector_type: str, report_md: str, evidence_context: str = "") -> AgentEvalResult:
    """Send report to Gemini for grading. Returns structured eval result."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("ERROR: google-genai not installed. Run: uv sync --extra autoeval", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        # Try loading from .env file
        env_path = Path.home() / ".config" / "flowtracker" / "gemini.env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        print("ERROR: No Gemini API key found. Set GEMINI_API_KEY env var or create ~/.config/flowtracker/gemini.env", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    system_prompt = EVAL_SYSTEM_TEMPLATE.format(
        sector_type=sector_type,
        agent=agent,
        stock=stock,
    )

    user_prompt = (
        f"## Evaluation Request\n"
        f"Agent: {agent}\n"
        f"Stock: {stock}\n"
        f"Sector: {sector_type}\n\n"
        f"## Report\n\n{report_md}"
    )
    if evidence_context:
        user_prompt += f"\n\n---\n\n{evidence_context}"

    # Truncate very long reports to stay within limits
    if len(user_prompt) > 100_000:
        user_prompt = user_prompt[:100_000] + "\n\n[Report truncated at 100K chars]"

    start = time.monotonic()
    try:
        response = await client.aio.models.generate_content(
            model="gemini-3.1-pro-preview",
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                thinking_config=types.ThinkingConfig(thinking_budget=65_535),
                temperature=0.1,  # near-deterministic grading
            ),
        )
        eval_duration = time.monotonic() - start
        raw_text = response.text or ""
    except Exception as exc:
        eval_duration = time.monotonic() - start
        print(f"  [ERROR] Gemini eval failed for {agent}/{stock}: {exc}", file=sys.stderr)
        return AgentEvalResult(
            agent=agent, stock=stock, sector=sector_type,
            grade="ERR", grade_numeric=0,
            summary=f"Gemini eval failed: {exc}",
            eval_duration_s=eval_duration,
            raw_gemini_response=str(exc),
        )

    # Parse JSON from response
    parsed = _extract_json(raw_text)
    if not parsed:
        return AgentEvalResult(
            agent=agent, stock=stock, sector=sector_type,
            grade="ERR", grade_numeric=0,
            summary=f"Could not parse Gemini JSON response",
            eval_duration_s=eval_duration,
            raw_gemini_response=raw_text[:2000],
        )

    issues = [
        EvalIssue(
            type=i.get("type", "NOT_OUR_PROBLEM"),
            section=i.get("section", ""),
            issue=i.get("issue", ""),
            suggestion=i.get("suggestion", ""),
        )
        for i in parsed.get("issues", [])
    ]

    # Extract overall grade (new format nests under "overall", fallback to flat)
    overall = parsed.get("overall", {})
    grade = overall.get("grade") or parsed.get("grade", "F")
    grade_numeric = overall.get("grade_numeric") or parsed.get("grade_numeric") or GRADE_MAP.get(grade, 50)

    # Extract per-parameter grades
    parameters: dict[str, ParameterGrade] = {}
    for param_name, param_data in parsed.get("parameters", {}).items():
        if isinstance(param_data, dict):
            parameters[param_name] = ParameterGrade(
                grade=param_data.get("grade", ""),
                numeric=param_data.get("numeric", 0),
                rationale=param_data.get("rationale", ""),
            )

    return AgentEvalResult(
        agent=agent,
        stock=stock,
        sector=sector_type,
        grade=grade,
        grade_numeric=grade_numeric,
        parameters=parameters,
        issues=issues,
        strengths=parsed.get("strengths", []),
        summary=parsed.get("summary", ""),
        report_length=len(report_md),
        eval_duration_s=eval_duration,
        raw_gemini_response=raw_text[:3000],
    )


def _extract_json(text: str) -> dict | None:
    """Extract JSON from Gemini response (may be wrapped in markdown fences)."""
    import re
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Strip markdown fences
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Find first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass
    return None


def write_last_run(result: LastRunResult) -> None:
    """Write last_run.json (latest) and archive a timestamped copy.

    last_run.json is the working file the orchestrator reads.
    eval_history/{timestamp}_{sector}.json is the permanent archive.
    """
    base = Path(__file__).parent

    # Archive — never overwritten
    history_dir = base / "eval_history"
    history_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    sector_tag = result.sector.replace("/", "_")
    archive_path = history_dir / f"{ts}_{sector_tag}.json"

    out_path = base / "last_run.json"
    # Convert dataclasses to dicts
    data = {
        "sector": result.sector,
        "stock": result.stock,
        "timestamp": result.timestamp,
        "all_passing": result.all_passing,
        "failing_agents": result.failing_agents,
        "results": {
            name: asdict(r) for name, r in result.results.items()
        },
    }
    payload = json.dumps(data, indent=2, default=str)
    out_path.write_text(payload)
    archive_path.write_text(payload)
    print(f"\nWrote: {out_path}")
    print(f"Archived: {archive_path}")


def append_results_tsv(results: dict[str, AgentEvalResult], sector: str, cycle: int = 0) -> None:
    """Append results to results.tsv."""
    tsv_path = Path(__file__).parent / "results.tsv"
    write_header = not tsv_path.exists()

    with open(tsv_path, "a") as f:
        if write_header:
            f.write("timestamp\tcycle\tagent\tstock\tsector\tgrade\tgrade_numeric\treport_len\trun_s\teval_s\tprompt_fixes\tnotes\n")
        for name, r in results.items():
            prompt_fixes = sum(1 for i in r.issues if i.type == "PROMPT_FIX")
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(f"{ts}\t{cycle}\t{r.agent}\t{r.stock}\t{sector}\t{r.grade}\t{r.grade_numeric}\t{r.report_length}\t{r.run_duration_s:.1f}\t{r.eval_duration_s:.1f}\t{prompt_fixes}\t{r.summary[:100]}\n")


def append_fix_tracker(results: dict[str, AgentEvalResult], sector: str, cycle: int = 0) -> None:
    """Append all issues from eval results to fix_tracker.md."""
    tracker_path = Path(__file__).parent / "fix_tracker.md"
    if not tracker_path.exists():
        return

    # Read existing to determine next ID
    existing = tracker_path.read_text()
    existing_lines = [l for l in existing.splitlines() if l.startswith("| ") and not l.startswith("| ID") and not l.startswith("| -")]
    next_id = len(existing_lines) + 1

    lines = []
    for _name, r in results.items():
        for issue in r.issues:
            # Escape pipes in text fields
            section = issue.section.replace("|", "/")
            desc = issue.issue.replace("|", "/").replace("\n", " ")[:150]
            suggestion = issue.suggestion.replace("|", "/").replace("\n", " ")[:150]
            lines.append(
                f"| {next_id} | {r.agent} | {sector} | {r.stock} | {cycle} | {issue.type} | "
                f"{section} | {desc} | {suggestion} | pending | | |"
            )
            next_id += 1

    if lines:
        with open(tracker_path, "a") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Appended {len(lines)} fixes to fix_tracker.md (IDs {next_id - len(lines)}-{next_id - 1})")


def print_summary(results: dict[str, AgentEvalResult], target_numeric: int = 90) -> None:
    """Print greppable summary with per-parameter breakdown."""
    total = len(results)
    passing = sum(1 for r in results.values() if r.grade_numeric >= target_numeric)
    failing = total - passing

    PARAM_SHORT = {
        "analytical_depth": "Depth",
        "logical_consistency": "Logic",
        "completeness": "Complete",
        "actionability": "Action",
        "sector_framework": "Sector",
        "data_sourcing": "Data",
        "tool_use_discipline": "Tools",
        "cost_efficiency": "Cost",
    }

    print(f"\n{'='*90}")
    print(f"EVAL SUMMARY")
    print(f"{'='*90}")
    header = f"  {'Name':12s}  {'Overall':8s}  " + "  ".join(f"{v:8s}" for v in PARAM_SHORT.values()) + "  Fixes"
    print(header)
    print(f"  {'-'*12}  {'-'*8}  " + "  ".join("-"*8 for _ in PARAM_SHORT) + "  -----")
    for name, r in sorted(results.items()):
        status = "PASS" if r.grade_numeric >= target_numeric else "FAIL"
        prompt_fixes = sum(1 for i in r.issues if i.type == "PROMPT_FIX")
        overall = f"{r.grade:3s}({r.grade_numeric:2d})"
        params = []
        for pk in PARAM_SHORT:
            pg = r.parameters.get(pk)
            if pg:
                params.append(f"{pg.grade:3s}({pg.numeric:2d})")
            else:
                params.append("  ---  ")
        param_str = "  ".join(f"{p:8s}" for p in params)
        print(f"  {name:12s}  {overall:8s}  {param_str}  {prompt_fixes} [{status}]")
    print(f"{'='*90}")
    print(f"passing:{passing}  failing:{failing}  total:{total}")
    print(f"{'='*90}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def _eval_sector(agent: str, sector_name: str, sector_cfg: dict,
                       target_numeric: int, skip_run: bool, cycle: int) -> AgentEvalResult:
    """Run and eval a single agent for a single sector. Returns AgentEvalResult."""
    stock = sector_cfg["stock"]
    sector_type = sector_cfg["type"]

    print(f"--- {agent} / {stock} ({sector_name}) ---")

    # Step 1: Run agent (unless --skip-run)
    run_duration = 0.0
    run_skipped = skip_run
    if not skip_run:
        print(f"  Running agent...")
        run_duration, success = run_agent(agent, stock)
        print(f"  Agent completed in {run_duration:.1f}s (success={success})")
        if not success:
            return AgentEvalResult(
                agent=agent, stock=stock, sector=sector_type,
                grade="ERR", grade_numeric=0,
                summary="Agent run failed",
                run_duration_s=run_duration,
            )

    # Step 2: Read report
    report_md = read_report(agent, stock)
    if not report_md:
        print(f"  [WARN] No report found for {agent}/{stock}")
        return AgentEvalResult(
            agent=agent, stock=stock, sector=sector_type,
            grade="ERR", grade_numeric=0,
            summary="No report file found",
        )
    print(f"  Report: {len(report_md)} chars")

    # Step 3: Load agent execution evidence
    evidence = read_agent_evidence(agent, stock)
    if evidence:
        print(f"  Evidence log loaded ({evidence.count(chr(10))} lines)")

    # Step 4: Grade with Gemini (report + evidence)
    print(f"  Grading with Gemini...")
    eval_result = await eval_with_gemini(agent, stock, sector_type, report_md, evidence)
    eval_result.run_duration_s = run_duration
    eval_result.run_skipped = run_skipped
    eval_result.report_length = len(report_md)

    status = "PASS" if eval_result.grade_numeric >= target_numeric else "FAIL"
    print(f"  Grade: {eval_result.grade} ({eval_result.grade_numeric}) [{status}]")
    return eval_result


async def async_main_sector(args: argparse.Namespace) -> None:
    """Original mode: one sector, multiple agents."""
    matrix = load_matrix()

    sector_cfg = matrix["sectors"].get(args.sector)
    if not sector_cfg:
        print(f"ERROR: Unknown sector '{args.sector}'. Available: {list(matrix['sectors'].keys())}", file=sys.stderr)
        sys.exit(1)

    target_numeric = matrix.get("target_grade_numeric", 90)

    # Determine which agents to eval
    if args.agents:
        agent_names = [a.strip() for a in args.agents.split(",")]
    else:
        agent_names = matrix.get("agents", ["business", "financials", "ownership", "valuation", "risk", "technical", "sector"])

    print(f"AutoEval: sector={args.sector} stock={sector_cfg['stock']} agents={agent_names}")
    print(f"Target: grade_numeric >= {target_numeric}")
    print()

    results: dict[str, AgentEvalResult] = {}
    for agent in agent_names:
        results[agent] = await _eval_sector(agent, args.sector, sector_cfg, target_numeric, args.skip_run, args.cycle)

    # Build last_run result
    failing = [name for name, r in results.items() if r.grade_numeric < target_numeric]
    last_run = LastRunResult(
        sector=args.sector,
        stock=sector_cfg["stock"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        results=results,
        all_passing=len(failing) == 0,
        failing_agents=failing,
    )

    write_last_run(last_run)
    append_results_tsv(results, args.sector, cycle=args.cycle)
    append_fix_tracker(results, args.sector, cycle=args.cycle)
    print_summary(results, target_numeric)


async def async_main_agent(args: argparse.Namespace) -> None:
    """Agent-first mode: one agent across all (or specified) sectors."""
    matrix = load_matrix()
    agent = args.agent
    target_numeric = matrix.get("target_grade_numeric", 90)

    # Determine which sectors to eval
    if args.sectors:
        sector_names = [s.strip() for s in args.sectors.split(",")]
    else:
        sector_names = list(matrix["sectors"].keys())

    print(f"AutoEval (agent-first): agent={agent} sectors={sector_names}")
    print(f"Target: grade_numeric >= {target_numeric}")
    print()

    results: dict[str, AgentEvalResult] = {}  # keyed by sector name
    for sector_name in sector_names:
        sector_cfg = matrix["sectors"].get(sector_name)
        if not sector_cfg:
            print(f"  [WARN] Unknown sector '{sector_name}', skipping")
            continue
        result = await _eval_sector(agent, sector_name, sector_cfg, target_numeric, args.skip_run, args.cycle)
        results[sector_name] = result
        # Append per-sector as we go (don't wait till end)
        append_results_tsv({agent: result}, sector_name, cycle=args.cycle)
        append_fix_tracker({agent: result}, sector_name, cycle=args.cycle)
        print()

    # Build last_run keyed by sector (not agent)
    failing = [name for name, r in results.items() if r.grade_numeric < target_numeric]
    last_run = LastRunResult(
        sector=f"all_for_{agent}",
        stock="(multiple)",
        timestamp=datetime.now(timezone.utc).isoformat(),
        results=results,
        all_passing=len(failing) == 0,
        failing_agents=failing,  # actually failing sectors
    )
    write_last_run(last_run)

    # Print agent-focused summary
    print(f"\n{'='*70}")
    print(f"AGENT SUMMARY: {agent}")
    print(f"{'='*70}")
    for sector_name in sector_names:
        r = results.get(sector_name)
        if not r:
            continue
        status = "PASS" if r.grade_numeric >= target_numeric else "FAIL"
        prompt_fixes = sum(1 for i in r.issues if i.type == "PROMPT_FIX")
        print(f"  {sector_name:18s}  {r.stock:12s}  {r.grade:3s} ({r.grade_numeric:2d})  [{status}]  prompt_fixes:{prompt_fixes}")
    print(f"{'='*70}")
    print(f"passing:{len(sector_names) - len(failing)}  failing:{len(failing)}  total:{len(sector_names)}")
    print(f"{'='*70}")


def _setup_run_log() -> Path:
    """Set up tee-style logging — stdout/stderr go to both console and run log file."""
    import io

    log_dir = Path(__file__).parent / "run_logs"
    log_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_path = log_dir / f"{ts}.log"

    class TeeWriter(io.TextIOBase):
        """Write to both the original stream and a log file."""

        def __init__(self, original: object, log_file: object) -> None:
            self._original = original
            self._log_file = log_file

        def write(self, s: str) -> int:
            self._original.write(s)
            self._log_file.write(s)
            self._log_file.flush()
            return len(s)

        def flush(self) -> None:
            self._original.flush()
            self._log_file.flush()

    log_file = open(log_path, "w")  # noqa: SIM115
    sys.stdout = TeeWriter(sys.__stdout__, log_file)  # type: ignore[assignment]
    sys.stderr = TeeWriter(sys.__stderr__, log_file)  # type: ignore[assignment]

    print(f"Run log: {log_path}")
    return log_path


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoEval — Gemini eval harness")

    # Mode selection: --sector (sector-first) or --agent (agent-first)
    parser.add_argument("--sector", default=None, help="Sector-first mode: evaluate one sector (e.g., bfsi)")
    parser.add_argument("--agent", default=None, help="Agent-first mode: evaluate one agent across sectors (e.g., business)")
    parser.add_argument("--agents", default=None, help="Comma-separated agent names (sector-first mode)")
    parser.add_argument("--sectors", default=None, help="Comma-separated sector names (agent-first mode, default: all)")
    parser.add_argument("--skip-run", action="store_true", help="Skip agent runs, grade existing reports only")
    parser.add_argument("--cycle", type=int, default=0, help="Cycle number for results.tsv logging")
    args = parser.parse_args()

    _setup_run_log()

    if args.agent:
        asyncio.run(async_main_agent(args))
    elif args.sector:
        asyncio.run(async_main_sector(args))
    else:
        print("ERROR: Specify --agent (agent-first) or --sector (sector-first)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
