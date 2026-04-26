"""Tests for five_year_parser.parse_five_year_summary.

Covers the standard 10-yr highlights table (NESTLEIND-style), unit detection
across crore/million/billion/lakh, image-rendered detection, malformed input,
and 10-year tables with mid-table sub-headings.

The parser is pure-Python (no LLM); these tests use inline markdown
fixtures rather than real AR PDFs.
"""
from __future__ import annotations

import pytest

from flowtracker.research.five_year_parser import (
    FiveYearHighlight,
    _looks_image_rendered,
    parse_five_year_summary,
)


# ----------------------------------------------------------------------
# Fixture: real NESTLEIND FY25 10-year highlights (₹ in million)
# Trimmed from ~/vault/stocks/NESTLEIND/filings/FY25/_docling.md so the
# fixture is self-contained.
# ----------------------------------------------------------------------
NESTLEIND_FY25_FIXTURE = """## 10 - Year Financial Highlights

₹ in million (except otherwise stated)

| Particulars | 2024-25 | 2023-24 ^ | 2022 | 2021 | 2020 | 2019 | 2018 | 2017 | 2016 | 2015* |
|-------------|---------|-----------|------|------|------|------|------|------|------|-------|
| Sales | 200,775 | 242,755 | 167,895 | 146,649 | 132,902 | 122,953 | 112,162 | 101,351 | 94,096 | 81,233 |
| Profit from Operations | 43,104 | 53,418 | 33,659 | 32,288 | 28,775 | 25,940 | 23,509 | 18,305 | 16,542 | 13,338 |
| Profit after Tax | 33,145 | 39,328 | 23,905 | 21,184 | 20,824 | 19,684 | 16,069 | 12,252 | 10,014 | 5,633 |
| Shareholders Fund | 41,172 | 33,409 | 24,592 | 19,464 | 20,193 | 19,189 | 36,737 | 34,206 | 32,823 | 28,178 |
| Operating Cash flow | 29,363 | 41,748 | 27,374 | 22,360 | 24,545 | 22,953 | 20,525 | 18,178 | 14,659 | 10,981 |
| Capital Expenditure | 20,044 | 18,783 | 5,407 | 7,308 | 4,741 | 1,522 | 1,628 | 1,959 | 1,133 | 1,493 |
| Earnings per share (₹) | 34.38 | 40.79 | 24.79 | 21.97 | 21.60 | 20.42 | 16.67 | 12.71 | 10.39 | 5.84 |
| Dividend per share (₹) | 27.0 | 32.2 | 22.0 | 20.0 | 20.0 | 34.2 | 11.5 | 8.6 | 6.3 | 4.8 |
"""


def test_parse_standard_10year_table():
    """Standard layout — years as columns, metrics as rows. Returns one
    FiveYearHighlight per fiscal-year column, sorted DESC."""
    rows = parse_five_year_summary(NESTLEIND_FY25_FIXTURE, source_ar_fy="FY25")
    assert len(rows) == 10, f"expected 10 fiscal years, got {len(rows)}"

    # Sorted DESC by fy_end
    fys = [r.fy_end for r in rows]
    assert fys == sorted(fys, reverse=True)

    # All rows are FiveYearHighlight instances with provenance set
    for r in rows:
        assert isinstance(r, FiveYearHighlight)
        assert r.source_ar_fy == "FY25"
        assert r.raw_unit == "million"


def test_parse_unit_conversion_million_to_crore():
    """Unit detected as 'million' → multiplier 0.1 → values divide by 10
    (10 million = 1 crore). NESTLEIND FY25 sales = 200,775 mn = 20,077.5 cr.
    """
    rows = parse_five_year_summary(NESTLEIND_FY25_FIXTURE, source_ar_fy="FY25")
    fy25 = next(r for r in rows if r.fy_end == "2025-03-31")
    assert fy25.revenue == pytest.approx(20077.5, rel=1e-6)
    assert fy25.pat == pytest.approx(3314.5, rel=1e-6)
    assert fy25.operating_profit == pytest.approx(4310.4, rel=1e-6)


