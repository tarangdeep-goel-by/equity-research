"""Tests for FlowStore flow-related methods.

Tables: daily_flows, mf_monthly_flows, mf_aum_summary, mf_daily_flows, audit_log
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from flowtracker.store import FlowStore
from tests.fixtures.factories import (
    make_daily_flow,
    make_daily_flows,
    make_mf_monthly_flows,
    make_mf_aum_summary,
    make_mf_daily_flows,
)


# ---------------------------------------------------------------------------
# daily_flows — upsert + get round-trips
# ---------------------------------------------------------------------------


class TestUpsertFlows:
    def test_upsert_two_flows_returns_count_2(self, store: FlowStore):
        flows = [
            make_daily_flow(dt="2026-03-28", category="FII"),
            make_daily_flow(dt="2026-03-28", category="DII", buy=8000, sell=7000),
        ]
        count = store.upsert_flows(flows)
        assert count == 2

    def test_upsert_flows_retrievable_via_get_flows(self, store: FlowStore):
        today = date.today()
        dt = today.isoformat()
        flows = [
            make_daily_flow(dt=dt, category="FII"),
            make_daily_flow(dt=dt, category="DII", buy=8000, sell=7000),
        ]
        store.upsert_flows(flows)
        result = store.get_flows(days=7)
        assert len(result) == 2
        symbols = {f.category for f in result}
        assert symbols == {"FII", "DII"}

    def test_upsert_changed_net_creates_audit_entry(self, store: FlowStore):
        dt = "2026-03-28"
        store.upsert_flows([make_daily_flow(dt=dt, category="FII", net=-1500)])
        # Now update with different net_value
        store.upsert_flows([make_daily_flow(dt=dt, category="FII", net=-2000)])
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'daily_flows'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["old_value"] == "-1500.0"
        assert rows[0]["new_value"] == "-2000.0"

    def test_upsert_idempotent_no_audit(self, store: FlowStore):
        dt = "2026-03-28"
        flow = make_daily_flow(dt=dt, category="FII", net=-1500)
        store.upsert_flows([flow])
        store.upsert_flows([flow])  # same data again
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'daily_flows'"
        ).fetchall()
        assert len(rows) == 0


class TestGetLatest:
    def test_returns_pair_after_insert(self, store: FlowStore):
        dt = "2026-03-28"
        store.upsert_flows([
            make_daily_flow(dt=dt, category="FII"),
            make_daily_flow(dt=dt, category="DII", buy=8000, sell=7000),
        ])
        pair = store.get_latest()
        assert pair is not None
        assert pair.fii.category == "FII"
        assert pair.dii.category == "DII"
        assert pair.date == date.fromisoformat(dt)

    def test_returns_none_on_empty_db(self, store: FlowStore):
        assert store.get_latest() is None


class TestGetFlows:
    def test_date_range_filtering(self, store: FlowStore):
        today = date.today()
        # Insert flows for today and 10 days ago
        store.upsert_flows([
            make_daily_flow(dt=today.isoformat(), category="FII"),
            make_daily_flow(dt=(today - timedelta(days=10)).isoformat(), category="FII"),
        ])
        result = store.get_flows(days=5)
        assert len(result) == 1
        assert result[0].date == today

    def test_empty_db_returns_empty(self, store: FlowStore):
        assert store.get_flows(days=30) == []


class TestGetStreak:
    def test_buying_streak(self, store: FlowStore):
        today = date.today()
        # 3 consecutive positive FII days
        flows = []
        for i in range(3):
            d = (today - timedelta(days=2 - i)).isoformat()
            flows.append(make_daily_flow(dt=d, category="FII", buy=12000, sell=10000, net=2000))
        store.upsert_flows(flows)
        streak = store.get_streak("FII")
        assert streak is not None
        assert streak.direction == "buying"
        assert streak.days == 3
        assert streak.cumulative_net == pytest.approx(6000.0)

    def test_selling_streak(self, store: FlowStore):
        today = date.today()
        flows = []
        for i in range(2):
            d = (today - timedelta(days=1 - i)).isoformat()
            flows.append(make_daily_flow(dt=d, category="FII", buy=10000, sell=12000, net=-2000))
        store.upsert_flows(flows)
        streak = store.get_streak("FII")
        assert streak is not None
        assert streak.direction == "selling"
        assert streak.days == 2

    def test_returns_none_on_empty_db(self, store: FlowStore):
        assert store.get_streak("FII") is None


# ---------------------------------------------------------------------------
# mf_monthly_flows — upsert + get round-trips
# ---------------------------------------------------------------------------


class TestMFMonthlyFlows:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        flows = make_mf_monthly_flows(n=2)  # 2 months x 2 sub-categories = 4
        count = store.upsert_mf_flows(flows)
        assert count == 4
        # get_mf_flows uses date-relative query, insert recent months
        result = store.get_mf_flows(months=12)
        assert len(result) >= 4

    def test_category_filter(self, store: FlowStore):
        store.upsert_mf_flows(make_mf_monthly_flows(n=2))
        result = store.get_mf_flows(months=12, category="Equity")
        assert all(f.category == "Equity" for f in result)


# ---------------------------------------------------------------------------
# mf_aum_summary — upsert + get round-trips
# ---------------------------------------------------------------------------


class TestMFAUM:
    def test_upsert_single_and_get_latest(self, store: FlowStore):
        summaries = make_mf_aum_summary(n=1)
        store.upsert_mf_aum(summaries[0])
        latest = store.get_mf_latest_aum()
        assert latest is not None
        assert latest.month == summaries[0].month
        assert latest.total_aum == summaries[0].total_aum

    def test_get_mf_aum_trend(self, store: FlowStore):
        for s in make_mf_aum_summary(n=3):
            store.upsert_mf_aum(s)
        trend = store.get_mf_aum_trend(months=12)
        assert len(trend) == 3
        # Most recent first
        assert trend[0].month >= trend[-1].month

    def test_get_latest_on_empty_db(self, store: FlowStore):
        assert store.get_mf_latest_aum() is None


# ---------------------------------------------------------------------------
# mf_daily_flows — upsert + get round-trips
# ---------------------------------------------------------------------------


class TestMFDailyFlows:
    def test_upsert_and_get_latest(self, store: FlowStore):
        flows = make_mf_daily_flows(n=3)  # 3 days x 2 categories = 6
        count = store.upsert_mf_daily_flows(flows)
        assert count == 6
        latest = store.get_mf_daily_latest()
        # Latest day should have 2 records (Equity + Debt)
        assert len(latest) == 2

    def test_get_daily_summary(self, store: FlowStore):
        # Use today-relative dates so they fall within the 30-day window
        from flowtracker.mf_models import MFDailyFlow
        today = date.today()
        flows = [
            MFDailyFlow(date=today.isoformat(), category="Equity",
                        gross_purchase=5000, gross_sale=4200, net_investment=800),
            MFDailyFlow(date=today.isoformat(), category="Debt",
                        gross_purchase=3000, gross_sale=3500, net_investment=-500),
        ]
        store.upsert_mf_daily_flows(flows)
        summary = store.get_mf_daily_summary(days=30)
        assert len(summary) >= 1
        row = summary[0]
        assert row["equity_net"] == pytest.approx(800.0)
        assert row["debt_net"] == pytest.approx(-500.0)

    def test_get_latest_on_empty_db(self, store: FlowStore):
        assert store.get_mf_daily_latest() == []
