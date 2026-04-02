#!/usr/bin/env python3
"""P-3B: Migrate existing DB to standardized crore units.

One-time migration script. Run AFTER taking a DB backup.
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

    # ── Step 1: Delete yfinance annual_financials rows ────────────────
    # yfinance rows have employee_cost IS NULL and revenue in raw rupees (> 100000 Cr)
    before = cur.execute("SELECT COUNT(*) FROM annual_financials").fetchone()[0]
    cur.execute(
        "DELETE FROM annual_financials WHERE employee_cost IS NULL AND revenue > 100000"
    )
    after = cur.execute("SELECT COUNT(*) FROM annual_financials").fetchone()[0]
    deleted_annual = before - after
    print(f"[1/5] annual_financials: deleted {deleted_annual} yfinance rows ({before} → {after})")

    # ── Step 2: Delete yfinance quarterly_results rows ────────────────
    # yfinance rows have expenses IS NULL and revenue in raw rupees
    before = cur.execute("SELECT COUNT(*) FROM quarterly_results").fetchone()[0]
    cur.execute(
        "DELETE FROM quarterly_results WHERE expenses IS NULL AND revenue > 100000"
    )
    after = cur.execute("SELECT COUNT(*) FROM quarterly_results").fetchone()[0]
    deleted_qtr = before - after
    print(f"[2/5] quarterly_results: deleted {deleted_qtr} yfinance rows ({before} → {after})")

    # ── Step 3: Convert valuation_snapshot monetary fields to crores ──
    # Only convert rows still in rupees (market_cap > 1,000,000 means rupees, not crores)
    count = cur.execute(
        "SELECT COUNT(*) FROM valuation_snapshot WHERE market_cap > 1000000"
    ).fetchone()[0]
    cur.execute("""
        UPDATE valuation_snapshot SET
            market_cap = market_cap / 1e7,
            enterprise_value = enterprise_value / 1e7,
            total_cash = total_cash / 1e7,
            total_debt = total_debt / 1e7,
            free_cash_flow = free_cash_flow / 1e7,
            operating_cash_flow = operating_cash_flow / 1e7
        WHERE market_cap > 1000000
    """)
    print(f"[3/5] valuation_snapshot: converted {count} rows to crores")

    # ── Step 4: Convert insider_transactions value to crores ──────────
    # Values > 1,000,000 are in rupees (largest single Cr trade would be < 1M Cr)
    count = cur.execute(
        "SELECT COUNT(*) FROM insider_transactions WHERE value > 1000000"
    ).fetchone()[0]
    cur.execute(
        "UPDATE insider_transactions SET value = value / 1e7 WHERE value > 1000000"
    )
    print(f"[4/5] insider_transactions: converted {count} rows to crores")

    # ── Step 5: Rename mf_scheme_holdings column lakhs → crores ───────
    # SQLite doesn't support ALTER COLUMN RENAME before 3.25, so recreate table
    count = cur.execute("SELECT COUNT(*) FROM mf_scheme_holdings").fetchone()[0]
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mf_scheme_holdings_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            amc TEXT NOT NULL,
            scheme_name TEXT NOT NULL,
            isin TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            market_value_cr REAL NOT NULL,
            pct_of_nav REAL NOT NULL,
            fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(month, amc, scheme_name, isin)
        )
    """)
    cur.execute("""
        INSERT INTO mf_scheme_holdings_new
            (id, month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav, fetched_at)
        SELECT
            id, month, amc, scheme_name, isin, stock_name, quantity, market_value_lakhs / 100.0, pct_of_nav, fetched_at
        FROM mf_scheme_holdings
    """)
    cur.execute("DROP TABLE mf_scheme_holdings")
    cur.execute("ALTER TABLE mf_scheme_holdings_new RENAME TO mf_scheme_holdings")
    print(f"[5/5] mf_scheme_holdings: renamed column + converted {count} rows (lakhs → crores)")

    conn.commit()
    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