def test_parse_per_share_values_unconverted():
    """EPS and DPS are per-share rupee values — must NOT be unit-converted."""
    rows = parse_five_year_summary(NESTLEIND_FY25_FIXTURE, source_ar_fy="FY25")
    fy25 = next(r for r in rows if r.fy_end == "2025-03-31")
    assert fy25.eps == pytest.approx(34.38)
    assert fy25.dividend_per_share == pytest.approx(27.0)


def test_parse_balance_sheet_and_cash_flow():
    """Net worth (Shareholders Fund), CFO, capex all parse to crore."""
    rows = parse_five_year_summary(NESTLEIND_FY25_FIXTURE, source_ar_fy="FY25")
    fy25 = next(r for r in rows if r.fy_end == "2025-03-31")
    assert fy25.net_worth == pytest.approx(4117.2, rel=1e-6)
    assert fy25.cfo == pytest.approx(2936.3, rel=1e-6)
    assert fy25.capex == pytest.approx(2004.4, rel=1e-6)


def test_parse_oldest_year_present():
    """Oldest fiscal-year column (2014-15 → 2015-03-31) parses correctly."""
    rows = parse_five_year_summary(NESTLEIND_FY25_FIXTURE)
    fys = {r.fy_end for r in rows}
    # 2015* notation parses as the 2015 fiscal-year close.
    assert "2015-03-31" in fys


# ----------------------------------------------------------------------
# Unit detection across the four supported units
# ----------------------------------------------------------------------

def _build_min_fixture(unit_phrase: str, sales_value: str) -> str:
    """Minimal 3-year 1-metric fixture for unit-detection tests."""
    return (
        "## 5-Year Financial Highlights\n\n"
        f"{unit_phrase}\n\n"
        "| Particulars | FY25 | FY24 | FY23 |\n"
        "|---|---|---|---|\n"
        f"| Sales | {sales_value} | {sales_value} | {sales_value} |\n"
        "| Profit after Tax | 100 | 100 | 100 |\n"
        "| Operating Cash flow | 90 | 90 | 90 |\n"
        "| Capital Expenditure | 50 | 50 | 50 |\n"
        "| Earnings per share | 5.0 | 5.0 | 5.0 |\n"
        "| Number of shares | 10 | 10 | 10 |\n"
        "| Total assets | 1000 | 1000 | 1000 |\n"
    )


@pytest.mark.parametrize("unit_phrase,sales_in,sales_cr,unit_label", [
    ("(₹ in crore)", "1000", 1000.0, "crore"),
    ("(₹ in million)", "1000", 100.0, "million"),
    ("(₹ in billion)", "10", 1000.0, "billion"),
    ("(₹ in lakh)", "10000", 100.0, "lakh"),
])
def test_unit_detection(unit_phrase: str, sales_in: str, sales_cr: float, unit_label: str):
    """Each unit phrase resolves to the correct multiplier-to-crores."""
    md = _build_min_fixture(unit_phrase, sales_in)
    rows = parse_five_year_summary(md)
    assert rows, "expected at least one row"
    assert rows[0].raw_unit == unit_label
    assert rows[0].revenue == pytest.approx(sales_cr, rel=1e-6)


# ----------------------------------------------------------------------
# Image-rendered detection
# ----------------------------------------------------------------------

def test_image_rendered_short_section():
    """Section <500 chars → image_rendered (no parseable content)."""
    short_md = (
        "## Five Year Financial Highlights\n\n"
        "<!-- image -->\n\n"
        "Refer to the highlights chart on page 12.\n"
    )
    assert _looks_image_rendered(short_md) is True
    # Parser still returns [] without raising.
    rows = parse_five_year_summary(short_md)
    assert rows == []


