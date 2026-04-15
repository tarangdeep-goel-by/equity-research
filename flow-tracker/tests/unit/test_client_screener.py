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


# ---------------------------------------------------------------------------
# _load_credentials
# ---------------------------------------------------------------------------


class TestLoadCredentials:
    """Test the module-level _load_credentials function."""

    def test_loads_email_and_password(self, tmp_path):
        """Valid screener.env returns (email, password)."""
        env = tmp_path / "screener.env"
        env.write_text("SCREENER_EMAIL=foo@bar.com\nSCREENER_PASSWORD=secret123\n")
        with patch("flowtracker.screener_client._CRED_PATH", env):
            from flowtracker.screener_client import _load_credentials

            email, password = _load_credentials()
            assert email == "foo@bar.com"
            assert password == "secret123"

    def test_skips_blank_and_comment_lines(self, tmp_path):
        """Blank lines and # comments are ignored."""
        env = tmp_path / "screener.env"
        env.write_text(
            "# this is a comment\n"
            "\n"
            "SCREENER_EMAIL=user@example.com\n"
            "  # another comment\n"
            "SCREENER_PASSWORD=pw\n"
        )
        with patch("flowtracker.screener_client._CRED_PATH", env):
            from flowtracker.screener_client import _load_credentials

            email, password = _load_credentials()
            assert email == "user@example.com"
            assert password == "pw"


# ---------------------------------------------------------------------------
# _login (success path)
# ---------------------------------------------------------------------------


class TestLogin:
    """Test the _login method (success path; failure handled in test_client_error_paths.py)."""

    def test_login_success_sets_session(self, tmp_path):
        """Full login flow: GET /login/ → CSRF cookie → POST /login/ → 200 to home."""
        import respx

        env = tmp_path / "screener.env"
        env.write_text("SCREENER_EMAIL=u@x.com\nSCREENER_PASSWORD=pw\n")

        with patch("flowtracker.screener_client._CRED_PATH", env):
            with respx.mock:
                # GET /login/ returns a CSRF token via cookie
                respx.get("https://www.screener.in/login/").respond(
                    200, headers={"set-cookie": "csrftoken=tok123; Path=/"}
                )
                # POST /login/ redirects to "/" (success: final URL no longer contains /login/)
                respx.post("https://www.screener.in/login/").respond(
                    302, headers={"location": "https://www.screener.in/"}
                )
                respx.get("https://www.screener.in/").respond(
                    200, html="<html>welcome</html>"
                )

                client = ScreenerClient()
                # CSRF cookie persisted on the httpx client
                assert client._client.cookies.get("csrftoken") == "tok123"
                client.close()

    def test_login_no_csrf_token_raises(self, tmp_path):
        """GET /login/ without csrftoken cookie → ScreenerError."""
        import respx

        env = tmp_path / "screener.env"
        env.write_text("SCREENER_EMAIL=u@x.com\nSCREENER_PASSWORD=pw\n")

        with patch("flowtracker.screener_client._CRED_PATH", env):
            with respx.mock:
                # No set-cookie header → csrftoken absent
                respx.get("https://www.screener.in/login/").respond(200)

                with pytest.raises(ScreenerError, match="CSRF"):
                    ScreenerClient()


# ---------------------------------------------------------------------------
# _request_with_retry — retry exhaustion / 403 re-login / transient errors
# ---------------------------------------------------------------------------


