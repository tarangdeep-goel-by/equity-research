"""Unit tests for flowtracker.fmp_display — Rich console rendering of FMP data.

Captures the module-level console to a StringIO buffer via monkeypatch and asserts
that key strings appear in the rendered output. Covers the six public display_*
functions plus the fetch-result summary, with happy-path, empty-data, and one
edge case each.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from flowtracker import fmp_display
from flowtracker.fmp_models import (
    FMPAnalystGrade,
    FMPDcfValue,
    FMPFinancialGrowth,
    FMPKeyMetrics,
    FMPPriceTarget,
    FMPTechnicalIndicator,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def captured_console(monkeypatch):
    """Patch the module-level console with a StringIO-backed one and return the buffer."""
    buf = StringIO()
    con = Console(file=buf, width=200, color_system=None, no_color=True)
    monkeypatch.setattr(fmp_display, "console", con)
    return buf


# ---------------------------------------------------------------------------
# display_fmp_fetch_result
# ---------------------------------------------------------------------------


class TestDisplayFetchResult:
    def test_happy_path_all_sections(self, captured_console):
        summary = {
            "dcf": True,
            "dcf_history": [1, 2, 3],
            "technicals": [1] * 5,
            "key_metrics": [1] * 4,
            "financial_growth": [1] * 4,
            "analyst_grades": [1] * 2,
            "price_targets": [1] * 7,
        }
        fmp_display.display_fmp_fetch_result(summary)
        out = captured_console.getvalue()
        assert "FMP Fetch Complete" in out
        assert "DCF" in out
        assert "Technicals" in out
        assert "Key Metrics" in out
        assert "Analyst Grades" in out
        assert "Price Targets" in out

    def test_empty_summary(self, captured_console):
        fmp_display.display_fmp_fetch_result({})
        out = captured_console.getvalue()
        assert "No data fetched" in out


# ---------------------------------------------------------------------------
# display_dcf
# ---------------------------------------------------------------------------


class TestDisplayDcf:
    def test_happy_path_with_current_and_history(self, captured_console):
        current = FMPDcfValue(symbol="INFY", date="2026-01-15", dcf=1800.0, stock_price=1500.0)
        history = [
            FMPDcfValue(symbol="INFY", date="2025-12-15", dcf=1750.0, stock_price=1400.0),
            FMPDcfValue(symbol="INFY", date="2025-11-15", dcf=1700.0, stock_price=1600.0),
        ]
        fmp_display.display_dcf(current, history)
        out = captured_console.getvalue()
        assert "DCF Valuation" in out
        assert "INFY" in out
        assert "Margin of Safety" in out
        # Current margin = (1800-1500)/1500 = +20.0%
        assert "+20.0%" in out
        assert "DCF History" in out
        # Second history row: (1700-1600)/1600 = +6.2%; render negative margin too
        assert "-12.5%" not in out  # sanity
        # First history row (2025-12-15) has +25.0% margin
        assert "+25.0%" in out

    def test_empty_returns_warning(self, captured_console):
        fmp_display.display_dcf(None, [])
        out = captured_console.getvalue()
        assert "No DCF data" in out

    def test_history_only_with_zero_price(self, captured_console):
        # Edge case: stock_price=0 -> margin computation skipped; dcf=None in one row
        history = [
            FMPDcfValue(symbol="TCS", date="2026-01-01", dcf=None, stock_price=None),
            FMPDcfValue(symbol="TCS", date="2025-12-01", dcf=3000.0, stock_price=0.0),
        ]
        fmp_display.display_dcf(None, history)
        out = captured_console.getvalue()
        assert "DCF History" in out
        # Both rows should render --" for margin (no crash on zero/None)
        assert "--" in out


# ---------------------------------------------------------------------------
# display_technicals
# ---------------------------------------------------------------------------


class TestDisplayTechnicals:
    def test_happy_path_covers_rsi_zones(self, captured_console):
        indicators = [
            FMPTechnicalIndicator(symbol="INFY", date="2026-01-15", indicator="rsi", value=75.0),
            FMPTechnicalIndicator(symbol="INFY", date="2026-01-15", indicator="sma_50", value=1450.0),
            FMPTechnicalIndicator(symbol="INFY", date="2026-01-15", indicator="sma_200", value=1350.0),
            FMPTechnicalIndicator(symbol="INFY", date="2026-01-15", indicator="macd", value=2.5),
            FMPTechnicalIndicator(symbol="INFY", date="2026-01-15", indicator="adx", value=28.0),
            FMPTechnicalIndicator(symbol="INFY", date="2026-01-15", indicator="custom", value=42.0),
        ]
        fmp_display.display_technicals(indicators)
        out = captured_console.getvalue()
        assert "Technical Indicators" in out
        assert "RSI" in out
        assert "overbought" in out
        assert "SMA 50" in out
        assert "CUSTOM" in out  # extra indicator rendered

    def test_rsi_oversold_zone(self, captured_console):
        indicators = [
            FMPTechnicalIndicator(symbol="X", date="2026-01-15", indicator="rsi", value=25.0),
        ]
        fmp_display.display_technicals(indicators)
        out = captured_console.getvalue()
        assert "oversold" in out

    def test_empty_returns_warning(self, captured_console):
        fmp_display.display_technicals([])
        out = captured_console.getvalue()
        assert "No technical indicators" in out


# ---------------------------------------------------------------------------
# display_key_metrics
# ---------------------------------------------------------------------------


class TestDisplayKeyMetrics:
    def test_happy_path_with_dupont(self, captured_console):
        metrics = [
            FMPKeyMetrics(
                symbol="INFY",
                date="2025-03-31",
                pe_ratio=24.5,
                pb_ratio=8.2,
                ev_to_ebitda=18.0,
                roe=30.5,
                roic=28.1,
                debt_to_equity=0.10,
                dividend_yield=2.5,
                free_cash_flow_yield=4.1,
                net_profit_margin_dupont=20.0,
                asset_turnover=1.2,
                equity_multiplier=1.5,
            ),
            FMPKeyMetrics(symbol="INFY", date="2024-03-31", pe_ratio=22.0),
        ]
        fmp_display.display_key_metrics(metrics)
        out = captured_console.getvalue()
        assert "Key Financial Metrics" in out
        assert "P/E" in out
        assert "ROE" in out
        assert "DuPont" in out
        assert "Net Profit Margin" in out
        # Implied ROE = 20.0 * 1.2 * 1.5 = 36.0
        assert "36.0%" in out

    def test_all_none_fields(self, captured_console):
        metrics = [FMPKeyMetrics(symbol="X", date="2025-03-31")]
        fmp_display.display_key_metrics(metrics)
        out = captured_console.getvalue()
        assert "Key Financial Metrics" in out
        assert "--" in out

    def test_empty_returns_warning(self, captured_console):
        fmp_display.display_key_metrics([])
        out = captured_console.getvalue()
        assert "No key metrics" in out


# ---------------------------------------------------------------------------
# display_financial_growth
# ---------------------------------------------------------------------------


class TestDisplayFinancialGrowth:
    def test_happy_path_with_cagr(self, captured_console):
        growth = [
            FMPFinancialGrowth(
                symbol="INFY",
                date="2025-03-31",
                revenue_growth=15.0,
                ebitda_growth=-5.0,
                net_income_growth=12.0,
                eps_growth=11.0,
                free_cash_flow_growth=8.0,
                book_value_per_share_growth=10.0,
                revenue_growth_3y=14.0,
                revenue_growth_5y=13.0,
                revenue_growth_10y=12.0,
                net_income_growth_3y=11.0,
                net_income_growth_5y=10.0,
            ),
        ]
        fmp_display.display_financial_growth(growth)
        out = captured_console.getvalue()
        assert "Financial Growth Rates" in out
        assert "Revenue" in out
        assert "+15.0%" in out
        assert "-5.0%" in out
        assert "3Y CAGR" in out
        assert "5Y CAGR" in out
        assert "10Y CAGR" in out

    def test_no_cagr_data_skips_panel(self, captured_console):
        growth = [FMPFinancialGrowth(symbol="X", date="2025-03-31", revenue_growth=5.0)]
        fmp_display.display_financial_growth(growth)
        out = captured_console.getvalue()
        assert "Financial Growth Rates" in out
        assert "CAGR" not in out

    def test_empty_returns_warning(self, captured_console):
        fmp_display.display_financial_growth([])
        out = captured_console.getvalue()
        assert "No financial growth" in out


# ---------------------------------------------------------------------------
# display_analyst_grades
# ---------------------------------------------------------------------------


class TestDisplayAnalystGrades:
    def test_happy_path_upgrade_downgrade(self, captured_console):
        grades = [
            FMPAnalystGrade(
                symbol="INFY",
                date="2026-01-10",
                grading_company="Morgan Stanley",
                previous_grade="Hold",
                new_grade="Buy",
            ),
            FMPAnalystGrade(
                symbol="INFY",
                date="2026-01-05",
                grading_company="Goldman Sachs",
                previous_grade="Buy",
                new_grade="Sell",
            ),
            FMPAnalystGrade(
                symbol="INFY",
                date="2026-01-01",
                grading_company="CLSA",
                previous_grade=None,
                new_grade="Neutral",
            ),
        ]
        fmp_display.display_analyst_grades(grades)
        out = captured_console.getvalue()
        assert "Analyst Grade Changes" in out
        assert "Morgan Stanley" in out
        assert "Buy" in out
        assert "Sell" in out
        assert "Neutral" in out

    def test_empty_returns_warning(self, captured_console):
        fmp_display.display_analyst_grades([])
        out = captured_console.getvalue()
        assert "No analyst grades" in out


# ---------------------------------------------------------------------------
# display_price_targets
# ---------------------------------------------------------------------------


class TestDisplayPriceTargets:
    def test_happy_path_with_consensus(self, captured_console):
        targets = [
            FMPPriceTarget(
                symbol="INFY",
                published_date="2026-01-15",
                analyst_name="Jane Doe",
                analyst_company="Morgan Stanley",
                price_target=1800.0,
                price_when_posted=1500.0,
            ),
            FMPPriceTarget(
                symbol="INFY",
                published_date="2026-01-10",
                analyst_name="John Smith",
                analyst_company="Goldman Sachs",
                price_target=1600.0,
                price_when_posted=1500.0,
            ),
            FMPPriceTarget(
                symbol="INFY",
                published_date="2026-01-05",
                analyst_name=None,
                analyst_company=None,
                price_target=2000.0,
                price_when_posted=None,
            ),
        ]
        fmp_display.display_price_targets(targets)
        out = captured_console.getvalue()
        assert "Price Target Consensus" in out
        assert "Individual Price Targets" in out
        assert "Morgan Stanley" in out
        # avg = (1800+1600+2000)/3 = 1800
        assert "1,800.00" in out
        assert "Upside" in out

    def test_targets_without_valid_prices(self, captured_console):
        # All price_target=None -> no consensus panel but individual table still renders
        targets = [
            FMPPriceTarget(
                symbol="X",
                published_date="2026-01-10",
                analyst_name="A",
                analyst_company="Firm",
                price_target=None,
                price_when_posted=None,
            ),
        ]
        fmp_display.display_price_targets(targets)
        out = captured_console.getvalue()
        assert "Individual Price Targets" in out
        assert "Consensus" not in out  # panel skipped when no valid targets

    def test_empty_returns_warning(self, captured_console):
        fmp_display.display_price_targets([])
        out = captured_console.getvalue()
        assert "No price targets" in out
