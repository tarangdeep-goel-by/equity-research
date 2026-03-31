"""Multi-turn research agent using Claude Agent SDK with MCP tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

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
    BUSINESS_AGENT_TOOLS,
    FINANCIAL_AGENT_TOOLS,
    OWNERSHIP_AGENT_TOOLS,
    RISK_AGENT_TOOLS,
    TECHNICAL_AGENT_TOOLS,
    VALUATION_AGENT_TOOLS,
)


_VAULT_BASE = Path.home() / "vault" / "stocks"
_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


# --- Multi-agent specialist defaults ---

DEFAULT_MODELS: dict[str, str] = {
    "business": "claude-sonnet-4-20250514",
    "financials": "claude-sonnet-4-20250514",
    "ownership": "claude-sonnet-4-20250514",
    "valuation": "claude-sonnet-4-20250514",
    "risk": "claude-sonnet-4-20250514",
    "technical": "claude-sonnet-4-20250514",
    "synthesis": "claude-sonnet-4-20250514",
    "verifier": "claude-haiku-4-5-20251001",
}

AGENT_TOOLS: dict[str, list] = {
    "business": BUSINESS_AGENT_TOOLS,
    "financials": FINANCIAL_AGENT_TOOLS,
    "ownership": OWNERSHIP_AGENT_TOOLS,
    "valuation": VALUATION_AGENT_TOOLS,
    "risk": RISK_AGENT_TOOLS,
    "technical": TECHNICAL_AGENT_TOOLS,
}

AGENT_MAX_TURNS: dict[str, int] = {
    "business": 40,
    "financials": 35,
    "ownership": 30,
    "valuation": 30,
    "risk": 30,
    "technical": 25,
}

AGENT_MAX_BUDGET: dict[str, float] = {
    "business": 1.00,
    "financials": 0.75,
    "ownership": 0.60,
    "valuation": 0.60,
    "risk": 0.60,
    "technical": 0.50,
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
}


async def _run_agent(symbol: str, model: str | None = None) -> str:
    """Run the research agent and return the Markdown report."""
    from flowtracker.research.prompts import RESEARCH_SYSTEM_PROMPT
    from flowtracker.research.tools import RESEARCH_TOOLS

    server = create_sdk_mcp_server("research-data", tools=RESEARCH_TOOLS)

    options = ClaudeAgentOptions(
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        mcp_servers={"research": server},
        max_turns=30,
        permission_mode="bypassPermissions",
        model=model,
    )

    report = ""
    async for message in query(
        prompt=f"Generate a comprehensive equity research thesis for {symbol}. Pull all available data, cross-reference signals, and produce the full Markdown report.",
        options=options,
    ):
        if isinstance(message, ResultMessage):
            report = message.result or ""

    return report


async def _run_business_agent(symbol: str, model: str | None = None) -> str:
    """Run the business profile agent — lightweight, qualitative only."""
    from flowtracker.research.prompts import BUSINESS_SYSTEM_PROMPT
    from flowtracker.research.tools import BUSINESS_TOOLS

    server = create_sdk_mcp_server("business-data", tools=BUSINESS_TOOLS)

    options = ClaudeAgentOptions(
        system_prompt=BUSINESS_SYSTEM_PROMPT,
        mcp_servers={"business": server},
        max_turns=25,
        permission_mode="bypassPermissions",
        model=model,
    )

    report = ""
    async for message in query(
        prompt=f"Research and write a business profile for {symbol}. Explain what the company does, how it makes money, its competitive position, and key risks. Use web search if the stored data is thin.",
        options=options,
    ):
        if isinstance(message, ResultMessage):
            report = message.result or ""

    return report


def generate_thesis(symbol: str, model: str | None = None) -> Path:
    """Generate a research thesis for a stock symbol. Returns path to .md file."""
    symbol = symbol.upper()
    today = date.today().isoformat()

    report = asyncio.run(_run_agent(symbol, model))

    if not report.strip():
        raise RuntimeError(f"Agent returned empty report for {symbol}")

    # Save to vault
    vault_dir = _VAULT_BASE / symbol / "thesis"
    vault_dir.mkdir(parents=True, exist_ok=True)
    vault_path = vault_dir / f"{today}.md"
    vault_path.write_text(report)

    # Save to reports/
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    reports_path = _REPORTS_DIR / f"{symbol.lower()}-thesis.md"
    reports_path.write_text(report)

    return vault_path


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


def generate_business_profile(symbol: str, model: str | None = None) -> Path:
    """Generate a business profile for a stock. Returns path to HTML report."""
    symbol = symbol.upper()

    report = asyncio.run(_run_business_agent(symbol, model))

    if not report.strip():
        raise RuntimeError(f"Agent returned empty business profile for {symbol}")

    # Save raw markdown to vault
    profile_dir = _VAULT_BASE / symbol
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profile_dir / "profile.md"
    profile_path.write_text(report)

    # Render HTML with mermaid diagrams
    html = _render_mermaid_to_html(report, profile_dir)
    html_path = _REPORTS_DIR / f"{symbol.lower()}-business.html"
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)

    return html_path


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

    tools = tools or AGENT_TOOLS.get(name, [])
    max_turns = max_turns or AGENT_MAX_TURNS.get(name, 20)
    max_budget = max_budget or AGENT_MAX_BUDGET.get(name, 0.50)
    model = model or DEFAULT_MODELS.get(name, "claude-sonnet-4-20250514")

    # Create MCP server with agent's tool subset
    server = create_sdk_mcp_server(f"{name}-data", tools=tools)

    # Build options
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers={name: server},
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
    except Exception:
        # Claude CLI may exit with code 1 after delivering results.
        # If we already captured text, proceed with what we have.
        pass

    # Use collected TextBlocks as fallback if ResultMessage.result was empty
    if not report_text and text_blocks:
        report_text = "\n\n".join(text_blocks)

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
    except Exception:
        # Final fallback: return minimal briefing
        return {"agent": name, "symbol": symbol, "extraction_failed": True}


async def run_single_agent(
    agent_name: str,
    symbol: str,
    system_prompt: str,
    model: str | None = None,
) -> BriefingEnvelope:
    """Run a single specialist agent. Public API for CLI."""
    return await _run_specialist(
        name=agent_name,
        symbol=symbol.upper(),
        system_prompt=system_prompt,
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
        lines.append(f"**Agent agreement:** {len(signal_values)} agents responded. "
                      f"Majority signal: {majority[0]} ({majority[1]}/{len(signal_values)} = {agreement:.0f}%)")
        lines.append(f"**Signal breakdown:** {dict(counts)}")

        # Flag contradictions
        if len(counts) > 1:
            dissenters = [(name, sig) for name, sig in signals.items() if sig != majority[0] and sig != "unknown"]
            if dissenters:
                lines.append(f"**Contradictions to resolve:** {', '.join(f'{n} says {s}' for n, s in dissenters)} "
                              f"vs majority {majority[0]}. WHY do these agents disagree? Your synthesis must address this.")

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

    if cross_signals:
        lines.append("\n**Cross-signals detected (investigate these):**")
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
    """Run all 6 specialist agents in parallel, optionally verify, return results."""
    from flowtracker.research.prompts import AGENT_PROMPTS

    symbol = symbol.upper()
    agent_names = ["business", "financials", "ownership", "valuation", "risk", "technical"]

    # Phase 1: Run all specialists in parallel
    specialist_tasks = []
    for name in agent_names:
        prompt = AGENT_PROMPTS.get(name)
        if not prompt:
            continue
        specialist_tasks.append(
            _run_specialist(name=name, symbol=symbol, system_prompt=prompt, model=model)
        )

    results = await asyncio.gather(*specialist_tasks, return_exceptions=True)

    # Collect successful results
    envelopes: dict[str, BriefingEnvelope] = {}
    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            # Log but continue — partial results are fine
            print(f"  ⚠ {name} agent failed: {result}")
            continue
        envelopes[name] = result

    # Phase 1.5: Verification (parallel, one per specialist)
    if verify and envelopes:
        from flowtracker.research.verifier import _run_verifier, apply_corrections

        verify_tasks = []
        verify_names = []
        for name, envelope in envelopes.items():
            verify_tasks.append(
                _run_verifier(name, symbol, envelope, model=verify_model)
            )
            verify_names.append(name)

        verify_results = await asyncio.gather(*verify_tasks, return_exceptions=True)

        # Apply corrections
        for name, vresult in zip(verify_names, verify_results):
            if isinstance(vresult, Exception):
                print(f"  ⚠ {name} verifier failed: {vresult}")
                continue
            envelopes[name] = apply_corrections(envelopes[name], vresult)

            # Re-save corrected envelope
            save_envelope(envelopes[name])

            # If verification failed, re-run with corrections injected into prompt.
            # We use the SAME specialist prompt + correction context so the agent
            # starts with full domain knowledge and knows exactly what to fix.
            if vresult.verdict == "fail":
                print(f"  🔄 {name} failed verification — re-running with corrections")
                base_prompt = AGENT_PROMPTS.get(name, "")
                corrections_context = (
                    f"\n\n## CORRECTIONS REQUIRED (from verification agent)\n"
                    f"Your previous report was independently verified and flagged.\n"
                    f"**Issues found:**\n{json.dumps(vresult.issues, indent=2)}\n\n"
                    f"**Required corrections:**\n{json.dumps(vresult.corrections, indent=2)}\n\n"
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
                    print(f"  ⚠ {name} re-run failed: {e}")

    return envelopes


async def run_synthesis_agent(
    symbol: str,
    model: str | None = None,
) -> BriefingEnvelope:
    """Run the synthesis agent on existing briefings."""
    from flowtracker.research.prompts import SYNTHESIS_AGENT_PROMPT
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

    # --- Directed synthesis: pre-analyze briefings for the synthesis agent ---
    signals_analysis = _analyze_briefing_signals(briefings)

    # Synthesis tools: just composite_score and fair_value
    synthesis_tools = [get_composite_score, get_fair_value]

    model = model or DEFAULT_MODELS.get("synthesis", "claude-opus-4-20250514")

    user_prompt = (
        f"Synthesize the analysis for {symbol}.\n\n"
        f"## Pre-Analysis (signals detected by orchestrator)\n{signals_analysis}\n\n"
        f"## Specialist Briefings\n{briefing_text}\n\n"
        "Use the pre-analysis to guide your cross-referencing. Resolve contradictions, "
        "amplify agreements, and produce: Verdict, Executive Summary, Key Signals, "
        "Catalysts, The Big Question."
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