class TestRetryExhaustion:
    """Test _request_with_retry retry semantics."""

    def test_transient_error_then_success(self, screener_client):
        """First request raises a TransportError, retry returns 200."""
        import httpx
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                route = respx.get("https://www.screener.in/api/test/")
                route.side_effect = [
                    httpx.ConnectError("boom"),
                    httpx.Response(200, json={"ok": True}),
                ]
                resp = screener_client._request_with_retry(
                    "GET", "https://www.screener.in/api/test/"
                )
                assert resp.status_code == 200
                assert route.call_count == 2

    def test_retry_exhausted_raises(self, screener_client):
        """Persistent TransportError exhausts retries and re-raises."""
        import httpx
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                respx.get("https://www.screener.in/api/fail/").mock(
                    side_effect=httpx.ConnectError("network down")
                )
                with pytest.raises(httpx.ConnectError):
                    screener_client._request_with_retry(
                        "GET",
                        "https://www.screener.in/api/fail/",
                        max_retries=2,
                    )

    def test_http_status_error_retried(self, screener_client):
        """500 errors raise HTTPStatusError, retried until success."""
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                route = respx.get("https://www.screener.in/api/flaky/")
                route.side_effect = [
                    respx.MockResponse(500),
                    respx.MockResponse(200, json={"ok": True}),
                ] if False else None
                # respx doesn't expose MockResponse at top level in all versions —
                # use httpx.Response for robustness
                import httpx as _httpx

                route.side_effect = [
                    _httpx.Response(500),
                    _httpx.Response(200, json={"ok": True}),
                ]
                resp = screener_client._request_with_retry(
                    "GET", "https://www.screener.in/api/flaky/"
                )
                assert resp.status_code == 200


class TestReLoginOn403:
    """Test that 403 responses trigger _login() and a retry."""

    def test_403_triggers_relogin_then_success(self, screener_client):
        """A 403 should call _login() and retry the same request."""
        import httpx
        import respx

        login_calls = {"n": 0}

        def fake_login() -> None:
            login_calls["n"] += 1

        with patch.object(screener_client, "_login", side_effect=fake_login):
            with patch("flowtracker.screener_client.time.sleep"):
                with respx.mock:
                    route = respx.get("https://www.screener.in/api/protected/")
                    route.side_effect = [
                        httpx.Response(403),
                        httpx.Response(200, json={"ok": True}),
                    ]
                    resp = screener_client._request_with_retry(
                        "GET",
                        "https://www.screener.in/api/protected/",
                        max_retries=3,
                    )
                    assert resp.status_code == 200
                    assert login_calls["n"] == 1
                    assert route.call_count == 2


# ---------------------------------------------------------------------------
# _get_warehouse_id — primary regex, fallback regex, both fail
# ---------------------------------------------------------------------------


class TestWarehouseIdRegex:
    """Test the _get_warehouse_id regex matching paths."""

    def test_primary_formaction_regex(self, screener_client):
        """formaction='/user/company/export/123/' matches the primary pattern."""
        html = '<form><button formaction="/user/company/export/12345/">Export</button></form>'
        with patch.object(screener_client, "fetch_company_page", return_value=html):
            assert screener_client._get_warehouse_id("FOO") == "12345"

    def test_fallback_url_regex(self, screener_client):
        """Without formaction, the bare /user/company/export/N/ URL still matches."""
        html = '<a href="/user/company/export/99999/">link</a>'
        with patch.object(screener_client, "fetch_company_page", return_value=html):
            assert screener_client._get_warehouse_id("FOO") == "99999"

    def test_no_match_raises(self, screener_client):
        """No warehouse ID in HTML → ScreenerError."""
        html = "<html><body>nothing here</body></html>"
        with patch.object(screener_client, "fetch_company_page", return_value=html):
            with pytest.raises(ScreenerError, match="warehouse"):
                screener_client._get_warehouse_id("FOO")


# ---------------------------------------------------------------------------
# fetch_company_page — consolidated/standalone fallback
# ---------------------------------------------------------------------------


class TestFetchCompanyPage:
    """Test fetch_company_page consolidated → standalone fallback logic."""

    def test_consolidated_succeeds(self, screener_client):
        """Consolidated page with data-date-key returns the consolidated HTML."""
        import respx

        with respx.mock:
            respx.get("https://www.screener.in/company/SBIN/consolidated/").respond(
                200, html='<html data-date-key="2025-12">consolidated</html>'
            )
            html = screener_client.fetch_company_page("SBIN")
            assert "consolidated" in html
            assert screener_client._is_consolidated is True

    def test_falls_back_to_standalone_when_consolidated_empty(self, screener_client):
        """Consolidated page lacking data-date-key → falls back to standalone."""
        import respx

        with respx.mock:
            respx.get("https://www.screener.in/company/FOO/consolidated/").respond(
                200, html="<html>empty skeleton</html>"
            )
            respx.get("https://www.screener.in/company/FOO/").respond(
                200, html='<html data-date-key="2025-12">standalone</html>'
            )
            html = screener_client.fetch_company_page("FOO")
            assert "standalone" in html
            assert screener_client._is_consolidated is False

    def test_both_fail_raises(self, screener_client):
        """Both consolidated and standalone return errors → ScreenerError."""
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                respx.get("https://www.screener.in/company/BAD/consolidated/").respond(404)
                respx.get("https://www.screener.in/company/BAD/").respond(404)
                with pytest.raises(ScreenerError, match="not found"):
                    screener_client.fetch_company_page("BAD")


