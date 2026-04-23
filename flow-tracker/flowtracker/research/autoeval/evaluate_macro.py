#!/usr/bin/env python3
"""AutoEval — Macro Agent (Part 3 Tier 1).

Parallel to evaluate.py but scoped to the macro specialist, which the
specialist harness can't grade because (a) it's sector-agnostic and (b) its
output is market-wide regime state, not per-stock domain analysis.

Design choices:
  * Flat date matrix (eval_matrix_macro.yaml) — no sector × stock dimension.
    Macro state changes slowly; 4-6 eval points per quarter is enough.
  * Anchor-exhaustion is fetched live from ``get_macro_catalog`` BEFORE
    grading. The expected anchor list is injected into the Gemini prompt
    so the grader can check every ``status='complete'`` anchor was drilled
    in the report.
  * Rubric dimensions (5): anchor_exhaustion, trajectory_check, fact_view,
    india_transmission, stale_policy.
  * Reuses GRADE_MAP and _extract_json from evaluate.py — it's IMMUTABLE
    by convention, so we import its helpers rather than duplicating them.
  * Writes to ``results_macro.tsv`` so it doesn't pollute the specialist
    ``results.tsv`` that is graphed by progress tooling.

Usage:
    uv run python flowtracker/research/autoeval/evaluate_macro.py
    uv run python flowtracker/research/autoeval/evaluate_macro.py --dates 2025-11-01
    uv run python flowtracker/research/autoeval/evaluate_macro.py --skip-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from flowtracker.research.autoeval.evaluate import (
    GRADE_MAP,
    AgentEvalResult,
    EvalIssue,
    ParameterGrade,
    _extract_json,
)


MACRO_MATRIX_PATH = Path(__file__).parent / "eval_matrix_macro.yaml"
MACRO_RESULTS_TSV = Path(__file__).parent / "results_macro.tsv"


# ---------------------------------------------------------------------------
# Rubric — macro-specific, not a template over the specialist rubric
# ---------------------------------------------------------------------------

MACRO_EVAL_SYSTEM = """You are a senior macro strategist with 20 years covering Indian and global macro for institutional investors. Grade this AI-generated macro regime report.

Unlike the specialist rubric (which checks sector-framework coverage), the macro rubric checks **regime-reasoning discipline and anchor grounding**. The agent is expected to anchor every secular/cyclical claim to an official India anchor doc (Economic Survey, RBI Annual Report, RBI MPR, Union Budget) and every global claim to a named central bank decision or IMF publication. The regime output feeds synthesis as a macro prior; sloppy anchor citations poison downstream calibration.

## Evaluation Parameters (grade each independently A+ through F)

1. **Anchor Exhaustion** — For every anchor marked ``status='complete'`` in the catalog, did the report either (a) drill into it with an inline citation, OR (b) explicitly null-finding ("RBI Annual Report FY26 reviewed — no regime-relevant disclosures beyond already-cited rate stance")? Silently skipping a completed anchor is a hard fail. The expected anchor list is provided below under "Complete Anchors".

2. **Trajectory-Check Discipline** — Every ``SECULAR``-tagged theme must be backed by ≥2 anchor publications across time (e.g., Economic Survey FY24 + FY25 both identify manufacturing formalization; ONE source = cyclical by default). Every ``CYCLICAL``-tagged theme must explicitly cite the current stance (not a 6-month-old decision).

3. **FACT/VIEW Separation** — Every bullet must be prefixed FACT: or VIEW:. Every FACT must have an inline URL or (source: ...) citation + publication date. VIEWs must flag themselves as inferred, not sourced. Mixing them is editorial noise dressed as data.

4. **India Transmission** — Every global claim (Fed stance, oil regime, China slowdown) must be followed by a specific INR-denominated second-order transmission effect (USD/INR, crude-import bill, FII flow, rupee liquidity). A report that cites "Fed hiking" without naming the transmission is half-finished.

5. **Stale-Policy Defense** — Does the report cite the MOST RECENT Fed/ECB/RBI/PBOC decision, or a stale prior one? Today's date is provided; any central bank claim older than 60 days without a "pending next decision" qualifier is a stale-policy fail.

## Grade Scale
A+ (97) = Institutional — sent to a macro PM without edits
A  (93) = Strong — minor polish needed
A- (90) = Good — 1-2 meaningful gaps
B+ (87) = Usable — clear improvements needed but core reasoning solid
B  (83) = Below bar — recurring anchor or transmission gaps
C  (73) = Poor — major rubric failures across 2+ dimensions
F  (50) = Structural failure — agent editorialized, skipped anchors, or ran stale policy

## Input Payload

**Report**: the macro agent's markdown output.
**Complete Anchors** (expected to be drilled or null-findinged): {anchor_list}
**Today's date (as-of for stale-policy check)**: {as_of_date}

## Required Output

Return ONLY this JSON structure, no preamble or commentary:

