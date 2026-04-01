"""Tests for screener_client.py — Screener.in HTML + Excel parsing functions.

Uses golden fixture files (real SBIN data) for realistic parsing validation.
Constructor is mocked to avoid network login.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from flowtracker.fund_models import AnnualEPS, AnnualFinancials, QuarterlyResult, ScreenerRatios
from flowtracker.screener_client import ScreenerClient, ScreenerError, _parse_screener_date


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def screener_client():
    """ScreenerClient with login mocked out."""
    with patch(
        "flowtracker.screener_client._load_credentials",
        return_value=("test@test.com", "password"),
    ):
        with patch.object(ScreenerClient, "_login"):
            client = ScreenerClient()
            yield client
            client._client.close()


@pytest.fixture
def golden_html(golden_dir: Path) -> str:
    return (golden_dir / "screener_company_page.html").read_text()


@pytest.fixture
def golden_excel(golden_dir: Path) -> bytes:
    return (golden_dir / "screener_excel_export.xlsx").read_bytes()


# ---------------------------------------------------------------------------
# _parse_screener_date
# ---------------------------------------------------------------------------


class TestParseScreenerDate:
    """Test the module-level _parse_screener_date function."""

    def test_mar_quarter_end(self):
        assert _parse_screener_date("Mar 2026") == "2026-03-31"

    def test_jun_quarter_end(self):
        assert _parse_screener_date("Jun 2024") == "2024-06-30"

    def test_sep_quarter_end(self):
        assert _parse_screener_date("Sep 2023") == "2023-09-30"

    def test_dec_quarter_end(self):
        assert _parse_screener_date("Dec 2025") == "2025-12-31"

    def test_full_month_name(self):
        """Full month names like 'January 2025' should parse to last day of month."""
        result = _parse_screener_date("January 2025")
        assert result == "2025-01-31"

    def test_non_quarter_month(self):
        """Non-quarter months map to the last day of that month."""
        result = _parse_screener_date("Feb 2024")
        assert result == "2024-02-29"  # 2024 is a leap year

    def test_invalid_raises_screener_error(self):
        with pytest.raises(ScreenerError, match="Cannot parse date"):
            _parse_screener_date("abc")

    def test_whitespace_stripped(self):
        assert _parse_screener_date("  Mar 2026  ") == "2026-03-31"


# ---------------------------------------------------------------------------
# Excel: parse_quarterly_results
# ---------------------------------------------------------------------------


class TestParseQuarterlyResults:
    """Test Excel-based quarterly results parsing."""

    def test_returns_list_of_quarterly_result(self, screener_client, golden_excel):
        results = screener_client.parse_quarterly_results("SBIN", golden_excel)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, QuarterlyResult) for r in results)

    def test_sorted_ascending_by_quarter_end(self, screener_client, golden_excel):
        results = screener_client.parse_quarterly_results("SBIN", golden_excel)
        dates = [r.quarter_end for r in results]
        assert dates == sorted(dates)

    def test_symbol_set_correctly(self, screener_client, golden_excel):
        results = screener_client.parse_quarterly_results("SBIN", golden_excel)
        assert all(r.symbol == "SBIN" for r in results)

    def test_quarter_end_is_iso_date(self, screener_client, golden_excel):
        results = screener_client.parse_quarterly_results("SBIN", golden_excel)
        iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        for r in results:
            assert iso_re.match(r.quarter_end), f"Bad date format: {r.quarter_end}"

    def test_revenue_present(self, screener_client, golden_excel):
        """At least some quarters should have non-None revenue."""
        results = screener_client.parse_quarterly_results("SBIN", golden_excel)
        revenues = [r.revenue for r in results if r.revenue is not None]
        assert len(revenues) > 0
        assert all(v > 0 for v in revenues)

    def test_net_income_present(self, screener_client, golden_excel):
        results = screener_client.parse_quarterly_results("SBIN", golden_excel)
        net_incomes = [r.net_income for r in results if r.net_income is not None]
        assert len(net_incomes) > 0

    def test_bad_excel_raises_error(self, screener_client):
        with pytest.raises(Exception):
            screener_client.parse_quarterly_results("SBIN", b"not-an-excel-file")


# ---------------------------------------------------------------------------
# Excel: parse_annual_eps
# ---------------------------------------------------------------------------


class TestParseAnnualEps:
    """Test Excel-based annual EPS parsing."""

    def test_returns_list_of_annual_eps(self, screener_client, golden_excel):
        results = screener_client.parse_annual_eps("SBIN", golden_excel)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, AnnualEPS) for r in results)

    def test_eps_not_none(self, screener_client, golden_excel):
        results = screener_client.parse_annual_eps("SBIN", golden_excel)
        for r in results:
            assert r.eps is not None

    def test_sorted_ascending(self, screener_client, golden_excel):
        results = screener_client.parse_annual_eps("SBIN", golden_excel)
        dates = [r.fiscal_year_end for r in results]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# Excel: parse_annual_financials
# ---------------------------------------------------------------------------


class TestParseAnnualFinancials:
    """Test Excel-based full annual financials parsing."""

    def test_returns_list_of_annual_financials(self, screener_client, golden_excel):
        results = screener_client.parse_annual_financials("SBIN", golden_excel)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, AnnualFinancials) for r in results)

    def test_key_fields_populated(self, screener_client, golden_excel):
        """Revenue, net_income, equity_capital, borrowings, cfo should be present."""
        results = screener_client.parse_annual_financials("SBIN", golden_excel)
        has_revenue = any(r.revenue is not None for r in results)
        has_net_income = any(r.net_income is not None for r in results)
        has_equity = any(r.equity_capital is not None for r in results)
        has_borrowings = any(r.borrowings is not None for r in results)
        has_cfo = any(r.cfo is not None for r in results)
        assert has_revenue, "No revenue found in annual financials"
        assert has_net_income, "No net_income found in annual financials"
        assert has_equity, "No equity_capital found in annual financials"
        assert has_borrowings, "No borrowings found in annual financials"
        assert has_cfo, "No cfo found in annual financials"

    def test_sorted_ascending(self, screener_client, golden_excel):
        results = screener_client.parse_annual_financials("SBIN", golden_excel)
        dates = [r.fiscal_year_end for r in results]
        assert dates == sorted(dates)

    def test_no_data_sheet_returns_empty(self, screener_client):
        """Excel without 'Data Sheet' returns empty list (parse_annual_financials)."""
        import openpyxl
        import io

        wb = openpyxl.Workbook()
        wb.active.title = "Wrong Sheet"
        buf = io.BytesIO()
        wb.save(buf)
        wb.close()
        result = screener_client.parse_annual_financials("SBIN", buf.getvalue())
        assert result == []


# ---------------------------------------------------------------------------
# HTML: parse_quarterly_from_html
# ---------------------------------------------------------------------------


class TestParseQuarterlyFromHtml:
    """Test HTML-based quarterly results parsing."""

    def test_returns_list_of_quarterly_result(self, screener_client, golden_html):
        results = screener_client.parse_quarterly_from_html("SBIN", golden_html)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, QuarterlyResult) for r in results)

    def test_revenue_positive(self, screener_client, golden_html):
        results = screener_client.parse_quarterly_from_html("SBIN", golden_html)
        revenues = [r.revenue for r in results if r.revenue is not None]
        assert len(revenues) > 0
        assert all(v > 0 for v in revenues)

    def test_sorted_ascending(self, screener_client, golden_html):
        results = screener_client.parse_quarterly_from_html("SBIN", golden_html)
        dates = [r.quarter_end for r in results]
        assert dates == sorted(dates)

    def test_empty_html_returns_empty(self, screener_client):
        assert screener_client.parse_quarterly_from_html("SBIN", "") == []

    def test_html_without_quarters_section(self, screener_client):
        html = "<html><body><section id='other'>content</section></body></html>"
        assert screener_client.parse_quarterly_from_html("SBIN", html) == []


# ---------------------------------------------------------------------------
# HTML: parse_ratios_from_html
# ---------------------------------------------------------------------------


class TestParseRatiosFromHtml:
    """Test HTML-based ratios parsing."""

    def test_returns_list_of_screener_ratios(self, screener_client, golden_html):
        results = screener_client.parse_ratios_from_html("SBIN", golden_html)
        assert isinstance(results, list)
        assert len(results) > 0
        assert all(isinstance(r, ScreenerRatios) for r in results)

    def test_has_roce(self, screener_client, golden_html):
        results = screener_client.parse_ratios_from_html("SBIN", golden_html)
        roce_values = [r.roce_pct for r in results if r.roce_pct is not None]
        assert len(roce_values) > 0

    def test_sorted_ascending(self, screener_client, golden_html):
        results = screener_client.parse_ratios_from_html("SBIN", golden_html)
        dates = [r.fiscal_year_end for r in results]
        assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# HTML: parse_documents_from_html
# ---------------------------------------------------------------------------


class TestParseDocumentsFromHtml:
    """Test document link extraction from HTML."""

    def test_returns_dict_with_expected_keys(self, screener_client, golden_html):
        result = screener_client.parse_documents_from_html(golden_html)
        assert isinstance(result, dict)
        assert "concalls" in result
        assert "annual_reports" in result

    def test_concalls_is_list(self, screener_client, golden_html):
        result = screener_client.parse_documents_from_html(golden_html)
        assert isinstance(result["concalls"], list)

    def test_empty_html_returns_empty_lists(self, screener_client):
        result = screener_client.parse_documents_from_html("")
        assert result == {"concalls": [], "annual_reports": []}


# ---------------------------------------------------------------------------
# HTML: parse_about_from_html
# ---------------------------------------------------------------------------


class TestParseAboutFromHtml:
    """Test company profile parsing from HTML."""

    def test_returns_dict_with_about_text(self, screener_client, golden_html):
        result = screener_client.parse_about_from_html("SBIN", golden_html)
        assert isinstance(result, dict)
        assert "about_text" in result
        assert isinstance(result["about_text"], str)
        assert len(result["about_text"]) > 0

    def test_has_screener_url(self, screener_client, golden_html):
        result = screener_client.parse_about_from_html("SBIN", golden_html)
        assert "screener_url" in result
        assert "SBIN" in result["screener_url"]

    def test_empty_html_returns_default(self, screener_client):
        result = screener_client.parse_about_from_html("SBIN", "")
        assert result["about_text"] == ""
        assert result["key_points"] == []


# ---------------------------------------------------------------------------
# HTML: parse_growth_rates_from_html
# ---------------------------------------------------------------------------


class TestParseGrowthRatesFromHtml:
    """Test growth rate extraction from HTML."""

    def test_returns_dict(self, screener_client, golden_html):
        result = screener_client.parse_growth_rates_from_html(golden_html)
        assert isinstance(result, dict)

    def test_has_sales_growth_keys(self, screener_client, golden_html):
        result = screener_client.parse_growth_rates_from_html(golden_html)
        # Should have at least some sales/profit growth rates
        growth_keys = [k for k in result if k.startswith("sales_") or k.startswith("profit_")]
        assert len(growth_keys) > 0

    def test_values_are_fractions(self, screener_client, golden_html):
        """Growth rates should be decimals (e.g. 0.23 for 23%), not raw percentages."""
        result = screener_client.parse_growth_rates_from_html(golden_html)
        for key, val in result.items():
            if val is not None:
                # Reasonable range: -5 to +5 (i.e. -500% to +500%)
                assert -5 <= val <= 5, f"{key}={val} looks like raw percentage, not fraction"


# ---------------------------------------------------------------------------
# Static: _parse_table_section
# ---------------------------------------------------------------------------


class TestParseTableSection:
    """Test the static _parse_table_section helper."""

    def test_quarters_section(self, golden_html):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(golden_html, "html.parser")
        result = ScreenerClient._parse_table_section(soup, "quarters")
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_nonexistent_section_returns_empty(self, golden_html):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(golden_html, "html.parser")
        result = ScreenerClient._parse_table_section(soup, "nonexistent_id")
        assert result == {}

    def test_empty_html_returns_empty(self):
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("", "html.parser")
        result = ScreenerClient._parse_table_section(soup, "quarters")
        assert result == {}
