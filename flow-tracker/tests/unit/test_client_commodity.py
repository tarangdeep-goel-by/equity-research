"""Tests for commodity_client.py — gold/silver prices and ETF NAVs."""

from __future__ import annotations

import math
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import respx

from flowtracker.commodity_client import CommodityClient


def _make_hist(data: dict[str, list[float]], dates: list[str]) -> pd.DataFrame:
    """Build a DataFrame mimicking yfinance .history() output."""
    idx = pd.to_datetime(dates)
    return pd.DataFrame(data, index=idx)


class TestFetchPrices:
    """Test fetch_prices with mocked yfinance Ticker.history."""

    def test_basic_gold_silver(self):
        gold_hist = _make_hist({"Close": [2000.0]}, ["2026-03-20"])
        silver_hist = _make_hist({"Close": [25.0]}, ["2026-03-20"])
        usdinr_hist = _make_hist({"Close": [85.0]}, ["2026-03-20"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "GC=F":
                t.history.return_value = gold_hist
            elif symbol == "SI=F":
                t.history.return_value = silver_hist
            elif symbol == "INR=X":
                t.history.return_value = usdinr_hist
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_prices(days=5)

        symbols = {r.symbol for r in records}
        assert "GOLD" in symbols
        assert "SILVER" in symbols
        assert "GOLD_INR" in symbols
        assert "SILVER_INR" in symbols

    def test_gold_usd_price(self):
        gold_hist = _make_hist({"Close": [2000.0]}, ["2026-03-20"])
        usdinr_hist = _make_hist({"Close": [85.0]}, ["2026-03-20"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "GC=F":
                t.history.return_value = gold_hist
            elif symbol == "SI=F":
                t.history.return_value = pd.DataFrame()
            elif symbol == "INR=X":
                t.history.return_value = usdinr_hist
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_prices(days=5)

        gold_usd = [r for r in records if r.symbol == "GOLD"]
        assert len(gold_usd) == 1
        assert gold_usd[0].price == 2000.0
        assert gold_usd[0].unit == "USD/oz"

    def test_gold_inr_conversion(self):
        """GOLD_INR = (USD/oz * INR/USD) / 31.1035 * 10."""
        gold_hist = _make_hist({"Close": [2000.0]}, ["2026-03-20"])
        usdinr_hist = _make_hist({"Close": [85.0]}, ["2026-03-20"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "GC=F":
                t.history.return_value = gold_hist
            elif symbol == "SI=F":
                t.history.return_value = pd.DataFrame()
            elif symbol == "INR=X":
                t.history.return_value = usdinr_hist
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_prices(days=5)

        gold_inr = [r for r in records if r.symbol == "GOLD_INR"]
        assert len(gold_inr) == 1
        expected = round((2000.0 * 85.0) / 31.1035 * 10, 2)
        assert gold_inr[0].price == expected
        assert gold_inr[0].unit == "INR/10g"

    def test_nan_prices_skipped(self):
        gold_hist = _make_hist({"Close": [float("nan")]}, ["2026-03-20"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "GC=F":
                t.history.return_value = gold_hist
            else:
                t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_prices(days=5)

        gold_records = [r for r in records if r.symbol == "GOLD"]
        assert gold_records == []


class TestFetchMetals:
    """Test fetch_metals with mocked yfinance Ticker.history."""

    def test_basic_metals(self):
        ali_hist = _make_hist({"Close": [3600.0, 3610.0]}, ["2026-04-23", "2026-04-24"])
        hg_hist = _make_hist({"Close": [6.0, 6.05]}, ["2026-04-23", "2026-04-24"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "ALI=F":
                t.history.return_value = ali_hist
            elif symbol == "HG=F":
                t.history.return_value = hg_hist
            else:
                t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_metals(days=5)

        symbols = {r.symbol for r in records}
        assert "ALUMINIUM" in symbols
        assert "COPPER" in symbols

        alu = [r for r in records if r.symbol == "ALUMINIUM"]
        assert len(alu) == 2
        assert alu[0].unit == "USD/MT"
        assert alu[1].price == 3610.0

        cu = [r for r in records if r.symbol == "COPPER"]
        assert len(cu) == 2
        assert cu[0].unit == "USD/lb"
        assert cu[1].price == 6.05

    def test_empty_ticker_skipped(self):
        """A ticker returning empty DataFrame must be skipped without error."""
        ali_hist = _make_hist({"Close": [3600.0]}, ["2026-04-24"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "ALI=F":
                t.history.return_value = ali_hist
            else:
                t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_metals(days=5)

        symbols = {r.symbol for r in records}
        assert "ALUMINIUM" in symbols
        assert "COPPER" not in symbols

    def test_nan_prices_skipped(self):
        ali_hist = _make_hist(
            {"Close": [float("nan"), 3610.0]},
            ["2026-04-23", "2026-04-24"],
        )

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "ALI=F":
                t.history.return_value = ali_hist
            else:
                t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_metals(days=5)

        alu = [r for r in records if r.symbol == "ALUMINIUM"]
        assert len(alu) == 1
        assert alu[0].price == 3610.0

    def test_metals_history(self):
        ali_hist = _make_hist({"Close": [3500.0, 3600.0]}, ["2025-04-25", "2026-04-24"])

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "ALI=F":
                t.history.return_value = ali_hist
            else:
                t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.commodity_client.yf.Ticker", side_effect=mock_ticker):
            with CommodityClient() as client:
                records = client.fetch_metals_history(start="2025-04-25")

        alu = [r for r in records if r.symbol == "ALUMINIUM"]
        assert len(alu) == 2
        assert alu[0].date == "2025-04-25"
        assert alu[0].unit == "USD/MT"


class TestFetchEtfNavs:
    """Test fetch_etf_navs with respx mock for mfapi.in."""

    # All scheme codes in _ETF_SCHEMES — kept in sync with commodity_client.
    # Tests that target a single scheme mock the others as empty so respx
    # doesn't 503 on unmatched URLs.
    _ALL_SCHEME_CODES = (
        "105085", "115744", "140088", "106193", "111954",
        "113049", "113076", "149758",
    )

    def test_basic_nav_fetch(self):
        today = date.today().isoformat()
        mfapi_response = {
            "data": [
                {"date": "20-03-2026", "nav": "68.5"},
                {"date": "19-03-2026", "nav": "68.2"},
            ],
        }

        with respx.mock:
            for code in self._ALL_SCHEME_CODES:
                respx.get(url__regex=rf"api\.mfapi\.in/mf/{code}").respond(
                    200, json=mfapi_response,
                )

            with CommodityClient() as client:
                records = client.fetch_etf_navs(days=365)

        assert len(records) > 0
        # Each scheme gets 2 records — 8 schemes × 2 rows = 16
        assert len(records) == 16
        assert all(r.nav > 0 for r in records)

    def test_date_parsing(self):
        """mfapi returns DD-MM-YYYY, should be converted to YYYY-MM-DD."""
        mfapi_response = {
            "data": [{"date": "20-03-2026", "nav": "68.5"}],
        }

        with respx.mock:
            respx.get(url__regex=r"api\.mfapi\.in/mf/140088").respond(
                200, json=mfapi_response,
            )
            for code in self._ALL_SCHEME_CODES:
                if code == "140088":
                    continue
                respx.get(url__regex=rf"api\.mfapi\.in/mf/{code}").respond(
                    200, json={"data": []},
                )

            with CommodityClient() as client:
                records = client.fetch_etf_navs(days=365)

        gold_records = [r for r in records if r.scheme_code == "140088"]
        assert len(gold_records) == 1
        assert gold_records[0].date == "2026-03-20"

    def test_invalid_nav_skipped(self):
        mfapi_response = {
            "data": [{"date": "20-03-2026", "nav": "invalid"}],
        }

        with respx.mock:
            for code in self._ALL_SCHEME_CODES:
                respx.get(url__regex=rf"api\.mfapi\.in/mf/{code}").respond(
                    200, json=mfapi_response if code == "140088" else {"data": []},
                )

            with CommodityClient() as client:
                records = client.fetch_etf_navs(days=365)

        assert len(records) == 0

    def test_cutoff_date_filtering(self):
        """Records older than cutoff should be filtered."""
        old_date = (date.today() - timedelta(days=400)).strftime("%d-%m-%Y")
        mfapi_response = {
            "data": [{"date": old_date, "nav": "60.0"}],
        }

        with respx.mock:
            for code in ("105085", "115744", "140088", "106193", "111954",
                         "113049", "113076", "149758"):
                respx.get(url__regex=rf"api\.mfapi\.in/mf/{code}").respond(
                    200, json=mfapi_response if code == "140088" else {"data": []},
                )

            with CommodityClient() as client:
                records = client.fetch_etf_navs(days=365)

        assert len(records) == 0


class TestFetchEtfNavsSince:
    """Test fetch_etf_navs_since — date-anchored backfill, 2007→present."""

    def test_full_gold_bees_2007_to_2026_history(self):
        """Gold BeES (Benchmark MF, code 105085) launched 2007. The mock
        spans 2007-03-16 → 2026-05-26 and ``since='2007-03-08'`` (Gold
        BeES inception) must surface every row."""
        # mfapi returns newest-first; build oldest → newest then reverse.
        navs_oldest_first = [
            ("16-03-2007", "942.87"),
            ("01-01-2010", "1700.50"),
            ("22-08-2011", "2701.84"),
            ("01-06-2015", "2500.00"),
            ("07-11-2016", "2801.45"),
            ("01-01-2020", "3500.00"),
            ("25-05-2026", "130.29"),
        ]
        mfapi_response = {
            "data": [{"date": d, "nav": n} for d, n in reversed(navs_oldest_first)],
        }

        with respx.mock:
            # Gold BeES Benchmark scheme returns the full series; all
            # other schemes mocked empty so the test isolates one stream.
            respx.get(url__regex=r"api\.mfapi\.in/mf/105085").respond(
                200, json=mfapi_response,
            )
            for code in ("115744", "140088", "106193", "111954",
                         "113049", "113076", "149758"):
                respx.get(url__regex=rf"api\.mfapi\.in/mf/{code}").respond(
                    200, json={"data": []},
                )

            with CommodityClient() as client:
                records = client.fetch_etf_navs_since("2007-03-08")

        # All 7 rows must survive (oldest 2007-03-16 ≥ since 2007-03-08).
        assert len(records) == 7
        dates = sorted(r.date for r in records)
        assert dates[0] == "2007-03-16"
        assert dates[-1] == "2026-05-25"
        assert all(r.scheme_code == "105085" for r in records)

    def test_since_filters_earlier_rows(self):
        """Rows with date < since must be excluded; ≥ since must be kept."""
        mfapi_response = {
            "data": [
                {"date": "25-05-2026", "nav": "130.0"},
                {"date": "01-01-2020", "nav": "3500.0"},
                {"date": "16-03-2007", "nav": "942.0"},  # before since
            ],
        }

        with respx.mock:
            respx.get(url__regex=r"api\.mfapi\.in/mf/140088").respond(
                200, json=mfapi_response,
            )
            for code in ("105085", "115744", "106193", "111954",
                         "113049", "113076", "149758"):
                respx.get(url__regex=rf"api\.mfapi\.in/mf/{code}").respond(
                    200, json={"data": []},
                )

            with CommodityClient() as client:
                records = client.fetch_etf_navs_since("2019-01-01")

        # Only the 2026 and 2020 rows survive — 2007 row drops.
        assert len(records) == 2
        assert {r.date for r in records} == {"2026-05-25", "2020-01-01"}

    def test_all_gold_bees_schemes_present_in_scheme_map(self):
        """The three Gold BeES scheme codes (Benchmark/GS/Nippon) must
        be in `_ETF_SCHEMES` — these chain together to cover 2007→present
        because the ETF transferred between AMCs."""
        from flowtracker.commodity_client import _ETF_SCHEMES

        # Three Gold BeES codes covering 2007 → 2011, 2011 → 2016, 2016 → now
        assert "105085" in _ETF_SCHEMES  # Benchmark MF
        assert "115744" in _ETF_SCHEMES  # Goldman Sachs MF
        assert "140088" in _ETF_SCHEMES  # Nippon India MF
        # Triangulation gold ETFs
        for triangulation_code in ("106193", "111954", "113049", "113076"):
            assert triangulation_code in _ETF_SCHEMES