# ---------------------------------------------------------------------------
# download_excel and download_standalone_excel
# ---------------------------------------------------------------------------


class TestDownloadExcel:
    """Test download_excel and download_standalone_excel paths."""

    def test_download_excel_returns_bytes(self, screener_client):
        """Successful POST to export URL returns the response bytes."""
        import respx

        with patch.object(screener_client, "_get_warehouse_id", return_value="42"):
            with respx.mock:
                respx.post("https://www.screener.in/user/company/export/42/").respond(
                    200,
                    headers={"content-type": "application/vnd.openxmlformats"},
                    content=b"FAKE-EXCEL-BYTES",
                )
                content = screener_client.download_excel("FOO")
                assert content == b"FAKE-EXCEL-BYTES"

    def test_download_excel_html_response_raises(self, screener_client):
        """Server returned HTML (e.g., a login page) → ScreenerError."""
        import respx

        with patch.object(screener_client, "_get_warehouse_id", return_value="42"):
            with respx.mock:
                respx.post("https://www.screener.in/user/company/export/42/").respond(
                    200, headers={"content-type": "text/html"}, html="<html>nope</html>"
                )
                with pytest.raises(ScreenerError, match="HTML instead of Excel"):
                    screener_client.download_excel("FOO")

    def test_download_standalone_no_warehouse_returns_none(self, screener_client):
        """Standalone page without warehouse ID → returns None."""
        import respx

        with respx.mock:
            respx.get("https://www.screener.in/company/FOO/").respond(
                200, html="<html>no warehouse here</html>"
            )
            assert screener_client.download_standalone_excel("FOO") is None

    def test_download_standalone_404_returns_none(self, screener_client):
        """Standalone page returning 404 (after retries) → None (exception swallowed)."""
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                respx.get("https://www.screener.in/company/FOO/").respond(404)
                assert screener_client.download_standalone_excel("FOO") is None


# ---------------------------------------------------------------------------
# Growth rates and ratios — edge cases
# ---------------------------------------------------------------------------


class TestGrowthRatesEdgeCases:
    """Edge cases for parse_growth_rates_from_html."""

    def test_empty_html(self, screener_client):
        """No tables at all → empty dict."""
        assert screener_client.parse_growth_rates_from_html("") == {}

    def test_unknown_table_header_skipped(self, screener_client):
        """A ranges-table whose header isn't in key_map is silently ignored."""
        html = """
        <html><body>
          <table class="ranges-table">
            <tr><th>Some Unknown Metric</th><th></th></tr>
            <tr><td>10 Years:</td><td>15%</td></tr>
          </table>
        </body></html>
        """
        result = screener_client.parse_growth_rates_from_html(html)
        assert result == {}

    def test_non_numeric_value_becomes_none(self, screener_client):
        """A garbled value cell parses to None (try/except branch)."""
        html = """
        <html><body>
          <table class="ranges-table">
            <tr><th>Compounded Sales Growth</th><th></th></tr>
            <tr><td>10 Years:</td><td>not-a-number</td></tr>
            <tr><td>5 Years:</td><td>17%</td></tr>
          </table>
        </body></html>
        """
        result = screener_client.parse_growth_rates_from_html(html)
        assert result["sales_10y"] is None
        assert result["sales_5y"] == pytest.approx(0.17)

    def test_unknown_period_skipped(self, screener_client):
        """A row with a period not in period_map is skipped, not added as None."""
        html = """
        <html><body>
          <table class="ranges-table">
            <tr><th>Compounded Sales Growth</th><th></th></tr>
            <tr><td>2 Years:</td><td>10%</td></tr>
            <tr><td>5 Years:</td><td>17%</td></tr>
          </table>
        </body></html>
        """
        result = screener_client.parse_growth_rates_from_html(html)
        assert "sales_2y" not in result
        assert result["sales_5y"] == pytest.approx(0.17)


