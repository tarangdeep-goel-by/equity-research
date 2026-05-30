"""Tests for the US add-on (Phase 3) storage foundations.

Covers: us_* tables exist with market/currency defaults; round-trip upsert+get
incl. composite-PK conflict semantics; symbol_registry.cik migration +
seed_us_validation_universe; USD validation bounds (crore bounds NOT applied,
percentage bounds ARE applied). India behavior is exercised elsewhere and must
stay byte-identical — these tests only touch us_* tables + the registry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.store import FlowStore
from flowtracker.store_domains._shared import _validate_row


US_TABLES = [
    "us_daily_prices",
    "us_annual_financials",
    "us_quarterly_financials",
    "us_valuation_snapshot",
    "us_consensus_estimates",
    "us_insider_transactions",
    "us_institutional_holdings",
    "us_short_interest",
]


@pytest.fixture
def store(tmp_db: Path) -> FlowStore:
    s = FlowStore(db_path=tmp_db)
    yield s
    s.close()


# --- schema -----------------------------------------------------------------

def test_all_us_tables_exist(store: FlowStore) -> None:
    names = {
        r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for t in US_TABLES:
        assert t in names, f"missing table {t}"


def test_us_tables_have_market_default(store: FlowStore) -> None:
    """Every us_* table carries a market column defaulting to NASDAQ."""
    for t in US_TABLES:
        cols = {r[1]: r for r in store._conn.execute(f"PRAGMA table_info({t})")}
        assert "market" in cols, f"{t} missing market"
        # column 4 (index) is dflt_value
        assert "NASDAQ" in str(cols["market"][4]), f"{t} market default wrong"


def test_us_monetary_tables_have_currency_default(store: FlowStore) -> None:
    for t in ["us_annual_financials", "us_quarterly_financials",
              "us_valuation_snapshot", "us_consensus_estimates",
              "us_insider_transactions", "us_institutional_holdings",
              "us_short_interest"]:
        cols = {r[1]: r for r in store._conn.execute(f"PRAGMA table_info({t})")}
        assert "currency" in cols, f"{t} missing currency"
        assert "USD" in str(cols["currency"][4]), f"{t} currency default wrong"


def test_market_currency_defaults_materialize_on_insert(store: FlowStore) -> None:
    """Inserting without market/currency keys gets NASDAQ/USD defaults."""
    store.upsert_us_annual_financials([
        {"symbol": "AAPL", "fiscal_year": 2023, "revenue": 383_000},
    ])
    row = store.get_us_annual_financials("AAPL")[0]
    assert row["market"] == "NASDAQ"
    assert row["currency"] == "USD"


# --- round trips ------------------------------------------------------------

def test_daily_prices_round_trip(store: FlowStore) -> None:
    store.upsert_us_daily_prices([
        {"symbol": "AAPL", "date": "2024-01-02", "open": 187.0, "high": 188.4,
         "low": 183.9, "close": 185.6, "volume": 82_000_000, "adj_close": 185.6},
        {"symbol": "AAPL", "date": "2024-01-03", "open": 184.2, "high": 185.9,
         "low": 183.4, "close": 184.2, "volume": 58_000_000, "adj_close": 184.2},
    ])
    rows = store.get_us_daily_prices("AAPL")
    assert len(rows) == 2
    # most recent first
    assert rows[0]["date"] == "2024-01-03"
    assert rows[0]["close"] == 184.2


def test_annual_financials_conflict_updates(store: FlowStore) -> None:
    """Same (symbol, market, fiscal_year) updates in place; no dupe."""
    store.upsert_us_annual_financials([
        {"symbol": "MSFT", "fiscal_year": 2023, "revenue": 211_000,
         "net_income": 72_000},
    ])
    store.upsert_us_annual_financials([
        {"symbol": "MSFT", "fiscal_year": 2023, "revenue": 211_915,
         "net_income": 72_361},
    ])
    rows = store.get_us_annual_financials("MSFT")
    assert len(rows) == 1
    assert rows[0]["revenue"] == 211_915


def test_valuation_different_market_coexists(store: FlowStore) -> None:
    """Same symbol+date on a different market is a distinct row."""
    store.upsert_us_valuation_snapshot([
        {"symbol": "XYZ", "market": "NASDAQ", "date": "2024-06-01",
         "price": 100.0, "market_cap": 50_000},
        {"symbol": "XYZ", "market": "NYSE", "date": "2024-06-01",
         "price": 101.0, "market_cap": 50_100},
    ])
    nasdaq = store.get_us_valuation_snapshot("XYZ", market="NASDAQ")
    nyse = store.get_us_valuation_snapshot("XYZ", market="NYSE")
    assert len(nasdaq) == 1 and nasdaq[0]["price"] == 100.0
    assert len(nyse) == 1 and nyse[0]["price"] == 101.0


def test_insider_round_trip(store: FlowStore) -> None:
    store.upsert_us_insider_transactions([
        {"symbol": "NVDA", "transaction_date": "2024-03-15",
         "owner_name": "Jensen Huang", "owner_title": "CEO",
         "transaction_code": "S", "shares": 120_000, "price_per_share": 880.0,
         "value": 105.6, "is_director": 1, "is_officer": 1},
    ])
    rows = store.get_us_insider_transactions("NVDA")
    assert len(rows) == 1
    assert rows[0]["owner_name"] == "Jensen Huang"
    assert rows[0]["market"] == "NASDAQ"


def test_institutional_put_call_sentinel(store: FlowStore) -> None:
    """put_call defaults to '' so plain-long rows have a stable unique key."""
    store.upsert_us_institutional_holdings([
        {"symbol": "AAPL", "manager_cik": "1067983", "manager_name": "Berkshire",
         "quarter_end": "2024-03-31", "shares": 789_000_000, "value_usd": 135_000},
    ])
    store.upsert_us_institutional_holdings([
        {"symbol": "AAPL", "manager_cik": "1067983", "manager_name": "Berkshire",
         "quarter_end": "2024-03-31", "shares": 790_000_000, "value_usd": 135_400},
    ])
    rows = store.get_us_institutional_holdings("AAPL")
    assert len(rows) == 1
    assert rows[0]["put_call"] == ""
    assert rows[0]["shares"] == 790_000_000


# --- registry cik + seed ----------------------------------------------------

def test_symbol_registry_cik_column_exists(store: FlowStore) -> None:
    cols = {r[1] for r in store._conn.execute("PRAGMA table_info(symbol_registry)")}
    assert "cik" in cols


def test_seed_validation_universe(store: FlowStore) -> None:
    n = store.seed_us_validation_universe()
    assert n == 6
    aapl = store.get_symbol_registry_entry("AAPL", market="NASDAQ")
    assert aapl is not None
    assert aapl["cik"] == "320193"
    assert aapl["currency"] == "USD"
    assert aapl["fiscal_year_system"] == "CALENDAR"
    assert aapl["sector"] == "Technology"
    # NYSE entry too
    jpm = store.get_symbol_registry_entry("JPM", market="NYSE")
    assert jpm["cik"] == "19617"
    assert jpm["currency"] == "USD"
    # idempotent
    assert store.seed_us_validation_universe() == 6
    assert len(store.get_symbol_registry(market="NASDAQ")) == 3
    assert len(store.get_symbol_registry(market="NYSE")) == 3


# --- USD validation ---------------------------------------------------------

def test_usd_large_market_cap_not_flagged(store: FlowStore) -> None:
    """A $3T market cap (3,000,000 mn) is valid under USD bounds, not INR crore."""
    row = {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
           "date": "2024-06-01", "market_cap": 3_000_000, "net_margin": 25.0}
    warnings = _validate_row("us_valuation_snapshot", row,
                             market="NASDAQ", currency="USD")
    assert warnings == [], warnings


def test_usd_bad_net_margin_flagged(store: FlowStore) -> None:
    """A nonsense net_margin is currency-agnostic and IS flagged under USD."""
    row = {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
           "date": "2024-06-01", "market_cap": 3_000_000, "net_margin": 250.0}
    warnings = _validate_row("us_valuation_snapshot", row,
                             market="NASDAQ", currency="USD")
    assert any("net_margin" in w for w in warnings), warnings


def test_inr_crore_bounds_unchanged(store: FlowStore) -> None:
    """INR valuation_snapshot still applies crore bounds (regression guard)."""
    # A USD $3T market cap stored as raw rupees would be ~3e8 Cr — far above the
    # INR upper bound (25,000,000 Cr) → must be flagged for INR.
    row = {"market_cap": 300_000_000}
    warnings = _validate_row("valuation_snapshot", row, market="NSE", currency="INR")
    assert any("market_cap" in w for w in warnings), warnings


def test_short_interest_round_trip(store: FlowStore) -> None:
    """us_short_interest upsert+get round-trips, most-recent settlement first,
    and the (symbol, market, settlement_date) conflict key updates in place."""
    store.upsert_us_short_interest([
        {"symbol": "AAPL", "settlement_date": "2026-04-30",
         "short_interest": 134_675_274.0, "avg_daily_volume": 45_944_025.0,
         "days_to_cover": 2.93},
        {"symbol": "AAPL", "settlement_date": "2026-05-15",
         "short_interest": 138_782_718.0, "avg_daily_volume": 50_565_316.0,
         "days_to_cover": 2.74},
    ])
    rows = store.get_us_short_interest("AAPL")
    assert len(rows) == 2
    assert rows[0]["settlement_date"] == "2026-05-15"  # DESC
    assert rows[0]["market"] == "NASDAQ" and rows[0]["currency"] == "USD"

    # Same settlement_date → update in place (no duplicate row).
    store.upsert_us_short_interest([
        {"symbol": "AAPL", "settlement_date": "2026-05-15",
         "short_interest": 140_000_000.0, "avg_daily_volume": 50_000_000.0,
         "days_to_cover": 2.80},
    ])
    rows = store.get_us_short_interest("AAPL")
    assert len(rows) == 2
    assert rows[0]["short_interest"] == 140_000_000.0
