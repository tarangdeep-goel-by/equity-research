"""Tests that agent prompts reference the expected tool sections."""
from flowtracker.research.prompts import (
    BUSINESS_INSTRUCTIONS,
    BUSINESS_SYSTEM,
    FINANCIAL_INSTRUCTIONS,
    FINANCIAL_SYSTEM,
    OWNERSHIP_INSTRUCTIONS,
    OWNERSHIP_SYSTEM,
    RISK_INSTRUCTIONS,
    RISK_SYSTEM,
    TECHNICAL_INSTRUCTIONS,
    TECHNICAL_SYSTEM,
    SECTOR_INSTRUCTIONS,
    SECTOR_SYSTEM,
    NEWS_INSTRUCTIONS,
    VALUATION_INSTRUCTIONS,
    VALUATION_SYSTEM,
    SHARED_PREAMBLE,
)


class TestPromptCoverage:
    def test_business_calls_valuation(self):
        assert "get_valuation" in BUSINESS_INSTRUCTIONS

    def test_business_calls_events(self):
        assert "get_events_actions" in BUSINESS_INSTRUCTIONS

    def test_risk_has_cost_structure(self):
        assert "cost_structure" in RISK_INSTRUCTIONS

    def test_risk_has_working_capital(self):
        assert "working_capital" in RISK_INSTRUCTIONS

    def test_technical_calls_estimates(self):
        assert "get_estimates" in TECHNICAL_INSTRUCTIONS

    def test_technical_calls_ownership(self):
        assert "get_ownership" in TECHNICAL_INSTRUCTIONS

    def test_sector_calls_fundamentals(self):
        assert "get_fundamentals" in SECTOR_INSTRUCTIONS

    def test_sector_calls_valuation(self):
        assert "get_valuation" in SECTOR_INSTRUCTIONS

    def test_news_calls_company_context(self):
        assert "get_company_context" in NEWS_INSTRUCTIONS

    def test_valuation_has_material_events(self):
        assert "material_events" in VALUATION_INSTRUCTIONS

    def test_valuation_has_cash_flow_quality(self):
        assert "cash_flow_quality" in VALUATION_INSTRUCTIONS

    def test_financial_has_quarterly_bs(self):
        assert "quarterly_balance_sheet" in FINANCIAL_INSTRUCTIONS

    def test_preamble_has_freshness(self):
        assert "data_age_hours" in SHARED_PREAMBLE

    def test_preamble_has_capex_cycle(self):
        assert "Capex cycle" in SHARED_PREAMBLE

    def test_preamble_has_f_score(self):
        assert "F-Score" in SHARED_PREAMBLE

    def test_preamble_has_name_op_concrete_usage_map(self):
        """Name-op tenet must ship the concrete-usage-map examples so agents
        don't misuse pct_of / growth_rate / margin_of_safety (see Fix 8).
        """
        assert "Concrete usage map" in SHARED_PREAMBLE
        # pct_of: "what % of b is a" — NOT "compute a% of b".
        assert 'What is 36.24% of 238,563?' in SHARED_PREAMBLE
        assert 'expr(a="0.3624 * 238563"' in SHARED_PREAMBLE
        assert 'What percent of 238,563 is 86,462?' in SHARED_PREAMBLE
        assert "pct_of(a=86462, b=238563)" in SHARED_PREAMBLE
        # growth_rate vs pp-delta.
        assert "growth_rate(a=100, b=120)" in SHARED_PREAMBLE
        assert 'expr(a="2.1 - 1.8"' in SHARED_PREAMBLE
        # margin_of_safety vs price-vs-SMA.
        assert "margin_of_safety(a=1200, b=1000)" in SHARED_PREAMBLE
        assert "(1010 - 980) / 980 * 100" in SHARED_PREAMBLE


