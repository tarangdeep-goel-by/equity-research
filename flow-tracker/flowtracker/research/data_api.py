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

    # --- FMP Data ---

    def get_dcf_valuation(self, symbol: str) -> dict:
        """Latest DCF intrinsic value + margin of safety."""
        dcf = self._store.get_fmp_dcf_latest(symbol)
        if not dcf:
            return {}
        result = _clean(dcf.model_dump())
        if dcf.dcf and dcf.stock_price and dcf.stock_price > 0:
            result["margin_of_safety_pct"] = round(
                (dcf.dcf - dcf.stock_price) / dcf.stock_price * 100, 2
            )
        return result

    def get_dcf_history(self, symbol: str, days: int = 365) -> list[dict]:
        """Historical DCF trajectory."""
        rows = self._store.get_fmp_dcf_history(symbol, limit=10)
        return _clean([r.model_dump() for r in rows])

    def get_technical_indicators(self, symbol: str) -> list[dict]:
        """Latest RSI, MACD, SMA-50, SMA-200, ADX."""
        rows = self._store.get_fmp_technical_indicators(symbol)
        return _clean([r.model_dump() for r in rows])

    def get_dupont_decomposition(self, symbol: str) -> dict:
        """ROE = margin × turnover × leverage (10yr). Uses Screener annual_financials, falls back to FMP key_metrics."""
        # Try Screener data first
        annuals = self._store.get_annual_financials(symbol, limit=10)
        if annuals:
            decomp = []
            for a in annuals:
                total_equity = (a.equity_capital or 0) + (a.reserves or 0)
                if a.revenue and a.revenue > 0 and a.net_income is not None and a.total_assets and a.total_assets > 0 and total_equity and total_equity > 0:
                    npm = a.net_income / a.revenue
                    at = a.revenue / a.total_assets
                    em = a.total_assets / total_equity
                    roe = npm * at * em
                    decomp.append({
                        "fiscal_year_end": a.fiscal_year_end,
                        "net_profit_margin": round(npm, 4),
                        "asset_turnover": round(at, 4),
                        "equity_multiplier": round(em, 4),
                        "roe_dupont": round(roe, 4),
                    })
            if decomp:
                return {"source": "screener", "years": decomp}

        # Fallback to FMP
        metrics = self._store.get_fmp_key_metrics(symbol, limit=10)
        if metrics:
            decomp = []
            for m in metrics:
                if m.net_profit_margin_dupont is not None and m.asset_turnover is not None and m.equity_multiplier is not None:
                    roe = m.net_profit_margin_dupont * m.asset_turnover * m.equity_multiplier
                    decomp.append({
                        "date": m.date,
                        "net_profit_margin": round(m.net_profit_margin_dupont, 4),
                        "asset_turnover": round(m.asset_turnover, 4),
                        "equity_multiplier": round(m.equity_multiplier, 4),
                        "roe_dupont": round(roe, 4),
                    })
            if decomp:
                return {"source": "fmp", "years": decomp}

        return {}

    def get_key_metrics_history(self, symbol: str, years: int = 10) -> list[dict]:
        """Comprehensive per-share + ratio history from FMP."""
        rows = self._store.get_fmp_key_metrics(symbol, limit=years)
        return _clean([r.model_dump() for r in rows])

    def get_financial_growth_rates(self, symbol: str) -> list[dict]:
        """Pre-computed 1yr/3yr/5yr/10yr growth from FMP."""
        rows = self._store.get_fmp_financial_growth(symbol, limit=10)
        return _clean([r.model_dump() for r in rows])

    def get_analyst_grades(self, symbol: str) -> list[dict]:
        """Upgrade/downgrade history from FMP."""
        rows = self._store.get_fmp_analyst_grades(symbol, limit=20)
        return _clean([r.model_dump() for r in rows])

    def get_price_targets(self, symbol: str) -> list[dict]:
        """Individual analyst targets with dispersion from FMP."""
        rows = self._store.get_fmp_price_targets(symbol, limit=20)
        result = _clean([r.model_dump() for r in rows])
        # Add summary stats
        valid = [r["price_target"] for r in result if r.get("price_target")]
        if valid:
            return {
                "targets": result,
                "consensus_mean": round(sum(valid) / len(valid), 2),
                "high": max(valid),
                "low": min(valid),
                "count": len(valid),
            }
        return {"targets": result}

    def get_fair_value(self, symbol: str) -> dict:
        """Combined fair value from PE band + DCF + consensus target.

        Returns bear/base/bull range, margin of safety %, signal.
        """
        result: dict = {"symbol": symbol}

        # 1. PE band fair value
        pe_band = self._store.get_valuation_band(symbol, "pe_trailing", days=2500)
        est = self._store.get_estimate_latest(symbol)
        snap_rows = self._store.get_valuation_history(symbol, days=7)
        current_price = snap_rows[-1].price if snap_rows else None

        forward_eps = None
        if est and est.forward_eps:
            forward_eps = est.forward_eps

        pe_fair = None
        if pe_band and forward_eps:
            # ValuationBand has min_val, median_val, max_val, percentile
            # bear = min-to-median midpoint, base = median, bull = median-to-max midpoint
            bear = ((pe_band.min_val + pe_band.median_val) / 2) * forward_eps
            base = pe_band.median_val * forward_eps
            bull = ((pe_band.median_val + pe_band.max_val) / 2) * forward_eps
            result["pe_band"] = {
                "bear": round(bear, 2), "base": round(base, 2), "bull": round(bull, 2),
                "forward_eps": forward_eps, "pe_percentile": pe_band.percentile,
            }
            pe_fair = base

        # 2. FMP DCF
        dcf = self._store.get_fmp_dcf_latest(symbol)
        dcf_value = dcf.dcf if dcf else None
        if dcf_value:
            result["dcf"] = dcf_value

        # 3. Analyst consensus target
        target_mean = est.target_mean if est else None
        if target_mean:
            result["consensus_target"] = target_mean

        # Combined fair value = average of available
        values = [v for v in [pe_fair, dcf_value, target_mean] if v]
        if values and current_price:
            combined = sum(values) / len(values)
            margin = (combined - current_price) / combined * 100
            result["combined_fair_value"] = round(combined, 2)
            result["current_price"] = current_price
            result["margin_of_safety_pct"] = round(margin, 2)
            result["sources_used"] = len(values)

            # Signal
            bear = result.get("pe_band", {}).get("bear")
            bull = result.get("pe_band", {}).get("bull")
            if bear and current_price < bear:
                result["signal"] = "DEEP VALUE"
            elif current_price < combined:
                result["signal"] = "UNDERVALUED"
            elif bull and current_price > bull:
                result["signal"] = "EXPENSIVE"
            else:
                result["signal"] = "FAIR VALUE"
        elif current_price:
            result["current_price"] = current_price
            result["signal"] = "INSUFFICIENT DATA"

        return _clean(result)

    # --- Company Info ---

    def get_company_info(self, symbol: str) -> dict:
        """Company name and industry from index constituents."""
        constituents = self._store.get_index_constituents()
        match = [c for c in constituents if c.symbol == symbol]
        if match:
            return {"symbol": symbol, "company_name": match[0].company_name, "industry": match[0].industry}
        return {"symbol": symbol, "company_name": symbol, "industry": "Unknown"}
