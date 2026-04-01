"""Financial projection model — bear/base/bull 3-year forward P&L."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class ProjectionScenario:
    """One scenario (bear/base/bull) for a single projected year."""
    label: str  # "bear", "base", "bull"
    year: int   # FY offset: 1, 2, 3
    fiscal_year: str  # "FY27", "FY28", etc.
    revenue: float
    revenue_growth: float
    ebitda: float
    ebitda_margin: float
    depreciation: float
    interest: float
    pbt: float
    tax: float
    tax_rate: float
    net_income: float
    net_margin: float
    eps: float
    shares_outstanding: float


def build_projections(
    annual_data: list[dict],
    adjustment_factor: float = 1.0,
    shares_override: float | None = None,
) -> dict:
    """Build 3-year bear/base/bull projections from historical annual data.

    Args:
        annual_data: List of annual financials dicts (most recent first), needs at least 3 years
        adjustment_factor: Cumulative split/bonus factor for per-share adjustment
        shares_override: Override shares outstanding (post-adjustment)

    Returns:
        Dict with actuals summary, assumptions, and 3 scenarios x 3 years of projections
    """
    if len(annual_data) < 3:
        return {"error": "Need at least 3 years of annual data for projections"}

    # Sort most recent first
    data = sorted(annual_data, key=lambda d: d.get("fiscal_year_end", ""), reverse=True)

    # Extract historical metrics (last 3 and 5 years where available)
    revenues = [d["revenue"] for d in data if d.get("revenue")]
    net_incomes = [d["net_income"] for d in data if d.get("net_income")]

    # Latest actuals
    latest = data[0]
    latest_revenue = latest.get("revenue", 0)
    latest_ni = latest.get("net_income", 0)
    latest_fy = latest.get("fiscal_year_end", "")

    # Shares outstanding — Screener's num_shares is already the current post-adjustment count,
    # so we do NOT multiply by adjustment_factor. The factor is only for normalizing historical
    # per-share metrics (handled by get_adjusted_eps). For projections we use current shares as-is.
    shares = shares_override or (latest.get("num_shares") or 0)

    # Detect NI units: Screener stores some companies' financials in crores, others in raw rupees.
    # Derive the NI-to-EPS conversion by comparing Screener's known EPS against NI/shares.
    # If NI is in crores, we need to multiply by 1e7 before dividing by shares.
    screener_eps = latest.get("eps")
    ni_to_eps_factor = 1.0  # default: NI is in rupees, EPS = NI / shares
    if screener_eps and shares and latest_ni and abs(screener_eps) > 0.01:
        raw_eps = latest_ni / shares
        if abs(raw_eps) > 1e-10:
            # Ratio of screener EPS to raw computation tells us the scale factor
            inferred_factor = screener_eps / raw_eps
            # Should be close to 1 (rupees) or ~1e7 (crores) — pick nearest
            if inferred_factor > 1e3:
                ni_to_eps_factor = 1e7  # NI is in crores
            # else stays 1.0 (NI is in rupees)

    # Compute historical growth rates
    rev_growths = []
    for i in range(min(len(revenues) - 1, 4)):
        if revenues[i + 1] and revenues[i + 1] > 0:
            rev_growths.append((revenues[i] / revenues[i + 1]) - 1)

    # Compute CAGRs
    def _cagr(latest_val: float, oldest_val: float, years: int) -> float | None:
        if oldest_val and oldest_val > 0 and latest_val > 0 and years > 0:
            return (latest_val / oldest_val) ** (1 / years) - 1
        return None

    rev_3yr_cagr = _cagr(revenues[0], revenues[min(3, len(revenues) - 1)], min(3, len(revenues) - 1)) if len(revenues) > 1 else None
    rev_5yr_cagr = _cagr(revenues[0], revenues[min(5, len(revenues) - 1)], min(5, len(revenues) - 1)) if len(revenues) > 1 else None

    # Operating margin (EBITDA proxy: operating_profit + depreciation)
    # If operating_profit is missing, build EBITDA bottom-up: NI + tax + interest + depreciation
    ebitda_margins = []
    for d in data[:5]:
        rev = d.get("revenue") or 0
        if not rev or rev <= 0:
            continue
        dep = d.get("depreciation") or 0
        op = d.get("operating_profit")
        if op is not None:
            ebitda = op + dep
        elif d.get("total_expenses"):
            ebitda = (rev - d["total_expenses"]) + dep
        else:
            # Bottom-up: EBITDA = NI + Tax + Interest + Depreciation
            ni = d.get("net_income") or 0
            tax = d.get("tax") or 0
            interest = d.get("interest") or 0
            ebitda = ni + tax + interest + dep
        ebitda_margins.append(ebitda / rev)

    net_margins = []
    for d in data[:5]:
        rev = d.get("revenue") or 0
        ni = d.get("net_income") or 0
        if rev and rev > 0 and ni is not None:
            net_margins.append(ni / rev)

    # Tax rate
    tax_rates = []
    for d in data[:5]:
        pbt = d.get("profit_before_tax") or ((d.get("net_income") or 0) + (d.get("tax") or 0))
        tax = d.get("tax", 0) or 0
        if pbt and pbt > 0:
            tax_rates.append(tax / pbt)

    avg_tax_rate = statistics.mean(tax_rates) if tax_rates else 0.25

    # Dep and interest as % of revenue
    dep_pcts = [(d.get("depreciation") or 0) / d["revenue"] for d in data[:5] if d.get("revenue")]
    int_pcts = [(d.get("interest") or 0) / d["revenue"] for d in data[:5] if d.get("revenue")]

    avg_dep_pct = statistics.mean(dep_pcts) if dep_pcts else 0.03
    avg_int_pct = statistics.mean(int_pcts) if int_pcts else 0.01

    # --- Define scenarios ---

    # Base case: trailing 3yr CAGR for growth, trailing 3yr avg margin
    base_growth = rev_3yr_cagr or (statistics.mean(rev_growths) if rev_growths else 0.10)
    base_ebitda_margin = statistics.mean(ebitda_margins[:3]) if ebitda_margins else 0.15

    # Bear case: half growth, 200bps margin compression
    bear_growth = base_growth * 0.5
    bear_ebitda_margin = base_ebitda_margin - 0.02

    # Bull case: 1.5x growth (capped at reasonable), 200bps margin expansion
    bull_growth = min(base_growth * 1.5, 0.40)  # Cap at 40%
    bull_ebitda_margin = base_ebitda_margin + 0.02

    # Clamp margins to reasonable range
    # Don't cap bull below base — banks/software naturally have 80%+ EBITDA margins
    bear_ebitda_margin = max(bear_ebitda_margin, 0.02)
    bull_ebitda_margin = min(bull_ebitda_margin, 0.95)

    # Derive last actual fiscal year label
    fy_year = int(latest_fy[:4]) if latest_fy else 2025
    if latest_fy and "-03-" in latest_fy:
        fy_label_base = fy_year  # FY25 = ending Mar 2025
    else:
        fy_label_base = fy_year + 1

    def _project_scenario(label: str, growth: float, ebitda_margin: float) -> list[dict]:
        projections = []
        rev = latest_revenue
        for yr in range(1, 4):
            rev = rev * (1 + growth)
            ebitda = rev * ebitda_margin
            dep = rev * avg_dep_pct
            interest = rev * avg_int_pct
            pbt = ebitda - dep - interest
            tax = pbt * avg_tax_rate if pbt > 0 else 0
            ni = pbt - tax
            # Convert NI to per-share EPS using detected scale factor
            eps = (ni * ni_to_eps_factor / shares) if shares else 0
            # Convert to crores-friendly rounding
            fy_label = f"FY{str(fy_label_base + yr)[2:]}"
            projections.append({
                "label": label,
                "year": yr,
                "fiscal_year": fy_label,
                "revenue": round(rev, 2),
                "revenue_growth": round(growth * 100, 1),
                "ebitda": round(ebitda, 2),
                "ebitda_margin": round(ebitda_margin * 100, 1),
                "depreciation": round(dep, 2),
                "interest": round(interest, 2),
                "pbt": round(pbt, 2),
                "tax": round(tax, 2),
                "tax_rate": round(avg_tax_rate * 100, 1),
                "net_income": round(ni, 2),
                "net_margin": round((ni / rev * 100) if rev else 0, 1),
                "eps": round(eps, 2),
                "shares_outstanding": round(shares, 2) if shares else None,
            })
        return projections

    bear = _project_scenario("bear", bear_growth, bear_ebitda_margin)
    base = _project_scenario("base", base_growth, base_ebitda_margin)
    bull = _project_scenario("bull", bull_growth, bull_ebitda_margin)

    # Implied fair values at different PE multiples
    # Use trailing PE from latest data if available
    latest_eps_adj = (latest_ni * ni_to_eps_factor / shares) if shares and latest_ni else 0

    # Use year-3 EPS for terminal valuation
    bear_terminal_eps = bear[-1]["eps"]
    base_terminal_eps = base[-1]["eps"]
    bull_terminal_eps = bull[-1]["eps"]

    # PE multiples: use historical median or sector standard
    pe_low = 15
    pe_mid = 20
    pe_high = 30

    fair_values = {
        "bear_low_pe": round(bear_terminal_eps * pe_low, 2),
        "bear_mid_pe": round(bear_terminal_eps * pe_mid, 2),
        "base_low_pe": round(base_terminal_eps * pe_low, 2),
        "base_mid_pe": round(base_terminal_eps * pe_mid, 2),
        "base_high_pe": round(base_terminal_eps * pe_high, 2),
        "bull_mid_pe": round(bull_terminal_eps * pe_mid, 2),
        "bull_high_pe": round(bull_terminal_eps * pe_high, 2),
        "pe_multiples_used": {"low": pe_low, "mid": pe_mid, "high": pe_high},
        "note": "Fair value = Year-3 projected EPS x PE multiple. These are illustrative — the agent should refine PE assumptions based on sector, growth, and quality."
    }

    return {
        "symbol": latest.get("symbol", ""),
        "last_actual_fy": f"FY{str(fy_label_base)[2:]}",
        "last_actual_revenue": latest_revenue,
        "last_actual_net_income": latest_ni,
        "last_actual_eps": round(latest_eps_adj, 2) if latest_eps_adj else None,
        "shares_outstanding": round(shares, 2) if shares else None,
        "adjustment_factor": adjustment_factor,
        "assumptions": {
            "base_revenue_growth": round(base_growth * 100, 1),
            "bear_revenue_growth": round(bear_growth * 100, 1),
            "bull_revenue_growth": round(bull_growth * 100, 1),
            "base_ebitda_margin": round(base_ebitda_margin * 100, 1),
            "bear_ebitda_margin": round(bear_ebitda_margin * 100, 1),
            "bull_ebitda_margin": round(bull_ebitda_margin * 100, 1),
            "tax_rate": round(avg_tax_rate * 100, 1),
            "depreciation_pct": round(avg_dep_pct * 100, 1),
            "interest_pct": round(avg_int_pct * 100, 1),
            "methodology": "Base: 3yr revenue CAGR + 3yr avg EBITDA margin. Bear: 50% growth, -200bps margin. Bull: 150% growth (cap 40%), +200bps margin.",
        },
        "historical_context": {
            "revenue_3yr_cagr": round(rev_3yr_cagr * 100, 1) if rev_3yr_cagr else None,
            "revenue_5yr_cagr": round(rev_5yr_cagr * 100, 1) if rev_5yr_cagr else None,
            "recent_yoy_growths": [round(g * 100, 1) for g in rev_growths[:3]],
            "ebitda_margins_3yr": [round(m * 100, 1) for m in ebitda_margins[:3]],
            "net_margins_3yr": [round(m * 100, 1) for m in net_margins[:3]],
        },
        "projections": {
            "bear": bear,
            "base": base,
            "bull": bull,
        },
        "implied_fair_values": fair_values,
    }
