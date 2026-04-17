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


class TestEpsCurrentNextYear:
    """fetch_estimates should populate eps_current_year / eps_next_year from
    yfinance's earnings_estimate DataFrame (period index `0y` / `+1y`)."""

    def _earnings_estimate_df(self) -> pd.DataFrame:
        """Mirrors the live yfinance shape: rows `0q`, `+1q`, `0y`, `+1y`."""
        return pd.DataFrame(
            {
                "avg": [10.0, 11.0, 59.5, 65.2],
                "low": [9.0, 10.0, 53.0, 48.0],
                "high": [11.0, 12.0, 65.0, 88.0],
                "yearAgoEps": [8.0, 9.0, 51.0, 59.5],
                "numberOfAnalysts": [8, 1, 34, 34],
                "growth": [0.09, 0.15, 0.15, 0.10],
                "currency": ["INR"] * 4,
            },
            index=["0q", "+1q", "0y", "+1y"],
        )

    def test_populates_cy_and_ny_eps(self):
        mock_ticker = MagicMock()
        mock_ticker.info = _MOCK_INFO
        mock_ticker.earnings_estimate = self._earnings_estimate_df()

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.eps_current_year == 59.5
        assert est.eps_next_year == 65.2

    def test_empty_earnings_estimate_leaves_fields_none(self):
        mock_ticker = MagicMock()
        mock_ticker.info = _MOCK_INFO
        mock_ticker.earnings_estimate = pd.DataFrame()

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.eps_current_year is None
        assert est.eps_next_year is None

    def test_missing_earnings_estimate_attribute_leaves_fields_none(self):
        """yfinance raising when accessing earnings_estimate must not crash fetch."""
        mock_ticker = MagicMock()
        mock_ticker.info = _MOCK_INFO
        type(mock_ticker).earnings_estimate = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no earnings_estimate"))
        )

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.eps_current_year is None
        assert est.eps_next_year is None

    def test_partial_periods_populate_available(self):
        """Only `0y` row present → eps_current_year set, eps_next_year None."""
        mock_ticker = MagicMock()
        mock_ticker.info = _MOCK_INFO
        mock_ticker.earnings_estimate = pd.DataFrame(
            {"avg": [50.0]},
            index=["0y"],
        )

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.eps_current_year == 50.0
        assert est.eps_next_year is None

    def test_nan_avg_filtered_to_none(self):
        mock_ticker = MagicMock()
        mock_ticker.info = _MOCK_INFO
        mock_ticker.earnings_estimate = pd.DataFrame(
            {"avg": [float("nan"), float("nan")]},
            index=["0y", "+1y"],
        )

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.eps_current_year is None
        assert est.eps_next_year is None


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


class TestEarningHistoryFallback:
    """quarterly_earnings empty → fallback to get_earnings_history."""

    def test_earning_history_populates_surprises(self):
        mock_ticker = MagicMock()
        # quarterly_earnings raises so fallback path is used
        type(mock_ticker).quarterly_earnings = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no qe"))
        )
        eh = pd.DataFrame(
            [
                {"epsActual": 2.0, "epsEstimate": 1.8, "quarter": "2025Q1"},
                {"epsActual": 3.0, "epsEstimate": 3.0, "quarter": "2025Q2"},
            ]
        )
        mock_ticker.get_earnings_history.return_value = eh

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert len(surprises) == 2
        # surprise_pct = (2.0-1.8)/1.8 * 100 ≈ 11.11
        assert surprises[0].eps_actual == 2.0
        assert surprises[0].eps_estimate == 1.8
        assert surprises[0].surprise_pct == round((0.2 / 1.8) * 100, 2)
        assert surprises[0].quarter_end == "2025Q1"
        # zero-surprise
        assert surprises[1].surprise_pct == 0.0

    def test_earning_history_handles_zero_estimate(self):
        """estimate == 0 → division branch skipped, surprise_pct stays None."""
        mock_ticker = MagicMock()
        type(mock_ticker).quarterly_earnings = property(
            lambda self: (_ for _ in ()).throw(AttributeError("no qe"))
        )
        eh = pd.DataFrame(
            {"epsActual": [1.5], "epsEstimate": [0.0], "quarter": ["2025Q3"]}
        )
        mock_ticker.get_earnings_history.return_value = eh

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert len(surprises) == 1
        assert surprises[0].eps_actual == 1.5
        assert surprises[0].eps_estimate == 0.0
        # estimate==0 → branch skips division → surprise_pct stays None
        assert surprises[0].surprise_pct is None

    def test_earning_history_exception_returns_empty(self):
        """quarterly_earnings empty + get_earnings_history throws → []."""
        mock_ticker = MagicMock()
        mock_ticker.quarterly_earnings = pd.DataFrame()
        mock_ticker.get_earnings_history.side_effect = RuntimeError("api down")

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            surprises = client.fetch_surprises("SBIN")

        assert surprises == []


