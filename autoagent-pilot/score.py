#!/usr/bin/env python3
"""Aggregate one benchmark run into a results.tsv row + diagnosis JSON.

Reads eval_history/{ts}_{matrix_key}.json files produced since --since-ts
(one per stock in benchmark.json), computes aggregate metrics, and writes:
  - one tab-separated row to --tsv
  - diagnosis JSON to stdout (issue counts grouped by layer for the meta-agent)

Invoked by run_benchmark.sh after all per-stock evals complete.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

PASS_THRESHOLD = 91  # A- with margin — strictly above the A- floor (90).
                     # eval_matrix.yaml's target is 90, but pilot uses 91 as
                     # practical threshold so borderline stocks don't count
                     # as pass on Gemini variance ±1 noise.
MAX_GRADE = 97       # A+

# eval-pipeline.sh hard-codes FT_DIR to the main repo path, so autoeval writes
# archives into the main repo's autoeval dir — NOT the worktree's. Matching
# that here instead of computing relative to this file.
AUTOEVAL_DIR = Path("/Users/tarang/Documents/Projects/equity-research/flow-tracker/flowtracker/research/autoeval")
HISTORY_DIR = AUTOEVAL_DIR / "eval_history"

# eval-pipeline.sh invokes `autoeval -a <agent> --sectors <matrix_key>` which
# runs async_main_agent (agent-first mode). That writes archives named
# `{ts}_all_for_{agent}.json` with a `results` dict keyed by the `--sectors`
# values (e.g. {"bfsi": {...stock result...}}).


def find_stock_result(matrix_key: str, since_ts: datetime, agent: str) -> tuple[Path, dict] | None:
    """Walk eval_history archives newer than since_ts and return the newest
    (archive_path, stock_result) where `results[matrix_key]` is populated.
    """
    candidates = sorted(HISTORY_DIR.glob(f"*_all_for_{agent}.json"))
    for path in reversed(candidates):
        ts_str = path.name.split("_", 1)[0]
        ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        if ts < since_ts:
            break
        data = json.loads(path.read_text())
        result = data.get("results", {}).get(matrix_key)
        if result:
            return path, result
    return None


def layer_of(section: str) -> str:
    """Heuristic layer routing hint by issue section.

    NOTE: authoritative layer selection lives in program.md. This hint is
    advisory — it flags *which layer the issue likely lives at* based on the
    Gemini grader's free-form section string. The meta-agent confirms by
    cross-referencing occurrences across sectors before editing.
    """
    s = (section or "").lower()
    # L1 candidates: preamble-level behaviors (citations, temporal, say-unknown, monologue)
    if any(k in s for k in ["citation", "temporal", "unknown", "monologue", "thinking",
                             "source format", "ar/deck", "briefing envelope"]):
        return "L1"
    # L3/L4 candidates: sector-framework-specific
    if any(k in s for k in ["sector framework", "sector-framework", "sector compliance",
                             "mandatory_metrics", "casa", "nim", "gnpa", "asset quality",
                             "r&d", "anda", "commodity", "segment"]):
        return "L3_or_L4"
    # Default: L2 (business-report-specific framing)
    return "L2"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True, help="benchmark.json path")
    ap.add_argument("--since-ts", required=True, help="ISO8601 UTC — benchmark start time")
    ap.add_argument("--commit", required=True, help="git short SHA")
    ap.add_argument("--agent", default="business",
                    help="Specialist agent whose eval_history archives to read (default: business)")
    ap.add_argument("--description", default="", help="one-line description of this iteration")
    ap.add_argument("--tsv", required=True, help="results.tsv path to append to")
    ap.add_argument("--diagnose-json", default=None, help="if set, also write diagnosis JSON here")
    args = ap.parse_args()

    since_ts = datetime.fromisoformat(args.since_ts.replace("Z", "+00:00"))
    bench = json.loads(Path(args.benchmark).read_text())

    per_stock: list[dict] = []
    issues_by_layer: dict[str, list[dict]] = defaultdict(list)
    issue_type_counts: Counter = Counter()
    missing: list[str] = []

    for cell in bench["cells"]:
        for pair in cell["pairs"]:
            key = pair["eval_matrix_key"]
            stock = pair["stock"]
            found = find_stock_result(key, since_ts, args.agent)
            if found is None:
                missing.append(f"{key}:{stock}")
                per_stock.append({"eval_matrix_key": key, "stock": stock,
                                  "sector_skill": cell["sector_skill"],
                                  "grade_numeric": 0, "grade": "MISSING"})
                continue
            arc, res = found
            gnum = int(res.get("grade_numeric", 0))
            tc = res.get("tool_coverage") or {}
            per_stock.append({
                "eval_matrix_key": key,
                "stock": stock,
                "sector_skill": cell["sector_skill"],
                "grade": res.get("grade", "?"),
                "grade_numeric": gnum,
                "tool_coverage": {
                    "called": tc.get("tools_called"),
                    "available": tc.get("tools_available"),
                    "coverage_pct": tc.get("coverage_pct"),
                    "uncalled": tc.get("uncalled_tools") or [],
                },
                "archive": arc.name,
            })
            for issue in res.get("issues", []) or []:
                issue_type_counts[issue.get("type", "UNKNOWN")] += 1
                if issue.get("type") == "PROMPT_FIX":
                    layer = layer_of(issue.get("section", ""))
                    issues_by_layer[layer].append({
                        "sector_skill": cell["sector_skill"],
                        "stock": stock,
                        "section": issue.get("section", ""),
                        "issue": issue.get("issue", ""),
                        "suggestion": issue.get("suggestion", ""),
                    })

    graded = [s for s in per_stock if s["grade_numeric"] > 0]
    total = len(per_stock)
    passed = sum(1 for s in graded if s["grade_numeric"] >= PASS_THRESHOLD)
    avg_gnum = sum(s["grade_numeric"] for s in graded) / len(graded) if graded else 0.0
    avg_score = round(avg_gnum / MAX_GRADE, 4)

    task_scores = ",".join(f"{s['stock']}={s['grade_numeric']}" for s in per_stock)

    # Append results.tsv row — matches kevingu's format
    tsv_path = Path(args.tsv)
    write_header = not tsv_path.exists()
    with tsv_path.open("a") as f:
        if write_header:
            f.write("commit\tavg_score\tpassed\ttask_scores\tcost_usd\tstatus\tdescription\n")
        f.write(f"{args.commit}\t{avg_score}\t{passed}/{total}\t{task_scores}\t\tpending\t{args.description}\n")

    diagnosis = {
        "commit": args.commit,
        "avg_score": avg_score,
        "passed": f"{passed}/{total}",
        "per_stock": per_stock,
        "issue_type_counts": dict(issue_type_counts),
        "prompt_fix_issues_by_layer_hint": {
            layer: issues for layer, issues in issues_by_layer.items()
        },
        "missing": missing,
    }
    print(json.dumps(diagnosis, indent=2))
    if args.diagnose_json:
        Path(args.diagnose_json).write_text(json.dumps(diagnosis, indent=2))


if __name__ == "__main__":
    main()
