"""Tests for FMP data store methods (6 tables)."""

from __future__ import annotations

from flowtracker.store import FlowStore
from flowtracker.fmp_models import (
    FMPDcfValue, FMPTechnicalIndicator, FMPKeyMetrics,
    FMPFinancialGrowth, FMPAnalystGrade, FMPPriceTarget,
)
from tests.fixtures.factories import (
    make_fmp_dcf, make_fmp_technicals, make_fmp_key_metrics,
    make_fmp_growth, make_fmp_grades, make_fmp_targets,
)


# -- fmp_dcf --


def test_upsert_and_get_fmp_dcf_latest(store: FlowStore):
    """Upsert DCF records and get the latest one."""
    records = make_fmp_dcf("SBIN")
    count = store.upsert_fmp_dcf(records)
    assert count >= 2

    latest = store.get_fmp_dcf_latest("SBIN")
    assert latest is not None
    assert latest.symbol == "SBIN"
    assert latest.date == "2026-03-28"  # Most recent
    assert latest.dcf == 950.0
    assert latest.stock_price == 820.0


def test_get_fmp_dcf_latest_empty_db(store: FlowStore):
    """Returns None when no DCF data exists."""
    assert store.get_fmp_dcf_latest("UNKNOWN") is None


def test_get_fmp_dcf_history(store: FlowStore):
    """Returns multiple records ordered by date DESC."""
    store.upsert_fmp_dcf(make_fmp_dcf("SBIN"))

    history = store.get_fmp_dcf_history("SBIN")
    assert len(history) == 2
    assert history[0].date > history[1].date  # DESC order


# -- fmp_technical_indicators --


def test_upsert_and_get_fmp_technicals(store: FlowStore):
    """Upsert technical indicators and retrieve all for a symbol."""
    records = make_fmp_technicals("SBIN")
    count = store.upsert_fmp_technical_indicators(records)
    assert count >= 5

    result = store.get_fmp_technical_indicators("SBIN")
    assert len(result) == 5
    indicators = {r.indicator for r in result}
    assert "rsi" in indicators
    assert "sma_50" in indicators
    assert "sma_200" in indicators


def test_get_fmp_technicals_empty_db(store: FlowStore):
    """Returns empty list when no technical data exists."""
    assert store.get_fmp_technical_indicators("UNKNOWN") == []


# -- fmp_key_metrics --


def test_upsert_and_get_fmp_key_metrics(store: FlowStore):
    """Upsert key metrics and retrieve them."""
    records = make_fmp_key_metrics("SBIN")
    count = store.upsert_fmp_key_metrics(records)
    assert count >= 1

    result = store.get_fmp_key_metrics("SBIN")
    assert len(result) == 1
    assert result[0].symbol == "SBIN"
    assert result[0].pe_ratio == 9.5
    assert result[0].roe == 18.5
    assert result[0].net_profit_margin_dupont == 35.0


def test_get_fmp_key_metrics_empty_db(store: FlowStore):
    """Returns empty list when no key metrics exist."""
    assert store.get_fmp_key_metrics("UNKNOWN") == []


# -- fmp_financial_growth --


def test_upsert_and_get_fmp_growth(store: FlowStore):
    """Upsert financial growth and retrieve it."""
    records = make_fmp_growth("SBIN")
    count = store.upsert_fmp_financial_growth(records)
    assert count >= 1

    result = store.get_fmp_financial_growth("SBIN")
    assert len(result) == 1
    assert result[0].symbol == "SBIN"
    assert result[0].revenue_growth == 12.0
    assert result[0].net_income_growth == 18.0
    assert result[0].revenue_growth_10y is None  # factory sets this as None


def test_get_fmp_growth_empty_db(store: FlowStore):
    """Returns empty list when no growth data exists."""
    assert store.get_fmp_financial_growth("UNKNOWN") == []


# -- fmp_analyst_grades --


def test_upsert_and_get_fmp_grades(store: FlowStore):
    """Upsert analyst grades and retrieve them."""
    records = make_fmp_grades("SBIN")
    count = store.upsert_fmp_analyst_grades(records)
    assert count >= 2

    result = store.get_fmp_analyst_grades("SBIN")
    assert len(result) == 2
    # Ordered by date DESC
    assert result[0].date >= result[1].date
    assert result[0].grading_company == "Morgan Stanley"


def test_get_fmp_grades_empty_db(store: FlowStore):
    """Returns empty list when no grade data exists."""
    assert store.get_fmp_analyst_grades("UNKNOWN") == []


# -- fmp_price_targets --


def test_upsert_and_get_fmp_targets(store: FlowStore):
    """Upsert price targets and retrieve them."""
    records = make_fmp_targets("SBIN")
    count = store.upsert_fmp_price_targets(records)
    assert count >= 2

    result = store.get_fmp_price_targets("SBIN")
    assert len(result) == 2
    # Ordered by published_date DESC
    assert result[0].published_date >= result[1].published_date
    assert result[0].analyst_company == "Morgan Stanley"
    assert result[0].price_target == 1000.0


def test_get_fmp_targets_empty_db(store: FlowStore):
    """Returns empty list when no price targets exist."""
    assert store.get_fmp_price_targets("UNKNOWN") == []


# -- cross-table: two symbols --


def test_fmp_data_isolated_by_symbol(store: FlowStore):
    """FMP data for different symbols doesn't interfere."""
    store.upsert_fmp_dcf(make_fmp_dcf("SBIN"))
    store.upsert_fmp_dcf(make_fmp_dcf("INFY"))

    sbin_dcf = store.get_fmp_dcf_history("SBIN")
    infy_dcf = store.get_fmp_dcf_history("INFY")
    assert all(d.symbol == "SBIN" for d in sbin_dcf)
    assert all(d.symbol == "INFY" for d in infy_dcf)
