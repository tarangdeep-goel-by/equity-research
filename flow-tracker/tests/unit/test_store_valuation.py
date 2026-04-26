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


# ---------------------------------------------------------------------------
# valuation_band — Phase 3.1: prefer screener_charts for pe_trailing
# ---------------------------------------------------------------------------


def _seed_screener_charts_pe(store: FlowStore, symbol: str, n_days: int,
                             start_pe: float = 10.0, step: float = 0.05) -> None:
    """Seed screener_charts with chart_type='pe' rows going back n_days from today."""
    today = date.today()
    for i in range(n_days):
        d = (today - timedelta(days=n_days - 1 - i)).isoformat()
        pe = start_pe + i * step
        store._conn.execute(
            "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
            "VALUES (?, 'pe', 'Price to Earning', ?, ?) "
            "ON CONFLICT(symbol, chart_type, metric, date) DO UPDATE SET value=excluded.value",
            (symbol.upper(), d, pe),
        )
    store._conn.commit()


class TestValuationBandPEFromCharts:
    def test_get_valuation_band_uses_screener_charts_when_available(self, store: FlowStore):
        """Phase 3.1: pe_trailing band should read 200 rows from screener_charts
        instead of the ~15 rows in valuation_snapshot."""
        _seed_screener_charts_pe(store, "HDFCBANK", n_days=200, start_pe=12.0, step=0.02)

        # Also seed a few valuation_snapshot rows to confirm they are NOT used when
        # charts are available.
        today = date.today()
        for i in range(5):
            d = (today - timedelta(days=i)).isoformat()
            store.upsert_valuation_snapshot(
                make_valuation_snapshot(symbol="HDFCBANK", dt=d, pe=99.0))

        band = store.get_valuation_band("HDFCBANK", "pe_trailing", days=365)
        assert band is not None
        assert band.num_observations == 200
        # min from charts = 12.0; max = 12.0 + 199*0.02 = 15.98
        assert band.min_val == pytest.approx(12.0)
        assert band.max_val == pytest.approx(15.98, abs=0.01)
        # period spans ~200 days back to today
        assert band.period_start < band.period_end
        # Current value should be the most recent data point; valuation_snapshot.date
        # equals today (same as latest chart date), and 99.0 > chart_latest, so the
        # snapshot takes precedence when dates are tied on the snapshot side (> check).
        # Latest chart is today with pe ≈ 15.98; snapshot also today (tie, chart wins).
        assert band.current_val == pytest.approx(15.98, abs=0.01)

    def test_get_valuation_band_falls_back_to_valuation_snapshot_when_no_charts(
        self, store: FlowStore
    ):
        """If screener_charts has no 'pe' data, behavior should be unchanged
        (read from valuation_snapshot)."""
        today = date.today()
        for i in range(10):
            d = (today - timedelta(days=9 - i)).isoformat()
            store.upsert_valuation_snapshot(
                make_valuation_snapshot(symbol="SBIN", dt=d, pe=8.0 + i))

        band = store.get_valuation_band("SBIN", "pe_trailing", days=30)
        assert band is not None
        assert band.num_observations == 10
        assert band.min_val == pytest.approx(8.0)
        assert band.max_val == pytest.approx(17.0)

    def test_get_valuation_band_non_pe_metric_unchanged(self, store: FlowStore):
        """Non-PE metrics (e.g., pb_ratio) should always read from valuation_snapshot,
        even if screener_charts has 'pe' data for the same symbol."""
        _seed_screener_charts_pe(store, "INFY", n_days=300, start_pe=20.0, step=0.1)
        today = date.today()
        for i in range(7):
            d = (today - timedelta(days=6 - i)).isoformat()
            store.upsert_valuation_snapshot(
                make_valuation_snapshot(symbol="INFY", dt=d, pe=25.0))

        band = store.get_valuation_band("INFY", "pb_ratio", days=30)
        assert band is not None
        # factories default pb_ratio = 1.8, so all 7 snapshot rows have pb_ratio=1.8
        assert band.num_observations == 7
        assert band.min_val == pytest.approx(1.8)
        assert band.max_val == pytest.approx(1.8)

    def test_get_valuation_band_pe_snapshot_newer_than_charts(self, store: FlowStore):
        """When valuation_snapshot has a more recent date than any screener_charts row,
        the snapshot PE is spliced in as an extra observation so min/max/median
        reflect current_val's position in the full set."""
        # Seed charts ending 10 days ago with pe ranging 14.0 → 15.96
        today = date.today()
        for i in range(50):
            d = (today - timedelta(days=10 + (49 - i))).isoformat()
            pe = 14.0 + i * 0.04
            store._conn.execute(
                "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
                "VALUES (?, 'pe', 'Price to Earning', ?, ?)",
                ("TCS", d, pe),
            )
        store._conn.commit()

        # Snapshot from today with pe=42 — far above the chart range
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="TCS", dt=today.isoformat(), pe=42.0))

        band = store.get_valuation_band("TCS", "pe_trailing", days=365)
        assert band is not None
        assert band.num_observations == 51  # 50 charts + spliced snapshot
        assert band.current_val == pytest.approx(42.0)  # from snapshot (newer)
        assert band.max_val == pytest.approx(42.0)  # snapshot is the new max
        assert band.min_val == pytest.approx(14.0)  # chart series min preserved
        # percentile uses strict-less-than; current_val itself is in the set so
        # the reflexive max percentile is (n-1)/n = 50/51 ≈ 98.04%, not 100.
        assert band.percentile == pytest.approx(50 / 51 * 100, abs=0.01)
        assert band.period_end == today.isoformat()

    def test_get_valuation_band_pe_snapshot_above_chart_max(self, store: FlowStore):
        """Regression guard for the Gemini-flagged bug: snapshot PE strictly greater
        than chart_max must appear in max_val, not just current_val (otherwise the
        band has current_val > max_val, which is nonsensical)."""
        today = date.today()
        # Charts top out at 30.0 and end 5 days ago
        for i in range(20):
            d = (today - timedelta(days=5 + (19 - i))).isoformat()
            pe = 10.0 + i * 1.0  # 10, 11, ..., 29
            store._conn.execute(
                "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
                "VALUES (?, 'pe', 'Price to Earning', ?, ?)",
                ("WIPRO", d, pe),
            )
        store._conn.commit()

        # Snapshot today with pe well above chart max
        store.upsert_valuation_snapshot(
            make_valuation_snapshot(symbol="WIPRO", dt=today.isoformat(), pe=45.0))

        band = store.get_valuation_band("WIPRO", "pe_trailing", days=365)
        assert band is not None
        assert band.current_val == pytest.approx(45.0)
        assert band.max_val == pytest.approx(45.0)  # bug fix: snapshot now in the set
        assert band.current_val <= band.max_val  # invariant


