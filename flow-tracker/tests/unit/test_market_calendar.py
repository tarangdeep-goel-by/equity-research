"""Tests for the MarketCalendar trading-day abstraction.

NSE/BSE tests lock in behavior-identity with the legacy ``weekday() < 5``
checks: India is open Mon–Fri, closed Sat/Sun, with no real holiday calendar
(regression lock — India must stay invariant). NASDAQ/NYSE tests assert the
real US exchange holiday calendar (via ``pandas_market_calendars``) is applied,
and that US and India diverge on US-only holidays.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from flowtracker.market import DEFAULT_MARKET, Market, MarketCalendar


def test_is_trading_day_matches_legacy_weekday_over_span():
    """Over a 14-day span, is_trading_day must equal the legacy weekday()<5."""
    start = date(2026, 5, 25)  # Monday
    for offset in range(14):
        d = start + timedelta(days=offset)
        assert MarketCalendar.is_trading_day(d) == (d.weekday() < 5)


def test_weekdays_true_weekends_false():
    # 2026-05-25 is a Monday → Mon..Fri True, Sat/Sun False
    monday = date(2026, 5, 25)
    expected = [True, True, True, True, True, False, False]
    for offset, exp in enumerate(expected):
        assert MarketCalendar.is_trading_day(monday + timedelta(days=offset)) is exp


def test_accepts_date_and_datetime():
    friday = date(2026, 5, 29)
    saturday = date(2026, 5, 30)
    # date input
    assert MarketCalendar.is_trading_day(friday) is True
    assert MarketCalendar.is_trading_day(saturday) is False
    # datetime input (same calendar days, arbitrary time-of-day)
    assert MarketCalendar.is_trading_day(datetime(2026, 5, 29, 15, 30)) is True
    assert MarketCalendar.is_trading_day(datetime(2026, 5, 30, 9, 0)) is False


def test_default_market_param():
    d = date(2026, 5, 29)  # Friday
    assert MarketCalendar.is_trading_day(d) == MarketCalendar.is_trading_day(d, DEFAULT_MARKET)
    assert DEFAULT_MARKET is Market.NSE


def test_nse_unchanged_weekdays_true_weekends_false():
    """Regression lock: NSE stays weekday-based, identical to the legacy logic.

    India must NOT gain a holiday calendar — even on a date that is a US market
    holiday, NSE follows weekday() < 5.
    """
    start = date(2026, 5, 25)  # Monday (also US Memorial Day)
    for offset in range(14):
        d = start + timedelta(days=offset)
        assert MarketCalendar.is_trading_day(d, Market.NSE) == (d.weekday() < 5)
        assert MarketCalendar.is_trading_day(d, Market.BSE) == (d.weekday() < 5)


# --- US exchange holiday calendar (NASDAQ / NYSE) ---------------------------

US_HOLIDAYS_2025 = [
    date(2025, 1, 1),   # New Year's Day
    date(2025, 7, 4),   # Independence Day
    date(2025, 12, 25),  # Christmas Day
]


def test_us_market_holidays_are_closed():
    for holiday in US_HOLIDAYS_2025:
        assert MarketCalendar.is_trading_day(holiday, Market.NASDAQ) is False
        assert MarketCalendar.is_trading_day(holiday, Market.NYSE) is False


def test_us_normal_weekday_is_open():
    weekday = date(2025, 7, 3)  # Thursday, normal trading day
    assert MarketCalendar.is_trading_day(weekday, Market.NASDAQ) is True
    assert MarketCalendar.is_trading_day(weekday, Market.NYSE) is True


def test_us_weekend_is_closed():
    saturday = date(2025, 7, 5)
    sunday = date(2025, 7, 6)
    assert MarketCalendar.is_trading_day(saturday, Market.NASDAQ) is False
    assert MarketCalendar.is_trading_day(sunday, Market.NYSE) is False


def test_us_accepts_datetime_input():
    holiday = datetime(2025, 7, 4, 13, 0)  # time-of-day must not matter
    weekday = datetime(2025, 7, 3, 9, 30)
    assert MarketCalendar.is_trading_day(holiday, Market.NASDAQ) is False
    assert MarketCalendar.is_trading_day(weekday, Market.NASDAQ) is True


def test_us_and_india_diverge_on_us_weekday_holiday():
    """A US holiday that falls on a weekday: NASDAQ/NYSE closed, NSE/BSE open.

    This proves the markets diverge correctly — India keeps weekday logic while
    the US applies its real holiday calendar.
    """
    july4 = date(2025, 7, 4)  # Friday — a weekday
    assert july4.weekday() < 5  # sanity: it's a weekday
    # India: open (weekday logic, no holiday calendar)
    assert MarketCalendar.is_trading_day(july4, Market.NSE) is True
    assert MarketCalendar.is_trading_day(july4, Market.BSE) is True
    # US: closed (Independence Day)
    assert MarketCalendar.is_trading_day(july4, Market.NASDAQ) is False
    assert MarketCalendar.is_trading_day(july4, Market.NYSE) is False


def test_us_falls_back_to_weekday_on_calendar_error(monkeypatch):
    """If the calendar lookup raises, US silently falls back to weekday logic."""
    import flowtracker.market.calendar as cal_mod

    def boom(name):
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(cal_mod, "_get_calendar", boom)
    # July 4 is a weekday → fallback returns True (no crash)
    assert MarketCalendar.is_trading_day(date(2025, 7, 4), Market.NASDAQ) is True
    # A weekend → fallback returns False
    assert MarketCalendar.is_trading_day(date(2025, 7, 5), Market.NASDAQ) is False
