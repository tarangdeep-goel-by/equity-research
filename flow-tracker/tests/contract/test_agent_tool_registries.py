"""Contract tests for V2 agent tool registry membership.

These tests guard mandatory-consult contracts: certain tools (notably
`get_annual_report` and `get_deck_insights`) MUST appear in specific
specialist registries. Accidental removal during refactors should fail CI.

If a registry's expected membership genuinely changes, update the
``AR_MANDATED`` / ``DECK_MANDATED`` sets below in the same commit so the
contract change is explicit and reviewable.
"""

from __future__ import annotations

from flowtracker.research.tools import (
    BUSINESS_AGENT_TOOLS_V2,
    FINANCIAL_AGENT_TOOLS_V2,
    NEWS_AGENT_TOOLS_V2,
    OWNERSHIP_AGENT_TOOLS_V2,
    RESEARCH_TOOLS_V2,
    RISK_AGENT_TOOLS_V2,
    SECTOR_AGENT_TOOLS_V2,
    TECHNICAL_AGENT_TOOLS_V2,
    VALUATION_AGENT_TOOLS_V2,
    get_annual_report,
    get_deck_insights,
)

# Specialist registries that MUST consult the annual report.
AR_MANDATED = {"BUSINESS", "FINANCIAL", "OWNERSHIP", "VALUATION", "RISK"}

# Specialist registries that MUST consult investor deck insights.
DECK_MANDATED = {"BUSINESS", "FINANCIAL", "VALUATION"}

REGISTRIES = {
    "BUSINESS": BUSINESS_AGENT_TOOLS_V2,
    "FINANCIAL": FINANCIAL_AGENT_TOOLS_V2,
    "OWNERSHIP": OWNERSHIP_AGENT_TOOLS_V2,
    "VALUATION": VALUATION_AGENT_TOOLS_V2,
    "RISK": RISK_AGENT_TOOLS_V2,
    "TECHNICAL": TECHNICAL_AGENT_TOOLS_V2,
    "SECTOR": SECTOR_AGENT_TOOLS_V2,
    "NEWS": NEWS_AGENT_TOOLS_V2,
}


def test_get_annual_report_in_mandated_registries():
    """`get_annual_report` must appear in (and only in) the AR-mandated registries."""
    for name, reg in REGISTRIES.items():
        has_ar = get_annual_report in reg
        if name in AR_MANDATED:
            assert has_ar, (
                f"{name} agent registry must include get_annual_report "
                f"(mandatory-consult contract)"
            )
        else:
            assert not has_ar, (
                f"{name} agent registry must NOT include get_annual_report; "
                f"add to AR_MANDATED in this test if the contract changed"
            )


def test_get_deck_insights_in_mandated_registries():
    """`get_deck_insights` must appear in (and only in) the deck-mandated registries."""
    for name, reg in REGISTRIES.items():
        has_deck = get_deck_insights in reg
        if name in DECK_MANDATED:
            assert has_deck, (
                f"{name} agent registry must include get_deck_insights "
                f"(mandatory-consult contract)"
            )
        else:
            assert not has_deck, (
                f"{name} agent registry must NOT include get_deck_insights; "
                f"add to DECK_MANDATED in this test if the contract changed"
            )


def test_ar_deck_tools_in_research_tools_v2_master_list():
    """Both AR/deck tools must be exported via the master V2 registry."""
    assert get_annual_report in RESEARCH_TOOLS_V2
    assert get_deck_insights in RESEARCH_TOOLS_V2
