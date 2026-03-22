"""SQLite persistence for FII/DII daily flow data."""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from flowtracker.models import DailyFlow, DailyFlowPair, StreakInfo
from flowtracker.mf_models import MFMonthlyFlow, MFAUMSummary, MFDailyFlow
from flowtracker.holding_models import WatchlistEntry, ShareholdingRecord, ShareholdingChange, PromoterPledge
from flowtracker.commodity_models import CommodityPrice, GoldETFNav, GoldCorrelation
from flowtracker.scan_models import IndexConstituent, ScanSummary
from flowtracker.fund_models import QuarterlyResult, ValuationSnapshot, ValuationBand, AnnualFinancials
from flowtracker.macro_models import MacroSnapshot
from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.deals_models import BulkBlockDeal
from flowtracker.insider_models import InsiderTransaction
from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from flowtracker.mfportfolio_models import MFSchemeHolding, MFHoldingChange

_DEFAULT_DB_DIR = Path.home() / ".local" / "share" / "flowtracker"
_DEFAULT_DB_NAME = "flows.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS daily_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    buy_value REAL NOT NULL,
    sell_value REAL NOT NULL,
    net_value REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, category)
);

CREATE TABLE IF NOT EXISTS mf_monthly_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    category TEXT NOT NULL,
    sub_category TEXT NOT NULL,
    num_schemes INTEGER,
    funds_mobilized REAL,
    redemption REAL,
    net_flow REAL NOT NULL,
    aum REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month, category, sub_category)
);

CREATE TABLE IF NOT EXISTS mf_aum_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    total_aum REAL NOT NULL,
    equity_aum REAL NOT NULL,
    debt_aum REAL NOT NULL,
    hybrid_aum REAL NOT NULL,
    other_aum REAL NOT NULL,
    equity_net_flow REAL NOT NULL,
    debt_net_flow REAL NOT NULL,
    hybrid_net_flow REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month)
);

CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    company_name TEXT,
    added_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS shareholding (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    category TEXT NOT NULL,
    percentage REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end, category)
);

CREATE TABLE IF NOT EXISTS index_constituents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    index_name TEXT NOT NULL,
    company_name TEXT,
    industry TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, index_name)
);

CREATE TABLE IF NOT EXISTS promoter_pledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    pledge_pct REAL NOT NULL DEFAULT 0,
    encumbered_pct REAL NOT NULL DEFAULT 0,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS commodity_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    price REAL NOT NULL,
    unit TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, symbol)
);

CREATE TABLE IF NOT EXISTS gold_etf_nav (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    scheme_code TEXT NOT NULL,
    scheme_name TEXT,
    nav REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, scheme_code)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    symbol TEXT,
    key_info TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS quarterly_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    net_income REAL,
    ebitda REAL,
    eps REAL,
    eps_diluted REAL,
    operating_margin REAL,
    net_margin REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS valuation_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    price REAL,
    market_cap REAL,
    enterprise_value REAL,
    pe_trailing REAL,
    pe_forward REAL,
    pb_ratio REAL,
    ev_ebitda REAL,
    dividend_yield REAL,
    roe REAL,
    roa REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    free_cash_flow REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS annual_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    fiscal_year_end TEXT NOT NULL,
    revenue REAL,
    employee_cost REAL,
    other_income REAL,
    depreciation REAL,
    interest REAL,
    profit_before_tax REAL,
    tax REAL,
    net_income REAL,
    eps REAL,
    dividend_amount REAL,
    equity_capital REAL,
    reserves REAL,
    borrowings REAL,
    other_liabilities REAL,
    total_assets REAL,
    net_block REAL,
    cwip REAL,
    investments REAL,
    other_assets REAL,
    receivables REAL,
    inventory REAL,
    cash_and_bank REAL,
    num_shares REAL,
    cfo REAL,
    cfi REAL,
    cff REAL,
    net_cash_flow REAL,
    price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, fiscal_year_end)
);

CREATE TABLE IF NOT EXISTS mf_daily_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    gross_purchase REAL NOT NULL,
    gross_sale REAL NOT NULL,
    net_investment REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, category)
);

CREATE TABLE IF NOT EXISTS macro_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    india_vix REAL,
    usd_inr REAL,
    brent_crude REAL,
    gsec_10y REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);

CREATE TABLE IF NOT EXISTS daily_stock_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    prev_close REAL NOT NULL,
    volume INTEGER NOT NULL,
    turnover REAL NOT NULL,
    delivery_qty INTEGER,
    delivery_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, symbol)
);

CREATE INDEX IF NOT EXISTS idx_daily_stock_symbol ON daily_stock_data(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_stock_date ON daily_stock_data(date);

CREATE TABLE IF NOT EXISTS bulk_block_deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    deal_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    client_name TEXT,
    buy_sell TEXT,
    quantity INTEGER NOT NULL,
    price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, deal_type, symbol, client_name)
);

CREATE TABLE IF NOT EXISTS insider_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    person_name TEXT NOT NULL,
    person_category TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    value REAL NOT NULL,
    mode TEXT,
    holding_before_pct REAL,
    holding_after_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, symbol, person_name, transaction_type, quantity)
);

CREATE TABLE IF NOT EXISTS consensus_estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    target_mean REAL,
    target_median REAL,
    target_high REAL,
    target_low REAL,
    num_analysts INTEGER,
    recommendation TEXT,
    recommendation_score REAL,
    forward_pe REAL,
    forward_eps REAL,
    eps_current_year REAL,
    eps_next_year REAL,
    earnings_growth REAL,
    current_price REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);

CREATE TABLE IF NOT EXISTS earnings_surprises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    eps_actual REAL,
    eps_estimate REAL,
    surprise_pct REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

CREATE TABLE IF NOT EXISTS mf_scheme_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL,
    amc TEXT NOT NULL,
    scheme_name TEXT NOT NULL,
    isin TEXT NOT NULL,
    stock_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    market_value_lakhs REAL NOT NULL,
    pct_of_nav REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(month, amc, scheme_name, isin)
);

