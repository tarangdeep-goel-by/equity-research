"""Tests for mf_scheme_holdings store methods."""

from __future__ import annotations

from flowtracker.store import FlowStore
from flowtracker.mfportfolio_models import MFSchemeHolding
from tests.fixtures.factories import make_mf_scheme_holdings


def test_upsert_mf_scheme_holdings(store: FlowStore):
    """Upsert holdings and confirm count."""
    holdings = make_mf_scheme_holdings()
    count = store.upsert_mf_scheme_holdings(holdings)
    assert count >= 4  # 4 records in factory


def test_get_mf_stock_holdings_by_name_like(store: FlowStore):
    """LIKE search on stock_name returns matching holdings."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    # Search by partial stock name (case insensitive LIKE)
    results = store.get_mf_stock_holdings("STATE BANK")
    assert len(results) >= 1
    for r in results:
        assert "State Bank" in r.stock_name


def test_get_mf_stock_holdings_exact_isin(store: FlowStore):
    """Exact ISIN match returns holdings for that stock."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    results = store.get_mf_stock_holdings("INE062A01020")
    assert len(results) >= 1
    for r in results:
        assert r.isin == "INE062A01020"


def test_get_mf_stock_holdings_returns_latest_month(store: FlowStore):
    """Only returns data from the most recent month."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    # The factory has data for 2026-01 and 2026-02; latest is 2026-02
    results = store.get_mf_stock_holdings("INE062A01020")
    months = {r.month for r in results}
    assert months == {"2026-02"}


def test_get_mf_stock_holdings_empty_db(store: FlowStore):
    """Returns empty list when no holdings exist."""
    assert store.get_mf_stock_holdings("ANYTHING") == []


def test_get_mf_holding_changes_buy(store: FlowStore):
    """Detects INCREASE when quantity goes up between months."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    # SBI Bluechip Fund: 4,500,000 (2026-01) -> 5,000,000 (2026-02) = INCREASE
    changes = store.get_mf_holding_changes(month="2026-02", change_type="buy")
    assert len(changes) >= 1

    increase_found = False
    for c in changes:
        if c.scheme_name == "SBI Bluechip Fund" and c.isin == "INE062A01020":
            assert c.change_type == "INCREASE"
            assert c.qty_change > 0
            increase_found = True
    assert increase_found, "Expected SBI Bluechip Fund INCREASE not found"


def test_get_mf_holding_changes_new_position(store: FlowStore):
    """Detects NEW when holding appears in current month but not previous."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    changes = store.get_mf_holding_changes(month="2026-02", change_type="buy")
    # ICICI Pru Bluechip Fund and SBI Focused Equity Fund are in 2026-02 but not 2026-01
    new_found = any(c.change_type == "NEW" for c in changes)
    assert new_found, "Expected at least one NEW position"


def test_get_mf_holding_changes_empty_db(store: FlowStore):
    """Returns empty list when no holdings exist."""
    assert store.get_mf_holding_changes() == []


def test_get_mf_portfolio_summary(store: FlowStore):
    """AMC-level aggregation returns expected structure."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    summary = store.get_mf_portfolio_summary(month="2026-02")
    assert len(summary) >= 1

    # Check structure of first entry
    first = summary[0]
    assert "amc" in first
    assert "num_schemes" in first
    assert "num_stocks" in first
    assert "total_value_cr" in first


def test_get_mf_portfolio_summary_auto_month(store: FlowStore):
    """When month is None, uses the latest available month."""
    store.upsert_mf_scheme_holdings(make_mf_scheme_holdings())

    summary = store.get_mf_portfolio_summary()
    assert len(summary) >= 1


def test_get_mf_portfolio_summary_empty_db(store: FlowStore):
    """Returns empty list when no holdings exist."""
    assert store.get_mf_portfolio_summary() == []
