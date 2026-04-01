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
    "Get 10 years of annual financials. P&L: revenue, expenses, operating profit, net income, EPS. "
    "Balance Sheet: equity capital, reserves, borrowings, total assets, net block, CWIP, investments, receivables, inventory, cash. "
    "Cash Flow: CFO, CFI, CFF, net cash flow. Also includes: expense breakdown (raw material, employee, power, selling costs), shares outstanding, dividend, and price.",
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


@tool(
    "get_quarterly_balance_sheet",
    "Get quarterly balance sheet from yfinance: total assets, debt, equity, cash, investments, shares outstanding. "
    "Up to 8 quarters. Values in crores. Not available for all stocks (some return empty).",
    {"symbol": str, "quarters": int},
)
async def get_quarterly_balance_sheet(args):
    with ResearchDataAPI() as api:
        data = api.get_quarterly_balance_sheet(args["symbol"], args.get("quarters", 8))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_quarterly_cash_flow",
    "Get quarterly cash flow from yfinance: operating CF, free CF, capex, investing CF, financing CF, working capital changes. "
    "Up to 8 quarters. Values in crores. NOT available for banks or many Indian stocks — if empty, use annual CF from get_annual_financials.",
    {"symbol": str, "quarters": int},
)
async def get_quarterly_cash_flow(args):
    with ResearchDataAPI() as api:
        data = api.get_quarterly_cash_flow(args["symbol"], args.get("quarters", 8))
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


