"""Catalyst event gathering from multiple data sources."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta

from .catalyst_models import IMPACT_MAP, STATIC_CALENDAR, CatalystEvent

logger = logging.getLogger(__name__)


def gather_catalysts(
    symbol: str, store, days: int = 90,
) -> list[CatalystEvent]:
    """Gather catalyst events from all sources, deduplicate, and sort by date.

    Calls four source functions. Each is wrapped in try/except so a single
    failure never blocks the rest.  Events are deduped by
    (event_type, event_date, symbol) — when duplicates exist the confirmed
    event wins.
    """
    from .store import FlowStore  # deferred to avoid circular imports

    events: list[CatalystEvent] = []

    sources = [
        ("yfinance", lambda: _fetch_yfinance_calendar(symbol)),
        ("bse_filing", lambda: _extract_filing_events(symbol, store)),
        ("static", lambda: _get_static_events(days)),
        ("estimated", lambda: _estimate_next_results(symbol, store)),
    ]

    for name, fn in sources:
        try:
            events.extend(fn())
        except Exception:
            logger.warning("catalyst source '%s' failed for %s", name, symbol, exc_info=True)

    # Compute days_until and filter to window
    today = date.today()
    cutoff = today + timedelta(days=days)
    filtered: list[CatalystEvent] = []
    for ev in events:
        ev.days_until = (ev.event_date - today).days
        if today <= ev.event_date <= cutoff:
            filtered.append(ev)

    # Deduplicate: keep confirmed over unconfirmed for same (event_type, event_date, symbol)
    seen: dict[tuple, CatalystEvent] = {}
    for ev in filtered:
        key = (ev.event_type, ev.event_date, ev.symbol)
        existing = seen.get(key)
        if existing is None:
            seen[key] = ev
        elif ev.confirmed and not existing.confirmed:
            seen[key] = ev

    return sorted(seen.values(), key=lambda e: e.event_date)


# ---------------------------------------------------------------------------
# Source 1: yfinance calendar
# ---------------------------------------------------------------------------

def _fetch_yfinance_calendar(symbol: str) -> list[CatalystEvent]:
    """Fetch upcoming calendar events from yfinance."""
    import yfinance as yf  # optional dependency

    ticker = yf.Ticker(f"{symbol}.NS")
    cal = ticker.calendar

    events: list[CatalystEvent] = []
    today = date.today()

    if cal is None:
        return events

    # yfinance returns a dict (modern) or DataFrame (older versions)
    if hasattr(cal, "to_dict"):
        # DataFrame — transpose so keys are event names
        cal = cal.to_dict()

    if isinstance(cal, dict):
        # Earnings date — can be a single Timestamp or list
        earnings_raw = cal.get("Earnings Date") or cal.get("Earnings Dates")
        if earnings_raw is not None:
            if not isinstance(earnings_raw, list):
                earnings_raw = [earnings_raw]
            for ts in earnings_raw:
                try:
                    d = _to_date(ts)
                    events.append(CatalystEvent(
                        symbol=symbol,
                        event_type="earnings",
                        event_date=d,
                        days_until=(d - today).days,
                        description=f"{symbol} earnings release",
                        impact=IMPACT_MAP["earnings"],
                        source="yfinance",
                    ))
                except Exception:
                    pass

        # Ex-dividend date
        ex_div = cal.get("Ex-Dividend Date")
        if ex_div is not None:
            try:
                d = _to_date(ex_div)
                events.append(CatalystEvent(
                    symbol=symbol,
                    event_type="ex_dividend",
                    event_date=d,
                    days_until=(d - today).days,
                    description=f"{symbol} ex-dividend date",
                    impact=IMPACT_MAP["ex_dividend"],
                    source="yfinance",
                ))
            except Exception:
                pass

        # Dividend date
        div_date = cal.get("Dividend Date")
        if div_date is not None:
            try:
                d = _to_date(div_date)
                events.append(CatalystEvent(
                    symbol=symbol,
                    event_type="ex_dividend",
                    event_date=d,
                    days_until=(d - today).days,
                    description=f"{symbol} dividend payment date",
                    impact=IMPACT_MAP["ex_dividend"],
                    source="yfinance",
                ))
            except Exception:
                pass

    return events


def _to_date(val) -> date:
    """Convert a yfinance Timestamp / datetime / str to date."""
    if isinstance(val, date):
        return val
    if hasattr(val, "date"):
        return val.date()
    return date.fromisoformat(str(val)[:10])


# ---------------------------------------------------------------------------
# Source 2: BSE filing events
# ---------------------------------------------------------------------------

def _extract_filing_events(symbol: str, store) -> list[CatalystEvent]:
    """Extract catalyst events from stored BSE corporate filings."""
    filings = store.get_filings(symbol, limit=200)
    events: list[CatalystEvent] = []

    keywords_board = ("board meeting", "meeting of the board")
    keywords_results = ("financial result", "quarterly result", "un-audited", "unaudited", "audited")

    for f in filings:
        headline_lower = (f.headline or "").lower()
        category_lower = (f.category or "").lower()
        subcategory_lower = (f.subcategory or "").lower()
        combined = f"{headline_lower} {category_lower} {subcategory_lower}"

        event_type: str | None = None
        desc = f.headline or ""

        if any(kw in combined for kw in keywords_board):
            event_type = "board_meeting"
        elif any(kw in combined for kw in keywords_results):
            event_type = "earnings"

        if event_type and f.filing_date:
            try:
                d = date.fromisoformat(f.filing_date[:10])
            except (ValueError, TypeError):
                continue
            events.append(CatalystEvent(
                symbol=symbol,
                event_type=event_type,
                event_date=d,
                days_until=0,  # computed later in gather_catalysts
                description=desc[:120],
                impact=IMPACT_MAP.get(event_type, "medium"),
                source="bse_filing",
            ))

    return events


# ---------------------------------------------------------------------------
# Source 3: Static calendar (RBI, budget, etc.)
# ---------------------------------------------------------------------------

def _get_static_events(days: int) -> list[CatalystEvent]:
    """Return static calendar events within the window."""
    today = date.today()
    cutoff = today + timedelta(days=days)
    events: list[CatalystEvent] = []

    for entry in STATIC_CALENDAR:
        d = date.fromisoformat(str(entry["event_date"]))
        if today <= d <= cutoff:
            events.append(CatalystEvent(
                symbol=None,
                event_type=entry["event_type"],
                event_date=d,
                days_until=(d - today).days,
                description=entry["description"],
                impact=entry.get("impact", IMPACT_MAP.get(entry["event_type"], "medium")),
                source="static",
            ))

    return events


# ---------------------------------------------------------------------------
# Source 4: Estimated next results from quarterly history
# ---------------------------------------------------------------------------

def _estimate_next_results(symbol: str, store) -> list[CatalystEvent]:
    """Estimate next quarterly results date from historical pattern."""
    results = store.get_quarterly_results(symbol, limit=12)
    if len(results) < 2:
        return []

    # Parse quarter_end dates and find typical month gaps
    quarter_dates: list[date] = []
    for r in results:
        try:
            quarter_dates.append(date.fromisoformat(r.quarter_end[:10]))
        except (ValueError, TypeError):
            continue

    if len(quarter_dates) < 2:
        return []

    # Sort ascending
    quarter_dates.sort()

    # Find the most common month for quarter ends
    month_counts = Counter(d.month for d in quarter_dates)
    # Get sorted unique months
    typical_months = sorted(month_counts.keys())

    # Last known quarter end
    last_qe = quarter_dates[-1]
    today = date.today()

    # Find the next quarter-end month after last_qe
    estimated_dates: list[date] = []
    for offset_years in range(0, 2):
        for m in typical_months:
            # Use last day-ish of the month (quarter ends are typically month-end)
            year = last_qe.year + offset_years
            try:
                # Use the typical day from historical data for this month
                historical_days = [d.day for d in quarter_dates if d.month == m]
                day = max(historical_days) if historical_days else 28
                candidate = date(year, m, min(day, 28))
            except ValueError:
                continue

            if candidate > last_qe and candidate > today:
                estimated_dates.append(candidate)

    if not estimated_dates:
        return []

    # Take the nearest future estimated date
    next_date = min(estimated_dates)

    return [CatalystEvent(
        symbol=symbol,
        event_type="results_estimated",
        event_date=next_date,
        days_until=(next_date - today).days,
        description=f"{symbol} estimated next quarterly results",
        impact=IMPACT_MAP["results_estimated"],
        source="estimated",
        confirmed=False,
    )]


# ---------------------------------------------------------------------------
# Watchlist aggregation
# ---------------------------------------------------------------------------

def gather_watchlist_catalysts(
    symbols: list[str], store, days: int = 90,
) -> list[CatalystEvent]:
    """Gather catalysts for multiple symbols, merge and sort by date."""
    all_events: list[CatalystEvent] = []
    for sym in symbols:
        try:
            all_events.extend(gather_catalysts(sym, store, days=days))
        except Exception:
            logger.warning("failed to gather catalysts for %s", sym, exc_info=True)

    # Static events may be duplicated across calls — deduplicate
    seen: dict[tuple, CatalystEvent] = {}
    for ev in all_events:
        key = (ev.event_type, ev.event_date, ev.symbol)
        existing = seen.get(key)
        if existing is None:
            seen[key] = ev
        elif ev.confirmed and not existing.confirmed:
            seen[key] = ev

    return sorted(seen.values(), key=lambda e: e.event_date)
