"""Unit tests for flowtracker/mf_display.py — Rich display formatters for MF data.

Captures Rich console output into a StringIO buffer via monkeypatching the
module-level ``console`` object, then verifies expected strings appear.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from flowtracker import mf_display
from flowtracker.mf_models import (
    AMFIReportRow,
    MFAUMSummary,
    MFDailyFlow,
    MFMonthlyFlow,
)


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    # highlight=False prevents Rich from inserting ANSI codes around numbers/dates,
    # keeping substrings like "2026-02" contiguous for assertions.
    con = Console(file=buf, width=200, highlight=False, no_color=True)
    return con, buf


# ---------------------------------------------------------------------------
# display_mf_fetch_result
# ---------------------------------------------------------------------------


class TestDisplayMfFetchResult:
    def test_happy_path_shows_categories_and_counts(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        rows = [
            AMFIReportRow(
                category="Equity",
                sub_category="Large Cap Fund",
                num_schemes=30,
                funds_mobilized=5000.0,
                redemption=2000.0,
                net_flow=3000.0,
                aum=250000.0,
            ),
            AMFIReportRow(
                category="Equity",
                sub_category="Mid Cap Fund",
                num_schemes=25,
                funds_mobilized=3000.0,
                redemption=1000.0,
                net_flow=2000.0,
                aum=150000.0,
            ),
            AMFIReportRow(
                category="Debt",
                sub_category="Liquid Fund",
                num_schemes=40,
                funds_mobilized=10000.0,
                redemption=9000.0,
                net_flow=1000.0,
                aum=500000.0,
            ),
        ]
        mf_display.display_mf_fetch_result(rows, "2026-02")
        out = buf.getvalue()
        assert "2026-02" in out
        assert "Equity" in out
        assert "Debt" in out
        # 3 sub-category rows across 2 categories
        assert "3" in out
        assert "2" in out

    def test_empty_rows_shows_warning(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        mf_display.display_mf_fetch_result([], "2026-02")
        out = buf.getvalue()
        assert "No data" in out


# ---------------------------------------------------------------------------
# display_mf_summary
# ---------------------------------------------------------------------------


class TestDisplayMfSummary:
    def test_happy_path_renders_aum_panel(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        summary = MFAUMSummary(
            month="2026-02",
            total_aum=5000000.0,
            equity_aum=2500000.0,
            debt_aum=1500000.0,
            hybrid_aum=800000.0,
            other_aum=200000.0,
            equity_net_flow=30000.0,
            debt_net_flow=-5000.0,
            hybrid_net_flow=1000.0,
        )
        mf_display.display_mf_summary(summary)
        out = buf.getvalue()
        assert "2026-02" in out
        assert "Equity" in out
        assert "Debt" in out
        assert "Hybrid" in out
        assert "Total" in out
        assert "50.0%" in out  # equity = 2.5M / 5M
        assert "100.0%" in out  # footer

    def test_zero_total_aum_avoids_division(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        summary = MFAUMSummary(
            month="2026-02",
            total_aum=0.0,
            equity_aum=0.0,
            debt_aum=0.0,
            hybrid_aum=0.0,
            other_aum=0.0,
            equity_net_flow=0.0,
            debt_net_flow=0.0,
            hybrid_net_flow=0.0,
        )
        mf_display.display_mf_summary(summary)
        out = buf.getvalue()
        assert "2026-02" in out
        assert "0.0%" in out


# ---------------------------------------------------------------------------
# display_mf_flows_table
# ---------------------------------------------------------------------------


class TestDisplayMfFlowsTable:
    def test_happy_path_renders_flow_rows(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        flows = [
            MFMonthlyFlow(
                month="2026-02",
                category="Equity",
                sub_category="Large Cap Fund",
                num_schemes=30,
                funds_mobilized=5000.0,
                redemption=2000.0,
                net_flow=3000.0,
                aum=250000.0,
            ),
            MFMonthlyFlow(
                month="2026-01",
                category="Debt",
                sub_category="Liquid Fund",
                num_schemes=40,
                funds_mobilized=1000.0,
                redemption=500.0,
                net_flow=500.0,
                aum=None,
            ),
        ]
        mf_display.display_mf_flows_table(flows, "3 months")
        out = buf.getvalue()
        assert "Large Cap Fund" in out
        assert "Liquid Fund" in out
        assert "Equity" in out
        assert "2026-02" in out
        # aum=None path should render em-dash
        assert "\u2014" in out

    def test_empty_flows_shows_warning(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        mf_display.display_mf_flows_table([], "3 months")
        out = buf.getvalue()
        assert "No MF flow data" in out


# ---------------------------------------------------------------------------
# display_mf_aum_trend
# ---------------------------------------------------------------------------


class TestDisplayMfAumTrend:
    def test_happy_path_renders_trend_rows(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        summaries = [
            MFAUMSummary(
                month="2026-02",
                total_aum=5000000.0,
                equity_aum=2500000.0,
                debt_aum=1500000.0,
                hybrid_aum=800000.0,
                other_aum=200000.0,
                equity_net_flow=30000.0,
                debt_net_flow=-5000.0,
                hybrid_net_flow=1000.0,
            ),
            MFAUMSummary(
                month="2026-01",
                total_aum=4800000.0,
                equity_aum=2400000.0,
                debt_aum=1400000.0,
                hybrid_aum=800000.0,
                other_aum=200000.0,
                equity_net_flow=25000.0,
                debt_net_flow=1000.0,
                hybrid_net_flow=500.0,
            ),
        ]
        mf_display.display_mf_aum_trend(summaries)
        out = buf.getvalue()
        assert "AUM Trend" in out
        assert "2026-02" in out
        assert "2026-01" in out
        # equity share shown
        assert "50.0%" in out

    def test_empty_summaries_shows_warning(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        mf_display.display_mf_aum_trend([])
        out = buf.getvalue()
        assert "No AUM trend" in out


# ---------------------------------------------------------------------------
# display_mf_daily_summary
# ---------------------------------------------------------------------------


class TestDisplayMfDailySummary:
    def test_happy_path_renders_daily_panel_with_totals(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        flows = [
            MFDailyFlow(
                date="2026-03-19",
                category="Equity",
                gross_purchase=15000.0,
                gross_sale=12000.0,
                net_investment=3000.0,
            ),
            MFDailyFlow(
                date="2026-03-19",
                category="Debt",
                gross_purchase=8000.0,
                gross_sale=9000.0,
                net_investment=-1000.0,
            ),
        ]
        mf_display.display_mf_daily_summary(flows)
        out = buf.getvalue()
        assert "2026-03-19" in out
        assert "Equity" in out
        assert "Debt" in out
        assert "Total" in out
        assert "SEBI" in out

    def test_empty_flows_shows_fetch_hint(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        mf_display.display_mf_daily_summary([])
        out = buf.getvalue()
        assert "No daily MF data" in out
        assert "mf daily fetch" in out


# ---------------------------------------------------------------------------
# display_mf_daily_trend
# ---------------------------------------------------------------------------


class TestDisplayMfDailyTrend:
    def test_happy_path_renders_trend(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        rows = [
            {"date": "2026-03-19", "equity_net": 3000.0, "debt_net": -1000.0},
            {"date": "2026-03-18", "equity_net": 2500.0, "debt_net": 500.0},
        ]
        mf_display.display_mf_daily_trend(rows)
        out = buf.getvalue()
        assert "2026-03-19" in out
        assert "2026-03-18" in out
        assert "Daily Net Investment" in out

    def test_empty_trend_shows_warning(self, monkeypatch):
        con, buf = _make_console()
        monkeypatch.setattr(mf_display, "console", con)
        mf_display.display_mf_daily_trend([])
        out = buf.getvalue()
        assert "No daily MF trend" in out
