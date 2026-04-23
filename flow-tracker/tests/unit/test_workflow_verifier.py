"""Unit tests for plan v3 A+G workflow verifier."""
from __future__ import annotations

import pytest

from flowtracker.research.briefing import AgentTrace, ToolEvidence
from flowtracker.research.workflow_verifier import (
    MANDATORY_TOOLS_BY_AGENT,
    MANDATORY_TOOLS_BY_AGENT_SECTOR,
    PEER_MISMATCH_PRONE_SECTORS,
    check_trace,
    WorkflowViolation,
)


# --- helpers ----------------------------------------------------------------


def _trace(agent: str, calls: list[tuple[str, dict]] | None = None) -> AgentTrace:
    evidence = [
        ToolEvidence(tool=tool, args=args) for tool, args in (calls or [])
    ]
    return AgentTrace(
        agent=agent, symbol="TEST",
        started_at="2026-04-23T00:00:00+00:00",
        finished_at="2026-04-23T00:01:00+00:00",
        tool_calls=evidence,
    )


# --- Rule A: universal per-agent rules --------------------------------------


class TestRiskMandatorySections:
    """Risk agent must call get_annual_report for 3 sections (prompts.py:860)."""

    def test_clean_run_no_violations(self):
        trace = _trace("risk", [
            ("get_annual_report", {"section": "auditor_report"}),
            ("get_annual_report", {"section": "risk_management"}),
            ("get_annual_report", {"section": "related_party"}),
            ("get_company_context", {"section": "concall_insights"}),
        ])
        assert check_trace(trace, sector=None) == []

    def test_missing_auditor_report_flagged(self):
        trace = _trace("risk", [
            ("get_annual_report", {"section": "risk_management"}),
            ("get_annual_report", {"section": "related_party"}),
        ])
        violations = check_trace(trace, sector=None)
        assert len(violations) == 1
        v = violations[0]
        assert v.kind == "missing_mandatory_tool"
        assert v.agent == "risk"
        assert any("auditor_report" in m for m in v.missing_tools)

    def test_missing_all_three_sections_flagged(self):
        trace = _trace("risk", [
            ("get_company_context", {}),
            ("get_valuation", {}),
        ])
        violations = check_trace(trace, sector=None)
        assert len(violations) == 1
        assert len(violations[0].missing_tools) == 3

    def test_different_agent_not_subject_to_risk_rules(self):
        # Business agent with no get_annual_report calls is fine — those rules
        # only apply to risk.
        trace = _trace("business", [("get_company_context", {})])
        violations = check_trace(trace, sector=None)
        assert all(v.agent != "risk" for v in violations)


class TestUniversalMandatoryTools:
    def test_technical_missing_market_context(self):
        trace = _trace("technical", [("get_fair_value", {})])
        violations = check_trace(trace, sector=None)
        assert any(
            "get_market_context" in m for v in violations for m in v.missing_tools
        )

    def test_ownership_missing_get_ownership(self):
        trace = _trace("ownership", [("get_company_context", {})])
        violations = check_trace(trace, sector=None)
        assert any(
            "get_ownership" in m for v in violations for m in v.missing_tools
        )


# --- Rule A: (agent, sector) tuples -----------------------------------------


class TestConglomerateValuation:
    """prompts.py:364 — conglomerate valuation MUST call get_valuation(sotp) + subsidiaries."""

    def test_clean_run_no_sector_violations(self):
        trace = _trace("valuation", [
            ("get_valuation", {"section": "sotp"}),
            ("get_company_context", {"section": "subsidiaries"}),
        ])
        assert check_trace(trace, sector="conglomerate") == []

    def test_missing_sotp_flagged(self):
        trace = _trace("valuation", [
            ("get_valuation", {}),  # calls get_valuation but NOT for sotp
            ("get_company_context", {"section": "subsidiaries"}),
        ])
        violations = check_trace(trace, sector="conglomerate")
        # Universal get_valuation passes (any section); sector rule needs sotp
        sector_violations = [v for v in violations if v.sector == "conglomerate"]
        assert len(sector_violations) == 1
        assert any("sotp" in m for m in sector_violations[0].missing_tools)

    def test_missing_subsidiaries_flagged(self):
        trace = _trace("valuation", [
            ("get_valuation", {"section": "sotp"}),
        ])
        violations = check_trace(trace, sector="conglomerate")
        sector_violations = [v for v in violations if v.sector == "conglomerate"]
        assert any(
            "subsidiaries" in m
            for v in sector_violations for m in v.missing_tools
        )


