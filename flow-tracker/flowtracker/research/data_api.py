"""Unified data access for equity research — wraps FlowStore for agent tools."""

from __future__ import annotations

import statistics

from flowtracker.store import FlowStore
from flowtracker.utils import _clean


def _percentile_rank(values: list[float], value: float) -> float:
    """Simple percentile rank: % of values strictly below the given value."""
    below = sum(1 for v in values if v < value)
    return round(100 * below / len(values)) if values else 0


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