class TestRatiosEdgeCases:
    """Edge cases for parse_ratios_from_html."""

    def test_empty_html_returns_empty(self, screener_client):
        assert screener_client.parse_ratios_from_html("SBIN", "") == []

    def test_html_without_ratios_section(self, screener_client):
        html = "<html><body><section id='other'>x</section></body></html>"
        assert screener_client.parse_ratios_from_html("SBIN", html) == []


# ---------------------------------------------------------------------------
# Static helpers and small utilities
# ---------------------------------------------------------------------------


class TestQuarterKeyAndCompanyId:
    """Test _parse_quarter_key and _get_company_id helpers."""

    def test_parse_quarter_key_known_month(self):
        assert ScreenerClient._parse_quarter_key("Dec 2025") == "2025-12"
        assert ScreenerClient._parse_quarter_key("Jan 2024") == "2024-01"

    def test_parse_quarter_key_unknown_format(self):
        """Non 'Mon YYYY' input is returned unchanged."""
        assert ScreenerClient._parse_quarter_key("garbage") == "garbage"

    def test_get_company_id_extracts(self, screener_client):
        html = '<html><a href="/api/company/9876/chart/">link</a></html>'
        assert screener_client._get_company_id(html) == "9876"

    def test_get_company_id_missing(self, screener_client):
        assert screener_client._get_company_id("<html></html>") is None

    def test_get_both_ids_via_attributes(self, screener_client):
        """Both IDs extracted from data attributes when present."""
        html = (
            '<html><body>'
            '<div id="company-info" data-company-id="111" data-warehouse-id="222"></div>'
            '</body></html>'
        )
        cid, wid = screener_client._get_both_ids(html)
        assert cid == "111"
        assert wid == "222"

    def test_get_both_ids_via_regex_fallback(self, screener_client):
        """When data-warehouse-id absent, regex falls back to formaction."""
        html = (
            '<html><body>'
            '<div data-company-id="333"></div>'
            '<form><button formaction="/user/company/export/444/">x</button></form>'
            '</body></html>'
        )
        cid, wid = screener_client._get_both_ids(html)
        assert cid == "333"
        assert wid == "444"


# ---------------------------------------------------------------------------
# Phase 2 API methods — search, fetch_chart_data_by_type, context manager
# ---------------------------------------------------------------------------


class TestSimpleApiMethods:
    """Tests for search, fetch_chart_data_by_type, and the context-manager protocol."""

    def test_search_returns_json_list(self, screener_client):
        import respx

        with respx.mock:
            respx.get(url__regex=r"screener\.in/api/company/search/").respond(
                200, json=[{"id": 1, "name": "SBI", "url": "/company/SBIN/"}]
            )
            result = screener_client.search("SBI")
            assert isinstance(result, list)
            assert result[0]["name"] == "SBI"

    def test_fetch_chart_data_by_type_unknown_returns_empty(self, screener_client):
        """Unknown chart_type → empty datasets dict, no HTTP call."""
        result = screener_client.fetch_chart_data_by_type("123", "unknown_chart")
        assert result == {"datasets": []}

    def test_fetch_chart_data_by_type_known(self, screener_client):
        """Known chart_type makes the API call and returns parsed JSON."""
        import respx

        screener_client._is_consolidated = True
        with respx.mock:
            respx.get(url__regex=r"screener\.in/api/company/123/chart/").respond(
                200, json={"datasets": [{"label": "Price", "values": [["2025-01", 100]]}]}
            )
            result = screener_client.fetch_chart_data_by_type("123", "price")
            assert result["datasets"][0]["label"] == "Price"

    def test_context_manager_closes(self, screener_client):
        """__enter__ returns self; __exit__ closes the underlying client."""
        with patch.object(screener_client._client, "close") as mock_close:
            with screener_client as c:
                assert c is screener_client
            mock_close.assert_called_once()


# ---------------------------------------------------------------------------
# fetch_* convenience methods (one-call download + parse)
# ---------------------------------------------------------------------------