class TestBFSIFinancials:
    def test_missing_concall_insights_flagged(self):
        trace = _trace("financials", [("get_company_context", {})])
        violations = check_trace(trace, sector="bfsi")
        sector_violations = [v for v in violations if v.sector == "bfsi"]
        assert len(sector_violations) == 1
        assert any("concall_insights" in m for m in sector_violations[0].missing_tools)

    def test_sector_rule_does_not_fire_for_non_bfsi(self):
        trace = _trace("financials", [("get_company_context", {})])
        violations = check_trace(trace, sector="it_services")
        assert all(v.sector != "bfsi" for v in violations)


# --- Rule G: peer-swap enforcement ------------------------------------------


class TestPeerSwapEnforcement:
    def test_platform_sector_without_screener_peers_flagged(self):
        trace = _trace("business", [
            ("get_company_context", {}),
            ("get_yahoo_peers", {}),
        ])
        violations = check_trace(trace, sector="platform")
        peer_violations = [v for v in violations if v.kind == "peer_swap_missing"]
        assert len(peer_violations) == 1
        assert "get_screener_peers" in peer_violations[0].missing_tools

    def test_platform_sector_with_both_peer_tools_clean(self):
        trace = _trace("business", [
            ("get_yahoo_peers", {}),
            ("get_screener_peers", {}),
        ])
        violations = check_trace(trace, sector="platform")
        assert all(v.kind != "peer_swap_missing" for v in violations)

    def test_platform_sector_without_yahoo_peers_no_violation(self):
        # Agent skipped yahoo peers entirely — no peer-swap rule fires
        trace = _trace("business", [("get_company_context", {})])
        violations = check_trace(trace, sector="platform")
        assert all(v.kind != "peer_swap_missing" for v in violations)

    def test_non_prone_sector_skips_peer_swap_rule(self):
        # Regular sector: yahoo peers alone is fine
        trace = _trace("business", [("get_yahoo_peers", {})])
        violations = check_trace(trace, sector="bfsi")
        assert all(v.kind != "peer_swap_missing" for v in violations)


# --- Shape of the violation record ------------------------------------------


class TestViolationRecord:
    def test_summary_is_human_readable(self):
        v = WorkflowViolation(
            kind="missing_mandatory_tool",
            agent="risk", sector="bfsi",
            missing_tools=["get_annual_report(section=auditor_report)"],
            note="test note",
        )
        s = v.summary()
        assert "missing_mandatory_tool" in s
        assert "risk/bfsi" in s
        assert "auditor_report" in s
        assert "test note" in s


# --- Registry sanity --------------------------------------------------------


class TestRegistryShape:
    """Dumb but useful guards against accidental edits that break lookup."""

    def test_all_agent_keys_are_strings(self):
        for agent in MANDATORY_TOOLS_BY_AGENT:
            assert isinstance(agent, str)

    def test_all_sector_keys_are_tuples(self):
        for key in MANDATORY_TOOLS_BY_AGENT_SECTOR:
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert all(isinstance(p, str) for p in key)

    def test_peer_mismatch_prone_is_not_empty(self):
        assert len(PEER_MISMATCH_PRONE_SECTORS) >= 3
        assert "platform" in PEER_MISMATCH_PRONE_SECTORS
