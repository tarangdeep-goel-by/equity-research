"""Multi-turn research agent using Claude Agent SDK with MCP tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

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
    AgentCost,
    BriefingEnvelope,
    ToolEvidence,
    parse_briefing_from_markdown,
    save_envelope,
)
from flowtracker.research.tools import (
    BUSINESS_AGENT_TOOLS_V2,
    FINANCIAL_AGENT_TOOLS_V2,
    OWNERSHIP_AGENT_TOOLS_V2,
    RISK_AGENT_TOOLS_V2,
    SECTOR_AGENT_TOOLS_V2,
    TECHNICAL_AGENT_TOOLS_V2,
    VALUATION_AGENT_TOOLS_V2,
)


_VAULT_BASE = Path.home() / "vault" / "stocks"
_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


# --- Multi-agent specialist defaults ---

DEFAULT_MODELS: dict[str, str] = {
    "business": "claude-sonnet-4-6",
    "financials": "claude-sonnet-4-6",
    "ownership": "claude-sonnet-4-6",
    "valuation": "claude-sonnet-4-6",
    "risk": "claude-sonnet-4-6",
    "technical": "claude-sonnet-4-6",
    "sector": "claude-sonnet-4-6",
    "synthesis": "claude-sonnet-4-6",
    "verifier": "claude-haiku-4-5-20251001",
    "explainer": "claude-sonnet-4-6",
}

AGENT_TOOLS: dict[str, list] = {
    "business": BUSINESS_AGENT_TOOLS_V2,
    "financials": FINANCIAL_AGENT_TOOLS_V2,
    "ownership": OWNERSHIP_AGENT_TOOLS_V2,
    "valuation": VALUATION_AGENT_TOOLS_V2,
    "risk": RISK_AGENT_TOOLS_V2,
    "technical": TECHNICAL_AGENT_TOOLS_V2,
    "sector": SECTOR_AGENT_TOOLS_V2,
}

# Agent failure severity tiers for synthesis confidence capping
AGENT_TIERS = {
    # Tier 1: Dealbreakers — core financial analysis
    "risk": 1, "financials": 1, "valuation": 1,
    # Tier 2: Core context — business model and ownership
    "business": 2, "ownership": 2,
    # Tier 3: Enhancers — sector and market timing
    "sector": 3, "technical": 3,
}

AGENT_MAX_TURNS: dict[str, int] = {
    "business": 40,
    "financials": 35,
    "ownership": 30,
    "valuation": 30,
    "risk": 30,
    "technical": 30,
    "sector": 25,
}

AGENT_MAX_BUDGET: dict[str, float] = {
    "business": 1.00,
    "financials": 0.75,
    "ownership": 0.60,
    "valuation": 0.60,
    "risk": 0.60,
    "technical": 0.60,
    "sector": 0.50,
}

# Claude Code built-ins that agents should NOT have access to.
# MCP tools (our custom research tools) are registered separately via mcp_servers
# and are always available regardless of this list.
_DISALLOWED_BUILTINS = [
    "Bash", "Write", "Edit", "Read", "Glob", "Grep",
    "NotebookEdit", "Agent", "TodoWrite",
]

# Additional Claude Code built-ins that specific agents ARE allowed to use.
# These get added to allowed_tools (whitelist) on top of MCP tools.
AGENT_ALLOWED_BUILTINS: dict[str, list[str]] = {
    "business": ["WebSearch", "WebFetch"],  # needs web research for industry context
    "sector": ["WebSearch", "WebFetch"],  # needs web research for sector dynamics
}


def generate_business_profile(symbol: str, model: str | None = None) -> Path:
    """Generate a business profile via the business specialist agent.

    Uses the same V2 tools+prompts as run_all_agents (business slot).
    Returns path to the HTML report.
    """
    symbol = symbol.upper()

    envelope = asyncio.run(run_single_agent("business", symbol, model=model))

    report = envelope.report
    if not report or not report.strip():
        raise RuntimeError(f"Business agent returned empty report for {symbol}")

    # Save raw markdown to vault
    profile_dir = _VAULT_BASE / symbol
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.md"
    profile_path.write_text(report)

    # Render HTML
    html = _render_mermaid_to_html(report, profile_dir)
    html_path = _REPORTS_DIR / f"{symbol.lower()}-business.html"
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)

    return html_path


def _render_mermaid_to_html(markdown: str, output_dir: Path) -> str:
    """Convert markdown to HTML with mermaid.js CDN for diagram rendering."""
    return _wrap_html_with_mermaid_js(markdown)


def _md_to_html(md_content: str) -> str:
    """Convert markdown to HTML using the markdown library. Handles tables, code blocks, etc."""
    import markdown as _md
    return _md.markdown(md_content, extensions=["tables", "fenced_code", "codehilite"])


def _wrap_html(content: str) -> str:
    """Wrap markdown+SVG content in a styled HTML document.

    Content may contain a mix of raw SVG (from mmdc) and markdown.
    We split on SVGs, convert markdown parts, then reassemble.
    """
    import re
    # Split content into markdown chunks and SVG chunks
    parts = re.split(r"(<svg[\s\S]*?</svg>)", content)
    html_parts = []
    for part in parts:
        if part.strip().startswith("<svg"):
            html_parts.append(f'<div class="diagram">{part}</div>')
        else:
            html_parts.append(_md_to_html(part))
    return _HTML_TEMPLATE.replace("{{CONTENT}}", "\n".join(html_parts))


def _wrap_html_with_mermaid_js(markdown: str) -> str:
    """Wrap markdown in HTML with mermaid.js CDN for client-side rendering."""
    import re
    # Extract mermaid blocks before markdown conversion (fenced_code would escape them)
    mermaid_placeholder = []
    def _replace_mermaid(m):
        idx = len(mermaid_placeholder)
        mermaid_placeholder.append(m.group(1))
        return f"MERMAID_PLACEHOLDER_{idx}"

    md = re.sub(r"```mermaid\n(.*?)```", _replace_mermaid, markdown, flags=re.DOTALL)
    html = _md_to_html(md)

    # Replace placeholders with mermaid divs
    for idx, code in enumerate(mermaid_placeholder):
        html = html.replace(
            f"MERMAID_PLACEHOLDER_{idx}",
            f'<pre class="mermaid">{code}</pre>',
        )

    template = _HTML_TEMPLATE.replace("</head>",
        '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>\n'
        '<script>mermaid.initialize({startOnLoad:true, theme:"dark"});</script>\n</head>')
    return template.replace("{{CONTENT}}", html)


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Business Profile</title>
<style>
  :root { --bg: #1a1a2e; --surface: #16213e; --text: #e8e8e8; --muted: #8b8b9e;
          --accent: #e94560; --accent2: #0f3460; --green: #4ecca3; --border: #2a2a4a; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, system-ui, sans-serif; background: var(--bg);
         color: var(--text); line-height: 1.7; padding: 2rem; max-width: 900px; margin: 0 auto; }
  h1 { font-size: 2rem; color: #fff; margin: 1.5rem 0 0.5rem; border-bottom: 3px solid var(--accent); padding-bottom: 0.5rem; }
  h2 { font-size: 1.5rem; color: var(--green); margin: 2rem 0 0.8rem; }
  h3 { font-size: 1.15rem; color: var(--accent); margin: 1.2rem 0 0.5rem; }
  p, li { margin-bottom: 0.5rem; }
  strong { color: #fff; }
  blockquote { border-left: 4px solid var(--accent); padding: 0.5rem 1rem; margin: 1rem 0;
               background: var(--surface); border-radius: 0 8px 8px 0; color: var(--muted); font-style: italic; }
  li { margin-left: 1.5rem; }
  svg { max-width: 100%; height: auto; margin: 1.5rem 0; display: block;
        background: var(--surface); border-radius: 12px; padding: 1rem; border: 1px solid var(--border); }
  pre.mermaid { background: var(--surface); border-radius: 12px; padding: 1.5rem; border: 1px solid var(--border); margin: 1.5rem 0; }
  table { width: 100%; border-collapse: collapse; margin: 1.2rem 0; }
  th { background: var(--accent2); color: #fff; text-align: left; padding: 0.6rem 1rem; border: 1px solid var(--border); }
  td { padding: 0.5rem 1rem; border: 1px solid var(--border); }
  tr:nth-child(even) { background: rgba(255,255,255,0.03); }
  code { background: var(--surface); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
  pre { background: var(--surface); padding: 1rem; border-radius: 8px; overflow-x: auto; margin: 1rem 0; border: 1px solid var(--border); }
  .diagram { margin: 1.5rem 0; text-align: center; }
  .container { background: var(--surface); border-radius: 16px; padding: 2.5rem; margin-top: 1rem;
               border: 1px solid var(--border); box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
</style>
</head>
<body>
<div class="container">
{{CONTENT}}
</div>
</body>
</html>
"""


