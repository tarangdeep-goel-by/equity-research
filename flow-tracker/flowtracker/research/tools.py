"""MCP tool definitions wrapping ResearchDataAPI for the research agent."""

from __future__ import annotations

import difflib
import json
from typing import Any, Literal

from claude_agent_sdk import tool
from mcp.types import ToolAnnotations

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.research.macro_anchors import get_anchor_content, list_current_anchors

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


def _wrap_handler_is_error(tool):
    """Set `is_error` on the result envelope when the payload classifies as an error.

    The agent harness reads `is_error` off the tool-result block, but no tool
    handler sets it today, so failures are invisible. This wrapper decodes the
    envelope's JSON text payload, reuses `classify_completeness`, and flags the
    envelope when the payload is an error dict.

    Rides on the envelope dict only — never touches `content[0]["text"]`, so the
    dedup hash (`_with_dedup`) is preserved. Idempotent: wraps each unique tool's
    handler exactly once via a sentinel attribute.
    """
    orig = tool.handler
    if getattr(orig, "_is_error_wrapped", False):
        return tool

    async def wrapped(args):
        result = await orig(args)
        try:
            if isinstance(result, dict) and "is_error" not in result:
                text = result.get("content", [{}])[0].get("text", "")
                payload = json.loads(text)
                comp, _ = classify_completeness(payload)
                if comp == "error":
                    result["is_error"] = True
        except Exception:
            pass  # non-JSON text (dedup stub, bare strings) → leave unflagged
        return result

    wrapped._is_error_wrapped = True
    tool.handler = wrapped
    return tool


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


def _invalid_enum_error(tool_name: str, param: str, value, valid, args: dict) -> dict:
    """Return a 'did-you-mean' error envelope for an out-of-vocab enum value.

    The Phase 0 wrapper (`_wrap_handler_is_error`) decodes the payload and flags
    `is_error=True` because the payload carries a truthy `"error"` key — so this
    helper only has to RETURN the error dict in the normal envelope shape.
    `valid` may be any iterable of strings (frozenset/tuple/list).
    """
    valid_list = list(valid)
    sugg = difflib.get_close_matches(str(value), valid_list, n=3, cutoff=0.3)
    err = {
        "error": f"Invalid {param} '{value}' for {tool_name}.",
        "valid_values": sorted(valid_list),
        "suggestion": (
            f"Did you mean {sugg}?" if sugg
            else f"Call {tool_name} with no {param} to see the TOC."
        ),
    }
    # Phase 3b: error envelopes carry a `_meta` sidecar (status="error") too.
    # Exception-safe — never break the error path for metadata.
    try:
        from datetime import date
        err["_meta"] = {
            "as_of_date": str(date.today()),
            "status": "error",
            "count": None,
            "data_freshness": None,
        }
    except Exception:
        pass
    return _with_dedup(
        tool_name,
        {"content": [{"type": "text", "text": json.dumps(err, default=str)}]},
        args,
    )


# ---------------------------------------------------------------------------
# US-market safety (P3.6 consumption wiring)
#
# India-only data concepts (FII/DII flows, promoter pledge, MF scheme holdings,
# F&O positioning, delivery %) have no US equivalent. The underlying
# ResearchDataAPI methods already return empty for US symbols (via `_is_us`),
# but an empty India payload is misleading for a US ticker — it reads as "no
# data found" rather than "this concept does not apply to this market". These
# helpers let the India-only tools emit an EXPLICIT not-applicable envelope so
# the agent knows to skip the concept rather than infer a data gap.
# ---------------------------------------------------------------------------


def _market_of(symbol: str) -> str:
    """Resolve a symbol's market via a short-lived ResearchDataAPI (shares the
    routed `_market_of` resolver — NASDAQ/NYSE for US listings, else NSE)."""
    with ResearchDataAPI() as api:
        return api._market_of(symbol)


def _is_us_symbol(symbol: str) -> bool:
    """True when the symbol resolves to a US listing (NASDAQ / NYSE)."""
    return _market_of(symbol) in ("NASDAQ", "NYSE")


def _us_not_applicable(tool_name: str, concept: str, symbol: str, args: dict) -> dict:
    """Explicit 'not applicable for US market' envelope for India-only concepts.

    Returns a clean payload (status='not_applicable') rather than a misleading
    empty India result or an error. Classifies as 'empty' (not 'error') so the
    is-error wrapper leaves it unflagged — it is a clean terminal answer, not a
    failure.
    """
    from datetime import date
    payload = {
        "status": "not_applicable",
        "market": _market_of(symbol),
        "symbol": symbol,
        "reason": (
            f"{concept} is an India-market concept with no US equivalent; "
            f"not applicable for US-listed {symbol}."
        ),
        "_meta": {
            "as_of_date": str(date.today()),
            "status": "not_applicable",
            "count": 0,
            "data_freshness": None,
        },
    }
    return _with_dedup(
        tool_name,
        {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]},
        args,
    )


# India-only ownership sections — degrade to not-applicable for US symbols.
_OWNERSHIP_INDIA_ONLY = frozenset({
    "mf_holdings", "mf_changes", "mf_conviction", "promoter_pledge",
    "shareholder_detail", "public_breakdown", "esop", "adr_gdr", "bulk_block",
})
# India-only market-context sections — degrade to not-applicable for US symbols.
_MARKET_CONTEXT_INDIA_ONLY = frozenset({
    "delivery", "delivery_analysis", "fii_dii_streak", "fii_dii_flows",
})


# ---------------------------------------------------------------------------
# Section vocabularies — single source of truth shared by the @tool schema enum
# and the handler-side validation guard (`_validate_sections`). Each tuple lists
# the routable sections; the trailing sentinels (toc/summary/all) are added
# per-tool to match exactly what that handler special-cases. Derived from the
# routing functions (`_get_<name>_section`) below — the handler is ground truth.
# Defined here (before any tool) so the schema dicts can reference them at
# module-import time.
# ---------------------------------------------------------------------------
_FUNDAMENTALS_SECTIONS = (
    "quarterly_results", "annual_financials", "ratios", "quarterly_balance_sheet",
    "quarterly_cash_flow", "expense_breakdown", "growth_rates", "capital_allocation",
    "rate_sensitivity", "cagr_table", "cost_structure", "balance_sheet_detail",
    "cash_flow_quality", "working_capital",
)
_FUNDAMENTALS_SENTINELS = ("toc", "summary", "all")

_QUALITY_SCORES_SECTIONS = (
    "earnings_quality", "piotroski", "beneish", "dupont", "common_size", "capex_cycle",
    "bfsi", "subsidiary", "insurance", "metals", "realestate", "telecom", "power",
    "sector_health", "risk_flags", "forensic_checks", "improvement_metrics",
    "capital_discipline", "incremental_roce", "altman_zscore", "working_capital",
    "operating_leverage", "fcf_yield", "tax_rate_analysis", "receivables_quality",
)
_QUALITY_SCORES_SENTINELS = ("all",)

_OWNERSHIP_SECTIONS = (
    "shareholding", "changes", "insider", "bulk_block", "mf_holdings", "mf_changes",
    "shareholder_detail", "promoter_pledge", "mf_conviction", "adr_gdr",
    "public_breakdown", "esop",
)
_OWNERSHIP_SENTINELS = ("toc", "summary", "all")

_VALUATION_SECTIONS = ("snapshot", "band", "pe_history", "key_metrics", "wacc", "sotp")
_VALUATION_SENTINELS = ("all",)

_FAIR_VALUE_SECTIONS = ("combined", "dcf", "dcf_history", "reverse_dcf", "projections")
_FAIR_VALUE_SENTINELS = ("all",)

_PEER_SECTOR_SECTIONS = (
    "peer_table", "peer_metrics", "peer_growth", "valuation_matrix", "benchmarks",
    "sector_overview", "sector_flows", "sector_valuations", "yahoo_peers",
    "sector_index_valuation", "sector_performance",
)
_PEER_SECTOR_SENTINELS = ("toc", "summary", "all")

_ESTIMATES_SECTIONS = (
    "consensus", "surprises", "revisions", "momentum", "revenue", "growth",
    "analyst_grades", "price_targets",
)
_ESTIMATES_SENTINELS = ("all",)

_MARKET_CONTEXT_SECTIONS = (
    "delivery", "macro", "fii_dii_streak", "fii_dii_flows", "technicals",
    "price_performance", "delivery_analysis", "commodities", "institutional_consensus",
)
_MARKET_CONTEXT_SENTINELS = ("all",)

_COMPANY_CONTEXT_SECTIONS = (
    "info", "profile", "documents", "business_profile", "concall_insights",
    "deck_insights", "annual_report", "sector_kpis", "filings",
)
_COMPANY_CONTEXT_SENTINELS = ("all",)

# Nested sub_section vocabularies for get_company_context (validated conditionally
# on the parent section). sector_kpis sub_section is free-text (canonical KPI key)
# and is intentionally NOT enumerated/validated.
_CONCALL_SUB_SECTIONS = (
    "operational_metrics", "financial_metrics", "management_commentary", "subsidiaries",
    "qa_session", "flags", "opening_remarks", "comparable_growth_metrics",
)
_DECK_SUB_SECTIONS = (
    "highlights", "segment_performance", "strategic_priorities", "outlook_and_guidance",
    "new_initiatives", "charts_described",
)
_ANNUAL_REPORT_SUB_SECTIONS = (
    "chairman_letter", "mdna", "risk_management", "auditor_report",
    "corporate_governance", "brsr", "related_party", "segmental",
    "notes_to_financials", "financial_statements",
)
_COMPANY_CONTEXT_SUB_SECTION_VOCAB = {
    "concall_insights": _CONCALL_SUB_SECTIONS,
    "deck_insights": _DECK_SUB_SECTIONS,
    "annual_report": _ANNUAL_REPORT_SUB_SECTIONS,
}

