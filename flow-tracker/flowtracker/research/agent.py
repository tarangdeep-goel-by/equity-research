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
    CLIConnectionError,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
)

from flowtracker.research.briefing import (
    AgentCost,
    AgentTrace,
    BriefingEnvelope,
    ComplianceGateTrace,
    PipelineTrace,
    RetryEvent,
    ToolEvidence,
    TurnEvent,
    parse_briefing_from_markdown,
    save_envelope,
    save_trace,
)
from flowtracker.research.tools import (
    _tool_result_cache,
    BUSINESS_AGENT_TOOLS_V2,
    FINANCIAL_AGENT_TOOLS_V2,
    HISTORICAL_ANALOG_AGENT_TOOLS_V2,
    MACRO_AGENT_TOOLS_V2,
    NEWS_AGENT_TOOLS_V2,
    OWNERSHIP_AGENT_TOOLS_V2,
    RISK_AGENT_TOOLS_V2,
    SECTOR_AGENT_TOOLS_V2,
    TECHNICAL_AGENT_TOOLS_V2,
    VALUATION_AGENT_TOOLS_V2,
)


_VAULT_BASE = Path.home() / "vault" / "stocks"
_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

# --- Specialist-run retry config (E14 extension to _run_specialist) ---
# Mirror annual_report_extractor: [30s, 60s, 120s] backoff = 3 retries on top
# of the initial attempt. Retry only when the SDK subprocess crashed BEFORE
# emitting useful content (< PARTIAL_OUTPUT_BYTES). Crashes after content is
# captured fall through to the existing "graceful degradation" path.
SPECIALIST_RETRY_DELAYS_SEC: tuple[int, ...] = (30, 60, 120)
PARTIAL_OUTPUT_BYTES = 400


# --- Multi-agent specialist defaults ---

DEFAULT_MODELS: dict[str, str] = {
    "business": "claude-sonnet-4-6",
    "financials": "claude-sonnet-4-6",
    "ownership": "claude-sonnet-4-6",
    "valuation": "claude-sonnet-4-6",
    "risk": "claude-sonnet-4-6",
    "technical": "claude-sonnet-4-6",
    "sector": "claude-sonnet-4-6",
    "news": "claude-sonnet-4-6",
    "macro": "claude-sonnet-4-6",
    "historical_analog": "claude-sonnet-4-6",
    "synthesis": "claude-opus-4-6",
    "verifier": "claude-haiku-4-5-20251001",
    "web_research": "claude-sonnet-4-6",
    "explainer": "claude-sonnet-4-6",
}

DEFAULT_EFFORT: dict[str, str] = {
    "financials": "max",
    "valuation": "max",
    "synthesis": "max",
    "business": "high",
    "risk": "high",
    "sector": "high",
    "ownership": "medium",
    "technical": "medium",
    "news": "medium",
    "macro": "medium",
    "historical_analog": "medium",  # structured pattern matching, not deep reasoning
    "web_research": "medium",  # fact-retrieval, not deep reasoning
    "explainer": "high",
}

AGENT_TOOLS: dict[str, list] = {
    "business": BUSINESS_AGENT_TOOLS_V2,
    "financials": FINANCIAL_AGENT_TOOLS_V2,
    "ownership": OWNERSHIP_AGENT_TOOLS_V2,
    "valuation": VALUATION_AGENT_TOOLS_V2,
    "risk": RISK_AGENT_TOOLS_V2,
    "technical": TECHNICAL_AGENT_TOOLS_V2,
    "sector": SECTOR_AGENT_TOOLS_V2,
    "news": NEWS_AGENT_TOOLS_V2,
    "macro": MACRO_AGENT_TOOLS_V2,
    "historical_analog": HISTORICAL_ANALOG_AGENT_TOOLS_V2,
}

# Agent failure severity tiers for synthesis confidence capping
AGENT_TIERS = {
    # Tier 1: Dealbreakers — core financial analysis
    "risk": 1, "financials": 1, "valuation": 1,
    # Tier 2: Core context — business model and ownership
    "business": 2, "ownership": 2,
    # Tier 3: Enhancers — sector, market timing, historical analog priors
    "sector": 3, "technical": 3, "news": 3, "macro": 3, "historical_analog": 3,
}

# Tier-aware retry counts — tier-1 agents are critical, get extra retries
TIER_MAX_RETRIES = {1: 2, 2: 1, 3: 1}

AGENT_MAX_TURNS: dict[str, int] = {
    "business": 40,
    "financials": 35,
    "ownership": 30,
    "valuation": 30,
    "risk": 30,
    "technical": 30,
    "sector": 25,
    "news": 25,
    "macro": 25,
    "historical_analog": 20,  # 3-5 tool calls + clustering + report
    "web_research": 20,
}

AGENT_MAX_BUDGET: dict[str, float] = {
    "business": 1.50,
    "financials": 2.00,
    "ownership": 0.75,
    "valuation": 0.75,
    "risk": 0.75,
    "technical": 0.75,
    "sector": 0.60,
    "news": 0.50,
    "macro": 0.60,
    "historical_analog": 0.50,
    "web_research": 0.50,
}

# Claude Code built-ins that agents should NOT have access to.
# MCP tools (our custom research tools) are registered separately via mcp_servers
# and are always available regardless of this list.
#
# External MCP servers registered at the user-level (~/.claude/config) are
# INHERITED by the bundled CLI subprocess. They leak into research agents
# unless explicitly blocked. We've observed mcp__gemini-bridge__* and
# mcp__pencil__* leak into ownership/business agents, wasting tokens on
# arbitrary file reads. Block with explicit prefixes.
_DISALLOWED_BUILTINS = [
    "Bash", "Write", "Edit", "Read", "Glob", "Grep",
    "NotebookEdit", "Agent", "TodoWrite", "AskUserQuestion",
    "Skill", "ReadMcpResourceTool", "ListMcpResourcesTool",
    "WebSearch", "WebFetch",  # only web_research/news agents get these
    # Claude Code session-internal tools that leak into subprocess tool registries.
    # Observed in the INOX run: web_research agent invoked Monitor + ToolSearch +
    # TaskOutput to run curl pipelines, bypassing the WebSearch/WebFetch-only design.
    "Monitor", "ToolSearch",
    "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskStop", "TaskOutput",
    "CronCreate", "CronDelete", "CronList",
    "EnterPlanMode", "ExitPlanMode", "EnterWorktree", "ExitWorktree",
    "LSP", "PushNotification", "RemoteTrigger", "ScheduleWakeup",
    # External user-level MCP servers that leak into the subprocess
    "mcp__gemini-bridge__gemini_chat_end",
    "mcp__gemini-bridge__gemini_chat_list",
    "mcp__gemini-bridge__gemini_chat_send",
    "mcp__gemini-bridge__gemini_chat_start",
    "mcp__gemini-bridge__gemini_query",
    "mcp__pencil__batch_design", "mcp__pencil__batch_get",
    "mcp__pencil__find_empty_space_on_canvas",
    "mcp__pencil__get_editor_state", "mcp__pencil__get_guidelines",
    "mcp__pencil__get_screenshot", "mcp__pencil__get_style_guide",
    "mcp__pencil__get_style_guide_tags", "mcp__pencil__get_variables",
    "mcp__pencil__open_document",
    "mcp__pencil__replace_all_matching_properties",
    "mcp__pencil__search_all_unique_properties",
    "mcp__pencil__set_variables", "mcp__pencil__snapshot_layout",
]

# Additional Claude Code built-ins that specific agents ARE allowed to use.
# These get added to allowed_tools (whitelist) on top of MCP tools.
AGENT_ALLOWED_BUILTINS: dict[str, list[str]] = {
    "news": ["WebFetch"],  # needs web fetch to read full articles
    "web_research": ["WebSearch", "WebFetch"],
    "macro": ["WebSearch", "WebFetch"],  # fallback for anchors not in local vault
}

# Fields to extract from briefings for synthesis context.
# Full briefings can exceed 100K tokens (nested evidence, long report text);
# synthesis only needs structured signals + key numerical metrics. The whitelist
# keeps compact scalar/list/dict fields that drive synthesis reasoning — drop
# only the long narrative `report` body + detailed nested evidence.
_SYNTHESIS_FIELDS = {
    "agent", "symbol", "confidence", "signal", "key_findings", "open_questions",
    "mandatory_metrics_status",  # data-quality flag from specialists
    # Business
    "business_model", "moat_strength", "moat_type", "revenue_drivers", "management_quality",
    "company_name", "key_metrics", "key_risks", "industry_growth", "revenue_mix",
    # Financial — keep hard numbers, not just trend labels
    "revenue_cagr_5yr", "opm_trend", "dupont_driver", "fcf_positive",
    "growth_trajectory", "quality_signal",
    "opm_current", "roce_current", "debt_equity", "earnings_beat_ratio",
    "net_debt_cr", "cash_conversion",
    # Ownership
    "promoter_pct", "promoter_trend", "fii_pct", "fii_trend", "mf_pct", "mf_trend",
    "institutional_handoff", "insider_signal", "pledge_pct",
    "delivery_signal", "mf_scheme_count",
    # Valuation
    "current_pe", "pe_percentile", "fair_value_base", "fair_value_bear", "fair_value_bull",
    "margin_of_safety_pct", "valuation_signal", "vs_peers",
    "analyst_count", "analyst_dispersion", "peg_ratio", "forward_pe",
    # Risk
    "composite_score", "top_risks", "governance_signal", "bear_case_trigger",
    "macro_sensitivity", "financial_health",
    "m_score", "z_score",  # dealbreaker thresholds
    # Technical — keep hard values, not just labels
    "rsi_signal", "trend_strength", "accumulation_signal", "timing_suggestion",
    "rsi", "price_vs_sma50", "price_vs_sma200", "delivery_avg_7d",
    # Sector — industry field is CRITICAL for macro-vs-micro routing
    "sector_growth_signal", "competitive_position", "regulatory_risk",
    "industry", "sector_valuation_signal", "median_pe", "median_roce",
    "key_sector_tailwinds", "key_sector_headwinds", "top_sector_picks",
    "institutional_flow", "sector_size_cr", "stock_count",
    # News
    "top_events", "sentiment_signal", "catalysts_identified",
    # Macro
    "regime_state", "secular_tailwinds", "secular_headwinds",
    "cyclical_stage", "india_transmission", "sector_implications",
    "bull_case_triggers", "bear_case_triggers", "trajectory_checks",
    "anchors_fetched",
    # Historical Analog (Sprint 1) — base-rate priors for synthesis
    "target_features", "analog_count", "analog_lookback_years",
    "base_rates", "cluster_summary", "top_analogs",
    "differentiators", "directional_adjustments", "regime_caveat",
}


