"""Tests for portfolio_holdings, alerts, and alert_history store methods."""

from __future__ import annotations

from flowtracker.store import FlowStore
from flowtracker.portfolio_models import PortfolioHolding
from flowtracker.alert_models import Alert
from tests.fixtures.factories import make_portfolio_holdings, make_alerts


# -- portfolio_holdings --


def test_upsert_and_get_portfolio_holdings(store: FlowStore):
    """Upsert holdings and retrieve them."""
    holdings = make_portfolio_holdings()
    for h in holdings:
        count = store.upsert_portfolio_holding(h)
        assert count >= 1

    result = store.get_portfolio_holdings()
    assert len(result) == 2
    symbols = {r.symbol for r in result}
    assert symbols == {"SBIN", "INFY"}


def test_get_portfolio_holdings_ordered_by_symbol(store: FlowStore):
    """Holdings are returned ordered by symbol alphabetically."""
    for h in make_portfolio_holdings():
        store.upsert_portfolio_holding(h)

    result = store.get_portfolio_holdings()
    assert result[0].symbol == "INFY"
    assert result[1].symbol == "SBIN"


def test_get_portfolio_holdings_empty_db(store: FlowStore):
    """Returns empty list when no holdings exist."""
    assert store.get_portfolio_holdings() == []


def test_remove_portfolio_holding_success(store: FlowStore):
    """Removing an existing holding returns True."""
    for h in make_portfolio_holdings():
        store.upsert_portfolio_holding(h)

    removed = store.remove_portfolio_holding("SBIN")
    assert removed is True

    # Verify it's gone
    result = store.get_portfolio_holdings()
    assert len(result) == 1
    assert result[0].symbol == "INFY"


def test_remove_portfolio_holding_unknown(store: FlowStore):
    """Removing a non-existent holding returns False."""
    removed = store.remove_portfolio_holding("UNKNOWN")
    assert removed is False


def test_upsert_portfolio_holding_updates_existing(store: FlowStore):
    """Upserting same symbol updates the record (UNIQUE on symbol)."""
    h = PortfolioHolding(symbol="SBIN", quantity=100, avg_cost=750.0)
    store.upsert_portfolio_holding(h)

    h_updated = PortfolioHolding(symbol="SBIN", quantity=200, avg_cost=800.0)
    store.upsert_portfolio_holding(h_updated)

    result = store.get_portfolio_holdings()
    assert len(result) == 1
    assert result[0].quantity == 200
    assert result[0].avg_cost == 800.0


# -- alerts --


def test_upsert_alert_returns_id(store: FlowStore):
    """upsert_alert returns the auto-generated alert ID."""
    alert = Alert(symbol="SBIN", condition_type="price_below", threshold=700.0)
    alert_id = store.upsert_alert(alert)
    assert isinstance(alert_id, int)
    assert alert_id > 0


def test_get_active_alerts(store: FlowStore):
    """get_active_alerts returns all active alerts."""
    alerts = make_alerts()
    for a in alerts:
        store.upsert_alert(a)

    result = store.get_active_alerts()
    assert len(result) == 4
    assert all(a.active for a in result)


def test_get_active_alerts_empty_db(store: FlowStore):
    """Returns empty list when no alerts exist."""
    assert store.get_active_alerts() == []


def test_deactivate_alert_success(store: FlowStore):
    """Deactivating an existing alert returns True and sets active=0."""
    alert_id = store.upsert_alert(
        Alert(symbol="SBIN", condition_type="price_below", threshold=700.0)
    )

    result = store.deactivate_alert(alert_id)
    assert result is True

    # Verify it's no longer in active alerts
    active = store.get_active_alerts()
    assert len(active) == 0


def test_deactivate_alert_invalid_id(store: FlowStore):
    """Deactivating a non-existent alert ID returns False."""
    result = store.deactivate_alert(99999)
    assert result is False


# -- alert_history --


def test_log_and_get_alert_history(store: FlowStore):
    """Log a trigger and retrieve from history."""
    alert_id = store.upsert_alert(
        Alert(symbol="SBIN", condition_type="price_below", threshold=700.0)
    )

    store.log_alert_trigger(alert_id, value=680.0, message="SBIN dropped below 700")

    history = store.get_alert_history()
    assert len(history) >= 1
    entry = history[0]
    assert entry["alert_id"] == alert_id
    assert entry["current_value"] == 680.0
    assert entry["message"] == "SBIN dropped below 700"
    assert entry["symbol"] == "SBIN"
    assert entry["condition_type"] == "price_below"


def test_log_alert_trigger_updates_last_triggered(store: FlowStore):
    """Logging a trigger updates last_triggered on the alert row."""
    alert_id = store.upsert_alert(
        Alert(symbol="SBIN", condition_type="price_below", threshold=700.0)
    )

    # Before trigger: last_triggered should be None
    active = store.get_active_alerts()
    assert active[0].last_triggered is None

    store.log_alert_trigger(alert_id, value=680.0, message="triggered")

    # After trigger: last_triggered should be set
    active = store.get_active_alerts()
    assert active[0].last_triggered is not None


def test_get_alert_history_empty_db(store: FlowStore):
    """Returns empty list when no history exists."""
    assert store.get_alert_history() == []