# ---------------------------------------------------------------------------
# valuation_band — PB band reads from screener_charts (chart_type='pbv')
# ---------------------------------------------------------------------------


def _seed_screener_charts_pbv(store: FlowStore, symbol: str, n_days: int,
                              start_pb: float = 1.5, step: float = 0.005) -> None:
    """Seed screener_charts with chart_type='pbv' rows going back n_days from today."""
    today = date.today()
    for i in range(n_days):
        d = (today - timedelta(days=n_days - 1 - i)).isoformat()
        pb = start_pb + i * step
        store._conn.execute(
            "INSERT INTO screener_charts (symbol, chart_type, metric, date, value) "
            "VALUES (?, 'pbv', 'Price to book value', ?, ?) "
            "ON CONFLICT(symbol, chart_type, metric, date) DO UPDATE SET value=excluded.value",
            (symbol.upper(), d, pb),
        )
    store._conn.commit()


class TestValuationBandPBFromCharts:
    """PB band must prefer screener_charts (deep history) like PE does — banks
    don't trade on PE, so PB band is the primary BFSI valuation signal."""

    def test_pb_band_uses_screener_charts_when_available(self, store: FlowStore):
        """pb_ratio band reads many years of pbv charts vs the ~28 days in
        valuation_snapshot since the daily cron started."""
        _seed_screener_charts_pbv(store, "HDFCBANK", n_days=300, start_pb=1.5, step=0.005)

        band = store.get_valuation_band("HDFCBANK", "pb_ratio", days=365)
        assert band is not None
        assert band.num_observations == 300
        assert band.metric == "pb_ratio"
        assert band.min_val == pytest.approx(1.5)
        # max = 1.5 + 299 * 0.005 = 2.995
        assert band.max_val == pytest.approx(2.995, abs=0.01)
        assert band.period_start < band.period_end

    def test_pb_alias_resolves_to_pb_ratio(self, store: FlowStore):
        """The fallback prompt at prompts.py:736 uses metric='pb'. Accept it as
        an alias for pb_ratio so agents don't get empty results."""
        _seed_screener_charts_pbv(store, "ICICIBANK", n_days=100, start_pb=2.0, step=0.01)

        band = store.get_valuation_band("ICICIBANK", "pb", days=365)
        assert band is not None
        assert band.metric in ("pb", "pb_ratio")
        assert band.num_observations == 100
        assert band.min_val == pytest.approx(2.0)

    def test_pb_band_falls_back_to_valuation_snapshot_when_no_charts(
        self, store: FlowStore
    ):
        """If screener_charts has no 'pbv' rows, behavior is unchanged
        (read from valuation_snapshot.pb_ratio)."""
        today = date.today()
        for i in range(8):
            d = (today - timedelta(days=7 - i)).isoformat()
            store.upsert_valuation_snapshot(
                make_valuation_snapshot(symbol="SBIN", dt=d, pe=8.0))
        band = store.get_valuation_band("SBIN", "pb_ratio", days=30)
        assert band is not None
        # factories default pb_ratio = 1.8
        assert band.num_observations == 8
        assert band.min_val == pytest.approx(1.8)

    def test_pb_band_pe_charts_unrelated(self, store: FlowStore):
        """Seeding pe charts must not affect pb_ratio band — different chart_type."""
        _seed_screener_charts_pe(store, "INFY", n_days=300, start_pe=20.0, step=0.1)
        today = date.today()
        for i in range(7):
            d = (today - timedelta(days=6 - i)).isoformat()
            store.upsert_valuation_snapshot(
                make_valuation_snapshot(symbol="INFY", dt=d, pe=25.0))

        band = store.get_valuation_band("INFY", "pb_ratio", days=30)
        assert band is not None
        # Falls through to valuation_snapshot — factories pb_ratio = 1.8
        assert band.num_observations == 7
        assert band.min_val == pytest.approx(1.8)
