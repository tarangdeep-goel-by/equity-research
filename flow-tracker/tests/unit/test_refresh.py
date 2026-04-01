"""Tests for refresh._is_fresh (research/refresh.py).

Tests the freshness-checking logic that determines whether data
needs to be re-fetched before a research agent runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from flowtracker.research.refresh import _is_fresh
from flowtracker.store import FlowStore


class TestIsFresh:
    def test_fresh_valuation_data(self, populated_store: FlowStore):
        """Valuation snapshots have date column; recent data → fresh."""
        # Insert a row with today's date to ensure freshness
        now_str = datetime.now().strftime("%Y-%m-%d")
        populated_store._conn.execute(
            "INSERT OR REPLACE INTO valuation_snapshot (symbol, date, price, pe_trailing) VALUES (?, ?, ?, ?)",
            ("FRESHTEST", now_str, 100.0, 10.0),
        )
        populated_store._conn.commit()
        assert _is_fresh(populated_store, "FRESHTEST", "valuation_snapshot", hours=6) is True

    def test_stale_data(self, populated_store: FlowStore):
        """Data from many days ago → stale."""
        old_ts = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        old_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        populated_store._conn.execute(
            "INSERT OR REPLACE INTO valuation_snapshot (symbol, date, price, pe_trailing, fetched_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("STALETEST", old_date, 100.0, 10.0, old_ts),
        )
        populated_store._conn.commit()
        assert _is_fresh(populated_store, "STALETEST", "valuation_snapshot", hours=6) is False

    def test_empty_table_returns_false(self, store: FlowStore):
        """No rows for the symbol → not fresh."""
        assert _is_fresh(store, "NONEXIST", "valuation_snapshot", hours=6) is False

    def test_fetched_at_column_preferred(self, populated_store: FlowStore):
        """If fetched_at column exists and is recent, data is fresh."""
        # quarterly_results has a fetched_at column
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        populated_store._conn.execute(
            "UPDATE quarterly_results SET fetched_at = ? WHERE symbol = ?",
            (now_str, "SBIN"),
        )
        populated_store._conn.commit()
        assert _is_fresh(populated_store, "SBIN", "quarterly_results", hours=6) is True

    def test_date_fallback_when_no_fetched_at(self, populated_store: FlowStore):
        """Tables without fetched_at fall back to date column."""
        # fmp_dcf has date column but likely no fetched_at
        result = _is_fresh(populated_store, "SBIN", "fmp_dcf", hours=999999)
        # With a huge hours window, even old data should be fresh
        assert result is True

    def test_nonexistent_table_returns_false(self, store: FlowStore):
        """Querying a table that doesn't exist → False (exception caught)."""
        assert _is_fresh(store, "SBIN", "nonexistent_table_xyz", hours=6) is False