_EVENTS_ACTIONS_SECTIONS = (
    "events", "dividends", "corporate_actions", "adjusted_eps", "catalysts",
    "material_events", "dividend_policy",
)
_EVENTS_ACTIONS_SENTINELS = ("all",)

# Standalone get_annual_report — same AR sections as the nested vocab. NO 'toc'
# sentinel (the handler treats a missing section as the TOC; 'toc' is a notorious
# wrong guess and must be rejected with a did-you-mean).
_ANNUAL_REPORT_SECTIONS = _ANNUAL_REPORT_SUB_SECTIONS

# get_macro_anchor doc_type enum. `section` stays free-text (fuzzy heading match).
_MACRO_ANCHOR_DOC_TYPES = (
    "economic_survey", "budget_speech", "budget_at_a_glance", "rbi_mpr",
    "rbi_mpc_statement", "rbi_ar_assessment", "rbi_ar_economic", "rbi_ar_monetary",
    "irdai_annual_report",
)

# ---------------------------------------------------------------------------
# Phase 1-B: standalone vocab tools — same single-source-of-truth pattern as the
# section dispatchers above. Each tuple is the EXACT vocab the handler accepts
# (derived from the handler / charts.py / data_api / store — the handler is
# ground truth), referenced by BOTH the @tool schema enum and the handler guard.
# ---------------------------------------------------------------------------

# render_chart: PNG renderer. Exact set = charts._AVAILABLE_CHARTS (25 types).
# NOTE: distinct from _CHART_DATA_TYPES below (rendered PNG vs raw Screener series).
_RENDER_CHART_TYPES = (
    "price", "pe", "delivery", "revenue_profit", "shareholding",
    "quarterly", "margin_trend", "roce_trend", "dupont", "cashflow",
    "fair_value_range", "expense_pie", "composite_radar",
    "sector_mcap", "sector_valuation_scatter", "sector_ownership_flow",
    "sector_growth_bars", "sector_profitability_bars", "sector_pe_distribution",
    "comparison_revenue", "comparison_pe", "comparison_shareholding",
    "comparison_radar", "comparison_margins",
    "dividend_history",
)

# get_chart_data: raw Screener chart series (NOT the render_chart vocab).
_CHART_DATA_TYPES = ("price", "pe", "sales_margin", "ev_ebitda", "pbv", "mcap_sales")

# calculate: named operations + 'expr' fallback. Mirrors the if/elif chain.
_CALCULATE_OPERATIONS = (
    "shares_to_value_cr", "per_share_to_total_cr", "total_cr_to_per_share",
    "pe_from_price_eps", "eps_from_pat_shares", "fair_value", "growth_rate",
    "cagr", "mcap_cr", "margin_of_safety", "annualize_quarterly", "pct_of",
    "ratio", "expr",
)

# get_data_quality_flags: severity tier filter (store sev_rank keys; uppercase).
_DATA_QUALITY_SEVERITIES = ("LOW", "MEDIUM", "HIGH")

# get_shareholder_detail: classification filter (screener_client tokens).
_SHAREHOLDER_CLASSIFICATIONS = (
    "foreign_institutions", "domestic_institutions", "promoters", "public",
)

# get_company_documents: doc_type filter (store upsert_documents tokens).
# NOTE: includes 'concall_recording' (the 3-value reference list was stale).
_COMPANY_DOC_TYPES = (
    "concall_transcript", "concall_ppt", "concall_recording", "annual_report",
)

# get_sector_benchmarks: metric vocab = peer_refresh._BENCHMARK_METRICS (closed
# set — only producer). Enum'd.
_SECTOR_BENCHMARK_METRICS = (
    "pe_trailing", "pe_forward", "pb", "ev_ebitda", "peg",
    "market_cap", "div_yield",
    "operating_margin", "net_margin", "roe", "roa", "roce", "roic",
    "revenue_growth", "earnings_growth",
    "beta", "debt_to_equity",
)

# get_valuation_band: metric vocab = store.get_valuation_band valid_metrics
# (closed set; SQL-injection-guarded) + the 'pb'/'pe' aliases the prompt docs use.
_VALUATION_BAND_METRICS = (
    "pe_trailing", "pe_forward", "pb_ratio", "ev_ebitda", "ev_revenue",
    "ps_ratio", "peg_ratio", "dividend_yield", "beta",
    "gross_margin", "operating_margin", "net_margin", "roe", "roa",
    "pb", "pe",
)


# --- Screener APIs (Phase 2) ---


