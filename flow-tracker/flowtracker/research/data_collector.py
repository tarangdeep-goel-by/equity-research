"""Collect all fundamentals data for a symbol from the store."""

from __future__ import annotations

import json
from collections import defaultdict

from flowtracker.store import FlowStore
from flowtracker.utils import _clean


def apply_screener_charts(data: dict) -> None:
    """Populate pe_chart and price_chart from Screener API data.

    Call this AFTER setting data["screener_charts"] from the fetch phase.
    Screener is the sole source for chart data — no yfinance fallback.
    Mutates data in place.
    """
    sc = data.get("screener_charts", {})
    sc_pe = sc.get("pe_chart", {})
    sc_price = sc.get("price_chart", {})

    if sc_pe and "PE" in sc_pe:
        pe_points = sc_pe["PE"]  # [[date, pe], ...]
        data["pe_chart"] = {
            "dates": [p[0] for p in pe_points],
            "pe_vals": [p[1] for p in pe_points],
            "price_vals": [],  # backfilled from price_chart below
        }
        for label in sc_pe:
            if "Median PE" in label:
                try:
                    data["pe_median_screener"] = float(label.split("=")[1].strip())
                except (IndexError, ValueError):
                    pass

    if sc_price:
        price_key = [k for k in sc_price if "Price" in k]
        dma50_key = [k for k in sc_price if "50 DMA" in k]
        dma200_key = [k for k in sc_price if "200 DMA" in k]
        vol_key = [k for k in sc_price if "Volume" in k]

        price_data = sc_price[price_key[0]] if price_key else []
        data["price_chart"] = {
            "dates": [p[0] for p in price_data],
            "prices": [float(p[1]) for p in price_data],
            "dma_50": [float(p[1]) for p in sc_price[dma50_key[0]]] if dma50_key else [],
            "dma_200": [float(p[1]) for p in sc_price[dma200_key[0]]] if dma200_key else [],
            "volumes": [int(p[1]) for p in sc_price[vol_key[0]]] if vol_key else [],
        }
        # Backfill pe_chart price_vals from price data
        if data["pe_chart"]["dates"] and price_data:
            price_map = {p[0]: float(p[1]) for p in price_data}
            data["pe_chart"]["price_vals"] = [
                price_map.get(d, None) for d in data["pe_chart"]["dates"]
            ]