```json
{{
  "grade": "<A+|A|A-|B+|B|B-|C+|C|C-|D+|D|D-|F>",
  "grade_numeric": <50-97>,
  "parameters": {{
    "anchor_exhaustion":    {{"grade": "<letter>", "numeric": <int>, "rationale": "<1-2 sentences>"}},
    "trajectory_check":     {{"grade": "<letter>", "numeric": <int>, "rationale": "<1-2 sentences>"}},
    "fact_view":            {{"grade": "<letter>", "numeric": <int>, "rationale": "<1-2 sentences>"}},
    "india_transmission":   {{"grade": "<letter>", "numeric": <int>, "rationale": "<1-2 sentences>"}},
    "stale_policy":         {{"grade": "<letter>", "numeric": <int>, "rationale": "<1-2 sentences>"}}
  }},
  "issues": [
    {{"type": "PROMPT_FIX|DATA_FIX|COMPUTATION|NOT_OUR_PROBLEM",
      "section": "<section name>",
      "issue": "<1 sentence>",
      "suggestion": "<1 sentence>"}}
  ],
  "strengths": ["<1 line>", "<1 line>"],
  "summary": "<2-3 sentences — overall verdict>"
}}
```
"""


def load_macro_matrix() -> dict:
    with open(MACRO_MATRIX_PATH) as f:
        return yaml.safe_load(f)


def fetch_anchor_catalog() -> list[str]:
    """Return the list of ``status='complete'`` anchors from get_macro_catalog.

    Used to populate the rubric's anchor-exhaustion expected list at eval
    time. Returning an empty list when the tool is unavailable is safe —
    the grader falls back to generic anchor-class coverage.
    """
    from flowtracker.research.data_api import ResearchDataAPI

    try:
        api = ResearchDataAPI()
        catalog = api.get_macro_catalog()
    except Exception as exc:
        print(f"  [WARN] get_macro_catalog failed: {exc}", file=sys.stderr)
        return []

    anchors = catalog.get("anchors") if isinstance(catalog, dict) else catalog or []
    completed: list[str] = []
    for a in anchors:
        if not isinstance(a, dict):
            continue
        if a.get("status") == "complete":
            name = a.get("name") or a.get("title") or a.get("id")
            if name:
                completed.append(str(name))
    return completed


def run_macro_agent(as_of_date: str, placeholder_symbol: str) -> tuple[float, bool]:
    """Invoke the macro agent via CLI for the given as-of date.

    The CLI doesn't take --as-of today, so this runs macro against the live
    system date. For backdated eval points (the common case in this matrix)
    callers should document that the grade reflects agent behavior at the
    wall-clock eval time, not a simulated as-of. A proper as-of harness is
    a Phase 2 upgrade.
    """
    cwd = Path(__file__).resolve().parents[3]
    start = time.monotonic()
    proc = subprocess.Popen(
        ["uv", "run", "flowtrack", "research", "run", "macro", "-s", placeholder_symbol],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        while proc.poll() is None:
            line = proc.stderr.readline()
            if line:
                print(f"  {line.rstrip()}", file=sys.stderr)
            if time.monotonic() - start > 1800:
                proc.kill()
                proc.wait()
                return time.monotonic() - start, False
        for line in proc.stderr:
            print(f"  {line.rstrip()}", file=sys.stderr)
    except Exception as exc:
        print(f"  [WARN] macro run failed: {exc}", file=sys.stderr)
        return time.monotonic() - start, False

    return time.monotonic() - start, proc.returncode == 0


def read_macro_report(placeholder_symbol: str) -> str:
    path = Path.home() / "vault" / "stocks" / placeholder_symbol / "reports" / "macro.md"
    if not path.exists():
        return ""
    return path.read_text()


async def eval_macro_report(
    as_of_date: str,
    report_md: str,
    anchors: list[str],
) -> AgentEvalResult:
    """Grade a macro report with the macro-specific rubric."""
    from claude_agent_sdk import query, ClaudeAgentOptions

    anchor_list = ", ".join(anchors) if anchors else "(catalog returned no complete anchors — fall back to coverage of: Economic Survey, RBI Annual Report, RBI MPR, Union Budget)"
    system_prompt = MACRO_EVAL_SYSTEM.format(
        anchor_list=anchor_list, as_of_date=as_of_date,
    )
    user_prompt = f"## Report to Grade (macro, as-of {as_of_date})\n\n{report_md}"

    t0 = time.monotonic()
    opts = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model="gemini-3.1-pro-preview",
        setting_sources=[],
        plugins=[],
    )

    raw = ""
    try:
        async for msg in query(prompt=user_prompt, options=opts):
            text = getattr(msg, "content", None) or getattr(msg, "text", "") or ""
            if isinstance(text, list):
                text = "".join(str(c) for c in text)
            raw += str(text)
    except Exception as exc:
        return AgentEvalResult(
            agent="macro", stock="NIFTY", sector="_macro_",
            grade="ERR", grade_numeric=0,
            summary=f"Gemini grading failed: {exc}",
            eval_duration_s=time.monotonic() - t0,
            raw_gemini_response=raw,
        )

    parsed = _extract_json(raw)
    if not parsed:
        return AgentEvalResult(
            agent="macro", stock="NIFTY", sector="_macro_",
            grade="ERR", grade_numeric=0,
            summary="Gemini returned no parseable JSON",
            eval_duration_s=time.monotonic() - t0,
            raw_gemini_response=raw,
        )

    params = {
        name: ParameterGrade(grade=v["grade"], numeric=v["numeric"], rationale=v["rationale"])
        for name, v in (parsed.get("parameters") or {}).items()
    }
    issues = [
        EvalIssue(
            type=i.get("type", ""), section=i.get("section", ""),
            issue=i.get("issue", ""), suggestion=i.get("suggestion", ""),
        )
        for i in (parsed.get("issues") or [])
    ]

    return AgentEvalResult(
        agent="macro", stock="NIFTY", sector="_macro_",
        grade=parsed.get("grade", "ERR"),
        grade_numeric=parsed.get("grade_numeric", 0),
        parameters=params, issues=issues,
        strengths=parsed.get("strengths", []),
        summary=parsed.get("summary", ""),
        eval_duration_s=time.monotonic() - t0,
        raw_gemini_response=raw,
    )


def append_macro_tsv(result: AgentEvalResult, as_of_date: str, cycle: int) -> None:
    MACRO_RESULTS_TSV.parent.mkdir(parents=True, exist_ok=True)
    is_new = not MACRO_RESULTS_TSV.exists()
    with open(MACRO_RESULTS_TSV, "a") as f:
        if is_new:
            f.write("timestamp\tcycle\tas_of_date\tgrade\tgrade_numeric\tprompt_fixes\tissues\tsummary\n")
        ts = datetime.now(timezone.utc).isoformat()
        prompt_fixes = sum(1 for i in result.issues if i.type == "PROMPT_FIX")
        issues_count = len(result.issues)
        summary = (result.summary or "").replace("\t", " ").replace("\n", " ")[:300]
        f.write(f"{ts}\t{cycle}\t{as_of_date}\t{result.grade}\t{result.grade_numeric}\t{prompt_fixes}\t{issues_count}\t{summary}\n")


async def _eval_one_date(date_entry: dict, placeholder_symbol: str,
                         skip_run: bool, cycle: int) -> AgentEvalResult:
    as_of_date = date_entry["date"]
    print(f"--- macro / {as_of_date} ({date_entry.get('why', '')}) ---")

    if not skip_run:
        print(f"  Running macro agent...")
        duration, success = run_macro_agent(as_of_date, placeholder_symbol)
        print(f"  Macro completed in {duration:.1f}s (success={success})")
        if not success:
            return AgentEvalResult(
                agent="macro", stock=placeholder_symbol, sector="_macro_",
                grade="ERR", grade_numeric=0, summary="Macro agent run failed",
                run_duration_s=duration,
            )

    report_md = read_macro_report(placeholder_symbol)
    if not report_md:
        return AgentEvalResult(
            agent="macro", stock=placeholder_symbol, sector="_macro_",
            grade="ERR", grade_numeric=0, summary="No macro report found",
        )
    print(f"  Report: {len(report_md)} chars")

    print(f"  Fetching anchor catalog...")
    anchors = fetch_anchor_catalog()
    print(f"  Complete anchors: {len(anchors)}")

    print(f"  Grading with Gemini...")
    result = await eval_macro_report(as_of_date, report_md, anchors)
    print(f"  Grade: {result.grade} ({result.grade_numeric})")
    return result


async def async_main(args: argparse.Namespace) -> None:
    matrix = load_macro_matrix()
    placeholder_symbol = matrix.get("placeholder_symbol", "NIFTY")
    target_numeric = matrix.get("target_grade_numeric", 90)

    if args.dates:
        requested = {d.strip() for d in args.dates.split(",")}
        entries = [e for e in matrix["eval_dates"] if e["date"] in requested]
    else:
        entries = matrix["eval_dates"]

    print(f"Macro AutoEval: {len(entries)} date(s), target_numeric >= {target_numeric}")
    print()

    results: list[AgentEvalResult] = []
    for entry in entries:
        r = await _eval_one_date(entry, placeholder_symbol, args.skip_run, args.cycle)
        results.append(r)
        append_macro_tsv(r, entry["date"], args.cycle)
        print()

    print("=" * 70)
    print("MACRO EVAL SUMMARY")
    print("=" * 70)
    for entry, r in zip(entries, results):
        status = "PASS" if r.grade_numeric >= target_numeric else "FAIL"
        print(f"  {entry['date']:12s}  {r.grade:3s} ({r.grade_numeric:2d})  [{status}]")
    passing = sum(1 for r in results if r.grade_numeric >= target_numeric)
    print(f"passing: {passing}/{len(results)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Macro AutoEval — regime-report grader")
    parser.add_argument("--dates", default=None,
                        help="Comma-separated dates (default: all in eval_matrix_macro.yaml)")
    parser.add_argument("--skip-run", action="store_true",
                        help="Skip macro agent runs, grade existing report only")
    parser.add_argument("--cycle", type=int, default=0, help="Cycle number for results_macro.tsv")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
