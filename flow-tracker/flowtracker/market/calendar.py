"""Trading-calendar abstraction (Phase 2).

Centralizes the scattered ``date.weekday() < 5`` checks behind a
market-parameterized API. Behavior is intentionally IDENTICAL to the legacy
weekday logic — NSE is treated as open Mon–Fri. A real exchange holiday list
is deliberately NOT introduced here (that would change which days the crons
attempt to fetch). The HTTP "404 = no data" fallback in the clients stays as
the authoritative holiday signal.
"""
from __future__ import annotations
from datetime import date, datetime
from flowtracker.market import Market, DEFAULT_MARKET


class MarketCalendar:
    @staticmethod
    def is_trading_day(d: "date | datetime", market: Market = DEFAULT_MARKET) -> bool:
        """True if ``d`` is a trading day for ``market``. Currently weekday-based
        (Mon–Fri) for all markets — behavior-identical to the legacy weekday()<5."""
        return d.weekday() < 5