def collect_fundamentals_data(symbol: str) -> dict:
    """Pull all stored data for a symbol into a single dict for report rendering.

    Data sources:
        - Screener.in (via store): quarterly_results, annual_financials, screener_ratios
        - Screener.in (live, injected later): charts, growth_rates, documents
        - yfinance (via store): valuation_latest (beta, margins, cash/debt), consensus
        - NSE (via store): shareholding, mf_scheme_holdings
    """
    symbol = symbol.upper()
    data: dict = {"symbol": symbol}

    with FlowStore() as s:
        # Valuation snapshot — latest only (for live ratios: beta, margins, cash/debt)
        # P/E chart data comes from Screener API, NOT from this table
        hist = s.get_valuation_history(symbol, days=7)
        if hist:
            data["valuation_latest"] = _clean(hist[-1].model_dump())
        else:
            data["valuation_latest"] = {}

        # Quarterly results (last 20 quarters) — source: Screener.in
        qr = s.get_quarterly_results(symbol, limit=20)
        data["quarterly_results"] = _clean([q.model_dump() for q in qr])

        # Annual financials (last 10 years) — source: Screener.in
        af = s.get_annual_financials(symbol, limit=10)
        data["annual_financials"] = _clean([a.model_dump() for a in af])

        # Consensus estimates — source: yfinance (Screener doesn't have this)
        est = s.get_estimate_latest(symbol)
        data["consensus"] = _clean(est.model_dump()) if est else {}

        # Earnings surprises — source: yfinance
        surp = s.get_surprises(symbol)
        data["surprises"] = _clean([su.model_dump() for su in surp])

        # Screener ratios (efficiency metrics) — source: Screener.in
        sr = s.get_screener_ratios(symbol, limit=12)
        data["screener_ratios"] = _clean([r.model_dump() for r in sr])

        # Industry and company name from index constituents
        constituents = s.get_index_constituents()
        match = [c for c in constituents if c.symbol == symbol]
        if match:
            data["industry"] = match[0].industry
            data["company_name"] = match[0].company_name
        else:
            data["industry"] = "Unknown"
            data["company_name"] = symbol

        # Shareholding (latest quarter) — source: NSE
        changes = s.get_shareholding_changes(symbol)
        ownership = {}
        for c in changes:
            ownership[c.category.lower()] = {
                "pct": c.curr_pct,
                "change": c.change_pct,
            }
        data["shareholding"] = ownership

        # Shareholding history (8 quarters × categories) — source: NSE
        sh_records = s.get_shareholding(symbol, limit=8)
        sh_by_quarter: dict[str, dict[str, float]] = defaultdict(dict)
        for rec in sh_records:
            sh_by_quarter[rec.quarter_end][rec.category.lower()] = rec.percentage
        sh_quarters = sorted(sh_by_quarter.keys(), reverse=True)
        data["shareholding_history"] = [
            {"quarter": q, **sh_by_quarter[q]} for q in sh_quarters
        ]

        # MF scheme holdings — source: AMFI (5 AMCs)
        mf_holdings = s.get_mf_stock_holdings(symbol)
        data["mf_holdings"] = _clean([
            {
                "scheme": h.scheme_name,
                "amc": h.amc,
                "qty": h.quantity,
                "value_cr": h.market_value_cr,
                "pct_nav": h.pct_of_nav,
            }
            for h in mf_holdings[:30]
        ])

    # Derived values for template convenience
    v = data.get("valuation_latest", {})
    consensus = data.get("consensus", {})
    price = v.get("price", 0)
    mcap = v.get("market_cap", 0)

    data["price"] = price
    data["mcap_cr"] = round(mcap) if mcap else 0  # already in crores
    data["pe_trailing"] = v.get("pe_trailing")
    data["pe_forward"] = v.get("pe_forward")

    # PE band/percentile — will be overridden by Screener median if available
    data["pe_median"] = 0
    data["pe_percentile"] = None
    data["pe_observations"] = 0
    data["pe_period_start"] = ""
    data["pe_period_end"] = ""

    # Analyst upside — source: yfinance (Screener doesn't have this)
    target_mean = consensus.get("target_mean", 0)
    data["target_mean"] = target_mean
    data["upside_pct"] = round((target_mean / price - 1) * 100, 1) if price and target_mean else 0
    data["num_analysts"] = consensus.get("num_analysts", 0)

    # ROCE from Screener ratios
    ratios = data.get("screener_ratios", [])
    data["roce"] = ratios[0].get("roce_pct") if ratios else None

    # Shares and EPS
    shares = v.get("shares_outstanding", 0)
    data["shares"] = shares
    af_list = data.get("annual_financials", [])
    if af_list:
        ni = af_list[0].get("net_income", 0)
        data["eps_annual"] = round(ni / (shares / 1e7), 1) if shares and ni else 0
        data["ni_annual"] = ni
    else:
        data["eps_annual"] = 0
        data["ni_annual"] = 0

    # Quarterly chart data (oldest first) — source: Screener.in quarterly results
    qr_reversed = list(reversed(data["quarterly_results"][:13]))
    data["qr_chart"] = {
        "dates": [q["quarter_end"] for q in qr_reversed],
        "revenues": [q["revenue"] for q in qr_reversed],
        "net_incomes": [q["net_income"] for q in qr_reversed],
        "opms": [
            round(q["operating_margin"] * 100, 1) if q.get("operating_margin") else None
            for q in qr_reversed
        ],
    }

    # PE chart + price chart — empty, populated by apply_screener_charts()
    # Source: Screener chart API (TTM P/E, daily price+DMA+volume)
    data["pe_chart"] = {"dates": [], "pe_vals": [], "price_vals": []}
    data["price_chart"] = {}

    # Annual financials — full 10yr (oldest first for table)
    data["af_table"] = list(reversed(af_list[:10]))

    # Compute derived P&L fields for af_table
    for a in data["af_table"]:
        a.setdefault("operating_profit", None)
        a.setdefault("total_expenses", None)
        a.setdefault("opm_pct", None)
        a.setdefault("tax_pct_annual", None)
        a.setdefault("dividend_payout_pct", None)

        pbt = a.get("profit_before_tax")
        interest = a.get("interest") or 0
        dep = a.get("depreciation") or 0
        oi = a.get("other_income") or 0
        rev = a.get("revenue")
        tax = a.get("tax")
        ni = a.get("net_income")
        div = a.get("dividend_amount")

        if pbt is not None:
            op = pbt + interest + dep - oi
            a["operating_profit"] = round(op, 1)
            if rev:
                a["opm_pct"] = round(op / rev * 100, 1)
            a["total_expenses"] = round(rev - op, 1) if rev else None

        if tax is not None and pbt and pbt != 0:
            a["tax_pct_annual"] = round(tax / pbt * 100, 1)

        if div is not None and ni and ni > 0:
            a["dividend_payout_pct"] = round(div / ni * 100, 1)

    # TTM (trailing twelve months) — sum of last 4 quarters
    qr_list = data.get("quarterly_results", [])[:4]
    if len(qr_list) == 4:
        ttm: dict = {}
        sum_keys = [
            "revenue", "expenses", "operating_income", "other_income",
            "interest", "depreciation", "profit_before_tax", "net_income", "eps",
        ]
        for key in sum_keys:
            vals = [q.get(key) for q in qr_list if q.get(key) is not None]
            ttm[key] = round(sum(vals), 1) if vals else None
        ttm["operating_profit"] = ttm.pop("operating_income", None)
        ttm["total_expenses"] = (
            round(ttm["revenue"] - ttm["operating_profit"], 1)
            if ttm.get("revenue") and ttm.get("operating_profit")
            else None
        )
        if ttm.get("operating_profit") and ttm.get("revenue"):
            ttm["opm_pct"] = round(ttm["operating_profit"] / ttm["revenue"] * 100, 1)
        if ttm.get("profit_before_tax") and ttm["profit_before_tax"] != 0:
            if ttm.get("net_income") is not None:
                ttm["tax"] = round(ttm["profit_before_tax"] - ttm["net_income"], 1)
                ttm["tax_pct_annual"] = round(
                    ttm["tax"] / ttm["profit_before_tax"] * 100, 1
                )
        data["ttm"] = ttm
    else:
        data["ttm"] = {}

    # Ratios (oldest first for table)
    data["ratios_table"] = list(reversed(ratios))

    # Full quarterly results table (13Q, oldest first)
    data["quarterly_full"] = list(reversed(data["quarterly_results"][:13]))

    # Growth rates — placeholder, overridden by Screener data in research_commands.py
    data["growth_rates"] = {}

    # ROE history (from Screener annual financials, oldest first)
    roe_history = []
    for a in reversed(af_list):
        ni = a.get("net_income")
        eq_cap = a.get("equity_capital")
        reserves = a.get("reserves")
        fy = a.get("fiscal_year_end", "")[:4]
        if ni and eq_cap is not None and reserves is not None:
            equity = eq_cap + reserves
            roe_val = round(ni / equity * 100, 1) if equity > 0 else None
        else:
            roe_val = None
        roe_history.append({"year": fy, "roe": roe_val})
    data["roe_history"] = roe_history

    return data
