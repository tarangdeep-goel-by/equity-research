"""Collect all fundamentals data for a symbol from the store."""

from __future__ import annotations

import json

from flowtracker.store import FlowStore


def _clean(obj):
    """Force all values to JSON-serializable Python types (handles numpy, Decimal, etc.)."""
    return json.loads(json.dumps(obj, default=str))


def collect_fundamentals_data(symbol: str) -> dict:
    """Pull all stored data for a symbol into a single dict for report rendering.

    Returns a dict with keys:
        valuation_latest, pe_history, pe_band, quarterly_results,
        annual_financials, consensus, surprises, screener_ratios,
        industry, company_name, shareholding
    """
    symbol = symbol.upper()
    data: dict = {"symbol": symbol}

    with FlowStore() as s:
        # Valuation snapshot (latest + history for P/E chart)
        hist = s.get_valuation_history(symbol, days=2500)
        if hist:
            data["valuation_latest"] = _clean(hist[-1].model_dump())
            data["pe_history"] = _clean([
                {"date": h.date, "pe": h.pe_trailing, "price": h.price}
                for h in hist
                if h.pe_trailing
            ])
        else:
            data["valuation_latest"] = {}
            data["pe_history"] = []

        # Valuation band (P/E percentile)
        band = s.get_valuation_band(symbol, "pe_trailing", days=2500)
        data["pe_band"] = _clean(band.model_dump()) if band else {}

        # Quarterly results (last 20 quarters)
        qr = s.get_quarterly_results(symbol, limit=20)
        data["quarterly_results"] = _clean([q.model_dump() for q in qr])

        # Annual financials (last 10 years)
        af = s.get_annual_financials(symbol, limit=10)
        data["annual_financials"] = _clean([a.model_dump() for a in af])

        # Consensus estimates
        est = s.get_estimate_latest(symbol)
        data["consensus"] = _clean(est.model_dump()) if est else {}

        # Earnings surprises
        surp = s.get_surprises(symbol)
        data["surprises"] = _clean([su.model_dump() for su in surp])

        # Screener ratios (efficiency metrics)
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

        # Shareholding (latest quarter)
        changes = s.get_shareholding_changes(symbol)
        ownership = {}
        for c in changes:
            ownership[c.category.lower()] = {
                "pct": c.curr_pct,
                "change": c.change_pct,
            }
        data["shareholding"] = ownership

    # Derived values for template convenience
    v = data.get("valuation_latest", {})
    band = data.get("pe_band", {})
    consensus = data.get("consensus", {})
    price = v.get("price", 0)
    mcap = v.get("market_cap", 0)

    data["price"] = price
    data["mcap_cr"] = round(mcap / 1e7) if mcap else 0
    data["pe_trailing"] = v.get("pe_trailing")
    data["pe_forward"] = v.get("pe_forward")
    data["pe_median"] = band.get("median_val", 0)
    data["pe_percentile"] = band.get("percentile")
    data["pe_observations"] = band.get("num_observations", 0)
    data["pe_period_start"] = band.get("period_start", "")
    data["pe_period_end"] = band.get("period_end", "")

    # Analyst upside
    target_mean = consensus.get("target_mean", 0)
    data["target_mean"] = target_mean
    data["upside_pct"] = round((target_mean / price - 1) * 100, 1) if price and target_mean else 0
    data["num_analysts"] = consensus.get("num_analysts", 0)

    # ROCE from ratios
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

    # Quarterly chart data (oldest first)
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

    # PE chart data
    data["pe_chart"] = {
        "dates": [p["date"] for p in data["pe_history"]],
        "pe_vals": [p["pe"] for p in data["pe_history"]],
        "price_vals": [p["price"] for p in data["pe_history"]],
    }

    # Annual financials (oldest first for table)
    data["af_table"] = list(reversed(af_list[:5]))

    # Ratios (oldest first for table)
    data["ratios_table"] = list(reversed(ratios))

    return data