CREATE INDEX IF NOT EXISTS idx_mf_holdings_isin ON mf_scheme_holdings(isin);
CREATE INDEX IF NOT EXISTS idx_mf_holdings_month ON mf_scheme_holdings(month);
"""


class FlowStore:
    """SQLite store for daily FII/DII flows."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            env_path = os.environ.get("FLOWTRACKER_DB")
            if env_path:
                db_path = Path(env_path)
            else:
                db_path = _DEFAULT_DB_DIR / _DEFAULT_DB_NAME

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def upsert_flows(self, flows: list[DailyFlow]) -> int:
        """Insert or replace flows. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for f in flows:
            existing = self._conn.execute(
                "SELECT net_value FROM daily_flows WHERE date = ? AND category = ?",
                (f.date.isoformat(), f.category),
            ).fetchone()
            if existing and existing["net_value"] != f.net_value:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("daily_flows", f.category, f.date.isoformat(),
                     "net_value", str(existing["net_value"]), str(f.net_value)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO daily_flows (date, category, buy_value, sell_value, net_value) "
                "VALUES (?, ?, ?, ?, ?)",
                (f.date.isoformat(), f.category, f.buy_value, f.sell_value, f.net_value),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_latest(self) -> DailyFlowPair | None:
        """Get the most recent day's FII + DII pair."""
        row = self._conn.execute(
            "SELECT DISTINCT date FROM daily_flows ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None

        latest_date = row["date"]
        rows = self._conn.execute(
            "SELECT * FROM daily_flows WHERE date = ? ORDER BY category",
            (latest_date,),
        ).fetchall()

        return _rows_to_pair(rows)

    def get_flows(self, days: int) -> list[DailyFlow]:
        """Get flows for the last N calendar days, ordered by date DESC."""
        rows = self._conn.execute(
            "SELECT * FROM daily_flows "
            "WHERE date >= date('now', ? || ' days') "
            "ORDER BY date DESC, category",
            (f"-{days}",),
        ).fetchall()

        return [_row_to_flow(r) for r in rows]

    def get_streak(self, category: str) -> StreakInfo | None:
        """Get current buying/selling streak for a category.

        Counts consecutive days with same-sign net_value, starting from most recent.
        """
        rows = self._conn.execute(
            "SELECT date, net_value FROM daily_flows "
            "WHERE category = ? ORDER BY date DESC",
            (category,),
        ).fetchall()

        if not rows:
            return None

        first_net = rows[0]["net_value"]
        if first_net == 0:
            return None

        is_buying = first_net > 0
        direction = "buying" if is_buying else "selling"
        cumulative = 0.0
        streak_days = 0
        end_date = date.fromisoformat(rows[0]["date"])
        start_date = end_date

        for row in rows:
            net = row["net_value"]
            if (is_buying and net > 0) or (not is_buying and net < 0):
                streak_days += 1
                cumulative += net
                start_date = date.fromisoformat(row["date"])
            else:
                break

        return StreakInfo(
            category=category,
            direction=direction,
            days=streak_days,
            cumulative_net=cumulative,
            start_date=start_date,
            end_date=end_date,
        )

    # -- Phase 3: Mutual Fund flows & AUM --

    def upsert_mf_flows(self, flows: list[MFMonthlyFlow]) -> int:
        """Insert or replace MF monthly flow records."""
        cursor = self._conn.cursor()
        count = 0
        for f in flows:
            cursor.execute(
                "INSERT OR REPLACE INTO mf_monthly_flows "
                "(month, category, sub_category, num_schemes, funds_mobilized, redemption, net_flow, aum) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f.month, f.category, f.sub_category, f.num_schemes, f.funds_mobilized, f.redemption, f.net_flow, f.aum),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_mf_aum(self, summary: MFAUMSummary) -> int:
        """Insert or replace MF AUM summary for a month."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO mf_aum_summary "
            "(month, total_aum, equity_aum, debt_aum, hybrid_aum, other_aum, "
            "equity_net_flow, debt_net_flow, hybrid_net_flow) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (summary.month, summary.total_aum, summary.equity_aum, summary.debt_aum,
             summary.hybrid_aum, summary.other_aum, summary.equity_net_flow,
             summary.debt_net_flow, summary.hybrid_net_flow),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_mf_flows(self, months: int = 12, category: str | None = None) -> list[MFMonthlyFlow]:
        """Get MF flows for the last N months, optionally filtered by category."""
        if category:
            rows = self._conn.execute(
                "SELECT * FROM mf_monthly_flows "
                "WHERE month >= strftime('%Y-%m', 'now', ? || ' months') AND category = ? "
                "ORDER BY month DESC, sub_category",
                (f"-{months}", category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM mf_monthly_flows "
                "WHERE month >= strftime('%Y-%m', 'now', ? || ' months') "
                "ORDER BY month DESC, category, sub_category",
                (f"-{months}",),
            ).fetchall()
        return [MFMonthlyFlow(
            month=r["month"], category=r["category"], sub_category=r["sub_category"],
            num_schemes=r["num_schemes"], funds_mobilized=r["funds_mobilized"],
            redemption=r["redemption"], net_flow=r["net_flow"], aum=r["aum"],
        ) for r in rows]

    def get_mf_aum_trend(self, months: int = 12) -> list[MFAUMSummary]:
        """Get MF AUM summaries for the last N months."""
        rows = self._conn.execute(
            "SELECT * FROM mf_aum_summary "
            "WHERE month >= strftime('%Y-%m', 'now', ? || ' months') "
            "ORDER BY month DESC",
            (f"-{months}",),
        ).fetchall()
        return [MFAUMSummary(
            month=r["month"], total_aum=r["total_aum"], equity_aum=r["equity_aum"],
            debt_aum=r["debt_aum"], hybrid_aum=r["hybrid_aum"], other_aum=r["other_aum"],
            equity_net_flow=r["equity_net_flow"], debt_net_flow=r["debt_net_flow"],
            hybrid_net_flow=r["hybrid_net_flow"],
        ) for r in rows]

    def get_mf_latest_aum(self) -> MFAUMSummary | None:
        """Get the most recent MF AUM summary."""
        row = self._conn.execute(
            "SELECT * FROM mf_aum_summary ORDER BY month DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return MFAUMSummary(
            month=row["month"], total_aum=row["total_aum"], equity_aum=row["equity_aum"],
            debt_aum=row["debt_aum"], hybrid_aum=row["hybrid_aum"], other_aum=row["other_aum"],
            equity_net_flow=row["equity_net_flow"], debt_net_flow=row["debt_net_flow"],
            hybrid_net_flow=row["hybrid_net_flow"],
        )

    # -- MF Daily Flows (SEBI) --

    def upsert_mf_daily_flows(self, flows: list[MFDailyFlow]) -> int:
        """Insert or replace daily MF flow records from SEBI."""
        cursor = self._conn.cursor()
        count = 0
        for f in flows:
            cursor.execute(
                "INSERT OR REPLACE INTO mf_daily_flows "
                "(date, category, gross_purchase, gross_sale, net_investment) "
                "VALUES (?, ?, ?, ?, ?)",
                (f.date, f.category, f.gross_purchase, f.gross_sale, f.net_investment),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_mf_daily_flows(self, days: int = 30, category: str | None = None) -> list[MFDailyFlow]:
        """Get daily MF flows for the last N days, optionally filtered by category."""
        if category:
            rows = self._conn.execute(
                "SELECT * FROM mf_daily_flows "
                "WHERE date >= date('now', ? || ' days') AND category = ? "
                "ORDER BY date DESC, category",
                (f"-{days}", category),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM mf_daily_flows "
                "WHERE date >= date('now', ? || ' days') "
                "ORDER BY date DESC, category",
                (f"-{days}",),
            ).fetchall()
        return [MFDailyFlow(
            date=r["date"], category=r["category"],
            gross_purchase=r["gross_purchase"], gross_sale=r["gross_sale"],
            net_investment=r["net_investment"],
        ) for r in rows]

    def get_mf_daily_latest(self) -> list[MFDailyFlow]:
        """Get the most recent day's MF flows (both equity and debt)."""
        rows = self._conn.execute(
            "SELECT * FROM mf_daily_flows "
            "WHERE date = (SELECT MAX(date) FROM mf_daily_flows) "
            "ORDER BY category"
        ).fetchall()
        return [MFDailyFlow(
            date=r["date"], category=r["category"],
            gross_purchase=r["gross_purchase"], gross_sale=r["gross_sale"],
            net_investment=r["net_investment"],
        ) for r in rows]

    def get_mf_daily_summary(self, days: int = 30) -> list[dict]:
        """Get daily MF equity net investment for trend display."""
        rows = self._conn.execute(
            "SELECT date, "
            "SUM(CASE WHEN category = 'Equity' THEN net_investment ELSE 0 END) as equity_net, "
            "SUM(CASE WHEN category = 'Debt' THEN net_investment ELSE 0 END) as debt_net "
            "FROM mf_daily_flows "
            "WHERE date >= date('now', ? || ' days') "
            "GROUP BY date ORDER BY date DESC",
            (f"-{days}",),
        ).fetchall()
        return [{"date": r["date"], "equity_net": r["equity_net"], "debt_net": r["debt_net"]} for r in rows]

    # -- Phase 4: Watchlist & Shareholding --

    def add_to_watchlist(self, symbol: str, company_name: str | None = None) -> None:
        """Add a symbol to the watchlist."""
        self._conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, company_name) VALUES (?, ?)",
            (symbol.upper(), company_name),
        )
        self._conn.commit()

    def remove_from_watchlist(self, symbol: str) -> None:
        """Remove a symbol from the watchlist."""
        self._conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
        self._conn.commit()

    def get_watchlist(self) -> list[WatchlistEntry]:
        """Get all watchlist entries."""
        rows = self._conn.execute("SELECT * FROM watchlist ORDER BY symbol").fetchall()
        return [WatchlistEntry(
            symbol=r["symbol"], company_name=r["company_name"], added_at=r["added_at"],
        ) for r in rows]

    def upsert_shareholding(self, records: list[ShareholdingRecord]) -> int:
        """Insert or replace shareholding records. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            # Check for existing value before replace
            existing = self._conn.execute(
                "SELECT percentage FROM shareholding WHERE symbol = ? AND quarter_end = ? AND category = ?",
                (r.symbol, r.quarter_end, r.category),
            ).fetchone()
            if existing and existing["percentage"] != r.percentage:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("shareholding", r.symbol, f"{r.quarter_end}|{r.category}",
                     "percentage", str(existing["percentage"]), str(r.percentage)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO shareholding (symbol, quarter_end, category, percentage) "
                "VALUES (?, ?, ?, ?)",
                (r.symbol, r.quarter_end, r.category, r.percentage),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_shareholding(self, symbol: str, limit: int = 8) -> list[ShareholdingRecord]:
        """Get shareholding records for a symbol, most recent quarters first."""
        rows = self._conn.execute(
            "SELECT * FROM shareholding WHERE symbol = ? "
            "ORDER BY quarter_end DESC, category LIMIT ?",
            (symbol.upper(), limit * 6),  # 6 categories per quarter
        ).fetchall()
        return [ShareholdingRecord(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            category=r["category"], percentage=r["percentage"],
        ) for r in rows]

    def get_shareholding_changes(self, symbol: str) -> list[ShareholdingChange]:
        """Get quarter-over-quarter shareholding changes for a symbol."""
        rows = self._conn.execute(
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.symbol = ? "
            "AND s1.quarter_end = (SELECT MAX(quarter_end) FROM shareholding WHERE symbol = ?) "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC",
            (symbol.upper(), symbol.upper()),
        ).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    def get_biggest_changes(self, category: str | None = None, limit: int = 10) -> list[ShareholdingChange]:
        """Get biggest shareholding changes across all watchlist stocks."""
        cat_filter = "AND s1.category = ?" if category else ""
        params: list = []

        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN watchlist w ON s1.symbol = w.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            f") {cat_filter} "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC LIMIT ?"
        )
        if category:
            params = [category, limit]
        else:
            params = [limit]

        rows = self._conn.execute(query, params).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    # -- Phase 5: Index Scanner --

    def upsert_index_constituents(self, constituents: list[IndexConstituent]) -> int:
        """Insert or replace index constituents."""
        cursor = self._conn.cursor()
        count = 0
        for c in constituents:
            cursor.execute(
                "INSERT OR REPLACE INTO index_constituents (symbol, index_name, company_name, industry) "
                "VALUES (?, ?, ?, ?)",
                (c.symbol, c.index_name, c.company_name, c.industry),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_index_constituents(self, index_name: str | None = None) -> list[IndexConstituent]:
        """Get index constituents, optionally filtered by index name."""
        if index_name:
            rows = self._conn.execute(
                "SELECT * FROM index_constituents WHERE index_name = ? ORDER BY symbol",
                (index_name,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM index_constituents ORDER BY index_name, symbol"
            ).fetchall()
        return [IndexConstituent(
            symbol=r["symbol"], index_name=r["index_name"],
            company_name=r["company_name"], industry=r["industry"],
        ) for r in rows]

    def get_all_scanner_symbols(self) -> list[str]:
        """Get distinct symbols from index_constituents."""
        rows = self._conn.execute(
            "SELECT DISTINCT symbol FROM index_constituents ORDER BY symbol"
        ).fetchall()
        return [r["symbol"] for r in rows]

    def get_symbols_with_quarter(self, quarter_end: str) -> set[str]:
        """Get set of symbols that have shareholding data for a specific quarter."""
        rows = self._conn.execute(
            "SELECT DISTINCT symbol FROM shareholding WHERE quarter_end = ?",
            (quarter_end,),
        ).fetchall()
        return {r["symbol"] for r in rows}

    def get_scanner_deviations(
        self, category: str | None = None, limit: int = 20, min_change: float = 0.0,
    ) -> list[ShareholdingChange]:
        """Get biggest shareholding changes across all index constituents."""
        cat_filter = "AND s1.category = ?" if category else ""
        min_filter = f"AND ABS(s1.percentage - s2.percentage) >= {min_change}" if min_change > 0 else ""
        params: list = []

        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN index_constituents ic ON s1.symbol = ic.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            f") {cat_filter} {min_filter} "
            "GROUP BY s1.symbol, s1.category "
            "ORDER BY ABS(s1.percentage - s2.percentage) DESC LIMIT ?"
        )
        if category:
            params = [category, limit]
        else:
            params = [limit]

        rows = self._conn.execute(query, params).fetchall()
        return [ShareholdingChange(
            symbol=r["symbol"],
            category=r["category"],
            prev_quarter_end=r["prev_qtr"],
            curr_quarter_end=r["curr_qtr"],
            prev_pct=r["prev_pct"],
            curr_pct=r["curr_pct"],
            change_pct=r["curr_pct"] - r["prev_pct"],
        ) for r in rows]

    def get_handoff_signals(self, limit: int = 20) -> list[tuple[ShareholdingChange, ShareholdingChange]]:
        """Find stocks where FII decreased AND MF increased (handoff pattern).

        Returns list of (fii_change, mf_change) tuples.
        """
        # Get all latest QoQ changes for scanner stocks
        query = (
            "SELECT s1.symbol, s1.category, s1.quarter_end AS curr_qtr, s1.percentage AS curr_pct, "
            "s2.quarter_end AS prev_qtr, s2.percentage AS prev_pct "
            "FROM shareholding s1 "
            "INNER JOIN index_constituents ic ON s1.symbol = ic.symbol "
            "INNER JOIN shareholding s2 ON s1.symbol = s2.symbol AND s1.category = s2.category "
            "AND s2.quarter_end = ("
            "  SELECT MAX(s3.quarter_end) FROM shareholding s3 "
            "  WHERE s3.symbol = s1.symbol AND s3.category = s1.category "
            "  AND s3.quarter_end < s1.quarter_end"
            ") "
            "WHERE s1.quarter_end = ("
            "  SELECT MAX(s4.quarter_end) FROM shareholding s4 WHERE s4.symbol = s1.symbol"
            ") "
            "AND s1.category IN ('FII', 'MF') "
            "GROUP BY s1.symbol, s1.category "
            "ORDER BY s1.symbol"
        )
        rows = self._conn.execute(query).fetchall()

        # Group by symbol, find FII-down + MF-up pairs
        by_symbol: dict[str, dict[str, ShareholdingChange]] = {}
        for r in rows:
            change = ShareholdingChange(
                symbol=r["symbol"], category=r["category"],
                prev_quarter_end=r["prev_qtr"], curr_quarter_end=r["curr_qtr"],
                prev_pct=r["prev_pct"], curr_pct=r["curr_pct"],
                change_pct=r["curr_pct"] - r["prev_pct"],
            )
            by_symbol.setdefault(r["symbol"], {})[r["category"]] = change

        handoffs: list[tuple[ShareholdingChange, ShareholdingChange]] = []
        for symbol, cats in by_symbol.items():
            fii = cats.get("FII")
            mf = cats.get("MF")
            if fii and mf and fii.change_pct < 0 and mf.change_pct > 0:
                handoffs.append((fii, mf))

        # Sort by FII selling magnitude
        handoffs.sort(key=lambda x: x[0].change_pct)
        return handoffs[:limit]

    # -- Commodity Prices --

    def upsert_commodity_prices(self, prices: list[CommodityPrice]) -> int:
        """Insert or replace commodity price records."""
        import math
        cursor = self._conn.cursor()
        count = 0
        for p in prices:
            if math.isnan(p.price):
                continue
            cursor.execute(
                "INSERT OR REPLACE INTO commodity_prices (date, symbol, price, unit) "
                "VALUES (?, ?, ?, ?)",
                (p.date, p.symbol, p.price, p.unit),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_etf_navs(self, navs: list[GoldETFNav]) -> int:
        """Insert or replace gold ETF NAV records."""
        cursor = self._conn.cursor()
        count = 0
        for n in navs:
            cursor.execute(
                "INSERT OR REPLACE INTO gold_etf_nav (date, scheme_code, scheme_name, nav) "
                "VALUES (?, ?, ?, ?)",
                (n.date, n.scheme_code, n.scheme_name, n.nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_commodity_prices(self, symbol: str, days: int = 30) -> list[CommodityPrice]:
        """Get commodity prices for a symbol, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM commodity_prices WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [CommodityPrice(
            date=r["date"], symbol=r["symbol"], price=r["price"], unit=r["unit"],
        ) for r in rows]

    def get_etf_navs(self, scheme_code: str, days: int = 365) -> list[GoldETFNav]:
        """Get ETF NAVs for a scheme, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM gold_etf_nav WHERE scheme_code = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (scheme_code, f"-{days}"),
        ).fetchall()
        return [GoldETFNav(
            date=r["date"], scheme_code=r["scheme_code"],
            scheme_name=r["scheme_name"], nav=r["nav"],
        ) for r in rows]

    def get_gold_fii_correlation(self, days: int = 30) -> list[GoldCorrelation]:
        """Get FII daily net flows aligned with gold price changes."""
        rows = self._conn.execute(
            "SELECT df.date, df.net_value AS fii_net, "
            "cp_gold.price AS gold_close, cp_inr.price AS gold_inr "
            "FROM daily_flows df "
            "LEFT JOIN commodity_prices cp_gold ON df.date = cp_gold.date AND cp_gold.symbol = 'GOLD' "
            "LEFT JOIN commodity_prices cp_inr ON df.date = cp_inr.date AND cp_inr.symbol = 'GOLD_INR' "
            "WHERE df.category = 'FII' AND cp_gold.price IS NOT NULL "
            "AND df.date >= date('now', ? || ' days') "
            "ORDER BY df.date DESC",
            (f"-{days}",),
        ).fetchall()

        results: list[GoldCorrelation] = []
        for i, r in enumerate(rows):
            # Calculate day-over-day gold change %
            if i + 1 < len(rows) and rows[i + 1]["gold_close"]:
                prev_gold = rows[i + 1]["gold_close"]
                change_pct = round((r["gold_close"] - prev_gold) / prev_gold * 100, 2) if prev_gold else 0.0
            else:
                change_pct = 0.0

            results.append(GoldCorrelation(
                date=r["date"],
                fii_net=r["fii_net"],
                gold_close=r["gold_close"],
                gold_change_pct=change_pct,
                gold_inr=r["gold_inr"],
            ))
        return results

    # -- Promoter Pledge --

    def upsert_promoter_pledges(self, pledges: list[PromoterPledge]) -> int:
        """Insert or replace promoter pledge records. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for p in pledges:
            existing = self._conn.execute(
                "SELECT pledge_pct, encumbered_pct FROM promoter_pledge WHERE symbol = ? AND quarter_end = ?",
                (p.symbol, p.quarter_end),
            ).fetchone()
            if existing and (existing["pledge_pct"] != p.pledge_pct or existing["encumbered_pct"] != p.encumbered_pct):
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("promoter_pledge", p.symbol, p.quarter_end,
                     "pledge_pct", str(existing["pledge_pct"]), str(p.pledge_pct)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO promoter_pledge (symbol, quarter_end, pledge_pct, encumbered_pct) "
                "VALUES (?, ?, ?, ?)",
                (p.symbol, p.quarter_end, p.pledge_pct, p.encumbered_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_promoter_pledge(self, symbol: str, limit: int = 8) -> list[PromoterPledge]:
        """Get promoter pledge history for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM promoter_pledge WHERE symbol = ? ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [PromoterPledge(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            pledge_pct=r["pledge_pct"], encumbered_pct=r["encumbered_pct"],
        ) for r in rows]

    def get_high_pledge_stocks(self, min_pledge_pct: float = 1.0, limit: int = 20) -> list[PromoterPledge]:
        """Get stocks with high promoter pledging from latest quarter, joined with scanner stocks."""
        rows = self._conn.execute(
            "SELECT pp.* FROM promoter_pledge pp "
            "INNER JOIN index_constituents ic ON pp.symbol = ic.symbol "
            "WHERE pp.quarter_end = ("
            "  SELECT MAX(pp2.quarter_end) FROM promoter_pledge pp2 WHERE pp2.symbol = pp.symbol"
            ") AND pp.pledge_pct >= ? "
            "ORDER BY pp.pledge_pct DESC LIMIT ?",
            (min_pledge_pct, limit),
        ).fetchall()
        return [PromoterPledge(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            pledge_pct=r["pledge_pct"], encumbered_pct=r["encumbered_pct"],
        ) for r in rows]

    def get_scan_summary(self) -> ScanSummary:
        """Get aggregate stats for the scanner."""
        all_symbols = self.get_all_scanner_symbols()
        total = len(all_symbols)

        # Find latest quarter in shareholding for scanner symbols
        row = self._conn.execute(
            "SELECT MAX(quarter_end) as latest FROM shareholding s "
            "INNER JOIN index_constituents ic ON s.symbol = ic.symbol"
        ).fetchone()
        latest_quarter = row["latest"] if row and row["latest"] else None

        # Symbols that have any shareholding data
        rows = self._conn.execute(
            "SELECT DISTINCT s.symbol FROM shareholding s "
            "INNER JOIN index_constituents ic ON s.symbol = ic.symbol"
        ).fetchall()
        symbols_with_data = {r["symbol"] for r in rows}

        missing = sorted(set(all_symbols) - symbols_with_data)

        return ScanSummary(
            total_symbols=total,
            symbols_with_data=len(symbols_with_data),
            latest_quarter=latest_quarter,
            missing_symbols=missing,
        )

    # -- Fundamentals: Quarterly Results --

    def upsert_quarterly_results(self, results: list[QuarterlyResult]) -> int:
        """Insert or replace quarterly results. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        count = 0
        for r in results:
            existing = self._conn.execute(
                "SELECT revenue FROM quarterly_results WHERE symbol = ? AND quarter_end = ?",
                (r.symbol, r.quarter_end),
            ).fetchone()
            if existing and existing["revenue"] != r.revenue:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("quarterly_results", r.symbol, r.quarter_end,
                     "revenue", str(existing["revenue"]), str(r.revenue)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO quarterly_results "
                "(symbol, quarter_end, revenue, gross_profit, operating_income, net_income, "
                "ebitda, eps, eps_diluted, operating_margin, net_margin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.quarter_end, r.revenue, r.gross_profit, r.operating_income,
                 r.net_income, r.ebitda, r.eps, r.eps_diluted, r.operating_margin, r.net_margin),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_quarterly_results(self, symbol: str, limit: int = 12) -> list[QuarterlyResult]:
        """Get stored quarterly results, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM quarterly_results WHERE symbol = ? "
            "ORDER BY quarter_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [QuarterlyResult(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            revenue=r["revenue"], gross_profit=r["gross_profit"],
            operating_income=r["operating_income"], net_income=r["net_income"],
            ebitda=r["ebitda"], eps=r["eps"], eps_diluted=r["eps_diluted"],
            operating_margin=r["operating_margin"], net_margin=r["net_margin"],
        ) for r in rows]

    # -- Fundamentals: Valuation Snapshots --

    def upsert_valuation_snapshot(self, snapshot: ValuationSnapshot) -> int:
        """Insert or replace a valuation snapshot. Logs changes to audit_log."""
        cursor = self._conn.cursor()
        existing = self._conn.execute(
            "SELECT pe_trailing FROM valuation_snapshot WHERE symbol = ? AND date = ?",
            (snapshot.symbol, snapshot.date),
        ).fetchone()
        if existing and existing["pe_trailing"] != snapshot.pe_trailing:
            cursor.execute(
                "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("valuation_snapshot", snapshot.symbol, snapshot.date,
                 "pe_trailing", str(existing["pe_trailing"]), str(snapshot.pe_trailing)),
            )
        cursor.execute(
            "INSERT OR REPLACE INTO valuation_snapshot "
            "(symbol, date, price, market_cap, enterprise_value, pe_trailing, pe_forward, "
            "pb_ratio, ev_ebitda, dividend_yield, roe, roa, debt_to_equity, current_ratio, free_cash_flow) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot.symbol, snapshot.date, snapshot.price, snapshot.market_cap,
             snapshot.enterprise_value, snapshot.pe_trailing, snapshot.pe_forward,
             snapshot.pb_ratio, snapshot.ev_ebitda, snapshot.dividend_yield,
             snapshot.roe, snapshot.roa, snapshot.debt_to_equity, snapshot.current_ratio,
             snapshot.free_cash_flow),
        )
        self._conn.commit()
        return cursor.rowcount

    def upsert_valuation_snapshots(self, snapshots: list[ValuationSnapshot]) -> int:
        """Batch insert valuation snapshots."""
        count = 0
        for s in snapshots:
            count += self.upsert_valuation_snapshot(s)
        return count

    def get_valuation_history(self, symbol: str, days: int = 365) -> list[ValuationSnapshot]:
        """Get valuation snapshots for the last N days, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM valuation_snapshot "
            "WHERE symbol = ? AND date >= date('now', ? || ' days') "
            "ORDER BY date ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()
        return [ValuationSnapshot(
            symbol=r["symbol"], date=r["date"], price=r["price"],
            market_cap=r["market_cap"], enterprise_value=r["enterprise_value"],
            pe_trailing=r["pe_trailing"], pe_forward=r["pe_forward"],
            pb_ratio=r["pb_ratio"], ev_ebitda=r["ev_ebitda"],
            dividend_yield=r["dividend_yield"], roe=r["roe"], roa=r["roa"],
            debt_to_equity=r["debt_to_equity"], current_ratio=r["current_ratio"],
            free_cash_flow=r["free_cash_flow"],
        ) for r in rows]

    def get_valuation_band(self, symbol: str, metric: str, days: int = 1095) -> ValuationBand | None:
        """Compute min/max/median/percentile for a valuation metric over N days.

        metric must be a column name in valuation_snapshot (e.g., 'pe_trailing', 'ev_ebitda', 'pb_ratio').
        """
        # Validate metric name to prevent SQL injection
        valid_metrics = {"pe_trailing", "pe_forward", "pb_ratio", "ev_ebitda", "dividend_yield"}
        if metric not in valid_metrics:
            return None

        rows = self._conn.execute(
            f"SELECT {metric}, date FROM valuation_snapshot "
            f"WHERE symbol = ? AND date >= date('now', ? || ' days') AND {metric} IS NOT NULL "
            f"ORDER BY {metric} ASC",
            (symbol.upper(), f"-{days}"),
        ).fetchall()

        if not rows:
            return None

        values = [r[metric] for r in rows]
        n = len(values)
        min_val = values[0]
        max_val = values[-1]
        median_val = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2

        # Get current value (most recent)
        latest = self._conn.execute(
            f"SELECT {metric} FROM valuation_snapshot "
            f"WHERE symbol = ? AND {metric} IS NOT NULL "
            f"ORDER BY date DESC LIMIT 1",
            (symbol.upper(),),
        ).fetchone()
        if latest is None:
            return None
        current_val = latest[metric]

        # Compute percentile
        below = sum(1 for v in values if v < current_val)
        percentile = (below / n) * 100

        dates = [r["date"] for r in rows]
        return ValuationBand(
            symbol=symbol.upper(),
            metric=metric,
            min_val=min_val,
            max_val=max_val,
            median_val=median_val,
            current_val=current_val,
            percentile=percentile,
            num_observations=n,
            period_start=min(dates),
            period_end=max(dates),
        )

    # -- Fundamentals: Annual Financials --

    def upsert_annual_financials(self, records: list) -> int:
        """Insert or replace annual financials. Audit-logged."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            existing = self._conn.execute(
                "SELECT revenue FROM annual_financials WHERE symbol = ? AND fiscal_year_end = ?",
                (r.symbol, r.fiscal_year_end),
            ).fetchone()
            if existing and existing["revenue"] != r.revenue:
                cursor.execute(
                    "INSERT INTO audit_log (table_name, symbol, key_info, field, old_value, new_value) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("annual_financials", r.symbol, r.fiscal_year_end,
                     "revenue", str(existing["revenue"]), str(r.revenue)),
                )
            cursor.execute(
                "INSERT OR REPLACE INTO annual_financials "
                "(symbol, fiscal_year_end, revenue, employee_cost, other_income, depreciation, "
                "interest, profit_before_tax, tax, net_income, eps, dividend_amount, "
                "equity_capital, reserves, borrowings, other_liabilities, total_assets, "
                "net_block, cwip, investments, other_assets, receivables, inventory, "
                "cash_and_bank, num_shares, cfo, cfi, cff, net_cash_flow, price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.symbol, r.fiscal_year_end, r.revenue, r.employee_cost, r.other_income,
                 r.depreciation, r.interest, r.profit_before_tax, r.tax, r.net_income,
                 r.eps, r.dividend_amount, r.equity_capital, r.reserves, r.borrowings,
                 r.other_liabilities, r.total_assets, r.net_block, r.cwip, r.investments,
                 r.other_assets, r.receivables, r.inventory, r.cash_and_bank, r.num_shares,
                 r.cfo, r.cfi, r.cff, r.net_cash_flow, r.price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_annual_financials(self, symbol: str, limit: int = 10) -> list:
        """Get stored annual financials, most recent first."""
        from flowtracker.fund_models import AnnualFinancials
        rows = self._conn.execute(
            "SELECT * FROM annual_financials WHERE symbol = ? "
            "ORDER BY fiscal_year_end DESC LIMIT ?",
            (symbol.upper(), limit),
        ).fetchall()
        return [AnnualFinancials(
            symbol=r["symbol"], fiscal_year_end=r["fiscal_year_end"],
            revenue=r["revenue"], employee_cost=r["employee_cost"],
            other_income=r["other_income"], depreciation=r["depreciation"],
            interest=r["interest"], profit_before_tax=r["profit_before_tax"],
            tax=r["tax"], net_income=r["net_income"], eps=r["eps"],
            dividend_amount=r["dividend_amount"], equity_capital=r["equity_capital"],
            reserves=r["reserves"], borrowings=r["borrowings"],
            other_liabilities=r["other_liabilities"], total_assets=r["total_assets"],
            net_block=r["net_block"], cwip=r["cwip"], investments=r["investments"],
            other_assets=r["other_assets"], receivables=r["receivables"],
            inventory=r["inventory"], cash_and_bank=r["cash_and_bank"],
            num_shares=r["num_shares"], cfo=r["cfo"], cfi=r["cfi"],
            cff=r["cff"], net_cash_flow=r["net_cash_flow"], price=r["price"],
        ) for r in rows]

    # -- Macro Indicators --

    def upsert_macro_snapshots(self, snapshots: list[MacroSnapshot]) -> int:
        """Insert or replace macro daily snapshots."""
        cursor = self._conn.cursor()
        count = 0
        for s in snapshots:
            cursor.execute(
                "INSERT OR REPLACE INTO macro_daily "
                "(date, india_vix, usd_inr, brent_crude, gsec_10y) "
                "VALUES (?, ?, ?, ?, ?)",
                (s.date, s.india_vix, s.usd_inr, s.brent_crude, s.gsec_10y),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_macro_latest(self) -> MacroSnapshot | None:
        """Get the most recent macro snapshot."""
        row = self._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return MacroSnapshot(
            date=row["date"], india_vix=row["india_vix"],
            usd_inr=row["usd_inr"], brent_crude=row["brent_crude"],
            gsec_10y=row["gsec_10y"],
        )

    def get_macro_previous(self) -> MacroSnapshot | None:
        """Get the second most recent macro snapshot (for delta display)."""
        row = self._conn.execute(
            "SELECT * FROM macro_daily ORDER BY date DESC LIMIT 1 OFFSET 1"
        ).fetchone()
        if not row:
            return None
        return MacroSnapshot(
            date=row["date"], india_vix=row["india_vix"],
            usd_inr=row["usd_inr"], brent_crude=row["brent_crude"],
            gsec_10y=row["gsec_10y"],
        )

    def get_macro_trend(self, days: int = 30) -> list[MacroSnapshot]:
        """Get macro snapshots for the last N days, most recent first."""
        rows = self._conn.execute(
            "SELECT * FROM macro_daily "
            "WHERE date >= date('now', ? || ' days') "
            "ORDER BY date DESC",
            (f"-{days}",),
        ).fetchall()
        return [MacroSnapshot(
            date=r["date"], india_vix=r["india_vix"],
            usd_inr=r["usd_inr"], brent_crude=r["brent_crude"],
            gsec_10y=r["gsec_10y"],
        ) for r in rows]

    # -- Bhavcopy + Delivery --

    def upsert_daily_stock_data(self, records: list[DailyStockData]) -> int:
        """Insert or replace daily stock data records."""
        cursor = self._conn.cursor()
        count = 0
        for r in records:
            cursor.execute(
                "INSERT OR REPLACE INTO daily_stock_data "
                "(date, symbol, open, high, low, close, prev_close, volume, "
                "turnover, delivery_qty, delivery_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r.date, r.symbol, r.open, r.high, r.low, r.close, r.prev_close,
                 r.volume, r.turnover, r.delivery_qty, r.delivery_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_top_delivery(self, date_str: str | None = None, limit: int = 20) -> list[DailyStockData]:
        """Get stocks with highest delivery % for a date (default: latest)."""
        if date_str is None:
            row = self._conn.execute("SELECT MAX(date) as d FROM daily_stock_data").fetchone()
            if not row or not row["d"]:
                return []
            date_str = row["d"]
        rows = self._conn.execute(
            "SELECT * FROM daily_stock_data WHERE date = ? AND delivery_pct IS NOT NULL "
            "ORDER BY delivery_pct DESC LIMIT ?",
            (date_str, limit),
        ).fetchall()
        return [DailyStockData(
            date=r["date"], symbol=r["symbol"], open=r["open"], high=r["high"],
            low=r["low"], close=r["close"], prev_close=r["prev_close"],
            volume=r["volume"], turnover=r["turnover"],
            delivery_qty=r["delivery_qty"], delivery_pct=r["delivery_pct"],
        ) for r in rows]

    def get_stock_delivery(self, symbol: str, days: int = 30) -> list[DailyStockData]:
        """Get delivery trend for a specific stock."""
        rows = self._conn.execute(
            "SELECT * FROM daily_stock_data WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [DailyStockData(
            date=r["date"], symbol=r["symbol"], open=r["open"], high=r["high"],
            low=r["low"], close=r["close"], prev_close=r["prev_close"],
            volume=r["volume"], turnover=r["turnover"],
            delivery_qty=r["delivery_qty"], delivery_pct=r["delivery_pct"],
        ) for r in rows]

    # -- Bulk/Block Deals --

    def upsert_deals(self, deals: list[BulkBlockDeal]) -> int:
        """Insert or replace bulk/block deal records."""
        cursor = self._conn.cursor()
        count = 0
        for d in deals:
            cursor.execute(
                "INSERT OR REPLACE INTO bulk_block_deals "
                "(date, deal_type, symbol, client_name, buy_sell, quantity, price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (d.date, d.deal_type, d.symbol, d.client_name, d.buy_sell,
                 d.quantity, d.price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_deals_latest(self) -> list[BulkBlockDeal]:
        """Get deals for the most recent day."""
        row = self._conn.execute("SELECT MAX(date) as d FROM bulk_block_deals").fetchone()
        if not row or not row["d"]:
            return []
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals WHERE date = ? ORDER BY deal_type, symbol",
            (row["d"],),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def get_deals_by_symbol(self, symbol: str) -> list[BulkBlockDeal]:
        """Get all deals for a specific symbol."""
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals WHERE symbol = ? ORDER BY date DESC",
            (symbol,),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    def get_deals_top(self, days: int = 30, limit: int = 20) -> list[BulkBlockDeal]:
        """Get biggest deals by value in the last N days."""
        rows = self._conn.execute(
            "SELECT * FROM bulk_block_deals "
            "WHERE date >= date('now', ? || ' days') AND price IS NOT NULL "
            "ORDER BY (quantity * price) DESC LIMIT ?",
            (f"-{days}", limit),
        ).fetchall()
        return [BulkBlockDeal(
            date=r["date"], deal_type=r["deal_type"], symbol=r["symbol"],
            client_name=r["client_name"], buy_sell=r["buy_sell"],
            quantity=r["quantity"], price=r["price"],
        ) for r in rows]

    # -- Insider/SAST Transactions --

    def upsert_insider_transactions(self, trades: list[InsiderTransaction]) -> int:
        """Insert or replace insider transaction records."""
        cursor = self._conn.cursor()
        count = 0
        for t in trades:
            cursor.execute(
                "INSERT OR REPLACE INTO insider_transactions "
                "(date, symbol, person_name, person_category, transaction_type, "
                "quantity, value, mode, holding_before_pct, holding_after_pct) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (t.date, t.symbol, t.person_name, t.person_category,
                 t.transaction_type, t.quantity, t.value, t.mode,
                 t.holding_before_pct, t.holding_after_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_insider_by_symbol(self, symbol: str, days: int = 365) -> list[InsiderTransaction]:
        """Get insider transactions for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions WHERE symbol = ? "
            "AND date >= date('now', ? || ' days') ORDER BY date DESC",
            (symbol, f"-{days}"),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    def get_promoter_buys(self, days: int = 30) -> list[InsiderTransaction]:
        """Get promoter buying transactions."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions "
            "WHERE person_category LIKE '%Promoter%' "
            "AND transaction_type = 'Buy' "
            "AND date >= date('now', ? || ' days') "
            "ORDER BY value DESC",
            (f"-{days}",),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    def get_insider_recent(self, days: int = 7) -> list[InsiderTransaction]:
        """Get all recent insider transactions."""
        rows = self._conn.execute(
            "SELECT * FROM insider_transactions "
            "WHERE date >= date('now', ? || ' days') "
            "ORDER BY date DESC, value DESC",
            (f"-{days}",),
        ).fetchall()
        return [InsiderTransaction(
            date=r["date"], symbol=r["symbol"], person_name=r["person_name"],
            person_category=r["person_category"], transaction_type=r["transaction_type"],
            quantity=r["quantity"], value=r["value"], mode=r["mode"],
            holding_before_pct=r["holding_before_pct"], holding_after_pct=r["holding_after_pct"],
        ) for r in rows]

    # -- Consensus Estimates --

    def upsert_consensus_estimates(self, estimates: list[ConsensusEstimate]) -> int:
        """Insert or replace consensus estimate records."""
        cursor = self._conn.cursor()
        count = 0
        for e in estimates:
            cursor.execute(
                "INSERT OR REPLACE INTO consensus_estimates "
                "(symbol, date, target_mean, target_median, target_high, target_low, "
                "num_analysts, recommendation, recommendation_score, forward_pe, "
                "forward_eps, eps_current_year, eps_next_year, earnings_growth, current_price) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e.symbol, e.date, e.target_mean, e.target_median, e.target_high,
                 e.target_low, e.num_analysts, e.recommendation, e.recommendation_score,
                 e.forward_pe, e.forward_eps, e.eps_current_year, e.eps_next_year,
                 e.earnings_growth, e.current_price),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def upsert_earnings_surprises(self, surprises: list[EarningsSurprise]) -> int:
        """Insert or replace earnings surprise records."""
        cursor = self._conn.cursor()
        count = 0
        for s in surprises:
            cursor.execute(
                "INSERT OR REPLACE INTO earnings_surprises "
                "(symbol, quarter_end, eps_actual, eps_estimate, surprise_pct) "
                "VALUES (?, ?, ?, ?, ?)",
                (s.symbol, s.quarter_end, s.eps_actual, s.eps_estimate, s.surprise_pct),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_estimate_latest(self, symbol: str) -> ConsensusEstimate | None:
        """Get the most recent estimate for a symbol."""
        row = self._conn.execute(
            "SELECT * FROM consensus_estimates WHERE symbol = ? ORDER BY date DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if not row:
            return None
        return ConsensusEstimate(
            symbol=row["symbol"], date=row["date"],
            target_mean=row["target_mean"], target_median=row["target_median"],
            target_high=row["target_high"], target_low=row["target_low"],
            num_analysts=row["num_analysts"], recommendation=row["recommendation"],
            recommendation_score=row["recommendation_score"],
            forward_pe=row["forward_pe"], forward_eps=row["forward_eps"],
            eps_current_year=row["eps_current_year"], eps_next_year=row["eps_next_year"],
            earnings_growth=row["earnings_growth"], current_price=row["current_price"],
        )

    def get_all_latest_estimates(self) -> list[ConsensusEstimate]:
        """Get latest estimate for each symbol, ranked by upside."""
        rows = self._conn.execute(
            "SELECT ce.* FROM consensus_estimates ce "
            "INNER JOIN (SELECT symbol, MAX(date) as max_date FROM consensus_estimates "
            "GROUP BY symbol) latest "
            "ON ce.symbol = latest.symbol AND ce.date = latest.max_date "
            "ORDER BY CASE WHEN ce.target_mean IS NOT NULL AND ce.current_price IS NOT NULL "
            "AND ce.current_price > 0 "
            "THEN (ce.target_mean - ce.current_price) / ce.current_price ELSE -999 END DESC"
        ).fetchall()
        return [ConsensusEstimate(
            symbol=r["symbol"], date=r["date"],
            target_mean=r["target_mean"], target_median=r["target_median"],
            target_high=r["target_high"], target_low=r["target_low"],
            num_analysts=r["num_analysts"], recommendation=r["recommendation"],
            recommendation_score=r["recommendation_score"],
            forward_pe=r["forward_pe"], forward_eps=r["forward_eps"],
            eps_current_year=r["eps_current_year"], eps_next_year=r["eps_next_year"],
            earnings_growth=r["earnings_growth"], current_price=r["current_price"],
        ) for r in rows]

    def get_surprises(self, symbol: str) -> list[EarningsSurprise]:
        """Get earnings surprises for a symbol."""
        rows = self._conn.execute(
            "SELECT * FROM earnings_surprises WHERE symbol = ? ORDER BY quarter_end DESC",
            (symbol,),
        ).fetchall()
        return [EarningsSurprise(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            eps_actual=r["eps_actual"], eps_estimate=r["eps_estimate"],
            surprise_pct=r["surprise_pct"],
        ) for r in rows]

    def get_recent_surprises(self, days: int = 90) -> list[EarningsSurprise]:
        """Get recent earnings surprises across all stocks."""
        rows = self._conn.execute(
            "SELECT * FROM earnings_surprises "
            "WHERE quarter_end >= date('now', ? || ' days') "
            "ORDER BY ABS(COALESCE(surprise_pct, 0)) DESC",
            (f"-{days}",),
        ).fetchall()
        return [EarningsSurprise(
            symbol=r["symbol"], quarter_end=r["quarter_end"],
            eps_actual=r["eps_actual"], eps_estimate=r["eps_estimate"],
            surprise_pct=r["surprise_pct"],
        ) for r in rows]

    # -- Sector Aggregation --

    def get_sector_overview(self) -> list[dict]:
        """Get sector-level ownership shifts + delivery + price signals.

        Returns list of dicts with industry, num_stocks, avg changes per category,
        avg delivery %, avg price change %.
        """
        rows = self._conn.execute("""
            SELECT
                ic.industry,
                COUNT(DISTINCT ic.symbol) as num_stocks,
                AVG(CASE WHEN s1.category = 'FII' THEN s1.percentage - s2.percentage END) as avg_fii_change,
                AVG(CASE WHEN s1.category = 'MF' THEN s1.percentage - s2.percentage END) as avg_mf_change,
                AVG(CASE WHEN s1.category = 'DII' THEN s1.percentage - s2.percentage END) as avg_dii_change,
                AVG(CASE WHEN s1.category = 'Promoter' THEN s1.percentage - s2.percentage END) as avg_promoter_change,
                del_stats.avg_delivery_pct,
                del_stats.avg_price_change_pct
            FROM index_constituents ic
            INNER JOIN shareholding s1 ON ic.symbol = s1.symbol
            INNER JOIN shareholding s2 ON s1.symbol = s2.symbol
                AND s1.category = s2.category
                AND s2.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM shareholding s3
                    WHERE s3.symbol = s1.symbol AND s3.category = s1.category
                    AND s3.quarter_end < s1.quarter_end
                )
            LEFT JOIN (
                SELECT ic2.industry,
                    AVG(d.delivery_pct) as avg_delivery_pct,
                    AVG((d.close - d.prev_close) / NULLIF(d.prev_close, 0) * 100) as avg_price_change_pct
                FROM daily_stock_data d
                INNER JOIN index_constituents ic2 ON d.symbol = ic2.symbol
                WHERE d.date >= date('now', '-30 days')
                    AND d.delivery_pct IS NOT NULL
                GROUP BY ic2.industry
            ) del_stats ON ic.industry = del_stats.industry
            WHERE ic.industry IS NOT NULL
                AND s1.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM shareholding s4
                    WHERE s4.symbol = s1.symbol
                )
                AND s1.category IN ('FII', 'MF', 'DII', 'Promoter')
            GROUP BY ic.industry
            HAVING num_stocks >= 3
            ORDER BY avg_mf_change DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_sector_detail(self, industry: str) -> list[dict]:
        """Get stock-level ownership + delivery + price data for a sector."""
        rows = self._conn.execute("""
            SELECT
                ic.symbol,
                MAX(CASE WHEN s1.category = 'FII' THEN s1.percentage END) as curr_fii,
                MAX(CASE WHEN s1.category = 'MF' THEN s1.percentage END) as curr_mf,
                MAX(CASE WHEN s1.category = 'FII' THEN s1.percentage - s2.percentage END) as fii_change,
                MAX(CASE WHEN s1.category = 'MF' THEN s1.percentage - s2.percentage END) as mf_change,
                MAX(CASE WHEN s1.category = 'DII' THEN s1.percentage - s2.percentage END) as dii_change,
                MAX(CASE WHEN s1.category = 'Promoter' THEN s1.percentage - s2.percentage END) as promoter_change,
                vs.pe_trailing,
                del_stats.avg_delivery_pct,
                del_stats.avg_price_change_pct
            FROM index_constituents ic
            INNER JOIN shareholding s1 ON ic.symbol = s1.symbol
            INNER JOIN shareholding s2 ON s1.symbol = s2.symbol
                AND s1.category = s2.category
                AND s2.quarter_end = (
                    SELECT MAX(s3.quarter_end) FROM shareholding s3
                    WHERE s3.symbol = s1.symbol AND s3.category = s1.category
                    AND s3.quarter_end < s1.quarter_end
                )
            LEFT JOIN (
                SELECT symbol, pe_trailing FROM valuation_snapshot
                WHERE (symbol, date) IN (
                    SELECT symbol, MAX(date) FROM valuation_snapshot GROUP BY symbol
                )
            ) vs ON ic.symbol = vs.symbol
            LEFT JOIN (
                SELECT symbol,
                    AVG(delivery_pct) as avg_delivery_pct,
                    AVG((close - prev_close) / NULLIF(prev_close, 0) * 100) as avg_price_change_pct
                FROM daily_stock_data
                WHERE date >= date('now', '-30 days') AND delivery_pct IS NOT NULL
                GROUP BY symbol
            ) del_stats ON ic.symbol = del_stats.symbol
            WHERE ic.industry = ?
                AND s1.quarter_end = (
                    SELECT MAX(s4.quarter_end) FROM shareholding s4
                    WHERE s4.symbol = s1.symbol
                )
                AND s1.category IN ('FII', 'MF', 'DII', 'Promoter')
            GROUP BY ic.symbol
            ORDER BY mf_change DESC
        """, (industry,)).fetchall()
        return [dict(r) for r in rows]

    def get_sector_list(self) -> list[str]:
        """Get distinct industry names from index constituents."""
        rows = self._conn.execute(
            "SELECT DISTINCT industry FROM index_constituents "
            "WHERE industry IS NOT NULL ORDER BY industry"
        ).fetchall()
        return [r["industry"] for r in rows]

    # -- MF Scheme Holdings --

    def upsert_mf_scheme_holdings(self, holdings: list[MFSchemeHolding]) -> int:
        """Insert or replace MF scheme holding records."""
        cursor = self._conn.cursor()
        count = 0
        for h in holdings:
            cursor.execute(
                "INSERT OR REPLACE INTO mf_scheme_holdings "
                "(month, amc, scheme_name, isin, stock_name, quantity, market_value_lakhs, pct_of_nav) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (h.month, h.amc, h.scheme_name, h.isin, h.stock_name,
                 h.quantity, h.market_value_lakhs, h.pct_of_nav),
            )
            count += cursor.rowcount
        self._conn.commit()
        return count

    def get_mf_stock_holdings(self, search: str) -> list[MFSchemeHolding]:
        """Get MF holdings for a stock by name or ISIN."""
        rows = self._conn.execute(
            "SELECT * FROM mf_scheme_holdings "
            "WHERE (UPPER(stock_name) LIKE ? OR isin = ?) "
            "AND month = (SELECT MAX(month) FROM mf_scheme_holdings) "
            "ORDER BY market_value_lakhs DESC",
            (f"%{search}%", search),
        ).fetchall()
        return [MFSchemeHolding(
            month=r["month"], amc=r["amc"], scheme_name=r["scheme_name"],
            isin=r["isin"], stock_name=r["stock_name"], quantity=r["quantity"],
            market_value_lakhs=r["market_value_lakhs"], pct_of_nav=r["pct_of_nav"],
        ) for r in rows]

    def get_mf_holding_changes(
        self, month: str | None = None, change_type: str = "buy", limit: int = 30,
    ) -> list[MFHoldingChange]:
        """Get month-over-month MF holding changes.

        change_type: "buy" for new+increased, "sell" for exits+decreased
        """
        if month is None:
            row = self._conn.execute("SELECT MAX(month) as m FROM mf_scheme_holdings").fetchone()
            if not row or not row["m"]:
                return []
            month = row["m"]

        # Find previous month
        year, mon = int(month[:4]), int(month[5:7])
        if mon == 1:
            prev_month = f"{year - 1}-12"
        else:
            prev_month = f"{year}-{mon - 1:02d}"

        if change_type == "buy":
            # New positions (in curr but not in prev) + increased positions
            rows = self._conn.execute("""
                SELECT c.stock_name, c.isin, c.amc, c.scheme_name,
                    ? as prev_month, ? as curr_month,
                    COALESCE(p.quantity, 0) as prev_qty, c.quantity as curr_qty,
                    c.quantity - COALESCE(p.quantity, 0) as qty_change,
                    COALESCE(p.market_value_lakhs, 0) as prev_value,
                    c.market_value_lakhs as curr_value,
                    CASE WHEN p.isin IS NULL THEN 'NEW' ELSE 'INCREASE' END as change_type
                FROM mf_scheme_holdings c
                LEFT JOIN mf_scheme_holdings p ON c.isin = p.isin
                    AND c.amc = p.amc AND c.scheme_name = p.scheme_name
                    AND p.month = ?
                WHERE c.month = ?
                    AND (p.isin IS NULL OR c.quantity > p.quantity)
                ORDER BY c.market_value_lakhs - COALESCE(p.market_value_lakhs, 0) DESC
                LIMIT ?
            """, (prev_month, month, prev_month, month, limit)).fetchall()
        else:
            # Exits (in prev but not in curr) + decreased positions
            rows = self._conn.execute("""
                SELECT p.stock_name, p.isin, p.amc, p.scheme_name,
                    ? as prev_month, ? as curr_month,
                    p.quantity as prev_qty, COALESCE(c.quantity, 0) as curr_qty,
                    COALESCE(c.quantity, 0) - p.quantity as qty_change,
                    p.market_value_lakhs as prev_value,
                    COALESCE(c.market_value_lakhs, 0) as curr_value,
                    CASE WHEN c.isin IS NULL THEN 'EXIT' ELSE 'DECREASE' END as change_type
                FROM mf_scheme_holdings p
                LEFT JOIN mf_scheme_holdings c ON p.isin = c.isin
                    AND p.amc = c.amc AND p.scheme_name = c.scheme_name
                    AND c.month = ?
                WHERE p.month = ?
                    AND (c.isin IS NULL OR c.quantity < p.quantity)
                ORDER BY p.market_value_lakhs - COALESCE(c.market_value_lakhs, 0) DESC
                LIMIT ?
            """, (prev_month, month, month, prev_month, limit)).fetchall()

        return [MFHoldingChange(
            stock_name=r["stock_name"], isin=r["isin"], amc=r["amc"],
            scheme_name=r["scheme_name"], prev_month=r["prev_month"],
            curr_month=r["curr_month"], prev_qty=r["prev_qty"],
            curr_qty=r["curr_qty"], qty_change=r["qty_change"],
            prev_value=r["prev_value"], curr_value=r["curr_value"],
            change_type=r["change_type"],
        ) for r in rows]

    def get_mf_portfolio_summary(self, month: str | None = None) -> list[dict]:
        """Get AMC-level portfolio summary for a month."""
        if month is None:
            row = self._conn.execute("SELECT MAX(month) as m FROM mf_scheme_holdings").fetchone()
            if not row or not row["m"]:
                return []
            month = row["m"]

        rows = self._conn.execute(
            "SELECT amc, COUNT(DISTINCT scheme_name) as num_schemes, "
            "COUNT(DISTINCT isin) as num_stocks, "
            "SUM(market_value_lakhs) as total_value_lakhs "
            "FROM mf_scheme_holdings WHERE month = ? "
            "GROUP BY amc ORDER BY total_value_lakhs DESC",
            (month,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> FlowStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _row_to_flow(row: sqlite3.Row) -> DailyFlow:
    """Convert a database row to a DailyFlow model."""
    return DailyFlow(
        date=date.fromisoformat(row["date"]),
        category=row["category"],
        buy_value=row["buy_value"],
        sell_value=row["sell_value"],
        net_value=row["net_value"],
    )


def _rows_to_pair(rows: list[sqlite3.Row]) -> DailyFlowPair | None:
    """Convert rows for a single date into a DailyFlowPair."""
    fii = dii = None
    for row in rows:
        flow = _row_to_flow(row)
        if flow.category == "FII":
            fii = flow
        elif flow.category == "DII":
            dii = flow

    if fii is None or dii is None:
        return None

    return DailyFlowPair(date=fii.date, fii=fii, dii=dii)
