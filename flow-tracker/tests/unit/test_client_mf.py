"""Tests for mf_client.py — AMFI monthly MF flow parsing."""

from __future__ import annotations

from flowtracker.mf_client import AMFIClient


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