class TestDataExhaustionReconciliation:
    """Lever 2 — agent must surface unconsumed/empty data as `data_gaps`, uncapped.

    The reframe: under-consuming available data is the worst error. An explicit
    "tool returned empty for X" is a welcomed, first-class output (not a
    failure to minimize). Separate from the 3-5 thesis open-question cap.
    """

    def test_preamble_has_data_exhaustion_section(self):
        assert "Data Exhaustion Reconciliation" in SHARED_PREAMBLE

    def test_preamble_references_data_gaps_briefing_field(self):
        """Agent must know to populate `briefing.data_gaps` as a structured field."""
        assert "data_gaps" in SHARED_PREAMBLE

    def test_preamble_has_data_gaps_markdown_table(self):
        """End-of-report `## Data Gaps` markdown table is mandated for visibility."""
        assert "## Data Gaps" in SHARED_PREAMBLE

    def test_data_gaps_channel_is_uncapped(self):
        """Reframe — the 3-5 cap is for thesis OQs only; data_gaps are uncapped."""
        # The new section must explicitly state data_gaps are unbounded — agents
        # must not silently drop genuine empties to "stay under the cap".
        assert "uncapped" in SHARED_PREAMBLE.lower() or "no limit" in SHARED_PREAMBLE.lower()

    def test_preamble_distinguishes_thesis_oqs_vs_data_gaps(self):
        """Two distinct channels: thesis open_questions (capped 3-5) vs data_gaps (uncapped).

        Both must be mentioned together so the agent learns the distinction.
        """
        # Thesis OQ cap survives.
        assert "3-5" in SHARED_PREAMBLE or "hard cap: 5" in SHARED_PREAMBLE
        # Both channels named near each other.
        assert "thesis" in SHARED_PREAMBLE.lower()
        assert "data_gaps" in SHARED_PREAMBLE

    def test_fallback_exhaustion_emits_data_gap_not_suppress(self):
        """After fallback exhaustion + still empty, the answer is `data_gaps`, not silence.

        Existing 'Fallback exhaustion required' rule (line 153 pre-Lever-2) treated
        gaps as a workflow violation. Reframed: exhaust + empty → surface as data_gap.
        """
        # The reframed exhaustion guidance must reference data_gaps as the destination.
        # Find the fallback section and assert data_gaps emission is the prescribed action.
        # Use a lenient check — any near-mention of "exhausted" near "data_gap" suffices.
        text = SHARED_PREAMBLE.lower()
        assert "data_gap" in text
        # The reframe phrase must appear — explicit that empty-after-exhaustion is welcomed,
        # not punished. We match for "welcome" / "first-class" / "loudly" / "surface" near data_gap.
        assert any(
            kw in text
            for kw in ("welcome", "first-class", "first class", "surface", "flag loudly", "raise it as a data_gap")
        )

    def test_each_agent_schema_includes_data_gaps_field(self):
        """Empirical fix: agents follow the JSON schema example shown in their
        INSTRUCTIONS, not the abstract SHARED_PREAMBLE rule. First eval run
        (HINDUNILVR + ADANIENT 2026-05-28) proved this — agents emitted the old
        briefing shape (no data_gaps) despite the new SHARED_PREAMBLE section.
        Each per-agent JSON schema example MUST include the data_gaps field.
        """
        for name, instr in [
            ("BUSINESS", BUSINESS_INSTRUCTIONS),
            ("FINANCIAL", FINANCIAL_INSTRUCTIONS),
            ("RISK", RISK_INSTRUCTIONS),
            ("TECHNICAL", TECHNICAL_INSTRUCTIONS),
            ("SECTOR", SECTOR_INSTRUCTIONS),
            ("VALUATION", VALUATION_INSTRUCTIONS),
        ]:
            assert '"data_gaps":' in instr, f"{name}_INSTRUCTIONS missing data_gaps in JSON schema example"
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
        text = SHARED_PREAMBLE.lower()
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
        text = SHARED_PREAMBLE.lower()
        assert "toc" in text
        assert "consumed" in text or "drilled" in text
        # The N-A escape valve prevents tick-box behavior on irrelevant sections.
        assert "not-applicable" in text or "not applicable" in text or "n/a" in text


class TestNoRedundantFetches:
    """Verify prompts don't instruct re-fetching data already in analytical_profile."""

    def test_financial_no_piotroski_in_quality_scores(self):
        assert "'piotroski'" not in FINANCIAL_INSTRUCTIONS.split("get_quality_scores")[1].split("\n")[0]

    def test_financial_no_beneish_in_quality_scores(self):
        assert "'beneish'" not in FINANCIAL_INSTRUCTIONS.split("get_quality_scores")[1].split("\n")[0]

    def test_risk_no_composite_score_tool(self):
        assert "get_composite_score" not in RISK_INSTRUCTIONS

    def test_valuation_single_valuation_call(self):
        # Should only have one get_valuation call, not two
        count = VALUATION_INSTRUCTIONS.count("Call `get_valuation`")
        assert count == 1, f"Expected 1 get_valuation call, found {count}"

    def test_preamble_warns_against_refetch(self):
        assert "avoids redundant calls" in SHARED_PREAMBLE

    def test_preamble_lists_profile_contents(self):
        assert "Quality scores" in SHARED_PREAMBLE
        assert "Reverse DCF" in SHARED_PREAMBLE
        assert "WACC" in SHARED_PREAMBLE


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