def _build_baseline_context(symbol: str) -> str:
    """Build a compact tear sheet from cached DB data for injection into agent prompts."""
    from flowtracker.research.data_api import ResearchDataAPI

    symbol = symbol.upper()
    baseline: dict = {"symbol": symbol}

    try:
        with ResearchDataAPI() as api:
            # Company identity
            info = api.get_company_info(symbol)
            if info:
                baseline["company"] = info.get("company_name", "")
                baseline["industry"] = info.get("industry", "")

            # Valuation snapshot (subset of key fields)
            snap = api.get_valuation_snapshot(symbol)
            if snap and isinstance(snap, dict):
                baseline["snapshot"] = {
                    k: snap.get(k)
                    for k in [
                        "current_price", "market_cap", "pe_ratio", "pb_ratio",
                        "roe", "roce", "debt_to_equity", "dividend_yield",
                        "fifty_two_week_high", "fifty_two_week_low",
                        "sector", "industry",
                    ]
                    if snap.get(k) is not None
                }

            # Ownership (latest 4 quarters, compressed)
            own = api.get_shareholding(symbol, quarters=4)
            if own:
                ownership: dict = {}
                for row in own:
                    cat = row.get("category", "")
                    pct = row.get("percentage")
                    qtr = row.get("quarter_end", "")
                    if cat and pct is not None:
                        ownership.setdefault(cat, []).append({"q": qtr, "pct": round(float(pct), 2)})
                baseline["ownership"] = ownership

            # Consensus estimate
            est = api.get_consensus_estimate(symbol)
            if est and isinstance(est, dict):
                baseline["consensus"] = {
                    k: est.get(k)
                    for k in [
                        "target_mean", "target_median", "target_high", "target_low",
                        "num_analysts", "recommendation", "forward_pe", "forward_eps",
                    ]
                    if est.get(k) is not None
                }

            # Fair value signal
            fv = api.get_fair_value(symbol)
            if fv and isinstance(fv, dict):
                baseline["fair_value"] = {
                    k: fv.get(k)
                    for k in [
                        "signal", "margin_of_safety_pct", "current_price",
                        "combined_fair_value",
                    ]
                    if fv.get(k) is not None
                }

            # Data freshness
            fresh = api.get_data_freshness(symbol)
            if fresh:
                baseline["data_freshness"] = fresh

            # SME detection: market cap < ₹500 Cr suggests SME/micro-cap
            mcap = (snap or {}).get("market_cap")
            if mcap is not None and float(mcap) < 500:
                baseline["is_sme"] = True
                baseline["sme_note"] = (
                    "Small/SME stock — may report half-yearly instead of quarterly. "
                    "Adapt financial analysis to available reporting frequency."
                )

            # Corporate actions: check for recent stock splits/bonus
            try:
                events = api.get_upcoming_catalysts(symbol)
                if events and isinstance(events, list):
                    corp_actions = [
                        e for e in events
                        if any(kw in str(e.get("event", "")).lower()
                               for kw in ("split", "bonus", "rights", "subdivision"))
                    ]
                    if corp_actions:
                        baseline["corporate_actions_warning"] = (
                            "Recent/upcoming corporate actions detected (split/bonus/rights). "
                            "Historical per-share data may need adjustment."
                        )
                        baseline["corporate_actions"] = corp_actions
            except Exception:
                pass  # non-critical — don't block baseline

            # Recent news headlines (so specialists see current events)
            try:
                news_items = api.get_stock_news(symbol, days=30)
                if news_items:
                    baseline["recent_headlines"] = [
                        {"title": n["title"], "source": n["source"], "date": n["date"]}
                        for n in news_items[:10]
                    ]
            except Exception:
                pass  # non-critical

    except Exception as exc:
        logger.warning("Failed to build baseline context for %s: %s", symbol, exc)
        baseline["error"] = str(exc)

    return f"<company_baseline>\n{json.dumps(baseline, indent=2, default=str)}\n</company_baseline>"


def generate_business_profile(symbol: str, model: str | None = None) -> Path:
    """Generate a business profile via the business specialist agent.

    Uses the same V2 tools+prompts as run_all_agents (business slot).
    Returns path to the HTML report.
    """
    symbol = symbol.upper()

    envelope, _trace = asyncio.run(run_single_agent("business", symbol, model=model))

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


# --- Verification issue classification & patching ---