def test_image_rendered_no_tables():
    """Long prose with no markdown tables → image_rendered."""
    prose_md = (
        "## Ten Year Financial Highlights\n\n"
        + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20)
    )
    assert _looks_image_rendered(prose_md) is True
    rows = parse_five_year_summary(prose_md)
    assert rows == []


def test_image_rendered_sparse_digit_table():
    """A table heading with just labels (no numbers) → image_rendered."""
    sparse_md = (
        "## Financial Highlights\n\n"
        + ("Some descriptive text. " * 30)
        + "\n\n| Metric | Value |\n|---|---|\n| Sales | NA |\n| Profit | NA |\n"
    )
    assert _looks_image_rendered(sparse_md) is True


# ----------------------------------------------------------------------
# Malformed / missing inputs
# ----------------------------------------------------------------------

def test_empty_input_returns_empty_list():
    assert parse_five_year_summary("") == []


def test_no_table_returns_empty_list():
    md = "## Heading Only\n\nSome prose here.\n"
    rows = parse_five_year_summary(md)
    assert rows == []


def test_table_with_unrecognized_metrics_yields_empty_rows():
    """Table exists but no labels match canonical metric aliases → no rows."""
    md = (
        "## Financial Highlights\n"
        "(₹ in crore)\n\n"
        "| Foo | FY25 | FY24 | FY23 |\n"
        "|---|---|---|---|\n"
        "| Random Metric A | 100 | 200 | 300 |\n"
        "| Random Metric B | 400 | 500 | 600 |\n"
        "| Random Metric C | 700 | 800 | 900 |\n"
        "| Random Metric D | 100 | 200 | 300 |\n"
        "| Random Metric E | 400 | 500 | 600 |\n"
        "| Random Metric F | 700 | 800 | 900 |\n"
    )
    rows = parse_five_year_summary(md)
    assert rows == []


def test_ratios_and_percent_lines_are_skipped():
    """Lines like 'As %of Sales' must NOT be matched as a canonical metric.
    Table is sized above the digit-density floor (30 cells) so the parser
    runs end-to-end rather than getting flagged image-rendered."""
    md = (
        "## Financial Highlights\n"
        "(₹ in crore)\n\n"
        "| Particulars | FY25 | FY24 | FY23 | FY22 | FY21 |\n"
        "|---|---|---|---|---|---|\n"
        "| Sales | 1000 | 900 | 800 | 700 | 600 |\n"
        "| As %of Sales | 21.5 | 22.0 | 23.0 | 24.0 | 25.0 |\n"
        "| Profit after Tax | 200 | 180 | 160 | 140 | 120 |\n"
        "| Return on Average Equity (%) | 88.9 | 108.5 | 90.0 | 80.0 | 70.0 |\n"
        "| Shareholders Fund | 5000 | 4500 | 4000 | 3500 | 3000 |\n"
        "| Total Assets | 10000 | 9000 | 8000 | 7000 | 6000 |\n"
        "| Operating Cash flow | 250 | 220 | 200 | 180 | 150 |\n"
    )
    rows = parse_five_year_summary(md)
    # Five years parsed
    assert len(rows) == 5
    fy25 = next(r for r in rows if r.fy_end == "2025-03-31")
    # Sales = 1000 (the percent row above is skipped — no double-write)
    assert fy25.revenue == 1000.0
    assert fy25.pat == 200.0
    assert fy25.net_worth == 5000.0


