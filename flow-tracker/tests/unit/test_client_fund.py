"""Tests for fund_client.py — yfinance fundamentals, valuation snapshot, historical PE."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pandas as pd
import pytest
from freezegun import freeze_time

from flowtracker.fund_client import (
    FundClient,
    YFinanceError,
    _div100,
    _ev_ebitda_currency_safe,
    _safe_get,
    nse_symbol,
)
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


class TestEvEbitdaCurrencySafe:
    """Currency-safe EV/EBITDA: detects ADR-denominated EBITDA (USD) against
    INR-denominated EV and recomputes; otherwise passes raw value through.

    Background: yfinance reports ``enterpriseValue`` in display ``currency``
    (INR for ``.NS`` stocks) but ``ebitda`` in ``financialCurrency`` — which
    is USD for Indian companies that file ADRs in USD (INFY, HCLTECH, WIT).
    The raw ``enterpriseToEbitda`` field then computes INR-EV / USD-EBITDA,
    inflating EV/EBITDA by ~84x (INFY=994x in production).
    """

    def test_same_currency_sane_value_passthrough(self):
        info = {
            "currency": "INR",
            "financialCurrency": "INR",
            "enterpriseToEbitda": 11.5,
        }
        assert _ev_ebitda_currency_safe(info) == 11.5

    def test_same_currency_absurd_value_dropped(self):
        """Same-currency but EV/EBITDA > 100 is data junk → drop."""
        info = {
            "currency": "INR",
            "financialCurrency": "INR",
            "enterpriseToEbitda": 250.0,
        }
        assert _ev_ebitda_currency_safe(info) is None

    def test_cross_currency_recomputes_with_fx(self, monkeypatch):
        """USD financialCurrency on INR-listed stock: recompute via stored FX."""
        from flowtracker.macro_models import MacroSnapshot

        info = {
            "currency": "INR",
            "financialCurrency": "USD",
            "enterpriseValue": 4_669_912_907_776,  # INR (INFY-like)
            "ebitda": 4_428_000_256,  # USD
            "enterpriseToEbitda": 1054.6,  # raw yfinance — wrong
        }

        # Patch FlowStore.get_macro_latest to return a known FX rate.
        class _FakeStore:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def get_macro_latest(self):
                return MacroSnapshot(date="2026-04-25", usd_inr=84.0)

        monkeypatch.setattr(
            "flowtracker.fund_client.FlowStore",
            lambda: _FakeStore(),
            raising=False,
        )
        # Re-import path: helper imports FlowStore inline.
        import flowtracker.store as _store_mod
        monkeypatch.setattr(_store_mod, "FlowStore", lambda: _FakeStore())

        ratio = _ev_ebitda_currency_safe(info)
        # 4_669_912_907_776 / (4_428_000_256 * 84) = ~12.55
        assert ratio is not None
        assert 10 < ratio < 15

    def test_cross_currency_no_fx_drops_absurd(self, monkeypatch):
        """No FX rate available + raw is absurd → drop rather than publish junk."""
        info = {
            "currency": "INR",
            "financialCurrency": "USD",
            "enterpriseValue": 4_669_912_907_776,
            "ebitda": 4_428_000_256,
            "enterpriseToEbitda": 1054.6,
        }

        class _NoMacroStore:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def get_macro_latest(self):
                return None

        import flowtracker.store as _store_mod
        monkeypatch.setattr(_store_mod, "FlowStore", lambda: _NoMacroStore())

        assert _ev_ebitda_currency_safe(info) is None

    def test_missing_currency_fields_passthrough(self):
        """No currency metadata at all → trust raw if sane."""
        info = {"enterpriseToEbitda": 22.5}
        assert _ev_ebitda_currency_safe(info) == 22.5

    def test_none_input_returns_none(self):
        assert _ev_ebitda_currency_safe({}) is None


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

    def test_cash_flow_fallback_from_statement(self):
        """When info lacks freeCashflow/operatingCashflow (typical for NSE),
        fall back to get_cash_flow(freq='yearly') with FreeCashFlow /
        OperatingCashFlow rows."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "currentPrice": 100.0,
            "freeCashflow": None,
            "operatingCashflow": None,
        }
        # 1e9 rupees == 100 crore
        cash_flow_df = pd.DataFrame(
            {pd.Timestamp("2025-03-31"): [1e9, 2e9]},
            index=["FreeCashFlow", "OperatingCashFlow"],
        )
        mock_ticker.get_cash_flow.return_value = cash_flow_df
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            snap = client.fetch_valuation_snapshot("RELIANCE")
        assert snap.free_cash_flow == 100.0  # 1e9 / 1e7
        assert snap.operating_cash_flow == 200.0  # 2e9 / 1e7

    def test_peg_ratio_falls_back_to_trailing(self):
        """pegRatio is missing for many NSE tickers; trailingPegRatio is the
        documented fallback."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "currentPrice": 100.0,
            "pegRatio": None,
            "trailingPegRatio": 2.75,
        }
        mock_ticker.get_cash_flow.return_value = pd.DataFrame()
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            snap = client.fetch_valuation_snapshot("ITC")
        assert snap.peg_ratio == 2.75

    def test_peg_ratio_prefers_primary_over_trailing(self):
        """When both pegRatio and trailingPegRatio are present, keep pegRatio."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "currentPrice": 100.0,
            "pegRatio": 0.82,
            "trailingPegRatio": 2.75,
        }
        mock_ticker.get_cash_flow.return_value = pd.DataFrame()
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            snap = client.fetch_valuation_snapshot("RELIANCE")
        assert snap.peg_ratio == 0.82