def _classify_verification_issues(
    issues: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Classify verification issues into factual, logic, and missing_data categories.

    Factual: wrong numbers (contain specific numeric claims vs actuals)
    Logic: wrong reasoning or unsupported conclusions
    Missing: data gaps flagged by verifier
    """
    import re

    factual, logic, missing_data = [], [], []
    for issue in issues:
        claim = str(issue.get("claim", ""))
        actual = str(issue.get("actual", ""))

        # Missing data: mentions "missing", "not available", "no data", "unavailable"
        if any(
            kw in claim.lower()
            for kw in ("missing", "not available", "no data", "unavailable", "could not find")
        ) or any(
            kw in actual.lower()
            for kw in ("missing", "not available", "no data", "unavailable", "could not find")
        ):
            missing_data.append(issue)
        # Factual: contains numbers in both the claim and actual value
        elif re.search(r"\d+\.?\d*", claim) and re.search(r"\d+\.?\d*", actual):
            factual.append(issue)
        else:
            logic.append(issue)

    return factual, logic, missing_data


def _patch_factual_errors(
    envelope: BriefingEnvelope, factual_issues: list[dict]
) -> BriefingEnvelope:
    """Append a corrections section to the report without re-running the agent."""
    if not factual_issues:
        return envelope

    corrections_text = "\n\n## Auto-Corrections Applied\n"
    corrections_text += "*The following factual errors were detected and corrected by the verification system:*\n\n"
    for issue in factual_issues:
        claim = issue.get("claim", "")
        actual = issue.get("actual", "")
        section = issue.get("section", "")
        section_prefix = f" ({section})" if section else ""
        corrections_text += f"- **Reported{section_prefix}:** {claim}\n  **Actual:** {actual}\n"

    envelope.report = (envelope.report or "") + corrections_text
    return envelope


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
    effort: str | None = None,
) -> tuple[BriefingEnvelope, AgentTrace]:
    """Run a single specialist agent. Returns (BriefingEnvelope, AgentTrace)."""

    tools = tools if tools is not None else AGENT_TOOLS.get(name, [])
    tool_names = [getattr(t, "__name__", str(t)) for t in tools] if tools else []
    max_turns = max_turns or AGENT_MAX_TURNS.get(name, 20)
    max_budget = max_budget or AGENT_MAX_BUDGET.get(name, 0.50)
    model = model or DEFAULT_MODELS.get(name, "claude-sonnet-4-6")

    # Capture subprocess stderr for diagnostics — SDK otherwise hides it
    # behind a hard-coded "Check stderr output for details" placeholder
    # (see https://github.com/anthropics/claude-agent-sdk-python/issues/800).
    # Needed to diagnose the reproducible valuation-agent crash pattern
    # (https://github.com/anthropics/claude-agent-sdk-python/issues/701).
    _stderr_buffer: list[str] = []
    def _stderr_cb(line: str) -> None:
        _stderr_buffer.append(line)
        # Also log at DEBUG so live tail can see it
        logger.debug("[%s] cli-stderr: %s", name, line.rstrip())

    # Build options — only create MCP server when agent has tools
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
        stderr=_stderr_cb,
        setting_sources=[],  # isolate subprocess from user hooks/plugins/skills
        plugins=[],          # no external plugins in specialist subprocess
        env={
            # Bypass cmux's claude-wrapper hook injection — specialist
            # subprocesses don't need SessionStart/UserPromptSubmit/PreToolUse
            # tracking, and the hook calls add latency + a crash surface.
            "CMUX_CLAUDE_HOOKS_DISABLED": "1",
        },
    )
    effort = effort or DEFAULT_EFFORT.get(name)
    if effort:
        options.effort = effort
    if tools:
        server = create_sdk_mcp_server(f"{name}-data", tools=tools)
        options.mcp_servers = {name: server}

    # Block dangerous Claude Code built-ins (Bash, Write, Edit, etc.)
    # MCP tools registered via mcp_servers are available regardless.
    # Per-agent allowed built-ins are SUBTRACTED from the disallow list so an
    # agent with WebSearch allowed isn't simultaneously blocked by the default
    # deny. Without this, the CLI receives the same tool in both --allowedTools
    # and --disallowedTools, and deny wins.
    extra_builtins = AGENT_ALLOWED_BUILTINS.get(name, [])
    options.disallowed_tools = [t for t in _DISALLOWED_BUILTINS if t not in extra_builtins]
    if extra_builtins:
        options.allowed_tools = extra_builtins

    # Reset per-session tool result dedup cache
    _tool_result_cache.set({})

    # Phase 1: Generate report with thinking
    agent_started = datetime.now(timezone.utc).isoformat()
    start_time = time.time()
    start_mono = time.monotonic()
    evidence: list[ToolEvidence] = []
    report_text = ""
    text_blocks: list[str] = []  # fallback: collect text from AssistantMessages
    reasoning_blocks: list[str] = []  # agent thinking before report header
    total_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    agent_model = model
    agent_status = "success"

    # Track tool calls for evidence capture
    # tool_use_id -> {tool, args, started_at, start_mono, turn_index}
    pending_tool_calls: dict[str, dict] = {}

    # Telemetry (C-2a, C-2f): turn-level + time-to-first-token
    turns: list[TurnEvent] = []
    # Telemetry (C-2b): retry events (rate_limit + same-args tool re-calls)
    retries: list[RetryEvent] = []
    turn_index = -1                  # incremented on each AssistantMessage
    current_turn_mono: float | None = None
    current_turn_started: str = ""
    current_turn_reasoning_chars = 0
    current_turn_tool_ids: list[str] = []
    current_turn_usage: dict = {}
    first_token_mono: float | None = None

    def _flush_turn() -> None:
        """Close the in-flight TurnEvent (if any) and append to turns list."""
        nonlocal current_turn_mono, current_turn_started, current_turn_reasoning_chars
        nonlocal current_turn_tool_ids, current_turn_usage
        if current_turn_mono is None or turn_index < 0:
            return
        duration_ms = int((time.monotonic() - current_turn_mono) * 1000)
        u = current_turn_usage or {}
        turns.append(TurnEvent(
            turn_index=turn_index,
            started_at=current_turn_started,
            duration_ms=duration_ms,
            model=agent_model,
            input_tokens=u.get("input_tokens", 0) or 0,
            output_tokens=u.get("output_tokens", 0) or 0,
            cache_read_tokens=u.get("cache_read_input_tokens", 0) or 0,
            cache_write_tokens=u.get("cache_creation_input_tokens", 0) or 0,
            reasoning_chars=current_turn_reasoning_chars,
            tool_call_ids=list(current_turn_tool_ids),
        ))
        # Reset per-turn accumulators
        current_turn_mono = None
        current_turn_started = ""
        current_turn_reasoning_chars = 0
        current_turn_tool_ids = []
        current_turn_usage = {}

    # Retry loop: the Claude SDK subprocess occasionally crashes with
    # "Command failed with exit code 1" before emitting any useful content
    # (ghost spawn, hook crash on teardown, etc.). Retry up to
    # len(SPECIALIST_RETRY_DELAYS_SEC) times — but only when the crash produced
    # no captured content. Crashes AFTER useful content was captured fall
    # through to the existing "graceful degradation" path.
    max_attempts = 1 + len(SPECIALIST_RETRY_DELAYS_SEC)
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        if attempt > 1:
            # Reset per-attempt state before retrying.
            evidence.clear()
            pending_tool_calls.clear()
            text_blocks.clear()
            report_text = ""
            total_cost = 0.0
            input_tokens = 0
            output_tokens = 0
            first_token_mono = None
            turn_index = -1
            current_turn_mono = None
            current_turn_started = ""
            current_turn_reasoning_chars = 0
            current_turn_tool_ids = []
            current_turn_usage = {}
            # Track retry on the trace so evals can see the re-run.
            retries.append(RetryEvent(
                tool_name="(specialist)",
                attempt=attempt,
                cause="subprocess_crash",
                wait_ms=SPECIALIST_RETRY_DELAYS_SEC[attempt - 2] * 1000,
                at=datetime.now(timezone.utc).isoformat(),
            ))
            logger.warning(
                "[%s] %s: specialist retry attempt %d/%d after %ds (no content from prior attempt)...",
                name, symbol, attempt - 1, len(SPECIALIST_RETRY_DELAYS_SEC),
                SPECIALIST_RETRY_DELAYS_SEC[attempt - 2],
            )
            await asyncio.sleep(SPECIALIST_RETRY_DELAYS_SEC[attempt - 2])

        try:
            async for message in query(
                prompt=user_prompt or f"Analyze {symbol}. Pull all relevant data using your tools. Produce your full report section.",
                options=options,
            ):
                if isinstance(message, RateLimitEvent):
                    logger.warning(
                        "[%s] rate limited: status=%s type=%s resets_at=%s",
                        name, message.rate_limit_info.status,
                        message.rate_limit_info.rate_limit_type,
                        message.rate_limit_info.resets_at,
                    )
                    # C-2b: record rate-limit retry event (no specific tool context here)
                    retries.append(RetryEvent(
                        tool_name="(any)",
                        attempt=len(retries) + 1,
                        cause="rate_limit",
                        wait_ms=0,
                        at=datetime.now(timezone.utc).isoformat(),
                    ))
                    continue
                if isinstance(message, AssistantMessage):
                    # C-2f: record first-token timestamp on the very first AssistantMessage
                    if first_token_mono is None:
                        first_token_mono = time.monotonic()

                    # C-2a: a new assistant message = a new turn. Flush previous, start fresh.
                    _flush_turn()
                    turn_index += 1
                    current_turn_mono = time.monotonic()
                    current_turn_started = datetime.now(timezone.utc).isoformat()

                    # Accumulate tokens from each assistant turn (usage is a dict)
                    msg_usage = getattr(message, "usage", None)
                    if isinstance(msg_usage, dict):
                        current_turn_usage = msg_usage  # stored on turn flush
                        input_tokens += msg_usage.get("input_tokens", 0) or 0
                        output_tokens += msg_usage.get("output_tokens", 0) or 0

                    for block in message.content:
                        block_type = type(block).__name__
                        if block_type == "TextBlock":
                            text_blocks.append(block.text)
                            current_turn_reasoning_chars += len(block.text or "")
                        elif isinstance(block, ToolUseBlock):
                            call_started = datetime.now(timezone.utc).isoformat()
                            call_args = block.input or {}
                            pending_tool_calls[block.id] = {
                                "tool": block.name,
                                "args": call_args,
                                "started_at": call_started,
                                "start_mono": time.monotonic(),
                                "turn_index": turn_index,
                            }
                            current_turn_tool_ids.append(block.id)
                            # C-2b: same-(tool, args) re-call = retry. Count prior evidence
                            # entries that match BEFORE we append the new one.
                            prior_matches = sum(
                                1 for ev in evidence
                                if ev.tool == block.name and ev.args == call_args
                            )
                            if prior_matches > 0:
                                retries.append(RetryEvent(
                                    tool_name=block.name,
                                    attempt=prior_matches + 1,
                                    cause="other",
                                    wait_ms=0,
                                    at=call_started,
                                ))
                            # Record evidence immediately from ToolUseBlock.
                            # The Agent SDK processes tool results internally and does NOT
                            # expose ToolResultBlock through the stream, so we capture
                            # tool calls here (result_summary/hash stay empty).
                            evidence.append(ToolEvidence(
                                tool=block.name,
                                args=call_args,
                                started_at=call_started,
                                turn_index=turn_index,
                            ))
                            # Compact args for log readability — show all params, truncate long values
                            compact = {}
                            for k, v in (block.input or {}).items():
                                sv = str(v)
                                compact[k] = sv if len(sv) <= 80 else sv[:77] + "..."
                            logger.info(
                                "[%s] tool_call: %s(%s)",
                                name, block.name, json.dumps(compact, default=str),
                            )
                        elif isinstance(block, ToolResultBlock):
                            # Agent SDK may expose results in future versions.
                            # When available, enrich the matching evidence entry.
                            tool_id = block.tool_use_id
                            if tool_id in pending_tool_calls:
                                call = pending_tool_calls.pop(tool_id)
                                result_str = str(block.content) if block.content else ""
                                call_duration_ms = int((time.monotonic() - call["start_mono"]) * 1000)
                                is_err = getattr(block, "is_error", False) or False
                                # Find and enrich the evidence entry we created above
                                for ev in reversed(evidence):
                                    if ev.tool == call["tool"] and ev.started_at == call["started_at"]:
                                        ev.result_summary = result_str[:500]
                                        ev.result_hash = hashlib.sha256(result_str.encode()).hexdigest()
                                        ev.is_error = is_err
                                        ev.duration_ms = call_duration_ms
                                        break
                                status_icon = "ERR" if is_err else "ok"
                                logger.info(
                                    "[%s] tool_result: %s → %s %d chars %.1fs",
                                    name, call["tool"], status_icon, len(result_str), call_duration_ms / 1000,
                                )
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
                    # C-2a: close the final turn on ResultMessage
                    _flush_turn()
            # Reached end of message stream cleanly — break out of retry loop.
            break
        except Exception as exc:
            # Claude CLI may exit with code 1 after delivering results.
            # If we already captured text, proceed with what we have.
            captured_bytes = len(report_text) + sum(len(tb) for tb in text_blocks)
            has_content = captured_bytes > 0
            # Surface the captured subprocess stderr (SDK bug #800 hides it by default)
            stderr_tail = "\n".join(_stderr_buffer[-50:]).strip()
            if stderr_tail:
                logger.warning(
                    "Agent '%s' for %s CLI stderr (last 50 lines):\n%s",
                    name, symbol, stderr_tail,
                )
            # Retry path: subprocess crashed with no/negligible content and we
            # haven't exhausted attempts yet.
            if captured_bytes < PARTIAL_OUTPUT_BYTES and attempt < max_attempts:
                logger.warning(
                    "Agent '%s' for %s attempt %d raised %s with %d bytes captured — retrying",
                    name, symbol, attempt, type(exc).__name__, captured_bytes,
                )
                # _flush_turn first so any in-flight turn is preserved in telemetry.
                _flush_turn()
                continue  # next iteration of the retry while-loop
            # Otherwise: existing behaviour — preserve partial output OR mark failed.
            if has_content:
                logger.warning(
                    "Agent '%s' for %s raised %s after producing content — proceeding with partial output",
                    name, symbol, type(exc).__name__,
                )
            else:
                agent_status = "failed"
                logger.error(
                    "Agent '%s' for %s FAILED with no output: %s: %s",
                    name, symbol, type(exc).__name__, exc,
                    exc_info=True,
                )
            break
        finally:
            # C-2a: ensure any in-flight turn is flushed even on exception paths
            _flush_turn()

    # C-2f: compute time-to-first-token (delta from query start to first AssistantMessage)
    time_to_first_token_ms = (
        int((first_token_mono - start_mono) * 1000)
        if first_token_mono is not None else None
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
        agent_status = "empty"
        logger.error("Agent '%s' %s: EMPTY REPORT — no ResultMessage and no TextBlocks captured", name, symbol)

    # Capture agent reasoning — the "thinking out loud" preamble before the report.
    # These TextBlocks contain the agent's tool selection rationale and intermediate analysis.
    # Saved separately for observability before being stripped from the report.
    if report_text:
        lines = report_text.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("---"):
                if i > 0:
                    reasoning_blocks = ["\n".join(lines[:i])]
                report_text = "\n".join(lines[i:])
                break

    duration = time.time() - start_time
    agent_finished = datetime.now(timezone.utc).isoformat()

    # Phase 2: Extract structured briefing (skip for non-analyst agents like explainer)
    briefing = {}
    if name not in ("explainer",):
        briefing = await _extract_briefing(name, symbol, report_text)

    cost = AgentCost(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_cost_usd=total_cost,
        duration_seconds=duration,
        model=agent_model,
    )

    # Build envelope
    envelope = BriefingEnvelope(
        agent=name,
        symbol=symbol.upper(),
        generated_at=datetime.now(timezone.utc).isoformat(),
        report=report_text,
        briefing=briefing,
        evidence=evidence,
        cost=cost,
    )

    # C-2e: compliance-gate cross-reference — map mandatory_metrics_status
    # attempt strings to actual tool_use_ids in evidence, so evals can verify
    # that "attempted" claims are backed by real tool calls.
    compliance_traces: list[ComplianceGateTrace] = []
    mms = (briefing or {}).get("mandatory_metrics_status", {}) or {}
    if isinstance(mms, dict):
        for metric_name, entry in mms.items():
            if not isinstance(entry, dict):
                continue
            status = entry.get("status", "missing") or "missing"
            attempts = entry.get("attempts", []) or []
            if not isinstance(attempts, list):
                attempts = []
            # Match "get_foo(section='x')"-style strings against tool names in evidence
            attempted_ids: list[str] = []
            for attempt_str in attempts:
                if not isinstance(attempt_str, str):
                    continue
                # Extract bare tool name (before first '(' or whole string)
                bare = attempt_str.split("(", 1)[0].strip()
                for idx, ev in enumerate(evidence):
                    # tool names may be prefixed (mcp__agent__get_foo)
                    ev_bare = ev.tool.split("__")[-1]
                    if bare and bare == ev_bare:
                        # Use evidence list index as stable tool_use_id proxy
                        attempted_ids.append(f"ev-{idx}")
                        break  # one match per attempt is enough
            if status not in ("extracted", "attempted", "not_applicable", "missing"):
                status = "missing"
            compliance_traces.append(ComplianceGateTrace(
                metric=str(metric_name),
                status=status,
                attempted_tool_use_ids=attempted_ids,
                note=str(entry.get("source", "") or entry.get("value", "") or ""),
            ))

    # Build trace
    trace = AgentTrace(
        agent=name,
        symbol=symbol.upper(),
        started_at=agent_started,
        finished_at=agent_finished,
        duration_seconds=duration,
        status=agent_status,
        tools_available=tool_names,
        tool_calls=evidence,
        reasoning=reasoning_blocks,
        report_chars=len(report_text),
        cost=cost,
        turns=turns,
        retries=retries,
        time_to_first_token_ms=time_to_first_token_ms,
        compliance_gate_traces=compliance_traces,
    )

    # Log unused tools for pipeline optimization
    called_tools = {e.tool.split("__")[-1] for e in evidence}  # strip mcp__agent__ prefix
    available_set = set(tool_names)
    unused = available_set - called_tools
    if unused:
        logger.info("[%s] unused_tools: %s", name, ", ".join(sorted(unused)))

    logger.info(
        "[%s] done: %s %d chars, %d calls, %d/%d tools used, %.0fs, $%.2f",
        name, agent_status, len(report_text), len(evidence), len(called_tools), len(available_set), duration, total_cost,
    )

    # Save to vault (explainer output is saved by the caller to thesis/ paths)
    if name != "explainer":
        save_envelope(envelope)

    return envelope, trace


async def _extract_briefing(name: str, symbol: str, report_text: str) -> dict:
    """Extract structured briefing JSON from a report.

    First tries to parse the ```json block that agents are instructed to include.
    Falls back to a cheap haiku pass that re-uses the agent's own prompt schema.
    """
    # First try: parse from markdown (if agent included a JSON block)
    briefing = parse_briefing_from_markdown(report_text)
    if briefing:
        return briefing

    # No point running haiku on empty/tiny reports
    if len(report_text.strip()) < 200:
        logger.warning(
            "Briefing extraction skipped for '%s' %s: report too short (%d chars)",
            name, symbol, len(report_text),
        )
        return {"agent": name, "symbol": symbol, "extraction_failed": True}

    # Second pass: extract the briefing JSON schema from the agent's own prompt
    # and ask haiku to fill it from the report text
    from flowtracker.research.prompts import AGENT_PROMPTS_V2
    entry = AGENT_PROMPTS_V2.get(name)

    # Find the JSON schema block in the agent's prompt (between ```json and ```)
    # AGENT_PROMPTS_V2 stores (system, instructions) tuples — schema is in instructions
    schema_hint = ""
    if entry:
        import re
        prompt_text = entry[1] if isinstance(entry, tuple) else entry
        schema_matches = re.findall(r"```json\s*\n(.*?)```", prompt_text, re.DOTALL)
        if schema_matches:
            schema_hint = f"\nThe JSON must follow this exact schema:\n```json\n{schema_matches[-1].strip()}\n```\n"

    try:
        extraction_prompt = (
            f"Extract the structured briefing JSON from this {name} analysis report for {symbol}.\n\n"
            "The report should have ended with a JSON briefing block but it's missing. "
            "Read the report and produce the JSON that the analyst should have included.\n"
            f"{schema_hint}\n"
            "Return ONLY valid JSON — no markdown fences, no explanation.\n\n"
            f"Report:\n{report_text[:12000]}"
        )

        options = ClaudeAgentOptions(
            system_prompt=(
                "You are a data extraction assistant. Extract structured data "
                "from equity research reports. Return ONLY valid JSON — no markdown, "
                "no explanation, no code fences. Just the JSON object."
            ),
            max_turns=1,
            permission_mode="bypassPermissions",
            model="claude-haiku-4-5-20251001",
            # Pure JSON extraction from a bounded report — disable thinking so
            # max_turns=1 is always enough (same rationale as extractors).
            thinking={"type": "disabled"},
            setting_sources=[],  # isolate from user hooks/plugins/skills
            plugins=[],          # no external plugins in briefing subprocess
            env={"CMUX_CLAUDE_HOOKS_DISABLED": "1"},  # no cmux hook injection
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

        # Try parsing from markdown fences first (haiku might wrap in ```)
        extracted = parse_briefing_from_markdown(result_text)
        if extracted:
            return extracted

        # Try parsing the raw text as JSON
        raw = result_text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        return json.loads(raw.strip())
    except Exception as exc:
        logger.warning(
            "Briefing extraction failed for '%s' %s: %s: %s (report length: %d chars)",
            name, symbol, type(exc).__name__, exc, len(report_text),
        )
        return {"agent": name, "symbol": symbol, "extraction_failed": True}


