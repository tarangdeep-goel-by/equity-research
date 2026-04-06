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
class AgentEvalResult:
    agent: str
    stock: str
    sector: str
    grade: str
    grade_numeric: int
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
EVAL_SYSTEM_TEMPLATE = """You are a senior equity research analyst with 20 years covering Indian {sector_type} companies. Grade this AI-generated {agent} report for {stock}.

Evaluation Criteria:
1. **Analytical Depth** — Does it go beyond surface-level observation? Are the right analytical frameworks applied for this sector?
2. **Logical Consistency** — Do conclusions follow from the data presented? Are there contradictions?
3. **Completeness** — What important dimensions should have been covered but weren't? For this sector type, are the sector-specific metrics and frameworks present?
4. **Actionability** — Does the analysis lead to clear, evidence-backed conclusions?

CRITICAL INSTRUCTIONS:
- Do NOT grade the accuracy of specific numbers (revenue, margins, shareholding percentages, stock prices). Your training data is outdated — the report uses live data that is more current than yours. Focus on whether the right frameworks are applied.
- If a number looks suspicious to you, classify it as "worth verifying" rather than marking it as incorrect.
- Focus on analytical depth, logical consistency, completeness of coverage, and whether the right sector-specific frameworks are applied.

Classify each issue into exactly one of these categories:
- **PROMPT_FIX**: Agent behavior or reasoning issue that can be fixed by editing the agent's instructions (e.g., missing framework, wrong approach, skipped analysis)
- **DATA_FIX**: Missing or broken data in the pipeline (e.g., tool returned empty data, metric not available)
- **COMPUTATION**: Mathematical calculation the LLM did incorrectly (e.g., wrong CAGR formula, flipped margin of safety)
- **NOT_OUR_PROBLEM**: Inherent LLM limitation (e.g., minor hallucination, inconsistent phrasing)

The report may include an **Agent Execution Log** at the end showing which tools were called,
any tool errors, token usage, and duration. Use this to improve your classification:
- If the report is missing analysis AND the agent never called the relevant tool → PROMPT_FIX (add tool call to workflow)
- If the agent called a tool but it returned an error or empty data → DATA_FIX (pipeline issue)
- If the agent ran out of turns/budget → note this, it's a config issue
- If the agent called the right tools but misinterpreted the data → PROMPT_FIX (add interpretation rules)

You MUST respond with valid JSON matching this exact structure:
{{
  "grade": "<letter grade A+ through F>",
  "grade_numeric": <integer 50-97>,
  "issues": [
    {{
      "type": "<PROMPT_FIX|DATA_FIX|COMPUTATION|NOT_OUR_PROBLEM>",
      "section": "<which section of the report>",
      "issue": "<specific description of the problem>",
      "suggestion": "<concrete fix suggestion>"
    }}
  ],
  "strengths": ["<strength 1>", "<strength 2>"],
  "summary": "<2-3 sentence overall assessment>"
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
        timeout=600,  # 10 min max per agent
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

    user_prompt = f"Grade this {agent} agent report for {stock} ({sector_type}):\n\n{report_md}"
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
                thinking_config=types.ThinkingConfig(thinking_budget=65_536),
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

    grade = parsed.get("grade", "F")
    grade_numeric = parsed.get("grade_numeric") or GRADE_MAP.get(grade, 50)

    return AgentEvalResult(
        agent=agent,
        stock=stock,
        sector=sector_type,
        grade=grade,
        grade_numeric=grade_numeric,
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


def print_summary(results: dict[str, AgentEvalResult], target_numeric: int = 90) -> None:
    """Print greppable summary."""
    total = len(results)
    passing = sum(1 for r in results.values() if r.grade_numeric >= target_numeric)
    failing = total - passing

    print(f"\n{'='*60}")
    print(f"EVAL SUMMARY")
    print(f"{'='*60}")
    for name, r in sorted(results.items()):
        status = "PASS" if r.grade_numeric >= target_numeric else "FAIL"
        prompt_fixes = sum(1 for i in r.issues if i.type == "PROMPT_FIX")
        print(f"  {name:12s}  {r.grade:3s} ({r.grade_numeric:2d})  [{status}]  prompt_fixes:{prompt_fixes}")
    print(f"{'='*60}")
    print(f"passing:{passing}  failing:{failing}  total:{total}")
    print(f"{'='*60}")


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

    if args.agent:
        asyncio.run(async_main_agent(args))
    elif args.sector:
        asyncio.run(async_main_sector(args))
    else:
        print("ERROR: Specify --agent (agent-first) or --sector (sector-first)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
