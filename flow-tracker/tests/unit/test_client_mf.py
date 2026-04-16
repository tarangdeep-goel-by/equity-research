"""Tests for mf_client.py — AMFI monthly MF flow parsing."""

from __future__ import annotations

import io
from unittest.mock import patch

import openpyxl
import pytest
import respx

from flowtracker.mf_client import AMFIClient, AMFIFetchError
from flowtracker.mf_models import AMFIReportRow


class TestSafeFloat:
    """Test AMFIClient._safe_float static method."""

    def test_int_value(self):
        assert AMFIClient._safe_float(1000) == 1000.0

    def test_float_value(self):
        assert AMFIClient._safe_float(1234.56) == 1234.56

    def test_string_value(self):
        assert AMFIClient._safe_float("1234.56") == 1234.56

    def test_string_with_commas(self):
        assert AMFIClient._safe_float("1,234.56") == 1234.56

    def test_none_returns_none(self):
        assert AMFIClient._safe_float(None) is None

    def test_empty_returns_none(self):
        assert AMFIClient._safe_float("") is None

    def test_dash_returns_none(self):
        assert AMFIClient._safe_float("-") is None

    def test_garbage_returns_none(self):
        assert AMFIClient._safe_float("N/A") is None


class TestSafeInt:
    """Test AMFIClient._safe_int static method."""

    def test_int_value(self):
        assert AMFIClient._safe_int(42) == 42

    def test_float_value(self):
        assert AMFIClient._safe_int(42.7) == 42

    def test_string_value(self):
        assert AMFIClient._safe_int("42") == 42

    def test_string_with_commas(self):
        assert AMFIClient._safe_int("1,234") == 1234

    def test_none_returns_none(self):
        assert AMFIClient._safe_int(None) is None

    def test_empty_returns_none(self):
        assert AMFIClient._safe_int("") is None

    def test_dash_returns_none(self):
        assert AMFIClient._safe_int("-") is None


class TestDetectCategory:
    """Test AMFIClient._detect_category."""

    def test_roman_i_debt(self):
        client = AMFIClient()
        assert client._detect_category("I - Debt Schemes") == "Debt"
        client.close()

    def test_roman_ii_equity(self):
        client = AMFIClient()
        assert client._detect_category("II - Equity Schemes") == "Equity"
        client.close()

    def test_roman_iii_hybrid(self):
        client = AMFIClient()
        assert client._detect_category("III - Hybrid Schemes") == "Hybrid"
        client.close()

    def test_roman_iv_solution(self):
        client = AMFIClient()
        assert client._detect_category("IV - Solution Oriented") == "Solution"
        client.close()

    def test_roman_v_other(self):
        client = AMFIClient()
        assert client._detect_category("V - Other Schemes") == "Other"
        client.close()

    def test_roman_no_dash(self):
        client = AMFIClient()
        assert client._detect_category("II- Equity") == "Equity"
        client.close()

    def test_roman_with_dot(self):
        client = AMFIClient()
        assert client._detect_category("II.Equity") == "Equity"
        client.close()

    def test_standalone_roman(self):
        client = AMFIClient()
        assert client._detect_category("II") == "Equity"
        client.close()

    def test_non_category_returns_none(self):
        client = AMFIClient()
        assert client._detect_category("Large Cap Fund") is None
        client.close()


class TestProcessRow:
    """Test AMFIClient._process_row with fixture data."""

    def test_data_row(self):
        client = AMFIClient()
        row = ["1", "Large Cap Fund", 25, 50000, 8500.0, 7200.0, 1300.0, 125000.0]
        result = client._process_row(row, "Equity")
        assert result is not None
        assert not isinstance(result, str)
        assert result.category == "Equity"
        assert result.sub_category == "Large Cap Fund"
        assert result.num_schemes == 25
        assert result.funds_mobilized == 8500.0
        assert result.redemption == 7200.0
        assert result.net_flow == 1300.0
        assert result.aum == 125000.0
        client.close()

    def test_category_header_row(self):
        client = AMFIClient()
        row = ["II - Equity Schemes", "", "", "", "", "", "", ""]
        result = client._process_row(row, None)
        assert result == "Equity"
        client.close()

    def test_skip_header_row(self):
        client = AMFIClient()
        row = ["", "Scheme Name", "No. of Schemes", "", "", "", "", ""]
        result = client._process_row(row, "Equity")
        assert result is None
        client.close()

    def test_skip_grand_total(self):
        client = AMFIClient()
        row = ["", "Grand Total", "", "", 50000.0, 45000.0, 5000.0, 500000.0]
        result = client._process_row(row, "Equity")
        assert result is None
        client.close()

    def test_empty_row(self):
        client = AMFIClient()
        row = ["", "", "", "", "", "", "", ""]
        result = client._process_row(row, "Equity")
        assert result is None
        client.close()

    def test_short_row(self):
        client = AMFIClient()
        row = ["1", "Fund"]
        result = client._process_row(row, "Equity")
        assert result is None
        client.close()

    def test_no_current_category_skips(self):
        client = AMFIClient()
        row = ["1", "Large Cap Fund", 25, 50000, 8500.0, 7200.0, 1300.0, 125000.0]
        result = client._process_row(row, None)
        assert result is None
        client.close()

    def test_no_net_flow_skips(self):
        client = AMFIClient()
        row = ["1", "Some Fund", 25, 50000, 8500.0, 7200.0, None, 125000.0]
        result = client._process_row(row, "Equity")
        assert result is None
        client.close()