async def run_single_agent(
    agent_name: str,
    symbol: str,
    model: str | None = None,
    effort: str | None = None,
) -> tuple[BriefingEnvelope, AgentTrace]:
    """Run a single specialist agent. Uses same V2 prompts/tools as run_all_agents."""
    from flowtracker.research.prompts import build_specialist_prompt

    symbol_upper = symbol.upper()
    system_prompt, instructions = build_specialist_prompt(agent_name, symbol_upper)
    if not system_prompt:
        raise ValueError(f"Unknown agent: {agent_name}")

    baseline = _build_baseline_context(symbol_upper)

    return await _run_specialist(
        name=agent_name,
        symbol=symbol_upper,
        system_prompt=system_prompt,
        model=model,
        effort=effort,
        user_prompt=f"{baseline}\n\n{instructions}\n\nAnalyze {symbol_upper} for the {agent_name} section of the equity research report.",
    )


def _safe_float(val) -> float | None:
    """Safely extract a float from LLM-generated values like '25.5%', '1.5x', 'N/A', ''.

    Returns None on any failure — callers must check for None, not truthiness
    (0.0 is falsy but valid).
    """
    if val is None:
        return None
    try:
        import re as _re
        cleaned = _re.sub(r"[^\d.\-]", "", str(val))
        # Reject multi-decimal like '1.2.3' or empty/just-minus
        if not cleaned or cleaned in ("-", ".", "-.") or cleaned.count(".") > 1:
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _has_word(blob: str, keywords: tuple) -> bool:
    """Word-boundary match for industry keyword detection.

    Avoids false positives like 'oil' matching 'foil' or 'boiler', 'auto' matching
    'auto ancillary' when we only want auto OEM, 'bank' matching 'powerbank'.
    Multi-word keywords are matched as phrases.
    """
    import re as _re
    for k in keywords:
        # Escape + use \b boundaries; multi-word keywords (with spaces) match as-is
        if _re.search(r"\b" + _re.escape(k) + r"\b", blob, _re.IGNORECASE):
            return True
    return False


