"""Tests for fund_client.py — yfinance fundamentals, valuation snapshot, historical PE."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd

from flowtracker.fund_client import FundClient, _safe_get, _div100, nse_symbol
from flowtracker.fund_models import AnnualEPS, ValuationSnapshot


class TestNseSymbol:
    """Test nse_symbol conversion."""

    def test_plain_symbol(self):
        assert nse_symbol("SBIN") == "SBIN.NS"

    def test_already_ns(self):
        assert nse_symbol("SBIN.NS") == "SBIN.NS"

    def test_already_bo(self):
        assert nse_symbol("SBIN.BO") == "SBIN.BO"


class TestSafeGet:
    """Test _safe_get helper for DataFrame extraction."""

    def test_valid_extraction(self):
        df = pd.DataFrame({"2024-03": [100.0]}, index=["TotalRevenue"])
        assert _safe_get(df, "TotalRevenue", "2024-03") == 100.0

    def test_missing_row_returns_none(self):
        df = pd.DataFrame({"2024-03": [100.0]}, index=["TotalRevenue"])
        assert _safe_get(df, "NetIncome", "2024-03") is None

    def test_missing_col_returns_none(self):
        df = pd.DataFrame({"2024-03": [100.0]}, index=["TotalRevenue"])
        assert _safe_get(df, "TotalRevenue", "2025-03") is None

    def test_nan_returns_none(self):
        df = pd.DataFrame({"2024-03": [float("nan")]}, index=["TotalRevenue"])
        assert _safe_get(df, "TotalRevenue", "2024-03") is None

    def test_none_value_returns_none(self):
        df = pd.DataFrame({"2024-03": [None]}, index=["TotalRevenue"])
        assert _safe_get(df, "TotalRevenue", "2024-03") is None


class TestDiv100:
    """Test _div100 helper."""

    def test_normal_value(self):
        assert _div100(50.0) == 0.5

    def test_none_returns_none(self):
        assert _div100(None) is None

    def test_zero(self):
        assert _div100(0.0) == 0.0


class TestComputeHistoricalPE:
    """Test compute_historical_pe — pure function (no network)."""

    def _make_eps(self, fy_end: str, eps: float) -> AnnualEPS:
        return AnnualEPS(symbol="SBIN", fiscal_year_end=fy_end, eps=eps)

    def test_basic_pe_computation(self):
        client = FundClient()
        eps_list = [
            self._make_eps("2024-03-31", 50.0),
            self._make_eps("2025-03-31", 60.0),
        ]
        prices = [
            ("2024-06-15", 500.0, 100000),
            ("2025-06-15", 900.0, 200000),
        ]
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert len(result) == 2
        # 500 / 50 = 10
        assert result[0].pe_trailing == 10.0
        assert result[0].price == 500.0
        # 900 / 60 = 15
        assert result[1].pe_trailing == 15.0

    def test_empty_eps_returns_empty(self):
        client = FundClient()
        result = client.compute_historical_pe("SBIN", [], weekly_prices=[("2025-01-01", 500, 0)])
        assert result == []

    def test_empty_prices_returns_empty(self):
        client = FundClient()
        eps_list = [self._make_eps("2024-03-31", 50.0)]
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=[])
        assert result == []

    def test_zero_price_skipped(self):
        client = FundClient()
        eps_list = [self._make_eps("2024-03-31", 50.0)]
        prices = [("2024-06-15", 0, 100000)]
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert result == []

    def test_negative_eps_skipped(self):
        client = FundClient()
        eps_list = [self._make_eps("2024-03-31", -5.0)]
        prices = [("2024-06-15", 500.0, 100000)]
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert result == []

    def test_extreme_pe_filtered(self):
        """PE > 200 is filtered as data error."""
        client = FundClient()
        eps_list = [self._make_eps("2024-03-31", 1.0)]
        prices = [("2024-06-15", 500.0, 100000)]  # PE = 500
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert result == []

    def test_pe_below_1_filtered(self):
        """PE < 1 is filtered as data error."""
        client = FundClient()
        eps_list = [self._make_eps("2024-03-31", 1000.0)]
        prices = [("2024-06-15", 500.0, 100000)]  # PE = 0.5
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert result == []

    def test_eps_sorted_and_applied_correctly(self):
        """Ensures the most recent EPS as-of each date is used."""
        client = FundClient()
        eps_list = [
            self._make_eps("2025-03-31", 60.0),
            self._make_eps("2024-03-31", 50.0),
        ]
        prices = [
            ("2024-06-15", 500.0, 100000),  # should use 50 EPS
            ("2025-06-15", 900.0, 200000),  # should use 60 EPS
        ]
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert result[0].pe_trailing == 10.0  # 500/50
        assert result[1].pe_trailing == 15.0  # 900/60


class TestFetchValuationSnapshot:
    """Test fetch_valuation_snapshot with mocked yfinance."""

    def test_basic_snapshot(self):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "currentPrice": 820.0,
            "regularMarketPrice": 820.0,
            "marketCap": 7300000000000,
            "enterpriseValue": 7500000000000,
            "trailingPE": 9.5,
            "forwardPE": 8.0,
            "priceToBook": 1.8,
            "enterpriseToEbitda": 6.5,
            "returnOnEquity": 0.18,
            "debtToEquity": 50.0,  # in % — should be divided by 100
            "fiftyTwoWeekHigh": 900.0,
            "fiftyTwoWeekLow": 650.0,
        }
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            snap = client.fetch_valuation_snapshot("SBIN")

        assert snap.symbol == "SBIN"
        assert snap.price == 820.0
        assert snap.pe_trailing == 9.5
        assert snap.debt_to_equity == 0.5  # 50/100
        assert snap.fifty_two_week_high == 900.0
