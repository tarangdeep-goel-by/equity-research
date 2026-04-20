#!/usr/bin/env python3
"""Backfill daily_stock_data.adj_close + adj_factor across the universe.

One-time run after Sprint 0 schema migration. Iterates every symbol with
price history and calls FlowStore.recompute_adj_close, which applies the
cumulative split + bonus multiplier and writes adj_close / adj_factor.

Usage:
    uv run python scripts/backfill_adj_close.py
    uv run python scripts/backfill_adj_close.py --symbol RELIANCE  # single-symbol
    uv run python scripts/backfill_adj_close.py --verify           # drift sweep only

Exit 0 on success; exit 1 on drift discovery or recompute error.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowtracker.store import FlowStore
from flowtracker.research.data_api import ResearchDataAPI


def backfill_all(store: FlowStore, only_symbol: str | None = None) -> dict:
    """Recompute adj_close for all symbols (or one). Returns run stats."""
    if only_symbol:
        symbols = [only_symbol.upper()]
    else:
        rows = store._conn.execute(
            "SELECT DISTINCT symbol FROM daily_stock_data ORDER BY symbol"
        ).fetchall()
        symbols = [r["symbol"] for r in rows]

    total_rows = 0
    t0 = time.time()
    failures: list[tuple[str, str]] = []

    for i, sym in enumerate(symbols, 1):
        try:
            n = store.recompute_adj_close(sym)
            total_rows += n
            if i % 100 == 0 or i == len(symbols):
                dt = time.time() - t0
                print(
                    f"  [{i}/{len(symbols)}] {total_rows:,} rows, "
                    f"{i / dt:.1f} symbols/sec",
                    flush=True,
                )
        except Exception as exc:
            failures.append((sym, str(exc)))
            print(f"  ⚠ {sym}: {exc}", flush=True)

    elapsed = time.time() - t0
    print(
        f"\n✓ Backfilled {len(symbols) - len(failures)}/{len(symbols)} symbols "
        f"({total_rows:,} rows) in {elapsed:.1f}s",
        flush=True,
    )
    return {
        "symbols": len(symbols),
        "rows": total_rows,
        "failures": failures,
        "elapsed_sec": elapsed,
    }


def verify_drift(store: FlowStore, n_samples: int = 100) -> list[dict]:
    """Sample n_samples (symbol, date) pairs and compare stored adj_close
    to dynamically computed value. Returns list of drift records (empty = clean).
    """
    rows = store._conn.execute(
        "SELECT symbol, date, adj_close FROM daily_stock_data "
        "WHERE adj_close IS NOT NULL "
        "ORDER BY RANDOM() LIMIT ?",
        (n_samples,),
    ).fetchall()

    drifts: list[dict] = []
    api = ResearchDataAPI(store=store)

    # Group samples by symbol to amortize the helper's action-fetch cost
    by_symbol: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        by_symbol.setdefault(r["symbol"], []).append((r["date"], r["adj_close"]))

    for sym, pairs in by_symbol.items():
        dates = [d for d, _ in pairs]
        min_d, max_d = min(dates), max(dates)
        computed = dict(api.get_adjusted_close_series(sym, min_d, max_d))
        for d, stored in pairs:
            c = computed.get(d)
            if c is None:
                drifts.append({"symbol": sym, "date": d, "reason": "missing_computed"})
                continue
            if abs(c - stored) > max(1e-6, abs(stored) * 1e-6):
                drifts.append({
                    "symbol": sym, "date": d,
                    "stored": stored, "computed": c,
                    "abs_diff": abs(c - stored),
                })

    return drifts


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill adj_close across universe")
    parser.add_argument("--symbol", help="Run for a single symbol only")
    parser.add_argument("--verify", action="store_true", help="Skip backfill, run drift sweep only")
    parser.add_argument("--samples", type=int, default=100, help="Drift sweep sample size")
    args = parser.parse_args()

    store = FlowStore()

    try:
        if not args.verify:
            print(
                f"Backfilling adj_close"
                f"{' for ' + args.symbol if args.symbol else ' for full universe'}...",
                flush=True,
            )
            stats = backfill_all(store, only_symbol=args.symbol)
            if stats["failures"]:
                print(f"\n⚠ {len(stats['failures'])} failures — see above")
                return 1

        print(f"\nRunning drift sweep ({args.samples} random samples)...", flush=True)
        drifts = verify_drift(store, n_samples=args.samples)
        if drifts:
            print(f"\n✗ {len(drifts)} drift(s) detected:")
            for d in drifts[:10]:
                print(f"  {d}")
            return 1
        print(f"✓ No drift across {args.samples} samples — stored and computed paths agree.")
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
