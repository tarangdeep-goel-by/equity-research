#!/usr/bin/env python3
"""Detect unexplained day-over-day price cliffs (>40%) in daily_stock_data.

For each symbol, compute d/d returns from adj_close (Sprint 0 — falls back to
close when NULL). Moves above threshold with no corporate_actions row within
±2 trading days are written to unresolved_cliffs for manual triage.

Why ±2 days: NSE bhavcopy ex-date and BSE corp-action ex-date sometimes drift
by a session due to record-date / holiday boundaries.

Usage:
  uv run python scripts/reconcile_price_cliffs.py
  uv run python scripts/reconcile_price_cliffs.py --symbol SBIN
  uv run python scripts/reconcile_price_cliffs.py --threshold-pct 30
  uv run python scripts/reconcile_price_cliffs.py --from 2020-01-01 --to 2024-12-31
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowtracker.store import FlowStore


def find_cliffs_for_symbol(
    store: FlowStore, symbol: str, threshold_pct: float,
    date_from: str | None = None, date_to: str | None = None,
) -> list[dict]:
    """Return cliff candidates for ``symbol`` via LAG-based d/d returns
    (adj_close-first, close-fallback)."""
    where_extra = ""
    params: list = [symbol.upper()]
    if date_from:
        where_extra += " AND date >= ?"
        params.append(date_from)
    if date_to:
        where_extra += " AND date <= ?"
        params.append(date_to)
    sql = f"""
        WITH dod AS (
            SELECT symbol, date,
                   COALESCE(adj_close, close) AS px,
                   LAG(COALESCE(adj_close, close)) OVER
                       (PARTITION BY symbol ORDER BY date) AS prev_px
            FROM daily_stock_data
            WHERE symbol = ?{where_extra}
        )
        SELECT symbol, date AS trade_date, prev_px AS prev_close,
               px AS close,
               (px - prev_px) / prev_px * 100.0 AS return_pct
        FROM dod
        WHERE prev_px IS NOT NULL AND prev_px > 0
          AND ABS((px - prev_px) / prev_px * 100.0) > ?
        ORDER BY date
    """
    params.append(threshold_pct)
    return [dict(r) for r in store._conn.execute(sql, tuple(params)).fetchall()]


def has_nearby_corp_action(
    store: FlowStore, symbol: str, trade_date: str, window_days: int = 2,
) -> bool:
    """Check corporate_actions within ±window_days calendar days of trade_date."""
    row = store._conn.execute(
        "SELECT 1 FROM corporate_actions "
        "WHERE symbol = ? AND ex_date BETWEEN DATE(?, '-' || ? || ' days') "
        "AND DATE(?, '+' || ? || ' days') LIMIT 1",
        (symbol.upper(), trade_date, window_days, trade_date, window_days),
    ).fetchone()
    return row is not None


def reconcile(
    store: FlowStore, only_symbol: str | None = None,
    threshold_pct: float = 40.0,
    date_from: str | None = None, date_to: str | None = None,
) -> list[dict]:
    """Run reconciliation. Returns the list of unresolved cliffs written."""
    if only_symbol:
        symbols = [only_symbol.upper()]
    else:
        symbols = [r["symbol"] for r in store._conn.execute(
            "SELECT DISTINCT symbol FROM daily_stock_data ORDER BY symbol"
        ).fetchall()]
    unresolved: list[dict] = []
    for sym in symbols:
        for cliff in find_cliffs_for_symbol(
            store, sym, threshold_pct, date_from, date_to,
        ):
            if has_nearby_corp_action(store, sym, cliff["trade_date"]):
                continue
            unresolved.append(cliff)
    if unresolved:
        store.upsert_unresolved_cliffs(unresolved)
    return unresolved


def print_summary(unresolved: list[dict]) -> None:
    if not unresolved:
        print("No unresolved cliffs found.")
        return
    print(f"\nFlagged {len(unresolved)} unresolved cliff(s).")
    by_symbol = Counter(c["symbol"] for c in unresolved)
    print("\nTop symbols by cliff count:")
    for sym, n in by_symbol.most_common(10):
        print(f"  {sym:<15} {n}")
    worst = sorted(unresolved, key=lambda c: abs(c["return_pct"]), reverse=True)[:10]
    print("\nTop 10 worst cliffs:")
    print(f"  {'symbol':<15} {'trade_date':<12} {'prev':>10} {'close':>10} {'ret%':>8}")
    for c in worst:
        print(
            f"  {c['symbol']:<15} {c['trade_date']:<12} "
            f"{c['prev_close']:>10.2f} {c['close']:>10.2f} {c['return_pct']:>+8.1f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--symbol", help="Restrict to one symbol")
    parser.add_argument("--threshold-pct", type=float, default=40.0,
                        help="Absolute d/d return %% to flag (default 40)")
    parser.add_argument("--from", dest="date_from", help="ISO date — start")
    parser.add_argument("--to", dest="date_to", help="ISO date — end")
    args = parser.parse_args()
    store = FlowStore()
    try:
        unresolved = reconcile(
            store, only_symbol=args.symbol,
            threshold_pct=args.threshold_pct,
            date_from=args.date_from, date_to=args.date_to,
        )
        print_summary(unresolved)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
