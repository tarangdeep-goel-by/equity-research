"""Contract tests: schema regression via syrupy snapshots.

Ensures database schema (table names, column definitions) doesn't
change unexpectedly. First run generates snapshots; subsequent runs
compare and fail on drift.
"""

from __future__ import annotations

import pytest

from flowtracker.store import FlowStore


class TestSchemaSnapshot:
    def test_table_names_snapshot(self, store: FlowStore, snapshot):
        """All table names must match the recorded snapshot."""
        tables = sorted(
            r["name"]
            for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
            ).fetchall()
        )
        assert tables == snapshot

    def test_table_count(self, store: FlowStore):
        """Verify the expected number of tables exists (regression guard)."""
        tables = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
        ).fetchall()
        count = len(tables)
        # Currently ~60 tables (Wave 4+5 added ar_esop_summary, ar_five_year_summary,
        # shareholding_breakdown, adr_gdr_outstanding, data_quality_flags).
        assert 35 <= count <= 80, f"Expected 35-80 tables, got {count}"

    def test_column_names_snapshot(self, store: FlowStore, snapshot):
        """Column names per table must match the recorded snapshot."""
        tables = sorted(
            r["name"]
            for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
            ).fetchall()
        )
        schema: dict[str, list[str]] = {}
        for table in tables:
            cols = store._conn.execute(f"PRAGMA table_info({table})").fetchall()
            schema[table] = sorted(c["name"] for c in cols)
        assert schema == snapshot

    def test_critical_tables_present(self, store: FlowStore):
        """Core tables that are essential to the application must exist."""
        tables = {
            r["name"]
            for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        critical = {
            "daily_flows",
            "quarterly_results",
            "annual_financials",
            "valuation_snapshot",
            "shareholding",
            "promoter_pledge",
            "daily_stock_data",
            "alerts",
            "alert_history",
            "portfolio_holdings",
            "fmp_dcf",
        }
        missing = critical - tables
        assert not missing, f"Missing critical tables: {missing}"