class TestPhase0DedupedPatterns:
    """Phase 0 of prompt-pattern-transfer: 4 patterns previously duplicated across
    5-7 specialist prompts are consolidated into SHARED_PREAMBLE. These tests
    assert (a) the canonical rule lives in SHARED, and (b) no per-agent block
    redundantly re-states the rule.

    The 4 moved patterns:
      - Anomaly Resolution (exhaust tools before asking) → SHARED, agents keep
        only a one-line trio pointer
      - Hard-evidence rule for overriding system signals → SHARED only
      - Single-period anomaly: reclassification-first → SHARED only
      - Structural signal absence ≠ informational → SHARED only

    Per-agent canonical anomaly-resolution tool trios stay where they are (each
    agent has a unique trio for its domain).
    """

    # --- Anomaly Resolution ---

    def test_shared_has_anomaly_resolution_section(self):
        assert "### Anomaly Resolution — Exhaust Tools Before Asking" in SHARED_PREAMBLE
        assert "canonical anomaly-resolution trio" in SHARED_PREAMBLE

    def test_each_specialist_has_anomaly_resolution_trio_pointer(self):
        """Every specialist that previously had a full anomaly-resolution bullet
        now has a short trio pointer that references SHARED. The pointer lives
        in each agent's SYSTEM block (Key Rules)."""
        for name, instr in [
            ("BUSINESS", BUSINESS_SYSTEM),
            ("FINANCIAL", FINANCIAL_SYSTEM),
            ("VALUATION", VALUATION_SYSTEM),
            ("RISK", RISK_SYSTEM),
            ("TECHNICAL", TECHNICAL_SYSTEM),
            ("SECTOR", SECTOR_SYSTEM),
        ]:
            assert "Anomaly-resolution trio" in instr, (
                f"{name} missing 'Anomaly-resolution trio' pointer — should reference SHARED"
            )

    def test_no_specialist_re_states_anomaly_resolution_framing(self):
        """The old 'Anomaly resolution via tools first' / 'Before flagging X as
        an open question, resolve via...' framing must not duplicate the SHARED
        rule in any specialist prompt."""
        for name, instr in [
            ("BUSINESS_INSTRUCTIONS", BUSINESS_INSTRUCTIONS),
            ("BUSINESS_SYSTEM", BUSINESS_SYSTEM),
            ("FINANCIAL_SYSTEM", FINANCIAL_SYSTEM),
            ("VALUATION_SYSTEM", VALUATION_SYSTEM),
            ("RISK_SYSTEM", RISK_SYSTEM),
            ("TECHNICAL_SYSTEM", TECHNICAL_SYSTEM),
            ("SECTOR_SYSTEM", SECTOR_SYSTEM),
        ]:
            assert "Anomaly resolution via tools first" not in instr, (
                f"{name} still contains the old 'Anomaly resolution via tools first' framing"
            )

    # --- Hard-evidence rule ---

    def test_shared_has_hard_evidence_rule(self):
        assert "Hard-evidence rule for overriding system-classified signals" in SHARED_PREAMBLE
        assert "2 INDEPENDENT DATA POINTS" in SHARED_PREAMBLE

    def test_no_specialist_re_states_hard_evidence_rule(self):
        """Hard-evidence rule was previously in 7/7 specialists. After Phase 0
        it must appear only in SHARED."""
        for name, instr in [
            ("BUSINESS_SYSTEM", BUSINESS_SYSTEM),
            ("FINANCIAL_SYSTEM", FINANCIAL_SYSTEM),
            ("OWNERSHIP_SYSTEM", OWNERSHIP_SYSTEM),
            ("VALUATION_SYSTEM", VALUATION_SYSTEM),
            ("RISK_SYSTEM", RISK_SYSTEM),
            ("TECHNICAL_SYSTEM", TECHNICAL_SYSTEM),
            ("SECTOR_SYSTEM", SECTOR_SYSTEM),
        ]:
            assert "Hard-evidence rule for overriding system" not in instr, (
                f"{name} still contains a 'Hard-evidence rule' bullet — should be SHARED-only"
            )

    # --- Single-period reclassification-first ---

    def test_shared_has_single_period_reclassification_rule(self):
        assert "Single-period anomaly → reclassification hypothesis first" in SHARED_PREAMBLE
        assert "block-trade / index rebalance / corporate action" in SHARED_PREAMBLE

    def test_no_specialist_re_states_single_period_rule(self):
        """Single-period reclassification rule was previously in 5+ specialists
        (Bus, Val, Risk, Tech, Sector — Own keeps its 5pp-specific text)."""
        for name, instr in [
            ("BUSINESS_SYSTEM", BUSINESS_SYSTEM),
            ("VALUATION_SYSTEM", VALUATION_SYSTEM),
            ("RISK_SYSTEM", RISK_SYSTEM),
            ("TECHNICAL_SYSTEM", TECHNICAL_SYSTEM),
            ("SECTOR_SYSTEM", SECTOR_SYSTEM),
        ]:
            # The exact generic-framing phrases used pre-Phase-0:
            assert "Single-period anomaly → reclassification hypothesis first" not in instr, (
                f"{name} still contains pre-Phase-0 single-period-reclassification framing"
            )
            assert "Single-period anomaly → reclassification-first" not in instr, (
                f"{name} still contains pre-Phase-0 single-period-reclassification framing"
            )

    # --- Structural absence ---

    def test_shared_has_structural_absence_rule(self):
        assert "Structural signal absence ≠ informational signal" in SHARED_PREAMBLE
        assert "structurally possible" in SHARED_PREAMBLE

    def test_no_specialist_re_states_structural_absence_rule(self):
        """Structural absence rule was previously in 6+ specialists. Only allowed
        per-agent reference is a short pointer like 'per SHARED Structural signal absence'.
        Full framings ('Structural signal absence ≠ informational signal' as a
        bullet header) must not duplicate the SHARED rule."""
        for name, instr in [
            ("BUSINESS_SYSTEM", BUSINESS_SYSTEM),
            ("FINANCIAL_SYSTEM", FINANCIAL_SYSTEM),
            ("VALUATION_SYSTEM", VALUATION_SYSTEM),
            ("RISK_SYSTEM", RISK_SYSTEM),
            ("SECTOR_SYSTEM", SECTOR_SYSTEM),
        ]:
            # The bullet-header version of the rule. (A short "per SHARED ..."
            # reference like the one in OWNERSHIP T9 is allowed.)
            assert "**Structural signal absence ≠ informational signal.**" not in instr, (
                f"{name} still contains the full Structural-absence bullet — should be SHARED-only"
            )

    # --- Signal Interpretation Discipline section as a whole ---

    def test_shared_has_signal_interpretation_section(self):
        """All 3 paired 'don't over-read signals' rules live together in a
        dedicated SHARED section so they're discoverable as a unit."""
        assert "## Signal Interpretation Discipline" in SHARED_PREAMBLE


