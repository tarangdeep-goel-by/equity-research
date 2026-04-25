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
import os
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
MACRO_HISTORY_DIR = Path(__file__).parent / "eval_history"
GEMINI_RETRY_ATTEMPTS = 3
GEMINI_RETRY_BACKOFF_S = 30


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


def fetch_anchor_catalog(as_of_date: str | None = None) -> list[str]:
    """Return ``status='complete'`` anchors from get_macro_catalog, optionally
    filtered to ``publication_date <= as_of_date``. WARN-and-pass-through
    when the catalog rows lack publication_date (current state of
    list_current_anchors in macro_anchors.py)."""
    from flowtracker.research.data_api import ResearchDataAPI

    try:
        api = ResearchDataAPI()
        catalog = api.get_macro_catalog()
    except Exception as exc:
        print(f"  [WARN] get_macro_catalog failed: {exc}", file=sys.stderr)
        return []

    anchors = catalog.get("anchors") if isinstance(catalog, dict) else catalog or []
    completed: list[dict] = []
    for a in anchors:
        if not isinstance(a, dict):
            continue
        if a.get("status") != "complete":
            continue
        completed.append(a)

    if as_of_date and completed:
        has_pub_date = any(
            (a.get("publication_date") or a.get("date")) for a in completed
        )
        if not has_pub_date:
            print(
                "  [WARN] get_macro_catalog has no publication_date — "
                "skipping anchor temporal filter",
                file=sys.stderr,
            )
        else:
            filtered: list[dict] = []
            for a in completed:
                pub = a.get("publication_date") or a.get("date")
                if pub and str(pub) > as_of_date:
                    continue
                filtered.append(a)
            completed = filtered

    names: list[str] = []
    for a in completed:
        name = a.get("name") or a.get("title") or a.get("id") or a.get("doc_type")
        if name:
            names.append(str(name))
    return names


def macro_out_dir(as_of_date: str) -> Path:
    """Return the per-run vault dir for a backdated macro report."""
    return Path.home() / "vault" / "macro" / as_of_date


