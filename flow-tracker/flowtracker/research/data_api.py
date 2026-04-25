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

    def __init__(self, store: FlowStore | None = None):
        if store is not None:
            self._store = store
            self._owns_store = False
        else:
            self._store = FlowStore()
            self._store.__enter__()
            self._owns_store = True

    def close(self):
        if self._owns_store:
            self._store.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # --- Historical Analog Agent ---

    @staticmethod
    def _default_as_of(as_of_date: str | None) -> str:
        """Resolve a caller-omitted as_of_date.

        Honors ``FLOWTRACK_AS_OF=YYYY-MM-DD`` when set (backtest hook) so
        tool calls that don't pass an explicit date still run against the
        historical sample's as-of, not wall-clock.
        """
        import os
        from datetime import date
        if as_of_date is not None:
            return as_of_date
        env_val = os.environ.get("FLOWTRACK_AS_OF")
        if env_val:
            try:
                date.fromisoformat(env_val)
                return env_val
            except ValueError:
                pass
        return date.today().isoformat()

    def get_setup_feature_vector(self, symbol: str, as_of_date: str | None = None) -> dict:
        """Return the 16-feature fingerprint for (symbol, as_of_date).

        Used by the Historical Analog Agent to inspect the target setup.
        Default as_of_date = today (or FLOWTRACK_AS_OF env var). Strict
        temporal cutoff — every input filtered to date <= as_of_date to
        prevent data leakage.
        """
        from flowtracker.research.analog_builder import compute_feature_vector
        as_of_date = self._default_as_of(as_of_date)
        return compute_feature_vector(self._store, symbol, as_of_date)

    def get_historical_analogs(
        self, symbol: str, k: int = 20, as_of_date: str | None = None,
    ) -> dict:
        """Retrieve top-K historical analogs for `symbol`'s current setup.

        Each analog has: (symbol, quarter_end), feature vector, z-scored
        distance, forward returns (3m/6m/12m absolute + vs sector/nifty),
        outcome label (recovered / sideways / blew_up). Hard-filtered to
        same industry + same mcap bucket; excludes target's own rows
        within 2 years (leakage guard).
        """
        from flowtracker.research.analog_builder import (
            compute_feature_vector, retrieve_top_k_analogs,
        )
        as_of_date = self._default_as_of(as_of_date)
        target_vec = compute_feature_vector(self._store, symbol, as_of_date)
        retrieval = retrieve_top_k_analogs(
            self._store, target_symbol=symbol, target_date=as_of_date,
            target_features=target_vec, k=k,
        )
        analogs = retrieval["analogs"]
        return {
            "symbol": symbol.upper(),
            "as_of_date": as_of_date,
            "target_features": target_vec,
            "analog_count": len(analogs),
            "analogs": analogs,
            "relaxation_level": retrieval["relaxation_level"],
            "relaxation_label": retrieval["relaxation_label"],
            "unique_symbols": retrieval["unique_symbols"],
            "gross_count": retrieval["gross_count"],
        }

    def get_analog_cohort_stats(
        self, symbol: str, k: int = 50, as_of_date: str | None = None,
    ) -> dict:
        """Aggregate base rates across the analog cohort (recovery rate,
        median 12m return, blow-up rate, p10/p90 tails). Larger K gives a
        richer cohort for statistics; default 50 vs 20 for the detailed list.
        """
        from flowtracker.research.analog_builder import cohort_stats
        result = self.get_historical_analogs(symbol, k=k, as_of_date=as_of_date)
        stats = cohort_stats(result["analogs"])
        result["cohort_stats"] = stats
        return result

    # --- Adjusted close (computed path, independent of stored adj_close column) ---

    def get_adjusted_close_series(
        self,
        symbol: str,
        from_date: str,
        to_date: str,
    ) -> list[tuple[str, float]]:
        """Return [(date, adjusted_close)] computed dynamically from raw close
        + corporate_actions, with the same price-cliff verification used by
        FlowStore.recompute_adj_close.

        Independent of daily_stock_data.adj_close — used for drift verification
        against the stored path and for ad-hoc what-if queries. Must produce
        identical output to the stored path (the drift sweep asserts this).
        """
        symbol = symbol.upper()
        rows = self._store._conn.execute(
            "SELECT date, close FROM daily_stock_data "
            "WHERE symbol = ? AND date BETWEEN ? AND ? ORDER BY date",
            (symbol, from_date, to_date),
        ).fetchall()
        if not rows:
            return []

        raw_actions = [
            a for a in self._store.get_split_bonus_actions(symbol)
            if a.get("multiplier")
        ]

        # Group by ex_date, compose combined multiplier, then verify each
        # date's combined multiplier against the observed price cliff. Same
        # tolerance as recompute_adj_close (see docstring there).
        from collections import defaultdict
        per_date: dict[str, float] = defaultdict(lambda: 1.0)
        for a in raw_actions:
            per_date[a["ex_date"]] *= a["multiplier"]

        verified: list[tuple[str, float]] = []
        conn = self._store._conn
        for ex_date, composed_mult in per_date.items():
            px = conn.execute(
                "SELECT close, prev_close FROM daily_stock_data "
                "WHERE symbol = ? AND date = ?",
                (symbol, ex_date),
            ).fetchone()
            if px and px["close"] and px["prev_close"] and px["prev_close"] > 0:
                observed_ratio = px["close"] / px["prev_close"]
                expected_ratio = 1.0 / composed_mult
                # Mirror the recompute_adj_close verification rules exactly.
                if composed_mult > 1.0 and observed_ratio > 0.85:
                    continue
                if composed_mult < 1.0 and observed_ratio < 1.15:
                    continue
                if abs(observed_ratio - expected_ratio) > 0.3 * expected_ratio:
                    continue
            verified.append((ex_date, composed_mult))

        verified_desc = sorted(verified, key=lambda a: a[0], reverse=True)

        result: list[tuple[str, float]] = []
        for row in rows:
            date = row["date"]
            close = row["close"]
            factor = 1.0
            for ex_date, mult in verified_desc:
                if ex_date > date:
                    factor *= mult
                else:
                    break
            result.append((date, close / factor if factor else close))
        return result

    # --- SOTP: Listed Subsidiaries ---

    def _is_recently_listed(self, sub_symbol: str, days: int = 180) -> tuple[bool, str | None]:
        """Detect recently-listed Indian equities via daily_stock_data earliest date.

        Plan v2 §7 E10: cross-check SOTP subsidiaries against listings within the
        last `days`. Returns (is_recent, earliest_date_str).

        A symbol is considered "recently listed" if its earliest row in
        daily_stock_data is within the last `days`. Falls back to (False, None)
        if no bhavcopy history exists (e.g. sub not tracked in NSE bhavcopy feed).
        """
        row = self._store._conn.execute(
            "SELECT MIN(date) AS first_date FROM daily_stock_data WHERE symbol = ?",
            (sub_symbol.upper(),),
        ).fetchone()
        if not row or not row["first_date"]:
            return False, None
        from datetime import date, timedelta
        try:
            first_dt = datetime.strptime(row["first_date"], "%Y-%m-%d").date()
        except Exception:
            return False, None
        cutoff = date.today() - timedelta(days=days)
        return first_dt >= cutoff, row["first_date"]

    # --- SOTP: Auto-Discovery (PR-14) ---

    _SOTP_SUFFIX_PAT = re.compile(
        r"\s+(limited|ltd|pvt|private|company|corp|corporation)\s*$"
    )

    @staticmethod
    def _clean_company_name(name: str) -> str:
        """Normalize for substring matching: strip suffixes (LIMITED/LTD/PVT/...), lowercase."""
        if not name:
            return ""
        s = re.sub(r"[.,]+", " ", name.strip().lower())
        prev = None
        while prev != s:
            prev = s
            s = ResearchDataAPI._SOTP_SUFFIX_PAT.sub("", s).strip()
        return re.sub(r"\s+", " ", s)

    def _discover_recent_listings(self, days: int = 180) -> list[dict]:
        """Symbols whose earliest daily_stock_data row is within the last `days` (cap 540)."""
        days = max(1, min(int(days), 540))
        rows = self._store._conn.execute(
            "SELECT symbol, MIN(date) AS listed_on, COUNT(*) AS observations "
            "FROM daily_stock_data GROUP BY symbol "
            "HAVING listed_on >= DATE('now', '-' || ? || ' days') "
            "ORDER BY listed_on DESC",
            (days,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _find_promoter_owned_children(
        self, parent_symbol: str, candidate_symbols: list[str], min_pct: float = 50.0,
    ) -> list[dict]:
        """Latest-quarter promoter rows whose holder_name contains parent name (>= min_pct)."""
        parent_key = self._clean_company_name(
            self.get_company_info(parent_symbol).get("company_name", "") or ""
        )
        if not parent_key:
            return []
        conn = self._store._conn
        hits: list[dict] = []
        for sym in candidate_symbols:
            sym_u = sym.upper()
            qrow = conn.execute(
                "SELECT MAX(quarter) AS q FROM shareholder_detail "
                "WHERE symbol = ? AND classification LIKE 'Promoter%'",
                (sym_u,),
            ).fetchone()
            if not qrow or not qrow["q"]:
                logger.debug("auto_discovery: no named promoter rows for %s", sym_u)
                continue
            last_q = qrow["q"]
            for pr in conn.execute(
                "SELECT holder_name, percentage FROM shareholder_detail "
                "WHERE symbol = ? AND classification LIKE 'Promoter%' AND quarter = ?",
                (sym_u, last_q),
            ).fetchall():
                pct = pr["percentage"] or 0.0
                if parent_key in self._clean_company_name(pr["holder_name"] or "") and pct >= min_pct:
                    hits.append({
                        "symbol": sym_u,
                        "parent_ownership_pct": round(float(pct), 2),
                        "promoter_name": pr["holder_name"],
                        "last_quarter": last_q,
                    })
                    break
        return hits

    def get_listed_subsidiaries(self, symbol: str) -> dict | list[dict] | None:
        """Get listed subsidiary valuations for SOTP analysis.

        Reads curated parent→subsidiary mappings, fetches live market caps,
        and computes per-share value to the parent. PR-14 augments with
        `auto_discovered_candidates` — recently-listed symbols whose latest
        promoter row names this parent (substring match, >=50% holding).
        Returns None only when both curated and auto-discovery yield nothing.
        """
        subs = self._store.get_listed_subsidiaries(symbol)

        # Always run auto-discovery so recently-listed children surface
        # even when no curated mapping exists yet.
        auto_window_days = 180
        recent = self._discover_recent_listings(days=auto_window_days)
        curated_subsymbols = {s["sub_symbol"].upper() for s in subs}
        candidate_syms = [
            r["symbol"] for r in recent if r["symbol"].upper() not in curated_subsymbols
        ]
        recent_idx = {r["symbol"]: r for r in recent}
        auto_discovered = [
            {
                "subsidiary": h["symbol"],
                "symbol": h["symbol"],
                "parent_ownership_pct": h["parent_ownership_pct"],
                "promoter_name": h["promoter_name"],
                "listed_on": recent_idx.get(h["symbol"], {}).get("listed_on"),
                "last_quarter": h["last_quarter"],
                "confidence": "auto_discovered_needs_verification",
            }
            for h in self._find_promoter_owned_children(symbol, candidate_syms)
        ]

        def _auto_only_payload() -> dict:
            return {
                "subsidiaries": [],
                "subsidiaries_listed_recently": [],
                "auto_discovered_candidates": auto_discovered,
                "_meta": {
                    "freshness_check": "bhavcopy_earliest_date",
                    "freshness_window_days": auto_window_days,
                    "auto_discovery_window_days": auto_window_days,
                },
            }

        if not subs:
            return _auto_only_payload() if auto_discovered else None

        import yfinance as yf
        parent_shares = self.get_valuation_snapshot(symbol).get("shares_outstanding", 0)
        if not parent_shares:
            # Curated rows can't be priced — surface auto-discovery if any.
            return _auto_only_payload() if auto_discovered else None

        recently_listed: list[str] = []
        results = []
        for row in subs:
            sub_sym = row["sub_symbol"]
            is_recent, first_date = self._is_recently_listed(sub_sym, days=180)
            try:
                t = yf.Ticker(f"{sub_sym}.NS")
                sub_mcap = t.info.get("marketCap", 0) or 0
                sub_mcap_cr = (sub_mcap / 1e7) if sub_mcap else None
                ownership = row["parent_ownership_pct"]
                parent_stake_cr = (sub_mcap_cr or 0) * (ownership / 100) if sub_mcap_cr else None
                per_share_value = (
                    (parent_stake_cr * 1e7) / parent_shares
                    if parent_stake_cr and parent_shares
                    else None
                )
                entry = {
                    "subsidiary": row["sub_name"],
                    "symbol": sub_sym,
                    "parent_ownership_pct": ownership,
                    "relationship": row.get("relationship", ""),
                    "subsidiary_market_cap_cr": round(sub_mcap_cr) if sub_mcap_cr else None,
                    "parent_stake_value_cr": round(parent_stake_cr) if parent_stake_cr else None,
                    "per_share_value": round(per_share_value, 2) if per_share_value else None,
                }
                if is_recent:
                    entry["recently_listed"] = True
                    entry["listed_on"] = first_date
                    recently_listed.append(row["sub_name"])
                if sub_mcap_cr is None:
                    entry["needs_refresh"] = True
                results.append(entry)
            except Exception:
                # Still surface the row so agents see the subsidiary even if yf failed.
                entry = {
                    "subsidiary": row["sub_name"],
                    "symbol": sub_sym,
                    "parent_ownership_pct": row["parent_ownership_pct"],
                    "relationship": row.get("relationship", ""),
                    "subsidiary_market_cap_cr": None,
                    "parent_stake_value_cr": None,
                    "per_share_value": None,
                    "needs_refresh": True,
                }
                if is_recent:
                    entry["recently_listed"] = True
                    entry["listed_on"] = first_date
                    recently_listed.append(row["sub_name"])
                results.append(entry)

        if not results:
            return None

        return {
            "subsidiaries": results,
            "subsidiaries_listed_recently": recently_listed,
            "auto_discovered_candidates": auto_discovered,
            "_meta": {
                "freshness_check": (
                    "bhavcopy_earliest_date"
                    if self._store._conn.execute(
                        "SELECT 1 FROM daily_stock_data LIMIT 1"
                    ).fetchone()
                    else "unavailable"
                ),
                "freshness_window_days": 180,
                "auto_discovery_window_days": auto_window_days,
            },
        }

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

    def get_data_quality_flags(
        self, symbol: str, min_severity: str = "MEDIUM"
    ) -> list[dict]:
        """Reclassification flags for `annual_financials` — see flowtracker.data_quality
        and plans/screener-data-discontinuity.md.

        Each flag marks a YoY break (prior_fy → curr_fy) on a specific line
        where Screener's bucketing changed (Schedule III, Ind-AS 116 leases,
        merger/demerger). Multi-year ratios that span a flagged boundary are
        corrupt — agents should narrow their window or narrate the break.

        min_severity: 'LOW' returns everything; 'MEDIUM' filters out the noisy
        100-200% band; 'HIGH' returns only sign flips and >500% jumps.
        """
        return self._store.get_data_quality_flags(symbol, min_severity=min_severity)

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

    def _detect_pe_basis(self, symbol: str) -> str:
        """Return 'standalone' if Screener PE chart exists (Screener PE = standalone for most
        Indian companies), else 'consolidated' (yfinance valuation_snapshot PE), else 'unknown'.

        Plan v2 §7 E11: expose PE/EPS basis so agents can flag standalone/consolidated
        mismatches when PE band and EPS projection are sourced from different bases.
        """
        # Screener charts — chart_type='pe'
        has_chart = self._store._conn.execute(
            "SELECT 1 FROM screener_charts "
            "WHERE symbol = ? AND chart_type = 'pe' AND metric = 'Price to Earning' "
            "LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if has_chart:
            return "standalone"
        has_snap = self._store._conn.execute(
            "SELECT 1 FROM valuation_snapshot "
            "WHERE symbol = ? AND pe_trailing IS NOT NULL "
            "LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if has_snap:
            return "consolidated"
        return "unknown"

    def _detect_eps_basis(self, symbol: str) -> str:
        """EPS projection source — yfinance consensus (forward_eps) is consolidated.
        Screener/annual_financials EPS is standalone for most Indian companies.

        For the auto-blend path in get_fair_value, we use consensus forward_eps →
        'consolidated'. If only annual_financials EPS is available, returns 'standalone'.
        Plan v2 §7 E11.
        """
        est = self._store.get_estimate_latest(symbol)
        if est and est.forward_eps:
            return "consolidated"
        # Fallback: annual_financials (Screener) EPS
        annual = self._store.get_annual_financials(symbol, limit=1)
        if annual and annual[0].eps:
            return "standalone"
        return "unknown"

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
        # Plan v2 §7 E11: expose PE/EPS basis so agents detect standalone/consolidated
        # mismatches. pe_trailing + eps_ttm here come from yfinance → 'consolidated'.
        snap["pe_basis"] = "consolidated" if snap.get("pe_trailing") else "unknown"
        snap["eps_basis"] = "consolidated" if snap.get("eps_ttm") is not None else "unknown"
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

    def get_insider_transactions(
        self, symbol: str, days: int = 1825, top_n: int = 50,
    ) -> list[dict]:
        """SAST insider buy/sell trades with person name, category, value.

        Capped to top_n transactions by absolute value (default 50). For
        large-cap private banks with active ESOP vesting cycles, 5-year
        insider history can reach 10,000+ rows and 600K+ chars of JSON,
        which destroys the MCP tool-result transport. The remaining
        transactions are aggregated into a tail summary row with net
        buy/sell counts and net value.
        """
        rows = self._store.get_insider_by_symbol(symbol, days=days)
        dumped = _clean([r.model_dump() for r in rows])
        if top_n is None or len(dumped) <= top_n:
            return dumped
        # Rank by absolute value so the biggest transactions are preserved
        def abs_val(r: dict) -> float:
            return abs(float(r.get("value_cr") or r.get("value") or 0))
        sorted_rows = sorted(dumped, key=abs_val, reverse=True)
        kept = sorted_rows[:top_n]
        tail = sorted_rows[top_n:]
        buy_count = sum(
            1 for r in tail
            if (r.get("transaction_type") or "").lower() in ("buy", "market purchase", "purchase")
        )
        sell_count = sum(
            1 for r in tail
            if (r.get("transaction_type") or "").lower() in ("sell", "market sale", "sale")
        )
        tail_net_value = round(
            sum(
                (r.get("value_cr") or r.get("value") or 0)
                * (1 if (r.get("transaction_type") or "").lower() in ("buy", "market purchase", "purchase") else -1)
                for r in tail
            ),
            2,
        )
        kept.append({
            "_is_tail_summary": True,
            "summary": f"[TAIL — {len(tail)} smaller-value insider transactions combined]",
            "tail_buy_count": buy_count,
            "tail_sell_count": sell_count,
            "tail_net_value_cr": tail_net_value,
        })
        return kept

    def get_bulk_block_deals(self, symbol: str) -> list[dict]:
        """BSE bulk/block deals — large institutional trades."""
        rows = self._store.get_deals_by_symbol(symbol)
        return _clean([r.model_dump() for r in rows])

    def get_mf_holdings(self, symbol: str, top_n: int = 30) -> list[dict]:
        """MF scheme holdings — which schemes hold this stock, qty, % of NAV.

        Capped to top_n schemes by market_value_cr (default 30) to keep the
        MCP tool-result payload under the ~30KB truncation threshold. The full
        universe can have 100-200 schemes for large-cap banks, which produced
        80-150K char tool responses that got truncated mid-response, causing
        agents to hallucinate data gaps.

        The tail (schemes beyond top_n) is summarized into a final synthetic
        row with aggregate count + value so the agent has the full picture.
        """
        rows = self._store.get_mf_stock_holdings(symbol)
        dumped = _clean([r.model_dump() for r in rows])
        if top_n is None or len(dumped) <= top_n:
            return dumped
        # Sort by market_value_cr desc, keep top_n, summarize tail
        sorted_rows = sorted(
            dumped,
            key=lambda r: (r.get("market_value_cr") or 0),
            reverse=True,
        )
        kept = sorted_rows[:top_n]
        tail = sorted_rows[top_n:]
        tail_value = round(sum((r.get("market_value_cr") or 0) for r in tail), 2)
        tail_qty = sum((r.get("quantity") or 0) for r in tail)
        kept.append({
            "scheme_name": f"[TAIL — {len(tail)} additional schemes combined]",
            "amc": "MULTIPLE",
            "stock_name": symbol.upper(),
            "market_value_cr": tail_value,
            "quantity": tail_qty,
            "pct_of_nav": None,
            "_is_tail_summary": True,
        })
        return kept

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

        # Build lookup by scheme for previous month.
        # Match prev rows on the SAME stock_name/isin set the current month
        # produced — `get_mf_stock_holdings(symbol)` resolves NSE symbols
        # (e.g. HDFCBANK) to AMFI stock_names (e.g. "HDFC Bank Ltd.") via
        # index_constituents. Reusing `f"%{symbol}%"` here would silently
        # miss the prior month for any symbol whose AMFI name does not
        # contain the NSE ticker substring (HDFCBANK, TCS, SUNPHARMA, VEDL,
        # etc.), tagging every scheme as `new_entry` with prev_count=0.
        # Match on union of ISINs ∪ stock_names so an exited-scheme row that
        # historically carried a different ISIN (rare but seen in the wild)
        # still surfaces, while ISIN-matched rows handle the common case
        # where AMFI's stock_name does not contain the NSE ticker substring.
        isins = {r.isin for r in current if getattr(r, "isin", None)}
        stock_names = {r.stock_name for r in current if getattr(r, "stock_name", None)}
        clauses: list[str] = []
        params: list = []
        if isins:
            clauses.append(f"isin IN ({','.join('?' * len(isins))})")
            params.extend(isins)
        if stock_names:
            clauses.append(f"stock_name IN ({','.join('?' * len(stock_names))})")
            params.extend(stock_names)
        if clauses:
            params.append(prev_month)
            prev_rows = self._store._conn.execute(
                f"SELECT * FROM mf_scheme_holdings "
                f"WHERE ({' OR '.join(clauses)}) AND month = ? "
                f"ORDER BY market_value_cr DESC",
                params,
            ).fetchall()
        else:
            prev_rows = []
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
        # Cap at top 30 by |value_change| + tail summary. Full universe can
        # have 200+ schemes for large-cap BFSI names, producing 70K+ chars
        # that contribute to MCP tool-result truncation.
        top_n = 30
        if len(changes) > top_n:
            kept = changes[:top_n]
            tail = changes[top_n:]
            tail_net = round(sum((r.get("value_change_cr") or 0) for r in tail), 2)
            tail_new = sum(1 for r in tail if r.get("change_type") == "new_entry")
            tail_exited = sum(1 for r in tail if r.get("change_type") == "exited")
            tail_incr = sum(1 for r in tail if r.get("change_type") == "increased")
            tail_decr = sum(1 for r in tail if r.get("change_type") == "decreased")
            kept.append({
                "_is_tail_summary": True,
                "summary": f"[TAIL — {len(tail)} smaller MF scheme changes combined]",
                "tail_net_value_change_cr": tail_net,
                "tail_new_entries": tail_new,
                "tail_exits": tail_exited,
                "tail_increased": tail_incr,
                "tail_decreased": tail_decr,
            })
            changes = kept
        return _clean(changes)

    @staticmethod
    def _classify_scheme_type(scheme_name: str) -> str:
        """Classify an MF scheme as equity / debt / hybrid / other based on the name.

        AMFI scheme names follow recognisable conventions. A debt scheme holding
        this company's BONDS will appear in `mf_scheme_holdings` alongside
        equity schemes and — if we don't separate them — can materially distort
        "MF conviction" metrics. Example failure mode observed on ADANIENT
        (Gemini eval 2026-04-14): ICICI Prudential debt funds held Adani bonds
        and the agent reported them as equity conviction.

        Heuristic rules (broad matching, case-insensitive):
          debt: 'debt', 'gilt', 'liquid', 'overnight', 'treasury', 'credit risk',
                'banking psu', 'corporate bond', 'short term', 'dynamic bond',
                'money market', 'floater', 'income fund'
          hybrid: 'hybrid', 'balanced', 'asset allocator', 'multi asset', 'equity savings'
          equity: everything else (flexi, largecap, midcap, smallcap, focused,
                  value, dividend yield, sectoral, thematic, index/ETF)
        """
        if not scheme_name:
            return "unknown"
        s = scheme_name.lower()
        debt_markers = (
            "debt", "gilt", "liquid", "overnight", "treasury", "credit risk",
            "banking psu", "corporate bond", "short term", "short duration",
            "dynamic bond", "money market", "floater", "income fund",
            "medium duration", "low duration", "ultra short",
        )
        hybrid_markers = (
            "hybrid", "balanced", "asset allocator", "multi asset",
            "equity savings", "conservative", "aggressive allocation",
        )
        # Check hybrid FIRST — "Equity & Debt Fund" contains 'debt' but is hybrid.
        # Order: hybrid > debt > equity (default).
        if any(m in s for m in hybrid_markers):
            return "hybrid"
        if "equity" in s and "debt" in s:
            return "hybrid"  # catch-all for "Equity & Debt" style names
        if any(m in s for m in debt_markers):
            return "debt"
        return "equity"

    def get_mf_conviction(self, symbol: str) -> dict:
        """MF conviction breadth: how many schemes/AMCs hold and are adding this stock.

        Segregates equity vs debt vs hybrid schemes. Debt schemes holding a
        company's bonds should NOT be counted as equity conviction — confusing
        the two was flagged by Gemini on ADANIENT where ICICI debt funds
        appeared in the MF conviction narrative.

        Returns a structured dict with equity/debt/hybrid sub-breakdowns plus
        the legacy blended top-level fields (for backwards compatibility).
        """
        current = self._store.get_mf_stock_holdings(symbol)
        if not current:
            return {"available": False, "reason": "No MF holdings data"}

        # Segregate by scheme type
        by_type: dict[str, list] = {"equity": [], "debt": [], "hybrid": [], "unknown": []}
        for r in current:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            stype = self._classify_scheme_type(d.get("scheme_name", ""))
            by_type.setdefault(stype, []).append(d)

        # Top-level blended stats (preserve backwards compat)
        schemes: set[str] = set()
        amcs: set[str] = set()
        total_value = 0.0
        for r in current:
            d = r.model_dump() if hasattr(r, "model_dump") else r
            schemes.add(d.get("scheme_name", ""))
            amcs.add(d.get("amc", ""))
            total_value += d.get("market_value_cr") or 0

        # Previous month for trend (count distinct schemes)
        months = sorted(set(
            (r.month if hasattr(r, "month") else r.get("month", ""))
            for r in current
        ))
        curr_month = months[-1] if months else ""
        prev_count = 0
        if curr_month:
            y, m = int(curr_month[:4]), int(curr_month[5:7])
            prev_month = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
            # Match prev-month on the resolved isin/stock_name from `current`
            # (not `f"%{symbol}%"`) — see get_mf_holding_changes for rationale.
            # Using the LIKE on the raw NSE ticker silently returned 0 for
            # HDFCBANK / TCS / SUNPHARMA / VEDL whose AMFI stock_names don't
            # contain the ticker substring.
            isins = {
                (r.isin if hasattr(r, "isin") else r.get("isin"))
                for r in current
                if (r.isin if hasattr(r, "isin") else r.get("isin"))
            }
            stock_names = {
                (r.stock_name if hasattr(r, "stock_name") else r.get("stock_name"))
                for r in current
                if (r.stock_name if hasattr(r, "stock_name") else r.get("stock_name"))
            }
            clauses: list[str] = []
            params: list = []
            if isins:
                clauses.append(f"isin IN ({','.join('?' * len(isins))})")
                params.extend(isins)
            if stock_names:
                clauses.append(f"stock_name IN ({','.join('?' * len(stock_names))})")
                params.extend(stock_names)
            if clauses:
                params.append(prev_month)
                prev_rows = self._store._conn.execute(
                    f"SELECT COUNT(DISTINCT scheme_name) as cnt FROM mf_scheme_holdings "
                    f"WHERE ({' OR '.join(clauses)}) AND month = ?",
                    params,
                ).fetchone()
            else:
                prev_rows = None
            prev_count = prev_rows[0] if prev_rows else 0

        scheme_count = len(schemes)
        trend = "adding" if scheme_count > prev_count else "trimming" if scheme_count < prev_count else "stable"

        # Top 10 equity schemes (the metric that matters for ownership analysis)
        equity_holdings = by_type.get("equity", [])
        sorted_equity = sorted(
            equity_holdings,
            key=lambda d: (d.get("market_value_cr") or 0),
            reverse=True,
        )
        top_equity_schemes = [
            {
                "scheme": d.get("scheme_name", ""),
                "amc": d.get("amc", ""),
                "value_cr": round(d.get("market_value_cr") or 0, 2),
                "pct_of_nav": d.get("pct_of_nav"),
                "scheme_type": "equity",
            }
            for d in sorted_equity[:10]
        ]

        # Compact per-type breakdown (value + count)
        def _agg(rows: list) -> dict:
            if not rows:
                return {"scheme_count": 0, "amc_count": 0, "total_value_cr": 0.0}
            s, a = set(), set()
            total = 0.0
            for d in rows:
                s.add(d.get("scheme_name", ""))
                a.add(d.get("amc", ""))
                total += d.get("market_value_cr") or 0
            return {
                "scheme_count": len(s),
                "amc_count": len(a),
                "total_value_cr": round(total, 2),
            }

        by_type_summary = {
            "equity": _agg(by_type.get("equity", [])),
            "debt": _agg(by_type.get("debt", [])),
            "hybrid": _agg(by_type.get("hybrid", [])),
            "unknown": _agg(by_type.get("unknown", [])),
        }

        # Top 3 debt schemes separately — named explicitly so the agent can
        # cite them as debt (bond) holdings rather than equity conviction
        debt_holdings = by_type.get("debt", [])
        sorted_debt = sorted(
            debt_holdings,
            key=lambda d: (d.get("market_value_cr") or 0),
            reverse=True,
        )[:3]
        top_debt_schemes = [
            {
                "scheme": d.get("scheme_name", ""),
                "amc": d.get("amc", ""),
                "value_cr": round(d.get("market_value_cr") or 0, 2),
                "note": "DEBT scheme — likely holds bonds, NOT equity conviction",
            }
            for d in sorted_debt
        ]

        return {
            "available": True,
            "month": curr_month,
            # Legacy blended totals (backwards compat)
            "schemes_holding": scheme_count,
            "amcs_holding": len(amcs),
            "total_mf_value_cr": round(total_value, 2),
            "prev_month_schemes": prev_count,
            "scheme_trend": trend,
            "scheme_change": scheme_count - prev_count,
            # NEW: segregated by scheme type
            "by_scheme_type": by_type_summary,
            "top_equity_schemes": top_equity_schemes,
            "top_debt_schemes_if_any": top_debt_schemes,
            # Legacy field — now equivalent to top_equity_schemes for backwards compat
            "top_schemes": top_equity_schemes,
            "_note": (
                "Equity conviction = by_scheme_type.equity fields + top_equity_schemes. "
                "DO NOT cite debt schemes (by_scheme_type.debt or top_debt_schemes_if_any) "
                "as equity ownership — those holders bought bonds, not shares."
            ),
        }

    def get_peer_sector_toc(self, symbol: str) -> dict:
        """Compact TOC for get_peer_sector — ~1-2 KB static section menu + waves.

        Default response when the agent calls get_peer_sector with no section.
        Lists all 9 sections + 3 recommended wave compositions so the agent
        can plan drills without triggering the MCP-truncation failure mode
        that hit get_fundamentals(section='all') and get_ownership(section='all').
        """
        sections = [
            {"key": "peer_table",         "size": "med",   "purpose": "CMP, P/E, MCap, ROCE%, growth for peers of this stock — quick comparison"},
            {"key": "peer_metrics",       "size": "med",   "purpose": "Fuller metric dict per peer (margins, turns, leverage)"},
            {"key": "peer_growth",        "size": "small", "purpose": "1Y/3Y/5Y revenue, PAT, EPS growth per peer"},
            {"key": "valuation_matrix",   "size": "med",   "purpose": "Multi-metric valuation comparison (PE/PB/EV-EBITDA/EV-Sales) with sector medians + percentile rank"},
            {"key": "benchmarks",         "size": "small", "purpose": "Sector median + percentile rank for a single chosen metric (pass metric= arg)"},
            {"key": "sector_overview",    "size": "small", "purpose": "Sector aggregate stats — TAM proxy, stock count, size tiers"},
            {"key": "sector_flows",       "size": "small", "purpose": "Sector-level FII/DII flow direction + momentum"},
            {"key": "sector_valuations",  "size": "small", "purpose": "Sector-wide valuation percentile vs own history"},
            {"key": "yahoo_peers",        "size": "small", "purpose": "Yahoo-sourced peer set (supplements Screener peers)"},
        ]
        waves = [
            {
                "wave": 1,
                "label": "Peer comparison (~12 KB)",
                "sections": ["peer_table", "peer_metrics", "peer_growth", "benchmarks"],
                "purpose": "Core peer-comparison block — who trades at what multiple and who grows how fast.",
            },
            {
                "wave": 2,
                "label": "Sector context (~6 KB)",
                "sections": ["sector_overview", "sector_flows", "sector_valuations"],
                "purpose": "Top-down macro on the sector — flow direction, valuation tier, aggregate size.",
            },
            {
                "wave": 3,
                "label": "Deep relative-valuation + peer-set cross-check (~10 KB)",
                "sections": ["valuation_matrix", "yahoo_peers"],
                "purpose": "Full multi-metric matrix + Yahoo peer-set cross-check when the Screener peer list looks off.",
            },
        ]
        return {
            "symbol": symbol.upper(),
            "available_sections": sections,
            "recommended_waves": waves,
            "warnings": {
                "truncation": "Do NOT call get_peer_sector(section='all') — the ~50 KB payload across 9 sections may truncate. Use recommended_waves.",
                "seven_plus": "Calling 7+ sections in one list is near the truncation ceiling. Split into Wave 1 + Wave 2 instead.",
            },
            "hint": "Call get_peer_sector(section=[<wave sections>]) using recommended_waves, or section='<single>' for targeted drill. TOC is ~1-2 KB; each wave is 6-12 KB.",
        }

    def get_fundamentals_toc(self, symbol: str) -> dict:
        """Compact table-of-contents for get_fundamentals — ~1-2 KB summary.

        Default response when the agent calls get_fundamentals without specifying
        a section. Tells the agent what sections exist, their rough size class,
        their purpose, and the recommended wave-call composition to stay under
        the 30-40 KB MCP truncation ceiling.

        Static menu (not per-stock) — the same 14 sections and 4 waves apply to
        every equity. Per-stock availability is discovered as the agent calls
        each section; empty sections simply return an empty structure.
        """
        is_bfsi = self._is_bfsi(symbol) if hasattr(self, "_is_bfsi") else False
        sections = [
            {"key": "quarterly_results",       "size": "med",   "purpose": "12Q Revenue/OP/NP — the core P&L quarterly trend"},
            {"key": "annual_financials",       "size": "med",   "purpose": "10Y P&L annual rows"},
            {"key": "ratios",                  "size": "small", "purpose": "10Y margin, ROE, ROCE, D/E from Screener"},
            {"key": "quarterly_balance_sheet", "size": "small", "purpose": "8Q BS snapshots (sparse for some)"},
            {"key": "quarterly_cash_flow",     "size": "small", "purpose": "8Q CF (empty for banks + many NSE listed)"},
            {"key": "expense_breakdown",       "size": "med",   "purpose": "Line items (R&D, employee, material, other) — drill for R&D / pharma / 'Other Cost' decomposition"},
            {"key": "growth_rates",            "size": "small", "purpose": "TTM revenue/PAT growth %"},
            {"key": "capital_allocation",      "size": "small", "purpose": "5Y dividend, buyback, capex, net-debt trajectory; FCF = CFO - capex (per_year_fcf + cumulative.fcf)"},
            {"key": "rate_sensitivity",        "size": "small", "purpose": "BFSI only — asset-liability repricing sensitivity"},
            {"key": "cagr_table",              "size": "small", "purpose": "Pre-computed 1/3/5/10Y CAGRs (Revenue, EBITDA, NI, EPS, FCF) + trajectory class"},
            {"key": "cost_structure",          "size": "med",   "purpose": "Material/employee/other as % of revenue — explains margin moves"},
            {"key": "balance_sheet_detail",    "size": "med",   "purpose": "Borrowing structure (ST/LT), asset composition, net debt, capitalized interest notes"},
            {"key": "cash_flow_quality",       "size": "med",   "purpose": "CFO decomposition, FCF trajectory, accrual ratio, earnings-quality forensics"},
            {"key": "working_capital",         "size": "small", "purpose": "Receivables/inventory/payables days, CCC trend"},
        ]
        waves = [
            {
                "wave": 1,
                "label": "P&L + ratios — start here (~15 KB)",
                "sections": ["quarterly_results", "annual_financials", "ratios", "cagr_table"],
                "purpose": "Establish the top-line trajectory, 12Q trend, and pre-computed CAGRs. Run first.",
            },
            {
                "wave": 2,
                "label": "Margin decomposition (~8 KB)",
                "sections": ["cost_structure", "growth_rates"],
                "purpose": "Explains which cost line is driving margin moves identified in Wave 1.",
            },
            {
                "wave": 3,
                "label": "Balance sheet + cash flow (~15 KB)",
                "sections": ["balance_sheet_detail", "cash_flow_quality", "working_capital", "capital_allocation"],
                "purpose": "Leverage, cash conversion quality, WC cycle, capital-return history.",
            },
            {
                "wave": 4,
                "label": "On-demand — call only when needed",
                "sections": ["expense_breakdown", "rate_sensitivity", "quarterly_balance_sheet", "quarterly_cash_flow"],
                "purpose": (
                    "expense_breakdown when 'Other Cost' >20% of revenue or for R&D extraction; "
                    "rate_sensitivity for BFSI; quarterly BS/CF when the 8Q granularity matters."
                ),
            },
        ]
        # Mark BFSI-inapplicable sections
        if is_bfsi:
            for s in sections:
                if s["key"] in ("quarterly_cash_flow", "cash_flow_quality", "working_capital"):
                    s["purpose"] += " — typically empty/not-meaningful for banks"
        return {
            "symbol": symbol.upper(),
            "is_bfsi": is_bfsi,
            "available_sections": sections,
            "recommended_waves": waves,
            "warnings": {
                "truncation": "Do NOT call get_fundamentals(section='all') — the 70+ KB payload is truncated mid-response by the MCP transport, causing partial data and hallucinated gaps.",
                "singular_bloat": "Do NOT pass 10+ sections in one call — same truncation risk. Use the recommended waves above.",
            },
            "hint": "Call get_fundamentals(section=[<wave sections>]) with one of recommended_waves, or with a single section for targeted drill-down. This TOC is ~1-2 KB; wave calls are 8-15 KB each; all well within the 30-40 KB readable window.",
        }

    def get_ownership_toc(self, symbol: str) -> dict:
        """Compact table-of-contents for get_ownership — ~3-5KB summary.

        Default response when the agent calls get_ownership without specifying
        a section. Gives all the high-level signals needed to decide which
        sections to drill into, without hitting the 80-150K-char payload that
        caused MCP transport truncation on HDFCBANK/TCS ownership runs.

        Includes:
          - current_ownership: latest-quarter category breakdown
          - qoq_changes_summary: pp-change by category (last quarter)
          - quarters_available: how many historical quarters are on file
          - top_holders_brief: top 10 named holders (name, class, pct)
          - mf_summary: scheme count, total value, trend, top AMCs
          - pledge_status: current pledge %, trend, margin-call risk
          - insider_activity_365d: buy/sell counts and net value
          - bulk_block_365d: deal count + latest date
          - available_sections + hint: drill-down menu for next call
        """
        # Shareholding snapshot (12 quarters) for current + QoQ
        sh_rows = self.get_shareholding(symbol, quarters=12)
        by_q: dict[str, dict[str, float]] = {}
        for r in sh_rows:
            q = r.get("quarter_end", "")
            by_q.setdefault(q, {})[r.get("category", "")] = r.get("percentage", 0.0)
        quarters_sorted = sorted(by_q.keys(), reverse=True)
        current_q = quarters_sorted[0] if quarters_sorted else None
        prev_q = quarters_sorted[1] if len(quarters_sorted) > 1 else None

        def pct(q: str | None, cat: str) -> float | None:
            if not q:
                return None
            return by_q.get(q, {}).get(cat)

        categories = ["Promoter", "FII", "DII", "MF", "Insurance", "AIF", "Public"]
        current_ownership = {
            "as_of_quarter": current_q,
            **{cat.lower() + "_pct": pct(current_q, cat) for cat in categories},
        }
        qoq_changes = {}
        if prev_q:
            for cat in categories:
                c = pct(current_q, cat)
                p = pct(prev_q, cat)
                if c is not None and p is not None:
                    qoq_changes[cat.lower()] = round(c - p, 2)

        # Top 10 named holders (latest quarter).
        # get_shareholder_detail now returns pivoted rows with latest_pct +
        # holder_type populated (E4 fix). Pre-fix this loop scanned for
        # wide-format keys that never existed and emitted empty names.
        top_holders = self.get_shareholder_detail(symbol, top_n=10)
        holders_brief = []
        for h in top_holders[:10]:
            latest_pct = h.get("latest_pct")
            holders_brief.append({
                "name": h.get("name") or h.get("holder_name") or "",
                "holder_type": h.get("holder_type") or h.get("classification", ""),
                "classification": h.get("classification", ""),
                "latest_pct": round(latest_pct, 2) if isinstance(latest_pct, (int, float)) else None,
                "latest_quarter": h.get("latest_quarter"),
            })

        # MF summary from conviction
        mf_conv = self.get_mf_conviction(symbol)
        mf_summary = (
            {
                "scheme_count": mf_conv.get("schemes_holding"),
                "amc_count": mf_conv.get("amcs_holding"),
                "total_value_cr": mf_conv.get("total_mf_value_cr"),
                "scheme_trend": mf_conv.get("scheme_trend"),
                "top_3_amcs": [s.get("amc") for s in (mf_conv.get("top_schemes") or [])[:3]],
            }
            if mf_conv.get("available")
            else {"available": False, "reason": mf_conv.get("reason", "no data")}
        )

        # Pledge status
        pledge_rows = self.get_promoter_pledge(symbol)
        pledge_status: dict
        if isinstance(pledge_rows, dict) and "error" not in pledge_rows:
            # structured dict from get_promoter_pledge
            pledge_status = {
                "current_pct": pledge_rows.get("latest_pledge_pct"),
                "trend": pledge_rows.get("trend"),
                "margin_call_risk": pledge_rows.get("margin_call_risk"),
            }
        elif isinstance(pledge_rows, list) and pledge_rows:
            latest = pledge_rows[0]
            pledge_status = {
                "current_pct": latest.get("pledge_pct", latest.get("percentage")),
                "trend": "see_drill",
                "margin_call_risk": None,
            }
        else:
            pledge_status = {"current_pct": None, "trend": "no_data", "margin_call_risk": None}

        # Insider activity — 365d summary
        insider_rows = self.get_insider_transactions(symbol, days=365)
        buy_count = sum(
            1 for r in insider_rows
            if (r.get("transaction_type") or "").lower() in ("buy", "market purchase", "purchase")
        )
        sell_count = sum(
            1 for r in insider_rows
            if (r.get("transaction_type") or "").lower() in ("sell", "market sale", "sale")
        )
        net_value_cr = round(
            sum(
                (r.get("value_cr") or r.get("value") or 0)
                * (1 if (r.get("transaction_type") or "").lower() in ("buy", "market purchase", "purchase") else -1)
                for r in insider_rows
            ),
            2,
        ) if insider_rows else 0

        # Bulk/block 365d
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(days=365)).isoformat()
        deal_rows = self.get_bulk_block_deals(symbol)
        deals_365d = [
            d for d in deal_rows
            if (d.get("date") or d.get("deal_date") or "") >= cutoff
        ] if deal_rows else []
        latest_deal_date = max(
            (d.get("date") or d.get("deal_date") or "" for d in deals_365d),
            default=None,
        ) or None

        return {
            "symbol": symbol.upper(),
            "current_ownership": current_ownership,
            "qoq_changes_summary": qoq_changes,
            "quarters_available": len(quarters_sorted),
            "top_10_holders_brief": holders_brief,
            "mf_summary": mf_summary,
            "pledge_status": pledge_status,
            "insider_activity_365d": {
                "buy_count": buy_count,
                "sell_count": sell_count,
                "net_value_cr": net_value_cr,
                "txn_count": len(insider_rows),
            },
            "bulk_block_365d": {
                "count": len(deals_365d),
                "latest_deal_date": latest_deal_date,
            },
            "available_sections": [
                "shareholding", "changes", "shareholder_detail",
                "mf_holdings", "mf_changes", "mf_conviction",
                "insider", "bulk_block", "promoter_pledge",
                "adr_gdr",
            ],
            "hint": (
                "This is a compact TOC. Call get_ownership(section='<name>') "
                "to drill into any section. Heavy sections are capped: "
                "mf_holdings returns top 30 schemes by value (+ tail summary); "
                "shareholder_detail returns top 20 holders. Pass section=['s1','s2'] "
                "for multiple targeted sections in one call — avoid section='all' "
                "which can exceed the MCP tool-result transport limit."
            ),
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
        """Current macro indicators: VIX, USD/INR, Brent crude, 10Y G-sec.

        Coalesces field-by-field across the most recent 7 rows so that a
        partially-populated today-row (e.g. only USD/INR fetched mid-day)
        falls forward to the most recent prior value for any null field.
        The top-level ``date`` is the latest row's date; per-field
        ``<field>_as_of`` records the source date when it differs.
        """
        rows = self._store._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 7"
        ).fetchall()
        if not rows:
            return {}
        latest_date = rows[0]["date"]
        result: dict = {"date": latest_date}
        keys = set(rows[0].keys())
        for field in ("india_vix", "usd_inr", "brent_crude", "gsec_10y"):
            if field not in keys:
                continue
            for row in rows:
                v = row[field]
                if v is not None:
                    result[field] = v
                    if row["date"] != latest_date:
                        result[f"{field}_as_of"] = row["date"]
                    break
        return _clean(result)

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
        """Current commodity prices with 1M/3M/1Y changes.

        Includes gold, silver (USD + INR variants from commodity_prices) and
        Brent crude (sourced from macro_daily.brent_crude). Brent carries
        forward across the most recent rows when the latest row is null.
        """
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

        # Brent crude from macro_daily — surface as a commodity entry.
        # Use only non-null brent_crude rows so 1M/3M/1Y deltas are computed
        # against actual prices, and the latest entry carries forward when
        # today's row is partial.
        brent_rows = self._store._conn.execute(
            "SELECT date, brent_crude FROM macro_daily "
            "WHERE brent_crude IS NOT NULL ORDER BY date ASC"
        ).fetchall()
        brent_data = [(r["date"], r["brent_crude"]) for r in brent_rows]
        if brent_data:
            latest_brent = brent_data[-1][1]

            def _brent_change(days_ago: int, _data=brent_data, _latest=latest_brent) -> float | None:
                target_idx = max(0, len(_data) - days_ago)
                if target_idx < len(_data) and _data[target_idx][1]:
                    return round((_latest - _data[target_idx][1]) / _data[target_idx][1] * 100, 1)
                return None

            result["brent"] = {
                "price": latest_brent,
                "date": brent_data[-1][0],
                "change_1m_pct": _brent_change(22),
                "change_3m_pct": _brent_change(66),
                "change_1y_pct": _brent_change(252),
            }

        return _clean(result) if result else {"available": False, "reason": "No commodity data"}

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

    def get_peer_comparison(self, symbol: str) -> dict:
        """Peer comparison for the subject vs a vetted peer set.

        Primary source is Yahoo's peer recommendations (peer_links table).
        Falls back to Screener's peer_comparison table when Yahoo's set is
        empty or sector-mismatched:

          (a) **empty** — Yahoo returned no peers for this symbol at all.
          (b) **sector-mismatched** — >50% of Yahoo peers belong to a
              different industry than the subject (e.g. SBIN's Yahoo list
              historically includes LT, RELIANCE — both non-banking).

        Provenance surfaced via `source` and `fallback_reason` fields so
        callers can see which peer set they got and why.

        Returned shape is unchanged for callers that don't check source —
        still {subject, peers, peer_count, source}. Peers from the fallback
        path have `screener_fallback=true` and no `yahoo_score`.
        """
        subject = self._store.get_company_snapshot(symbol) or {"symbol": symbol}
        subject_industry = (subject.get("industry") or "").strip().lower()

        peer_links = self._store.get_peer_links(symbol)
        peer_symbols = [p["peer_symbol"] for p in peer_links]
        peer_snapshots = (
            self._store.get_company_snapshots(peer_symbols) if peer_symbols else []
        )

        # Fallback trigger (a): Yahoo returned nothing
        if not peer_snapshots:
            return self._screener_peer_fallback(
                symbol, subject,
                reason="No Yahoo peers found for this symbol",
            )

        # Fallback trigger (b): sector mismatch — >50% of Yahoo peers in a
        # different industry than the subject. Skip the check when we lack
        # a subject industry (can't validate).
        if subject_industry:
            mismatch_count = sum(
                1 for p in peer_snapshots
                if (p.get("industry") or "").strip().lower() != subject_industry
                and (p.get("industry") or "").strip()  # don't penalize missing peer industry
            )
            if peer_snapshots and mismatch_count > len(peer_snapshots) / 2:
                mismatched_industries = sorted({
                    (p.get("industry") or "unknown")
                    for p in peer_snapshots
                    if (p.get("industry") or "").strip().lower() != subject_industry
                })[:3]
                return self._screener_peer_fallback(
                    symbol, subject,
                    reason=f"{mismatch_count} of {len(peer_snapshots)} Yahoo peers mismatched "
                           f"subject industry '{subject.get('industry')}' "
                           f"(e.g. {', '.join(mismatched_industries)})",
                )

        # Happy path — Yahoo peers look sector-consistent.
        score_map = {p["peer_symbol"]: p["score"] for p in peer_links}
        for snap in peer_snapshots:
            snap["yahoo_score"] = score_map.get(snap["symbol"])
        return {
            "subject": _clean(subject),
            "peers": _clean(peer_snapshots),
            "peer_count": len(peer_snapshots),
            "source": "yahoo_recommendations",
        }

    def _screener_peer_fallback(self, symbol: str, subject: dict, reason: str) -> dict:
        """Build a peer_comparison-shaped response from Screener peers.

        Invoked when Yahoo peers are empty or sector-mismatched. Keeps the
        same return schema so agents don't need to special-case the path.

        Two enrichment fixes vs. the prior implementation:

        (1) When a Screener peer's `company_snapshot` is missing or has
            empty market_cap_cr (common for small-cap peers Screener
            recommends but we don't track), fall back to the peer_comparison
            row's own `market_cap` field. Without this, conglomerate peers
            uniformly returned mcap=0 and looked like microcaps.

        (2) Filter the peer set to the subject's industry where possible.
            Screener's peer recommendation API is itself sector-noisy for
            conglomerates (HINDUNILVR's recommended peers include a sugar
            mill and a chemicals company; VEDL's include specialty
            chemicals). We keep peers whose industry matches the subject,
            and surface a `peer_quality_warning` when we drop the count
            below 2.
        """
        screener_rows = self._store.get_peers(symbol) or []
        screener_by_sym = {
            r["peer_symbol"]: r for r in screener_rows if r.get("peer_symbol")
        }
        peer_symbols = list(screener_by_sym.keys())
        peer_snapshots = (
            self._store.get_company_snapshots(peer_symbols) if peer_symbols else []
        )
        snap_by_sym = {s["symbol"]: dict(s) for s in peer_snapshots}

        # Enrich every Screener peer — even those without a company_snapshot
        # row — using the peer_comparison row as the data source of last
        # resort. Subject's own row is excluded (already in `subject`).
        enriched: list[dict] = []
        for sym in peer_symbols:
            if sym == symbol:
                continue
            screener = screener_by_sym.get(sym, {})
            snap = snap_by_sym.get(sym, {"symbol": sym})
            # Backfill mcap from peer_comparison.market_cap when snapshot is
            # missing or zero. Screener stores market_cap in Cr already.
            if not snap.get("market_cap_cr") and screener.get("market_cap"):
                snap["market_cap_cr"] = screener["market_cap"]
            # Backfill name + PE + ROCE from screener row when snapshot is
            # entirely synthetic.
            if not snap.get("name") and screener.get("peer_name"):
                snap["name"] = screener["peer_name"]
            if not snap.get("pe_trailing") and screener.get("pe"):
                snap["pe_trailing"] = screener["pe"]
            snap["screener_fallback"] = True
            snap["yahoo_score"] = None
            enriched.append(snap)

        # Industry filter: keep peers whose industry matches the subject's.
        # Skip the filter when subject industry is unknown (can't validate).
        subject_industry = (subject.get("industry") or "").strip().lower()
        warnings: list[str] = []
        if subject_industry and enriched:
            matched = [
                p for p in enriched
                if (p.get("industry") or "").strip().lower() == subject_industry
            ]
            if len(matched) >= 2:
                # Drop sector-mismatched peers if we still have ≥2 left
                dropped = len(enriched) - len(matched)
                if dropped > 0:
                    warnings.append(
                        f"Filtered out {dropped} sector-mismatched peer(s) "
                        f"from Screener recommendation"
                    )
                enriched = matched
            else:
                # Not enough sector-matched peers — keep all but warn
                warnings.append(
                    "Screener peer set is sector-noisy and "
                    "subject industry is underrepresented; treat peer "
                    "comparisons with caution"
                )

        result: dict = {
            "subject": _clean(subject),
            "peers": _clean(enriched),
            "peer_count": len(enriched),
            "source": "screener_fallback",
            "fallback_reason": reason,
        }
        if warnings:
            result["peer_quality_warning"] = warnings
        return result

    def get_screener_peers(self, symbol: str) -> list[dict]:
        """Screener.in-recommended peers from peer_comparison table.

        Explicit fallback when the Yahoo peer set from get_peer_comparison
        looks sector-mismatched. Returns raw Screener rows (CMP, P/E, MCap,
        ROCE, div_yield, quarterly sales/NP with YoY variance).
        """
        return self._store.get_peers(symbol)

    def get_shareholder_detail(
        self, symbol: str, classification: str | None = None, top_n: int = 20,
        min_latest_pct: float = 1.0,
    ) -> list[dict]:
        """Individual shareholder names and quarterly %: Vanguard, LIC, etc.

        Returns ONE pivoted row per holder (not per holder x quarter) with:
          {name, holder_type, classification, latest_pct, latest_quarter,
           quarters: {qtr: pct, ...}}

        Applies the 1% BSE disclosure threshold on the LATEST quarter and
        sorts globally by latest_pct desc, capping to top_n (default 20).
        This fixes E4 — pre-fix, large FII stakes (e.g., BHARTIARTL 28% FII)
        surfaced zero named FII entities because the top-N sort was reading
        wide-format keys (q_XXX / Q-prefix / _pct suffix) against a narrow
        holder x quarter row schema, so latest_pct was always 0 and the
        alphabetical classification order (domestic_institutions first)
        deterministically filled all 20 slots with DII rows.

        holder_type normalization: foreign_institutions -> 'FII',
        domestic_institutions -> 'DII', promoters -> 'Promoter',
        public -> 'Public'.

        Cap strategy (to guarantee FII representation for large-cap FII-heavy
        names like BHARTIARTL where individual FII holdings are 1.0-1.5% but
        individual DII/LIC holdings are 3-5% and would otherwise crowd the
        entire top_n): reserve up to min(5, #FII_holders) slots for FII, then
        fill remaining slots globally by latest_pct desc.

        Aggregate-FII fallback: when Screener's per-name FII feed surfaces
        zero named foreign holders (TCS pattern — every individual FII is
        below the 1% disclosure threshold) but the BSE shareholding pattern
        reports a non-zero aggregate FII stake, we emit a single synthetic
        row of holder_type='FII' named 'Aggregate FII (no individuals
        disclosed at >=1%)' carrying the aggregate FII percentage. This
        prevents the agent from concluding the stock has zero foreign
        ownership when the aggregate disagrees. Only fires when classification
        is None or 'foreign_institutions' and #FII_named == 0.
        """
        rows = self._store.get_shareholder_details(symbol, classification)
        pivoted = self._pivot_shareholder_rows(rows)
        if min_latest_pct is not None and min_latest_pct > 0:
            pivoted = [h for h in pivoted if (h.get("latest_pct") or 0) >= min_latest_pct]

        # Aggregate-FII fallback (TCS pattern). Only emit when caller hasn't
        # filtered to a non-FII classification, and when no named FII rows
        # cleared the disclosure threshold.
        if classification in (None, "foreign_institutions"):
            has_named_fii = any(h.get("holder_type") == "FII" for h in pivoted)
            if not has_named_fii:
                synthetic = self._synthetic_aggregate_fii_row(symbol)
                if synthetic is not None:
                    pivoted.append(synthetic)

        pivoted.sort(key=lambda h: h.get("latest_pct") or 0.0, reverse=True)
        if top_n is None or len(pivoted) <= top_n:
            return pivoted

        # Reserve FII slots so large-cap FII stakes aren't dropped entirely.
        # Only applies when caller didn't filter to a single classification.
        if classification is None:
            fii_rows = [h for h in pivoted if h.get("holder_type") == "FII"]
            fii_reserve = min(5, len(fii_rows))
            other_rows = [h for h in pivoted if h.get("holder_type") != "FII"]
            # Keep top fii_reserve FIIs (already sorted by latest_pct)
            reserved = fii_rows[:fii_reserve]
            remaining_slots = top_n - fii_reserve
            # Fill remaining from (pivoted minus reserved) ordered by latest_pct
            # Include the leftover FIIs (if any) in the global pool too so a
            # very large individual FII still qualifies on merit.
            reserved_names = {(r["classification"], r["name"]) for r in reserved}
            pool = [h for h in pivoted if (h["classification"], h["name"]) not in reserved_names]
            filler = pool[:remaining_slots]
            combined = reserved + filler
            # Re-sort the combined set by latest_pct desc for display.
            combined.sort(key=lambda h: h.get("latest_pct") or 0.0, reverse=True)
            return combined
        return pivoted[:top_n]

    # Screener's narrow classification strings -> normalized holder_type labels
    # used in reports. Mirrored in the ownership TOC's top_10_holders_brief.
    _HOLDER_TYPE_MAP = {
        "foreign_institutions": "FII",
        "domestic_institutions": "DII",
        "promoters": "Promoter",
        "public": "Public",
    }

    @classmethod
    def _pivot_shareholder_rows(cls, rows: list[dict]) -> list[dict]:
        """Collapse narrow (name x quarter) rows into one row per holder.

        Input row schema (from store.get_shareholder_details):
          {symbol, classification, holder_name, quarter, percentage, ...}

        Output row schema:
          {name, holder_type, classification, latest_pct, latest_quarter,
           quarters: {quarter: pct}}
        """
        from datetime import datetime as _dt

        def parse_q(q: str) -> tuple[int, int]:
            # Screener quarter strings are "Sep 2025", "Jun 2025", ...
            try:
                dt = _dt.strptime(q.strip(), "%b %Y")
                return (dt.year, dt.month)
            except Exception:
                return (0, 0)

        grouped: dict[tuple[str, str], dict] = {}
        for r in rows:
            name = r.get("holder_name") or r.get("name") or ""
            cls_raw = r.get("classification") or ""
            key = (cls_raw, name)
            pct = r.get("percentage")
            qtr = r.get("quarter") or ""
            if name == "" or pct is None or qtr == "":
                continue
            entry = grouped.setdefault(
                key,
                {
                    "name": name,
                    "classification": cls_raw,
                    "holder_type": cls._HOLDER_TYPE_MAP.get(cls_raw, cls_raw),
                    "quarters": {},
                },
            )
            entry["quarters"][qtr] = pct

        result: list[dict] = []
        for entry in grouped.values():
            qtrs = entry["quarters"]
            if not qtrs:
                continue
            latest_q = max(qtrs.keys(), key=parse_q)
            entry["latest_quarter"] = latest_q
            entry["latest_pct"] = qtrs[latest_q]
            result.append(entry)
        return result

    def _synthetic_aggregate_fii_row(self, symbol: str) -> dict | None:
        """Build a placeholder FII row from BSE aggregate when no named FIIs disclosed.

        Some symbols (TCS pattern) have a non-trivial aggregate FII stake
        (e.g., 10.37%) but no individual foreign holder above the 1% disclosure
        threshold, so Screener's `/investors/foreign_institutions/` endpoint
        returns an empty list. Without this fallback, agents would conclude
        the stock has zero foreign ownership — directly contradicting the
        aggregate. We synthesize ONE row carrying the aggregate so the FII
        bucket isn't silently dropped from the report.

        Returns None when:
          * shareholding table has no rows for this symbol, OR
          * latest aggregate FII percentage is None / <= 0
        """
        sym = symbol.upper()
        try:
            row = self._store._conn.execute(
                "SELECT quarter_end, percentage FROM shareholding "
                "WHERE symbol = ? AND category = 'FII' "
                "ORDER BY quarter_end DESC LIMIT 1",
                (sym,),
            ).fetchone()
        except Exception:
            return None
        if not row:
            return None
        pct = row["percentage"] if hasattr(row, "keys") else row[1]
        if pct is None or pct <= 0:
            return None
        quarter_end = row["quarter_end"] if hasattr(row, "keys") else row[0]
        # Convert "2025-12-31" -> "Dec 2025" to match the per-name quarter format.
        try:
            from datetime import datetime as _dt
            qtr_label = _dt.strptime(quarter_end, "%Y-%m-%d").strftime("%b %Y")
        except Exception:
            qtr_label = quarter_end or ""
        return {
            "name": "Aggregate FII (no individuals disclosed at >=1%)",
            "classification": "foreign_institutions",
            "holder_type": "FII",
            "latest_pct": float(pct),
            "latest_quarter": qtr_label,
            "quarters": {qtr_label: float(pct)},
            "is_aggregate": True,
            "source": "shareholding_pattern_aggregate",
        }

    # ------------------------------------------------------------------
    # E7 — ADR / GDR outstanding (stub)
    # ------------------------------------------------------------------
    # Known Indian names with active ADR / GDR programs. Used as a stub
    # allowlist until AR extraction is wired to surface share-capital notes.
    # TODO(E7): replace with live extraction from the AR notes-to-financials
    # "Note - Share Capital" sub-section once the AR extractor surfaces it.
    _ADR_GDR_LISTINGS: dict[str, list[str]] = {
        "INFY": ["NYSE"],
        "TCS": ["NYSE"],  # Unsponsored Level 1 OTC; listed for completeness
        "HDFCBANK": ["NYSE"],
        "ICICIBANK": ["NYSE"],
        "WIT": ["NYSE"],
        "WIPRO": ["NYSE"],
        "RDY": ["NYSE"],
        "DRREDDY": ["NYSE"],
        "SIFY": ["NASDAQ"],
        "MMTC": ["LSE"],
        "TATAMOTORS": ["NYSE"],
        "SBIN": ["LSE"],
        "AXISBANK": ["LSE"],
        "RELIANCE": [],  # Explicitly none — used as a negative-case anchor
    }

    def get_adr_gdr(self, symbol: str) -> dict:
        """ADR/GDR outstanding — reads from AR notes-to-financials when present,
        falls back to a structured stub payload otherwise.

        Attempts live extraction by scanning the most recent AR's
        `notes_to_financials` section for depositary-receipt disclosures:
          1. A dedicated `share_capital.adr_gdr_details` sub-dict, if the
             extractor produces one.
          2. Any `material_items` / `forensic_red_flags` entry that mentions
             "depositary receipts" / "ADR" / "GDR" / "American Depositary"
             with an adjacent numeric (outstanding units) token.

        The AR extractor schema today does NOT emit ADR-specific fields
        (see _SECTION_PROMPTS['notes_to_financials'] in
        annual_report_extractor.py), so live population is best-effort. When
        nothing is found we preserve the stub behavior but record which
        AR years were consulted in `_meta.source_checked`.

        Returned shape:
          {
            "listed_on": ["NYSE", ...],           # empty list if none
            "outstanding_units_mn": None | float,
            "pct_of_total_equity": None | float,
            "as_of_date": None | "YYYY-MM-DD",
            "source": "stub" | "FY25_AR_notes_to_financials",
            "_meta": {"stub": bool, "source_checked": [...], ...}
          }
        """
        sym_up = symbol.upper()
        listed = self._ADR_GDR_LISTINGS.get(sym_up, [])
        meta: dict = {"stub": True, "todo": "E7"}
        if sym_up not in self._ADR_GDR_LISTINGS:
            meta["reason"] = "symbol_not_in_known_adr_gdr_list"
        elif not listed:
            meta["reason"] = "no_known_adr_gdr_listing"

        payload: dict = {
            "listed_on": listed,
            "outstanding_units_mn": None,
            "pct_of_total_equity": None,
            "as_of_date": None,
            "source": "stub",
            "_meta": meta,
        }

        # Only attempt live extraction for known ADR/GDR issuers.
        if not listed:
            return payload

        try:
            ar = self.get_annual_report(
                sym_up, section="notes_to_financials", include_cross_year=False,
            )
        except Exception:
            ar = {"error": "get_annual_report raised"}

        if not isinstance(ar, dict) or "error" in ar:
            meta["source_checked"] = []
            return payload

        years_payload = ar.get("years") or []
        checked: list[str] = []
        found_entry: dict | None = None
        found_fy: str | None = None

        # Walk years newest-first (get_annual_report already sorts that way).
        for yslice in years_payload:
            fy_label = (yslice.get("fiscal_year") or "").upper()
            notes = yslice.get("notes_to_financials")
            if not fy_label or not isinstance(notes, dict):
                continue
            # Skip the placeholder-empty shape.
            if notes.get("status") == "section_not_found_or_empty":
                continue
            if "extraction_error" in notes:
                continue
            checked.append(f"{fy_label}_AR_notes_to_financials")

            hit = self._find_adr_gdr_in_notes(notes)
            if hit is not None:
                found_entry = hit
                found_fy = fy_label
                break

        meta["source_checked"] = checked

        if found_entry is not None and found_fy:
            payload["outstanding_units_mn"] = found_entry.get("outstanding_units_mn")
            payload["pct_of_total_equity"] = found_entry.get("pct_of_total_equity")
            payload["as_of_date"] = found_entry.get("as_of_date")
            payload["source"] = f"{found_fy}_AR_notes_to_financials"
            meta["stub"] = False
            meta.pop("todo", None)
            meta.pop("reason", None)
        return payload

    @staticmethod
    def _find_adr_gdr_in_notes(notes: dict) -> dict | None:
        """Best-effort search for ADR/GDR outstanding inside a notes_to_financials payload.

        Two paths:
          1. Structured: `share_capital.adr_gdr_details` if extractor surfaces it.
          2. Free-text: scan `material_items` / `forensic_red_flags` strings for
             ADR/GDR/depositary keywords and an adjacent numeric.

        Returns None when nothing usable is found.
        """
        # Path 1 — explicit sub-dict (future-proof; current extractor does not emit this).
        share_cap = notes.get("share_capital")
        if isinstance(share_cap, dict):
            adr = share_cap.get("adr_gdr_details")
            if isinstance(adr, dict):
                return {
                    "outstanding_units_mn": adr.get("outstanding_units_mn")
                        or adr.get("outstanding_mn") or adr.get("units_mn"),
                    "pct_of_total_equity": adr.get("pct_of_total_equity")
                        or adr.get("pct_equity"),
                    "as_of_date": adr.get("as_of_date") or adr.get("as_of"),
                }

        # Path 2 — free-text scan of narrative list fields.
        kw_re = re.compile(r"\b(adr|gdr|american depositary|depositary receipts?)\b", re.IGNORECASE)
        # Pull a numeric with optional "mn" / "million" / "lakh" / "crore" unit suffix.
        num_re = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(mn|million|lakh|lakhs|crore|cr)?", re.IGNORECASE)

        candidates: list[str] = []
        for key in ("material_items", "forensic_red_flags",
                    "significant_accounting_policy_changes"):
            val = notes.get(key)
            if isinstance(val, list):
                candidates.extend(str(x) for x in val if x)
            elif isinstance(val, str):
                candidates.append(val)

        for text in candidates:
            if not kw_re.search(text):
                continue
            m = num_re.search(text)
            if not m:
                continue
            try:
                units = float(m.group(1))
            except ValueError:
                continue
            unit = (m.group(2) or "").lower()
            if unit in ("crore", "cr"):
                units = units * 10.0  # 1 cr = 10 mn
            elif unit in ("lakh", "lakhs"):
                units = units / 10.0  # 1 lakh = 0.1 mn
            return {
                "outstanding_units_mn": units,
                "pct_of_total_equity": None,
                "as_of_date": None,
            }
        return None

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
        """Latest DCF intrinsic value + margin of safety.

        Plan v2 §7 E15: when DCF is empty/unavailable, emit a reason code
        ('insufficient_history' | 'negative_fcf' | 'growth_above_limits' |
        'unknown') instead of returning an empty dict, so agents can show
        the user *why* DCF was skipped.
        """
        dcf = self._store.get_fmp_dcf_latest(symbol)
        if not dcf or not dcf.dcf or dcf.dcf <= 0:
            reason = self._classify_dcf_empty_reason(symbol)
            return {
                "fv_cr": None,
                "reason_empty": reason,
                "notes": (
                    "DCF unavailable — see reason_empty. Agents should defer to "
                    "PE-band/consensus/PB-band for fair value."
                ),
            }
        result = _clean(dcf.model_dump())
        if dcf.dcf and dcf.stock_price and dcf.dcf > 0:
            result["margin_of_safety_pct"] = round(
                (dcf.dcf - dcf.stock_price) / dcf.dcf * 100, 2
            )
        return result

    def _classify_dcf_empty_reason(self, symbol: str) -> str:
        """Plan v2 §7 E15: classify *why* DCF is empty.

        Returns one of: 'insufficient_history' | 'negative_fcf' |
        'growth_above_limits' | 'unknown'.
        """
        annual = self._store.get_annual_financials(symbol, limit=5)
        if not annual:
            return "insufficient_history"

        # Compute FCF proxy = cfo + cfi (cfi is typically negative = capex outflow).
        fcfs: list[float] = []
        for a in annual:
            cfo = getattr(a, "cfo", None)
            cfi = getattr(a, "cfi", None)
            if cfo is not None and cfi is not None:
                fcfs.append(cfo + cfi)
            elif getattr(a, "free_cash_flow", None) is not None:
                fcfs.append(a.free_cash_flow)

        if not fcfs:
            return "insufficient_history"

        positive = [v for v in fcfs if v and v > 0]
        if len(positive) < 3:
            return "insufficient_history"

        # Latest FCF first (annual sorted DESC by fiscal_year_end by default)
        latest_fcf = fcfs[0]
        if latest_fcf is not None and latest_fcf < 0:
            return "negative_fcf"

        # 5Y CAGR check — compare oldest positive FCF to latest
        if len(fcfs) >= 5:
            oldest = fcfs[-1]
            latest = fcfs[0]
            if oldest and oldest > 0 and latest and latest > 0:
                years = len(fcfs) - 1
                try:
                    cagr = (latest / oldest) ** (1 / years) - 1
                    if cagr > 0.30:
                        return "growth_above_limits"
                except (ValueError, ZeroDivisionError):
                    pass

        return "unknown"

    def get_dcf_history(self, symbol: str, days: int = 365) -> list[dict]:
        """Historical DCF trajectory."""
        rows = self._store.get_fmp_dcf_history(symbol, limit=10)
        return _clean([r.model_dump() for r in rows])

    def get_fno_metrics(self, symbol: str) -> dict | None:
        """F&O derivatives metrics for the latest trading day with data.

        Returns aggregate open interest by instrument leg, put-call ratio
        (PCR), and rollover percentage (next-expiry OI share of the
        current+next pair, computed only when ≥2 future expiries exist).

        None when no F&O contracts are on file for the symbol.
        """
        conn = self._store._conn
        row = conn.execute(
            "SELECT MAX(trade_date) AS max_date FROM fno_contracts WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        if not row or not row["max_date"]:
            return None
        latest = row["max_date"]

        aggs = conn.execute(
            """
            SELECT instrument, option_type,
                   SUM(open_interest) AS total_oi,
                   SUM(change_in_oi)  AS oi_change
            FROM fno_contracts
            WHERE symbol = ? AND trade_date = ?
            GROUP BY instrument, option_type
            """,
            (symbol, latest),
        ).fetchall()
        if not aggs:
            return None

        futures_oi = futures_oi_change = 0
        call_oi = call_oi_change = 0
        put_oi = put_oi_change = 0
        for a in aggs:
            instr = a["instrument"]
            opt = a["option_type"]
            oi = a["total_oi"] or 0
            chg = a["oi_change"] or 0
            if instr in ("FUTSTK", "FUTIDX"):
                futures_oi += oi
                futures_oi_change += chg
            elif instr in ("OPTSTK", "OPTIDX") and opt == "CE":
                call_oi += oi
                call_oi_change += chg
            elif instr in ("OPTSTK", "OPTIDX") and opt == "PE":
                put_oi += oi
                put_oi_change += chg

        pcr = round(put_oi / call_oi, 3) if call_oi > 0 else None

        # Rollover %: share of next-month future OI in the (current + next) pair.
        # Convention: as expiry approaches, rollover trend = next/(curr+next).
        expiries = conn.execute(
            """
            SELECT expiry_date, SUM(open_interest) AS oi
            FROM fno_contracts
            WHERE symbol = ? AND trade_date = ?
              AND instrument IN ('FUTSTK', 'FUTIDX')
            GROUP BY expiry_date
            ORDER BY expiry_date ASC
            """,
            (symbol, latest),
        ).fetchall()
        rollover_pct = None
        if len(expiries) >= 2:
            cur_oi = expiries[0]["oi"] or 0
            nxt_oi = expiries[1]["oi"] or 0
            if (cur_oi + nxt_oi) > 0:
                rollover_pct = round(nxt_oi / (cur_oi + nxt_oi) * 100, 1)

        return {
            "date": latest,
            "futures_oi": futures_oi,
            "futures_oi_change": futures_oi_change,
            "call_oi": call_oi,
            "call_oi_change": call_oi_change,
            "put_oi": put_oi,
            "put_oi_change": put_oi_change,
            "pcr": pcr,
            "rollover_pct": rollover_pct,
            "total_oi": futures_oi + call_oi + put_oi,
        }

    def get_technical_indicators(self, symbol: str) -> list[dict]:
        """Latest RSI, MACD, SMA-50, SMA-200, ADX (FMP primary, yfinance fallback).

        Augments the indicator row with F&O fields (PCR, futures/call/put OI,
        rollover %) when F&O contracts exist for the symbol — required for
        F&O-listed stocks per the technical-agent prompt.
        """
        fno = self.get_fno_metrics(symbol)

        rows = self._store.get_fmp_technical_indicators(symbol)
        if rows:
            out = [r.model_dump() for r in rows]
            if fno and out:
                out[0] = {**out[0], "fno": fno}
            return _clean(out)

        # Fallback: compute basic technicals from daily_stock_data (bhavcopy).
        # Use adj_close — SMA-50/SMA-200/RSI-14 over 200 days are directly
        # distorted by unadjusted split/bonus cliffs. Fallback to raw close
        # if adj_close not yet populated (pre-backfill).
        conn = self._store._conn
        prices = conn.execute(
            "SELECT date, COALESCE(adj_close, close) AS close "
            "FROM daily_stock_data WHERE symbol = ? ORDER BY date DESC LIMIT 200",
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

        if fno:
            result["fno"] = fno

        return [result] if result else []

    def get_dupont_decomposition(self, symbol: str) -> dict:
        """ROE = margin × turnover × leverage (10yr). Uses Screener annual_financials, falls back to FMP key_metrics.

        If MEDIUM+ data_quality_flags overlap the requested window, the result
        is computed only on the longest unbroken segment, and the dropped
        boundary is reported in `effective_window.narrowed_due_to`. Agents should
        narrate the break rather than chain ratios across it.
        """
        from flowtracker.data_quality import longest_unflagged_window

        # Try Screener data first
        annuals = self._store.get_annual_financials(symbol, limit=10)
        if annuals:
            # Narrow to longest unbroken segment if flags overlap.
            flags = self._store.get_data_quality_flags(symbol, min_severity="MEDIUM")
            relevant = [f for f in flags if f["curr_fy"] in {a.fiscal_year_end for a in annuals}]
            segment, dropped = longest_unflagged_window(annuals, relevant)
            effective_window = {
                "start_fy": segment[-1].fiscal_year_end if segment else None,
                "end_fy": segment[0].fiscal_year_end if segment else None,
                "n_years": len(segment),
                "narrowed_due_to": [
                    {"prior_fy": f["prior_fy"], "curr_fy": f["curr_fy"],
                     "line": f["line"], "severity": f["severity"]}
                    for f in dropped
                ],
            }
            decomp = []
            for i, a in enumerate(segment):
                total_equity = (a.equity_capital or 0) + (a.reserves or 0)
                # Use average of T and T-1 for balance sheet items (more accurate
                # for growing companies). Pull from `segment` not `annuals` so the
                # prior-year sample stays within the same bucketing era.
                if i + 1 < len(segment):
                    prev = segment[i + 1]
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
                return {"source": "screener", "years": decomp, "effective_window": effective_window}

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
        # Plan v2 §7 E11: detect basis mismatch between PE-band source and EPS source.
        pe_basis = self._detect_pe_basis(symbol)
        eps_basis = self._detect_eps_basis(symbol)
        basis_mismatch = (
            pe_basis != "unknown"
            and eps_basis != "unknown"
            and pe_basis != eps_basis
        )
        result["pe_basis"] = pe_basis
        result["eps_basis"] = eps_basis
        if basis_mismatch:
            result["_warning_basis_mismatch"] = (
                f"PE sourced from {pe_basis} basis, EPS sourced from {eps_basis} basis — "
                "blend weight downranked to 0"
            )

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
            # E11: pe_fair contributes to auto-blend only if basis matches or unknown.
            pe_fair = None if basis_mismatch else base

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

        # Combined fair value = average of available (PE component dropped on basis mismatch)
        values = [v for v in [pe_fair, dcf_value, target_mean] if v]
        if values and current_price:
            combined = sum(values) / len(values)
            margin = (combined - current_price) / combined * 100
            result["combined_fair_value"] = round(combined, 2)
            result["current_price"] = current_price
            result["margin_of_safety_pct"] = round(margin, 2)
            result["sources_used"] = len(values)
            # E11: if basis mismatch downranked PE weight to 0, expose the weights
            # the auto-blend actually used so agents can reason about the shape.
            if basis_mismatch:
                result["blend_weights"] = {
                    "pe_band": 0,
                    "dcf": round(1.0 / len(values), 3) if dcf_value else 0,
                    "consensus_target": round(1.0 / len(values), 3) if target_mean else 0,
                }

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

    # Matrix metrics must match company_snapshot column names. Dropped
    # ev_revenue + ps_ratio (not present in company_snapshot); renamed
    # pb_ratio->pb, peg_ratio->peg, dividend_yield->div_yield.
    _MATRIX_METRICS = [
        "pe_trailing", "pe_forward", "pb", "ev_ebitda",
        "peg", "roe", "roa", "operating_margin", "net_margin",
        "debt_to_equity", "div_yield", "revenue_growth", "earnings_growth",
        "market_cap",
    ]

    def get_valuation_matrix(self, symbol: str) -> dict:
        """Multi-metric valuation matrix: subject vs Yahoo peers, using company_snapshot."""
        peer_links = self._store.get_peer_links(symbol)
        peer_syms = [p["peer_symbol"] for p in peer_links if p.get("peer_symbol") != symbol]

        subject_snap = self._store.get_company_snapshot(symbol) or {}
        subject_data: dict = {
            k: subject_snap.get(k)
            for k in self._MATRIX_METRICS
            if subject_snap.get(k) is not None
        }
        subject_data["symbol"] = symbol

        peer_snaps = self._store.get_company_snapshots(peer_syms) if peer_syms else []
        peer_data: list[dict] = []
        for snap in peer_snaps:
            row = {k: snap.get(k) for k in self._MATRIX_METRICS if snap.get(k) is not None}
            if not row:
                continue
            row["symbol"] = snap.get("symbol")
            peer_data.append(row)

        all_entries = [subject_data] + peer_data
        sector_stats: dict = {}
        subject_percentiles: dict = {}
        for metric in self._MATRIX_METRICS:
            values = [e[metric] for e in all_entries if metric in e and e[metric] is not None]
            if len(values) < 2:
                continue
            quantiles = statistics.quantiles(values, n=4)
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
        """Alias for get_peer_comparison (kept for back-compat)."""
        return self.get_peer_comparison(symbol)

    # Top-level concall quarter sections that can be requested via sub_section
    _CONCALL_SECTIONS = (
        "opening_remarks",
        "operational_metrics",
        "financial_metrics",
        "management_commentary",
        "subsidiaries",
        "qa_session",
        "flags",
        # Management's "like-for-like / comparable basis" growth statements.
        # Backstop for trend math when annual_financials has a reclassification
        # flag — see plans/screener-data-discontinuity.md Strategy 3.
        "comparable_growth_metrics",
    )

    def get_concall_insights(
        self,
        symbol: str,
        section_filter: str | None = None,
        quarter: str | None = None,
        qa_topics: list[str] | None = None,
    ) -> dict:
        """Get pre-extracted concall insights from the vault.

        Returns structured concall data covering the last 4 quarters:
        operational metrics, financial metrics, management commentary,
        subsidiary updates, flags, and cross-quarter narrative themes.
        Falls back to v1 extraction if v2 doesn't exist.

        When called WITHOUT section_filter: returns a compact table of contents
        (quarters + which sections are populated + cross-quarter narrative) — NO
        per-quarter payload. Keeps first-call response under ~4KB. When Q&A
        entries carry topic tags, TOC also includes qa_topics_by_quarter so the
        agent can drill by topic.

        When called WITH section_filter (e.g. 'operational_metrics'): returns that
        section's content across all quarters. Each section is ~5-15KB — well
        within the agent's readable window.

        Optional narrowing:
          - quarter='FY26-Q3' restricts every path to a single quarter.
          - qa_topics=['margins','guidance'] returns only Q&A exchanges whose
            topics intersect with the requested set (implies section_filter=
            'qa_session'). Falls back to the full Q&A with a warning when the
            extraction predates topic tagging.

        QA sessions are trimmed to questions + notable flags only (+ topics when
        present). key_numbers_mentioned is dropped (redundant with operational_metrics).
        """
        import json
        from pathlib import Path

        # qa_topics implies Q&A drill-down — resolve conflict / default early.
        if qa_topics:
            if section_filter and section_filter != "qa_session":
                return {
                    "error": "qa_topics only applies to section_filter='qa_session'",
                    "hint": "Drop section_filter (or set it to 'qa_session') when using qa_topics",
                }
            section_filter = "qa_session"

        vault = Path.home() / "vault" / "stocks" / symbol.upper() / "fundamentals"
        data = None
        for filename in ["concall_extraction_v2.json", "concall_extraction.json"]:
            path = vault / filename
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["_source_file"] = filename
                    break
                except (json.JSONDecodeError, OSError):
                    continue
        if data is None:
            return {"error": f"No concall extraction found for {symbol}", "hint": "Run concall pipeline first"}

        # Narrow to a single quarter early when requested — trims every downstream path.
        if quarter:
            wanted = quarter.upper().replace(" ", "")
            matched = [
                q for q in data.get("quarters", [])
                if (q.get("fy_quarter") or q.get("label") or "").upper().replace(" ", "") == wanted
            ]
            if not matched:
                available = [q.get("fy_quarter") or q.get("label") for q in data.get("quarters", [])]
                return {
                    "error": f"Quarter '{quarter}' not found in extraction",
                    "available_quarters": available,
                }
            data["quarters"] = matched

        # Trim verbose sections universally (these trims are always safe) + track quality.
        # quality_statuses is per-quarter parallel to missing_periods — index i of each
        # refers to the same quarter, so we can report missing_periods accurately in _meta.
        quality_statuses: list[str] = []
        quarter_labels: list[str] = []
        missing_periods: list[str] = []
        qa_topics_by_quarter: dict[str, list[str]] = {}
        any_topics_present = False
        for q in data.get("quarters", []):
            trimmed_qa = []
            quarter_topic_set: set[str] = set()
            for qa in q.get("qa_session", []):
                trimmed = {
                    "analyst": qa.get("analyst", ""),
                    "questions": qa.get("questions", []),
                    "notable": qa.get("notable", ""),
                }
                topics = qa.get("topics") or []
                if topics:
                    trimmed["topics"] = topics
                    quarter_topic_set.update(t.lower() for t in topics if t)
                    any_topics_present = True
                trimmed_qa.append(trimmed)
            q["qa_session"] = trimmed_qa
            q.pop("key_numbers_mentioned", None)
            status = q.get("extraction_status", "complete")
            quality_statuses.append(status)
            label = q.get("fy_quarter") or q.get("label") or q.get("period_ended") or ""
            quarter_labels.append(label)
            if quarter_topic_set and label:
                qa_topics_by_quarter[label] = sorted(quarter_topic_set)
            if status in ("partial", "recovered", "failed"):
                missing_periods.append(label)

        # Build extraction-quality warning (applied to both TOC and drill-down responses).
        # A quarter with "partial"/"recovered"/"failed" means the concall extraction model
        # returned prose or errored — `_build_partial_extraction` kicked in with regex-only
        # number extraction, so narrative fields are thin. Surfaces so the agent downweights.
        degraded = [s for s in quality_statuses if s in ("partial", "recovered", "failed")]
        extraction_quality_warning = (
            f"Concall extraction was degraded for {len(degraded)}/{len(quality_statuses)} "
            f"quarters (statuses: {quality_statuses}). Management commentary, guidance, "
            "and narrative fields may be thin or missing. Treat concall-derived analysis "
            "as partial — cross-check key claims against get_fundamentals or filings, "
            "and note the data limitation in the report."
        ) if degraded else None

        # _meta dict — machine-readable companion to the human-readable warning.
        # Downstream graders use this to distinguish "agent didn't cover X" from
        # "source-data couldn't support X". See C-2d.
        if not quality_statuses:
            # No quarters in file at all — empty extraction payload
            meta_status = "empty"
        elif degraded:
            meta_status = "partial"
        else:
            meta_status = "full"
        meta = {
            "extraction_status": meta_status,
            "missing_periods": missing_periods,
            "degraded_quality": meta_status == "partial",
        }

        # Targeted drill-down: return only the requested section across all quarters
        if section_filter:
            if section_filter not in self._CONCALL_SECTIONS:
                return {
                    "error": f"Unknown section '{section_filter}'",
                    "valid_sections": list(self._CONCALL_SECTIONS),
                }
            topic_filter_fallback: str | None = None
            wanted_topics = {t.lower() for t in qa_topics} if qa_topics else set()
            slices = []
            for q in data.get("quarters", []):
                section_payload = q.get(section_filter)
                if section_filter == "qa_session" and wanted_topics:
                    exchanges = section_payload or []
                    if any_topics_present:
                        section_payload = [
                            qa for qa in exchanges
                            if wanted_topics & {t.lower() for t in (qa.get("topics") or [])}
                        ]
                    else:
                        # Extraction predates topic tagging — can't filter. Return full Q&A
                        # with a warning so the agent knows to do its own pattern match.
                        topic_filter_fallback = (
                            "Q&A topic filter unavailable — this concall extraction predates "
                            "topic tagging. Returning full Q&A; filter manually on question text."
                        )
                slices.append({
                    "fy_quarter": q.get("fy_quarter", q.get("label", "")),
                    "period_ended": q.get("period_ended"),
                    section_filter: section_payload,
                })
            result = {
                "symbol": symbol.upper(),
                "section": section_filter,
                "quarters": slices,
                "cross_quarter_narrative": data.get("cross_quarter_narrative", {}) if section_filter == "management_commentary" else None,
            }
            if wanted_topics:
                result["qa_topics_requested"] = sorted(wanted_topics)
            if topic_filter_fallback:
                result["_topic_filter_warning"] = topic_filter_fallback
            if extraction_quality_warning:
                result["_extraction_quality_warning"] = extraction_quality_warning
            result["_meta"] = meta
            return result

        # Default: compact table of contents — no per-quarter payload
        toc_quarters = []
        for q in data.get("quarters", []):
            populated = [
                s for s in self._CONCALL_SECTIONS
                if q.get(s) and (len(q[s]) > 0 if isinstance(q[s], (list, dict, str)) else True)
            ]
            toc_quarters.append({
                "fy_quarter": q.get("fy_quarter", q.get("label", "")),
                "period_ended": q.get("period_ended"),
                "sections_populated": populated,
            })
        # Narrative keys only (drop full prose). Agent requests 'management_commentary'
        # via sub_section if they need the full cross-quarter narrative.
        cross = data.get("cross_quarter_narrative", {}) or {}
        narrative_keys = list(cross.keys()) if isinstance(cross, dict) else []
        toc = {
            "symbol": symbol.upper(),
            "_source_file": data.get("_source_file"),
            "quarters": toc_quarters,
            "cross_quarter_narrative_keys": narrative_keys,
            "available_sections": list(self._CONCALL_SECTIONS),
            "hint": "Call again with sub_section='<section>' for full content. Example: sub_section='operational_metrics' or 'management_commentary'. Valid sections listed in available_sections.",
        }
        if qa_topics_by_quarter:
            toc["qa_topics_by_quarter"] = qa_topics_by_quarter
            toc["hint"] += (
                " For Q&A, pass qa_topics=['margins', ...] to filter exchanges by topic "
                "(topic list per quarter in qa_topics_by_quarter)."
            )
        if extraction_quality_warning:
            toc["_extraction_quality_warning"] = extraction_quality_warning
        toc["_meta"] = meta
        return toc

    _DECK_SECTIONS = (
        "highlights",
        "segment_performance",
        "strategic_priorities",
        "outlook_and_guidance",
        "new_initiatives",
        "charts_described",
    )

    def get_deck_insights(
        self,
        symbol: str,
        section_filter: str | None = None,
        quarter: str | None = None,
        slide_topics: list[str] | None = None,
    ) -> dict:
        """Get pre-extracted investor-deck insights from the vault.

        Deck extraction runs via `flowtrack filings extract-deck`. Output lives at
        ~/vault/stocks/{SYMBOL}/fundamentals/deck_extraction.json. Covers the most
        recent N deck PDFs (typically 4 quarters).

        Without section_filter: returns a compact table of contents (quarters +
        populated sections + slide_topics_by_quarter when tagged). <4KB.

        With section_filter: returns that deck section across all quarters. Valid:
        'highlights', 'segment_performance', 'strategic_priorities',
        'outlook_and_guidance', 'new_initiatives', 'charts_described'.

        Optional narrowing:
          - quarter='FY26-Q3' narrows every path to one quarter.
          - slide_topics=['segmental','outlook'] returns only decks whose slide_topics
            intersect with the requested set — implies no specific section_filter
            (returns relevant charts_described across matching decks).
        """
        import json
        from pathlib import Path

        vault = Path.home() / "vault" / "stocks" / symbol.upper() / "fundamentals"
        path = vault / "deck_extraction.json"
        if not path.exists():
            return {
                "error": f"No deck extraction found for {symbol}",
                "hint": f"Run: flowtrack filings extract-deck -s {symbol}",
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            return {"error": f"Failed to read deck extraction for {symbol}: {e}"}

        # Narrow to a single quarter when requested.
        if quarter:
            wanted = quarter.upper().replace(" ", "")
            matched = [
                q for q in data.get("quarters", [])
                if (q.get("fy_quarter") or "").upper().replace(" ", "") == wanted
            ]
            if not matched:
                available = [q.get("fy_quarter") for q in data.get("quarters", [])]
                return {
                    "error": f"Quarter '{quarter}' not found in deck extraction",
                    "available_quarters": available,
                }
            data = {**data, "quarters": matched}

        # Track quality + topic index in one pass.
        quality_statuses: list[str] = []
        missing_periods: list[str] = []
        slide_topics_by_quarter: dict[str, list[str]] = {}
        any_topics_present = False
        for q in data.get("quarters", []):
            status = q.get("extraction_status", "complete")
            quality_statuses.append(status)
            label = q.get("fy_quarter") or ""
            if status in ("partial", "failed", "not_a_deck"):
                missing_periods.append(label)
            topics = q.get("slide_topics") or []
            if topics and label:
                slide_topics_by_quarter[label] = sorted({t.lower() for t in topics if t})
                any_topics_present = True

        degraded = [s for s in quality_statuses if s in ("partial", "failed", "not_a_deck")]
        extraction_quality_warning = (
            f"Deck extraction was degraded for {len(degraded)}/{len(quality_statuses)} "
            f"quarters (statuses: {quality_statuses}). Some decks may be corporate "
            "notices rather than real presentations, or Docling/Claude extraction failed. "
            "Treat deck-derived analysis as partial — cross-check against concall_insights."
        ) if degraded else None

        if not quality_statuses:
            meta_status = "empty"
        elif degraded:
            meta_status = "partial"
        else:
            meta_status = "full"
        meta = {
            "extraction_status": meta_status,
            "missing_periods": missing_periods,
            "degraded_quality": meta_status == "partial",
        }

        # slide_topics filter — narrow to quarters whose slide_topics intersect,
        # implies agent wants the charts_described section from those quarters.
        wanted_topics = {t.lower() for t in slide_topics} if slide_topics else set()
        topic_filter_fallback: str | None = None

        if wanted_topics and not any_topics_present:
            topic_filter_fallback = (
                "Slide-topic filter unavailable — this deck extraction predates topic "
                "tagging. Returning all quarters; filter manually via section_filter."
            )

        # Targeted drill-down: one section across all (filtered) quarters.
        if section_filter:
            if section_filter not in self._DECK_SECTIONS:
                return {
                    "error": f"Unknown section '{section_filter}'",
                    "valid_sections": list(self._DECK_SECTIONS),
                }
            slices = []
            for q in data.get("quarters", []):
                if wanted_topics and any_topics_present:
                    q_topics = {t.lower() for t in (q.get("slide_topics") or [])}
                    if not (wanted_topics & q_topics):
                        continue
                slices.append({
                    "fy_quarter": q.get("fy_quarter", ""),
                    "period_ended": q.get("period_ended"),
                    section_filter: q.get(section_filter),
                })
            result = {
                "symbol": symbol.upper(),
                "section": section_filter,
                "quarters": slices,
            }
            if wanted_topics:
                result["slide_topics_requested"] = sorted(wanted_topics)
            if topic_filter_fallback:
                result["_topic_filter_warning"] = topic_filter_fallback
            if extraction_quality_warning:
                result["_extraction_quality_warning"] = extraction_quality_warning
            result["_meta"] = meta
            return result

        # Default: TOC (no per-quarter payload).
        toc_quarters = []
        for q in data.get("quarters", []):
            populated = [
                s for s in self._DECK_SECTIONS
                if q.get(s) and (len(q[s]) > 0 if isinstance(q[s], (list, dict, str)) else True)
            ]
            toc_quarters.append({
                "fy_quarter": q.get("fy_quarter", ""),
                "period_ended": q.get("period_ended"),
                "sections_populated": populated,
                "extraction_status": q.get("extraction_status", "complete"),
            })
        toc = {
            "symbol": symbol.upper(),
            "source_file": "deck_extraction.json",
            "quarters": toc_quarters,
            "available_sections": list(self._DECK_SECTIONS),
            "hint": (
                "Call get_deck_insights(sub_section='<section>') to drill in. "
                "Pass quarter='FY26-Q3' to narrow. Pass slide_topics=['segmental',...] "
                "to filter quarters by slide topics."
            ),
        }
        if slide_topics_by_quarter:
            toc["slide_topics_by_quarter"] = slide_topics_by_quarter
        if extraction_quality_warning:
            toc["_extraction_quality_warning"] = extraction_quality_warning
        toc["_meta"] = meta
        return toc

    _AR_SECTIONS = (
        "chairman_letter",
        "mdna",
        "risk_management",
        "auditor_report",
        "corporate_governance",
        "brsr",
        "related_party",
        "segmental",
        "notes_to_financials",
        "financial_statements",
    )

    def get_annual_report(
        self,
        symbol: str,
        year: str | None = None,
        section: str | None = None,
        include_cross_year: bool = True,
    ) -> dict:
        """Get pre-extracted annual report insights from the vault.

        Extraction runs via `flowtrack filings extract-ar`. Per-year JSONs land at
        ~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY??.json
        Cross-year narrative at annual_report_cross_year.json.

        Without year or section: returns TOC — available years + which sections
        were extracted per year + cross-year narrative summary. <5KB.

        With year='FY25': TOC for that single year + section sizes.

        With section: drills into that section across available years. Valid sections:
        'chairman_letter', 'mdna', 'risk_management', 'auditor_report',
        'corporate_governance', 'brsr', 'related_party', 'segmental',
        'notes_to_financials', 'financial_statements'.

        With year + section: single section for single year.
        """
        import json
        from pathlib import Path

        vault = Path.home() / "vault" / "stocks" / symbol.upper() / "fundamentals"
        if not vault.exists():
            return {
                "error": f"No AR extractions found for {symbol}",
                "hint": f"Run: flowtrack filings extract-ar -s {symbol}",
            }

        # Discover per-year JSONs on disk.
        year_files = sorted(
            vault.glob("annual_report_FY*.json"),
            key=lambda p: p.stem,
            reverse=True,
        )
        if not year_files:
            return {
                "error": f"No AR extractions found for {symbol}",
                "hint": f"Run: flowtrack filings extract-ar -s {symbol}",
            }

        per_year: list[dict] = []
        for f in year_files:
            try:
                per_year.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue

        # Year filter.
        if year:
            wanted = year.upper().replace(" ", "")
            matched = [y for y in per_year if (y.get("fiscal_year") or "").upper() == wanted]
            if not matched:
                available = [y.get("fiscal_year") for y in per_year]
                return {
                    "error": f"Year '{year}' not found in extractions",
                    "available_years": available,
                }
            per_year = matched

        # Section validation.
        if section and section not in self._AR_SECTIONS:
            return {
                "error": f"Unknown section '{section}'",
                "valid_sections": list(self._AR_SECTIONS),
            }

        # Cross-year narrative (optional include).
        cross_data: dict = {}
        cross_path = vault / "annual_report_cross_year.json"
        if include_cross_year and cross_path.exists() and not (year or section):
            try:
                cross_data = json.loads(cross_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                cross_data = {}

        # Track quality across (filtered) years. Mirrors concall/deck pattern.
        # A year is "degraded" if extraction_status is partial/recovered/failed,
        # OR if more than 3 sections returned section_not_found_or_empty / extraction_error
        # (section-level failures within an otherwise "complete" run).
        quality_statuses: list[str] = []
        missing_periods: list[str] = []
        for y in per_year:
            status = y.get("extraction_status") or "complete"
            label = y.get("fiscal_year") or ""
            section_failures = 0
            for s in self._AR_SECTIONS:
                v = y.get(s)
                if isinstance(v, dict) and (
                    v.get("status") == "section_not_found_or_empty"
                    or "extraction_error" in v
                ):
                    section_failures += 1
            year_degraded = status in ("partial", "recovered", "failed") or section_failures > 3
            # Normalize the status we record so meta_status logic below is consistent —
            # if section-level failures push us over the threshold but the file says
            # "complete", surface that as "partial" in the per-year status list.
            if year_degraded and status not in ("partial", "recovered", "failed"):
                quality_statuses.append("partial")
            else:
                quality_statuses.append(status)
            if year_degraded and label:
                missing_periods.append(label)

        degraded = [s for s in quality_statuses if s in ("partial", "recovered", "failed")]
        extraction_quality_warning = (
            f"AR extraction was degraded for {len(degraded)}/{len(quality_statuses)} "
            f"years (statuses: {quality_statuses}). Auditor KAMs, related-party tables, "
            "and notes detail may be thin. Treat AR-derived analysis as partial and "
            "flag the data limitation."
        ) if degraded else None

        if not quality_statuses:
            meta_status = "empty"
        elif degraded:
            meta_status = "partial"
        else:
            meta_status = "full"
        meta = {
            "extraction_status": meta_status,
            "missing_periods": missing_periods,
            "degraded_quality": meta_status == "partial",
        }

        # Drill-down: one section across (filtered) years.
        if section:
            slices = [
                {"fiscal_year": y.get("fiscal_year"), section: y.get(section)}
                for y in per_year
            ]
            result = {
                "symbol": symbol.upper(),
                "section": section,
                "years": slices,
            }
            if extraction_quality_warning:
                result["_extraction_quality_warning"] = extraction_quality_warning
            result["_meta"] = meta
            return result

        # Default: TOC.
        toc_years = []
        for y in per_year:
            populated = [
                s for s in self._AR_SECTIONS
                if y.get(s) and not isinstance(y.get(s), dict) or
                (isinstance(y.get(s), dict) and y.get(s) and "section_not_found_or_empty" not in str(y.get(s)))
            ]
            # Tighter: only include sections whose payload has real content.
            populated = []
            for s in self._AR_SECTIONS:
                v = y.get(s)
                if not v:
                    continue
                if isinstance(v, dict) and v.get("status") == "section_not_found_or_empty":
                    continue
                if isinstance(v, dict) and "extraction_error" in v:
                    continue
                populated.append(s)
            toc_years.append({
                "fiscal_year": y.get("fiscal_year"),
                "extraction_status": y.get("extraction_status", "unknown"),
                "pages_chars": y.get("pages_chars"),
                "sections_populated": populated,
                "section_index": y.get("section_index", []),
            })

        toc = {
            "symbol": symbol.upper(),
            "years_on_file": [y["fiscal_year"] for y in toc_years],
            "years": toc_years,
            "available_sections": list(self._AR_SECTIONS),
            "hint": (
                "Call with section='<name>' to drill into one section across years "
                "(e.g. section='auditor_report' for KAMs). Pass year='FY25' to narrow. "
                "Valid sections in available_sections."
            ),
        }
        if cross_data.get("narrative"):
            toc["cross_year_narrative"] = cross_data["narrative"]
            toc["cross_year_years"] = cross_data.get("years_analyzed", [])
        if extraction_quality_warning:
            toc["_extraction_quality_warning"] = extraction_quality_warning
        toc["_meta"] = meta
        return toc

    def get_sector_kpis(self, symbol: str, kpi_key: str | None = None) -> dict:
        """Extract sector-specific KPIs from concall data using canonical field names.

        Reads the concall extraction JSON, identifies the company's sector, and
        pulls out KPIs matching the canonical keys defined in sector_kpis.py.

        When called WITHOUT kpi_key: returns a compact table of contents listing
        available KPIs + coverage — no per-quarter payload. This is ~2KB and lets
        the agent discover canonical keys before drilling in.

        When called WITH kpi_key: returns ONLY that KPI's full per-quarter timeline.
        Use this to avoid the 50+KB payload that full dumps produce.
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
        # Alias table: canonical_key -> list of accepted source-field variants.
        # Handles naming drift from the concall extractor (e.g. concall writes
        # 'domestic_nim_pct' but schema canonical is 'net_interest_margin_pct').
        key_aliases: dict[str, list[str]] = {k["key"]: list(k.get("aliases") or []) for k in kpi_defs}

        # Read concall extraction — pull operational_metrics directly via the
        # filtered path. get_concall_insights() now returns a TOC by default, so
        # we explicitly request the section we need.
        op_slice = self.get_concall_insights(symbol, section_filter="operational_metrics")
        if isinstance(op_slice, dict) and "error" in op_slice:
            return {"error": op_slice["error"], "sector": sector, "kpis_expected": [k["key"] for k in kpi_defs]}

        quarters = op_slice.get("quarters", [])
        if not quarters:
            return {"error": "No quarterly data in concall extraction", "sector": sector}

        # BFSI fallback: when structured operational_metrics is empty for a quarter,
        # the concall extractor sometimes puts asset-quality / capital ratios into
        # financial_metrics.consolidated (or .standalone). Pre-load that slice so we
        # can consult it in the per-key matching loop below.
        # Applies to the `banks` sector only — other sectors have different
        # financial_metrics semantics and would create false positives.
        fin_metrics_by_quarter: dict[str, dict] = {}
        bfsi_fallback_enabled = sector == "banks"
        if bfsi_fallback_enabled:
            fin_slice = self.get_concall_insights(symbol, section_filter="financial_metrics")
            if isinstance(fin_slice, dict) and "error" not in fin_slice:
                for fq in fin_slice.get("quarters", []) or []:
                    q_label = fq.get("fy_quarter", fq.get("label", ""))
                    fm = fq.get("financial_metrics") or {}
                    if not isinstance(fm, dict):
                        continue
                    # Flatten consolidated + standalone into a single dict for lookup.
                    # Consolidated takes precedence when the same key appears in both.
                    flat: dict = {}
                    for src in ("standalone", "consolidated"):
                        block = fm.get(src) or {}
                        if isinstance(block, dict):
                            flat.update(block)
                    if flat:
                        fin_metrics_by_quarter[q_label] = flat

        # Extract KPIs from each quarter's operational_metrics
        kpi_timeline: dict[str, list[dict]] = {k: [] for k in canonical_keys}

        for q in quarters:
            quarter_label = q.get("fy_quarter", q.get("label", ""))
            op_metrics = q.get("operational_metrics") or {}
            key_numbers = {}  # key_numbers_mentioned dropped in trimming; fuzzy match falls back to op_metrics only
            fin_metrics = fin_metrics_by_quarter.get(quarter_label, {}) if bfsi_fallback_enabled else {}

            # Direct match on canonical keys
            for canonical_key in canonical_keys:
                value = None
                context = None
                matched_via = None

                # 1. Direct match on canonical key in operational_metrics
                if canonical_key in op_metrics:
                    entry = op_metrics[canonical_key]
                    if isinstance(entry, dict):
                        value = entry.get("value")
                        context = entry.get("context")
                    else:
                        value = entry
                    if value is not None:
                        matched_via = "canonical"

                # 2. Alias match — handles concall extractor naming drift
                if value is None:
                    for alias in key_aliases.get(canonical_key, []):
                        if alias in op_metrics:
                            entry = op_metrics[alias]
                            if isinstance(entry, dict):
                                value = entry.get("value")
                                context = entry.get("context")
                            else:
                                value = entry
                            if value is not None:
                                matched_via = f"alias:{alias}"
                                break

                # 3. key_numbers_mentioned fallback (legacy, usually empty)
                if value is None and canonical_key in key_numbers:
                    value = key_numbers[canonical_key]
                    matched_via = "key_numbers"

                # 4. Fuzzy match: try without unit suffix and common variations
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
                            matched_via = f"fuzzy:{src_key}"
                            break

                # 5. BFSI financial_metrics fallback — for banks only, when the
                # structured KPI store (operational_metrics) is empty for this quarter,
                # look into financial_metrics.{consolidated,standalone}. Tries canonical
                # key, then each alias.
                if value is None and bfsi_fallback_enabled and fin_metrics:
                    candidate_keys = [canonical_key] + list(key_aliases.get(canonical_key, []))
                    for ck in candidate_keys:
                        if ck in fin_metrics:
                            entry = fin_metrics[ck]
                            if isinstance(entry, dict):
                                value = entry.get("value")
                                context = entry.get("context")
                            else:
                                value = entry
                            if value is not None:
                                matched_via = f"financial_metrics:{ck}"
                                break

                if value is not None:
                    entry = {"quarter": quarter_label, "value": value}
                    if context:
                        entry["context"] = context
                    if matched_via and matched_via != "canonical":
                        entry["matched_via"] = matched_via
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

        # Cross-quarter metric trajectories — pull from the raw concall file since
        # op_slice only has operational_metrics. Read directly, inexpensive.
        import json as _json
        from pathlib import Path as _Path
        trajectories = {}
        for _fn in ("concall_extraction_v2.json", "concall_extraction.json"):
            _p = _Path.home() / "vault" / "stocks" / symbol.upper() / "fundamentals" / _fn
            if _p.exists():
                try:
                    _raw = _json.loads(_p.read_text(encoding="utf-8"))
                    trajectories = _raw.get("cross_quarter_narrative", {}).get("metric_trajectories", {})
                    break
                except (OSError, _json.JSONDecodeError):
                    pass

        # Compute extraction-quality _meta. Signal for sector KPIs:
        # >50% of canonical KPIs missing → partial; none found → empty; else full.
        # missing_metrics lists the canonical keys that no quarter reported. Graders
        # use this to distinguish "agent ignored a metric" from "concall didn't mention it".
        total_kpis = len(kpi_defs)
        found_count = len(found_kpis)
        if found_count == 0:
            meta_status = "empty"
        elif total_kpis and (total_kpis - found_count) / total_kpis > 0.5:
            meta_status = "partial"
        else:
            meta_status = "full"
        meta = {
            "extraction_status": meta_status,
            "missing_metrics": list(missing_kpis),
            "degraded_quality": meta_status == "partial",
        }

        # Targeted drill-down: return ONLY the requested KPI's timeline
        if kpi_key:
            match = next((k for k in found_kpis if k["key"] == kpi_key), None)
            if match:
                return {
                    "symbol": symbol.upper(),
                    "sector": sector,
                    "kpi": match,
                    "trajectory": trajectories.get(kpi_key),
                    "quarters_analyzed": len(quarters),
                    "_meta": meta,
                }
            # Requested KPI exists in schema but has no values, or doesn't exist at all
            valid_keys = [k["key"] for k in kpi_defs]
            if kpi_key in valid_keys:
                return {
                    "symbol": symbol.upper(),
                    "sector": sector,
                    "kpi": kpi_key,
                    "status": "schema_valid_but_unavailable",
                    "reason": f"'{kpi_key}' is a canonical {sector} KPI but no quarter reported it",
                    "quarters_analyzed": len(quarters),
                    "_meta": meta,
                }
            return {
                "symbol": symbol.upper(),
                "sector": sector,
                "kpi": kpi_key,
                "status": "unknown_key",
                "reason": f"'{kpi_key}' is not a canonical KPI for sector '{sector}'",
                "valid_keys": valid_keys,
            }

        # Default: compact table-of-contents (no full per-quarter timelines)
        # Agent drills in with sub_section='<kpi_key>' for full data.
        toc = []
        for k in found_kpis:
            latest = k["values"][-1] if k["values"] else None
            toc.append({
                "key": k["key"],
                "label": k["label"],
                "unit": k["unit"],
                "coverage": f"{len(k['values'])}/{len(quarters)} quarters",
                "latest_value": latest.get("value") if isinstance(latest, dict) else latest,
            })
        return {
            "symbol": symbol.upper(),
            "sector": sector,
            "industry": industry,
            "available_kpis": toc,
            "kpis_missing": missing_kpis,
            "coverage": f"{len(found_kpis)}/{len(kpi_defs)} canonical KPIs have values",
            "quarters_analyzed": len(quarters),
            "hint": "Call again with sub_section='<kpi_key>' for full per-quarter timeline + context. Example: sub_section='gross_npa_pct'",
            "_meta": meta,
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
        Plan v2 §7 E12: passes resolved sector token to build_projections for
        sector-aware D&A routing.
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

        # Plan v2 §7 E12: resolve industry → sector token for D&A routing.
        industry_token = self._resolve_industry_token(symbol)

        return build_projections(
            annual,
            adjustment_factor=factor,
            pe_multiples=pe_multiples,
            shares_override=current_shares or None,
            industry=industry_token,
        )

    def _resolve_industry_token(self, symbol: str) -> str | None:
        """Map symbol's industry classification to a normalized token used by
        projections._resolve_da_strategy (e.g. 'bfsi', 'platform', 'manufacturing').
        Plan v2 §7 E12.
        """
        if self._is_bfsi(symbol):
            return "bfsi"
        if self._is_insurance(symbol):
            return "insurance"
        if self._is_realestate(symbol):
            return "real_estate"
        if self._is_metals(symbol):
            return "metals"
        if self._is_it_services(symbol):
            return "it_services"
        raw = (self._get_industry(symbol) or "").lower()
        if not raw or raw == "unknown":
            return None
        if "auto" in raw:
            return "auto"
        if "cement" in raw:
            return "cement"
        if "platform" in raw or "internet" in raw or "ecommerce" in raw or "marketplace" in raw:
            return "platform"
        # Generic manufacturing umbrella: chemicals, industrials, consumer durables, etc.
        if any(kw in raw for kw in ("manufactur", "industrial", "chemical", "machinery", "capital goods")):
            return "manufacturing"
        return None

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

        Each horizon's start↔end pair is checked against MEDIUM+ data_quality_flags;
        any horizon that spans a flag boundary returns null and the dropped flag
        is reported in `effective_window.narrowed_due_to`. Spot ratios that don't
        chain across years (latest values) are unaffected.
        """
        annual = self.get_annual_financials(symbol, years=11)
        if len(annual) < 2:
            return {"error": "Need at least 2 years of financials"}

        # Flags whose curr_fy falls anywhere in the loaded history. A horizon
        # that starts at-or-before the flag's prior_fy and ends at-or-after the
        # flag's curr_fy spans the break.
        all_flags = self.get_data_quality_flags(symbol, min_severity="MEDIUM")
        flag_curr_fys = {f["curr_fy"] for f in all_flags
                         if f["curr_fy"] in {r["fiscal_year_end"] for r in annual}}

        def _spans_flag(latest_fy: str, oldest_fy: str) -> list[str]:
            """Return curr_fys of flags between (oldest, latest] inclusive of latest."""
            return [c for c in flag_curr_fys if oldest_fy < c <= latest_fy]

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

        # EBITDA and FCF are meaningless for BFSI (interest is core revenue/cost, not opex;
        # no inventory/receivables/capex cycle). Suppress entirely — the agent shouldn't
        # see these rows at all. Including them has caused hallucinations ("EBITDA as NII
        # proxy") in past eval runs.
        metric_defs = [
            ("revenue", lambda d, _: _get(d, "revenue")),
            ("net_income", lambda d, _: _get(d, "net_income")),
            ("eps", lambda d, _: _get(d, "eps")),
        ]
        if not is_bfsi:
            metric_defs.insert(1, ("ebitda", lambda d, _: _ebitda(d)))
            metric_defs.append(("fcf", lambda d, prev: _fcf(d, prev)))

        # Per-horizon flag check — once per horizon, reused across metrics.
        latest_fy = annual[0]["fiscal_year_end"]
        horizon_breaks: dict[str, list[str]] = {}  # "1y" -> [flag curr_fys]
        for label, idx in (("1y", 1), ("3y", 3), ("5y", 5), ("10y", 10)):
            if idx < len(annual):
                horizon_breaks[label] = _spans_flag(latest_fy, annual[idx]["fiscal_year_end"])

        metrics = {}
        for label, extract in metric_defs:
            values = []
            for i, d in enumerate(annual):
                prev = annual[i + 1] if i + 1 < n else None
                values.append(extract(d, prev))

            row = {}
            if len(values) >= 2 and values[0] and values[1] and not horizon_breaks.get("1y"):
                row["1y"] = _yoy(values[0], values[1])
            if len(values) >= 4 and values[0] and values[3] and not horizon_breaks.get("3y"):
                row["3y"] = _cagr(values[0], values[3], 3)
            if len(values) >= 6 and values[0] and values[5] and not horizon_breaks.get("5y"):
                row["5y"] = _cagr(values[0], values[5], 5)
            if len(values) >= 11 and values[0] and values[10] and not horizon_breaks.get("10y"):
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

        # Build effective_window: which horizons were nullified, and why.
        narrowed_due_to: list[dict] = []
        suppressed_horizons: list[str] = []
        for h, breaks in horizon_breaks.items():
            if breaks:
                suppressed_horizons.append(h)
                for curr in breaks:
                    f = next((x for x in all_flags if x["curr_fy"] == curr), None)
                    if f is not None:
                        narrowed_due_to.append({
                            "prior_fy": f["prior_fy"], "curr_fy": f["curr_fy"],
                            "line": f["line"], "severity": f["severity"],
                            "horizon": h,
                        })

        return {
            "symbol": symbol,
            "years_available": n,
            "cagrs": metrics,
            "growth_trajectory": trajectory,
            "effective_window": {
                "suppressed_horizons": suppressed_horizons,
                "narrowed_due_to": narrowed_due_to,
            },
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
        """Piotroski F-Score (0-9): profitability, leverage, operating efficiency.

        Most criteria compare T vs T-1. If a MEDIUM+ data_quality_flag falls at
        the curr_fy of the most-recent annual row, the (T, T-1) pair crosses a
        bucketing break and the score is meaningless. We shift to the latest
        unflagged consecutive pair and report the shift in `effective_window`.
        """
        from flowtracker.data_quality import longest_unflagged_window

        # Pull more history so we have shift-back room when the latest pair is flagged.
        annuals = self.get_annual_financials(symbol, years=5)
        if len(annuals) < 2:
            return {"error": f"Need at least 2 years of data, got {len(annuals)}"}

        # Narrow to the longest unflagged segment; require 2 consecutive years.
        flags = self.get_data_quality_flags(symbol, min_severity="MEDIUM")
        relevant = [f for f in flags if f["curr_fy"] in {a["fiscal_year_end"] for a in annuals}]
        segment, dropped = longest_unflagged_window(annuals, relevant)
        effective_window = {
            "start_fy": segment[1]["fiscal_year_end"] if len(segment) >= 2 else None,
            "end_fy": segment[0]["fiscal_year_end"] if segment else None,
            "n_years": len(segment),
            "narrowed_due_to": [
                {"prior_fy": f["prior_fy"], "curr_fy": f["curr_fy"],
                 "line": f["line"], "severity": f["severity"]}
                for f in dropped
            ],
        }
        if len(segment) < 2:
            return {
                "error": "All recent year-pairs cross MEDIUM+ reclassification flags; F-score abstained.",
                "effective_window": effective_window,
            }
        t, t1 = segment[0], segment[1]  # t = latest unflagged, t1 = prior
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
            "effective_window": effective_window,
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

        FCF formula (canonical, also used by get_fcf_yield):
            capex_t = (NetBlock_t - NetBlock_{t-1})
                    + (CWIP_t   - CWIP_{t-1})
                    + Depreciation_t        # PP&E additions, derived from BS deltas
            FCF_t   = CFO_t - capex_t

        Both per-year FCF (`per_year_fcf`) and the cumulative figure
        (`cumulative.fcf`) are returned explicitly so agents do not have to
        re-derive FCF from `cumulative.cfo - cumulative.net_capex` (which
        could otherwise drift from `get_fcf_yield` / `get_cash_flow`-derived
        FCF and cause definitional inconsistency in the report).
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

        # Capex: delta_Net_Block + delta_CWIP + Depreciation. Same formula
        # used in get_fcf_yield — keep them in lockstep so FCF figures
        # reconcile between capital_allocation and fcf_yield endpoints.
        total_gross_capex = 0
        total_divestments = 0
        per_year_fcf: list[dict] = []
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
                cfo_y = d.get("cfo", 0) or 0
                fcf_y = cfo_y - net_capex
                per_year_fcf.append({
                    "fiscal_year": d.get("fiscal_year_end", ""),
                    "cfo": round(cfo_y, 2),
                    "capex": round(net_capex, 2),
                    "fcf": round(fcf_y, 2),
                })
        total_capex = total_gross_capex - total_divestments
        # Cumulative FCF: sum of per-year (CFO - capex) — only across years
        # for which a previous-year row exists (i.e., capex computable).
        total_fcf = sum(y["fcf"] for y in per_year_fcf)

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
            "fcf_formula": "FCF = CFO - capex; capex = delta(NetBlock) + delta(CWIP) + Depreciation",
            "cumulative": {
                "cfo": round(total_cfo, 2),
                "gross_capex": round(total_gross_capex, 2),
                "divestments": round(total_divestments, 2),
                "net_capex": round(total_capex, 2),
                "fcf": round(total_fcf, 2),
                "dividends": round(total_dividends, 2),
                "residual_cash_acquisitions": round(residual, 2),
                "capex_pct_of_cfo": round(total_gross_capex / total_cfo * 100, 1) if total_cfo > 0 else None,
                "dividends_pct_of_cfo": round(total_dividends / total_cfo * 100, 1) if total_cfo > 0 else None,
                "fcf_pct_of_cfo": round(total_fcf / total_cfo * 100, 1) if total_cfo > 0 else None,
            },
            "per_year_fcf": per_year_fcf,
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
        """Common size P&L — all items as % of revenue (or Total Income for BFSI).

        Margin walks ("OPM expanded 200bps over 3yr") are the canonical use case.
        If MEDIUM+ data_quality_flags overlap the requested 10yr window, the result
        is narrowed to the longest unbroken segment so the walk doesn't span a
        bucketing change. The dropped boundary is reported in `effective_window`.
        """
        from flowtracker.data_quality import longest_unflagged_window

        annual = self.get_annual_financials(symbol, years=10)
        if not annual:
            return {"error": "No annual financial data"}

        # Narrow to longest unflagged segment.
        flags = self.get_data_quality_flags(symbol, min_severity="MEDIUM")
        relevant = [f for f in flags if f["curr_fy"] in {a["fiscal_year_end"] for a in annual}]
        annual, dropped = longest_unflagged_window(annual, relevant)
        effective_window = {
            "start_fy": annual[-1]["fiscal_year_end"] if annual else None,
            "end_fy": annual[0]["fiscal_year_end"] if annual else None,
            "n_years": len(annual),
            "narrowed_due_to": [
                {"prior_fy": f["prior_fy"], "curr_fy": f["curr_fy"],
                 "line": f["line"], "severity": f["severity"]}
                for f in dropped
            ],
        }

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
            "effective_window": effective_window,
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

        # --- Asset quality from concall (banks only — NBFCs use stage_3_assets via sector_kpis) ---
        asset_quality = self._extract_bfsi_asset_quality(symbol)

        result = {"is_bfsi": True, "years": years_data}
        if asset_quality:
            result["asset_quality"] = asset_quality
        return result

    # --- BFSI peer compare ---

    # Canonical keys the BFSI peer-compare surfaces per bank. Chosen for
    # peer-ranking utility: NIM (profitability of core book), GNPA (credit
    # discipline), cost-to-income (operating leverage).
    _BFSI_PEER_COMPARE_KEYS = ("nim_pct", "gnpa_pct", "cost_to_income_pct")

    def get_bfsi_peer_metrics(self, symbol: str) -> dict:
        """BFSI peer-compare: subject + peers with nim_pct / gnpa_pct / cost_to_income_pct.

        Returns {subject, peers, peer_count, keys}. Each entry contains the three
        canonical peer-compare keys when resolvable. NIM and cost-to-income are
        computed from annual financials via `get_bfsi_metrics`; GNPA is lifted
        from the latest concall via `get_sector_kpis(sub_section='gross_npa_pct')`.

        Non-BFSI subject → {skipped: true, reason: ...}. Peers that are non-BFSI
        are filtered out silently.
        """
        if not self._is_bfsi(symbol):
            return {"skipped": True, "reason": f"{symbol} is not a BFSI stock"}
        if self._is_insurance(symbol):
            return {"skipped": True, "reason": "Insurance uses a different KPI framework"}

        def _row_for(sym: str) -> dict | None:
            """Build a single peer-compare row. Returns None if nothing resolvable."""
            if not self._is_bfsi(sym) or self._is_insurance(sym):
                return None
            row: dict = {"symbol": sym}
            # NIM + cost_to_income from computed annual financials (latest year).
            try:
                bfsi = self.get_bfsi_metrics(sym)
            except Exception:
                bfsi = {}
            years = (bfsi or {}).get("years") or []
            if years:
                latest = years[-1]
                if latest.get("nim_pct") is not None:
                    row["nim_pct"] = latest["nim_pct"]
                if latest.get("cost_to_income_pct") is not None:
                    row["cost_to_income_pct"] = latest["cost_to_income_pct"]
                row["fiscal_year"] = latest.get("fiscal_year")
            # GNPA from latest concall quarter via structured KPI lookup.
            try:
                gnpa_resp = self.get_sector_kpis(sym, kpi_key="gross_npa_pct")
            except Exception:
                gnpa_resp = {}
            if isinstance(gnpa_resp, dict) and "kpi" in gnpa_resp:
                kpi = gnpa_resp["kpi"]
                values = kpi.get("values") if isinstance(kpi, dict) else None
                if values:
                    latest_q = values[-1]
                    if isinstance(latest_q, dict) and latest_q.get("value") is not None:
                        row["gnpa_pct"] = latest_q["value"]
                        row["gnpa_quarter"] = latest_q.get("quarter")
            # Only return rows that resolved at least one peer-compare key.
            has_any = any(k in row for k in self._BFSI_PEER_COMPARE_KEYS)
            return row if has_any else None

        subject_row = _row_for(symbol) or {"symbol": symbol}

        peers = self._store.get_peers(symbol)
        peer_rows: list[dict] = []
        for p in peers:
            psym = p.get("peer_symbol") or p.get("peer_name")
            if not psym or psym == symbol:
                continue
            row = _row_for(psym)
            if row:
                peer_rows.append(row)

        return {
            "subject": subject_row,
            "peers": peer_rows,
            "peer_count": len(peer_rows),
            "keys": list(self._BFSI_PEER_COMPARE_KEYS),
        }

    # Canonical asset quality keys in the concall schema (see sector_kpis.py 'banks' block).
    _BFSI_ASSET_QUALITY_KEYS = (
        "gross_npa_pct",
        "net_npa_pct",
        "provision_coverage_ratio_pct",
        "fresh_slippages_cr",
        "credit_cost_bps",
    )

    def _extract_bfsi_asset_quality(self, symbol: str) -> dict | None:
        """Lift asset quality metrics from concall operational_metrics into the
        BFSI structured response. Returns None if no concall or no asset quality
        fields present. If present but sparse, returns what exists + status hint
        (so the agent's compliance gate can mark 'attempted' honestly instead of
        punting to open questions).
        """
        try:
            concall = self.get_concall_insights(symbol)
        except Exception:
            return None
        if not isinstance(concall, dict) or "error" in concall:
            return None

        # After our refactor, unfiltered get_concall_insights returns a TOC only.
        # Pull the full operational_metrics slice explicitly for the lift.
        op_slice = self.get_concall_insights(symbol, section_filter="operational_metrics")
        if not isinstance(op_slice, dict) or "quarters" not in op_slice:
            return None

        per_quarter: dict[str, list[dict]] = {k: [] for k in self._BFSI_ASSET_QUALITY_KEYS}
        for q in op_slice.get("quarters", []):
            quarter_label = q.get("fy_quarter", "")
            op_metrics = q.get("operational_metrics", {}) or {}
            if not isinstance(op_metrics, dict):
                continue
            for key in self._BFSI_ASSET_QUALITY_KEYS:
                if key in op_metrics:
                    raw = op_metrics[key]
                    if isinstance(raw, dict):
                        per_quarter[key].append({
                            "quarter": quarter_label,
                            "value": raw.get("value"),
                            "context": raw.get("context"),
                        })
                    elif raw is not None:
                        per_quarter[key].append({"quarter": quarter_label, "value": raw})

        found = {k: v for k, v in per_quarter.items() if v}
        if not found:
            return {
                "status": "not_captured_in_concall_extraction",
                "hint": "Call get_sector_kpis(sub_section='gross_npa_pct') or inspect concall narrative via get_concall_insights(sub_section='management_commentary') — asset quality may be in prose rather than structured metrics for this filing.",
                "canonical_keys_expected": list(self._BFSI_ASSET_QUALITY_KEYS),
            }
        return {
            "source": "concall operational_metrics",
            "metrics": found,
            "missing_keys": [k for k in self._BFSI_ASSET_QUALITY_KEYS if k not in found],
        }

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

    @staticmethod
    def _compute_ebitda_from_row(row: dict) -> float:
        """Compute EBITDA from an annual financials row with a robust fallback.

        Preferred: operating_profit + depreciation (EBIT + D&A).
        Fallback (when operating_profit is missing — the common case for
        Screener-sourced annual data across metals/telecom/IT/FMCG/financials):
        bottom-up reconstruction as net_income + tax + interest + depreciation.
        This mirrors the approach used in projections.py and get_fair_value.

        Without this fallback, ``0 + depreciation`` is returned, causing EBITDA
        to equal depreciation — the E1 bug in plans/post-eval-fix-plan.md that
        affected metals/telecom Net Debt/EBITDA and EV/EBITDA calculations.
        """
        dep = row.get("depreciation", 0) or 0
        op = row.get("operating_profit")
        if op is not None:
            return op + dep
        ni = row.get("net_income", 0) or 0
        tax = row.get("tax", 0) or 0
        interest = row.get("interest", 0) or 0
        return ni + tax + interest + dep

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
            borrowings = row.get("borrowings", 0) or 0
            cash = row.get("cash_and_bank", 0) or 0
            revenue = row.get("revenue", 0) or 0

            ebitda = self._compute_ebitda_from_row(row)
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
            borrowings = row.get("borrowings", 0) or 0
            cash = row.get("cash_and_bank", 0) or 0
            revenue = row.get("revenue", 0) or 0
            cfo = row.get("cfo", 0) or 0
            cfi = row.get("cfi", 0) or 0

            ebitda = self._compute_ebitda_from_row(row)
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

    # Plan v2 §7 E16: sub-sector / normalized-token fallback for sector index.
    # When `_SECTOR_INDEX` doesn't have a hit, normalize the industry string
    # and try this table. Final fallback is NIFTY 500 (^CRSLDX).
    _SECTOR_INDEX_FALLBACK: dict[str, str] = {
        "banks-regional": "^NSEBANK",
        "banks - regional": "^NSEBANK",
        "banks": "^NSEBANK",
        "private_bank": "^NSEBANK",
        "nbfc": "^NSEBANK",
        "credit services": "^NSEBANK",
        "reit": "NIFTY_REALTY.NS",
        "real_estate": "NIFTY_REALTY.NS",
        "real estate - development": "NIFTY_REALTY.NS",
        "fmcg": "^CNXFMCG",
        "it_services": "^CNXIT",
        "information technology services": "^CNXIT",
        "software - application": "^CNXIT",
        "software - infrastructure": "^CNXIT",
        "pharma": "^CNXPHARMA",
        "pharmaceuticals": "^CNXPHARMA",
        "drug manufacturers - specialty & generic": "^CNXPHARMA",
        "metals": "NIFTY_METAL.NS",
        "steel": "NIFTY_METAL.NS",
        "aluminum": "NIFTY_METAL.NS",
        "auto": "NIFTY_AUTO.NS",
        "auto components": "NIFTY_AUTO.NS",
        "automobile": "NIFTY_AUTO.NS",
        "platform": "^CRSLDX",  # no dedicated index — fallback to Nifty 500
    }
    _SECTOR_INDEX_DEFAULT = "^CRSLDX"  # Nifty 500

    def _resolve_sector_index(self, industry: str | None) -> str:
        """Resolve industry → index ticker. Never returns None.

        Plan v2 §7 E16: when sub-sector / classification doesn't map directly,
        normalize and try the fallback table. Final default is Nifty 500
        ('^CRSLDX') rather than null.
        """
        if industry and industry in self._SECTOR_INDEX:
            return self._SECTOR_INDEX[industry]
        norm = (industry or "").strip().lower()
        if norm in self._SECTOR_INDEX_FALLBACK:
            return self._SECTOR_INDEX_FALLBACK[norm]
        return self._SECTOR_INDEX_DEFAULT

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

        # Get split/bonus-adjusted stock prices from DB. adj_close collapses
        # discontinuity cliffs at ex-dates; raw close produces phantom drops
        # (splits) or phantom gains (reverse splits) in multi-period returns.
        # Fall back to raw close when adj_close is NULL (pre-backfill symbols).
        conn = self._store._conn
        stock_rows = conn.execute(
            "SELECT date, COALESCE(adj_close, close) AS price FROM daily_stock_data "
            "WHERE symbol = ? ORDER BY date DESC LIMIT 400",
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
        # E16: never return null; default to Nifty 500 when sector can't be mapped.
        sector_idx = self._resolve_sector_index(industry)
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

        # stock_prices are already split/bonus-adjusted via daily_stock_data.adj_close
        # (see FlowStore.recompute_adj_close + Sprint 0 hybrid architecture).
        # No per-call adjustment needed — it's a property of the read.

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

    # --- F&O Positioning (Sprint 3) ---

    def _fno_front_expiry(self, symbol: str, trade_date: str, instrument: str = "FUTSTK") -> str | None:
        """Front (nearest non-expired) expiry for symbol+instrument on trade_date."""
        row = self._store._conn.execute(
            "SELECT MIN(expiry_date) AS e FROM fno_contracts "
            "WHERE symbol = ? AND instrument = ? AND trade_date = ? "
            "  AND expiry_date >= trade_date",
            (symbol.upper(), instrument, trade_date),
        ).fetchone()
        return row["e"] if row and row["e"] else None

    def _fno_latest_trade_date(self, symbol: str) -> str | None:
        row = self._store._conn.execute(
            "SELECT MAX(trade_date) AS d FROM fno_contracts WHERE symbol = ?",
            (symbol.upper(),),
        ).fetchone()
        return row["d"] if row and row["d"] else None

    def get_fno_positioning(self, symbol: str) -> dict | None:
        """Composite F&O positioning snapshot. Returns None for non-F&O symbols."""
        from datetime import date as _date

        symbol = symbol.upper()
        if symbol not in self._store.get_fno_eligible_stocks():
            return None

        as_of_iso = self._fno_latest_trade_date(symbol)
        empty = {
            "fno_eligible": True, "as_of_date": as_of_iso,
            "futures_positioning": {}, "options_positioning": {},
            "fii_derivative_stance": {},
            "data_freshness": {"last_trade_date": as_of_iso, "days_since_update": None},
        }
        if not as_of_iso:
            return empty
        as_of = _date.fromisoformat(as_of_iso)

        # Futures positioning
        history = self._store.get_fno_oi_history(symbol, days=90)
        latest = history[-1] if history else None
        current_oi = latest.get("open_interest") if latest else None
        oi_pct = self._store.get_oi_percentile(symbol, as_of, lookback_days=90)

        def _pct_chg(c, b):
            return None if (c is None or not b) else (c - b) / b * 100

        oi_trend_20d = "flat"
        if len(history) >= 21 and current_oi is not None:
            chg = _pct_chg(current_oi, history[-21].get("open_interest"))
            if chg is not None:
                oi_trend_20d = "building" if chg > 10 else "unwinding" if chg < -10 else "flat"

        oi_change_5d_pct = None
        if len(history) >= 6 and current_oi is not None:
            v = _pct_chg(current_oi, history[-6].get("open_interest"))
            oi_change_5d_pct = round(v, 2) if v is not None else None

        basis = self._store.get_basis(symbol, as_of)
        basis_pct = basis["basis_pct"] if basis else None
        basis_label = None
        if basis_pct is not None:
            basis_label = ("flat" if abs(basis_pct) < 0.05 else
                           "contango" if basis_pct > 0 else "backwardation")

        futures_positioning = {
            "current_oi": current_oi,
            "oi_percentile_90d": round(oi_pct, 2) if oi_pct is not None else None,
            "oi_trend_20d": oi_trend_20d,
            "basis_pct": round(basis_pct, 4) if basis_pct is not None else None,
            "basis_label": basis_label,
            "oi_change_5d_pct": oi_change_5d_pct,
        }

        # Options positioning
        pcr = self._store.get_pcr(symbol, as_of)
        pcr_oi = pcr["pcr_oi"] if pcr else None
        pcr_oi_label = None
        if pcr_oi is not None:
            pcr_oi_label = "low" if pcr_oi < 0.7 else "neutral" if pcr_oi <= 1.0 else "high"

        max_pain_strike = atm_iv = None
        opt_expiry = self._fno_front_expiry(symbol, as_of_iso, instrument="OPTSTK")
        if opt_expiry:
            conn = self._store._conn
            pain = conn.execute(
                "SELECT strike, SUM(open_interest) AS c FROM fno_contracts "
                "WHERE symbol=? AND trade_date=? AND instrument='OPTSTK' "
                "  AND expiry_date=? AND option_type IN ('CE','PE') AND strike!=-1 "
                "GROUP BY strike ORDER BY c DESC LIMIT 1",
                (symbol, as_of_iso, opt_expiry),
            ).fetchone()
            if pain and pain["strike"] is not None:
                max_pain_strike = float(pain["strike"])
            spot_row = conn.execute(
                "SELECT close FROM daily_stock_data WHERE symbol=? AND date=?",
                (symbol, as_of_iso),
            ).fetchone()
            if spot_row and spot_row["close"]:
                atm = conn.execute(
                    "SELECT implied_volatility FROM fno_contracts "
                    "WHERE symbol=? AND trade_date=? AND instrument='OPTSTK' "
                    "  AND expiry_date=? AND option_type='CE' "
                    "  AND implied_volatility IS NOT NULL AND strike!=-1 "
                    "ORDER BY ABS(strike-?) ASC LIMIT 1",
                    (symbol, as_of_iso, opt_expiry, float(spot_row["close"])),
                ).fetchone()
                if atm and atm["implied_volatility"] is not None:
                    atm_iv = float(atm["implied_volatility"])

        options_positioning = {
            "pcr_oi": round(pcr_oi, 4) if pcr_oi is not None else None,
            "pcr_oi_label": pcr_oi_label,
            "max_pain_strike": max_pain_strike,
            "atm_iv": atm_iv,
        }

        # FII derivative stance (market-wide)
        fii_latest = self._store.get_fii_derivative_positioning(as_of, days=1)
        idx_pct = stk_pct = None
        if fii_latest and fii_latest.get("by_category"):
            cats = fii_latest["by_category"]
            idx_pct = (cats.get("idx_fut") or {}).get("net_long_pct")
            stk_pct = (cats.get("stk_fut") or {}).get("net_long_pct")

        idx_trend = "flat"
        flow = self.get_fii_derivative_flow(days=10)
        idx_series = [r["index_fut_net_long_pct"] for r in flow
                      if r.get("index_fut_net_long_pct") is not None]
        if len(idx_series) >= 6:
            delta = idx_series[0] - idx_series[5]  # newest first
            idx_trend = "rising" if delta > 2 else "falling" if delta < -2 else "flat"

        return {
            "fno_eligible": True,
            "as_of_date": as_of_iso,
            "futures_positioning": futures_positioning,
            "options_positioning": options_positioning,
            "fii_derivative_stance": {
                "index_fut_net_long_pct": round(idx_pct, 2) if idx_pct is not None else None,
                "index_fut_net_long_trend": idx_trend,
                "stock_fut_net_long_pct": round(stk_pct, 2) if stk_pct is not None else None,
            },
            "data_freshness": {
                "last_trade_date": as_of_iso,
                "days_since_update": (_date.today() - as_of).days,
            },
        }

    def get_oi_history(self, symbol: str, days: int = 90) -> list[dict]:
        """Daily OI + close + volume for front-month futures (passthrough)."""
        symbol = symbol.upper()
        if symbol not in self._store.get_fno_eligible_stocks():
            return []
        return self._store.get_fno_oi_history(symbol, days=days)

    def get_option_chain_concentration(self, symbol: str) -> dict | None:
        """Strike-wise CE/PE OI concentration for the front expiry."""
        symbol = symbol.upper()
        if symbol not in self._store.get_fno_eligible_stocks():
            return None
        as_of_iso = self._fno_latest_trade_date(symbol)
        if not as_of_iso:
            return None
        opt_expiry = self._fno_front_expiry(symbol, as_of_iso, instrument="OPTSTK")
        if not opt_expiry:
            return None

        conn = self._store._conn
        sql = ("SELECT strike, open_interest FROM fno_contracts "
               "WHERE symbol=? AND trade_date=? AND instrument='OPTSTK' "
               "  AND expiry_date=? AND option_type=? AND strike!=-1")
        ce_rows = conn.execute(sql, (symbol, as_of_iso, opt_expiry, "CE")).fetchall()
        pe_rows = conn.execute(sql, (symbol, as_of_iso, opt_expiry, "PE")).fetchall()
        if not ce_rows and not pe_rows:
            return None

        total_ce_oi = sum(int(r["open_interest"] or 0) for r in ce_rows)
        total_pe_oi = sum(int(r["open_interest"] or 0) for r in pe_rows)

        def _top(rows, total):
            if not rows:
                return None
            top = max(rows, key=lambda r: int(r["open_interest"] or 0))
            oi = int(top["open_interest"] or 0)
            return {
                "strike": float(top["strike"]),
                "oi": oi,
                "pct_of_total_ce": round(oi / total * 100, 2) if total > 0 else None,
            }

        combined: dict[float, int] = {}
        for r in list(ce_rows) + list(pe_rows):
            k = float(r["strike"])
            combined[k] = combined.get(k, 0) + int(r["open_interest"] or 0)
        max_pain = max(combined, key=combined.get) if combined else None

        return {
            "expiry_date": opt_expiry,
            "call_oi_concentration": _top(ce_rows, total_ce_oi),
            "put_oi_concentration": _top(pe_rows, total_pe_oi),
            "max_pain_strike": max_pain,
            "total_ce_oi": total_ce_oi,
            "total_pe_oi": total_pe_oi,
        }

    def get_fii_derivative_flow(self, days: int = 30) -> list[dict]:
        """Market-wide FII derivative positioning, newest-first list. Empty if no data."""
        rows = self._store._conn.execute(
            "SELECT trade_date, instrument_category, "
            "       SUM(long_oi) AS long_oi, SUM(short_oi) AS short_oi "
            "FROM fno_participant_oi WHERE participant='FII' "
            "  AND trade_date >= date('now', ? || ' days') "
            "GROUP BY trade_date, instrument_category ORDER BY trade_date DESC",
            (f"-{days}",),
        ).fetchall()
        if not rows:
            return []

        by_date: dict[str, dict] = {}
        for r in rows:
            d = r["trade_date"]
            entry = by_date.setdefault(d, {
                "trade_date": d,
                "index_fut_long_oi": 0, "index_fut_short_oi": 0,
                "index_fut_net_long_pct": None,
                "index_opt_ce_oi": 0, "index_opt_pe_oi": 0,
                "stock_fut_long_oi": 0, "stock_fut_short_oi": 0,
                "stock_fut_net_long_pct": None,
            })
            cat = r["instrument_category"]
            long_oi, short_oi = int(r["long_oi"] or 0), int(r["short_oi"] or 0)
            if cat == "idx_fut":
                entry["index_fut_long_oi"], entry["index_fut_short_oi"] = long_oi, short_oi
            elif cat == "idx_opt_ce":
                entry["index_opt_ce_oi"] = long_oi + short_oi
            elif cat == "idx_opt_pe":
                entry["index_opt_pe_oi"] = long_oi + short_oi
            elif cat == "stk_fut":
                entry["stock_fut_long_oi"], entry["stock_fut_short_oi"] = long_oi, short_oi

        for e in by_date.values():
            it = e["index_fut_long_oi"] + e["index_fut_short_oi"]
            if it > 0:
                e["index_fut_net_long_pct"] = round(e["index_fut_long_oi"] / it * 100, 2)
            st = e["stock_fut_long_oi"] + e["stock_fut_short_oi"]
            if st > 0:
                e["stock_fut_net_long_pct"] = round(e["stock_fut_long_oi"] / st * 100, 2)

        return sorted(by_date.values(), key=lambda r: r["trade_date"], reverse=True)

    def get_futures_basis(self, symbol: str, days: int = 30) -> list[dict]:
        """Spot-futures basis trajectory over N trading days (newest first)."""
        from datetime import date as _date

        symbol = symbol.upper()
        if symbol not in self._store.get_fno_eligible_stocks():
            return []

        rows = self._store._conn.execute(
            "SELECT f.trade_date, f.expiry_date, f.close AS futures_close "
            "FROM fno_contracts f INNER JOIN ("
            "  SELECT trade_date, MIN(expiry_date) AS front_expiry "
            "  FROM fno_contracts "
            "  WHERE symbol=? AND instrument='FUTSTK' AND expiry_date >= trade_date "
            "    AND trade_date >= date('now', ? || ' days') "
            "  GROUP BY trade_date"
            ") m ON f.trade_date=m.trade_date AND f.expiry_date=m.front_expiry "
            "WHERE f.symbol=? AND f.instrument='FUTSTK' "
            "ORDER BY f.trade_date DESC",
            (symbol, f"-{days}", symbol),
        ).fetchall()
        if not rows:
            return []

        out: list[dict] = []
        for r in rows:
            td, fut_close, expiry_iso = r["trade_date"], r["futures_close"], r["expiry_date"]
            spot_row = self._store._conn.execute(
                "SELECT close FROM daily_stock_data WHERE symbol=? AND date=?",
                (symbol, td),
            ).fetchone()
            if not spot_row or spot_row["close"] is None or fut_close is None:
                continue
            spot = float(spot_row["close"])
            if spot == 0:
                continue
            try:
                dte = (_date.fromisoformat(expiry_iso) - _date.fromisoformat(td)).days
            except Exception:
                dte = None
            out.append({
                "trade_date": td,
                "spot_close": spot,
                "futures_close": float(fut_close),
                "basis_pct": round((float(fut_close) - spot) / spot * 100, 4),
                "days_to_expiry": dte,
                "expiry_date": expiry_iso,
            })
        return out
