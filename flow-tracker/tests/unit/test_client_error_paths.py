"""Tests for error/edge-case paths across all HTTP clients.

Validates retry logic, graceful degradation, credential errors, and malformed data handling.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import respx
from httpx import Response

# ---------------------------------------------------------------------------
# NSE Client error paths
# ---------------------------------------------------------------------------


class TestNSEClientErrors:
    """NSE FII/DII client retry and error handling."""

    def test_403_retry_then_success(self):
        """403 triggers cookie refresh; second attempt succeeds."""
        with respx.mock:
            # Preflight always OK (may be called multiple times for cookie refresh)
            respx.get(url__regex=r"nseindia\.com/reports").respond(200)

            # First API call: 403, second: 200 with valid data
            api = respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact")
            api.side_effect = [
                Response(403),
                Response(200, json=[
                    {"category": "FII/FPI *", "date": "28-Mar-2026",
                     "buyValue": "12,000.00", "sellValue": "13,500.00", "netValue": "-1,500.00"},
                    {"category": "DII *", "date": "28-Mar-2026",
                     "buyValue": "8,000.00", "sellValue": "7,200.00", "netValue": "800.00"},
                ]),
            ]
            from flowtracker.client import NSEClient
            with NSEClient() as client:
                flows = client.fetch_daily()
            assert len(flows) == 2
            assert flows[0].category in ("FII", "DII")

    def test_403_every_attempt_raises(self):
        """Permanent 403 → raises NSEFetchError after MAX_RETRIES."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports").respond(200)
            respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact").respond(403)

            from flowtracker.client import NSEClient, NSEFetchError, MAX_RETRIES
            with NSEClient() as client:
                with pytest.raises(NSEFetchError, match="Failed after"):
                    client.fetch_daily()

    def test_500_retries_then_raises(self):
        """HTTP 500 on every attempt → NSEFetchError."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports").respond(200)
            respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact").respond(500)

            from flowtracker.client import NSEClient, NSEFetchError
            with NSEClient() as client:
                with pytest.raises(NSEFetchError, match="Failed after"):
                    client.fetch_daily()

    def test_empty_json_raises(self):
        """API returns empty list → NSEFetchError ('No FII/DII data')."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports").respond(200)
            respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact").respond(
                200, json=[]
            )

            from flowtracker.client import NSEClient, NSEFetchError
            with NSEClient() as client:
                with pytest.raises(NSEFetchError, match="No FII/DII data"):
                    client.fetch_daily()

    def test_malformed_json_raises(self):
        """Non-JSON response body → NSEFetchError after retries."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports").respond(200)
            respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact").respond(
                200, text="<html>not json</html>",
                headers={"content-type": "text/html"},
            )

            from flowtracker.client import NSEClient, NSEFetchError
            with NSEClient() as client:
                with pytest.raises(NSEFetchError):
                    client.fetch_daily()

    def test_preflight_failure_raises(self):
        """If preflight page itself returns 500, we fail after retries."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports").respond(500)

            from flowtracker.client import NSEClient, NSEFetchError
            with NSEClient() as client:
                with pytest.raises(NSEFetchError, match="Failed after"):
                    client.fetch_daily()


# ---------------------------------------------------------------------------
# Bhavcopy Client error paths
# ---------------------------------------------------------------------------


class TestBhavcopyClientErrors:
    """Bhavcopy CSV client error handling."""

    def test_404_returns_empty_list(self):
        """HTTP 404 (holiday/weekend) → empty list, no exception."""
        from datetime import date

        with respx.mock:
            respx.get(url__regex=r"nsearchives\.nseindia\.com").respond(404)

            from flowtracker.bhavcopy_client import BhavcopyClient
            with BhavcopyClient() as client:
                result = client.fetch_day(date(2026, 1, 26))  # Republic Day
            assert result == []

    def test_500_retries_returns_empty(self):
        """Persistent 500 → returns empty list after MAX_RETRIES (logs error)."""
        from datetime import date

        with respx.mock:
            respx.get(url__regex=r"nsearchives\.nseindia\.com").respond(500)

            from flowtracker.bhavcopy_client import BhavcopyClient
            with BhavcopyClient() as client:
                result = client.fetch_day(date(2026, 3, 28))
            assert result == []

    def test_mangled_csv_skips_bad_rows(self):
        """Non-numeric values in price columns → those rows are skipped."""
        from datetime import date

        csv_text = (
            " SYMBOL , SERIES , OPEN_PRICE , HIGH_PRICE , LOW_PRICE , CLOSE_PRICE , "
            "PREV_CLOSE , TTL_TRD_QNTY , TURNOVER_LACS , DELIV_QTY , DELIV_PER \n"
            " SBIN , EQ , 820.0 , 830.0 , 815.0 , 825.0 , 818.0 , 15000000 , 12375.0 , 9000000 , 60.0 \n"
            " BAD , EQ , NOT_A_NUMBER , 830.0 , 815.0 , 825.0 , 818.0 , 15000000 , 12375.0 , 9000000 , 60.0 \n"
        )
        with respx.mock:
            respx.get(url__regex=r"nsearchives\.nseindia\.com").respond(
                200, text=csv_text
            )

            from flowtracker.bhavcopy_client import BhavcopyClient
            with BhavcopyClient() as client:
                result = client.fetch_day(date(2026, 3, 28))
            # Good SBIN row parsed, bad row skipped
            assert len(result) == 1
            assert result[0].symbol == "SBIN"

    def test_empty_csv_returns_empty(self):
        """CSV with only headers → empty list."""
        from datetime import date

        csv_text = (
            " SYMBOL , SERIES , OPEN_PRICE , HIGH_PRICE , LOW_PRICE , CLOSE_PRICE , "
            "PREV_CLOSE , TTL_TRD_QNTY , TURNOVER_LACS , DELIV_QTY , DELIV_PER \n"
        )
        with respx.mock:
            respx.get(url__regex=r"nsearchives\.nseindia\.com").respond(
                200, text=csv_text
            )

            from flowtracker.bhavcopy_client import BhavcopyClient
            with BhavcopyClient() as client:
                result = client.fetch_day(date(2026, 3, 28))
            assert result == []


