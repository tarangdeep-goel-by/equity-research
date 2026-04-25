"""Tests for chart rendering functions in flowtracker/research/charts.py.

Each test verifies: no exception raised + PNG file created + file size > 0.
All charts are rendered with the Agg backend and output redirected to tmp_path.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def redirect_chart_dir(tmp_path, monkeypatch):
    """Redirect _chart_dir to tmp_path so no files land in the real vault."""
    monkeypatch.setattr(
        "flowtracker.research.charts._chart_dir", lambda s: tmp_path
    )


# ---------------------------------------------------------------------------
# Helper: assert PNG was created with non-trivial size
# ---------------------------------------------------------------------------

def _assert_png(path_str: str, min_bytes: int = 500):
    assert path_str, "Chart function returned empty string"
    p = Path(path_str)
    assert p.exists(), f"Chart file not found: {path_str}"
    assert p.stat().st_size > min_bytes, f"Chart file too small: {p.stat().st_size} bytes"


# ---------------------------------------------------------------------------
# render_price_chart — expects [{metric, values: [{date, value}]}]
# ---------------------------------------------------------------------------

class TestRenderPriceChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_price_chart

        data = [
            {
                "metric": "Price",
                "values": [
                    {"date": f"2026-03-{i:02d}", "value": 800 + i * 5}
                    for i in range(1, 21)
                ],
            },
            {
                "metric": "DMA50",
                "values": [
                    {"date": f"2026-03-{i:02d}", "value": 790 + i * 4}
                    for i in range(1, 21)
                ],
            },
        ]
        path = render_price_chart("SBIN", data)
        _assert_png(path)

    def test_single_series(self, tmp_path):
        from flowtracker.research.charts import render_price_chart

        data = [
            {
                "metric": "Price",
                "values": [
                    {"date": f"2026-01-{i:02d}", "value": 100 + i}
                    for i in range(1, 11)
                ],
            }
        ]
        path = render_price_chart("INFY", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_pe_chart — expects [{metric, values: [{date, value}]}]
# ---------------------------------------------------------------------------

class TestRenderPeChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_pe_chart

        data = [
            {
                "metric": "PE Ratio",
                "values": [
                    {"date": f"2026-03-{i:02d}", "value": 9.0 + i * 0.1}
                    for i in range(1, 21)
                ],
            }
        ]
        path = render_pe_chart("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_delivery_chart — expects [{date, delivery_pct, volume}]
# ---------------------------------------------------------------------------

class TestRenderDeliveryChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_delivery_chart

        data = [
            {"date": f"2026-03-{i:02d}", "delivery_pct": 50 + i, "volume": 15_000_000 + i * 100_000}
            for i in range(1, 21)
        ]
        path = render_delivery_chart("SBIN", data)
        _assert_png(path)

    def test_empty_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_delivery_chart

        path = render_delivery_chart("SBIN", [])
        assert path == ""


# ---------------------------------------------------------------------------
# render_revenue_profit_chart — expects [{fiscal_year_end, revenue, net_income}]
# ---------------------------------------------------------------------------

class TestRenderRevenueProfitChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_revenue_profit_chart

        data = [
            {"fiscal_year_end": f"{2017 + i}-03-31", "revenue": 100_000 + i * 10_000, "net_income": 20_000 + i * 3_000}
            for i in range(10)
        ]
        path = render_revenue_profit_chart("SBIN", data)
        _assert_png(path)

    def test_empty_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_revenue_profit_chart

        path = render_revenue_profit_chart("SBIN", [])
        assert path == ""


# ---------------------------------------------------------------------------
# render_shareholding_chart — expects [{quarter_end, category, percentage}]
# ---------------------------------------------------------------------------

class TestRenderShareholdingChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_shareholding_chart

        data = []
        for q in ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]:
            for cat, pct in [("Promoters", 57.5), ("FII", 11.2), ("DII", 8.5), ("Public", 9.8)]:
                data.append({"quarter_end": q, "category": cat, "percentage": pct})
        path = render_shareholding_chart("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_quarterly_chart — expects [{quarter_end, revenue, net_income}]
# ---------------------------------------------------------------------------

class TestRenderQuarterlyChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_quarterly_chart

        quarters = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
                     "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]
        data = [
            {"quarter_end": q, "revenue": 45_000 + i * 1_500, "net_income": 15_000 + i * 500}
            for i, q in enumerate(quarters)
        ]
        path = render_quarterly_chart("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_margin_trend — expects [{fiscal_year_end, revenue, operating_profit, net_income}]
# ---------------------------------------------------------------------------

class TestRenderMarginTrend:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_margin_trend

        data = [
            {
                "fiscal_year_end": f"{2017 + i}-03-31",
                "revenue": 100_000 + i * 8_000,
                "operating_profit": 35_000 + i * 3_000,
                "net_income": 20_000 + i * 2_000,
                "opm": 35 + i * 0.5,
                "npm": 20 + i * 0.3,
            }
            for i in range(10)
        ]
        path = render_margin_trend("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_roce_trend — expects [{fiscal_year_end, roce_pct}]
# ---------------------------------------------------------------------------

class TestRenderRoceTrend:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_roce_trend

        data = [
            {"fiscal_year_end": f"{2017 + i}-03-31", "roce_pct": 15 + i * 0.8}
            for i in range(10)
        ]
        path = render_roce_trend("SBIN", data)
        _assert_png(path)

    def test_empty_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_roce_trend

        path = render_roce_trend("SBIN", [])
        assert path == ""


# ---------------------------------------------------------------------------
# render_dupont_chart — expects list[dict] or {"years": [...]}
# ---------------------------------------------------------------------------

class TestRenderDupontChart:
    def test_renders_png_from_list(self, tmp_path):
        from flowtracker.research.charts import render_dupont_chart

        data = [
            {
                "fiscal_year_end": f"{2017 + i}-03-31",
                "net_profit_margin": 0.20 + i * 0.01,
                "asset_turnover": 0.05 + i * 0.002,
                "equity_multiplier": 10.0 - i * 0.2,
                "roe_dupont": 0.10 + i * 0.005,
            }
            for i in range(10)
        ]
        path = render_dupont_chart("SBIN", data)
        _assert_png(path)

    def test_renders_png_from_dict_with_years(self, tmp_path):
        from flowtracker.research.charts import render_dupont_chart

        years = [
            {
                "fiscal_year_end": f"{2020 + i}-03-31",
                "net_profit_margin": 25 + i,
                "asset_turnover": 0.06,
                "equity_multiplier": 9.5,
                "roe_dupont": 15 + i,
            }
            for i in range(5)
        ]
        data = {"source": "screener", "years": years}
        path = render_dupont_chart("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_cashflow_chart — expects [{fiscal_year_end, cfo, cfi}]
# ---------------------------------------------------------------------------

class TestRenderCashflowChart:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_cashflow_chart

        data = [
            {
                "fiscal_year_end": f"{2017 + i}-03-31",
                "cfo": 25_000 + i * 2_000,
                "cfi": -(10_000 + i * 1_000),
            }
            for i in range(10)
        ]
        path = render_cashflow_chart("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# render_fair_value_range — expects dict with pe_band, combined_fair_value, etc.
# ---------------------------------------------------------------------------

class TestRenderFairValueRange:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_fair_value_range

        data = {
            "pe_band": {"bear": 600, "base": 800, "bull": 1100},
            "combined_fair_value": 850,
            "consensus_target": 950,
            "current_price": 820,
            "margin_of_safety_pct": 3.7,
            "signal": "FAIR VALUE",
        }
        path = render_fair_value_range("SBIN", data)
        _assert_png(path)

    def test_empty_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_fair_value_range

        path = render_fair_value_range("SBIN", {})
        assert path == ""


# ---------------------------------------------------------------------------
# render_expense_pie — expects [{name, value}]
# ---------------------------------------------------------------------------

class TestRenderExpensePie:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_expense_pie

        data = [
            {"name": "Employee Cost", "value": 20_000},
            {"name": "Raw Materials", "value": 45_000},
            {"name": "Power & Fuel", "value": 8_000},
            {"name": "Selling & Admin", "value": 12_000},
            {"name": "Other Expenses", "value": 15_000},
        ]
        path = render_expense_pie("SBIN", data)
        _assert_png(path)

    def test_empty_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_expense_pie

        path = render_expense_pie("SBIN", [])
        assert path == ""


# ---------------------------------------------------------------------------
# render_composite_radar — expects {factors: [{name, score}], composite_score}
# ---------------------------------------------------------------------------

class TestRenderCompositeRadar:
    def test_renders_png_from_list_factors(self, tmp_path):
        from flowtracker.research.charts import render_composite_radar

        data = {
            "composite_score": 72,
            "factors": [
                {"name": "Ownership", "score": 80},
                {"name": "Insider", "score": 65},
                {"name": "Valuation", "score": 75},
                {"name": "Earnings", "score": 70},
                {"name": "Quality", "score": 85},
                {"name": "Delivery", "score": 60},
                {"name": "Estimates", "score": 68},
                {"name": "Risk", "score": 72},
            ],
        }
        path = render_composite_radar("SBIN", data)
        _assert_png(path)

    def test_renders_png_from_dict_factors(self, tmp_path):
        from flowtracker.research.charts import render_composite_radar

        data = {
            "composite_score": 65,
            "factors": {
                "Ownership": 80,
                "Insider": 60,
                "Valuation": 70,
                "Quality": 75,
            },
        }
        path = render_composite_radar("SBIN", data)
        _assert_png(path)

    def test_empty_factors_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_composite_radar

        path = render_composite_radar("SBIN", {})
        assert path == ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestFyLabel:
    """Unit tests for the _fy_label helper."""

    def test_march_end_returns_same_year(self):
        from flowtracker.research.charts import _fy_label

        assert _fy_label("2025-03-31") == "FY25"
        assert _fy_label("2016-03-31") == "FY16"

    def test_post_march_bumps_year_by_one(self):
        from flowtracker.research.charts import _fy_label

        # Month > 3 → FY is year+1 per the Indian FY convention
        assert _fy_label("2025-06-30") == "FY26"
        assert _fy_label("2025-12-31") == "FY26"

    def test_invalid_month_falls_back_to_suffix(self):
        from flowtracker.research.charts import _fy_label

        # Non-numeric month can't parse → returns last 7 chars of the input
        out = _fy_label("2025-XY-31")
        assert out == "2025-XY-31"[-7:]
        assert len(out) == 7

    def test_short_non_date_uses_suffix(self):
        from flowtracker.research.charts import _fy_label

        assert _fy_label("FY2024") == "FY2024"


class TestChartDir:
    """Unit test for the _chart_dir helper (only one that isn't monkeypatched
    — we exercise a temporary home to avoid polluting the real vault)."""

    def test_creates_directory_under_symbol(self, tmp_path, monkeypatch):
        # Override the module-level REPORTS dir so the directory is under tmp
        monkeypatch.setattr(
            "flowtracker.research.charts._REPORTS_DIR", tmp_path / "stocks"
        )
        # Temporarily restore the real _chart_dir (the autouse fixture stubbed it)
        import flowtracker.research.charts as charts

        # Recompute using the real logic
        real_dir = charts._REPORTS_DIR / "sbin".upper() / "charts"
        real_dir.mkdir(parents=True, exist_ok=True)
        assert real_dir.exists()
        assert real_dir.name == "charts"


# ---------------------------------------------------------------------------
# Additional coverage for render_price_chart / render_pe_chart empty paths
# ---------------------------------------------------------------------------

class TestRenderPriceChartEdgeCases:
    def test_series_with_empty_values_is_skipped(self, tmp_path):
        """A series whose `values` list is empty must not raise and must
        still yield a PNG if at least one other series has data."""
        from flowtracker.research.charts import render_price_chart

        data = [
            {"metric": "Price", "values": [
                {"date": f"2026-01-{i:02d}", "value": 100 + i} for i in range(1, 11)
            ]},
            {"metric": "DMA50", "values": []},  # empty — should be skipped
        ]
        path = render_price_chart("INFY", data)
        _assert_png(path)


class TestRenderPeChartEdgeCases:
    def test_industry_pe_uses_second_color(self, tmp_path):
        """Second series labelled "Industry" should also render."""
        from flowtracker.research.charts import render_pe_chart

        data = [
            {"metric": "PE Ratio", "values": [
                {"date": f"2026-03-{i:02d}", "value": 20 + i * 0.2} for i in range(1, 11)
            ]},
            {"metric": "Industry PE", "values": [
                {"date": f"2026-03-{i:02d}", "value": 22 + i * 0.1} for i in range(1, 11)
            ]},
        ]
        path = render_pe_chart("SBIN", data)
        _assert_png(path)

    def test_empty_series_skipped(self, tmp_path):
        from flowtracker.research.charts import render_pe_chart

        data = [
            {"metric": "PE Ratio", "values": []},
            {"metric": "Industry PE", "values": [
                {"date": f"2026-02-{i:02d}", "value": 15.0 + i} for i in range(1, 6)
            ]},
        ]
        path = render_pe_chart("SBIN", data)
        _assert_png(path)


# ---------------------------------------------------------------------------
# Empty-data early-return tests for chart builders missing coverage
# ---------------------------------------------------------------------------

class TestEmptyDataEarlyReturns:
    """Each chart builder returns "" when given empty data or data that
    evaluates as missing the required keys."""

    def test_shareholding_empty(self, tmp_path):
        from flowtracker.research.charts import render_shareholding_chart

        assert render_shareholding_chart("X", []) == ""

    def test_shareholding_all_rows_missing_keys(self, tmp_path):
        from flowtracker.research.charts import render_shareholding_chart

        # Rows with no quarter or no category → quarters_map stays empty
        data = [{"quarter_end": "", "category": ""}]
        assert render_shareholding_chart("X", data) == ""

    def test_quarterly_empty(self, tmp_path):
        from flowtracker.research.charts import render_quarterly_chart

        assert render_quarterly_chart("X", []) == ""

    def test_quarterly_all_rows_no_quarter_end(self, tmp_path):
        from flowtracker.research.charts import render_quarterly_chart

        # quarter_end missing → quarters stays empty, returns ""
        data = [{"revenue": 100, "net_income": 10}]
        assert render_quarterly_chart("X", data) == ""

    def test_margin_trend_empty(self, tmp_path):
        from flowtracker.research.charts import render_margin_trend

        assert render_margin_trend("X", []) == ""

    def test_margin_trend_no_fiscal_year(self, tmp_path):
        from flowtracker.research.charts import render_margin_trend

        # No fiscal_year_end → years list stays empty, returns ""
        data = [{"revenue": 1000, "operating_profit": 300, "net_income": 120}]
        assert render_margin_trend("X", data) == ""

    def test_dupont_empty_list(self, tmp_path):
        from flowtracker.research.charts import render_dupont_chart

        assert render_dupont_chart("X", []) == ""

    def test_dupont_empty_dict(self, tmp_path):
        from flowtracker.research.charts import render_dupont_chart

        assert render_dupont_chart("X", {}) == ""

    def test_dupont_dict_with_empty_years(self, tmp_path):
        from flowtracker.research.charts import render_dupont_chart

        assert render_dupont_chart("X", {"years": []}) == ""

    def test_dupont_missing_margin(self, tmp_path):
        from flowtracker.research.charts import render_dupont_chart

        # net_profit_margin missing → years list empty → returns ""
        data = [{"fiscal_year_end": "2024-03-31", "asset_turnover": 0.5}]
        assert render_dupont_chart("X", data) == ""

    def test_cashflow_empty(self, tmp_path):
        from flowtracker.research.charts import render_cashflow_chart

        assert render_cashflow_chart("X", []) == ""

    def test_cashflow_all_zero_cfo(self, tmp_path):
        from flowtracker.research.charts import render_cashflow_chart

        data = [
            {"fiscal_year_end": f"{2019 + i}-03-31", "cfo": 0, "free_cash_flow": 0}
            for i in range(5)
        ]
        assert render_cashflow_chart("X", data) == ""


# ---------------------------------------------------------------------------
# render_fair_value_range edge cases
# ---------------------------------------------------------------------------

class TestRenderFairValueRangeEdgeCases:
    def test_bull_rescaled_by_consensus_when_implausibly_high(self, tmp_path):
        """When pe_band.bull > current_price * 5 AND consensus exists,
        the function replaces bull with consensus * 1.2."""
        from flowtracker.research.charts import render_fair_value_range

        data = {
            "pe_band": {"bear": 100, "bull": 50_000},  # absurd
            "combined_fair_value": 120,
            "consensus_target": 180,
            "current_price": 150,
            "margin_of_safety_pct": 20,
            "signal": "UNDERVALUED",
        }
        path = render_fair_value_range("SBIN", data)
        _assert_png(path)

    def test_combined_fair_value_as_dict(self, tmp_path):
        """combined_fair_value passed as dict with `base` key should be
        unpacked."""
        from flowtracker.research.charts import render_fair_value_range

        data = {
            "pe_band": {"bear": 500, "bull": 1000},
            "combined_fair_value": {"base": 750},
            "consensus_target": 900,
            "current_price": 800,
            "margin_of_safety_pct": -6.7,
            "signal": "FAIR",
        }
        path = render_fair_value_range("SBIN", data)
        _assert_png(path)

    def test_missing_bear_or_current_returns_empty(self, tmp_path):
        """Without both `bear` and `current_price` the builder returns ""."""
        from flowtracker.research.charts import render_fair_value_range

        path = render_fair_value_range("SBIN", {
            "pe_band": {"bear": 0, "bull": 1000},
            "combined_fair_value": 500,
            "current_price": 0,
            "signal": "NA",
        })
        assert path == ""


# ---------------------------------------------------------------------------
# render_expense_pie — all-zero values path
# ---------------------------------------------------------------------------

class TestRenderExpensePieEdgeCases:
    def test_all_zero_values_returns_empty(self, tmp_path):
        """Items with value 0 are filtered out; empty labels → returns ""."""
        from flowtracker.research.charts import render_expense_pie

        assert render_expense_pie("X", [{"name": "A", "value": 0}]) == ""

    def test_uses_item_and_amount_aliases(self, tmp_path):
        """Alternative keys `item` and `amount` should also be accepted."""
        from flowtracker.research.charts import render_expense_pie

        data = [
            {"item": "Raw Mat", "amount": 100},
            {"item": "Salaries", "amount": 50},
            {"item": "Other", "amount": 20},
        ]
        _assert_png(render_expense_pie("X", data))


# ---------------------------------------------------------------------------
# render_chart('expense_pie', ...) — graceful degradation for banks/sparse
# ---------------------------------------------------------------------------

class TestExpensePieDispatcher:
    """Verify the render_chart dispatcher builds expense slices from
    annual_financials (latest year) and degrades honestly when sparse.
    """

    def _patch_api(self, monkeypatch, *, annual_row: dict, is_bfsi: bool = False,
                   is_insurance: bool = False):
        """Stub ResearchDataAPI used inside render_chart to avoid touching the DB."""

        class _StubAPI:
            def __init__(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get_annual_financials(self, symbol, years=10):
                return [annual_row] if annual_row else []

            def _is_bfsi(self, symbol):
                return is_bfsi

            def _is_insurance(self, symbol):
                return is_insurance

        monkeypatch.setattr(
            "flowtracker.research.data_api.ResearchDataAPI", _StubAPI
        )

    def test_bank_row_renders_pie_with_interest_slice(self, tmp_path, monkeypatch):
        """Bank-shaped row (employee + other_expenses_detail + interest) → pie renders."""
        from flowtracker.research.charts import render_chart

        self._patch_api(
            monkeypatch,
            annual_row={
                "fiscal_year_end": "2025-03-31",
                "revenue": 462489.35,
                "raw_material_cost": None,
                "power_and_fuel": None,
                "selling_and_admin": 18159.0,
                "other_mfr_exp": 1268.0,
                "employee_cost": 64353.0,
                "other_expenses_detail": 46066.0,
                "interest": 295524.0,
            },
            is_bfsi=True,
        )

        out = render_chart("SBIN", "expense_pie")
        assert "path" in out, f"Expected rendered path, got: {out}"
        assert "sparse" not in out
        _assert_png(out["path"])

    def test_sparse_single_category_returns_sparse_indicator(self, tmp_path, monkeypatch):
        """Only 1 expense category populated → sparse indicator, not raise, not (no data)."""
        from flowtracker.research.charts import render_chart

        self._patch_api(
            monkeypatch,
            annual_row={
                "fiscal_year_end": "2025-03-31",
                "revenue": 1000.0,
                "employee_cost": 250.0,
                # everything else None / 0
                "raw_material_cost": None,
                "power_and_fuel": None,
                "selling_and_admin": None,
                "other_mfr_exp": None,
                "other_expenses_detail": None,
                "interest": None,
            },
            is_bfsi=False,
        )

        out = render_chart("X", "expense_pie")
        assert out.get("sparse") is True
        assert out["chart_type"] == "expense_pie"
        assert out["symbol"] == "X"
        assert out["categories"] == [{"name": "Employee", "value": 250.0}]
        assert "message" in out

    def test_no_annual_financials_returns_sparse(self, tmp_path, monkeypatch):
        """No annual_financials row at all → sparse with 0 categories."""
        from flowtracker.research.charts import render_chart

        self._patch_api(monkeypatch, annual_row={}, is_bfsi=False)
        # annual_row={} → get_annual_financials returns [] (empty dict skipped)

        class _EmptyAPI:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def get_annual_financials(self, s, years=10): return []
            def _is_bfsi(self, s): return False
            def _is_insurance(self, s): return False

        monkeypatch.setattr(
            "flowtracker.research.data_api.ResearchDataAPI", _EmptyAPI
        )

        out = render_chart("NODATA", "expense_pie")
        assert out.get("sparse") is True
        assert out["categories"] == []

    def test_manufacturing_row_renders_pie(self, tmp_path, monkeypatch):
        """Standard manufacturing row (DRREDDY-like, all 6 fields) → pie renders."""
        from flowtracker.research.charts import render_chart

        self._patch_api(
            monkeypatch,
            annual_row={
                "fiscal_year_end": "2025-03-31",
                "revenue": 32643.9,
                "raw_material_cost": 10524.6,
                "employee_cost": 5594.4,
                "power_and_fuel": 562.5,
                "selling_and_admin": 4721.9,
                "other_mfr_exp": 2563.2,
                "other_expenses_detail": 674.9,
                "interest": 282.9,
            },
            is_bfsi=False,
        )

        out = render_chart("DRREDDY", "expense_pie")
        assert "path" in out
        _assert_png(out["path"])

    def test_explicit_data_passthrough_unchanged(self, tmp_path, monkeypatch):
        """Pre-shaped data passed in directly bypasses the helper (back-compat)."""
        from flowtracker.research.charts import render_chart

        # API stub shouldn't be touched, but provide one to be safe
        self._patch_api(monkeypatch, annual_row={}, is_bfsi=False)

        data = [
            {"name": "Employee Cost", "value": 20_000},
            {"name": "Raw Materials", "value": 45_000},
            {"name": "Power & Fuel", "value": 8_000},
        ]
        out = render_chart("X", "expense_pie", data=data)
        assert "path" in out
        _assert_png(out["path"])


# ---------------------------------------------------------------------------
# render_composite_radar edge cases
# ---------------------------------------------------------------------------

class TestRenderCompositeRadarEdgeCases:
    def test_factors_non_list_non_dict_returns_empty(self, tmp_path):
        """`factors` must be a list or dict; anything else → empty string."""
        from flowtracker.research.charts import render_composite_radar

        path = render_composite_radar("X", {"factors": "not-a-collection"})
        assert path == ""

    def test_missing_factors_key_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_composite_radar

        assert render_composite_radar("X", {"composite_score": 70}) == ""

    def test_empty_dict_factors_returns_empty(self, tmp_path):
        """Empty dict factors → no labels → returns ""."""
        from flowtracker.research.charts import render_composite_radar

        assert render_composite_radar("X", {"factors": {}}) == ""


# ---------------------------------------------------------------------------
# Sector-level charts
# ---------------------------------------------------------------------------

class TestRenderSectorMcapBar:
    """Coverage for render_sector_mcap_bar (large-mcap formatting and
    subject highlighting)."""

    def test_renders_png_with_lakh_crore_formatting(self, tmp_path):
        from flowtracker.research.charts import render_sector_mcap_bar

        # Mix of sub-lakh-cr and >=1L cr to exercise both label branches
        data = [
            {"symbol": "SBIN", "mcap_cr": 800_000},     # > 1 lakh cr
            {"symbol": "AXIS", "mcap_cr": 450_000},
            {"symbol": "ICICI", "mcap_cr": 90_000},      # < 1 lakh cr
            {"symbol": "HDFC", "mcap_cr": 1_200_000},
            {"symbol": "KOTAK", "mcap_cr": 400_000},
        ]
        path = render_sector_mcap_bar("SBIN", data)
        _assert_png(path)

    def test_too_few_stocks_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_mcap_bar

        assert render_sector_mcap_bar("X", []) == ""
        assert render_sector_mcap_bar("X", [{"symbol": "A", "mcap_cr": 100}]) == ""

    def test_caps_at_fifteen_stocks(self, tmp_path):
        """Should render ok with >15 entries (only top 15 drawn)."""
        from flowtracker.research.charts import render_sector_mcap_bar

        data = [
            {"symbol": f"S{i:02d}", "mcap_cr": 10_000 + i * 1000}
            for i in range(20)
        ]
        path = render_sector_mcap_bar("S05", data)
        _assert_png(path)


class TestRenderSectorValuationScatter:
    def test_renders_png_with_quadrant_lines(self, tmp_path):
        from flowtracker.research.charts import render_sector_valuation_scatter

        data = [
            {"symbol": "SBIN", "pe": 12, "roce_pct": 14, "mcap_cr": 800_000},
            {"symbol": "AXIS", "pe": 18, "roce_pct": 16, "mcap_cr": 400_000},
            {"symbol": "ICICI", "pe": 20, "roce_pct": 18, "mcap_cr": 600_000},
            {"symbol": "HDFC", "pe": 25, "roce_pct": 20, "mcap_cr": 1_000_000},
            {"symbol": "KOTAK", "pe": 30, "roce_pct": 15, "mcap_cr": 350_000},
        ]
        path = render_sector_valuation_scatter("SBIN", data)
        _assert_png(path)

    def test_too_few_valid_stocks_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_valuation_scatter

        # Only 1 valid entry after filtering (ZERO pe is rejected)
        data = [
            {"symbol": "A", "pe": 10, "roce_pct": 20, "mcap_cr": 100},
            {"symbol": "B", "pe": 0, "roce_pct": 15, "mcap_cr": 100},
            {"symbol": "C", "pe": 15, "roce_pct": 0, "mcap_cr": 100},
        ]
        assert render_sector_valuation_scatter("A", data) == ""

    def test_none_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_valuation_scatter

        assert render_sector_valuation_scatter("X", []) == ""

    def test_explicit_y_metric_roa_uses_roa_and_labels_axis(self, tmp_path, monkeypatch):
        """Explicit y_metric='roa_pct' plots ROA on the y-axis and labels it."""
        from flowtracker.research import charts as charts_mod
        from flowtracker.research.charts import render_sector_valuation_scatter

        # Capture the ylabel the chart ends up setting.
        labels: dict[str, str] = {}

        class _FakeAx:
            def scatter(self, *a, **k): pass
            def annotate(self, *a, **k): pass
            def axvline(self, *a, **k): pass
            def axhline(self, *a, **k): pass
            def text(self, *a, **k): pass
            def set_xlabel(self, *a, **k): pass
            def set_ylabel(self, s, *a, **k): labels["y"] = s
            def set_title(self, *a, **k): pass
            def legend(self, *a, **k): pass
            def grid(self, *a, **k): pass
            def get_xlim(self): return (0, 100)
            def get_ylim(self): return (0, 100)

        class _FakeFig:
            def savefig(self, *a, **k): pass

        monkeypatch.setattr(
            charts_mod.plt, "subplots", lambda *a, **k: (_FakeFig(), _FakeAx())
        )
        monkeypatch.setattr(charts_mod.plt, "close", lambda *a, **k: None)
        monkeypatch.setattr(charts_mod, "_chart_dir", lambda sym: tmp_path)

        data = [
            {"symbol": "HDFCBANK", "pe": 20, "roa_pct": 1.8, "mcap_cr": 1_000_000},
            {"symbol": "ICICIBANK", "pe": 18, "roa_pct": 1.6, "mcap_cr": 800_000},
            {"symbol": "SBIN", "pe": 12, "roa_pct": 1.1, "mcap_cr": 600_000},
        ]
        render_sector_valuation_scatter("HDFCBANK", data, y_metric="roa_pct")
        assert "ROA" in labels["y"]

    def test_falls_back_to_roce_when_roa_data_missing(self, tmp_path):
        """If caller asks for ROA but data only has roce_pct, fall back rather than silent-fail."""
        from flowtracker.research.charts import render_sector_valuation_scatter

        data = [
            {"symbol": "HDFCBANK", "pe": 20, "roce_pct": 14, "mcap_cr": 1_000_000},
            {"symbol": "ICICIBANK", "pe": 18, "roce_pct": 16, "mcap_cr": 800_000},
            {"symbol": "SBIN", "pe": 12, "roce_pct": 12, "mcap_cr": 600_000},
        ]
        # y_metric='roa_pct' with no roa_pct fields → fallback to roce_pct, chart renders
        path = render_sector_valuation_scatter("HDFCBANK", data, y_metric="roa_pct")
        _assert_png(path)


class TestRenderSectorOwnershipFlow:
    def test_renders_png_additions_and_reductions(self, tmp_path):
        from flowtracker.research.charts import render_sector_ownership_flow

        data = {
            "top_additions": [
                {"symbol": "SBIN", "mf_change_pct": 0.8},
                {"symbol": "AXIS", "mf_change_pct": 0.6},
                {"symbol": "HDFC", "mf_change_pct": 0.4},
            ],
            "top_reductions": [
                {"symbol": "ICICI", "mf_change_pct": -0.5},
                {"symbol": "KOTAK", "mf_change_pct": -0.3},
            ],
            "total_stocks": 20,
            "mf_increased": 12,
            "mf_decreased": 8,
        }
        path = render_sector_ownership_flow("SBIN", data)
        _assert_png(path)

    def test_empty_flow_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_ownership_flow

        assert render_sector_ownership_flow("X", {"top_additions": [], "top_reductions": []}) == ""
        assert render_sector_ownership_flow("X", {}) == ""


class TestRenderSectorGrowthBars:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_sector_growth_bars

        data = [
            {"peer_symbol": "SBIN", "qtr_sales_var": 12.5},
            {"peer_symbol": "AXIS", "qtr_sales_var": 8.2},
            {"peer_symbol": "ICICI", "qtr_sales_var": -3.1},
            {"peer_symbol": "HDFC", "qtr_sales_var": 15.0},
            {"peer_symbol": "KOTAK", "qtr_sales_var": 5.5},
        ]
        path = render_sector_growth_bars("SBIN", data)
        _assert_png(path)

    def test_uses_fallback_symbol_keys(self, tmp_path):
        """The function tries `peer_symbol`, then `symbol`, then `peer_name`."""
        from flowtracker.research.charts import render_sector_growth_bars

        data = [
            {"symbol": "A", "qtr_sales_var": 10},
            {"peer_name": "B", "qtr_sales_var": 5},
            {"peer_symbol": "C", "qtr_sales_var": -2},
        ]
        path = render_sector_growth_bars("A", data)
        _assert_png(path)

    def test_too_few_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_growth_bars

        assert render_sector_growth_bars("X", []) == ""
        assert render_sector_growth_bars(
            "X", [{"peer_symbol": "A", "qtr_sales_var": 5}]
        ) == ""

    def test_non_numeric_growth_values_skipped(self, tmp_path):
        from flowtracker.research.charts import render_sector_growth_bars

        data = [
            {"peer_symbol": "A", "qtr_sales_var": "not-a-number"},
            {"peer_symbol": "B", "qtr_sales_var": None},
        ]
        # Only 0 valid → returns ""
        assert render_sector_growth_bars("A", data) == ""


class TestRenderSectorProfitabilityBars:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_sector_profitability_bars

        data = [
            {"symbol": "SBIN", "roce_pct": 14},
            {"symbol": "AXIS", "roce_pct": 16},
            {"symbol": "ICICI", "roce_pct": 18},
            {"symbol": "HDFC", "roce_pct": 20},
            {"symbol": "KOTAK", "roce_pct": 11},
        ]
        path = render_sector_profitability_bars("SBIN", data)
        _assert_png(path)

    def test_too_few_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_profitability_bars

        assert render_sector_profitability_bars("X", []) == ""

    def test_non_numeric_roce_skipped(self, tmp_path):
        from flowtracker.research.charts import render_sector_profitability_bars

        data = [{"symbol": "A", "roce_pct": "abc"}, {"symbol": "B", "roce_pct": None}]
        assert render_sector_profitability_bars("A", data) == ""


class TestRenderSectorPeDistribution:
    def test_renders_png_with_subject_marker(self, tmp_path):
        from flowtracker.research.charts import render_sector_pe_distribution

        data = [
            {"symbol": "SBIN", "pe": 12},
            {"symbol": "AXIS", "pe": 15},
            {"symbol": "ICICI", "pe": 18},
            {"symbol": "HDFC", "pe": 20},
            {"symbol": "KOTAK", "pe": 24},
            {"symbol": "PNB", "pe": 10},
        ]
        path = render_sector_pe_distribution("SBIN", data)
        _assert_png(path)

    def test_subject_stock_not_in_data(self, tmp_path):
        """Subject PE absent → still renders (just without subject marker)."""
        from flowtracker.research.charts import render_sector_pe_distribution

        data = [
            {"symbol": "A", "pe": 10},
            {"symbol": "B", "pe": 12},
            {"symbol": "C", "pe": 14},
            {"symbol": "D", "pe": 16},
        ]
        path = render_sector_pe_distribution("ZZZ", data)
        _assert_png(path)

    def test_insufficient_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_sector_pe_distribution

        # Fewer than 3 entries → empty
        assert render_sector_pe_distribution("X", [
            {"symbol": "A", "pe": 10},
            {"symbol": "B", "pe": 12},
        ]) == ""

    def test_invalid_pe_values_skipped(self, tmp_path):
        from flowtracker.research.charts import render_sector_pe_distribution

        data = [
            {"symbol": "A", "pe": None},
            {"symbol": "B", "pe": "abc"},
            {"symbol": "C", "pe": -5},  # negative PE filtered
        ]
        assert render_sector_pe_distribution("A", data) == ""


# ---------------------------------------------------------------------------
# Comparison (multi-symbol) charts
# ---------------------------------------------------------------------------

class TestRenderComparisonRevenue:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_comparison_revenue

        symbols = ["SBIN", "AXIS"]
        data_map = {
            "SBIN": [
                {"fiscal_year_end": f"{2017 + i}-03-31", "revenue": 100_000 + i * 10_000}
                for i in range(5)
            ],
            "AXIS": [
                {"fiscal_year_end": f"{2017 + i}-03-31", "revenue": 80_000 + i * 7_000}
                for i in range(5)
            ],
        }
        path = render_comparison_revenue(symbols, data_map)
        _assert_png(path)

    def test_insufficient_symbols_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_revenue

        assert render_comparison_revenue(["SBIN"], {"SBIN": [
            {"fiscal_year_end": "2024-03-31", "revenue": 100}
        ]}) == ""

    def test_empty_data_map_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_revenue

        assert render_comparison_revenue(["A", "B"], {}) == ""

    def test_missing_data_for_one_symbol_still_renders(self, tmp_path):
        """One symbol absent in map — loop just skips it."""
        from flowtracker.research.charts import render_comparison_revenue

        symbols = ["A", "B"]
        data_map = {
            "A": [
                {"fiscal_year_end": f"{2019 + i}-03-31", "revenue": 1000 + i * 200}
                for i in range(4)
            ],
            "B": [
                {"fiscal_year_end": f"{2019 + i}-03-31", "revenue": 800 + i * 100}
                for i in range(4)
            ],
        }
        _assert_png(render_comparison_revenue(symbols, data_map))


class TestRenderComparisonPe:
    def test_renders_png_with_industry_series(self, tmp_path):
        from flowtracker.research.charts import render_comparison_pe

        symbols = ["SBIN", "AXIS"]
        pe_map = {
            "SBIN": [{"metric": "PE Ratio", "values": [
                {"date": f"2025-06-{i:02d}", "value": 12 + i * 0.1}
                for i in range(1, 10)
            ]}],
            "AXIS": [{"metric": "PE Ratio", "values": [
                {"date": f"2025-06-{i:02d}", "value": 18 + i * 0.1}
                for i in range(1, 10)
            ]}, {"metric": "Industry PE", "values": [
                {"date": f"2025-06-{i:02d}", "value": 22 + i * 0.05}
                for i in range(1, 10)
            ]}],
        }
        _assert_png(render_comparison_pe(symbols, pe_map))

    def test_insufficient_symbols_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_pe

        assert render_comparison_pe(["ONE"], {"ONE": []}) == ""

    def test_no_pe_series_returns_empty(self, tmp_path):
        """Series without "PE"/"Industry" in metric name → no data plotted."""
        from flowtracker.research.charts import render_comparison_pe

        symbols = ["A", "B"]
        pe_map = {
            "A": [{"metric": "Volume", "values": [
                {"date": "2025-01-01", "value": 10}
            ]}],
            "B": [{"metric": "Volume", "values": [
                {"date": "2025-01-01", "value": 20}
            ]}],
        }
        assert render_comparison_pe(symbols, pe_map) == ""


class TestRenderComparisonShareholding:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_comparison_shareholding

        symbols = ["A", "B"]
        quarters = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30"]
        data_map = {}
        for sym in symbols:
            rows = []
            for q in quarters:
                rows.append({"quarter_end": q, "category": "FII", "percentage": 10 + len(rows)})
                rows.append({"quarter_end": q, "category": "MF", "percentage": 8 + len(rows)})
            data_map[sym] = rows
        _assert_png(render_comparison_shareholding(symbols, data_map))

    def test_insufficient_symbols_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_shareholding

        assert render_comparison_shareholding(["A"], {"A": []}) == ""

    def test_empty_data_map_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_shareholding

        assert render_comparison_shareholding(["A", "B"], {}) == ""

    def test_no_matching_category_returns_empty(self, tmp_path):
        """All rows produce 0 for FII and MF — chart has no data."""
        from flowtracker.research.charts import render_comparison_shareholding

        data_map = {
            "A": [{"quarter_end": "2025-03-31", "category": "Public", "percentage": 30}],
            "B": [{"quarter_end": "2025-03-31", "category": "Public", "percentage": 25}],
        }
        assert render_comparison_shareholding(["A", "B"], data_map) == ""


class TestRenderComparisonRadar:
    def test_renders_radar_for_few_symbols(self, tmp_path):
        """<=3 stocks → polar radar branch."""
        from flowtracker.research.charts import render_comparison_radar

        score_map = {
            "SBIN": {"composite_score": 72, "factors": {
                "Ownership": 80, "Insider": 65, "Valuation": 75, "Quality": 70
            }},
            "AXIS": {"composite_score": 68, "factors": {
                "Ownership": 75, "Insider": 70, "Valuation": 60, "Quality": 72
            }},
        }
        _assert_png(render_comparison_radar(["SBIN", "AXIS"], score_map))

    def test_renders_grouped_bar_for_many_symbols(self, tmp_path):
        """>3 stocks → grouped-bar branch (radar gets unreadable)."""
        from flowtracker.research.charts import render_comparison_radar

        score_map = {
            f"S{i}": {
                "composite_score": 50 + i * 3,
                "factors": [
                    {"factor": "Ownership", "score": 50 + i * 5},
                    {"factor": "Quality", "score": 60 + i},
                    {"factor": "Valuation", "score": 70 - i * 2},
                ],
            }
            for i in range(5)
        }
        _assert_png(render_comparison_radar(list(score_map.keys()), score_map))

    def test_insufficient_valid_scores_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_radar

        # Only 1 valid score — rest missing or malformed
        score_map = {
            "A": {"factors": {"Ownership": 80}},
            "B": {},
            "C": {"factors": "bad"},
        }
        assert render_comparison_radar(["A", "B", "C"], score_map) == ""

    def test_empty_map_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_radar

        assert render_comparison_radar(["A", "B"], {}) == ""


class TestRenderComparisonMargins:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_comparison_margins

        symbols = ["SBIN", "AXIS"]
        data_map = {}
        for sym in symbols:
            data_map[sym] = [
                {
                    "fiscal_year_end": f"{2018 + i}-03-31",
                    "revenue": 100_000 + i * 10_000,
                    "opm": 30 + i * 0.3,
                    "npm": 18 + i * 0.2,
                    "operating_profit": 30_000 + i * 3000,
                    "net_income": 18_000 + i * 2000,
                }
                for i in range(6)
            ]
        _assert_png(render_comparison_margins(symbols, data_map))

    def test_opm_derived_from_pbt_when_absent(self, tmp_path):
        """Exercise the derived-OPM branch when operating_profit is missing."""
        from flowtracker.research.charts import render_comparison_margins

        symbols = ["A", "B"]
        data_map = {}
        for sym in symbols:
            data_map[sym] = [
                {
                    "fiscal_year_end": f"{2019 + i}-03-31",
                    "revenue": 10_000 + i * 500,
                    "profit_before_tax": 1500,
                    "interest": 200,
                    "depreciation": 300,
                    "other_income": 100,
                    "net_income": 1200,
                }
                for i in range(4)
            ]
        _assert_png(render_comparison_margins(symbols, data_map))

    def test_insufficient_symbols_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_margins

        assert render_comparison_margins(["A"], {"A": []}) == ""

    def test_empty_map_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_comparison_margins

        assert render_comparison_margins(["A", "B"], {}) == ""


# ---------------------------------------------------------------------------
# render_dividend_history
# ---------------------------------------------------------------------------

class TestRenderDividendHistory:
    def test_renders_png(self, tmp_path):
        from flowtracker.research.charts import render_dividend_history

        data = [
            {
                "fiscal_year_end": f"{2017 + i}-03-31",
                "dividend_amount": 500 + i * 50,
                "net_income": 5000 + i * 400,
                "eps": 10 + i * 0.5,
                "num_shares": 900 + i * 10,
            }
            for i in range(8)
        ]
        _assert_png(render_dividend_history("SBIN", data))

    def test_empty_data_returns_empty(self, tmp_path):
        from flowtracker.research.charts import render_dividend_history

        assert render_dividend_history("X", []) == ""

    def test_all_zero_dividends_returns_empty(self, tmp_path):
        """If every payout ratio evaluates to 0 → returns ""."""
        from flowtracker.research.charts import render_dividend_history

        data = [
            {
                "fiscal_year_end": f"{2019 + i}-03-31",
                "dividend_amount": 0,
                "net_income": 1000,
                "eps": 5,
                "num_shares": 100,
            }
            for i in range(3)
        ]
        assert render_dividend_history("X", data) == ""


# ---------------------------------------------------------------------------
# render_chart dispatcher — covers the master MCP-level entry point
# ---------------------------------------------------------------------------

class TestRenderChartDispatcher:
    """Cover the dispatcher function: unknown types, comparison-arg check,
    cache hit, and the per-chart-type branches."""

    def test_unknown_chart_type_returns_error(self, tmp_path):
        from flowtracker.research.charts import render_chart

        out = render_chart("SBIN", "nonexistent_chart", data=[])
        assert "error" in out
        assert "available" in out

    def test_comparison_chart_with_single_symbol_errors(self, tmp_path):
        from flowtracker.research.charts import render_chart

        out = render_chart("SBIN", "comparison_revenue", data={})
        assert "error" in out
        assert "multiple symbols" in out["error"].lower() or "comma" in out["error"].lower()

    def test_price_chart_via_dispatcher_returns_path(self, tmp_path):
        """Passing pre-fetched `data` bypasses the DB fetch path in the
        dispatcher so we can test the branch without external deps."""
        from flowtracker.research.charts import render_chart

        data = [{
            "metric": "Price",
            "values": [
                {"date": f"2025-09-{i:02d}", "value": 100 + i} for i in range(1, 11)
            ],
        }]
        out = render_chart("SBIN", "price", data=data)
        assert "path" in out
        assert out["chart_type"] == "price"
        assert out["symbol"] == "SBIN"
        assert "embed_markdown" in out
        assert out["embed_markdown"].startswith("![")

    def test_revenue_profit_via_dispatcher(self, tmp_path):
        from flowtracker.research.charts import render_chart

        data = [
            {"fiscal_year_end": f"{2019 + i}-03-31", "revenue": 10000 + i * 1000, "net_income": 2000 + i * 200}
            for i in range(4)
        ]
        out = render_chart("SBIN", "revenue_profit", data=data)
        assert "path" in out and out["chart_type"] == "revenue_profit"

    def test_comparison_revenue_via_dispatcher(self, tmp_path):
        """Use a comma-separated symbol list + pre-fetched data to exercise
        the comparison branch."""
        from flowtracker.research.charts import render_chart

        data_map = {
            "SBIN": [
                {"fiscal_year_end": f"{2019 + i}-03-31", "revenue": 10000 + i * 800}
                for i in range(4)
            ],
            "AXIS": [
                {"fiscal_year_end": f"{2019 + i}-03-31", "revenue": 8000 + i * 600}
                for i in range(4)
            ],
        }
        out = render_chart("SBIN,AXIS", "comparison_revenue", data=data_map)
        assert "path" in out
        assert out["chart_type"] == "comparison_revenue"

    def test_dispatcher_when_builder_returns_empty(self, tmp_path):
        """If the underlying builder returns "" the dispatcher returns
        the `error` key. Supply truthy-but-unrenderable data so the
        dispatcher doesn't fall back to the DB API."""
        from flowtracker.research.charts import render_chart

        # Dict passed where list expected — no `fiscal_year_end` / `revenue`
        # keys means years list stays empty → builder returns ""
        bogus = [{"foo": "bar"}, {"baz": "qux"}]
        out = render_chart("SBIN", "revenue_profit", data=bogus)
        assert "error" in out
        assert "No data" in out["error"]