def _analyze_briefing_signals(briefings: dict[str, dict]) -> str:
    """Pre-analyze briefings for cross-signal forcing functions to the synthesis agent.

    The orchestrator does deterministic pattern-matching; the synthesis agent resolves
    and narrates. Every flag becomes a DIRECTIVE in the synthesis user prompt so Opus
    cannot silently skip high-signal tensions.

    Hardened per Gemini code review:
    - `_safe_float` for dirty LLM-emitted numeric strings (percents, 'x' suffixes)
    - `_has_word` for word-boundary industry matching (no 'foil' → 'oil' false positive)
    - Financial institutions exempted from Altman Z-score (ratio is meaningless for banks)
    - All nested-dict accesses use `(x or {}).get(...)` (LLMs emit explicit None)
    - All string comparisons case-insensitive
    - Directives framed as DIRECTIVE: (stronger than 'investigate')
    """
    lines = []
    cross_signals: list[str] = []

    # --- Normalize signals (lowercase, safe extraction) ---
    signals = {name: str((b or {}).get("signal", "unknown")).lower() for name, b in briefings.items()}

    # --- Safe extraction of all briefing objects ---
    biz = briefings.get("business") or {}
    fin = briefings.get("financials") or {}
    own = briefings.get("ownership") or {}
    val = briefings.get("valuation") or {}
    risk = briefings.get("risk") or {}
    tech = briefings.get("technical") or {}
    macro = briefings.get("macro") or {}
    sector = briefings.get("sector") or {}
    news = briefings.get("news") or {}

    biz_metrics = biz.get("key_metrics") or {}
    regime = macro.get("regime_state") or {}
    india_transmission = macro.get("india_transmission") or {}

    # Industry blob for keyword-based routing — case-insensitive
    sector_name = str(biz.get("sector") or "")
    industry_str = str(sector.get("industry") or "")
    biz_industry = str(biz.get("industry") or "")
    industry_blob = f"{sector_name} {industry_str} {biz_industry}".lower()

    val_signal = signals.get("valuation", "")
    tech_signal = signals.get("technical", "")
    risk_signal = signals.get("risk", "")
    macro_signal = signals.get("macro", "")

    # --- Agreement + dissent (framed as divergence, not a vote) ---
    valid_signals = [s for s in signals.values() if s not in ("unknown", "neutral", "")]
    if valid_signals:
        from collections import Counter
        counts = Counter(valid_signals)
        majority_sig, majority_count = counts.most_common(1)[0]
        agreement = majority_count / len(valid_signals) * 100
        lines.append(
            f"**Signal landscape:** {len(valid_signals)} agents responded. "
            f"Leaning {majority_sig.upper()} ({majority_count}/{len(valid_signals)} = {agreement:.0f}%). "
            f"Breakdown: {dict(counts)}."
        )
        dissenters = [
            (n, s) for n, s in signals.items()
            if s not in (majority_sig, "unknown", "neutral", "")
        ]
        if dissenters:
            lines.append(
                f"**DIRECTIVE — divergence detected:** "
                f"{', '.join(f'{n}={s}' for n, s in dissenters)} vs majority {majority_sig}. "
                f"Verdict MUST explicitly address the dissenting agents' concerns, not average them away."
            )

    # --- Growth vs ownership ---
    growth = str(fin.get("growth_trajectory") or biz.get("signal", "")).lower()
    mf_trend = str(own.get("mf_trend", "")).lower()
    fii_trend = str(own.get("fii_trend", "")).lower()
    insider = str(own.get("insider_signal", "")).lower()

    if "decelerat" in growth and "increas" in mf_trend:
        cross_signals.append("Growth decelerating BUT DIIs/MFs accumulating — smart money sees value or turnaround despite slowing growth. Investigate the thesis institutions are pricing in.")
    if "decreas" in fii_trend and "increas" in mf_trend:
        cross_signals.append("FII selling + DII/MF buying = institutional handoff. Historically a strong support base in Indian equities 2022-2025.")

    # --- Promoter/insider amplifier (new per review) ---
    if "net_buying" in insider and ("decreas" in fii_trend or "decreas" in mf_trend):
        cross_signals.append("Promoter/insider buying WHILE FIIs/MFs sell — management sees intrinsic value institutions are missing. High-conviction contrarian signal in Indian markets.")
    if "net_buying" in insider and "bearish" in tech_signal:
        cross_signals.append("Insider buying into technical weakness — management conviction at a price level institutions are exiting.")

    # --- Quality vs valuation ---
    roce_val = _safe_float(biz_metrics.get("roce_pct")) or _safe_float(fin.get("roce_current"))
    if roce_val is not None and roce_val > 20 and "undervalued" in val_signal:
        cross_signals.append(f"High ROCE ({roce_val}%) + undervalued = classic Quality-at-Reasonable-Price (QARP) setup.")

    # --- Falling knife guard (new per review) ---
    if "undervalued" in val_signal and "bearish" in tech_signal:
        cross_signals.append("DIRECTIVE — Falling knife risk: Undervalued AND technicals bearish. Require explicit technical bottoming signal or a named near-term fundamental catalyst before assigning BUY. PSU/legacy stocks frequently trap investors in this pattern.")

    # --- Risk vs valuation (value trap — distinct from governance cap below) ---
    if "bearish" in risk_signal and "undervalued" in val_signal:
        cross_signals.append("Risk bearish + valuation undervalued — potential value trap. Explicitly determine whether the market has already priced the risks or whether they are underappreciated.")

    # --- Sector × stock ---
    sector_signal = str(sector.get("sector_growth_signal", "")).lower()
    sector_valuation = str(sector.get("sector_valuation_signal", "")).lower()
    if "growing" in sector_signal and "undervalued" in val_signal:
        cross_signals.append("Sector growing + stock undervalued = riding sector tailwind at a discount.")
    if "expensive" in sector_valuation and "expensive" in val_signal:
        cross_signals.append("Both sector and stock expensive — mean-reversion risk amplified if either rerates down.")

    # --- News sentiment contrarian ---
    news_sentiment = str(news.get("sentiment_signal", "")).lower()
    if "negative" in news_sentiment and "increas" in mf_trend:
        cross_signals.append("Negative news sentiment BUT DIIs/MFs accumulating — smart money buying the dip. Identify what institutions are pricing in that headlines aren't.")
    if "positive" in news_sentiment and "decreas" in fii_trend:
        cross_signals.append("Positive news flow BUT FII selling — institutions see something headlines miss. Identify the disconnect.")

    # --- Quality-trajectory guard ---
    quality_sig = str(fin.get("quality_signal", "")).lower()
    dupont = str(fin.get("dupont_driver", "")).lower()
    is_quality_declining = any(w in quality_sig + " " + dupont for w in ("declin", "deterior", "weaken", "compress", "erod"))
    if is_quality_declining and "undervalued" in val_signal:
        cross_signals.append("DIRECTIVE — Quality trajectory declining (ROCE/margins/FCF eroding) + undervalued = deterioration already priced in. Require a specific reversal catalyst (management change, capacity commissioning, cycle turn) before assigning BUY. Otherwise: value trap.")
    if is_quality_declining and roce_val is not None and roce_val > 20:
        cross_signals.append(f"ROCE {roce_val}% high but trajectory declining — Ambit/Marathon capital-cycle quality degradation. A single-year high does NOT equal secular quality; synthesis must weight trajectory over snapshot.")

    # --- Macro regime × business model routers ---
    # Financial institution detection — needed for Z-score exemption AND rate-sensitivity
    is_financial = _has_word(industry_blob, ("bank", "nbfc", "finance", "housing finance", "insurance", "asset management"))

    # Rate-sensitivity: include banks/NBFCs/HFCs/REITs/auto OEMs. Exclude auto ancillary (B2B, export-driven).
    is_rate_sensitive = is_financial or _has_word(industry_blob, ("real estate", "realty", "reit", "auto oem", "two wheeler", "passenger vehicle"))
    rate_cycle = str(regime.get("rate_cycle", "")).lower()
    if is_rate_sensitive and "hiking" in rate_cycle:
        cross_signals.append(f"DIRECTIVE — Rate-sensitive business in {rate_cycle} regime. Bottom-up thesis must explicitly model margin compression + demand moderation from rising cost of funds/EMIs. Require stronger evidence before BUY.")
    if is_rate_sensitive and "cutting" in rate_cycle:
        cross_signals.append(f"Rate-sensitive business in {rate_cycle} regime — macro tailwind via NIM expansion (financials) or demand acceleration (autos/real estate). Verify the bottom-up thesis quantifies this benefit.")

    # Macro × micro tension
    bottom_up_bullish_count = sum(1 for a in (biz, fin, own, val) if str((a or {}).get("signal", "")).lower() == "bullish")
    if macro_signal == "bearish" and bottom_up_bullish_count >= 2:
        cross_signals.append("DIRECTIVE — Macro-vs-micro tension: macro regime BEARISH but 2+ bottom-up specialists BULLISH. Require 5+ confirming signals (not 3) + explicit reasoning on why the bottom-up thesis survives the macro regime.")
    if macro_signal == "bullish" and "bearish" in risk_signal:
        cross_signals.append("Macro tailwind BUT risk agent bearish — idiosyncratic concern dominates a favorable regime. The company-specific risk is the binding constraint.")

    # Input-cost tension
    input_cost = str(india_transmission.get("input_cost", "")).lower()
    opm_trend = str(fin.get("opm_trend", "")).lower()
    if input_cost == "headwind" and "expand" in opm_trend:
        cross_signals.append("Macro flags input-cost HEADWIND but financials show margin expansion — either pricing power is exceptional (confirm) or the shock hasn't hit reported financials yet (check recency: financials latest period vs today).")

    # FX × export/import (regex word boundaries to avoid false positives)
    inr_regime = str(regime.get("inr_regime", "")).lower()
    exporter_keywords = (
        "it services", "software", "it consulting", "bpo", "ites",
        "pharma", "drug manufacturer", "cdmo", "specialty chemical", "apl",
        "textile", "apparel", "leather", "engineering export",
    )
    importer_keywords = (
        "refinery", "refineries", "oil marketing", "fertilizer",
        "electronic component", "edible oil", "lng import",
    )
    is_exporter = _has_word(industry_blob, exporter_keywords)
    is_importer = _has_word(industry_blob, importer_keywords)

    if "weaken" in inr_regime and is_exporter:
        cross_signals.append("INR weakening + export-heavy industry — revenue translation TAILWIND. Verify the bottom-up thesis explicitly quantifies the FX benefit (esp. EBITDA margin impact from USD-billed revenue against INR cost base).")
    if "weaken" in inr_regime and is_importer:
        cross_signals.append("INR weakening + import-dependent industry — margin HEADWIND via imported-input cost inflation. Check hedging policy, pass-through ability, and whether current margins already reflect the FX shock.")
    if "strengthen" in inr_regime and is_exporter:
        cross_signals.append("INR strengthening + exporter — revenue translation HEADWIND. Verify guidance has been re-based for stronger INR; legacy ₹83-84 assumptions will overstate.")

    # Commodity regime × producer/consumer (new per review)
    commodity_regime = str(regime.get("commodity_regime", "")).lower()
    commodity_consumer = _has_word(industry_blob, (
        "fmcg", "paint", "adhesive", "packaging", "tyre", "auto oem", "consumer durable",
        "personal care", "food", "beverage",
    ))
    commodity_producer = _has_word(industry_blob, (
        "metal", "mining", "steel", "aluminium", "copper", "zinc",
        "oil exploration", "oil and gas", "cement", "sugar",
    ))
    if ("inflation" in commodity_regime or "inflationary" in commodity_regime) and commodity_consumer:
        cross_signals.append("DIRECTIVE — Commodity regime inflationary + consumer-facing industry (FMCG/autos/paints): gross-margin HEADWIND via raw-material cost. Bottom-up thesis must demonstrate price-pass-through ability or premiumisation shield.")
    if ("inflation" in commodity_regime or "inflationary" in commodity_regime) and commodity_producer:
        cross_signals.append("Commodity regime inflationary + commodity producer (metals/energy/cement): realization TAILWIND on output prices. Check whether volumes + realizations are captured in recent quarter earnings.")
    if ("disinflation" in commodity_regime or "deflation" in commodity_regime) and commodity_consumer:
        cross_signals.append("Commodity regime disinflationary + consumer sector: gross-margin TAILWIND via input-cost relief. Check whether financials show expanding OPM.")
    if ("disinflation" in commodity_regime or "deflation" in commodity_regime) and commodity_producer:
        cross_signals.append("DIRECTIVE — Commodity regime disinflationary + producer sector: revenue realization HEADWIND. Even volume growth may not offset price declines. Require explicit price/volume decomposition.")

    # --- Governance & distress cap (Ambit/Marcellus style) ---
    gov_signal = str(risk.get("governance_signal", "")).lower()
    m_score = _safe_float(risk.get("m_score"))
    z_score = _safe_float(risk.get("z_score"))
    pledge_pct = _safe_float(own.get("pledge_pct"))

    gov_triggers: list[str] = []
    if m_score is not None and m_score > -2.22:
        gov_triggers.append(f"M-Score {m_score} > -2.22 (Beneish earnings-manipulation zone)")
    # Altman Z-score is designed for non-financial firms; the ratios (WC/Assets, Sales/Assets)
    # are meaningless for banks/NBFCs/insurers. Exempt them explicitly.
    if z_score is not None and z_score < 1.8 and not is_financial:
        gov_triggers.append(f"Altman Z-Score {z_score} < 1.8 (distress zone — non-financial firms only)")
    if pledge_pct is not None and pledge_pct > 20:
        gov_triggers.append(f"Promoter pledge {pledge_pct}% > 20%")
    if "red_flag" in gov_signal or "deteriorat" in gov_signal:
        gov_triggers.append(f"Qualitative governance signal: {gov_signal}")

    if gov_triggers:
        triggers_str = "; ".join(gov_triggers)
        cross_signals.append(
            f"**🔴 GOVERNANCE / DISTRESS CAP TRIGGERED** — {triggers_str}. "
            f"DIRECTIVE: Verdict MUST cap at HOLD regardless of other signals unless a verified "
            f"change-in-management or change-in-auditor catalyst exists. Indian institutional investors "
            f"heavily penalize these metrics — governance failures destroy portfolio returns faster than "
            f"valuation mistakes."
        )

    # --- Emit ---
    if cross_signals:
        lines.append("\n**SYNTHESIS DIRECTIVES & CROSS-SIGNALS (From Orchestrator — must be addressed in Verdict):**")
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
    effort: str | None = None,
) -> tuple[dict[str, BriefingEnvelope], PipelineTrace]:
    """Run all 8 specialist agents in parallel, optionally verify, return (envelopes, trace)."""
    from flowtracker.research.briefing import PhaseEvent
    from flowtracker.research.prompts import build_specialist_prompt

    symbol = symbol.upper()
    agent_names = ["business", "financials", "ownership", "valuation", "risk", "technical", "sector", "news", "macro", "historical_analog"]

    pipeline_started = datetime.now(timezone.utc).isoformat()
    pipeline_start_mono = time.monotonic()
    trace = PipelineTrace(symbol=symbol, started_at=pipeline_started)

    # Pre-fetch baseline context once for all agents
    baseline = _build_baseline_context(symbol)

    # Phase 1: Run specialists with concurrency limit, error recovery, and abort cascading
    specialists_phase = PhaseEvent(phase="specialists", started_at=datetime.now(timezone.utc).isoformat())
    MAX_CONCURRENT = 3  # max agents running simultaneously
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tier1_failed = asyncio.Event()  # abort signal for tier-3 agents

    def _classify_error(exc: Exception) -> tuple[str, int]:
        """Classify exception for error-specific backoff. Returns (error_class, base_delay_s)."""
        if isinstance(exc, CLIConnectionError):
            return "cli_connection", 5
        err_str = str(exc).lower()
        if "rate limit" in err_str or "429" in err_str:
            return "rate_limit", 30
        if "overloaded" in err_str or "529" in err_str:
            return "overloaded", 15
        return "unknown", 5

    async def _run_with_limit(name: str, sys_prompt: str, instr: str) -> tuple[str, BriefingEnvelope | Exception, AgentTrace | None]:
        """Run a specialist with concurrency limiting, error-classified retry, and abort awareness."""
        tier = AGENT_TIERS.get(name, 3)
        max_retries = TIER_MAX_RETRIES.get(tier, 1)
        last_trace: AgentTrace | None = None

        for attempt in range(1 + max_retries):
            # Tier-3 agents check abort before acquiring semaphore
            if tier == 3 and tier1_failed.is_set():
                logger.info("[%s] skipped — tier-1 failed, synthesis capped", name)
                return name, BriefingEnvelope(
                    agent=name, symbol=symbol,
                    status="skipped", failure_reason="Tier-1 agent failed",
                ), None

            async with semaphore:
                try:
                    envelope, agent_trace = await _run_specialist(
                        name=name, symbol=symbol, system_prompt=sys_prompt, model=model,
                        effort=effort,
                        user_prompt=f"{baseline}\n\n{instr}\n\nAnalyze {symbol} for the {name} section of the equity research report.",
                    )
                    last_trace = agent_trace
                    # Check if agent actually produced content
                    if envelope.report and len(envelope.report.strip()) > 100:
                        return name, envelope, agent_trace
                    # Empty report — treat as failure for retry
                    if attempt < max_retries:
                        agent_trace.status = "retried"
                        logger.warning(
                            "[%s] empty report (attempt %d/%d) — retrying in 5s",
                            name, attempt + 1, 1 + max_retries,
                        )
                        await asyncio.sleep(5)
                        continue
                    return name, envelope, agent_trace  # return empty on last attempt
                except Exception as exc:
                    error_class, base_delay = _classify_error(exc)
                    delay = min(base_delay * (2 ** attempt), 120)
                    if attempt < max_retries:
                        logger.warning(
                            "[%s] %s error (attempt %d/%d) — retrying in %ds: %s",
                            name, error_class, attempt + 1, 1 + max_retries, delay, exc,
                        )
                        await asyncio.sleep(delay)
                        continue
                    logger.error(
                        "[%s] failed after %d attempts (%s): %s",
                        name, 1 + max_retries, error_class, exc,
                    )
                    return name, exc, last_trace
        # Should not reach here, but just in case
        return name, Exception(f"Agent {name} exhausted retries"), last_trace

    async def _run_with_abort(name: str, sys_prompt: str, instr: str) -> tuple[str, BriefingEnvelope | Exception, AgentTrace | None]:
        """Wrapper that signals/checks tier-1 abort cascading."""
        result = await _run_with_limit(name, sys_prompt, instr)
        name_r, envelope_r, trace_r = result

        # Signal abort if tier-1 agent failed
        tier = AGENT_TIERS.get(name, 3)
        if tier == 1:
            is_failed = isinstance(envelope_r, Exception) or (
                hasattr(envelope_r, "status") and envelope_r.status in ("failed", "empty")
            )
            if is_failed:
                tier1_failed.set()
                logger.warning("[%s] tier-1 failed — signaling abort for pending tier-3 agents", name)

        return result

    # Phase 1 + 1.5 pipelined: as soon as a specialist finishes, kick off its verifier.
    # Separate semaphores keep specialist and verifier concurrency caps independent —
    # no increase in peak Claude subprocess count (≤3 specialists + ≤3 verifiers in flight).
    # Sequential specialist-only then verifier-only wastes wall time waiting for the
    # slowest specialist before any verifier starts; pipelining removes that stall.
    from flowtracker.research.verifier import _run_verifier, apply_corrections
    verify_sem = asyncio.Semaphore(MAX_CONCURRENT)

    # Agents whose output is web-sourced with inline citations (macro) or
    # fact-retrieval answers (web_research) don't fit the MCP-data spot-check
    # model the verifier is designed for — skip them to save cost + avoid noise.
    _VERIFIER_SKIP = {"web_research", "macro"}

    async def _run_specialist_then_verify(
        name: str, sys_prompt: str, instr: str
    ) -> tuple[str, BriefingEnvelope | Exception, AgentTrace | None, object]:
        """Run a specialist and, on success, immediately verify — pipelined."""
        spec_name, envelope_or_exc, agent_trace = await _run_with_abort(name, sys_prompt, instr)

        # Skip verification for failed / empty / exception specialists
        if not verify or isinstance(envelope_or_exc, Exception):
            return (spec_name, envelope_or_exc, agent_trace, None)
        envelope = envelope_or_exc
        if not envelope.report or len(envelope.report.strip()) < 100:
            return (spec_name, envelope, agent_trace, None)
        if getattr(envelope, "status", None) in ("skipped", "failed"):
            return (spec_name, envelope, agent_trace, None)
        # Skip verification for web-sourced / fact-retrieval agents
        if spec_name in _VERIFIER_SKIP:
            return (spec_name, envelope, agent_trace, None)

        try:
            async with verify_sem:
                vdata = await _run_verifier(spec_name, symbol, envelope, model=verify_model)
            return (spec_name, envelope, agent_trace, vdata)
        except Exception as vexc:
            return (spec_name, envelope, agent_trace, vexc)

    # Build pipelined tasks for all agents that have prompts
    specialist_tasks = []
    for name in agent_names:
        system_prompt, instructions = build_specialist_prompt(name, symbol)
        if not system_prompt:
            continue
        specialist_tasks.append(_run_specialist_then_verify(name, system_prompt, instructions))

    results = await asyncio.gather(*specialist_tasks)

    # Collect specialist envelopes + traces
    envelopes: dict[str, BriefingEnvelope] = {}
    verification_payloads: dict[str, object] = {}  # name -> vdata (or Exception / None)
    for name, envelope_or_exc, agent_trace, vdata in results:
        if agent_trace:
            trace.agents[name] = agent_trace
        if isinstance(envelope_or_exc, Exception):
            print(f"  ⚠ {name} agent failed: {envelope_or_exc}")
            envelopes[name] = BriefingEnvelope(
                agent=name, symbol=symbol,
                status="failed", failure_reason=str(envelope_or_exc),
            )
        elif not envelope_or_exc.report or len(envelope_or_exc.report.strip()) < 100:
            envelopes[name] = BriefingEnvelope(
                agent=name, symbol=symbol,
                status="empty", failure_reason="Agent produced no substantive output",
                report=envelope_or_exc.report, briefing=envelope_or_exc.briefing,
                evidence=envelope_or_exc.evidence, cost=envelope_or_exc.cost,
            )
        else:
            envelopes[name] = envelope_or_exc
        verification_payloads[name] = vdata

    specialists_phase.finished_at = datetime.now(timezone.utc).isoformat()
    specialists_phase.duration_seconds = sum(
        t.duration_seconds for t in trace.agents.values()
    )
    trace.phases.append(specialists_phase)

    # Phase 1.5: Apply verification corrections (verifier Claude calls already ran in pipeline above)
    if verify and envelopes:
        verification_questions: list[dict] = []  # missing data issues -> web research

        # Iterate over verify payloads collected from the pipeline
        for name, vdata in verification_payloads.items():
            if vdata is None:
                continue  # specialist was skipped/failed/empty — no verifier ran
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

            # Tiered handling for verification failures:
            # - Logic errors -> full re-run (expensive but necessary)
            # - Factual errors only -> patch in-place (no re-run)
            # - Missing data -> route to web research agent
            if vdata.verdict == "fail":
                factual, logic, missing = _classify_verification_issues(vdata.issues or [])

                # Collect missing data issues for web research
                if missing:
                    for issue in missing:
                        claim = issue.get("claim", "") or issue.get("actual", "")
                        verification_questions.append({
                            "question": f"Verify: {claim}",
                            "source_agent": name,
                        })

                if logic and len(logic) >= 3:
                    # Logic/reasoning errors -> re-run only when >=3 errors (systemic issue)
                    print(f"  🔄 {name} has {len(logic)} logic error(s) — re-running once with corrections")
                    rerun_system, rerun_instructions = build_specialist_prompt(name, symbol)
                    corrections_context = (
                        f"\n\n## CORRECTIONS REQUIRED (from verification agent)\n"
                        f"Your previous report was independently verified and flagged.\n"
                        f"**Issues found:**\n{json.dumps(vdata.issues, indent=2)}\n\n"
                        f"**Required corrections:**\n{json.dumps(vdata.corrections, indent=2)}\n\n"
                        f"Re-generate your report. Fix the flagged issues. "
                        f"Re-fetch the specific data points that were wrong — don't guess."
                    )
                    try:
                        rerun, rerun_trace = await _run_specialist(
                            name=name,
                            symbol=symbol,
                            system_prompt=rerun_system + corrections_context,
                            model=model,
                            user_prompt=f"{baseline}\n\n{rerun_instructions}\n\nAnalyze {symbol} for the {name} section of the equity research report.",
                        )
                        envelopes[name] = rerun
                        rerun_trace.status = "rerun_after_verification"
                        trace.agents[f"{name}_rerun"] = rerun_trace
                    except Exception as e:
                        print(f"  ⚠ {name} re-run failed — marking as failed: {e}")
                        envelopes[name] = BriefingEnvelope(
                            agent=name, symbol=symbol,
                            status="failed",
                            failure_reason=f"Failed verification and re-run: {e}",
                        )
                elif logic:
                    # Fewer than 3 logic errors — downgrade to pass_with_notes, no re-run
                    logger.info(
                        "%s verification downgraded: fail -> pass_with_notes (%d logic errors < 3 threshold)",
                        name, len(logic),
                    )
                    vdata.verdict = "pass_with_notes"
                    print(f"  ↓ {name} verification downgraded to pass_with_notes ({len(logic)} logic errors, below re-run threshold)")
                    envelopes[name] = apply_corrections(envelopes[name], vdata)
                    save_envelope(envelopes[name])
                elif factual:
                    # Factual errors only -> patch directly, no expensive re-run
                    print(f"  ✓ {name} — patching {len(factual)} factual error(s) (no re-run)")
                    envelopes[name] = _patch_factual_errors(envelopes[name], factual)
                    save_envelope(envelopes[name])

        # Inject verification-sourced missing data questions into briefings
        # so run_web_research_agent picks them up via open_questions
        if verification_questions:
            updated_agents: set[str] = set()
            for vq in verification_questions:
                agent_name = vq["source_agent"]
                if agent_name in envelopes and envelopes[agent_name].briefing:
                    oq = envelopes[agent_name].briefing.setdefault("open_questions", [])
                    oq.append(vq["question"])
                    updated_agents.add(agent_name)
            # Re-save updated envelopes so run_web_research_agent picks up the
            # injected questions when it calls load_all_briefings from vault
            for agent_name in updated_agents:
                save_envelope(envelopes[agent_name])
            logger.info(
                "Injected %d verification questions into %d briefing(s) for web research",
                len(verification_questions),
                len(updated_agents),
            )

    # Phase 1.75: Web research to resolve open questions
    web_phase = PhaseEvent(phase="web_research", started_at=datetime.now(timezone.utc).isoformat())
    try:
        web_envelope, web_trace = await run_web_research_agent(symbol, model)
        trace.agents["web_research"] = web_trace
        if web_envelope.status == "success":
            envelopes["web_research"] = web_envelope
            print(f"  ✓ web_research: {web_envelope.briefing.get('questions_resolved', 0)} questions resolved")
        elif web_envelope.status == "empty":
            print(f"  ○ web_research: no open questions to research")
        else:
            print(f"  ⚠ web_research: {web_envelope.failure_reason}")
    except Exception as exc:
        logger.warning("Web research agent failed for %s: %s", symbol, exc)
        print(f"  ⚠ web_research failed: {exc}")
    web_phase.finished_at = datetime.now(timezone.utc).isoformat()
    trace.phases.append(web_phase)

    return envelopes, trace


