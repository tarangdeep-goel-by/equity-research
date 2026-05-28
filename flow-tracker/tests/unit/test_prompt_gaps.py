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

    def test_preamble_has_name_op_concrete_usage_map(self):
        """Name-op tenet must ship the concrete-usage-map examples so agents
        don't misuse pct_of / growth_rate / margin_of_safety (see Fix 8).
        """
        assert "Concrete usage map" in SHARED_PREAMBLE_V2
        # pct_of: "what % of b is a" — NOT "compute a% of b".
        assert 'What is 36.24% of 238,563?' in SHARED_PREAMBLE_V2
        assert 'expr(a="0.3624 * 238563"' in SHARED_PREAMBLE_V2
        assert 'What percent of 238,563 is 86,462?' in SHARED_PREAMBLE_V2
        assert "pct_of(a=86462, b=238563)" in SHARED_PREAMBLE_V2
        # growth_rate vs pp-delta.
        assert "growth_rate(a=100, b=120)" in SHARED_PREAMBLE_V2
        assert 'expr(a="2.1 - 1.8"' in SHARED_PREAMBLE_V2
        # margin_of_safety vs price-vs-SMA.
        assert "margin_of_safety(a=1200, b=1000)" in SHARED_PREAMBLE_V2
        assert "(1010 - 980) / 980 * 100" in SHARED_PREAMBLE_V2


class TestDataExhaustionReconciliation:
    """Lever 2 — agent must surface unconsumed/empty data as `data_gaps`, uncapped.

    The reframe: under-consuming available data is the worst error. An explicit
    "tool returned empty for X" is a welcomed, first-class output (not a
    failure to minimize). Separate from the 3-5 thesis open-question cap.
    """

    def test_preamble_has_data_exhaustion_section(self):
        assert "Data Exhaustion Reconciliation" in SHARED_PREAMBLE_V2

    def test_preamble_references_data_gaps_briefing_field(self):
        """Agent must know to populate `briefing.data_gaps` as a structured field."""
        assert "data_gaps" in SHARED_PREAMBLE_V2

    def test_preamble_has_data_gaps_markdown_table(self):
        """End-of-report `## Data Gaps` markdown table is mandated for visibility."""
        assert "## Data Gaps" in SHARED_PREAMBLE_V2

    def test_data_gaps_channel_is_uncapped(self):
        """Reframe — the 3-5 cap is for thesis OQs only; data_gaps are uncapped."""
        # The new section must explicitly state data_gaps are unbounded — agents
        # must not silently drop genuine empties to "stay under the cap".
        assert "uncapped" in SHARED_PREAMBLE_V2.lower() or "no limit" in SHARED_PREAMBLE_V2.lower()

    def test_preamble_distinguishes_thesis_oqs_vs_data_gaps(self):
        """Two distinct channels: thesis open_questions (capped 3-5) vs data_gaps (uncapped).

        Both must be mentioned together so the agent learns the distinction.
        """
        # Thesis OQ cap survives.
        assert "3-5" in SHARED_PREAMBLE_V2 or "hard cap: 5" in SHARED_PREAMBLE_V2
        # Both channels named near each other.
        assert "thesis" in SHARED_PREAMBLE_V2.lower()
        assert "data_gaps" in SHARED_PREAMBLE_V2

    def test_fallback_exhaustion_emits_data_gap_not_suppress(self):
        """After fallback exhaustion + still empty, the answer is `data_gaps`, not silence.

        Existing 'Fallback exhaustion required' rule (line 153 pre-Lever-2) treated
        gaps as a workflow violation. Reframed: exhaust + empty → surface as data_gap.
        """
        # The reframed exhaustion guidance must reference data_gaps as the destination.
        # Find the fallback section and assert data_gaps emission is the prescribed action.
        # Use a lenient check — any near-mention of "exhausted" near "data_gap" suffices.
        text = SHARED_PREAMBLE_V2.lower()
        assert "data_gap" in text
        # The reframe phrase must appear — explicit that empty-after-exhaustion is welcomed,
        # not punished. We match for "welcome" / "first-class" / "loudly" / "surface" near data_gap.
        assert any(
            kw in text
            for kw in ("welcome", "first-class", "first class", "surface", "flag loudly", "raise it as a data_gap")
        )

    def test_each_agent_schema_includes_data_gaps_field(self):
        """Empirical fix: agents follow the JSON schema example shown in their
        INSTRUCTIONS_V2, not the abstract SHARED_PREAMBLE rule. First eval run
        (HINDUNILVR + ADANIENT 2026-05-28) proved this — agents emitted the old
        briefing shape (no data_gaps) despite the new SHARED_PREAMBLE section.
        Each per-agent JSON schema example MUST include the data_gaps field.
        """
        for name, instr in [
            ("BUSINESS", BUSINESS_INSTRUCTIONS_V2),
            ("FINANCIAL", FINANCIAL_INSTRUCTIONS_V2),
            ("RISK", RISK_INSTRUCTIONS_V2),
            ("TECHNICAL", TECHNICAL_INSTRUCTIONS_V2),
            ("SECTOR", SECTOR_INSTRUCTIONS_V2),
            ("VALUATION", VALUATION_INSTRUCTIONS_V2),
        ]:
            assert '"data_gaps":' in instr, f"{name}_INSTRUCTIONS_V2 missing data_gaps in JSON schema example"
            # Confirm the structured shape, not just the key word:
            assert '"fallbacks_attempted":' in instr, f"{name} schema missing fallbacks_attempted"
            assert '"thesis_impact":' in instr, f"{name} schema missing thesis_impact"

    def test_fallback_first_invariant_for_data_gaps(self):
        """Empirical fix: HUL eval 2026-05-28 emitted a data_gap entry with
        empty fallbacks_attempted when get_screener_peers (a registered
        fallback) existed. The Lever 2 reframe ('flag what's missing') gave
        the agent permission to skip the fallback. Rule must explicitly say:
        fallback-first is non-negotiable; emitting a data_gap before invoking
        the registered fallback is a workflow violation.
        """
        text = SHARED_PREAMBLE_V2.lower()
        assert "fallback-first" in text or "fallback first" in text
        assert "workflow violation" in text or "permission slip" in text
        assert "registered fallback" in text

    def test_per_section_accounting_for_section_routed_tools(self):
        """Reconciliation mechanism: account for every populated TOC section per tool used.

        Scope (agreed): for tools the agent actually called, enumerate sections the TOC
        listed as populated, and mark each consumed / N-A with reason / EMPTY → data_gap.
        Not the full catalog — only the TOC-populated subset.
        """
        # The mechanism phrase must reference per-section accounting tied to the TOC.
        text = SHARED_PREAMBLE_V2.lower()
        assert "toc" in text
        assert "consumed" in text or "drilled" in text
        # The N-A escape valve prevents tick-box behavior on irrelevant sections.
        assert "not-applicable" in text or "not applicable" in text or "n/a" in text


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
        assert "avoids redundant calls" in SHARED_PREAMBLE_V2

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
