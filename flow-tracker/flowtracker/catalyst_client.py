"""Catalyst event gathering from multiple data sources."""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, timedelta

from .catalyst_models import IMPACT_MAP, STATIC_CALENDAR, CatalystEvent, MADealDetails

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# M&A deal parsing — Wave 4-5 P2 (2026-04-25)
# ---------------------------------------------------------------------------
# Pharma autoeval (SUNPHARMA / DRREDDY / CIPLA) flagged that
# `get_events_actions(catalysts=True)` returned acquisition headlines but no
# structured deal info (size, target, status). The headline + filing-body
# regex below extracts the four most-asked fields agents need:
#   - deal_size (currency + amount)
#   - deal_target (acquired/divested entity name)
#   - deal_target_country
#   - deal_status (announced | pending_regulatory | closed | terminated)
#
# Approach: lightweight regex with sector-aware fallback. We don't try to
# resolve every possible filing layout — we cover the patterns observed in
# pharma + IT-services + auto + cement filings, since those drive most M&A
# deal flow on Indian exchanges.

# Deal size: capture amount + currency. Patterns observed:
#   "USD 1.2 billion"         "1,200 crore"      "INR 500 crore"
#   "$ 800 million"           "Rs. 1,500 cr"     "EUR 250 mn"
#   "₹2,400 crore"            "USD 350 mn"
_DEAL_SIZE_RE = re.compile(
    r"(?:"
    # Pattern A: currency word/symbol BEFORE amount
    r"(?P<cur1>USD|INR|EUR|GBP|JPY|US\$|Rs\.?|INR|₹|\$|€|£)\s*"
    r"(?P<amt1>[\d,]+(?:\.\d+)?)\s*"
    r"(?P<unit1>billion|bn|million|mn|crore|cr|lakh|lakhs)?"
    r"|"
    # Pattern B: amount BEFORE currency word (Rs.1500 crore form)
    r"(?P<amt2>[\d,]+(?:\.\d+)?)\s*"
    r"(?P<unit2>billion|bn|million|mn|crore|cr|lakh|lakhs)\s*"
    r"(?:\(?(?P<cur2>USD|INR|EUR|GBP|JPY|US\$|Rs\.?|INR|₹|\$|€|£)\)?)?"
    r")",
    re.IGNORECASE,
)

# Currency → ISO code
_CURRENCY_NORM = {
    "USD": "USD", "US$": "USD", "$": "USD",
    "INR": "INR", "RS": "INR", "RS.": "INR", "₹": "INR",
    "EUR": "EUR", "€": "EUR",
    "GBP": "GBP", "£": "GBP",
    "JPY": "JPY",
}

# Multipliers — convert raw → "natural" units (millions for USD/EUR/GBP/JPY,
# crores for INR). Crore conversion: 1 crore = 10 million; we keep crores
# as the canonical INR unit per CLAUDE.md ("Monetary values in crores").
_UNIT_MULTIPLIER_NATIVE = {
    "billion": 1000, "bn": 1000,
    "million": 1, "mn": 1,
    "crore": 1, "cr": 1,    # crore stays as crore (INR canonical)
    "lakh": 0.01, "lakhs": 0.01,  # 100 lakh = 1 crore
}

# INR conversion: when the raw is in crore, we already have crores. When it's
# in million USD, we leave deal_size_cr null (caller can convert via FX if
# needed). We store both deal_size_native (in disclosure currency unit) and
# deal_size_cr (only when currency is INR, per CLAUDE.md crore rule).

