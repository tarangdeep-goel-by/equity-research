"""MCP tool definitions wrapping ResearchDataAPI for the research agent."""

from __future__ import annotations

import json

from claude_agent_sdk import tool

from flowtracker.research.data_api import ResearchDataAPI


# --- Core Financials ---


@tool(
    "get_quarterly_results",
    "Get quarterly P&L: revenue, expenses, operating profit, net income, EPS, margins. Returns up to 12 quarters.",
    {"symbol": str, "quarters": int},
)
async def get_quarterly_results(args):
    with ResearchDataAPI() as api:
        data = api.get_quarterly_results(args["symbol"], args.get("quarters", 12))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_annual_financials",
    "Get annual P&L + Balance Sheet + Cash Flow for up to 10 years. Revenue, profit, debt, FCF, etc.",
    {"symbol": str, "years": int},
)
async def get_annual_financials(args):
    with ResearchDataAPI() as api:
        data = api.get_annual_financials(args["symbol"], args.get("years", 10))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_screener_ratios",
    "Get efficiency ratios: debtor days, inventory days, cash conversion cycle, working capital days, ROCE%. Up to 10 years.",
    {"symbol": str, "years": int},
)
async def get_screener_ratios(args):
    with ResearchDataAPI() as api:
        data = api.get_screener_ratios(args["symbol"], args.get("years", 10))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Valuation ---


@tool(
    "get_valuation_snapshot",
    "Get latest valuation snapshot: price, PE, PB, EV/EBITDA, dividend yield, margins, market cap — 50+ fields.",
    {"symbol": str},
)
async def get_valuation_snapshot(args):
    with ResearchDataAPI() as api:
        data = api.get_valuation_snapshot(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_valuation_band",
    "Get PE (or other metric) percentile band over historical period. Shows where current valuation sits vs history.",
    {"symbol": str, "metric": str, "days": int},
)
async def get_valuation_band(args):
    with ResearchDataAPI() as api:
        data = api.get_valuation_band(
            args["symbol"],
            args.get("metric", "pe_trailing"),
            args.get("days", 2500),
        )
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_pe_history",
    "Get historical PE and price time series for charting. Up to ~7 years of daily data.",
    {"symbol": str, "days": int},
)
async def get_pe_history(args):
    with ResearchDataAPI() as api:
        data = api.get_pe_history(args["symbol"], args.get("days", 2500))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Ownership & Institutional ---


@tool(
    "get_shareholding",
    "Get quarterly ownership breakdown: FII%, DII%, MF%, Promoter%, Public%. Up to 12 quarters.",
    {"symbol": str, "quarters": int},
)
async def get_shareholding(args):
    with ResearchDataAPI() as api:
        data = api.get_shareholding(args["symbol"], args.get("quarters", 12))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_shareholding_changes",
    "Get latest quarter-over-quarter ownership changes by category (FII, DII, Promoter, etc.).",
    {"symbol": str},
)
async def get_shareholding_changes(args):
    with ResearchDataAPI() as api:
        data = api.get_shareholding_changes(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_insider_transactions",
    "Get SAST insider buy/sell trades: person name, category, quantity, value. Up to 1 year.",
    {"symbol": str, "days": int},
)
async def get_insider_transactions(args):
    with ResearchDataAPI() as api:
        data = api.get_insider_transactions(args["symbol"], args.get("days", 365))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_bulk_block_deals",
    "Get BSE bulk/block deals — large institutional trades with buyer/seller, qty, price.",
    {"symbol": str},
)
async def get_bulk_block_deals(args):
    with ResearchDataAPI() as api:
        data = api.get_bulk_block_deals(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_mf_holdings",
    "Get MF scheme holdings — which mutual fund schemes hold this stock, quantity, % of NAV.",
    {"symbol": str},
)
async def get_mf_holdings(args):
    with ResearchDataAPI() as api:
        data = api.get_mf_holdings(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_mf_holding_changes",
    "Get MF holding changes for this stock (latest month). Shows scheme-level additions/reductions.",
    {"symbol": str},
)
async def get_mf_holding_changes(args):
    with ResearchDataAPI() as api:
        data = api.get_mf_holding_changes(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Market Signals ---


@tool(
    "get_delivery_trend",
    "Get daily delivery % from bhavcopy — high delivery signals accumulation. Up to 30 days.",
    {"symbol": str, "days": int},
)
async def get_delivery_trend(args):
    with ResearchDataAPI() as api:
        data = api.get_delivery_trend(args["symbol"], args.get("days", 30))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_promoter_pledge",
    "Get quarterly promoter pledge % history. Rising pledge = risk signal.",
    {"symbol": str},
)
async def get_promoter_pledge(args):
    with ResearchDataAPI() as api:
        data = api.get_promoter_pledge(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Consensus ---


@tool(
    "get_consensus_estimate",
    "Get latest analyst consensus: target price, recommendation, forward PE, earnings growth estimate.",
    {"symbol": str},
)
async def get_consensus_estimate(args):
    with ResearchDataAPI() as api:
        data = api.get_consensus_estimate(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_earnings_surprises",
    "Get quarterly earnings surprises: actual vs estimate EPS, surprise %. Shows beat/miss history.",
    {"symbol": str},
)
async def get_earnings_surprises(args):
    with ResearchDataAPI() as api:
        data = api.get_earnings_surprises(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Macro Context ---


@tool(
    "get_macro_snapshot",
    "Get current macro indicators: VIX, USD/INR, Brent crude, 10Y G-sec yield.",
    {},
)
async def get_macro_snapshot(args):
    with ResearchDataAPI() as api:
        data = api.get_macro_snapshot()
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_fii_dii_streak",
    "Get current FII/DII buying/selling streak — consecutive days of net buy or sell.",
    {},
)
async def get_fii_dii_streak(args):
    with ResearchDataAPI() as api:
        data = api.get_fii_dii_streak()
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_fii_dii_flows",
    "Get daily FII/DII net flows (in crores) for recent period. Up to 30 days.",
    {"days": int},
)
async def get_fii_dii_flows(args):
    with ResearchDataAPI() as api:
        data = api.get_fii_dii_flows(args.get("days", 30))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Screener APIs (Phase 2) ---