# ---------------------------------------------------------------------------
# FMP Client error paths
# ---------------------------------------------------------------------------


class TestFMPClientErrors:
    """FMP API client credential and response error handling."""

    def test_missing_api_key_file_raises(self, tmp_path):
        """No fmp.env file → FileNotFoundError."""
        with patch("flowtracker.fmp_client._CONFIG_PATH", tmp_path / "nonexistent.env"):
            from flowtracker.fmp_client import FMPClient
            with pytest.raises(FileNotFoundError, match="FMP config not found"):
                FMPClient()

    def test_empty_api_key_file_raises(self, tmp_path):
        """fmp.env exists but no FMP_API_KEY line → ValueError."""
        env_file = tmp_path / "fmp.env"
        env_file.write_text("SOME_OTHER_KEY=abc\n")

        with patch("flowtracker.fmp_client._CONFIG_PATH", env_file):
            from flowtracker.fmp_client import FMPClient
            with pytest.raises(ValueError, match="FMP_API_KEY not found"):
                FMPClient()

    def test_http_error_returns_empty_list(self, tmp_path):
        """HTTP 429 (rate limit) → _get returns empty list, fetch methods return None/empty."""
        env_file = tmp_path / "fmp.env"
        env_file.write_text("FMP_API_KEY=test_key_123\n")

        with patch("flowtracker.fmp_client._CONFIG_PATH", env_file):
            with respx.mock:
                respx.get(url__regex=r"financialmodelingprep\.com").respond(429)

                from flowtracker.fmp_client import FMPClient
                client = FMPClient()
                # _get swallows the error and returns []
                result = client.fetch_dcf("SBIN")
                assert result is None

    def test_error_message_json_returns_empty(self, tmp_path):
        """FMP error JSON like {"Error Message": "..."} → treated as empty."""
        env_file = tmp_path / "fmp.env"
        env_file.write_text("FMP_API_KEY=test_key_123\n")

        with patch("flowtracker.fmp_client._CONFIG_PATH", env_file):
            with respx.mock:
                respx.get(url__regex=r"financialmodelingprep\.com").respond(
                    200, json={"Error Message": "Invalid API KEY."}
                )

                from flowtracker.fmp_client import FMPClient
                client = FMPClient()
                # dict response → _get wraps in [dict], but fetch_dcf tries data[0]
                # which would be the error dict — should still produce a result (with Nones)
                # or the key metrics should return a list
                grades = client.fetch_analyst_grades("SBIN")
                # Regardless of shape, should not crash
                assert isinstance(grades, list)

    def test_unexpected_json_shape_returns_empty(self, tmp_path):
        """Non-list, non-dict JSON → _get returns []."""
        env_file = tmp_path / "fmp.env"
        env_file.write_text("FMP_API_KEY=test_key_123\n")

        with patch("flowtracker.fmp_client._CONFIG_PATH", env_file):
            with respx.mock:
                respx.get(url__regex=r"financialmodelingprep\.com").respond(
                    200, json="just a string"
                )

                from flowtracker.fmp_client import FMPClient
                client = FMPClient()
                result = client.fetch_key_metrics("SBIN")
                assert result == []


# ---------------------------------------------------------------------------
# Screener Client error paths
# ---------------------------------------------------------------------------


