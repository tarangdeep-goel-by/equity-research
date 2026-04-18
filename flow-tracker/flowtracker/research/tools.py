"""MCP tool definitions wrapping ResearchDataAPI for the research agent."""

from __future__ import annotations

import json
from typing import Any, Literal

from claude_agent_sdk import tool
from mcp.types import ToolAnnotations

from flowtracker.research.data_api import ResearchDataAPI

READ_ONLY = ToolAnnotations(readOnlyHint=True)

import hashlib
from contextvars import ContextVar

# Per-session tool result cache for deduplication
_tool_result_cache: ContextVar[dict[str, str]] = ContextVar("tool_result_cache", default={})


# ---------------------------------------------------------------------------
# Completeness classification (C-2c)
#
# Public helpers for downstream instrumentation (agent.py, evals) to classify
# tool return payloads without changing the tool wire format. We intentionally
# do NOT mutate tool return dicts — the MCP envelope text payload is already
# what the agent sees, and injecting `_meta` would change evidence hashes and
# risk breaking the dedup cache. Instead, callers that observe a raw payload
# (e.g. agent.py's ToolResultBlock path, or evals post-run) invoke
# `classify_completeness` on the decoded JSON to populate
# `ToolEvidence.completeness` and `ToolEvidence.row_count`.
# ---------------------------------------------------------------------------


Completeness = Literal["full", "partial", "empty", "truncated", "error"]


def _count_rows(payload: Any) -> int | None:
    """Best-effort row count for common payload shapes.

    Returns:
        - len(payload) if payload is a list
        - len(payload[key]) for the first matching key in ("rows", "items", "data")
          if payload is a dict whose value at that key is a list
        - None otherwise
    """
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("rows", "items", "data"):
            if key in payload and isinstance(payload[key], list):
                return len(payload[key])
    return None


def classify_completeness(payload: Any) -> tuple[Completeness | None, int | None]:
    """Classify a tool return payload for eval/telemetry purposes.

    Heuristics (evaluated in order):
        - None / empty dict / empty list / empty string → ("empty", 0)
        - dict with truthy "error" key → ("error", None)
        - dict with "_truncated" or "truncated" == True → ("truncated", row_count)
        - dict with "_meta.degraded_quality" truthy → ("partial", row_count)
        - list (non-empty) → ("full", len)
        - str (whitespace-only) → ("empty", 0)
        - fallback → ("full", row_count)
    """
    # Explicit empty cases first
    if payload is None:
        return ("empty", 0)
    if isinstance(payload, (dict, list, str)) and len(payload) == 0:
        return ("empty", 0)

    # Dict-specific signals
    if isinstance(payload, dict):
        if payload.get("error"):
            return ("error", None)
        if payload.get("_truncated") is True or payload.get("truncated") is True:
            return ("truncated", _count_rows(payload))
        meta = payload.get("_meta")
        if isinstance(meta, dict) and meta.get("degraded_quality"):
            return ("partial", _count_rows(payload))

    # Non-empty list → full, with count
    if isinstance(payload, list):
        return ("full", len(payload))

    # Whitespace-only string counts as empty
    if isinstance(payload, str) and not payload.strip():
        return ("empty", 0)

    # Default: full, try to derive a row count
    return ("full", _count_rows(payload))


def _cache_key(tool_name: str, args: dict) -> str:
    """Stable hash of tool name + sorted args."""
    arg_str = json.dumps(args, sort_keys=True, default=str)
    return hashlib.sha256(f"{tool_name}:{arg_str}".encode()).hexdigest()[:16]


def _with_dedup(tool_name: str, result: dict, args: dict) -> dict:
    """Return compact stub if result matches a previous call with same args."""
    cache = _tool_result_cache.get()
    key = _cache_key(tool_name, args)
    result_text = result["content"][0]["text"] if result.get("content") else ""
    result_hash = hashlib.sha256(result_text.encode()).hexdigest()[:16]

    if key in cache and cache[key] == result_hash:
        return {"content": [{"type": "text", "text":
            "[Identical to previous call with same arguments — use prior result.]"}]}

    cache[key] = result_hash
    _tool_result_cache.set(cache)
    return result


def _parse_section(section: str | list) -> str | list:
    """Normalize section parameter — parse JSON array strings into lists.

    Agents sometimes pass '["snapshot","band"]' as a string instead of a list.
    The tool schema declares section as str, so the SDK serializes arrays as strings.
    """
    if isinstance(section, list):
        return section
    if isinstance(section, str) and section.startswith("["):
        try:
            parsed = json.loads(section)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return section


# --- Core Financials ---


