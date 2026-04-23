"""Post-run workflow verifier — plan v3 items A + G.

After a specialist finishes, inspect its `AgentTrace.tool_calls` and compare
against a registry of tools that MUST appear for that (agent, sector) tuple.
Emit `WorkflowViolation` records for anything missing so they can be logged,
surfaced in the trace, and fed into the next-cycle eval.

**Detection-only for the first cycle.** No 2nd-pass retry yet — the plan
calls that out as budget-risky. Ship observability first, measure the real
lift, then decide whether auto-remediation is worth the cost.

## Rule kinds

1. **Mandatory-tool gap (A).** The prompt declares "MUST call X" but the
   agent never invoked it. Example: risk agent must call
   `get_annual_report(section='auditor_report')`.

2. **Peer-swap gap (G).** For sectors where `get_yahoo_peers` frequently
   returns a mismatched peer set, `get_screener_peers` must also be called
   as the explicit fallback.

## Matching semantics

Registry entries are one of:
- `str` — any tool call whose `.tool` equals this name satisfies the rule
- `dict` with keys `{"tool": "<name>", "args": {...}}` — the tool name
  must match AND every key/value in `args` must be present in the
  recorded `ToolEvidence.args`

Sub-section rules (e.g., `get_annual_report(section='auditor_report')`)
therefore match the specific invocation, not just any call to the tool.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from flowtracker.research.briefing import AgentTrace, ToolEvidence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Tool spec: a bare string or {"tool": str, "args": dict}.
ToolSpec = str | dict[str, Any]

# Per-agent mandatory tools that apply across ALL sectors.
#
# Derived from the "MUST call" / "mandatory" declarations in prompts.py as of
# plan v3 (2026-04-23). When a prompt adds a new MUST rule, extend this
# registry and the rule is picked up automatically.
MANDATORY_TOOLS_BY_AGENT: dict[str, list[ToolSpec]] = {
    "risk": [
        # From prompts.py:860 — "you MUST read" auditor_report / risk_management /
        # related_party. These are the highest-signal governance inputs.
        {"tool": "get_annual_report", "args": {"section": "auditor_report"}},
        {"tool": "get_annual_report", "args": {"section": "risk_management"}},
        {"tool": "get_annual_report", "args": {"section": "related_party"}},
    ],
    "technical": [
        # prompts.py:1004 — technical indicators must be pulled.
        "get_market_context",
    ],
    "valuation": [
        # prompts.py:718 Sector Compliance Gate — valuation primary multiple
        # source always comes via get_valuation.
        "get_valuation",
    ],
    "ownership": [
        # prompts.py:529 — public float sub-breakdown is mandatory when Public > 15%.
        # The sub-breakdown tool path goes through get_ownership + shareholder_detail.
        "get_ownership",
    ],
}


# Per (agent, sector) mandatory tools — layered on top of MANDATORY_TOOLS_BY_AGENT.
#
# Stored as (agent, sector) tuples so a lookup for ("valuation", "conglomerate")
# returns the conglomerate-specific SOTP + subsidiaries requirement on top of
# the universal get_valuation rule.
MANDATORY_TOOLS_BY_AGENT_SECTOR: dict[tuple[str, str], list[ToolSpec]] = {
    # prompts.py:364 — Conglomerate valuation MUST call SOTP + subsidiaries
    ("valuation", "conglomerate"): [
        {"tool": "get_valuation", "args": {"section": "sotp"}},
        {"tool": "get_company_context", "args": {"section": "subsidiaries"}},
    ],
    ("business", "conglomerate"): [
        {"tool": "get_company_context", "args": {"section": "subsidiaries"}},
    ],
    # prompts.py:408 — BFSI financials mandatory-metric set. LCR / credit-cost
    # / non-interest-income are extracted from concall_insights financial_metrics.
    ("financials", "bfsi"): [
        {"tool": "get_company_context", "args": {"section": "concall_insights"}},
    ],
    ("financials", "private_bank"): [
        {"tool": "get_company_context", "args": {"section": "concall_insights"}},
    ],
    # Real estate — business & sector skill mandates deck drill before
    # raising presales/collections gaps (sector_skills/real_estate/_shared.md:50).
    ("business", "real_estate"): ["get_deck_insights"],
    ("sector", "real_estate"): ["get_deck_insights"],
}


# Sectors where Yahoo-sourced peers frequently misclassify (wrong industry
# bucket or too few peers) and the agent must fall back to Screener's peer
# set to get a meaningful benchmark.
#
# Evidence: 2026-04-22 re-eval flagged heterogeneous peer sets on platform
# (food-delivery with NBFC peers) and conglomerate (multi-business with
# single-business comparables).
PEER_MISMATCH_PRONE_SECTORS: set[str] = {
    "platform",
    "conglomerate",
    "insurance",     # PolicyBazaar-style insurtech platforms often mismatched
    "holding_company",
    "broker",
}


# ---------------------------------------------------------------------------
# Violation records
# ---------------------------------------------------------------------------


@dataclass
class WorkflowViolation:
    """One detected mandatory-workflow failure for an agent run.

    `kind` determines the downstream treatment:
      - "missing_mandatory_tool" — the agent skipped a tool the prompt
        declared as MUST-call for its (agent, sector) tuple.
      - "peer_swap_missing" — agent is in a peer-mismatch-prone sector and
        called get_yahoo_peers but never get_screener_peers.
    """

    kind: str
    agent: str
    sector: str
    missing_tools: list[str] = field(default_factory=list)
    note: str = ""

    def summary(self) -> str:
        tools = ", ".join(self.missing_tools) if self.missing_tools else "(none)"
        return f"[{self.kind}] {self.agent}/{self.sector}: {tools} — {self.note}"


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _spec_matches_call(spec: ToolSpec, call: ToolEvidence) -> bool:
    """True when a single tool-call satisfies a registry spec."""
    if isinstance(spec, str):
        return call.tool == spec
    # dict spec: tool name must match, and every arg key/value must be
    # present in the recorded call's args.
    if call.tool != spec.get("tool"):
        return False
    want_args = spec.get("args", {}) or {}
    call_args = call.args or {}
    return all(call_args.get(k) == v for k, v in want_args.items())


def _find_missing(specs: list[ToolSpec], calls: list[ToolEvidence]) -> list[str]:
    """Return human-readable names of specs that don't match any call."""
    missing: list[str] = []
    for spec in specs:
        if any(_spec_matches_call(spec, c) for c in calls):
            continue
        missing.append(_spec_label(spec))
    return missing


