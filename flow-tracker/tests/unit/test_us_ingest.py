"""Tests for us_ingest.py — US prices / valuation / estimates ingestion (P3.2).

All yfinance / estimates access is mocked — no network. Asserts key mapping,
market='NASDAQ' / currency='USD' tagging, USD-millions magnitude convention,
upsert+read-back round-trips via a temp-DB FlowStore, and that a normal US
large-cap snapshot does NOT trip the _USD_VALIDATION_RULES bounds.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pandas as pd
from freezegun import freeze_time

from flowtracker.estimates_models import ConsensusEstimate
from flowtracker.market import Market
from flowtracker.us_ingest import (
    fetch_and_store_us_consensus_estimates,
    fetch_and_store_us_daily_prices,
    fetch_and_store_us_valuation_snapshot,
    fetch_us_consensus_estimates,
    fetch_us_daily_prices,
    fetch_us_valuation_snapshot,
)


# --------------------------------------------------------------------------- #
# 1. US daily prices
# --------------------------------------------------------------------------- #

def _price_history_df() -> pd.DataFrame:
    idx = pd.to_datetime(["2025-05-27", "2025-05-28"])
    return pd.DataFrame(
        {
            "Open": [200.0, 205.0],
            "High": [206.0, 210.0],
            "Low": [199.0, 204.0],
            "Close": [205.0, 208.0],
            "Adj Close": [204.5, 207.5],
            "Volume": [50_000_000, 45_000_000],
        },
        index=idx,
    )


def test_fetch_us_daily_prices_maps_keys_and_tags():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _price_history_df()
    with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
        rows = fetch_us_daily_prices("aapl", period="5d")

    assert len(rows) == 2
    r = rows[0]
    assert r["symbol"] == "AAPL"          # upper-cased
    assert r["market"] == "NASDAQ"
    assert r["date"] == "2025-05-27"
    assert r["open"] == 200.0
    assert r["high"] == 206.0
    assert r["low"] == 199.0
    assert r["close"] == 205.0
    assert r["volume"] == 50_000_000
    assert r["adj_close"] == 204.5
    # yfinance called with raw OHLC (auto_adjust=False)
    _, kwargs = mock_ticker.history.call_args
    assert kwargs.get("auto_adjust") is False
    assert kwargs.get("period") == "5d"


def test_fetch_us_daily_prices_empty_history():
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
        assert fetch_us_daily_prices("AAPL") == []


def test_us_daily_prices_roundtrip(store):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _price_history_df()
    with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
        n = fetch_and_store_us_daily_prices(store, "AAPL", period="5d")
    assert n == 2

    got = store.get_us_daily_prices("AAPL")
    assert len(got) == 2
    assert {row["date"] for row in got} == {"2025-05-27", "2025-05-28"}
    assert all(row["market"] == "NASDAQ" for row in got)
    latest = got[0]  # most recent first
    assert latest["date"] == "2025-05-28"
    assert latest["close"] == 208.0
    assert latest["adj_close"] == 207.5


# --------------------------------------------------------------------------- #
# 2. US valuation snapshot
# --------------------------------------------------------------------------- #

def _large_cap_info() -> dict:
    """A realistic Apple-scale snapshot in raw USD (yfinance native units)."""
    return {
        "quoteType": "EQUITY",
        "currentPrice": 207.5,
        "regularMarketPrice": 207.5,
        "marketCap": 3_100_000_000_000,        # $3.1T
        "enterpriseValue": 3_150_000_000_000,
        "trailingPE": 32.0,
        "forwardPE": 28.0,
        "priceToBook": 45.0,
        "dividendYield": 0.005,                 # raw fraction from yfinance
        "beta": 1.25,
        "totalCash": 60_000_000_000,            # $60B
        "totalDebt": 100_000_000_000,           # $100B
        "freeCashflow": 95_000_000_000,         # $95B
        "operatingMargins": 0.30,               # 30%
        "profitMargins": 0.25,                  # 25%
        "returnOnEquity": 1.50,                 # 150% (Apple's actual ~150%)
    }


@freeze_time("2025-05-29")
def test_fetch_us_valuation_snapshot_magnitude_and_mapping():
    mock_ticker = MagicMock()
    mock_ticker.info = _large_cap_info()
    with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
        row = fetch_us_valuation_snapshot("AAPL")

    assert row["symbol"] == "AAPL"
    assert row["market"] == "NASDAQ"
    assert row["currency"] == "USD"
    assert row["date"] == "2025-05-29"
    # raw USD per-share / ratios
    assert row["price"] == 207.5
    assert row["pe_trailing"] == 32.0
    assert row["pe_forward"] == 28.0
    assert row["pb"] == 45.0
    assert row["beta"] == 1.25
    assert row["dividend_yield"] == 0.005
    # USD MILLIONS for monetary aggregates (÷1e6)
    assert row["market_cap"] == 3_100_000.0       # $3.1T -> 3.1M mn
    assert row["enterprise_value"] == 3_150_000.0
    assert row["total_cash"] == 60_000.0
    assert row["total_debt"] == 100_000.0
    assert row["free_cash_flow"] == 95_000.0
    # percentages (×100)
    assert row["operating_margin"] == 30.0
    assert row["net_margin"] == 25.0
    assert row["roe"] == 150.0


def test_us_valuation_snapshot_does_not_trip_validation(store, caplog):
    """A normal US large-cap snapshot must NOT emit validation warnings under
    _USD_VALIDATION_RULES (market_cap in millions is well under the $5T bound)."""
    mock_ticker = MagicMock()
    mock_ticker.info = _large_cap_info()
    with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
        with caplog.at_level(logging.WARNING, logger="flowtracker.validation"):
            n = fetch_and_store_us_valuation_snapshot(store, "AAPL")
    assert n == 1
    val_warnings = [
        r for r in caplog.records
        if r.name == "flowtracker.validation"
    ]
    assert val_warnings == [], f"unexpected validation warnings: {[r.message for r in val_warnings]}"

    got = store.get_us_valuation_snapshot("AAPL")
    assert len(got) == 1
    assert got[0]["market_cap"] == 3_100_000.0
    assert got[0]["currency"] == "USD"
    assert got[0]["roe"] == 150.0


def test_us_valuation_snapshot_unscaled_would_trip_validation():
    """Sanity: raw (unscaled) USD market cap is far above the $5T-millions bound,
    proving the ÷1e6 scaling is what keeps us inside the rules."""
    from flowtracker.store_domains._shared import _validate_row

    bad = {"market_cap": 3_100_000_000_000, "currency": "USD"}
    warnings = _validate_row("us_valuation_snapshot", bad, market="NASDAQ", currency="USD")
    assert any("market_cap" in w for w in warnings)


# --------------------------------------------------------------------------- #
# 3. US consensus estimates
# --------------------------------------------------------------------------- #

def _consensus() -> ConsensusEstimate:
    return ConsensusEstimate(
        symbol="AAPL",
        date="2025-05-29",
        target_mean=240.0,
        target_median=238.0,
        target_high=300.0,
        target_low=180.0,
        num_analysts=40,
        recommendation="buy",
        recommendation_score=2.0,
        forward_pe=28.0,
        forward_eps=7.4,
        eps_current_year=7.0,
        eps_next_year=7.9,
        earnings_growth=12.5,
        current_price=207.5,
    )


def test_fetch_us_consensus_estimates_mapping():
    mock_client = MagicMock()
    mock_client.fetch_estimates.return_value = _consensus()
    row = fetch_us_consensus_estimates("AAPL", client=mock_client)

    mock_client.fetch_estimates.assert_called_once_with("AAPL", market=Market.NASDAQ)
    assert row["symbol"] == "AAPL"
    assert row["market"] == "NASDAQ"
    assert row["currency"] == "USD"
    assert row["date"] == "2025-05-29"
    assert row["target_mean"] == 240.0
    assert row["target_median"] == 238.0
    assert row["num_analysts"] == 40
    assert row["recommendation"] == "buy"
    assert row["forward_pe"] == 28.0
    assert row["forward_eps"] == 7.4
    assert row["eps_current_year"] == 7.0
    assert row["eps_next_year"] == 7.9
    assert row["earnings_growth"] == 12.5
    assert row["current_price"] == 207.5


def test_us_consensus_estimates_none_when_no_data():
    mock_client = MagicMock()
    mock_client.fetch_estimates.return_value = None
    assert fetch_us_consensus_estimates("AAPL", client=mock_client) is None


def test_us_consensus_estimates_roundtrip(store):
    mock_client = MagicMock()
    mock_client.fetch_estimates.return_value = _consensus()
    n = fetch_and_store_us_consensus_estimates(store, "AAPL", client=mock_client)
    assert n == 1

    got = store.get_us_consensus_estimates("AAPL")
    assert len(got) == 1
    assert got[0]["market"] == "NASDAQ"
    assert got[0]["currency"] == "USD"
    assert got[0]["target_mean"] == 240.0
    assert got[0]["num_analysts"] == 40
