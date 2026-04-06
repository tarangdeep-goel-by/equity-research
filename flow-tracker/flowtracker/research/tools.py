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


@tool(
    "get_wacc_params",
    "Get WACC parameters for a stock: risk-free rate, equity risk premium, beta (Nifty regression), "
    "cost of equity (CAPM), cost of debt, debt/equity mix, and final WACC%. Used as discount rate for DCF.",
    {"symbol": str},
)
async def get_wacc_params(args):
    with ResearchDataAPI() as api:
        data = api.get_wacc_params(args["symbol"])
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
        data = api.get_insider_transactions(args["symbol"], args.get("days", 1825))
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
    "Get delivery % trend — weekly data up to 20 years from Screener charts. High delivery signals accumulation, low signals speculative churn. Default 90 days, set days=9999 for full history.",
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
    "Get raw schedule sub-item breakdowns from financial_schedules table (e.g., Expenses -> Employee Cost, Raw Material). section: 'profit-loss', 'balance-sheet', 'quarters', 'cash-flow'. For structured/analyzed views, use get_fundamentals with section: 'cost_structure', 'balance_sheet_detail', 'cash_flow_quality', or 'working_capital'.",
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


@tool(
    "get_earnings_quality",
    "Earnings quality analysis: CFO/PAT ratio, CFO/EBITDA ratio, accrual ratio (5-10Y trend). "
    "Signals high/low cash conversion quality. NOT available for banks/NBFCs (requires NPA data).",
    {"symbol": str},
)
async def get_earnings_quality(args):
    with ResearchDataAPI() as api:
        data = api.get_earnings_quality(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_piotroski_score",
    "Piotroski F-Score (0-9): profitability, leverage, operating efficiency. Adapted for BFSI (NIM proxy for gross margin). Uses split/bonus-adjusted shares for dilution check.",
    {"symbol": str},
)
async def get_piotroski_score(args):
    with ResearchDataAPI() as api:
        data = api.get_piotroski_score(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_beneish_score",
    "Beneish M-Score: earnings manipulation probability. 8-variable model. Skipped for BFSI. Returns null if any variable can't be computed (no defaults).",
    {"symbol": str},
)
async def get_beneish_score(args):
    with ResearchDataAPI() as api:
        data = api.get_beneish_score(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_reverse_dcf",
    "Reverse DCF: solve for implied growth rate that justifies current market cap. "
    "Uses FCFF model (WACC) for non-BFSI, FCFE model (Ke) for banks. "
    "Compares implied growth with historical 3Y/5Y revenue CAGR.",
    {"symbol": str},
)
async def get_reverse_dcf(args):
    with ResearchDataAPI() as api:
        data = api.get_reverse_dcf(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_capex_cycle",
    "CWIP/Capex tracking with phase detection (Investing/Commissioning/Harvesting/Mature). "
    "10Y trend of CWIP/NetBlock, asset turnover, capex intensity. Not applicable to BFSI.",
    {"symbol": str},
)
async def get_capex_cycle(args):
    with ResearchDataAPI() as api:
        data = api.get_capex_cycle(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_common_size_pl",
    "Common Size P&L: all expense items as %% of revenue (10Y trend). "
    "For BFSI, denominator is Total Income (interest earned + other income). "
    "Highlights biggest cost and fastest-growing cost category.",
    {"symbol": str},
)
async def get_common_size_pl(args):
    with ResearchDataAPI() as api:
        data = api.get_common_size_pl(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_revenue_estimates",
    "Consensus revenue estimates: avg/low/high for current and next quarter/year. "
    "Values in crores. Coverage limited to ~Nifty 100-150 stocks.",
    {"symbol": str},
)
async def get_revenue_estimates(args):
    with ResearchDataAPI() as api:
        data = api.get_revenue_estimates(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_growth_estimates",
    "Growth estimates: stock growth vs index growth for current/next quarter and year. "
    "Includes long-term growth (LTG) estimate. Coverage limited to ~Nifty 100-150 stocks.",
    {"symbol": str},
)
async def get_growth_estimates(args):
    with ResearchDataAPI() as api:
        data = api.get_growth_estimates(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_price_performance",
    "Price return vs Nifty 50 and sector index (1M/3M/6M/1Y). "
    "Price return only — excludes dividends. Uses local DB for stock prices, live yfinance for index.",
    {"symbol": str},
)
async def get_price_performance(args):
    with ResearchDataAPI() as api:
        data = api.get_price_performance(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_sector_kpis",
    "Sector-specific operational KPIs extracted from concall transcripts. "
    "Uses canonical field names per sector (14 sectors covered: banks, NBFCs, insurance, IT, pharma, "
    "FMCG, auto, cement, metals, real estate, telecom, chemicals, power, oil & gas). "
    "Returns per-quarter values + trends. Requires concall extraction to exist.",
    {"symbol": str},
)
async def get_sector_kpis(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_kpis(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_bfsi_metrics",
    "Bank/NBFC-specific metrics: NIM, ROA, Cost-to-Income, P/B, equity multiplier (5Y trend). "
    "Only for BFSI stocks — returns skipped for non-BFSI and insurance.",
    {"symbol": str},
)
async def get_bfsi_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_bfsi_metrics(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "get_analytical_profile",
    "Pre-computed analytical profile (updated weekly). Returns ALL metrics in ONE call: "
    "composite score (0-100), Piotroski F-Score (0-9), Beneish M-Score, earnings quality, "
    "Bernstein reverse DCF (implied growth + implied margin + 5x5 sensitivity matrix), "
    "capex cycle phase, common size P&L, BFSI metrics (NIM/ROA if bank), "
    "price performance (1M/3M/6M/1Y vs Nifty + sector). "
    "CALL THIS FIRST — drill into individual tools only for full 10Y history.",
    {"symbol": str},
)
async def get_analytical_profile(args):
    with ResearchDataAPI() as api:
        data = api.get_analytical_profile(args["symbol"])
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


@tool(
    "screen_stocks",
    "Screen ~600 Nifty index stocks by pre-computed analytical metrics. "
    "Pass filters dict with _min/_max suffixes or exact match. "
    "Examples: {\"f_score_min\": 7} for F-Score >= 7. "
    "{\"eq_signal\": \"high_quality\", \"composite_score_min\": 60} combines filters. "
    "Available: f_score, m_score, composite_score, eq_signal, rdcf_implied_growth, "
    "capex_phase, perf_1y_excess, is_bfsi, industry, m_score_signal.",
    {"filters": dict},
)
async def screen_stocks(args):
    with ResearchDataAPI() as api:
        data = api.screen_stocks(args["filters"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    "Unified financial data. section: 'quarterly_results' | 'annual_financials' | 'ratios' | 'quarterly_balance_sheet' | 'quarterly_cash_flow' | 'expense_breakdown' | 'growth_rates' | 'capital_allocation' | 'rate_sensitivity' | 'cagr_table' | 'cost_structure' | 'balance_sheet_detail' | 'cash_flow_quality' | 'working_capital' | ['section1', 'section2']",
    {"symbol": str, "section": str, "quarters": int, "years": int, "sub_section": str},
)
async def get_fundamentals(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_fundamentals_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
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
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_quality_scores",
    "Accounting & quality metrics. section: 'earnings_quality' | 'piotroski' | 'beneish' | 'dupont' | 'common_size' | 'capex_cycle' | 'bfsi' | 'insurance' | 'metals' | 'realestate' | 'telecom' | 'power' | 'sector_health' | 'subsidiary' | ['section1', 'section2']. "
    "BFSI routing: 'all' auto-skips non-applicable sections. 'subsidiary' returns consolidated-standalone diff for SOTP analysis.",
    {"symbol": str, "section": str},
)
async def get_quality_scores(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
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
                }
        else:
            data = _get_quality_scores_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_ownership",
    "Ownership & stakeholder data. section: 'shareholding' | 'changes' | 'insider' | 'bulk_block' | 'mf_holdings' | 'mf_changes' | 'shareholder_detail' | 'promoter_pledge' | ['section1', 'section2']",
    {"symbol": str, "section": str, "quarters": int, "days": int, "classification": str},
)
async def get_ownership(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_ownership_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "shareholding": api.get_shareholding(symbol, args.get("quarters", 12)),
                "changes": api.get_shareholding_changes(symbol),
                "insider": api.get_insider_transactions(symbol, args.get("days", 1825)),
                "bulk_block": api.get_bulk_block_deals(symbol),
                "mf_holdings": api.get_mf_holdings(symbol),
                "mf_changes": api.get_mf_holding_changes(symbol),
                "shareholder_detail": api.get_shareholder_detail(symbol, args.get("classification")),
                "promoter_pledge": api.get_promoter_pledge(symbol),
            }
        else:
            data = _get_ownership_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    "Valuation metrics & history. section: 'snapshot' | 'band' | 'pe_history' | 'key_metrics' | 'wacc' (WACC params: beta, cost of equity/debt, discount rate) | 'sotp' (listed subsidiaries for SOTP valuation) | ['section1', 'section2']",
    {"symbol": str, "section": str, "metric": str, "days": int, "years": int},
)
async def get_valuation(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
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
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
)
async def get_fair_value_analysis(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
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
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_peer_sector",
    "Peer comparison & sector data. section: 'peer_table' | 'peer_metrics' | 'peer_growth' | 'valuation_matrix' | 'benchmarks' | 'sector_overview' | 'sector_flows' | 'sector_valuations' | ['section1', 'section2']",
    {"symbol": str, "section": str, "metric": str},
)
async def get_peer_sector(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_peer_sector_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
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
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
)
async def get_estimates(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
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
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_market_context",
    "Market signals & macro. section: 'delivery' | 'macro' | 'fii_dii_streak' | 'fii_dii_flows' | 'technicals' | 'price_performance' | ['section1', 'section2']",
    {"symbol": str, "section": str, "days": int},
)
async def get_market_context(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_market_context_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "delivery": api.get_delivery_trend(symbol, args.get("days", 30)),
                "macro": api.get_macro_snapshot(),
                "fii_dii_streak": api.get_fii_dii_streak(),
                "fii_dii_flows": api.get_fii_dii_flows(args.get("days", 30)),
                "technicals": api.get_technical_indicators(symbol),
                "price_performance": api.get_price_performance(symbol),
            }
        else:
            data = _get_market_context_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
        return api.get_concall_insights(symbol)
    elif section == "sector_kpis":
        return api.get_sector_kpis(symbol)
    elif section == "filings":
        return api.get_recent_filings(symbol, args.get("limit", 10))
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_company_context",
    "Company info, profile & documents. section: 'info' | 'profile' | 'documents' | 'business_profile' | 'concall_insights' | 'sector_kpis' | 'filings' | ['section1', 'section2']",
    {"symbol": str, "section": str, "doc_type": str, "limit": int},
)
async def get_company_context(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
    with ResearchDataAPI() as api:
        if isinstance(section, list):
            data = {s: _get_company_context_section(api, symbol, s, args) for s in section}
        elif section == "all":
            data = {
                "info": api.get_company_info(symbol),
                "profile": api.get_company_profile(symbol),
                "documents": api.get_company_documents(symbol, args.get("doc_type")),
                "business_profile": _get_company_context_section(api, symbol, "business_profile", args),
                "concall_insights": api.get_concall_insights(symbol),
                "sector_kpis": api.get_sector_kpis(symbol),
                "filings": api.get_recent_filings(symbol, args.get("limit", 10)),
            }
        else:
            data = _get_company_context_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


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
    else:
        return {"error": f"Unknown section: {section}"}


@tool(
    "get_events_actions",
    "Events, dividends & corporate actions. section: 'events' | 'dividends' | 'corporate_actions' | 'adjusted_eps' | 'catalysts' | ['section1', 'section2']",
    {"symbol": str, "section": str, "years": int, "quarters": int, "days": int},
)
async def get_events_actions(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
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
            }
        else:
            data = _get_events_actions_section(api, symbol, section, args)
        if isinstance(data, dict) and "error" not in data:
            data = _add_freshness_meta(data, api, symbol)
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- News ---


@tool(
    "get_stock_news",
    "Get recent news articles for a stock from Google News RSS + yfinance. "
    "Returns up to 100 articles from the last N days (default 90). "
    "Pre-filtered to remove market commentary — focuses on business events, "
    "catalysts, regulatory actions, M&A, management changes. "
    "Each article has: title, source, date, url, summary.",
    {"symbol": str, "days": int},
)
async def get_stock_news(args):
    with ResearchDataAPI() as api:
        data = api.get_stock_news(args["symbol"], args.get("days", 90))
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}


