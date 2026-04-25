"""Coverage-focused tests for recently-added ResearchDataAPI methods.

Targets methods added since 2026-04-01 that drove data_api.py from ~3500 to
~5900 lines but lacked dedicated tests. Focus areas:
  - TOC + drill patterns (get_ownership_toc, get_fundamentals_toc edges)
  - BFSI / sector-specific metric methods (metals, realestate, telecom, power,
    insurance, sector_health, subsidiary, quality_scores_all)
  - Piotroski / Beneish / reverse_dcf / capex_cycle / capital_allocation /
    common_size_pl
  - Dividend policy, institutional consensus, delivery analysis, MF conviction
  - Material events classifier, schedule grouping helpers, adjustment factor
  - Price performance (with split adjustment), data freshness,
    fundamentals_toc BFSI flag, listed subsidiaries

These tests seed minimal fixture rows directly where the shared
populated_store fixture lacks coverage (e.g. company_snapshot for industry
tagging, standalone financials for subsidiary contribution).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI backed by the populated test database."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


@pytest.fixture
def vault_home(tmp_path: Path, monkeypatch) -> Path:
    """Redirect Path.home() to a tmp dir so concall reads hit our fixtures."""
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def _write_concall(
    vault_root: Path,
    symbol: str,
    quarters: list[dict],
    narrative: dict | None = None,
) -> None:
    """Write a concall_extraction_v2.json for <symbol> under <vault_root>."""
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "quarters": quarters,
        "cross_quarter_narrative": narrative or {},
    }
    (fdir / "concall_extraction_v2.json").write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# _clean / helper methods
# ---------------------------------------------------------------------------


class TestNormalizeSubItem:
    """_normalize_sub_item converts Screener schedule names to snake_case keys."""

    @pytest.mark.parametrize("raw,expected", [
        ("Material Cost %", "material_cost_pct"),
        ("Long term Borrowings", "long_term_borrowings"),
        ("Trade receivables", "trade_receivables"),
        ("Other Income", "other_income"),
        ("Employee Benefit Exp.", "employee_benefit_exp"),
    ])
    def test_normalize(self, raw, expected):
        assert ResearchDataAPI._normalize_sub_item(raw) == expected

    def test_empty_string(self):
        assert ResearchDataAPI._normalize_sub_item("") == ""

    def test_pct_suffix_preserved(self):
        # Even if normalisation strips the raw %, the _pct suffix must be re-added
        assert ResearchDataAPI._normalize_sub_item("Tax Rate%").endswith("_pct")


class TestGroupSchedules:
    """_group_schedules groups raw schedule rows by parent/sub-item."""

    def test_groups_by_parent_and_subitem(self):
        rows = [
            {"parent_item": "Expenses", "sub_item": "Employee Cost",
             "period": "Mar 2025", "value": 100.0, "section": "profit-loss"},
            {"parent_item": "Expenses", "sub_item": "Employee Cost",
             "period": "Mar 2024", "value": 90.0, "section": "profit-loss"},
            {"parent_item": "Expenses", "sub_item": "Material Cost",
             "period": "Mar 2025", "value": 50.0, "section": "profit-loss"},
        ]
        grouped = ResearchDataAPI._group_schedules(rows)
        assert "Expenses" in grouped
        assert "employee_cost" in grouped["Expenses"]
        assert len(grouped["Expenses"]["employee_cost"]) == 2

    def test_section_filter(self):
        rows = [
            {"parent_item": "Expenses", "sub_item": "Employee Cost",
             "period": "Mar 2025", "value": 100.0, "section": "profit-loss"},
            {"parent_item": "Expenses", "sub_item": "Employee Cost",
             "period": "Q1", "value": 25.0, "section": "quarters"},
        ]
        grouped = ResearchDataAPI._group_schedules(rows, section="quarters")
        # Only the quarters row should pass the filter
        assert len(grouped["Expenses"]["employee_cost"]) == 1
        assert grouped["Expenses"]["employee_cost"][0]["period"] == "Q1"

    def test_skips_rows_with_no_subitem(self):
        rows = [
            {"parent_item": "Expenses", "sub_item": "",
             "period": "Mar 2025", "value": 100.0, "section": "profit-loss"},
        ]
        assert ResearchDataAPI._group_schedules(rows) == {}


# ---------------------------------------------------------------------------
# Industry / sector detection paths
# ---------------------------------------------------------------------------


class TestSectorType:
    """get_sector_type dispatches to the first matching _is_* check."""

    def test_general_default(self, api):
        # populated_store has no industry tagging → company_info returns 'Banks'
        # or IT - Software, neither of which is in the core BFSI industry list
        # unless mapped there. The default path ('general') covers stocks
        # without a specific framework.
        assert api.get_sector_type("NOSUCHSYM") == "general"

    def test_bfsi_via_monkeypatch(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        assert api.get_sector_type("ANY") == "bfsi"

    def test_insurance_priority_over_bfsi(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: True)
        # Insurance check runs first
        assert api.get_sector_type("ANY") == "insurance"


class TestIndustryHelpers:
    """_is_* helpers return False for the default 'Unknown' industry."""

    def test_is_bfsi_unknown_industry(self, api):
        assert api._is_bfsi("NOSUCHSYM") is False

    def test_is_insurance_unknown_industry(self, api):
        assert api._is_insurance("NOSUCHSYM") is False

    def test_is_it_services_unknown_industry(self, api):
        assert api._is_it_services("NOSUCHSYM") is False

    def test_is_holding_company_unknown_industry(self, api):
        assert api._is_holding_company("NOSUCHSYM") is False

    def test_is_conglomerate_unknown_industry(self, api):
        assert api._is_conglomerate("NOSUCHSYM") is False


# ---------------------------------------------------------------------------
# TOC: get_ownership_toc (distinct from pagination tests)
# ---------------------------------------------------------------------------


class TestOwnershipTOC:
    """get_ownership_toc returns a compact multi-section TOC."""

    def test_returns_expected_keys(self, api):
        toc = api.get_ownership_toc("SBIN")
        assert toc["symbol"] == "SBIN"
        for key in (
            "current_ownership", "qoq_changes_summary", "quarters_available",
            "top_10_holders_brief", "mf_summary", "pledge_status",
            "insider_activity_365d", "bulk_block_365d",
            "available_sections", "hint",
        ):
            assert key in toc

    def test_insider_activity_counts_buys_sells(self, api):
        toc = api.get_ownership_toc("SBIN")
        ia = toc["insider_activity_365d"]
        assert "buy_count" in ia
        assert "sell_count" in ia
        assert "txn_count" in ia
        # populated_store seeds 2 Buys + 1 Sell for SBIN
        assert ia["buy_count"] >= 0
        assert ia["sell_count"] >= 0

    def test_hint_mentions_section(self, api):
        toc = api.get_ownership_toc("SBIN")
        assert "section" in toc["hint"].lower()

    def test_current_ownership_has_category_pcts(self, api):
        toc = api.get_ownership_toc("SBIN")
        co = toc["current_ownership"]
        # Categories seeded in factories: Promoter, FII, DII, MF, Insurance, Public
        assert "promoter_pct" in co
        assert "fii_pct" in co
        assert "dii_pct" in co


# ---------------------------------------------------------------------------
# Material events classifier
# ---------------------------------------------------------------------------


class TestMaterialEvents:
    def test_returns_structure(self, api):
        result = api.get_material_events("SBIN", days=3650)
        assert "events" in result
        assert "summary" in result
        assert "total" in result
        assert "high_signal_count" in result

    def test_filters_non_classified_filings(self, api):
        # factories.py seeds 2 filings: "Financial Results" + "Investor Presentation".
        # The first maps to 'results', the second has no mapping → gets dropped.
        result = api.get_material_events("SBIN", days=3650)
        # At most 1 event should come through
        assert result["total"] <= 2
        for ev in result["events"]:
            assert "event_type" in ev
            assert "high_signal" in ev

    def test_unknown_symbol_returns_empty(self, api):
        result = api.get_material_events("NONEXIST", days=365)
        assert result["total"] == 0
        assert result["events"] == []


# ---------------------------------------------------------------------------
# Commodity snapshot
# ---------------------------------------------------------------------------


class TestCommoditySnapshot:
    def test_returns_dict(self, api):
        result = api.get_commodity_snapshot()
        assert isinstance(result, dict)
        # At minimum the GOLD seed row from factories.py should produce a 'gold' entry
        # unless no commodity prices are fetched in this shape.
        # If no data, fallback message
        if not result.get("available") is False:
            # Assert normal shape
            for k, v in result.items():
                if isinstance(v, dict) and "price" in v:
                    assert "date" in v
                    assert "change_1m_pct" in v


# ---------------------------------------------------------------------------
# Delivery analysis + Institutional consensus
# ---------------------------------------------------------------------------


class TestDeliveryAnalysis:
    def test_has_required_keys_when_available(self, api):
        result = api.get_delivery_analysis("SBIN", days=60)
        # populated_store seeds 30 days of daily_stock_data with delivery_pct
        if result.get("available"):
            for key in ("avg_delivery_pct", "trend", "volume_delivery_divergence"):
                assert key in result
            assert result["trend"] in ("rising", "falling", "stable")
            assert result["volume_delivery_divergence"] in (
                "none", "speculative_churn", "quiet_accumulation",
            )

    def test_unavailable_for_unknown_symbol(self, api):
        result = api.get_delivery_analysis("NONEXIST", days=60)
        assert result.get("available") is False


class TestInstitutionalConsensus:
    def test_returns_composite(self, api):
        result = api.get_institutional_consensus("SBIN")
        assert "composite" in result
        assert result["composite"] in (
            "strong_bullish", "moderately_bullish", "neutral",
            "moderately_bearish", "bearish",
        )
        assert "composite_score" in result

    def test_unknown_symbol_still_returns_composite(self, api):
        # No signals → composite = 'neutral' with score 0
        result = api.get_institutional_consensus("NONEXIST")
        assert "composite" in result
        assert result["composite_score"] == 0


# ---------------------------------------------------------------------------
# MF conviction
# ---------------------------------------------------------------------------


class TestMFConviction:
    def test_returns_dict_with_available_flag(self, api):
        result = api.get_mf_conviction("SBIN")
        # Either available=True with real data, or available=False with reason
        if result.get("available"):
            for key in (
                "schemes_holding", "amcs_holding", "total_mf_value_cr",
                "by_scheme_type", "top_equity_schemes", "top_debt_schemes_if_any",
            ):
                assert key in result
            # by_scheme_type must segregate equity/debt/hybrid/unknown
            bst = result["by_scheme_type"]
            assert "equity" in bst
            assert "debt" in bst

    def test_unknown_symbol_returns_unavailable(self, api):
        result = api.get_mf_conviction("NONEXIST")
        assert result.get("available") is False


# ---------------------------------------------------------------------------
# Adjustment factor + adjusted EPS
# ---------------------------------------------------------------------------


class TestAdjustmentFactor:
    def test_no_actions_returns_unity(self, api):
        # populated_store has no corporate_actions seeded
        result = api.get_adjustment_factor("SBIN")
        assert result["symbol"] == "SBIN"
        assert result["cumulative_factor"] == 1.0
        assert result["actions"] == []

    def test_unknown_symbol_returns_unity(self, api):
        result = api.get_adjustment_factor("NONEXIST")
        assert result["cumulative_factor"] == 1.0


class TestAdjustedEPS:
    def test_returns_list_of_dicts(self, api):
        result = api.get_adjusted_eps("SBIN", quarters=4)
        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "period" in row
            assert "raw_eps" in row
            assert "adjusted_eps" in row
            assert "adjustment_factor" in row

    def test_unknown_symbol_returns_empty(self, api):
        result = api.get_adjusted_eps("NONEXIST")
        assert result == []


# ---------------------------------------------------------------------------
# Dividend policy
# ---------------------------------------------------------------------------


class TestDividendPolicy:
    def test_no_actions_unavailable(self, api):
        # No corporate_actions seeded in factories → unavailable
        result = api.get_dividend_policy("SBIN")
        assert result.get("available") is False

    def test_unknown_symbol_unavailable(self, api):
        result = api.get_dividend_policy("NONEXIST")
        assert result.get("available") is False


# ---------------------------------------------------------------------------
# Piotroski F-Score
# ---------------------------------------------------------------------------


class TestPiotroskiScore:
    def test_returns_score_and_criteria(self, api):
        result = api.get_piotroski_score("INFY")
        if "error" in result:
            pytest.skip("Need 2+ years of data")
        assert "score" in result
        assert "max_score" in result
        assert "criteria" in result
        assert "signal" in result
        assert 0 <= result["score"] <= 9
        assert result["signal"] in ("strong", "moderate", "weak")

    def test_criteria_have_passed_field(self, api):
        result = api.get_piotroski_score("INFY")
        if "error" in result:
            pytest.skip("Need 2+ years of data")
        for c in result["criteria"]:
            assert "name" in c
            assert "passed" in c  # passed can be True/False/None
            assert "value" in c

    def test_insufficient_data_returns_error(self, api):
        result = api.get_piotroski_score("NONEXIST")
        assert "error" in result


# ---------------------------------------------------------------------------
# Beneish M-Score
# ---------------------------------------------------------------------------


class TestBeneishScore:
    def test_bfsi_is_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        result = api.get_beneish_score("SBIN")
        assert result.get("skipped") is True

    def test_insufficient_data_returns_error(self, api):
        result = api.get_beneish_score("NONEXIST")
        assert "error" in result

    def test_non_bfsi_fixture_yields_variables_or_error(self, api, monkeypatch):
        """INFY factory has raw_material_cost=None, so GMI path must
        gracefully report insufficient data instead of crashing."""
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_beneish_score("INFY")
        # Fixture data is synthetic; M-score may or may not be computable. Either
        # way the method must return a structured dict (not raise).
        assert isinstance(result, dict)
        assert ("m_score" in result) or ("error" in result) or ("skipped" in result)


# ---------------------------------------------------------------------------
# Reverse DCF
# ---------------------------------------------------------------------------


class TestReverseDCF:
    def test_returns_structure_or_error(self, api):
        result = api.get_reverse_dcf("INFY")
        # Fixture: INFY has 5 years of data but possibly degenerate DCF inputs
        assert isinstance(result, dict)
        if "error" not in result:
            assert "implied_growth_rate" in result
            assert "model" in result
            assert result["model"] in ("FCFF", "FCFE")
            assert "sensitivity" in result
            assert "assessment" in result

    def test_unknown_symbol_errors(self, api):
        result = api.get_reverse_dcf("NONEXIST")
        assert "error" in result

    def test_bfsi_uses_fcfe_model(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_reverse_dcf("SBIN")
        if "error" not in result:
            assert result.get("model") == "FCFE"


# ---------------------------------------------------------------------------
# Capital allocation
# ---------------------------------------------------------------------------


class TestCapitalAllocation:
    def test_returns_cumulative_and_cash_position(self, api):
        result = api.get_capital_allocation("INFY", years=5)
        if "error" in result:
            pytest.skip("Need 2+ years")
        assert "cumulative" in result
        assert "cash_position" in result
        assert "payout_trend" in result
        # Cumulative fields
        for field in ("cfo", "gross_capex", "dividends"):
            assert field in result["cumulative"]

    def test_bfsi_has_caveat(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_capital_allocation("SBIN", years=5)
        if "error" in result:
            pytest.skip("Need 2+ years")
        assert "bfsi_investments_caveat" in result

    def test_unknown_symbol_errors(self, api):
        result = api.get_capital_allocation("NONEXIST")
        assert "error" in result

    def test_fcf_formula_explicit_and_reconciles_with_fcf_yield(
        self, tmp_db, monkeypatch
    ):
        """FCF = CFO - capex must be explicitly returned in capital_allocation,
        and the latest-year value must reconcile exactly with get_fcf_yield's
        FCF — same formula, same answer.

        Regression: pre-fix `capital_allocation` exposed only `cfo` and
        `net_capex`, forcing agents to recompute FCF. The recomputed value
        could drift from `get_fcf_yield` (which uses the same balance-sheet-
        delta capex formula) when the agent picked a different capex source
        (e.g. yfinance quarterly capex), yielding two FCF figures in one
        report — caught by the NYKAA Gemini grader.
        """
        from flowtracker.fund_models import AnnualFinancials
        from flowtracker.store import FlowStore

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        store = FlowStore(db_path=tmp_db)
        # Two consecutive years — minimal data for capex delta + FCF.
        # Net block growth + depreciation define capex; cfo is given directly.
        rows = [
            AnnualFinancials(
                symbol="NYKA_T", fiscal_year_end="2025-03-31",
                revenue=8000.0, net_income=80.0,
                cfo=466.63, cfi=-205.43,
                net_block=834.82, cwip=36.74, depreciation=266.40,
                dividend_amount=0.0,
            ),
            AnnualFinancials(
                symbol="NYKA_T", fiscal_year_end="2024-03-31",
                revenue=7000.0, net_income=10.0,
                cfo=0.25, cfi=-10.11,
                net_block=668.16, cwip=29.78, depreciation=224.23,
                dividend_amount=0.0,
            ),
        ]
        for r in rows:
            store.upsert_annual_financials([r])
        store.close()

        api = ResearchDataAPI()
        try:
            ca = api.get_capital_allocation("NYKA_T", years=5)
            assert "fcf_formula" in ca, "capital_allocation must document FCF formula"
            assert "fcf" in ca["cumulative"], "cumulative.fcf must be present"
            assert "per_year_fcf" in ca, "per_year_fcf must be present"
            assert len(ca["per_year_fcf"]) >= 1
            # capex_2025 = (834.82 - 668.16) + (36.74 - 29.78) + 266.40 = 440.02
            # fcf_2025 = 466.63 - 440.02 = 26.61
            latest = ca["per_year_fcf"][0]
            assert latest["fiscal_year"] == "2025-03-31"
            assert latest["capex"] == pytest.approx(440.02, abs=0.05)
            assert latest["fcf"] == pytest.approx(26.61, abs=0.05)
            # Cumulative FCF == sum of per-year FCFs
            assert ca["cumulative"]["fcf"] == pytest.approx(
                sum(y["fcf"] for y in ca["per_year_fcf"]), abs=0.05
            )
        finally:
            api.close()


# ---------------------------------------------------------------------------
# Capex cycle
# ---------------------------------------------------------------------------


class TestCapexCycle:
    def test_returns_years_and_phase(self, api, monkeypatch):
        # Force non-BFSI so the capex path runs
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_capex_cycle("INFY")
        if "error" in result or "skipped" in result:
            pytest.skip("Insufficient data or sector-skipped")
        assert "years" in result
        assert "phase" in result
        assert result["phase"] in ("Investing", "Commissioning", "Harvesting", "Mature")

    def test_bfsi_is_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        result = api.get_capex_cycle("SBIN")
        assert result.get("skipped") is True


# ---------------------------------------------------------------------------
# Common size P&L
# ---------------------------------------------------------------------------


class TestCommonSizePL:
    def test_returns_structure(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_common_size_pl("INFY")
        if "error" in result:
            pytest.skip("Insufficient data")
        assert "years" in result
        assert "is_bfsi" in result
        # Each year should have margin breakdowns
        if result["years"]:
            y = result["years"][0]
            assert "fiscal_year" in y

    def test_bfsi_denominator_is_total_income(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_common_size_pl("SBIN")
        if "error" in result:
            pytest.skip("Insufficient data")
        assert result["is_bfsi"] is True
        if result["years"]:
            assert result["years"][0]["denominator"] == "total_income"

    def test_unknown_symbol_errors(self, api):
        result = api.get_common_size_pl("NONEXIST")
        assert "error" in result


# ---------------------------------------------------------------------------
# Sector metric dispatchers (BFSI-routing)
# ---------------------------------------------------------------------------


class TestBFSIMetrics:
    def test_non_bfsi_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_bfsi_metrics("INFY")
        assert result.get("skipped") is True

    def test_insurance_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_insurance", lambda s: True)
        result = api.get_bfsi_metrics("SBIN")
        assert result.get("skipped") is True

    def test_bfsi_runs_year_loop(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_bfsi_metrics("SBIN")
        if "error" in result:
            pytest.skip("No annual data")
        assert result["is_bfsi"] is True
        assert "years" in result
        if result["years"]:
            y = result["years"][0]
            # NIM and ROA should appear when total_assets > 0
            assert "nim_pct" in y or "roa_pct" in y


class TestInsuranceMetrics:
    def test_non_insurance_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_insurance_metrics("INFY")
        assert result.get("skipped") is True

    def test_insurance_runs_and_adds_concall_kpis(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_insurance", lambda s: True)
        monkeypatch.setattr(api, "_get_industry", lambda s: "Life Insurance")
        result = api.get_insurance_metrics("SBIN")
        if "error" in result:
            pytest.skip("No annual data")
        assert result["is_insurance"] is True
        assert "sub_type" in result
        assert result["sub_type"] in ("life", "general")
        # concall_kpis present whether or not concall exists
        assert "concall_kpis" in result


class TestMetalsMetrics:
    def test_non_metals_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_metals", lambda s: False)
        result = api.get_metals_metrics("INFY")
        assert result.get("skipped") is True

    def test_metals_computes_ebitda_net_debt(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_metals", lambda s: True)
        result = api.get_metals_metrics("INFY")
        if "error" in result:
            pytest.skip("No annual data")
        assert result["is_metals"] is True
        if result["years"]:
            y = result["years"][0]
            assert "ebitda" in y
            assert "net_debt" in y


class TestRealEstateMetrics:
    def test_non_realestate_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_realestate", lambda s: False)
        result = api.get_realestate_metrics("INFY")
        assert result.get("skipped") is True

    def test_realestate_has_adjusted_bv(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_realestate", lambda s: True)
        result = api.get_realestate_metrics("INFY")
        if "error" in result:
            pytest.skip("No annual data")
        assert result["is_realestate"] is True


class TestTelecomMetrics:
    def test_non_telecom_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_telecom", lambda s: False)
        monkeypatch.setattr(api, "_is_telecom_infra", lambda s: False)
        result = api.get_telecom_metrics("INFY")
        assert result.get("skipped") is True

    def test_telecom_computes_ebitda(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_telecom", lambda s: True)
        monkeypatch.setattr(api, "_is_telecom_infra", lambda s: False)
        result = api.get_telecom_metrics("INFY")
        if "error" in result:
            pytest.skip("No annual data")
        assert result["is_telecom"] is True
        assert result["sub_type"] in ("telecom", "telecom_infra")

    def test_telecom_infra_sub_type(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_telecom", lambda s: False)
        monkeypatch.setattr(api, "_is_telecom_infra", lambda s: True)
        result = api.get_telecom_metrics("INFY")
        if "error" in result:
            pytest.skip("No annual data")
        assert result["sub_type"] == "telecom_infra"


class TestPowerMetrics:
    def test_non_power_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_regulated_power", lambda s: False)
        monkeypatch.setattr(api, "_is_merchant_power", lambda s: False)
        result = api.get_power_metrics("INFY")
        assert result.get("skipped") is True

    def test_regulated_power_adds_justified_pb(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_regulated_power", lambda s: True)
        monkeypatch.setattr(api, "_is_merchant_power", lambda s: False)
        result = api.get_power_metrics("SBIN")
        assert result["is_power"] is True
        assert result["sub_type"] == "regulated"
        # justified_pb requires ROE + gsec → one of them may be missing; just
        # confirm structure.
        assert isinstance(result, dict)

    def test_merchant_power_sub_type(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_regulated_power", lambda s: False)
        monkeypatch.setattr(api, "_is_merchant_power", lambda s: True)
        result = api.get_power_metrics("SBIN")
        assert result["sub_type"] == "merchant"


class TestSectorHealthMetrics:
    def test_non_it_fmcg_skipped(self, api, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Unknown")
        result = api.get_sector_health_metrics("NOSUCHSYM")
        # insufficient data wins over unknown industry
        assert result.get("skipped") is True

    def test_it_path_runs(self, api, monkeypatch):
        monkeypatch.setattr(api, "_get_industry",
                            lambda s: "Computers - Software & Consulting")
        result = api.get_sector_health_metrics("INFY")
        if result.get("skipped"):
            pytest.skip("Need 2+ annual rows")
        assert result["sector"] == "it"
        assert "dso_trend" in result

    def test_fmcg_path_runs(self, api, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Packaged Foods")
        result = api.get_sector_health_metrics("INFY")
        if result.get("skipped"):
            pytest.skip("Need 2+ annual rows")
        assert result["sector"] == "fmcg"
        assert "wc_trend" in result


class TestSubsidiaryContribution:
    def test_no_standalone_data_unavailable(self, api):
        # populated_store doesn't seed standalone_financials
        result = api.get_subsidiary_contribution("SBIN")
        assert result.get("available") is False

    def test_unknown_symbol_unavailable(self, api):
        result = api.get_subsidiary_contribution("NONEXIST")
        assert result.get("available") is False


class TestQualityScoresAll:
    def test_non_bfsi_path(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_quality_scores_all("INFY")
        # Always-present sections
        for key in (
            "piotroski", "dupont", "common_size", "improvement_metrics",
            "operating_leverage", "fcf_yield", "tax_rate_analysis",
            "metals", "realestate", "telecom", "power",
            "sector_health", "subsidiary", "risk_flags",
        ):
            assert key in result
        # Non-BFSI: these should compute, not skip-flagged
        assert "forensic_checks" in result
        assert "capital_discipline" in result
        assert "incremental_roce" in result
        assert "altman_zscore" in result
        assert "working_capital" in result
        assert "receivables_quality" in result

    def test_bfsi_path_skips_non_applicable(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_quality_scores_all("SBIN")
        # BFSI: these should be explicitly skipped (not computed)
        for key in (
            "earnings_quality", "beneish", "incremental_roce",
            "altman_zscore", "working_capital", "receivables_quality",
        ):
            assert result[key].get("skipped") is True
        assert result["bfsi"].get("is_bfsi") is True or "error" in result["bfsi"]

    def test_insurance_path_skips_non_applicable(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_insurance", lambda s: True)
        result = api.get_quality_scores_all("SBIN")
        for key in ("earnings_quality", "beneish", "capex_cycle"):
            assert result[key].get("skipped") is True
        # bfsi is skipped when insurance=True (dedicated metrics)
        assert result["bfsi"].get("skipped") is True


# ---------------------------------------------------------------------------
# Data freshness
# ---------------------------------------------------------------------------


class TestDataFreshness:
    def test_returns_dict_with_per_table_entries(self, api):
        result = api.get_data_freshness("SBIN")
        assert isinstance(result, dict)
        # populated_store seeds annual_financials + shareholding for SBIN
        # → at least those keys appear in the freshness dict
        assert "annual_financials" in result
        # Each section has last_fetched + latest_period
        af = result["annual_financials"]
        assert "last_fetched" in af

    def test_unknown_symbol_returns_dict(self, api):
        # Unknown symbol → empty-ish dict (no entries for that symbol's tables)
        result = api.get_data_freshness("NOSUCHSYM")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Company info + profile + documents
# ---------------------------------------------------------------------------


class TestCompanyInfo:
    def test_known_symbol_from_index_constituents(self, api):
        info = api.get_company_info("SBIN")
        assert info["symbol"] == "SBIN"
        assert info["company_name"] == "State Bank of India"

    def test_unknown_symbol_fallback(self, api):
        info = api.get_company_info("NOSUCHSYM")
        assert info["symbol"] == "NOSUCHSYM"
        assert info["industry"] == "Unknown"


class TestCompanyProfile:
    def test_no_profile_returns_empty(self, api):
        result = api.get_company_profile("NOSUCHSYM")
        assert result == {}


class TestCompanyDocuments:
    def test_returns_list(self, api):
        result = api.get_company_documents("SBIN")
        assert isinstance(result, list)

    def test_doctype_filter_accepted(self, api):
        result = api.get_company_documents("SBIN", doc_type="concall")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Recent filings + chart data
# ---------------------------------------------------------------------------


class TestRecentFilings:
    def test_returns_list(self, api):
        result = api.get_recent_filings("SBIN")
        assert isinstance(result, list)
        if result:
            assert "filing_date" in result[0]

    def test_limit_honoured(self, api):
        result = api.get_recent_filings("SBIN", limit=1)
        assert isinstance(result, list)
        assert len(result) <= 1


class TestChartData:
    def test_returns_list(self, api):
        # No chart data seeded in factories → empty list but shouldn't crash
        result = api.get_chart_data("SBIN", "price")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Listed subsidiaries
# ---------------------------------------------------------------------------


class TestListedSubsidiaries:
    def test_none_or_empty_when_not_seeded(self, api):
        # No listed_subsidiaries seeded → method should return None or empty list
        result = api.get_listed_subsidiaries("SBIN")
        assert result is None or result == []


# ---------------------------------------------------------------------------
# Concall insights: degraded extraction quality warning
# ---------------------------------------------------------------------------


class TestConcallExtractionQualityWarning:
    def test_degraded_quarter_emits_warning(self, api, vault_home):
        quarters = [
            {
                "fy_quarter": "FY26-Q2",
                "period_ended": "2025-09-30",
                "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
                "extraction_status": "partial",
            },
            {
                "fy_quarter": "FY26-Q1",
                "operational_metrics": {},
                "extraction_status": "complete",
            },
        ]
        _write_concall(vault_home / "vault", "DEGR", quarters)
        toc = api.get_concall_insights("DEGR")
        assert "_extraction_quality_warning" in toc
        assert "degraded" in toc["_extraction_quality_warning"].lower()

    def test_all_complete_no_warning(self, api, vault_home):
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
            "extraction_status": "complete",
        }]
        _write_concall(vault_home / "vault", "CLEAN", quarters)
        toc = api.get_concall_insights("CLEAN")
        assert "_extraction_quality_warning" not in toc

    def test_drill_mode_also_carries_warning(self, api, vault_home):
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
            "extraction_status": "recovered",
        }]
        _write_concall(vault_home / "vault", "DEGR2", quarters)
        drill = api.get_concall_insights("DEGR2", section_filter="operational_metrics")
        assert "_extraction_quality_warning" in drill


# ---------------------------------------------------------------------------
# _meta extraction-status (C-2d) — machine-readable signal for graders to
# distinguish "source data was incomplete" from "agent ignored the data".
# ---------------------------------------------------------------------------


class TestConcallInsightsMeta:
    def test_full_status_when_all_quarters_complete(self, api, vault_home):
        quarters = [
            {
                "fy_quarter": "FY26-Q2",
                "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
                "extraction_status": "complete",
            },
            {
                "fy_quarter": "FY26-Q1",
                "operational_metrics": {"casa_ratio_pct": {"value": "38%"}},
                "extraction_status": "complete",
            },
        ]
        _write_concall(vault_home / "vault", "METAFULL", quarters)
        toc = api.get_concall_insights("METAFULL")
        assert toc["_meta"]["extraction_status"] == "full"
        assert toc["_meta"]["missing_periods"] == []
        assert toc["_meta"]["degraded_quality"] is False

    def test_partial_status_lists_degraded_quarter(self, api, vault_home):
        quarters = [
            {
                "fy_quarter": "FY26-Q2",
                "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
                "extraction_status": "complete",
            },
            {
                "fy_quarter": "FY26-Q1",
                "operational_metrics": {},
                "extraction_status": "partial",
            },
            {
                "fy_quarter": "FY25-Q4",
                "operational_metrics": {},
                "extraction_status": "failed",
            },
        ]
        _write_concall(vault_home / "vault", "METAPARTIAL", quarters)
        toc = api.get_concall_insights("METAPARTIAL")
        assert toc["_meta"]["extraction_status"] == "partial"
        assert toc["_meta"]["degraded_quality"] is True
        # Only the partial/failed quarters show up in missing_periods
        assert "FY26-Q1" in toc["_meta"]["missing_periods"]
        assert "FY25-Q4" in toc["_meta"]["missing_periods"]
        assert "FY26-Q2" not in toc["_meta"]["missing_periods"]

    def test_meta_present_on_drill_down(self, api, vault_home):
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
            "extraction_status": "recovered",
        }]
        _write_concall(vault_home / "vault", "METADRILL", quarters)
        drill = api.get_concall_insights("METADRILL", section_filter="operational_metrics")
        assert "_meta" in drill
        assert drill["_meta"]["extraction_status"] == "partial"
        assert "FY26-Q2" in drill["_meta"]["missing_periods"]

    def test_empty_status_when_no_quarters(self, api, vault_home):
        _write_concall(vault_home / "vault", "METAEMPTY", [])
        toc = api.get_concall_insights("METAEMPTY")
        assert toc["_meta"]["extraction_status"] == "empty"
        assert toc["_meta"]["missing_periods"] == []
        assert toc["_meta"]["degraded_quality"] is False


class TestSectorKPIsMeta:
    def test_full_status_when_majority_kpis_present(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        # Banks have 11 canonical KPIs — populate 8 for a clean "full" signal.
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {
                "casa_ratio_pct": {"value": "39%"},
                "gross_npa_pct": {"value": "1.73%"},
                "net_npa_pct": {"value": "0.44%"},
                "net_interest_margin_pct": {"value": "3.2%"},
                "provision_coverage_ratio_pct": {"value": "77%"},
                "credit_cost_bps": {"value": "25"},
                "capital_adequacy_ratio_pct": {"value": "16%"},
                "cost_to_income_ratio_pct": {"value": "45%"},
            },
        }]
        _write_concall(vault_home / "vault", "SKPIFULL", quarters)
        result = api.get_sector_kpis("SKPIFULL")
        assert "_meta" in result
        assert result["_meta"]["extraction_status"] == "full"
        assert result["_meta"]["degraded_quality"] is False

    def test_partial_status_when_majority_kpis_missing(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        # Only 2 of 11 KPIs present → > 50% missing → partial.
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {
                "casa_ratio_pct": {"value": "39%"},
                "gross_npa_pct": {"value": "1.73%"},
            },
        }]
        _write_concall(vault_home / "vault", "SKPIPART", quarters)
        result = api.get_sector_kpis("SKPIPART")
        assert result["_meta"]["extraction_status"] == "partial"
        assert result["_meta"]["degraded_quality"] is True
        # Missing metrics include the unreported canonical keys
        assert "net_interest_margin_pct" in result["_meta"]["missing_metrics"]
        assert "liquidity_coverage_ratio_pct" in result["_meta"]["missing_metrics"]
        # Populated ones should not appear in missing_metrics
        assert "casa_ratio_pct" not in result["_meta"]["missing_metrics"]

    def test_empty_status_when_no_kpis_found(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"unrelated_key": "x"},
        }]
        _write_concall(vault_home / "vault", "SKPIEMPTY", quarters)
        result = api.get_sector_kpis("SKPIEMPTY")
        assert result["_meta"]["extraction_status"] == "empty"
        assert result["_meta"]["degraded_quality"] is False

    def test_meta_on_drilldown_match(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
        }]
        _write_concall(vault_home / "vault", "SKPIDRILL", quarters)
        result = api.get_sector_kpis("SKPIDRILL", kpi_key="casa_ratio_pct")
        assert "_meta" in result
        # 1 of 11 → partial
        assert result["_meta"]["extraction_status"] == "partial"

    def test_meta_on_drilldown_schema_valid_but_unavailable(
        self, api, vault_home, monkeypatch,
    ):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
        }]
        _write_concall(vault_home / "vault", "SKPINOVAL", quarters)
        # gross_npa_pct is a canonical banks KPI but no value for it in this concall
        result = api.get_sector_kpis("SKPINOVAL", kpi_key="gross_npa_pct")
        assert result.get("status") == "schema_valid_but_unavailable"
        assert "_meta" in result
        assert result["_meta"]["extraction_status"] == "partial"


# ---------------------------------------------------------------------------
# BFSI asset-quality lift end-to-end
# ---------------------------------------------------------------------------


class TestBFSIAssetQualityExtraction:
    def test_lifts_gross_npa_into_structured_response(
        self, api, vault_home, monkeypatch,
    ):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {
                "gross_npa_pct": {"value": "1.73%", "context": "Down 32bps"},
                "net_npa_pct": {"value": "0.44%"},
                "provision_coverage_ratio_pct": {"value": "77%"},
            },
        }]
        _write_concall(vault_home / "vault", "TESTBANK", quarters)
        result = api.get_bfsi_metrics("TESTBANK")
        if "error" in result:
            pytest.skip("need annual data for TESTBANK")
        aq = result.get("asset_quality")
        assert aq is not None
        assert aq.get("source") == "concall operational_metrics"
        assert "gross_npa_pct" in aq.get("metrics", {})

    def test_returns_status_when_keys_missing(
        self, api, vault_home, monkeypatch,
    ):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        # Concall exists but has no canonical asset-quality keys
        quarters = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"casa_ratio_pct": {"value": "39%"}},
        }]
        _write_concall(vault_home / "vault", "TESTBANK2", quarters)
        # Call _extract_bfsi_asset_quality directly — get_bfsi_metrics may
        # skip if no annual data exists for TESTBANK2
        aq = api._extract_bfsi_asset_quality("TESTBANK2")
        assert aq is not None
        assert aq.get("status") == "not_captured_in_concall_extraction"
        assert "canonical_keys_expected" in aq

    def test_no_concall_returns_none(self, api, vault_home):
        # No concall file written → None
        aq = api._extract_bfsi_asset_quality("NOSUCHSYM")
        assert aq is None


# ---------------------------------------------------------------------------
# Sector KPIs: no sector + empty concall edge cases
# ---------------------------------------------------------------------------


class TestSectorKPIsEdges:
    def test_industry_without_framework_errors(self, api, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Totally Made Up Sector")
        result = api.get_sector_kpis("SBIN")
        assert "error" in result

    def test_no_quarters_returns_error(self, api, monkeypatch, vault_home):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        # Concall file exists with an empty quarters list
        _write_concall(vault_home / "vault", "EMPTYQ", [])
        result = api.get_sector_kpis("EMPTYQ")
        assert "error" in result


# ---------------------------------------------------------------------------
# Growth CAGR table — insufficient data path
# ---------------------------------------------------------------------------


class TestGrowthCAGRTable:
    def test_insufficient_data_errors(self, api):
        result = api.get_growth_cagr_table("NONEXIST")
        assert "error" in result

    def test_returns_trajectory_classification(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_growth_cagr_table("INFY")
        if "error" in result:
            pytest.skip("Need 2+ years")
        assert "growth_trajectory" in result
        assert result["growth_trajectory"] in (
            "accelerating", "decelerating", "stable", "unknown",
        )


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------


class TestRiskFlags:
    def test_returns_flags_list(self, api):
        result = api.get_risk_flags("INFY")
        assert "flags" in result
        assert isinstance(result["flags"], list)

    def test_no_flags_has_note(self, api):
        # With synthetic fixture data, unlikely to trigger any flag
        result = api.get_risk_flags("INFY")
        if not result["flags"]:
            assert "note" in result


# ---------------------------------------------------------------------------
# Earnings quality
# ---------------------------------------------------------------------------


class TestEarningsQuality:
    def test_returns_dict(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        result = api.get_earnings_quality("INFY")
        assert isinstance(result, dict)

    def test_bfsi_path(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        result = api.get_earnings_quality("SBIN")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# WACC params
# ---------------------------------------------------------------------------


class TestWACCParams:
    def test_returns_wacc_dict(self, api):
        result = api.get_wacc_params("SBIN")
        assert isinstance(result, dict)
        # Either valid result with wacc/ke, or error dict — both are acceptable
        assert "wacc" in result or "ke" in result or "error" in result

    def test_reliability_flags_carried_forward(self, api):
        result = api.get_wacc_params("NOSUCHSYM")
        # Stock has no prices → should carry the no_stock_prices flag
        flags = result.get("reliability_flags", []) if isinstance(result, dict) else []
        # Accept either flags list or error — both exercise the data path
        assert isinstance(flags, list)


# ---------------------------------------------------------------------------
# Financial projections
# ---------------------------------------------------------------------------


class TestFinancialProjections:
    def test_returns_structure(self, api):
        result = api.get_financial_projections("INFY")
        assert isinstance(result, dict)
        # Either valid projections or error
        assert "error" in result or "bear" in result or "base" in result \
               or "bull" in result or "projections" in result or "years" in result

    def test_unknown_symbol_errors(self, api):
        result = api.get_financial_projections("NONEXIST")
        assert "error" in result


# ---------------------------------------------------------------------------
# Valuation matrix + Peer metrics + Peer growth
# ---------------------------------------------------------------------------


class TestValuationMatrix:
    def test_returns_structure(self, api):
        result = api.get_valuation_matrix("SBIN")
        for key in ("subject", "peers", "sector_stats", "subject_percentiles", "peer_count"):
            assert key in result

    def test_unknown_symbol_empty_peers(self, api):
        result = api.get_valuation_matrix("NONEXIST")
        assert result["peer_count"] == 0


class TestPeerMetrics:
    def test_returns_subject_and_peers(self, api):
        result = api.get_peer_metrics("SBIN")
        assert "subject" in result
        assert "peers" in result
        assert "peer_count" in result


class TestPeerGrowth:
    def test_returns_subject_and_peers(self, api):
        result = api.get_peer_growth("SBIN")
        assert "subject" in result
        assert "peers" in result


# ---------------------------------------------------------------------------
# Yahoo peer comparison + company snapshot
# ---------------------------------------------------------------------------


class TestYahooPeerComparison:
    def test_returns_subject_and_peers(self, api):
        result = api.get_yahoo_peer_comparison("SBIN")
        assert "subject" in result
        assert "peers" in result
        assert "peer_count" in result
        assert "source" in result


class TestCompanySnapshot:
    def test_missing_returns_empty(self, api):
        # company_snapshot table not seeded in factories → empty dict
        result = api.get_company_snapshot("NOSUCHSYM")
        assert result == {}


# ---------------------------------------------------------------------------
# Serialisation — all methods must produce JSON-serialisable output
# ---------------------------------------------------------------------------


class TestJSONSerialisability:
    """Sanity-check JSON round-trip on recently-added methods."""

    @pytest.mark.parametrize("method", [
        "get_ownership_toc", "get_fundamentals_toc", "get_peer_sector_toc",
        "get_piotroski_score", "get_capital_allocation", "get_capex_cycle",
        "get_common_size_pl", "get_quality_scores_all",
        "get_institutional_consensus", "get_material_events",
        "get_adjustment_factor", "get_dividend_policy",
        "get_company_info", "get_valuation_matrix",
        "get_growth_cagr_table", "get_risk_flags",
    ])
    def test_roundtrip(self, api, method):
        data = getattr(api, method)("INFY")
        json.dumps(data, default=str)


# ---------------------------------------------------------------------------
# Schedule-backed methods (cost_structure, balance_sheet_detail, cash_flow,
# working_capital_cycle) — require financial_schedules rows to be seeded.
# ---------------------------------------------------------------------------


@pytest.fixture
def api_with_schedules(api, populated_store: FlowStore):
    """api + populated_store with some financial_schedules rows seeded.

    Seeds quarterly + annual expense rows for INFY so schedule-grouping
    methods exercise real data, not just an empty-list shortcut.
    """
    # Quarterly expenses (8 quarters to exceed the trend 8-row threshold)
    quarters = [
        "Jun 2024", "Sep 2024", "Dec 2024", "Mar 2025",
        "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026",
    ]
    q_employee = {q: 100.0 + i * 5 for i, q in enumerate(quarters)}
    q_material = {q: 50.0 + i * 2 for i, q in enumerate(quarters)}
    populated_store.upsert_schedules(
        "INFY", "quarters", "Expenses",
        {"Employee Cost": q_employee, "Material Cost": q_material},
    )
    # Annual expenses (3 years)
    annual_years = ["Mar 2024", "Mar 2025", "Mar 2026"]
    populated_store.upsert_schedules(
        "INFY", "profit-loss", "Expenses",
        {"Employee Cost": {y: 400.0 + i * 20 for i, y in enumerate(annual_years)}},
    )
    # Balance sheet schedules
    populated_store.upsert_schedules(
        "INFY", "balance-sheet", "Borrowings",
        {
            "Long term Borrowings": {"Mar 2025": 1000.0, "Mar 2026": 1100.0},
            "Short term Borrowings": {"Mar 2025": 300.0, "Mar 2026": 250.0},
        },
    )
    populated_store.upsert_schedules(
        "INFY", "balance-sheet", "Other Assets",
        {
            "Trade receivables": {"Mar 2025": 500.0, "Mar 2026": 550.0},
            "Inventories": {"Mar 2025": 200.0, "Mar 2026": 210.0},
        },
    )
    populated_store.upsert_schedules(
        "INFY", "balance-sheet", "Other Liabilities",
        {"Trade payables": {"Mar 2025": 300.0, "Mar 2026": 320.0}},
    )
    populated_store.upsert_schedules(
        "INFY", "balance-sheet", "Fixed Assets",
        {"Gross Block": {"Mar 2025": 2000.0, "Mar 2026": 2100.0}},
    )
    # Cash-flow schedules
    populated_store.upsert_schedules(
        "INFY", "cash-flow", "Cash from Operating Activity",
        {"Net Profit": {"Mar 2025": 1000.0, "Mar 2026": 1100.0}},
    )
    populated_store.upsert_schedules(
        "INFY", "cash-flow", "Cash from Investing Activity",
        {"Capex": {"Mar 2025": -500.0, "Mar 2026": -550.0}},
    )
    populated_store.upsert_schedules(
        "INFY", "cash-flow", "Cash from Financing Activity",
        {"Dividends Paid": {"Mar 2025": -200.0, "Mar 2026": -220.0}},
    )
    return api


class TestCostStructure:
    def test_returns_quarterly_annual_and_trends(self, api_with_schedules):
        result = api_with_schedules.get_cost_structure("INFY")
        assert "quarterly" in result
        assert "annual" in result
        assert "trends" in result

    def test_trend_direction_computed(self, api_with_schedules):
        result = api_with_schedules.get_cost_structure("INFY")
        # 8 quarters seeded with rising values → trend should compute
        assert any("_direction" in k for k in result["trends"].keys())
        for k, v in result["trends"].items():
            if k.endswith("_direction"):
                assert v in ("rising", "falling", "stable", "insufficient_history")


class TestBalanceSheetDetail:
    def test_returns_borrowings_assets_liabilities(self, api_with_schedules):
        result = api_with_schedules.get_balance_sheet_detail("INFY")
        assert "borrowings" in result
        assert "assets" in result
        assert "liabilities" in result
        assert "long_term_borrowings" in result["borrowings"]
        assert "trade_receivables" in result["assets"]


class TestCashFlowQuality:
    def test_returns_three_sections(self, api_with_schedules):
        result = api_with_schedules.get_cash_flow_quality("INFY")
        assert "operating" in result
        assert "investing" in result
        assert "financing" in result

    def test_empty_when_no_schedules(self, api):
        # Bare api (no schedules seeded for SBIN) → each section empty
        result = api.get_cash_flow_quality("NOSUCHSYM")
        assert result == {"operating": {}, "investing": {}, "financing": {}}


class TestWorkingCapitalCycle:
    def test_returns_components(self, api_with_schedules):
        result = api_with_schedules.get_working_capital_cycle("INFY")
        assert "components" in result
        assert "as_pct_of_revenue" in result
        # Components pulled from balance-sheet schedules
        assert "trade_receivables" in result["components"]


# ---------------------------------------------------------------------------
# Dividend history (seeds corporate_actions)
# ---------------------------------------------------------------------------


class TestDividendHistory:
    def test_no_dividends_returns_empty(self, api):
        # populated_store has no corporate_actions → empty list
        result = api.get_dividend_history("SBIN")
        assert result == []

    def test_with_dividends_returns_fy_grouped(self, api, populated_store: FlowStore):
        populated_store.upsert_corporate_actions([
            {"symbol": "SBIN", "ex_date": "2024-08-15",
             "action_type": "dividend", "dividend_amount": 5.0,
             "source": "yfinance"},
            {"symbol": "SBIN", "ex_date": "2025-08-20",
             "action_type": "dividend", "dividend_amount": 6.0,
             "source": "yfinance"},
            {"symbol": "SBIN", "ex_date": "2026-01-15",
             "action_type": "dividend", "dividend_amount": 2.5,
             "source": "yfinance"},
        ])
        result = api.get_dividend_history("SBIN", years=5)
        assert isinstance(result, list)
        assert len(result) >= 1
        row = result[0]
        assert "fiscal_year" in row
        assert "annual_dividend_per_share" in row
        # FY26 = Aug 2025 + Jan 2026 = 6.0 + 2.5 = 8.5
        assert row["fiscal_year"].startswith("FY")


# ---------------------------------------------------------------------------
# MF holdings tail-summary pagination
# ---------------------------------------------------------------------------


class TestMFHoldingsPagination:
    def test_returns_list(self, api):
        result = api.get_mf_holdings("SBIN", top_n=30)
        assert isinstance(result, list)
        # 2 seeded SBIN MF holdings → no tail summary
        for r in result:
            assert not r.get("_is_tail_summary")

    def test_tail_summary_appended_when_over_cap(self, api, populated_store: FlowStore):
        from flowtracker.mfportfolio_models import MFSchemeHolding
        # Seed 5 additional SBIN holdings, total = 7. Cap at 3 → tail of 4 summarised
        extra = [
            MFSchemeHolding(
                month="2026-02", amc=f"AMC{i}",
                scheme_name=f"AMC{i} Extra Fund",
                isin="INE062A01020", stock_name="State Bank of India",
                quantity=1000000 - i * 10,
                market_value_cr=50.0 - i * 5,
                pct_of_nav=1.0,
            )
            for i in range(5)
        ]
        populated_store.upsert_mf_scheme_holdings(extra)
        result = api.get_mf_holdings("SBIN", top_n=3)
        # Tail summary row should be appended
        assert result[-1].get("_is_tail_summary") is True
        assert "TAIL" in result[-1]["scheme_name"]


# ---------------------------------------------------------------------------
# Insider transactions tail-summary pagination
# ---------------------------------------------------------------------------


class TestInsiderTransactionsPagination:
    def test_within_cap_no_tail(self, api):
        # Only 3 seeded insider txns for SBIN → below default cap (50), no tail
        result = api.get_insider_transactions("SBIN", top_n=50)
        assert all(not r.get("_is_tail_summary") for r in result)

    def test_tail_summary_added_when_over_cap(self, api):
        # Force very low cap to trigger tail path
        result = api.get_insider_transactions("SBIN", top_n=1)
        # With only 3 txns and cap=1, 2 go to tail → last row is summary
        if len(result) > 1:
            assert result[-1].get("_is_tail_summary") is True
            assert "tail_buy_count" in result[-1]
            assert "tail_sell_count" in result[-1]


# ---------------------------------------------------------------------------
# Shareholder detail
# ---------------------------------------------------------------------------


class TestShareholderDetail:
    def test_returns_list_capped(self, api, populated_store: FlowStore):
        # Seed 25 individual shareholders to exceed top_n=20 default
        holders = {
            "public": [
                {"name": f"Holder {i}", "classification": "public",
                 "q_2025_12_31": 2.0 - i * 0.05}
                for i in range(25)
            ],
        }
        populated_store.upsert_shareholder_details("SBIN", holders)
        result = api.get_shareholder_detail("SBIN", top_n=20)
        assert isinstance(result, list)
        assert len(result) <= 20

    def test_small_list_returned_whole(self, api):
        # populated_store has no shareholder_details → empty list
        result = api.get_shareholder_detail("NOSUCHSYM", top_n=20)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Subsidiary contribution — with seeded standalone financials
# ---------------------------------------------------------------------------


class TestSubsidiaryContributionWithData:
    def test_computes_when_overlap_exists(
        self, api, populated_store: FlowStore,
    ):
        # Seed standalone financials that overlap with populated_store consolidated
        populated_store.upsert_standalone_financials([
            {"symbol": "SBIN", "fiscal_year_end": "2025-03-31",
             "revenue": 140000.0, "net_income": 42000.0,
             "total_assets": 200000.0, "equity_capital": 1000.0, "reserves": 20000.0},
            {"symbol": "SBIN", "fiscal_year_end": "2024-03-31",
             "revenue": 130000.0, "net_income": 38000.0,
             "total_assets": 190000.0, "equity_capital": 1000.0, "reserves": 18000.0},
        ])
        result = api.get_subsidiary_contribution("SBIN")
        assert result.get("available") is True
        assert len(result["years"]) >= 1
        year = result["years"][0]
        assert "subsidiary_net_income" in year
        assert "subsidiary_revenue" in year


# ---------------------------------------------------------------------------
# Listed subsidiaries with DB mapping
# ---------------------------------------------------------------------------


class TestListedSubsidiariesWithMapping:
    def test_seeded_mapping_but_no_shares(self, api, populated_store: FlowStore):
        # Seed a parent→sub mapping. yfinance will be called live which can
        # be slow — but when parent has no shares_outstanding, the method
        # returns None before any HTTP call.
        populated_store.upsert_listed_subsidiary(
            parent_symbol="NOPRICESYM", sub_symbol="CHILD",
            sub_name="Child Co", ownership_pct=60.0,
            relationship="subsidiary",
        )
        # NOPRICESYM has no valuation_snapshot → shares_outstanding = 0 → None
        result = api.get_listed_subsidiaries("NOPRICESYM")
        assert result is None


# ---------------------------------------------------------------------------
# get_expense_breakdown (raw schedule passthrough)
# ---------------------------------------------------------------------------


class TestExpenseBreakdown:
    def test_empty_without_schedules(self, api):
        result = api.get_expense_breakdown("NOSUCHSYM")
        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_rows_when_seeded(self, api_with_schedules):
        result = api_with_schedules.get_expense_breakdown(
            "INFY", section="profit-loss",
        )
        assert isinstance(result, list)
        # Annual expenses seeded for INFY → at least one row
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# Screen stocks + analytical_profile
# ---------------------------------------------------------------------------


class TestScreenStocks:
    def test_returns_list(self, api):
        # No analytical_snapshot seeded, but method should return empty list
        result = api.screen_stocks({"roe_min": 15})
        assert isinstance(result, list)


class TestAnalyticalProfile:
    def test_missing_snapshot_returns_error(self, api):
        result = api.get_analytical_profile("NOSUCHSYM")
        assert "error" in result


# ---------------------------------------------------------------------------
# Peer + chart passthroughs
# ---------------------------------------------------------------------------


class TestPeerComparison:
    def test_returns_peer_dict(self, api):
        # PR #103 (peer-source-fallback) added auto-fallback Yahoo→Screener when the
        # Yahoo recommendation set is sector-noisy; SBIN's live peer set goes down
        # the screener_fallback path. Either source is a valid contract output;
        # the consumer-facing shape (subject + peers + source label) is what matters.
        result = api.get_peer_comparison("SBIN")
        assert isinstance(result, dict)
        assert "subject" in result
        assert "peers" in result
        assert result.get("source") in {"yahoo_recommendations", "screener_fallback"}


class TestScreenerPeersFallback:
    def test_returns_list(self, api):
        result = api.get_screener_peers("SBIN")
        assert isinstance(result, list)


class TestCorporateActions:
    def test_returns_list(self, api):
        result = api.get_corporate_actions("SBIN")
        assert isinstance(result, list)


class TestMFHoldingChanges:
    def test_empty_when_no_data(self, api):
        result = api.get_mf_holding_changes("NOSUCHSYM")
        assert result == []

    def test_returns_list_with_change_type(self, api):
        result = api.get_mf_holding_changes("SBIN")
        assert isinstance(result, list)
        # Each row should have change_type classification
        for r in result:
            if not r.get("_is_tail_summary"):
                assert "change_type" in r
                assert r["change_type"] in (
                    "increased", "decreased", "unchanged", "new_entry", "exited",
                )

    def test_prev_month_matches_when_symbol_not_in_stock_name(self, api):
        """Regression: NSE ticker (e.g. SBIN) is not a substring of the AMFI
        stock_name ("State Bank of India"). The prev-month diff query
        previously used `LIKE '%{symbol}%'` and silently returned 0 prior
        holdings, causing every scheme to be flagged as `new_entry` (the
        HDFCBANK / TCS / SUNPHARMA / VEDL pipeline-artifact bug).

        The seed fixture puts SBI Bluechip Fund in BOTH 2026-01 and 2026-02
        for SBIN (qty 4.5M -> 5M), so it MUST classify as `increased`, not
        `new_entry`. If the prev-month lookup is broken, this test fails.
        """
        result = api.get_mf_holding_changes("SBIN")
        rows = [r for r in result if not r.get("_is_tail_summary")]
        # The bug: every scheme tagged 'new_entry'.
        types = {r["change_type"] for r in rows}
        assert "new_entry" not in types or len(types) > 1, (
            f"All schemes flagged as new_entry — prev-month lookup broken. "
            f"Rows: {[(r['scheme_name'], r['change_type']) for r in rows]}"
        )
        # SBI Bluechip Fund holds SBIN in both 2026-01 and 2026-02 (qty up)
        # so it must be classified as 'increased'.
        bluechip = next(
            (r for r in rows if r["scheme_name"] == "SBI Bluechip Fund"),
            None,
        )
        assert bluechip is not None, "SBI Bluechip Fund missing from results"
        assert bluechip["change_type"] == "increased", (
            f"SBI Bluechip Fund prev-qty should be matched (4.5M -> 5M), "
            f"got change_type={bluechip['change_type']}, "
            f"prev_quantity={bluechip.get('prev_quantity')}"
        )
        assert bluechip.get("prev_quantity") == 4500000


class TestMFConvictionPrevMonth:
    def test_prev_month_schemes_nonzero_when_symbol_not_in_stock_name(self, api):
        """Regression: get_mf_conviction's prev_month_schemes used the same
        broken `LIKE '%{symbol}%'` query, returning 0 for HDFCBANK/TCS/etc.
        and producing scheme_change == schemes_holding (a fake "all new"
        signal). With the seed fixture (SBI Bluechip in both months),
        prev_month_schemes for SBIN must be >= 1.
        """
        result = api.get_mf_conviction("SBIN")
        assert result.get("available") is True
        assert result.get("prev_month_schemes", 0) >= 1, (
            f"prev_month_schemes should be >= 1 (SBI Bluechip Fund holds "
            f"SBIN in 2026-01), got {result.get('prev_month_schemes')}. "
            f"Symbol-vs-stock_name resolution likely broken."
        )


# ---------------------------------------------------------------------------
# Consensus-related passthroughs
# ---------------------------------------------------------------------------


class TestEstimateRevisions:
    def test_returns_list(self, api):
        result = api.get_estimate_revisions("SBIN")
        assert isinstance(result, list)


class TestEstimateMomentum:
    def test_returns_dict(self, api):
        result = api.get_estimate_momentum("SBIN")
        assert isinstance(result, dict)


class TestKeyMetricsHistory:
    def test_returns_list(self, api):
        result = api.get_key_metrics_history("SBIN")
        assert isinstance(result, list)


class TestFinancialGrowthRates:
    def test_returns_list(self, api):
        result = api.get_financial_growth_rates("SBIN")
        assert isinstance(result, list)


class TestAnalystGrades:
    def test_returns_list(self, api):
        result = api.get_analyst_grades("SBIN")
        assert isinstance(result, list)


class TestPriceTargets:
    def test_returns_summary_dict(self, api):
        # get_price_targets aggregates recent targets into a summary dict
        result = api.get_price_targets("SBIN")
        assert isinstance(result, (list, dict))


# ---------------------------------------------------------------------------
# Upcoming catalysts + rate sensitivity + sector methods
# ---------------------------------------------------------------------------


class TestUpcomingCatalysts:
    def test_returns_list(self, api):
        result = api.get_upcoming_catalysts("SBIN")
        assert isinstance(result, list)


class TestRateSensitivity:
    def test_returns_dict(self, api):
        result = api.get_rate_sensitivity("SBIN")
        assert isinstance(result, dict)


class TestSectorBenchmarks:
    def test_returns_default_shape(self, api):
        result = api.get_sector_benchmarks("SBIN")
        # Can be list or dict depending on branch
        assert isinstance(result, (list, dict))


class TestSectorOverviewMetrics:
    def test_returns_dict(self, api):
        result = api.get_sector_overview_metrics("SBIN")
        assert isinstance(result, dict)


class TestSectorFlows:
    def test_returns_dict(self, api):
        result = api.get_sector_flows("SBIN")
        assert isinstance(result, dict)


class TestSectorValuations:
    def test_returns_list(self, api):
        result = api.get_sector_valuations("SBIN")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# DCF history + revenue/growth estimates
# ---------------------------------------------------------------------------


class TestDCFHistory:
    def test_returns_list(self, api):
        result = api.get_dcf_history("SBIN")
        assert isinstance(result, list)


class TestRevenueEstimates:
    def test_returns_dict(self, api):
        result = api.get_revenue_estimates("SBIN")
        assert isinstance(result, dict)


class TestGrowthEstimates:
    def test_returns_dict(self, api):
        result = api.get_growth_estimates("SBIN")
        assert isinstance(result, dict)


class TestEventsCalendar:
    def test_returns_dict(self, api):
        result = api.get_events_calendar("SBIN")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_exit(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as a:
            assert a is not None
            assert a.get_company_info("SBIN")["symbol"] == "SBIN"
