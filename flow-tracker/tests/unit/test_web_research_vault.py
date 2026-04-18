"""Tests for web_research agent vault access (task K1).

web_research used to have no MCP tools — only WebSearch/WebFetch — so it
re-downloaded AR/deck/concall PDFs from NSE/BSE instead of reading the
already-extracted vault JSONs. These tests nail down the fix:
  - Vault tools are in its registry
  - Temporal context (today + periods-on-file) is prepended to its prompt
  - Prompt contains the check-vault-first rule
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from flowtracker.research import agent as agent_mod
from flowtracker.research.prompts import WEB_RESEARCH_AGENT_PROMPT
from flowtracker.research.tools import (
    get_annual_report,
    get_concall_insights,
    get_deck_insights,
)


def test_web_research_prompt_has_vault_first_rule():
    """Prompt must instruct the agent to check vault tools before WebSearch."""
    assert "Check Vault Before the Web" in WEB_RESEARCH_AGENT_PROMPT
    assert "get_concall_insights" in WEB_RESEARCH_AGENT_PROMPT
    assert "get_annual_report" in WEB_RESEARCH_AGENT_PROMPT
    assert "get_deck_insights" in WEB_RESEARCH_AGENT_PROMPT
    assert "before you WebSearch or WebFetch" in WEB_RESEARCH_AGENT_PROMPT.lower() or \
           "before you websearch or webfetch" in WEB_RESEARCH_AGENT_PROMPT.lower()


@pytest.mark.asyncio
async def test_run_web_research_agent_passes_vault_tools_and_temporal_context(
    populated_store, monkeypatch, tmp_db, tmp_path,
):
    """run_web_research_agent must pass the 3 vault tools and prepend temporal context."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    monkeypatch.setenv("HOME", str(tmp_path))

    # Seed a synthetic briefing with one open question so the agent actually runs.
    from flowtracker.research.briefing import save_envelope, BriefingEnvelope

    env = BriefingEnvelope(
        agent="business",
        symbol="SBIN",
        status="success",
        report="# stub",
        briefing={
            "agent": "business",
            "symbol": "SBIN",
            "open_questions": ["What is the latest credit-cost guidance?"],
        },
    )
    save_envelope(env)

    captured = {}

    async def fake_run_specialist(**kwargs):
        captured.update(kwargs)
        from flowtracker.research.briefing import BriefingEnvelope as BE
        from flowtracker.research.agent import AgentTrace
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return (
            BE(agent="web_research", symbol="SBIN", status="success",
               report="stub", briefing={"questions_resolved": 0}),
            AgentTrace(
                agent="web_research", symbol="SBIN",
                started_at=now, finished_at=now, status="success",
            ),
        )

    with patch.object(agent_mod, "_run_specialist", side_effect=fake_run_specialist):
        env_out, _trace = await agent_mod.run_web_research_agent("SBIN")

    assert env_out.status == "success"
    # Vault tools are passed
    tools_passed = captured["tools"]
    assert get_concall_insights in tools_passed, "concall tool not passed"
    assert get_annual_report in tools_passed, "annual_report tool not passed"
    assert get_deck_insights in tools_passed, "deck_insights tool not passed"
    assert len(tools_passed) == 3, f"expected exactly 3 tools, got {len(tools_passed)}"
    # Temporal context is prepended
    sys_prompt = captured["system_prompt"]
    assert "Time & Data Anchor" in sys_prompt, "temporal context not prepended"
    # today = YYYY-MM-DD pattern
    import re
    assert re.search(r"today = \d{4}-\d{2}-\d{2}", sys_prompt), "today anchor missing"
    # Check-vault-first rule is present
    assert "Check Vault Before the Web" in sys_prompt
    # User prompt instructs vault-first
    assert "Check vault first" in captured["user_prompt"]