# Deal status keywords. Order matters — first match wins. Looser patterns
# at the bottom. The leading `\b` anchors the keyword start; the trailing edge
# is left unanchored so word-stems like `terminat`/`announc` match all
# inflections (terminates, terminated, announces, announced, etc.).
_STATUS_KEYWORDS: list[tuple[str, re.Pattern[str]]] = [
    ("terminated", re.compile(r"\b(terminat\w*|withdraw\w*|cancel\w*|aband\w*|call(ed)?\s+off|dropp?ed)", re.IGNORECASE)),
    ("closed", re.compile(r"\b(complet\w*|conclud\w*|clos(ed|ing)|consummat\w*|finaliz\w*|fully\s+integrat\w*|merger\s+effective)", re.IGNORECASE)),
    ("pending_regulatory", re.compile(r"\b(subject\s+to|pending\s+(regulatory|approval|cci|sebi|fda|antitrust)|awaiting\s+(regulatory|approval)|cci\s+approval|regulatory\s+(approval|clearance)\s+pending)", re.IGNORECASE)),
    ("announced", re.compile(r"\b(announc\w*|sign(ed)?\s+(definitive|spa|share\s+purchase)|enter(ed)?\s+into\s+(an?\s+)?agreement|definitive\s+agreement|to\s+acquire|will\s+acquire|propos(ed|al))", re.IGNORECASE)),
]

# Target-name extraction: strict patterns to keep precision high.
# "to acquire X" / "acquisition of X" / "buying X" / "acquired X" /
# "purchase of X by" / "for acquisition of X"
_TARGET_RE = re.compile(
    r"(?:"
    r"(?:to\s+acquire|acquir(?:e|ed|ing|es|ition\s+of)|buy(?:ing|out\s+of)|purchas(?:e|ing)\s+of)\s+"
    r"(?P<target>[A-Z][A-Za-z0-9&'\.\- ]{2,80}?)"
    r"(?=\s+(?:for|by|in|to|from|at|,|\.|$|—|–|\(|with))"
    r")",
)

# Country detection: lightweight — check well-known country names.
_COUNTRY_KEYWORDS = {
    "US": re.compile(r"\b(United\s+States|U\.?S\.?A?\.?|US-based)\b", re.IGNORECASE),
    "UK": re.compile(r"\b(United\s+Kingdom|U\.?K\.?|UK-based|British)\b", re.IGNORECASE),
    "Germany": re.compile(r"\b(German|Germany)\b", re.IGNORECASE),
    "France": re.compile(r"\b(French|France)\b", re.IGNORECASE),
    "Japan": re.compile(r"\b(Japanese|Japan)\b", re.IGNORECASE),
    "China": re.compile(r"\b(Chinese|China-based)\b", re.IGNORECASE),
    "India": re.compile(r"\b(Indian|India-based)\b", re.IGNORECASE),
    "Israel": re.compile(r"\b(Israeli|Israel-based)\b", re.IGNORECASE),
    "Switzerland": re.compile(r"\b(Swiss|Switzerland)\b", re.IGNORECASE),
    "Australia": re.compile(r"\b(Australian|Australia-based)\b", re.IGNORECASE),
}


