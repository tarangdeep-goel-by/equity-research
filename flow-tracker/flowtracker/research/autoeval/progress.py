#!/usr/bin/env python3
"""AutoEval progress chart — ASCII visualization of experiment history.

Reads results.tsv and renders a sector × agent grade matrix plus
experiment timeline showing improvements and discards.

Usage:
    python progress.py              # full summary
    python progress.py --sector bfsi  # single sector detail
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


GRADE_ORDER = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F", "ERR"]
TARGET = "A-"
TARGET_NUMERIC = 90


def load_results() -> list[dict]:
    """Load results.tsv into list of dicts."""
    tsv_path = Path(__file__).parent / "results.tsv"
    if not tsv_path.exists():
        return []
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def load_macro_results() -> list[dict]:
    """Load results_macro.tsv into list of dicts (empty if file absent)."""
    tsv_path = Path(__file__).parent / "results_macro.tsv"
    if not tsv_path.exists():
        return []
    with open(tsv_path) as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def macro_block(rows: list[dict], limit: int = 10) -> None:
    """Render last N macro evals (sorted by as_of_date, newest last)."""
    if not rows:
        return
    sorted_rows = sorted(rows, key=lambda r: r.get("as_of_date", ""))[-limit:]
    print(f"\nMacro autoeval — last {len(sorted_rows)} dates")
    passing = 0
    for r in sorted_rows:
        as_of = r.get("as_of_date", "?")
        grade = r.get("grade", "?")
        try:
            numeric = int(r.get("grade_numeric", "0"))
        except ValueError:
            numeric = 0
        is_pass = numeric >= TARGET_NUMERIC
        if is_pass:
            passing += 1
        status = "PASS" if is_pass else "FAIL"
        print(f"  {as_of:12s}  {grade:3s} ({numeric:2d})  {status}")
    print(f"passing: {passing}/{len(sorted_rows)}")


def grade_matrix(rows: list[dict]) -> None:
    """Print sector × agent grade matrix (latest grade per cell)."""
    # Build latest grade per (sector, agent)
    latest: dict[tuple[str, str], str] = {}
    for row in rows:
        key = (row["sector"], row["agent"])
        latest[key] = row["grade"]

    sectors = sorted({r["sector"] for r in rows})
    agents = sorted({r["agent"] for r in rows})

    if not sectors or not agents:
        print("No results yet.")
        return

    # Header
    col_width = 12
    header = f"{'sector':<14s}" + "".join(f"{a:<{col_width}s}" for a in agents)
    print(header)
    print("-" * len(header))

    for sector in sectors:
        cells = []
        for agent in agents:
            grade = latest.get((sector, agent), "---")
            # Color-code: pass = grade, fail = grade*
            try:
                numeric = int(next(
                    r["grade_numeric"] for r in reversed(rows)
                    if r["sector"] == sector and r["agent"] == agent
                ))
                marker = " " if numeric >= TARGET_NUMERIC else "*"
            except (StopIteration, ValueError):
                marker = "?"
            cells.append(f"{grade}{marker}")
        row_str = f"{sector:<14s}" + "".join(f"{c:<{col_width}s}" for c in cells)
        print(row_str)

    # Summary
    total = len(latest)
    passing = sum(
        1 for (s, a), g in latest.items()
        if any(
            int(r["grade_numeric"]) >= TARGET_NUMERIC
            for r in rows
            if r["sector"] == s and r["agent"] == a
        )
    )
    print(f"\n{passing}/{total} cells passing ({TARGET}+)")


def sector_timeline(rows: list[dict], sector: str) -> None:
    """Print experiment timeline for a single sector."""
    sector_rows = [r for r in rows if r["sector"] == sector]
    if not sector_rows:
        print(f"No results for sector '{sector}'")
        return

    print(f"\nTimeline: {sector}")
    print(f"{'cycle':<8s}{'agent':<14s}{'grade':<8s}{'numeric':<10s}{'prompt_fixes':<14s}{'notes'}")
    print("-" * 80)
    for r in sector_rows:
        cycle = r.get("cycle", "?")
        agent = r.get("agent", "?")
        grade = r.get("grade", "?")
        numeric = r.get("grade_numeric", "?")
        fixes = r.get("prompt_fixes", "?")
        notes = r.get("notes", "")[:50]
        print(f"{cycle:<8s}{agent:<14s}{grade:<8s}{numeric:<10s}{fixes:<14s}{notes}")


def experiment_chart(rows: list[dict]) -> None:
    """Print ASCII experiment history chart."""
    by_sector = defaultdict(list)
    for r in rows:
        by_sector[r["sector"]].append(r)

    print("\nExperiment History")
    print("  # = passed (A-+)   . = failed   x = error\n")

    for sector in sorted(by_sector.keys()):
        sector_rows = by_sector[sector]
        symbols = []
        for r in sector_rows:
            try:
                numeric = int(r["grade_numeric"])
            except (ValueError, KeyError):
                numeric = 0
            if numeric == 0:
                symbols.append("x")
            elif numeric >= TARGET_NUMERIC:
                symbols.append("#")
            else:
                symbols.append(".")
        timeline = "".join(symbols)
        print(f"  {sector:<14s} {timeline}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AutoEval progress chart")
    parser.add_argument("--sector", default=None, help="Show detailed timeline for a sector")
    args = parser.parse_args()

    rows = load_results()
    if not rows:
        print("No results.tsv found. Run evaluate.py first.")
        return

    grade_matrix(rows)
    experiment_chart(rows)

    if args.sector:
        sector_timeline(rows, args.sector)

    macro_block(load_macro_results())


if __name__ == "__main__":
    main()