@tool(
    "get_estimate_revisions",
    "Get EPS estimate revision trends: current vs 7/30/60/90 day ago estimates, plus analyst upgrade/downgrade counts. "
    "Shows if consensus is moving up or down for current quarter, next quarter, current FY, and next FY.",
    {"symbol": str},
)
async def get_estimate_revisions(args):
    with ResearchDataAPI() as api:
        data = api.get_estimate_revisions(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_estimate_momentum",
    "Get computed estimate momentum signal: score (0-1), direction (positive/neutral/negative), "
    "and narrative summary of revision trends. Rising estimates = fundamental momentum.",
    {"symbol": str},
)
async def get_estimate_momentum(args):
    with ResearchDataAPI() as api:
        data = api.get_estimate_momentum(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Events & Calendar ---


@tool(
    "get_events_calendar",
    "Get upcoming events: next earnings date (with days until), ex-dividend date, consensus EPS and revenue estimates. "
    "Live fetch — always current. Check before any research to set temporal context.",
    {"symbol": str},
)
async def get_events_calendar(args):
    with ResearchDataAPI() as api:
        data = api.get_events_calendar(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Dividend History ---


@tool(
    "get_dividend_history",
    "Get annual dividend per share, payout ratio, and yield history (up to 10 years). "
    "Computed from corporate actions + annual financials. Shows dividend growth trends.",
    {"symbol": str, "years": int},
)
async def get_dividend_history(args):
    with ResearchDataAPI() as api:
        data = api.get_dividend_history(args["symbol"], args.get("years", 10))
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


# --- Peer Benchmarking ---


@tool(
    "get_peer_metrics",
    "Get FMP key financial metrics (PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, debt/equity, margins) for the subject company and all its peers. Returns subject data, individual peer data, and peer count.",
    {"symbol": str},
)
async def get_peer_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_peer_metrics(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_peer_growth",
    "Get FMP growth rates (revenue, EBITDA, net income, EPS, FCF growth + 3yr/5yr CAGRs) for the subject company and all its peers.",
    {"symbol": str},
)
async def get_peer_growth(args):
    with ResearchDataAPI() as api:
        data = api.get_peer_growth(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_valuation_matrix",
    "Get multi-metric valuation comparison matrix for a stock vs all its peers. Returns PE, PB, EV/EBITDA, EV/Sales, margins, ROE, growth for subject + all peers, with sector medians and subject percentile ranks. Use this for relative valuation analysis.",
    {"symbol": str},
)
async def get_valuation_matrix(args):
    with ResearchDataAPI() as api:
        data = api.get_valuation_matrix(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_sector_benchmarks",
    "Get computed sector benchmark statistics for a metric: subject value, sector median, P25/P75, min/max, and the subject's percentile rank. If no metric specified, returns all benchmarks.",
    {"symbol": str, "metric": str},
)
async def get_sector_benchmarks(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_benchmarks(args["symbol"], args.get("metric"))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


get_concall_insights = tool(
    "get_concall_insights",
    "Get pre-extracted concall insights from the vault: 4 quarters of operational metrics, financial metrics, management commentary, subsidiary updates, risk flags, and cross-quarter narrative themes. This is structured data already extracted from concall transcripts — much richer and faster than reading raw PDFs.",
    {"symbol": str},
)


@get_concall_insights
async def get_concall_insights(args):
    with ResearchDataAPI() as api:
        data = api.get_concall_insights(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


render_chart = tool(
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


@render_chart
async def render_chart(args):
    from flowtracker.research.charts import render_chart as _render
    result = _render(args["symbol"], args["chart_type"])
    return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}


@tool(
    "get_corporate_actions",
    "Get all corporate actions (bonuses, stock splits, dividends, spinoffs, buybacks) for a stock. Shows action type, date, ratio/multiplier, and source. Use to understand share capital changes and adjust historical per-share metrics.",
    {"symbol": str},
)
async def get_corporate_actions(args):
    with ResearchDataAPI() as api:
        data = api.get_corporate_actions(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_adjusted_eps",
    "Get quarterly EPS adjusted for all stock splits and bonuses. Returns both raw and adjusted EPS so you can see the true earnings trend without per-share discontinuities. Essential for any stock that has had a split or bonus.",
    {"symbol": str, "quarters": int},
)
async def get_adjusted_eps(args):
    with ResearchDataAPI() as api:
        data = api.get_adjusted_eps(args["symbol"], args.get("quarters", 12))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_financial_projections",
    "Get 3-year bear/base/bull financial projections. Projects revenue, EBITDA, net income, and EPS "
    "based on historical growth trends and margin patterns. Returns assumptions, projections for 3 scenarios, "
    "and implied fair values at different PE multiples. The agent should refine assumptions using concall "
    "guidance and sector context — these are starting estimates, not final answers.",
    {"symbol": str},
)
async def get_financial_projections(args):
    with ResearchDataAPI() as api:
        data = api.get_financial_projections(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Sector Analysis ---


@tool(
    "get_sector_overview_metrics",
    "Get industry-level overview: stock count, total market cap, median PE/PB/ROCE, "
    "valuation range, top stocks. Looks up the industry from the given stock's classification.",
    {"symbol": str},
)
async def get_sector_overview_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_overview_metrics(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_sector_flows",
    "Get aggregate institutional ownership changes across all stocks in the subject's industry. "
    "Shows which stocks MFs are accumulating, which they're exiting, and net sector flow direction.",
    {"symbol": str},
)
async def get_sector_flows(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_flows(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_sector_valuations",
    "Get all stocks in the subject's industry ranked by market cap, with key metrics: "
    "PE, ROCE, FII%, MF%, price change. Shows where the subject ranks among peers.",
    {"symbol": str},
)
async def get_sector_valuations(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_valuations(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_upcoming_catalysts",
    "Get upcoming events that could move the stock: earnings dates, board meetings, "
    "ex-dividend, RBI policy, estimated results dates. Returns events within the next "
    "N days sorted by date.",
    {"symbol": str, "days": int},
)
async def get_upcoming_catalysts(args):
    with ResearchDataAPI() as api:
        data = api.get_upcoming_catalysts(args["symbol"], args.get("days", 90))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


_PEER_TOOLS = [get_peer_metrics, get_peer_growth, get_valuation_matrix, get_sector_benchmarks]


# --- Tool Registry ---

RESEARCH_TOOLS = [
    get_quarterly_results,
    get_annual_financials,
    get_screener_ratios,
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
    get_estimate_momentum,
    # Events & calendar
    get_events_calendar,
    # Dividend history
    get_dividend_history,
    # Chart data for trends
    get_chart_data,
]

# --- Specialist Agent Tool Registries ---

BUSINESS_AGENT_TOOLS = [
    get_company_info, get_company_profile, get_company_documents,
    get_business_profile, save_business_profile,
    get_concall_insights,  # pre-extracted concall data (4 quarters)
    get_quarterly_results, get_annual_financials, get_screener_ratios,
    get_valuation_snapshot, get_peer_comparison, get_expense_breakdown,
    get_consensus_estimate, get_earnings_surprises,
    get_upcoming_catalysts,
    render_chart,  # generate PNG charts for embedding
    *_PEER_TOOLS,
]  # 19 tools

FINANCIAL_AGENT_TOOLS = [
    get_company_info, get_quarterly_results, get_annual_financials,
    get_screener_ratios, get_quarterly_balance_sheet, get_quarterly_cash_flow,
    get_expense_breakdown, get_financial_growth_rates,
    get_dupont_decomposition, get_key_metrics_history,
    get_chart_data, get_earnings_surprises,
    get_concall_insights,  # management commentary on margins, guidance, segment performance
    get_corporate_actions, get_adjusted_eps,
    get_financial_projections,
    get_estimate_revisions, get_estimate_momentum,
    get_dividend_history,
    render_chart,
    *_PEER_TOOLS,
]  # 21 tools

OWNERSHIP_AGENT_TOOLS = [
    get_shareholding, get_shareholding_changes, get_insider_transactions,
    get_bulk_block_deals, get_mf_holdings, get_mf_holding_changes,
    get_shareholder_detail, get_promoter_pledge, get_delivery_trend,
    get_fii_dii_flows, get_fii_dii_streak,
    get_sector_benchmarks,
    render_chart,
]  # 13 tools — no concall (ownership data comes from filings, not concalls)

VALUATION_AGENT_TOOLS = [
    get_valuation_snapshot, get_valuation_band, get_pe_history,
    get_fair_value, get_dcf_valuation, get_dcf_history,
    get_price_targets, get_analyst_grades, get_peer_comparison,
    get_chart_data, get_consensus_estimate,
    get_concall_insights,  # management guidance affects forward valuation
    get_corporate_actions, get_adjusted_eps,
    get_financial_projections,
    get_estimate_revisions, get_estimate_momentum,
    get_events_calendar,
    get_dividend_history,
    get_upcoming_catalysts,
    render_chart,
    *_PEER_TOOLS,
]

RISK_AGENT_TOOLS = [
    get_quarterly_results, get_annual_financials, get_quarterly_balance_sheet,
    get_promoter_pledge,
    get_insider_transactions, get_macro_snapshot, get_fii_dii_streak,
    get_composite_score, get_earnings_surprises, get_recent_filings,
    get_valuation_snapshot, get_peer_comparison,
    get_concall_insights,  # red flags, evasive answers, risk acknowledgments from management
    get_corporate_actions,  # share capital changes are a risk factor
    get_upcoming_catalysts,
    *_PEER_TOOLS,
]  # 16 tools

TECHNICAL_AGENT_TOOLS = [
    get_technical_indicators, get_chart_data, get_delivery_trend,
    get_valuation_snapshot, get_bulk_block_deals,
    get_fii_dii_flows, get_fii_dii_streak,
    get_sector_benchmarks,
    render_chart,  # price + delivery charts
]  # 9 tools

SECTOR_AGENT_TOOLS = [
    get_company_info, get_sector_overview_metrics, get_sector_flows,
    get_sector_valuations, get_peer_comparison,
    get_peer_metrics, get_peer_growth, get_sector_benchmarks,
    get_macro_snapshot, get_fii_dii_flows, get_fii_dii_streak,
    render_chart,
]  # 12 tools