class TestFetchConvenienceMethods:
    """Tests for fetch_all, fetch_annual_eps, fetch_all_with_annual, fetch_standalone_summary."""

    def test_fetch_all(self, screener_client, golden_excel):
        """fetch_all downloads the Excel and returns parsed quarterly results."""
        with patch.object(screener_client, "download_excel", return_value=golden_excel):
            results = screener_client.fetch_all("SBIN")
            assert isinstance(results, list)
            assert len(results) > 0
            assert all(isinstance(r, QuarterlyResult) for r in results)

    def test_fetch_annual_eps_convenience(self, screener_client, golden_excel):
        """fetch_annual_eps downloads and parses annual EPS in one call."""
        with patch.object(screener_client, "download_excel", return_value=golden_excel):
            results = screener_client.fetch_annual_eps("SBIN")
            assert isinstance(results, list)
            assert all(isinstance(r, AnnualEPS) for r in results)

    def test_fetch_all_with_annual(self, screener_client, golden_excel):
        """Returns 3-tuple of (quarters, annual_eps, annual_financials)."""
        with patch.object(screener_client, "download_excel", return_value=golden_excel):
            quarters, annual_eps, annual_fin = screener_client.fetch_all_with_annual("SBIN")
            assert all(isinstance(q, QuarterlyResult) for q in quarters)
            assert all(isinstance(a, AnnualEPS) for a in annual_eps)
            assert all(isinstance(f, AnnualFinancials) for f in annual_fin)

    def test_fetch_standalone_summary_no_excel(self, screener_client):
        """If standalone Excel can't be downloaded, returns empty list."""
        with patch.object(screener_client, "download_standalone_excel", return_value=None):
            assert screener_client.fetch_standalone_summary("FOO") == []

    def test_fetch_standalone_summary_with_excel(self, screener_client, golden_excel):
        """Standalone summary builds dicts of key fields from parsed annual financials."""
        with patch.object(screener_client, "download_standalone_excel", return_value=golden_excel):
            result = screener_client.fetch_standalone_summary("SBIN")
            assert isinstance(result, list)
            assert len(result) > 0
            # Each row has the expected keys
            keys = set(result[0].keys())
            assert {"symbol", "fiscal_year_end", "revenue", "net_income"} <= keys

    def test_download_standalone_success(self, screener_client):
        """Standalone page with warehouse ID + valid POST → returns Excel bytes."""
        import respx

        with respx.mock:
            respx.get("https://www.screener.in/company/FOO/").respond(
                200,
                html='<html><form><button formaction="/user/company/export/77/">x</button></form></html>',
            )
            respx.post("https://www.screener.in/user/company/export/77/").respond(
                200,
                headers={"content-type": "application/vnd.openxmlformats"},
                content=b"STANDALONE-EXCEL",
            )
            content = screener_client.download_standalone_excel("FOO")
            assert content == b"STANDALONE-EXCEL"

    def test_download_standalone_html_response_returns_none(self, screener_client):
        """Standalone export returning HTML → returns None."""
        import respx

        with respx.mock:
            respx.get("https://www.screener.in/company/FOO/").respond(
                200,
                html='<html><form><button formaction="/user/company/export/77/">x</button></form></html>',
            )
            respx.post("https://www.screener.in/user/company/export/77/").respond(
                200, headers={"content-type": "text/html"}, html="<html>err</html>"
            )
            assert screener_client.download_standalone_excel("FOO") is None


# ---------------------------------------------------------------------------
# Phase 2 chart, peers, shareholders, schedules
# ---------------------------------------------------------------------------