def _spec_label(spec: ToolSpec) -> str:
    if isinstance(spec, str):
        return spec
    args = spec.get("args", {}) or {}
    if not args:
        return spec.get("tool", "<unknown>")
    arg_str = ",".join(f"{k}={v}" for k, v in args.items())
    return f"{spec.get('tool', '<unknown>')}({arg_str})"


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def check_trace(
    trace: AgentTrace,
    sector: str | None,
) -> list[WorkflowViolation]:
    """Inspect a completed agent trace and return any workflow violations.

    `sector` is the snake_case sector key (e.g., "bfsi", "conglomerate",
    "platform") — the same key the sector_skills directory uses. Pass None
    when the sector is unknown; only agent-level mandatory rules fire.
    """
    agent = trace.agent
    calls = list(trace.tool_calls or [])
    violations: list[WorkflowViolation] = []

    # Rule A — mandatory tools by agent (sector-agnostic).
    universal = MANDATORY_TOOLS_BY_AGENT.get(agent, [])
    missing_universal = _find_missing(universal, calls)
    if missing_universal:
        violations.append(WorkflowViolation(
            kind="missing_mandatory_tool",
            agent=agent,
            sector=sector or "",
            missing_tools=missing_universal,
            note=f"agent prompt declares {len(missing_universal)} MUST-call tool(s) not invoked",
        ))

    # Rule A (sector-specific) — mandatory tools by (agent, sector).
    if sector:
        sector_specific = MANDATORY_TOOLS_BY_AGENT_SECTOR.get((agent, sector), [])
        missing_sector = _find_missing(sector_specific, calls)
        if missing_sector:
            violations.append(WorkflowViolation(
                kind="missing_mandatory_tool",
                agent=agent,
                sector=sector,
                missing_tools=missing_sector,
                note=f"sector-specific {agent}/{sector} rules list {len(missing_sector)} uncalled tool(s)",
            ))

    # Rule G — peer-swap enforcement.
    if sector in PEER_MISMATCH_PRONE_SECTORS:
        called_tools = {c.tool for c in calls}
        if "get_yahoo_peers" in called_tools and "get_screener_peers" not in called_tools:
            violations.append(WorkflowViolation(
                kind="peer_swap_missing",
                agent=agent,
                sector=sector or "",
                missing_tools=["get_screener_peers"],
                note=(
                    "agent called get_yahoo_peers in a mismatch-prone sector "
                    "but never fell back to get_screener_peers"
                ),
            ))

    return violations


def log_violations(violations: list[WorkflowViolation]) -> None:
    """Emit each violation as a WARNING log line.

    Detection-only surface for cycle 1 — we don't retry, we don't block
    synthesis, we just make the gap visible so it shows up in eval logs and
    can be measured. If the next eval round shows this is catching real
    gaps cheaply, we can add a targeted 2nd-pass retry.
    """
    for v in violations:
        logger.warning("[workflow_verifier] %s", v.summary())
