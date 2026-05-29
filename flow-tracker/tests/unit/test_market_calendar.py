"""Tests for the MarketCalendar trading-day abstraction (Phase 2).

These lock in behavior-identity with the legacy ``weekday() < 5`` checks:
NSE (and every market, for now) is open Mon–Fri, closed Sat/Sun. No real
holiday calendar is involved.
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


def test_market_param_is_uniform_across_markets():
    """Logic is uniform now: every market gives the same answer for a given day."""
    start = date(2026, 5, 25)
    for offset in range(14):
        d = start + timedelta(days=offset)
        nse = MarketCalendar.is_trading_day(d, Market.NSE)
        nasdaq = MarketCalendar.is_trading_day(d, Market.NASDAQ)
        assert nse == nasdaq == (d.weekday() < 5)
