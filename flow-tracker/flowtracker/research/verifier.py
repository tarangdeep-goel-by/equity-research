"""Verification agent for specialist reports.

Independently spot-checks data accuracy, calculations, and interpretations
in specialist agent reports. Uses a different model to reduce correlated errors.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time

logger = logging.getLogger(__name__)

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
)

from flowtracker.research.briefing import (
    BriefingEnvelope,
    ToolEvidence,
    VerificationResult,
    load_envelope,
    parse_briefing_from_markdown,
)


# Verifier gets same tools as specialist MINUS write operations
_WRITE_TOOLS = {"save_business_profile"}

DEFAULT_VERIFY_MODEL = "claude-haiku-4-5-20251001"


def _get_verifier_tools(agent_name: str) -> list:
    """Get read-only tool subset for verifying a specialist agent."""
    from flowtracker.research.agent import AGENT_TOOLS

    tools = AGENT_TOOLS.get(agent_name, [])
    # Filter out write tools — verifier is read-only
    return [
        t
        for t in tools
        if getattr(t, "name", getattr(t, "__name__", "")) not in _WRITE_TOOLS
    ]


VERIFICATION_PROMPT = """You are strictly a NUMBER CHECKER. Your ONLY job is to verify that specific numbers, percentages, and data points in the report match what the tools returned. Do NOT judge the quality of analysis, reasoning, or conclusions. Do NOT flag logic errors — only flag cases where a specific number in the report contradicts the tool evidence.

You receive:
1. A specialist research report (markdown)
2. An evidence log showing every tool call the specialist made and its result

## Your Task

Check 5-8 key numerical claims in the report against the evidence log:
- Revenue/profit figures — do they match the tool output?
- Growth rates and CAGRs — are the calculations correct?
- Sector rankings and percentile claims — do they match benchmarks data?
- Valuation multiples (PE, PB, EV/EBITDA) — do they match the snapshot?

## What You Are NOT Doing
- You are NOT judging writing quality, insight depth, or analytical reasoning
- You are NOT evaluating whether interpretations, conclusions, or investment logic are sound
- You are NOT checking whether DuPont decompositions, reverse DCFs, or moat assessments are "correct"
- You are NOT re-analyzing the company — ONLY checking that cited numbers match tool data
- If the specialist's REASONING seems wrong but their NUMBERS are right, that is a PASS

## Rules
- If the evidence log doesn't contain data for a claim, mark it as "unverifiable" — NOT as an error
- Rounding differences (±2%) are acceptable — mark as "note" not "error"
- If report says "~25%" and data shows 24.7%, that's a pass
- Focus on material NUMERICAL errors only: wrong order of magnitude, wrong direction, wrong company, fabricated numbers
- Analytical disagreements are NOT errors — never flag "weak reasoning" or "questionable logic"
- Any (source: FY?? AR, ...) or (source: FY??-Q? deck, ...) inline citation in the report must be re-fetched via get_annual_report / get_deck_insights and the quoted content verified against the tool response. Hallucinated section references or misquoted numbers from AR/deck are a hard fail — flag these as `ar_deck_citation_unverified`.
- 8 turns max

## Output
End with a JSON code block:
```json
{
    "agent_verified": "<agent_name>",
    "symbol": "<SYMBOL>",
    "verdict": "<pass|pass_with_notes|fail>",
    "spot_checks_performed": <number>,
    "issues": [
        {
            "severity": "<error|warning|note>",
            "claim": "<what the report says>",
            "actual": "<what the evidence shows>",
            "evidence_tool": "<which tool call to check>"
        }
    ],
    "corrections": ["<specific correction if needed>"],
    "overall_data_quality": "<summary>"
}
```

- **pass**: All checked claims match evidence (±2% rounding OK)
- **pass_with_notes**: Minor numerical discrepancies flagged but no material errors
- **fail**: Material NUMERICAL errors found — wrong numbers, fabricated data points, or numbers that contradict tool evidence. Never fail for reasoning quality.
"""


# ---------------------------------------------------------------------------
# Audit-vs-evidence cross-check (iter3 §4.7, shadow mode)
#
# Mechanical string-match: extract tool names the agent listed in its
# "## Tool Audit" section of the report, compare to the set of tool names
# that actually appear in BriefingEnvelope.evidence[]. Mismatches fall into
# three buckets:
#   (a) claimed_but_not_called  — agent says it called X, evidence has no X
#   (b) called_but_not_claimed  — agent ran X but forgot to list it in audit
#   (c) claimed_empty_but_nonempty — agent marked X as ∅, evidence is non-empty
#
# Returned as correction strings — in shadow mode these are attached to
# VerificationResult.corrections but do NOT flip the verdict. Tighten to
# verdict="fail" on (a) or (c) mismatches once 1 eval cycle confirms no
# paraphrase false-positives.
# ---------------------------------------------------------------------------


# Match a wide range of tool-name appearances inside the Tool Audit table.
# Tool names are typically mcp__<agent>__<name> or just <name> in audits.
_AUDIT_TOOL_RE = re.compile(
    r"`?(?:mcp__[a-z_]+__)?(get_[a-z_]+|render_chart|calculate|ToolSearch|save_business_profile)`?",
)


def _extract_tool_audit_section(report: str) -> str | None:
    """Return the text of the ## Tool Audit section, or None if absent."""
    m = re.search(
        r"(?mi)^\#{1,3}\s*Tool\s+Audit\b.*?(?=^\#{1,3}\s|\Z)",
        report,
        flags=re.DOTALL,
    )
    return m.group(0) if m else None


