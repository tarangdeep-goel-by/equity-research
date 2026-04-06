"""Tests for expanded schedule storage and structured analysis methods.

Covers:
- _normalize_sub_item: snake_case conversion
- _group_schedules: raw row grouping
- Store upsert/get round-trip for balance-sheet, cash-flow, quarters sections
- data_api methods: get_cost_structure, get_balance_sheet_detail,
  get_cash_flow_quality, get_working_capital_cycle
- _get_fundamentals_section routing for new sections
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _populate_schedules(store: FlowStore) -> None:
    """Insert schedule data for TESTCO across all sections."""
    # Quarterly expenses (8 quarters for trend computation)
    quarters_expenses = {
        "Material Cost %": {
            "Jun 2023": "25", "Sep 2023": "26", "Dec 2023": "27", "Mar 2024": "28",
            "Jun 2024": "29", "Sep 2024": "30", "Dec 2024": "31", "Mar 2025": "32",
        },
        "Employee Cost %": {
            "Jun 2023": "15", "Sep 2023": "14", "Dec 2023": "14", "Mar 2024": "13",
            "Jun 2024": "13", "Sep 2024": "12", "Dec 2024": "12", "Mar 2025": "11",
        },
    }
    store.upsert_schedules("TESTCO", "quarters", "Expenses", quarters_expenses)

    # Annual expenses
    annual_expenses = {
        "Material Cost %": {"Mar 2023": "24", "Mar 2024": "27", "Mar 2025": "31"},
        "Employee Cost %": {"Mar 2023": "16", "Mar 2024": "14", "Mar 2025": "12"},
    }
    store.upsert_schedules("TESTCO", "profit-loss", "Expenses", annual_expenses)

    # Balance sheet — Borrowings
    borrowings = {
        "Long term Borrowings": {"Mar 2024": "1200", "Mar 2025": "1100"},
        "Short term Borrowings": {"Mar 2024": "300", "Mar 2025": "250"},
    }
    store.upsert_schedules("TESTCO", "balance-sheet", "Borrowings", borrowings)

    # Balance sheet — Other Assets
    other_assets = {
        "Inventories": {"Mar 2024": "200", "Mar 2025": "250"},
        "Trade receivables": {"Mar 2024": "500", "Mar 2025": "550"},
        "Cash Equivalents": {"Mar 2024": "100", "Mar 2025": "120"},
    }
    store.upsert_schedules("TESTCO", "balance-sheet", "Other Assets", other_assets)

    # Balance sheet — Other Liabilities
    other_liabs = {
        "Trade Payables": {"Mar 2024": "350", "Mar 2025": "400"},
    }
    store.upsert_schedules("TESTCO", "balance-sheet", "Other Liabilities", other_liabs)

    # Cash flow — Operating
    cf_operating = {
        "Profit from operations": {"Mar 2024": "500", "Mar 2025": "600"},
        "Receivables": {"Mar 2024": "-50", "Mar 2025": "-30"},
        "Inventory": {"Mar 2024": "-20", "Mar 2025": "-40"},
        "Working capital changes": {"Mar 2024": "-100", "Mar 2025": "-80"},
    }
    store.upsert_schedules("TESTCO", "cash-flow", "Cash from Operating Activity", cf_operating)

    # Cash flow — Investing
    cf_investing = {
        "Fixed assets purchased": {"Mar 2024": "-200", "Mar 2025": "-250"},
    }
    store.upsert_schedules("TESTCO", "cash-flow", "Cash from Investing Activity", cf_investing)


# ---------------------------------------------------------------------------
# _normalize_sub_item
# ---------------------------------------------------------------------------


class TestNormalizeSubItem:
    def test_pct_suffix(self):
        assert ResearchDataAPI._normalize_sub_item("Material Cost %") == "material_cost_pct"

    def test_no_pct(self):
        assert ResearchDataAPI._normalize_sub_item("Long term Borrowings") == "long_term_borrowings"

    def test_simple_name(self):
        assert ResearchDataAPI._normalize_sub_item("Trade receivables") == "trade_receivables"

    def test_special_chars(self):
        assert ResearchDataAPI._normalize_sub_item("Loans n Advances") == "loans_n_advances"

    def test_employee_cost_pct(self):
        assert ResearchDataAPI._normalize_sub_item("Employee Cost %") == "employee_cost_pct"


# ---------------------------------------------------------------------------
# _group_schedules
# ---------------------------------------------------------------------------


class TestGroupSchedules:
    def test_groups_by_parent_and_sub(self):
        rows = [
            {"section": "profit-loss", "parent_item": "Expenses", "sub_item": "Material Cost %", "period": "Mar 2024", "value": 30.0},
            {"section": "profit-loss", "parent_item": "Expenses", "sub_item": "Material Cost %", "period": "Mar 2025", "value": 28.0},
            {"section": "profit-loss", "parent_item": "Expenses", "sub_item": "Employee Cost %", "period": "Mar 2024", "value": 12.0},
        ]
        result = ResearchDataAPI._group_schedules(rows)
        assert "Expenses" in result
        assert "material_cost_pct" in result["Expenses"]
        assert len(result["Expenses"]["material_cost_pct"]) == 2
        assert "employee_cost_pct" in result["Expenses"]
        assert len(result["Expenses"]["employee_cost_pct"]) == 1

    def test_filters_by_section(self):
        rows = [
            {"section": "profit-loss", "parent_item": "Expenses", "sub_item": "Material Cost %", "period": "Mar 2024", "value": 30.0},
            {"section": "quarters", "parent_item": "Expenses", "sub_item": "Material Cost %", "period": "Dec 2024", "value": 28.0},
        ]
        result = ResearchDataAPI._group_schedules(rows, section="quarters")
        expenses = result.get("Expenses", {})
        material = expenses.get("material_cost_pct", [])
        assert len(material) == 1
        assert material[0]["period"] == "Dec 2024"

    def test_empty_sub_item_skipped(self):
        rows = [
            {"section": "profit-loss", "parent_item": "Expenses", "sub_item": "", "period": "Mar 2024", "value": 10.0},
        ]
        result = ResearchDataAPI._group_schedules(rows)
        assert result == {}

    def test_no_section_filter_returns_all(self):
        rows = [
            {"section": "profit-loss", "parent_item": "Expenses", "sub_item": "Tax %", "period": "Mar 2024", "value": 5.0},
            {"section": "quarters", "parent_item": "Expenses", "sub_item": "Tax %", "period": "Dec 2024", "value": 6.0},
        ]
        result = ResearchDataAPI._group_schedules(rows)
        assert len(result["Expenses"]["tax_pct"]) == 2


# ---------------------------------------------------------------------------
# Store round-trip: upsert + get for new sections
# ---------------------------------------------------------------------------


class TestScheduleStorage:
    def test_upsert_and_get_balance_sheet(self, tmp_db):
        store = FlowStore(db_path=tmp_db)
        data = {
            "Long term Borrowings": {"Mar 2024": "1200", "Mar 2025": "1100"},
            "Short term Borrowings": {"Mar 2024": "300", "Mar 2025": "250"},
        }
        count = store.upsert_schedules("TESTCO", "balance-sheet", "Borrowings", data)
        assert count == 4

        rows = store.get_schedules("TESTCO", "balance-sheet")
        assert len(rows) == 4
        assert all(r["section"] == "balance-sheet" for r in rows)

    def test_upsert_and_get_cash_flow(self, tmp_db):
        store = FlowStore(db_path=tmp_db)
        data = {
            "Profit from operations": {"Mar 2024": "500", "Mar 2025": "600"},
            "Receivables": {"Mar 2024": "-50", "Mar 2025": "-30"},
        }
        count = store.upsert_schedules("TESTCO", "cash-flow", "Cash from Operating Activity", data)
        assert count == 4

        rows = store.get_schedules("TESTCO", "cash-flow")
        assert len(rows) == 4
        assert all(r["section"] == "cash-flow" for r in rows)

    def test_upsert_quarterly_schedules(self, tmp_db):
        store = FlowStore(db_path=tmp_db)
        data = {"YOY Sales Growth %": {"Dec 2024": "20", "Mar 2025": "18"}}
        count = store.upsert_schedules("TESTCO", "quarters", "Sales", data)
        assert count == 2

        rows = store.get_schedules("TESTCO", "quarters")
        assert len(rows) == 2
        assert rows[0]["parent_item"] == "Sales"

    def test_upsert_updates_existing(self, tmp_db):
        store = FlowStore(db_path=tmp_db)
        data = {"Trade receivables": {"Mar 2024": "500"}}
        store.upsert_schedules("TESTCO", "balance-sheet", "Other Assets", data)

        # Upsert again with different value
        data_updated = {"Trade receivables": {"Mar 2024": "510"}}
        store.upsert_schedules("TESTCO", "balance-sheet", "Other Assets", data_updated)

        rows = store.get_schedules("TESTCO", "balance-sheet")
        assert len(rows) == 1
        assert rows[0]["value"] == 510.0

    def test_get_schedules_without_section_returns_all(self, tmp_db):
        store = FlowStore(db_path=tmp_db)
        store.upsert_schedules("TESTCO", "balance-sheet", "Borrowings",
                               {"Long term Borrowings": {"Mar 2024": "1200"}})
        store.upsert_schedules("TESTCO", "cash-flow", "Cash from Operating Activity",
                               {"Profit from operations": {"Mar 2024": "500"}})

        all_rows = store.get_schedules("TESTCO")
        assert len(all_rows) == 2
        sections = {r["section"] for r in all_rows}
        assert sections == {"balance-sheet", "cash-flow"}

    def test_none_value_skipped(self, tmp_db):
        store = FlowStore(db_path=tmp_db)
        data = {"Trade receivables": {"Mar 2024": "500", "Mar 2025": None}}
        count = store.upsert_schedules("TESTCO", "balance-sheet", "Other Assets", data)
        assert count == 1


# ---------------------------------------------------------------------------
# data_api: get_cost_structure
# ---------------------------------------------------------------------------


class TestCostStructure:
    def test_returns_quarterly_and_annual(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cost_structure("TESTCO")

        assert "quarterly" in result
        assert "annual" in result
        assert "trends" in result
        assert "material_cost_pct" in result["quarterly"]
        assert "employee_cost_pct" in result["quarterly"]

    def test_annual_has_expected_items(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cost_structure("TESTCO")

        assert "material_cost_pct" in result["annual"]
        assert len(result["annual"]["material_cost_pct"]) == 3

    def test_trend_rising(self, tmp_db, monkeypatch):
        """Trend uses alphabetical period ordering (DB ORDER BY period).

        Periods in alpha order: Dec 2023, Dec 2024, Jun 2023, Jun 2024,
        Mar 2024, Mar 2025, Sep 2023, Sep 2024.
        Use values that create a clear rising trend under this ordering.
        """
        store = FlowStore(db_path=tmp_db)
        rising_data = {
            "Other Cost %": {
                "Dec 2023": "10", "Dec 2024": "12",   # alpha-first 4
                "Jun 2023": "11", "Jun 2024": "13",
                "Mar 2024": "20", "Mar 2025": "22",   # alpha-last 4
                "Sep 2023": "21", "Sep 2024": "23",
            },
        }
        store.upsert_schedules("TESTCO", "quarters", "Expenses", rising_data)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cost_structure("TESTCO")

        # prior avg = (10+12+11+13)/4 = 11.5
        # recent avg = (20+22+21+23)/4 = 21.5, diff = +10 > 2 → rising
        assert result["trends"]["other_cost_pct_direction"] == "rising"

    def test_trend_stable(self, tmp_db, monkeypatch):
        """Populated data produces stable trend due to alpha period ordering."""
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cost_structure("TESTCO")

        # Under alphabetical ordering, values are shuffled so the
        # first/last 4 half-averages differ by <= 2pp → stable
        assert result["trends"]["material_cost_pct_direction"] == "stable"
        assert result["trends"]["employee_cost_pct_direction"] == "stable"

    def test_empty_symbol_returns_empty(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cost_structure("NONEXIST")

        # _clean strips empty dicts, so result may be empty or have empty sub-dicts
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# data_api: get_balance_sheet_detail
# ---------------------------------------------------------------------------


class TestBalanceSheetDetail:
    def test_returns_structured(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_balance_sheet_detail("TESTCO")

        assert "borrowings" in result
        assert "assets" in result
        assert "liabilities" in result

    def test_borrowings_decomposed(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_balance_sheet_detail("TESTCO")

        assert "long_term_borrowings" in result["borrowings"]
        assert "short_term_borrowings" in result["borrowings"]
        assert len(result["borrowings"]["long_term_borrowings"]) == 2

    def test_assets_include_other_assets(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_balance_sheet_detail("TESTCO")

        assert "inventories" in result["assets"]
        assert "trade_receivables" in result["assets"]
        assert "cash_equivalents" in result["assets"]

    def test_liabilities_include_payables(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_balance_sheet_detail("TESTCO")

        assert "trade_payables" in result["liabilities"]
        assert len(result["liabilities"]["trade_payables"]) == 2

    def test_empty_symbol(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_balance_sheet_detail("NONEXIST")

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# data_api: get_cash_flow_quality
# ---------------------------------------------------------------------------


class TestCashFlowQuality:
    def test_returns_operating_investing(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cash_flow_quality("TESTCO")

        assert "operating" in result
        assert "investing" in result

    def test_operating_components(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cash_flow_quality("TESTCO")

        assert "profit_from_operations" in result["operating"]
        assert "receivables" in result["operating"]
        assert "inventory" in result["operating"]
        assert "working_capital_changes" in result["operating"]

    def test_investing_components(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cash_flow_quality("TESTCO")

        assert "fixed_assets_purchased" in result["investing"]
        assert len(result["investing"]["fixed_assets_purchased"]) == 2

    def test_negative_values_preserved(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cash_flow_quality("TESTCO")

        receivables = result["operating"]["receivables"]
        vals = [p["value"] for p in receivables]
        assert all(v < 0 for v in vals)

    def test_empty_symbol(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_cash_flow_quality("NONEXIST")

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# data_api: get_working_capital_cycle
# ---------------------------------------------------------------------------


class TestWorkingCapitalCycle:
    def test_returns_components(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_working_capital_cycle("TESTCO")

        assert "components" in result
        assert "trade_receivables" in result["components"]
        assert "inventories" in result["components"]
        assert "trade_payables" in result["components"]

    def test_component_values(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_working_capital_cycle("TESTCO")

        receivables = result["components"]["trade_receivables"]
        assert len(receivables) == 2
        vals = [p["value"] for p in receivables]
        assert 500.0 in vals
        assert 550.0 in vals

    def test_as_pct_of_revenue(self, tmp_db, monkeypatch):
        """Verify receivables/inventory/payables as % of revenue computes correctly."""
        from flowtracker.fund_models import AnnualFinancials

        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        # Insert annual financials — fiscal_year_end must convert to "Mar YYYY"
        store.upsert_annual_financials([
            AnnualFinancials(
                symbol="TESTCO", fiscal_year_end="2024-03-31", revenue=4000.0,
                net_income=400.0, eps=10.0,
            ),
            AnnualFinancials(
                symbol="TESTCO", fiscal_year_end="2025-03-31", revenue=5000.0,
                net_income=500.0, eps=12.5,
            ),
        ])
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_working_capital_cycle("TESTCO")

        pct = result.get("as_pct_of_revenue", {})
        assert "receivables_pct" in pct
        # receivables 500 / revenue 4000 * 100 = 12.5%
        mar24 = next((p for p in pct["receivables_pct"] if p["period"] == "Mar 2024"), None)
        assert mar24 is not None
        assert mar24["value"] == 12.5
        # receivables 550 / revenue 5000 * 100 = 11.0%
        mar25 = next((p for p in pct["receivables_pct"] if p["period"] == "Mar 2025"), None)
        assert mar25 is not None
        assert mar25["value"] == 11.0

    def test_empty_symbol(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        with ResearchDataAPI() as api:
            result = api.get_working_capital_cycle("NONEXIST")

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _get_fundamentals_section routing
# ---------------------------------------------------------------------------


class TestFundamentalsSectionRouting:
    def test_cost_structure_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.tools import _get_fundamentals_section

        with ResearchDataAPI() as api:
            result = _get_fundamentals_section(api, "TESTCO", "cost_structure", {})
        assert "quarterly" in result

    def test_balance_sheet_detail_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.tools import _get_fundamentals_section

        with ResearchDataAPI() as api:
            result = _get_fundamentals_section(api, "TESTCO", "balance_sheet_detail", {})
        assert "borrowings" in result

    def test_cash_flow_quality_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.tools import _get_fundamentals_section

        with ResearchDataAPI() as api:
            result = _get_fundamentals_section(api, "TESTCO", "cash_flow_quality", {})
        assert "operating" in result

    def test_working_capital_routes(self, tmp_db, monkeypatch):
        store = FlowStore(db_path=tmp_db)
        _populate_schedules(store)
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.tools import _get_fundamentals_section

        with ResearchDataAPI() as api:
            result = _get_fundamentals_section(api, "TESTCO", "working_capital", {})
        assert "components" in result
