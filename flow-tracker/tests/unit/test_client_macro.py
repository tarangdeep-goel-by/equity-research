"""Tests for macro_client.py — VIX, USD/INR, Brent, G-sec yield."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import respx

from flowtracker.macro_client import MacroClient


def _make_hist(closes: list[float], dates: list[str]) -> pd.DataFrame:
    idx = pd.to_datetime(dates)
    return pd.DataFrame({"Close": closes}, index=idx)


class TestFetchSnapshot:
    """Test fetch_snapshot with mocked yfinance + CCIL."""

    def test_basic_snapshot(self):
        vix_hist = _make_hist([14.5], ["2026-03-20"])
        usdinr_hist = _make_hist([85.23], ["2026-03-20"])
        brent_hist = _make_hist([72.50], ["2026-03-20"])

        call_count = {"n": 0}

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "^INDIAVIX":
                t.history.return_value = vix_hist
            elif symbol == "USDINR=X":
                t.history.return_value = usdinr_hist
            elif symbol == "BZ=F":
                t.history.return_value = brent_hist
            return t

        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with respx.mock:
                respx.get(url__regex=r"ccilindia\.com").respond(200, text="<html></html>")
                with MacroClient() as client:
                    snapshots = client.fetch_snapshot(days=5)

        assert len(snapshots) == 1
        s = snapshots[0]
        assert s.date == "2026-03-20"
        assert s.india_vix == 14.5
        assert s.usd_inr == 85.23
        assert s.brent_crude == 72.5

    def test_empty_histories(self):
        def mock_ticker(symbol):
            t = MagicMock()
            t.history.return_value = pd.DataFrame()
            return t

        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with respx.mock:
                respx.get(url__regex=r"ccilindia\.com").respond(200, text="<html></html>")
                with MacroClient() as client:
                    snapshots = client.fetch_snapshot(days=5)

        assert snapshots == []


class TestFetchGsecYield:
    """Test _fetch_gsec_yield with HTML scraping."""

    def test_parses_yield(self):
        html = """
        <table>
        <tr><td>8Y-9Y</td><td>6.85</td></tr>
        <tr><td>9Y-10Y</td><td>7.12</td></tr>
        <tr><td>10Y-15Y</td><td>7.25</td></tr>
        </table>
        """
        with respx.mock:
            respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
            with MacroClient() as client:
                result = client._fetch_gsec_yield()

        assert result == 7.12

    def test_no_match_returns_none(self):
        html = "<html><body>No yield data here</body></html>"
        with respx.mock:
            respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
            with MacroClient() as client:
                result = client._fetch_gsec_yield()

        assert result is None

    def test_fetch_failure_returns_none(self):
        with respx.mock:
            respx.get(url__regex=r"ccilindia\.com").respond(500)
            with MacroClient() as client:
                result = client._fetch_gsec_yield()

        assert result is None

    def test_dash_separator(self):
        """Test with en-dash separator between tenor range."""
        html = "<tr><td>9 Y \u2013 10 Y</td><td>7.15</td></tr>"
        with respx.mock:
            respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
            with MacroClient() as client:
                result = client._fetch_gsec_yield()

        assert result == 7.15
