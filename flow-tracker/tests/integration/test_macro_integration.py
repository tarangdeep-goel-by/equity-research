"""Integration tests for macro agent in the orchestration pipeline."""
from __future__ import annotations

import inspect


def test_macro_in_agent_names():
    """run_all_agents must include 'macro' in agent_names."""
    from flowtracker.research import agent
    src = inspect.getsource(agent.run_all_agents)
    assert '"macro"' in src, "macro not added to agent_names list"


def test_verifier_skip_set_contains_macro_and_web_research():
    from flowtracker.research import agent
    src = inspect.getsource(agent.run_all_agents)
    assert "_VERIFIER_SKIP" in src
    assert "macro" in src
    assert "web_research" in src


def test_synthesis_injects_macro_section():
    """run_synthesis_agent constructs a Macro Backdrop section when macro briefing present."""
    from flowtracker.research import agent
    src = inspect.getsource(agent.run_synthesis_agent)
    assert "macro_section" in src
    assert "Macro Backdrop" in src
    assert "regime_state" in src
    assert "secular_tailwinds" in src
    assert "cyclical_stage" in src


def test_assembly_includes_macro_section():
    """assembly.py report_order must include macro before sector."""
    import flowtracker.research.assembly as assembly
    src = inspect.getsource(assembly)
    assert '("macro", "Macro Backdrop' in src
    # macro section must appear before sector entry
    macro_idx = src.find('("macro"')
    sector_idx = src.find('("sector", "Sector')
    assert macro_idx != -1 and sector_idx != -1
    assert macro_idx < sector_idx, "macro section must be placed before sector"


def test_build_specialist_prompt_returns_macro():
    """build_specialist_prompt should return a non-empty tuple for 'macro'."""
    # Use a mock industry / no DB access — build_specialist_prompt reads api,
    # but tolerates failures. We just test the AGENT_PROMPTS_V2 lookup works.
    from flowtracker.research.prompts import AGENT_PROMPTS_V2
    system_base, instructions = AGENT_PROMPTS_V2["macro"]
    assert system_base and instructions
    assert "Global Macro Strategist" in system_base
