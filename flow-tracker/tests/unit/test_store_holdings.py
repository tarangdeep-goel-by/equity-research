"""Tests for FlowStore holdings-related methods.

Tables: watchlist, shareholding, promoter_pledge, index_constituents
"""

from __future__ import annotations

import pytest

from flowtracker.store import FlowStore
from tests.fixtures.factories import (
    make_shareholding,
    make_promoter_pledges,
    make_index_constituents,
)


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------


class TestWatchlist:
    def test_add_and_get_round_trip(self, store: FlowStore):
        store.add_to_watchlist("SBIN", "State Bank of India")
        wl = store.get_watchlist()
        assert len(wl) == 1
        assert wl[0].symbol == "SBIN"
        assert wl[0].company_name == "State Bank of India"

    def test_add_duplicate_no_error(self, store: FlowStore):
        store.add_to_watchlist("SBIN", "State Bank of India")
        store.add_to_watchlist("SBIN", "State Bank of India")
        wl = store.get_watchlist()
        assert len(wl) == 1

    def test_remove_from_watchlist(self, store: FlowStore):
        store.add_to_watchlist("SBIN")
        store.add_to_watchlist("INFY")
        store.remove_from_watchlist("SBIN")
        wl = store.get_watchlist()
        assert len(wl) == 1
        assert wl[0].symbol == "INFY"

    def test_case_normalization(self, store: FlowStore):
        store.add_to_watchlist("sbin")
        wl = store.get_watchlist()
        assert wl[0].symbol == "SBIN"

    def test_get_empty_watchlist(self, store: FlowStore):
        assert store.get_watchlist() == []


# ---------------------------------------------------------------------------
# shareholding
# ---------------------------------------------------------------------------


class TestShareholding:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        records = make_shareholding("SBIN", n=2)
        count = store.upsert_shareholding(records)
        assert count > 0
        result = store.get_shareholding("SBIN", limit=8)
        assert len(result) > 0
        assert all(r.symbol == "SBIN" for r in result)

    def test_get_shareholding_with_limit(self, store: FlowStore):
        records = make_shareholding("SBIN", n=4)  # 4 quarters x 6 categories = 24
        store.upsert_shareholding(records)
        # limit=1 means 1 quarter = 6 categories max
        result = store.get_shareholding("SBIN", limit=1)
        # limit is multiplied by 6 internally
        assert len(result) <= 6

    def test_shareholding_changes_qoq(self, store: FlowStore):
        records = make_shareholding("SBIN", n=2)  # need >=2 quarters for change
        store.upsert_shareholding(records)
        changes = store.get_shareholding_changes("SBIN")
        assert len(changes) > 0
        for ch in changes:
            assert ch.symbol == "SBIN"
            assert ch.change_pct == pytest.approx(ch.curr_pct - ch.prev_pct)

    def test_shareholding_audit_on_change(self, store: FlowStore):
        from flowtracker.holding_models import ShareholdingRecord
        store.upsert_shareholding([
            ShareholdingRecord(symbol="SBIN", quarter_end="2025-12-31",
                               category="FII", percentage=11.0),
        ])
        store.upsert_shareholding([
            ShareholdingRecord(symbol="SBIN", quarter_end="2025-12-31",
                               category="FII", percentage=12.5),
        ])
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'shareholding'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["old_value"] == "11.0"
        assert rows[0]["new_value"] == "12.5"

    def test_get_shareholding_empty(self, store: FlowStore):
        assert store.get_shareholding("SBIN") == []


# ---------------------------------------------------------------------------
# promoter_pledge
# ---------------------------------------------------------------------------


class TestPromoterPledge:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        pledges = make_promoter_pledges("SBIN", n=4)
        count = store.upsert_promoter_pledges(pledges)
        assert count == 4
        result = store.get_promoter_pledge("SBIN")
        assert len(result) == 4
        # Most recent first
        assert result[0].quarter_end >= result[-1].quarter_end

    def test_get_high_pledge_stocks(self, store: FlowStore):
        # Need index_constituents for the JOIN
        store.upsert_index_constituents(make_index_constituents())
        pledges = make_promoter_pledges("SBIN", n=1)
        store.upsert_promoter_pledges(pledges)
        result = store.get_high_pledge_stocks(min_pledge_pct=1.0)
        assert len(result) >= 1
        assert all(p.pledge_pct >= 1.0 for p in result)

    def test_pledge_audit_on_change(self, store: FlowStore):
        from flowtracker.holding_models import PromoterPledge
        store.upsert_promoter_pledges([
            PromoterPledge(symbol="SBIN", quarter_end="2025-12-31",
                           pledge_pct=2.5, encumbered_pct=3.0),
        ])
        store.upsert_promoter_pledges([
            PromoterPledge(symbol="SBIN", quarter_end="2025-12-31",
                           pledge_pct=5.0, encumbered_pct=6.0),
        ])
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'promoter_pledge'"
        ).fetchall()
        assert len(rows) == 1

    def test_get_pledge_empty(self, store: FlowStore):
        assert store.get_promoter_pledge("SBIN") == []


# ---------------------------------------------------------------------------
# index_constituents
# ---------------------------------------------------------------------------


class TestIndexConstituents:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        constituents = make_index_constituents()
        count = store.upsert_index_constituents(constituents)
        assert count == 3
        result = store.get_index_constituents()
        assert len(result) == 3

    def test_filter_by_index_name(self, store: FlowStore):
        from flowtracker.scan_models import IndexConstituent
        store.upsert_index_constituents([
            IndexConstituent(symbol="SBIN", index_name="NIFTY 50",
                             company_name="SBI", industry="Banks"),
            IndexConstituent(symbol="SBIN", index_name="NIFTY BANK",
                             company_name="SBI", industry="Banks"),
            IndexConstituent(symbol="INFY", index_name="NIFTY 50",
                             company_name="Infosys", industry="IT"),
        ])
        result = store.get_index_constituents(index_name="NIFTY 50")
        assert len(result) == 2
        assert all(c.index_name == "NIFTY 50" for c in result)

    def test_get_all_scanner_symbols(self, store: FlowStore):
        store.upsert_index_constituents(make_index_constituents())
        symbols = store.get_all_scanner_symbols()
        assert "SBIN" in symbols
        assert "INFY" in symbols
        assert "RELIANCE" in symbols
        # Should be sorted and distinct
        assert symbols == sorted(set(symbols))

    def test_get_all_scanner_symbols_empty(self, store: FlowStore):
        assert store.get_all_scanner_symbols() == []