class TestNaNHandling:
    """NaN/None tolerance across estimate fields."""

    def test_missing_earnings_growth_defaults_none(self):
        """No earningsGrowth field → earnings_growth is None, not a crash."""
        info = dict(_MOCK_INFO)
        info.pop("earningsGrowth")
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.earnings_growth is None

    def test_none_recommendation_score_passthrough(self):
        """recommendationMean=None → recommendation_score is None."""
        info = dict(_MOCK_INFO)
        info["recommendationMean"] = None
        info["recommendationKey"] = None
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.recommendation_score is None
        assert est.recommendation is None

    def test_current_price_fallback_to_regular_market(self):
        """Missing currentPrice → uses regularMarketPrice fallback."""
        info = dict(_MOCK_INFO)
        info.pop("currentPrice")
        info["regularMarketPrice"] = 777.5
        mock_ticker = MagicMock()
        mock_ticker.info = info

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            est = client.fetch_estimates("SBIN")

        assert est is not None
        assert est.current_price == 777.5


class TestEstimateRevisions:
    """fetch_estimate_revisions — EPS trend + revisions momentum score."""

    def test_positive_momentum(self):
        mock_ticker = MagicMock()
        # Trend: current > 90d ago → positive change
        eps_trend = pd.DataFrame(
            {
                "current": [1.20, 1.30, 5.0, 6.0],
                "7daysAgo": [1.19, 1.29, 4.95, 5.95],
                "30daysAgo": [1.18, 1.28, 4.90, 5.90],
                "60daysAgo": [1.15, 1.25, 4.80, 5.80],
                "90daysAgo": [1.00, 1.10, 4.50, 5.50],
            },
            index=["0q", "+1q", "0y", "+1y"],
        )
        eps_revisions = pd.DataFrame(
            {
                "upLast7days": [2, 3, 1, 2],
                "upLast30days": [5, 6, 3, 4],
                "downLast30days": [1, 0, 1, 1],
                "downLast7Days": [0, 0, 0, 0],
            },
            index=["0q", "+1q", "0y", "+1y"],
        )
        mock_ticker.eps_trend = eps_trend
        mock_ticker.eps_revisions = eps_revisions

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            result = client.fetch_estimate_revisions("SBIN")

        assert result is not None
        assert result["symbol"] == "SBIN"
        assert "0q" in result["eps_trend"]
        assert result["eps_trend"]["0q"]["current"] == 1.20
        assert result["momentum_signal"] == "positive"
        assert 0.0 <= result["momentum_score"] <= 1.0

    def test_empty_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.eps_trend = pd.DataFrame()
        mock_ticker.eps_revisions = pd.DataFrame()

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            result = client.fetch_estimate_revisions("SBIN")

        assert result is None

    def test_exception_returns_none(self):
        with patch(
            "flowtracker.estimates_client.yf.Ticker",
            side_effect=Exception("yf down"),
        ):
            client = EstimatesClient()
            assert client.fetch_estimate_revisions("SBIN") is None


