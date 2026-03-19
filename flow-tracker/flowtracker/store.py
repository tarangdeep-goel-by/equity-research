"""SQLite persistence for FII/DII daily flow data."""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from flowtracker.models import DailyFlow, DailyFlowPair, StreakInfo
from flowtracker.mf_models import MFMonthlyFlow, MFAUMSummary
from flowtracker.holding_models import WatchlistEntry, ShareholdingRecord, ShareholdingChange
from flowtracker.scan_models import IndexConstituent, ScanSummary
from flowtracker.fund_models import QuarterlyResult, ValuationSnapshot, ValuationBand

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