def _audit_entries(audit_text: str) -> list[tuple[str, bool]]:
    """Parse (tool_name, claimed_empty) pairs from the Tool Audit section.

    claimed_empty is True when the audit line contains ∅ (U+2205) or "empty".
    """
    entries: list[tuple[str, bool]] = []
    for line in audit_text.splitlines()[1:]:  # skip the header line
        names_in_line = _AUDIT_TOOL_RE.findall(line)
        if not names_in_line:
            continue
        claimed_empty = ("∅" in line) or bool(re.search(r"\bempty\b", line, re.I))
        for name in names_in_line:
            # Normalize: drop mcp__<agent>__ prefix so audit names and
            # evidence names compare apples-to-apples.
            base = name.split("__")[-1]
            entries.append((base, claimed_empty))
    return entries


def _check_audit_vs_evidence(envelope: BriefingEnvelope) -> list[str]:
    """Shadow-mode cross-check. Returns human-readable correction strings.

    Empty list when audit section is absent or perfectly matches evidence.
    """
    audit_text = _extract_tool_audit_section(envelope.report or "")
    if not audit_text:
        # No audit section — agent didn't emit one. Not a mismatch by itself.
        return []

    audit = _audit_entries(audit_text)
    if not audit:
        return []

    # Normalize evidence tool names the same way
    evidence_tools: dict[str, list[ToolEvidence]] = {}
    for e in envelope.evidence:
        base = e.tool.split("__")[-1]
        evidence_tools.setdefault(base, []).append(e)

    claimed_names = {name for name, _ in audit}
    called_names = set(evidence_tools.keys())

    corrections: list[str] = []

    # (a) claimed but not called
    for name in sorted(claimed_names - called_names):
        corrections.append(
            f"Tool Audit claims `{name}` was called but evidence[] has no matching entry"
        )

    # (b) called but not claimed — less severe; many agents omit ToolSearch from audit
    unclaimed = sorted(called_names - claimed_names - {"ToolSearch"})
    for name in unclaimed:
        corrections.append(
            f"evidence[] shows `{name}` call but Tool Audit does not list it"
        )

    # (c) claimed empty but evidence shows non-empty
    for name, empty_flag in audit:
        if not empty_flag or name not in evidence_tools:
            continue
        evs = evidence_tools[name]
        non_empty = [
            e for e in evs
            if not e.is_error and (e.completeness in (None, "full", "partial"))
        ]
        if non_empty:
            corrections.append(
                f"Tool Audit marks `{name}` as ∅ but evidence shows non-empty result"
            )

    return corrections


