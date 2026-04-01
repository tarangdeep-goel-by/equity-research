"""E2E tests: full alert pipeline — create, check, trigger, history.

Uses populated_store which has valuation snapshots, shareholding, pledges,
and FMP data for SBIN and INFY.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.alert_engine import check_all_alerts
from flowtracker.alert_models import Alert
from flowtracker.store import FlowStore


class TestAlertPipeline:
    def test_check_triggers_expected_alerts(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """Alerts with conditions met by populated data should trigger."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # The populated_store has SBIN price ~820, PE ~9.5 (from valuation snapshots).
        # It already has alerts from factories (price_below 700, pe_above 15, pledge_above 10, INFY rsi_below 30).
        # The SBIN price is ~875 (last snapshot), so price_below 700 should NOT trigger.
        # The PE is ~10.4 (last snapshot), so pe_above 15 should NOT trigger.
        # The pledge is 1.0% for last quarter, so pledge_above 10 should NOT trigger.
        # The RSI for INFY is 55.0 (from FMP technicals), so rsi_below 30 should NOT trigger.

        # Now add an alert that WILL trigger:
        # SBIN price_above 750 — price is ~875 so this triggers.
        trigger_alert = Alert(symbol="SBIN", condition_type="price_above", threshold=750.0)
        populated_store.upsert_alert(trigger_alert)

        triggered = check_all_alerts(populated_store)
        triggered_conditions = [(t.alert.symbol, t.alert.condition_type) for t in triggered]
        assert ("SBIN", "price_above") in triggered_conditions

    def test_alert_history_created(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """Triggered alerts should create history entries."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        alert = Alert(symbol="SBIN", condition_type="price_above", threshold=750.0)
        populated_store.upsert_alert(alert)

        check_all_alerts(populated_store)

        history = populated_store.get_alert_history(limit=10)
        assert len(history) >= 1
        assert any(h["symbol"] == "SBIN" for h in history)

    def test_deactivated_alerts_skipped(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """Deactivated alerts should not be evaluated."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        alert_id = populated_store.upsert_alert(
            Alert(symbol="SBIN", condition_type="price_above", threshold=750.0)
        )
        populated_store.deactivate_alert(alert_id)

        triggered = check_all_alerts(populated_store)
        triggered_ids = [t.alert.id for t in triggered]
        assert alert_id not in triggered_ids

    def test_dcf_upside_alert(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """DCF upside alert should compute margin from fmp_dcf table."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # Populated store has SBIN DCF=950, stock_price=820 → upside ~15.9%
        alert = Alert(symbol="SBIN", condition_type="dcf_upside_above", threshold=10.0)
        populated_store.upsert_alert(alert)

        triggered = check_all_alerts(populated_store)
        dcf_triggers = [t for t in triggered if t.alert.condition_type == "dcf_upside_above"]
        assert len(dcf_triggers) >= 1
        assert dcf_triggers[0].current_value > 10.0

    def test_multiple_condition_types(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """Multiple alert types for the same symbol can trigger independently."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        # Add two alerts that should both trigger
        populated_store.upsert_alert(Alert(symbol="SBIN", condition_type="price_above", threshold=750.0))
        populated_store.upsert_alert(Alert(symbol="SBIN", condition_type="dcf_upside_above", threshold=10.0))

        triggered = check_all_alerts(populated_store)
        sbin_triggers = [t for t in triggered if t.alert.symbol == "SBIN"]
        condition_types = {t.alert.condition_type for t in sbin_triggers}
        assert "price_above" in condition_types
        assert "dcf_upside_above" in condition_types