@tool(
    "get_chart_data",
    "Get raw Screener chart time series (the underlying numeric series, NOT a rendered "
    "image). chart_type: 'price', 'pe', 'sales_margin', 'ev_ebitda', 'pbv', 'mcap_sales'. "
    "NOTE: this vocab is DIFFERENT from render_chart's chart_type (which produces PNGs and "
    "uses names like 'revenue_profit', 'dupont', 'fair_value_range'). Use get_chart_data for "
    "the numbers, render_chart for an embeddable chart image.",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "chart_type": {
                "type": "string",
                "description": (
                    "Raw Screener series to fetch: price; pe; sales_margin; ev_ebitda; "
                    "pbv; mcap_sales. DISTINCT from render_chart's PNG chart_type vocab."
                ),
                "enum": list(_CHART_DATA_TYPES),
            },
        },
        "required": ["symbol", "chart_type"],
    },
    annotations=READ_ONLY,
)
async def get_chart_data(args):
    chart_type = args["chart_type"]
    if chart_type not in _CHART_DATA_TYPES:
        return _invalid_enum_error("get_chart_data", "chart_type", chart_type, _CHART_DATA_TYPES, args)
    with ResearchDataAPI() as api:
        data = api.get_chart_data(args["symbol"], chart_type)
    return _with_dedup("get_chart_data", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


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
    "get_screener_peers",
    "Get Screener.in-recommended peer companies with basic financials. "
    "EXPLICIT FALLBACK ONLY — use this when the default peer set returned by "
    "get_peer_sector (Yahoo-recommended) looks sector-mismatched (e.g. food-delivery "
    "subject returned financials/insurance peers). Screener's peer list is often "
    "too narrow or off-sector; prefer Yahoo peers by default.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_screener_peers(args):
    symbol = args["symbol"].upper()
    with ResearchDataAPI() as api:
        data = api.get_screener_peers(symbol)
    return _with_dedup("get_screener_peers", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


# --- Business Profile (Vault) ---


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
    "get_data_quality_flags",
    "Get reclassification breaks in Screener annual_financials for this symbol. "
    "Call BEFORE computing any multi-year ratio (DuPont, F-score, margin walk, CAGR, leverage trend) — "
    "if any MEDIUM+ flag overlaps your window, the trend is corrupted by accounting bucketing changes "
    "(Schedule III amendments, Ind-AS 116 lease transition, mergers/demergers, sector regulator mandates). "
    "Each flag has prior_fy, curr_fy, line, prior_val, curr_val, jump_pct, flag_type (RECLASS|SIGN_FLIP), severity (HIGH|MEDIUM|LOW). "
    "Default min_severity=MEDIUM. Empty list = no breaks in the stored history.",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "min_severity": {
                "type": "string",
                "description": (
                    "Minimum severity tier to return. LOW returns everything; MEDIUM "
                    "(default) filters the noisy 100-200% band; HIGH returns only sign "
                    "flips and >500% jumps."
                ),
                "enum": list(_DATA_QUALITY_SEVERITIES),
            },
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_data_quality_flags(args):
    min_severity = args.get("min_severity")
    if min_severity is not None and min_severity not in _DATA_QUALITY_SEVERITIES:
        return _invalid_enum_error("get_data_quality_flags", "min_severity", min_severity, _DATA_QUALITY_SEVERITIES, args)
    with ResearchDataAPI() as api:
        data = api.get_data_quality_flags(args["symbol"], min_severity or "MEDIUM")
    return _with_dedup("get_data_quality_flags", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


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


get_concall_insights = tool(
    "get_concall_insights",
    "Get pre-extracted concall insights from the vault: 4 quarters of operational metrics, financial metrics, management commentary, subsidiary updates, risk flags, comparable-basis growth statements, and cross-quarter narrative themes. First call returns a compact table of contents (quarters + populated sections + qa_topics_by_quarter when Q&A carries topic tags). Pass sub_section to drill into one section across all quarters ('operational_metrics' | 'financial_metrics' | 'management_commentary' | 'subsidiaries' | 'qa_session' | 'flags' | 'opening_remarks' | 'comparable_growth_metrics' — the last is management's like-for-like / ex-merger / constant-currency growth statements; use it when a data_quality_flag corrupts the structured CAGR/trend). Pass quarter (e.g. 'FY26-Q3') to narrow to a single quarter. Pass qa_topics (e.g. ['margins','guidance']) to return only Q&A exchanges tagged with those topics — implies sub_section='qa_session'.",
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
    "Get pre-extracted investor-deck insights from the vault: up to 4 quarters of highlights, segment_performance, key_metrics, strategic_priorities, outlook_and_guidance, new_initiatives, charts_described, and slide_topics. Complements get_concall_insights — decks show polished charts, segmental tables, and forward guidance slides that the transcript doesn't expose as structured data. key_metrics holds non-segment quantitative KPIs read off the slides (debt, capex, order book/backlog, NIM/GNPA/CASA, time-series financials). First call returns a compact TOC (quarters + populated sections + slide_topics_by_quarter when tagged). Pass sub_section to drill into one section across all quarters ('highlights' | 'segment_performance' | 'key_metrics' | 'strategic_priorities' | 'outlook_and_guidance' | 'new_initiatives' | 'charts_described'). Pass full=true to read a whole deck's complete record in one call (combine with quarter to scope to one quarter). Pass quarter (e.g. 'FY26-Q3') to narrow. Pass slide_topics (e.g. ['segmental','outlook']) to filter quarters by their topic tags.",
    {"symbol": str, "sub_section": str, "quarter": str, "slide_topics": list, "full": bool},
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
            full=args.get("full", False),
        )
    return _with_dedup("get_deck_insights", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


get_annual_report = tool(
    "get_annual_report",
    "Get pre-extracted annual-report insights from the vault: up to 2 recent fiscal years, plus a cross-year evolution narrative (YoY changes in risks, auditor KAMs, governance, RPTs, strategic framing). Covers chairman_letter, mdna, risk_management, auditor_report, corporate_governance, brsr, related_party, segmental, notes_to_financials, financial_statements. Annual reports unlock data NOT in concalls or decks — auditor opinions & KAMs, contingent liabilities, board composition, related-party scrutiny, BRSR/ESG disclosures, detailed notes to accounts, segmental accounting. First call returns a compact TOC (years_on_file + sections_populated + cross_year_narrative). Pass section='auditor_report' (or any other) to drill into that section across years. Pass year='FY25' to narrow to one year.",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "type": "string",
                "description": (
                    "AR section to drill into. Omit for a compact TOC (do NOT pass 'toc'). "
                    "chairman_letter; mdna; risk_management; auditor_report; "
                    "corporate_governance; brsr; related_party; segmental; "
                    "notes_to_financials; financial_statements."
                ),
                "enum": list(_ANNUAL_REPORT_SECTIONS),
            },
            "year": {"type": "string", "description": "FY filter, e.g. 'FY25' (omit for all years on file)."},
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)


@get_annual_report
async def get_annual_report(args):
    section = args.get("section")
    if section is not None and section not in _ANNUAL_REPORT_SECTIONS:
        return _invalid_enum_error("get_annual_report", "section", section, _ANNUAL_REPORT_SECTIONS, args)
    with ResearchDataAPI() as api:
        data = api.get_annual_report(
            args["symbol"],
            year=args.get("year"),
            section=section,
        )
    return _with_dedup("get_annual_report", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


get_macro_anchor = tool(
    "get_macro_anchor",
    "Fetch pre-extracted content from canonical India macro anchor documents. "
    "Available doc_types: "
    "'economic_survey' (Economic Survey of India, annual pre-budget), "
    "'budget_speech' (Union Budget Speech, annual Feb), "
    "'budget_at_a_glance' (Union Budget receipts + expenditure summary), "
    "'rbi_mpr' (RBI Monetary Policy Report, biannual Apr/Oct), "
    "'rbi_mpc_statement' (RBI MPC bi-monthly resolution — latest rate decision + FY projections), "
    "'rbi_ar_assessment' (RBI Annual Report — Ch 1: Assessment & Outlook), "
    "'rbi_ar_economic' (RBI Annual Report — Ch 2: Economic Review, GDP/inflation/real sector), "
    "'rbi_ar_monetary' (RBI Annual Report — Ch 3: Monetary Policy Operations, liquidity/rates), "
    "'irdai_annual_report' (IRDAI Annual Report — insurance-sector regulator's annual review). "
    "First call WITHOUT section returns a compact TOC (available headings + metadata). "
    "Second call WITH section='<heading substring>' returns that section's markdown content. "
    "Heading match is fuzzy: case-insensitive, tolerant of section-prefix numbering "
    "('I.2', '3.'), em/en-dashes, trailing punctuation, and word-order swaps. If no heading "
    "matches, falls back to a body-text anchor (slice anchored on the first body occurrence "
    "of the query). If a doc_type is unavailable, returns status='unavailable' with fallback hint.",
    {
        "type": "object",
        "properties": {
            "doc_type": {
                "description": (
                    "Which anchor document. economic_survey; budget_speech; "
                    "budget_at_a_glance; rbi_mpr; rbi_mpc_statement; rbi_ar_assessment; "
                    "rbi_ar_economic; rbi_ar_monetary; irdai_annual_report."
                ),
                "enum": list(_MACRO_ANCHOR_DOC_TYPES),
            },
            "section": {
                "type": "string",
                "description": (
                    "Free-text heading substring to drill into (fuzzy match). Omit for a "
                    "compact TOC of available headings."
                ),
            },
        },
        "required": ["doc_type"],
    },
    annotations=READ_ONLY,
)


@get_macro_anchor
async def get_macro_anchor(args):
    doc_type = args["doc_type"]
    if doc_type not in _MACRO_ANCHOR_DOC_TYPES:
        return _invalid_enum_error("get_macro_anchor", "doc_type", doc_type, _MACRO_ANCHOR_DOC_TYPES, args)
    section = args.get("section")
    data = get_anchor_content(doc_type, section)
    return _with_dedup(
        "get_macro_anchor",
        {"content": [{"type": "text", "text": json.dumps(data, default=str)}]},
        args,
    )


get_macro_catalog = tool(
    "get_macro_catalog",
    "List all macro anchor documents currently available in the vault. "
    "Returns each anchor's status, title, url, heading_count, and extraction backend. "
    "Use this FIRST before calling get_macro_anchor to see which docs are cached and ready.",
    {},
    annotations=READ_ONLY,
)


@get_macro_catalog
async def get_macro_catalog(args):
    catalog = list_current_anchors()
    summary = {
        "anchors": [
            {
                "doc_type": k,
                "title": v.get("title") if isinstance(v, dict) else None,
                "status": v.get("status") if isinstance(v, dict) else "unknown",
                "heading_count": v.get("heading_count") if isinstance(v, dict) else None,
                "url": v.get("url") if isinstance(v, dict) else None,
            }
            for k, v in catalog.get("anchors", {}).items()
            if isinstance(v, dict)
        ],
    }
    return _with_dedup(
        "get_macro_catalog",
        {"content": [{"type": "text", "text": json.dumps(summary, default=str)}]},
        args,
    )


@tool(
    "get_macro_indicators",
    "India macro time-series from the local flowtracker DB (T1 numeric source): "
    "CPI inflation, IIP (industrial production), PMI (services + manufacturing) monthly "
    "trend, plus the full G-sec yield curve (1Y/5Y/10Y/30Y) history. Cite THIS for India "
    "CPI/IIP/PMI/yield NUMBERS (with as-of month) instead of WebSearch. Optional: months "
    "(trailing window, default 24).",
    {"months": int},
    annotations=READ_ONLY,
)
async def get_macro_indicators(args):
    with ResearchDataAPI() as api:
        data = api.get_macro_indicators(args.get("months", 24))
    return _with_dedup(
        "get_macro_indicators",
        {"content": [{"type": "text", "text": json.dumps(data, default=str)}]},
        args,
    )


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
    "'sector_valuation_scatter' (PE vs ROCE scatter — bargain/avoid quadrants; "
    "for BFSI sectors the y-axis auto-switches to ROA since ROCE is meaningless for banks), "
    "'sector_ownership_flow' (MF ownership changes — accumulation/exit). "
    "COMPARISON CHARTS (use comma-separated symbols, e.g. symbol='HDFCBANK,ICICIBANK'): "
    "'comparison_revenue' (indexed revenue trajectories), "
    "'comparison_pe' (PE history overlay), "
    "'comparison_shareholding' (FII/MF ownership trends overlay), "
    "'comparison_radar' (quality score radars overlaid), "
    "'comparison_margins' (OPM/NPM trends overlay). "
    "Returns: {path, embed_markdown}.",
    {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": (
                    "NSE symbol, uppercase. For comparison_* charts pass comma-"
                    "separated symbols (e.g. 'HDFCBANK,ICICIBANK')."
                ),
            },
            "chart_type": {
                "type": "string",
                "description": (
                    "Which PNG to render. STOCK: price; pe; delivery; revenue_profit; "
                    "quarterly; margin_trend; roce_trend; dupont; cashflow; shareholding; "
                    "fair_value_range; expense_pie; composite_radar; dividend_history. "
                    "SECTOR: sector_mcap; sector_growth_bars; sector_profitability_bars; "
                    "sector_pe_distribution; sector_valuation_scatter; sector_ownership_flow. "
                    "COMPARISON (comma-separated symbols): comparison_revenue; comparison_pe; "
                    "comparison_shareholding; comparison_radar; comparison_margins. "
                    "These are RENDERED PNGs — distinct from get_chart_data's raw-series "
                    "chart_type vocab (price/pe/sales_margin/ev_ebitda/pbv/mcap_sales)."
                ),
                "enum": list(_RENDER_CHART_TYPES),
            },
        },
        "required": ["symbol", "chart_type"],
    },
)
async def render_chart(args):
    from flowtracker.research.charts import render_chart as _render
    chart_type = args["chart_type"]
    if chart_type not in _RENDER_CHART_TYPES:
        return _invalid_enum_error("render_chart", "chart_type", chart_type, _RENDER_CHART_TYPES, args)
    result = _render(args["symbol"], chart_type)
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