# --- Tool Registry ---

# V2 macro-tools (10 consolidated) + 6 standalone = 16 agent-facing tools
RESEARCH_TOOLS_V2 = [
    get_fundamentals, get_quality_scores, get_ownership, get_valuation,
    get_fair_value_analysis, get_peer_sector, get_estimates,
    get_market_context, get_company_context, get_events_actions,
    get_analytical_profile, render_chart, get_composite_score,
    screen_stocks, save_business_profile, get_chart_data,
]

# Individual tools kept for CLI `flowtrack research data <tool_name>` and monolith agent
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
    get_piotroski_score,
    get_reverse_dcf, get_capex_cycle, get_common_size_pl,
    get_revenue_estimates, get_growth_estimates, get_price_performance,
    get_sector_kpis,
    get_analytical_profile, screen_stocks,
    get_wacc_params,
]

# V1 agent registries (BUSINESS_TOOLS, *_AGENT_TOOLS, _PEER_TOOLS) removed — see *_AGENT_TOOLS_V2 below

# --- V2 Agent Tool Registries (macro-tools) ---

BUSINESS_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context, get_fundamentals,
    get_peer_sector, get_estimates, get_events_actions,
    get_valuation, get_chart_data, save_business_profile, render_chart,
]

FINANCIAL_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context, get_fundamentals,
    get_quality_scores, get_valuation, get_peer_sector,
    get_estimates, get_events_actions, get_fair_value_analysis,
    get_chart_data, render_chart,
]

OWNERSHIP_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_ownership, get_market_context,
    get_peer_sector, get_company_context, get_estimates,
    get_fundamentals, render_chart,
]

VALUATION_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_valuation, get_fair_value_analysis,
    get_estimates, get_peer_sector, get_events_actions,
    get_company_context, get_quality_scores, get_market_context,
    get_chart_data, render_chart,
]

RISK_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_composite_score, get_fundamentals,
    get_quality_scores, get_ownership, get_market_context,
    get_peer_sector, get_company_context, get_events_actions,
    get_estimates, render_chart,
]

TECHNICAL_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_market_context, get_valuation,
    get_ownership, get_peer_sector, get_chart_data, render_chart,
]

SECTOR_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context, get_peer_sector,
    get_market_context, get_fundamentals, get_estimates,
    get_valuation, get_chart_data, render_chart,
]

NEWS_AGENT_TOOLS_V2 = [
    get_analytical_profile, get_company_context,
    get_stock_news, get_events_actions,
]