def test_negative_values_in_parens():
    """Parenthesized values parse as negatives. Use a table large enough to
    pass the digit-density floor."""
    md = (
        "## Financial Highlights\n"
        "(₹ in crore)\n\n"
        "| Particulars | FY25 | FY24 | FY23 | FY22 | FY21 |\n"
        "|---|---|---|---|---|---|\n"
        "| Sales | 1000 | 900 | 800 | 700 | 600 |\n"
        "| Profit after Tax | (50) | 180 | 160 | 140 | 120 |\n"
        "| Shareholders Fund | 5000 | 4500 | 4000 | 3500 | 3000 |\n"
        "| Total Assets | 10000 | 9000 | 8000 | 7000 | 6000 |\n"
        "| Operating Cash flow | 250 | 220 | 200 | 180 | 150 |\n"
        "| Capital Expenditure | 100 | 90 | 80 | 70 | 60 |\n"
        "| Earnings per share | 5.0 | 4.5 | 4.0 | 3.5 | 3.0 |\n"
    )
    rows = parse_five_year_summary(md)
    fy25 = next(r for r in rows if r.fy_end == "2025-03-31")
    assert fy25.pat == -50.0


# ----------------------------------------------------------------------
# 10-year table with mid-table sub-headings (NESTLEIND-style)
# ----------------------------------------------------------------------

def test_10year_table_with_subheading_rows():
    """Real NESTLEIND-style table has 'Balance Sheet and Cash flow Statement'
    sub-heading rows interleaved. Parser must skip those non-numeric rows
    cleanly without polluting any year bucket. Parser requires >=3 year columns."""
    md = (
        "## 10-Year Financial Highlights\n"
        "(₹ in crore)\n\n"
        "| Particulars | FY25 | FY24 | FY23 |\n"
        "|---|---|---|---|\n"
        "| | Results | Results | Results |\n"
        "| Sales | 1000 | 900 | 800 |\n"
        "| Profit after Tax | 200 | 180 | 160 |\n"
        "| | Balance Sheet | Balance Sheet | Balance Sheet |\n"
        "| Shareholders Fund | 5000 | 4500 | 4000 |\n"
        "| | Per Share Data | Per Share Data | Per Share Data |\n"
        "| Earnings per share | 20.0 | 18.0 | 16.0 |\n"
    )
    rows = parse_five_year_summary(md)
    assert len(rows) == 3
    fy25 = next(r for r in rows if r.fy_end == "2025-03-31")
    assert fy25.revenue == 1000.0
    assert fy25.pat == 200.0
    assert fy25.net_worth == 5000.0
    assert fy25.eps == 20.0


def test_provenance_recorded_when_supplied():
    md = _build_min_fixture("(₹ in crore)", "1000")
    rows = parse_five_year_summary(md, source_ar_fy="FY25")
    assert all(r.source_ar_fy == "FY25" for r in rows)
    assert all(r.raw_unit == "crore" for r in rows)


def test_provenance_optional():
    """Without source_ar_fy, the field stays None — no exception."""
    md = _build_min_fixture("(₹ in crore)", "1000")
    rows = parse_five_year_summary(md)
    assert all(r.source_ar_fy is None for r in rows)


# ----------------------------------------------------------------------
# Year-format coverage (strict per-token patterns)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("year_header,expected_fy_end", [
    ("FY25", "2025-03-31"),
    ("FY 2025", "2025-03-31"),
    ("2024-25", "2025-03-31"),
    ("March 2025", "2025-03-31"),
])
def test_year_header_normalization(year_header: str, expected_fy_end: str):
    """Each supported year-header pattern yields the canonical fy_end. Parser
    requires >=3 year columns, so we pad with two adjacent years."""
    md = (
        "## Financial Highlights\n"
        "(₹ in crore)\n\n"
        f"| Particulars | {year_header} | FY24 | FY23 |\n"
        "|---|---|---|---|\n"
        "| Sales | 1000 | 900 | 800 |\n"
        "| Profit after Tax | 200 | 180 | 160 |\n"
        "| Shareholders Fund | 5000 | 4500 | 4000 |\n"
        "| Total Assets | 10000 | 9000 | 8000 |\n"
    )
    rows = parse_five_year_summary(md)
    fys = {r.fy_end for r in rows}
    assert expected_fy_end in fys