class TestPhase2ApiMethods:
    """Tests for fetch_chart_data, fetch_peers, fetch_shareholders, fetch_schedules."""

    def test_fetch_chart_data_no_company_id_returns_empty(self, screener_client):
        """If page HTML lacks company ID, fetch_chart_data returns {}."""
        result = screener_client.fetch_chart_data("FOO", html="<html></html>")
        assert result == {}

    def test_fetch_chart_data_full(self, screener_client):
        """fetch_chart_data hits all 6 chart endpoints and aggregates them."""
        import respx

        html = '<html><a href="/api/company/55/chart/">x</a></html>'
        with respx.mock:
            respx.get(url__regex=r"screener\.in/api/company/55/chart/").respond(
                200,
                json={
                    "datasets": [
                        {"label": "Price", "values": [["2025-01", 100]]}
                    ]
                },
            )
            result = screener_client.fetch_chart_data("FOO", html=html)
            assert "price_chart" in result
            assert result["price_chart"]["Price"] == [["2025-01", 100]]

    def test_fetch_peers(self, screener_client):
        """Parses the peers HTML table into a list of dicts."""
        import respx

        peers_html = """
        <table>
          <thead><tr><th>Name</th><th>CMP Rs.</th><th>P/E</th></tr></thead>
          <tbody>
            <tr>
              <td><a href="/company/HDFCBANK/">HDFC Bank</a></td>
              <td>1,500</td>
              <td>22.5</td>
            </tr>
          </tbody>
        </table>
        """
        with respx.mock:
            respx.get("https://www.screener.in/api/company/123/peers/").respond(
                200, html=peers_html
            )
            peers = screener_client.fetch_peers("123")
            assert len(peers) == 1
            assert peers[0]["peer_symbol"] == "HDFCBANK"
            assert peers[0]["cmp_rs"] == 1500.0
            assert peers[0]["p_e"] == 22.5

    def test_fetch_peers_no_table(self, screener_client):
        """When response has no <table>, fetch_peers returns []."""
        import respx

        with respx.mock:
            respx.get("https://www.screener.in/api/company/9/peers/").respond(
                200, html="<html>no table</html>"
            )
            assert screener_client.fetch_peers("9") == []

    def test_fetch_shareholders(self, screener_client):
        """Parses individual shareholder JSON for each classification."""
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                respx.get(
                    url__regex=r"screener\.in/api/3/42/investors/.*/quarterly/"
                ).respond(
                    200,
                    json={
                        "Person A": {
                            "Dec 2025": "1.5",
                            "setAttributes": {"data-person-url": "/p/A/"},
                        }
                    },
                )
                result = screener_client.fetch_shareholders("42")
                assert "promoters" in result
                assert "foreign_institutions" in result
                assert "domestic_institutions" in result
                assert "public" in result
                holders = result["promoters"]
                assert holders[0]["name"] == "Person A"
                assert holders[0]["url"] == "/p/A/"

    def test_fetch_shareholders_failure_swallowed(self, screener_client):
        """A failing request → empty list for that classification."""
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with patch("flowtracker.screener_client.time.sleep"):
                with respx.mock:
                    respx.get(
                        url__regex=r"screener\.in/api/3/42/investors/.*/quarterly/"
                    ).respond(500)
                    result = screener_client.fetch_shareholders("42")
                    # All four classifications fall back to empty lists
                    assert result == {
                        "promoters": [],
                        "foreign_institutions": [],
                        "domestic_institutions": [],
                        "public": [],
                    }

    def test_fetch_schedules(self, screener_client):
        """fetch_schedules returns the parsed JSON dict."""
        import respx

        screener_client._is_consolidated = True
        with respx.mock:
            respx.get(url__regex=r"screener\.in/api/company/42/schedules/").respond(
                200, json={"sub_items": {"A": [1, 2, 3]}}
            )
            result = screener_client.fetch_schedules("42", "quarters", "Sales")
            assert result == {"sub_items": {"A": [1, 2, 3]}}

    def test_fetch_schedules_non_dict_returns_empty(self, screener_client):
        """If API returns a list, fetch_schedules normalizes to {}."""
        import respx

        with respx.mock:
            respx.get(url__regex=r"screener\.in/api/company/42/schedules/").respond(
                200, json=["not", "a", "dict"]
            )
            result = screener_client.fetch_schedules("42", "quarters", "Sales")
            assert result == {}

    def test_fetch_all_schedules(self, screener_client):
        """fetch_all_schedules iterates every (section, parent) combination."""
        import respx

        with patch("flowtracker.screener_client.time.sleep"):
            with respx.mock:
                respx.get(url__regex=r"screener\.in/api/company/9/schedules/").respond(
                    200, json={"x": 1}
                )
                result = screener_client.fetch_all_schedules("9")
                assert set(result.keys()) == {
                    "quarters",
                    "profit-loss",
                    "balance-sheet",
                    "cash-flow",
                }
                # Each section should have its parents populated
                assert result["quarters"]["Sales"] == {"x": 1}
