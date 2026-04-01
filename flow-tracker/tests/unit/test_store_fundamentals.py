"""Tests for FlowStore fundamentals-related methods.

Tables: quarterly_results, annual_financials, screener_ratios
"""

from __future__ import annotations

import pytest

from flowtracker.store import FlowStore
from tests.fixtures.factories import (
    make_quarterly_result,
    make_quarterly_results,
    make_annual_financials,
    make_screener_ratios,
)


# ---------------------------------------------------------------------------
# quarterly_results
# ---------------------------------------------------------------------------


class TestQuarterlyResults:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        results = make_quarterly_results("SBIN", n=4)
        count = store.upsert_quarterly_results(results)
        assert count == 4
        got = store.get_quarterly_results("SBIN", limit=12)
        assert len(got) == 4
        # Most recent first
        assert got[0].quarter_end >= got[-1].quarter_end

    def test_all_fields_present(self, store: FlowStore):
        qr = make_quarterly_result(symbol="SBIN", quarter_end="2025-12-31",
                                   revenue=52000.0, net_income=18500.0)
        store.upsert_quarterly_results([qr])
        got = store.get_quarterly_results("SBIN", limit=1)
        assert len(got) == 1
        r = got[0]
        assert r.symbol == "SBIN"
        assert r.quarter_end == "2025-12-31"
        assert r.revenue == pytest.approx(52000.0)
        assert r.net_income == pytest.approx(18500.0)
        assert r.gross_profit is not None
        assert r.operating_income is not None
        assert r.ebitda is not None
        assert r.eps is not None
        assert r.operating_margin is not None
        assert r.net_margin is not None
        assert r.expenses is not None
        assert r.other_income is not None
        assert r.depreciation is not None
        assert r.interest is not None
        assert r.profit_before_tax is not None
        assert r.tax_pct is not None

    def test_audit_log_on_revenue_change(self, store: FlowStore):
        store.upsert_quarterly_results([
            make_quarterly_result(symbol="SBIN", quarter_end="2025-12-31", revenue=50000.0),
        ])
        store.upsert_quarterly_results([
            make_quarterly_result(symbol="SBIN", quarter_end="2025-12-31", revenue=52000.0),
        ])
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'quarterly_results'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["field"] == "revenue"
        assert rows[0]["old_value"] == "50000.0"
        assert rows[0]["new_value"] == "52000.0"

    def test_no_audit_on_same_revenue(self, store: FlowStore):
        qr = make_quarterly_result(symbol="SBIN", quarter_end="2025-12-31", revenue=52000.0)
        store.upsert_quarterly_results([qr])
        store.upsert_quarterly_results([qr])
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'quarterly_results'"
        ).fetchall()
        assert len(rows) == 0

    def test_case_normalization_on_get(self, store: FlowStore):
        store.upsert_quarterly_results([
            make_quarterly_result(symbol="SBIN", quarter_end="2025-12-31"),
        ])
        got = store.get_quarterly_results("sbin", limit=1)
        assert len(got) == 1

    def test_get_empty(self, store: FlowStore):
        assert store.get_quarterly_results("SBIN") == []


# ---------------------------------------------------------------------------
# annual_financials
# ---------------------------------------------------------------------------


class TestAnnualFinancials:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        records = make_annual_financials("SBIN", n=5)
        count = store.upsert_annual_financials(records)
        assert count == 5
        got = store.get_annual_financials("SBIN", limit=10)
        assert len(got) == 5
        # Most recent first
        assert got[0].fiscal_year_end >= got[-1].fiscal_year_end

    def test_key_fields_preserved(self, store: FlowStore):
        records = make_annual_financials("SBIN", n=1)
        store.upsert_annual_financials(records)
        got = store.get_annual_financials("SBIN", limit=1)
        assert len(got) == 1
        r = got[0]
        assert r.symbol == "SBIN"
        assert r.revenue is not None
        assert r.net_income is not None
        assert r.eps is not None
        assert r.cfo is not None
        assert r.total_assets is not None
        assert r.borrowings is not None
        assert r.operating_profit is not None
        assert r.total_expenses is not None

    def test_audit_on_revenue_change(self, store: FlowStore):
        from flowtracker.fund_models import AnnualFinancials
        r1 = make_annual_financials("SBIN", n=1)[0]
        store.upsert_annual_financials([r1])
        # Modify revenue
        r2 = r1.model_copy(update={"revenue": r1.revenue + 10000})
        store.upsert_annual_financials([r2])
        rows = store._conn.execute(
            "SELECT * FROM audit_log WHERE table_name = 'annual_financials'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["field"] == "revenue"

    def test_get_empty(self, store: FlowStore):
        assert store.get_annual_financials("SBIN") == []


# ---------------------------------------------------------------------------
# screener_ratios
# ---------------------------------------------------------------------------


class TestScreenerRatios:
    def test_upsert_and_get_round_trip(self, store: FlowStore):
        ratios = make_screener_ratios("SBIN", n=5)
        count = store.upsert_screener_ratios(ratios)
        assert count == 5
        got = store.get_screener_ratios("SBIN", limit=10)
        assert len(got) == 5
        # Most recent first
        assert got[0].fiscal_year_end >= got[-1].fiscal_year_end

    def test_fields_preserved(self, store: FlowStore):
        ratios = make_screener_ratios("SBIN", n=1)
        store.upsert_screener_ratios(ratios)
        got = store.get_screener_ratios("SBIN", limit=1)
        r = got[0]
        assert r.symbol == "SBIN"
        assert r.debtor_days is not None
        assert r.days_payable is not None
        assert r.cash_conversion_cycle is not None
        assert r.working_capital_days is not None
        assert r.roce_pct is not None

    def test_case_normalization(self, store: FlowStore):
        store.upsert_screener_ratios(make_screener_ratios("SBIN", n=1))
        got = store.get_screener_ratios("sbin")
        assert len(got) == 1

    def test_get_empty(self, store: FlowStore):
        assert store.get_screener_ratios("SBIN") == []