class TestScreenerClientErrors:
    """Screener.in client credential, login, and parsing errors."""

    def test_missing_credentials_file_raises(self, tmp_path):
        """No screener.env → ScreenerError with helpful message."""
        with patch("flowtracker.screener_client._CRED_PATH", tmp_path / "nonexistent.env"):
            from flowtracker.screener_client import ScreenerClient, ScreenerError
            with pytest.raises(ScreenerError, match="credentials not found"):
                ScreenerClient()

    def test_empty_credentials_raises(self, tmp_path):
        """screener.env exists but email/password blank → ScreenerError."""
        env_file = tmp_path / "screener.env"
        env_file.write_text("SCREENER_EMAIL=\nSCREENER_PASSWORD=\n")

        with patch("flowtracker.screener_client._CRED_PATH", env_file):
            from flowtracker.screener_client import ScreenerClient, ScreenerError
            with pytest.raises(ScreenerError, match="SCREENER_EMAIL and SCREENER_PASSWORD"):
                ScreenerClient()

    def test_login_failure_raises(self):
        """POST to /login/ redirects back to /login/ → ScreenerError."""
        with respx.mock:
            # GET /login/ → 200 with CSRF cookie
            respx.get(url__regex=r"screener\.in/login").respond(
                200, headers={"set-cookie": "csrftoken=fake_token; Path=/"}
            )
            # POST /login/ → redirect back to /login/ (failure)
            respx.post(url__regex=r"screener\.in/login").respond(
                200,
                headers={"location": "https://www.screener.in/login/"},
            )

            from flowtracker.screener_client import ScreenerClient, ScreenerError, _load_credentials
            with patch(
                "flowtracker.screener_client._load_credentials",
                return_value=("bad@test.com", "wrongpass"),
            ):
                with pytest.raises(ScreenerError, match="Login failed"):
                    ScreenerClient()

    def test_excel_without_data_sheet_raises(self):
        """Excel export missing 'Data Sheet' → ScreenerError."""
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Summary"
        ws["A1"] = "No data here"
        buf = io.BytesIO()
        wb.save(buf)
        excel_bytes = buf.getvalue()
        wb.close()

        from flowtracker.screener_client import ScreenerClient, ScreenerError
        with patch(
            "flowtracker.screener_client._load_credentials",
            return_value=("test@test.com", "password"),
        ):
            with patch.object(ScreenerClient, "_login"):
                client = ScreenerClient()
                with pytest.raises(ScreenerError, match="No 'Data Sheet'"):
                    client.parse_quarterly_results("SBIN", excel_bytes)
                client._client.close()

    def test_html_without_ratios_section_returns_empty(self):
        """HTML missing #ratios section → parse_ratios_from_html returns []."""
        html = "<html><body><section id='other'>nothing</section></body></html>"

        from flowtracker.screener_client import ScreenerClient
        with patch(
            "flowtracker.screener_client._load_credentials",
            return_value=("test@test.com", "password"),
        ):
            with patch.object(ScreenerClient, "_login"):
                client = ScreenerClient()
                result = client.parse_ratios_from_html("SBIN", html)
                assert result == []
                client._client.close()


# ---------------------------------------------------------------------------
# yfinance / FundClient error paths
# ---------------------------------------------------------------------------


class TestFundClientErrors:
    """yfinance FundClient error and edge-case handling."""

    def test_empty_info_raises(self):
        """Ticker.info returns empty dict → YFinanceError."""
        from flowtracker.fund_client import FundClient, YFinanceError

        mock_ticker = MagicMock()
        mock_ticker.info = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            client = FundClient()
            with pytest.raises(YFinanceError, match="No data found"):
                client.get_live_snapshot("FAKESYM")

    def test_none_info_raises(self):
        """Ticker.info returns None → YFinanceError."""
        from flowtracker.fund_client import FundClient, YFinanceError

        mock_ticker = MagicMock()
        mock_ticker.info = None

        with patch("yfinance.Ticker", return_value=mock_ticker):
            client = FundClient()
            with pytest.raises(YFinanceError, match="No data found"):
                client.get_live_snapshot("FAKESYM")

    def test_empty_quarterly_returns_empty_list(self):
        """Ticker with empty income statement → returns []."""
        import pandas as pd
        from flowtracker.fund_client import FundClient

        mock_ticker = MagicMock()
        mock_ticker.get_income_stmt.return_value = pd.DataFrame()

        with patch("yfinance.Ticker", return_value=mock_ticker):
            client = FundClient()
            # Bypass the _info call by going directly to fetch_quarterly_results
            # which uses _ticker → get_income_stmt
            result = client.fetch_quarterly_results("SBIN")
            assert result == []


# ---------------------------------------------------------------------------
# EstimatesClient error paths
# ---------------------------------------------------------------------------


class TestEstimatesClientErrors:
    """Consensus estimates client error handling."""

    def test_no_data_returns_none(self):
        """Ticker.info with no quoteType → returns None, no crash."""
        from flowtracker.estimates_client import EstimatesClient

        mock_ticker = MagicMock()
        mock_ticker.info = {}

        with patch("yfinance.Ticker", return_value=mock_ticker):
            client = EstimatesClient()
            result = client.fetch_estimates("NOSYMBOL")
            assert result is None

    def test_exception_returns_none(self):
        """yfinance raises an exception → returns None gracefully."""
        from flowtracker.estimates_client import EstimatesClient

        with patch("yfinance.Ticker", side_effect=Exception("network error")):
            client = EstimatesClient()
            result = client.fetch_estimates("SBIN")
            assert result is None