# --- Sector Analysis ---


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


def _validate_sections(tool_name, section, valid, args):
    """Validate a resolved section value (str or list) against `valid`.

    Returns an `_invalid_enum_error` envelope on the first out-of-vocab value,
    or None if everything is valid. `valid` is the full accepted set INCLUDING
    sentinels the handler supports.
    """
    candidates = section if isinstance(section, list) else [section]
    valid_set = set(valid)
    for s in candidates:
        if s not in valid_set:
            return _invalid_enum_error(tool_name, "section", s, valid, args)
    return None


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


# Phase 3b: completeness label → wire status. "full" reads as "ok"; "truncated"
# normalizes to "partial" (both mean "data present but capped"). empty/partial/
# error pass through. None (unclassifiable) → None so the status key still rides.
_COMPLETENESS_TO_STATUS = {
    "full": "ok",
    "truncated": "partial",
    "partial": "partial",
    "empty": "empty",
    "error": "error",
}


def _stamp_meta(data, api, symbol: str):
    """Standardize a `_meta` sidecar on a dict payload (Phase 3b).

    Rides ALONGSIDE the existing data dict — does NOT restructure the payload —
    so the dedup hash, `classify_completeness`, and agent.py parsing are all
    preserved. Derives status + count from `classify_completeness(data)`, then
    appends freshness (best-effort). Applied on TOC, per-section success, AND
    error paths of the 10 section dispatchers.

    Bare LISTS can't carry a sidecar key, so they pass through untouched (the
    agent layer already captures row_count for lists). Always exception-safe —
    never break a tool call for metadata.
    """
    if not isinstance(data, dict):
        return data  # bare list / str — leave as-is
    try:
        from datetime import date
        comp, count = classify_completeness(data)
        status = _COMPLETENESS_TO_STATUS.get(comp, comp)
        freshness = None
        if status != "error":
            try:
                freshness = api.get_data_freshness(symbol)
            except Exception:
                freshness = None
        data["_meta"] = {
            "as_of_date": str(date.today()),
            "status": status,
            "count": count,
            "data_freshness": freshness,
        }
    except Exception:
        pass  # Don't break tool calls for metadata failures
    return data


