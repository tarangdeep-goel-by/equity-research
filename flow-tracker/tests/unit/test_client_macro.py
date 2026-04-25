"""Tests for macro_client.py — VIX, USD/INR, Brent, G-sec yield, RBI WSS."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import respx

from flowtracker.macro_client import MacroClient
from flowtracker.macro_models import MacroSystemCredit


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

    def test_skips_security_coupon_uses_ytm_column(self):
        """CCIL 4-column layout: tenor | security | (extra) | YTM.

        The Security cell contains a coupon like '6.33% GS 2035' \u2014 the parser
        must not return that coupon as the yield. It must return the YTM cell.
        Regression test for the gsec_10y NULL-since-2026-04-18 bug where the
        previous regex matched the security coupon (6.33) instead of the
        actual YTM (6.8537).
        """
        html = """
        <table>
        <thead><tr><th>Date</th><th>Tenor Bucket</th><th>Security</th><th>YTM (%)</th></tr></thead>
        <tbody>
        <tr><td>2026-04-24</td><td>4Y-5Y</td><td>6.36% GS 2031</td><td>6.7025</td></tr>
        <tr><td>2026-04-24</td><td>9Y-10Y</td><td>6.33% GS 2035</td><td>6.8537</td></tr>
        <tr><td>2026-04-24</td><td>13Y-15Y</td><td>6.68% GS 2040</td><td>7.2962</td></tr>
        </tbody>
        </table>
        """
        with respx.mock:
            respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
            with MacroClient() as client:
                result = client._fetch_gsec_yield()

        assert result == 6.85, f"expected YTM 6.85, got {result} (probably coupon)"

    def test_implausible_value_returns_none(self):
        """If the parsed value is outside the plausible 10Y yield range
        (3%-12%), return None and log error rather than persist garbage."""
        html = """
        <table>
        <tr><td>9Y-10Y</td><td>foo</td><td>0.5</td></tr>
        </table>
        """
        with respx.mock:
            respx.get(url__regex=r"ccilindia\.com").respond(200, text=html)
            with MacroClient() as client:
                result = client._fetch_gsec_yield()

        assert result is None


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


# WSS HTML fixture mimicking the post-tag-strip / whitespace-collapse output of
# the real BS_viewWssExtract.aspx page. We embed the labels and numeric layout
# directly so the parser exercises the same regex paths.
_FAKE_WSS_INDEX_HTML = '''
<html><body>
<a href="javascript:..(SelectedDate=4/24/2026..)">Apr 24, 2026</a>
<a href="javascript:..(SelectedDate=4/17/2026..)">Apr 17, 2026</a>
</body></html>
'''

_FAKE_WSS_DETAIL_HTML = '''
<html><body>
<table>
<tr><td>4. Scheduled Commercial Banks - Business in India (₹ Crore)</td></tr>
<tr><td>Item Outstanding as on Apr. 15, 2026 Variation over Fortnight Financial year so far Year-on-Year 2025-26 2026-27 2025 2026</td></tr>
<tr><td>1 2 3 4 5 6</td></tr>
<tr><td>2 Liabilities to Others</td></tr>
<tr><td>2.1 Aggregate Deposits 25648470 -581447 280265 -581447 2107472 2787604</td></tr>
<tr><td>2.1a Growth (Per cent) -2.2 1.2 -2.2 10.2 12.2</td></tr>
<tr><td>2.1.1 Demand 3220633 -467496 -59486 -467496 176617 582070</td></tr>
<tr><td>2.1.2 Time 22427836 -113951 339750 -113951 1930855 2205534</td></tr>
<tr><td>2.2 Borrowings 892979 84770 -46643 84770 93267 24374</td></tr>
<tr><td>2.3 Other Demand and Time Liabilities 1061704 -66349 -61666 -66349 102718 61738</td></tr>
<tr><td>7 Bank Credit 20921084 -438864 -56081 -438864 1696095 2733192</td></tr>
<tr><td>7.1a Growth (Per cent) -2.1 -0.3 -2.1 10.3 15.0</td></tr>
<tr><td>7a.1 Food Credit 68489 -17 -1782 -17 13439 -1782</td></tr>
<tr><td>7a.2 Non-food credit 20852595 -438847 -54299 -438847 1682656 2734974</td></tr>
<tr><td>Note: Data include the impact of merger of a non-bank with a bank w.e.f. July 1, 2023.</td></tr>
<tr><td>6. Money Stock: Components and Sources (₹ Crore)</td></tr>
<tr><td>M3 31465906 30927112 -538794 -1.7 344097 1.3 -538794 -1.7 2370729 9.4 3296425 11.9</td></tr>
<tr><td>1 Components</td></tr>
<tr><td>1.1 Currency with the Public 4067578 4142452 74874 1.8 63002 1.7 74874 1.8 239499 6.9 448699 12.1</td></tr>
</table>
</body></html>
'''


class TestFetchRbiWss:
    """Test _fetch_rbi_wss against synthetic but layout-faithful HTML."""

    def test_happy_path_extracts_credit_deposit_growth(self):
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract\.aspx$").respond(
                200, text=_FAKE_WSS_INDEX_HTML,
            )
            respx.get(url__regex=r"BS_viewWssExtract\.aspx\?SelectedDate=4/24/2026").respond(
                200, text=_FAKE_WSS_DETAIL_HTML,
            )
            with MacroClient() as client:
                result = client._fetch_rbi_wss()

        assert result is not None
        assert isinstance(result, MacroSystemCredit)
        assert result.release_date == "2026-04-24"
        assert result.as_of_date == "2026-04-15"
        # Outstandings (₹ Cr)
        assert result.aggregate_deposits_cr == 25648470.0
        assert result.bank_credit_cr == 20921084.0
        # YoY growth — last value on Growth (Per cent) line
        assert result.deposit_growth_yoy == 12.2
        assert result.credit_growth_yoy == 15.0
        # Non-food credit: derived from variation / prev_year_out
        # nums = [20852595, -438847, -54299, -438847, 1682656, 2734974]
        # prev = 20852595 - 2734974 = 18117621; growth = 2734974/18117621*100 = 15.097..
        assert result.non_food_credit_growth_yoy == 15.1
        # CD ratio = 20921084 / 25648470 * 100 = 81.57%
        assert result.cd_ratio == 81.57
        # M3 row last value is YoY current-year %
        assert result.m3_growth_yoy == 11.9
        assert result.source == "RBI_WSS"

    def test_explicit_selected_date_skips_index(self):
        with respx.mock:
            # Index call should NOT be made when selected_date passed
            respx.get(url__regex=r"BS_viewWssExtract\.aspx\?SelectedDate=4/17/2026").respond(
                200, text=_FAKE_WSS_DETAIL_HTML,
            )
            with MacroClient() as client:
                result = client._fetch_rbi_wss(selected_date="4/17/2026")

        assert result is not None
        assert result.release_date == "2026-04-17"

    def test_empty_html_returns_none(self):
        empty_html = "<html><body>No WSS data</body></html>"
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract\.aspx$").respond(
                200, text=_FAKE_WSS_INDEX_HTML,
            )
            respx.get(url__regex=r"SelectedDate=4/24/2026").respond(200, text=empty_html)
            with MacroClient() as client:
                result = client._fetch_rbi_wss()

        assert result is None

    def test_http_failure_returns_none(self):
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract").respond(500)
            with MacroClient() as client:
                result = client._fetch_rbi_wss()

        assert result is None

    def test_no_release_dates_on_index_returns_none(self):
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract\.aspx$").respond(
                200, text="<html><body>No links here</body></html>",
            )
            with MacroClient() as client:
                result = client._fetch_rbi_wss()

        assert result is None

    def test_implausible_growth_dropped(self):
        """Growth > 30% (e.g. parser confusion) returns None for that field
        rather than persisting garbage. Other fields can still populate.
        """
        # Inject an impossible 99.9 deposit growth, plausible credit
        bad_html = _FAKE_WSS_DETAIL_HTML.replace(
            "2.1a Growth (Per cent) -2.2 1.2 -2.2 10.2 12.2",
            "2.1a Growth (Per cent) -2.2 1.2 -2.2 10.2 99.9",
        )
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract\.aspx$").respond(
                200, text=_FAKE_WSS_INDEX_HTML,
            )
            respx.get(url__regex=r"SelectedDate=4/24/2026").respond(200, text=bad_html)
            with MacroClient() as client:
                result = client._fetch_rbi_wss()

        assert result is not None
        # Bad value was dropped, not persisted
        assert result.deposit_growth_yoy is None
        # Other fields still populated
        assert result.credit_growth_yoy == 15.0

    def test_implausible_cd_ratio_dropped(self):
        """If outstandings produce an out-of-range CD ratio, drop it."""
        # Make credit much larger than deposits (CD ratio > 95)
        bad_html = _FAKE_WSS_DETAIL_HTML.replace(
            "7 Bank Credit 20921084",
            "7 Bank Credit 99000000",
        )
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract\.aspx$").respond(
                200, text=_FAKE_WSS_INDEX_HTML,
            )
            respx.get(url__regex=r"SelectedDate=4/24/2026").respond(200, text=bad_html)
            with MacroClient() as client:
                result = client._fetch_rbi_wss()

        assert result is not None
        # CD ratio dropped (99M/25.6M = 386% — out of [60, 95])
        assert result.cd_ratio is None

    def test_fetch_system_credit_public_wrapper(self):
        with respx.mock:
            respx.get(url__regex=r"BS_viewWssExtract\.aspx$").respond(
                200, text=_FAKE_WSS_INDEX_HTML,
            )
            respx.get(url__regex=r"SelectedDate=4/24/2026").respond(
                200, text=_FAKE_WSS_DETAIL_HTML,
            )
            with MacroClient() as client:
                result = client.fetch_system_credit()

        assert result is not None
        assert result.release_date == "2026-04-24"
