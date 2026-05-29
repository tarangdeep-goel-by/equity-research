"""FII/DII + mutual fund flows domain (split from FlowStore, refactor P1.4).

Methods moved verbatim from store.py. They run on the FlowStore instance via
mixin composition, so ``self._conn`` is the shared connection. The module-level
row helpers (``_row_to_flow`` / ``_rows_to_pair``) still live in store.py and
are imported lazily inside the methods that use them to avoid a circular import
(store.py imports this mixin for its bases).
"""

from __future__ import annotations

from datetime import date

from flowtracker.models import DailyFlow, DailyFlowPair, StreakInfo
from flowtracker.mf_models import MFMonthlyFlow, MFAUMSummary, MFDailyFlow


class FlowsMixin:
    """FII/DII daily flows + MF monthly/daily flows + AUM."""

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
        from flowtracker.store import _rows_to_pair
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
        from flowtracker.store import _row_to_flow
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
