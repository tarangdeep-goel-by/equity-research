"""Unit tests for the macro specialist agent registration + guardrails."""
from __future__ import annotations

import pytest

from flowtracker.research.agent import (
    AGENT_ALLOWED_BUILTINS,
    AGENT_MAX_BUDGET,
    AGENT_MAX_TURNS,
    AGENT_TIERS,
    AGENT_TOOLS,
    DEFAULT_EFFORT,
    DEFAULT_MODELS,
    _SYNTHESIS_FIELDS,
)
from flowtracker.research.prompts import AGENT_PROMPTS_V2
from flowtracker.research.tools import MACRO_AGENT_TOOLS_V2


def test_macro_prompt_registered():
    assert "macro" in AGENT_PROMPTS_V2
    entry = AGENT_PROMPTS_V2["macro"]
    assert isinstance(entry, tuple) and len(entry) == 2
    system, instructions = entry
    assert isinstance(system, str) and len(system) > 500
    assert isinstance(instructions, str) and len(instructions) > 1000


def test_macro_system_has_guardrails():
    """Every G1..G12 guardrail token must be present in the system prompt."""
    system, _ = AGENT_PROMPTS_V2["macro"]
    # G1 — date-stamped grounding
    assert "today" in system.lower()
    # G2 — FACT/VIEW separation
    assert "FACT:" in system
    assert "VIEW:" in system
    # G3 — source tiering (T1 canonical names)
    assert "Economic Survey" in system
    assert "RBI" in system
    assert "IMF" in system
    # G4 — mechanism required
    assert "mechanism" in system.lower() or "channel" in system.lower()
    # G5 — secular/cyclical
    assert "SECULAR" in system
    assert "CYCLICAL" in system
    assert "EMERGING" in system
    assert "capital" in system.lower()  # capital-cycle check
    # G6 — India-first translation
    assert "India" in system
    assert "INR" in system
    # G7 — Unknown permission
    assert "Unknown" in system
    # G8 — per-claim citation
    assert "citation" in system.lower() or "cite" in system.lower()
    # G9 — no price targets
    assert "BUY" in system  # mentioned as forbidden
    # G10 — stale-policy defense
    assert "MPC" in system or "FOMC" in system
    # G11 — anchor-first
    assert "anchor" in system.lower()
    # G12 — trajectory discipline
    assert "trajectory" in system.lower()


def test_macro_instructions_include_workflow_and_briefing():
    _, instructions = AGENT_PROMPTS_V2["macro"]
    # Workflow steps 0-7 present
    for step in ["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7."]:
        assert step in instructions
    # JSON briefing schema has required fields
    assert "regime_state" in instructions
    assert "secular_tailwinds" in instructions
    assert "secular_headwinds" in instructions
    assert "cyclical_stage" in instructions
    assert "india_transmission" in instructions
    assert "sector_implications" in instructions
    assert "bull_case_triggers" in instructions
    assert "bear_case_triggers" in instructions
    assert "anchors_fetched" in instructions
    assert "trajectory_checks" in instructions


def test_macro_tools_registered():
    """Macro agent has anchor-reading MCP tools (get_macro_catalog + get_macro_anchor)."""
    assert len(MACRO_AGENT_TOOLS_V2) == 2
    tool_names = {t.name for t in MACRO_AGENT_TOOLS_V2}
    assert "get_macro_catalog" in tool_names
    assert "get_macro_anchor" in tool_names


def test_macro_in_agent_constants():
    for d, name in [
        (DEFAULT_MODELS, "DEFAULT_MODELS"),
        (DEFAULT_EFFORT, "DEFAULT_EFFORT"),
        (AGENT_TOOLS, "AGENT_TOOLS"),
        (AGENT_TIERS, "AGENT_TIERS"),
        (AGENT_MAX_TURNS, "AGENT_MAX_TURNS"),
        (AGENT_MAX_BUDGET, "AGENT_MAX_BUDGET"),
        (AGENT_ALLOWED_BUILTINS, "AGENT_ALLOWED_BUILTINS"),
    ]:
        assert "macro" in d, f"{name} missing macro"


def test_macro_tier_is_3():
    assert AGENT_TIERS["macro"] == 3


def test_macro_allowed_web_tools():
    allowed = AGENT_ALLOWED_BUILTINS["macro"]
    assert "WebSearch" in allowed
    assert "WebFetch" in allowed


def test_macro_budget_and_turns_bounded():
    assert AGENT_MAX_BUDGET["macro"] <= 1.0
    assert AGENT_MAX_TURNS["macro"] <= 30


def test_synthesis_fields_include_macro():
    required_macro_fields = {
        "regime_state",
        "secular_tailwinds",
        "secular_headwinds",
        "cyclical_stage",
        "india_transmission",
        "sector_implications",
        "bull_case_triggers",
        "bear_case_triggers",
        "trajectory_checks",
        "anchors_fetched",
    }
    missing = required_macro_fields - _SYNTHESIS_FIELDS
    assert not missing, f"_SYNTHESIS_FIELDS missing macro fields: {missing}"


def test_synthesis_prompt_mentions_9_agents_and_macro_tension():
    from flowtracker.research.prompts import SYNTHESIS_AGENT_PROMPT_V2
    assert "9 specialist" in SYNTHESIS_AGENT_PROMPT_V2
    assert "macro" in SYNTHESIS_AGENT_PROMPT_V2.lower()
    # Macro-vs-micro tension rule
    assert "Macro vs Micro" in SYNTHESIS_AGENT_PROMPT_V2 or "macro vs micro" in SYNTHESIS_AGENT_PROMPT_V2.lower()
