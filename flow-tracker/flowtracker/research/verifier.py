"""Verification agent for specialist reports.

Independently spot-checks data accuracy, calculations, and interpretations
in specialist agent reports. Uses a different model to reduce correlated errors.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time

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


VERIFICATION_PROMPT = """You are a verification agent. Your job is to independently spot-check the accuracy of a specialist research report.

You have READ-ONLY access to the same data tools the specialist used. You will:

1. **Verify 3-5 key numerical claims** — re-fetch the data and compare to what the report states.
   - Focus on: revenue/profit numbers, growth rates, margins, ROCE, sector rankings, percentile claims
   - For each claim: state what the report says, what the data shows, and whether they match

2. **Recompute 1-2 calculations** — recalculate growth rates or CAGRs from raw data.
   - E.g., if the report says "5yr revenue CAGR of 18%", verify: (latest/earliest)^(1/5) - 1

3. **Check interpretation validity** — do conclusions follow from data?
   - E.g., "margins expanding" — verify the actual trajectory shows expansion, not a one-quarter blip

4. **Check peer benchmark accuracy** — verify any percentile or ranking claims against sector benchmarks.

5. **Check consistency** — numbers cited in different sections should agree.

## Output Format

End your response with a JSON code block:

```json
{
    "agent_verified": "<agent_name>",
    "symbol": "<SYMBOL>",
    "verdict": "<pass|pass_with_notes|fail>",
    "spot_checks_performed": <number>,
    "issues": [
        {
            "severity": "<error|warning|note>",
            "section": "<section name>",
            "claim": "<what the report says>",
            "actual": "<what the data shows>",
            "data_source": "<tool used to verify>",
            "action": "<correct_number|minor_correction|none>"
        }
    ],
    "corrections": [
        "<specific text replacement instruction>"
    ],
    "overall_data_quality": "<summary>"
}
```

- **verdict = "pass"**: All spot checks match. Report is accurate.
- **verdict = "pass_with_notes"**: Minor discrepancies (rounding, small differences). List corrections.
- **verdict = "fail"**: Significant errors found (wrong numbers, wrong interpretation). Must be corrected.

## Rules
- You are checking ACCURACY, not writing style. Don't critique the prose.
- If you can't verify a claim (tool fails, data unavailable), note it but don't count it as an error.
- Be specific: "Report says 23%, data shows 19.8%" not just "growth rate is wrong".
- 10 turns max — be efficient. Focus on the most important claims.
"""


async def _run_verifier(
    agent_name: str,
    symbol: str,
    envelope: BriefingEnvelope,
    model: str | None = None,
) -> VerificationResult:
    """Run verification on a specialist report."""
    model = model or DEFAULT_VERIFY_MODEL
    tools = _get_verifier_tools(agent_name)

    server = create_sdk_mcp_server(f"verify-{agent_name}", tools=tools)

    options = ClaudeAgentOptions(
        system_prompt=VERIFICATION_PROMPT,
        mcp_servers={f"verify-{agent_name}": server},
        max_turns=10,
        max_budget_usd=0.20,
        permission_mode="bypassPermissions",
        model=model,
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

    # Parse verification result from JSON
    parsed = parse_briefing_from_markdown(result_text)
    if parsed:
        return VerificationResult(
            agent_verified=parsed.get("agent_verified", agent_name),
            symbol=parsed.get("symbol", symbol),
            verdict=parsed.get("verdict", "pass"),
            spot_checks_performed=parsed.get("spot_checks_performed", 0),
            issues=parsed.get("issues", []),
            corrections=parsed.get("corrections", []),
            overall_data_quality=parsed.get("overall_data_quality", ""),
        )

    # Fallback if parsing fails
    return VerificationResult(
        agent_verified=agent_name,
        symbol=symbol,
        verdict="pass",
        spot_checks_performed=0,
        issues=[],
        corrections=[],
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
