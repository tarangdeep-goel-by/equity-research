"""Build company_snapshot from existing DB tables.

Aggregates data from quarterly_results, valuation_snapshot, screener_ratios,
shareholding, and company_profiles into a single denormalized row per company.
No HTTP calls — pure DB reads + writes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)


def _build_screener(symbol: str, store: FlowStore) -> dict:
    """Collect Screener-owned fields from DB tables."""
    data: dict = {}

    # Name + industry from index_constituents (company_profiles lacks these)
    row = store._conn.execute(
        "SELECT company_name, industry FROM index_constituents WHERE symbol = ? LIMIT 1",
        (symbol,),
    ).fetchone()
    if row:
        data["name"] = row["company_name"]
        data["industry"] = row["industry"]

    # CMP + market_cap + PE from peer_comparison self-row, fallback to valuation_snapshot
    peers = store.get_peers(symbol)
    self_row = next((p for p in peers if p.get("peer_symbol") == symbol), None)
    if self_row:
        data["cmp"] = self_row.get("cmp")
        data["market_cap"] = self_row.get("market_cap")
        data["pe_trailing"] = self_row.get("pe")

    # Fallback: fill gaps from valuation_snapshot (yfinance has CMP, market_cap, PE too)
    if not data.get("cmp") or not data.get("pe_trailing"):
        snaps = store.get_valuation_history(symbol, days=7)
        if snaps:
            s = snaps[-1]
            if not data.get("cmp") and s.price:
                data["cmp"] = s.price
            if not data.get("market_cap") and s.market_cap:
                data["market_cap"] = s.market_cap
            if not data.get("pe_trailing") and s.pe_trailing:
                data["pe_trailing"] = s.pe_trailing

    # ROCE from screener_ratios (latest year)
    ratios = store.get_screener_ratios(symbol, limit=1)
    if ratios:
        r = ratios[0]
        roce = r.roce_pct if hasattr(r, "roce_pct") else r.get("roce_pct") if isinstance(r, dict) else None
        if roce is not None:
            data["roce"] = roce

    # Quarterly data (latest quarter + YoY variance)
    quarters = store.get_quarterly_results(symbol, limit=5)
    if quarters:
        latest = quarters[0]
        data["sales_qtr"] = latest.revenue
        data["np_qtr"] = latest.net_income
        # YoY variance: Q0 vs Q4 (same quarter last year)
        if len(quarters) >= 5:
            prev = quarters[4]
            if prev.revenue and prev.revenue > 0 and latest.revenue is not None:
                data["qtr_sales_var"] = round(
                    (latest.revenue - prev.revenue) / prev.revenue * 100, 1
                )
            if prev.net_income and prev.net_income > 0 and latest.net_income is not None:
                data["qtr_profit_var"] = round(
                    (latest.net_income - prev.net_income) / prev.net_income * 100, 1
                )

    return data


def _build_yfinance(symbol: str, store: FlowStore) -> dict:
    """Collect yfinance-owned fields from valuation_snapshot + live sector/industry."""
    data: dict = {}
    snaps = store.get_valuation_history(symbol, days=7)
    if not snaps:
        return data
    s = snaps[-1]  # latest (get_valuation_history returns oldest-first)
    data["pe_forward"] = s.pe_forward
    data["pb"] = s.pb_ratio
    data["ev_ebitda"] = s.ev_ebitda
    data["peg"] = s.peg_ratio
    data["div_yield"] = s.dividend_yield
    data["operating_margin"] = s.operating_margin
    data["net_margin"] = s.net_margin
    data["roe"] = s.roe
    data["roa"] = s.roa
    data["revenue_growth"] = s.revenue_growth
    data["earnings_growth"] = s.earnings_growth
    data["beta"] = s.beta
    data["debt_to_equity"] = s.debt_to_equity
    data["current_ratio"] = s.current_ratio
    data["high_52w"] = s.fifty_two_week_high
    data["low_52w"] = s.fifty_two_week_low

    # Computed PEG fallback: yfinance's peg_ratio is usually None for Indian stocks.
    # Compute PEG = forward_pe / earnings_growth_pct when yfinance didn't supply it
    # and both inputs are available with a positive growth rate.
    if data.get("peg") is None:
        fpe = s.pe_forward
        eg = s.earnings_growth
        if fpe is not None and eg is not None and eg > 0:
            data["peg"] = round(fpe / eg, 2)

    # Sector/industry from yfinance (authoritative source)
    try:
        from flowtracker.fund_client import FundClient
        fc = FundClient()
        live = fc.get_live_snapshot(symbol)
        if live.sector:
            data["sector"] = live.sector
        if live.industry:
            data["industry"] = live.industry
    except Exception:
        pass  # non-critical — don't block snapshot build

    return data


def _build_computed(symbol: str, store: FlowStore) -> dict:
    """Compute ROIC and FCF yield from annual_financials + latest mcap.

    ROIC  = NOPAT / invested_capital
            NOPAT            = operating_profit * (1 - effective_tax_rate)
            invested_capital = (equity_capital + reserves) + borrowings - cash_and_bank
            effective_tax    = tax / profit_before_tax  (fallback 0.25 if PBT <= 0)

    FCF yield = (CFO - capex) / mcap * 100
                capex = (net_block_t - net_block_{t-1})
                        + (cwip_t - cwip_{t-1})
                        + depreciation_t
                (requires 2 adjacent years of annual_financials)

    Returns only keys whose inputs were all present. Silently skips metrics whose
    inputs are missing — callers treat absence as "leave NULL".
    """
    data: dict = {}

    annuals = store.get_annual_financials(symbol, limit=2)
    if not annuals:
        return data
    latest = annuals[0]

    # --- ROIC ---
    op = getattr(latest, "operating_profit", None)
    pbt = getattr(latest, "profit_before_tax", None) or 0
    tax = getattr(latest, "tax", None) or 0
    equity_capital = getattr(latest, "equity_capital", None) or 0
    reserves = getattr(latest, "reserves", None) or 0
    borrowings = getattr(latest, "borrowings", None) or 0
    cash = getattr(latest, "cash_and_bank", None) or 0

    if op is not None and op != 0:
        eff_tax_rate = (tax / pbt) if pbt and pbt > 0 else 0.25
        # Clamp tax rate to a sensible [0, 1] band — negative PBT / refunds can
        # produce garbage values otherwise.
        if eff_tax_rate < 0:
            eff_tax_rate = 0.25
        if eff_tax_rate > 1:
            eff_tax_rate = 1.0
        nopat = op * (1 - eff_tax_rate)
        invested_capital = (equity_capital + reserves) + borrowings - cash
        if invested_capital > 0:
            data["roic"] = round(nopat / invested_capital * 100, 2)

    # --- FCF yield ---
    # Need mcap (from latest valuation_snapshot) and 2 years of annuals for capex.
    mcap = None
    snaps = store.get_valuation_history(symbol, days=7)
    if snaps:
        mcap = snaps[-1].market_cap
    if mcap and mcap > 0 and len(annuals) >= 2:
        prev = annuals[1]
        cfo = getattr(latest, "cfo", None)
        if cfo is not None:
            nb_t = getattr(latest, "net_block", None) or 0
            nb_t1 = getattr(prev, "net_block", None) or 0
            cwip_t = getattr(latest, "cwip", None) or 0
            cwip_t1 = getattr(prev, "cwip", None) or 0
            dep = getattr(latest, "depreciation", None) or 0
            capex = (nb_t - nb_t1) + (cwip_t - cwip_t1) + dep
            fcf = cfo - capex
            data["fcf_yield"] = round(fcf / mcap * 100, 2)

    return data


def _build_ownership(symbol: str, store: FlowStore) -> dict:
    """Collect ownership fields from shareholding + promoter_pledge."""
    data: dict = {}
    holdings = store.get_shareholding(symbol, limit=8)
    if holdings:
        latest_quarter = holdings[0].quarter_end
        for h in holdings:
            if h.quarter_end != latest_quarter:
                break
            if h.category.lower() in ("promoter", "promoters"):
                data["promoter_holding"] = h.percentage

    pledges = store.get_promoter_pledge(symbol, limit=1)
    if pledges:
        data["promoter_pledge"] = pledges[0].pledge_pct
    return data


def build_company_snapshot(symbol: str, store: FlowStore) -> bool:
    """Build/update company_snapshot from existing DB tables.

    No HTTP calls — aggregates from data already in SQLite.
    Returns True if any data was written.
    """
    symbol = symbol.upper()
    screener = _build_screener(symbol, store)
    yfinance = _build_yfinance(symbol, store)
    ownership = _build_ownership(symbol, store)
    computed = _build_computed(symbol, store)

    wrote = False
    if screener:
        store.upsert_snapshot_screener(symbol, screener)
        wrote = True
    if yfinance:
        store.upsert_snapshot_yfinance(symbol, yfinance)
        wrote = True
    if ownership:
        store.upsert_snapshot_ownership(symbol, ownership)
        wrote = True
    if computed:
        store.upsert_snapshot_computed(symbol, computed)
        wrote = True

    if wrote:
        logger.info(
            "[snapshot] %s: built (%d screener, %d yfinance, %d ownership, %d computed fields)",
            symbol, len(screener), len(yfinance), len(ownership), len(computed),
        )
    return wrote
