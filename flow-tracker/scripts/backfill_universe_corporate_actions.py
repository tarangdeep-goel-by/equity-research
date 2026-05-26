#!/usr/bin/env python3
"""Universe-wide corporate actions backfill — splits/bonuses/dividends.

Source: yfinance (``FilingClient.fetch_yfinance_corporate_actions``). The
research-pipeline ``refresh_for_research`` already calls this per symbol on
demand, but only for stocks that have been researched. This script bulk-
populates ``corporate_actions`` for the entire price-history universe so
that the nightly ``recompute_adj_close`` job applies correct split/bonus
multipliers across all 3,700+ symbols.

Behavior:
  * Universe = ``SELECT DISTINCT symbol FROM daily_stock_data``.
  * Skips symbols that already have rows in ``corporate_actions``
    (resume-safe). Pass ``--force`` to refresh everything.
  * yfinance has no formal rate limit; default sleep 0.3s is conservative.
  * Failures (delisted, network) are logged + skipped, not fatal.
  * After backfill, optionally re-runs ``recompute_adj_close`` for any
    symbol that gained a split/bonus row.

Usage:
    uv run python scripts/backfill_universe_corporate_actions.py
    uv run python scripts/backfill_universe_corporate_actions.py --test 5
    uv run python scripts/backfill_universe_corporate_actions.py --no-recompute
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowtracker.filing_client import FilingClient
from flowtracker.store import FlowStore


_PROGRESS_LOG = Path("/tmp/corp_actions_backfill_progress.log")


def _log(symbol: str, status: str, note: str = "") -> None:
    line = json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "status": status,
        "note": note,
    })
    with _PROGRESS_LOG.open("a") as fp:
        fp.write(line + "\n")


def select_universe(store: FlowStore, skip_existing: bool) -> list[str]:
    """Symbols with price history; optionally exclude those that already
    have corporate_actions rows (resume-safe).
    """
    if skip_existing:
        rows = store._conn.execute(
            """
            SELECT DISTINCT symbol FROM daily_stock_data
             WHERE symbol NOT IN (SELECT DISTINCT symbol FROM corporate_actions)
             ORDER BY symbol
            """
        ).fetchall()
    else:
        rows = store._conn.execute(
            "SELECT DISTINCT symbol FROM daily_stock_data ORDER BY symbol"
        ).fetchall()
    return [r["symbol"] for r in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=int, default=0, help="Process N symbols only")
    parser.add_argument("--sleep", type=float, default=0.3, help="Sleep between symbols")
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch even for symbols already in corporate_actions")
    parser.add_argument("--no-recompute", action="store_true",
                        help="Skip the recompute_adj_close pass after backfill")
    args = parser.parse_args()

    with FlowStore() as store:
        pending = select_universe(store, skip_existing=not args.force)

    if args.test:
        pending = pending[: args.test]

    print(f"Symbols to process: {len(pending)}")
    if not pending:
        print("Nothing to do.")
        return 0

    ok = 0
    splits_seen = 0
    divs_seen = 0
    failed: list[tuple[str, str]] = []
    touched_for_recompute: set[str] = set()

    with FilingClient() as fc:
        for i, sym in enumerate(pending, 1):
            t0 = time.time()
            try:
                actions = fc.fetch_yfinance_corporate_actions(sym)
                if actions:
                    # Tell the store NOT to recompute per-upsert; we batch at
                    # the end (one pass per touched symbol).
                    with FlowStore() as store:
                        store.upsert_corporate_actions(
                            actions, recompute_adj_close=False,
                        )
                    n_split = sum(1 for a in actions if a["action_type"] == "split")
                    n_div = sum(1 for a in actions if a["action_type"] == "dividend")
                    splits_seen += n_split
                    divs_seen += n_div
                    if n_split > 0:
                        touched_for_recompute.add(sym)
                    _log(sym, "ok", f"split={n_split} div={n_div}")
                    ok += 1
                    dt = time.time() - t0
                    print(f"[{i:4d}/{len(pending)}] {sym:18s} ok split={n_split:2d} "
                          f"div={n_div:3d}  ({dt:.1f}s)", flush=True)
                else:
                    _log(sym, "empty", "no actions")
                    print(f"[{i:4d}/{len(pending)}] {sym:18s} -- no actions",
                          flush=True)
            except Exception as e:
                failed.append((sym, str(e)))
                _log(sym, "fail", str(e)[:200])
                print(f"[{i:4d}/{len(pending)}] {sym:18s} FAIL {e}", flush=True)

            if i < len(pending):
                time.sleep(args.sleep)

    print("\n=== Corporate actions backfill summary ===")
    print(f"  Symbols ok:           {ok}/{len(pending)}")
    print(f"  Split/bonus rows:     {splits_seen:,}")
    print(f"  Dividend rows:        {divs_seen:,}")
    print(f"  Failed:               {len(failed)}")
    print(f"  Touched (need adj_close recompute): {len(touched_for_recompute)}")

    if failed:
        print("  First 10 failures:")
        for sym, err in failed[:10]:
            print(f"    {sym}: {err[:120]}")

    if not args.no_recompute and touched_for_recompute:
        print(f"\nRecomputing adj_close for {len(touched_for_recompute)} touched symbols...")
        with FlowStore() as store:
            for i, sym in enumerate(sorted(touched_for_recompute), 1):
                try:
                    store.recompute_adj_close(sym)
                    if i % 50 == 0:
                        print(f"  [{i}/{len(touched_for_recompute)}] recomputed", flush=True)
                except Exception as e:
                    print(f"  recompute fail {sym}: {e}", flush=True)
        print("  done.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
