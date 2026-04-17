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


class TestSnapshotGsecCarryForward:
    """fetch_snapshot must carry today's gsec forward to all prior days in window."""

    def test_gsec_populated_for_all_days(self):
        """With a successful CCIL scrape, every snapshot day gets the same gsec value."""
        dates = ["2026-04-14", "2026-04-15", "2026-04-16"]
        vix_hist = _make_hist([14.1, 14.2, 14.3], dates)
        usdinr_hist = _make_hist([85.0, 85.1, 85.2], dates)
        brent_hist = _make_hist([72.0, 72.5, 73.0], dates)

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "^INDIAVIX":
                t.history.return_value = vix_hist
            elif symbol == "USDINR=X":
                t.history.return_value = usdinr_hist
            elif symbol == "BZ=F":
                t.history.return_value = brent_hist
            return t

        html = "<tr><td>9Y-10Y</td><td>6.48</td></tr>"
        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with respx.mock:
                respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
                with MacroClient() as client:
                    snapshots = client.fetch_snapshot(days=5)

        assert len(snapshots) == 3
        # Every snapshot should have the scraped gsec value, not just today
        for s in snapshots:
            assert s.gsec_10y == 6.48, f"{s.date} missing gsec carry-forward"

    def test_gsec_none_when_scrape_fails(self):
        """If CCIL scrape fails, all snapshots have gsec_10y=None (no fabrication)."""
        dates = ["2026-04-15", "2026-04-16"]
        vix_hist = _make_hist([14.1, 14.2], dates)
        usdinr_hist = _make_hist([85.0, 85.1], dates)
        brent_hist = _make_hist([72.0, 72.5], dates)

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
                respx.get(url__regex=r"ccilindia\.com").respond(500)
                with MacroClient() as client:
                    snapshots = client.fetch_snapshot(days=5)

        assert len(snapshots) == 2
        for s in snapshots:
            assert s.gsec_10y is None


class TestFetchHistoryGsec:
    """fetch_history should assign today's gsec to the most-recent row only."""

    def test_gsec_on_latest_row_only(self):
        dates = ["2024-01-02", "2024-01-03", "2026-04-16"]
        vix_hist = _make_hist([14.0, 14.1, 14.3], dates)
        usdinr_hist = _make_hist([83.0, 83.1, 85.2], dates)
        brent_hist = _make_hist([70.0, 70.5, 73.0], dates)

        def mock_ticker(symbol):
            t = MagicMock()
            if symbol == "^INDIAVIX":
                t.history.return_value = vix_hist
            elif symbol == "USDINR=X":
                t.history.return_value = usdinr_hist
            elif symbol == "BZ=F":
                t.history.return_value = brent_hist
            return t

        html = "<tr><td>9Y-10Y</td><td>6.48</td></tr>"
        with patch("flowtracker.macro_client.yf.Ticker", side_effect=mock_ticker):
            with respx.mock:
                respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
                with MacroClient() as client:
                    snapshots = client.fetch_history(start="2024-01-01")

        assert len(snapshots) == 3
        # Only the latest row has gsec; historical rows left None
        assert snapshots[-1].gsec_10y == 6.48
        assert snapshots[0].gsec_10y is None
        assert snapshots[1].gsec_10y is None
