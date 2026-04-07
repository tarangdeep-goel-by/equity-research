#!/usr/bin/env python3
"""P-3B.2: Migrate existing DB percentage fields from decimal to percentage form.

One-time migration script. Run ONCE ONLY after taking a DB backup.
WARNING: NOT fully idempotent for values near 0 (e.g., 0.5% OPM = 0.005 decimal).
The abs(field) < 1 guard prevents most double-conversion but tiny percentages
(< 1% after conversion) would be re-converted on a second run. Run once only.
"""
import os
import sqlite3
import sys

DB_PATH = os.path.expanduser("~/.local/share/flowtracker/flows.db")


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Step 1: valuation_snapshot — 8 fields ×100
    # Guard: operating_margin IS NOT NULL AND abs(operating_margin) < 1
    # This detects decimal format (0.25) and skips already-percentage values (25.0)
    before = cur.execute("SELECT COUNT(*) FROM valuation_snapshot WHERE operating_margin IS NOT NULL AND abs(operating_margin) < 1").fetchone()[0]
    cur.execute("""
        UPDATE valuation_snapshot SET
            gross_margin = gross_margin * 100,
            operating_margin = operating_margin * 100,
            net_margin = net_margin * 100,
            roe = roe * 100,
            roa = roa * 100,
            revenue_growth = revenue_growth * 100,
            earnings_growth = earnings_growth * 100,
            earnings_quarterly_growth = earnings_quarterly_growth * 100
        WHERE operating_margin IS NOT NULL AND abs(operating_margin) < 1
    """)
    after = cur.execute("SELECT COUNT(*) FROM valuation_snapshot WHERE operating_margin IS NOT NULL AND abs(operating_margin) < 1").fetchone()[0]
    print(f"[1/4] valuation_snapshot: converted {before - after} rows (decimal → percentage)")

    # Step 2: quarterly_results — 2 fields ×100
    before = cur.execute("SELECT COUNT(*) FROM quarterly_results WHERE operating_margin IS NOT NULL AND abs(operating_margin) < 1").fetchone()[0]
    cur.execute("""
        UPDATE quarterly_results SET
            operating_margin = operating_margin * 100,
            net_margin = net_margin * 100
        WHERE operating_margin IS NOT NULL AND abs(operating_margin) < 1
    """)
    after = cur.execute("SELECT COUNT(*) FROM quarterly_results WHERE operating_margin IS NOT NULL AND abs(operating_margin) < 1").fetchone()[0]
    print(f"[2/4] quarterly_results: converted {before - after} rows (decimal → percentage)")

    # Step 3: consensus_estimates — 1 field ×100
    # Use abs(field) <= 1 for growth (100% growth = 1.0 in decimal)
    before = cur.execute("SELECT COUNT(*) FROM consensus_estimates WHERE earnings_growth IS NOT NULL AND abs(earnings_growth) <= 1").fetchone()[0]
    cur.execute("""
        UPDATE consensus_estimates SET
            earnings_growth = earnings_growth * 100
        WHERE earnings_growth IS NOT NULL AND abs(earnings_growth) <= 1
    """)
    after = cur.execute("SELECT COUNT(*) FROM consensus_estimates WHERE earnings_growth IS NOT NULL AND abs(earnings_growth) <= 1").fetchone()[0]
    print(f"[3/4] consensus_estimates: converted {before - after} rows (decimal → percentage)")

    # Step 4: FMP tables — expect 0 rows
    fmp_km = cur.execute("SELECT COUNT(*) FROM fmp_key_metrics").fetchone()[0]
    fmp_fg = cur.execute("SELECT COUNT(*) FROM fmp_financial_growth").fetchone()[0]
    print(f"[4/4] FMP tables: {fmp_km} key_metrics rows, {fmp_fg} financial_growth rows (ingestion code updated, no migration needed)")

    conn.commit()
    conn.close()
    print("\nP-3B.2 migration complete.")


if __name__ == "__main__":
    main()
