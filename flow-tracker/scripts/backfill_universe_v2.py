#!/usr/bin/env python3
"""Universe-v2 backfill — expand the remaining narrow tables to full NSE EQ.

Companion to ``backfill_universe_fundamentals.py`` (which owns
quarterly_results / annual_financials / valuation_snapshot). This script
extends the *other* six tables that still hover near the Nifty-500 ceiling
to the full ``daily_stock_data`` universe (~2,000 liquid NSE EQ symbols):

    shareholding              -- NSE XBRL shareholding patterns (last 4 Qs)
    shareholding_breakdown    -- granular sub-categories (same XBRL pass)
    promoter_pledge           -- promoter pledge % (same XBRL pass)
    screener_charts           -- 21yr PE + price history (Screener Chart API)
    quarterly_balance_sheet   -- yfinance quarterly BS (crores)
    quarterly_cash_flow       -- Screener Excel fiscal-year CF (crores) —
                                 yfinance only covered ~49/1700 symbols, so
                                 we now pull annual CF rows from Screener
                                 (source='screener') for full coverage.
    estimate_revisions        -- yfinance analyst EPS trend + revisions

Behavior:
  * Liquid-universe filter mirrors backfill_universe_fundamentals.py
    (>= 100 trading days, >= ₹1Cr/day avg turnover since 2024-01-01).
  * Idempotent skip: a symbol with >= 4 shareholding quarters AND any
    screener_charts row is considered done and skipped.
  * 3s sleep between symbols (Screener rate limit).
  * Each upstream fetch is wrapped in try/except so one bad source
    (404, parse error, yfinance hiccup) doesn't take out the whole row.
  * Progress log at /tmp/universe_v2_progress.log -- re-runs resume.
  * Opens a fresh FlowStore per symbol so we never hold the SQLite
    writer lock across the 1-3s network fetch -- keeps the parallel
    fund-backfill / mf-backfill scripts moving.

Usage:
    uv run python scripts/backfill_universe_v2.py
    uv run python scripts/backfill_universe_v2.py --test 5
    uv run python scripts/backfill_universe_v2.py --sleep 3 --min-turnover-cr 1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowtracker.estimates_client import EstimatesClient
from flowtracker.fund_client import FundClient
from flowtracker.holding_client import NSEHoldingClient, NSEHoldingError
from flowtracker.screener_client import ScreenerClient, ScreenerError
from flowtracker.store import FlowStore


_PROGRESS_LOG = Path("/tmp/universe_v2_progress.log")

# Chart types we want from Screener Chart API. 'pe' is adjustment-invariant
# and ideal for analog/long-history work. 'price' is raw and will need to be
# invalidated on splits/bonuses (handled by store.invalidate_screener_price_charts).
_CHART_TYPES = ("pe", "price")


# --- Progress log -------------------------------------------------------


def _log_progress(symbol: str, status: str, note: str = "") -> None:
    """Append a JSON line to the progress log."""
    line = json.dumps(
        {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "symbol": symbol,
            "status": status,
            "note": note,
        }
    )
    with _PROGRESS_LOG.open("a") as fp:
        fp.write(line + "\n")


def _already_processed() -> set[str]:
    """Read past progress log to skip symbols we've already attempted.

    Mirrors backfill_universe_fundamentals: any prior attempt (ok/fail/empty)
    counts so we don't re-hammer 404s. Use --force-retry to override.
    """
    if not _PROGRESS_LOG.exists():
        return set()
    done: set[str] = set()
    with _PROGRESS_LOG.open() as fp:
        for line in fp:
            try:
                entry = json.loads(line)
                done.add(entry["symbol"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


# --- Universe selection -------------------------------------------------


def select_universe(
    store: FlowStore,
    min_turnover_cr: float,
    min_days: int,
) -> list[str]:
    """Liquid NSE EQ symbols NOT already fully covered by both
    `shareholding` (>= 4 distinct quarters) AND `screener_charts` (any row).

    Same liquidity filter as backfill_universe_fundamentals so the two
    scripts agree on what 'the universe' means.
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
        ),
        covered AS (
            SELECT s.symbol
              FROM (SELECT symbol, COUNT(DISTINCT quarter_end) AS qs
                      FROM shareholding GROUP BY symbol) s
              JOIN (SELECT DISTINCT symbol FROM screener_charts) c
                ON c.symbol = s.symbol
             WHERE s.qs >= 4
        )
        SELECT symbol FROM active
         WHERE symbol NOT IN (SELECT symbol FROM covered)
         ORDER BY symbol
        """,
        (min_days, min_turnover_cr),
    ).fetchall()
    return [r["symbol"] for r in rows]


# --- Per-source fetchers (each isolated; one failure won't kill the row) --


def _fetch_shareholding(
    holding_client: NSEHoldingClient, store: FlowStore, symbol: str
) -> dict:
    """NSE XBRL → shareholding + promoter_pledge + shareholding_breakdown.

    Same path as `flowtrack holding fetch -s SYM -q 4`.
    """
    records, pledges, breakdowns = holding_client.fetch_latest_quarters_full(symbol, 4)
    stats = {"sh_rows": 0, "pledge_rows": 0, "breakdown_rows": 0}
    if records:
        store.upsert_shareholding(records)
        stats["sh_rows"] = len(records)
    if pledges:
        store.upsert_promoter_pledges(pledges)
        stats["pledge_rows"] = len(pledges)
    if breakdowns:
        store.upsert_shareholding_breakdown(breakdowns)
        stats["breakdown_rows"] = len(breakdowns)
    return stats


def _resolve_company_id(
    sc: ScreenerClient, store: FlowStore, symbol: str
) -> str | None:
    """Use cached screener_ids if present, else fetch the page + extract +
    cache. Returns None on parse failure -- caller skips chart fetch.
    """
    cached = store.get_screener_ids(symbol)
    if cached and cached[0]:
        return cached[0]
    # Fetch the company page once to extract both IDs (HTML required).
    html = sc.fetch_company_page(symbol)
    company_id, warehouse_id = sc._get_both_ids(html)
    if company_id:
        store.upsert_screener_ids(symbol, company_id, warehouse_id)
        return company_id
    return None


def _fetch_charts(
    sc: ScreenerClient, store: FlowStore, symbol: str
) -> dict:
    """Screener Chart API → screener_charts (pe + price)."""
    stats = {"chart_points": 0}
    company_id = _resolve_company_id(sc, store, symbol)
    if not company_id:
        return stats
    for ctype in _CHART_TYPES:
        try:
            data = sc.fetch_chart_data_by_type(company_id, ctype)
        except (ScreenerError, Exception):  # pragma: no cover - defensive
            continue
        datasets = data.get("datasets", []) if isinstance(data, dict) else []
        if datasets:
            stats["chart_points"] += store.upsert_chart_data(symbol, ctype, datasets)
    return stats


def _fetch_quarterly_bs_cf(
    fc: FundClient, store: FlowStore, symbol: str
) -> dict:
    """yfinance → quarterly_balance_sheet only (crores).

    Cash flow rows are NOT populated here — yfinance returns nothing for
    ~97% of Indian smallcaps. The CF backfill is delegated to
    ``_fetch_screener_cash_flow`` below, which pulls fiscal-year CF from
    Screener (the only reliable source for the full universe).
    """
    payload = fc.fetch_quarterly_bs_cf(symbol)
    stats = {"qbs_rows": 0, "qcf_rows": 0}
    bs_rows = payload.get("balance_sheet", []) if isinstance(payload, dict) else []
    if bs_rows:
        stats["qbs_rows"] = store.upsert_quarterly_balance_sheet(symbol, bs_rows)
    return stats


def _fetch_screener_cash_flow(
    sc: ScreenerClient, store: FlowStore, symbol: str
) -> dict:
    """Screener Excel → quarterly_cash_flow (fiscal-year cadence, crores).

    Replaces the yfinance qCF path which only covered ~49 of ~1,700
    symbols. Screener has CFO/CFI/CFF for every listed Indian company.
    Cadence is annual (FY end) — see
    ``ScreenerClient.parse_quarterly_cash_flow_screener`` for the caveat.
    """
    rows = sc.fetch_quarterly_cash_flow_screener(symbol)
    stats = {"scf_rows": 0}
    if rows:
        stats["scf_rows"] = store.upsert_quarterly_cash_flow(symbol, rows)
    return stats


def _fetch_estimate_revisions(
    ec: EstimatesClient, store: FlowStore, symbol: str
) -> dict:
    """yfinance → estimate_revisions (EPS trend + revisions + momentum)."""
    data = ec.fetch_estimate_revisions(symbol)
    if not data:
        return {"est_rev_rows": 0}
    rows = store.upsert_estimate_revisions(data)
    return {"est_rev_rows": rows if isinstance(rows, int) else 1}


# --- Per-symbol orchestration ------------------------------------------


def backfill_symbol(
    sc: ScreenerClient,
    holding_client: NSEHoldingClient,
    fc: FundClient,
    ec: EstimatesClient,
    store: FlowStore,
    symbol: str,
) -> tuple[dict, list[str]]:
    """Run all 4 fetchers for one symbol. Each is isolated -- failures
    accumulate in `errors`, partial success still commits.

    Returns (stats, errors).
    """
    stats: dict = {
        "sh_rows": 0, "pledge_rows": 0, "breakdown_rows": 0,
        "chart_points": 0, "qbs_rows": 0, "qcf_rows": 0,
        "scf_rows": 0, "est_rev_rows": 0,
    }
    errors: list[str] = []

    try:
        stats.update(_fetch_shareholding(holding_client, store, symbol))
    except NSEHoldingError as e:
        errors.append(f"shareholding: {e}")
    except Exception as e:  # pragma: no cover - defensive
        errors.append(f"shareholding!: {e}")

    try:
        stats.update(_fetch_charts(sc, store, symbol))
    except ScreenerError as e:
        errors.append(f"charts: {e}")
    except Exception as e:  # pragma: no cover - defensive
        errors.append(f"charts!: {e}")

    try:
        stats.update(_fetch_quarterly_bs_cf(fc, store, symbol))
    except Exception as e:  # pragma: no cover - defensive
        errors.append(f"qbs_cf!: {e}")

    try:
        stats.update(_fetch_screener_cash_flow(sc, store, symbol))
    except ScreenerError as e:
        errors.append(f"scf: {e}")
    except Exception as e:  # pragma: no cover - defensive
        errors.append(f"scf!: {e}")

    try:
        stats.update(_fetch_estimate_revisions(ec, store, symbol))
    except Exception as e:  # pragma: no cover - defensive
        errors.append(f"est_rev!: {e}")

    return stats, errors


# --- CLI entrypoint -----------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", type=int, default=0,
                        help="Process N symbols only (smoke test)")
    parser.add_argument("--min-turnover-cr", type=float, default=1.0,
                        help="Min avg daily turnover (₹Cr) since 2024-01-01")
    parser.add_argument("--min-days", type=int, default=100,
                        help="Min trading days present since 2024-01-01")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="Sleep between symbols (Screener rate limit)")
    parser.add_argument("--force-retry", action="store_true",
                        help="Re-attempt symbols that previously failed/empty")
    args = parser.parse_args()

    with FlowStore() as store:
        all_syms = select_universe(store, args.min_turnover_cr, args.min_days)

    if not all_syms:
        print("No symbols matched the universe filter (or all are covered).")
        return 0

    skip = set() if args.force_retry else _already_processed()
    pending = [s for s in all_syms if s not in skip]
    skipped_due_to_log = len(all_syms) - len(pending)
    if args.test:
        pending = pending[: args.test]

    print(f"Universe: {len(all_syms)} symbols missing shareholding/charts coverage")
    print(f"  Already attempted (progress log): {skipped_due_to_log}")
    print(f"  To process now: {len(pending)}")
    if not pending:
        return 0

    totals = {
        "sh_rows": 0, "pledge_rows": 0, "breakdown_rows": 0,
        "chart_points": 0, "qbs_rows": 0, "qcf_rows": 0, "est_rev_rows": 0,
    }
    ok = 0
    partial = 0
    failed: list[tuple[str, str]] = []

    fc = FundClient()
    ec = EstimatesClient()

    try:
        with ScreenerClient() as sc, NSEHoldingClient() as holding_client:
            for i, sym in enumerate(pending, 1):
                t0 = time.time()
                try:
                    with FlowStore() as store:
                        stats, errors = backfill_symbol(
                            sc, holding_client, fc, ec, store, sym
                        )
                    for k in totals:
                        totals[k] += stats[k]

                    # Status classification: any row written counts as ok;
                    # only-errors counts as fail; no rows + no errors is empty.
                    any_rows = any(stats[k] > 0 for k in totals)
                    if any_rows and errors:
                        partial += 1
                        _log_progress(
                            sym, "partial",
                            f"sh={stats['sh_rows']} ch={stats['chart_points']} "
                            f"qbs={stats['qbs_rows']} qcf={stats['qcf_rows']} "
                            f"est={stats['est_rev_rows']} "
                            f"errs=[{'; '.join(errors)[:200]}]"
                        )
                    elif any_rows:
                        ok += 1
                        _log_progress(
                            sym, "ok",
                            f"sh={stats['sh_rows']} ch={stats['chart_points']} "
                            f"qbs={stats['qbs_rows']} qcf={stats['qcf_rows']} "
                            f"est={stats['est_rev_rows']}"
                        )
                    elif errors:
                        failed.append((sym, "; ".join(errors)))
                        _log_progress(sym, "fail", "; ".join(errors)[:200])
                    else:
                        _log_progress(sym, "empty", "no rows from any source")

                    dt = time.time() - t0
                    print(
                        f"[{i:4d}/{len(pending)}] {sym:20s} "
                        f"sh={stats['sh_rows']:2d} ch={stats['chart_points']:5d} "
                        f"qbs={stats['qbs_rows']:2d} qcf={stats['qcf_rows']:2d} "
                        f"est={stats['est_rev_rows']:1d}"
                        + (f"  ERR={len(errors)}" if errors else "")
                        + f"  ({dt:.1f}s)",
                        flush=True,
                    )
                except Exception as e:  # pragma: no cover - defensive
                    failed.append((sym, f"unexpected: {e}"))
                    _log_progress(sym, "error", str(e)[:200])
                    print(
                        f"[{i:4d}/{len(pending)}] {sym:20s} ERROR {e}",
                        flush=True,
                    )

                if i < len(pending):
                    time.sleep(args.sleep)
    except ScreenerError as e:
        print(f"\nScreener.in login failed: {e}")
        return 1

    print("\n=== Universe-v2 backfill summary ===")
    print(f"  Symbols ok:                {ok}/{len(pending)}")
    print(f"  Symbols partial:           {partial}")
    print(f"  Symbols failed:            {len(failed)}")
    print(f"  Shareholding rows:         {totals['sh_rows']:,}")
    print(f"  Pledge rows:               {totals['pledge_rows']:,}")
    print(f"  Breakdown rows:            {totals['breakdown_rows']:,}")
    print(f"  Chart points:              {totals['chart_points']:,}")
    print(f"  Quarterly BS rows:         {totals['qbs_rows']:,}")
    print(f"  Quarterly CF rows:         {totals['qcf_rows']:,}")
    print(f"  Estimate-revision rows:    {totals['est_rev_rows']:,}")
    if failed:
        print("  First 20 failures:")
        for sym, err in failed[:20]:
            print(f"    {sym}: {err[:120]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
