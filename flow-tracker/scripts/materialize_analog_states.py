#!/usr/bin/env python3
"""Materialize historical_states + analog_forward_returns for the Nifty 500
universe across the last 10 years of quarter-ends.

Output: ~20K rows in historical_states (500 symbols × 40 quarters). Runtime
roughly 10-15 minutes on a warm DB. Idempotent — re-running updates existing
rows via INSERT OR REPLACE. Run after Sprint 0 adj_close backfill.

Usage:
    uv run python scripts/materialize_analog_states.py
    uv run python scripts/materialize_analog_states.py --symbol INOXINDIA  # one symbol
    uv run python scripts/materialize_analog_states.py --years 5           # shallower
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flowtracker.store import FlowStore
from flowtracker.research.analog_builder import (
    compute_feature_vector, compute_forward_returns,
)


def quarter_ends(years: int, end_date: date | None = None) -> list[str]:
    """Generate quarter-end date strings for the last `years` years."""
    if end_date is None:
        end_date = date.today()
    out: list[str] = []
    # Walk backwards by quarter
    for y in range(end_date.year, end_date.year - years - 1, -1):
        for m, d in [(3, 31), (6, 30), (9, 30), (12, 31)]:
            qe = date(y, m, d)
            if qe <= end_date:
                out.append(qe.isoformat())
    return sorted(set(out), reverse=True)


def target_symbols(store: FlowStore, only_symbol: str | None = None) -> list[str]:
    """Universe: Nifty 500 constituents (Nifty 50 + Next 50 + Midcap 150 + Smallcap 250)."""
    if only_symbol:
        return [only_symbol.upper()]
    rows = store._conn.execute(
        "SELECT DISTINCT symbol FROM index_constituents "
        "WHERE index_name IN ('NIFTY 50', 'NIFTY NEXT 50', 'NIFTY MIDCAP 150', 'NIFTY SMALLCAP 250') "
        "ORDER BY symbol"
    ).fetchall()
    return [r["symbol"] for r in rows]


def upsert_feature_row(store: FlowStore, symbol: str, qtr: str, vec: dict) -> None:
    cols = (
        "symbol", "quarter_end",
        "pe_trailing", "pe_percentile_10y",
        "roce_current", "roce_3yr_delta",
        "revenue_cagr_3yr", "opm_trend",
        "promoter_pct", "fii_pct", "fii_delta_2q",
        "mf_pct", "mf_delta_2q", "pledge_pct",
        "price_vs_sma200", "delivery_pct_6m", "rsi_14",
        "industry", "mcap_bucket",
        "listed_days", "is_backfilled",
        "industry_as_of_date", "industry_source",
    )
    values = tuple(vec.get(c) if c not in ("symbol", "quarter_end") else None for c in cols)
    values = (symbol, qtr) + values[2:]
    # SQLite stores booleans as 0/1 — coerce is_backfilled explicitly
    values = tuple(
        1 if (c == "is_backfilled" and v is True)
        else 0 if (c == "is_backfilled" and v is False)
        else v
        for c, v in zip(cols, values)
    )
    store._conn.execute(
        f"INSERT OR REPLACE INTO historical_states ({','.join(cols)}) "
        f"VALUES ({','.join('?' * len(cols))})",
        values,
    )


def upsert_returns_row(store: FlowStore, symbol: str, qtr: str, rets: dict) -> None:
    store._conn.execute(
        "INSERT OR REPLACE INTO analog_forward_returns "
        "(symbol, as_of_date, return_3m_pct, return_6m_pct, return_12m_pct, "
        " excess_3m_vs_sector, excess_12m_vs_sector, excess_12m_vs_nifty, outcome_label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            symbol, qtr,
            rets.get("return_3m_pct"), rets.get("return_6m_pct"), rets.get("return_12m_pct"),
            rets.get("excess_3m_vs_sector"), rets.get("excess_12m_vs_sector"),
            rets.get("excess_12m_vs_nifty"), rets.get("outcome_label"),
        ),
    )


def materialize(
    store: FlowStore, only_symbol: str | None, years: int,
    as_of: date | None = None,
) -> dict:
    """Materialize feature + return rows up through ``as_of`` (default: today).

    Passing ``as_of`` ensures the quarter-end walk halts at the backtest
    horizon AND that ``compute_feature_vector`` / ``compute_forward_returns``
    don't peek beyond it. Without this, ``FLOWTRACK_AS_OF=2024-12-31``
    correctly anchored agent prompts (PR #80) but materialization still
    contaminated the cohort with wall-clock data.
    """
    symbols = target_symbols(store, only_symbol)
    qtrs = quarter_ends(years, end_date=as_of)
    print(
        f"Materializing {len(symbols)} symbols × {len(qtrs)} quarter-ends = "
        f"~{len(symbols) * len(qtrs):,} feature rows", flush=True,
    )

    t0 = time.time()
    wrote_features = 0
    wrote_returns = 0
    failures: list[tuple[str, str]] = []

    for i, sym in enumerate(symbols, 1):
        try:
            for qtr in qtrs:
                vec = compute_feature_vector(store, sym, qtr)
                # Skip if too sparse — require at least industry + one numeric feature
                non_null_features = sum(
                    1 for k, v in vec.items() if v is not None and k not in ("industry", "mcap_bucket")
                )
                if vec.get("industry") is None or non_null_features < 3:
                    continue
                upsert_feature_row(store, sym, qtr, vec)
                wrote_features += 1
                rets = compute_forward_returns(store, sym, qtr)
                upsert_returns_row(store, sym, qtr, rets)
                wrote_returns += 1
            # Commit per-symbol so a mid-run failure doesn't lose progress
            store._conn.commit()
        except Exception as exc:
            failures.append((sym, str(exc)))
            print(f"  ⚠ {sym}: {exc}", flush=True)

        if i % 25 == 0 or i == len(symbols):
            dt = time.time() - t0
            rate = i / dt if dt > 0 else 0
            eta = (len(symbols) - i) / rate if rate > 0 else 0
            print(
                f"  [{i}/{len(symbols)}] {wrote_features:,} state rows, "
                f"{wrote_returns:,} return rows, {rate:.1f} sym/s, eta {eta:.0f}s",
                flush=True,
            )

    return {
        "symbols": len(symbols), "failures": failures,
        "feature_rows": wrote_features, "return_rows": wrote_returns,
        "elapsed_sec": time.time() - t0,
    }


def _resolve_as_of(cli_value: str | None) -> date:
    """Resolve the materialization horizon: CLI flag > env var > today.

    Surfaces a clear ``ValueError`` for malformed inputs from either source
    rather than silently falling back, so a typo in a backtest doesn't
    quietly run against wall-clock.
    """
    if cli_value:
        return date.fromisoformat(cli_value)
    env_val = os.environ.get("FLOWTRACK_AS_OF")
    if env_val:
        return date.fromisoformat(env_val)
    return date.today()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", help="Run for one symbol")
    parser.add_argument("--years", type=int, default=10, help="Years of history (default 10)")
    parser.add_argument(
        "--as-of", dest="as_of", default=None,
        help="ISO date YYYY-MM-DD; falls back to FLOWTRACK_AS_OF env var, then today.",
    )
    args = parser.parse_args()

    as_of = _resolve_as_of(args.as_of)

    store = FlowStore()
    try:
        stats = materialize(store, args.symbol, args.years, as_of=as_of)
        print(
            f"\n✓ Done in {stats['elapsed_sec']:.1f}s: "
            f"{stats['symbols']} symbols, {stats['feature_rows']:,} feature rows, "
            f"{stats['return_rows']:,} return rows, {len(stats['failures'])} failures"
        )
        return 1 if stats["failures"] else 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
