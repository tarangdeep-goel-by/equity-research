#!/usr/bin/env python3
"""Backfill data_quality_flags from annual_financials.

Computes the full LOW+ flag set so callers can filter at query time.
Idempotent — clears existing flags then re-upserts the freshly computed set.

Usage:
  uv run python scripts/backfill_data_quality_flags.py
  uv run python scripts/backfill_data_quality_flags.py --symbols HDFCBANK,INFY
  uv run python scripts/backfill_data_quality_flags.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter

from flowtracker.data_quality import detect, fetch_rows
from flowtracker.store import FlowStore


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbols", type=str, default=None,
                   help="Comma-separated symbols. Default: full universe.")
    p.add_argument("--threshold-revenue", type=float, default=0.30,
                   help="Reclass flag only if |revenue change| stays below this fraction (default 0.30 = 30%%).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute flags and print summary without writing to DB.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None

    with FlowStore() as store:
        rows = fetch_rows(store._conn, symbols)
        flags = detect(rows, threshold_revenue=args.threshold_revenue, min_severity="LOW")
        by_sev = Counter(f.severity for f in flags)
        by_sym = Counter(f.symbol for f in flags)
        print(
            f"Computed {len(flags)} flags across {len(by_sym)} symbols — "
            f"HIGH={by_sev.get('HIGH', 0)} MEDIUM={by_sev.get('MEDIUM', 0)} LOW={by_sev.get('LOW', 0)}"
        )

        if args.dry_run:
            print("dry-run: no DB writes")
            return 0

        # Idempotent: clear (scoped or full) then re-upsert the computed set.
        if symbols:
            for sym in symbols:
                store.clear_data_quality_flags(sym)
        else:
            store.clear_data_quality_flags(None)
        n = store.upsert_data_quality_flags(flags)
        print(f"Wrote {n} rows to data_quality_flags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