@tool(
    "get_quarterly_results",
    "Get quarterly P&L: revenue, expenses, operating profit, net income, EPS, margins. Returns up to 12 quarters.",
    {"symbol": str, "quarters": int},
    annotations=READ_ONLY,
)
async def get_quarterly_results(args):
    with ResearchDataAPI() as api:
        data = api.get_quarterly_results(args["symbol"], args.get("quarters", 12))
    return _with_dedup("get_quarterly_results", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_annual_financials",
    "Get 10 years of annual financials. P&L: revenue, expenses, operating profit, net income, EPS. "
    "Balance Sheet: equity capital, reserves, borrowings, total assets, net block, CWIP, investments, receivables, inventory, cash. "
    "Cash Flow: CFO, CFI, CFF, net cash flow. Also includes: expense breakdown (raw material, employee, power, selling costs), shares outstanding, dividend, and price.",
    {"symbol": str, "years": int},
    annotations=READ_ONLY,
)
async def get_annual_financials(args):
    with ResearchDataAPI() as api:
        data = api.get_annual_financials(args["symbol"], args.get("years", 10))
    return _with_dedup("get_annual_financials", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_efficiency_ratios",
    "Get efficiency ratios: debtor days, inventory days, cash conversion cycle, working capital days, ROCE%. Up to 10 years.",
    {"symbol": str, "years": int},
    annotations=READ_ONLY,
)
async def get_efficiency_ratios(args):
    with ResearchDataAPI() as api:
        data = api.get_screener_ratios(args["symbol"], args.get("years", 10))
    return _with_dedup("get_efficiency_ratios", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_quarterly_balance_sheet",
    "Get quarterly balance sheet from yfinance: total assets, debt, equity, cash, investments, shares outstanding. "
    "Up to 8 quarters. Values in crores. Not available for all stocks (some return empty).",
    {"symbol": str, "quarters": int},
    annotations=READ_ONLY,
)
async def get_quarterly_balance_sheet(args):
    with ResearchDataAPI() as api:
        data = api.get_quarterly_balance_sheet(args["symbol"], args.get("quarters", 8))
    return _with_dedup("get_quarterly_balance_sheet", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_quarterly_cash_flow",
    "Get quarterly cash flow from yfinance: operating CF, free CF, capex, investing CF, financing CF, working capital changes. "
    "Up to 8 quarters. Values in crores. NOT available for banks or many Indian stocks — if empty, use annual CF from get_annual_financials.",
    {"symbol": str, "quarters": int},
    annotations=READ_ONLY,
)
async def get_quarterly_cash_flow(args):
    with ResearchDataAPI() as api:
        data = api.get_quarterly_cash_flow(args["symbol"], args.get("quarters", 8))
    return _with_dedup("get_quarterly_cash_flow", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Valuation ---


@tool(
    "get_valuation_snapshot",
    "Get latest valuation snapshot: price, PE, PB, EV/EBITDA, dividend yield, margins, market cap — 50+ fields.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_valuation_snapshot(args):
    with ResearchDataAPI() as api:
        data = api.get_valuation_snapshot(args["symbol"])
    return _with_dedup("get_valuation_snapshot", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_valuation_band",
    "Get PE (or other metric) percentile band over historical period. Shows where current valuation sits vs history.",
    {"symbol": str, "metric": str, "days": int},
    annotations=READ_ONLY,
)
async def get_valuation_band(args):
    with ResearchDataAPI() as api:
        data = api.get_valuation_band(
            args["symbol"],
            args.get("metric", "pe_trailing"),
            args.get("days", 2500),
        )
    return _with_dedup("get_valuation_band", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_pe_history",
    "Get historical PE and price time series for charting. Up to ~7 years of daily data.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_pe_history(args):
    with ResearchDataAPI() as api:
        data = api.get_pe_history(args["symbol"], args.get("days", 2500))
    return _with_dedup("get_pe_history", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_wacc_params",
    "Get WACC parameters for a stock: risk-free rate, equity risk premium, beta (Nifty regression), "
    "cost of equity (CAPM), cost of debt, debt/equity mix, and final WACC%. Used as discount rate for DCF.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_wacc_params(args):
    with ResearchDataAPI() as api:
        data = api.get_wacc_params(args["symbol"])
    return _with_dedup("get_wacc_params", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Ownership & Institutional ---


@tool(
    "get_shareholding",
    "Get quarterly ownership breakdown: FII%, DII%, MF%, Promoter%, Public%. Up to 12 quarters.",
    {"symbol": str, "quarters": int},
    annotations=READ_ONLY,
)
async def get_shareholding(args):
    with ResearchDataAPI() as api:
        data = api.get_shareholding(args["symbol"], args.get("quarters", 12))
    return _with_dedup("get_shareholding", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_shareholding_changes",
    "Get latest quarter-over-quarter ownership changes by category (FII, DII, Promoter, etc.).",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_shareholding_changes(args):
    with ResearchDataAPI() as api:
        data = api.get_shareholding_changes(args["symbol"])
    return _with_dedup("get_shareholding_changes", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_insider_transactions",
    "Get SAST insider buy/sell trades: person name, category, quantity, value. Up to 1 year.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_insider_transactions(args):
    with ResearchDataAPI() as api:
        data = api.get_insider_transactions(args["symbol"], args.get("days", 1825))
    return _with_dedup("get_insider_transactions", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_bulk_block_deals",
    "Get BSE bulk/block deals — large institutional trades with buyer/seller, qty, price.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_bulk_block_deals(args):
    with ResearchDataAPI() as api:
        data = api.get_bulk_block_deals(args["symbol"])
    return _with_dedup("get_bulk_block_deals", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_mf_holdings",
    "Get MF scheme holdings — which mutual fund schemes hold this stock, quantity, % of NAV.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_mf_holdings(args):
    with ResearchDataAPI() as api:
        data = api.get_mf_holdings(args["symbol"])
    return _with_dedup("get_mf_holdings", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_mf_holding_changes",
    "Get MF holding changes for this stock (latest month). Shows scheme-level additions/reductions.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_mf_holding_changes(args):
    with ResearchDataAPI() as api:
        data = api.get_mf_holding_changes(args["symbol"])
    return _with_dedup("get_mf_holding_changes", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Market Signals ---


@tool(
    "get_delivery_trend",
    "Get delivery % trend — weekly data up to 20 years from Screener charts. High delivery signals accumulation, low signals speculative churn. Default 90 days, set days=9999 for full history.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_delivery_trend(args):
    with ResearchDataAPI() as api:
        data = api.get_delivery_trend(args["symbol"], args.get("days", 30))
    return _with_dedup("get_delivery_trend", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_promoter_pledge",
    "Get quarterly promoter pledge % history. Rising pledge = risk signal.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_promoter_pledge(args):
    with ResearchDataAPI() as api:
        data = api.get_promoter_pledge(args["symbol"])
    return _with_dedup("get_promoter_pledge", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Consensus ---


@tool(
    "get_consensus_estimate",
    "Get latest analyst consensus: target price, recommendation, forward PE, earnings growth estimate.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_consensus_estimate(args):
    with ResearchDataAPI() as api:
        data = api.get_consensus_estimate(args["symbol"])
    return _with_dedup("get_consensus_estimate", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_earnings_surprises",
    "Get quarterly earnings surprises: actual vs estimate EPS, surprise %. Shows beat/miss history.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_earnings_surprises(args):
    with ResearchDataAPI() as api:
        data = api.get_earnings_surprises(args["symbol"])
    return _with_dedup("get_earnings_surprises", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_estimate_revisions",
    "Get EPS estimate revision trends: current vs 7/30/60/90 day ago estimates, plus analyst upgrade/downgrade counts. "
    "Shows if consensus is moving up or down for current quarter, next quarter, current FY, and next FY.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_estimate_revisions(args):
    with ResearchDataAPI() as api:
        data = api.get_estimate_revisions(args["symbol"])
    return _with_dedup("get_estimate_revisions", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_estimate_momentum",
    "Get computed estimate momentum signal: score (0-1), direction (positive/neutral/negative), "
    "and narrative summary of revision trends. Rising estimates = fundamental momentum.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_estimate_momentum(args):
    with ResearchDataAPI() as api:
        data = api.get_estimate_momentum(args["symbol"])
    return _with_dedup("get_estimate_momentum", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Events & Calendar ---


@tool(
    "get_events_calendar",
    "Get upcoming events: next earnings date (with days until), ex-dividend date, consensus EPS and revenue estimates. "
    "Live fetch — always current. Check before any research to set temporal context.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_events_calendar(args):
    with ResearchDataAPI() as api:
        data = api.get_events_calendar(args["symbol"])
    return _with_dedup("get_events_calendar", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Dividend History ---


@tool(
    "get_dividend_history",
    "Get annual dividend per share, payout ratio, and yield history (up to 10 years). "
    "Computed from corporate actions + annual financials. Shows dividend growth trends.",
    {"symbol": str, "years": int},
    annotations=READ_ONLY,
)
async def get_dividend_history(args):
    with ResearchDataAPI() as api:
        data = api.get_dividend_history(args["symbol"], args.get("years", 10))
    return _with_dedup("get_dividend_history", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Macro Context ---


@tool(
    "get_macro_snapshot",
    "Get current macro indicators: VIX, USD/INR, Brent crude, 10Y G-sec yield.",
    {},
    annotations=READ_ONLY,
)
async def get_macro_snapshot(args):
    with ResearchDataAPI() as api:
        data = api.get_macro_snapshot()
    return _with_dedup("get_macro_snapshot", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_fii_dii_streak",
    "Get current FII/DII buying/selling streak — consecutive days of net buy or sell.",
    {},
    annotations=READ_ONLY,
)
async def get_fii_dii_streak(args):
    with ResearchDataAPI() as api:
        data = api.get_fii_dii_streak()
    return _with_dedup("get_fii_dii_streak", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_fii_dii_flows",
    "Get daily FII/DII net flows (in crores) for recent period. Up to 30 days.",
    {"days": int},
    annotations=READ_ONLY,
)
async def get_fii_dii_flows(args):
    with ResearchDataAPI() as api:
        data = api.get_fii_dii_flows(args.get("days", 30))
    return _with_dedup("get_fii_dii_flows", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Screener APIs (Phase 2) ---


@tool(
    "get_chart_data",
    "Get Screener chart time series. chart_type: 'price', 'pe', 'sales_margin', 'ev_ebitda', 'pbv', 'mcap_sales'.",
    {"symbol": str, "chart_type": str},
    annotations=READ_ONLY,
)
async def get_chart_data(args):
    with ResearchDataAPI() as api:
        data = api.get_chart_data(args["symbol"], args["chart_type"])
    return _with_dedup("get_chart_data", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_peer_comparison",
    "Get peer comparison table: CMP, P/E, MCap, ROCE%, etc. for sector peers of the given stock.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_peer_comparison(args):
    with ResearchDataAPI() as api:
        data = api.get_peer_comparison(args["symbol"])
    return _with_dedup("get_peer_comparison", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_yahoo_peers",
    "Get Yahoo Finance recommended peer companies with fundamentals snapshots. "
    "Returns subject + peer company snapshots (valuation, profitability, growth, ownership) with similarity scores. "
    "Better peer selection than Screener — uses Yahoo's recommendation engine.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_yahoo_peers(args):
    symbol = args["symbol"].upper()
    with ResearchDataAPI() as api:
        data = api.get_yahoo_peer_comparison(symbol)
    return _with_dedup("get_yahoo_peers", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_shareholder_detail",
    "Get individual shareholder names and quarterly %: e.g. Vanguard, LIC, etc. Optionally filter by classification.",
    {"symbol": str, "classification": str},
    annotations=READ_ONLY,
)
async def get_shareholder_detail(args):
    with ResearchDataAPI() as api:
        data = api.get_shareholder_detail(
            args["symbol"], args.get("classification")
        )
    return _with_dedup("get_shareholder_detail", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_expense_breakdown",
    "Get raw schedule sub-item breakdowns from financial_schedules table (e.g., Expenses -> Employee Cost, Raw Material). section: 'profit-loss', 'balance-sheet', 'quarters', 'cash-flow'. For structured/analyzed views, use get_fundamentals with section: 'cost_structure', 'balance_sheet_detail', 'cash_flow_quality', or 'working_capital'.",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_expense_breakdown(args):
    with ResearchDataAPI() as api:
        data = api.get_expense_breakdown(
            args["symbol"], args.get("section", "profit-loss")
        )
    return _with_dedup("get_expense_breakdown", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Filings & Info ---


@tool(
    "get_recent_filings",
    "Get recent BSE corporate filings for a stock. Returns filing type, date, subject, PDF link.",
    {"symbol": str, "limit": int},
    annotations=READ_ONLY,
)
async def get_recent_filings(args):
    with ResearchDataAPI() as api:
        data = api.get_recent_filings(args["symbol"], args.get("limit", 10))
    return _with_dedup("get_recent_filings", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_company_info",
    "Get basic company info: symbol, company name, and industry classification.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_company_info(args):
    with ResearchDataAPI() as api:
        data = api.get_company_info(args["symbol"])
    return _with_dedup("get_company_info", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Company Profile & Documents ---


@tool(
    "get_company_profile",
    "Get company business description, key points, and Screener URL. Use to understand what the company does.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_company_profile(args):
    with ResearchDataAPI() as api:
        data = api.get_company_profile(args["symbol"])
    return _with_dedup("get_company_profile", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_company_documents",
    "Get concall transcript/PPT/recording URLs and annual report URLs. Optionally filter by doc_type: 'concall_transcript', 'concall_ppt', 'annual_report'.",
    {"symbol": str, "doc_type": str},
    annotations=READ_ONLY,
)
async def get_company_documents(args):
    with ResearchDataAPI() as api:
        data = api.get_company_documents(args["symbol"], args.get("doc_type"))
    return _with_dedup("get_company_documents", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Business Profile (Vault) ---


@tool(
    "get_business_profile",
    "Read cached business profile from vault. Returns markdown content if exists, empty if not. Check this BEFORE doing web research.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_business_profile(args):
    from pathlib import Path
    symbol = args["symbol"].upper()
    path = Path.home() / "vault" / "stocks" / symbol / "profile.md"
    if path.exists():
        content = path.read_text()
        return _with_dedup("get_business_profile", {"content": [{"type": "text", "text": content}]}, args)
    return _with_dedup("get_business_profile", {"content": [{"type": "text", "text": ""}]}, args)


@tool(
    "save_business_profile",
    "Save a business profile to vault for future reuse. Content should be structured markdown covering: what they do, how they make money, competitive position, industry dynamics, key risks.",
    {"symbol": str, "content": str},
)
async def save_business_profile(args):
    from pathlib import Path
    symbol = args["symbol"].upper()
    path = Path.home() / "vault" / "stocks" / symbol / "profile.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args["content"])
    return {"content": [{"type": "text", "text": f"Saved business profile to {path}"}]}


# --- FMP Data ---


@tool(
    "get_dcf_valuation",
    "Get DCF intrinsic value and margin of safety for a stock. Shows how much the stock is over/under-valued according to discounted cash flow model.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_dcf_valuation(args):
    with ResearchDataAPI() as api:
        data = api.get_dcf_valuation(args["symbol"])
    return _with_dedup("get_dcf_valuation", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_dcf_history",
    "Get historical DCF intrinsic value trajectory. Shows how fair value has changed over time.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_dcf_history(args):
    with ResearchDataAPI() as api:
        data = api.get_dcf_history(args["symbol"])
    return _with_dedup("get_dcf_history", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_technical_indicators",
    "Get latest RSI, SMA-50, SMA-200, MACD, ADX. Use for entry timing context — NOT for buy/sell decisions alone.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_technical_indicators(args):
    with ResearchDataAPI() as api:
        data = api.get_technical_indicators(args["symbol"])
    return _with_dedup("get_technical_indicators", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_dupont_decomposition",
    "Decompose ROE into Net Profit Margin × Asset Turnover × Equity Multiplier (10yr history). Shows what's driving ROE — margin, efficiency, or leverage.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_dupont_decomposition(args):
    with ResearchDataAPI() as api:
        data = api.get_dupont_decomposition(args["symbol"])
    return _with_dedup("get_dupont_decomposition", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_key_metrics_history",
    "Get comprehensive per-share metrics and valuation ratios history (up to 10 years). Includes PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, etc.",
    {"symbol": str, "years": int},
    annotations=READ_ONLY,
)
async def get_key_metrics_history(args):
    with ResearchDataAPI() as api:
        data = api.get_key_metrics_history(args["symbol"], args.get("years", 10))
    return _with_dedup("get_key_metrics_history", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_financial_growth_rates",
    "Get pre-computed annual growth rates: revenue, EBITDA, net income, EPS, FCF. Includes 3yr, 5yr, 10yr CAGRs.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_financial_growth_rates(args):
    with ResearchDataAPI() as api:
        data = api.get_financial_growth_rates(args["symbol"])
    return _with_dedup("get_financial_growth_rates", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_analyst_grades",
    "Get analyst upgrade/downgrade history. Shows which firms are changing ratings and the direction — useful for sell-side sentiment momentum.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_analyst_grades(args):
    with ResearchDataAPI() as api:
        data = api.get_analyst_grades(args["symbol"])
    return _with_dedup("get_analyst_grades", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_price_targets",
    "Get individual analyst price targets with consensus mean, high, low. Shows analyst dispersion and conviction.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_price_targets(args):
    with ResearchDataAPI() as api:
        data = api.get_price_targets(args["symbol"])
    return _with_dedup("get_price_targets", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_fair_value",
    "Get combined fair value estimate from PE band + DCF + analyst consensus. Returns bear/base/bull range, margin of safety %, and signal (DEEP VALUE / UNDERVALUED / FAIR VALUE / EXPENSIVE).",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_fair_value(args):
    with ResearchDataAPI() as api:
        data = api.get_fair_value(args["symbol"])
    return _with_dedup("get_fair_value", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Scoring ---


@tool(
    "get_composite_score",
    "Get 8-factor composite score (0-100) for a stock: ownership, insider, valuation, earnings, quality, delivery, estimates, risk. Each factor has a score, raw value, and explanation.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_composite_score(args):
    from flowtracker.screener_engine import ScreenerEngine
    from flowtracker.store import FlowStore

    with FlowStore() as store:
        engine = ScreenerEngine(store)
        score = engine.score_stock(args["symbol"])
    if score is None:
        return _with_dedup("get_composite_score", {"content": [{"type": "text", "text": "No scoring data available"}]}, args)
    data = {
        "symbol": score.symbol,
        "composite_score": score.composite_score,
        "factors": [
            {"factor": f.factor, "score": f.score, "raw_value": f.raw_value, "detail": f.detail}
            for f in score.factors
        ],
    }
    return _with_dedup("get_composite_score", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Peer Benchmarking ---


@tool(
    "get_peer_metrics",
    "Get FMP key financial metrics (PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, debt/equity, margins) for the subject company and all its peers. Returns subject data, individual peer data, and peer count.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_peer_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_peer_metrics(args["symbol"])
    return _with_dedup("get_peer_metrics", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_peer_growth",
    "Get FMP growth rates (revenue, EBITDA, net income, EPS, FCF growth + 3yr/5yr CAGRs) for the subject company and all its peers.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_peer_growth(args):
    with ResearchDataAPI() as api:
        data = api.get_peer_growth(args["symbol"])
    return _with_dedup("get_peer_growth", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_valuation_matrix",
    "Get multi-metric valuation comparison matrix for a stock vs all its peers. Returns PE, PB, EV/EBITDA, EV/Sales, margins, ROE, growth for subject + all peers, with sector medians and subject percentile ranks. Use this for relative valuation analysis.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_valuation_matrix(args):
    with ResearchDataAPI() as api:
        data = api.get_valuation_matrix(args["symbol"])
    return _with_dedup("get_valuation_matrix", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_sector_benchmarks",
    "Get computed sector benchmark statistics for a metric: subject value, sector median, P25/P75, min/max, and the subject's percentile rank. If no metric specified, returns all benchmarks.",
    {"symbol": str, "metric": str},
    annotations=READ_ONLY,
)
async def get_sector_benchmarks(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_benchmarks(args["symbol"], args.get("metric"))
    return _with_dedup("get_sector_benchmarks", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


get_concall_insights = tool(
    "get_concall_insights",
    "Get pre-extracted concall insights from the vault: 4 quarters of operational metrics, financial metrics, management commentary, subsidiary updates, risk flags, and cross-quarter narrative themes. First call returns a compact table of contents (quarters + populated sections + qa_topics_by_quarter when Q&A carries topic tags). Pass sub_section to drill into one section across all quarters ('operational_metrics' | 'financial_metrics' | 'management_commentary' | 'subsidiaries' | 'qa_session' | 'flags' | 'opening_remarks'). Pass quarter (e.g. 'FY26-Q3') to narrow to a single quarter. Pass qa_topics (e.g. ['margins','guidance']) to return only Q&A exchanges tagged with those topics — implies sub_section='qa_session'.",
    {"symbol": str, "sub_section": str, "quarter": str, "qa_topics": list},
    annotations=READ_ONLY,
)


@get_concall_insights
async def get_concall_insights(args):
    with ResearchDataAPI() as api:
        data = api.get_concall_insights(
            args["symbol"],
            section_filter=args.get("sub_section"),
            quarter=args.get("quarter"),
            qa_topics=args.get("qa_topics"),
        )
    return _with_dedup("get_concall_insights", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


get_deck_insights = tool(
    "get_deck_insights",
    "Get pre-extracted investor-deck insights from the vault: up to 4 quarters of highlights, segment_performance, strategic_priorities, outlook_and_guidance, new_initiatives, charts_described, and slide_topics. Complements get_concall_insights — decks show polished charts, segmental tables, and forward guidance slides that the transcript doesn't expose as structured data. First call returns a compact TOC (quarters + populated sections + slide_topics_by_quarter when tagged). Pass sub_section to drill into one section across all quarters ('highlights' | 'segment_performance' | 'strategic_priorities' | 'outlook_and_guidance' | 'new_initiatives' | 'charts_described'). Pass quarter (e.g. 'FY26-Q3') to narrow. Pass slide_topics (e.g. ['segmental','outlook']) to filter quarters by their topic tags.",
    {"symbol": str, "sub_section": str, "quarter": str, "slide_topics": list},
    annotations=READ_ONLY,
)


@get_deck_insights
async def get_deck_insights(args):
    with ResearchDataAPI() as api:
        data = api.get_deck_insights(
            args["symbol"],
            section_filter=args.get("sub_section"),
            quarter=args.get("quarter"),
            slide_topics=args.get("slide_topics"),
        )
    return _with_dedup("get_deck_insights", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


get_annual_report = tool(
    "get_annual_report",
    "Get pre-extracted annual-report insights from the vault: up to 2 recent fiscal years, plus a cross-year evolution narrative (YoY changes in risks, auditor KAMs, governance, RPTs, strategic framing). Covers chairman_letter, mdna, risk_management, auditor_report, corporate_governance, brsr, related_party, segmental, notes_to_financials, financial_statements. Annual reports unlock data NOT in concalls or decks — auditor opinions & KAMs, contingent liabilities, board composition, related-party scrutiny, BRSR/ESG disclosures, detailed notes to accounts, segmental accounting. First call returns a compact TOC (years_on_file + sections_populated + cross_year_narrative). Pass section='auditor_report' (or any other) to drill into that section across years. Pass year='FY25' to narrow to one year.",
    {"symbol": str, "year": str, "section": str},
    annotations=READ_ONLY,
)


@get_annual_report
async def get_annual_report(args):
    with ResearchDataAPI() as api:
        data = api.get_annual_report(
            args["symbol"],
            year=args.get("year"),
            section=args.get("section"),
        )
    return _with_dedup("get_annual_report", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "render_chart",
    "Generate a PNG chart and return the file path for embedding in your report. "
    "Use the embed_markdown value directly in your report to show the chart. "
    "chart_type options: "
    "STOCK CHARTS: "
    "'price' (price + SMA50/200, 7yr), "
    "'pe' (PE ratio history, 7yr), "
    "'delivery' (delivery % + volume bars, 90 days), "
    "'revenue_profit' (10yr annual revenue & profit bars), "
    "'quarterly' (12-quarter revenue & profit bars), "
    "'margin_trend' (10yr OPM & NPM lines), "
    "'roce_trend' (10yr ROCE bars, color-coded by quality), "
    "'dupont' (DuPont decomposition: margin × turnover × leverage → ROE), "
    "'cashflow' (10yr operating & free cash flow bars), "
    "'shareholding' (12-quarter ownership trend lines), "
    "'fair_value_range' (bear/base/bull vs current price horizontal bar), "
    "'expense_pie' (expense breakdown pie chart), "
    "'composite_radar' (8-factor quality score spider chart), "
    "'dividend_history' (dividend payout ratio & DPS over time). "
    "SECTOR CHARTS: "
    "'sector_mcap' (all sector stocks by market cap), "
    "'sector_growth_bars' (sector peer revenue growth bars), "
    "'sector_profitability_bars' (sector peer ROCE bars), "
    "'sector_pe_distribution' (sector PE histogram with subject marked), "
    "'sector_valuation_scatter' (PE vs ROCE scatter — bargain/avoid quadrants), "
    "'sector_ownership_flow' (MF ownership changes — accumulation/exit). "
    "COMPARISON CHARTS (use comma-separated symbols, e.g. symbol='HDFCBANK,ICICIBANK'): "
    "'comparison_revenue' (indexed revenue trajectories), "
    "'comparison_pe' (PE history overlay), "
    "'comparison_shareholding' (FII/MF ownership trends overlay), "
    "'comparison_radar' (quality score radars overlaid), "
    "'comparison_margins' (OPM/NPM trends overlay). "
    "Returns: {path, embed_markdown}.",
    {"symbol": str, "chart_type": str},
)
async def render_chart(args):
    from flowtracker.research.charts import render_chart as _render
    result = _render(args["symbol"], args["chart_type"])
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


@tool(
    "get_corporate_actions",
    "Get all corporate actions (bonuses, stock splits, dividends, spinoffs, buybacks) for a stock. Shows action type, date, ratio/multiplier, and source. Use to understand share capital changes and adjust historical per-share metrics.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_corporate_actions(args):
    with ResearchDataAPI() as api:
        data = api.get_corporate_actions(args["symbol"])
    return _with_dedup("get_corporate_actions", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_adjusted_eps",
    "Get quarterly EPS adjusted for all stock splits and bonuses. Returns both raw and adjusted EPS so you can see the true earnings trend without per-share discontinuities. Essential for any stock that has had a split or bonus.",
    {"symbol": str, "quarters": int},
    annotations=READ_ONLY,
)
async def get_adjusted_eps(args):
    with ResearchDataAPI() as api:
        data = api.get_adjusted_eps(args["symbol"], args.get("quarters", 12))
    return _with_dedup("get_adjusted_eps", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_financial_projections",
    "Get 3-year bear/base/bull financial projections. Projects revenue, EBITDA, net income, and EPS "
    "based on historical growth trends and margin patterns. Returns assumptions, projections for 3 scenarios, "
    "and implied fair values at different PE multiples. The agent should refine assumptions using concall "
    "guidance and sector context — these are starting estimates, not final answers.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_financial_projections(args):
    with ResearchDataAPI() as api:
        data = api.get_financial_projections(args["symbol"])
    return _with_dedup("get_financial_projections", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Sector Analysis ---


@tool(
    "get_sector_overview_metrics",
    "Get industry-level overview: stock count, total market cap, median PE/PB/ROCE, "
    "valuation range, top stocks. Looks up the industry from the given stock's classification.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_sector_overview_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_overview_metrics(args["symbol"])
    return _with_dedup("get_sector_overview_metrics", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_sector_flows",
    "Get aggregate institutional ownership changes across all stocks in the subject's industry. "
    "Shows which stocks MFs are accumulating, which they're exiting, and net sector flow direction.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_sector_flows(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_flows(args["symbol"])
    return _with_dedup("get_sector_flows", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_sector_valuations",
    "Get all stocks in the subject's industry ranked by market cap, with key metrics: "
    "PE, ROCE, FII%, MF%, price change. Shows where the subject ranks among peers.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_sector_valuations(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_valuations(args["symbol"])
    return _with_dedup("get_sector_valuations", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_upcoming_catalysts",
    "Get upcoming events that could move the stock: earnings dates, board meetings, "
    "ex-dividend, RBI policy, estimated results dates. Returns events within the next "
    "N days sorted by date.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_upcoming_catalysts(args):
    with ResearchDataAPI() as api:
        data = api.get_upcoming_catalysts(args["symbol"], args.get("days", 90))
    return _with_dedup("get_upcoming_catalysts", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_earnings_quality",
    "Earnings quality analysis: CFO/PAT ratio, CFO/EBITDA ratio, accrual ratio (5-10Y trend). "
    "Signals high/low cash conversion quality. NOT available for banks/NBFCs (requires NPA data).",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_earnings_quality(args):
    with ResearchDataAPI() as api:
        data = api.get_earnings_quality(args["symbol"])
    return _with_dedup("get_earnings_quality", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_piotroski_score",
    "Piotroski F-Score (0-9): profitability, leverage, operating efficiency. Adapted for BFSI (NIM proxy for gross margin). Uses split/bonus-adjusted shares for dilution check.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_piotroski_score(args):
    with ResearchDataAPI() as api:
        data = api.get_piotroski_score(args["symbol"])
    return _with_dedup("get_piotroski_score", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_beneish_score",
    "Beneish M-Score: earnings manipulation probability. 8-variable model. Skipped for BFSI. Returns null if any variable can't be computed (no defaults).",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_beneish_score(args):
    with ResearchDataAPI() as api:
        data = api.get_beneish_score(args["symbol"])
    return _with_dedup("get_beneish_score", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_reverse_dcf",
    "Reverse DCF: solve for implied growth rate that justifies current market cap. "
    "Uses FCFF model (WACC) for non-BFSI, FCFE model (Ke) for banks. "
    "Compares implied growth with historical 3Y/5Y revenue CAGR.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_reverse_dcf(args):
    with ResearchDataAPI() as api:
        data = api.get_reverse_dcf(args["symbol"])
    return _with_dedup("get_reverse_dcf", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_capex_cycle",
    "CWIP/Capex tracking with phase detection (Investing/Commissioning/Harvesting/Mature). "
    "10Y trend of CWIP/NetBlock, asset turnover, capex intensity. Not applicable to BFSI.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_capex_cycle(args):
    with ResearchDataAPI() as api:
        data = api.get_capex_cycle(args["symbol"])
    return _with_dedup("get_capex_cycle", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_common_size_pl",
    "Common Size P&L: all expense items as %% of revenue (10Y trend). "
    "For BFSI, denominator is Total Income (interest earned + other income). "
    "Highlights biggest cost and fastest-growing cost category.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_common_size_pl(args):
    with ResearchDataAPI() as api:
        data = api.get_common_size_pl(args["symbol"])
    return _with_dedup("get_common_size_pl", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_revenue_estimates",
    "Consensus revenue estimates: avg/low/high for current and next quarter/year. "
    "Values in crores. Coverage limited to ~Nifty 100-150 stocks.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_revenue_estimates(args):
    with ResearchDataAPI() as api:
        data = api.get_revenue_estimates(args["symbol"])
    return _with_dedup("get_revenue_estimates", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_growth_estimates",
    "Growth estimates: stock growth vs index growth for current/next quarter and year. "
    "Includes long-term growth (LTG) estimate. Coverage limited to ~Nifty 100-150 stocks.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_growth_estimates(args):
    with ResearchDataAPI() as api:
        data = api.get_growth_estimates(args["symbol"])
    return _with_dedup("get_growth_estimates", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_price_performance",
    "Price return vs Nifty 50 and sector index (1M/3M/6M/1Y). "
    "Price return only — excludes dividends. Uses local DB for stock prices, live yfinance for index.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_price_performance(args):
    with ResearchDataAPI() as api:
        data = api.get_price_performance(args["symbol"])
    return _with_dedup("get_price_performance", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_sector_kpis",
    "Sector-specific operational KPIs extracted from concall transcripts. "
    "Uses canonical field names per sector (14 sectors covered: banks, NBFCs, insurance, IT, pharma, "
    "FMCG, auto, cement, metals, real estate, telecom, chemicals, power, oil & gas). "
    "First call returns a table of contents (available KPI keys + coverage + latest values). "
    "Pass sub_section='<kpi_key>' to drill into one KPI's full per-quarter timeline with context. "
    "Example canonical keys: 'gross_npa_pct', 'casa_ratio_pct', 'r_and_d_spend_pct', 'anda_filed_number'.",
    {"symbol": str, "sub_section": str},
    annotations=READ_ONLY,
)
async def get_sector_kpis(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_kpis(args["symbol"], kpi_key=args.get("sub_section"))
    return _with_dedup("get_sector_kpis", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_bfsi_metrics",
    "Bank/NBFC-specific metrics: NIM, ROA, Cost-to-Income, P/B, equity multiplier (5Y trend). "
    "Only for BFSI stocks — returns skipped for non-BFSI and insurance.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_bfsi_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_bfsi_metrics(args["symbol"])
    return _with_dedup("get_bfsi_metrics", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_analytical_profile",
    "Pre-computed analytical profile (updated weekly). Returns ALL metrics in ONE call: "
    "composite score (0-100), Piotroski F-Score (0-9), Beneish M-Score, earnings quality, "
    "Bernstein reverse DCF (implied growth + implied margin + 5x5 sensitivity matrix), "
    "capex cycle phase, common size P&L, BFSI metrics (NIM/ROA if bank), "
    "price performance (1M/3M/6M/1Y vs Nifty + sector). "
    "CALL THIS FIRST — drill into individual tools only for full 10Y history.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_analytical_profile(args):
    with ResearchDataAPI() as api:
        data = api.get_analytical_profile(args["symbol"])
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, args["symbol"])
    return _with_dedup("get_analytical_profile", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "screen_stocks",
    "Screen ~600 Nifty index stocks by pre-computed analytical metrics. "
    "Pass filters dict with _min/_max suffixes or exact match. "
    "Examples: {\"f_score_min\": 7} for F-Score >= 7. "
    "{\"eq_signal\": \"high_quality\", \"composite_score_min\": 60} combines filters. "
    "Available: f_score, m_score, composite_score, eq_signal, rdcf_implied_growth, "
    "capex_phase, perf_1y_excess, is_bfsi, industry, m_score_signal.",
    {"filters": dict},
    annotations=READ_ONLY,
)
async def screen_stocks(args):
    with ResearchDataAPI() as api:
        data = api.screen_stocks(args["filters"])
    return _with_dedup("screen_stocks", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Macro Tools (V2 consolidated) ---


def _add_freshness_meta(data: dict, api, symbol: str) -> dict:
    """Add freshness metadata to tool return payloads."""
    if not isinstance(data, dict):
        return data
    try:
        from datetime import date
        freshness = api.get_data_freshness(symbol)
        data["_meta"] = {
            "as_of_date": str(date.today()),
            "data_freshness": freshness,
        }
    except Exception:
        pass  # Don't break tool calls for metadata failures
    return data


def _get_fundamentals_section(api, symbol, section, args):
    """Route a single section for get_fundamentals."""
    if section == "quarterly_results":
        return api.get_quarterly_results(symbol, args.get("quarters", 12))
    elif section == "annual_financials":
        return api.get_annual_financials(symbol, args.get("years", 10))
    elif section == "ratios":
        return api.get_screener_ratios(symbol, args.get("years", 10))
    elif section == "quarterly_balance_sheet":
        return api.get_quarterly_balance_sheet(symbol, args.get("quarters", 8))
    elif section == "quarterly_cash_flow":
        return api.get_quarterly_cash_flow(symbol, args.get("quarters", 8))
    elif section == "expense_breakdown":
        return api.get_expense_breakdown(symbol, args.get("sub_section", "profit-loss"))
    elif section == "growth_rates":
        return api.get_financial_growth_rates(symbol)
    elif section == "capital_allocation":
        return api.get_capital_allocation(symbol, args.get("years", 5))
    elif section == "rate_sensitivity":
        return api.get_rate_sensitivity(symbol)
    elif section == "cagr_table":
        return api.get_growth_cagr_table(symbol)
    elif section == "cost_structure":
        return api.get_cost_structure(symbol)
    elif section == "balance_sheet_detail":
        return api.get_balance_sheet_detail(symbol)
    elif section == "cash_flow_quality":
        return api.get_cash_flow_quality(symbol)
    elif section == "working_capital":
        return api.get_working_capital_cycle(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_fundamentals",
    "Unified financial data. First call with NO section (or section='toc') returns a compact ~1-2KB table of contents listing the 14 available sections + 4 recommended wave-call compositions. Then drill with section=['<wave sections>'] or section='<single>'. Valid sections: 'quarterly_results' | 'annual_financials' | 'ratios' | 'quarterly_balance_sheet' | 'quarterly_cash_flow' | 'expense_breakdown' | 'growth_rates' | 'capital_allocation' | 'rate_sensitivity' | 'cagr_table' | 'cost_structure' | 'balance_sheet_detail' | 'cash_flow_quality' | 'working_capital'. Do NOT call section='all' — the 70+KB response is truncated mid-payload by the MCP transport. Optional: quarters (default 12), years (default 10), sub_section.",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_fundamentals(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    with ResearchDataAPI() as api:
        # Default behavior when no section specified: return compact TOC.
        # Prevents the 70+KB 'all'-sections payload being truncated mid-response
        # by the MCP transport, the same failure mode ownership fixed earlier.
        if not section_raw or section_raw in ("toc", "summary"):
            data = api.get_fundamentals_toc(symbol)
            if isinstance(data, dict) and "error" not in data:
                data = _add_freshness_meta(data, api, symbol)
            return _with_dedup("get_fundamentals", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)

        section = _parse_section(section_raw)
        if isinstance(section, list):
            data = {s: _get_fundamentals_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "_warning": (
                    "section='all' returns ~70K+ chars and may be truncated by the "
                    "MCP transport. Prefer calling with a specific section or a short "
                    "list of 3-5 sections. Call get_fundamentals with no section "
                    "argument to see the compact TOC with recommended wave compositions."
                ),
                "quarterly_results": api.get_quarterly_results(symbol, args.get("quarters", 12)),
                "annual_financials": api.get_annual_financials(symbol, args.get("years", 10)),
                "ratios": api.get_screener_ratios(symbol, args.get("years", 10)),
                "quarterly_balance_sheet": api.get_quarterly_balance_sheet(symbol, args.get("quarters", 8)),
                "quarterly_cash_flow": api.get_quarterly_cash_flow(symbol, args.get("quarters", 8)),
                "expense_breakdown": api.get_expense_breakdown(symbol, args.get("sub_section", "profit-loss")),
                "growth_rates": api.get_financial_growth_rates(symbol),
                "capital_allocation": api.get_capital_allocation(symbol, args.get("years", 5)),
                "rate_sensitivity": api.get_rate_sensitivity(symbol),
                "cagr_table": api.get_growth_cagr_table(symbol),
                "cost_structure": api.get_cost_structure(symbol),
                "balance_sheet_detail": api.get_balance_sheet_detail(symbol),
                "cash_flow_quality": api.get_cash_flow_quality(symbol),
                "working_capital": api.get_working_capital_cycle(symbol),
            }
        else:
            data = _get_fundamentals_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_fundamentals", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_quality_scores_section(api, symbol, section, args):
    """Route a single section for get_quality_scores."""
    if section == "earnings_quality":
        return api.get_earnings_quality(symbol)
    elif section == "piotroski":
        return api.get_piotroski_score(symbol)
    elif section == "beneish":
        return api.get_beneish_score(symbol)
    elif section == "dupont":
        return api.get_dupont_decomposition(symbol)
    elif section == "common_size":
        return api.get_common_size_pl(symbol)
    elif section == "capex_cycle":
        return api.get_capex_cycle(symbol)
    elif section == "bfsi":
        return api.get_bfsi_metrics(symbol)
    elif section == "subsidiary":
        return api.get_subsidiary_contribution(symbol)
    elif section == "insurance":
        return api.get_insurance_metrics(symbol)
    elif section == "metals":
        return api.get_metals_metrics(symbol)
    elif section == "realestate":
        return api.get_realestate_metrics(symbol)
    elif section == "telecom":
        return api.get_telecom_metrics(symbol)
    elif section == "power":
        return api.get_power_metrics(symbol)
    elif section == "sector_health":
        return api.get_sector_health_metrics(symbol)
    elif section == "risk_flags":
        return api.get_risk_flags(symbol)
    elif section == "forensic_checks":
        return api.get_forensic_checks(symbol)
    elif section == "improvement_metrics":
        return api.get_improvement_metrics(symbol)
    elif section == "capital_discipline":
        return api.get_capital_discipline(symbol)
    elif section == "incremental_roce":
        return api.get_incremental_roce(symbol)
    elif section == "altman_zscore":
        return api.get_altman_zscore(symbol)
    elif section == "working_capital":
        return api.get_working_capital_deterioration(symbol)
    elif section == "operating_leverage":
        return api.get_operating_leverage(symbol)
    elif section == "fcf_yield":
        return api.get_fcf_yield(symbol)
    elif section == "tax_rate_analysis":
        return api.get_tax_rate_analysis(symbol)
    elif section == "receivables_quality":
        return api.get_receivables_quality(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_quality_scores",
    "Accounting & quality metrics. section: 'earnings_quality' | 'piotroski' | 'beneish' | 'dupont' | 'common_size' | 'capex_cycle' | "
    "'forensic_checks' | 'improvement_metrics' | 'capital_discipline' | "
    "'incremental_roce' | 'altman_zscore' | 'working_capital' | 'operating_leverage' | 'fcf_yield' | 'tax_rate_analysis' | 'receivables_quality' | "
    "'bfsi' | 'insurance' | 'metals' | 'realestate' | 'telecom' | 'power' | 'sector_health' | 'subsidiary' | ['section1', 'section2']. "
    "BFSI routing: 'all' auto-skips non-applicable. "
    "'incremental_roce' = marginal return on new capital. 'altman_zscore' = EM distress predictor. 'working_capital' = CCC trend + channel stuffing flags. "
    "'operating_leverage' = DOL earnings sensitivity. 'fcf_yield' = FCF/EV vs risk-free. 'tax_rate_analysis' = ETR anomalies. 'receivables_quality' = revenue recognition risk.",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_quality_scores(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_quality_scores_section(api, symbol, s, args) for s in section}
        elif section == "all":
            is_bfsi = api._is_bfsi(symbol)
            skipped = {"skipped": "not applicable for BFSI"}
            if is_bfsi:
                data = {
                    "earnings_quality": skipped,
                    "piotroski": api.get_piotroski_score(symbol),
                    "beneish": skipped,
                    "dupont": api.get_dupont_decomposition(symbol),
                    "common_size": api.get_common_size_pl(symbol),
                    "capex_cycle": skipped,
                    "bfsi": api.get_bfsi_metrics(symbol),
                    "forensic_checks": skipped,
                    "improvement_metrics": api.get_improvement_metrics(symbol),
                    "capital_discipline": skipped,
                    "incremental_roce": skipped,
                    "altman_zscore": skipped,
                    "working_capital": skipped,
                    "operating_leverage": api.get_operating_leverage(symbol),
                    "fcf_yield": api.get_fcf_yield(symbol),
                    "tax_rate_analysis": api.get_tax_rate_analysis(symbol),
                    "receivables_quality": skipped,
                }
            else:
                data = {
                    "earnings_quality": api.get_earnings_quality(symbol),
                    "piotroski": api.get_piotroski_score(symbol),
                    "beneish": api.get_beneish_score(symbol),
                    "dupont": api.get_dupont_decomposition(symbol),
                    "common_size": api.get_common_size_pl(symbol),
                    "capex_cycle": api.get_capex_cycle(symbol),
                    "bfsi": {"skipped": "not applicable for non-BFSI"},
                    "forensic_checks": api.get_forensic_checks(symbol),
                    "improvement_metrics": api.get_improvement_metrics(symbol),
                    "capital_discipline": api.get_capital_discipline(symbol),
                    "incremental_roce": api.get_incremental_roce(symbol),
                    "altman_zscore": api.get_altman_zscore(symbol),
                    "working_capital": api.get_working_capital_deterioration(symbol),
                    "operating_leverage": api.get_operating_leverage(symbol),
                    "fcf_yield": api.get_fcf_yield(symbol),
                    "tax_rate_analysis": api.get_tax_rate_analysis(symbol),
                    "receivables_quality": api.get_receivables_quality(symbol),
                }
        else:
            data = _get_quality_scores_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_quality_scores", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_ownership_section(api, symbol, section, args):
    """Route a single section for get_ownership."""
    if section == "shareholding":
        return api.get_shareholding(symbol, args.get("quarters", 12))
    elif section == "changes":
        return api.get_shareholding_changes(symbol)
    elif section == "insider":
        return api.get_insider_transactions(symbol, args.get("days", 1825))
    elif section == "bulk_block":
        return api.get_bulk_block_deals(symbol)
    elif section == "mf_holdings":
        return api.get_mf_holdings(symbol)
    elif section == "mf_changes":
        return api.get_mf_holding_changes(symbol)
    elif section == "shareholder_detail":
        return api.get_shareholder_detail(symbol, args.get("classification"))
    elif section == "promoter_pledge":
        return api.get_promoter_pledge(symbol)
    elif section == "mf_conviction":
        return api.get_mf_conviction(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_ownership",
    "Ownership & stakeholder data. First call without section returns a compact TOC (~3-5KB) with current ownership snapshot, QoQ changes, top-10 holders brief, MF/pledge/insider/bulk-block summaries — enough to decide what to drill into. Then call with section='<name>' or section=['s1','s2'] to drill in. Sections: 'shareholding' | 'changes' | 'insider' | 'bulk_block' | 'mf_holdings' | 'mf_changes' | 'shareholder_detail' | 'promoter_pledge' | 'mf_conviction'. Heavy sections are capped (mf_holdings top 30 by value + tail summary; shareholder_detail top 20 holders) to stay under MCP tool-result transport limits. Avoid section='all' — payloads of 80-150K can get truncated. Optional: quarters (default 12), days (default 1825), classification (for shareholder_detail filter).",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_ownership(args):
    symbol = args["symbol"]
    # Default behavior when no section specified: return compact TOC.
    # This prevents the 80-150K-char payload truncation seen when agents
    # defaulted to fetching all sections at once (HDFCBANK hallucinated a
    # 5-quarter shareholding gap because the middle of a truncated response
    # is what the agent saw).
    section_raw = args.get("section")
    with ResearchDataAPI() as api:
        if not section_raw or section_raw in ("toc", "summary"):
            data = api.get_ownership_toc(symbol)
        else:
            section = _parse_section(section_raw)
            if isinstance(section, list):
                data = {s: _get_ownership_section(api, symbol, s, args) for s in section}
            elif section == "all":
                data = {
                    "_warning": (
                        "section='all' returns 80-150K chars and may be truncated by the "
                        "MCP transport. Prefer calling without section for a compact TOC "
                        "first, then drilling into specific sections."
                    ),
                    "shareholding": api.get_shareholding(symbol, args.get("quarters", 12)),
                    "changes": api.get_shareholding_changes(symbol),
                    "insider": api.get_insider_transactions(symbol, args.get("days", 1825)),
                    "bulk_block": api.get_bulk_block_deals(symbol),
                    "mf_holdings": api.get_mf_holdings(symbol),
                    "mf_changes": api.get_mf_holding_changes(symbol),
                    "shareholder_detail": api.get_shareholder_detail(symbol, args.get("classification")),
                    "promoter_pledge": api.get_promoter_pledge(symbol),
                    "mf_conviction": api.get_mf_conviction(symbol),
                }
            else:
                data = _get_ownership_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_ownership", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_valuation_section(api, symbol, section, args):
    """Route a single section for get_valuation."""
    if section == "snapshot":
        return api.get_valuation_snapshot(symbol)
    elif section == "band":
        return api.get_valuation_band(symbol, args.get("metric", "pe_trailing"), args.get("days", 2500))
    elif section == "pe_history":
        return api.get_pe_history(symbol, args.get("days", 2500))
    elif section == "key_metrics":
        return api.get_key_metrics_history(symbol, args.get("years", 10))
    elif section == "wacc":
        return api.get_wacc_params(symbol)
    elif section == "sotp":
        return api.get_listed_subsidiaries(symbol) or {"info": "No listed subsidiaries found for this company"}
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_valuation",
    "Valuation metrics & history. section: 'snapshot' | 'band' | 'pe_history' | 'key_metrics' | 'wacc' (WACC params: beta, cost of equity/debt, discount rate) | 'sotp' (listed subsidiaries for SOTP valuation) | ['section1', 'section2']. Optional: metric (for band, default 'pe_trailing'), days (default 2500), years (default 10).",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_valuation(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_valuation_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "snapshot": api.get_valuation_snapshot(symbol),
                "band": api.get_valuation_band(symbol, args.get("metric", "pe_trailing"), args.get("days", 2500)),
                "pe_history": api.get_pe_history(symbol, args.get("days", 2500)),
                "key_metrics": api.get_key_metrics_history(symbol, args.get("years", 10)),
            }
        else:
            data = _get_valuation_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_valuation", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_fair_value_analysis_section(api, symbol, section, args):
    """Route a single section for get_fair_value_analysis."""
    if section == "combined":
        return api.get_fair_value(symbol)
    elif section == "dcf":
        return api.get_dcf_valuation(symbol)
    elif section == "dcf_history":
        return api.get_dcf_history(symbol)
    elif section == "reverse_dcf":
        return api.get_reverse_dcf(symbol)
    elif section == "projections":
        return api.get_financial_projections(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_fair_value_analysis",
    "Fair value & DCF models. section: 'combined' | 'dcf' | 'dcf_history' | 'reverse_dcf' | 'projections' | ['section1', 'section2']",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_fair_value_analysis(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_fair_value_analysis_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "combined": api.get_fair_value(symbol),
                "dcf": api.get_dcf_valuation(symbol),
                "dcf_history": api.get_dcf_history(symbol),
                "reverse_dcf": api.get_reverse_dcf(symbol),
                "projections": api.get_financial_projections(symbol),
            }
        else:
            data = _get_fair_value_analysis_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_fair_value_analysis", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_peer_sector_section(api, symbol, section, args):
    """Route a single section for get_peer_sector."""
    if section == "peer_table":
        return api.get_peer_comparison(symbol)
    elif section == "peer_metrics":
        return api.get_peer_metrics(symbol)
    elif section == "peer_growth":
        return api.get_peer_growth(symbol)
    elif section == "valuation_matrix":
        return api.get_valuation_matrix(symbol)
    elif section == "benchmarks":
        return api.get_sector_benchmarks(symbol, args.get("metric"))
    elif section == "sector_overview":
        return api.get_sector_overview_metrics(symbol)
    elif section == "sector_flows":
        return api.get_sector_flows(symbol)
    elif section == "sector_valuations":
        return api.get_sector_valuations(symbol)
    elif section == "yahoo_peers":
        return api.get_yahoo_peer_comparison(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_peer_sector",
    "Peer comparison & sector data. First call with NO section (or section='toc') returns a compact ~1-2KB TOC listing the 9 sections + 3 recommended wave compositions. Then drill with section=['<wave sections>'] or section='<single>'. Valid sections: 'peer_table' | 'peer_metrics' | 'peer_growth' | 'valuation_matrix' | 'benchmarks' | 'sector_overview' | 'sector_flows' | 'sector_valuations' | 'yahoo_peers'. Do NOT call section='all' — the ~50KB payload across 9 sections may truncate. Optional: metric (for specific valuation metric).",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_peer_sector(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    with ResearchDataAPI() as api:
        # Default behavior when no section specified: return compact TOC.
        # Same TOC-then-drill pattern as get_fundamentals / get_ownership.
        if not section_raw or section_raw in ("toc", "summary"):
            data = api.get_peer_sector_toc(symbol)
            if isinstance(data, dict) and "error" not in data:
                data = _add_freshness_meta(data, api, symbol)
            return _with_dedup("get_peer_sector", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)

        section = _parse_section(section_raw)
        if isinstance(section, list):
            data = {s: _get_peer_sector_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "_warning": (
                    "section='all' returns ~50 KB across 9 sections and may be truncated by the "
                    "MCP transport. Prefer calling get_peer_sector with no section to see the TOC "
                    "with recommended wave compositions."
                ),
                "peer_table": api.get_peer_comparison(symbol),
                "peer_metrics": api.get_peer_metrics(symbol),
                "peer_growth": api.get_peer_growth(symbol),
                "valuation_matrix": api.get_valuation_matrix(symbol),
                "benchmarks": api.get_sector_benchmarks(symbol, args.get("metric")),
                "sector_overview": api.get_sector_overview_metrics(symbol),
                "sector_flows": api.get_sector_flows(symbol),
                "sector_valuations": api.get_sector_valuations(symbol),
            }
        else:
            data = _get_peer_sector_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_peer_sector", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_estimates_section(api, symbol, section, args):
    """Route a single section for get_estimates."""
    if section == "consensus":
        return api.get_consensus_estimate(symbol)
    elif section == "surprises":
        return api.get_earnings_surprises(symbol)
    elif section == "revisions":
        return api.get_estimate_revisions(symbol)
    elif section == "momentum":
        return api.get_estimate_momentum(symbol)
    elif section == "revenue":
        return api.get_revenue_estimates(symbol)
    elif section == "growth":
        return api.get_growth_estimates(symbol)
    elif section == "analyst_grades":
        return api.get_analyst_grades(symbol)
    elif section == "price_targets":
        return api.get_price_targets(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_estimates",
    "Analyst estimates & targets. section: 'consensus' | 'surprises' | 'revisions' | 'momentum' | 'revenue' | 'growth' | 'analyst_grades' | 'price_targets' | ['section1', 'section2']",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_estimates(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_estimates_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "consensus": api.get_consensus_estimate(symbol),
                "surprises": api.get_earnings_surprises(symbol),
                "revisions": api.get_estimate_revisions(symbol),
                "momentum": api.get_estimate_momentum(symbol),
                "revenue": api.get_revenue_estimates(symbol),
                "growth": api.get_growth_estimates(symbol),
                "analyst_grades": api.get_analyst_grades(symbol),
                "price_targets": api.get_price_targets(symbol),
            }
        else:
            data = _get_estimates_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_estimates", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_market_context_section(api, symbol, section, args):
    """Route a single section for get_market_context."""
    if section == "delivery":
        return api.get_delivery_trend(symbol, args.get("days", 30))
    elif section == "macro":
        return api.get_macro_snapshot()
    elif section == "fii_dii_streak":
        return api.get_fii_dii_streak()
    elif section == "fii_dii_flows":
        return api.get_fii_dii_flows(args.get("days", 30))
    elif section == "technicals":
        return api.get_technical_indicators(symbol)
    elif section == "price_performance":
        return api.get_price_performance(symbol)
    elif section == "delivery_analysis":
        return api.get_delivery_analysis(symbol, args.get("days", 90))
    elif section == "commodities":
        return api.get_commodity_snapshot()
    elif section == "institutional_consensus":
        return api.get_institutional_consensus(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_market_context",
    "Market signals & macro. section: 'delivery' | 'macro' | 'fii_dii_streak' | 'fii_dii_flows' | 'technicals' | 'price_performance' | 'delivery_analysis' | 'commodities' | 'institutional_consensus' | ['section1', 'section2']. Optional: days (default 90).",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_market_context(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_market_context_section(api, symbol, s, args) for s in section}
        elif section == "all":
            # Compute ADTV (avg daily traded value in ₹ Cr) from bhavcopy turnover
            stock_data = api._store.get_stock_delivery(symbol, days=30)
            turnovers = [r.turnover for r in stock_data if r.turnover and r.turnover > 0]
            adtv_cr = round(sum(turnovers) / len(turnovers) / 1e7, 1) if turnovers else None  # turnover is in ₹, convert to Cr

            data = {
                "delivery": api.get_delivery_trend(symbol, args.get("days", 30)),
                "adtv_cr": adtv_cr,
                "adtv_signal": (
                    "severe_liquidity_risk" if adtv_cr is not None and adtv_cr < 5
                    else "moderate_liquidity_risk" if adtv_cr is not None and adtv_cr < 20
                    else "adequate" if adtv_cr is not None
                    else None
                ),
                "macro": api.get_macro_snapshot(),
                "fii_dii_streak": api.get_fii_dii_streak(),
                "fii_dii_flows": api.get_fii_dii_flows(args.get("days", 30)),
                "technicals": api.get_technical_indicators(symbol),
                "price_performance": api.get_price_performance(symbol),
                "delivery_analysis": api.get_delivery_analysis(symbol, args.get("days", 90)),
                "commodities": api.get_commodity_snapshot(),
                "institutional_consensus": api.get_institutional_consensus(symbol),
            }
        else:
            data = _get_market_context_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_market_context", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_company_context_section(api, symbol, section, args):
    """Route a single section for get_company_context."""
    if section == "info":
        return api.get_company_info(symbol)
    elif section == "profile":
        return api.get_company_profile(symbol)
    elif section == "documents":
        return api.get_company_documents(symbol, args.get("doc_type"))
    elif section == "business_profile":
        from pathlib import Path
        path = Path.home() / "vault" / "stocks" / symbol.upper() / "profile.md"
        return path.read_text() if path.exists() else ""
    elif section == "concall_insights":
        return api.get_concall_insights(
            symbol,
            section_filter=args.get("sub_section"),
            quarter=args.get("quarter"),
            qa_topics=args.get("qa_topics"),
        )
    elif section == "deck_insights":
        return api.get_deck_insights(
            symbol,
            section_filter=args.get("sub_section"),
            quarter=args.get("quarter"),
            slide_topics=args.get("slide_topics"),
        )
    elif section == "annual_report":
        return api.get_annual_report(
            symbol,
            year=args.get("year"),
            section=args.get("sub_section"),
        )
    elif section == "sector_kpis":
        return api.get_sector_kpis(symbol, kpi_key=args.get("sub_section"))
    elif section == "filings":
        return api.get_recent_filings(symbol, args.get("limit", 10))
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_company_context",
    "Company info, profile & documents. section: 'info' | 'profile' | 'documents' | 'business_profile' | 'concall_insights' | 'deck_insights' | 'annual_report' | 'sector_kpis' | 'filings' | ['section1', 'section2']. Optional sub_section (for concall_insights: 'operational_metrics' | 'financial_metrics' | 'management_commentary' | 'subsidiaries' | 'qa_session' | 'flags' | 'opening_remarks'; for deck_insights: 'highlights' | 'segment_performance' | 'strategic_priorities' | 'outlook_and_guidance' | 'new_initiatives' | 'charts_described'; for annual_report: 'chairman_letter' | 'mdna' | 'risk_management' | 'auditor_report' | 'corporate_governance' | 'brsr' | 'related_party' | 'segmental' | 'notes_to_financials' | 'financial_statements' — optional 'year' param to narrow to one FY like FY25; for sector_kpis: a specific canonical KPI key like 'gross_npa_pct' — call without sub_section first to see available keys). First call returns a compact table of contents; drill in with sub_section.",
    {"symbol": str, "section": str, "doc_type": str, "limit": int, "sub_section": str, "year": str},
    annotations=READ_ONLY,
)
async def get_company_context(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_company_context_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "info": api.get_company_info(symbol),
                "profile": api.get_company_profile(symbol),
                "documents": api.get_company_documents(symbol, args.get("doc_type")),
                "business_profile": _get_company_context_section(api, symbol, "business_profile", args),
                "concall_insights": api.get_concall_insights(
                    symbol,
                    section_filter=args.get("sub_section"),
                    quarter=args.get("quarter"),
                    qa_topics=args.get("qa_topics"),
                ),
                "deck_insights": api.get_deck_insights(
                    symbol,
                    section_filter=args.get("sub_section"),
                    quarter=args.get("quarter"),
                    slide_topics=args.get("slide_topics"),
                ),
                "annual_report": api.get_annual_report(
                    symbol,
                    year=args.get("year"),
                    section=args.get("sub_section"),
                ),
                "sector_kpis": api.get_sector_kpis(symbol, kpi_key=args.get("sub_section")),
                "filings": api.get_recent_filings(symbol, args.get("limit", 10)),
            }
        else:
            data = _get_company_context_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_company_context", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_events_actions_section(api, symbol, section, args):
    """Route a single section for get_events_actions."""
    if section == "events":
        return api.get_events_calendar(symbol)
    elif section == "dividends":
        return api.get_dividend_history(symbol, args.get("years", 10))
    elif section == "corporate_actions":
        return api.get_corporate_actions(symbol)
    elif section == "adjusted_eps":
        return api.get_adjusted_eps(symbol, args.get("quarters", 12))
    elif section == "catalysts":
        return api.get_upcoming_catalysts(symbol, args.get("days", 90))
    elif section == "material_events":
        return api.get_material_events(symbol, args.get("days", 365))
    elif section == "dividend_policy":
        return api.get_dividend_policy(symbol)
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_events_actions",
    "Events, dividends & corporate actions. section: 'events' | 'dividends' | 'corporate_actions' | 'adjusted_eps' | 'catalysts' | 'material_events' | 'dividend_policy' | ['section1', 'section2']. Optional: years (default 10), quarters (default 12), days (default 90).",
    {"symbol": str, "section": str},
    annotations=READ_ONLY,
)
async def get_events_actions(args):
    symbol = args["symbol"]
    section = _parse_section(args.get("section", "all"))
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_events_actions_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "events": api.get_events_calendar(symbol),
                "dividends": api.get_dividend_history(symbol, args.get("years", 10)),
                "corporate_actions": api.get_corporate_actions(symbol),
                "adjusted_eps": api.get_adjusted_eps(symbol, args.get("quarters", 12)),
                "catalysts": api.get_upcoming_catalysts(symbol, args.get("days", 90)),
                "material_events": api.get_material_events(symbol, args.get("days", 365)),
                "dividend_policy": api.get_dividend_policy(symbol),
            }
        else:
            data = _get_events_actions_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return _with_dedup("get_events_actions", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- News ---


@tool(
    "get_stock_news",
    "Get recent news articles for a stock from Google News RSS + yfinance. "
    "Returns up to 100 articles from the last N days (default 90). "
    "Pre-filtered to remove market commentary — focuses on business events, "
    "catalysts, regulatory actions, M&A, management changes. "
    "Each article has: title, source, date, url, summary.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_stock_news(args):
    with ResearchDataAPI() as api:
        data = api.get_stock_news(args["symbol"], args.get("days", 90))
    return _with_dedup("get_stock_news", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Financial Calculator ---


@tool(
    "calculate",
    "Financial calculator — use for ALL math, never compute in your head. Returns numeric result + plain calculation string for citation. Output is pure numeric — no currency symbols, no unit labels. Field name indicates unit (e.g. value_cr means crores, pe is PE ratio, growth_pct is percent). Wrap numbers in your own prose units in the report.\n"
    "Arguments a and b are strings; pass numeric values as numeric strings (e.g. '1063.55', '892459574').\n"
    "\nNAMED OPERATIONS (preferred — enforce Indian unit conversion) — pass operation + a + b:\n"
    "  'shares_to_value_cr'     a=shares (raw count), b=price -> value_cr (in crores)\n"
    "  'per_share_to_total_cr'  a=per_share_value, b=shares (raw count) -> total_cr\n"
    "  'total_cr_to_per_share'  a=total_cr, b=shares (raw count) -> per_share\n"
    "  'pe_from_price_eps'      a=price, b=eps -> pe (ratio)\n"
    "  'eps_from_pat_shares'    a=pat_cr, b=shares (raw count) -> eps\n"
    "  'fair_value'             a=pe_multiple, b=eps -> fair_value (per share)\n"
    "  'growth_rate'            a=old, b=new -> growth_pct (percent; single-period)\n"
    "  'cagr'                   a=start, b=end, years=<N> -> cagr_pct (compound annual growth rate; use 'years' kwarg OR pass years as third positional via inputs_as_of='years:5')\n"
    "  'mcap_cr'                a=price, b=shares (raw count) -> mcap_cr (in crores)\n"
    "  'margin_of_safety'       a=fair_value, b=current_price -> mos_pct (percent)\n"
    "  'annualize_quarterly'    a=quarterly_value -> annualized (x4); leave b='0'\n"
    "  'pct_of'                 a=part, b=whole -> pct (percent)\n"
    "  'ratio'                  a=numerator, b=denominator -> ratio\n"
    "\nEXPRESSION FALLBACK — for arbitrary arithmetic use operation='expr':\n"
    "  'expr'                   a='<arithmetic string>' (e.g. '(74 - 47.67) / 2'), b='0' (ignored)\n"
    "  Only numbers and + - * / ( ) are permitted in the expression.\n"
    "\nPrefer named operations over 'expr' when a matching op exists — named ops carry unit-aware field names (value_cr, mcap_cr, pct) that are self-documenting.\n"
    "\nTIMESTAMP DISCIPLINE (for historical flow-value math) — pass optional inputs_as_of and mcap_as_of:\n"
    "  When multiplying a historical %pt change by a market cap to derive a flow value, pass inputs_as_of (ISO quarter or date of the %pt context, e.g. '2023-Q4') AND mcap_as_of (ISO quarter or date of the mcap context, e.g. '2026-Q1'). If they differ, the tool returns a HISTORICAL_MCAP_MISMATCH warning that you MUST echo verbatim in prose before citing the flow-value figure — because current mcap x historical %pt can be off by 20-50%.\n"
    "  Omit both args (back-compat) for current-period math. See Tenet 16.",
    # Schema: a/b declared as str to allow the 'expr' operation to pass an expression
    # string without MCP validation rejecting it. Numeric ops parse a/b via float().
    # Previously schema was {a: float, b: float} which caused MCP to reject
    # calculate(operation='expr', a='74 - 47.67') on BHARTIARTL ownership run.
    # inputs_as_of / mcap_as_of are optional timestamp strings for historical-flow
    # discipline; see Tenet 16 (OWNERSHIP_SYSTEM_V2).
    # years: optional kwarg for cagr operation.
    {"operation": str, "a": str, "b": str, "inputs_as_of": str, "mcap_as_of": str, "years": str},
    annotations=READ_ONLY,
)
async def calculate(args):
    import math
    op = args["operation"]
    raw_a = args.get("a")
    raw_b = args.get("b")

    # For named numeric ops, require parseable numeric strings and surface a
    # helpful error if the agent accidentally passed an expression string
    # (e.g. a='74-47') — otherwise the op would compute silently on 0.0.
    # For 'expr', a is an expression string and b is ignored.
    def _parse_numeric(v, default=0.0):
        """Returns (value, error). error is None on success."""
        if v is None or v == "":
            return default, None
        try:
            return float(v), None
        except (TypeError, ValueError):
            return default, f"'{v}' is not a valid numeric string"

    if op == "expr":
        # 'expr' path: a is an expression string; b is ignored (default '0').
        a = 0.0
        b = 0.0
    else:
        a, err_a = _parse_numeric(raw_a)
        b, err_b = _parse_numeric(raw_b)
        # annualize_quarterly only needs 'a' — b is optional
        if op == "annualize_quarterly":
            err_b = None
        if err_a or err_b:
            hint = (
                f"Argument parse error for operation='{op}': "
                f"{err_a or ''}{' ; ' if err_a and err_b else ''}{err_b or ''}. "
                f"Named ops need numeric strings (e.g. a='1063.55', b='892459574'). "
                f"If you need arithmetic like '74 - 47.67', use operation='expr' with the expression as `a` and b='0'."
            )
            return _with_dedup(
                "calculate",
                {"content": [{"type": "text", "text": json.dumps({"error": hint}, default=str)}]},
                args,
            )

    try:
        if op == "shares_to_value_cr":
            result = {"value_cr": round(a * b / 1e7, 2),
                      "calculation": f"{a} * {b} / 10000000 = {a * b / 1e7:.2f}"}
        elif op == "per_share_to_total_cr":
            result = {"total_cr": round(a * b / 1e7, 2),
                      "calculation": f"{a} * {b} / 10000000 = {a * b / 1e7:.2f}"}
        elif op == "total_cr_to_per_share":
            result = {"per_share": round(a * 1e7 / b, 2) if b else 0,
                      "calculation": f"{a} * 10000000 / {b} = {a * 1e7 / b:.2f}" if b else "division by zero"}
        elif op == "pe_from_price_eps":
            result = {"pe": round(a / b, 2) if b else 0,
                      "calculation": f"{a} / {b} = {a / b:.2f}" if b else "division by zero"}
        elif op == "eps_from_pat_shares":
            result = {"eps": round(a * 1e7 / b, 2) if b else 0,
                      "calculation": f"{a} * 10000000 / {b} = {a * 1e7 / b:.2f}" if b else "division by zero"}
        elif op == "fair_value":
            result = {"fair_value": round(a * b, 2),
                      "calculation": f"{a} * {b} = {a * b:.2f}"}
        elif op == "growth_rate":
            result = {"growth_pct": round((b - a) / a * 100, 2) if a else 0,
                      "calculation": f"({b} - {a}) / {a} * 100 = {(b - a) / a * 100:.2f}" if a else "division by zero"}
        elif op == "cagr":
            # a = start, b = end, years = number of periods
            years_str = args.get("years") or ""
            # Allow 'years:N' fallback via inputs_as_of if kwarg missing
            if not years_str and args.get("inputs_as_of", "").startswith("years:"):
                years_str = args["inputs_as_of"].split(":", 1)[1]
            try:
                years = float(years_str) if years_str else 0.0
            except (TypeError, ValueError):
                years = 0.0
            if a and years and b:
                cagr_pct = ((b / a) ** (1 / years) - 1) * 100
                result = {"cagr_pct": round(cagr_pct, 2),
                          "calculation": f"({b} / {a}) ** (1 / {years}) - 1 = {cagr_pct / 100:.4f} = {cagr_pct:.2f}%"}
            else:
                result = {"note": f"cagr requires a (start), b (end), and years (>0). Got a={a} b={b} years={years}. Pass years via the 'years' kwarg or via inputs_as_of='years:N'."}
        elif op == "mcap_cr":
            result = {"mcap_cr": round(a * b / 1e7, 2),
                      "calculation": f"{a} * {b} / 10000000 = {a * b / 1e7:.2f}"}
        elif op == "margin_of_safety":
            result = {"mos_pct": round((a - b) / a * 100, 2) if a else 0,
                      "calculation": f"({a} - {b}) / {a} * 100 = {(a - b) / a * 100:.2f}" if a else "division by zero"}
        elif op == "annualize_quarterly":
            result = {"annualized": round(a * 4, 2),
                      "calculation": f"{a} * 4 = {a * 4:.2f}"}
        elif op == "pct_of":
            result = {"pct": round(a / b * 100, 2) if b else 0,
                      "calculation": f"{a} / {b} * 100 = {a / b * 100:.2f}" if b else "division by zero"}
        elif op == "ratio":
            result = {"ratio": round(a / b, 4) if b else 0,
                      "calculation": f"{a} / {b} = {a / b:.4f}" if b else "division by zero"}
        elif op == "expr":
            # Safe arithmetic eval — only allow numbers and basic operators.
            # raw_a is the original string from the agent (e.g. '74 - 47.67').
            expr_str = str(raw_a if raw_a is not None else "0")
            allowed = set("0123456789.+-*/() eE")
            if all(c in allowed for c in expr_str):
                val = eval(expr_str)  # noqa: S307
                result = {"result": round(float(val), 4), "expression": expr_str}
            else:
                result = {
                    "error": "Only arithmetic expressions allowed (numbers, +, -, *, /, parentheses). "
                             f"Received: a='{expr_str}'"
                }
        else:
            result = {"error": f"Unknown operation: {op}. See tool description for available operations."}
    except Exception as e:
        result = {"error": str(e)}

    # Timestamp discipline for historical flow-value math (Tenet 16).
    # If the agent passed both inputs_as_of and mcap_as_of and they differ,
    # attach a HISTORICAL_MCAP_MISMATCH warning to the result. The agent must
    # echo this string verbatim in prose before citing the flow-value figure.
    inputs_as_of = args.get("inputs_as_of") or None
    mcap_as_of = args.get("mcap_as_of") or None
    if (
        isinstance(result, dict)
        and "error" not in result
        and inputs_as_of and mcap_as_of and inputs_as_of != mcap_as_of
    ):
        result["timestamp_discipline"] = (
            f"HISTORICAL_MCAP_MISMATCH: inputs from {inputs_as_of} combined with mcap from {mcap_as_of}. "
            f"Result is at {mcap_as_of} mcap — actual historical flow value may differ 20-50%. "
            f"Either pass mcap_as_of matching inputs_as_of, or report the change in pp only. "
            f"You must echo this caveat verbatim in prose before citing the flow-value figure."
        )

    return _with_dedup("calculate", {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}, args)


# --- Tool Registry ---

# V2 macro-tools (10 consolidated) + 6 standalone = 16 agent-facing tools
RESEARCH_TOOLS_V2 = [
    get_fundamentals, get_quality_scores, get_ownership, get_valuation,
    get_fair_value_analysis, get_peer_sector, get_estimates,
    get_market_context, get_company_context, get_events_actions,
    get_analytical_profile, render_chart, get_composite_score,
    screen_stocks, save_business_profile, get_chart_data, calculate,
    get_annual_report, get_deck_insights,
]

# Individual tools kept for CLI `flowtrack research data <tool_name>` and monolith agent
RESEARCH_TOOLS = [
    get_quarterly_results,
    get_annual_financials,
    get_efficiency_ratios,
    get_quarterly_balance_sheet,
    get_quarterly_cash_flow,
    get_valuation_snapshot,
    get_valuation_band,
    get_pe_history,
    get_shareholding,
    get_shareholding_changes,
    get_insider_transactions,
    get_bulk_block_deals,
    get_mf_holdings,
    get_mf_holding_changes,
    get_delivery_trend,
    get_promoter_pledge,
    get_consensus_estimate,
    get_earnings_surprises,
    get_estimate_momentum,
    get_macro_snapshot,
    get_fii_dii_streak,
    get_fii_dii_flows,
    get_chart_data,
    get_peer_comparison,
    get_shareholder_detail,
    get_expense_breakdown,
    get_recent_filings,
    get_company_info,
    get_composite_score,
    get_company_profile,
    get_company_documents,
    get_business_profile,
    save_business_profile,
    get_dcf_valuation,
    get_dcf_history,
    get_technical_indicators,
    get_dupont_decomposition,
    get_key_metrics_history,
    get_financial_growth_rates,
    get_analyst_grades,
    get_price_targets,
    get_fair_value,
    get_valuation_matrix,
    get_corporate_actions,
    get_adjusted_eps,
    get_financial_projections,
    get_piotroski_score,
    get_reverse_dcf, get_capex_cycle, get_common_size_pl,
    get_revenue_estimates, get_growth_estimates, get_price_performance,
    get_sector_kpis,
    get_analytical_profile, screen_stocks,
    get_wacc_params,
    get_yahoo_peers,
]

# V1 agent registries (BUSINESS_TOOLS, *_AGENT_TOOLS, _PEER_TOOLS) removed — see *_AGENT_TOOLS_V2 below

# --- V2 Agent Tool Registries (macro-tools) ---

BUSINESS_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context, get_fundamentals,
    get_peer_sector, get_events_actions, get_yahoo_peers,
    get_valuation, get_chart_data, save_business_profile, render_chart, calculate,
    get_annual_report, get_deck_insights,
]

FINANCIAL_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context, get_fundamentals,
    get_quality_scores, get_valuation, get_peer_sector,
    get_estimates, get_events_actions, get_fair_value_analysis,
    get_chart_data, render_chart, calculate,
    get_annual_report, get_deck_insights,
]

OWNERSHIP_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_ownership, get_market_context,
    get_peer_sector, get_company_context, get_estimates,
    get_fundamentals, render_chart, calculate,
    get_annual_report,
]

VALUATION_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_valuation, get_fair_value_analysis,
    get_estimates, get_peer_sector, get_events_actions, get_yahoo_peers,
    get_company_context, get_quality_scores, get_market_context,
    get_chart_data, render_chart, calculate,
    get_annual_report, get_deck_insights,
]

RISK_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_composite_score, get_fundamentals,
    get_quality_scores, get_ownership, get_market_context,
    get_peer_sector, get_company_context, get_events_actions,
    get_estimates, render_chart, calculate,
    get_annual_report,
]

TECHNICAL_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_market_context, get_valuation,
    get_ownership, get_peer_sector, get_chart_data, render_chart, calculate,
]

SECTOR_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context, get_peer_sector,
    get_market_context, get_fundamentals, get_estimates, get_yahoo_peers,
    get_valuation, get_chart_data, render_chart, calculate,
]

NEWS_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context,
    get_stock_news, get_events_actions,
]
