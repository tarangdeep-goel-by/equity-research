"""Financial projection model — bear/base/bull 3-year forward P&L."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


# Plan v2 §7 E12: sector-aware D&A routing.
# Returns (ratio, source_tag, caveat_text|None). BFSI/real_estate use different
# logic handled inline in build_projections (line-item based, not % of revenue).
_INDUSTRY_DA_RATIOS: dict[str, tuple[float, str, str | None]] = {
    # Asset-heavy manufacturing/resource (keep legacy 5% default)
    "manufacturing": (0.05, "manufacturing_default", None),
    "metals": (0.05, "metals_default", None),
    "cement": (0.05, "cement_default", None),
    "auto": (0.05, "auto_default", None),
    # Asset-light platforms / IT services / insurance / marketplaces
    "it_services": (0.01, "it_services_default",
                    "Industry classified as 'it_services' — D&A 1% of revenue per asset-light routing."),
    "platform": (0.01, "platform_default",
                 "Industry classified as 'platform' — D&A 1% of revenue per asset-light routing."),
    "insurance": (0.01, "insurance_default",
                  "Industry classified as 'insurance' — D&A 1% of revenue per asset-light routing."),
    "marketplace": (0.01, "marketplace_default",
                    "Industry classified as 'marketplace' — D&A 1% of revenue per asset-light routing."),
}

_BFSI_INDUSTRIES_PROJ = {"bfsi", "private_bank", "nbfc", "public_bank", "banks"}
_REAL_ESTATE_INDUSTRIES = {"real_estate", "realestate"}


def _resolve_da_strategy(
    industry: str | None,
    latest_rev: float,
    latest_dep: float,
    latest_net_block: float | None,
) -> dict:
    """Return D&A strategy for projections based on industry classification.

    Returns a dict with:
      - mode: "ratio" | "line_item" | "net_block"
      - ratio: float (for mode='ratio' and 'net_block')
      - source: str tag
      - caveats: list[str]
    """
    ind = (industry or "").strip().lower()

    if ind in _BFSI_INDUSTRIES_PROJ:
        # Do NOT project D&A as % of revenue — use latest reported line item.
        return {
            "mode": "line_item",
            "growth_rate": 0.05,  # modest 5%/yr growth
            "base_value": latest_dep or 0.0,
            "source": "bfsi_line_item",
            "caveats": [
                "Industry classified as BFSI — D&A projected from latest reported "
                "line item with 5%/yr growth (not % of revenue)."
            ],
        }

    if ind in _REAL_ESTATE_INDUSTRIES:
        # Project from fixed-asset base (net_block / 30yr life). Fallback to 2%.
        if latest_net_block and latest_net_block > 0:
            # depreciation per year ≈ net_block / 30; ratio = dep / revenue
            implied_dep = latest_net_block / 30.0
            ratio = (implied_dep / latest_rev) if latest_rev and latest_rev > 0 else 0.02
            return {
                "mode": "ratio",
                "ratio": ratio,
                "source": "real_estate_net_block",
                "caveats": [
                    "Industry classified as 'real_estate' — D&A derived from net block / 30yr typical life."
                ],
            }
        return {
            "mode": "ratio",
            "ratio": 0.02,
            "source": "real_estate_fallback",
            "caveats": [
                "Industry classified as 'real_estate' but net_block unavailable — "
                "fell back to 2% of revenue."
            ],
        }

    if ind in _INDUSTRY_DA_RATIOS:
        ratio, source, caveat = _INDUSTRY_DA_RATIOS[ind]
        return {
            "mode": "ratio",
            "ratio": ratio,
            "source": source,
            "caveats": [caveat] if caveat else [],
        }

    # Unknown / unresolved industry → 2% midpoint with caveat flag.
    return {
        "mode": "ratio",
        "ratio": 0.02,
        "source": "unresolved_default",
        "caveats": [
            "Industry classification unresolved — used 2% midpoint default. "
            "Valuation downstream should manually override for known asset-light or BFSI cases."
        ],
    }


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
    pe_multiples: dict | None = None,
    industry: str | None = None,
) -> dict:
    """Build 3-year bear/base/bull projections from historical annual data.

    Args:
        annual_data: List of annual financials dicts (most recent first), needs at least 3 years
        adjustment_factor: Cumulative split/bonus factor for per-share adjustment
        shares_override: Override shares outstanding (post-adjustment)
        industry: Optional industry classification (e.g. 'platform', 'bfsi', 'manufacturing')
            used for sector-aware D&A routing. Plan v2 §7 E12.

    Returns:
        Dict with actuals summary, assumptions, and 3 scenarios x 3 years of projections.
        Includes `_projection_assumptions` meta dict with D&A ratio used, source tag, and caveats.
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

    # Plan v2 §7 E12: sector-aware D&A strategy. Overrides avg_dep_pct (ratio mode)
    # or routes to line-item projection (BFSI).
    latest_dep = latest.get("depreciation") or 0.0
    latest_net_block = (
        latest.get("net_block")
        or latest.get("fixed_assets")
        or latest.get("gross_block")
    )
    da_strategy = _resolve_da_strategy(
        industry=industry,
        latest_rev=latest_revenue,
        latest_dep=latest_dep,
        latest_net_block=latest_net_block,
    )
    if da_strategy["mode"] == "ratio":
        avg_dep_pct = da_strategy["ratio"]

    # --- Define scenarios ---

    # Base case: trailing 3yr CAGR for growth, trailing 3yr avg margin
    base_growth = rev_3yr_cagr or (statistics.mean(rev_growths) if rev_growths else 0.10)
    base_ebitda_margin = statistics.mean(ebitda_margins[:3]) if ebitda_margins else 0.15

    # Bear case: half growth, 200bps margin compression
    bear_growth = base_growth - abs(base_growth * 0.5)
    bear_ebitda_margin = base_ebitda_margin - 0.02

    # Bull case: 1.5x growth (capped at reasonable), 200bps margin expansion
    bull_growth = min(base_growth + abs(base_growth * 0.5), 0.40)
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
        dep_running = da_strategy.get("base_value", 0.0)  # line_item seed
        for yr in range(1, 4):
            rev = rev * (1 + growth)
            ebitda = rev * ebitda_margin
            if da_strategy["mode"] == "line_item":
                # BFSI: grow depreciation line item at fixed %/yr
                dep_running = dep_running * (1 + da_strategy.get("growth_rate", 0.05))
                dep = dep_running
            else:
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
    if pe_multiples:
        pe_low = pe_multiples.get("low", 15)
        pe_mid = pe_multiples.get("mid", 20)
        pe_high = pe_multiples.get("high", 30)
    else:
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
        "_projection_assumptions": {
            "da_ratio_used": round(da_strategy.get("ratio", avg_dep_pct), 4)
            if da_strategy["mode"] != "line_item"
            else None,
            "da_mode": da_strategy["mode"],
            "da_ratio_source": da_strategy["source"],
            "industry_resolved": industry,
            "caveats": da_strategy.get("caveats", []),
        },
    }