class TestPhase1NewSharedRules:
    """Phase 1 of prompt-pattern-transfer: 4 genuinely-new rules added to
    SHARED_PREAMBLE so every specialist receives them via inheritance.

    The 4 new patterns:
      - Unit + Time-Period Verification (was Financial T21; now universal)
      - One-Off Adjustment Discipline (was Financial T9; now universal)
      - JSON-to-prose parity (was Risk iter1 first bullet; now universal)
      - Cross-Section Reconciliation OUTPUT (was Ownership-only; now universal,
        with mandatory `reconciliations[]` field in every specialist's briefing schema)
    """

    # --- P1.1 Unit + time-period verification ---

    def test_shared_has_unit_verification_section(self):
        assert "## Unit + Time-Period Verification" in SHARED_PREAMBLE
        assert "Per-period basis" in SHARED_PREAMBLE
        assert "Counts in millions vs crores" in SHARED_PREAMBLE
        assert "TTM vs FY vs YTD vs annualized" in SHARED_PREAMBLE

    def test_financial_unit_verification_tenet_removed(self):
        """Was Fin T21 (later T19 post-Phase-0) — now redundant with SHARED."""
        assert "Unit and time-period verification gate" not in FINANCIAL_SYSTEM, (
            "Fin still contains pre-Phase-1 unit-verification tenet — should be SHARED-only"
        )

    # --- P1.2 One-off adjustment discipline ---

    def test_shared_has_one_off_adjustment_section(self):
        assert "## One-Off Adjustment Discipline" in SHARED_PREAMBLE
        assert "Demerger / merger years" in SHARED_PREAMBLE
        assert "Pandemic-era anomalies (FY21" in SHARED_PREAMBLE

    def test_financial_one_off_tenet_removed(self):
        """Was Fin T9 — now redundant with SHARED."""
        assert "Adjust for one-offs" not in FINANCIAL_SYSTEM, (
            "Fin still contains pre-Phase-1 one-off-adjustment tenet — should be SHARED-only"
        )

    # --- P1.3 JSON-to-prose parity ---

    def test_shared_has_json_prose_parity(self):
        assert "JSON-to-prose parity" in SHARED_PREAMBLE

    def test_risk_iter1_json_prose_bullet_removed(self):
        """Was Risk iter1 first bullet — now SHARED-only. Risk INSTRUCTIONS
        must not re-state the JSON-prose-parity rule."""
        assert "JSON-to-prose parity" not in RISK_INSTRUCTIONS, (
            "Risk INSTRUCTIONS still contains the JSON-to-prose-parity bullet — should be SHARED-only"
        )

    # --- P1.4 Cross-section reconciliation field ---

    def test_shared_has_cross_section_reconciliation_rule(self):
        assert "### Cross-Section Reconciliation" in SHARED_PREAMBLE
        # The SHARED rule must include the structured field template + the
        # "empty list acceptable only if no contradictions" gate.
        assert '"reconciliations":' in SHARED_PREAMBLE
        assert "acceptable ONLY if no contradictions" in SHARED_PREAMBLE

    def test_each_specialist_schema_includes_reconciliations_field(self):
        """The structured-output field is what catches drift — agents that
        skip the field skip the reconciliation step. Every specialist's
        JSON schema example MUST include it."""
        for name, instr in [
            ("BUSINESS", BUSINESS_INSTRUCTIONS),
            ("FINANCIAL", FINANCIAL_INSTRUCTIONS),
            ("OWNERSHIP", OWNERSHIP_INSTRUCTIONS),
            ("VALUATION", VALUATION_INSTRUCTIONS),
            ("RISK", RISK_INSTRUCTIONS),
            ("TECHNICAL", TECHNICAL_INSTRUCTIONS),
            ("SECTOR", SECTOR_INSTRUCTIONS),
        ]:
            assert '"reconciliations":' in instr, (
                f"{name}_INSTRUCTIONS schema missing reconciliations[] field"
            )
            assert '"claims":' in instr, (
                f"{name} reconciliations entry missing claims field"
            )
            assert '"reconciliation":' in instr, (
                f"{name} reconciliations entry missing reconciliation field"
            )

    def test_ownership_keeps_specialist_pitfalls_list(self):
        """Ownership has a workflow step 7 with ownership-specific pitfalls
        (timeframe mismatch, FII handoff conflicts, OFS vs insider selling).
        That ownership-specific guidance must survive the dedupe — only the
        general rule moved up to SHARED."""
        assert "Cross-section reconciliation (per SHARED" in OWNERSHIP_INSTRUCTIONS
        assert "OFS at IPO ≠ insider selling" in OWNERSHIP_INSTRUCTIONS


