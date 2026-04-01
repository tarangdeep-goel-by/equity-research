"""Tests for estimates_client.py — yfinance consensus estimates and surprises."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from flowtracker.estimates_client import EstimatesClient


# -- Mock info dict --

_MOCK_INFO = {
    "quoteType": "EQUITY",
    "targetMeanPrice": 950.0,
    "targetMedianPrice": 940.0,
    "targetHighPrice": 1100.0,
    "targetLowPrice": 800.0,
    "numberOfAnalystOpinions": 28,
    "recommendationKey": "buy",
    "recommendationMean": 2.1,
    "forwardPE": 8.5,
    "forwardEps": 96.5,
    "earningsGrowth": 0.15,
    "currentPrice": 820.0,
}


class TestFetchEstimates:
    """Test fetch_estimates with mocked yfinance."""

    def test_basic_estimates(self):
        mock_ticker = MagicMock()
        mock_ticker.info = _MOCK_INFO

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.symbol == "SBIN"
        assert est.target_mean == 950.0
        assert est.target_median == 940.0
        assert est.target_high == 1100.0
        assert est.target_low == 800.0
        assert est.num_analysts == 28
        assert est.recommendation == "buy"
        assert est.recommendation_score == 2.1
        assert est.forward_pe == 8.5
        assert est.current_price == 820.0

    def test_no_data_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {"quoteType": None}

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("INVALID")

        assert est is None

    def test_empty_info_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {}

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("INVALID")

        assert est is None

    def test_exception_returns_none(self):
        with patch("flowtracker.estimates_client.yf.Ticker", side_effect=Exception("network")):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is None


class TestFetchSurprises:
    """Test fetch_surprises with mocked yfinance."""

    def test_quarterly_earnings_path(self):
        mock_ticker = MagicMock()
        qe = pd.DataFrame(
            {"Earnings": [20.5, 22.0], "Surprise(%)": [5.2, -1.3]},
            index=["Q1 2025", "Q2 2025"],
        )
        mock_ticker.quarterly_earnings = qe

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert len(surprises) == 2
        assert surprises[0].symbol == "SBIN"
        assert surprises[0].quarter_end == "Q1 2025"
        assert surprises[0].eps_actual == 20.5
        assert surprises[0].surprise_pct == 5.2
        assert surprises[1].surprise_pct == -1.3

    def test_empty_quarterly_earnings_falls_through(self):
        mock_ticker = MagicMock()
        mock_ticker.quarterly_earnings = pd.DataFrame()  # empty
        mock_ticker.get_earnings_history.return_value = pd.DataFrame()  # empty too

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert surprises == []

    def test_exception_returns_empty(self):
        with patch("flowtracker.estimates_client.yf.Ticker", side_effect=Exception("network")):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert surprises == []

    def test_nan_surprise_handled(self):
        mock_ticker = MagicMock()
        qe = pd.DataFrame(
            {"Earnings": [20.5], "Surprise(%)": [float("nan")]},
            index=["Q1 2025"],
        )
        mock_ticker.quarterly_earnings = qe

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert len(surprises) == 1
        assert surprises[0].surprise_pct is None  # nan filtered to None
