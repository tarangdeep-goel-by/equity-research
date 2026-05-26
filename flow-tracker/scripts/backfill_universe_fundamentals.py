#!/usr/bin/env python3
"""Universe-wide fundamentals backfill — Screener.in HTML + Excel per symbol.

Target: every symbol with rows in ``daily_stock_data`` since 2024-01-01,
>= 100 trading days, >= ₹1Cr/day average turnover, NOT already present
in ``quarterly_results``. Populates 5 tables in one pass per symbol:

    quarterly_results
    annual_financials
    screener_ratios
    valuation_snapshot   (current snapshot, separate yfinance call)
    corporate_actions    (handled by backfill_universe_corporate_actions.py)

Behavior:
  * Mirror of the per-symbol path in ``fund_commands.py::backfill`` (HTML
    page → quarterly + ratios, Excel → annual EPS/financials).
  * Skips symbols already in ``quarterly_results`` (resume-safe).
  * 3s sleep between symbols to stay under Screener's rate limit.
  * Logs progress to ``/tmp/fund_backfill_progress.log``; re-running picks
    up after the last successful symbol.

Usage:
    uv run python scripts/backfill_universe_fundamentals.py
    uv run python scripts/backfill_universe_fundamentals.py --test 5
    uv run python scripts/backfill_universe_fundamentals.py --min-turnover-cr 0.5
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


_PROGRESS_LOG = Path("/tmp/fund_backfill_progress.log")


def _log_progress(symbol: str, status: str, note: str = "") -> None:
    """Append a JSON line to the progress log."""
    line = json.dumps({
        "ts": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "status": status,
        "note": note,
    })
    with _PROGRESS_LOG.open("a") as fp:
        fp.write(line + "\n")


def _already_processed() -> set[str]:
    """Read past progress log to skip symbols we've already attempted."""
    if not _PROGRESS_LOG.exists():
        return set()
    done: set[str] = set()
    with _PROGRESS_LOG.open() as fp:
        for line in fp:
            try:
                entry = json.loads(line)
                # Treat any prior attempt (ok/fail) as done so we don't
                # re-hammer 404s. Use --force-retry to override.
                done.add(entry["symbol"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def select_universe(store: FlowStore, min_turnover_cr: float, min_days: int) -> list[str]:
    """Symbols present in daily_stock_data with sufficient liquidity,
    NOT already in quarterly_results.
    """
    rows = store._conn.execute(
        """
        WITH active AS (
            SELECT symbol,
                   COUNT(*) AS days,
                   AVG(close * COALESCE(volume, 0)) / 1e7 AS avg_turnover_cr
              FROM daily_stock_data
             WHERE date >= '2024-01-01'
             GROUP BY symbol
            HAVING COUNT(*) >= ?
               AND AVG(close * COALESCE(volume, 0)) / 1e7 >= ?
        )
        SELECT symbol FROM active
         WHERE symbol NOT IN (SELECT symbol FROM quarterly_results)
         ORDER BY symbol
        """,
        (min_days, min_turnover_cr),
    ).fetchall()
    return [r["symbol"] for r in rows]


def backfill_symbol(sc: ScreenerClient, store: FlowStore, symbol: str) -> dict:
    """Fetch + persist quarterly + annual + ratios for one symbol.

    Returns a stats dict ``{quarters, annual, ratios}``. Raises ScreenerError
    on 404/login/parse failure — caller decides whether to skip.
    """
    html = sc.fetch_company_page(symbol)
    quarters = sc.parse_quarterly_from_html(symbol, html)
    excel_bytes = sc.download_excel(symbol)
    annual_fin = sc.parse_annual_financials(symbol, excel_bytes)
    ratios = sc.parse_ratios_from_html(symbol, html)

    # Fallback: HTML parsing missed quarters — try Excel
    if not quarters:
        quarters = sc.parse_quarterly_results(symbol, excel_bytes)

    stats = {"quarters": 0, "annual": 0, "ratios": 0}
    if quarters:
        store.upsert_quarterly_results(quarters)
        stats["quarters"] = len(quarters)
    if annual_fin:
        store.upsert_annual_financials(annual_fin)
        stats["annual"] = len(annual_fin)
    if ratios:
        store.upsert_screener_ratios(ratios)
        stats["ratios"] = len(ratios)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=int, default=0, help="Process N symbols only (smoke test)")
    parser.add_argument("--min-turnover-cr", type=float, default=1.0,
                        help="Min avg daily turnover (₹Cr) since 2024-01-01")
    parser.add_argument("--min-days", type=int, default=100,
                        help="Min trading days present since 2024-01-01")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="Sleep between symbols (Screener rate limit)")
    parser.add_argument("--force-retry", action="store_true",
                        help="Re-attempt symbols that previously failed")
    args = parser.parse_args()

    with FlowStore() as store:
        all_syms = select_universe(store, args.min_turnover_cr, args.min_days)

    if not all_syms:
        print("No symbols matched the universe filter.")
        return 0

    skip = set() if args.force_retry else _already_processed()
    pending = [s for s in all_syms if s not in skip]
    skipped_due_to_log = len(all_syms) - len(pending)
    if args.test:
        pending = pending[: args.test]

    print(f"Universe: {len(all_syms)} symbols matching filter")
    print(f"  Already attempted (resume-skip via progress log): {skipped_due_to_log}")
    print(f"  To process now: {len(pending)}")
    if not pending:
        return 0

    totals = {"quarters": 0, "annual": 0, "ratios": 0}
    ok = 0
    failed: list[tuple[str, str]] = []

    try:
        with ScreenerClient() as sc:
            for i, sym in enumerate(pending, 1):
                t0 = time.time()
                try:
                    # Open + close a store per symbol so we never hold the
                    # writer lock across the 1-3s Screener fetch — keeps the
                    # parallel mf/fno backfills moving.
                    with FlowStore() as store:
                        stats = backfill_symbol(sc, store, sym)
                    for k in totals:
                        totals[k] += stats[k]
                    if stats["quarters"] or stats["annual"]:
                        _log_progress(sym, "ok", f"q={stats['quarters']} a={stats['annual']} r={stats['ratios']}")
                        ok += 1
                    else:
                        _log_progress(sym, "empty", "no rows parsed")
                    dt = time.time() - t0
                    print(f"[{i:4d}/{len(pending)}] {sym:20s} ok q={stats['quarters']:3d} "
                          f"a={stats['annual']:3d} r={stats['ratios']:3d}  ({dt:.1f}s)",
                          flush=True)
                except ScreenerError as e:
                    failed.append((sym, str(e)))
                    _log_progress(sym, "fail", str(e)[:200])
                    print(f"[{i:4d}/{len(pending)}] {sym:20s} FAIL  {e}", flush=True)
                except Exception as e:  # pragma: no cover - defensive
                    failed.append((sym, f"unexpected: {e}"))
                    _log_progress(sym, "error", str(e)[:200])
                    print(f"[{i:4d}/{len(pending)}] {sym:20s} ERROR {e}", flush=True)

                if i < len(pending):
                    time.sleep(args.sleep)
    except ScreenerError as e:
        print(f"\nScreener.in login failed: {e}")
        return 1

    print("\n=== Backfill summary ===")
    print(f"  Symbols ok:        {ok}/{len(pending)}")
    print(f"  Quarterly rows:    {totals['quarters']:,}")
    print(f"  Annual rows:       {totals['annual']:,}")
    print(f"  Ratio rows:        {totals['ratios']:,}")
    print(f"  Failed symbols:    {len(failed)}")
    if failed:
        print("  First 20 failures:")
        for sym, err in failed[:20]:
            print(f"    {sym}: {err[:100]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
