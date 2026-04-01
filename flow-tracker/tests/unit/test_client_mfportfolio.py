"""Tests for mfportfolio_client.py — MF scheme holding row parsing."""

from __future__ import annotations

from flowtracker.mfportfolio_client import MFPortfolioClient, _parse_month, _ordinal


class TestParseMonth:
    """Test _parse_month helper."""

    def test_standard(self):
        assert _parse_month("2026-02") == (2026, 2)

    def test_december(self):
        assert _parse_month("2025-12") == (2025, 12)

    def test_january(self):
        assert _parse_month("2026-01") == (2026, 1)


class TestOrdinal:
    """Test _ordinal helper."""

    def test_1st(self):
        assert _ordinal(1) == "st"

    def test_2nd(self):
        assert _ordinal(2) == "nd"

    def test_3rd(self):
        assert _ordinal(3) == "rd"

    def test_4th(self):
        assert _ordinal(4) == "th"

    def test_11th(self):
        assert _ordinal(11) == "th"

    def test_12th(self):
        assert _ordinal(12) == "th"

    def test_13th(self):
        assert _ordinal(13) == "th"

    def test_21st(self):
        assert _ordinal(21) == "st"

    def test_31st(self):
        assert _ordinal(31) == "st"

    def test_28th(self):
        assert _ordinal(28) == "th"


class TestParseHoldingRow:
    """Test MFPortfolioClient._parse_holding_row with fixture cells."""

    def _header(self, **overrides) -> dict[str, int]:
        """Standard header mapping."""
        base = {"isin": 0, "name": 1, "qty": 2, "value": 3, "pct": 4}
        base.update(overrides)
        return base

    def test_valid_row(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank of India", "500000", "41000000", "5.25"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "SBI Blue Chip Fund",
        )
        assert holding is not None
        assert holding.isin == "INE062A01020"
        assert holding.stock_name == "State Bank of India"
        assert holding.quantity == 500000
        assert holding.market_value_lakhs == 41000000.0
        assert holding.pct_of_nav == 5.25
        assert holding.month == "2026-02"
        assert holding.amc == "SBI"
        assert holding.scheme_name == "SBI Blue Chip Fund"
        client.close()

    def test_invalid_isin_returns_none(self):
        client = MFPortfolioClient()
        cells = ["NOTANISIN", "Some Stock", "1000", "50000", "0.5"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is None
        client.close()

    def test_short_isin_returns_none(self):
        client = MFPortfolioClient()
        cells = ["IN123", "Some Stock", "1000", "50000", "0.5"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is None
        client.close()

    def test_empty_isin_returns_none(self):
        client = MFPortfolioClient()
        cells = ["", "Some Stock", "1000", "50000", "0.5"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is None
        client.close()

    def test_empty_name_returns_none(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "", "1000", "50000", "0.5"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is None
        client.close()

    def test_zero_qty_and_zero_value_returns_none(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank", "0", "0", "0"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is None
        client.close()

    def test_qty_with_commas(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank", "5,00,000", "41000000", "5.25"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is not None
        assert holding.quantity == 500000
        client.close()

    def test_pct_with_percent_sign(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank", "1000", "50000", "5.25%"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        assert holding is not None
        assert holding.pct_of_nav == 5.25
        client.close()

    def test_invalid_qty_defaults_to_zero(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank", "abc", "50000", "0.5"]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        # qty=0 but value=50000, so holding is returned
        assert holding is not None
        assert holding.quantity == 0
        assert holding.market_value_lakhs == 50000.0
        client.close()

    def test_scheme_name_truncated(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank", "1000", "50000", "0.5"]
        long_scheme = "X" * 150
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", long_scheme,
        )
        assert holding is not None
        assert len(holding.scheme_name) == 100
        client.close()

    def test_none_cells_handled(self):
        client = MFPortfolioClient()
        cells = ["INE062A01020", "State Bank", None, None, None]
        holding = client._parse_holding_row(
            cells, self._header(), "SBI", "2026-02", "Test Fund",
        )
        # qty=0, value=0 → returns None
        assert holding is None
        client.close()