# --- Multi-agent specialist functions ---


async def _run_specialist(
    name: str,
    symbol: str,
    system_prompt: str,
    tools: list | None = None,
    max_turns: int | None = None,
    max_budget: float | None = None,
    model: str | None = None,
    user_prompt: str | None = None,
) -> BriefingEnvelope:
    """Run a single specialist agent. Returns BriefingEnvelope with report, briefing, evidence, cost."""

    tools = tools if tools is not None else AGENT_TOOLS.get(name, [])
    max_turns = max_turns or AGENT_MAX_TURNS.get(name, 20)
    max_budget = max_budget or AGENT_MAX_BUDGET.get(name, 0.50)
    model = model or DEFAULT_MODELS.get(name, "claude-sonnet-4-6")

    # Create MCP server with agent's tool subset (skip if no tools)
    mcp_servers = {}
    if tools:
        server = create_sdk_mcp_server(f"{name}-data", tools=tools)
        mcp_servers[name] = server

    # Build options
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers=mcp_servers,
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
    )

    # Block dangerous Claude Code built-ins (Bash, Write, Edit, etc.)
    # MCP tools registered via mcp_servers are available regardless.
    options.disallowed_tools = list(_DISALLOWED_BUILTINS)

    # Add specific built-ins for agents that need them (e.g. WebSearch for business)
    extra_builtins = AGENT_ALLOWED_BUILTINS.get(name, [])
    if extra_builtins:
        options.allowed_tools = extra_builtins

    # Phase 1: Generate report with thinking
    start_time = time.time()
    evidence: list[ToolEvidence] = []
    report_text = ""
    text_blocks: list[str] = []  # fallback: collect text from AssistantMessages
    total_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    agent_model = model

    # Track tool calls for evidence capture
    pending_tool_calls: dict[str, dict] = {}  # tool_use_id -> {tool, args}

    try:
        async for message in query(
            prompt=user_prompt or f"Analyze {symbol}. Pull all relevant data using your tools. Produce your full report section.",
            options=options,
        ):
            if isinstance(message, AssistantMessage):
                # Accumulate tokens from each assistant turn (usage is a dict)
                msg_usage = getattr(message, "usage", None)
                if isinstance(msg_usage, dict):
                    input_tokens += msg_usage.get("input_tokens", 0) or 0
                    output_tokens += msg_usage.get("output_tokens", 0) or 0

                for block in message.content:
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
                            result_str = str(block.content) if block.content else ""
                            evidence.append(ToolEvidence(
                                tool=call["tool"],
                                args=call["args"],
                                result_summary=result_str[:500],
                                result_hash=hashlib.sha256(result_str.encode()).hexdigest(),
                                is_error=getattr(block, "is_error", False) or False,
                            ))
            elif isinstance(message, ResultMessage):
                report_text = message.result or ""
                total_cost = message.total_cost_usd or 0.0
                # ResultMessage.usage is a dict, not an object — use .get()
                usage = message.usage
                if isinstance(usage, dict):
                    # Prefer ResultMessage totals over accumulated per-turn counts
                    result_in = usage.get("input_tokens", 0) or 0
                    result_out = usage.get("output_tokens", 0) or 0
                    if result_in or result_out:
                        input_tokens = result_in
                        output_tokens = result_out
    except Exception as exc:
        # Claude CLI may exit with code 1 after delivering results.
        # If we already captured text, proceed with what we have.
        has_content = bool(report_text or text_blocks)
        if has_content:
            logger.warning(
                "Agent '%s' for %s raised %s after producing content — proceeding with partial output",
                name, symbol, type(exc).__name__,
            )
        else:
            logger.error(
                "Agent '%s' for %s FAILED with no output: %s: %s",
                name, symbol, type(exc).__name__, exc,
                exc_info=True,
            )

    # Prefer TextBlocks over ResultMessage.result when TextBlocks have more content.
    # ResultMessage.result often contains only a short summary, while the full report
    # is spread across TextBlocks from intermediate assistant turns.
    joined_blocks = "\n\n".join(text_blocks) if text_blocks else ""
    if len(joined_blocks) > len(report_text) * 2 and len(joined_blocks) > 1000:
        logger.info("Agent '%s' %s: TextBlocks (%d chars) >> ResultMessage (%d chars), using TextBlocks",
                     name, symbol, len(joined_blocks), len(report_text))
        report_text = joined_blocks
    elif not report_text and text_blocks:
        logger.info("Agent '%s' %s: no ResultMessage, using %d TextBlocks as fallback", name, symbol, len(text_blocks))
        report_text = joined_blocks

    if not report_text:
        logger.error("Agent '%s' %s: EMPTY REPORT — no ResultMessage and no TextBlocks captured", name, symbol)

    # Strip agent "thinking out loud" preamble (tool-calling chatter before the report).
    # The agent produces intermediate text ("I'll analyze...", "Now let me pull...")
    # before the actual report which starts with a # or --- header.
    if report_text:
        lines = report_text.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("---"):
                report_text = "\n".join(lines[i:])
                break

    duration = time.time() - start_time

    # Phase 2: Extract structured briefing (two-pass approach)
    briefing = await _extract_briefing(name, symbol, report_text)

    # Build envelope
    envelope = BriefingEnvelope(
        agent=name,
        symbol=symbol.upper(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        report=report_text,
        briefing=briefing,
        evidence=evidence,
        cost=AgentCost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_cost_usd=total_cost,
            duration_seconds=duration,
            model=agent_model,
        ),
    )

    # Save to vault
    save_envelope(envelope)

    return envelope


