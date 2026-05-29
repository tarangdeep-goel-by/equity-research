"""Trading-calendar abstraction.

Centralizes the scattered ``date.weekday() < 5`` checks behind a
market-parameterized API.

India (NSE/BSE) stays weekday-based — open Mon–Fri — exactly as the legacy
logic. A real exchange holiday list is deliberately NOT introduced for India
(that would change which days the crons attempt to fetch); the HTTP
"404 = no data" fallback in the clients stays as the authoritative holiday
signal.

US markets (NASDAQ/NYSE) DO use a real exchange holiday calendar via
``pandas_market_calendars`` so US trading-day checks reflect actual closures
(New Year's, Independence Day, Christmas, etc.). If that library errors for any
reason, US falls back to the same weekday-based logic and logs — it never
crashes.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from flowtracker.market import DEFAULT_MARKET, Market

logger = logging.getLogger(__name__)

# Markets that use a real exchange holiday calendar (everything else is
# weekday-based). The value is the pandas_market_calendars calendar name.
_US_CALENDAR_NAMES: dict[Market, str] = {
    Market.NASDAQ: "NASDAQ",
    Market.NYSE: "NYSE",
}

# Built calendars are cached module-level so each is constructed once.
_calendar_cache: dict[str, object] = {}


def _get_calendar(name: str):
    """Return a cached pandas_market_calendars calendar, building on first use."""
    cal = _calendar_cache.get(name)
    if cal is None:
        import pandas_market_calendars as mcal

        cal = mcal.get_calendar(name)
        _calendar_cache[name] = cal
    return cal


class MarketCalendar:
    @staticmethod
    def is_trading_day(d: "date | datetime", market: Market = DEFAULT_MARKET) -> bool:
        """True if ``d`` is a trading day for ``market``.

        NSE/BSE: weekday-based (Mon–Fri), behavior-identical to the legacy
        ``weekday() < 5``. NASDAQ/NYSE: real exchange holiday calendar via
        ``pandas_market_calendars`` (falls back to weekday-based on any error).
        Accepts either a ``date`` or a ``datetime``.
        """
        # Normalize datetime → date so time-of-day never affects the answer.
        day = d.date() if isinstance(d, datetime) else d

        cal_name = _US_CALENDAR_NAMES.get(market)
        if cal_name is None:
            # India and any non-US market: unchanged weekday logic.
            return day.weekday() < 5

        try:
            cal = _get_calendar(cal_name)
            return not cal.schedule(start_date=day, end_date=day).empty
        except Exception:  # noqa: BLE001 — never crash on calendar lookup
            logger.warning(
                "pandas_market_calendars lookup failed for %s on %s; "
                "falling back to weekday-based check",
                cal_name,
                day,
                exc_info=True,
            )
            return day.weekday() < 5
