"""Pydantic models and static calendar for catalyst events."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class MADealDetails(BaseModel, extra="ignore"):
    """Structured M&A / acquisition / divestiture deal payload.

    Wave 4-5 P2 addition 2026-04-25 — pharma autoeval flagged
    `get_events_actions(catalysts)` returning headlines only with no structured
    deal info (size, target, status). Populated by `parse_ma_deal_from_filing`
    in catalyst_client.py via headline + filing-body regex.

    Fields are best-effort: all default None when not parseable.
    """

    deal_size_cr: float | None = None  # converted to crores when currency is INR
    deal_size_currency: str | None = None  # USD, INR, EUR — original disclosure currency
    deal_size_native: float | None = None  # raw numeric in disclosure currency
    deal_target: str | None = None  # name of acquired/divested entity
    deal_target_country: str | None = None  # country code or name (e.g. "US", "India")
    # Status taxonomy — keep small + extensible. Caller normalizes free-text status.
    deal_status: str | None = None  # announced | pending_regulatory | closed | terminated
    deal_close_date_estimate: str | None = None  # ISO date or natural-language ("Q3 FY27")


class CatalystEvent(BaseModel, extra="ignore"):
    """A catalyst event that may impact a stock or the broader market."""

    symbol: str | None = None  # None for market-wide events (RBI, budget)
    event_type: str  # earnings, board_meeting, ex_dividend, rbi_policy, budget, results_estimated, sebi_meeting, mf_disclosure, m_and_a, divestiture
    event_date: date
    days_until: int  # computed from today
    description: str  # "Q3 FY26 earnings release"
    impact: str  # high, medium, low
    source: str  # yfinance, bse_filing, static, estimated
    confirmed: bool = True  # False for estimated dates
    # Wave 4-5 P2 addition 2026-04-25 — populated only when event_type ∈
    # {m_and_a, acquisition, divestiture}; None for everything else.
    ma_details: MADealDetails | None = None


IMPACT_MAP: dict[str, str] = {
    "earnings": "high",
    "board_meeting": "high",
    "results_estimated": "high",
    "ex_dividend": "medium",
    "rbi_policy": "medium",  # "high" for banks — caller overrides
    "budget": "high",
    "sebi_meeting": "low",
    "mf_disclosure": "low",
    # Wave 4-5 P2 (2026-04-25) — M&A and divestitures both rate as high since
    # they materially reprice the stock on announcement and again on closure.
    "m_and_a": "high",
    "acquisition": "high",  # legacy alias used by some upstream filings
    "divestiture": "high",
}

STATIC_CALENDAR: list[dict] = [
    # FY27 RBI MPC dates
    {"event_type": "rbi_policy", "event_date": "2026-04-08", "description": "RBI MPC April 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-06-04", "description": "RBI MPC June 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-08-05", "description": "RBI MPC August 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-10-01", "description": "RBI MPC October 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-12-03", "description": "RBI MPC December 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2027-02-04", "description": "RBI MPC February 2027", "impact": "medium"},
    # Budget
    {"event_type": "budget", "event_date": "2027-02-01", "description": "Union Budget FY28", "impact": "high"},
]
