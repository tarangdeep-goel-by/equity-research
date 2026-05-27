#!/usr/bin/env python3
"""Backfill quarterly_cash_flow from Screener (fiscal-year cadence).

Targets every symbol with rows in ``quarterly_results`` — those are the
symbols known to have a working Screener page. yfinance only ever
populated ~49 of ~1,700 such symbols; Screener has CFO/CFI/CFF for all
of them at annual (fiscal year-end) cadence.

Behavior:
  * Idempotent — ``upsert_quarterly_cash_flow`` overwrites by
    (symbol, quarter_end). Re-runs are safe even if other backfills are
    writing concurrently to other tables.
  * Skips symbols that already have any ``source='screener'`` row (set by
    a previous run of this script). Use ``--force`` to re-fetch.
  * 3s sleep between symbols (Screener rate limit).
  * Progress log at /tmp/screener_cf_backfill_progress.log.

Usage:
    uv run python scripts/backfill_screener_cash_flow.py
    uv run python scripts/backfill_screener_cash_flow.py --test 5
    uv run python scripts/backfill_screener_cash_flow.py --force
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowtracker.screener_client import ScreenerClient, ScreenerError
from flowtracker.store import FlowStore


_PROGRESS_LOG = Path("/tmp/screener_cf_backfill_progress.log")


def _log(symbol: str, status: str, note: str = "") -> None:
    line = json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "status": status,
        "note": note,
    })
    with _PROGRESS_LOG.open("a") as fp:
        fp.write(line + "\n")


def select_universe(store: FlowStore, force: bool) -> list[str]:
    """All symbols in quarterly_results, optionally filtered to those
    without an existing screener-sourced CF row.
    """
    if force:
        rows = store._conn.execute(
            "SELECT DISTINCT symbol FROM quarterly_results ORDER BY symbol"
        ).fetchall()
    else:
        rows = store._conn.execute(
            """
            SELECT DISTINCT q.symbol
              FROM quarterly_results q
             WHERE NOT EXISTS (
                   SELECT 1 FROM quarterly_cash_flow c
                    WHERE c.symbol = q.symbol AND c.source = 'screener'
               )
             ORDER BY q.symbol
            """
        ).fetchall()
    return [r["symbol"] for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=int, default=0,
                        help="Process only the first N symbols then exit (smoke test).")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even symbols that already have screener-sourced rows.")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="Seconds to sleep between symbols (default: 3).")
    args = parser.parse_args()

    with FlowStore() as store:
        symbols = select_universe(store, args.force)

    if not symbols:
        print("Nothing to do — all qresults symbols already have screener-sourced CF rows.")
        return 0

    if args.test:
        symbols = symbols[: args.test]

    print(f"Processing {len(symbols)} symbols (sleep={args.sleep}s between).")
    ok = empty = failed = 0
    total_rows = 0

    with ScreenerClient() as sc:
        for i, sym in enumerate(symbols, 1):
            try:
                rows = sc.fetch_quarterly_cash_flow_screener(sym)
                if rows:
                    with FlowStore() as store:
                        n = store.upsert_quarterly_cash_flow(sym, rows)
                    total_rows += n
                    ok += 1
                    _log(sym, "ok", f"{n} rows")
                    print(f"[{i}/{len(symbols)}] {sym}: {n} CF rows", flush=True)
                else:
                    empty += 1
                    _log(sym, "empty")
                    print(f"[{i}/{len(symbols)}] {sym}: empty (no CF section)", flush=True)
            except ScreenerError as e:
                failed += 1
                _log(sym, "fail", str(e))
                print(f"[{i}/{len(symbols)}] {sym}: FAIL — {e}", flush=True)
            except Exception as e:
                failed += 1
                _log(sym, "fail!", str(e))
                print(f"[{i}/{len(symbols)}] {sym}: FAIL! — {e}", flush=True)
            time.sleep(args.sleep)

    print()
    print(f"Done. ok={ok} empty={empty} failed={failed} total_rows={total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
