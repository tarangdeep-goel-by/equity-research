"""Tests for temporal grounding + Unknown-permission injection in build_specialist_prompt.

Covers two LLM failure modes documented in research:
- Temporal grounding drop (25-35% on relative-time queries) — mitigated by
  injecting today = YYYY-MM-DD + per-source staleness.
- Fluent-confidence narration — mitigated by explicit "say Unknown" permission.
"""

from __future__ import annotations

import re

import pytest

from flowtracker.research.prompts import (
    SHARED_PREAMBLE_V2,
    build_specialist_prompt,
)


def test_preamble_has_unknown_permission_block():
    assert "When Data Is Missing" in SHARED_PREAMBLE_V2
    assert "Unknown is permitted" in SHARED_PREAMBLE_V2
    assert "Fabrication is not" in SHARED_PREAMBLE_V2


@pytest.mark.parametrize("agent", ["business", "financials", "risk", "valuation", "ownership"])
def test_specialist_prompt_prepends_temporal_context(agent, populated_store, monkeypatch, tmp_db):
    """Every mandated specialist gets a Time & Data Anchor block with today + freshness."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    sys_p, _ = build_specialist_prompt(agent, symbol="SBIN")
    # Time & Data Anchor block present
    assert "## Time & Data Anchor" in sys_p
    # today = YYYY-MM-DD
    assert re.search(r"today = \d{4}-\d{2}-\d{2}", sys_p), "today anchor missing or malformed"
    # Temporal grounding rule present
    assert "Temporal grounding rule" in sys_p
    # Temporal context must come BEFORE the preamble mandate block
    assert sys_p.index("Time & Data Anchor") < sys_p.index("Scoped Mandatory Consult")


def test_specialist_prompt_includes_data_freshness(populated_store, monkeypatch, tmp_db):
    """Freshness rows should list at least quarterly_results + annual_financials when data exists."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    sys_p, _ = build_specialist_prompt("business", symbol="SBIN")
    # Either populated with latest-period OR marked "not on file" — but the labels must appear
    for label in ("quarterly_results:", "annual_financials:", "shareholding:"):
        assert label in sys_p, f"missing freshness row for {label}"


def test_specialist_prompt_lists_ar_deck_availability(populated_store, monkeypatch, tmp_db, tmp_path):
    """AR + deck on-file lines must appear (content may be 'none' if vault absent)."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    monkeypatch.setenv("HOME", str(tmp_path))
    sys_p, _ = build_specialist_prompt("risk", symbol="SBIN")
    assert "annual_reports_on_file:" in sys_p
    assert "deck_quarters_on_file:" in sys_p


def test_unknown_specialist_returns_empty():
    """Unknown agent name returns empty tuple (existing contract)."""
    assert build_specialist_prompt("nonexistent", symbol="SBIN") == ("", "")
