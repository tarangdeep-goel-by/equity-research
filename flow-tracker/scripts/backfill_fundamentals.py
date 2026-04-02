#!/usr/bin/env python3
"""Bulk backfill valuation snapshots for all scanner symbols.

Screener.in is the sole source for quarterly results and annual financials
(fetched via separate pipelines). This script only fetches valuation snapshots.

Usage:
    source .venv/bin/activate
    python scripts/backfill_fundamentals.py              # all 500 symbols
    python scripts/backfill_fundamentals.py --test 3     # test with 3 symbols
    python scripts/backfill_fundamentals.py --resume     # skip symbols already in DB
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date

# Add project root to path
sys.path.insert(0, ".")

from flowtracker.fund_client import FundClient, YFinanceError
from flowtracker.fund_models import ValuationSnapshot
from flowtracker.store import FlowStore


def get_symbols_with_data(store: FlowStore) -> set[str]:
    """Get symbols that already have valuation data for today."""
    v_syms = {r["symbol"] for r in store._conn.execute(
        "SELECT DISTINCT symbol FROM valuation_snapshot WHERE date = ?",
        (date.today().isoformat(),),
    ).fetchall()}
    return v_syms


def main():
    parser = argparse.ArgumentParser(description="Backfill valuation snapshots")
    parser.add_argument("--test", type=int, default=0, help="Test with N symbols first")
    parser.add_argument("--resume", action="store_true", help="Skip symbols already in DB")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between stocks (seconds)")
    parser.add_argument("--valuation-only", action="store_true", help="Only fetch valuation snapshots (default, kept for compatibility)")
    args = parser.parse_args()

    with FlowStore() as store:
        all_symbols = store.get_all_scanner_symbols()

    if not all_symbols:
        print("ERROR: No scanner symbols found. Run 'flowtrack scan fetch' first.")
        sys.exit(1)

    # Resume mode: skip symbols with existing data
    if args.resume:
        with FlowStore() as store:
            existing = get_symbols_with_data(store)
        before = len(all_symbols)
        all_symbols = [s for s in all_symbols if s not in existing]
        print(f"Resume mode: skipping {before - len(all_symbols)} symbols with existing data")

    if args.test > 0:
        all_symbols = all_symbols[:args.test]

    total = len(all_symbols)
    print(f"\nBackfill valuation snapshots for {total} symbols")
    print(f"  Delay: {args.delay}s between stocks")
    print()

    client = FundClient()
    stats = {
        "valuations": 0,
        "errors": [],
        "skipped": 0,
    }

    for i, sym in enumerate(all_symbols, 1):
        pct = (i / total) * 100
        print(f"[{i:3d}/{total}] ({pct:5.1f}%) {sym:20s} ", end="", flush=True)

        try:
            snap = client.fetch_valuation_snapshot(sym)
            if snap.price is not None:
                with FlowStore() as store:
                    store.upsert_valuation_snapshot(snap)
                stats["valuations"] += 1
                print("V:ok")
            else:
                print("V:no-price")
        except Exception as e:
            print(f"ERR ({e})")
            stats["errors"].append(f"{sym}: {e}")
            stats["skipped"] += 1

        # Rate limit
        if i < total:
            time.sleep(args.delay)

    # Summary
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"  Valuation snapshots:{stats['valuations']:6d} records")
    print(f"  Skipped:            {stats['skipped']:6d}")
    print(f"  Errors:             {len(stats['errors']):6d}")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for e in stats["errors"][:20]:
            print(f"  - {e}")
        if len(stats["errors"]) > 20:
            print(f"  ... and {len(stats['errors']) - 20} more")


if __name__ == "__main__":
    main()
