"""Unified data access for equity research — wraps FlowStore for agent tools."""

from __future__ import annotations

import statistics

from flowtracker.store import FlowStore
from flowtracker.utils import _clean


def _percentile_rank(values: list[float], value: float) -> float:
    """Simple percentile rank: % of values strictly below the given value."""
    below = sum(1 for v in values if v < value)
    return round(100 * below / len(values)) if values else 0


_BFSI_INDUSTRIES = {
    "Private Sector Bank", "Public Sector Bank", "Other Bank",
    "Non Banking Financial Company (NBFC)", "Financial Institution",
    "Other Financial Services", "Financial Products Distributor",
    "Financial Technology (Fintech)",
}

_INSURANCE_INDUSTRIES = {"Life Insurance", "General Insurance"}


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

    # --- Industry Helpers ---

    def _get_industry(self, symbol: str) -> str:
        """Get industry for a symbol from index_constituents."""
        info = self.get_company_info(symbol)
        return info.get("industry", "Unknown")

    def _is_bfsi(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _BFSI_INDUSTRIES

    def _is_insurance(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _INSURANCE_INDUSTRIES

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

    def get_quarterly_balance_sheet(self, symbol: str, quarters: int = 8) -> list[dict]:
        """Quarterly balance sheet: assets, debt, equity, cash, investments (from yfinance)."""
        rows = self._store.get_quarterly_balance_sheet(symbol, limit=quarters)
        return _clean(rows)

    def get_quarterly_cash_flow(self, symbol: str, quarters: int = 8) -> list[dict]:
        """Quarterly cash flow: OCF, FCF, capex, working capital changes (from yfinance).
        Note: not available for all stocks (banks typically missing)."""
        rows = self._store.get_quarterly_cash_flow(symbol, limit=quarters)
        return _clean(rows)

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

    def get_estimate_revisions(self, symbol: str) -> list[dict]:
        """Latest EPS estimate trends and revision counts for all periods."""
        rows = self._store.get_estimate_revisions(symbol)
        return _clean(rows)

    def get_estimate_momentum(self, symbol: str) -> dict:
        """Computed momentum signal from estimate revisions."""
        rows = self._store.get_estimate_revisions(symbol)
        if not rows:
            return {}
        # Find the row with momentum data (all rows have the same score)
        score = rows[0].get("momentum_score")
        signal = rows[0].get("momentum_signal")

        # Build narrative
        parts = []
        for r in rows:
            period = r.get("period", "")
            current = r.get("eps_current")
            ago_90 = r.get("eps_90d_ago")
            if current and ago_90 and ago_90 != 0:
                change_pct = round((current - ago_90) / abs(ago_90) * 100, 1)
                if abs(change_pct) > 0.5:
                    label = {"0q": "Current Q", "+1q": "Next Q", "0y": "FY current", "+1y": "FY next"}.get(period, period)
                    direction = "up" if change_pct > 0 else "down"
                    parts.append(f"{label} estimates revised {direction} {abs(change_pct)}% in 90 days")

        # Count net revisions
        total_up = sum(r.get("revisions_up_30d") or 0 for r in rows)
        total_down = sum(r.get("revisions_down_30d") or 0 for r in rows)
        if total_up or total_down:
            parts.append(f"{total_up} upgrades vs {total_down} downgrades in 30 days")

        return _clean({
            "symbol": symbol.upper(),
            "momentum_score": score,
            "momentum_signal": signal,
            "narrative": ". ".join(parts) if parts else "No significant revision activity",
            "periods": rows,
        })

    # --- Events & Calendar ---

    def get_events_calendar(self, symbol: str) -> dict:
        """Upcoming events: next earnings date, ex-dividend date, consensus estimates."""
        from flowtracker.estimates_client import EstimatesClient
        ec = EstimatesClient()
        data = ec.fetch_events_calendar(symbol)
        return _clean(data) if data else {}

    # --- Dividend History ---

    def get_dividend_history(self, symbol: str, years: int = 10) -> list[dict]:
        """Annual dividend per share, yield, and payout ratio history.

        Computed from corporate_actions (yfinance dividends) + annual_financials (EPS) + valuation_snapshot (price).
        """
        # 1. Get yfinance dividends from corporate_actions
        divs = self._store._conn.execute(
            "SELECT ex_date, dividend_amount FROM corporate_actions "
            "WHERE symbol = ? AND source = 'yfinance' AND action_type = 'dividend' "
            "AND dividend_amount IS NOT NULL ORDER BY ex_date",
            (symbol.upper(),),
        ).fetchall()
        if not divs:
            return []

        # 2. Group by fiscal year (Apr-Mar): ex_date in Apr 2024–Mar 2025 → FY25
        from collections import defaultdict
        fy_dividends: dict[str, float] = defaultdict(float)
        for row in divs:
            ex_date = row["ex_date"]
            amount = row["dividend_amount"]
            try:
                from datetime import date as dt_date
                d = dt_date.fromisoformat(ex_date)
                # Indian FY: Apr Y to Mar Y+1 = FY(Y+1)
                fy_year = d.year + 1 if d.month >= 4 else d.year
                fy_label = f"FY{str(fy_year)[2:]}"
                fy_dividends[fy_label] += amount
            except (ValueError, TypeError):
                continue

        if not fy_dividends:
            return []

        # 3. Get EPS from annual_financials
        from flowtracker.fund_models import AnnualFinancials
        annuals = self._store.get_annual_financials(symbol, limit=years)
        eps_by_fy: dict[str, float] = {}
        price_by_fy: dict[str, float] = {}
        for a in annuals:
            fy_end = a.fiscal_year_end
            try:
                from datetime import date as dt_date
                d = dt_date.fromisoformat(fy_end)
                fy_year = d.year + 1 if d.month >= 4 else d.year
                fy_label = f"FY{str(fy_year)[2:]}"
                if a.eps:
                    eps_by_fy[fy_label] = a.eps
                if a.price:
                    price_by_fy[fy_label] = a.price
            except (ValueError, TypeError):
                continue

        # 4. Build result
        result = []
        sorted_fys = sorted(fy_dividends.keys(), key=lambda x: int(x[2:]) + (2000 if int(x[2:]) < 50 else 1900))
        prev_dps = None
        for fy in sorted_fys:
            dps = round(fy_dividends[fy], 2)
            entry: dict = {"fiscal_year": fy, "annual_dividend_per_share": dps}

            eps = eps_by_fy.get(fy)
            if eps and eps > 0:
                entry["eps"] = eps
                entry["payout_ratio_pct"] = round(dps / eps * 100, 1)

            price = price_by_fy.get(fy)
            if price and price > 0:
                entry["price_at_fy_end"] = price
                entry["dividend_yield_pct"] = round(dps / price * 100, 2)

            if prev_dps and prev_dps > 0:
                entry["dividend_growth_yoy_pct"] = round((dps - prev_dps) / prev_dps * 100, 1)

            prev_dps = dps
            result.append(entry)

        return _clean(result[-years:])

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

    # --- Company Profile & Documents ---

    def get_company_profile(self, symbol: str) -> dict:
        """Company about text, key points, and Screener URL from stored profile."""
        profile = self._store.get_company_profile(symbol)
        return _clean(profile) if profile else {}

    def get_company_documents(self, symbol: str, doc_type: str | None = None) -> list[dict]:
        """Concall transcripts, PPTs, recordings, and annual report URLs."""
        return _clean(self._store.get_documents(symbol, doc_type))

    # --- Peer Benchmarking ---

    def get_peer_metrics(self, symbol: str) -> dict:
        """FMP key metrics for subject + all peers, with yfinance valuation fallback."""
        peers = self._store.get_peers(symbol)

        # Subject metrics (latest) — FMP first, fallback to valuation_snapshot
        subject_rows = self._store.get_fmp_key_metrics(symbol, limit=1)
        if subject_rows:
            subject = _clean(subject_rows[0].model_dump())
            subject["symbol"] = symbol
            subject["source"] = "fmp"
        else:
            val_rows = self._store.get_valuation_history(symbol, days=7)
            if val_rows:
                subject = _clean(val_rows[-1].model_dump())
                subject["symbol"] = symbol
                subject["source"] = "yfinance"
            else:
                subject = {}

        # Peer metrics — use peer_symbol if available, else peer_name as symbol
        peer_data = []
        for p in peers:
            psym = p.get("peer_symbol") or p.get("peer_name")
            if not psym or psym == symbol:
                continue
            rows = self._store.get_fmp_key_metrics(psym, limit=1)
            if rows:
                d = _clean(rows[0].model_dump())
                d["symbol"] = psym
                d["source"] = "fmp"
                peer_data.append(d)
            else:
                val_rows = self._store.get_valuation_history(psym, days=7)
                if val_rows:
                    d = _clean(val_rows[-1].model_dump())
                    d["symbol"] = psym
                    d["source"] = "yfinance"
                    peer_data.append(d)

        return {"subject": subject, "peers": peer_data, "peer_count": len(peer_data)}

    def get_peer_growth(self, symbol: str) -> dict:
        """FMP financial growth rates for subject + all peers."""
        peers = self._store.get_peers(symbol)

        subject_rows = self._store.get_fmp_financial_growth(symbol, limit=1)
        subject = _clean(subject_rows[0].model_dump()) if subject_rows else {}
        if subject:
            subject["symbol"] = symbol

        peer_data = []
        for p in peers:
            psym = p.get("peer_symbol") or p.get("peer_name")
            if not psym or psym == symbol:
                continue
            rows = self._store.get_fmp_financial_growth(psym, limit=1)
            if rows:
                d = _clean(rows[0].model_dump())
                d["symbol"] = psym
                peer_data.append(d)

        return {"subject": subject, "peers": peer_data, "peer_count": len(peer_data)}

    _MATRIX_METRICS = [
        "pe_trailing", "pe_forward", "pb_ratio", "ev_ebitda", "ev_revenue",
        "ps_ratio", "peg_ratio", "roe", "roa", "operating_margin", "net_margin",
        "debt_to_equity", "dividend_yield", "revenue_growth", "earnings_growth",
        "market_cap",
    ]

    def get_valuation_matrix(self, symbol: str) -> dict:
        """Multi-metric valuation comparison matrix: subject vs all peers."""
        peers = self._store.get_peers(symbol)

        def _latest_snapshot(sym: str) -> dict | None:
            rows = self._store.get_valuation_history(sym, days=7)
            if not rows:
                return None
            d = _clean(rows[-1].model_dump())
            return {k: d.get(k) for k in self._MATRIX_METRICS if d.get(k) is not None}

        # Subject
        subject_data = _latest_snapshot(symbol) or {}
        subject_data["symbol"] = symbol

        # Peers
        peer_data = []
        for p in peers:
            psym = p.get("peer_symbol") or p.get("peer_name")
            if not psym or psym == symbol:
                continue
            snap = _latest_snapshot(psym)
            if snap:
                snap["symbol"] = psym
                peer_data.append(snap)

        # Collect all entries for sector stats
        all_entries = [subject_data] + peer_data

        # Sector stats + subject percentiles
        sector_stats: dict = {}
        subject_percentiles: dict = {}
        for metric in self._MATRIX_METRICS:
            values = [e[metric] for e in all_entries if metric in e and e[metric] is not None]
            if len(values) < 2:
                continue
            quantiles = statistics.quantiles(values, n=4)  # [p25, median, p75]
            sector_stats[metric] = {
                "median": quantiles[1],
                "p25": quantiles[0],
                "p75": quantiles[2],
                "min": min(values),
                "max": max(values),
            }
            subj_val = subject_data.get(metric)
            if subj_val is not None:
                subject_percentiles[metric] = _percentile_rank(values, subj_val)

        return {
            "subject": subject_data,
            "peers": peer_data,
            "sector_stats": sector_stats,
            "subject_percentiles": subject_percentiles,
            "peer_count": len(peer_data),
        }

    def get_concall_insights(self, symbol: str) -> dict:
        """Get pre-extracted concall insights from the vault.

        Returns structured concall data covering the last 4 quarters:
        operational metrics, financial metrics, management commentary,
        subsidiary updates, flags, and cross-quarter narrative themes.
        Falls back to v1 extraction if v2 doesn't exist.
        """
        import json
        from pathlib import Path

        vault = Path.home() / "vault" / "stocks" / symbol.upper() / "fundamentals"
        for filename in ["concall_extraction_v2.json", "concall_extraction.json"]:
            path = vault / filename
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["_source_file"] = filename
                    return data
                except (json.JSONDecodeError, OSError):
                    continue
        return {"error": f"No concall extraction found for {symbol}", "hint": "Run concall pipeline first"}

    def get_sector_kpis(self, symbol: str) -> dict:
        """Extract sector-specific KPIs from concall data using canonical field names.

        Reads the concall extraction JSON, identifies the company's sector, and
        pulls out KPIs matching the canonical keys defined in sector_kpis.py.
        Returns per-quarter values + trends for the sector-relevant metrics.
        """
        from flowtracker.research.sector_kpis import (
            get_kpis_for_industry,
            get_sector_for_industry,
        )

        industry = self._get_industry(symbol)
        sector = get_sector_for_industry(industry)
        if sector is None:
            return {"error": f"No sector KPI framework for industry '{industry}'"}

        kpi_defs = get_kpis_for_industry(industry)
        canonical_keys = {k["key"] for k in kpi_defs}
        key_labels = {k["key"]: k["label"] for k in kpi_defs}

        # Read concall extraction
        concall = self.get_concall_insights(symbol)
        if "error" in concall:
            return {"error": concall["error"], "sector": sector, "kpis_expected": [k["key"] for k in kpi_defs]}

        quarters = concall.get("quarters", [])
        if not quarters:
            return {"error": "No quarterly data in concall extraction", "sector": sector}

        # Extract KPIs from each quarter's operational_metrics + key_numbers_mentioned
        kpi_timeline: dict[str, list[dict]] = {k: [] for k in canonical_keys}

        for q in quarters:
            quarter_label = q.get("fy_quarter", q.get("label", ""))
            op_metrics = q.get("operational_metrics", {})
            key_numbers = q.get("key_numbers_mentioned", {})

            # Direct match on canonical keys
            for canonical_key in canonical_keys:
                value = None
                context = None

                # Check operational_metrics (structured)
                if canonical_key in op_metrics:
                    entry = op_metrics[canonical_key]
                    if isinstance(entry, dict):
                        value = entry.get("value")
                        context = entry.get("context")
                    else:
                        value = entry

                # Fallback: check key_numbers_mentioned (flat dict)
                if value is None and canonical_key in key_numbers:
                    value = key_numbers[canonical_key]

                # Fuzzy match: try without unit suffix and common variations
                if value is None:
                    base_key = canonical_key.rsplit("_", 1)[0]  # strip _pct, _cr, etc.
                    for src_key, src_val in {**op_metrics, **key_numbers}.items():
                        src_lower = src_key.lower().replace(" ", "_").replace("-", "_")
                        if base_key in src_lower or src_lower in base_key:
                            if isinstance(src_val, dict):
                                value = src_val.get("value")
                                context = src_val.get("context")
                            else:
                                value = src_val
                            break

                if value is not None:
                    entry = {"quarter": quarter_label, "value": value}
                    if context:
                        entry["context"] = context
                    kpi_timeline[canonical_key].append(entry)

        # Build result with only KPIs that have at least one value
        found_kpis = []
        missing_kpis = []
        for kpi_def in kpi_defs:
            key = kpi_def["key"]
            values = kpi_timeline[key]
            if values:
                found_kpis.append({
                    "key": key,
                    "label": kpi_def["label"],
                    "unit": kpi_def["unit"],
                    "values": values,
                })
            else:
                missing_kpis.append(key)

        # Cross-quarter metric trajectories (if available)
        cross = concall.get("cross_quarter_narrative", {})
        trajectories = cross.get("metric_trajectories", {})

        return {
            "symbol": symbol.upper(),
            "sector": sector,
            "industry": industry,
            "kpis_found": found_kpis,
            "kpis_missing": missing_kpis,
            "coverage": f"{len(found_kpis)}/{len(kpi_defs)} KPIs found in concall data",
            "metric_trajectories": trajectories,
            "quarters_analyzed": len(quarters),
        }

    # --- Analytical Profile (pre-computed) ---

    def get_analytical_profile(self, symbol: str) -> dict:
        """Get pre-computed analytical profile. One call replaces 9 individual tools.

        Returns the full analytical snapshot with JSON fields parsed.
        Updated weekly by compute-analytics.py.
        """
        import json as _json
        snapshot = self._store.get_analytical_snapshot(symbol)
        if not snapshot:
            return {"error": f"No analytical snapshot for {symbol}. Run compute-analytics.py first."}

        for field in ("composite_factors", "f_score_criteria", "m_score_variables", "rdcf_sensitivity", "errors"):
            raw = snapshot.get(field)
            if raw and isinstance(raw, str):
                try:
                    snapshot[field] = _json.loads(raw)
                except (_json.JSONDecodeError, TypeError):
                    pass

        return snapshot

    def screen_stocks(self, filters: dict) -> list[dict]:
        """Screen stocks by pre-computed analytical metrics."""
        import json as _json
        results = self._store.screen_by_analytics(filters)
        for row in results:
            for field in ("composite_factors", "f_score_criteria", "m_score_variables", "rdcf_sensitivity", "errors"):
                raw = row.get(field)
                if raw and isinstance(raw, str):
                    try:
                        row[field] = _json.loads(raw)
                    except (_json.JSONDecodeError, TypeError):
                        pass
        return results

    # --- Corporate Actions ---

    def get_corporate_actions(self, symbol: str) -> list[dict]:
        """All corporate actions (bonus, split, dividend, spinoff, buyback) for a stock."""
        return _clean(self._store.get_corporate_actions(symbol))

    def get_adjustment_factor(self, symbol: str, as_of_date: str | None = None) -> dict:
        """Cumulative share adjustment factor for a stock.

        Returns the factor to multiply old per-share numbers by to make them
        comparable to current per-share numbers.
        """
        actions = self._store.get_split_bonus_actions(symbol)  # ordered by date ASC
        if not actions:
            return {"symbol": symbol, "cumulative_factor": 1.0, "actions": []}

        cumulative = 1.0
        action_log = []
        for a in actions:
            if as_of_date and a["ex_date"] > as_of_date:
                break
            mult = a.get("multiplier") or 1.0
            cumulative *= mult
            action_log.append({
                "date": a["ex_date"],
                "type": a["action_type"],
                "ratio": a.get("ratio_text"),
                "multiplier": mult,
                "cumulative_factor": cumulative,
            })

        return {
            "symbol": symbol,
            "cumulative_factor": cumulative,
            "actions": action_log,
        }

    def get_adjusted_eps(self, symbol: str, quarters: int = 12) -> list[dict]:
        """Quarterly EPS adjusted for all splits and bonuses.

        Takes raw quarterly EPS and divides by the adjustment factor at each date,
        so all EPS values are comparable on the current share base.
        """
        quarterly = self._store.get_quarterly_results(symbol, limit=quarters)
        actions = self._store.get_split_bonus_actions(symbol)  # ordered by date ASC

        if not quarterly:
            return []

        # Build total cumulative factor
        total_factor = 1.0
        for a in actions:
            total_factor *= (a.get("multiplier") or 1.0)

        result = []
        for q in quarterly:
            d = q.model_dump()
            period = d.get("quarter_end", "")
            raw_eps = d.get("eps")

            # Compute factor at this period
            factor_at_period = 1.0
            for a in actions:
                if a["ex_date"] <= period:
                    factor_at_period *= (a.get("multiplier") or 1.0)

            # Normalize to current share base
            adjustment = total_factor / factor_at_period if factor_at_period > 0 else 1.0
            adjusted_eps = round(raw_eps / adjustment, 2) if raw_eps is not None and adjustment != 0 else raw_eps

            result.append({
                "period": period,
                "raw_eps": raw_eps,
                "adjusted_eps": adjusted_eps,
                "adjustment_factor": round(adjustment, 4),
                "revenue": d.get("revenue"),
                "net_income": d.get("net_income"),
            })

        return _clean(result)

    def get_financial_projections(self, symbol: str) -> dict:
        """3-year bear/base/bull financial projections based on historical trends.

        Uses last 3-5 years of actuals to project revenue, EBITDA, net income, and EPS.
        Accounts for corporate actions (splits/bonuses) in per-share calculations.
        """
        from flowtracker.research.projections import build_projections

        annual = self.get_annual_financials(symbol, years=10)
        if not annual:
            return {"error": f"No annual financial data for {symbol}"}

        # Get adjustment factor for per-share calculations
        adj = self.get_adjustment_factor(symbol)
        factor = adj.get("cumulative_factor", 1.0)

        return build_projections(annual, adjustment_factor=factor)

    def get_sector_benchmarks(self, symbol: str, metric: str | None = None) -> list[dict] | dict:
        """Sector benchmark statistics — single metric or all."""
        if metric:
            result = self._store.get_sector_benchmark(symbol, metric)
            return _clean(result) if result else {}
        return _clean(self._store.get_all_sector_benchmarks(symbol))

    def get_sector_overview_metrics(self, symbol: str) -> dict:
        """Industry-level overview: stock count, total market cap, median PE/PB/ROCE, valuation range, top stocks."""
        info = self.get_company_info(symbol)
        industry = info.get("industry", "Unknown")
        if industry == "Unknown":
            return {"error": f"No industry found for {symbol}"}
        return _clean(self._store.get_sector_valuation_summary(industry))

    def get_sector_flows(self, symbol: str) -> dict:
        """Aggregate MF ownership changes across all stocks in the subject's industry."""
        info = self.get_company_info(symbol)
        industry = info.get("industry", "Unknown")
        if industry == "Unknown":
            return {"error": f"No industry found for {symbol}"}
        return _clean(self._store.get_sector_mf_flows(industry))

    def get_sector_valuations(self, symbol: str) -> list[dict]:
        """All stocks in the subject's industry ranked by market cap with key metrics."""
        info = self.get_company_info(symbol)
        industry = info.get("industry", "Unknown")
        if industry == "Unknown":
            return []
        return _clean(self._store.get_sector_stocks_ranked(industry))

    # --- Catalysts ---

    def get_upcoming_catalysts(self, symbol: str, days: int = 90) -> list[dict]:
        """Upcoming events that could move the stock: earnings, board meetings, ex-dividend, RBI policy."""
        from flowtracker.catalyst_client import gather_catalysts
        events = gather_catalysts(symbol, self._store, days)
        return _clean([e.model_dump() for e in events])

    # --- Analytical Frameworks ---

    def get_earnings_quality(self, symbol: str) -> dict:
        """Earnings quality analysis: CFO/PAT, CFO/EBITDA, accrual ratio (up to 10Y)."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Bank earnings quality requires NPA/Provisioning data, which is currently unavailable."}

        annuals = self.get_annual_financials(symbol, years=10)
        if not annuals:
            return {"error": f"No annual financial data for {symbol}"}

        years = []
        for a in annuals:
            ni = a.get("net_income")
            tax = a.get("tax") or 0
            interest = a.get("interest") or 0
            depreciation = a.get("depreciation") or 0
            cfo = a.get("cfo")
            total_assets = a.get("total_assets")

            ebitda = (ni or 0) + tax + interest + depreciation
            entry: dict = {"fiscal_year_end": a.get("fiscal_year_end")}

            if ni and ni > 0 and cfo is not None:
                entry["cfo_pat"] = round(cfo / ni, 3)
            if ebitda > 0 and cfo is not None:
                entry["cfo_ebitda"] = round(cfo / ebitda, 3)
            if total_assets and total_assets > 0 and ni is not None and cfo is not None:
                entry["accruals"] = round((ni - cfo) / total_assets, 4)

            years.append(entry)

        # Compute averages
        cfo_pat_vals = [y["cfo_pat"] for y in years if "cfo_pat" in y]
        accrual_vals = [y["accruals"] for y in years if "accruals" in y]

        avg_3y_cfo_pat = round(sum(cfo_pat_vals[:3]) / len(cfo_pat_vals[:3]), 3) if len(cfo_pat_vals) >= 3 else None
        avg_5y_cfo_pat = round(sum(cfo_pat_vals[:5]) / len(cfo_pat_vals[:5]), 3) if len(cfo_pat_vals) >= 5 else None
        avg_3y_accruals = round(sum(accrual_vals[:3]) / len(accrual_vals[:3]), 4) if len(accrual_vals) >= 3 else None

        # Signal
        signal = "moderate"
        if avg_3y_cfo_pat is not None:
            if avg_3y_cfo_pat > 0.8:
                signal = "high_quality"
            elif avg_3y_cfo_pat < 0.5:
                signal = "low_quality"
        if avg_3y_accruals is not None and avg_3y_accruals > 0.10:
            signal = "warning"

        return _clean({
            "years": years,
            "avg_3y_cfo_pat": avg_3y_cfo_pat,
            "avg_5y_cfo_pat": avg_5y_cfo_pat,
            "avg_3y_accruals": avg_3y_accruals,
            "signal": signal,
        })

    def get_piotroski_score(self, symbol: str) -> dict:
        """Piotroski F-Score (0-9): profitability, leverage, operating efficiency."""
        annuals = self.get_annual_financials(symbol, years=2)
        if len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals)}"}

        t, t1 = annuals[0], annuals[1]  # t = latest, t1 = prior year
        is_bfsi = self._is_bfsi(symbol)

        criteria = []
        score = 0
        max_score = 9

        # Helper to safely get numeric values
        def g(row: dict, key: str) -> float | None:
            v = row.get(key)
            return float(v) if v is not None else None

        ni_t, ni_t1 = g(t, "net_income"), g(t1, "net_income")
        ta_t, ta_t1 = g(t, "total_assets"), g(t1, "total_assets")
        cfo_t = g(t, "cfo")
        borr_t, borr_t1 = g(t, "borrowings"), g(t1, "borrowings")
        rev_t, rev_t1 = g(t, "revenue"), g(t1, "revenue")
        eps_t, eps_t1 = g(t, "eps"), g(t1, "eps")
        interest_t, interest_t1 = g(t, "interest"), g(t1, "interest")
        op_t, op_t1 = g(t, "operating_profit"), g(t1, "operating_profit")
        rmc_t, rmc_t1 = g(t, "raw_material_cost"), g(t1, "raw_material_cost")

        # 1. ROA > 0
        roa_t = ni_t / ta_t if ni_t is not None and ta_t and ta_t > 0 else None
        roa_t1 = ni_t1 / ta_t1 if ni_t1 is not None and ta_t1 and ta_t1 > 0 else None
        passed = roa_t is not None and roa_t > 0
        criteria.append({"name": "ROA > 0", "passed": passed, "value": round(roa_t, 4) if roa_t is not None else None})
        if passed:
            score += 1

        # 2. CFO > 0
        passed = cfo_t is not None and cfo_t > 0
        criteria.append({"name": "CFO > 0", "passed": passed, "value": cfo_t})
        if passed:
            score += 1

        # 3. ΔROA > 0
        passed = roa_t is not None and roa_t1 is not None and roa_t > roa_t1
        criteria.append({"name": "ΔROA > 0", "passed": passed, "value": round(roa_t - roa_t1, 4) if roa_t is not None and roa_t1 is not None else None})
        if passed:
            score += 1

        # 4. Accruals < 0 (CFO > net income)
        passed = cfo_t is not None and ni_t is not None and cfo_t > ni_t
        criteria.append({"name": "Accruals < 0 (CFO > NI)", "passed": passed, "value": round(cfo_t - ni_t, 2) if cfo_t is not None and ni_t is not None else None})
        if passed:
            score += 1

        # 5. ΔLeverage < 0
        lev_t = borr_t / ta_t if borr_t is not None and ta_t and ta_t > 0 else None
        lev_t1 = borr_t1 / ta_t1 if borr_t1 is not None and ta_t1 and ta_t1 > 0 else None
        passed = lev_t is not None and lev_t1 is not None and lev_t < lev_t1
        note = "BFSI: rising leverage may indicate growth, not weakness" if is_bfsi else None
        entry5: dict = {"name": "ΔLeverage < 0", "passed": passed, "value": round(lev_t - lev_t1, 4) if lev_t is not None and lev_t1 is not None else None}
        if note:
            entry5["note"] = note
        criteria.append(entry5)
        if passed:
            score += 1

        # 6. ΔCurrent Ratio > 0 — try quarterly balance sheet
        qbs = self.get_quarterly_balance_sheet(symbol, quarters=2)
        if len(qbs) >= 2:
            def _current_ratio(bs: dict) -> float | None:
                ca = bs.get("current_assets")
                cl = bs.get("current_liabilities")
                if ca and cl and cl > 0:
                    return ca / cl
                return None
            cr_t = _current_ratio(qbs[0])
            cr_t1 = _current_ratio(qbs[1])
            passed = cr_t is not None and cr_t1 is not None and cr_t > cr_t1
            criteria.append({"name": "ΔCurrent Ratio > 0", "passed": passed, "value": round(cr_t - cr_t1, 4) if cr_t is not None and cr_t1 is not None else None})
            if passed:
                score += 1
        else:
            max_score -= 1
            criteria.append({"name": "ΔCurrent Ratio > 0", "passed": None, "value": None, "note": "Quarterly balance sheet unavailable, skipped"})

        # 7. No dilution — use adjusted shares (net_income / eps) to handle splits/bonuses
        adj_shares_t = ni_t / eps_t if ni_t is not None and eps_t and eps_t != 0 else None
        adj_shares_t1 = ni_t1 / eps_t1 if ni_t1 is not None and eps_t1 and eps_t1 != 0 else None
        if adj_shares_t is not None and adj_shares_t1 is not None:
            passed = adj_shares_t <= adj_shares_t1
            criteria.append({"name": "No dilution", "passed": passed, "value": round(adj_shares_t - adj_shares_t1, 2)})
            if passed:
                score += 1
        else:
            max_score -= 1
            criteria.append({"name": "No dilution", "passed": None, "value": None, "note": "EPS is 0 or None, skipped"})

        # 8. ΔGross Margin > 0
        if is_bfsi:
            # NIM proxy: (revenue - interest) / total_assets
            gm_t = (rev_t - (interest_t or 0)) / ta_t if rev_t is not None and ta_t and ta_t > 0 else None
            gm_t1 = (rev_t1 - (interest_t1 or 0)) / ta_t1 if rev_t1 is not None and ta_t1 and ta_t1 > 0 else None
            gm_label = "ΔNIM Proxy > 0"
        elif rmc_t is not None:
            gm_t = (rev_t - rmc_t) / rev_t if rev_t and rev_t > 0 else None
            gm_t1 = (rev_t1 - (rmc_t1 or 0)) / rev_t1 if rev_t1 and rev_t1 > 0 else None
            gm_label = "ΔGross Margin > 0"
        else:
            # Fallback: operating_profit / revenue
            gm_t = op_t / rev_t if op_t is not None and rev_t and rev_t > 0 else None
            gm_t1 = op_t1 / rev_t1 if op_t1 is not None and rev_t1 and rev_t1 > 0 else None
            gm_label = "ΔOperating Margin > 0"
        passed = gm_t is not None and gm_t1 is not None and gm_t > gm_t1
        criteria.append({"name": gm_label, "passed": passed, "value": round(gm_t - gm_t1, 4) if gm_t is not None and gm_t1 is not None else None})
        if passed:
            score += 1

        # 9. ΔAsset Turnover > 0
        at_t = rev_t / ta_t if rev_t is not None and ta_t and ta_t > 0 else None
        at_t1 = rev_t1 / ta_t1 if rev_t1 is not None and ta_t1 and ta_t1 > 0 else None
        passed = at_t is not None and at_t1 is not None and at_t > at_t1
        criteria.append({"name": "ΔAsset Turnover > 0", "passed": passed, "value": round(at_t - at_t1, 4) if at_t is not None and at_t1 is not None else None})
        if passed:
            score += 1

        # Signal
        ratio = score / max_score if max_score > 0 else 0
        if ratio >= 8 / 9:
            signal = "strong"
        elif ratio >= 5 / 9:
            signal = "moderate"
        else:
            signal = "weak"

        return _clean({
            "score": score,
            "max_score": max_score,
            "criteria": criteria,
            "signal": signal,
        })

    def get_beneish_score(self, symbol: str) -> dict:
        """Beneish M-Score: earnings manipulation probability (8-variable model)."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "M-Score not applicable to banks/NBFCs"}

        annuals = self.get_annual_financials(symbol, years=2)
        if len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals)}"}

        t, t1 = annuals[0], annuals[1]

        def g(row: dict, key: str) -> float | None:
            v = row.get(key)
            return float(v) if v is not None else None

        rev_t, rev_t1 = g(t, "revenue"), g(t1, "revenue")
        rec_t, rec_t1 = g(t, "receivables"), g(t1, "receivables")
        ni_t = g(t, "net_income")
        cfo_t = g(t, "cfo")
        ta_t, ta_t1 = g(t, "total_assets"), g(t1, "total_assets")
        nb_t, nb_t1 = g(t, "net_block"), g(t1, "net_block")
        cash_t, cash_t1 = g(t, "cash_and_bank"), g(t1, "cash_and_bank")
        dep_t, dep_t1 = g(t, "depreciation"), g(t1, "depreciation")
        borr_t, borr_t1 = g(t, "borrowings"), g(t1, "borrowings")
        ol_t, ol_t1 = g(t, "other_liabilities"), g(t1, "other_liabilities")
        rmc_t, rmc_t1 = g(t, "raw_material_cost"), g(t1, "raw_material_cost")
        emp_t, emp_t1 = g(t, "employee_cost"), g(t1, "employee_cost")
        oe_t, oe_t1 = g(t, "other_expenses_detail"), g(t1, "other_expenses_detail")
        sa_t, sa_t1 = g(t, "selling_and_admin"), g(t1, "selling_and_admin")

        variables: dict = {}

        # DSRI
        if rec_t is not None and rev_t and rev_t > 0 and rec_t1 is not None and rev_t1 and rev_t1 > 0:
            dsr_t = rec_t / rev_t
            dsr_t1 = rec_t1 / rev_t1
            if dsr_t1 > 0:
                variables["DSRI"] = round(dsr_t / dsr_t1, 4)
            else:
                return {"score": None, "error": "Insufficient data: missing DSRI (zero denominator)"}
        else:
            return {"score": None, "error": "Insufficient data: missing DSRI"}

        # GMI
        if rmc_t is not None and rmc_t1 is not None:
            gm_t = (rev_t - rmc_t) / rev_t if rev_t and rev_t > 0 else None
            gm_t1 = (rev_t1 - rmc_t1) / rev_t1 if rev_t1 and rev_t1 > 0 else None
        elif emp_t is not None and oe_t is not None and emp_t1 is not None and oe_t1 is not None:
            gm_t = (rev_t - emp_t - oe_t) / rev_t if rev_t and rev_t > 0 else None
            gm_t1 = (rev_t1 - emp_t1 - oe_t1) / rev_t1 if rev_t1 and rev_t1 > 0 else None
        else:
            return {"score": None, "error": "Insufficient data: missing GMI"}
        if gm_t is not None and gm_t1 is not None and gm_t > 0:
            variables["GMI"] = round(gm_t1 / gm_t, 4)
        else:
            return {"score": None, "error": "Insufficient data: missing GMI (zero margin)"}

        # AQI
        if ta_t and ta_t > 0 and ta_t1 and ta_t1 > 0 and nb_t is not None and nb_t1 is not None:
            hard_t = nb_t + (rec_t or 0) + (cash_t or 0)
            hard_t1 = nb_t1 + (rec_t1 or 0) + (cash_t1 or 0)
            aqi_num = 1 - hard_t / ta_t
            aqi_den = 1 - hard_t1 / ta_t1
            if aqi_den != 0:
                variables["AQI"] = round(aqi_num / aqi_den, 4)
            else:
                return {"score": None, "error": "Insufficient data: missing AQI (zero denominator)"}
        else:
            return {"score": None, "error": "Insufficient data: missing AQI"}

        # SGI
        if rev_t and rev_t1 and rev_t1 > 0:
            variables["SGI"] = round(rev_t / rev_t1, 4)
        else:
            return {"score": None, "error": "Insufficient data: missing SGI"}

        # DEPI
        if dep_t is not None and dep_t1 is not None and nb_t is not None and nb_t1 is not None:
            dep_rate_t = dep_t / (dep_t + nb_t) if (dep_t + nb_t) > 0 else None
            dep_rate_t1 = dep_t1 / (dep_t1 + nb_t1) if (dep_t1 + nb_t1) > 0 else None
            if dep_rate_t is not None and dep_rate_t1 is not None and dep_rate_t > 0:
                variables["DEPI"] = round(dep_rate_t1 / dep_rate_t, 4)
            else:
                return {"score": None, "error": "Insufficient data: missing DEPI (zero depreciation rate)"}
        else:
            return {"score": None, "error": "Insufficient data: missing DEPI"}

        # SGAI
        sga_t = sa_t if sa_t is not None else ((emp_t or 0) + (oe_t or 0) if emp_t is not None or oe_t is not None else None)
        sga_t1 = sa_t1 if sa_t1 is not None else ((emp_t1 or 0) + (oe_t1 or 0) if emp_t1 is not None or oe_t1 is not None else None)
        if sga_t is not None and sga_t1 is not None and rev_t and rev_t > 0 and rev_t1 and rev_t1 > 0:
            sgai_t = sga_t / rev_t
            sgai_t1 = sga_t1 / rev_t1
            if sgai_t1 > 0:
                variables["SGAI"] = round(sgai_t / sgai_t1, 4)
            else:
                return {"score": None, "error": "Insufficient data: missing SGAI (zero denominator)"}
        else:
            return {"score": None, "error": "Insufficient data: missing SGAI"}

        # TATA
        if ni_t is not None and cfo_t is not None and ta_t and ta_t > 0:
            variables["TATA"] = round((ni_t - cfo_t) / ta_t, 4)
        else:
            return {"score": None, "error": "Insufficient data: missing TATA"}

        # LVGI
        if ta_t and ta_t > 0 and ta_t1 and ta_t1 > 0 and borr_t is not None and borr_t1 is not None:
            lev_t = (borr_t + (ol_t or 0)) / ta_t
            lev_t1 = (borr_t1 + (ol_t1 or 0)) / ta_t1
            if lev_t1 > 0:
                variables["LVGI"] = round(lev_t / lev_t1, 4)
            else:
                return {"score": None, "error": "Insufficient data: missing LVGI (zero denominator)"}
        else:
            return {"score": None, "error": "Insufficient data: missing LVGI"}

        # M-Score
        m = (-4.84
             + 0.920 * variables["DSRI"]
             + 0.528 * variables["GMI"]
             + 0.404 * variables["AQI"]
             + 0.892 * variables["SGI"]
             + 0.115 * variables["DEPI"]
             - 0.172 * variables["SGAI"]
             + 4.679 * variables["TATA"]
             - 0.327 * variables["LVGI"])

        if m > -1.78:
            signal = "likely_manipulator"
        elif m < -2.22:
            signal = "unlikely_manipulator"
        else:
            signal = "gray_zone"

        return _clean({
            "m_score": round(m, 4),
            "signal": signal,
            "variables": variables,
            "data_quality": "8/8 variables computed",
        })

    # --- Reverse DCF / Capex / Common Size (Batch 1B) ---

    def get_reverse_dcf(self, symbol: str) -> dict:
        """Bernstein-style reverse DCF: solve for implied growth, implied margin, + sensitivity matrix."""
        annual = self.get_annual_financials(symbol, years=10)
        if len(annual) < 2:
            return {"error": "Need at least 2 years of financials"}

        valuation = self.get_valuation_snapshot(symbol)
        market_cap_raw = valuation.get("market_cap")
        if not market_cap_raw or market_cap_raw <= 0:
            return {"error": "No market cap data"}
        # valuation_snapshot stores market_cap in rupees; financials are in crores
        market_cap = market_cap_raw / 1e7

        latest = annual[0]  # most recent year
        prev = annual[1]
        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)

        if is_bfsi:
            # FCFE model: discount net_income at cost of equity
            base_cf = latest.get("net_income", 0)
            if not base_cf or base_cf <= 0:
                return {"error": "Negative/zero net income — cannot run reverse DCF"}
            discount_rate = 0.14  # Cost of equity for Indian banks
            target = market_cap  # FCFE model → PV = Market Cap directly
            model = "FCFE"
            cash = 0
            borrowings = 0
            capex = 0
        else:
            # FCFF model: discount FCF at WACC, then bridge EV→MCap
            net_block_t = latest.get("net_block", 0) or 0
            net_block_t1 = prev.get("net_block", 0) or 0
            cwip_t = latest.get("cwip", 0) or 0
            cwip_t1 = prev.get("cwip", 0) or 0
            depr = latest.get("depreciation", 0) or 0
            cfo = latest.get("cfo", 0) or 0

            # Capex = ΔNet_Block + ΔCWIP + Depreciation (NOT CFI)
            capex = (net_block_t - net_block_t1) + (cwip_t - cwip_t1) + depr
            base_cf = cfo - capex

            if base_cf <= 0:
                # Fallback to net_income
                base_cf = latest.get("net_income", 0) or 0
                if base_cf <= 0:
                    return {"error": "Negative/zero FCF and net income — cannot run reverse DCF"}

            cash = latest.get("cash_and_bank", 0) or 0
            borrowings = latest.get("borrowings", 0) or 0
            discount_rate = 0.12  # WACC for Indian large-cap
            target = market_cap - cash + borrowings  # Target = Enterprise Value
            model = "FCFF"

        terminal_g = 0.05  # 5% nominal GDP growth

        # --- 1. Implied Growth Solve (existing) ---
        def dcf_value(g):
            pv = sum(base_cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
            terminal = base_cf * (1 + g) ** 10 * (1 + terminal_g) / (discount_rate - terminal_g)
            pv += terminal / (1 + discount_rate) ** 10
            return pv

        lo, hi = -0.20, 0.60
        for _ in range(100):
            mid = (lo + hi) / 2
            if dcf_value(mid) < target:
                lo = mid
            else:
                hi = mid
        implied_g = round((lo + hi) / 2, 4)

        # Historical CAGRs for context
        revenues = [(a.get("fiscal_year_end", ""), a.get("revenue", 0)) for a in annual if a.get("revenue")]
        cagr_3y = cagr_5y = None
        if len(revenues) >= 4:
            cagr_3y = round((revenues[0][1] / revenues[3][1]) ** (1/3) - 1, 4) if revenues[3][1] > 0 else None
        if len(revenues) >= 6:
            cagr_5y = round((revenues[0][1] / revenues[5][1]) ** (1/5) - 1, 4) if revenues[5][1] > 0 else None

        # --- 2. Implied Margin Solve (NEW — non-BFSI only) ---
        current_revenue = latest.get("revenue", 0) or 0
        current_net_income = latest.get("net_income", 0) or 0
        current_margin = round(current_net_income / current_revenue, 4) if current_revenue > 0 else 0
        num_shares = latest.get("num_shares", 0) or 0
        current_price = valuation.get("price")

        implied_margin = None
        hist_g = cagr_3y or cagr_5y or 0.10  # fallback 10%

        if not is_bfsi and current_revenue > 0:
            # Reinvestment rate: capex as fraction of earnings, capped at 80%
            reinvestment = min(capex / base_cf, 0.80) if base_cf > 0 else 0.30

            def dcf_with_margin(margin):
                cf_year0 = current_revenue * margin * (1 - reinvestment)
                pv = sum(cf_year0 * (1 + hist_g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                terminal = cf_year0 * (1 + hist_g) ** 10 * (1 + terminal_g) / (discount_rate - terminal_g)
                pv += terminal / (1 + discount_rate) ** 10
                return pv

            lo_m, hi_m = 0.01, 0.50
            for _ in range(100):
                mid_m = (lo_m + hi_m) / 2
                if dcf_with_margin(mid_m) < target:
                    lo_m = mid_m
                else:
                    hi_m = mid_m
            implied_margin = round((lo_m + hi_m) / 2, 4)

        # --- 3. Sensitivity Matrix (NEW) ---
        sensitivity = []
        if not is_bfsi and current_revenue > 0:
            reinvestment = min(capex / base_cf, 0.80) if base_cf > 0 else 0.30
            growth_scenarios = [0.05, 0.10, 0.15, 0.20, 0.25]
            margin_scenarios = [0.05, 0.08, 0.12, 0.16, 0.20]

            for g in growth_scenarios:
                for m in margin_scenarios:
                    cf = current_revenue * m * (1 - reinvestment)
                    pv = sum(cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                    terminal = cf * (1 + g) ** 10 * (1 + terminal_g) / (discount_rate - terminal_g)
                    pv += terminal / (1 + discount_rate) ** 10
                    implied_mcap = pv + cash - borrowings
                    # implied_mcap is in crores, num_shares is actual count → convert crores to rupees
                    implied_price = round(implied_mcap * 1e7 / num_shares, 2) if num_shares > 0 else None
                    sensitivity.append({"growth": g, "margin": m, "implied_price": implied_price})
        elif is_bfsi:
            # BFSI: use book_value × ROE instead of revenue × margin
            equity_capital = latest.get("equity_capital", 0) or 0
            reserves = latest.get("reserves", 0) or 0
            book_value = equity_capital + reserves
            roe_scenarios = [0.10, 0.12, 0.14, 0.16, 0.18]
            growth_scenarios = [0.05, 0.10, 0.15, 0.20, 0.25]

            for g in growth_scenarios:
                for roe in roe_scenarios:
                    cf = book_value * roe
                    pv = sum(cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                    terminal = cf * (1 + g) ** 10 * (1 + terminal_g) / (discount_rate - terminal_g)
                    pv += terminal / (1 + discount_rate) ** 10
                    # pv is in crores, num_shares is actual count → convert crores to rupees
                    implied_price = round(pv * 1e7 / num_shares, 2) if num_shares > 0 else None
                    sensitivity.append({"growth": g, "roe": roe, "implied_price": implied_price})

        # --- 4. Enhanced Assessment ---
        hist = cagr_3y or cagr_5y
        if hist is not None:
            if implied_g > hist + 0.05:
                growth_view = f"growth acceleration ({implied_g:.0%} vs {hist:.0%} historical)"
            elif implied_g < hist - 0.05:
                growth_view = f"growth deceleration ({implied_g:.0%} vs {hist:.0%} historical)"
            else:
                growth_view = f"growth continuation ({implied_g:.0%} ≈ {hist:.0%} historical)"

            if implied_margin is not None and current_margin > 0:
                if implied_margin > current_margin + 0.03:
                    margin_view = f"margin expansion ({implied_margin:.0%} implied vs {current_margin:.0%} current)"
                elif implied_margin < current_margin - 0.03:
                    margin_view = f"margin compression ({implied_margin:.0%} implied vs {current_margin:.0%} current)"
                else:
                    margin_view = f"stable margins ({implied_margin:.0%} ≈ {current_margin:.0%} current)"
                assessment = f"Market is pricing in {growth_view} + {margin_view}"
            else:
                assessment = f"Market is pricing in {growth_view}"
        else:
            assessment = f"Implied growth rate: {implied_g:.0%}"

        return {
            "implied_growth_rate": implied_g,
            "implied_margin": implied_margin,
            "current_margin": current_margin,
            "base_cf_used": round(base_cf, 2),
            "market_cap": market_cap,
            "model": model,
            "discount_rate": discount_rate,
            "historical_3y_cagr": cagr_3y,
            "historical_5y_cagr": cagr_5y,
            "sensitivity": sensitivity,
            "current_price": current_price,
            "assessment": assessment,
        }

    def get_capex_cycle(self, symbol: str) -> dict:
        """CWIP/Capex tracking with phase detection."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Capex cycle not applicable to BFSI/Insurance"}

        annual = self.get_annual_financials(symbol, years=10)
        if len(annual) < 2:
            return {"error": "Need at least 2 years of financials"}

        years_data = []
        for i, row in enumerate(annual):
            net_block = row.get("net_block", 0) or 0
            cwip_val = row.get("cwip", 0) or 0
            revenue = row.get("revenue", 0) or 0
            depr = row.get("depreciation", 0) or 0

            entry = {
                "fiscal_year": row.get("fiscal_year_end", ""),
                "net_block": net_block,
                "cwip": cwip_val,
                "cwip_to_netblock": round(cwip_val / net_block, 3) if net_block > 0 else None,
                "fixed_asset_turnover": round(revenue / net_block, 2) if net_block > 0 else None,
            }

            if i < len(annual) - 1:
                prev = annual[i + 1]
                prev_nb = prev.get("net_block", 0) or 0
                prev_cwip = prev.get("cwip", 0) or 0
                capex = (net_block - prev_nb) + (cwip_val - prev_cwip) + depr
                entry["capex"] = round(capex, 2)
                entry["capex_intensity"] = round(capex / revenue, 3) if revenue > 0 else None
                entry["netblock_growth_yoy"] = round((net_block - prev_nb) / prev_nb, 3) if prev_nb > 0 else None

            years_data.append(entry)

        # Phase detection from latest year
        latest = years_data[0]
        cwip_nb = latest.get("cwip_to_netblock")
        nb_growth = latest.get("netblock_growth_yoy")
        prev_cwip_nb = years_data[1].get("cwip_to_netblock") if len(years_data) > 1 else None
        prev_fat = years_data[1].get("fixed_asset_turnover") if len(years_data) > 1 else None
        curr_fat = latest.get("fixed_asset_turnover")

        if cwip_nb is not None and cwip_nb > 0.3 and prev_cwip_nb is not None and cwip_nb > prev_cwip_nb:
            phase = "Investing"
        elif prev_cwip_nb is not None and cwip_nb is not None and cwip_nb < prev_cwip_nb and nb_growth is not None and nb_growth > 0.10:
            phase = "Commissioning"
        elif cwip_nb is not None and cwip_nb < 0.1 and curr_fat is not None and prev_fat is not None and curr_fat > prev_fat:
            phase = "Harvesting"
        else:
            phase = "Mature"

        return {"years": years_data, "phase": phase}

    def get_common_size_pl(self, symbol: str) -> dict:
        """Common size P&L — all items as % of revenue (or Total Income for BFSI)."""
        annual = self.get_annual_financials(symbol, years=10)
        if not annual:
            return {"error": "No annual financial data"}

        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)

        years_data = []
        for row in annual:
            revenue = row.get("revenue", 0) or 0
            other_income = row.get("other_income", 0) or 0

            # BFSI: denominator = Total Income (revenue + other_income)
            # Non-BFSI: denominator = revenue
            denom = (revenue + other_income) if is_bfsi else revenue
            if denom <= 0:
                continue

            entry = {"fiscal_year": row.get("fiscal_year_end", "")}

            for field, label in [
                ("raw_material_cost", "raw_material_pct"),
                ("employee_cost", "employee_pct"),
                ("other_expenses_detail", "other_expenses_pct"),
                ("depreciation", "depreciation_pct"),
                ("interest", "interest_pct"),
                ("tax", "tax_pct"),
                ("net_income", "net_margin_pct"),
                ("other_income", "other_income_pct"),
            ]:
                val = row.get(field)
                if val is not None:
                    entry[label] = round(val / denom * 100, 2)

            # EBIT % = (PBT + interest - other_income) / denom
            pbt = row.get("profit_before_tax")
            interest = row.get("interest")
            if pbt is not None and interest is not None:
                ebit = pbt + (interest or 0) - (other_income or 0)
                entry["ebit_pct"] = round(ebit / denom * 100, 2)

            entry["denominator"] = "total_income" if is_bfsi else "revenue"
            entry["denominator_value"] = round(denom, 2)

            years_data.append(entry)

        if not years_data:
            return {"error": "No valid financial years with revenue data"}

        # Highlights
        latest = years_data[0]
        cost_fields = ["raw_material_pct", "employee_pct", "other_expenses_pct", "depreciation_pct", "interest_pct"]
        costs = {f: latest.get(f) for f in cost_fields if latest.get(f) is not None}
        biggest_cost = max(costs, key=costs.get) if costs else None

        # Fastest growing cost (latest vs 3Y ago)
        fastest_growing = None
        if len(years_data) >= 4:
            old = years_data[3]
            max_increase = 0
            for f in cost_fields:
                curr_v = latest.get(f)
                old_v = old.get(f)
                if curr_v is not None and old_v is not None and old_v > 0:
                    increase = curr_v - old_v
                    if increase > max_increase:
                        max_increase = increase
                        fastest_growing = f

        return {
            "years": years_data,
            "is_bfsi": is_bfsi,
            "biggest_cost": biggest_cost,
            "fastest_growing_cost": fastest_growing,
        }

    # --- Consensus Estimates (Batch 2A) ---

    def get_revenue_estimates(self, symbol: str) -> dict:
        """Consensus revenue estimates from analyst coverage."""
        from flowtracker.estimates_client import EstimatesClient
        client = EstimatesClient()
        result = client.fetch_revenue_estimates(symbol)
        if result is None:
            return {"estimates_available": False, "message": "No analyst consensus data available for this ticker."}
        return result

    def get_growth_estimates(self, symbol: str) -> dict:
        """Growth estimates: stock vs index trend for current/next periods."""
        from flowtracker.estimates_client import EstimatesClient
        client = EstimatesClient()
        result = client.fetch_growth_estimates(symbol)
        if result is None:
            return {"estimates_available": False, "message": "No growth estimate data available for this ticker."}
        return result

    # --- BFSI Metrics (Batch 3) ---

    def get_bfsi_metrics(self, symbol: str) -> dict:
        """Bank/NBFC-specific metrics: NIM, ROA, Cost-to-Income, P/B, equity multiplier."""
        if self._is_insurance(symbol):
            return {"skipped": True, "reason": "Insurance reporting structure incompatible with standard BFSI metrics"}
        if not self._is_bfsi(symbol):
            return {"skipped": True, "reason": f"{symbol} is not a BFSI stock"}

        annual = self.get_annual_financials(symbol, years=5)
        if not annual:
            return {"error": "No annual financial data"}

        valuation = self.get_valuation_snapshot(symbol)
        current_price = valuation.get("price")

        years_data = []
        for row in annual:
            revenue = row.get("revenue", 0) or 0  # interest earned
            interest = row.get("interest", 0) or 0  # interest expended
            total_assets = row.get("total_assets", 0) or 0
            net_income = row.get("net_income", 0) or 0
            employee_cost = row.get("employee_cost", 0) or 0
            other_exp = row.get("other_expenses_detail", 0) or 0
            other_income = row.get("other_income", 0) or 0
            equity_capital = row.get("equity_capital", 0) or 0
            reserves = row.get("reserves", 0) or 0
            num_shares = row.get("num_shares", 0) or 0
            borrowings = row.get("borrowings", 0) or 0

            nii = revenue - interest
            net_worth = equity_capital + reserves

            entry = {"fiscal_year": row.get("fiscal_year_end", "")}

            # NIM proxy = NII / total_assets
            if total_assets > 0:
                entry["nim_pct"] = round(nii / total_assets * 100, 2)

            # ROA
            if total_assets > 0:
                entry["roa_pct"] = round(net_income / total_assets * 100, 2)

            # Cost-to-Income
            operating_income = nii + other_income
            if operating_income > 0:
                entry["cost_to_income_pct"] = round((employee_cost + other_exp) / operating_income * 100, 2)

            # Book Value / Share
            if num_shares > 0:
                bvps = net_worth / num_shares
                entry["book_value_per_share"] = round(bvps, 2)
                # P/B (use current price if available)
                if current_price and current_price > 0:
                    entry["pb_ratio"] = round(current_price / bvps, 2)

            # Equity Multiplier = total_assets / net_worth (true leverage including deposits)
            if net_worth > 0:
                entry["equity_multiplier"] = round(total_assets / net_worth, 2)

            entry["nii"] = round(nii, 2)
            entry["net_worth"] = round(net_worth, 2)

            years_data.append(entry)

        return {"is_bfsi": True, "years": years_data}

    # --- Price Performance ---

    # Sector index mapping for price performance
    _SECTOR_INDEX = {
        "Private Sector Bank": "^NSEBANK", "Public Sector Bank": "^NSEBANK",
        "Other Bank": "^NSEBANK",
        "IT - Software": "^CNXIT", "IT - Services": "^CNXIT",
        "Pharmaceuticals": "^CNXPHARMA", "FMCG": "^CNXFMCG",
        "Automobile": "NIFTY_AUTO.NS", "Auto Components": "NIFTY_AUTO.NS",
        "Realty": "NIFTY_REALTY.NS",
        "Non Banking Financial Company (NBFC)": "^NSEBANK",
    }

    def get_price_performance(self, symbol: str, index_cache: dict | None = None) -> dict:
        """Price return vs Nifty 50 and sector index (excl. dividends).

        Args:
            index_cache: Optional dict of {ticker: {date_str: close_price}} for batch mode.
                When provided, skips live yfinance fetch. When None, fetches live.
        """
        from datetime import date, timedelta

        today = date.today()

        # Period definitions
        period_defs = [
            ("1M", 30), ("3M", 90), ("6M", 180), ("1Y", 365),
        ]

        # Get stock prices from DB (daily_stock_data)
        conn = self._store._conn
        stock_rows = conn.execute(
            "SELECT date, close FROM daily_stock_data WHERE symbol = ? ORDER BY date DESC LIMIT 400",
            (symbol.upper(),)
        ).fetchall()

        if not stock_rows:
            return {"error": f"No daily price data for {symbol}"}

        stock_prices = {row[0]: row[1] for row in stock_rows}
        latest_date = max(stock_prices.keys())
        latest_price = stock_prices[latest_date]

        # Nifty 50 index prices — from cache or live yfinance
        if index_cache and "^NSEI" in index_cache:
            nifty_prices = index_cache["^NSEI"]
        else:
            try:
                import yfinance as yf
                nifty = yf.Ticker("^NSEI")
                hist = nifty.history(period="1y")
                nifty_prices = {str(d.date()): row["Close"] for d, row in hist.iterrows()}
            except Exception:
                nifty_prices = {}

        industry = self._get_industry(symbol)
        sector_idx = self._SECTOR_INDEX.get(industry)
        sector_prices = {}
        if sector_idx:
            if index_cache and sector_idx in index_cache:
                sector_prices = index_cache[sector_idx]
            else:
                try:
                    import yfinance as yf
                    sec = yf.Ticker(sector_idx)
                    hist = sec.history(period="1y")
                    sector_prices = {str(d.date()): row["Close"] for d, row in hist.iterrows()}
                except Exception:
                    pass

        def find_price(prices_dict, target_date):
            """Find closest price on or before target date (within 5 day tolerance)."""
            for offset in range(6):
                d = str(target_date - timedelta(days=offset))
                if d in prices_dict:
                    return prices_dict[d]
            return None

        periods = []
        for label, days in period_defs:
            start_date = today - timedelta(days=days)

            stock_start = find_price(stock_prices, start_date)
            if stock_start is None or stock_start <= 0:
                continue

            stock_return = round((latest_price - stock_start) / stock_start * 100, 2)

            entry = {"period": label, "stock_return": stock_return}

            # Nifty return
            nifty_end = find_price(nifty_prices, today)
            nifty_start = find_price(nifty_prices, start_date)
            if nifty_start and nifty_end and nifty_start > 0:
                nifty_return = round((nifty_end - nifty_start) / nifty_start * 100, 2)
                entry["nifty_return"] = nifty_return
                entry["excess_return"] = round(stock_return - nifty_return, 2)

            # Sector return
            if sector_prices:
                sec_end = find_price(sector_prices, today)
                sec_start = find_price(sector_prices, start_date)
                if sec_start and sec_end and sec_start > 0:
                    entry["sector_return"] = round((sec_end - sec_start) / sec_start * 100, 2)

            periods.append(entry)

        if not periods:
            return {"error": "Insufficient price data to compute returns"}

        # Overall outperformer flag (based on 1Y if available, else longest period)
        longest = periods[-1]
        outperformer = longest.get("excess_return", 0) > 0

        return {
            "symbol": symbol.upper(),
            "periods": periods,
            "return_type": "price_return_excl_dividends",
            "sector_index": sector_idx,
            "industry": industry,
            "outperformer": outperformer,
        }
