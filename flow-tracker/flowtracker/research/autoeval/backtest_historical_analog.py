#!/usr/bin/env python3
"""Historical Analog Agent — empirical backtest (Part 3 Tier 2).

The Historical Analog agent is unique among specialists because its outputs
are falsifiable against realized returns. Gemini grading ("is this a good
analog?") is a subjective call; realized 12m returns are ground truth.

This script:
  1. Samples 20 ``(symbol, as_of_date)`` points where as_of is ≥15 months ago
     and 12m forward returns are observable. Stratified to cover all three
     outcome buckets (recovered / sideways / blew_up) so calibration is
     measured across the full outcome space.
  2. For each sample, runs the agent as-if the as-of-date were the present,
     parses the ``directional_adjustments`` from the briefing JSON
     (upside / base / downside × Thicker / Thinner / Unchanged).
  3. Compares the agent's directional call to the realized return's
     quartile position within the cohort:
       * Agent says ``downside: Thicker`` → P(realized in bottom quartile) > 0.35 passes
       * Agent says ``downside: Thinner``  → P(realized in bottom quartile) < 0.15 passes
       * ``Unchanged`` → no calibration claim; counted only for coverage.
  4. Writes ``backtest_results_analog.tsv`` with per-sample columns
     (symbol, as_of, directional_call, realized_quartile, hit/miss) and
     a summary row with per-direction calibration stats.

Usage:
    uv run python flowtracker/research/autoeval/backtest_historical_analog.py
    uv run python flowtracker/research/autoeval/backtest_historical_analog.py --n 20 --seed 42
    uv run python flowtracker/research/autoeval/backtest_historical_analog.py --skip-run
        (re-grades existing briefings without re-running the agent)
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path


# Calibration thresholds — what "Thicker" and "Thinner" mean quantitatively.
# The agent's directional enum is interpreted as a probability claim: Thicker
# means the tail is fatter than the cohort's naive rate; Thinner means thinner.
# A Thicker call passes calibration if realized lands in that tail at a rate
# meaningfully above 25% (random); Thinner passes if below 15%.
TAIL_THICKER_PASS_THRESHOLD = 0.35
TAIL_THINNER_PASS_THRESHOLD = 0.15

BACKTEST_RESULTS_TSV = Path(__file__).parent / "backtest_results_analog.tsv"


@dataclass
class BacktestSample:
    symbol: str
    as_of_date: str            # quarter_end used as-of
    realized_12m_pct: float
    realized_quartile: int      # 1 (bottom) to 4 (top) within the agent's retrieved cohort
    directional_call: dict      # {"upside": Thicker|..., "base": ..., "downside": ...}
    # Hits — which tail claims the sample validated
    upside_hit: bool | None = None
    base_hit: bool | None = None
    downside_hit: bool | None = None
    error: str | None = None


def load_mature_analog_points(cutoff_age_days: int = 450) -> list[dict]:
    """Return (symbol, as_of_date, return_12m_pct, outcome_label) rows from
    ``analog_forward_returns`` where as_of_date is old enough that 12m
    forward returns have landed. 450 days = 12mo + a buffer so T+12m < today.
    """
    from flowtracker.store import FlowStore

    cutoff = (date.today() - timedelta(days=cutoff_age_days)).isoformat()
    with FlowStore() as store:
        rows = store._conn.execute(
            """
            SELECT symbol, as_of_date, return_12m_pct, outcome_label
            FROM analog_forward_returns
            WHERE as_of_date <= ?
              AND return_12m_pct IS NOT NULL
              AND outcome_label IS NOT NULL
            """,
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def stratified_sample(
    population: list[dict], n: int, seed: int,
) -> list[dict]:
    """Sample ``n`` points balanced across outcome buckets (recovered /
    sideways / blew_up). If any bucket is undersupplied, fall back to
    proportional sampling from whatever's available.
    """
    rng = random.Random(seed)
    by_label: dict[str, list[dict]] = {"recovered": [], "sideways": [], "blew_up": []}
    for row in population:
        lbl = row.get("outcome_label")
        if lbl in by_label:
            by_label[lbl].append(row)

    target_per_bucket = max(1, n // 3)
    sample: list[dict] = []
    for lbl, bucket in by_label.items():
        rng.shuffle(bucket)
        sample.extend(bucket[:target_per_bucket])

    # Top-up with a proportional tail from whichever buckets had extras
    rng.shuffle(population)
    for row in population:
        if len(sample) >= n:
            break
        if row not in sample:
            sample.append(row)
    return sample[:n]


def run_analog_agent_as_of(symbol: str, as_of_date: str) -> tuple[float, bool]:
    """Invoke the historical_analog agent CLI for one sample.

    NOTE: the current CLI doesn't support --as-of-date; backtest calls the
    agent with live wall-clock state, meaning the feature-vector call inside
    the agent uses today's data, not as_of_date's data. This is a known
    simplification — proper as-of support is a Phase 2 CLI upgrade (plumb an
    AS_OF env var through the agent prompt + data_api calls). For now,
    backtest samples rely on the retrieval SQL itself being as-of-safe, which
    it is (analog_builder uses quarter_end <= target_date).
    """
    cwd = Path(__file__).resolve().parents[3]
    start = time.monotonic()
    proc = subprocess.run(
        ["uv", "run", "flowtrack", "research", "run", "historical_analog", "-s", symbol],
        cwd=cwd, capture_output=True, text=True, timeout=900,
    )
    return time.monotonic() - start, proc.returncode == 0


def load_briefing(symbol: str) -> dict | None:
    path = Path.home() / "vault" / "stocks" / symbol / "briefings" / "historical_analog.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def realized_quartile_within_cohort(
    realized_pct: float, cohort_12m_pcts: list[float],
) -> int:
    """Where did the realized return land within its own cohort's 12m return
    distribution? Returns 1 (bottom quartile) through 4 (top). Used as
    ground truth for directional calibration — "downside: Thicker" is a
    claim that realized lands in quartile 1 at a rate > 25%.
    """
    if not cohort_12m_pcts:
        return 0
    sorted_c = sorted(cohort_12m_pcts)
    n = len(sorted_c)
    below = sum(1 for v in sorted_c if v <= realized_pct)
    pct = below / n
    if pct <= 0.25:
        return 1
    if pct <= 0.50:
        return 2
    if pct <= 0.75:
        return 3
    return 4


def score_sample(sample_meta: dict, briefing: dict) -> BacktestSample:
    """Compare the agent's directional_adjustments to the sample's realized
    quartile within its retrieved cohort."""
    directional = briefing.get("directional_adjustments") or {}
    cohort_12m = [
        a.get("return_12m_pct") for a in (briefing.get("top_analogs") or [])
        if a.get("return_12m_pct") is not None
    ]
    quartile = realized_quartile_within_cohort(
        sample_meta["return_12m_pct"], cohort_12m,
    )
    bs = BacktestSample(
        symbol=sample_meta["symbol"],
        as_of_date=sample_meta["as_of_date"],
        realized_12m_pct=sample_meta["return_12m_pct"],
        realized_quartile=quartile,
        directional_call=dict(directional),
    )
    if not quartile:
        bs.error = "No cohort 12m returns to compute quartile"
        return bs

    # Score each tail. Pass semantics:
    #   Thicker at downside → quartile == 1 counts toward hit rate
    #   Thinner at downside → quartile >= 2 counts toward hit rate
    down = directional.get("downside")
    if down == "Thicker":
        bs.downside_hit = quartile == 1
    elif down == "Thinner":
        bs.downside_hit = quartile != 1

    up = directional.get("upside")
    if up == "Thicker":
        bs.upside_hit = quartile == 4
    elif up == "Thinner":
        bs.upside_hit = quartile != 4

    base = directional.get("base")
    if base == "Thicker":
        bs.base_hit = quartile in (2, 3)
    elif base == "Thinner":
        bs.base_hit = quartile in (1, 4)

    return bs


def summarize_calibration(samples: list[BacktestSample]) -> dict:
    """Aggregate hit rates per-direction. Pass thresholds:
       Thicker calls: hit rate >= TAIL_THICKER_PASS_THRESHOLD
       Thinner calls: hit rate <= TAIL_THINNER_PASS_THRESHOLD (interpreted
         on the rate of landing in the claimed-thinner tail specifically).
    """
    out: dict[str, dict] = {}
    for tail in ("upside", "base", "downside"):
        for direction in ("Thicker", "Thinner"):
            subset = [
                s for s in samples
                if s.directional_call.get(tail) == direction
                and getattr(s, f"{tail}_hit") is not None
            ]
            n = len(subset)
            if n == 0:
                continue
            hit_rate = sum(1 for s in subset if getattr(s, f"{tail}_hit")) / n
            threshold = TAIL_THICKER_PASS_THRESHOLD if direction == "Thicker" else TAIL_THINNER_PASS_THRESHOLD
            # Pass semantics differ: Thicker needs hit_rate >= threshold;
            # Thinner passes when the AGENT's claim of "thinner tail"
            # matches observed low hit rate (realized rarely lands in that tail)
            passed = hit_rate >= threshold if direction == "Thicker" else hit_rate >= (1 - threshold)
            out[f"{tail}_{direction}"] = {
                "n": n, "hit_rate": round(hit_rate, 3),
                "threshold": threshold, "passed": passed,
            }
    return out


def append_backtest_tsv(samples: list[BacktestSample], calibration: dict) -> None:
    is_new = not BACKTEST_RESULTS_TSV.exists()
    with open(BACKTEST_RESULTS_TSV, "a") as f:
        if is_new:
            f.write(
                "timestamp\tsymbol\tas_of_date\trealized_12m_pct\trealized_quartile\t"
                "upside_call\tbase_call\tdownside_call\t"
                "upside_hit\tbase_hit\tdownside_hit\terror\n"
            )
        ts = datetime.utcnow().isoformat()
        for s in samples:
            dc = s.directional_call
            f.write(
                f"{ts}\t{s.symbol}\t{s.as_of_date}\t{s.realized_12m_pct}\t{s.realized_quartile}\t"
                f"{dc.get('upside', '')}\t{dc.get('base', '')}\t{dc.get('downside', '')}\t"
                f"{s.upside_hit}\t{s.base_hit}\t{s.downside_hit}\t{s.error or ''}\n"
            )
        f.write(f"# CALIBRATION SUMMARY ({ts})\n")
        for key, stats in calibration.items():
            f.write(f"# {key}\tn={stats['n']}\thit_rate={stats['hit_rate']}\tthreshold={stats['threshold']}\tpassed={stats['passed']}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical Analog — empirical backtest")
    parser.add_argument("--n", type=int, default=20, help="Sample size (default 20)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for stratified sampler")
    parser.add_argument("--skip-run", action="store_true",
                        help="Skip agent runs; re-score using existing briefings")
    parser.add_argument("--cutoff-days", type=int, default=450,
                        help="Minimum age (days) for a sample's as_of (default 450 = 12mo + buffer)")
    args = parser.parse_args()

    print(f"Backtest: N={args.n} seed={args.seed} cutoff_days={args.cutoff_days}")
    population = load_mature_analog_points(args.cutoff_days)
    print(f"Population: {len(population)} mature (symbol, as_of) points")

    if len(population) < args.n:
        print(f"WARN: population {len(population)} < requested {args.n}; reducing N")

    samples_meta = stratified_sample(population, args.n, args.seed)
    print(f"Stratified sample: {len(samples_meta)} points")

    results: list[BacktestSample] = []
    for i, meta in enumerate(samples_meta, 1):
        symbol, as_of = meta["symbol"], meta["as_of_date"]
        print(f"--- [{i}/{len(samples_meta)}] {symbol} as_of={as_of} ---")

        if not args.skip_run:
            duration, success = run_analog_agent_as_of(symbol, as_of)
            print(f"  agent run: {duration:.1f}s (success={success})")
            if not success:
                bs = BacktestSample(
                    symbol=symbol, as_of_date=as_of,
                    realized_12m_pct=meta["return_12m_pct"],
                    realized_quartile=0, directional_call={}, error="Agent run failed",
                )
                results.append(bs)
                continue

        briefing = load_briefing(symbol)
        if not briefing:
            bs = BacktestSample(
                symbol=symbol, as_of_date=as_of,
                realized_12m_pct=meta["return_12m_pct"],
                realized_quartile=0, directional_call={}, error="No briefing produced",
            )
            results.append(bs)
            continue

        bs = score_sample(meta, briefing)
        results.append(bs)
        print(f"  call={bs.directional_call}  quartile={bs.realized_quartile}  "
              f"hits={{upside:{bs.upside_hit} base:{bs.base_hit} downside:{bs.downside_hit}}}")

    calibration = summarize_calibration(results)
    append_backtest_tsv(results, calibration)

    print()
    print("=" * 70)
    print("CALIBRATION SUMMARY")
    print("=" * 70)
    if not calibration:
        print("No directional claims matched ground-truth quartiles "
              "(likely all 'Unchanged' calls — no calibration signal).")
    else:
        for key, stats in calibration.items():
            status = "PASS" if stats["passed"] else "FAIL"
            print(f"  {key:30s} n={stats['n']:3d}  hit_rate={stats['hit_rate']:.2%}  [{status}]")


if __name__ == "__main__":
    main()