@tool(
    "get_chart_data",
    "Get Screener chart time series. chart_type: 'price', 'pe', 'sales_margin', 'ev_ebitda', 'pbv', 'mcap_sales'.",
    {"symbol": str, "chart_type": str},
)
async def get_chart_data(args):
    with ResearchDataAPI() as api:
        data = api.get_chart_data(args["symbol"], args["chart_type"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_peer_comparison",
    "Get peer comparison table: CMP, P/E, MCap, ROCE%, etc. for sector peers of the given stock.",
    {"symbol": str},
)
async def get_peer_comparison(args):
    with ResearchDataAPI() as api:
        data = api.get_peer_comparison(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_shareholder_detail",
    "Get individual shareholder names and quarterly %: e.g. Vanguard, LIC, etc. Optionally filter by classification.",
    {"symbol": str, "classification": str},
)
async def get_shareholder_detail(args):
    with ResearchDataAPI() as api:
        data = api.get_shareholder_detail(
            args["symbol"], args.get("classification")
        )
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_expense_breakdown",
    "Get schedule sub-item breakdowns (e.g., Expenses -> Employee Cost, Raw Material). section: 'profit-loss', 'balance-sheet'.",
    {"symbol": str, "section": str},
)
async def get_expense_breakdown(args):
    with ResearchDataAPI() as api:
        data = api.get_expense_breakdown(
            args["symbol"], args.get("section", "profit-loss")
        )
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Filings & Info ---


