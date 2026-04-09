"""Unified data access for equity research — wraps FlowStore for agent tools."""

from __future__ import annotations

import statistics
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from flowtracker.store import FlowStore
from flowtracker.utils import _clean


logger = logging.getLogger(__name__)


def _percentile_rank(values: list[float], value: float) -> float:
    """Simple percentile rank: % of values strictly below the given value."""
    below = sum(1 for v in values if v < value)
    return round(100 * below / len(values)) if values else 0


_BFSI_INDUSTRIES = {
    # yfinance strings
    "Banks - Regional", "Banks - Diversified", "Credit Services",
    "Mortgage Finance", "Financial Conglomerates",
    # Screener fallback strings
    "Private Sector Bank", "Public Sector Bank", "Other Bank",
    "Non Banking Financial Company (NBFC)", "Financial Institution",
    "Other Financial Services", "Financial Products Distributor",
    "Financial Technology (Fintech)", "Housing Finance Company",
    "Microfinance Institutions",
}

_INSURANCE_INDUSTRIES = {
    # yfinance
    "Insurance - Life", "Insurance - Diversified", "Insurance - Property & Casualty",
    "Insurance - Specialty", "Insurance - Reinsurance",
    # Screener
    "Life Insurance", "General Insurance",
}

_REALESTATE_INDUSTRIES = {
    # yfinance
    "Real Estate - Development", "Real Estate - Diversified", "Real Estate Services",
    # Screener
    "Residential Commercial Projects",
}

_METALS_INDUSTRIES = {
    # yfinance
    "Steel", "Aluminum", "Copper", "Other Industrial Metals & Mining",
    "Gold", "Silver", "Other Precious Metals & Mining", "Coal",
    # Screener
    "Iron & Steel", "Iron & Steel Products", "Aluminium", "Zinc",
    "Diversified Metals", "Industrial Minerals",
}

_TELECOM_INDUSTRIES = {
    # yfinance
    "Telecom Services",
    # Screener
    "Telecom - Cellular & Fixed line services", "Other Telecom Services",
}

_TELECOM_INFRA_INDUSTRIES = {
    # yfinance
    "Communication Equipment",
    # Screener
    "Telecom - Infrastructure", "Telecom - Equipment & Accessories",
}

_REGULATED_POWER_INDUSTRIES = {
    # yfinance
    "Utilities - Regulated Electric", "Utilities - Regulated Gas",
    "Utilities - Diversified",
    # Screener
    "Power Generation", "Power Distribution", "Power - Transmission",
}

_MERCHANT_POWER_INDUSTRIES = {
    # yfinance
    "Utilities - Independent Power Producers", "Utilities - Renewable",
    # Screener
    "Integrated Power Utilities",
}

_BROKER_INDUSTRIES = {
    # yfinance
    "Capital Markets",
    # Screener
    "Stockbroking & Allied",
}

_AMC_INDUSTRIES = {
    # yfinance
    "Asset Management",
    # Screener
    "Asset Management Company",
}

_EXCHANGE_INDUSTRIES = {
    # yfinance
    "Financial Data & Stock Exchanges",
    # Screener
    "Exchange and Data Platform",
    "Depositories Clearing Houses and Other Intermediaries",
}

_HOSPITAL_INDUSTRIES = {
    # yfinance
    "Medical Care Facilities", "Health Information Services",
    # Screener
    "Hospital", "Healthcare Service Provider",
}

_IT_INDUSTRIES = {
    # yfinance
    "Information Technology Services", "Software - Infrastructure",
    "Software - Application",
    # Screener
    "Computers - Software & Consulting", "IT Enabled Services",
    "Software Products", "Business Process Outsourcing (BPO)/ Knowledge Process Outsourcing (KPO)",
}

_GOLD_LOAN_KEYWORDS = {"gold", "muthoot", "manappuram"}

_MICROFINANCE_INDUSTRIES = {
    # yfinance: classified as Credit Services (shared with NBFCs) — use keywords
    "Microfinance Institutions",
}

_HOLDING_COMPANY_INDUSTRIES = {
    # yfinance
    "Conglomerates",
    # Screener
    "Holding Company", "Investment Company",
    "Diversified Commercial Services",
}
_HOLDING_COMPANY_KEYWORDS = {"holdings", "investment", "enterprises"}