def parse_ma_deal_from_filing(
    headline: str, body: str | None = None,
) -> MADealDetails | None:
    """Parse an M&A filing's headline + optional body into structured deal fields.

    Returns None when no recognizable deal-size pattern AND no recognizable
    target name appears — i.e. the filing is too vague to extract anything
    useful. Returns MADealDetails(...) with whatever fields parsed when at
    least one usable signal is found.

    Caller passes in headline (always present from BSE filings) + optional
    body (filing description / press-release text). Body is searched first
    when provided since headlines truncate aggressively on BSE.
    """
    if not headline:
        return None
    text = " ".join(t for t in (body, headline) if t)

    # --- Deal size ---
    deal_size_native: float | None = None
    deal_size_currency: str | None = None
    deal_size_cr: float | None = None

    m = _DEAL_SIZE_RE.search(text)
    if m:
        cur = (m.group("cur1") or m.group("cur2") or "").upper().strip(".")
        amt_raw = m.group("amt1") or m.group("amt2")
        unit = (m.group("unit1") or m.group("unit2") or "").lower()
        if cur and amt_raw:
            try:
                amt = float(amt_raw.replace(",", ""))
                multiplier = _UNIT_MULTIPLIER_NATIVE.get(unit, 1)
                # Store native in "disclosure unit" (millions for USD/EUR; crore for INR).
                # We multiply billion→1000 to get to millions equivalent, etc.
                deal_size_native = round(amt * multiplier, 2)
                deal_size_currency = _CURRENCY_NORM.get(cur)
                # Convert to crore when currency is INR. crore is already canonical
                # for INR so multiplier collapses to native.
                if deal_size_currency == "INR":
                    deal_size_cr = deal_size_native
            except (ValueError, TypeError):
                pass

    # --- Target name ---
    deal_target: str | None = None
    tm = _TARGET_RE.search(text)
    if tm:
        candidate = tm.group("target").strip()
        # Drop trailing common-stopword tails (e.g. "Limited acquisition of XYZ")
        # Keep alphanumeric tail only; strip punctuation.
        candidate = candidate.rstrip(",.-—–")
        # Reject if target looks like a stopword phrase ("of", "the").
        if len(candidate) >= 3 and not candidate.lower() in {"the", "all", "an"}:
            deal_target = candidate

    # --- Country ---
    deal_target_country: str | None = None
    for country, pattern in _COUNTRY_KEYWORDS.items():
        if pattern.search(text):
            deal_target_country = country
            break

    # --- Status ---
    deal_status: str | None = None
    for status, pattern in _STATUS_KEYWORDS:
        if pattern.search(text):
            deal_status = status
            break

    # If literally nothing parsed, return None — no signal.
    if not any((deal_size_native, deal_target, deal_status)):
        return None
    return MADealDetails(
        deal_size_cr=deal_size_cr,
        deal_size_currency=deal_size_currency,
        deal_size_native=deal_size_native,
        deal_target=deal_target,
        deal_target_country=deal_target_country,
        deal_status=deal_status,
        deal_close_date_estimate=None,  # not parseable from headlines reliably
    )


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
    # M&A keywords — Wave 4-5 P2 (2026-04-25). Matched on combined
    # headline+category+subcategory text. We separate acquisition vs divestiture
    # for downstream agents, but tag both as event_type='m_and_a' for
    # backward-compat with `IMPACT_MAP`. Granular type is preserved by parsing
    # the headline body and storing `ma_details.deal_status`.
    keywords_ma = (
        "acquisition", "acquire", "merger", "amalgamation",
        "scheme of arrangement", "spa ", "share purchase agreement",
        "definitive agreement", "to acquire", "stake in",
    )
    keywords_divestiture = ("divestiture", "divestment", "sale of", "stake sale", "demerger", "disinvestment")

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
        elif any(kw in combined for kw in keywords_divestiture):
            event_type = "divestiture"
        elif any(kw in combined for kw in keywords_ma):
            event_type = "m_and_a"

        if event_type and f.filing_date:
            try:
                d = date.fromisoformat(f.filing_date[:10])
            except (ValueError, TypeError):
                continue
            ma_details = None
            if event_type in ("m_and_a", "divestiture"):
                # Parse structured deal info from headline. Body data isn't
                # stored on `CorporateFiling` — pass headline only.
                try:
                    ma_details = parse_ma_deal_from_filing(f.headline)
                except Exception:  # noqa: BLE001 — defensive; never block catalyst pipeline
                    logger.warning(
                        "M&A parsing failed for %s filing %r", symbol, (f.headline or "")[:80],
                        exc_info=True,
                    )
                    ma_details = None
            events.append(CatalystEvent(
                symbol=symbol,
                event_type=event_type,
                event_date=d,
                days_until=0,  # computed later in gather_catalysts
                description=desc[:120],
                # M&A is high-impact per IMPACT_MAP fallback (defaults to "high")
                impact=IMPACT_MAP.get(event_type, "high" if event_type in ("m_and_a", "divestiture") else "medium"),
                source="bse_filing",
                ma_details=ma_details,
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