@tool(
    "get_recent_filings",
    "Get recent BSE corporate filings for a stock. Returns filing type, date, subject, PDF link.",
    {"symbol": str, "limit": int},
)
async def get_recent_filings(args):
    with ResearchDataAPI() as api:
        data = api.get_recent_filings(args["symbol"], args.get("limit", 10))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_company_info",
    "Get basic company info: symbol, company name, and industry classification.",
    {"symbol": str},
)
async def get_company_info(args):
    with ResearchDataAPI() as api:
        data = api.get_company_info(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Company Profile & Documents ---


@tool(
    "get_company_profile",
    "Get company business description, key points, and Screener URL. Use to understand what the company does.",
    {"symbol": str},
)
async def get_company_profile(args):
    with ResearchDataAPI() as api:
        data = api.get_company_profile(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_company_documents",
    "Get concall transcript/PPT/recording URLs and annual report URLs. Optionally filter by doc_type: 'concall_transcript', 'concall_ppt', 'annual_report'.",
    {"symbol": str, "doc_type": str},
)
async def get_company_documents(args):
    with ResearchDataAPI() as api:
        data = api.get_company_documents(args["symbol"], args.get("doc_type"))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Business Profile (Vault) ---


@tool(
    "get_business_profile",
    "Read cached business profile from vault. Returns markdown content if exists, empty if not. Check this BEFORE doing web research.",
    {"symbol": str},
)
async def get_business_profile(args):
    from pathlib import Path
    symbol = args["symbol"].upper()
    path = Path.home() / "vault" / "stocks" / symbol / "profile.md"
    if path.exists():
        content = path.read_text()
        return {"content": [{"type": "text", "text": content}]}
    return {"content": [{"type": "text", "text": ""}]}


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
)
async def get_dcf_valuation(args):
    with ResearchDataAPI() as api:
        data = api.get_dcf_valuation(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_dcf_history",
    "Get historical DCF intrinsic value trajectory. Shows how fair value has changed over time.",
    {"symbol": str},
)
async def get_dcf_history(args):
    with ResearchDataAPI() as api:
        data = api.get_dcf_history(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_technical_indicators",
    "Get latest RSI, SMA-50, SMA-200, MACD, ADX. Use for entry timing context — NOT for buy/sell decisions alone.",
    {"symbol": str},
)
async def get_technical_indicators(args):
    with ResearchDataAPI() as api:
        data = api.get_technical_indicators(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_dupont_decomposition",
    "Decompose ROE into Net Profit Margin × Asset Turnover × Equity Multiplier (10yr history). Shows what's driving ROE — margin, efficiency, or leverage.",
    {"symbol": str},
)
async def get_dupont_decomposition(args):
    with ResearchDataAPI() as api:
        data = api.get_dupont_decomposition(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_key_metrics_history",
    "Get comprehensive per-share metrics and valuation ratios history (up to 10 years). Includes PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, etc.",
    {"symbol": str, "years": int},
)
async def get_key_metrics_history(args):
    with ResearchDataAPI() as api:
        data = api.get_key_metrics_history(args["symbol"], args.get("years", 10))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_financial_growth_rates",
    "Get pre-computed annual growth rates: revenue, EBITDA, net income, EPS, FCF. Includes 3yr, 5yr, 10yr CAGRs.",
    {"symbol": str},
)
async def get_financial_growth_rates(args):
    with ResearchDataAPI() as api:
        data = api.get_financial_growth_rates(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_analyst_grades",
    "Get analyst upgrade/downgrade history. Shows which firms are changing ratings and the direction — useful for sell-side sentiment momentum.",
    {"symbol": str},
)
async def get_analyst_grades(args):
    with ResearchDataAPI() as api:
        data = api.get_analyst_grades(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_price_targets",
    "Get individual analyst price targets with consensus mean, high, low. Shows analyst dispersion and conviction.",
    {"symbol": str},
)
async def get_price_targets(args):
    with ResearchDataAPI() as api:
        data = api.get_price_targets(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_fair_value",
    "Get combined fair value estimate from PE band + DCF + analyst consensus. Returns bear/base/bull range, margin of safety %, and signal (DEEP VALUE / UNDERVALUED / FAIR VALUE / EXPENSIVE).",
    {"symbol": str},
)
async def get_fair_value(args):
    with ResearchDataAPI() as api:
        data = api.get_fair_value(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Scoring ---


@tool(
    "get_composite_score",
    "Get 8-factor composite score (0-100) for a stock: ownership, insider, valuation, earnings, quality, delivery, estimates, risk. Each factor has a score, raw value, and explanation.",
    {"symbol": str},
)
async def get_composite_score(args):
    from flowtracker.screener_engine import ScreenerEngine
    from flowtracker.store import FlowStore

    with FlowStore() as store:
        engine = ScreenerEngine(store)
        score = engine.score_stock(args["symbol"])
    if score is None:
        return {"content": [{"type": "text", "text": "No scoring data available"}]}
    data = {
        "symbol": score.symbol,
        "composite_score": score.composite_score,
        "factors": [
            {"factor": f.factor, "score": f.score, "raw_value": f.raw_value, "detail": f.detail}
            for f in score.factors
        ],
    }
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Tool Registry ---

RESEARCH_TOOLS = [
    get_quarterly_results,
    get_annual_financials,
    get_screener_ratios,
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
]

# Subset for business research — qualitative + key financials for context
# Excludes: market signals (delivery, pledge), macro, FII/DII flows, bulk deals
BUSINESS_TOOLS = [
    # Qualitative context
    get_company_info,
    get_company_profile,
    get_company_documents,
    get_business_profile,
    save_business_profile,
    # Financial data (for backing claims with numbers and trends)
    get_quarterly_results,
    get_annual_financials,
    get_screener_ratios,
    get_valuation_snapshot,
    get_peer_comparison,
    get_expense_breakdown,
    # Analyst consensus
    get_consensus_estimate,
    get_earnings_surprises,
    # Chart data for trends
    get_chart_data,
]
