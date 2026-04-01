"""Tests for FlowStore valuation-related methods.

Tables: valuation_snapshot
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from flowtracker.store import FlowStore
from tests.fixtures.factories import (
    make_valuation_snapshot,
    make_valuation_snapshots,
)


# ---------------------------------------------------------------------------
# valuation_snapshot — single upsert
# ---------------------------------------------------------------------------


class TestValuationSnapshotSingle:
    def test_upsert_and_get_history_round_trip(self, store: FlowStore):
        today = date.today()
        snap = make_valuation_snapshot(symbol="SBIN", dt=today.isoformat(),
                                       price=820.0, pe=9.5)
        count = store.upsert_valuation_snapshot(snap)
        assert count == 1
        history = store.get_valuation_history("SBIN", days=7)
        assert len(history) == 1
        assert history[0].symbol == "SBIN"
        assert history[0].price == pytest.approx(820.0)
        assert history[0].pe_trailing == pytest.approx(9.5)

    def test_all_fields_round_trip(self, store: FlowStore):
        today = date.today()
        snap = make_valuation_snapshot(symbol="SBIN", dt=today.isoformat())
        store.upsert_valuation_snapshot(snap)
        got = store.get_valuation_history("SBIN", days=7)
        r = got[0]
        assert r.market_cap is not None
        assert r.enterprise_value is not None
        assert r.fifty_two_week_high is not None
        assert r.fifty_two_week_low is not None
        assert r.beta is not None
        assert r.pb_ratio is not None
        assert r.ev_ebitda is not None
        assert r.roe is not None
        assert r.dividend_yield is not None
        assert r.free_cash_flow is not None

    def test_audit_on_pe_change(self, store: FlowStore):
        dt = "2026-03-28"
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="SBIN", dt=dt, pe=9.5))
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="SBIN", dt=dt, pe=10.0))
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'valuation_snapshot'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["field"] == "pe_trailing"

    def test_no_audit_on_same_pe(self, store: FlowStore):
        dt = "2026-03-28"
        snap = make_valuation_snapshot(symbol="SBIN", dt=dt, pe=9.5)
        store.upsert_valuation_snapshot(snap)
        store.upsert_valuation_snapshot(snap)
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'valuation_snapshot'"
        ).fetchall()
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# valuation_snapshot — batch upsert
# ---------------------------------------------------------------------------


class TestValuationSnapshotBatch:
    def test_batch_upsert(self, store: FlowStore):
        today = date.today()
        snapshots = []
        for i in range(5):
            d = (today - timedelta(days=4 - i)).isoformat()
            snapshots.append(make_valuation_snapshot(symbol="SBIN", dt=d,
                                                      price=800 + i * 10))
        count = store.upsert_valuation_snapshots(snapshots)
        assert count == 5
        history = store.get_valuation_history("SBIN", days=10)
        assert len(history) == 5

    def test_history_ordered_oldest_first(self, store: FlowStore):
        today = date.today()
        snapshots = []
        for i in range(3):
            d = (today - timedelta(days=2 - i)).isoformat()
            snapshots.append(make_valuation_snapshot(symbol="SBIN", dt=d))
        store.upsert_valuation_snapshots(snapshots)
        history = store.get_valuation_history("SBIN", days=10)
        dates = [h.date for h in history]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# valuation_band
# ---------------------------------------------------------------------------


class TestValuationBand:
    def test_band_computation(self, store: FlowStore):
        today = date.today()
        snapshots = []
        for i in range(10):
            d = (today - timedelta(days=9 - i)).isoformat()
            pe = 8.0 + i  # 8, 9, 10, ..., 17
            snapshots.append(make_valuation_snapshot(symbol="SBIN", dt=d, pe=pe))
        store.upsert_valuation_snapshots(snapshots)

        band = store.get_valuation_band("SBIN", "pe_trailing", days=30)
        assert band is not None
        assert band.symbol == "SBIN"
        assert band.metric == "pe_trailing"
        assert band.min_val == pytest.approx(8.0)
        assert band.max_val == pytest.approx(17.0)
        assert band.num_observations == 10
        # Median of 8..17 = (12+13)/2 = 12.5
        assert band.median_val == pytest.approx(12.5)
        # Current (latest pe=17) should be at a high percentile
        assert band.percentile >= 80.0

    def test_band_returns_none_on_empty(self, store: FlowStore):
        assert store.get_valuation_band("SBIN", "pe_trailing") is None

    def test_band_single_data_point(self, store: FlowStore):
        today = date.today()
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="SBIN", dt=today.isoformat(), pe=10.0))
        band = store.get_valuation_band("SBIN", "pe_trailing", days=30)
        assert band is not None
        assert band.num_observations == 1
        assert band.min_val == pytest.approx(10.0)
        assert band.max_val == pytest.approx(10.0)
        assert band.median_val == pytest.approx(10.0)

    def test_band_invalid_metric_returns_none(self, store: FlowStore):
        today = date.today()
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="SBIN", dt=today.isoformat()))
        assert store.get_valuation_band("SBIN", "invalid_metric") is None

    def test_band_case_normalization(self, store: FlowStore):
        today = date.today()
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="SBIN", dt=today.isoformat(), pe=10.0))
        band = store.get_valuation_band("sbin", "pe_trailing", days=30)
        assert band is not None
        assert band.symbol == "SBIN"
