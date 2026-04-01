"""Tests for flowtracker/utils.py utility functions."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from flowtracker.utils import (
    _clean,
    fmt_crores,
    fmt_crores_label,
    normalize_category,
    parse_nse_date,
    parse_period,
)


# ---------------------------------------------------------------------------
# _clean — JSON serialization helper
# ---------------------------------------------------------------------------
class TestClean:
    def test_dict_with_date(self):
        result = _clean({"date": date(2026, 3, 17), "value": 100})
        assert result["date"] == "2026-03-17"
        assert result["value"] == 100

    def test_dict_with_datetime(self):
        dt = datetime(2026, 3, 17, 14, 30, 0)
        result = _clean({"ts": dt})
        assert "2026-03-17" in result["ts"]

    def test_dict_with_decimal(self):
        result = _clean({"price": Decimal("920.50")})
        assert result["price"] == "920.50"

    def test_nested_dict(self):
        result = _clean({"outer": {"inner_date": date(2026, 1, 1)}})
        assert result["outer"]["inner_date"] == "2026-01-01"

    def test_list_of_dicts(self):
        result = _clean([{"d": date(2026, 1, 1)}, {"d": date(2026, 2, 1)}])
        assert result[0]["d"] == "2026-01-01"
        assert result[1]["d"] == "2026-02-01"

    def test_plain_values_unchanged(self):
        result = _clean({"a": 42, "b": "hello", "c": 3.14, "d": True, "e": None})
        assert result == {"a": 42, "b": "hello", "c": 3.14, "d": True, "e": None}

    def test_empty_dict(self):
        assert _clean({}) == {}

    def test_empty_list(self):
        assert _clean([]) == []


# ---------------------------------------------------------------------------
# fmt_crores — format float as crores string
# ---------------------------------------------------------------------------
class TestFmtCrores:
    def test_positive(self):
        assert fmt_crores(1234.56) == "+1,234.56"

    def test_negative(self):
        assert fmt_crores(-567.89) == "-567.89"

    def test_zero(self):
        assert fmt_crores(0.0) == "+0.00"

    def test_none(self):
        assert fmt_crores(None) == "N/A"

    def test_large_value(self):
        result = fmt_crores(12345678.90)
        assert "12,345,678.90" in result


# ---------------------------------------------------------------------------
# fmt_crores_label — format with rupee sign and Cr suffix
# ---------------------------------------------------------------------------
class TestFmtCroresLabel:
    def test_positive(self):
        assert fmt_crores_label(1234.56) == "₹1,234.56 Cr"

    def test_none(self):
        assert fmt_crores_label(None) == "N/A"

    def test_zero(self):
        assert fmt_crores_label(0.0) == "₹0.00 Cr"


# ---------------------------------------------------------------------------
# parse_period — "7d" -> 7
# ---------------------------------------------------------------------------
class TestParsePeriod:
    def test_7d(self):
        assert parse_period("7d") == 7

    def test_30d(self):
        assert parse_period("30d") == 30

    def test_365d(self):
        assert parse_period("365d") == 365

    def test_with_whitespace(self):
        assert parse_period("  14d  ") == 14

    def test_uppercase(self):
        assert parse_period("7D") == 7

    def test_invalid_no_d(self):
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("7")

    def test_invalid_letters(self):
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("abc")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("")

    def test_invalid_weeks(self):
        with pytest.raises(ValueError, match="Invalid period"):
            parse_period("2w")


# ---------------------------------------------------------------------------
# normalize_category — NSE category normalization
# ---------------------------------------------------------------------------
class TestNormalizeCategory:
    def test_fii_fpi_star(self):
        assert normalize_category("FII/FPI *") == "FII"

    def test_fii_plain(self):
        assert normalize_category("FII") == "FII"

    def test_fpi_prefix(self):
        assert normalize_category("FPI Investments") == "FII"

    def test_dii_star(self):
        assert normalize_category("DII *") == "DII"

    def test_dii_plain(self):
        assert normalize_category("DII") == "DII"

    def test_other_category(self):
        assert normalize_category("Promoter") == "Promoter"

    def test_whitespace_stripped(self):
        assert normalize_category("  FII/FPI  ") == "FII"

    def test_lowercase_fii(self):
        assert normalize_category("fii/fpi") == "FII"

    def test_lowercase_dii(self):
        assert normalize_category("dii") == "DII"


# ---------------------------------------------------------------------------
# parse_nse_date — "17-Mar-2026" -> date
# ---------------------------------------------------------------------------
class TestParseNseDate:
    def test_valid_date(self):
        assert parse_nse_date("17-Mar-2026") == date(2026, 3, 17)

    def test_single_digit_day(self):
        assert parse_nse_date("1-Jan-2026") == date(2026, 1, 1)

    def test_whitespace_stripped(self):
        assert parse_nse_date("  17-Mar-2026  ") == date(2026, 3, 17)

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_nse_date("2026-03-17")