# --------------------------------------------------------------------------- #
# XLSX fixture helpers                                                         #
# --------------------------------------------------------------------------- #

def _build_amfi_xlsx() -> bytes:
    """Build an in-memory AMFI-style XLSX with two categories and a sub-total each.

    Layout mirrors the real AMFI monthly report:
        col 0 = Roman numeral (category header) OR serial,
        col 1 = scheme/sub-category name,
        col 2 = num schemes, 3 = folios, 4 = mobilized,
        col 5 = redemption, 6 = net flow, 7 = AUM.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["", "Scheme Name", "No. of Schemes", "Folios", "Funds Mobilized",
               "Redemption", "Net Flow", "AUM"])

    # Category I — Debt
    ws.append(["I - Debt Schemes", "", "", "", "", "", "", ""])
    ws.append(["1", "Liquid Fund", 40, 100000, 50000.0, 48000.0, 2000.0, 400000.0])
    ws.append(["2", "Money Market Fund", 20, 50000, 10000.0, 9000.0, 1000.0, 150000.0])
    ws.append(["", "Sub Total", 60, 150000, 60000.0, 57000.0, 3000.0, 550000.0])

    # Category II — Equity
    ws.append(["II - Equity Schemes", "", "", "", "", "", "", ""])
    ws.append(["1", "Large Cap Fund", 25, 80000, 8500.0, 7200.0, 1300.0, 125000.0])
    ws.append(["2", "Mid Cap Fund", 30, 90000, 6000.0, 4500.0, 1500.0, 90000.0])
    ws.append(["", "Sub Total", 55, 170000, 14500.0, 11700.0, 2800.0, 215000.0])

    # Metadata rows that should be skipped
    ws.append(["", "Grand Total", "", "", 74500.0, 68700.0, 5800.0, 765000.0])
    ws.append(["", "Note: figures in crores", "", "", "", "", "", ""])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_empty_xlsx() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["", "Scheme Name", "No.", "Folios", "Mob", "Red", "Net", "AUM"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# HTTP-path tests                                                              #
# --------------------------------------------------------------------------- #


class TestFetchMonthly:
    """End-to-end fetch + parse with respx."""

    def test_fetch_monthly_success(self):
        content = _build_amfi_xlsx()
        with respx.mock:
            respx.get(url__regex=r"portal\.amfiindia\.com").respond(
                200, content=content,
            )
            with AMFIClient() as client:
                rows, summary = client.fetch_monthly(2026, 3)

        # Should parse 4 data rows (2 liquid/money market + 2 equity) + 2 sub-totals = 6 rows
        assert len(rows) == 6
        debt_rows = [r for r in rows if r.category == "Debt"]
        equity_rows = [r for r in rows if r.category == "Equity"]
        assert len(debt_rows) == 3  # 2 data + 1 sub-total
        assert len(equity_rows) == 3

        # Summary prefers Sub Total rows
        assert summary.month == "2026-03"
        assert summary.equity_aum == 215000.0
        assert summary.debt_aum == 550000.0
        assert summary.equity_net_flow == 2800.0
        assert summary.debt_net_flow == 3000.0

    def test_empty_response_raises(self):
        content = _build_empty_xlsx()
        with respx.mock, patch("time.sleep"):
            respx.get(url__regex=r"portal\.amfiindia\.com").respond(
                200, content=content,
            )
            with AMFIClient() as client, pytest.raises(AMFIFetchError):
                client.fetch_monthly(2026, 3)

    def test_malformed_content_raises(self):
        # Not a valid xls or xlsx — xlrd should fail; retries kick in then raise.
        with respx.mock, patch("time.sleep"):
            respx.get(url__regex=r"portal\.amfiindia\.com").respond(
                200, content=b"not-a-spreadsheet",
            )
            with AMFIClient() as client, pytest.raises(AMFIFetchError):
                client.fetch_monthly(2026, 3)


class TestRetry:
    """Retry / backoff behaviour of fetch_monthly."""

    def test_retry_then_success(self):
        content = _build_amfi_xlsx()
        with respx.mock, patch("time.sleep") as mock_sleep:
            route = respx.get(url__regex=r"portal\.amfiindia\.com")
            route.side_effect = [
                httpx_response_500(),
                httpx_response_200(content),
            ]
            with AMFIClient() as client:
                rows, summary = client.fetch_monthly(2026, 3)

        assert len(rows) == 6
        assert summary.month == "2026-03"
        # Slept once between the two attempts.
        assert mock_sleep.call_count == 1

    def test_retry_exhausted_raises(self):
        with respx.mock, patch("time.sleep") as mock_sleep:
            respx.get(url__regex=r"portal\.amfiindia\.com").respond(500)
            with AMFIClient() as client, pytest.raises(AMFIFetchError):
                client.fetch_monthly(2026, 3)
        # Slept between attempts 1->2 and 2->3 but not after the final failure.
        assert mock_sleep.call_count == 2


class TestFetchRange:
    """fetch_range iterates months and tolerates skips."""

    def test_fetch_range_three_months(self):
        content = _build_amfi_xlsx()
        with respx.mock:
            respx.get(url__regex=r"portal\.amfiindia\.com").respond(
                200, content=content,
            )
            with AMFIClient() as client:
                results = client.fetch_range(2026, 1, 2026, 3)

        assert len(results) == 3
        # Each entry is (rows, summary)
        for rows, summary in results:
            assert len(rows) == 6
            assert summary.month.startswith("2026-")

    def test_fetch_range_skips_failures(self):
        # All months fail — fetch_range swallows AMFIFetchError and returns [].
        with respx.mock, patch("time.sleep"):
            respx.get(url__regex=r"portal\.amfiindia\.com").respond(500)
            with AMFIClient() as client:
                results = client.fetch_range(2026, 1, 2026, 2)

        assert results == []


# --------------------------------------------------------------------------- #
# _parse_report + _build_summary direct tests                                  #
# --------------------------------------------------------------------------- #


class TestParseReport:
    """Direct tests for _parse_report dispatcher."""

    def test_parse_xlsx_hierarchical(self):
        content = _build_amfi_xlsx()
        with AMFIClient() as client:
            rows = client._parse_report(content, "2026-03")

        categories = {r.category for r in rows}
        assert categories == {"Debt", "Equity"}
        # Sub categories should include the named funds, no Grand Total/Note.
        sub_names = {r.sub_category for r in rows}
        assert "Large Cap Fund" in sub_names
        assert "Liquid Fund" in sub_names
        assert "Grand Total" not in sub_names
        assert not any("Note" in s for s in sub_names)

    def test_parse_empty_xlsx(self):
        content = _build_empty_xlsx()
        with AMFIClient() as client:
            rows = client._parse_report(content, "2026-03")
        assert rows == []


class TestBuildSummary:
    """_build_summary aggregation logic."""

    def test_prefers_sub_total_rows(self):
        rows = [
            AMFIReportRow(category="Equity", sub_category="Large Cap Fund",
                          num_schemes=25, funds_mobilized=8500.0,
                          redemption=7200.0, net_flow=1300.0, aum=125000.0),
            AMFIReportRow(category="Equity", sub_category="Mid Cap Fund",
                          num_schemes=30, funds_mobilized=6000.0,
                          redemption=4500.0, net_flow=1500.0, aum=90000.0),
            AMFIReportRow(category="Equity", sub_category="Sub Total",
                          num_schemes=55, funds_mobilized=14500.0,
                          redemption=11700.0, net_flow=2800.0, aum=215000.0),
            AMFIReportRow(category="Debt", sub_category="Liquid Fund",
                          num_schemes=40, funds_mobilized=50000.0,
                          redemption=48000.0, net_flow=2000.0, aum=400000.0),
            AMFIReportRow(category="Debt", sub_category="Sub Total",
                          num_schemes=40, funds_mobilized=50000.0,
                          redemption=48000.0, net_flow=2000.0, aum=400000.0),
        ]
        with AMFIClient() as client:
            summary = client._build_summary(rows, "2026-03")

        # Should use sub-total rows only, not double-count.
        assert summary.month == "2026-03"
        assert summary.equity_aum == 215000.0
        assert summary.debt_aum == 400000.0
        assert summary.equity_net_flow == 2800.0
        assert summary.debt_net_flow == 2000.0
        assert summary.total_aum == 615000.0
        assert summary.hybrid_aum == 0
        assert summary.other_aum == 0

    def test_fallback_to_all_rows_when_no_subtotal(self):
        rows = [
            AMFIReportRow(category="Hybrid", sub_category="Aggressive Hybrid",
                          num_schemes=10, funds_mobilized=1000.0,
                          redemption=800.0, net_flow=200.0, aum=50000.0),
            AMFIReportRow(category="Hybrid", sub_category="Conservative Hybrid",
                          num_schemes=8, funds_mobilized=500.0,
                          redemption=400.0, net_flow=100.0, aum=20000.0),
        ]
        with AMFIClient() as client:
            summary = client._build_summary(rows, "2026-04")

        assert summary.hybrid_aum == 70000.0
        assert summary.hybrid_net_flow == 300.0


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def httpx_response_500():
    import httpx
    return httpx.Response(500, text="server error")


def httpx_response_200(content: bytes):
    import httpx
    return httpx.Response(200, content=content)