async def _extract_briefing(name: str, symbol: str, report_text: str) -> dict:
    """Extract structured briefing JSON from a report using a cheap second pass.

    Falls back to parse_briefing_from_markdown if the second pass fails.
    """
    # First try: parse from markdown (if agent included a JSON block)
    briefing = parse_briefing_from_markdown(report_text)
    if briefing:
        return briefing

    # Second pass: use a cheap model to extract structured data
    try:
        extraction_prompt = (
            f"Extract a structured briefing from this {name} analysis report for {symbol}.\n\n"
            "Return a JSON object with these fields:\n"
            f'- agent: "{name}"\n'
            f'- symbol: "{symbol}"\n'
            "- confidence: float 0-1 (how confident the analysis is)\n"
            "- key_metrics: dict of important numerical metrics found in the report\n"
            "- key_findings: list of 3-5 key findings as strings\n"
            '- signal: overall signal (e.g. "bullish", "bearish", "neutral", "mixed")\n\n'
            f"Report:\n{report_text[:8000]}"
        )

        options = ClaudeAgentOptions(
            system_prompt=(
                "You are a data extraction assistant. Extract structured data "
                "from research reports. Return only valid JSON."
            ),
            max_turns=1,
            permission_mode="bypassPermissions",
            model="claude-haiku-4-5-20251001",
        )

        result_text = ""
        text_parts: list[str] = []
        try:
            async for message in query(prompt=extraction_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if type(block).__name__ == "TextBlock":
                            text_parts.append(block.text)
                elif isinstance(message, ResultMessage):
                    result_text = message.result or ""
        except Exception:
            pass
        if not result_text and text_parts:
            result_text = "\n".join(text_parts)

        extracted = parse_briefing_from_markdown(result_text)
        if extracted:
            return extracted

        # Try parsing the raw text as JSON
        return json.loads(result_text.strip())
    except Exception as exc:
        # Final fallback: return minimal briefing
        logger.warning(
            "Briefing extraction failed for '%s' %s: %s: %s (report length: %d chars)",
            name, symbol, type(exc).__name__, exc, len(report_text),
        )
        return {"agent": name, "symbol": symbol, "extraction_failed": True}


async def run_single_agent(
    agent_name: str,
    symbol: str,
    model: str | None = None,
) -> BriefingEnvelope:
    """Run a single specialist agent. Uses same V2 prompts/tools as run_all_agents."""
    from flowtracker.research.prompts import build_specialist_prompt

    prompt = build_specialist_prompt(agent_name, symbol.upper())
    if not prompt:
        raise ValueError(f"Unknown agent: {agent_name}")

    return await _run_specialist(
        name=agent_name,
        symbol=symbol.upper(),
        system_prompt=prompt,
        model=model,
    )


def _analyze_briefing_signals(briefings: dict[str, dict]) -> str:
    """Pre-analyze briefings to find agreements, contradictions, and cross-signals.

    This gives the synthesis agent a directed starting point instead of raw data.
    The orchestrator does the pattern-matching; the synthesis agent resolves and narrates.
    """
    lines = []

    # Collect signals from each agent
    signals = {}
    for name, b in briefings.items():
        signals[name] = b.get("signal", "unknown")

    # Count agreement
    signal_values = [s for s in signals.values() if s != "unknown"]
    if signal_values:
        from collections import Counter
        counts = Counter(signal_values)
        majority = counts.most_common(1)[0]
        agreement = majority[1] / len(signal_values) * 100
        lines.append(f"**Suggested signal (orchestrator analysis):** {len(signal_values)} agents responded. "
                      f"Majority signal appears {majority[0]} ({majority[1]}/{len(signal_values)} = {agreement:.0f}%). "
                      f"Please validate — do the underlying briefing details support this?")
        lines.append(f"**Signal breakdown:** {dict(counts)}")

        # Flag contradictions
        if len(counts) > 1:
            dissenters = [(name, sig) for name, sig in signals.items() if sig != majority[0] and sig != "unknown"]
            if dissenters:
                lines.append(f"**Potential contradiction:** {', '.join(f'{n} says {s}' for n, s in dissenters)} "
                              f"vs majority {majority[0]}. Investigate whether these reflect genuinely conflicting evidence or different timeframes/scopes.")

    # Cross-signal detection
    cross_signals = []

    biz = briefings.get("business", {})
    fin = briefings.get("financials", {})
    own = briefings.get("ownership", {})
    val = briefings.get("valuation", {})
    risk = briefings.get("risk", {})
    tech = briefings.get("technical", {})

    # Growth vs ownership: decelerating growth + institutional accumulation = contrarian signal
    growth = fin.get("growth_trajectory") or biz.get("signal", "")
    mf_trend = own.get("mf_trend", "")
    fii_trend = own.get("fii_trend", "")
    if "decelerat" in str(growth).lower() and mf_trend == "increasing":
        cross_signals.append("Growth decelerating BUT MF accumulating — smart money sees value despite slowing growth?")
    if fii_trend == "decreasing" and mf_trend == "increasing":
        cross_signals.append("FII selling + MF buying = institutional handoff. Historically medium-term bullish in Indian markets.")

    # Quality vs valuation: high ROCE + low PE = quality at reasonable price
    roce = biz.get("key_metrics", {}).get("roce_pct") or fin.get("roce_current")
    val_signal = val.get("signal", "")
    if roce and float(roce) > 20 and "UNDERVALUED" in str(val_signal).upper():
        cross_signals.append(f"High ROCE ({roce}%) + undervalued signal = quality at reasonable price.")

    # Insider + technical: insider buying at weakness
    insider = own.get("insider_signal", "")
    tech_signal = tech.get("signal", "")
    if insider == "net_buying" and "bearish" in str(tech_signal).lower():
        cross_signals.append("Insider buying while technicals are bearish — management conviction at weakness.")

    # Risk vs valuation: high risk + cheap = value trap or opportunity
    risk_signal = risk.get("signal", "")
    if "bearish" in str(risk_signal).lower() and "UNDERVALUED" in str(val_signal).upper():
        cross_signals.append("Risk agent bearish but valuation says undervalued — potential value trap. Dig into whether risks are priced in.")

    # Sector signals
    sector = briefings.get("sector", {})
    sector_signal = sector.get("sector_growth_signal", "")
    sector_valuation = sector.get("sector_valuation_signal", "")

    if sector_signal == "growing" and "UNDERVALUED" in str(val_signal).upper():
        cross_signals.append("Sector growing + stock undervalued = riding sector tailwind at a discount.")

    if sector_valuation == "expensive" and "EXPENSIVE" in str(val_signal).upper():
        cross_signals.append("Both sector and stock are expensive — correction risk is amplified.")

    if cross_signals:
        lines.append("\n**Potential cross-signals (orchestrator suggestions — validate against briefing data):**")
        for i, sig in enumerate(cross_signals, 1):
            lines.append(f"  {i}. {sig}")
    else:
        lines.append("\n**No strong cross-signals detected.** Look for subtler connections in the briefing data.")

    return "\n".join(lines)


async def run_all_agents(
    symbol: str,
    model: str | None = None,
    verify: bool = True,
    verify_model: str | None = None,
) -> dict[str, BriefingEnvelope]:
    """Run all 7 specialist agents in parallel, optionally verify, return results."""
    from flowtracker.research.prompts import build_specialist_prompt

    symbol = symbol.upper()
    agent_names = ["business", "financials", "ownership", "valuation", "risk", "technical", "sector"]

    # Phase 1: Run specialists with concurrency limit and retry
    MAX_CONCURRENT = 3  # max agents running simultaneously
    MAX_RETRIES = 1     # retry once on failure
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _run_with_limit(name: str, prompt: str) -> tuple[str, BriefingEnvelope | Exception]:
        """Run a specialist with concurrency limiting and retry."""
        for attempt in range(1 + MAX_RETRIES):
            async with semaphore:
                try:
                    envelope = await _run_specialist(
                        name=name, symbol=symbol, system_prompt=prompt, model=model,
                    )
                    # Check if agent actually produced content
                    if envelope.report and len(envelope.report.strip()) > 100:
                        return name, envelope
                    # Empty report — treat as failure for retry
                    if attempt < MAX_RETRIES:
                        logger.warning(
                            "Agent '%s' for %s produced empty report (attempt %d/%d) — retrying in 5s",
                            name, symbol, attempt + 1, 1 + MAX_RETRIES,
                        )
                        await asyncio.sleep(5)
                        continue
                    return name, envelope  # return empty on last attempt
                except Exception as exc:
                    if attempt < MAX_RETRIES:
                        logger.warning(
                            "Agent '%s' for %s failed (attempt %d/%d): %s — retrying in 5s",
                            name, symbol, attempt + 1, 1 + MAX_RETRIES, exc,
                        )
                        await asyncio.sleep(5)
                        continue
                    logger.error(
                        "Agent '%s' for %s failed after %d attempts: %s",
                        name, symbol, 1 + MAX_RETRIES, exc,
                    )
                    return name, exc
        # Should not reach here, but just in case
        return name, Exception(f"Agent {name} exhausted retries")

    # Build tasks for all agents that have prompts
    specialist_tasks = []
    for name in agent_names:
        prompt = build_specialist_prompt(name, symbol)
        if not prompt:
            continue
        specialist_tasks.append(_run_with_limit(name, prompt))

    # Run with concurrency limit — gather still handles parallelism,
    # but the semaphore ensures only MAX_CONCURRENT run at once
    results = await asyncio.gather(*specialist_tasks)

    # Collect successful results
    envelopes: dict[str, BriefingEnvelope] = {}
    for name, result in results:
        if isinstance(result, Exception):
            print(f"  ⚠ {name} agent failed: {result}")
            envelopes[name] = BriefingEnvelope(
                agent=name, symbol=symbol,
                status="failed", failure_reason=str(result),
            )
        elif not result.report or len(result.report.strip()) < 100:
            envelopes[name] = BriefingEnvelope(
                agent=name, symbol=symbol,
                status="empty", failure_reason="Agent produced no substantive output",
                report=result.report, briefing=result.briefing,
                evidence=result.evidence, cost=result.cost,
            )
        else:
            envelopes[name] = result

    # Phase 1.5: Verification (with concurrency limit)
    if verify and envelopes:
        from flowtracker.research.verifier import _run_verifier, apply_corrections

        verify_sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def _verify_with_limit(name: str, envelope: BriefingEnvelope):
            async with verify_sem:
                return name, await _run_verifier(name, symbol, envelope, model=verify_model)

        verify_tasks = []
        for name, envelope in envelopes.items():
            verify_tasks.append(_verify_with_limit(name, envelope))

        verify_results = await asyncio.gather(*verify_tasks, return_exceptions=True)

        # Apply corrections
        for vresult in verify_results:
            if isinstance(vresult, Exception):
                continue
            name, vdata = vresult
            if isinstance(vdata, Exception):
                print(f"  ⚠ {name} verifier failed: {vdata}")
                continue
            # Log verification result
            if vdata.verdict == "pass":
                print(f"  ✓ {name} verification: pass ({vdata.spot_checks_performed} checks)")
            elif vdata.verdict == "pass_with_notes":
                issues_summary = ", ".join(
                    f"{i.get('severity', '?')}: {i.get('claim', '?')[:60]}"
                    for i in vdata.issues[:3]
                )
                print(f"  ✓ {name} verification: pass_with_notes ({vdata.spot_checks_performed} checks) — {issues_summary}")
            else:
                errors = [i for i in vdata.issues if i.get("severity") == "error"]
                print(f"  ✗ {name} verification: FAIL ({len(errors)} errors, {vdata.spot_checks_performed} checks)")
                for i in errors:
                    print(f"    → {i.get('claim', '?')[:80]} | actual: {i.get('actual', '?')[:80]}")

            envelopes[name] = apply_corrections(envelopes[name], vdata)

            # Re-save corrected envelope
            save_envelope(envelopes[name])

            # If verification failed, re-run with corrections injected into prompt.
            # We use the SAME specialist prompt + correction context so the agent
            # starts with full domain knowledge and knows exactly what to fix.
            if vdata.verdict == "fail":
                print(f"  🔄 {name} failed verification — re-running once with corrections")
                base_prompt = build_specialist_prompt(name, symbol)
                corrections_context = (
                    f"\n\n## CORRECTIONS REQUIRED (from verification agent)\n"
                    f"Your previous report was independently verified and flagged.\n"
                    f"**Issues found:**\n{json.dumps(vdata.issues, indent=2)}\n\n"
                    f"**Required corrections:**\n{json.dumps(vdata.corrections, indent=2)}\n\n"
                    f"Re-generate your report. Fix the flagged issues. "
                    f"Re-fetch the specific data points that were wrong — don't guess."
                )
                try:
                    rerun = await _run_specialist(
                        name=name,
                        symbol=symbol,
                        system_prompt=base_prompt + corrections_context,
                        model=model,
                    )
                    envelopes[name] = rerun
                except Exception as e:
                    print(f"  ⚠ {name} re-run failed — marking as failed: {e}")
                    envelopes[name] = BriefingEnvelope(
                        agent=name, symbol=symbol,
                        status="failed",
                        failure_reason=f"Failed verification and re-run: {e}",
                    )

    return envelopes


async def run_synthesis_agent(
    symbol: str,
    model: str | None = None,
    failed_agents: list[str] | None = None,
) -> BriefingEnvelope:
    """Run the synthesis agent on existing briefings."""
    from flowtracker.research.prompts import SYNTHESIS_AGENT_PROMPT_V2 as SYNTHESIS_AGENT_PROMPT
    from flowtracker.research.briefing import load_all_briefings
    from flowtracker.research.tools import get_composite_score, get_fair_value

    symbol = symbol.upper()
    briefings = load_all_briefings(symbol)

    if not briefings:
        raise ValueError(f"No briefings found for {symbol}. Run specialist agents first.")

    # Format briefings for the synthesis prompt
    briefing_text = ""
    for agent_name, data in briefings.items():
        briefing_text += f"\n### {agent_name.upper()} Briefing\n```json\n{json.dumps(data, indent=2)}\n```\n"

    if failed_agents:
        # Build tier-weighted failure info
        tier1_failed = [a for a in failed_agents if AGENT_TIERS.get(a) == 1]
        tier2_failed = [a for a in failed_agents if AGENT_TIERS.get(a) == 2]
        tier3_failed = [a for a in failed_agents if AGENT_TIERS.get(a) == 3]

        briefing_text += "\n\n### FAILED AGENTS\n"
        if tier1_failed:
            briefing_text += (
                f"**CRITICAL — Tier 1 agents failed: {', '.join(tier1_failed)}.** "
                "These are core financial analysis agents. Cap your verdict at HOLD and confidence at 40%. "
                "Lead with: 'WARNING: Core financial/risk analysis incomplete.'\n"
            )
        if tier2_failed:
            briefing_text += (
                f"**Tier 2 agents failed: {', '.join(tier2_failed)}.** "
                "Cap confidence at 65%. Note which dimensions are missing.\n"
            )
        if tier3_failed:
            briefing_text += (
                f"Tier 3 agents failed: {', '.join(tier3_failed)}. "
                "Cap confidence at 85%. These are supplementary — proceed with available data.\n"
            )

    # --- Directed synthesis: pre-analyze briefings for the synthesis agent ---
    signals_analysis = _analyze_briefing_signals(briefings)

    # Synthesis tools: just composite_score and fair_value
    synthesis_tools = [get_composite_score, get_fair_value]

    model = model or DEFAULT_MODELS.get("synthesis", "claude-opus-4-20250514")

    user_prompt = (
        f"Synthesize the analysis for {symbol}.\n\n"
        f"## Orchestrator Pre-Analysis (suggestions to investigate, not conclusions)\n{signals_analysis}\n\n"
        f"## Specialist Briefings\n{briefing_text}\n\n"
        "The orchestrator has flagged potential signals above — treat these as suggestions to investigate, "
        "not conclusions. You may find additional signals or disagree with the orchestrator's assessment. "
        "Your independent analysis takes precedence. "
        "Produce: Verdict, Executive Summary, Key Signals, Catalysts, The Big Question."
    )

    return await _run_specialist(
        name="synthesis",
        symbol=symbol,
        system_prompt=SYNTHESIS_AGENT_PROMPT,
        tools=synthesis_tools,
        max_turns=10,
        max_budget=0.30,
        model=model,
        user_prompt=user_prompt,
    )


async def run_explainer_agent(
    symbol: str,
    technical_report: str,
    model: str | None = None,
) -> BriefingEnvelope:
    """Run the explainer agent to add beginner-friendly annotations to a technical report.

    Takes the assembled technical markdown and returns an annotated version with
    blockquote callouts explaining financial terms and concepts. No tools needed —
    pure text transformation.
    """
    from flowtracker.research.prompts import EXPLAINER_AGENT_PROMPT

    model = model or DEFAULT_MODELS.get("explainer", "claude-sonnet-4-6")

    user_prompt = (
        f"Add beginner-friendly annotations to this equity research report for {symbol}.\n\n"
        f"---\n\n{technical_report}"
    )

    return await _run_specialist(
        name="explainer",
        symbol=symbol,
        system_prompt=EXPLAINER_AGENT_PROMPT,
        tools=[],
        max_turns=3,
        max_budget=1.00,
        model=model,
        user_prompt=user_prompt,
    )


def format_cost_summary(envelopes: dict[str, BriefingEnvelope]) -> str:
    """Format a Rich-compatible cost summary table."""
    lines = []
    lines.append("\n[bold]Agent Cost Summary[/]")
    lines.append(f"{'Agent':<14} {'Tokens (in/out)':<20} {'Cost':>8} {'Time':>8}")
    lines.append("─" * 54)

    total_cost = 0.0
    total_in = 0
    total_out = 0
    total_time = 0.0

    for name, env in envelopes.items():
        c = env.cost
        total_cost += c.total_cost_usd
        total_in += c.input_tokens
        total_out += c.output_tokens
        total_time += c.duration_seconds

        mins = int(c.duration_seconds // 60)
        secs = int(c.duration_seconds % 60)
        lines.append(
            f"{name:<14} {c.input_tokens:>8,} / {c.output_tokens:<8,} ${c.total_cost_usd:>6.2f} {mins}m {secs:02d}s"
        )

    lines.append("─" * 54)
    total_mins = int(total_time // 60)
    total_secs = int(total_time % 60)
    lines.append(
        f"{'TOTAL':<14} {total_in:>8,} / {total_out:<8,} ${total_cost:>6.2f} {total_mins}m {total_secs:02d}s"
    )

    return "\n".join(lines)


# --- Briefing freshness + comparison agent ---


def _briefings_fresh(symbol: str, max_age_days: int = 7) -> bool:
    """Check if ALL briefings for a stock are recent enough."""
    briefing_dir = Path.home() / "vault" / "stocks" / symbol.upper() / "briefings"
    if not briefing_dir.exists():
        return False
    agents = ["business", "financials", "ownership", "valuation", "risk", "technical", "sector"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    for agent in agents:
        path = briefing_dir / f"{agent}.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            gen_at = data.get("generated_at", "")
            if not gen_at:
                return False
            gen_dt = datetime.fromisoformat(gen_at)
            if gen_dt < cutoff:
                return False
        except (json.JSONDecodeError, ValueError):
            return False
    return True


async def _ensure_briefings(
    symbols: list[str],
    force: bool = False,
    skip_fetch: bool = False,
    model: str | None = None,
) -> dict[str, dict[str, dict]]:
    """Ensure all stocks have fresh briefings. Returns {symbol: {agent_name: briefing_dict}}."""
    from flowtracker.research.briefing import load_all_briefings

    result: dict[str, dict[str, dict]] = {}
    for symbol in symbols:
        briefings = load_all_briefings(symbol)
        if not force and briefings and _briefings_fresh(symbol, max_age_days=7):
            result[symbol] = briefings
        else:
            if not skip_fetch:
                from flowtracker.research.refresh import refresh_for_research
                from flowtracker.research.peer_refresh import refresh_peers

                refresh_for_research(symbol)
                refresh_peers(symbol)
            envelopes = await run_all_agents(symbol, model=model, verify=True)
            result[symbol] = {name: env.briefing for name, env in envelopes.items()}
    return result


async def run_comparison_agent(
    symbols: list[str],
    model: str | None = None,
    skip_fetch: bool = False,
    force: bool = False,
) -> BriefingEnvelope:
    """Run the comparison agent across multiple stocks. Returns BriefingEnvelope."""
    from flowtracker.research.prompts import COMPARISON_AGENT_PROMPT
    from flowtracker.research.tools import (
        get_fair_value_analysis,
        get_composite_score,
        get_valuation,
        get_peer_sector,
        get_events_actions,
        get_fundamentals,
        get_ownership,
        render_chart,
    )

    # Step 1: Ensure briefings exist and are fresh
    all_briefings = await _ensure_briefings(symbols, force, skip_fetch, model)

    # Step 2: Format briefings for the comparison agent
    briefing_text = ""
    for symbol, briefings in all_briefings.items():
        briefing_text += f"\n### {symbol}\n"
        for agent_name, data in briefings.items():
            briefing_text += f"**{agent_name}:** {json.dumps(data, indent=2)}\n"

    # Step 3: Run comparison agent
    comparison_tools = [get_fair_value_analysis, get_composite_score,
                        get_valuation, get_peer_sector,
                        get_events_actions, get_fundamentals,
                        get_ownership, render_chart]

    user_prompt = (
        f"Compare these {len(symbols)} stocks: {', '.join(symbols)}.\n\n"
        f"## Specialist Briefings\n{briefing_text}\n\n"
        "Use your tools to get current fair value and composite scores for EACH stock. "
        "Produce the full comparative analysis with side-by-side tables."
    )

    return await _run_specialist(
        name="comparison",
        symbol="_vs_".join(symbols),
        system_prompt=COMPARISON_AGENT_PROMPT,
        tools=comparison_tools,
        max_turns=20,
        max_budget=1.00,
        model=model or DEFAULT_MODELS.get("synthesis", "claude-sonnet-4-6"),
        user_prompt=user_prompt,
    )