async def run_synthesis_agent(
    symbol: str,
    model: str | None = None,
    failed_agents: list[str] | None = None,
    effort: str | None = None,
) -> tuple[BriefingEnvelope, AgentTrace]:
    """Run the synthesis agent on existing briefings."""
    from flowtracker.research.prompts import SYNTHESIS_AGENT_PROMPT_V2 as SYNTHESIS_AGENT_PROMPT
    from flowtracker.research.briefing import load_all_briefings
    from flowtracker.research.tools import get_composite_score, get_fair_value

    symbol = symbol.upper()
    briefings = load_all_briefings(symbol)

    if not briefings:
        raise ValueError(f"No briefings found for {symbol}. Run specialist agents first.")

    # Format briefings for the synthesis prompt — trim to signal fields only
    # to avoid exceeding context limits with full nested briefing data
    briefing_text = ""
    for agent_name, data in briefings.items():
        trimmed = {k: v for k, v in data.items() if k in _SYNTHESIS_FIELDS}
        briefing_text += f"\n### {agent_name.upper()} Briefing\n```json\n{json.dumps(trimmed, indent=2)}\n```\n"

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

    model = model or DEFAULT_MODELS.get("synthesis", "claude-opus-4-6")

    # Inject web research results if available
    web_research_section = ""
    web_briefing = briefings.get("web_research", {})
    resolved = web_briefing.get("resolved", [])
    unresolved = web_briefing.get("unresolved", [])
    if resolved or unresolved:
        web_research_section = "\n## Resolved Open Questions (from web research)\n"
        if resolved:
            for item in resolved:
                q = item.get("question", "")
                ans = item.get("answer", "")
                confidence = item.get("confidence", "?")
                sources = item.get("sources", [])
                agents = ", ".join(item.get("source_agents", []))
                src_str = " | ".join(sources[:2]) if sources else "no URL"
                web_research_section += (
                    f"**Q ({agents}):** {q}\n"
                    f"**A [{confidence}]:** {ans}\n"
                    f"*Source: {src_str}*\n\n"
                )
        if unresolved:
            web_research_section += "## Unresolved Questions\n"
            for item in unresolved:
                q = item.get("question", "")
                reason = item.get("reason", "unknown")
                web_research_section += f"- {q} — *{reason}*\n"
        web_research_section += "\n"

    # Inject news briefing highlights if available
    news_section = ""
    news_briefing = briefings.get("news", {})
    top_events = news_briefing.get("top_events", [])
    if top_events:
        news_section = "\n## Recent News & Catalysts (from news agent)\n"
        for event in top_events[:10]:
            news_section += (
                f"- **[{event.get('category', '?')}]** {event.get('event', '?')} "
                f"({event.get('date', '?')}) — Impact: {event.get('impact', '?')}\n"
            )
        sentiment = news_briefing.get("sentiment_signal", "unknown")
        news_section += f"\nOverall news sentiment: **{sentiment}**\n"

    # Inject macro briefing — placed BEFORE news since macro sets the regime
    # context against which specialists' bottom-up signals must hold up.
    macro_section = ""
    macro_briefing = briefings.get("macro", {})
    if macro_briefing:
        regime = macro_briefing.get("regime_state", {}) or {}
        macro_section = "\n## Macro Backdrop (from macro agent)\n"
        macro_section += f"- Rate cycle: **{regime.get('rate_cycle', '?')}**\n"
        macro_section += f"- Growth pulse: {regime.get('growth_pulse', '?')}\n"
        macro_section += f"- Commodity regime: {regime.get('commodity_regime', '?')}\n"
        macro_section += f"- INR regime: {regime.get('inr_regime', '?')}\n"
        macro_section += f"- Cyclical stage: {macro_briefing.get('cyclical_stage', '?')}\n"
        tailwinds = macro_briefing.get("secular_tailwinds") or []
        headwinds = macro_briefing.get("secular_headwinds") or []
        if tailwinds:
            macro_section += "\n**Secular tailwinds (verified across anchors):**\n"
            for t in tailwinds[:5]:
                name = t.get("name", "?") if isinstance(t, dict) else str(t)
                mech = t.get("mechanism", "") if isinstance(t, dict) else ""
                macro_section += f"- {name}"
                if mech:
                    macro_section += f" — {mech}"
                macro_section += "\n"
        if headwinds:
            macro_section += "\n**Secular headwinds:**\n"
            for h in headwinds[:5]:
                name = h.get("name", "?") if isinstance(h, dict) else str(h)
                mech = h.get("mechanism", "") if isinstance(h, dict) else ""
                macro_section += f"- {name}"
                if mech:
                    macro_section += f" — {mech}"
                macro_section += "\n"
        bull = macro_briefing.get("bull_case_triggers") or []
        bear = macro_briefing.get("bear_case_triggers") or []
        if bull:
            macro_section += "\n**Macro bull triggers:** " + "; ".join(str(b) for b in bull[:3]) + "\n"
        if bear:
            macro_section += f"**Macro bear triggers:** " + "; ".join(str(b) for b in bear[:3]) + "\n"
        macro_section += f"\nMacro regime signal: **{macro_briefing.get('signal', 'neutral')}**\n"

    user_prompt = (
        f"Synthesize the analysis for {symbol}.\n\n"
        f"## Orchestrator Pre-Analysis (suggestions to investigate, not conclusions)\n{signals_analysis}\n\n"
        f"{web_research_section}"
        f"{macro_section}"
        f"{news_section}"
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
        effort=effort,
    )


