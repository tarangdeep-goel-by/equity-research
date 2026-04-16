"""Tests for research/data_collector.py.

Covers:
    - apply_screener_charts() — pure dict mutation (pe_chart, price_chart,
      median PE extraction, price_vals backfill, dma/volume parsing, missing
      fields and empty-input branches).
    - collect_fundamentals_data() — end-to-end DB read against a populated
      FlowStore, plus empty-store path. FLOWTRACKER_DB is monkeypatched so
      the hard-coded FlowStore() in the function picks up the test db.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_collector import (
    apply_screener_charts,
    collect_fundamentals_data,
)
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers — screener chart payloads (shape mirrors real Screener API responses)
# ---------------------------------------------------------------------------

def _make_pe_chart(n: int = 3, median: float | None = 12.5) -> dict:
    """Build a mock Screener pe_chart payload with N date/PE points.

    Real shape: {"PE": [[date, pe], ...], "Median PE = 12.5": [[...]], ...}.
    """
    pe_points = [[f"2026-01-{i+1:02d}", 10.0 + i] for i in range(n)]
    payload: dict = {"PE": pe_points}
    if median is not None:
        payload[f"Median PE = {median}"] = [
            [p[0], median] for p in pe_points
        ]
    return payload


def _make_price_chart(n: int = 3, with_dma: bool = True, with_vol: bool = True) -> dict:
    """Build a mock Screener price_chart payload.

    Keys loosely include "Price", "50 DMA", "200 DMA", "Volume" substrings
    — matches the loose substring matching in apply_screener_charts.
    """
    dates = [f"2026-01-{i+1:02d}" for i in range(n)]
    payload: dict = {
        "Price": [[d, 800.0 + i * 10] for i, d in enumerate(dates)],
    }
    if with_dma:
        payload["50 DMA"] = [[d, 810.0 + i * 5] for i, d in enumerate(dates)]
        payload["200 DMA"] = [[d, 790.0 + i * 2] for i, d in enumerate(dates)]
    if with_vol:
        payload["Volume"] = [[d, 1500000 + i * 10000] for i, d in enumerate(dates)]
    return payload


# ===========================================================================
# apply_screener_charts — pure dict mutation, no DB required
# ===========================================================================

class TestApplyScreenerCharts:
    """apply_screener_charts(data) — in-place mutation of a data dict."""

    def test_populates_pe_chart_from_screener(self):
        """Given a PE payload, pe_chart dates/pe_vals are populated."""
        data = {"screener_charts": {"pe_chart": _make_pe_chart(n=3)}}
        apply_screener_charts(data)

        assert "pe_chart" in data
        assert data["pe_chart"]["dates"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
        assert data["pe_chart"]["pe_vals"] == [10.0, 11.0, 12.0]
        # No price_chart in payload → price_vals stays as initialized []
        assert data["pe_chart"]["price_vals"] == []

    def test_extracts_median_pe_from_label(self):
        """'Median PE = 12.5' label value is parsed into pe_median_screener."""
        data = {"screener_charts": {"pe_chart": _make_pe_chart(median=12.5)}}
        apply_screener_charts(data)
        assert data["pe_median_screener"] == 12.5

    def test_median_pe_missing_is_not_set(self):
        """No median label → key is simply absent (not crashed)."""
        data = {"screener_charts": {"pe_chart": _make_pe_chart(median=None)}}
        apply_screener_charts(data)
        assert "pe_median_screener" not in data

    def test_median_pe_unparseable_value_ignored(self):
        """Malformed 'Median PE = abc' must not raise, just skip."""
        data = {
            "screener_charts": {
                "pe_chart": {
                    "PE": [["2026-01-01", 10.0]],
                    "Median PE = abc": [["2026-01-01", 1]],
                },
            },
        }
        apply_screener_charts(data)  # must not raise
        assert "pe_median_screener" not in data

    def test_populates_price_chart_with_dma_and_volume(self):
        """price_chart gets prices, dma_50, dma_200, volumes parsed as floats/ints.

        In real usage apply_screener_charts runs after collect_fundamentals_data,
        which seeds an empty pe_chart dict. We mirror that here so the price_vals
        backfill branch finds the key it expects.
        """
        data = {
            "screener_charts": {"price_chart": _make_price_chart(n=3)},
            "pe_chart": {"dates": [], "pe_vals": [], "price_vals": []},
        }
        apply_screener_charts(data)

        pc = data["price_chart"]
        assert pc["dates"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
        assert pc["prices"] == [800.0, 810.0, 820.0]
        assert pc["dma_50"] == [810.0, 815.0, 820.0]
        assert pc["dma_200"] == [790.0, 792.0, 794.0]
        assert pc["volumes"] == [1500000, 1510000, 1520000]

    def test_price_chart_missing_dma_and_volume(self):
        """DMA / Volume keys missing → empty lists but no crash."""
        data = {
            "screener_charts": {
                "price_chart": _make_price_chart(n=2, with_dma=False, with_vol=False),
            },
            "pe_chart": {"dates": [], "pe_vals": [], "price_vals": []},
        }
        apply_screener_charts(data)
        pc = data["price_chart"]
        assert pc["prices"] == [800.0, 810.0]
        assert pc["dma_50"] == []
        assert pc["dma_200"] == []
        assert pc["volumes"] == []

    def test_pe_price_vals_backfilled_from_price_chart(self):
        """When both pe_chart and price_chart exist, pe_chart.price_vals is filled."""
        data = {
            "screener_charts": {
                "pe_chart": _make_pe_chart(n=3),
                "price_chart": _make_price_chart(n=3),
            },
        }
        apply_screener_charts(data)
        # Dates align, so every price_val must be set
        assert data["pe_chart"]["price_vals"] == [800.0, 810.0, 820.0]

    def test_pe_price_vals_backfill_with_missing_date(self):
        """PE dates with no matching price date get None in price_vals."""
        pe_chart = {"PE": [["2026-01-01", 10.0], ["2026-01-99", 11.0]]}
        price_chart = {"Price": [["2026-01-01", 800.0]]}
        data = {"screener_charts": {"pe_chart": pe_chart, "price_chart": price_chart}}
        apply_screener_charts(data)
        assert data["pe_chart"]["price_vals"] == [800.0, None]

    def test_empty_screener_charts_is_noop(self):
        """Empty screener_charts dict → no pe_chart/price_chart written."""
        data: dict = {"screener_charts": {}}
        apply_screener_charts(data)
        assert "pe_chart" not in data
        assert "price_chart" not in data

    def test_missing_screener_charts_key_is_noop(self):
        """Missing 'screener_charts' key entirely → no crash, no mutation."""
        data: dict = {}
        apply_screener_charts(data)
        assert data == {}

    def test_mutates_in_place_returns_none(self):
        """Function returns None and mutates the input dict."""
        data = {"screener_charts": {"pe_chart": _make_pe_chart(n=1)}}
        result = apply_screener_charts(data)
        assert result is None
        assert "pe_chart" in data

    def test_pe_chart_without_pe_key_is_skipped(self):
        """If pe_chart dict lacks 'PE' key, no pe_chart is written."""
        data = {"screener_charts": {"pe_chart": {"Something Else": []}}}
        apply_screener_charts(data)
        assert "pe_chart" not in data


# ===========================================================================
# collect_fundamentals_data — DB-backed integration
# ===========================================================================

@pytest.fixture
def db_env(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> Path:
    """Point FLOWTRACKER_DB at the populated test db.

    collect_fundamentals_data() instantiates FlowStore() with no args,
    so we rely on the env var resolution path in FlowStore.__init__.
    """
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    return tmp_db


class TestCollectFundamentalsDataPopulated:
    """collect_fundamentals_data against a populated store (SBIN/INFY fixtures)."""

    def test_returns_dict_with_symbol_uppercased(self, db_env):
        """Lowercase input is uppercased in output."""
        data = collect_fundamentals_data("sbin")
        assert data["symbol"] == "SBIN"

    def test_valuation_latest_populated(self, db_env):
        """valuation_latest has price/market_cap fields from fixture snapshots."""
        data = collect_fundamentals_data("SBIN")
        v = data["valuation_latest"]
        assert v, "valuation_latest should be non-empty with fixture data"
        assert v.get("price", 0) > 0
        assert v.get("pe_trailing") is not None
        # Derived top-level fields use the valuation snapshot
        assert data["price"] == v["price"]
        assert data["pe_trailing"] == v["pe_trailing"]
        assert data["mcap_cr"] > 0

    def test_quarterly_results_present(self, db_env):
        """Up to 20 quarterly results are returned (fixture has 8)."""
        data = collect_fundamentals_data("SBIN")
        qr = data["quarterly_results"]
        assert isinstance(qr, list)
        assert len(qr) == 8  # matches fixture
        assert all("quarter_end" in q for q in qr)
        assert all("revenue" in q for q in qr)

    def test_annual_financials_and_af_table(self, db_env):
        """annual_financials + derived af_table (reversed, oldest first)."""
        data = collect_fundamentals_data("SBIN")
        af = data["annual_financials"]
        assert len(af) == 5  # fixture n=5
        assert data["af_table"]  # derived table
        # af_table is reversed — oldest first
        assert data["af_table"][0]["fiscal_year_end"] <= data["af_table"][-1]["fiscal_year_end"]
        # Derived ops-profit fields set by loop
        first = data["af_table"][0]
        assert "operating_profit" in first
        assert "opm_pct" in first
        assert "tax_pct_annual" in first
        assert "dividend_payout_pct" in first

    def test_screener_ratios_and_roce(self, db_env):
        """screener_ratios list is populated; roce pulled from first row."""
        data = collect_fundamentals_data("SBIN")
        assert data["screener_ratios"]
        assert len(data["screener_ratios"]) == 5
        # roce is pulled from ratios[0] — must be non-None for SBIN fixture
        assert data["roce"] is not None

    def test_consensus_and_analyst_upside(self, db_env):
        """Consensus estimate populated; analyst upside derived from target vs price."""
        data = collect_fundamentals_data("SBIN")
        assert data["consensus"]
        assert data["target_mean"] == 950.0  # from fixture
        assert data["num_analysts"] == 28
        # Upside = (950/price - 1)*100, price ~820 → positive, ~15%
        assert data["upside_pct"] > 0

    def test_shareholding_and_history(self, db_env):
        """shareholding dict + shareholding_history list from NSE fixture."""
        data = collect_fundamentals_data("SBIN")
        # changes come from get_shareholding_changes (latest vs prior)
        assert isinstance(data["shareholding"], dict)
        # history: 4 quarters × categories
        hist = data["shareholding_history"]
        assert isinstance(hist, list)
        assert len(hist) == 4  # 4 quarters in fixture
        # Each row has quarter + lowercase category keys
        assert all("quarter" in row for row in hist)
        # fixture has Promoter/FII/DII/MF/Insurance/Public → lowercased
        row0 = hist[0]
        assert "promoter" in row0

    def test_mf_holdings_present(self, db_env):
        """MF scheme holdings resolved via company_name lookup for SBIN."""
        data = collect_fundamentals_data("SBIN")
        # Fixture puts 2 SBIN holdings in latest month (2026-02)
        assert data["mf_holdings"]
        assert all("scheme" in h for h in data["mf_holdings"])
        assert all("amc" in h for h in data["mf_holdings"])

    def test_industry_and_company_name(self, db_env):
        """Industry/company_name come from index_constituents."""
        data = collect_fundamentals_data("SBIN")
        assert data["industry"] == "Banks"
        assert data["company_name"] == "State Bank of India"

    def test_ttm_summed_from_four_quarters(self, db_env):
        """TTM rolls up last 4 quarters of revenue / net_income / etc."""
        data = collect_fundamentals_data("SBIN")
        ttm = data["ttm"]
        assert ttm, "TTM should be populated (fixture has 8 quarters)"
        # Revenue is summed across 4 quarters
        qr4 = data["quarterly_results"][:4]
        expected_rev = round(sum(q["revenue"] for q in qr4), 1)
        assert ttm["revenue"] == expected_rev
        # tax derived from pbt - net_income in TTM
        assert "operating_profit" in ttm  # renamed from operating_income

    def test_qr_chart_built_from_quarterly(self, db_env):
        """qr_chart contains oldest-first dates, revenues, net_incomes, opms."""
        data = collect_fundamentals_data("SBIN")
        chart = data["qr_chart"]
        assert chart["dates"]
        assert len(chart["dates"]) == len(chart["revenues"]) == len(chart["net_incomes"])
        # Oldest-first ordering
        assert chart["dates"] == sorted(chart["dates"])

    def test_roe_history_computed(self, db_env):
        """roe_history is one row per annual year, roe = ni/(eq_cap+reserves)*100."""
        data = collect_fundamentals_data("SBIN")
        roe = data["roe_history"]
        assert len(roe) == 5  # matches annual fixture
        # Every entry has year + roe keys
        assert all("year" in r and "roe" in r for r in roe)
        # SBIN fixture: ni positive, equity positive → roe not None
        assert roe[0]["roe"] is not None

    def test_empty_pe_chart_and_price_chart_placeholders(self, db_env):
        """Per contract, collect_fundamentals_data leaves pe_chart/price_chart empty.

        Those get filled later by apply_screener_charts.
        """
        data = collect_fundamentals_data("SBIN")
        assert data["pe_chart"] == {"dates": [], "pe_vals": [], "price_vals": []}
        assert data["price_chart"] == {}


class TestCollectFundamentalsDataEmpty:
    """collect_fundamentals_data against an empty store."""

    def test_unknown_symbol_returns_skeleton(self, tmp_db: Path, store: FlowStore, monkeypatch):
        """Empty store / unknown symbol → dict with symbol + sane defaults."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        data = collect_fundamentals_data("NONEXIST")

        assert data["symbol"] == "NONEXIST"
        assert data["valuation_latest"] == {}
        assert data["quarterly_results"] == []
        assert data["annual_financials"] == []
        assert data["screener_ratios"] == []
        assert data["consensus"] == {}
        assert data["surprises"] == []
        assert data["shareholding"] == {}
        assert data["shareholding_history"] == []
        assert data["mf_holdings"] == []
        # Defaulted derived fields
        assert data["industry"] == "Unknown"
        assert data["company_name"] == "NONEXIST"
        assert data["price"] == 0
        assert data["mcap_cr"] == 0
        assert data["pe_trailing"] is None
        assert data["target_mean"] == 0
        assert data["upside_pct"] == 0
        assert data["roce"] is None
        assert data["eps_annual"] == 0
        assert data["ni_annual"] == 0
        assert data["ttm"] == {}
        assert data["qr_chart"] == {"dates": [], "revenues": [], "net_incomes": [], "opms": []}
        assert data["pe_chart"] == {"dates": [], "pe_vals": [], "price_vals": []}
        assert data["af_table"] == []
        assert data["ratios_table"] == []
        assert data["roe_history"] == []
        assert data["growth_rates"] == {}
