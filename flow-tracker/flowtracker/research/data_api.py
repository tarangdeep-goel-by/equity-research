"""Unified data access for equity research — wraps FlowStore for agent tools."""

from __future__ import annotations

from flowtracker.store import FlowStore
from flowtracker.utils import _clean


class ResearchDataAPI:
    """Unified data access for equity research — wraps FlowStore for agent tools."""

    def __init__(self):
        self._store = FlowStore()
        self._store.__enter__()

    def close(self):
        self._store.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # --- Core Financials ---

    def get_quarterly_results(self, symbol: str, quarters: int = 12) -> list[dict]:
        """Quarterly P&L data (revenue, expenses, operating profit, net income, EPS, margins)."""
        rows = self._store.get_quarterly_results(symbol, limit=quarters)
        return _clean([r.model_dump() for r in rows])

    def get_annual_financials(self, symbol: str, years: int = 10) -> list[dict]:
        """Annual P&L + Balance Sheet + Cash Flow (10yr history)."""
        rows = self._store.get_annual_financials(symbol, limit=years)
        return _clean([r.model_dump() for r in rows])

    def get_screener_ratios(self, symbol: str, years: int = 10) -> list[dict]:
        """Efficiency ratios: debtor days, inventory days, CCC, working capital days, ROCE%."""
        rows = self._store.get_screener_ratios(symbol, limit=years)
        return _clean([r.model_dump() for r in rows])

    # --- Valuation ---

    def get_valuation_snapshot(self, symbol: str) -> dict:
        """Latest valuation snapshot (50+ fields: price, PE, PB, EV/EBITDA, margins, etc.)."""
        hist = self._store.get_valuation_history(symbol, days=7)
        if hist:
            return _clean(hist[-1].model_dump())
        return {}

    def get_valuation_band(self, symbol: str, metric: str = "pe_trailing", days: int = 2500) -> dict:
        """P/E (or other metric) percentile band over historical period."""
        band = self._store.get_valuation_band(symbol, metric, days=days)
        return _clean(band.model_dump()) if band else {}

    def get_pe_history(self, symbol: str, days: int = 2500) -> list[dict]:
        """Historical P/E and price time series for charting."""
        hist = self._store.get_valuation_history(symbol, days=days)
        return _clean([
            {"date": h.date, "pe": h.pe_trailing, "price": h.price}
            for h in hist if h.pe_trailing
        ])

    # --- Ownership & Institutional ---

    def get_shareholding(self, symbol: str, quarters: int = 12) -> list[dict]:
        """Quarterly ownership %: FII, DII, MF, Promoter, Public."""
        rows = self._store.get_shareholding(symbol, limit=quarters)
        return _clean([
            {"quarter_end": r.quarter_end, "category": r.category, "percentage": r.percentage}
            for r in rows
        ])

    def get_shareholding_changes(self, symbol: str) -> list[dict]:
        """Latest quarter-over-quarter ownership changes."""
        rows = self._store.get_shareholding_changes(symbol)
        return _clean([
            {"category": r.category, "curr_pct": r.curr_pct, "prev_pct": r.prev_pct, "change_pct": r.change_pct}
            for r in rows
        ])

    def get_insider_transactions(self, symbol: str, days: int = 365) -> list[dict]:
        """SAST insider buy/sell trades with person name, category, value."""
        rows = self._store.get_insider_by_symbol(symbol, days=days)
        return _clean([r.model_dump() for r in rows])

    def get_bulk_block_deals(self, symbol: str) -> list[dict]:
        """BSE bulk/block deals — large institutional trades."""
        rows = self._store.get_deals_by_symbol(symbol)
        return _clean([r.model_dump() for r in rows])

    def get_mf_holdings(self, symbol: str) -> list[dict]:
        """MF scheme holdings — which schemes hold this stock, qty, % of NAV."""
        rows = self._store.get_mf_stock_holdings(symbol)
        return _clean([r.model_dump() for r in rows])

    def get_mf_holding_changes(self, symbol: str) -> list[dict]:
        """MF holdings for this stock (latest month). Use for ownership analysis."""
        rows = self._store.get_mf_stock_holdings(symbol)
        return _clean([r.model_dump() for r in rows])

    # --- Market Signals ---

    def get_delivery_trend(self, symbol: str, days: int = 30) -> list[dict]:
        """Daily delivery % from bhavcopy — accumulation signal."""
        rows = self._store.get_stock_delivery(symbol, days=days)
        return _clean([r.model_dump() for r in rows])

    def get_promoter_pledge(self, symbol: str) -> list[dict]:
        """Quarterly promoter pledge % history."""
        rows = self._store.get_promoter_pledge(symbol)
        return _clean([r.model_dump() for r in rows])

    # --- Consensus ---

    def get_consensus_estimate(self, symbol: str) -> dict:
        """Latest analyst consensus: target price, recommendation, forward PE, earnings growth."""
        est = self._store.get_estimate_latest(symbol)
        return _clean(est.model_dump()) if est else {}

    def get_earnings_surprises(self, symbol: str) -> list[dict]:
        """Quarterly earnings surprises: actual vs estimate EPS, surprise %."""
        rows = self._store.get_surprises(symbol)
        return _clean([r.model_dump() for r in rows])

    # --- Macro Context ---

    def get_macro_snapshot(self) -> dict:
        """Current macro indicators: VIX, USD/INR, Brent crude, 10Y G-sec."""
        row = self._store._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row:
            return _clean(dict(row))
        return {}

    def get_fii_dii_streak(self) -> dict:
        """Current FII/DII buying/selling streak."""
        fii = self._store.get_streak("FII")
        dii = self._store.get_streak("DII")
        return {
            "fii": _clean(fii.model_dump()) if fii else {},
            "dii": _clean(dii.model_dump()) if dii else {},
        }

    def get_fii_dii_flows(self, days: int = 30) -> list[dict]:
        """Daily FII/DII net flows for recent period."""
        rows = self._store.get_flows(days=days)
        return _clean([r.model_dump() for r in rows])

    # --- Filings ---

    def get_recent_filings(self, symbol: str, limit: int = 10) -> list[dict]:
        """Recent BSE corporate filings."""
        rows = self._store.get_filings(symbol, limit=limit)
        return _clean([r.model_dump() for r in rows])

    # --- Screener APIs (new tables from Phase 2) ---

    def get_chart_data(self, symbol: str, chart_type: str) -> list[dict]:
        """Screener chart time series (PE, PBV, EV/EBITDA, margins, price/volume).
        chart_type: 'price', 'pe', 'sales_margin', 'ev_ebitda', 'pbv', 'mcap_sales'
        """
        return self._store.get_chart_data(symbol, chart_type)

    def get_peer_comparison(self, symbol: str) -> list[dict]:
        """Peer comparison: CMP, P/E, MCap, ROCE, etc. for sector peers."""
        return self._store.get_peers(symbol)

    def get_shareholder_detail(self, symbol: str, classification: str | None = None) -> list[dict]:
        """Individual shareholder names and quarterly %: Vanguard, LIC, etc."""
        return self._store.get_shareholder_details(symbol, classification)

    def get_expense_breakdown(self, symbol: str, section: str = "profit-loss") -> list[dict]:
        """Schedule sub-item breakdowns (e.g., Expenses → Employee Cost, Raw Material)."""
        return self._store.get_schedules(symbol, section)

    # --- Company Info ---

    def get_company_info(self, symbol: str) -> dict:
        """Company name and industry from index constituents."""
        constituents = self._store.get_index_constituents()
        match = [c for c in constituents if c.symbol == symbol]
        if match:
            return {"symbol": symbol, "company_name": match[0].company_name, "industry": match[0].industry}
        return {"symbol": symbol, "company_name": symbol, "industry": "Unknown"}