async def run_web_research_agent(
    symbol: str,
    model: str | None = None,
) -> tuple[BriefingEnvelope, AgentTrace]:
    """Run the web research agent to resolve open questions from specialist briefings.

    Loads existing briefings from vault, collects all open_questions,
    and uses WebSearch/WebFetch to find answers.
    """
    from flowtracker.research.prompts import WEB_RESEARCH_AGENT_PROMPT, _build_temporal_context
    from flowtracker.research.briefing import load_all_briefings
    from flowtracker.research.data_api import ResearchDataAPI
    from flowtracker.research.tools import (
        get_annual_report as _vault_ar_tool,
        get_concall_insights as _vault_concall_tool,
        get_deck_insights as _vault_deck_tool,
    )

    symbol = symbol.upper()
    briefings = load_all_briefings(symbol)

    if not briefings:
        raise ValueError(f"No briefings found for {symbol}. Run specialist agents first.")

    # Collect open questions from all specialist briefings
    all_questions: list[dict] = []
    for agent_name, data in briefings.items():
        if agent_name in ("synthesis", "web_research"):
            continue
        questions = data.get("open_questions", [])
        for q in questions:
            if isinstance(q, str) and q.strip():
                all_questions.append({"question": q.strip(), "source_agent": agent_name})

    if not all_questions:
        logger.info("No open questions found in briefings for %s — skipping web research", symbol)
        empty_env = BriefingEnvelope(
            agent="web_research",
            symbol=symbol,
            status="empty",
            failure_reason="No open questions in specialist briefings",
            briefing={"agent": "web_research", "symbol": symbol,
                      "questions_received": 0, "questions_resolved": 0,
                      "resolved": [], "unresolved": []},
        )
        empty_trace = AgentTrace(
            agent="web_research", symbol=symbol,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            status="skipped",
        )
        return empty_env, empty_trace

    # Group questions by text to find which agents asked the same thing
    question_map: dict[str, list[str]] = {}
    for item in all_questions:
        q = item["question"]
        if q not in question_map:
            question_map[q] = []
        question_map[q].append(item["source_agent"])

    # Build user prompt with all questions
    question_lines = []
    for i, (q, agents) in enumerate(question_map.items(), 1):
        agents_str = ", ".join(sorted(set(agents)))
        question_lines.append(f"{i}. [{agents_str}] {q}")

    user_prompt = (
        f"Research the following {len(question_map)} open questions about {symbol} "
        f"(an Indian-listed stock). Each question is tagged with the specialist agent(s) that asked it.\n\n"
        + "\n".join(question_lines)
        + "\n\nCheck vault first (get_concall_insights / get_annual_report / get_deck_insights) "
        "before WebSearch/WebFetch. Answer every question. Produce your structured JSON briefing at the end."
    )

    # Prepend temporal context so the web_research agent knows today's date + which
    # AR/deck/concall periods are on file — stops re-fetching documents we've already
    # extracted. build_specialist_prompt doesn't cover this agent; inject manually.
    try:
        with ResearchDataAPI() as _api:
            temporal_ctx = _build_temporal_context(symbol, _api)
    except Exception as exc:
        logger.warning("[web_research] temporal context unavailable: %s", exc)
        temporal_ctx = ""

    system_prompt = temporal_ctx + WEB_RESEARCH_AGENT_PROMPT

    model = model or DEFAULT_MODELS.get("web_research", "claude-sonnet-4-6")

    # Scale turns to question count: ~3 turns per question (search + fetch + answer)
    # plus overhead for grouping and final JSON
    dynamic_turns = min(max(len(question_map) * 3 + 5, 15), 40)

    return await _run_specialist(
        name="web_research",
        symbol=symbol,
        system_prompt=system_prompt,
        # Vault-read MCP tools let the agent consult extracted concalls/AR/decks
        # before WebFetching NSE/BSE archives for the same content. WebSearch +
        # WebFetch builtins still available via AGENT_ALLOWED_BUILTINS["web_research"].
        tools=[_vault_concall_tool, _vault_ar_tool, _vault_deck_tool],
        max_turns=dynamic_turns,
        model=model,
        user_prompt=user_prompt,
    )


