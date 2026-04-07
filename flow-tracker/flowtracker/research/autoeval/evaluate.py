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
- Your **overall grade_numeric** must equal the arithmetic mean of the 6 parameter numeric scores (rounded to nearest integer). Do not inflate the overall above the average.

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
    "data_sourcing": {{"grade": "<A+..F>", "numeric": <50-97>, "rationale": "<1-2 sentences>"}}
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
    """Run a specialist agent via CLI. Returns (duration_seconds, success)."""
    cwd = Path(__file__).resolve().parents[3]  # flow-tracker/
    start = time.monotonic()
    result = subprocess.run(
        ["uv", "run", "flowtrack", "research", "run", agent, "-s", stock],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=900,  # 15 min max per agent
    )
    duration = time.monotonic() - start
    success = result.returncode == 0
    if not success:
        print(f"  [WARN] Agent {agent} failed for {stock}: {result.stderr[:200]}", file=sys.stderr)
    return duration, success


def read_report(agent: str, stock: str) -> str:
    """Read the agent's report markdown."""
    report_path = Path.home() / "vault" / "stocks" / stock / "reports" / f"{agent}.md"
    if not report_path.exists():
        return ""
    return report_path.read_text()


def read_agent_evidence(agent: str, stock: str) -> str:
    """Read the agent's execution trace and format as context for the evaluator.

    Loads from the AgentTrace (preferred, includes tools_available + unused tools)
    or falls back to legacy evidence JSON. Returns a human-readable summary that
    helps the evaluator distinguish PROMPT_FIX from DATA_FIX issues.
    """
    vault_base = Path.home() / "vault" / "stocks" / stock
    sections = []

    # Try AgentTrace first (from pipeline traces — newest file)
    traces_dir = vault_base / "traces"
    trace_loaded = False
    if traces_dir.exists():
        trace_files = sorted(traces_dir.glob("*.json"), reverse=True)
        for tf in trace_files[:3]:  # check last 3 traces
            try:
                pipeline = json.loads(tf.read_text())
                agent_trace = pipeline.get("agents", {}).get(agent)
                if not agent_trace:
                    continue

                # Tools available vs called
                available = set(agent_trace.get("tools_available", []))
                calls = agent_trace.get("tool_calls", [])
                called = set(c["tool"] for c in calls)
                unused = sorted(available - called)
                errors = [c for c in calls if c.get("is_error")]

                sections.append(f"Tools available ({len(available)}): {', '.join(sorted(available))}")
                sections.append(f"Tools called ({len(calls)} calls): {', '.join(sorted(called))}")
                if unused:
                    sections.append(f"Tools NEVER called: {', '.join(unused)}")
                if errors:
                    sections.append(f"Tool errors ({len(errors)}):")
                    for e in errors:
                        sections.append(f"  - {e['tool']}({e.get('args',{})}) → ERROR: {e.get('result_summary','')[:200]}")

                # Cost and status
                cost = agent_trace.get("cost", {})
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

                trace_loaded = True
                break
            except (json.JSONDecodeError, KeyError):
                continue

    # Fallback to legacy evidence + briefing files
    if not trace_loaded:
        evidence_path = vault_base / "evidence" / f"{agent}.json"
        briefing_path = vault_base / "briefings" / f"{agent}.json"

        if evidence_path.exists():
            try:
                evidence = json.loads(evidence_path.read_text())
                tools_called = [e["tool"] for e in evidence]
                errors = [e for e in evidence if e.get("is_error")]
                sections.append(f"Tools called ({len(evidence)} total): {', '.join(tools_called)}")
                if errors:
                    sections.append(f"Tool errors ({len(errors)}):")
                    for e in errors:
                        sections.append(f"  - {e['tool']}({e.get('args',{})}) → ERROR: {e.get('result_summary','')[:200]}")
            except (json.JSONDecodeError, KeyError):
                pass

        if briefing_path.exists():
            try:
                briefing = json.loads(briefing_path.read_text())
                cost = briefing.get("cost", {})
                if cost:
                    sections.append(
                        f"Cost: ${cost.get('total_cost_usd', 0):.2f}, "
                        f"tokens: {cost.get('input_tokens', 0)}in/{cost.get('output_tokens', 0)}out, "
                        f"duration: {cost.get('duration_seconds', 0):.0f}s, "
                        f"model: {cost.get('model', 'unknown')}"
                    )
                status = briefing.get("status", "unknown")
                if status != "success":
                    sections.append(f"Agent status: {status} — {briefing.get('failure_reason', '')}")
            except (json.JSONDecodeError, KeyError):
                pass

    if not sections:
        return ""

    return "## Agent Execution Log\n" + "\n".join(sections)


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