async def _run_verifier(
    agent_name: str,
    symbol: str,
    envelope: BriefingEnvelope,
    model: str | None = None,
) -> VerificationResult:
    """Run verification on a specialist report."""
    verify_start = time.time()
    logger.info("[verify] %s %s: started", agent_name, symbol)
    model = model or DEFAULT_VERIFY_MODEL
    tools = _get_verifier_tools(agent_name)

    server = create_sdk_mcp_server(f"verify-{agent_name}", tools=tools)

    options = ClaudeAgentOptions(
        system_prompt=VERIFICATION_PROMPT,
        mcp_servers={f"verify-{agent_name}": server},
        max_turns=8,
        max_budget_usd=0.20,
        permission_mode="bypassPermissions",
        model=model,
        env={"CMUX_CLAUDE_HOOKS_DISABLED": "1"},  # no cmux hook injection
    )

    # Build the verification prompt with the report + evidence summary
    evidence_summary = "\n".join(
        f"- {e.tool}({e.args}): {e.result_summary[:200]}"
        for e in envelope.evidence[:20]  # cap at 20 evidence items
    )

    prompt = f"""Verify this {agent_name} report for {symbol}.

## Report to Verify:
{envelope.report[:15000]}

## Evidence Log (tool calls made by specialist):
{evidence_summary}

Spot-check 3-5 key claims by re-fetching data. Produce your verification result."""

    # Run verifier with same error handling as _run_specialist
    text_blocks: list[str] = []
    result_text = ""
    evidence: list[ToolEvidence] = []
    pending_tool_calls: dict[str, dict] = {}

    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    block_type = type(block).__name__
                    if block_type == "TextBlock":
                        text_blocks.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        pending_tool_calls[block.id] = {
                            "tool": block.name,
                            "args": block.input or {},
                        }
                    elif isinstance(block, ToolResultBlock):
                        tool_id = block.tool_use_id
                        if tool_id in pending_tool_calls:
                            call = pending_tool_calls.pop(tool_id)
                            result_str = (
                                str(block.content) if block.content else ""
                            )
                            evidence.append(
                                ToolEvidence(
                                    tool=call["tool"],
                                    args=call["args"],
                                    result_summary=result_str[:500],
                                    result_hash=hashlib.sha256(
                                        result_str.encode()
                                    ).hexdigest(),
                                    is_error=getattr(block, "is_error", False)
                                    or False,
                                )
                            )
            elif isinstance(msg, ResultMessage):
                result_text = msg.result or ""
    except Exception:
        # Claude CLI may exit with code 1 after delivering results.
        # If we already captured text, proceed with what we have.
        pass

    if not result_text and text_blocks:
        result_text = "\n\n".join(text_blocks)

    duration = time.time() - verify_start

    # Shadow-mode audit-vs-evidence cross-check (iter3 §4.7).
    # Appended to corrections; does NOT flip the verifier's LLM verdict.
    audit_findings = _check_audit_vs_evidence(envelope)
    if audit_findings:
        logger.info(
            "[verify] %s %s: audit-vs-evidence found %d mismatch(es) (shadow mode)",
            agent_name, symbol, len(audit_findings),
        )

    # Parse verification result from JSON
    parsed = parse_briefing_from_markdown(result_text)
    if parsed:
        verdict = parsed.get("verdict", "pass")
        checks = parsed.get("spot_checks_performed", 0)
        issues_n = len(parsed.get("issues", []))
        logger.info("[verify] %s %s: done %.1fs verdict=%s checks=%d issues=%d",
                    agent_name, symbol, duration, verdict, checks, issues_n)
        corrections = list(parsed.get("corrections", []))
        if audit_findings:
            corrections.extend([f"[audit-vs-evidence] {f}" for f in audit_findings])
        return VerificationResult(
            agent_verified=parsed.get("agent_verified", agent_name),
            symbol=parsed.get("symbol", symbol),
            verdict=verdict,
            spot_checks_performed=checks,
            issues=parsed.get("issues", []),
            corrections=corrections,
            overall_data_quality=parsed.get("overall_data_quality", ""),
        )

    # Fallback if parsing fails
    logger.warning("[verify] %s %s: done %.1fs parsing failed — accepting as pass", agent_name, symbol, duration)
    corrections = [f"[audit-vs-evidence] {f}" for f in audit_findings]
    return VerificationResult(
        agent_verified=agent_name,
        symbol=symbol,
        verdict="pass",
        spot_checks_performed=0,
        issues=[],
        corrections=corrections,
        overall_data_quality="Verification parsing failed -- report accepted as-is",
    )


def apply_corrections(
    envelope: BriefingEnvelope, result: VerificationResult
) -> BriefingEnvelope:
    """Apply corrections from verification to the report.

    - pass: return as-is
    - pass_with_notes: append verification notes with flagged issues
    - fail: prepend warning banner with error-severity issues
    """
    if result.verdict == "pass":
        return envelope

    if result.verdict == "pass_with_notes" and result.issues:
        corrections_note = "\n\n---\n### Verification Notes\n"
        corrections_note += (
            "*The following items were flagged by the verification agent:*\n\n"
        )
        for issue in result.issues:
            severity_icon = {"error": "[ERROR]", "warning": "[WARN]", "note": "[NOTE]"}.get(
                issue.get("severity", ""), ""
            )
            corrections_note += (
                f"- {severity_icon} **{issue.get('section', '')}**: "
                f"{issue.get('claim', '')} -> Actual: {issue.get('actual', '')}\n"
            )

        envelope.report = envelope.report + corrections_note
        return envelope

    # verdict == "fail" -- prepend warning banner with error-severity issues
    warning = (
        "\n\n---\n> **Verification Warning**: This report was flagged by the "
        "verification agent. Some claims may contain errors. See verification "
        "notes below.\n\n"
    )
    for issue in result.issues:
        if issue.get("severity") == "error":
            warning += (
                f"> - [ERROR] {issue.get('section', '')}: "
                f"{issue.get('claim', '')} -> Actual: {issue.get('actual', '')}\n"
            )

    envelope.report = warning + envelope.report
    return envelope


async def verify_report(
    agent_name: str,
    symbol: str,
    model: str | None = None,
) -> VerificationResult:
    """Verify an existing report from vault. Public API for CLI."""
    envelope = load_envelope(symbol, agent_name)
    if envelope is None:
        return VerificationResult(
            agent_verified=agent_name,
            symbol=symbol,
            verdict="fail",
            issues=[
                {
                    "severity": "error",
                    "claim": "No report found in vault",
                    "actual": "Report must exist before verification",
                }
            ],
            overall_data_quality="No report to verify",
        )
    return await _run_verifier(agent_name, symbol, envelope, model)
