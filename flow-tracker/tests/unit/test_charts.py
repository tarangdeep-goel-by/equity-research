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