_CONGLOMERATE_INDUSTRIES = {
    # yfinance
    "Conglomerates",
    # Screener
    "Diversified", "Conglomerate",
}
_CONGLOMERATE_KEYWORDS = {
    "reliance", "tata", "adani", "bajaj", "mahindra", "godrej",
    "aditya birla", "itc", "l&t", "larsen",
}


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

    # --- SOTP: Listed Subsidiaries ---

    def get_listed_subsidiaries(self, symbol: str) -> list[dict] | None:
        """Get listed subsidiary valuations for SOTP analysis.

        Reads parent→subsidiary mappings from DB, fetches live market caps
        from yfinance, and computes per-share value to the parent.
        Returns None if the company has no listed subsidiaries in DB.
        """
        subs = self._store.get_listed_subsidiaries(symbol)
        if not subs:
            return None

        import yfinance as yf
        parent_shares = self.get_valuation_snapshot(symbol).get("shares_outstanding", 0)
        if not parent_shares:
            return None

        results = []
        for row in subs:
            try:
                t = yf.Ticker(f"{row['sub_symbol']}.NS")
                sub_mcap = t.info.get("marketCap", 0) or 0
                sub_mcap_cr = sub_mcap / 1e7
                ownership = row["parent_ownership_pct"]
                parent_stake_cr = sub_mcap_cr * (ownership / 100)
                per_share_value = (parent_stake_cr * 1e7) / parent_shares if parent_shares else 0
                results.append({
                    "subsidiary": row["sub_name"],
                    "symbol": row["sub_symbol"],
                    "parent_ownership_pct": ownership,
                    "relationship": row.get("relationship", ""),
                    "subsidiary_market_cap_cr": round(sub_mcap_cr),
                    "parent_stake_value_cr": round(parent_stake_cr),
                    "per_share_value": round(per_share_value, 2),
                })
            except Exception:
                continue

        return results if results else None

    # --- Freshness Helpers ---

    def get_data_freshness(self, symbol: str) -> dict:
        """Get last-fetched timestamps for key data tables."""
        conn = self._store._conn
        symbol = symbol.upper()
        freshness = {}
        queries = {
            "quarterly_results": (
                "SELECT max(fetched_at) as last_fetched, max(quarter_end) as latest_period "
                "FROM quarterly_results WHERE symbol = ?"
            ),
            "annual_financials": (
                "SELECT max(fetched_at) as last_fetched, max(fiscal_year_end) as latest_period "
                "FROM annual_financials WHERE symbol = ?"
            ),
            "valuation_snapshot": (
                "SELECT max(fetched_at) as last_fetched, max(date) as latest_period "
                "FROM valuation_snapshot WHERE symbol = ?"
            ),
            "shareholding": (
                "SELECT max(fetched_at) as last_fetched, max(quarter_end) as latest_period "
                "FROM shareholding WHERE symbol = ?"
            ),
            "consensus_estimates": (
                "SELECT max(fetched_at) as last_fetched, max(date) as latest_period "
                "FROM consensus_estimates WHERE symbol = ?"
            ),
        }
        for table, sql in queries.items():
            try:
                row = conn.execute(sql, (symbol,)).fetchone()
                if row and row["last_fetched"]:
                    freshness[table] = {
                        "last_fetched": row["last_fetched"],
                        "latest_period": row["latest_period"],
                    }
            except Exception:
                pass
        return freshness

    # --- Industry Helpers ---

    def _get_industry(self, symbol: str) -> str:
        """Get industry for a symbol. Prefers yfinance (company_snapshot) over NSE/Screener."""
        # Primary: yfinance-sourced industry from company_snapshot (better classification)
        row = self._store._conn.execute(
            "SELECT industry FROM company_snapshot WHERE symbol = ?", (symbol,)
        ).fetchone()
        if row and row[0]:
            return row[0]
        # Fallback: index_constituents (NSE/Screener)
        info = self.get_company_info(symbol)
        return info.get("industry") or "Unknown"

    def _is_bfsi(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _BFSI_INDUSTRIES

    def _is_insurance(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _INSURANCE_INDUSTRIES

    def _is_realestate(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _REALESTATE_INDUSTRIES

    def _is_metals(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _METALS_INDUSTRIES

    def _is_telecom(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _TELECOM_INDUSTRIES

    def _is_telecom_infra(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _TELECOM_INFRA_INDUSTRIES

    def _is_regulated_power(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _REGULATED_POWER_INDUSTRIES

    def _is_merchant_power(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _MERCHANT_POWER_INDUSTRIES

    def _is_broker(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _BROKER_INDUSTRIES

    def _is_amc(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _AMC_INDUSTRIES

    def _is_exchange(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _EXCHANGE_INDUSTRIES

    def _is_hospital(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _HOSPITAL_INDUSTRIES

    def _is_it_services(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _IT_INDUSTRIES

    def _is_gold_loan_nbfc(self, symbol: str) -> bool:
        """Detect gold loan NBFCs by company name keywords + NBFC industry."""
        if not self._is_bfsi(symbol):
            return False
        info = self.get_company_info(symbol)
        name = info.get("company_name", "").lower()
        return any(kw in name for kw in _GOLD_LOAN_KEYWORDS)

    def _is_microfinance(self, symbol: str) -> bool:
        return self._get_industry(symbol) in _MICROFINANCE_INDUSTRIES

    def _is_holding_company(self, symbol: str) -> bool:
        industry = self._get_industry(symbol)
        if industry in _HOLDING_COMPANY_INDUSTRIES:
            return True
        name = self.get_company_info(symbol).get("company_name", "").lower()
        return any(kw in name for kw in _HOLDING_COMPANY_KEYWORDS) and industry not in _BFSI_INDUSTRIES

    def _is_conglomerate(self, symbol: str) -> bool:
        industry = self._get_industry(symbol)
        if industry in _CONGLOMERATE_INDUSTRIES:
            return True
        name = self.get_company_info(symbol).get("company_name", "").lower()
        return any(kw in name for kw in _CONGLOMERATE_KEYWORDS)

    def get_sector_type(self, symbol: str) -> str:
        """Return the sector classification for a symbol (used by dispatch)."""
        checks = [
            (self._is_insurance, "insurance"),
            (self._is_bfsi, "bfsi"),
            (self._is_realestate, "realestate"),
            (self._is_metals, "metals"),
            (self._is_regulated_power, "regulated_power"),
            (self._is_merchant_power, "merchant_power"),
            (self._is_broker, "broker"),
            (self._is_amc, "amc"),
            (self._is_exchange, "exchange"),
            (self._is_telecom, "telecom"),
            (self._is_telecom_infra, "telecom_infra"),
            (self._is_hospital, "hospital"),
        ]
        for checker, label in checks:
            if checker(symbol):
                return label
        return "general"

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
        if not hist:
            return {}
        snap = _clean(hist[-1].model_dump())
        # Pre-compute derived values so agents don't do unit math
        price = snap.get("price") or 0
        float_shares = snap.get("float_shares") or 0
        shares = snap.get("shares_outstanding") or 0
        mcap = snap.get("market_cap") or 0  # already in crores
        if float_shares and price:
            snap["free_float_mcap_cr"] = round(float_shares * price / 1e7, 2)
        if float_shares and shares:
            snap["free_float_pct"] = round(float_shares / shares * 100, 2)
        if snap.get("avg_volume") and price:
            snap["avg_daily_turnover_cr"] = round(snap["avg_volume"] * price / 1e7, 2)
        if shares:
            snap["shares_outstanding_lakh"] = round(shares / 1e5, 2)
        total_cash = snap.get("total_cash") or 0
        total_debt = snap.get("total_debt") or 0
        snap["net_cash_cr"] = round(total_cash - total_debt, 2)
        bvps = snap.get("book_value_per_share") or 0
        if bvps and shares:
            snap["total_book_value_cr"] = round(bvps * shares / 1e7, 2)
        rps = snap.get("revenue_per_share") or 0
        if rps and shares:
            snap["ttm_revenue_cr"] = round(rps * shares / 1e7, 2)
        # EPS derived from PE (single source of truth — prevents cross-agent PE disagreement)
        pe = snap.get("pe_trailing")
        if pe and price and pe > 0:
            snap["eps_ttm"] = round(price / pe, 2)
        pe_fwd = snap.get("pe_forward")
        if pe_fwd and price and pe_fwd > 0:
            snap["eps_forward"] = round(price / pe_fwd, 2)
        # Price vs 52-week range
        high = snap.get("fifty_two_week_high") or 0
        low = snap.get("fifty_two_week_low") or 0
        if high and price:
            snap["pct_below_52w_high"] = round((1 - price / high) * 100, 2)
        if low and price:
            snap["pct_above_52w_low"] = round((price / low - 1) * 100, 2)
        return snap

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

    def get_insider_transactions(self, symbol: str, days: int = 1825) -> list[dict]:
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
        """MF scheme-level month-over-month changes: which schemes added/trimmed this stock."""
        # Get current month holdings
        current = self._store.get_mf_stock_holdings(symbol)
        if not current:
            return []

        # Find the current month from the data
        months = sorted(set(r.month for r in current if hasattr(r, "month")))
        if not months:
            return _clean([r.model_dump() for r in current])

        curr_month = months[-1]
        # Compute previous month
        y, m = int(curr_month[:4]), int(curr_month[5:7])
        prev_month = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"

        # Build lookup by scheme for previous month
        prev_rows = self._store._conn.execute(
            "SELECT * FROM mf_scheme_holdings "
            "WHERE UPPER(stock_name) LIKE ? AND month = ? "
            "ORDER BY market_value_cr DESC",
            (f"%{symbol}%", prev_month),
        ).fetchall()
        prev_by_scheme = {r["scheme_name"]: r for r in prev_rows}

        changes = []
        for r in current:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            scheme = d.get("scheme_name", "")
            prev = prev_by_scheme.get(scheme)

            curr_val = d.get("market_value_cr") or 0
            prev_val = (prev["market_value_cr"] if prev else 0) or 0
            curr_qty = d.get("quantity") or 0
            prev_qty = (prev["quantity"] if prev else 0) or 0

            if prev:
                change_type = (
                    "increased" if curr_val > prev_val
                    else "decreased" if curr_val < prev_val
                    else "unchanged"
                )
                del prev_by_scheme[scheme]  # Mark as matched
            else:
                change_type = "new_entry"

            d["change_type"] = change_type
            d["prev_value_cr"] = round(prev_val, 2) if prev_val else None
            d["prev_quantity"] = prev_qty or None
            d["value_change_cr"] = round(curr_val - prev_val, 2) if prev_val else None
            changes.append(d)

        # Add schemes that exited (in prev but not in current)
        for scheme, prev in prev_by_scheme.items():
            changes.append({
                "scheme_name": scheme,
                "amc": prev["amc"],
                "stock_name": prev["stock_name"],
                "quantity": 0,
                "market_value_cr": 0,
                "pct_of_nav": 0,
                "change_type": "exited",
                "prev_value_cr": round(prev["market_value_cr"] or 0, 2),
                "prev_quantity": prev["quantity"],
                "value_change_cr": -round(prev["market_value_cr"] or 0, 2),
            })

        # Sort by absolute value change descending
        changes.sort(key=lambda x: abs(x.get("value_change_cr") or 0), reverse=True)
        return _clean(changes)

    def get_mf_conviction(self, symbol: str) -> dict:
        """MF conviction breadth: how many schemes/AMCs hold and are adding this stock."""
        current = self._store.get_mf_stock_holdings(symbol)
        if not current:
            return {"available": False, "reason": "No MF holdings data"}

        # Current month stats
        schemes: set[str] = set()
        amcs: set[str] = set()
        total_value = 0.0
        for r in current:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            schemes.add(d.get("scheme_name", ""))
            amcs.add(d.get("amc", ""))
            total_value += d.get("market_value_cr") or 0

        # Get previous month for trend
        months = sorted(set(
            (r.month if hasattr(r, "month") else r.get("month", ""))
            for r in current
        ))
        curr_month = months[-1] if months else ""

        prev_count = 0
        if curr_month:
            y, m = int(curr_month[:4]), int(curr_month[5:7])
            prev_month = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
            prev_rows = self._store._conn.execute(
                "SELECT COUNT(DISTINCT scheme_name) as cnt FROM mf_scheme_holdings "
                "WHERE UPPER(stock_name) LIKE ? AND month = ?",
                (f"%{symbol}%", prev_month),
            ).fetchone()
            prev_count = prev_rows[0] if prev_rows else 0

        scheme_count = len(schemes)
        trend = "adding" if scheme_count > prev_count else "trimming" if scheme_count < prev_count else "stable"

        # Top schemes by value
        sorted_holdings = sorted(
            current,
            key=lambda r: (r.market_value_cr if hasattr(r, "market_value_cr") else r.get("market_value_cr") or 0),
            reverse=True,
        )
        top_schemes = []
        for r in sorted_holdings[:10]:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            top_schemes.append({
                "scheme": d.get("scheme_name", ""),
                "amc": d.get("amc", ""),
                "value_cr": round(d.get("market_value_cr") or 0, 2),
                "pct_of_nav": d.get("pct_of_nav"),
            })

        return {
            "available": True,
            "month": curr_month,
            "schemes_holding": scheme_count,
            "amcs_holding": len(amcs),
            "total_mf_value_cr": round(total_value, 2),
            "prev_month_schemes": prev_count,
            "scheme_trend": trend,
            "scheme_change": scheme_count - prev_count,
            "top_schemes": top_schemes,
        }

    # --- Market Signals ---

    def get_delivery_trend(self, symbol: str, days: int = 30) -> list[dict]:
        """Delivery % trend — Screener chart (weekly, 20yr) with bhavcopy fallback (daily, recent).

        Returns list of {"date": str, "delivery_pct": float} sorted oldest-first.
        """
        # Primary: Screener chart Volume_Delivery (weekly, ~20 years of history)
        chart_data = self._store.get_chart_data(symbol, "price")
        for ds in chart_data:
            if ds["metric"] == "Volume_Delivery":
                points = ds["values"]
                if points:
                    # Trim to requested window if needed
                    if days and days < 9999:
                        from datetime import date as dt_date, timedelta
                        cutoff = (dt_date.today() - timedelta(days=days)).isoformat()
                        points = [p for p in points if p["date"] >= cutoff]
                    return [{"date": p["date"], "delivery_pct": p["value"]} for p in points]

        # Fallback: bhavcopy daily data (5-30 days typically)
        rows = self._store.get_stock_delivery(symbol, days=days)
        return _clean([{"date": r.date, "delivery_pct": r.delivery_pct} for r in rows if r.delivery_pct])

    def get_delivery_analysis(self, symbol: str, days: int = 90) -> dict:
        """Multi-week delivery analysis: trend, acceleration, volume-delivery divergence."""
        rows = self._store.get_stock_delivery(symbol, days=days)
        if not rows:
            return {"available": False, "reason": "No delivery data"}

        # Convert to dicts with value extraction
        data = []
        for r in rows:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            dp = d.get("delivery_pct")
            vol = d.get("volume") or 0
            close = d.get("close") or 0
            if dp is not None:
                data.append({"date": d.get("date", ""), "delivery_pct": dp, "volume": vol, "close": close})

        if len(data) < 5:
            return {"available": False, "reason": "Insufficient delivery data"}

        # Sort oldest first for trend calc
        data.sort(key=lambda x: x["date"])

        deliveries = [d["delivery_pct"] for d in data]
        volumes = [d["volume"] for d in data]

        # Weekly averages (last 4 weeks vs prior 4 weeks)
        recent_4w = deliveries[-20:] if len(deliveries) >= 20 else deliveries[-len(deliveries) // 2:]
        prior_4w = deliveries[-40:-20] if len(deliveries) >= 40 else deliveries[:len(deliveries) // 2]

        avg_recent = statistics.mean(recent_4w) if recent_4w else 0
        avg_prior = statistics.mean(prior_4w) if prior_4w else 0
        avg_overall = statistics.mean(deliveries)

        # Trend direction
        diff = avg_recent - avg_prior
        if diff > 3:
            trend = "rising"
        elif diff < -3:
            trend = "falling"
        else:
            trend = "stable"

        # Volume-delivery divergence: high vol + low delivery = speculative
        recent_vol = statistics.mean(volumes[-20:]) if len(volumes) >= 20 else statistics.mean(volumes)
        prior_vol = statistics.mean(volumes[:-20]) if len(volumes) > 20 else recent_vol
        vol_rising = recent_vol > prior_vol * 1.2  # 20% higher
        delivery_falling = avg_recent < avg_prior - 3

        divergence = "none"
        if vol_rising and delivery_falling:
            divergence = "speculative_churn"  # high vol, low delivery
        elif not vol_rising and avg_recent > 60:
            divergence = "quiet_accumulation"  # low vol, high delivery

        return {
            "available": True,
            "days_analyzed": len(data),
            "avg_delivery_pct": round(avg_overall, 1),
            "recent_4w_avg": round(avg_recent, 1),
            "prior_4w_avg": round(avg_prior, 1),
            "trend": trend,
            "acceleration_pp": round(diff, 1),
            "volume_delivery_divergence": divergence,
            "latest": {
                "date": data[-1]["date"],
                "delivery_pct": data[-1]["delivery_pct"],
                "volume": data[-1]["volume"],
            },
        }

    def get_institutional_consensus(self, symbol: str) -> dict:
        """Cross-table institutional signal: delivery + MF + insider combined."""
        signals: dict = {}

        # 1. Delivery signal
        delivery = self.get_delivery_analysis(symbol, days=60)
        if delivery.get("available"):
            avg = delivery.get("avg_delivery_pct", 0)
            trend = delivery.get("trend", "stable")
            if avg > 55 and trend == "rising":
                signals["delivery"] = "strong_accumulation"
            elif avg > 45:
                signals["delivery"] = "moderate_accumulation"
            elif avg < 30 and trend == "falling":
                signals["delivery"] = "distribution"
            else:
                signals["delivery"] = "neutral"
            signals["delivery_detail"] = {
                "avg_pct": delivery.get("avg_delivery_pct"),
                "trend": trend,
                "divergence": delivery.get("volume_delivery_divergence"),
            }

        # 2. MF signal
        mf = self.get_mf_conviction(symbol)
        if mf.get("available"):
            scheme_count = mf.get("schemes_holding", 0)
            scheme_trend = mf.get("scheme_trend", "stable")
            if scheme_count >= 8 and scheme_trend == "adding":
                signals["mf"] = "strong_conviction"
            elif scheme_count >= 5:
                signals["mf"] = "moderate_conviction"
            elif scheme_count <= 2:
                signals["mf"] = "low_conviction"
            else:
                signals["mf"] = "neutral"
            signals["mf_detail"] = {
                "schemes": scheme_count,
                "amcs": mf.get("amcs_holding"),
                "trend": scheme_trend,
                "value_cr": mf.get("total_mf_value_cr"),
            }

        # 3. Insider signal (last 90 days)
        insider = self.get_insider_transactions(symbol, days=90)
        if insider:
            buys = sum(1 for t in insider if t.get("transaction_type", "").lower() in ("buy", "acquisition"))
            sells = sum(1 for t in insider if t.get("transaction_type", "").lower() in ("sell", "disposal"))
            if buys > sells and buys >= 2:
                signals["insider"] = "net_buying"
            elif sells > buys and sells >= 2:
                signals["insider"] = "net_selling"
            else:
                signals["insider"] = "neutral"
            signals["insider_detail"] = {"buys": buys, "sells": sells, "total": len(insider)}

        # Composite
        signal_scores = {
            "strong_accumulation": 2, "strong_conviction": 2, "net_buying": 2,
            "moderate_accumulation": 1, "moderate_conviction": 1,
            "neutral": 0,
            "low_conviction": -1, "distribution": -2, "net_selling": -1,
        }

        score = sum(signal_scores.get(v, 0) for k, v in signals.items() if not k.endswith("_detail"))
        if score >= 4:
            composite = "strong_bullish"
        elif score >= 2:
            composite = "moderately_bullish"
        elif score <= -2:
            composite = "bearish"
        elif score < 0:
            composite = "moderately_bearish"
        else:
            composite = "neutral"

        signals["composite"] = composite
        signals["composite_score"] = score

        return signals

    def get_promoter_pledge(self, symbol: str) -> list[dict]:
        """Quarterly promoter pledge % history with margin-call analysis."""
        rows = self._store.get_promoter_pledge(symbol)
        result = _clean([r.model_dump() for r in rows])

        # Compute margin-call trigger if pledge exists
        if result:
            latest = result[0]  # most recent quarter (DESC order)
            pledge_pct = latest.get("pledge_pct", 0)
            if pledge_pct and pledge_pct > 0:
                # Find when pledge first appeared (to estimate pledge price)
                first_pledged = next(
                    (r for r in reversed(result) if (r.get("pledge_pct") or 0) > 0),
                    None,
                )
                pledge_quarter = first_pledged["quarter_end"] if first_pledged else None

                # Get stock price near pledge creation date
                snap = self._store.get_valuation_history(symbol, days=730)
                pledge_price = None
                if snap and pledge_quarter:
                    for s in snap:
                        if s.date and s.date >= pledge_quarter:
                            pledge_price = s.price
                            break
                    if not pledge_price and snap:
                        pledge_price = snap[-1].price

                # Adjust pledge price for splits/bonuses since pledge date
                if pledge_price and pledge_quarter:
                    actions = self._store.get_split_bonus_actions(symbol)
                    post_pledge_factor = 1.0
                    for a in actions:
                        if a["ex_date"] > pledge_quarter:
                            post_pledge_factor *= (a.get("multiplier") or 1.0)
                    if post_pledge_factor != 1.0:
                        pledge_price = pledge_price / post_pledge_factor

                cmp = snap[-1].price if snap else None

                if pledge_price and cmp:
                    # Loan per share at 50% LTV; margin call when LTV exceeds 65%
                    loan_per_share = pledge_price * 0.50
                    trigger_price = round(loan_per_share / 0.65, 2)
                    buffer_pct = round((cmp - trigger_price) / cmp * 100, 1)
                    latest["margin_call_analysis"] = {
                        "estimated_pledge_price": round(pledge_price, 2),
                        "pledge_appeared_quarter": pledge_quarter,
                        "assumed_initial_ltv": 0.50,
                        "margin_call_ltv": 0.65,
                        "loan_per_share": round(loan_per_share, 2),
                        "trigger_price": trigger_price,
                        "current_price": round(cmp, 2),
                        "buffer_pct": buffer_pct,
                        "systemic_risk": "low" if pledge_pct < 5 else "moderate" if pledge_pct < 15 else "high",
                    }

        return result

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

    def get_commodity_snapshot(self) -> dict:
        """Current commodity prices with 1M/3M/1Y changes."""
        result = {}
        for commodity in ("GOLD", "GOLD_INR", "SILVER", "SILVER_INR"):
            prices = self._store.get_commodity_prices(commodity, days=400)
            if not prices:
                continue

            data = [(p.date, p.price) for p in prices if p.price]
            if not data:
                continue

            data.sort(key=lambda x: x[0])
            latest = data[-1][1]

            def _change(days_ago: int, _data=data, _latest=latest) -> float | None:
                target_idx = max(0, len(_data) - days_ago)
                if target_idx < len(_data) and _data[target_idx][1]:
                    return round((_latest - _data[target_idx][1]) / _data[target_idx][1] * 100, 1)
                return None

            result[commodity.lower()] = {
                "price": latest,
                "date": data[-1][0],
                "change_1m_pct": _change(22),
                "change_3m_pct": _change(66),
                "change_1y_pct": _change(252),
            }

        return result if result else {"available": False, "reason": "No commodity data"}

    # --- Filings ---

    def get_recent_filings(self, symbol: str, limit: int = 10) -> list[dict]:
        """Recent BSE corporate filings."""
        rows = self._store.get_filings(symbol, limit=limit)
        return _clean([r.model_dump() for r in rows])

    def get_material_events(self, symbol: str, days: int = 365) -> dict:
        """Classify corporate filings into material event categories.

        Surfaces high-signal filings: credit ratings, order wins, auditor changes,
        acquisitions, fund raises, management changes. Filters out routine noise.
        """
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self._store.get_filings(symbol, limit=200)

        EVENT_CATEGORIES = {
            "Credit Rating": "credit_rating",
            "Award of Order / Receipt of Order": "order_win",
            "Acquisition": "acquisition",
            "Resignation of Statutory Auditors": "auditor_resignation",
            "Appointment of Statutory Auditor/s": "auditor_change",
            "Change in Management": "management_change",
            "Change in Directorate": "management_change",
            "Change in Management Control": "management_change",
            "Resignation of Director": "management_change",
            "Resignation of Chairman": "management_change",
            "Resignation of Chief Financial Officer (CFO)": "management_change",
            "Resignation of Company Secretary / Compliance Officer": "management_change",
            "Raising of Funds": "fund_raise",
            "Qualified Institutional Placement": "fund_raise",
            "Bonds / Right issue": "fund_raise",
            "Issue of Securities": "fund_raise",
            "Buy back": "buyback",
            "Scheme of Arrangement": "restructuring",
            "Restructuring": "restructuring",
            "Diversification / Disinvestment": "restructuring",
            "Financial Results": "results",
            "Outcome of Board Meeting": "board_outcome",
            "Press Release / Media Release": "press_release",
            "Strikes /Lockouts / Disturbances": "operational_disruption",
        }

        HIGH_SIGNAL = {
            "credit_rating", "order_win", "auditor_resignation", "auditor_change",
            "acquisition", "fund_raise", "buyback", "restructuring",
            "operational_disruption", "management_change",
        }

        events = []
        for r in rows:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            filing_date = d.get("filing_date", "")
            if filing_date < cutoff:
                continue

            subcat = d.get("subcategory", "")
            event_type = EVENT_CATEGORIES.get(subcat)
            if not event_type:
                continue

            events.append({
                "date": filing_date,
                "event_type": event_type,
                "headline": d.get("headline", ""),
                "subcategory": subcat,
                "high_signal": event_type in HIGH_SIGNAL,
            })

        events.sort(key=lambda e: (e["date"], not e["high_signal"]), reverse=True)

        type_counts: dict[str, int] = {}
        for e in events:
            type_counts[e["event_type"]] = type_counts.get(e["event_type"], 0) + 1

        return {
            "events": events,
            "summary": type_counts,
            "total": len(events),
            "high_signal_count": sum(1 for e in events if e["high_signal"]),
        }

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
        """Schedule sub-item breakdowns (e.g., Expenses → Employee Cost, Raw Material).

        Raw access to financial_schedules table. For structured/analyzed views,
        use get_cost_structure, get_balance_sheet_detail, get_cash_flow_quality.
        """
        return self._store.get_schedules(symbol, section)

    # --- Structured Schedule Analysis ---

    @staticmethod
    def _normalize_sub_item(name: str) -> str:
        """Convert Screener sub-item names to snake_case keys.

        'Material Cost %' → 'material_cost_pct'
        'Long term Borrowings' → 'long_term_borrowings'
        'Trade receivables' → 'trade_receivables'
        """
        s = name.strip().lower()
        has_pct = s.endswith("%") or "%" in s
        # Strip trailing % and special chars
        s = re.sub(r"[%]+$", "", s).strip()
        s = re.sub(r"[^a-z0-9\s]", "", s)
        # Collapse whitespace to underscore
        s = re.sub(r"\s+", "_", s).strip("_")
        if has_pct and not s.endswith("_pct"):
            s += "_pct"
        return s

    @staticmethod
    def _group_schedules(
        rows: list[dict], section: str | None = None
    ) -> dict[str, dict[str, list[dict]]]:
        """Group raw schedule rows into {parent_item: {sub_item_normalized: [{period, value}]}}.

        Optionally filter by section.
        """
        result: dict[str, dict[str, list[dict]]] = {}
        for r in rows:
            if section and r.get("section") != section:
                continue
            parent = r.get("parent_item", "")
            sub = r.get("sub_item", "")
            if not sub:
                continue
            key = ResearchDataAPI._normalize_sub_item(sub)
            if not key:
                continue
            result.setdefault(parent, {}).setdefault(key, []).append(
                {"period": r.get("period", ""), "value": r.get("value")}
            )
        return result

    def get_cost_structure(self, symbol: str) -> dict:
        """Quarterly + annual expense breakdowns with trend direction."""
        quarterly_rows = self._store.get_schedules(symbol, "quarters")
        annual_rows = self._store.get_schedules(symbol, "profit-loss")

        q_grouped = self._group_schedules(quarterly_rows)
        a_grouped = self._group_schedules(annual_rows)

        quarterly = q_grouped.get("Expenses", {})
        annual = a_grouped.get("Expenses", {})

        # Compute trends: last 4 quarters avg vs prior 4 quarters avg
        trends: dict[str, str] = {}
        for key, points in quarterly.items():
            vals = [p["value"] for p in points if p.get("value") is not None]
            if len(vals) >= 8:
                recent = statistics.mean(vals[-4:])
                prior = statistics.mean(vals[-8:-4])
                diff = recent - prior
                if diff > 2:
                    trends[f"{key}_direction"] = "rising"
                elif diff < -2:
                    trends[f"{key}_direction"] = "falling"
                else:
                    trends[f"{key}_direction"] = "stable"
            elif len(vals) >= 4:
                trends[f"{key}_direction"] = "insufficient_history"

        return _clean({
            "quarterly": quarterly,
            "annual": annual,
            "trends": trends,
        })

    def get_balance_sheet_detail(self, symbol: str) -> dict:
        """Decomposed balance sheet from schedule data."""
        rows = self._store.get_schedules(symbol, "balance-sheet")
        grouped = self._group_schedules(rows)

        return _clean({
            "borrowings": grouped.get("Borrowings", {}),
            "assets": {
                **grouped.get("Fixed Assets", {}),
                **grouped.get("Other Assets", {}),
            },
            "liabilities": grouped.get("Other Liabilities", {}),
        })

    def get_cash_flow_quality(self, symbol: str) -> dict:
        """Cash flow decomposition showing quality of operating CF."""
        rows = self._store.get_schedules(symbol, "cash-flow")
        grouped = self._group_schedules(rows)

        return _clean({
            "operating": grouped.get("Cash from Operating Activity", {}),
            "investing": grouped.get("Cash from Investing Activity", {}),
            "financing": grouped.get("Cash from Financing Activity", {}),
        })

    def get_working_capital_cycle(self, symbol: str) -> dict:
        """Working capital components + as % of revenue."""
        bs_rows = self._store.get_schedules(symbol, "balance-sheet")
        grouped = self._group_schedules(bs_rows)

        other_assets = grouped.get("Other Assets", {})
        other_liabs = grouped.get("Other Liabilities", {})

        components = {
            "trade_receivables": other_assets.get("trade_receivables", []),
            "inventories": other_assets.get("inventories", []),
            "trade_payables": other_liabs.get("trade_payables", []),
        }

        # Get annual revenue for % computation
        # AnnualFinancials uses fiscal_year_end ("2025-03-31") but schedule
        # periods are "Mar 2025" — convert to match.
        annual = self._store.get_annual_financials(symbol, limit=20)
        rev_by_period: dict[str, float] = {}
        for row in annual:
            d = row.model_dump() if hasattr(row, "model_dump") else row
            fye = d.get("fiscal_year_end", "")
            rev = d.get("revenue")
            if fye and rev:
                try:
                    dt = datetime.strptime(fye, "%Y-%m-%d")
                    period_key = dt.strftime("%b %Y")  # "Mar 2025"
                    rev_by_period[period_key] = float(rev)
                except (ValueError, TypeError):
                    pass

        as_pct: dict[str, list[dict]] = {}
        for comp_name, points in components.items():
            pct_key = comp_name.replace("trade_", "") + "_pct"
            if comp_name == "inventories":
                pct_key = "inventory_pct"
            pct_list = []
            for p in points:
                period = p.get("period", "")
                val = p.get("value")
                rev = rev_by_period.get(period)
                if val is not None and rev and rev > 0:
                    pct_list.append({
                        "period": period,
                        "value": round(val / rev * 100, 1),
                    })
            if pct_list:
                as_pct[pct_key] = pct_list

        return _clean({
            "components": components,
            "as_pct_of_revenue": as_pct,
        })

    # --- FMP Data ---

    def get_dcf_valuation(self, symbol: str) -> dict:
        """Latest DCF intrinsic value + margin of safety."""
        dcf = self._store.get_fmp_dcf_latest(symbol)
        if not dcf:
            return {}
        result = _clean(dcf.model_dump())
        if dcf.dcf and dcf.stock_price and dcf.dcf > 0:
            result["margin_of_safety_pct"] = round(
                (dcf.dcf - dcf.stock_price) / dcf.dcf * 100, 2
            )
        return result

    def get_dcf_history(self, symbol: str, days: int = 365) -> list[dict]:
        """Historical DCF trajectory."""
        rows = self._store.get_fmp_dcf_history(symbol, limit=10)
        return _clean([r.model_dump() for r in rows])

    def get_technical_indicators(self, symbol: str) -> list[dict]:
        """Latest RSI, MACD, SMA-50, SMA-200, ADX. FMP primary, yfinance fallback."""
        rows = self._store.get_fmp_technical_indicators(symbol)
        if rows:
            return _clean([r.model_dump() for r in rows])

        # Fallback: compute basic technicals from daily_stock_data (bhavcopy)
        conn = self._store._conn
        prices = conn.execute(
            "SELECT date, close FROM daily_stock_data WHERE symbol = ? ORDER BY date DESC LIMIT 200",
            (symbol,),
        ).fetchall()
        if len(prices) < 50:
            return []

        closes = [float(p["close"]) for p in prices]
        latest = closes[0]

        result: dict = {"date": prices[0]["date"], "close": latest}

        # SMA-50, SMA-200
        if len(closes) >= 50:
            result["sma_50"] = round(sum(closes[:50]) / 50, 2)
        if len(closes) >= 200:
            result["sma_200"] = round(sum(closes[:200]) / 200, 2)

        # RSI-14 (Wilder's smoothing)
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(14):
                diff = closes[i] - closes[i + 1]  # newest first, so diff = today - yesterday
                gains.append(max(diff, 0))
                losses.append(max(-diff, 0))
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                result["rsi_14"] = round(100 - (100 / (1 + rs)), 2)
            else:
                result["rsi_14"] = 100.0

        # Price vs SMA signals
        if "sma_50" in result:
            result["price_vs_sma50"] = "above" if latest > result["sma_50"] else "below"
        if "sma_200" in result:
            result["price_vs_sma200"] = "above" if latest > result["sma_200"] else "below"

        # Death cross / Golden cross detection
        if "sma_50" in result and "sma_200" in result:
            if result["sma_50"] < result["sma_200"]:
                result["sma_cross"] = "death_cross"
                result["sma_cross_note"] = "SMA50 below SMA200 — bearish trend signal (death cross)"
            else:
                result["sma_cross"] = "golden_cross"
                result["sma_cross_note"] = "SMA50 above SMA200 — bullish trend signal (golden cross)"

        return [result] if result else []

    def get_dupont_decomposition(self, symbol: str) -> dict:
        """ROE = margin × turnover × leverage (10yr). Uses Screener annual_financials, falls back to FMP key_metrics."""
        # Try Screener data first
        annuals = self._store.get_annual_financials(symbol, limit=10)
        if annuals:
            decomp = []
            for i, a in enumerate(annuals):
                total_equity = (a.equity_capital or 0) + (a.reserves or 0)
                # Use average of T and T-1 for balance sheet items (more accurate for growing companies)
                if i + 1 < len(annuals):
                    prev = annuals[i + 1]
                    prev_equity = (prev.equity_capital or 0) + (prev.reserves or 0)
                    prev_ta = prev.total_assets or 0
                    avg_ta = (a.total_assets + prev_ta) / 2 if prev_ta > 0 else a.total_assets
                    avg_equity = (total_equity + prev_equity) / 2 if prev_equity > 0 else total_equity
                else:
                    avg_ta = a.total_assets
                    avg_equity = total_equity
                if a.revenue and a.revenue > 0 and a.net_income is not None and avg_ta and avg_ta > 0 and avg_equity and avg_equity > 0:
                    npm = a.net_income / a.revenue
                    at = a.revenue / avg_ta
                    em = avg_ta / avg_equity
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
                    # net_profit_margin_dupont stored as percentage (P-3B.2), convert to decimal for multiplication
                    roe = (m.net_profit_margin_dupont / 100) * m.asset_turnover * m.equity_multiplier
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
        bear = bull = None

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

            # Flag narrow PE band (data window < 3 years)
            pe_data_points = pe_band.data_points if hasattr(pe_band, "data_points") else None
            pe_range = round(pe_band.max_val - pe_band.min_val, 1) if pe_band.max_val and pe_band.min_val else None
            narrow_band_warning = None
            if pe_range is not None and pe_range < 10:
                narrow_band_warning = (
                    f"PE band is narrow ({pe_band.min_val:.1f}x–{pe_band.max_val:.1f}x, range {pe_range}x). "
                    "This may reflect a short data window or recent regime change. "
                    "Use 5Y+ historical PE from chart data for context."
                )

            result["pe_band"] = {
                "bear": round(bear, 2), "base": round(base, 2), "bull": round(bull, 2),
                "forward_eps": forward_eps, "pe_percentile": pe_band.percentile,
            }
            if narrow_band_warning:
                result["pe_band"]["narrow_band_warning"] = narrow_band_warning
            pe_fair = base

        # 2. FMP DCF (exclude for BFSI — unreliable for Indian financials)
        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)
        dcf = self._store.get_fmp_dcf_latest(symbol)
        dcf_value = dcf.dcf if dcf and not is_bfsi else None
        if dcf_value:
            result["dcf"] = dcf_value
        elif dcf and is_bfsi:
            result["dcf_excluded"] = "FMP DCF unreliable for BFSI; use P/B band instead"

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

    def get_company_snapshot(self, symbol: str) -> dict:
        """Unified company fundamentals from snapshot cache."""
        snap = self._store.get_company_snapshot(symbol)
        return _clean(snap) if snap else {}

    def get_yahoo_peer_comparison(self, symbol: str) -> dict:
        """Yahoo-recommended peers with company snapshots.

        Returns subject snapshot + list of peer snapshots with similarity scores.
        Uses company_snapshot table for instant lookups (no HTTP calls).
        """
        subject = self._store.get_company_snapshot(symbol) or {"symbol": symbol}
        peer_links = self._store.get_peer_links(symbol)
        peer_symbols = [p["peer_symbol"] for p in peer_links]
        peer_snapshots = self._store.get_company_snapshots(peer_symbols) if peer_symbols else []

        score_map = {p["peer_symbol"]: p["score"] for p in peer_links}
        for snap in peer_snapshots:
            snap["yahoo_score"] = score_map.get(snap["symbol"])

        return {
            "subject": _clean(subject),
            "peers": _clean(peer_snapshots),
            "peer_count": len(peer_snapshots),
            "source": "yahoo_recommendations",
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

    def get_dividend_policy(self, symbol: str) -> dict:
        """Dividend policy analysis: payout trend, consistency, yield trajectory."""
        actions = self._store.get_corporate_actions(symbol)
        if not actions:
            return {"available": False, "reason": "No corporate actions data"}

        # Filter dividends — store returns list[dict]
        dividends = []
        for d in actions:
            if d.get("action_type") == "dividend" and d.get("dividend_amount"):
                dividends.append(d)

        if not dividends:
            return {"available": False, "reason": "No dividend history"}

        dividends.sort(key=lambda x: x.get("ex_date", ""))

        # Annual aggregation
        annual: dict[str, float] = {}
        for d in dividends:
            year = d["ex_date"][:4] if d.get("ex_date") else None
            if year:
                annual[year] = annual.get(year, 0) + (d.get("dividend_amount") or 0)

        # Get EPS for payout ratio
        financials = self._store.get_annual_financials(symbol, limit=10)
        eps_by_year: dict[str, float] = {}
        for f in financials:
            fd = f.model_dump() if hasattr(f, "model_dump") else f
            fye = fd.get("fiscal_year_end", "")
            eps = fd.get("eps")
            if fye and eps:
                eps_by_year[fye[:4]] = eps

        # Build annual policy
        years = sorted(annual.keys())
        policy = []
        for yr in years:
            div = annual[yr]
            eps = eps_by_year.get(yr)
            payout = round(div / eps * 100, 1) if eps and eps > 0 else None
            policy.append({
                "year": yr,
                "total_dividend": round(div, 2),
                "eps": eps,
                "payout_ratio_pct": payout,
            })

        # Consistency: how many of last 5 years had dividends?
        recent_5 = [p for p in policy if int(p["year"]) >= int(years[-1]) - 4] if years else []
        consistency = len(recent_5)

        # Trend: growing, stable, or declining?
        payouts = [p["payout_ratio_pct"] for p in policy[-5:] if p["payout_ratio_pct"] is not None]
        if len(payouts) >= 3:
            first_half = statistics.mean(payouts[:len(payouts) // 2])
            second_half = statistics.mean(payouts[len(payouts) // 2:])
            if second_half > first_half + 5:
                payout_trend = "increasing"
            elif second_half < first_half - 5:
                payout_trend = "decreasing"
            else:
                payout_trend = "stable"
        else:
            payout_trend = "insufficient_data"

        return {
            "available": True,
            "years_of_history": len(policy),
            "consistency_last_5y": f"{consistency}/5",
            "payout_trend": payout_trend,
            "annual_policy": policy,
            "latest_dividend": dividends[-1].get("dividend_amount"),
            "latest_ex_date": dividends[-1].get("ex_date"),
        }

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

        # Dynamic PE from historical band
        from flowtracker.research.wacc import compute_dynamic_pe
        pe_band_raw = self.get_valuation_band(symbol, "pe_trailing", days=2500)
        pe_band = pe_band_raw if pe_band_raw.get("median_val") else None
        pe_multiples = compute_dynamic_pe(pe_band)

        # Use current post-bonus shares from valuation snapshot (not stale Screener num_shares)
        valuation = self.get_valuation_snapshot(symbol)
        current_shares = valuation.get("shares_outstanding", 0)

        return build_projections(
            annual,
            adjustment_factor=factor,
            pe_multiples=pe_multiples,
            shares_override=current_shares or None,
        )

    def get_wacc_params(self, symbol: str) -> dict:
        """Dynamic WACC: beta, cost of equity, cost of debt, terminal growth, PE multiples."""
        from flowtracker.research.wacc import build_wacc_params

        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)
        flags: list[str] = []

        # --- Stock prices (bhavcopy preferred, Screener chart fallback) ---
        stock_rows = self._store.get_stock_delivery(symbol, days=800)
        stock_prices = [{"date": r.date, "close": r.close} for r in stock_rows if r.close]
        # Beta needs 53+ weeks; fall back to Screener chart prices if bhavcopy is thin
        if len(stock_prices) < 260:  # ~1yr of trading days
            chart_data = self._store.get_chart_data(symbol, "price")
            for metric_data in chart_data:
                if metric_data.get("metric") == "Price":
                    chart_prices = [
                        {"date": pt["date"], "close": pt["value"]}
                        for pt in metric_data.get("values", [])
                        if pt.get("value")
                    ]
                    if len(chart_prices) > len(stock_prices):
                        stock_prices = chart_prices
                    break
        if not stock_prices:
            flags.append("no_stock_prices")

        # --- Index prices (Nifty 500) ---
        index_prices = self._store.get_index_prices("^CRSLDX", days=800)
        if not index_prices:
            flags.append("no_index_prices")

        # --- Risk-free rate (G-sec 10Y) ---
        rf = None
        macro = self._store.get_macro_latest()
        if macro and macro.gsec_10y:
            rf = macro.gsec_10y / 100  # stored as %, convert to decimal
        if rf is None:
            # Fallback: scan recent macro rows for last non-null G-sec
            trend = self._store.get_macro_trend(days=30)
            for snap in trend:
                if snap.gsec_10y:
                    rf = snap.gsec_10y / 100
                    break
        if rf is None:
            rf = 0.07  # absolute fallback
            flags.append("rf_default")

        # --- Financials for ICR ---
        annual = self.get_annual_financials(symbol, years=2)
        interest = 0.0
        borrowings = 0.0
        pbt = 0.0
        eff_tax_rate = None
        if annual:
            latest = annual[0]
            interest = latest.get("interest", 0) or 0
            borrowings = latest.get("borrowings", 0) or 0
            pbt = latest.get("profit_before_tax", 0) or 0
            tax = latest.get("tax", 0) or 0
            if pbt > 0:
                eff_tax_rate = tax / pbt

        # --- Market cap ---
        valuation = self.get_valuation_snapshot(symbol)
        mcap = valuation.get("market_cap") or 0

        # --- PE band ---
        pe_band_raw = self.get_valuation_band(symbol, "pe_trailing", days=2500)
        pe_band = pe_band_raw if pe_band_raw.get("median_val") else None

        # --- Industry ---
        info = self.get_company_info(symbol)
        industry = info.get("industry")

        result = build_wacc_params(
            symbol=symbol,
            stock_prices=stock_prices,
            index_prices=index_prices,
            rf=rf,
            interest=interest,
            borrowings=borrowings,
            pbt=pbt,
            mcap_cr=mcap,
            pe_band=pe_band,
            industry=industry,
            is_bfsi=is_bfsi,
            effective_tax_rate=eff_tax_rate,
        )

        # Merge data-layer flags
        if flags:
            result.setdefault("reliability_flags", []).extend(flags)

        return result

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

    # --- Pre-computed Metrics (avoid agent math errors) ---

    def get_rate_sensitivity(self, symbol: str) -> dict:
        """Impact of a 1% interest rate rise on profitability.

        Computes: extra interest cost, EPS impact, interest coverage.
        Pre-computed so agents don't do this math themselves.
        """
        annual = self.get_annual_financials(symbol, years=1)
        if not annual:
            return {"error": "No annual financial data"}

        latest = annual[0]
        borrowings = latest.get("borrowings", 0) or 0
        interest = latest.get("interest", 0) or 0
        ni = latest.get("net_income", 0) or 0
        pbt = latest.get("profit_before_tax", 0) or 0
        tax = latest.get("tax", 0) or 0
        revenue = latest.get("revenue", 0) or 0
        eps = latest.get("eps", 0) or 0
        op = latest.get("operating_profit")

        if borrowings <= 0:
            return {"symbol": symbol, "net_debt": 0, "signal": "debt_free", "rate_sensitivity": "none"}

        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)

        tax_rate = tax / pbt if pbt > 0 else 0.25
        extra_interest = borrowings * 0.01  # 1% rate rise
        extra_interest_post_tax = extra_interest * (1 - tax_rate)

        # Interest coverage = EBIT / interest
        ebit = (op if op is not None else (pbt + interest)) or 0
        coverage = round(ebit / interest, 2) if interest > 0 else None

        # EPS impact
        eps_impact_pct = round(extra_interest_post_tax / ni * 100, 1) if ni > 0 else None
        margin_impact_bps = round(extra_interest / revenue * 10000, 0) if revenue > 0 else None

        return {
            "symbol": symbol,
            "borrowings": round(borrowings, 2),
            "current_interest": round(interest, 2),
            "interest_coverage": coverage,
            "rate_rise_1pct": {
                "extra_interest_cr": round(extra_interest, 2),
                "extra_interest_post_tax_cr": round(extra_interest_post_tax, 2),
                "net_income_impact_pct": eps_impact_pct,
                "margin_impact_bps": margin_impact_bps,
            },
            "signal": "high" if (eps_impact_pct and eps_impact_pct > 10) else "moderate" if (eps_impact_pct and eps_impact_pct > 3) else "low",
            **({"caveat": "BFSI: borrowings are deposits (raw material), not corporate debt. Rate sensitivity reflects NIM compression risk, not leverage risk."} if is_bfsi else {}),
        }

    def get_growth_cagr_table(self, symbol: str) -> dict:
        """Pre-computed CAGR table: 1Y/3Y/5Y/10Y for Revenue, EBITDA, NI, EPS, FCF.

        Pre-computed so agents don't calculate CAGRs themselves.
        """
        annual = self.get_annual_financials(symbol, years=11)
        if len(annual) < 2:
            return {"error": "Need at least 2 years of financials"}

        def _cagr(latest_val: float, oldest_val: float, years: int) -> float | None:
            if oldest_val and oldest_val > 0 and latest_val and latest_val > 0 and years > 0:
                return round(((latest_val / oldest_val) ** (1 / years) - 1) * 100, 1)
            return None

        def _yoy(latest_val: float, prev_val: float) -> float | None:
            if prev_val and prev_val > 0 and latest_val is not None:
                return round(((latest_val / prev_val) - 1) * 100, 1)
            return None

        # Extract series
        def _get(d: dict, key: str) -> float:
            return d.get(key, 0) or 0

        def _ebitda(d: dict) -> float:
            op = d.get("operating_profit")
            dep = _get(d, "depreciation")
            if op is not None:
                return op + dep
            return _get(d, "net_income") + _get(d, "tax") + _get(d, "interest") + dep

        def _fcf(d: dict, prev: dict | None) -> float | None:
            cfo = _get(d, "cfo")
            if not cfo or prev is None:
                return None
            nb_t, nb_t1 = _get(d, "net_block"), _get(prev, "net_block")
            cwip_t, cwip_t1 = _get(d, "cwip"), _get(prev, "cwip")
            dep = _get(d, "depreciation")
            capex = (nb_t - nb_t1) + (cwip_t - cwip_t1) + dep
            return cfo - capex

        n = len(annual)
        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)

        metric_defs = [
            ("revenue", lambda d, _: _get(d, "revenue")),
            ("ebitda", lambda d, _: _ebitda(d)),
            ("net_income", lambda d, _: _get(d, "net_income")),
            ("eps", lambda d, _: _get(d, "eps")),
        ]
        # FCF is meaningless for BFSI — suppress entirely, not even with caveats
        if not is_bfsi:
            metric_defs.append(("fcf", lambda d, prev: _fcf(d, prev)))

        metrics = {}
        for label, extract in metric_defs:
            values = []
            for i, d in enumerate(annual):
                prev = annual[i + 1] if i + 1 < n else None
                values.append(extract(d, prev))

            row = {}
            if len(values) >= 2 and values[0] and values[1]:
                row["1y"] = _yoy(values[0], values[1])
            if len(values) >= 4 and values[0] and values[3]:
                row["3y"] = _cagr(values[0], values[3], 3)
            if len(values) >= 6 and values[0] and values[5]:
                row["5y"] = _cagr(values[0], values[5], 5)
            if len(values) >= 11 and values[0] and values[10]:
                row["10y"] = _cagr(values[0], values[10], 10)

            row["latest"] = round(values[0], 2) if values[0] else None
            metrics[label] = row

        # Classify trajectory from revenue CAGRs
        rev = metrics.get("revenue", {})
        r1, r3, r5 = rev.get("1y"), rev.get("3y"), rev.get("5y")
        if r1 is not None and r3 is not None:
            if r1 > r3 + 3:
                trajectory = "accelerating"
            elif r1 < r3 - 3:
                trajectory = "decelerating"
            else:
                trajectory = "stable"
        else:
            trajectory = "unknown"

        return {
            "symbol": symbol,
            "years_available": n,
            "cagrs": metrics,
            "growth_trajectory": trajectory,
        }

    # --- Auto-Detected Risk Flags ---

    def get_risk_flags(self, symbol: str) -> dict:
        """Auto-detect generic risk patterns from financial data.

        Flags: Q4 revenue concentration, raw material cost spikes,
        large YoY swings in cost structure.
        """
        flags = []

        # Q4 revenue concentration: if Q4 > 35% of annual revenue
        quarters = self.get_quarterly_results(symbol, quarters=8)
        annual = self.get_annual_financials(symbol, years=2)
        if quarters and annual:
            latest_fy = annual[0].get("fiscal_year_end", "")[:4]  # "2025"
            fy_quarters = [q for q in quarters if q.get("quarter", "").startswith(f"Q") and
                           latest_fy in (q.get("quarter", "") or "")]
            # Simpler: group by fiscal year from quarter dates
            q4_revs = []
            annual_revs = []
            for q in quarters[:4]:  # last 4 quarters
                q4_revs.append(q.get("revenue", 0) or 0)
            if q4_revs and annual and annual[0].get("revenue"):
                annual_rev = annual[0]["revenue"]
                # Q4 is the first quarter in our list (most recent = Q4 if near March)
                # Better approach: find the Jan-Mar quarter
                for q in quarters[:8]:
                    period = q.get("quarter", "") or q.get("period", "")
                    if "Mar" in period or "Q4" in period:
                        q4_rev = q.get("revenue", 0) or 0
                        if annual_rev and annual_rev > 0:
                            q4_pct = round(q4_rev / annual_rev * 100, 1)
                            if q4_pct > 35:
                                flags.append({
                                    "flag": "q4_revenue_concentration",
                                    "severity": "medium",
                                    "detail": f"Q4 contributed {q4_pct}% of annual revenue — lumpy recognition risk",
                                    "value": q4_pct,
                                })
                        break

        # Raw material cost spike: >15pp YoY change in RM/revenue
        if len(annual) >= 2:
            for i in range(len(annual) - 1):
                curr = annual[i]
                prev = annual[i + 1]
                c_rev = curr.get("revenue", 0) or 0
                p_rev = prev.get("revenue", 0) or 0
                c_rm = curr.get("raw_material_cost", 0) or 0
                p_rm = prev.get("raw_material_cost", 0) or 0

                if c_rev > 0 and p_rev > 0 and (c_rm > 0 or p_rm > 0):
                    c_pct = c_rm / c_rev * 100
                    p_pct = p_rm / p_rev * 100
                    change = round(c_pct - p_pct, 1)
                    if abs(change) > 15:
                        flags.append({
                            "flag": "raw_material_cost_spike",
                            "severity": "high" if abs(change) > 20 else "medium",
                            "detail": f"Raw material cost shifted {change:+.1f}pp YoY ({p_pct:.1f}% → {c_pct:.1f}% of revenue) in {curr.get('fiscal_year_end', '')}",
                            "value": change,
                        })
                break  # only check most recent year

        return {"flags": flags} if flags else {"flags": [], "note": "No auto-detected risk flags"}

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

            other_inc = a.get("other_income") or 0
            ebitda = (ni or 0) + tax + interest + depreciation - other_inc
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
        # Flag negative PAT years where CFO/PAT ratio is misleading
        neg_pat_years = [y for y in years if "cfo_pat" in y and y["cfo_pat"] < 0]
        if neg_pat_years:
            signal += "_negative_pat_years"

        return _clean({
            "years": years,
            "avg_3y_cfo_pat": avg_3y_cfo_pat,
            "avg_5y_cfo_pat": avg_5y_cfo_pat,
            "avg_3y_accruals": avg_3y_accruals,
            "signal": signal,
        })

    def get_forensic_checks(self, symbol: str) -> dict:
        """Forensic accounting checks: CFO/EBITDA persistence, depreciation volatility, cash yield, CWIP parking."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Forensic accounting checks not applicable to BFSI/Insurance."}

        annuals = self.get_annual_financials(symbol, years=10)
        if not annuals:
            return {"error": f"No annual financial data for {symbol}"}

        years = []
        for a in annuals:
            ni = a.get("net_income") or 0
            tax = a.get("tax") or 0
            interest = a.get("interest") or 0
            depreciation = a.get("depreciation") or 0
            other_inc = a.get("other_income") or 0
            cfo = a.get("cfo")
            net_block = a.get("net_block") or 0
            cwip_val = a.get("cwip") or 0
            cash_bank = a.get("cash_and_bank") or 0
            investments = a.get("investments") or 0

            ebitda = ni + tax + interest + depreciation - other_inc
            total_fixed = net_block + cwip_val  # total net fixed assets (not gross block)
            liquid_assets = cash_bank + investments

            entry: dict = {"fiscal_year_end": a.get("fiscal_year_end")}

            # CFO/EBITDA
            if ebitda > 0 and cfo is not None:
                entry["cfo_ebitda"] = round(cfo / ebitda, 3)

            # Depreciation rate — denominator excludes CWIP (not yet depreciable)
            if net_block > 0:
                entry["depreciation_rate"] = round(depreciation / net_block, 4)

            # Cash yield — uses other_income as proxy for interest income
            # (other_income may include sub dividends/forex; interpret with caution)
            if liquid_assets > 0:
                entry["cash_yield_pct"] = round(other_inc / liquid_assets * 100, 1)

            # CWIP ratio — CWIP as % of total fixed assets
            if total_fixed > 0:
                entry["cwip_ratio"] = round(cwip_val / total_fixed, 3)

            years.append(entry)

        # --- CFO/EBITDA signal (aggregate, not averaged — avoids outlier skew) ---
        recent_5 = annuals[:5]
        sum_cfo_5y = sum((a.get("cfo") or 0) for a in recent_5 if a.get("cfo") is not None)
        sum_ebitda_5y = sum(
            (a.get("net_income") or 0) + (a.get("tax") or 0) + (a.get("interest") or 0)
            + (a.get("depreciation") or 0) - (a.get("other_income") or 0)
            for a in recent_5
        )
        cfo_ebitda_5y_avg = round(sum_cfo_5y / sum_ebitda_5y, 3) if sum_ebitda_5y > 0 else None

        cfo_ebitda_signal = "moderate"
        if cfo_ebitda_5y_avg is not None:
            if cfo_ebitda_5y_avg > 0.8:
                cfo_ebitda_signal = "clean"
            elif cfo_ebitda_5y_avg < 0.5:
                cfo_ebitda_signal = "warning"

        # --- Depreciation volatility ---
        dep_rates = [y["depreciation_rate"] for y in years if "depreciation_rate" in y]
        dep_vol = statistics.stdev(dep_rates) if len(dep_rates) >= 2 else 0
        dep_vol = round(dep_vol, 4)
        if dep_vol < 0.02:
            dep_signal = "stable"
        elif dep_vol <= 0.05:
            dep_signal = "moderate"
        else:
            dep_signal = "volatile"

        # --- Cash yield signal ---
        cash_yield_latest = years[0].get("cash_yield_pct") if years else None
        cash_yield_signal = "normal"
        if cash_yield_latest is not None:
            latest_liquid = (annuals[0].get("cash_and_bank") or 0) + (annuals[0].get("investments") or 0)
            if cash_yield_latest < 3 and latest_liquid > 100:
                cash_yield_signal = "suspicious"
            elif cash_yield_latest < 5:
                cash_yield_signal = "low"

        # --- CWIP signal ---
        cwip_vals = [y["cwip_ratio"] for y in years[:3] if "cwip_ratio" in y]
        cwip_3y_avg = round(sum(cwip_vals) / len(cwip_vals), 3) if cwip_vals else None

        cwip_signal = "normal"
        if cwip_3y_avg is not None:
            if cwip_3y_avg > 0.30:
                cwip_signal = "parking_risk"
            elif cwip_3y_avg > 0.15:
                cwip_signal = "elevated"

        return _clean({
            "years": years,
            "cfo_ebitda_5y_avg": cfo_ebitda_5y_avg,
            "cfo_ebitda_signal": cfo_ebitda_signal,
            "depreciation_volatility": dep_vol,
            "depreciation_signal": dep_signal,
            "cash_yield_latest_pct": cash_yield_latest,
            "cash_yield_signal": cash_yield_signal,
            "cwip_3y_avg": cwip_3y_avg,
            "cwip_signal": cwip_signal,
        })

    def get_improvement_metrics(self, symbol: str) -> dict:
        """Improvement trajectory and greatness score (Ambit Ten Baggers framework)."""
        annuals = self.get_annual_financials(symbol, years=10)
        if not annuals:
            return {"error": f"No annual financial data for {symbol}"}

        ratios = self.get_screener_ratios(symbol, years=10)
        # Build ROCE lookup by fiscal_year_end
        roce_map: dict[str, float] = {}
        for r in ratios:
            fy = r.get("fiscal_year_end", "")
            if r.get("roce_pct") is not None:
                roce_map[fy] = r["roce_pct"]

        # Step 1 — Per-year ratios
        per_year: list[dict] = []
        for a in annuals:
            fy = a.get("fiscal_year_end", "")
            ni = a.get("net_income") or 0
            equity = (a.get("equity_capital") or 0) + (a.get("reserves") or 0)
            revenue = a.get("revenue") or 0
            total_assets = a.get("total_assets") or 0
            cash_bank = a.get("cash_and_bank") or 0
            investments = a.get("investments") or 0
            borrowings = a.get("borrowings") or 0
            net_block = a.get("net_block") or 0
            cwip_val = a.get("cwip") or 0
            op_profit = a.get("operating_profit") or 0
            cfo = a.get("cfo") or 0

            entry: dict = {"fiscal_year_end": fy}
            if equity > 0:
                entry["roe"] = round(ni / equity * 100, 1)
            if fy in roce_map:
                entry["roce"] = roce_map[fy]
            if total_assets > 0:
                entry["asset_turnover"] = round(revenue / total_assets, 3)
                entry["cash_ratio"] = round((cash_bank + investments) / total_assets, 3)
            if equity > 0:
                entry["debt_equity"] = round(borrowings / equity, 3)
            entry["total_fixed_assets"] = round(net_block + cwip_val, 2)
            if revenue > 0:
                entry["pbit_margin"] = round(op_profit / revenue * 100, 1)
            entry["cfo"] = round(cfo, 2)
            entry["net_income"] = round(ni, 2)
            entry["revenue"] = round(revenue, 2)

            per_year.append(entry)

        data_years = len(per_year)

        # Step 2 — Improvement trajectories (need 6+ years)
        trajectories: dict = {}
        if data_years >= 6:
            metric_keys = ["roce", "roe", "asset_turnover", "cash_ratio", "pbit_margin", "debt_equity"]
            for mk in metric_keys:
                vals = [y.get(mk) for y in per_year[:6] if mk in y]
                if len(vals) >= 6:
                    latest_3y = vals[:3]
                    prior_3y = vals[3:6]
                    latest_avg = round(sum(latest_3y) / 3, 3)
                    prior_avg = round(sum(prior_3y) / 3, 3)
                    # For D/E, declining is improvement
                    if mk == "debt_equity":
                        improvement = round(prior_avg - latest_avg, 3)
                    else:
                        improvement = round(latest_avg - prior_avg, 3)
                    sd = statistics.stdev(vals) if len(vals) >= 2 else 0
                    consistency = round(improvement / sd, 3) if sd > 0 else 0
                    trajectories[mk] = {
                        "latest_3y_avg": latest_avg,
                        "prior_3y_avg": prior_avg,
                        "improvement": improvement,
                        "consistency": consistency,
                    }

        # Step 3 — Capex productivity
        capex_prod: dict = {}
        if data_years >= 6:
            gb_latest = per_year[0].get("total_fixed_assets") or 0
            gb_5y = per_year[5].get("total_fixed_assets") or 0
            rev_latest = per_year[0].get("revenue") or 0
            rev_5y = per_year[5].get("revenue") or 0

            if gb_5y > 0 and gb_latest > 0:
                gb_cagr = (gb_latest / gb_5y) ** (1 / 5) - 1
                capex_prod["gross_block_cagr_pct"] = round(gb_cagr * 100, 1)
            else:
                gb_cagr = 0
            if rev_5y > 0 and rev_latest > 0:
                s_cagr = (rev_latest / rev_5y) ** (1 / 5) - 1
                capex_prod["sales_cagr_pct"] = round(s_cagr * 100, 1)
            else:
                s_cagr = 0

            if gb_cagr > 0:
                ratio = round(s_cagr / gb_cagr, 3)
                capex_prod["ratio"] = ratio
                if ratio > 0.8:
                    capex_prod["signal"] = "productive"
                elif ratio >= 0.5:
                    capex_prod["signal"] = "moderate"
                else:
                    capex_prod["signal"] = "value_destruction"

        # Step 4 — Greatness classification
        greatness: dict = {}
        if data_years >= 6 and trajectories:
            dims: dict[str, int] = {}

            # 1. Investments — fixed asset CAGR > 0
            if capex_prod.get("gross_block_cagr_pct") is not None and capex_prod["gross_block_cagr_pct"] > 0:
                dims["investments"] = 1
            else:
                dims["investments"] = 0

            # 2. Conversion to Sales — asset_turnover improvement > 0 AND sales_cagr > 0
            at_traj = trajectories.get("asset_turnover", {})
            dims["conversion_to_sales"] = 1 if at_traj.get("improvement", 0) > 0 and capex_prod.get("sales_cagr_pct", 0) > 0 else 0

            # 3. Pricing Discipline — pbit_margin improvement > 0 AND consistency > 0
            pm_traj = trajectories.get("pbit_margin", {})
            dims["pricing_discipline"] = 1 if pm_traj.get("improvement", 0) > 0 and pm_traj.get("consistency", 0) > 0 else 0

            # 4. Balance Sheet Discipline — debt_equity improvement > 0 AND cash_ratio improvement > 0
            de_traj = trajectories.get("debt_equity", {})
            cr_traj = trajectories.get("cash_ratio", {})
            dims["balance_sheet_discipline"] = 1 if de_traj.get("improvement", 0) > 0 and cr_traj.get("improvement", 0) > 0 else 0

            # 5. Cash Generation — CFO improved AND net_income improved
            if data_years >= 6:
                cfo_latest_3y = [y.get("cfo", 0) for y in per_year[:3]]
                cfo_prior_3y = [y.get("cfo", 0) for y in per_year[3:6]]
                ni_latest_3y = [y.get("net_income", 0) for y in per_year[:3]]
                ni_prior_3y = [y.get("net_income", 0) for y in per_year[3:6]]
                cfo_improved = sum(cfo_latest_3y) / 3 > sum(cfo_prior_3y) / 3
                ni_improved = sum(ni_latest_3y) / 3 > sum(ni_prior_3y) / 3
                dims["cash_generation"] = 1 if cfo_improved and ni_improved else 0
            else:
                dims["cash_generation"] = 0

            # 6. Return Ratio Improvement — ROCE improvement > 0 AND ROE improvement > 0
            roce_traj = trajectories.get("roce", {})
            roe_traj = trajectories.get("roe", {})
            dims["return_ratio_improvement"] = 1 if roce_traj.get("improvement", 0) > 0 and roe_traj.get("improvement", 0) > 0 else 0

            score_pct = round(sum(dims.values()) / 6 * 100, 1)
            if score_pct > 67:
                classification = "great"
            elif score_pct >= 50:
                classification = "good"
            else:
                classification = "mediocre"

            greatness = {
                "dimensions": dims,
                "score_pct": score_pct,
                "classification": classification,
            }

        return _clean({
            "trajectories": trajectories or None,
            "capex_productivity": capex_prod or None,
            "greatness": greatness or None,
            "data_years": data_years,
        })

    def get_capital_discipline(self, symbol: str) -> dict:
        """Capital discipline: ROCE x reinvestment, equity dilution, RM cost cycle, BS loss detection."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Capital discipline metrics not applicable to BFSI/Insurance."}

        annuals = self.get_annual_financials(symbol, years=10)
        if not annuals:
            return {"error": f"No annual financial data for {symbol}"}

        ratios = self.get_screener_ratios(symbol, years=10)
        roce_map: dict[str, float] = {}
        for r in ratios:
            fy = r.get("fiscal_year_end", "")
            if r.get("roce_pct") is not None:
                roce_map[fy] = r["roce_pct"]

        # --- 1. ROCE x Reinvestment Rate ---
        roce_reinvest_years: list[dict] = []
        for i, a in enumerate(annuals):
            if i + 1 >= len(annuals):
                break  # need adjacent year for capex delta
            prev = annuals[i + 1]
            fy = a.get("fiscal_year_end", "")
            cfo = a.get("cfo") or 0
            depreciation = a.get("depreciation") or 0
            nb_t = a.get("net_block") or 0
            nb_t1 = prev.get("net_block") or 0
            cwip_t = a.get("cwip") or 0
            cwip_t1 = prev.get("cwip") or 0

            capex = (nb_t - nb_t1) + (cwip_t - cwip_t1) + depreciation
            roce_val = roce_map.get(fy)

            entry: dict = {"fiscal_year_end": fy}
            if roce_val is not None:
                entry["roce_pct"] = roce_val
            if cfo > 0:
                reinvest_rate = round(capex / cfo * 100, 1)
                entry["reinvestment_rate_pct"] = reinvest_rate
                if roce_val is not None:
                    entry["sustainable_growth_pct"] = round(roce_val * reinvest_rate / 100, 1)

            roce_reinvest_years.append(entry)

        # Latest signal
        latest_signal = "challenged"
        if roce_reinvest_years:
            lr = roce_reinvest_years[0]
            r_val = lr.get("roce_pct", 0)
            ri_val = lr.get("reinvestment_rate_pct", 0)
            if r_val > 15 and ri_val > 50:
                latest_signal = "compounder"
            elif r_val > 15 and ri_val <= 50:
                latest_signal = "cash_cow"
            elif r_val <= 15 and ri_val > 50:
                latest_signal = "growth_trap"

        # Avg sustainable growth (3Y)
        sg_vals = [y["sustainable_growth_pct"] for y in roce_reinvest_years[:3] if "sustainable_growth_pct" in y]
        avg_sg_3y = round(sum(sg_vals) / len(sg_vals), 1) if sg_vals else None

        # --- 2. Equity dilution ---
        equity_dilution: dict = {}
        shares_vals = [(a.get("num_shares") or 0) for a in annuals]
        if shares_vals and shares_vals[0] > 0:
            shares_latest = shares_vals[0]
            equity_dilution["shares_latest_cr"] = round(shares_latest, 2)

            # 3Y ago
            idx_3y = min(3, len(shares_vals) - 1)
            shares_3y = shares_vals[idx_3y] if shares_vals[idx_3y] > 0 else None
            if shares_3y and idx_3y > 0:
                equity_dilution["shares_3y_ago_cr"] = round(shares_3y, 2)
                cagr = (shares_latest / shares_3y) ** (1 / idx_3y) - 1
                cagr_pct = round(cagr * 100, 1)
                equity_dilution["cagr_3y_pct"] = cagr_pct
                if cagr_pct > 5:
                    equity_dilution["signal"] = "dilutive"
                elif cagr_pct > 2:
                    equity_dilution["signal"] = "moderate"
                elif cagr_pct >= 0:
                    equity_dilution["signal"] = "stable"
                else:
                    equity_dilution["signal"] = "buyback"

        # --- 3. RM cost/sales cycle ---
        rm_years: list[dict] = []
        for a in annuals:
            rm = a.get("raw_material_cost") or 0
            rev = a.get("revenue") or 0
            if rev > 0 and rm > 0:
                rm_years.append({
                    "fiscal_year_end": a.get("fiscal_year_end"),
                    "rm_pct": round(rm / rev * 100, 1),
                })

        rm_cycle: dict = {}
        if rm_years:
            all_rm_pcts = [y["rm_pct"] for y in rm_years]
            lt_avg = round(sum(all_rm_pcts) / len(all_rm_pcts), 1)
            latest_pct = rm_years[0]["rm_pct"]
            deviation = round(latest_pct - lt_avg, 1)
            rm_cycle = {
                "years": rm_years,
                "lt_avg_pct": lt_avg,
                "latest_pct": latest_pct,
                "deviation_pp": deviation,
            }
            if abs(deviation) < 2:
                rm_cycle["signal"] = "equilibrium"
            elif deviation < -2:
                rm_cycle["signal"] = "margin_tailwind"
            else:
                rm_cycle["signal"] = "margin_pressure"

        # --- 4. Balance sheet loss detection ---
        bs_loss_flags: list[dict] = []
        for i in range(len(annuals) - 1):
            curr = annuals[i]
            prev = annuals[i + 1]
            res_curr = curr.get("reserves") or 0
            res_prev = prev.get("reserves") or 0
            div_amt = curr.get("dividend_amount") or 0

            reserves_change = res_curr - res_prev  # negative = decrease
            if reserves_change < 0 and abs(reserves_change) > (div_amt * 1.5 + 50):
                bs_loss_flags.append({
                    "fiscal_year_end": curr.get("fiscal_year_end"),
                    "reserves_change_cr": round(reserves_change, 2),
                    "dividends_cr": round(div_amt, 2),
                    "flag": "potential_loss_writeoff",
                })

        return _clean({
            "roce_reinvestment": {
                "years": roce_reinvest_years,
                "latest_signal": latest_signal,
                "avg_sustainable_growth_3y": avg_sg_3y,
            } if roce_reinvest_years else None,
            "equity_dilution": equity_dilution or None,
            "rm_cost_cycle": rm_cycle or None,
            "bs_loss_flags": bs_loss_flags,
        })

    # ------------------------------------------------------------------
    # Batch-2 quality metrics (7 methods)
    # ------------------------------------------------------------------

    def get_incremental_roce(self, symbol: str) -> dict:
        """Incremental ROCE: return on newly deployed capital (3Y and 5Y windows)."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Incremental ROCE not applicable to BFSI/Insurance."}

        annuals = self.get_annual_financials(symbol, years=6)
        if not annuals or len(annuals) < 4:
            return {"error": f"Need at least 4 years of data, got {len(annuals)}"}

        # Pre-compute EBIT and CE per year
        ebit_list: list[float] = []
        ce_list: list[float] = []
        for a in annuals:
            ebit_list.append(a.get("operating_profit") or 0)
            ce_list.append(
                (a.get("equity_capital") or 0)
                + (a.get("reserves") or 0)
                + (a.get("borrowings") or 0)
            )

        result: dict = {}
        for window in [3, 5]:
            if len(annuals) < window + 1:
                continue
            delta_ebit = ebit_list[0] - ebit_list[window]
            delta_ce = ce_list[0] - ce_list[window]

            entry: dict = {
                "delta_ebit_cr": round(delta_ebit, 2),
                "delta_ce_cr": round(delta_ce, 2),
            }
            if delta_ce <= 0:
                entry["signal"] = "buyback_or_shrinkage"
            else:
                pct = round(delta_ebit / delta_ce * 100, 1)
                entry["pct"] = pct
                if pct > 15:
                    entry["signal"] = "value_creating"
                elif pct >= 10:
                    entry["signal"] = "moderate"
                else:
                    entry["signal"] = "value_destroying"

            result[f"incremental_roce_{window}y"] = entry

        result["caveat"] = (
            "Capital employed = equity + reserves + borrowings"
            " (other_liabilities excluded as it conflates current and non-current)"
        )
        return _clean(result)

    def get_altman_zscore(self, symbol: str) -> dict:
        """Altman Z-Score (Emerging Market variant) for distress prediction."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Altman Z-Score not applicable to BFSI/Insurance."}

        annuals = self.get_annual_financials(symbol, years=3)
        if not annuals:
            return {"error": f"No annual financial data for {symbol}"}

        years: list[dict] = []
        for a in annuals:
            ta = a.get("total_assets") or 0
            if ta <= 0:
                continue

            wc = (
                (a.get("cash_and_bank") or 0)
                + (a.get("receivables") or 0)
                + (a.get("inventory") or 0)
                - (a.get("other_liabilities") or 0)
            )
            re = a.get("reserves") or 0
            ebit = a.get("operating_profit") or 0
            bv_equity = (a.get("equity_capital") or 0) + (a.get("reserves") or 0)
            tl = (a.get("borrowings") or 0) + (a.get("other_liabilities") or 0)

            last_term = bv_equity / tl if tl > 0 else 10.0

            z = (
                3.25
                + 6.56 * (wc / ta)
                + 3.26 * (re / ta)
                + 6.72 * (ebit / ta)
                + 1.05 * last_term
            )

            if z > 2.6:
                zone = "safe"
            elif z >= 1.1:
                zone = "gray"
            else:
                zone = "distress"

            years.append({
                "fiscal_year_end": a.get("fiscal_year_end"),
                "z_score": round(z, 2),
                "zone": zone,
                "components": {
                    "wc_ta": round(wc / ta, 3),
                    "re_ta": round(re / ta, 3),
                    "ebit_ta": round(ebit / ta, 3),
                    "bve_tl": round(last_term, 3),
                },
            })

        if not years:
            return {"error": "Could not compute Z-Score (total_assets <= 0)"}

        return _clean({
            "years": years,
            "latest_z_score": years[0]["z_score"],
            "latest_zone": years[0]["zone"],
            "caveat": "other_liabilities used as current liabilities proxy; inventory=0 for service companies",
        })

    def get_working_capital_deterioration(self, symbol: str) -> dict:
        """Working capital trend: CCC direction, receivables/inventory vs revenue growth."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Working capital analysis not applicable to BFSI/Insurance."}

        ratios = self.get_screener_ratios(symbol, years=5)
        annuals = self.get_annual_financials(symbol, years=4)
        if not annuals or len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals) if annuals else 0}"}

        # --- CCC trend ---
        ccc_years: list[dict] = []
        for r in (ratios or []):
            ccc = r.get("cash_conversion_cycle")
            if ccc is not None:
                ccc_years.append({
                    "fiscal_year_end": r.get("fiscal_year_end"),
                    "ccc_days": ccc,
                })

        ccc_direction = "stable"
        if len(ccc_years) >= 2:
            latest_ccc = ccc_years[0]["ccc_days"]
            oldest_ccc = ccc_years[-1]["ccc_days"]
            diff = latest_ccc - oldest_ccc
            if diff < -5:
                ccc_direction = "improving"
            elif diff > 5:
                ccc_direction = "deteriorating"

        # --- Receivables / Revenue and Inventory / Revenue ratios ---
        recv_ratio_years: list[dict] = []
        inv_ratio_years: list[dict] = []
        has_inventory = False
        for a in annuals:
            rev = a.get("revenue") or 0
            recv = a.get("receivables")
            inv = a.get("inventory")
            fy = a.get("fiscal_year_end")

            if rev > 0 and recv is not None:
                recv_ratio_years.append({
                    "fiscal_year_end": fy,
                    "recv_pct": round(recv / rev * 100, 1),
                })
            if inv is not None:
                has_inventory = True
                if rev > 0:
                    inv_ratio_years.append({
                        "fiscal_year_end": fy,
                        "inv_pct": round(inv / rev * 100, 1),
                    })

        # --- 3Y CAGRs ---
        recv_cagr = None
        rev_cagr = None
        inv_cagr = None
        if len(annuals) >= 4:
            recv_0 = annuals[0].get("receivables")
            recv_3 = annuals[3].get("receivables")
            rev_0 = annuals[0].get("revenue") or 0
            rev_3 = annuals[3].get("revenue") or 0
            inv_0 = annuals[0].get("inventory")
            inv_3 = annuals[3].get("inventory")

            if recv_0 and recv_0 > 0 and recv_3 and recv_3 > 0:
                recv_cagr = round(((recv_0 / recv_3) ** (1 / 3) - 1) * 100, 1)
            if rev_0 > 0 and rev_3 > 0:
                rev_cagr = round(((rev_0 / rev_3) ** (1 / 3) - 1) * 100, 1)
            if inv_0 and inv_0 > 0 and inv_3 and inv_3 > 0:
                inv_cagr = round(((inv_0 / inv_3) ** (1 / 3) - 1) * 100, 1)

        # --- Flags ---
        flags: list[str] = []
        if recv_cagr is not None and rev_cagr is not None and recv_cagr > 0:
            if rev_cagr > 0 and recv_cagr > 1.5 * rev_cagr:
                flags.append("channel_stuffing_risk")
        if inv_cagr is not None and rev_cagr is not None and inv_cagr > 0:
            if rev_cagr > 0 and inv_cagr > 1.5 * rev_cagr:
                flags.append("inventory_buildup_risk")

        signal = "clean"
        if len(flags) >= 2:
            signal = "concern"
        elif len(flags) == 1:
            signal = "warning"
        if ccc_direction == "deteriorating":
            signal = signal + "_deteriorating" if signal != "clean" else "deteriorating"

        inv_result = None
        if has_inventory:
            inv_result = {"years": inv_ratio_years, "inv_3y_cagr_pct": inv_cagr}

        return _clean({
            "ccc_trend": {"years": ccc_years, "direction": ccc_direction},
            "receivable_ratio": {
                "years": recv_ratio_years,
                "recv_3y_cagr_pct": recv_cagr,
                "rev_3y_cagr_pct": rev_cagr,
            },
            "inventory_ratio": inv_result,
            "flags": flags,
            "signal": signal,
        })

    def get_operating_leverage(self, symbol: str) -> dict:
        """Degree of operating leverage (DOL): earnings sensitivity to revenue changes."""
        annuals = self.get_annual_financials(symbol, years=5)
        if not annuals or len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals) if annuals else 0}"}

        years: list[dict] = []
        for i in range(len(annuals) - 1):
            rev_t = annuals[i].get("revenue") or 0
            rev_t1 = annuals[i + 1].get("revenue") or 0
            ebit_t = annuals[i].get("operating_profit") or 0
            ebit_t1 = annuals[i + 1].get("operating_profit") or 0

            if abs(rev_t1) < 1 or abs(ebit_t1) < 1:
                continue
            # Skip if base EBIT is negative — % change formula gives inverted sign
            if ebit_t1 < 0:
                continue

            rev_change_pct = (rev_t - rev_t1) / rev_t1
            ebit_change_pct = (ebit_t - ebit_t1) / ebit_t1

            if abs(rev_change_pct) < 0.01:
                continue

            dol = ebit_change_pct / rev_change_pct
            dol = max(-10, min(10, dol))

            years.append({
                "fiscal_year_end": annuals[i].get("fiscal_year_end"),
                "rev_change_pct": round(rev_change_pct * 100, 1),
                "ebit_change_pct": round(ebit_change_pct * 100, 1),
                "dol": round(dol, 2),
            })

        if not years:
            return {"error": "Insufficient data to compute operating leverage"}

        # 3Y avg from first 3 valid pairs
        avg_dol_values = [y["dol"] for y in years[:3]]
        avg_3y_dol = round(statistics.mean(avg_dol_values), 2) if avg_dol_values else None

        signal = "moderate"
        if avg_3y_dol is not None:
            abs_dol = abs(avg_3y_dol)
            if abs_dol > 2.5:
                signal = "high_leverage"
            elif abs_dol >= 1.5:
                signal = "moderate"
            else:
                signal = "low"

        return _clean({
            "years": years,
            "avg_3y_dol": avg_3y_dol,
            "signal": signal,
        })

    def get_fcf_yield(self, symbol: str) -> dict:
        """Free cash flow yield vs enterprise value, compared to risk-free rate."""
        annuals = self.get_annual_financials(symbol, years=2)
        if not annuals or len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals) if annuals else 0}"}

        valuation = self.get_valuation_snapshot(symbol)
        ev = valuation.get("enterprise_value")
        if not ev or ev <= 0:
            return {"error": "Enterprise value not available or <= 0"}

        t, t1 = annuals[0], annuals[1]

        nb_t = t.get("net_block") or 0
        nb_t1 = t1.get("net_block") or 0
        cwip_t = t.get("cwip") or 0
        cwip_t1 = t1.get("cwip") or 0
        depreciation = t.get("depreciation") or 0
        cfo = t.get("cfo") or 0
        net_income = t.get("net_income") or 0

        capex = (nb_t - nb_t1) + (cwip_t - cwip_t1) + depreciation
        fcf = cfo - capex

        fcf_yield_pct = round(fcf / ev * 100, 1)
        fcf_pat_ratio = round(fcf / net_income, 2) if net_income and net_income > 0 else None

        risk_free_ref = 7.0
        if fcf_yield_pct > 14:
            signal = "deep_value"
        elif fcf_yield_pct > 7:
            signal = "attractive"
        elif fcf_yield_pct > 0:
            signal = "growth_priced"
        else:
            signal = "hope_trade"

        return _clean({
            "fcf_cr": round(fcf, 2),
            "capex_cr": round(capex, 2),
            "cfo_cr": round(cfo, 2),
            "ev_cr": round(ev, 2),
            "fcf_yield_pct": fcf_yield_pct,
            "fcf_pat_ratio": fcf_pat_ratio,
            "risk_free_ref_pct": risk_free_ref,
            "signal": signal,
        })

    def get_tax_rate_analysis(self, symbol: str) -> dict:
        """Effective tax rate trend analysis with anomaly detection."""
        annuals = self.get_annual_financials(symbol, years=6)
        if not annuals:
            return {"error": f"No annual financial data for {symbol}"}

        years: list[dict] = []
        etr_values: list[float] = []
        for a in annuals:
            pbt = a.get("profit_before_tax") or 0
            tax_val = a.get("tax") or 0
            fy = a.get("fiscal_year_end")

            entry: dict = {
                "fiscal_year_end": fy,
                "pbt_cr": round(pbt, 2),
                "tax_cr": round(tax_val, 2),
            }
            if pbt <= 0:
                entry["etr_pct"] = None
                entry["note"] = "negative_pbt"
            else:
                etr = round(tax_val / pbt * 100, 1)
                entry["etr_pct"] = etr
                etr_values.append(etr)

            years.append(entry)

        # Averages
        valid_3y = [v for v in etr_values[:3] if v is not None]
        valid_5y = [v for v in etr_values[:5] if v is not None]
        avg_3y_etr = round(statistics.mean(valid_3y), 1) if valid_3y else None
        avg_5y_etr = round(statistics.mean(valid_5y), 1) if valid_5y else None

        # Flags
        flags: list[dict] = []

        # YoY drop > 5pp
        for i in range(len(years) - 1):
            curr_etr = years[i].get("etr_pct")
            prev_etr = years[i + 1].get("etr_pct")
            if curr_etr is not None and prev_etr is not None:
                drop = prev_etr - curr_etr
                if drop > 5:
                    flags.append({
                        "year": years[i].get("fiscal_year_end"),
                        "flag": "tax_anomaly",
                        "drop_pp": round(drop, 1),
                    })

        # Below statutory
        if avg_3y_etr is not None and avg_3y_etr < 20.0:
            flags.append({
                "flag": "below_statutory",
                "avg_3y": avg_3y_etr,
                "statutory_ref": 25.17,
            })

        # Headwind — monotonically increasing over latest 3 years
        recent_3_etr = [y.get("etr_pct") for y in years[:3]]
        if (
            len(recent_3_etr) == 3
            and all(v is not None for v in recent_3_etr)
            and recent_3_etr[0] > recent_3_etr[1] > recent_3_etr[2]
        ):
            flags.append({"flag": "headwind"})

        # Signal
        signal = "normal"
        has_anomaly = any(f.get("flag") == "tax_anomaly" for f in flags)
        has_below = any(f.get("flag") == "below_statutory" for f in flags)
        has_headwind = any(f.get("flag") == "headwind" for f in flags)
        if has_anomaly:
            signal = "anomaly"
        elif has_below:
            signal = "below_statutory"
        elif has_headwind:
            signal = "headwind"

        return _clean({
            "years": years,
            "avg_3y_etr": avg_3y_etr,
            "avg_5y_etr": avg_5y_etr,
            "statutory_rate_ref": 25.17,
            "flags": flags,
            "signal": signal,
        })

    def get_receivables_quality(self, symbol: str) -> dict:
        """Receivables quality: revenue recognition risk detection."""
        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            return {"skipped": True, "reason": "Receivables quality not applicable to BFSI/Insurance."}

        annuals = self.get_annual_financials(symbol, years=5)
        ratios = self.get_screener_ratios(symbol, years=5)
        if not annuals or len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals) if annuals else 0}"}

        # Receivables / Revenue ratio per year
        recv_ratio_trend: list[dict] = []
        for a in annuals:
            rev = a.get("revenue") or 0
            recv = a.get("receivables")
            fy = a.get("fiscal_year_end")
            if rev > 0 and recv is not None:
                recv_ratio_trend.append({
                    "fiscal_year_end": fy,
                    "recv_pct_of_rev": round(recv / rev * 100, 1),
                })

        # 3Y CAGRs
        recv_cagr = None
        rev_cagr = None
        if len(annuals) >= 4:
            recv_0 = annuals[0].get("receivables")
            recv_3 = annuals[3].get("receivables")
            rev_0 = annuals[0].get("revenue") or 0
            rev_3 = annuals[3].get("revenue") or 0

            if recv_0 and recv_0 > 0 and recv_3 and recv_3 > 0:
                recv_cagr = round(((recv_0 / recv_3) ** (1 / 3) - 1) * 100, 1)
            if rev_0 > 0 and rev_3 > 0:
                rev_cagr = round(((rev_0 / rev_3) ** (1 / 3) - 1) * 100, 1)

        # Debtor days from screener_ratios
        debtor_days_info: dict = {}
        if ratios and len(ratios) >= 1:
            latest_dd = ratios[0].get("debtor_days")
            oldest_dd = None
            if len(ratios) >= 4:
                oldest_dd = ratios[3].get("debtor_days")
            elif len(ratios) >= 2:
                oldest_dd = ratios[-1].get("debtor_days")

            debtor_days_info["latest"] = latest_dd
            debtor_days_info["3y_ago"] = oldest_dd
            if latest_dd is not None and oldest_dd is not None and oldest_dd > 0:
                debtor_days_info["change_pct"] = round(
                    (latest_dd - oldest_dd) / oldest_dd * 100, 1
                )

        # Flags
        flags: list[str] = []
        if recv_cagr is not None and rev_cagr is not None and recv_cagr > 0:
            if rev_cagr > 0 and recv_cagr > 1.5 * rev_cagr:
                flags.append("revenue_quality_risk")
        dd_change = debtor_days_info.get("change_pct")
        if dd_change is not None and dd_change > 20:
            flags.append("debtor_days_deterioration")

        signal = "clean"
        if len(flags) >= 2:
            signal = "concern"
        elif len(flags) == 1:
            signal = "warning"

        return _clean({
            "receivable_ratio_trend": recv_ratio_trend,
            "recv_3y_cagr_pct": recv_cagr,
            "rev_3y_cagr_pct": rev_cagr,
            "debtor_days": debtor_days_info or None,
            "flags": flags,
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

        # 7. No dilution — compare num_shares directly (more reliable than NI/EPS inference)
        shares_t = g(t, "num_shares")
        shares_t1 = g(t1, "num_shares")
        if shares_t is not None and shares_t1 is not None and shares_t1 > 0:
            passed = shares_t <= shares_t1
            change_pct = round((shares_t - shares_t1) / shares_t1 * 100, 2)
            criteria.append({"name": "No dilution", "passed": passed, "value": change_pct, "unit": "% change"})
            if passed:
                score += 1
        else:
            max_score -= 1
            criteria.append({"name": "No dilution", "passed": None, "value": None, "note": "EPS is 0 or None, skipped"})

        # 8. ΔGross Margin > 0
        if is_bfsi:
            # NIM proxy: (revenue - interest) / avg_total_assets
            avg_ta = (ta_t + ta_t1) / 2 if ta_t and ta_t1 and ta_t > 0 and ta_t1 > 0 else None
            gm_t = (rev_t - (interest_t or 0)) / avg_ta if rev_t is not None and avg_ta and avg_ta > 0 else None
            gm_t1 = (rev_t1 - (interest_t1 or 0)) / avg_ta if rev_t1 is not None and avg_ta and avg_ta > 0 else None
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

        # SGI dominance check — high revenue growth inflates M-Score without manipulation
        sgi_contribution = 0.892 * variables["SGI"]  # SGI coefficient * SGI value
        positive_components = sum(
            coeff * variables[var]
            for var, coeff in [
                ("DSRI", 0.920), ("GMI", 0.528), ("AQI", 0.404),
                ("SGI", 0.892), ("DEPI", 0.115), ("TATA", 4.679),
            ]
            if coeff * variables[var] > 0
        )
        sgi_dominant = positive_components > 0 and (sgi_contribution / positive_components) > 0.40

        return _clean({
            "m_score": round(m, 4),
            "signal": signal,
            "variables": variables,
            "data_quality": "8/8 variables computed",
            "sgi_dominant": sgi_dominant,
            "sgi_contribution_pct": round(sgi_contribution / positive_components * 100, 1) if positive_components > 0 else 0,
        })

    # --- Reverse DCF / Capex / Common Size (Batch 1B) ---

    def get_reverse_dcf(self, symbol: str) -> dict:
        """Bernstein-style reverse DCF: solve for implied growth, implied margin, + sensitivity matrix."""
        annual = self.get_annual_financials(symbol, years=10)
        if len(annual) < 2:
            return {"error": "Need at least 2 years of financials"}

        valuation = self.get_valuation_snapshot(symbol)
        market_cap = valuation.get("market_cap")
        if not market_cap or market_cap <= 0:
            return {"error": "No market cap data"}

        latest = annual[0]  # most recent year
        prev = annual[1]
        is_bfsi = self._is_bfsi(symbol) or self._is_insurance(symbol)

        # Dynamic WACC parameters
        wacc_data = self.get_wacc_params(symbol)

        # Common: compute tax rate from latest year
        tax_amount = latest.get("tax", 0) or 0
        pbt = latest.get("profit_before_tax", 0) or 0
        tax_rate = tax_amount / pbt if pbt > 0 else 0.25

        if is_bfsi:
            # FCFE model: discount dividendable earnings at cost of equity
            base_ni = latest.get("net_income", 0)
            if not base_ni or base_ni <= 0:
                return {"error": "Negative/zero net income — cannot run reverse DCF"}
            # ROE needed for sustainable payout constraint
            equity_capital = latest.get("equity_capital", 0) or 0
            reserves = latest.get("reserves", 0) or 0
            book_value = equity_capital + reserves
            bfsi_roe = base_ni / book_value if book_value > 0 else 0.14
            discount_rate = wacc_data.get("ke", 0.14)  # Cost of equity from CAPM
            target = market_cap  # FCFE model → PV = Market Cap directly
            model = "FCFE"
            cash = 0
            borrowings = 0
            capex = 0
            base_cf = base_ni  # used for display only
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
            # FCFF = CFO + Interest*(1-tax_rate) - Capex
            # CFO under Ind AS is post-interest, so add back after-tax interest for FCFF
            interest_expense = latest.get("interest", 0) or 0
            base_cf = cfo + interest_expense * (1 - tax_rate) - capex

            if base_cf <= 0:
                # Normalize: use NOPAT * (1 - avg reinvestment) instead of raw NI
                op = latest.get("operating_profit", 0) or 0
                nopat_norm = op * (1 - tax_rate) if op > 0 else (latest.get("net_income", 0) or 0)
                # Use 30% default reinvestment for normalization
                base_cf = nopat_norm * 0.70
                if base_cf <= 0:
                    return {"error": "Negative/zero normalized FCFF — cannot run reverse DCF"}

            cash = latest.get("cash_and_bank", 0) or 0
            borrowings = latest.get("borrowings", 0) or 0
            discount_rate = wacc_data.get("wacc", 0.12)  # Dynamic WACC
            target = market_cap - cash + borrowings  # Target = Enterprise Value
            model = "FCFF"

        terminal_g = wacc_data.get("terminal_growth", 0.05)

        # --- 1. Implied Growth Solve ---
        if is_bfsi:
            # BFSI: embed payout constraint in DCF — payout = 1 - g/ROE
            def dcf_value(g):
                payout = max(1 - (g / bfsi_roe), 0) if bfsi_roe > 0 else 0
                cf = base_ni * payout
                pv = sum(cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                # Terminal: payout adjusts to terminal growth
                terminal_payout = max(1 - (terminal_g / bfsi_roe), 0) if bfsi_roe > 0 else 0
                terminal_cf = base_ni * (1 + g) ** 10 * terminal_payout
                terminal = terminal_cf * (1 + terminal_g) / (discount_rate - terminal_g)
                pv += terminal / (1 + discount_rate) ** 10
                return pv
        else:
            def dcf_value(g):
                pv = sum(base_cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                terminal = base_cf * (1 + g) ** 10 * (1 + terminal_g) / (discount_rate - terminal_g)
                pv += terminal / (1 + discount_rate) ** 10
                return pv

        def _solve_growth(dcf_fn):
            lo, hi = -0.50, 2.00
            for _ in range(100):
                mid = (lo + hi) / 2
                if dcf_fn(mid) < target:
                    lo = mid
                else:
                    hi = mid
            g = round((lo + hi) / 2, 4)
            return g, g >= 1.99 or g <= -0.49

        implied_g, growth_at_bound = _solve_growth(dcf_value)

        # --- Normalized (5Y avg) DCF — cycle-adjusted view ---
        normalized = {}
        if len(annual) >= 5:
            if is_bfsi:
                avg_ni = statistics.mean(a.get("net_income", 0) or 0 for a in annual[:5])
                if avg_ni > 0:
                    def dcf_value_norm(g):
                        payout = max(1 - (g / bfsi_roe), 0) if bfsi_roe > 0 else 0
                        cf = avg_ni * payout
                        pv = sum(cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                        terminal_payout = max(1 - (terminal_g / bfsi_roe), 0) if bfsi_roe > 0 else 0
                        t_cf = avg_ni * (1 + g) ** 10 * terminal_payout
                        t_val = t_cf * (1 + terminal_g) / (discount_rate - terminal_g)
                        pv += t_val / (1 + discount_rate) ** 10
                        return pv
                    norm_g, norm_at_bound = _solve_growth(dcf_value_norm)
                    normalized = {
                        "implied_growth_normalized": norm_g,
                        "base_cf_normalized": round(avg_ni, 2),
                        "at_bound": norm_at_bound,
                    }
            else:
                # Average FCFF over available years (up to 5)
                fcffs = []
                for i in range(min(5, len(annual) - 1)):
                    d, p = annual[i], annual[i + 1]
                    nb_d, nb_p = (d.get("net_block", 0) or 0), (p.get("net_block", 0) or 0)
                    cw_d, cw_p = (d.get("cwip", 0) or 0), (p.get("cwip", 0) or 0)
                    dep_d = d.get("depreciation", 0) or 0
                    cfo_d = d.get("cfo", 0) or 0
                    int_d = d.get("interest", 0) or 0
                    cap_d = (nb_d - nb_p) + (cw_d - cw_p) + dep_d
                    fcff_d = cfo_d + int_d * (1 - tax_rate) - cap_d
                    fcffs.append(fcff_d)
                avg_fcff = statistics.mean(fcffs) if fcffs else 0
                if avg_fcff > 0:
                    def dcf_value_norm(g):
                        pv = sum(avg_fcff * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                        t_val = avg_fcff * (1 + g) ** 10 * (1 + terminal_g) / (discount_rate - terminal_g)
                        pv += t_val / (1 + discount_rate) ** 10
                        return pv
                    norm_g, norm_at_bound = _solve_growth(dcf_value_norm)
                    normalized = {
                        "implied_growth_normalized": norm_g,
                        "base_cf_normalized": round(avg_fcff, 2),
                        "at_bound": norm_at_bound,
                    }

            if normalized and not normalized.get("at_bound"):
                delta = abs(implied_g - normalized["implied_growth_normalized"])
                normalized["cycle_signal"] = "high_cyclicality" if delta > 0.10 else "moderate_cyclicality" if delta > 0.05 else "low_cyclicality"

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
        current_net_margin = round(current_net_income / current_revenue, 4) if current_revenue > 0 else 0

        # Compute EBITDA margin (operating margin) — not inflated by other income
        depr_latest = latest.get("depreciation", 0) or 0
        op_profit = latest.get("operating_profit")
        if op_profit is not None:
            current_ebitda = op_profit + depr_latest
        else:
            # Bottom-up: EBITDA = NI + Tax + Interest + Depreciation
            tax_val = latest.get("tax", 0) or 0
            interest_val = latest.get("interest", 0) or 0
            current_ebitda = current_net_income + tax_val + interest_val + depr_latest
        current_ebitda_margin = round(current_ebitda / current_revenue, 4) if current_revenue > 0 else 0
        num_shares = latest.get("num_shares", 0) or 0
        current_price = valuation.get("price")

        implied_margin = None
        hist_g = cagr_3y or cagr_5y or 0.10  # fallback 10%

        if not is_bfsi and current_revenue > 0:
            # Reinvestment rate = net reinvestment / NOPAT (Damodaran textbook)
            # Net reinvestment = capex - depreciation (+ ΔWC if available, we skip)
            depr = latest.get("depreciation", 0) or 0
            net_reinvestment = capex - depr
            # NOPAT = Operating Profit * (1 - tax_rate), not net income
            op = latest.get("operating_profit", 0) or 0
            nopat = op * (1 - tax_rate) if op > 0 else current_net_income
            reinvestment = min(max(net_reinvestment / nopat, 0.05), 0.80) if nopat > 0 else 0.30

            # Terminal reinvestment: company growing at terminal_g needs less reinvestment
            # Reinvestment = g / ROIC; at terminal, reinvestment = terminal_g / ROIC
            roic = nopat / (latest.get("total_assets", 0) or 1) if nopat > 0 else 0.15
            terminal_reinvestment = min(terminal_g / roic, 0.80) if roic > 0 else 0.10

            def dcf_with_margin(margin):
                nopat_yr0 = current_revenue * margin
                cf_year0 = nopat_yr0 * (1 - reinvestment)
                pv = sum(cf_year0 * (1 + hist_g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                # Terminal: lower reinvestment at terminal growth rate
                terminal_nopat = nopat_yr0 * (1 + hist_g) ** 10
                terminal_cf = terminal_nopat * (1 - terminal_reinvestment)
                eff_discount = max(discount_rate - terminal_g, 0.001)
                terminal = terminal_cf * (1 + terminal_g) / eff_discount
                pv += terminal / (1 + discount_rate) ** 10
                return pv

            lo_m, hi_m = 0.01, 1.00
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
            # reinvestment already computed above (net_reinvestment / nopat)
            growth_scenarios = [0.05, 0.10, 0.15, 0.20, 0.25]
            margin_scenarios = [0.05, 0.08, 0.12, 0.16, 0.20]

            for g in growth_scenarios:
                for m in margin_scenarios:
                    cf = current_revenue * m * (1 - reinvestment)
                    pv = sum(cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                    eff_discount = max(discount_rate - terminal_g, 0.001)
                    terminal = cf * (1 + g) ** 10 * (1 + terminal_g) / eff_discount
                    pv += terminal / (1 + discount_rate) ** 10
                    implied_mcap = pv + cash - borrowings
                    implied_price = round(implied_mcap * 1e7 / num_shares, 2) if num_shares > 0 else None
                    sensitivity.append({"growth": g, "margin": m, "implied_price": implied_price})
        elif is_bfsi:
            # BFSI: use book_value × ROE × payout_ratio as FCFE
            # Banks must retain capital to grow: payout = 1 - g/ROE
            equity_capital = latest.get("equity_capital", 0) or 0
            reserves = latest.get("reserves", 0) or 0
            book_value = equity_capital + reserves
            roe_scenarios = [0.10, 0.12, 0.14, 0.16, 0.18]
            growth_scenarios = [0.05, 0.10, 0.15, 0.20, 0.25]

            for g in growth_scenarios:
                for roe in roe_scenarios:
                    net_income = book_value * roe
                    # g >= roe means bank can't grow this fast without raising equity
                    payout_ratio = max(1 - (g / roe), 0) if roe > 0 else 0
                    cf = net_income * payout_ratio  # true FCFE
                    pv = sum(cf * (1 + g) ** n / (1 + discount_rate) ** n for n in range(1, 11))
                    # Terminal: use terminal growth payout, not high-growth payout
                    terminal_payout = max(1 - (terminal_g / roe), 0) if roe > 0 else 0
                    terminal_cf = net_income * (1 + g) ** 10 * terminal_payout
                    eff_discount = max(discount_rate - terminal_g, 0.001)
                    terminal = terminal_cf * (1 + terminal_g) / eff_discount
                    pv += terminal / (1 + discount_rate) ** 10
                    implied_price = round(pv * 1e7 / num_shares, 2) if num_shares > 0 else None
                    sensitivity.append({"growth": g, "roe": roe, "implied_price": implied_price})

        # --- 4. Enhanced Assessment ---
        hist = cagr_3y or cagr_5y
        if growth_at_bound:
            assessment = f"Model cannot solve — implied growth hit bound ({implied_g:.0%}). FCFF (₹{base_cf:.0f} Cr) is too small relative to EV (₹{target:.0f} Cr). Check if capex-heavy or one-off year."
        elif hist is not None:
            if implied_g > hist + 0.05:
                growth_view = f"growth acceleration ({implied_g:.0%} vs {hist:.0%} historical)"
            elif implied_g < hist - 0.05:
                growth_view = f"growth deceleration ({implied_g:.0%} vs {hist:.0%} historical)"
            else:
                growth_view = f"growth continuation ({implied_g:.0%} ≈ {hist:.0%} historical)"

            if implied_margin is not None and current_ebitda_margin > 0:
                if implied_margin > current_ebitda_margin + 0.03:
                    margin_view = f"margin expansion ({implied_margin:.0%} implied vs {current_ebitda_margin:.0%} current EBITDA margin)"
                elif implied_margin < current_ebitda_margin - 0.03:
                    margin_view = f"margin compression ({implied_margin:.0%} implied vs {current_ebitda_margin:.0%} current EBITDA margin)"
                else:
                    margin_view = f"stable margins ({implied_margin:.0%} ≈ {current_ebitda_margin:.0%} current EBITDA margin)"
                assessment = f"Market is pricing in {growth_view} + {margin_view}"
            else:
                assessment = f"Market is pricing in {growth_view}"
        else:
            assessment = f"Implied growth rate: {implied_g:.0%}"

        result = {
            "implied_growth_rate": implied_g,
            "implied_margin": implied_margin,
            "current_ebitda_margin": current_ebitda_margin,
            "current_net_margin": current_net_margin,
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
        if normalized:
            result["normalized_5y"] = normalized
        result["wacc_params"] = wacc_data
        return result

    def get_capital_allocation(self, symbol: str, years: int = 5) -> dict:
        """Capital allocation analysis — how does the company deploy its cash?

        Computes from annual_financials + valuation_snapshot:
        - 5Y cumulative CFO
        - Deployment: capex, acquisitions (via CFI), dividends, net cash change
        - Cash as % of market cap
        - Payout ratio trend
        - Cash yield (dividends / market cap)
        """
        annual = self.get_annual_financials(symbol, years=years + 1)
        if len(annual) < 2:
            return {"error": "Need at least 2 years of financials"}

        valuation = self.get_valuation_snapshot(symbol)
        market_cap = valuation.get("market_cap")

        # Use up to `years` most recent years
        data = annual[:years]

        # Cumulative figures
        total_cfo = sum(d.get("cfo", 0) or 0 for d in data)
        total_dividends = 0
        dividend_details = []
        for d in data:
            # Screener uses dividend_amount (total dividends paid in crores)
            div_paid = d.get("dividend_amount", 0) or d.get("dividend_payout", 0) or 0
            ni = d.get("net_income", 0) or 0
            fy = d.get("fiscal_year_end", "")

            total_dividends += div_paid

            payout_ratio = round(div_paid / ni * 100, 1) if ni and ni > 0 else None
            dividend_details.append({
                "fiscal_year": fy,
                "dividends_paid": round(div_paid, 2),
                "net_income": round(ni, 2),
                "payout_ratio_pct": payout_ratio,
            })

        # Capex: delta_Net_Block + delta_CWIP + Depreciation
        total_gross_capex = 0
        total_divestments = 0
        for i, d in enumerate(data):
            if i + 1 < len(annual):  # need previous year for delta
                prev = annual[i + 1]  # data is sorted most recent first
                nb_t = d.get("net_block", 0) or 0
                nb_t1 = prev.get("net_block", 0) or 0
                cwip_t = d.get("cwip", 0) or 0
                cwip_t1 = prev.get("cwip", 0) or 0
                depr = d.get("depreciation", 0) or 0
                net_capex = (nb_t - nb_t1) + (cwip_t - cwip_t1) + depr
                if net_capex >= 0:
                    total_gross_capex += net_capex
                else:
                    total_divestments += abs(net_capex)
        total_capex = total_gross_capex - total_divestments

        # Cash position (cash_and_bank + investments for companies holding cash in MFs/FDs)
        latest = data[0]
        cash_bank = latest.get("cash_and_bank", 0) or 0
        investments = latest.get("investments", 0) or 0
        total_cash = cash_bank + investments
        borrowings = latest.get("borrowings", 0) or 0
        net_cash = total_cash - borrowings

        # Cash as % of market cap
        cash_pct_mcap = round(total_cash / market_cap * 100, 1) if market_cap and market_cap > 0 else None
        net_cash_pct_mcap = round(net_cash / market_cap * 100, 1) if market_cap and market_cap > 0 else None

        # Cash yield = dividends / market cap (last year)
        last_year_div = dividend_details[0]["dividends_paid"] if dividend_details else 0
        cash_yield = round(last_year_div / market_cap * 100, 2) if market_cap and market_cap > 0 else None

        # Deployment breakdown
        # CFI includes capex + acquisitions + investments
        # Residual = CFO - capex - dividends = what went to cash/investments/acquisitions
        residual = total_cfo - total_capex - total_dividends

        result = {
            "symbol": symbol,
            "years_analyzed": len(data),
            "cumulative": {
                "cfo": round(total_cfo, 2),
                "gross_capex": round(total_gross_capex, 2),
                "divestments": round(total_divestments, 2),
                "net_capex": round(total_capex, 2),
                "dividends": round(total_dividends, 2),
                "residual_cash_acquisitions": round(residual, 2),
                "capex_pct_of_cfo": round(total_gross_capex / total_cfo * 100, 1) if total_cfo > 0 else None,
                "dividends_pct_of_cfo": round(total_dividends / total_cfo * 100, 1) if total_cfo > 0 else None,
            },
            "cash_position": {
                "cash_and_bank": round(cash_bank, 2),
                "investments": round(investments, 2),
                "total_cash": round(total_cash, 2),
                "borrowings": round(borrowings, 2),
                "net_cash": round(net_cash, 2),
                "cash_pct_of_market_cap": cash_pct_mcap,
                "net_cash_pct_of_market_cap": net_cash_pct_mcap,
            },
            "cash_yield_pct": cash_yield,
            "payout_trend": dividend_details,
        }

        if market_cap:
            result["market_cap"] = market_cap

        if self._is_bfsi(symbol) or self._is_insurance(symbol):
            result["bfsi_investments_caveat"] = (
                "For BFSI companies, 'investments' represent the core loan/investment book, "
                "not idle cash. Cash position and capital deployment metrics should be interpreted "
                "differently — high investments are a sign of business growth, not capital misallocation."
            )

        return result

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

            # Book Value / Share (net_worth is in Cr, convert to Rs for per-share)
            if num_shares > 0:
                bvps = net_worth * 1e7 / num_shares
                entry["book_value_per_share"] = round(bvps, 2)
                # P/B (use current price if available)
                if current_price and current_price > 0:
                    entry["pb_ratio"] = round(current_price / bvps, 2)

            # Equity Multiplier = total_assets / net_worth (true leverage including deposits)
            if net_worth > 0:
                entry["equity_multiplier"] = round(total_assets / net_worth, 2)

            # Credit-Deposit ratio = Advances / Deposits (>78% stretched, >85% risky)
            advances = row.get("other_assets", 0) or 0  # Screener maps advances to other_assets for banks
            deposits = borrowings  # Screener maps deposits+market borrowings to borrowings
            if deposits > 0 and advances > 0:
                entry["cd_ratio_pct"] = round(advances / deposits * 100, 2)

            entry["nii"] = round(nii, 2)
            entry["net_worth"] = round(net_worth, 2)

            years_data.append(entry)

        return {"is_bfsi": True, "years": years_data}

    # --- Insurance Metrics ---

    def get_insurance_metrics(self, symbol: str) -> dict:
        """Insurance-specific metrics: ROE, ROA, opex ratio, premium growth, P/B."""
        if not self._is_insurance(symbol):
            return {"skipped": True, "reason": f"{symbol} is not an insurance stock"}

        annual = self.get_annual_financials(symbol, years=5)
        if not annual:
            return {"error": "No annual financial data"}

        valuation = self.get_valuation_snapshot(symbol)
        current_price = valuation.get("price")

        industry = self._get_industry(symbol)
        sub_type = "life" if "Life" in (industry or "") else "general"

        years_data = []
        prev_revenue = None
        for row in annual:
            # Screener stores insurance premiums as "revenue" — proxy for NEP.
            # Not identical to Net Earned Premium but best available from standardized data.
            revenue = row.get("revenue", 0) or 0
            net_income = row.get("net_income", 0) or 0
            employee_cost = row.get("employee_cost", 0) or 0
            other_exp = row.get("other_expenses_detail", 0) or row.get("other_expenses", 0) or 0
            total_assets = row.get("total_assets", 0) or 0
            equity_capital = row.get("equity_capital", 0) or 0
            reserves = row.get("reserves", 0) or 0
            num_shares = row.get("num_shares", 0) or 0

            net_worth = equity_capital + reserves
            entry = {"fiscal_year": row.get("fiscal_year_end", "")}

            if net_worth > 0:
                entry["roe_pct"] = round(net_income / net_worth * 100, 2)
            if total_assets > 0:
                entry["roa_pct"] = round(net_income / total_assets * 100, 2)
            if revenue > 0:
                entry["opex_ratio_pct"] = round((employee_cost + other_exp) / revenue * 100, 2)
            if prev_revenue and prev_revenue > 0:
                entry["premium_growth_yoy_pct"] = round((revenue - prev_revenue) / prev_revenue * 100, 2)
            prev_revenue = revenue

            entry["net_worth"] = round(net_worth, 2)
            if num_shares > 0:
                bvps = net_worth * 1e7 / num_shares
                entry["book_value_per_share"] = round(bvps, 2)
                if current_price and current_price > 0:
                    entry["pb_ratio"] = round(current_price / bvps, 2)

            years_data.append(entry)

        # Surface concall KPIs for insurance-specific metrics
        concall_kpis: dict = {}
        concall = self.get_concall_insights(symbol)
        if "error" not in concall:
            _insurance_keys = {"vnb", "vnb_margin", "combined_ratio", "persistency",
                               "embedded_value", "solvency"}
            for q in concall.get("quarters", []):
                for section in ("operational_metrics", "key_numbers_mentioned"):
                    metrics = q.get(section, {})
                    if isinstance(metrics, dict):
                        for k, v in metrics.items():
                            if k.lower().replace(" ", "_") in _insurance_keys:
                                concall_kpis[k] = v

        if not concall_kpis:
            concall_kpis = {
                "available": False,
                "note": "Key insurance KPIs (VNB, combined ratio, persistency, embedded value, "
                        "solvency) not available from concall data. Flag as open questions.",
            }

        return {"is_insurance": True, "sub_type": sub_type, "years": years_data, "concall_kpis": concall_kpis}

    # --- Metals/Mining Metrics ---

    def get_metals_metrics(self, symbol: str) -> dict:
        """Metals/Mining-specific metrics: EBITDA, Net Debt/EBITDA, EV/EBITDA."""
        if not self._is_metals(symbol):
            return {"skipped": True, "reason": f"{symbol} is not a metals/mining stock"}

        annual = self.get_annual_financials(symbol, years=5)
        if not annual:
            return {"error": "No annual financial data"}

        valuation = self.get_valuation_snapshot(symbol)

        years_data = []
        prev_revenue = None
        nd_ebitda_values = []

        for row in annual:
            op = row.get("operating_profit", 0) or 0
            dep = row.get("depreciation", 0) or 0
            borrowings = row.get("borrowings", 0) or 0
            cash = row.get("cash_and_bank", 0) or 0
            revenue = row.get("revenue", 0) or 0

            ebitda = op + dep
            net_debt = borrowings - cash

            entry = {"fiscal_year": row.get("fiscal_year_end", "")}
            entry["ebitda"] = round(ebitda, 2)
            entry["net_debt"] = round(net_debt, 2)

            if ebitda > 0:
                nd_ebitda = round(net_debt / ebitda, 2)
                entry["net_debt_ebitda"] = nd_ebitda
                nd_ebitda_values.append(nd_ebitda)

            entry["revenue"] = round(revenue, 2)
            if prev_revenue and prev_revenue > 0:
                entry["revenue_yoy_pct"] = round((revenue - prev_revenue) / prev_revenue * 100, 2)
            prev_revenue = revenue

            if ebitda > 0 and revenue > 0:
                entry["ebitda_margin_pct"] = round(ebitda / revenue * 100, 2)

            years_data.append(entry)

        return {
            "is_metals": True,
            "years": years_data,
            "current_ev_ebitda": valuation.get("ev_ebitda"),
            "avg_net_debt_ebitda_5y": round(sum(nd_ebitda_values) / len(nd_ebitda_values), 2) if nd_ebitda_values else None,
        }

    # --- Real Estate Metrics ---

    def get_realestate_metrics(self, symbol: str) -> dict:
        """Real estate metrics: Adjusted BV/share, P/Adjusted BV, Net Debt/Equity."""
        if not self._is_realestate(symbol):
            return {"skipped": True, "reason": f"{symbol} is not a real estate stock"}

        annual = self.get_annual_financials(symbol, years=5)
        if not annual:
            return {"error": "No annual financial data"}

        valuation = self.get_valuation_snapshot(symbol)
        current_price = valuation.get("price")

        years_data = []
        prev_revenue = None
        for row in annual:
            revenue = row.get("revenue", 0) or 0
            total_assets = row.get("total_assets", 0) or 0
            borrowings = row.get("borrowings", 0) or 0
            other_liabilities = row.get("other_liabilities", 0) or 0
            equity_capital = row.get("equity_capital", 0) or 0
            reserves = row.get("reserves", 0) or 0
            num_shares = row.get("num_shares", 0) or 0
            cash_and_bank = row.get("cash_and_bank", 0) or 0

            net_worth = equity_capital + reserves
            entry = {"fiscal_year": row.get("fiscal_year_end", "")}

            # Adjusted Book Value per share (NOT true NAV — no land revaluation)
            if num_shares > 0:
                adjusted_bv = (total_assets - borrowings - other_liabilities) / num_shares * 1e7
                entry["adjusted_bv_per_share"] = round(adjusted_bv, 2)
                if current_price and current_price > 0 and adjusted_bv > 0:
                    entry["p_adjusted_bv"] = round(current_price / adjusted_bv, 2)

            if net_worth > 0:
                entry["net_debt_equity"] = round((borrowings - cash_and_bank) / net_worth, 2)

            if prev_revenue and prev_revenue > 0:
                entry["revenue_growth_yoy_pct"] = round((revenue - prev_revenue) / prev_revenue * 100, 2)
            prev_revenue = revenue

            entry["net_worth"] = round(net_worth, 2)
            years_data.append(entry)

        return {
            "is_realestate": True,
            "years": years_data,
            "note": "Inventory months NOT computed — requires area sold/sales velocity data "
                    "from investor presentations, not annual financials.",
        }

    # --- Telecom Metrics ---

    def get_telecom_metrics(self, symbol: str) -> dict:
        """Telecom-specific metrics: EBITDA, Net Debt/EBITDA, OpFCF, Capex/Revenue."""
        if not self._is_telecom(symbol) and not self._is_telecom_infra(symbol):
            return {"skipped": True, "reason": f"{symbol} is not a telecom stock"}

        annual = self.get_annual_financials(symbol, years=5)
        if not annual:
            return {"error": "No annual financial data"}

        valuation = self.get_valuation_snapshot(symbol)
        sub_type = "telecom" if self._is_telecom(symbol) else "telecom_infra"

        years_data = []
        for row in annual:
            op = row.get("operating_profit", 0) or 0
            dep = row.get("depreciation", 0) or 0
            borrowings = row.get("borrowings", 0) or 0
            cash = row.get("cash_and_bank", 0) or 0
            revenue = row.get("revenue", 0) or 0
            cfo = row.get("cfo", 0) or 0
            cfi = row.get("cfi", 0) or 0

            ebitda = op + dep
            net_debt = borrowings - cash

            entry = {"fiscal_year": row.get("fiscal_year_end", "")}
            entry["ebitda"] = round(ebitda, 2)
            entry["net_debt"] = round(net_debt, 2)

            if ebitda > 0:
                entry["net_debt_ebitda"] = round(net_debt / ebitda, 2)
            if revenue > 0:
                entry["ebitda_margin_pct"] = round(ebitda / revenue * 100, 2)
                entry["capex_revenue_pct"] = round(abs(cfi) / revenue * 100, 2) if cfi else None

            # OpFCF = CFO + CFI (CFI is typically negative)
            if cfo:
                entry["opfcf"] = round(cfo + cfi, 2)

            years_data.append(entry)

        return {
            "is_telecom": True,
            "sub_type": sub_type,
            "years": years_data,
            "current_ev_ebitda": valuation.get("ev_ebitda"),
        }

    # --- Light Sector Metrics (IT, FMCG) ---

    def get_sector_health_metrics(self, symbol: str) -> dict:
        """Compute sector-specific health metrics for IT (DSO trend) and FMCG (working capital trend).

        Returns computable signals that the prompt caveats reference,
        so agents get data, not just guidance.
        """
        industry = self._get_industry(symbol)
        annual = self.get_annual_financials(symbol, years=5)
        if not annual or len(annual) < 2:
            return {"skipped": True, "reason": "Insufficient annual data"}

        _IT = {"Computers - Software & Consulting", "IT Enabled Services", "Software Products",
               "Business Process Outsourcing (BPO)/ Knowledge Process Outsourcing (KPO)"}
        _FMCG = {"Diversified FMCG", "Household Products", "Personal Care",
                 "Packaged Foods", "Other Food Products", "Household Appliances"}

        if industry in _IT:
            dso_values = []
            for row in annual:
                recv = row.get("receivables", 0) or 0
                rev = row.get("revenue", 0) or 0
                if rev > 0:
                    dso_values.append({"fiscal_year": row.get("fiscal_year_end", ""),
                                       "dso_days": round(recv / rev * 365, 1)})
            if len(dso_values) >= 2:
                latest = dso_values[0]["dso_days"]
                prev = dso_values[1]["dso_days"]
                change = round(latest - prev, 1)
                flag = "WARNING: DSO rising" if change > 5 else "stable" if abs(change) <= 5 else "improving"
                return {"sector": "it", "dso_trend": dso_values, "dso_yoy_change": change, "signal": flag}
            return {"sector": "it", "dso_trend": dso_values}

        if industry in _FMCG:
            wc_values = []
            for row in annual:
                recv = row.get("receivables", 0) or 0
                inv = row.get("inventory", 0) or 0
                rev = row.get("revenue", 0) or 0
                # payables not a direct field — approximate from other_liabilities
                payables = row.get("other_liabilities", 0) or 0
                if rev > 0:
                    recv_days = round(recv / rev * 365, 1)
                    inv_days = round(inv / rev * 365, 1)
                    pay_days = round(payables / rev * 365, 1)
                    nwc_days = round(recv_days + inv_days - pay_days, 1)
                    wc_values.append({"fiscal_year": row.get("fiscal_year_end", ""),
                                      "receivable_days": recv_days, "inventory_days": inv_days,
                                      "payable_days": pay_days, "nwc_days": nwc_days})
            if len(wc_values) >= 2:
                latest = wc_values[0]["nwc_days"]
                prev = wc_values[1]["nwc_days"]
                change = round(latest - prev, 1)
                negative_wc = latest < 0
                flag = "negative WC advantage intact" if negative_wc else "positive WC"
                if change > 5:
                    flag += " — WARNING: WC deteriorating"
                return {"sector": "fmcg", "wc_trend": wc_values, "nwc_yoy_change": change, "signal": flag}
            return {"sector": "fmcg", "wc_trend": wc_values}

        return {"skipped": True, "reason": f"No light metrics for industry: {industry}"}

    # --- Subsidiary Contribution (Consolidated - Standalone) for SOTP ---

    def get_subsidiary_contribution(self, symbol: str) -> dict:
        """Compute subsidiary profit contribution: consolidated - standalone financials.

        Returns per-year breakdown of subsidiary revenue and profit contribution.
        For SOTP: tells the agent how much profit comes from subsidiaries.
        """
        consolidated = self.get_annual_financials(symbol, years=5)
        standalone = self._store.get_standalone_financials(symbol.upper(), limit=5)

        if not consolidated:
            return {"available": False, "reason": "No consolidated financials"}
        if not standalone:
            return {"available": False, "reason": "No standalone financials — fetch standalone data first"}

        # Build lookup by fiscal year
        sa_by_year = {r["fiscal_year_end"]: r for r in standalone}

        years = []
        for c in consolidated:
            fy = c.get("fiscal_year_end", "")
            sa = sa_by_year.get(fy)
            if not sa:
                continue

            c_rev = c.get("revenue", 0) or 0
            s_rev = sa.get("revenue", 0) or 0
            c_ni = c.get("net_income", 0) or 0
            s_ni = sa.get("net_income", 0) or 0

            sub_rev = round(c_rev - s_rev, 2)
            sub_ni = round(c_ni - s_ni, 2)
            sub_pct = round(sub_ni / c_ni * 100, 1) if c_ni else None

            years.append({
                "fiscal_year": fy,
                "consolidated_net_income": round(c_ni, 2),
                "standalone_net_income": round(s_ni, 2),
                "subsidiary_net_income": sub_ni,
                "subsidiary_profit_pct": sub_pct,
                "consolidated_revenue": round(c_rev, 2),
                "standalone_revenue": round(s_rev, 2),
                "subsidiary_revenue": sub_rev,
            })

        if not years:
            return {"available": False, "reason": "No overlapping fiscal years between consolidated and standalone"}

        return {
            "available": True,
            "years": years,
            "note": "subsidiary_net_income = consolidated - standalone. Apply peer multiples to estimate subsidiary value for SOTP.",
        }

    def get_power_metrics(self, symbol: str) -> dict:
        """Power/Utility-specific metrics: dividend yield vs G-sec spread, justified P/B."""
        if not self._is_regulated_power(symbol) and not self._is_merchant_power(symbol):
            return {"skipped": True, "reason": f"{symbol} is not a power/utility stock"}

        valuation = self.get_valuation_snapshot(symbol)
        macro = self.get_macro_snapshot()

        dividend_yield = valuation.get("dividend_yield")  # %
        pb_ratio = valuation.get("pb_ratio")
        roe = valuation.get("roe")  # %
        gsec_yield = macro.get("gsec_10y")  # yield %
        gsec_date = macro.get("date")  # "YYYY-MM-DD"

        sub_type = "regulated" if self._is_regulated_power(symbol) else "merchant"

        result: dict = {"is_power": True, "sub_type": sub_type}

        if dividend_yield is not None:
            result["dividend_yield"] = dividend_yield
        if gsec_yield is not None:
            result["gsec_yield"] = gsec_yield
            result["gsec_as_of"] = gsec_date
        if dividend_yield is not None and gsec_yield is not None:
            result["div_yield_spread"] = round(dividend_yield - gsec_yield, 2)

        # Justified P/B = ROE / Cost of Equity
        # CoE approximated as G-sec yield + 5% equity risk premium
        if roe is not None and gsec_yield is not None:
            cost_of_equity = gsec_yield + 5.0  # %
            if cost_of_equity > 0:
                result["justified_pb"] = round((roe / cost_of_equity), 2)
            result["roe"] = roe

        if pb_ratio is not None:
            result["actual_pb"] = pb_ratio

        return result

    def get_quality_scores_all(self, symbol: str) -> dict:
        """Aggregate all quality score metrics with sector-aware routing.

        Routing priority: insurance > BFSI > general.
        Sector-specific metrics (metals, realestate, telecom, power) are additive.
        """
        bfsi = self._is_bfsi(symbol)
        insurance = self._is_insurance(symbol)
        sector = self.get_sector_type(symbol)
        result: dict = {"is_bfsi": bfsi, "is_insurance": insurance, "sector_type": sector}

        # Always included
        result["piotroski"] = self.get_piotroski_score(symbol)
        result["dupont"] = self.get_dupont_decomposition(symbol)
        result["common_size"] = self.get_common_size_pl(symbol)
        result["improvement_metrics"] = self.get_improvement_metrics(symbol)
        result["operating_leverage"] = self.get_operating_leverage(symbol)
        result["fcf_yield"] = self.get_fcf_yield(symbol)
        result["tax_rate_analysis"] = self.get_tax_rate_analysis(symbol)

        _skip_financial = {
            "skipped": True,
            "reason": "not applicable for financial companies",
        }

        if insurance:
            result["insurance"] = self.get_insurance_metrics(symbol)
            result["bfsi"] = {"skipped": True, "reason": "insurance uses dedicated metrics"}
            result["earnings_quality"] = _skip_financial
            result["beneish"] = _skip_financial
            result["capex_cycle"] = _skip_financial
            result["incremental_roce"] = _skip_financial
            result["altman_zscore"] = _skip_financial
            result["working_capital"] = _skip_financial
            result["receivables_quality"] = _skip_financial
        elif bfsi:
            result["bfsi"] = self.get_bfsi_metrics(symbol)
            result["earnings_quality"] = _skip_financial
            result["beneish"] = _skip_financial
            result["capex_cycle"] = {
                "skipped": True,
                "reason": "BFSI has no CWIP/capex cycle",
            }
            result["incremental_roce"] = _skip_financial
            result["altman_zscore"] = _skip_financial
            result["working_capital"] = _skip_financial
            result["receivables_quality"] = _skip_financial
        else:
            result["earnings_quality"] = self.get_earnings_quality(symbol)
            result["beneish"] = self.get_beneish_score(symbol)
            result["capex_cycle"] = self.get_capex_cycle(symbol)
            result["forensic_checks"] = self.get_forensic_checks(symbol)
            result["capital_discipline"] = self.get_capital_discipline(symbol)
            result["bfsi"] = {"skipped": True, "reason": "non-BFSI company"}
            result["incremental_roce"] = self.get_incremental_roce(symbol)
            result["altman_zscore"] = self.get_altman_zscore(symbol)
            result["working_capital"] = self.get_working_capital_deterioration(symbol)
            result["receivables_quality"] = self.get_receivables_quality(symbol)

        # Additive sector metrics — included alongside standard metrics
        result["metals"] = self.get_metals_metrics(symbol)
        result["realestate"] = self.get_realestate_metrics(symbol)
        result["telecom"] = self.get_telecom_metrics(symbol)
        result["power"] = self.get_power_metrics(symbol)
        result["sector_health"] = self.get_sector_health_metrics(symbol)
        result["subsidiary"] = self.get_subsidiary_contribution(symbol)
        result["risk_flags"] = self.get_risk_flags(symbol)

        return result

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

    # --- News ---

    _NEWS_NOISE_PATTERNS = [
        "stocks to watch", "share price today", "top picks", "market update",
        "stocks to buy", "multibagger", "best stocks", "portfolio picks",
        "stock market today", "intraday", "short term target",
        "stocks in focus", "market cap of", "penny stocks",
        "stocks under", "stocks for", "shares to buy",
    ]

    _LISTICLE_RE = re.compile(r"^\d+\s+(stocks?|picks?|shares?|companies)\b", re.IGNORECASE)

    def get_stock_news(self, symbol: str, days: int = 90) -> list[dict]:
        """Fetch recent news from Google News RSS + yfinance. Filters noise, deduplicates.

        This is the only method that fetches live HTTP (not from SQLite).
        Returns list of dicts sorted by date descending:
          {"title", "source", "date", "url", "summary", "provider"}
        """
        symbol = symbol.upper()
        info = self.get_company_info(symbol)
        company_name = info.get("company_name", symbol)

        articles: list[dict] = []

        # --- Google News RSS ---
        try:
            articles.extend(self._fetch_google_news(company_name, symbol, days))
        except Exception as exc:
            logger.warning("Google News fetch failed for %s: %s", symbol, exc)

        # --- yfinance news ---
        try:
            articles.extend(self._fetch_yfinance_news(symbol))
        except Exception as exc:
            logger.warning("yfinance news fetch failed for %s: %s", symbol, exc)

        # Deduplicate
        articles = self._deduplicate_news(articles)

        # Filter noise
        articles = [a for a in articles if not self._is_news_noise(a["title"])]

        # Filter by date range
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        articles = [a for a in articles if a.get("date", "") >= cutoff]

        # Sort by date descending
        articles.sort(key=lambda a: a.get("date", ""), reverse=True)

        return articles

    def _fetch_google_news(self, company_name: str, symbol: str, days: int) -> list[dict]:
        """Fetch from Google News RSS. Returns raw article dicts."""
        import urllib.parse

        query = urllib.parse.quote(f"{company_name} {symbol} stock India")
        url = (
            f"https://news.google.com/rss/search?"
            f"q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")

        results = []
        for item in items:
            title_el = item.find("title")
            source_el = item.find("source")
            pub_el = item.find("pubDate")
            link_el = item.find("link")

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            if not title:
                continue

            # Parse RFC 2822 date from RSS
            date_str = ""
            if pub_el is not None and pub_el.text:
                try:
                    dt = parsedate_to_datetime(pub_el.text)
                    date_str = dt.date().isoformat()
                except Exception:
                    pass

            results.append({
                "title": title,
                "source": source_el.text.strip() if source_el is not None and source_el.text else "Google News",
                "date": date_str,
                "url": link_el.text.strip() if link_el is not None and link_el.text else "",
                "summary": None,
                "provider": "google_rss",
            })

        return results

    def _fetch_yfinance_news(self, symbol: str) -> list[dict]:
        """Fetch from yfinance .news property. Returns raw article dicts."""
        import yfinance as yf

        ticker = yf.Ticker(f"{symbol}.NS")
        news = ticker.news or []

        results = []
        for item in news:
            content = item.get("content", item)
            title = content.get("title", "")
            if not title:
                continue

            # Parse date
            date_str = ""
            pub = content.get("pubDate") or content.get("providerPublishTime")
            if pub:
                try:
                    if isinstance(pub, (int, float)):
                        date_str = datetime.fromtimestamp(pub, tz=timezone.utc).date().isoformat()
                    else:
                        date_str = pub[:10]  # ISO prefix
                except Exception:
                    pass

            # Extract URL
            url = ""
            canon = content.get("canonicalUrl") or content.get("clickThroughUrl")
            if isinstance(canon, dict):
                url = canon.get("url", "")
            elif isinstance(canon, str):
                url = canon

            provider = content.get("provider", {})
            source = provider.get("displayName", "Yahoo Finance") if isinstance(provider, dict) else "Yahoo Finance"

            results.append({
                "title": title.strip(),
                "source": source,
                "date": date_str,
                "url": url,
                "summary": content.get("summary", None),
                "provider": "yfinance",
            })

        return results

    def _is_news_noise(self, title: str) -> bool:
        """Check if a title is market commentary noise rather than a business event."""
        lower = title.lower()
        for pattern in self._NEWS_NOISE_PATTERNS:
            if pattern in lower:
                return True
        if self._LISTICLE_RE.match(title):
            return True
        return False

    @staticmethod
    def _deduplicate_news(articles: list[dict]) -> list[dict]:
        """Deduplicate articles by title word overlap (>70% = duplicate)."""
        seen: list[set[str]] = []
        unique: list[dict] = []

        for article in articles:
            words = set(re.sub(r"[^\w\s]", "", article["title"].lower()).split())
            if not words:
                continue

            is_dup = False
            for seen_words in seen:
                overlap = len(words & seen_words)
                max_len = max(len(words), len(seen_words))
                if max_len > 0 and overlap / max_len > 0.7:
                    is_dup = True
                    break

            if not is_dup:
                seen.append(words)
                unique.append(article)

        return unique
