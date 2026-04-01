"""Tests for sebi_client.py — SEBI daily MF flow HTML parsing."""

from __future__ import annotations

import respx

from flowtracker.sebi_client import SEBIClient


# -- Fixture HTML mimicking SEBI table structure --

_SEBI_HTML = """
<html><body>
<table>
<thead><tr><th>Date</th><th>Category</th><th>Gross Purchase</th><th>Gross Sale</th><th>Net Investment</th></tr></thead>
<tbody>
<tr>
  <td rowspan="2">02 Mar, 2026</td>
  <td>Equity</td>
  <td>16545.47</td>
  <td>14233.12</td>
  <td>2312.35</td>
</tr>
<tr>
  <td>Debt</td>
  <td>8234.56</td>
  <td>11369.90</td>
  <td>(3135.34)</td>
</tr>
<tr>
  <td rowspan="2">03 Mar, 2026</td>
  <td>Equity</td>
  <td>12100.00</td>
  <td>11800.50</td>
  <td>299.50</td>
</tr>
<tr>
  <td>Debt</td>
  <td>5000.00</td>
  <td>5200.00</td>
  <td>(200.00)</td>
</tr>
<tr>
  <td rowspan="2">Total</td>
  <td>Equity</td>
  <td>28645.47</td>
  <td>26033.62</td>
  <td>2611.85</td>
</tr>
<tr>
  <td>Debt</td>
  <td>13234.56</td>
  <td>16569.90</td>
  <td>(3335.34)</td>
</tr>
</tbody>
</table>
</body></html>
"""

_SEBI_HTML_NO_TBODY = "<html><body><p>No data</p></body></html>"


class TestParseDate:
    """Test SEBIClient._parse_date static method."""

    def test_standard_format(self):
        assert SEBIClient._parse_date("02 Mar, 2026") == "2026-03-02"

    def test_no_comma(self):
        assert SEBIClient._parse_date("02 Mar 2026") == "2026-03-02"

    def test_december(self):
        assert SEBIClient._parse_date("31 Dec, 2025") == "2025-12-31"

    def test_invalid_returns_none(self):
        assert SEBIClient._parse_date("Total") is None

    def test_empty_returns_none(self):
        assert SEBIClient._parse_date("") is None

    def test_whitespace(self):
        assert SEBIClient._parse_date("  02 Mar, 2026  ") == "2026-03-02"


class TestParseAmount:
    """Test SEBIClient._parse_amount static method."""

    def test_positive(self):
        assert SEBIClient._parse_amount("16545.47") == 16545.47

    def test_negative_in_parens(self):
        assert SEBIClient._parse_amount("(3135.34)") == -3135.34

    def test_with_commas(self):
        assert SEBIClient._parse_amount("1,65,45.47") == 16545.47

    def test_zero(self):
        assert SEBIClient._parse_amount("0.0") == 0.0

    def test_invalid_returns_zero(self):
        assert SEBIClient._parse_amount("N/A") == 0.0

    def test_whitespace_stripped(self):
        assert SEBIClient._parse_amount("  16545.47  ") == 16545.47


class TestParseHTML:
    """Test SEBIClient._parse_html with fixture HTML."""

    def test_parses_two_dates_four_records(self):
        with SEBIClient() as client:
            flows = client._parse_html(_SEBI_HTML)
        # 2 dates x 2 categories = 4. Total rows should be skipped (date=None).
        assert len(flows) == 4

    def test_first_record_equity(self):
        with SEBIClient() as client:
            flows = client._parse_html(_SEBI_HTML)
        eq = flows[0]
        assert eq.date == "2026-03-02"
        assert eq.category == "Equity"
        assert eq.gross_purchase == 16545.47
        assert eq.gross_sale == 14233.12
        assert eq.net_investment == 2312.35

    def test_second_record_debt_negative(self):
        with SEBIClient() as client:
            flows = client._parse_html(_SEBI_HTML)
        debt = flows[1]
        assert debt.date == "2026-03-02"
        assert debt.category == "Debt"
        assert debt.net_investment == -3135.34

    def test_total_rows_excluded(self):
        """Rows with 'Total' as date should be excluded."""
        with SEBIClient() as client:
            flows = client._parse_html(_SEBI_HTML)
        dates = {f.date for f in flows}
        assert "Total" not in dates
        assert all(d.startswith("2026-") for d in dates)

    def test_no_tbody_returns_empty(self):
        with SEBIClient() as client:
            flows = client._parse_html(_SEBI_HTML_NO_TBODY)
        assert flows == []


class TestFetchDaily:
    """Test full fetch with respx mock."""

    def test_fetch_daily_success(self):
        with respx.mock:
            respx.get(url__regex=r"sebi\.gov\.in").respond(200, text=_SEBI_HTML)
            with SEBIClient() as client:
                flows = client.fetch_daily()
            assert len(flows) == 4