class TestPhase2PerAgentRules:
    """Phase 2 of prompt-pattern-transfer: 3 adaptive patterns added per-agent
    to the weaker specialists (Bus/Sec/Risk/Tech for triangulation;
    Fin/Risk/Sec for sensitivity; Bus/Fin/Risk/Tech for hypothesis-validation).

    Each pattern lifted from a strong-baseline agent (Val + Fin) and adapted
    with agent-specific content (signal trios, sensitivity inputs, distortion
    examples) so the rule matters for the receiving agent.
    """

    # --- P2.1 Triangulation (2-3 independent signals) ---

    def test_business_has_triangulation_tenet(self):
        """Business gets a 'Triangulate major conclusions' bullet with
        moat-sustainability / management-quality / unit-economics trios."""
        assert "Triangulate major conclusions with 2-3 independent signals" in BUSINESS_SYSTEM
        assert "Moat sustainability:" in BUSINESS_SYSTEM
        assert "pricing power" in BUSINESS_SYSTEM
        assert "capex efficiency" in BUSINESS_SYSTEM

    def test_sector_has_triangulation_tenet(self):
        """Sector gets 'Triangulate' with industry-direction / cycle-stage /
        competitive-rotation trios."""
        assert "Triangulate major conclusions with 2-3 independent signals" in SECTOR_SYSTEM
        assert "Industry direction:" in SECTOR_SYSTEM
        assert "capacity utilization" in SECTOR_SYSTEM

    def test_risk_has_triangulation_tenet(self):
        """Risk gets 'Triangulate' with stress-severity / governance-concern /
        earnings-quality trios."""
        assert "Triangulate major risk conclusions with 2-3 independent signals" in RISK_SYSTEM
        assert "Financial stress severity:" in RISK_SYSTEM
        assert "leverage trend" in RISK_SYSTEM and "cash buffer" in RISK_SYSTEM

    def test_technical_has_triangulation_tenet(self):
        """Technical gets 'Triangulate trend-conviction' with delivery /
        flow / breadth trios."""
        assert "Triangulate trend-conviction calls with 2-3 independent signals" in TECHNICAL_SYSTEM
        assert "Accumulation conviction:" in TECHNICAL_SYSTEM
        assert "delivery %" in TECHNICAL_SYSTEM

    # --- P2.2 Sensitivity on load-bearing assumption ---

    def test_financial_has_sensitivity_tenet(self):
        """Fin T20 adds sensitivity for RM cost / WC days / interest-rate."""
        assert "State sensitivity on the single most load-bearing assumption" in FINANCIAL_SYSTEM
        assert "±200 bps RM" in FINANCIAL_SYSTEM
        assert "working-capital build" in FINANCIAL_SYSTEM

    def test_risk_has_sensitivity_tenet(self):
        """Risk gets sensitivity for default-probability / recovery / coverage."""
        assert "State sensitivity on the single most load-bearing assumption" in RISK_SYSTEM
        assert "±10% recovery" in RISK_SYSTEM or "2× default rate" in RISK_SYSTEM

    def test_sector_has_sensitivity_tenet(self):
        """Sector gets sensitivity for industry growth / capacity cycle."""
        assert "State sensitivity on the single most load-bearing assumption" in SECTOR_SYSTEM
        assert "industry growth rate" in SECTOR_SYSTEM or "recession vs base" in SECTOR_SYSTEM

    def test_technical_does_NOT_get_sensitivity(self):
        """Per plan: skip Tech for sensitivity — not a natural fit for
        chart-based timing analysis."""
        assert "load-bearing assumption" not in TECHNICAL_SYSTEM

    # --- P2.3 Hypothesis validation (compute the correction) ---

    def test_business_has_hypothesis_validation_tenet(self):
        assert "Hypothesis validation — compute the correction" in BUSINESS_SYSTEM
        assert "ex-cash ROCE" in BUSINESS_SYSTEM or "parent-only margin" in BUSINESS_SYSTEM

    def test_financial_has_hypothesis_validation_tenet(self):
        assert "Hypothesis validation — compute the correction" in FINANCIAL_SYSTEM
        assert "segment-pure margin" in FINANCIAL_SYSTEM or "ex-strategic-cash ROCE" in FINANCIAL_SYSTEM

    def test_risk_has_hypothesis_validation_tenet(self):
        assert "Hypothesis validation — compute the correction" in RISK_SYSTEM
        assert "capitalized interest" in RISK_SYSTEM or "gross slippage rate" in RISK_SYSTEM

    def test_technical_has_hypothesis_validation_tenet(self):
        assert "Hypothesis validation — compute the correction" in TECHNICAL_SYSTEM
        assert "ex-block-day rolling delivery" in TECHNICAL_SYSTEM or "active-FII excluding passive" in TECHNICAL_SYSTEM

    def test_sector_keeps_existing_hypothesis_validation(self):
        """Sector already had 'Hypothesis validation' at L1278 (sector iter2).
        Phase 2 should NOT duplicate it — leave the existing rule in place."""
        count = SECTOR_INSTRUCTIONS.count("Hypothesis validation")
        assert count >= 1, "Sector lost its existing hypothesis-validation rule"
