"""Tests for the alert evaluation engine (alert_engine.py).

Tests condition checking, metric resolution, and full alert evaluation
across all 10 condition types.
"""

from __future__ import annotations

import pytest

from flowtracker.alert_engine import _condition_met, _format_message, _get_metric_value, check_all_alerts
from flowtracker.alert_models import Alert, TriggeredAlert
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# _condition_met — pure logic tests
# ---------------------------------------------------------------------------

class TestConditionMet:
    def test_price_below_triggered(self):
        assert _condition_met(680.0, "price_below", 700.0) is True

    def test_price_below_not_triggered(self):
        assert _condition_met(820.0, "price_below", 700.0) is False

    def test_price_above_triggered(self):
        assert _condition_met(900.0, "price_above", 850.0) is True

    def test_price_above_not_triggered(self):
        assert _condition_met(800.0, "price_above", 850.0) is False

    def test_pe_above_triggered(self):
        assert _condition_met(16.0, "pe_above", 15.0) is True

    def test_pe_above_not_triggered(self):
        assert _condition_met(9.5, "pe_above", 15.0) is False

    def test_pe_below_triggered(self):
        assert _condition_met(7.0, "pe_below", 8.0) is True

    def test_rsi_below_not_triggered(self):
        assert _condition_met(55.0, "rsi_below", 30.0) is False

    def test_rsi_below_triggered(self):
        assert _condition_met(25.0, "rsi_below", 30.0) is True

    def test_rsi_above_triggered(self):
        assert _condition_met(75.0, "rsi_above", 70.0) is True

    def test_pledge_above_triggered(self):
        assert _condition_met(12.0, "pledge_above", 10.0) is True

    def test_pledge_above_not_triggered(self):
        assert _condition_met(2.5, "pledge_above", 10.0) is False

    def test_dcf_upside_above_triggered(self):
        # upside_pct > threshold
        assert _condition_met(20.0, "dcf_upside_above", 15.0) is True

    def test_fii_pct_below_triggered(self):
        assert _condition_met(8.0, "fii_pct_below", 10.0) is True

    def test_mf_pct_above_triggered(self):
        assert _condition_met(12.0, "mf_pct_above", 10.0) is True

    def test_unknown_condition_type(self):
        assert _condition_met(100.0, "unknown_type", 50.0) is False


# ---------------------------------------------------------------------------
# _get_metric_value — reads from store
# ---------------------------------------------------------------------------

class TestGetMetricValue:
    def test_price_from_valuation_snapshot(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "SBIN", "price_below")
        assert val is not None
        assert isinstance(val, (int, float))
        # Fixture SBIN prices range around 800
        assert 700 < val < 900

    def test_pe_from_valuation_snapshot(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "SBIN", "pe_above")
        assert val is not None
        # Fixture SBIN PE ranges ~9
        assert 5 < val < 15

    def test_rsi_from_technicals(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "SBIN", "rsi_below")
        assert val is not None
        assert val == 55.0  # From fixture make_fmp_technicals

    def test_pledge_from_promoter_pledge(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "SBIN", "pledge_above")
        assert val is not None
        # Fixture pledges: 2.5, 2.0, 1.5, 1.0 — latest is 1.0
        assert val <= 2.5

    def test_dcf_upside_computed(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "SBIN", "dcf_upside_above")
        assert val is not None
        # DCF=950, price=820 → upside = (950-820)/820 * 100 ≈ 15.85%
        assert 15 < val < 16

    def test_fii_pct(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "SBIN", "fii_pct_below")
        assert val is not None
        # Fixture FII ~11.2% with some drift
        assert 8 < val < 15

    def test_nonexistent_symbol_returns_none(self, populated_store: FlowStore):
        val = _get_metric_value(populated_store, "NONEXIST", "price_below")
        assert val is None


# ---------------------------------------------------------------------------
# _format_message
# ---------------------------------------------------------------------------

class TestFormatMessage:
    def test_format_contains_symbol_and_type(self):
        alert = Alert(id=1, symbol="SBIN", condition_type="price_below", threshold=700.0)
        msg = _format_message(alert, 680.0)
        assert "SBIN" in msg
        assert "price_below" in msg
        assert "680.00" in msg
        assert "700.00" in msg


# ---------------------------------------------------------------------------
# check_all_alerts — integration
# ---------------------------------------------------------------------------

class TestCheckAllAlerts:
    def test_returns_list_of_triggered_alerts(self, populated_store: FlowStore):
        triggered = check_all_alerts(populated_store)
        assert isinstance(triggered, list)
        for t in triggered:
            assert isinstance(t, TriggeredAlert)

    def test_price_below_700_not_triggered(self, populated_store: FlowStore):
        """SBIN price ~820, alert threshold 700 → should NOT trigger."""
        triggered = check_all_alerts(populated_store)
        price_below = [t for t in triggered if t.alert.condition_type == "price_below" and t.alert.symbol == "SBIN"]
        assert len(price_below) == 0

    def test_pe_above_15_not_triggered(self, populated_store: FlowStore):
        """SBIN PE ~9.5, alert threshold 15 → should NOT trigger."""
        triggered = check_all_alerts(populated_store)
        pe_above = [t for t in triggered if t.alert.condition_type == "pe_above" and t.alert.symbol == "SBIN"]
        assert len(pe_above) == 0

    def test_pledge_above_10_not_triggered(self, populated_store: FlowStore):
        """SBIN pledge ~2.5%, threshold 10% → should NOT trigger."""
        triggered = check_all_alerts(populated_store)
        pledge = [t for t in triggered if t.alert.condition_type == "pledge_above" and t.alert.symbol == "SBIN"]
        assert len(pledge) == 0

    def test_deactivated_alerts_skipped(self, populated_store: FlowStore):
        """Deactivate all alerts, then check — should trigger nothing."""
        alerts = populated_store.get_active_alerts()
        for a in alerts:
            populated_store.deactivate_alert(a.id)
        triggered = check_all_alerts(populated_store)
        assert len(triggered) == 0

    def test_tight_threshold_triggers(self, populated_store: FlowStore):
        """Add an alert with a very tight threshold that should definitely trigger."""
        # SBIN PE is ~9.x, so pe_above 5 should trigger
        alert = Alert(symbol="SBIN", condition_type="pe_above", threshold=5.0, notes="test")
        populated_store.upsert_alert(alert)
        triggered = check_all_alerts(populated_store)
        pe_triggered = [t for t in triggered if t.alert.condition_type == "pe_above" and t.alert.threshold == 5.0]
        assert len(pe_triggered) == 1
        assert pe_triggered[0].current_value > 5.0

    def test_alert_for_nonexistent_symbol(self, populated_store: FlowStore):
        """Alert for symbol with no data → should NOT trigger (value is None)."""
        alert = Alert(symbol="ZZZZZ", condition_type="price_below", threshold=9999.0, notes="test")
        populated_store.upsert_alert(alert)
        triggered = check_all_alerts(populated_store)
        zz = [t for t in triggered if t.alert.symbol == "ZZZZZ"]
        assert len(zz) == 0