async def run_explainer_agent(
    symbol: str,
    technical_report: str,
    model: str | None = None,
) -> tuple[BriefingEnvelope, AgentTrace]:
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


def format_timeline(trace: PipelineTrace) -> str:
    """Format a structured pipeline timeline for console display.

    Each line is self-contained and LLM-searchable:
      MM:SS  agent/phase  event  (detail)
    """
    if not trace.started_at:
        return ""

    lines = ["\n[bold]Pipeline Timeline[/]", "─" * 58]

    # Collect all events with their timestamps for chronological ordering
    events: list[tuple[str, str]] = []  # (iso_timestamp, display_line)

    # Phase events
    for phase in trace.phases:
        events.append((phase.started_at, f"  {phase.phase:<20} started"))
        if phase.finished_at:
            dur = phase.duration_seconds
            events.append((phase.finished_at, f"  {phase.phase:<20} done ({dur:.0f}s)"))

    # Agent events — sorted by start time
    for name, at in sorted(trace.agents.items(), key=lambda x: x[1].started_at):
        tools_n = len(at.tool_calls)
        events.append((at.started_at, f"   → {name:<18} started"))
        if at.finished_at:
            status_icon = "✓" if at.status == "success" else "⚠" if at.status == "failed" else "○"
            detail = f"{at.duration_seconds:.0f}s, {tools_n} tools, ${at.cost.total_cost_usd:.2f}"
            events.append((at.finished_at, f"   {status_icon} {name:<18} {at.status} ({detail})"))

    # Sort by timestamp and compute relative offset from pipeline start
    try:
        t0 = datetime.fromisoformat(trace.started_at)
    except ValueError:
        return ""
    events.sort(key=lambda x: x[0])

    for ts, line in events:
        try:
            dt = datetime.fromisoformat(ts)
            offset = (dt - t0).total_seconds()
            mm, ss = divmod(int(offset), 60)
            lines.append(f"{mm:02d}:{ss:02d} {line}")
        except ValueError:
            lines.append(f"??:?? {line}")

    # Footer
    lines.append("─" * 58)
    total_m, total_s = divmod(int(trace.total_duration_seconds), 60)
    lines.append(f"Total: {total_m}m {total_s:02d}s | ${trace.total_cost_usd:.2f}")

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
    effort: str | None = None,
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

            # Pre-render common charts so agents get cache hits
            try:
                from flowtracker.research.charts import render_chart as _render_chart
                for ct in ["price", "pe", "shareholding", "revenue_profit", "composite_radar"]:
                    try:
                        _render_chart(symbol, ct)
                    except Exception:
                        pass  # non-critical — agent will render on demand
            except ImportError:
                pass

            envelopes, _trace = await run_all_agents(symbol, model=model, verify=True, effort=effort)
            result[symbol] = {name: env.briefing for name, env in envelopes.items()}
    return result


async def run_comparison_agent(
    symbols: list[str],
    model: str | None = None,
    skip_fetch: bool = False,
    force: bool = False,
    effort: str | None = None,
) -> tuple[BriefingEnvelope, AgentTrace]:
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
    all_briefings = await _ensure_briefings(symbols, force, skip_fetch, model, effort=effort)

    # Step 2: Format briefings for the comparison agent — trim to signal fields
    briefing_text = ""
    for symbol, briefings in all_briefings.items():
        briefing_text += f"\n### {symbol}\n"
        for agent_name, data in briefings.items():
            trimmed = {k: v for k, v in data.items() if k in _SYNTHESIS_FIELDS}
            briefing_text += f"**{agent_name}:** {json.dumps(trimmed, indent=2)}\n"

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
        model=model or DEFAULT_MODELS.get("synthesis", "claude-opus-4-6"),
        user_prompt=user_prompt,
        effort=effort,
    )