class TestTickerCache:
    """Test _ticker cache with 5-minute TTL."""

    def test_cache_hit_within_ttl(self):
        """Two consecutive calls within 5 minutes -> only 1 yfinance.Ticker construction."""
        with patch("flowtracker.fund_client.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value = MagicMock()
            client = FundClient()
            with freeze_time("2025-01-01 12:00:00"):
                t1 = client._ticker("SBIN")
            with freeze_time("2025-01-01 12:04:00"):  # 4 min later, within TTL
                t2 = client._ticker("SBIN")
            assert t1 is t2
            assert mock_ticker_cls.call_count == 1

    def test_cache_expires_after_ttl(self):
        """After 5 min -> re-construct."""
        with patch("flowtracker.fund_client.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.side_effect = [MagicMock(), MagicMock()]
            client = FundClient()
            with freeze_time("2025-01-01 12:00:00"):
                client._ticker("SBIN")
            with freeze_time("2025-01-01 12:06:00"):  # 6 min later, past TTL
                client._ticker("SBIN")
            assert mock_ticker_cls.call_count == 2

    def test_cache_separates_symbols(self):
        """Different symbols cached separately."""
        with patch("flowtracker.fund_client.yf.Ticker") as mock_ticker_cls:
            mock_ticker_cls.side_effect = [MagicMock(), MagicMock()]
            client = FundClient()
            client._ticker("SBIN")
            client._ticker("TECHM")
            assert mock_ticker_cls.call_count == 2


class TestInfoCache:
    """Test _info cache with 5-minute TTL."""

    def test_info_cache_hit_within_ttl(self):
        """Two _info calls within TTL -> info accessed once."""
        mock_ticker = MagicMock()
        info_prop = PropertyMock(return_value={"quoteType": "EQUITY", "longName": "X"})
        type(mock_ticker).info = info_prop
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            with freeze_time("2025-01-01 12:00:00"):
                i1 = client._info("SBIN")
            with freeze_time("2025-01-01 12:04:00"):
                i2 = client._info("SBIN")
            assert i1 is i2
            assert info_prop.call_count == 1

    def test_info_cache_expires_after_ttl(self):
        """After 5 min -> info fetched again."""
        mock_ticker = MagicMock()
        info_prop = PropertyMock(return_value={"quoteType": "EQUITY", "longName": "X"})
        type(mock_ticker).info = info_prop
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            with freeze_time("2025-01-01 12:00:00"):
                client._info("SBIN")
            with freeze_time("2025-01-01 12:06:00"):
                client._info("SBIN")
            assert info_prop.call_count == 2

    def test_info_raises_when_no_data(self):
        """Empty/quoteType=None info raises YFinanceError."""
        mock_ticker = MagicMock()
        type(mock_ticker).info = PropertyMock(return_value={})
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            with pytest.raises(YFinanceError, match="No data found for SBIN"):
                client._info("SBIN")

    def test_get_live_snapshot(self):
        """get_live_snapshot returns LiveSnapshot from info dict."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "quoteType": "EQUITY",
            "longName": "State Bank of India",
            "sector": "Financial Services",
            "currentPrice": 820.0,
            "marketCap": 7300000000000,
            "trailingPE": 9.5,
            "returnOnEquity": 0.18,
            "debtToEquity": 50.0,
        }
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            snap = client.get_live_snapshot("SBIN")
        assert snap.symbol == "SBIN"
        assert snap.company_name == "State Bank of India"
        assert snap.price == 820.0
        assert snap.roe == 18.0  # 0.18 * 100
        assert snap.debt_to_equity == 0.5  # 50 / 100


class TestFetchHistoricalPE:
    """Test fetch_weekly_prices + compute_historical_pe end-to-end with mocked yfinance."""

    def test_full_path_with_quarterly_history(self):
        """Mock yfinance Ticker.history -> compute_historical_pe yields PE snapshots."""
        # Build a weekly-price DataFrame for 2024-2025
        idx = pd.DatetimeIndex(["2024-06-15", "2025-06-15"])
        hist_df = pd.DataFrame(
            {"Close": [500.0, 900.0], "Volume": [100000, 200000]},
            index=idx,
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist_df
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            prices = client.fetch_weekly_prices("SBIN")
            assert len(prices) == 2
            assert prices[0][0] == "2024-06-15"
            assert prices[0][1] == 500.0
            assert prices[0][2] == 100000

            eps_list = [
                AnnualEPS(symbol="SBIN", fiscal_year_end="2024-03-31", eps=50.0),
                AnnualEPS(symbol="SBIN", fiscal_year_end="2025-03-31", eps=60.0),
            ]
            snapshots = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
            assert len(snapshots) == 2
            assert snapshots[0].pe_trailing == 10.0  # 500/50
            assert snapshots[1].pe_trailing == 15.0  # 900/60

    def test_fetch_weekly_prices_empty_df(self):
        """Empty history DataFrame -> empty list."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            assert client.fetch_weekly_prices("SBIN") == []

    def test_fetch_weekly_prices_none_history(self):
        """None history -> empty list."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = None
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            assert client.fetch_weekly_prices("SBIN") == []


class TestExtremePEFilter:
    """Cover compute_historical_pe filter branches with multiple price points."""

    def test_mix_of_extreme_and_valid(self):
        """Some prices yield PE > 200 (filtered), others valid."""
        client = FundClient()
        eps_list = [AnnualEPS(symbol="SBIN", fiscal_year_end="2024-03-31", eps=50.0)]
        prices = [
            ("2024-06-15", 500.0, 100000),    # PE = 10, valid
            ("2024-07-15", 30000.0, 100000),  # PE = 600, filtered
            ("2024-08-15", 25.0, 100000),     # PE = 0.5, filtered
            ("2024-09-15", 1000.0, 100000),   # PE = 20, valid
        ]
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert len(result) == 2
        assert result[0].pe_trailing == 10.0
        assert result[1].pe_trailing == 20.0

    def test_no_applicable_eps(self):
        """All prices precede earliest fiscal_year_end -> empty."""
        client = FundClient()
        eps_list = [AnnualEPS(symbol="SBIN", fiscal_year_end="2025-03-31", eps=50.0)]
        prices = [("2024-06-15", 500.0, 100000)]  # before any FY end
        result = client.compute_historical_pe("SBIN", eps_list, weekly_prices=prices)
        assert result == []


class TestFetchQuarterlyResults:
    """Test fetch_quarterly_results with mocked income statement."""

    def test_basic_quarterly_results(self):
        col = pd.Timestamp("2024-12-31")
        income_df = pd.DataFrame(
            {col: [1000.0, 400.0, 200.0, 150.0, 250.0, 5.0, 4.8]},
            index=[
                "TotalRevenue", "GrossProfit", "OperatingIncome",
                "NetIncome", "EBITDA", "BasicEPS", "DilutedEPS",
            ],
        )
        mock_ticker = MagicMock()
        mock_ticker.get_income_stmt.return_value = income_df
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            results = client.fetch_quarterly_results("SBIN")
        assert len(results) == 1
        r = results[0]
        assert r.symbol == "SBIN"
        assert r.quarter_end == "2024-12-31"
        assert r.revenue == 1000.0
        assert r.net_income == 150.0
        assert r.operating_margin == 0.2  # 200/1000
        assert r.net_margin == 0.15  # 150/1000

    def test_empty_income_returns_empty(self):
        mock_ticker = MagicMock()
        mock_ticker.get_income_stmt.return_value = pd.DataFrame()
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            assert client.fetch_quarterly_results("SBIN") == []

    def test_none_income_returns_empty(self):
        mock_ticker = MagicMock()
        mock_ticker.get_income_stmt.return_value = None
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            assert client.fetch_quarterly_results("SBIN") == []


class TestFetchQuarterlyBSCF:
    """Test fetch_quarterly_bs_cf with mocked balance sheet + cash flow."""

    def test_basic_bs_cf(self):
        col = pd.Timestamp("2024-12-31")
        bs_df = pd.DataFrame(
            {col: [1e9, 5e8, 3e8, 4e8, 1e8, 2e8, 1e7]},
            index=[
                "Total Assets", "Total Debt", "Long Term Debt",
                "Stockholders Equity", "Cash And Cash Equivalents",
                "Net Debt", "Ordinary Shares Number",
            ],
        )
        cf_df = pd.DataFrame(
            {col: [2e8, 1.5e8, -5e7, -1e8, -1e8, 1e7, 5e7]},
            index=[
                "Operating Cash Flow", "Free Cash Flow", "Capital Expenditure",
                "Investing Cash Flow", "Financing Cash Flow",
                "Change In Working Capital", "Depreciation And Amortization",
            ],
        )
        mock_ticker = MagicMock()
        # quarterly_balance_sheet and quarterly_cashflow are properties
        type(mock_ticker).quarterly_balance_sheet = PropertyMock(return_value=bs_df)
        type(mock_ticker).quarterly_cashflow = PropertyMock(return_value=cf_df)
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            result = client.fetch_quarterly_bs_cf("SBIN")
        assert result["symbol"] == "SBIN"
        assert len(result["balance_sheet"]) == 1
        bs = result["balance_sheet"][0]
        assert bs["quarter_end"] == "2024-12-31"
        assert bs["total_assets"] == 100.0  # 1e9 / 1e7
        assert bs["shares_outstanding"] == 10000000  # raw round, no /1e7
        assert len(result["cash_flow"]) == 1
        cf = result["cash_flow"][0]
        assert cf["operating_cash_flow"] == 20.0  # 2e8 / 1e7

    def test_empty_bs_cf(self):
        mock_ticker = MagicMock()
        type(mock_ticker).quarterly_balance_sheet = PropertyMock(return_value=pd.DataFrame())
        type(mock_ticker).quarterly_cashflow = PropertyMock(return_value=pd.DataFrame())
        with patch("flowtracker.fund_client.yf.Ticker", return_value=mock_ticker):
            client = FundClient()
            result = client.fetch_quarterly_bs_cf("SBIN")
        assert result["balance_sheet"] == []
        assert result["cash_flow"] == []


class TestFetchYahooPeers:
    """Test fetch_yahoo_peers httpx call path."""

    def test_basic_peers(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "finance": {
                "result": [{
                    "recommendedSymbols": [
                        {"symbol": "HDFCBANK.NS", "score": 0.1},
                        {"symbol": "ICICIBANK.NS", "score": 0.2},
                    ],
                }],
            },
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            client = FundClient()
            peers = client.fetch_yahoo_peers("SBIN")
        assert len(peers) == 2
        assert peers[0]["peer_symbol"] == "HDFCBANK"  # .NS stripped
        assert peers[0]["score"] == 0.1
        assert peers[1]["peer_symbol"] == "ICICIBANK"

    def test_empty_results_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"finance": {"result": []}}
        mock_resp.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=mock_resp):
            client = FundClient()
            assert client.fetch_yahoo_peers("SBIN") == []

    def test_exception_returns_empty(self):
        with patch("httpx.get", side_effect=Exception("boom")):
            client = FundClient()
            assert client.fetch_yahoo_peers("SBIN") == []
