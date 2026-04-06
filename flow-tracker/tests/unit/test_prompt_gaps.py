"""Tests that agent prompts reference the expected tool sections."""
from flowtracker.research.prompts import (
    BUSINESS_INSTRUCTIONS_V2,
    FINANCIAL_INSTRUCTIONS_V2,
    RISK_INSTRUCTIONS_V2,
    TECHNICAL_INSTRUCTIONS_V2,
    SECTOR_INSTRUCTIONS_V2,
    NEWS_INSTRUCTIONS_V2,
    VALUATION_INSTRUCTIONS_V2,
    SHARED_PREAMBLE_V2,
)


class TestPromptCoverage:
    def test_business_calls_valuation(self):
        assert "get_valuation" in BUSINESS_INSTRUCTIONS_V2

    def test_business_calls_events(self):
        assert "get_events_actions" in BUSINESS_INSTRUCTIONS_V2

    def test_risk_has_cost_structure(self):
        assert "cost_structure" in RISK_INSTRUCTIONS_V2

    def test_risk_has_working_capital(self):
        assert "working_capital" in RISK_INSTRUCTIONS_V2

    def test_technical_calls_estimates(self):
        assert "get_estimates" in TECHNICAL_INSTRUCTIONS_V2

    def test_technical_calls_ownership(self):
        assert "get_ownership" in TECHNICAL_INSTRUCTIONS_V2

    def test_sector_calls_fundamentals(self):
        assert "get_fundamentals" in SECTOR_INSTRUCTIONS_V2

    def test_sector_calls_valuation(self):
        assert "get_valuation" in SECTOR_INSTRUCTIONS_V2

    def test_news_calls_company_context(self):
        assert "get_company_context" in NEWS_INSTRUCTIONS_V2

    def test_valuation_has_material_events(self):
        assert "material_events" in VALUATION_INSTRUCTIONS_V2

    def test_valuation_has_cash_flow_quality(self):
        assert "cash_flow_quality" in VALUATION_INSTRUCTIONS_V2

    def test_financial_has_quarterly_bs(self):
        assert "quarterly_balance_sheet" in FINANCIAL_INSTRUCTIONS_V2

    def test_preamble_has_freshness(self):
        assert "data_age_hours" in SHARED_PREAMBLE_V2

    def test_preamble_has_capex_cycle(self):
        assert "Capex cycle" in SHARED_PREAMBLE_V2

    def test_preamble_has_f_score(self):
        assert "F-Score" in SHARED_PREAMBLE_V2


class TestNoRedundantFetches:
    """Verify prompts don't instruct re-fetching data already in analytical_profile."""

    def test_financial_no_piotroski_in_quality_scores(self):
        assert "'piotroski'" not in FINANCIAL_INSTRUCTIONS_V2.split("get_quality_scores")[1].split("\n")[0]

    def test_financial_no_beneish_in_quality_scores(self):
        assert "'beneish'" not in FINANCIAL_INSTRUCTIONS_V2.split("get_quality_scores")[1].split("\n")[0]

    def test_risk_no_composite_score_tool(self):
        assert "get_composite_score" not in RISK_INSTRUCTIONS_V2

    def test_valuation_single_valuation_call(self):
        # Should only have one get_valuation call, not two
        count = VALUATION_INSTRUCTIONS_V2.count("Call `get_valuation`")
        assert count == 1, f"Expected 1 get_valuation call, found {count}"

    def test_preamble_warns_against_refetch(self):
        assert "Do NOT re-fetch" in SHARED_PREAMBLE_V2

    def test_preamble_lists_profile_contents(self):
        assert "Quality scores" in SHARED_PREAMBLE_V2
        assert "Reverse DCF" in SHARED_PREAMBLE_V2
        assert "WACC" in SHARED_PREAMBLE_V2