class TestEventsCalendar:
    """fetch_events_calendar — earnings date, ex-div, consensus."""

    def test_dict_calendar_parses_earnings_and_estimates(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = {
            "Earnings Date": ["2026-05-01"],
            "Ex-Dividend Date": "2026-03-10",
            "Earnings Average": 5.0,
            "Earnings High": 6.0,
            "Earnings Low": 4.0,
            "Revenue Average": 1_000_000_000,  # 100 Cr
            "Revenue High": 1_200_000_000,
            "Revenue Low": 900_000_000,
        }

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            result = client.fetch_events_calendar("SBIN")

        assert result is not None
        assert result["symbol"] == "SBIN"
        assert result["next_earnings"] == "2026-05-01"
        assert "days_to_earnings" in result
        assert result["ex_dividend_date"] == "2026-03-10"
        assert result["earnings_estimate"]["avg"] == 5.0
        assert result["revenue_estimate_cr"]["avg"] == 100.0

    def test_none_calendar_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.calendar = None

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            assert client.fetch_events_calendar("SBIN") is None

    def test_exception_returns_none(self):
        with patch(
            "flowtracker.estimates_client.yf.Ticker",
            side_effect=Exception("oops"),
        ):
            client = EstimatesClient()
            assert client.fetch_events_calendar("SBIN") is None


class TestRevenueEstimates:
    """fetch_revenue_estimates — crore conversion."""

    def test_converts_to_crores(self):
        mock_ticker = MagicMock()
        rev = pd.DataFrame(
            {
                "avg": [1_000_000_000, 2_000_000_000],  # 100Cr, 200Cr
                "low": [900_000_000, 1_800_000_000],
                "high": [1_100_000_000, 2_200_000_000],
                "numberOfAnalysts": [10, 12],
                "yearAgoRevenue": [800_000_000, 1_600_000_000],
                "growth": [0.25, 0.25],
            },
            index=["0q", "+1y"],
        )
        mock_ticker.revenue_estimate = rev

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            result = client.fetch_revenue_estimates("SBIN")

        assert result is not None
        assert result["symbol"] == "SBIN"
        assert len(result["periods"]) == 2
        assert result["periods"][0]["avg_cr"] == 100.0
        assert result["periods"][0]["num_analysts"] == 10
        assert result["periods"][0]["growth"] == 0.25

    def test_empty_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.revenue_estimate = pd.DataFrame()

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            assert client.fetch_revenue_estimates("SBIN") is None


class TestGrowthEstimates:
    """fetch_growth_estimates — stock vs index."""

    def test_outperforming(self):
        mock_ticker = MagicMock()
        growth = pd.DataFrame(
            {
                "stockTrend": [0.15, 0.20, 0.12],
                "indexTrend": [0.10, 0.12, 0.12],
            },
            index=["0q", "+1y", "LTG"],
        )
        mock_ticker.growth_estimates = growth

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            result = client.fetch_growth_estimates("SBIN")

        assert result is not None
        assert result["symbol"] == "SBIN"
        # 0q and +1y go in periods; LTG goes in ltg dict
        assert len(result["periods"]) == 2
        assert result["periods"][0]["vs_index"] == "outperforming"
        assert result["ltg"]["stock"] == 0.12

    def test_empty_returns_none(self):
        mock_ticker = MagicMock()
        mock_ticker.growth_estimates = pd.DataFrame()

        with patch("flowtracker.estimates_client.yf.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            assert client.fetch_growth_estimates("SBIN") is None


class TestFetchBatch:
    """fetch_batch aggregates estimates + surprises across symbols."""

    def test_batch_aggregates_results(self):
        def ticker_factory(sym):
            t = MagicMock()
            t.info = _MOCK_INFO
            t.quarterly_earnings = pd.DataFrame(
                {"Earnings": [20.0], "Surprise(%)": [2.5]}, index=["Q1"]
            )
            return t

        with (
            patch("flowtracker.estimates_client.yf.Ticker", side_effect=ticker_factory),
            patch("flowtracker.estimates_client.time.sleep"),  # skip rate-limit delay
        ):
            client = EstimatesClient()
            estimates, surprises = client.fetch_batch(["SBIN", "HDFCBANK"])

        assert len(estimates) == 2
        assert len(surprises) == 2
        assert {e.symbol for e in estimates} == {"SBIN", "HDFCBANK"}