def _enum_toc(sections) -> dict:
    """Build a lightweight TOC from a Phase-1 section enum constant (Phase 3a).

    Used by the seven dispatchers that have no dedicated `get_<x>_toc` data_api
    method. Mirrors the compact-TOC-then-drill contract so a no-section call
    never falls through to the truncation-prone 'all' payload.
    """
    return {
        "_toc": list(sections),
        "hint": (
            "Call with section='<one>' or section=['a','b'] for specific data; "
            "section='all' returns everything (may be truncated)."
        ),
    }


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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Which fundamentals section(s). Omit (or 'toc') for a compact TOC. "
                    "Pass one value or a list. quarterly_results/annual_financials = P&L; "
                    "ratios; quarterly_balance_sheet/quarterly_cash_flow; expense_breakdown "
                    "(needs sub_section); growth_rates/cagr_table; capital_allocation; "
                    "rate_sensitivity; cost_structure; balance_sheet_detail; "
                    "cash_flow_quality; working_capital. Avoid 'all' (truncates)."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_FUNDAMENTALS_SECTIONS + _FUNDAMENTALS_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_FUNDAMENTALS_SECTIONS + _FUNDAMENTALS_SENTINELS)}},
                ],
            },
            "quarters": {"type": "integer", "description": "Quarters of history (default 12)."},
            "years": {"type": "integer", "description": "Years of history (default 10)."},
            "sub_section": {"type": "string", "description": "For expense_breakdown: 'profit-loss' etc."},
        },
        "required": ["symbol"],
    },
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
            data = _stamp_meta(data, api, symbol)
            return _with_dedup("get_fundamentals", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)

        section = _parse_section(section_raw)
        err = _validate_sections("get_fundamentals", section, _FUNDAMENTALS_SECTIONS + _FUNDAMENTALS_SENTINELS, args)
        if err is not None:
            return err
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
        data = _stamp_meta(data, api, symbol)
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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Accounting/quality section(s). Pass one value or a list. Omit to get "
                    "'all' (BFSI auto-skips non-applicable). Core: earnings_quality, "
                    "piotroski, beneish, dupont, common_size, capex_cycle, forensic_checks, "
                    "improvement_metrics, capital_discipline, incremental_roce, altman_zscore, "
                    "working_capital, operating_leverage, fcf_yield, tax_rate_analysis, "
                    "receivables_quality, subsidiary. Sector: bfsi, insurance, metals, "
                    "realestate, telecom, power, sector_health."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_QUALITY_SCORES_SECTIONS + _QUALITY_SCORES_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_QUALITY_SCORES_SECTIONS + _QUALITY_SCORES_SENTINELS)}},
                ],
            },
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_quality_scores(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    # Default behavior when no section specified: return a compact TOC instead
    # of the heavy 'all' payload (truncation-prone). 'all' stays an explicit opt-in.
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_QUALITY_SCORES_SECTIONS), api, symbol)
        return _with_dedup("get_quality_scores", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_quality_scores", section, _QUALITY_SCORES_SECTIONS + _QUALITY_SCORES_SENTINELS, args)
    if err is not None:
        return err
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
        data = _stamp_meta(data, api, symbol)
    return _with_dedup("get_quality_scores", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _india_only_section_marker(section: str, market: str) -> dict:
    """Per-section 'not applicable for US' marker for an India-only section."""
    return {
        "status": "not_applicable",
        "market": market,
        "reason": (
            f"'{section}' is an India-market ownership concept with no US "
            "equivalent (use get_institutional_ownership for US 13F holdings)."
        ),
    }


def _get_ownership_section(api, symbol, section, args, is_us=False):
    """Route a single section for get_ownership.

    When `is_us` and the section is India-only (MF/pledge/shareholder_detail/
    public_breakdown/esop/adr_gdr/bulk_block), return an explicit
    not-applicable marker instead of a misleading empty India payload.
    """
    if is_us and section in _OWNERSHIP_INDIA_ONLY:
        return _india_only_section_marker(section, api._market_of(symbol))
    if section == "shareholding":
        return api.get_shareholding(symbol, args.get("quarters", 20))
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
    elif section == "adr_gdr":
        # Wave 5 P2: live XBRL CustodianOrDRHolder + manual-seed table.
        return api.get_adr_gdr(symbol)
    elif section == "public_breakdown":
        # Wave 5 P2: Retail / HNI / Bodies Corporate / NRI sub-cats inside
        # the Public bucket, plus FPI Cat-I/II inside the FII bucket.
        return api.get_public_breakdown(symbol, args.get("quarters", 4))
    elif section == "esop":
        # Wave 5 P2: ESOP pool size + per-plan detail from AR Schedule III.
        return api.get_esop_summary(symbol, args.get("fiscal_years", 5))
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_ownership",
    "Ownership & stakeholder data. First call without section returns a compact TOC (~3-5KB) with current ownership snapshot, QoQ changes, top-10 holders brief, MF/pledge/insider/bulk-block summaries, public-breakdown brief (retail/HNI/bodies-corporate/NRI), and ESOP brief — enough to decide what to drill into. Then call with section='<name>' or section=['s1','s2'] to drill in. Sections: 'shareholding' | 'changes' | 'insider' | 'bulk_block' | 'mf_holdings' | 'mf_changes' | 'shareholder_detail' | 'promoter_pledge' | 'mf_conviction' | 'adr_gdr' | 'public_breakdown' | 'esop'. shareholder_detail returns top-20 named holders (pivoted per-holder, >=1% latest quarter) with holder_type in {FII, DII, Promoter, Public}. adr_gdr surfaces ADR/GDR outstanding live from XBRL CustodianOrDRHolder context (definitive — no scraping needed) with manual-seed override + AR-notes fallback. public_breakdown drills into the Public bucket with retail/HNI/bodies-corporate/NRI sub-cats, FPI Cat-I/II breakdown, and ADR/GDR-attributable foreign holding (Wave 5 P2). esop returns ESOP pool size + per-plan detail from AR Schedule III disclosure (critical for new-economy dilution analysis). Heavy sections are capped (mf_holdings top 30 by value + tail summary) to stay under MCP tool-result transport limits. Avoid section='all' — payloads of 80-150K can get truncated. Optional: quarters (default 12), days (default 1825), classification (for shareholder_detail filter), fiscal_years (default 5, for esop).",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Ownership section(s). Omit (or 'toc') for a compact TOC. Pass one value "
                    "or a list. shareholding; changes (QoQ); insider; bulk_block; mf_holdings; "
                    "mf_changes; shareholder_detail (top-20 named holders); promoter_pledge; "
                    "mf_conviction; adr_gdr; public_breakdown (retail/HNI/bodies-corp/NRI); "
                    "esop. Avoid 'all' (truncates)."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_OWNERSHIP_SECTIONS + _OWNERSHIP_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_OWNERSHIP_SECTIONS + _OWNERSHIP_SENTINELS)}},
                ],
            },
            "quarters": {"type": "integer", "description": "Quarters of history (default 12)."},
            "days": {"type": "integer", "description": "Lookback days for insider (default 1825)."},
            "classification": {"type": "string", "description": "Holder-type filter for shareholder_detail."},
            "fiscal_years": {"type": "integer", "description": "Years for esop (default 5)."},
        },
        "required": ["symbol"],
    },
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
        is_us = api._is_us(symbol)
        if not section_raw or section_raw in ("toc", "summary"):
            data = api.get_ownership_toc(symbol)
        else:
            section = _parse_section(section_raw)
            err = _validate_sections("get_ownership", section, _OWNERSHIP_SECTIONS + _OWNERSHIP_SENTINELS, args)
            if err is not None:
                return err
            if isinstance(section, list):
                data = {s: _get_ownership_section(api, symbol, s, args, is_us) for s in section}
            elif section == "all":
                def _own(sec, val):
                    # India-only sections degrade to a not-applicable marker for US.
                    if is_us and sec in _OWNERSHIP_INDIA_ONLY:
                        return _india_only_section_marker(sec, api._market_of(symbol))
                    return val
                data = {
                    "_warning": (
                        "section='all' returns 80-150K chars and may be truncated by the "
                        "MCP transport. Prefer calling without section for a compact TOC "
                        "first, then drilling into specific sections."
                    ),
                    "shareholding": api.get_shareholding(symbol, args.get("quarters", 12)),
                    "changes": api.get_shareholding_changes(symbol),
                    "insider": api.get_insider_transactions(symbol, args.get("days", 1825)),
                    "bulk_block": _own("bulk_block", api.get_bulk_block_deals(symbol)),
                    "mf_holdings": _own("mf_holdings", api.get_mf_holdings(symbol)),
                    "mf_changes": _own("mf_changes", api.get_mf_holding_changes(symbol)),
                    "shareholder_detail": _own("shareholder_detail", api.get_shareholder_detail(symbol, args.get("classification"))),
                    "promoter_pledge": _own("promoter_pledge", api.get_promoter_pledge(symbol)),
                    "mf_conviction": _own("mf_conviction", api.get_mf_conviction(symbol)),
                    "adr_gdr": _own("adr_gdr", api.get_adr_gdr(symbol)),
                    "public_breakdown": _own("public_breakdown", api.get_public_breakdown(symbol, args.get("quarters", 4))),
                    "esop": _own("esop", api.get_esop_summary(symbol, args.get("fiscal_years", 5))),
                }
            else:
                data = _get_ownership_section(api, symbol, section, args, is_us)
        data = _stamp_meta(data, api, symbol)
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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Valuation section(s). Pass one value or a list. Omit to get 'all'. "
                    "snapshot (live multiples); band (valuation band over time); pe_history; "
                    "key_metrics (10yr); wacc (beta, cost of equity/debt, discount rate); "
                    "sotp (listed subsidiaries)."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_VALUATION_SECTIONS + _VALUATION_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_VALUATION_SECTIONS + _VALUATION_SENTINELS)}},
                ],
            },
            "metric": {"type": "string", "description": "Valuation metric for band (default 'pe_trailing')."},
            "days": {"type": "integer", "description": "Lookback days for band/pe_history (default 2500)."},
            "years": {"type": "integer", "description": "Years for key_metrics (default 10)."},
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_valuation(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_VALUATION_SECTIONS), api, symbol)
        return _with_dedup("get_valuation", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_valuation", section, _VALUATION_SECTIONS + _VALUATION_SENTINELS, args)
    if err is not None:
        return err
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
        data = _stamp_meta(data, api, symbol)
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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Fair-value section(s). Pass one value or a list. Omit to get 'all'. "
                    "combined (blended fair value); dcf; dcf_history; reverse_dcf "
                    "(implied growth); projections (revenue/earnings model)."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_FAIR_VALUE_SECTIONS + _FAIR_VALUE_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_FAIR_VALUE_SECTIONS + _FAIR_VALUE_SENTINELS)}},
                ],
            },
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_fair_value_analysis(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_FAIR_VALUE_SECTIONS), api, symbol)
        return _with_dedup("get_fair_value_analysis", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_fair_value_analysis", section, _FAIR_VALUE_SECTIONS + _FAIR_VALUE_SENTINELS, args)
    if err is not None:
        return err
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
        data = _stamp_meta(data, api, symbol)
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
    elif section == "sector_index_valuation":
        return api.get_sector_index_valuation(symbol)
    elif section == "sector_performance":
        return api.get_sector_index_performance()
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_peer_sector",
    "Peer comparison & sector data. First call with NO section (or section='toc') returns a compact ~1-2KB TOC listing the sections + recommended wave compositions. Then drill with section=['<wave sections>'] or section='<single>'. Valid sections: 'peer_table' | 'peer_metrics' | 'peer_growth' | 'valuation_matrix' | 'benchmarks' | 'sector_overview' | 'sector_flows' | 'sector_valuations' | 'yahoo_peers' | 'sector_index_valuation' (the stock's sector index PE/PB vs its own 10yr median + percentile) | 'sector_performance' (1M/3M/6M/1Y returns across all broad+sectoral indices, ranked — sector rotation). Do NOT call section='all' — the large payload may truncate. Optional: metric (for specific valuation metric).",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Peer/sector section(s). Omit (or 'toc') for a compact TOC. Pass one value "
                    "or a list. peer_table; peer_metrics; peer_growth; valuation_matrix; "
                    "benchmarks; sector_overview; sector_flows; sector_valuations; yahoo_peers; "
                    "sector_index_valuation (sector index PE/PB vs 10yr median); "
                    "sector_performance (index returns, ranked). Avoid 'all' (truncates)."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_PEER_SECTOR_SECTIONS + _PEER_SECTOR_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_PEER_SECTOR_SECTIONS + _PEER_SECTOR_SENTINELS)}},
                ],
            },
            "metric": {"type": "string", "description": "Specific valuation metric for benchmarks."},
        },
        "required": ["symbol"],
    },
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
            data = _stamp_meta(data, api, symbol)
            return _with_dedup("get_peer_sector", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)

        section = _parse_section(section_raw)
        err = _validate_sections("get_peer_sector", section, _PEER_SECTOR_SECTIONS + _PEER_SECTOR_SENTINELS, args)
        if err is not None:
            return err
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
                "sector_index_valuation": api.get_sector_index_valuation(symbol),
                "sector_performance": api.get_sector_index_performance(),
            }
        else:
            data = _get_peer_sector_section(api, symbol, section, args)
        data = _stamp_meta(data, api, symbol)
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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Estimates section(s). Pass one value or a list. Omit to get 'all'. "
                    "consensus; surprises (beat/miss history); revisions; momentum; revenue; "
                    "growth; analyst_grades; price_targets."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_ESTIMATES_SECTIONS + _ESTIMATES_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_ESTIMATES_SECTIONS + _ESTIMATES_SENTINELS)}},
                ],
            },
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_estimates(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_ESTIMATES_SECTIONS), api, symbol)
        return _with_dedup("get_estimates", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_estimates", section, _ESTIMATES_SECTIONS + _ESTIMATES_SENTINELS, args)
    if err is not None:
        return err
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
        data = _stamp_meta(data, api, symbol)
    return _with_dedup("get_estimates", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _get_market_context_section(api, symbol, section, args, is_us=False):
    """Route a single section for get_market_context.

    India-only sections (delivery %, FII/DII flows) degrade to an explicit
    not-applicable marker for US symbols.
    """
    if is_us and section in _MARKET_CONTEXT_INDIA_ONLY:
        return {
            "status": "not_applicable",
            "market": api._market_of(symbol),
            "reason": (
                f"'{section}' is an India-market concept (NSE bhavcopy delivery / "
                "FII-DII flows) with no US equivalent."
            ),
        }
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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Market-context section(s). Pass one value or a list. Omit to get 'all'. "
                    "delivery; macro (VIX/USDINR/Brent/G-sec); fii_dii_streak; fii_dii_flows; "
                    "technicals; price_performance; delivery_analysis; commodities; "
                    "institutional_consensus."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_MARKET_CONTEXT_SECTIONS + _MARKET_CONTEXT_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_MARKET_CONTEXT_SECTIONS + _MARKET_CONTEXT_SENTINELS)}},
                ],
            },
            "days": {"type": "integer", "description": "Lookback days (default 90; delivery/flows default 30)."},
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_market_context(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_MARKET_CONTEXT_SECTIONS), api, symbol)
        return _with_dedup("get_market_context", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_market_context", section, _MARKET_CONTEXT_SECTIONS + _MARKET_CONTEXT_SENTINELS, args)
    if err is not None:
        return err
    with ResearchDataAPI() as api:
        is_us = api._is_us(symbol)
        if isinstance(section, list):
            data = {s: _get_market_context_section(api, symbol, s, args, is_us) for s in section}
        elif section == "all":
            def _mkt(sec, val):
                if is_us and sec in _MARKET_CONTEXT_INDIA_ONLY:
                    return _get_market_context_section(api, symbol, sec, args, is_us)
                return val
            # Compute ADTV (avg daily traded value in ₹ Cr) from bhavcopy turnover
            stock_data = api._store.get_stock_delivery(symbol, days=30)
            turnovers = [r.turnover for r in stock_data if r.turnover and r.turnover > 0]
            adtv_cr = round(sum(turnovers) / len(turnovers) / 1e7, 1) if turnovers else None  # turnover is in ₹, convert to Cr

            data = {
                "delivery": _mkt("delivery", api.get_delivery_trend(symbol, args.get("days", 30))),
                "adtv_cr": adtv_cr,
                "adtv_signal": (
                    "severe_liquidity_risk" if adtv_cr is not None and adtv_cr < 5
                    else "moderate_liquidity_risk" if adtv_cr is not None and adtv_cr < 20
                    else "adequate" if adtv_cr is not None
                    else None
                ),
                "macro": api.get_macro_snapshot(),
                "fii_dii_streak": _mkt("fii_dii_streak", api.get_fii_dii_streak()),
                "fii_dii_flows": _mkt("fii_dii_flows", api.get_fii_dii_flows(args.get("days", 30))),
                "technicals": api.get_technical_indicators(symbol),
                "price_performance": api.get_price_performance(symbol),
                "delivery_analysis": _mkt("delivery_analysis", api.get_delivery_analysis(symbol, args.get("days", 90))),
                "commodities": api.get_commodity_snapshot(),
                "institutional_consensus": api.get_institutional_consensus(symbol),
            }
        else:
            data = _get_market_context_section(api, symbol, section, args, is_us)
        data = _stamp_meta(data, api, symbol)
    return _with_dedup("get_market_context", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_institutional_ownership",
    "US 13F institutional ownership — the managers (funds, advisors) holding this "
    "US-listed stock, ordered largest USD value first. Each row carries manager_name, "
    "manager_cik, shares, value_usd, quarter_end, and put_call. This is the US analogue "
    "of India's MF-scheme/FII shareholding data (SEC Form 13F quarterly filings). "
    "For an India (NSE) symbol this returns status='not_applicable' — use get_ownership "
    "(mf_holdings / shareholder_detail) for India instead. Optional: top_n (default 50).",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "US ticker (NASDAQ/NYSE), uppercase."},
            "top_n": {"type": "integer", "description": "Cap on managers returned (default 50)."},
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_institutional_ownership(args):
    symbol = args["symbol"].upper()
    if not _is_us_symbol(symbol):
        return _india_not_applicable_13f(symbol, args)
    with ResearchDataAPI() as api:
        rows = api.get_institutional_holdings(symbol, args.get("top_n", 50))
    data = {"symbol": symbol, "holdings": rows}
    return _with_dedup("get_institutional_ownership", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


def _india_not_applicable_13f(symbol: str, args: dict) -> dict:
    """'n/a for India' envelope for the US-only 13F ownership tool."""
    from datetime import date
    payload = {
        "status": "not_applicable",
        "market": "NSE",
        "symbol": symbol,
        "reason": (
            "13F institutional ownership is a US SEC filing concept with no India "
            f"equivalent; not applicable for NSE-listed {symbol}. Use get_ownership "
            "(mf_holdings / shareholder_detail) for India institutional data."
        ),
        "_meta": {
            "as_of_date": str(date.today()),
            "status": "not_applicable",
            "count": 0,
            "data_freshness": None,
        },
    }
    return _with_dedup(
        "get_institutional_ownership",
        {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]},
        args,
    )


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
            full=args.get("full", False),
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
    "Company info, profile & documents. section: 'info' | 'profile' | 'documents' | 'business_profile' | 'concall_insights' | 'deck_insights' | 'annual_report' | 'sector_kpis' | 'filings' | ['section1', 'section2']. Optional sub_section (for concall_insights: 'operational_metrics' | 'financial_metrics' | 'management_commentary' | 'subsidiaries' | 'qa_session' | 'flags' | 'opening_remarks' | 'comparable_growth_metrics' (management's like-for-like / ex-merger / constant-currency statements); for deck_insights: 'highlights' | 'segment_performance' | 'key_metrics' (non-segment KPIs — debt, capex, order book, NIM/GNPA/CASA, multi-period financials — returns a cross-quarter time series per metric) | 'strategic_priorities' | 'outlook_and_guidance' | 'new_initiatives' | 'charts_described'; for annual_report: 'chairman_letter' | 'mdna' | 'risk_management' | 'auditor_report' | 'corporate_governance' | 'brsr' | 'related_party' | 'segmental' | 'notes_to_financials' | 'financial_statements' — optional 'year' param to narrow to one FY like FY25; for sector_kpis: a specific canonical KPI key like 'gross_npa_pct' — call without sub_section first to see available keys). First call returns a compact table of contents; drill in with sub_section.",
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Company-context section(s). Pass one value or a list. Omit to get 'all'. "
                    "info; profile; documents; business_profile; concall_insights; "
                    "deck_insights; annual_report; sector_kpis; filings."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_COMPANY_CONTEXT_SECTIONS + _COMPANY_CONTEXT_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_COMPANY_CONTEXT_SECTIONS + _COMPANY_CONTEXT_SENTINELS)}},
                ],
            },
            "sub_section": {
                "type": "string",
                "description": (
                    "Drill-in within section. For concall_insights: operational_metrics, "
                    "financial_metrics, management_commentary, subsidiaries, qa_session, flags, "
                    "opening_remarks, comparable_growth_metrics. For deck_insights: highlights, "
                    "segment_performance, key_metrics (non-segment KPIs + cross-quarter series), "
                    "strategic_priorities, outlook_and_guidance, "
                    "new_initiatives, charts_described. For annual_report: chairman_letter, mdna, "
                    "risk_management, auditor_report, corporate_governance, brsr, related_party, "
                    "segmental, notes_to_financials, financial_statements. For sector_kpis: a "
                    "canonical KPI key (free-text; call without sub_section to see keys)."
                ),
            },
            "doc_type": {"type": "string", "description": "Filter for documents section."},
            "year": {"type": "string", "description": "FY filter for annual_report (e.g. 'FY25')."},
            "quarter": {"type": "string", "description": "Quarter filter for concall/deck (e.g. 'FY26-Q3')."},
            "limit": {"type": "integer", "description": "Row cap for filings (default 10)."},
            "qa_topics": {"type": "array", "items": {"type": "string"}, "description": "Q&A topic tags for concall_insights."},
            "slide_topics": {"type": "array", "items": {"type": "string"}, "description": "Slide topic tags for deck_insights."},
            "full": {"type": "boolean", "description": "deck_insights: return a whole deck's complete record in one call."},
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_company_context(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_COMPANY_CONTEXT_SECTIONS), api, symbol)
        return _with_dedup("get_company_context", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_company_context", section, _COMPANY_CONTEXT_SECTIONS + _COMPANY_CONTEXT_SENTINELS, args)
    if err is not None:
        return err
    # Conditional sub_section validation: only when drilling into a single section
    # whose sub_section vocab is enumerable (concall/deck/AR). sector_kpis sub_section
    # is a free-text canonical KPI key and is intentionally not validated.
    sub_section = args.get("sub_section")
    if isinstance(section, str) and sub_section and section in _COMPANY_CONTEXT_SUB_SECTION_VOCAB:
        sub_vocab = _COMPANY_CONTEXT_SUB_SECTION_VOCAB[section]
        if sub_section not in sub_vocab:
            return _invalid_enum_error("get_company_context", "sub_section", sub_section, sub_vocab, args)
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
        data = _stamp_meta(data, api, symbol)
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
    {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "NSE symbol, uppercase."},
            "section": {
                "description": (
                    "Events/actions section(s). Pass one value or a list. Omit to get 'all'. "
                    "events (calendar); dividends; corporate_actions (splits/bonuses); "
                    "adjusted_eps; catalysts (upcoming); material_events; dividend_policy."
                ),
                "anyOf": [
                    {"type": "string", "enum": list(_EVENTS_ACTIONS_SECTIONS + _EVENTS_ACTIONS_SENTINELS)},
                    {"type": "array", "items": {"type": "string", "enum": list(_EVENTS_ACTIONS_SECTIONS + _EVENTS_ACTIONS_SENTINELS)}},
                ],
            },
            "years": {"type": "integer", "description": "Years for dividends (default 10)."},
            "quarters": {"type": "integer", "description": "Quarters for adjusted_eps (default 12)."},
            "days": {"type": "integer", "description": "Lookback days for catalysts/material_events (default 90/365)."},
        },
        "required": ["symbol"],
    },
    annotations=READ_ONLY,
)
async def get_events_actions(args):
    symbol = args["symbol"]
    section_raw = args.get("section")
    if not section_raw or section_raw in ("toc", "summary"):
        with ResearchDataAPI() as api:
            data = _stamp_meta(_enum_toc(_EVENTS_ACTIONS_SECTIONS), api, symbol)
        return _with_dedup("get_events_actions", {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)
    section = _parse_section(section_raw)
    err = _validate_sections("get_events_actions", section, _EVENTS_ACTIONS_SECTIONS + _EVENTS_ACTIONS_SENTINELS, args)
    if err is not None:
        return err
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
        data = _stamp_meta(data, api, symbol)
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
    "\nUNIT CONTRACT (read this first — agent errors here are the #1 cause of fair-value mistakes):\n"
    "  • Monetary aggregates → CRORES (₹1 Cr = 10M = 1e7). Field names ending `_cr` mean crores.\n"
    "  • Per-share values (price, EPS, BVPS, fair_value) → RUPEES.\n"
    "  • Share counts (shares, shares_outstanding) → RAW INTEGER COUNT, not lakhs, not crores.\n"
    "    NESTLEIND has 964,157,160 shares (~96 crore / ~9,641 lakh shares). Pass `964157160`.\n"
    "    Source: `get_company_snapshot()['shares_outstanding']` or `get_valuation(section='snapshot')['shares_outstanding']` — both return raw count.\n"
    "    DO NOT pass `shares_outstanding_lakh` (that field is human-readable, divided by 1e5). DO NOT pass shares in crores (divided by 1e7).\n"
    "    A listed Indian company has at least ~1 lakh (1e5) shares; if your `b` is < 100,000 the tool will REJECT with a unit-error message — read that error carefully.\n"
    "\nNAMED OPERATIONS (preferred — enforce Indian unit conversion) — pass operation + a + b:\n"
    "  'shares_to_value_cr'     a=shares (RAW count, e.g. 964157160), b=price (₹) -> value_cr (in crores)\n"
    "  'per_share_to_total_cr'  a=per_share_value (₹), b=shares (RAW count) -> total_cr (in crores)\n"
    "  'total_cr_to_per_share'  a=total_cr (in crores), b=shares (RAW count) -> per_share (in ₹)\n"
    "  'pe_from_price_eps'      a=price (₹), b=eps (₹) -> pe (ratio)\n"
    "  'eps_from_pat_shares'    a=pat_cr (in crores), b=shares (RAW count) -> eps (in ₹)\n"
    "  'fair_value'             a=pe_multiple, b=eps (₹) -> fair_value (per share, in ₹)\n"
    "  'growth_rate'            a=old, b=new -> growth_pct (percent; single-period)\n"
    "  'cagr'                   a=start, b=end, years=<N> -> cagr_pct (compound annual growth rate; use 'years' kwarg OR pass years as third positional via inputs_as_of='years:5')\n"
    "  'mcap_cr'                a=price (₹), b=shares (RAW count) -> mcap_cr (in crores)\n"
    "  'margin_of_safety'       a=fair_value (₹), b=current_price (₹) -> mos_pct (percent)\n"
    "  'annualize_quarterly'    a=quarterly_value -> annualized (x4); leave b='0'\n"
    "  'pct_of'                 a=part, b=whole -> pct (percent)\n"
    "  'ratio'                  a=numerator, b=denominator -> ratio\n"
    "\nWORKED EXAMPLE (NESTLEIND target price): blended fair-value of ₹36,780 Cr ÷ 964,157,160 shares → ₹381.49 per share.\n"
    "  calculate(operation='total_cr_to_per_share', a='36780', b='964157160') → {per_share: 381.49}\n"
    "Counter-example (BANKBARODA bug to avoid): passing b='51713.62' (lakhs of shares) → tool REJECTS as unit error. Pass raw count instead (`51713 lakh × 1e5 = 5,171,300,000`).\n"
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
    # discipline; see Tenet 16 (OWNERSHIP_SYSTEM).
    # years: optional kwarg for cagr operation.
    {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": (
                    "Which calculation to run. Named ops (preferred — unit-aware): "
                    "shares_to_value_cr; per_share_to_total_cr; total_cr_to_per_share; "
                    "pe_from_price_eps; eps_from_pat_shares; fair_value; growth_rate; cagr; "
                    "mcap_cr; margin_of_safety; annualize_quarterly; pct_of; ratio. "
                    "'expr' = arbitrary arithmetic (pass the expression as `a`, b='0'). "
                    "See the tool description for each op's a/b contract."
                ),
                "enum": list(_CALCULATE_OPERATIONS),
            },
            "a": {"type": "string", "description": "First operand as a numeric string (or the expression string for operation='expr')."},
            "b": {"type": "string", "description": "Second operand as a numeric string. Pass '0' when an op ignores b (annualize_quarterly, expr)."},
            "inputs_as_of": {"type": "string", "description": "ISO quarter/date of the %pt input context (historical-flow discipline; Tenet 16). Also accepts 'years:N' for cagr."},
            "mcap_as_of": {"type": "string", "description": "ISO quarter/date of the market-cap context. If it differs from inputs_as_of, the result carries a HISTORICAL_MCAP_MISMATCH caveat."},
            "years": {"type": "string", "description": "Number of periods for the 'cagr' operation (numeric string)."},
        },
        "required": ["operation"],
    },
    annotations=READ_ONLY,
)
async def calculate(args):
    import math
    op = args["operation"]
    if op not in _CALCULATE_OPERATIONS:
        return _invalid_enum_error("calculate", "operation", op, _CALCULATE_OPERATIONS, args)
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

    # Defensive unit check — share counts must be RAW integer counts, not lakhs/crores.
    # A listed Indian company has at least ~1 lakh (1e5) shares; values below that
    # almost certainly mean the agent passed lakhs (e.g. 51,713) or crores (e.g. 96)
    # by mistake. Reject loudly with a corrective message rather than silently
    # producing a 100x or 1e7x wrong result. Skip for divide-by-zero (b=0 already
    # handled gracefully) and skip when raw input was empty/None (back-compat).
    _MIN_SHARES = 1e5  # 1 lakh — minimum plausible listed-company share count
    _SHARE_OPS_B = {
        "shares_to_value_cr": "a",         # a=shares
        "per_share_to_total_cr": "b",
        "total_cr_to_per_share": "b",
        "eps_from_pat_shares": "b",
        "mcap_cr": "b",
    }
    if op in _SHARE_OPS_B:
        share_arg_name = _SHARE_OPS_B[op]
        share_val = a if share_arg_name == "a" else b
        share_raw = raw_a if share_arg_name == "a" else raw_b
        # Only reject if a positive but implausibly-low value was actually passed
        # (skip 0 — divide-by-zero paths handle that — and skip None/empty for back-compat).
        if share_raw not in (None, "") and 0 < share_val < _MIN_SHARES:
            unit_err = (
                f"UNIT_ERROR ({op}): argument '{share_arg_name}'={share_val} is implausibly low for a "
                f"listed Indian company's share count. Pass RAW share count (e.g. 964157160 for NESTLEIND), "
                f"NOT lakhs of shares (e.g. 9641) and NOT crores of shares (e.g. 96). "
                f"If your data source returned `shares_outstanding_lakh`, multiply by 1e5 to get raw count. "
                f"If you meant ~{share_val:.0f} lakh shares, pass {share_val * 1e5:.0f}; "
                f"if ~{share_val:.0f} crore shares, pass {share_val * 1e7:.0f}."
            )
            return _with_dedup(
                "calculate",
                {"content": [{"type": "text", "text": json.dumps({"error": unit_err}, default=str)}]},
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
RESEARCH_TOOLS = [
    get_fundamentals, get_quality_scores, get_ownership, get_valuation,
    get_fair_value_analysis, get_peer_sector, get_estimates,
    get_market_context, get_company_context, get_events_actions,
    get_analytical_profile, render_chart, get_composite_score,
    screen_stocks, save_business_profile, get_chart_data, calculate,
    get_annual_report, get_deck_insights,
]

# V1 agent registries (BUSINESS_TOOLS, *_AGENT_TOOLS, _PEER_TOOLS) removed — see *_AGENT_TOOLS below

# --- V2 Agent Tool Registries (macro-tools) ---

BUSINESS_AGENT_TOOLS = [
    get_analytical_profile, get_company_context, get_fundamentals,
    get_peer_sector, get_events_actions, get_yahoo_peers, get_screener_peers,
    get_valuation, get_chart_data, save_business_profile, render_chart, calculate,
    get_annual_report, get_deck_insights,
]

FINANCIAL_AGENT_TOOLS = [
    get_analytical_profile, get_company_context, get_fundamentals,
    get_quality_scores, get_valuation, get_peer_sector,
    get_estimates, get_events_actions, get_fair_value_analysis,
    get_chart_data, render_chart, calculate,
    get_annual_report, get_deck_insights,
    get_data_quality_flags,
]

OWNERSHIP_AGENT_TOOLS = [
    get_analytical_profile, get_ownership, get_market_context,
    get_peer_sector, get_company_context, get_estimates,
    get_fundamentals, render_chart, calculate,
    get_annual_report,
    get_institutional_ownership,  # US 13F ownership (n/a for India)
]

VALUATION_AGENT_TOOLS = [
    get_analytical_profile, get_valuation, get_fair_value_analysis,
    get_estimates, get_peer_sector, get_events_actions, get_yahoo_peers, get_screener_peers,
    get_company_context, get_quality_scores, get_fundamentals, get_market_context,
    get_chart_data, render_chart, calculate,
    get_annual_report, get_deck_insights,
    get_data_quality_flags,
]

RISK_AGENT_TOOLS = [
    get_analytical_profile, get_composite_score, get_fundamentals,
    get_quality_scores, get_ownership, get_market_context,
    get_peer_sector, get_company_context, get_events_actions,
    get_estimates, render_chart, calculate,
    get_annual_report,
    get_fair_value_analysis,  # reverse-DCF for bear-case downside stress
]

TECHNICAL_AGENT_TOOLS = [
    get_analytical_profile, get_market_context, get_valuation,
    get_ownership, get_peer_sector, get_chart_data, render_chart, calculate,
    get_events_actions,  # earnings / ex-div / corporate-action timing
]

SECTOR_AGENT_TOOLS = [
    get_analytical_profile, get_company_context, get_peer_sector,
    get_market_context, get_fundamentals, get_estimates, get_yahoo_peers, get_screener_peers,
    get_valuation, get_chart_data, render_chart, calculate, get_data_quality_flags,
]

NEWS_AGENT_TOOLS = [
    get_analytical_profile, get_company_context,
    get_stock_news, get_events_actions,
]

MACRO_AGENT_TOOLS = [
    get_macro_catalog,     # lists available anchors + their heading counts
    get_macro_anchor,      # TOC + section drill for a specific anchor
    get_macro_indicators,  # local-DB CPI/IIP/PMI trend + full G-sec yield curve
    get_market_context,    # live VIX / USD-INR / Brent / 10Y G-sec + FII-DII flows
]


# -- Historical Analog Agent (Sprint 1) --

@tool(
    "get_setup_feature_vector",
    "Return the target stock's current 16-feature fingerprint: valuation (pe_trailing, "
    "pe_percentile_10y), quality (roce_current, roce_3yr_delta, revenue_cagr_3yr, opm_trend), "
    "ownership (promoter_pct, fii_pct/delta, mf_pct/delta, pledge_pct), technical "
    "(price_vs_sma200, delivery_pct_6m, rsi_14), and categoricals (industry, mcap_bucket). "
    "Use this to describe the setup you're pattern-matching.",
    {"symbol": str, "as_of_date": str},
    annotations=READ_ONLY,
)
async def get_setup_feature_vector(args):
    with ResearchDataAPI() as api:
        data = api.get_setup_feature_vector(args["symbol"], args.get("as_of_date"))
    return _with_dedup("get_setup_feature_vector",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_historical_analogs",
    "Retrieve top-K historical analogs for the target. Each analog is a past "
    "(symbol, quarter-end) point from the last 10 years in the same industry + "
    "mcap bucket whose feature vector is closest (z-scored Euclidean distance). "
    "Returns each analog's features + forward returns (3m/6m/12m absolute + excess "
    "vs sector/nifty) + outcome label (recovered | sideways | blew_up). Target's own "
    "rows within 2 years are excluded to prevent data leakage. Default k=20.",
    {"symbol": str, "k": int, "as_of_date": str},
    annotations=READ_ONLY,
)
async def get_historical_analogs(args):
    """Returns analogs + cohort metadata.

    Response keys: ``symbol``, ``as_of_date``, ``target_features``,
    ``analogs`` (list with per-row distance + forward returns + relaxation_level),
    ``analog_count``, ``relaxation_level`` (0/1/2), ``relaxation_label``
    (strict/industry_only/mcap_only), ``unique_symbols``, ``gross_count``.
    """
    with ResearchDataAPI() as api:
        data = api.get_historical_analogs(
            args["symbol"], args.get("k", 20), args.get("as_of_date"),
        )
    return _with_dedup("get_historical_analogs",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_analog_cohort_stats",
    "Aggregate base rates across the analog cohort (default k=50 for richer stats). "
    "Returns: gross_N, unique_symbols, informative_N_{3m,6m,12m} (rows whose forward "
    "window at that horizon has closed — cite this N for base rates, not gross_N), "
    "relaxation_level (0=strict industry+mcap, 1=industry_only, 2=mcap_only), "
    "per_horizon stats (median_return_pct + p10/p90 when informative_N>=5 else "
    "individual_outcomes list), recovery_rate_pct / blow_up_rate_pct / sideways_rate_pct. "
    "Use these as your empirical prior before making bull/base/bear calibration.",
    {"symbol": str, "k": int, "as_of_date": str},
    annotations=READ_ONLY,
)
async def get_analog_cohort_stats(args):
    with ResearchDataAPI() as api:
        data = api.get_analog_cohort_stats(
            args["symbol"], args.get("k", 50), args.get("as_of_date"),
        )
    return _with_dedup("get_analog_cohort_stats",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


HISTORICAL_ANALOG_AGENT_TOOLS = [
    get_setup_feature_vector,
    get_historical_analogs,
    get_analog_cohort_stats,
    # Plus shared context tools for understanding the target stock
    get_analytical_profile, get_company_context,
]


# ---------------------------------------------------------------------------
# F&O Positioning Agent (Sprint 3)
#
# Eligibility-gated derivatives positioning tools. Wraps ResearchDataAPI
# methods that read from the F&O ingestion tables (fno_universe,
# fut_oi_history, opt_oi_snapshot, fii_deriv_flow, futures_basis).
# ---------------------------------------------------------------------------


@tool(
    "get_fno_positioning",
    "Composite F&O positioning snapshot for an F&O-eligible stock. Returns "
    "futures positioning (current OI, OI percentile vs 90d, OI trend, basis %, "
    "5d OI change), options positioning (PCR OI + label, max-pain strike, ATM IV), "
    "FII derivative stance (index-fut net-long %, trend), and as-of date. "
    "If symbol is NOT F&O-eligible (not in fno_universe), returns "
    "{'fno_eligible': false, 'reason': 'symbol not in NSE F&O eligibility list'} — "
    "the agent should treat this as terminal: write status=empty and exit.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_fno_positioning(args):
    if _is_us_symbol(args["symbol"]):
        return _us_not_applicable("get_fno_positioning", "NSE F&O positioning", args["symbol"], args)
    with ResearchDataAPI() as api:
        data = api.get_fno_positioning(args["symbol"])
    if data is None:
        data = {"fno_eligible": False, "reason": "symbol not in NSE F&O eligibility list"}
    return _with_dedup("get_fno_positioning",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_oi_history",
    "Daily front-month futures OI + close + volume for the last N trading days "
    "(default 90). Use to assess OI build-up direction, momentum, and liquidity. "
    "Returns empty list for non-F&O symbols.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_oi_history(args):
    if _is_us_symbol(args["symbol"]):
        return _us_not_applicable("get_oi_history", "NSE F&O open-interest history", args["symbol"], args)
    with ResearchDataAPI() as api:
        data = api.get_oi_history(args["symbol"], args.get("days", 90))
    return _with_dedup("get_oi_history",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_option_chain_concentration",
    "Strike-wise CE/PE OI concentration for the front expiry — returns the highest "
    "call-OI strike (likely OI resistance), highest put-OI strike (likely OI "
    "support), max-pain strike, and totals. Returns null for non-F&O symbols or "
    "symbols with no option contracts in the latest bhavcopy.",
    {"symbol": str},
    annotations=READ_ONLY,
)
async def get_option_chain_concentration(args):
    if _is_us_symbol(args["symbol"]):
        return _us_not_applicable("get_option_chain_concentration", "NSE option-chain OI", args["symbol"], args)
    with ResearchDataAPI() as api:
        data = api.get_option_chain_concentration(args["symbol"])
    return _with_dedup("get_option_chain_concentration",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_fii_derivative_flow",
    "Market-wide FII derivative positioning over the last N trading days "
    "(default 30). Returns daily rows of index-fut long/short OI + net-long %, "
    "index-options CE/PE OI, stock-fut long/short OI + net-long %. Use this to "
    "cross-reference cash-segment FII flow with derivative positioning — divergence "
    "(e.g. FII reducing cash holdings while adding index shorts) is a signal-rich pattern.",
    {"days": int},
    annotations=READ_ONLY,
)
async def get_fii_derivative_flow(args):
    with ResearchDataAPI() as api:
        data = api.get_fii_derivative_flow(args.get("days", 30))
    return _with_dedup("get_fii_derivative_flow",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


@tool(
    "get_futures_basis",
    "Spot-futures basis (front month) trajectory over the last N trading days "
    "(default 30). basis_pct = (futures - spot) / spot * 100. Negative basis "
    "near expiry signals distress / forced selling; positive spike signals "
    "aggressive buying. Returns empty list for non-F&O symbols.",
    {"symbol": str, "days": int},
    annotations=READ_ONLY,
)
async def get_futures_basis(args):
    if _is_us_symbol(args["symbol"]):
        return _us_not_applicable("get_futures_basis", "NSE spot-futures basis", args["symbol"], args)
    with ResearchDataAPI() as api:
        data = api.get_futures_basis(args["symbol"], args.get("days", 30))
    return _with_dedup("get_futures_basis",
                       {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}, args)


FNO_POSITIONING_AGENT_TOOLS = [
    get_fno_positioning,
    get_oi_history,
    get_option_chain_concentration,
    get_fii_derivative_flow,
    get_futures_basis,
    # Plus shared context for cross-referencing cash-segment positioning
    get_company_context, get_ownership, get_market_context,
]


# --- is_error envelope flagging (Phase 0-A) ---
#
# Wrap every registered tool's handler exactly once so an error payload sets
# `is_error: True` on the result envelope (which the agent harness already
# reads). The same SdkMcpTool object can appear in multiple registries, so we
# dedup by id() and rely on the `_is_error_wrapped` sentinel for idempotency.
_ALL_TOOL_REGISTRIES = [
    RESEARCH_TOOLS,
    BUSINESS_AGENT_TOOLS,
    FINANCIAL_AGENT_TOOLS,
    OWNERSHIP_AGENT_TOOLS,
    VALUATION_AGENT_TOOLS,
    RISK_AGENT_TOOLS,
    TECHNICAL_AGENT_TOOLS,
    SECTOR_AGENT_TOOLS,
    NEWS_AGENT_TOOLS,
    MACRO_AGENT_TOOLS,
    HISTORICAL_ANALOG_AGENT_TOOLS,
    FNO_POSITIONING_AGENT_TOOLS,
]

_seen_tool_ids: set[int] = set()
for _registry in _ALL_TOOL_REGISTRIES:
    for _tool in _registry:
        if id(_tool) not in _seen_tool_ids:
            _seen_tool_ids.add(id(_tool))
            _wrap_handler_is_error(_tool)
