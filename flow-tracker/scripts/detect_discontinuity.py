#!/usr/bin/env python3
"""Detect Screener line-item reclassification discontinuities in annual_financials.

CLI wrapper around `flowtracker.data_quality`. Reads
~/.local/share/flowtracker/flows.db, walks consecutive year pairs per symbol,
flags lines that jump while revenue is flat.

Usage:
  uv run python scripts/detect_discontinuity.py
  uv run python scripts/detect_discontinuity.py --symbols HDFCBANK,INFY,SIEMENS
  uv run python scripts/detect_discontinuity.py --min-severity HIGH --summary-only
  uv run python scripts/detect_discontinuity.py --output /tmp/flags.tsv
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from flowtracker.data_quality import Flag, SEVERITY_RANK, detect, fetch_rows

DB_PATH = Path.home() / ".local" / "share" / "flowtracker" / "flows.db"


def write_tsv(flags: list[Flag], out: Path | None) -> None:
    header = (
        "symbol\tprior_fy\tcurr_fy\tline\tprior_val\tcurr_val"
        "\tjump_pct\trev_change_pct\tflag_type\tseverity"
    )
    lines = [header]
    sev_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    for f in sorted(flags, key=lambda x: (sev_rank[x.severity], x.symbol, x.curr_fy, x.line)):
        lines.append(
            f"{f.symbol}\t{f.prior_fy}\t{f.curr_fy}\t{f.line}\t"
            f"{f.prior_val:.1f}\t{f.curr_val:.1f}\t{f.jump_pct:+.0f}\t"
            f"{f.revenue_change_pct:+.1f}\t{f.flag_type}\t{f.severity}"
        )
    text = "\n".join(lines) + "\n"
    if out:
        out.write_text(text)
        print(f"Wrote {len(flags)} flags to {out}", file=sys.stderr)
    else:
        print(text)


def print_summary(flags: list[Flag], rows_by_symbol: dict[str, list[dict]]) -> None:
    by_sev = Counter(f.severity for f in flags)
    by_type = Counter(f.flag_type for f in flags)
    by_line = Counter(f.line for f in flags)
    by_symbol = Counter(f.symbol for f in flags)
    print(
        f"\nScanned: {len(rows_by_symbol)} symbols, "
        f"{sum(len(v) for v in rows_by_symbol.values())} rows",
        file=sys.stderr,
    )
    print(
        f"Flags: {len(flags)} total — "
        f"HIGH={by_sev.get('HIGH', 0)} MEDIUM={by_sev.get('MEDIUM', 0)} LOW={by_sev.get('LOW', 0)} "
        f"| RECLASS={by_type.get('RECLASS', 0)} SIGN_FLIP={by_type.get('SIGN_FLIP', 0)}",
        file=sys.stderr,
    )
    print(f"Distinct symbols flagged: {len(by_symbol)}", file=sys.stderr)
    print("Top 8 lines by flag count:", file=sys.stderr)
    for line, count in by_line.most_common(8):
        print(f"  {line:32s} {count}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", type=Path, default=DB_PATH)
    p.add_argument("--symbols", type=str, default=None,
                   help="Comma-separated symbols. Default: full universe.")
    p.add_argument("--threshold-revenue", type=float, default=0.30,
                   help="Reclass flag only if |revenue change| stays below this fraction (default 0.30 = 30%%).")
    p.add_argument("--min-severity", choices=("LOW", "MEDIUM", "HIGH"), default="MEDIUM",
                   help="Lowest severity to report. HIGH = sign flip or jump >500%%; "
                        "MEDIUM = 200-500%%; LOW = 100-200%%. Default MEDIUM.")
    p.add_argument("--output", type=Path, default=None,
                   help="Write TSV here. Default: stdout.")
    p.add_argument("--summary-only", action="store_true",
                   help="Skip per-row TSV; print summary only.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.db.exists():
        print(f"DB not found: {args.db}", file=sys.stderr)
        return 1
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    conn = sqlite3.connect(args.db)
    try:
        rows = fetch_rows(conn, symbols)
    finally:
        conn.close()
    flags = detect(rows, args.threshold_revenue, args.min_severity)
    if not args.summary_only:
        write_tsv(flags, args.output)
    print_summary(flags, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
