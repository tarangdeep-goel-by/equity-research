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

    # CMP + market_cap + PE from peer_comparison self-row
    peers = store.get_peers(symbol)
    self_row = next((p for p in peers if p.get("peer_symbol") == symbol), None)
    if self_row:
        data["cmp"] = self_row.get("cmp")
        data["market_cap"] = self_row.get("market_cap")
        data["pe_trailing"] = self_row.get("pe")

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
    """Collect yfinance-owned fields from valuation_snapshot."""
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

    if wrote:
        logger.info(
            "[snapshot] %s: built (%d screener, %d yfinance, %d ownership fields)",
            symbol, len(screener), len(yfinance), len(ownership),
        )
    return wrote