class TestMFHoldingChangesFix:
    """Verify get_mf_holding_changes returns actual changes, not raw holdings."""

    def test_returns_change_type(self, tmp_db, monkeypatch):
        """After fix, results should have change_type field."""
        from flowtracker.store import FlowStore
        from flowtracker.research.data_api import ResearchDataAPI

        store = FlowStore(db_path=tmp_db)
        # Insert 2 months of MF data for same stock
        for month, qty, val in [("2026-01", 1000, 50.0), ("2026-02", 1200, 60.0)]:
            store._conn.execute(
                "INSERT INTO mf_scheme_holdings "
                "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (month, "HDFC", "HDFC Equity Fund", "INE001A01001", "TESTCO LTD", qty, val, 1.5),
            )
        store._conn.commit()
        store.close()

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            changes = api.get_mf_holding_changes("TESTCO")

        assert len(changes) > 0
        assert any("change_type" in c for c in changes)

    def test_detects_increased(self, tmp_db, monkeypatch):
        """Scheme with higher value in current month should be 'increased'."""
        from flowtracker.store import FlowStore
        from flowtracker.research.data_api import ResearchDataAPI

        store = FlowStore(db_path=tmp_db)
        for month, qty, val in [("2026-01", 1000, 50.0), ("2026-02", 1200, 60.0)]:
            store._conn.execute(
                "INSERT INTO mf_scheme_holdings "
                "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (month, "HDFC", "HDFC Equity Fund", "INE001A01001", "TESTCO LTD", qty, val, 1.5),
            )
        store._conn.commit()
        store.close()

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            changes = api.get_mf_holding_changes("TESTCO")

        increased = [c for c in changes if c.get("change_type") == "increased"]
        assert len(increased) == 1
        assert increased[0]["value_change_cr"] == 10.0

    def test_detects_new_entry(self, tmp_db, monkeypatch):
        """Scheme present only in current month should be 'new_entry'."""
        from flowtracker.store import FlowStore
        from flowtracker.research.data_api import ResearchDataAPI

        store = FlowStore(db_path=tmp_db)
        # Only insert current month — no previous month data
        store._conn.execute(
            "INSERT INTO mf_scheme_holdings "
            "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-02", "ICICI", "ICICI Pru Fund", "INE002A01001", "TESTCO LTD", 500, 25.0, 0.8),
        )
        store._conn.commit()
        store.close()

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            changes = api.get_mf_holding_changes("TESTCO")

        new_entries = [c for c in changes if c.get("change_type") == "new_entry"]
        assert len(new_entries) == 1

    def test_detects_exited(self, tmp_db, monkeypatch):
        """Scheme present in prev month but not current should be 'exited'."""
        from flowtracker.store import FlowStore
        from flowtracker.research.data_api import ResearchDataAPI

        store = FlowStore(db_path=tmp_db)
        # Insert current month scheme A, prev month scheme A + B
        store._conn.execute(
            "INSERT INTO mf_scheme_holdings "
            "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-02", "HDFC", "HDFC Equity Fund", "INE001A01001", "TESTCO LTD", 1200, 60.0, 1.5),
        )
        store._conn.execute(
            "INSERT INTO mf_scheme_holdings "
            "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-01", "HDFC", "HDFC Equity Fund", "INE001A01001", "TESTCO LTD", 1000, 50.0, 1.5),
        )
        store._conn.execute(
            "INSERT INTO mf_scheme_holdings "
            "(month, amc, scheme_name, isin, stock_name, quantity, market_value_cr, pct_of_nav) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("2026-01", "SBI", "SBI Blue Chip", "INE003A01001", "TESTCO LTD", 800, 40.0, 1.0),
        )
        store._conn.commit()
        store.close()

        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            changes = api.get_mf_holding_changes("TESTCO")

        exited = [c for c in changes if c.get("change_type") == "exited"]
        assert len(exited) == 1
        assert exited[0]["scheme_name"] == "SBI Blue Chip"
        assert exited[0]["quantity"] == 0
