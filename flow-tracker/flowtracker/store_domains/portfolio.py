"""Portfolio + alerts domain (split from FlowStore, refactor P1.4).

Methods moved verbatim from store.py. They run on the FlowStore instance via
mixin composition, so ``self._conn`` is the shared connection.
"""

from __future__ import annotations

from flowtracker.alert_models import Alert
from flowtracker.portfolio_models import PortfolioHolding


class PortfolioMixin:
    """User portfolio holdings + condition-based alerts."""

    # -- Portfolio --

    def upsert_portfolio_holding(self, holding: PortfolioHolding) -> int:
        """Insert or replace a portfolio holding."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO portfolio_holdings "
            "(symbol, quantity, avg_cost, buy_date, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (holding.symbol, holding.quantity, holding.avg_cost,
             holding.buy_date, holding.notes),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_portfolio_holdings(self) -> list[PortfolioHolding]:
        """Get all portfolio holdings."""
        rows = self._conn.execute(
            "SELECT * FROM portfolio_holdings ORDER BY symbol"
        ).fetchall()
        return [PortfolioHolding(
            symbol=r["symbol"], quantity=r["quantity"],
            avg_cost=r["avg_cost"], buy_date=r["buy_date"],
            notes=r["notes"], added_at=r["added_at"],
        ) for r in rows]

    def remove_portfolio_holding(self, symbol: str) -> bool:
        """Remove a holding. Returns True if deleted."""
        cursor = self._conn.cursor()
        cursor.execute(
            "DELETE FROM portfolio_holdings WHERE symbol = ?", (symbol,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Alerts --

    def upsert_alert(self, alert: Alert) -> int:
        """Insert a new alert. Returns the alert ID."""
        cursor = self._conn.cursor()
        cursor.execute(
            "INSERT INTO alerts (symbol, condition_type, threshold, notes) "
            "VALUES (?, ?, ?, ?)",
            (alert.symbol, alert.condition_type, alert.threshold, alert.notes),
        )
        self._conn.commit()
        return cursor.lastrowid

    def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts."""
        rows = self._conn.execute(
            "SELECT * FROM alerts WHERE active = 1 ORDER BY symbol, condition_type"
        ).fetchall()
        return [Alert(
            id=r["id"], symbol=r["symbol"], condition_type=r["condition_type"],
            threshold=r["threshold"], active=bool(r["active"]),
            last_triggered=r["last_triggered"], created_at=r["created_at"],
            notes=r["notes"],
        ) for r in rows]

    def deactivate_alert(self, alert_id: int) -> bool:
        """Deactivate an alert. Returns True if found."""
        cursor = self._conn.cursor()
        cursor.execute(
            "UPDATE alerts SET active = 0 WHERE id = ?", (alert_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def log_alert_trigger(self, alert_id: int, value: float | None, message: str) -> None:
        """Log an alert trigger and update last_triggered."""
        self._conn.execute(
            "INSERT INTO alert_history (alert_id, current_value, message) VALUES (?, ?, ?)",
            (alert_id, value, message),
        )
        self._conn.execute(
            "UPDATE alerts SET last_triggered = datetime('now') WHERE id = ?",
            (alert_id,),
        )
        self._conn.commit()

    def get_alert_history(self, limit: int = 20) -> list[dict]:
        """Get recent alert trigger history."""
        rows = self._conn.execute(
            "SELECT ah.*, a.symbol, a.condition_type, a.threshold "
            "FROM alert_history ah JOIN alerts a ON ah.alert_id = a.id "
            "ORDER BY ah.triggered_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
