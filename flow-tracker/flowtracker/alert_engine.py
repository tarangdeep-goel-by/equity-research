"""Alert evaluation engine — checks conditions against latest store data."""

from __future__ import annotations

import logging

from flowtracker.alert_models import Alert, TriggeredAlert
from flowtracker.store import FlowStore

logger = logging.getLogger(__name__)


def check_all_alerts(store: FlowStore) -> list[TriggeredAlert]:
    """Evaluate all active alerts against current data. Returns triggered alerts."""
    alerts = store.get_active_alerts()
    triggered: list[TriggeredAlert] = []

    for alert in alerts:
        current_value = _get_metric_value(store, alert.symbol, alert.condition_type)
        if current_value is None:
            continue
        if _condition_met(current_value, alert.condition_type, alert.threshold):
            message = _format_message(alert, current_value)
            store.log_alert_trigger(alert.id, current_value, message)
            triggered.append(TriggeredAlert(
                alert=alert, current_value=current_value, message=message,
            ))

    return triggered


def _get_metric_value(store: FlowStore, symbol: str, condition_type: str) -> float | None:
    """Get current metric value from store for a condition type."""
    try:
        if condition_type in ("price_above", "price_below"):
            row = store._conn.execute(
                "SELECT price FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return row["price"] if row else None

        elif condition_type in ("pe_above", "pe_below"):
            row = store._conn.execute(
                "SELECT pe_trailing FROM valuation_snapshot WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return row["pe_trailing"] if row else None

        elif condition_type == "fii_pct_below":
            row = store._conn.execute(
                "SELECT percentage FROM shareholding WHERE symbol = ? AND category = 'FII' "
                "ORDER BY quarter_end DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return row["percentage"] if row else None

        elif condition_type == "mf_pct_above":
            row = store._conn.execute(
                "SELECT percentage FROM shareholding WHERE symbol = ? AND category = 'DII' "
                "ORDER BY quarter_end DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return row["percentage"] if row else None

        elif condition_type in ("rsi_below", "rsi_above"):
            row = store._conn.execute(
                "SELECT value FROM fmp_technical_indicators "
                "WHERE symbol = ? AND indicator = 'rsi' ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return row["value"] if row else None

        elif condition_type == "pledge_above":
            row = store._conn.execute(
                "SELECT pledge_pct FROM promoter_pledge WHERE symbol = ? "
                "ORDER BY quarter_end DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            return row["pledge_pct"] if row else None

        elif condition_type == "dcf_upside_above":
            row = store._conn.execute(
                "SELECT dcf, stock_price FROM fmp_dcf WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row and row["dcf"] and row["stock_price"] and row["stock_price"] > 0:
                return (row["dcf"] - row["stock_price"]) / row["stock_price"] * 100
            return None
    except Exception as e:
        logger.warning("Failed to get metric for %s/%s: %s", symbol, condition_type, e)
    return None


def _condition_met(value: float, condition_type: str, threshold: float) -> bool:
    """Check if a condition is met."""
    if condition_type in ("price_above", "pe_above", "mf_pct_above", "rsi_above", "pledge_above", "dcf_upside_above"):
        return value > threshold
    elif condition_type in ("price_below", "pe_below", "fii_pct_below", "rsi_below"):
        return value < threshold
    return False


def _format_message(alert: Alert, value: float) -> str:
    """Format a human-readable alert message."""
    return f"{alert.symbol}: {alert.condition_type} triggered — current {value:.2f} vs threshold {alert.threshold:.2f}"
