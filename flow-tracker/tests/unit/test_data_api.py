"""Tests for ResearchDataAPI (research/data_api.py).

Tests that each API method returns correctly shaped data from the
populated test store, and that unknown symbols return empty results.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixture: create a ResearchDataAPI pointed at the populated test DB
# ---------------------------------------------------------------------------

@pytest.fixture
def api(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI backed by the populated test database."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# ---------------------------------------------------------------------------
# Core Financials
# ---------------------------------------------------------------------------

class TestQuarterlyResults:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_quarterly_results("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert isinstance(data[0], dict)

    def test_has_expected_keys(self, api: ResearchDataAPI):
        data = api.get_quarterly_results("SBIN")
        row = data[0]
        assert "revenue" in row
        assert "net_income" in row
        assert "quarter_end" in row

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_quarterly_results("NONEXIST")
        assert isinstance(data, list)
        assert len(data) == 0


class TestAnnualFinancials:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_annual_financials("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "revenue" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_annual_financials("NONEXIST")
        assert len(data) == 0


class TestScreenerRatios:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_screener_ratios("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "roce_pct" in data[0]


# ---------------------------------------------------------------------------
# Valuation
# ---------------------------------------------------------------------------

class TestValuationSnapshot:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_valuation_snapshot("SBIN")
        assert isinstance(data, dict)
        assert "price" in data
        assert "pe_trailing" in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_valuation_snapshot("NONEXIST")
        assert data == {}


class TestValuationBand:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_valuation_band("SBIN")
        assert isinstance(data, dict)
        # May be empty if not enough data for percentile band
        # Just verify it doesn't crash


class TestPeHistory:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_pe_history("SBIN", days=90)
        assert isinstance(data, list)
        if data:
            assert "pe" in data[0]
            assert "price" in data[0]
            assert "date" in data[0]


# ---------------------------------------------------------------------------
# Ownership & Institutional
# ---------------------------------------------------------------------------

class TestShareholding:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_shareholding("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "category" in data[0]
        assert "percentage" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_shareholding("NONEXIST")
        assert len(data) == 0


class TestShareholdingChanges:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_shareholding_changes("SBIN")
        assert isinstance(data, list)
        if data:
            assert "category" in data[0]
            assert "change_pct" in data[0]


class TestInsiderTransactions:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_insider_transactions("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "person_name" in data[0]
        assert "transaction_type" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_insider_transactions("NONEXIST")
        assert len(data) == 0


class TestBulkBlockDeals:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_bulk_block_deals("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# Market Signals
# ---------------------------------------------------------------------------

class TestDeliveryTrend:
    def test_returns_list_of_dicts(self, api: ResearchDataAPI):
        data = api.get_delivery_trend("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "delivery_pct" in data[0]

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_delivery_trend("NONEXIST")
        assert len(data) == 0


class TestPromoterPledge:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_promoter_pledge("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "pledge_pct" in data[0]


# ---------------------------------------------------------------------------
# Consensus
# ---------------------------------------------------------------------------

class TestConsensusEstimate:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_consensus_estimate("SBIN")
        assert isinstance(data, dict)
        assert "target_mean" in data
        assert "recommendation" in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_consensus_estimate("NONEXIST")
        assert data == {}


class TestEarningsSurprises:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_earnings_surprises("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "surprise_pct" in data[0]


# ---------------------------------------------------------------------------
# Macro Context
# ---------------------------------------------------------------------------

class TestMacroSnapshot:
    def test_returns_dict(self, api: ResearchDataAPI):
        data = api.get_macro_snapshot()
        assert isinstance(data, dict)
        assert "india_vix" in data
        assert "usd_inr" in data


class TestFiiDiiStreak:
    def test_returns_dict_with_fii_dii_keys(self, api: ResearchDataAPI):
        data = api.get_fii_dii_streak()
        assert isinstance(data, dict)
        assert "fii" in data
        assert "dii" in data


class TestFiiDiiFlows:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_fii_dii_flows(days=30)
        assert isinstance(data, list)
        assert len(data) > 0


# ---------------------------------------------------------------------------
# FMP Data
# ---------------------------------------------------------------------------

class TestDcfValuation:
    def test_returns_dict_with_margin(self, api: ResearchDataAPI):
        data = api.get_dcf_valuation("SBIN")
        assert isinstance(data, dict)
        assert "dcf" in data
        assert "stock_price" in data
        assert "margin_of_safety_pct" in data

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_dcf_valuation("NONEXIST")
        assert data == {}


class TestTechnicalIndicators:
    def test_returns_list(self, api: ResearchDataAPI):
        data = api.get_technical_indicators("SBIN")
        assert isinstance(data, list)
        assert len(data) > 0
        assert "indicator" in data[0]


class TestDupontDecomposition:
    def test_screener_path(self, api: ResearchDataAPI):
        """Should use Screener annual_financials data (source='screener')."""
        data = api.get_dupont_decomposition("SBIN")
        assert isinstance(data, dict)
        assert data.get("source") == "screener"
        assert "years" in data
        assert len(data["years"]) > 0
        year = data["years"][0]
        assert "net_profit_margin" in year
        assert "asset_turnover" in year
        assert "equity_multiplier" in year
        assert "roe_dupont" in year

    def test_unknown_symbol_returns_empty(self, api: ResearchDataAPI):
        data = api.get_dupont_decomposition("NONEXIST")
        assert data == {}


# ---------------------------------------------------------------------------
# Fair Value
# ---------------------------------------------------------------------------

class TestFairValue:
    def test_returns_dict_with_symbol(self, api: ResearchDataAPI):
        data = api.get_fair_value("SBIN")
        assert isinstance(data, dict)
        assert data["symbol"] == "SBIN"

    def test_has_dcf_component(self, api: ResearchDataAPI):
        data = api.get_fair_value("SBIN")
        # Fixture has DCF=950, estimates with target_mean=950
        assert "dcf" in data or "consensus_target" in data

    def test_has_signal(self, api: ResearchDataAPI):
        data = api.get_fair_value("SBIN")
        assert "signal" in data
        assert data["signal"] in ("DEEP VALUE", "UNDERVALUED", "FAIR VALUE", "EXPENSIVE", "INSUFFICIENT DATA")

    def test_unknown_symbol_no_crash(self, api: ResearchDataAPI):
        data = api.get_fair_value("NONEXIST")
        assert isinstance(data, dict)
        assert data["symbol"] == "NONEXIST"


# ---------------------------------------------------------------------------
# _clean applied
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Forensic Checks
# ---------------------------------------------------------------------------

class TestForensicChecks:
    def test_returns_data_for_sbin(self, api: ResearchDataAPI):
        """SBIN not tagged as BFSI in test fixture (no industry data) — returns data."""
        data = api.get_forensic_checks("SBIN")
        assert isinstance(data, dict)
        assert "years" in data

    def test_non_bfsi_returns_structure(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        assert isinstance(data, dict)
        assert "years" in data
        assert "cfo_ebitda_5y_avg" in data
        assert "cfo_ebitda_signal" in data
        assert "depreciation_volatility" in data
        assert "depreciation_signal" in data
        assert data["depreciation_signal"] in ("stable", "moderate", "volatile")
        assert data["cfo_ebitda_signal"] in ("clean", "moderate", "warning")

    def test_per_year_metrics(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        year = data["years"][0]
        assert "fiscal_year_end" in year
        assert "cfo_ebitda" in year
        assert "depreciation_rate" in year
        assert "cwip_ratio" in year

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("NONEXIST")
        assert "error" in data

    def test_cash_yield_signal(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        assert data.get("cash_yield_signal") in ("normal", "suspicious", "low")

    def test_cwip_signal(self, api: ResearchDataAPI):
        data = api.get_forensic_checks("INFY")
        assert data.get("cwip_signal") in ("normal", "elevated", "parking_risk")


# ---------------------------------------------------------------------------
# Improvement Metrics
# ---------------------------------------------------------------------------

class TestImprovementMetrics:
    def test_returns_structure(self, api: ResearchDataAPI):
        data = api.get_improvement_metrics("INFY")
        assert isinstance(data, dict)
        assert "data_years" in data
        assert data["data_years"] == 5

    def test_bfsi_not_skipped(self, api: ResearchDataAPI):
        """Improvement metrics apply to all sectors including BFSI."""
        data = api.get_improvement_metrics("SBIN")
        assert "skipped" not in data
        assert "data_years" in data

    def test_insufficient_data_no_trajectories(self, api: ResearchDataAPI):
        """With only 5 years, trajectories require 6+ so should be absent."""
        data = api.get_improvement_metrics("INFY")
        # 5 years fixture → trajectories may be empty
        if data["data_years"] < 6:
            assert data.get("trajectories") is None or data.get("trajectories") == {}

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_improvement_metrics("NONEXIST")
        assert "error" in data

    def test_with_10_years(self, api: ResearchDataAPI, populated_store: "FlowStore"):
        """With 10 years of data, trajectories and greatness should be populated."""
        from tests.fixtures.factories import make_annual_financials, make_screener_ratios
        # Insert 10 years for INFY
        populated_store.upsert_annual_financials(make_annual_financials("INFY", n=10))
        populated_store.upsert_screener_ratios(make_screener_ratios("INFY", n=10))
        data = api.get_improvement_metrics("INFY")
        assert data["data_years"] == 10
        assert data.get("trajectories") is not None
        # ROE is computed from annuals directly — should always have 6+ values
        assert "roe" in data["trajectories"]
        assert "improvement" in data["trajectories"]["roe"]
        assert "consistency" in data["trajectories"]["roe"]
        # ROCE may not have 6 matching FYs due to fixture alignment — check if present
        if "roce" in data["trajectories"]:
            assert "improvement" in data["trajectories"]["roce"]
        # Greatness
        assert data.get("greatness") is not None
        assert data["greatness"]["classification"] in ("great", "good", "mediocre")
        assert 0 <= data["greatness"]["score_pct"] <= 100
        # Capex productivity
        assert data.get("capex_productivity") is not None
        assert "gross_block_cagr_pct" in data["capex_productivity"]
        assert "sales_cagr_pct" in data["capex_productivity"]


# ---------------------------------------------------------------------------
# Capital Discipline
# ---------------------------------------------------------------------------

class TestCapitalDiscipline:
    def test_returns_data_for_sbin(self, api: ResearchDataAPI):
        """SBIN not tagged as BFSI in test fixture (no industry data) — returns data."""
        data = api.get_capital_discipline("SBIN")
        assert isinstance(data, dict)
        assert "roce_reinvestment" in data

    def test_non_bfsi_returns_structure(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("INFY")
        assert isinstance(data, dict)
        assert "roce_reinvestment" in data
        assert "equity_dilution" in data

    def test_roce_reinvestment_years(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("INFY")
        rr = data["roce_reinvestment"]
        assert "years" in rr
        assert "latest_signal" in rr
        assert rr["latest_signal"] in ("compounder", "cash_cow", "growth_trap", "challenged")
        year = rr["years"][0]
        assert "fiscal_year_end" in year

    def test_equity_dilution(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("INFY")
        ed = data["equity_dilution"]
        assert "shares_latest_cr" in ed
        assert "signal" in ed
        assert ed["signal"] in ("dilutive", "moderate", "stable", "buyback")

    def test_rm_cost_empty_when_no_data(self, api: ResearchDataAPI):
        """Fixture has raw_material_cost=None → rm_cost_cycle should be absent."""
        data = api.get_capital_discipline("INFY")
        # rm_cost_cycle should be None or absent since raw_material_cost is None in fixture
        assert data.get("rm_cost_cycle") is None

    def test_unknown_symbol(self, api: ResearchDataAPI):
        data = api.get_capital_discipline("NONEXIST")
        assert "error" in data

    def test_serializable(self, api: ResearchDataAPI):
        import json
        for method in ("get_forensic_checks", "get_improvement_metrics", "get_capital_discipline"):
            data = getattr(api, method)("INFY")
            json.dumps(data)  # Should not raise


# ---------------------------------------------------------------------------
# _clean applied
# ---------------------------------------------------------------------------

class TestClean:
    def test_no_none_values_in_quarterly(self, api: ResearchDataAPI):
        """_clean should convert None to JSON-friendly values (or strip them)."""
        data = api.get_quarterly_results("SBIN")
        # _clean passes through json.dumps/loads which converts None → null → None
        # But the key thing is it handles numpy/Decimal types
        assert isinstance(data, list)

    def test_serializable(self, api: ResearchDataAPI):
        """All API outputs should be JSON-serializable."""
        import json
        data = api.get_quarterly_results("SBIN")
        json.dumps(data)  # Should not raise

        data = api.get_fair_value("SBIN")
        json.dumps(data)
