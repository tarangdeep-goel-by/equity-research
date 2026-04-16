"""Unit tests for flowtracker.fund_display render functions.

Complements tests/integration/test_display_modules.py::TestFundDisplay which
only exercises display_quarterly_history. Here we cover:
- display_live_snapshot (full + minimal)
- display_peer_comparison (happy, empty, with ownership_data)
- display_valuation_band (happy, empty)
- display_quarterly_history (bad-date branch + None fields)
- Helper edge cases: _fmt_cr large values, _color_change zero/None

All tests capture Rich console output via StringIO and assert on substrings.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from flowtracker import fund_display
from flowtracker.fund_models import LiveSnapshot, QuarterlyResult, ValuationBand


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_console() -> tuple[Console, StringIO]:
    buf = StringIO()
    con = Console(file=buf, width=200, no_color=True)
    return con, buf


@pytest.fixture
def capture_console(monkeypatch):
    con, buf = _make_console()
    monkeypatch.setattr(fund_display, "console", con)
    return buf


# ---------------------------------------------------------------------------
# display_live_snapshot
# ---------------------------------------------------------------------------


class TestDisplayLiveSnapshot:
    def test_full_snapshot_renders_all_sections(self, capture_console):
        snap = LiveSnapshot(
            symbol="SBIN",
            company_name="State Bank of India",
            sector="Financial Services",
            industry="Banks",
            price=812.45,
            market_cap=725000.0,  # ₹7.25L Cr — triggers lakh-crore branch
            pe_trailing=12.3,
            pe_forward=10.8,
            pb_ratio=1.6,
            ev_ebitda=9.2,
            dividend_yield=1.8,
            roe=15.2,
            roa=1.1,
            gross_margin=45.0,
            operating_margin=28.4,
            net_margin=18.3,
            debt_to_equity=0.6,
            current_ratio=1.4,
            free_cash_flow=12500.0,
            revenue_growth=12.5,
            earnings_growth=-3.4,
        )
        fund_display.display_live_snapshot(snap)
        out = capture_console.getvalue()
        assert "SBIN" in out
        assert "State Bank of India" in out
        assert "Financial Services" in out
        # Price formatted with thousands separator
        assert "812.45" in out
        # Lakh-crore formatter
        assert "L Cr" in out
        # Growth line rendered with both revenue and earnings
        assert "Growth" in out
        assert "Revenue" in out
        assert "Earnings" in out

    def test_minimal_snapshot_renders_em_dashes(self, capture_console):
        # All optional fields None — every formatter should emit "—"
        snap = LiveSnapshot(symbol="ZZZZ")
        fund_display.display_live_snapshot(snap)
        out = capture_console.getvalue()
        assert "ZZZZ" in out
        assert "—" in out
        # No growth line when both revenue_growth and earnings_growth are None
        assert "Growth:" not in out


# ---------------------------------------------------------------------------
# display_peer_comparison
# ---------------------------------------------------------------------------


class TestDisplayPeerComparison:
    def _snap(self, symbol: str, **overrides) -> LiveSnapshot:
        base = dict(
            symbol=symbol,
            price=500.0,
            market_cap=250000.0,
            pe_trailing=18.5,
            ev_ebitda=11.2,
            pb_ratio=2.3,
            roe=16.0,
            operating_margin=22.0,
            net_margin=14.0,
            debt_to_equity=0.8,
            revenue_growth=10.5,
        )
        base.update(overrides)
        return LiveSnapshot(**base)

    def test_peers_side_by_side(self, capture_console):
        snaps = [self._snap("SBIN"), self._snap("HDFCBANK", price=1650.0)]
        fund_display.display_peer_comparison(snaps)
        out = capture_console.getvalue()
        assert "SBIN" in out and "HDFCBANK" in out
        assert "P/E" in out
        assert "ROE" in out

    def test_peers_empty_graceful(self, capture_console):
        fund_display.display_peer_comparison([])
        out = capture_console.getvalue()
        assert "No peer data" in out

    def test_peers_with_ownership_data(self, capture_console):
        snaps = [self._snap("SBIN"), self._snap("HDFCBANK")]
        ownership = {
            "SBIN": {"fii_pct": 11.2, "fii_change": 0.8, "mf_pct": 9.4, "mf_change": -0.3},
            "HDFCBANK": {"fii_pct": 52.1, "fii_change": -1.5, "mf_pct": 18.2, "mf_change": 2.1},
        }
        fund_display.display_peer_comparison(snaps, ownership_data=ownership)
        out = capture_console.getvalue()
        assert "FII%" in out
        assert "MF%" in out
        # Ownership values render
        assert "11.2%" in out
        assert "52.1%" in out


# ---------------------------------------------------------------------------
# display_valuation_band
# ---------------------------------------------------------------------------


class TestDisplayValuationBand:
    def _band(self, metric: str, percentile: float, **overrides) -> ValuationBand:
        base = dict(
            symbol="SBIN",
            metric=metric,
            min_val=10.0,
            max_val=30.0,
            median_val=18.0,
            current_val=16.0,
            percentile=percentile,
            num_observations=52,
            period_start="2025-01-01",
            period_end="2026-01-01",
        )
        base.update(overrides)
        return ValuationBand(**base)

    def test_bands_renders_metrics_with_all_percentile_colors(self, capture_console):
        # Three bands spanning green (<30), yellow (30-70), red (>70) color branches
        bands = [
            self._band("pe_trailing", 20.0),   # green
            self._band("ev_ebitda", 55.0),     # yellow
            self._band("pb_ratio", 85.0),      # red
        ]
        fund_display.display_valuation_band(bands)
        out = capture_console.getvalue()
        assert "SBIN" in out
        assert "P/E" in out
        assert "EV/EBITDA" in out
        assert "P/B" in out
        # Period subtitle
        assert "2025-01-01" in out
        # All three percentiles rendered
        assert "20%" in out
        assert "55%" in out
        assert "85%" in out

    def test_bands_empty_graceful(self, capture_console):
        fund_display.display_valuation_band([])
        out = capture_console.getvalue()
        assert "Not enough" in out or "Weekly" in out

    def test_bands_unknown_metric_falls_through(self, capture_console):
        # metric not in metric_labels dict — renders raw key
        bands = [self._band("custom_ratio", 40.0)]
        fund_display.display_valuation_band(bands)
        out = capture_console.getvalue()
        assert "custom_ratio" in out


# ---------------------------------------------------------------------------
# display_quarterly_history — covers the bad-date ValueError branch
# ---------------------------------------------------------------------------


class TestDisplayQuarterlyHistoryEdges:
    def test_bad_date_format_falls_through_to_raw(self, capture_console):
        results = [
            QuarterlyResult(
                symbol="SBIN",
                quarter_end="Q3-FY26",  # not YYYY-MM-DD — triggers ValueError branch
                revenue=100000.0,
                net_income=18000.0,
                eps=25.3,
                operating_margin=28.0,
                net_margin=18.0,
            )
        ]
        fund_display.display_quarterly_history(results, "SBIN")
        out = capture_console.getvalue()
        # Raw quarter label preserved when date parsing fails
        assert "Q3-FY26" in out
        assert "SBIN" in out

    def test_none_fields_render_dashes(self, capture_console):
        results = [
            QuarterlyResult(
                symbol="SBIN",
                quarter_end="2025-12-31",
                revenue=None,
                net_income=None,
                eps=None,
                operating_margin=None,
                net_margin=None,
            )
        ]
        fund_display.display_quarterly_history(results, "SBIN")
        out = capture_console.getvalue()
        # Header still renders
        assert "Dec 2025" in out
        # Dash tokens for missing numeric fields
        assert "—" in out


# ---------------------------------------------------------------------------
# Helper edge cases — pick up the last few uncovered lines
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_fmt_cr_none(self):
        assert fund_display._fmt_cr(None) == "—"

    def test_fmt_cr_small_value(self):
        # Below 1 lakh cr — plain ₹ format
        assert fund_display._fmt_cr(5000.0) == "₹5,000 Cr"

    def test_fmt_cr_lakh_crore(self):
        out = fund_display._fmt_cr(250000.0)
        assert "L Cr" in out
        assert "2.5" in out

    def test_fmt_pct_multiply_and_none(self):
        assert fund_display._fmt_pct(None) == "—"
        assert fund_display._fmt_pct(0.15, multiply=True) == "15.0%"
        assert fund_display._fmt_pct(15.0) == "15.0%"

    def test_fmt_ratio_none_and_value(self):
        assert fund_display._fmt_ratio(None) == "—"
        assert fund_display._fmt_ratio(12.345) == "12.3"

    def test_color_change_variants(self):
        assert fund_display._color_change(None) == "—"
        assert "green" in fund_display._color_change(5.2)
        assert "red" in fund_display._color_change(-3.4)
        # Exactly zero — falls into the "white" branch
        assert "white" in fund_display._color_change(0.0)
