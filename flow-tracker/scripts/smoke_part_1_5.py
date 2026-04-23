#!/usr/bin/env python3
"""Part 1.5 smoke — validate Fix #1/#2/#3 on the production DB.

Runs feature_vector + retrieve_top_k_analogs + cohort_stats directly for a
set of stress-test symbols (newly-listed, narrow-industry) and prints the
fields that §1.5.5 Exit Criteria require.

Usage:
    uv run python scripts/smoke_part_1_5.py
    uv run python scripts/smoke_part_1_5.py TMPV CMSINFO INOXINDIA
"""

from __future__ import annotations

import json
import sys
from datetime import date

from flowtracker.store import FlowStore
from flowtracker.research.analog_builder import (
    compute_feature_vector,
    retrieve_top_k_analogs,
    cohort_stats,
)


# Default symbols: each covers a Part 1.5 edge case
# TMPV:       newly-listed demerger (tests is_backfilled + industry-ring fallback)
# CMSINFO:    narrow niche industry (tests relaxation_level != 0)
# INOXINDIA:  small industry, thin-cohort N-reporting
DEFAULT_SYMBOLS = ("TMPV", "CMSINFO", "INOXINDIA")


def smoke_one(store: FlowStore, symbol: str, as_of: str) -> dict:
    vec = compute_feature_vector(store, symbol, as_of)
    retrieval = retrieve_top_k_analogs(
        store, target_symbol=symbol, target_date=as_of,
        target_features=vec, k=20,
    )
    stats = cohort_stats(retrieval["analogs"])
    return {
        "symbol": symbol,
        "as_of": as_of,
        "feature_vector": {
            "industry": vec.get("industry"),
            "mcap_bucket": vec.get("mcap_bucket"),
            "listed_days": vec.get("listed_days"),
            "is_backfilled": vec.get("is_backfilled"),
            "roce_3yr_delta": vec.get("roce_3yr_delta"),
        },
        "cohort": {
            "relaxation_level": retrieval["relaxation_level"],
            "relaxation_label": retrieval["relaxation_label"],
            "unique_symbols": retrieval["unique_symbols"],
            "gross_count": retrieval["gross_count"],
            "analog_count": len(retrieval["analogs"]),
        },
        "stats": {
            "gross_N": stats["gross_N"],
            "unique_symbols": stats["unique_symbols"],
            "informative_N_3m": stats.get("informative_N_3m"),
            "informative_N_6m": stats.get("informative_N_6m"),
            "informative_N_12m": stats.get("informative_N_12m"),
            "recovery_rate_pct": stats.get("recovery_rate_pct"),
            "blow_up_rate_pct": stats.get("blow_up_rate_pct"),
            "per_horizon_12m": stats["per_horizon"]["12m"],
            "per_horizon_3m": stats["per_horizon"]["3m"],
        },
    }


def main() -> int:
    symbols = sys.argv[1:] or list(DEFAULT_SYMBOLS)
    as_of = date.today().isoformat()
    print(f"Part 1.5 smoke — as_of={as_of}, symbols={symbols}\n")

    with FlowStore() as store:
        results = [smoke_one(store, s, as_of) for s in symbols]

    for r in results:
        print(json.dumps(r, indent=2, default=str))
        print("-" * 60)

    # Exit-criteria checks (§1.5.5)
    print("\nExit criteria check:")
    all_pass = True
    for r in results:
        sym = r["symbol"]
        cohort = r["cohort"]
        stats = r["stats"]
        vec = r["feature_vector"]

        unique_ok = cohort["unique_symbols"] >= 5 or cohort["relaxation_level"] >= 1
        print(f"  {sym:10s} unique_symbols>=5 OR relaxation>=1: {'PASS' if unique_ok else 'FAIL'} "
              f"(unique={cohort['unique_symbols']}, relax={cohort['relaxation_level']})")

        info_N_present = stats["informative_N_12m"] is not None and stats["informative_N_3m"] is not None
        print(f"  {sym:10s} informative_N fields present:           "
              f"{'PASS' if info_N_present else 'FAIL'} "
              f"(N_3m={stats['informative_N_3m']}, N_12m={stats['informative_N_12m']})")

        # is_backfilled is only expected True for newly-listed tickers
        listed_ok = vec["listed_days"] is not None
        print(f"  {sym:10s} listed_days populated:                  "
              f"{'PASS' if listed_ok else 'FAIL'} (listed_days={vec['listed_days']})")

        all_pass = all_pass and unique_ok and info_N_present and listed_ok

    print(f"\nOverall: {'PASS' if all_pass else 'FAIL'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
