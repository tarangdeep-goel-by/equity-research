#!/usr/bin/env python3
"""Check data freshness in the flowtracker database.

Run after daily crons to verify data is current.
Usage: uv run python scripts/check-freshness.py
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from flowtracker.store import FlowStore


def main() -> int:
    today = date.today()
    weekday = today.weekday()  # Mon=0, Sun=6

    # On weekends, allow data to be from Friday
    if weekday == 5:  # Saturday
        expected_freshness = today - timedelta(days=1)
    elif weekday == 6:  # Sunday
        expected_freshness = today - timedelta(days=2)
    else:
        expected_freshness = today - timedelta(days=1)  # Allow 1 day lag

    stale_threshold = expected_freshness.isoformat()

    with FlowStore() as store:
        checks: list[tuple[str, bool]] = []

        # --- Daily data checks ---

        latest_flow = store.get_latest()
        checks.append((
            "FII/DII Flows",
            latest_flow is not None and str(latest_flow.date) >= stale_threshold,
        ))

        macro = store.get_macro_latest()
        checks.append((
            "Macro Indicators",
            macro is not None and macro.date >= stale_threshold,
        ))

        top_del = store.get_top_delivery()
        checks.append(("Bhavcopy/Delivery", len(top_del) > 0))

        mf_daily = store.get_mf_daily_latest()
        checks.append(("MF Daily Flows", len(mf_daily) > 0))

        # --- Weekly data checks (only flag if > 10 days old) ---

        sbin_val = store.get_valuation_history("SBIN", days=10)
        checks.append(("Valuation Snapshots", len(sbin_val) > 0))

        # --- Monthly data checks (only flag if > 40 days old) ---

        mf_aum = store.get_mf_latest_aum()
        checks.append(("MF Monthly AUM", mf_aum is not None))

    # Print results
    all_ok = True
    print(f"\n  Flow-Tracker Data Freshness Check ({today})")
    print(f"  {'=' * 50}")
    for name, is_fresh in checks:
        status = "OK" if is_fresh else "STALE"
        icon = "\u2713" if is_fresh else "\u2717"
        print(f"  {icon}  {name:<25} {status}")
        if not is_fresh:
            all_ok = False

    print(f"  {'=' * 50}")
    if all_ok:
        print("  All data sources are fresh.\n")
    else:
        print("  WARNING: Some data sources are stale!\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
