"""Dynamic WACC computation — CAPM beta, synthetic credit rating, terminal growth."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# --- Constants ---
INDIA_ERP = 0.0746  # Damodaran July 2025 (latest available as of Apr 2026)
ERP_LAST_UPDATED = "2025-07"
STATUTORY_TAX_RATE = 0.2517  # Section 115BAA
SMALL_CAP_THRESHOLD_CR = 5000  # Market cap in crores
SMALL_CAP_PREMIUM = 0.03  # 3% small-cap premium
BETA_FLOOR = 0.5
BETA_CAP = 2.5

# ICR-to-Spread table (Damodaran EM, basis points)
_ICR_SPREAD_TABLE: list[tuple[float, str, int]] = [
    (0.5, "D", 1200),
    (0.8, "C", 1050),
    (1.25, "CC", 900),
    (1.5, "CCC", 750),
    (2.0, "B-", 600),
    (2.5, "B", 500),
    (3.0, "B+", 400),
    (3.5, "BB", 350),
    (4.5, "BB+", 300),
    (6.0, "BBB", 200),
    (7.5, "A-", 175),
    (10.0, "A", 150),
    (15.0, "A+", 125),
    (20.0, "AA", 100),
    (float("inf"), "AAA", 75),
]


def compute_nifty_beta(
    stock_prices: list[dict[str, Any]],
    index_prices: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute CAPM beta of a stock against Nifty using weekly log returns.

    Args:
        stock_prices: List of {"date": "YYYY-MM-DD", "close": float} for the stock.
        index_prices: List of {"date": "YYYY-MM-DD", "close": float} for the index.

    Returns:
        Dict with raw_beta, blume_beta, r_squared, num_weeks on success,
        or {"error": str, "num_weeks": int} on failure.
    """
    # Build date -> close maps
    stock_map: dict[str, float] = {p["date"]: p["close"] for p in stock_prices}
    index_map: dict[str, float] = {p["date"]: p["close"] for p in index_prices}

    # Align on common dates
    common_dates = sorted(set(stock_map) & set(index_map))
    if not common_dates:
        return {"error": "Insufficient data", "num_weeks": 0}

    # Resample to weekly (Friday close — last trading day of each ISO week)
    from datetime import date as _date

    weekly: dict[tuple[int, int], tuple[str, float, float]] = {}
    for d_str in common_dates:
        d = _date.fromisoformat(d_str)
        iso_year, iso_week, _ = d.isocalendar()
        key = (iso_year, iso_week)
        # Keep the latest date within each week
        if key not in weekly or d_str > weekly[key][0]:
            weekly[key] = (d_str, stock_map[d_str], index_map[d_str])

    # Sort weeks chronologically
    sorted_weeks = sorted(weekly.keys())
    if len(sorted_weeks) < 53:  # Need at least 52 returns (53 price points)
        return {"error": "Insufficient data", "num_weeks": len(sorted_weeks)}

    stock_closes = [weekly[k][1] for k in sorted_weeks]
    index_closes = [weekly[k][2] for k in sorted_weeks]

    # Log returns: ln(P_t / P_{t-1})
    stock_returns = np.array(
        [math.log(stock_closes[i] / stock_closes[i - 1]) for i in range(1, len(stock_closes))]
    )
    index_returns = np.array(
        [math.log(index_closes[i] / index_closes[i - 1]) for i in range(1, len(index_closes))]
    )

    num_weeks = len(stock_returns)

    # OLS regression: stock = alpha + beta * index
    # np.polyfit(x, y, 1) returns [slope, intercept] = [beta, alpha]
    coeffs = np.polyfit(index_returns, stock_returns, 1)
    raw_beta = float(coeffs[0])

    # R² = 1 - SS_res / SS_tot
    predicted = coeffs[0] * index_returns + coeffs[1]
    ss_res = float(np.sum((stock_returns - predicted) ** 2))
    ss_tot = float(np.sum((stock_returns - np.mean(stock_returns)) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Blume adjustment
    blume_beta = 0.67 * raw_beta + 0.33 * 1.0

    # Floor and cap
    blume_beta = max(BETA_FLOOR, min(BETA_CAP, blume_beta))

    return {
        "raw_beta": round(raw_beta, 4),
        "blume_beta": round(blume_beta, 4),
        "r_squared": round(r_squared, 4),
        "num_weeks": num_weeks,
    }


def compute_cost_of_equity(
    rf: float,
    beta: float,
    erp: float,
    mcap_cr: float | None = None,
) -> dict[str, Any]:
    """Compute cost of equity using CAPM with optional small-cap premium.

    Args:
        rf: Risk-free rate (e.g. 0.07 for 7%).
        beta: Adjusted beta.
        erp: Equity risk premium (e.g. 0.0746).
        mcap_cr: Market cap in crores, used to determine small-cap premium.

    Returns:
        Dict with ke, rf, beta, erp, small_cap_premium.
    """
    ke = rf + beta * erp
    premium = 0.0

    if mcap_cr is not None and mcap_cr < SMALL_CAP_THRESHOLD_CR:
        premium = SMALL_CAP_PREMIUM
        ke += premium

    return {
        "ke": round(ke, 4),
        "rf": rf,
        "beta": beta,
        "erp": erp,
        "small_cap_premium": premium,
    }


def compute_cost_of_debt(
    interest: float,
    borrowings: float,
    pbt: float,
    rf: float,
    effective_tax_rate: float | None = None,
) -> dict[str, Any]:
    """Compute cost of debt via synthetic credit rating from ICR.

    Args:
        interest: Interest expense (crores).
        borrowings: Total borrowings (crores).
        pbt: Profit before tax (crores).
        rf: Risk-free rate.
        effective_tax_rate: Actual tax/PBT from financials. If None, uses statutory rate.

    Returns:
        Dict with kd_pretax, kd_posttax, rating, icr, spread_bps, tax_rate_used.
    """
    if interest <= 0 or borrowings <= 0:
        return {
            "kd_pretax": 0,
            "kd_posttax": 0,
            "rating": "debt_free",
            "icr": None,
            "spread_bps": 0,
        }

    # ICR = EBIT / Interest = (PBT + Interest) / Interest
    icr = (pbt + interest) / interest

    # Lookup synthetic rating
    rating = "AAA"
    spread_bps = 75
    for threshold, rtg, bps in _ICR_SPREAD_TABLE:
        if icr < threshold:
            rating = rtg
            spread_bps = bps
            break

    kd_pretax = rf + spread_bps / 10000

    # Tax shield: use effective rate from financials, 0% if unprofitable
    if effective_tax_rate is not None:
        marginal_tax = effective_tax_rate if pbt > 0 else 0.0
    else:
        marginal_tax = STATUTORY_TAX_RATE if pbt > 0 else 0.0
    kd_posttax = kd_pretax * (1 - marginal_tax)

    return {
        "kd_pretax": round(kd_pretax, 4),
        "kd_posttax": round(kd_posttax, 4),
        "rating": rating,
        "icr": round(icr, 2),
        "spread_bps": spread_bps,
        "tax_rate_used": round(marginal_tax, 4),
    }


def compute_wacc(
    ke: float,
    kd_posttax: float,
    mcap: float,
    borrowings: float,
) -> dict[str, Any]:
    """Compute weighted average cost of capital.

    Args:
        ke: Cost of equity.
        kd_posttax: Post-tax cost of debt.
        mcap: Market capitalization (crores).
        borrowings: Total borrowings (crores).

    Returns:
        Dict with wacc, equity_weight, debt_weight.
    """
    if borrowings <= 0:
        return {
            "wacc": round(ke, 4),
            "equity_weight": 1.0,
            "debt_weight": 0.0,
        }

    total = mcap + borrowings
    equity_weight = mcap / total
    debt_weight = borrowings / total
    wacc = ke * equity_weight + kd_posttax * debt_weight

    return {
        "wacc": round(wacc, 4),
        "equity_weight": round(equity_weight, 4),
        "debt_weight": round(debt_weight, 4),
    }


def compute_terminal_growth(rf: float) -> float:
    """Compute terminal growth rate as Rf minus 50bps, floored at 4% and capped at Rf.

    Args:
        rf: Risk-free rate (e.g. 0.07 for 7%).

    Returns:
        Terminal growth rate as float.
    """
    g = rf - 0.005
    g = max(0.04, g)
    g = min(g, rf)
    return g


def compute_dynamic_pe(pe_band: dict[str, Any] | None) -> dict[str, Any]:
    """Compute dynamic PE multiples from historical PE band.

    Args:
        pe_band: Dict with min_val, median_val, max_val from get_valuation_band,
                 or None for defaults.

    Returns:
        Dict with low, mid, high, source.
    """
    if pe_band is None:
        return {"low": 15, "mid": 20, "high": 30, "source": "default"}

    min_val = pe_band.get("min_val")
    median_val = pe_band.get("median_val")
    max_val = pe_band.get("max_val")

    if min_val is None or median_val is None or max_val is None:
        return {"low": 15, "mid": 20, "high": 30, "source": "default"}

    low = round((min_val + median_val) / 2, 1)
    mid = round(median_val, 1)
    high = round((median_val + max_val) / 2, 1)

    # Floor low at 5, cap high at 100
    low = max(5.0, low)
    high = min(100.0, high)

    return {"low": low, "mid": mid, "high": high, "source": "historical_band"}


def get_reliability_flags(
    industry: str | None,
    mcap_cr: float | None,
    beta_r_squared: float | None,
    is_bfsi: bool = False,
) -> list[str]:
    """Return warning flags for WACC reliability.

    Args:
        industry: Company industry string.
        mcap_cr: Market cap in crores.
        beta_r_squared: R-squared from beta regression.
        is_bfsi: Whether the company is in BFSI sector.

    Returns:
        List of warning flag strings.
    """
    flags: list[str] = []

    if industry:
        ind_lower = industry.lower()
        if "holding" in ind_lower or "conglomerate" in ind_lower:
            flags.append("holdco_or_conglomerate")
        cyclical_keywords = ["steel", "mining", "cement", "commodity", "sugar", "chemicals"]
        if any(kw in ind_lower for kw in cyclical_keywords):
            flags.append("cyclical")

    if mcap_cr is not None and mcap_cr < 1000:
        flags.append("micro_cap")

    if beta_r_squared is not None and beta_r_squared < 0.10:
        flags.append("low_beta_r_squared")

    if is_bfsi:
        flags.append("bfsi_no_wacc")

    return flags


def build_wacc_params(
    symbol: str,
    stock_prices: list[dict[str, Any]],
    index_prices: list[dict[str, Any]],
    rf: float,
    interest: float,
    borrowings: float,
    pbt: float,
    mcap_cr: float,
    pe_band: dict[str, Any] | None,
    industry: str | None = None,
    is_bfsi: bool = False,
    effective_tax_rate: float | None = None,
) -> dict[str, Any]:
    """Orchestrate full WACC parameter computation for a stock.

    Computes beta, cost of equity, cost of debt, WACC, terminal growth,
    dynamic PE multiples, and reliability flags in one call.

    Args:
        symbol: Stock ticker symbol.
        stock_prices: Daily stock prices [{"date": ..., "close": ...}, ...].
        index_prices: Daily Nifty index prices [{"date": ..., "close": ...}, ...].
        rf: Risk-free rate.
        interest: Interest expense (crores).
        borrowings: Total borrowings (crores).
        pbt: Profit before tax (crores).
        mcap_cr: Market capitalization (crores).
        pe_band: Historical PE band dict or None.
        industry: Company industry string.
        is_bfsi: Whether the company is BFSI (uses CoE instead of WACC).
        effective_tax_rate: Actual tax/PBT from financials for accurate debt tax shield.

    Returns:
        Consolidated dict with all WACC parameters and reliability flags.
    """
    # --- Beta ---
    beta_result = compute_nifty_beta(stock_prices, index_prices)

    if "error" in beta_result:
        logger.warning("%s: beta computation failed (%s), using 1.0", symbol, beta_result["error"])
        beta_value = 1.0
        beta_defaulted = True
    else:
        beta_value = beta_result["blume_beta"]
        beta_defaulted = False

    # --- Cost of equity ---
    coe_result = compute_cost_of_equity(rf, beta_value, INDIA_ERP, mcap_cr)

    # --- Cost of debt (skip for BFSI) ---
    if is_bfsi:
        cod_result = None
        wacc_result = None
        wacc_value = coe_result["ke"]
    else:
        cod_result = compute_cost_of_debt(interest, borrowings, pbt, rf, effective_tax_rate)
        wacc_result = compute_wacc(coe_result["ke"], cod_result["kd_posttax"], mcap_cr, borrowings)
        wacc_value = wacc_result["wacc"]

    # --- Terminal growth ---
    terminal_g = compute_terminal_growth(rf)

    # --- Dynamic PE ---
    pe_result = compute_dynamic_pe(pe_band)

    # --- Reliability flags ---
    beta_r2 = beta_result.get("r_squared")
    flags = get_reliability_flags(industry, mcap_cr, beta_r2, is_bfsi)
    if beta_defaulted:
        flags.append("beta_default")

    return {
        "symbol": symbol,
        "beta": beta_result,
        "cost_of_equity": coe_result,
        "cost_of_debt": cod_result,
        "wacc_result": wacc_result,
        "wacc": wacc_value,
        "ke": coe_result["ke"],
        "terminal_growth": terminal_g,
        "pe_multiples": pe_result,
        "reliability_flags": flags,
        "is_bfsi": is_bfsi,
    }