def run_macro_agent(as_of_date: str, placeholder_symbol: str) -> tuple[float, bool]:
    """Invoke the macro agent CLI with FLOWTRACK_AS_OF + FLOWTRACK_MACRO_OUT_DIR
    set in the child env. Mirrors backtest_historical_analog.run_analog_agent_as_of.
    The out-dir override prevents backdated reports from polluting
    ~/vault/stocks/{placeholder_symbol}/ (briefing.save_envelope honors it)."""
    cwd = Path(__file__).resolve().parents[3]
    start = time.monotonic()
    env = os.environ.copy()
    env["FLOWTRACK_AS_OF"] = as_of_date
    env["FLOWTRACK_MACRO_OUT_DIR"] = str(macro_out_dir(as_of_date))
    proc = subprocess.Popen(
        ["uv", "run", "flowtrack", "research", "run", "macro", "-s", placeholder_symbol],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
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


def read_macro_report(placeholder_symbol: str, as_of_date: str | None = None) -> str:
    """Read the macro report. Prefer the per-as-of override dir if present."""
    if as_of_date:
        override = macro_out_dir(as_of_date) / "macro.md"
        if override.exists():
            return override.read_text()
    path = Path.home() / "vault" / "stocks" / placeholder_symbol / "reports" / "macro.md"
    if not path.exists():
        return ""
    return path.read_text()


async def _gemini_with_retry(
    query_fn,
    attempts: int = GEMINI_RETRY_ATTEMPTS,
    backoff_s: float = GEMINI_RETRY_BACKOFF_S,
) -> str:
    """Retry ``query_fn()`` up to ``attempts`` times with ``backoff_s`` sleeps.
    Resilience for transient Gemini 503/timeout blips; the 1800s subprocess
    timeout already bounds total wall-clock."""
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return await query_fn()
        except Exception as exc:
            last_exc = exc
            if i < attempts - 1:
                print(
                    f"  [WARN] Gemini attempt {i + 1}/{attempts} failed: {exc}; "
                    f"retrying in {backoff_s}s",
                    file=sys.stderr,
                )
                await asyncio.sleep(backoff_s)
    assert last_exc is not None
    raise last_exc


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
        # [""] workaround for SDK #794 — see extractors for full rationale.
        setting_sources=[""],
        plugins=[],
    )

    async def _one_attempt() -> str:
        raw_local = ""
        async for msg in query(prompt=user_prompt, options=opts):
            text = getattr(msg, "content", None) or getattr(msg, "text", "") or ""
            if isinstance(text, list):
                text = "".join(str(c) for c in text)
            raw_local += str(text)
        return raw_local

    try:
        raw = await _gemini_with_retry(
            _one_attempt,
            attempts=GEMINI_RETRY_ATTEMPTS,
            backoff_s=GEMINI_RETRY_BACKOFF_S,
        )
    except Exception as exc:
        return AgentEvalResult(
            agent="macro", stock="NIFTY", sector="_macro_",
            grade="ERR", grade_numeric=0,
            summary=f"Gemini grading failed: {exc}",
            eval_duration_s=time.monotonic() - t0,
            raw_gemini_response="",
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


def append_macro_tsv(result: AgentEvalResult, as_of_date: str, note: str) -> None:
    MACRO_RESULTS_TSV.parent.mkdir(parents=True, exist_ok=True)
    is_new = not MACRO_RESULTS_TSV.exists()
    with open(MACRO_RESULTS_TSV, "a") as f:
        if is_new:
            f.write("timestamp\tnote\tas_of_date\tgrade\tgrade_numeric\tprompt_fixes\tissues\tsummary\n")
        ts = datetime.now(timezone.utc).isoformat()
        prompt_fixes = sum(1 for i in result.issues if i.type == "PROMPT_FIX")
        issues_count = len(result.issues)
        summary = (result.summary or "").replace("\t", " ").replace("\n", " ")[:300]
        note_clean = (note or "").replace("\t", " ").replace("\n", " ")[:120]
        f.write(f"{ts}\t{note_clean}\t{as_of_date}\t{result.grade}\t{result.grade_numeric}\t{prompt_fixes}\t{issues_count}\t{summary}\n")


def archive_eval_run(
    result: AgentEvalResult,
    as_of_date: str,
    anchors: list[str],
    report_md: str,
    note: str,
    run_duration_s: float,
) -> Path:
    """Write per-run JSON to ``eval_history/macro_<ts>.json`` (parity with
    evaluate.py::write_last_run). Gitignored by workspace CLAUDE.md."""
    import hashlib

    MACRO_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    archive_path = MACRO_HISTORY_DIR / f"macro_{ts}.json"
    report_hash = hashlib.sha256(report_md.encode("utf-8")).hexdigest() if report_md else ""
    archive = {
        "agent": "macro",
        "as_of_date": as_of_date,
        "note": note,
        "anchors_used": anchors,
        "report_chars": len(report_md or ""),
        "report_sha256": report_hash,
        "run_duration_s": run_duration_s,
        "result": asdict(result),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    archive_path.write_text(json.dumps(archive, indent=2, default=str))
    return archive_path


async def _eval_one_date(date_entry: dict, placeholder_symbol: str,
                         skip_run: bool, note: str) -> tuple[AgentEvalResult, list[str], str, float]:
    """Returns (result, anchors_used, report_md, run_duration_s) for archival."""
    as_of_date = date_entry["date"]
    print(f"--- macro / {as_of_date} ({date_entry.get('why', '')}) ---")

    run_duration = 0.0
    if not skip_run:
        print(f"  Running macro agent (FLOWTRACK_AS_OF={as_of_date})...")
        run_duration, success = run_macro_agent(as_of_date, placeholder_symbol)
        print(f"  Macro completed in {run_duration:.1f}s (success={success})")
        if not success:
            return (
                AgentEvalResult(
                    agent="macro", stock=placeholder_symbol, sector="_macro_",
                    grade="ERR", grade_numeric=0, summary="Macro agent run failed",
                    run_duration_s=run_duration,
                ),
                [], "", run_duration,
            )

    report_md = read_macro_report(placeholder_symbol, as_of_date=as_of_date)
    if not report_md:
        return (
            AgentEvalResult(
                agent="macro", stock=placeholder_symbol, sector="_macro_",
                grade="ERR", grade_numeric=0, summary="No macro report found",
                run_duration_s=run_duration,
            ),
            [], "", run_duration,
        )
    print(f"  Report: {len(report_md)} chars")

    print(f"  Fetching anchor catalog (filter <= {as_of_date})...")
    anchors = fetch_anchor_catalog(as_of_date=as_of_date)
    print(f"  Complete anchors: {len(anchors)}")

    print(f"  Grading with Gemini...")
    result = await eval_macro_report(as_of_date, report_md, anchors)
    result.run_duration_s = run_duration
    result.report_length = len(report_md)
    print(f"  Grade: {result.grade} ({result.grade_numeric})")
    return result, anchors, report_md, run_duration


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
    if args.note:
        print(f"  note: {args.note}")
    print()

    results: list[AgentEvalResult] = []
    for entry in entries:
        r, anchors, report_md, run_dur = await _eval_one_date(
            entry, placeholder_symbol, args.skip_run, args.note,
        )
        results.append(r)
        append_macro_tsv(r, entry["date"], args.note)
        archive_path = archive_eval_run(
            r, entry["date"], anchors, report_md, args.note, run_dur,
        )
        print(f"  Archived: {archive_path}")
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
    parser.add_argument("--note", type=str, default="",
                        help="Free-form note written into eval_history archive (e.g. 'baseline', 'post-prompt-fix-3')")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
