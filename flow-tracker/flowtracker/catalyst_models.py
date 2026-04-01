"""Pydantic models and static calendar for catalyst events."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class CatalystEvent(BaseModel, extra="ignore"):
    """A catalyst event that may impact a stock or the broader market."""

    symbol: str | None = None  # None for market-wide events (RBI, budget)
    event_type: str  # earnings, board_meeting, ex_dividend, rbi_policy, budget, results_estimated, sebi_meeting, mf_disclosure
    event_date: date
    days_until: int  # computed from today
    description: str  # "Q3 FY26 earnings release"
    impact: str  # high, medium, low
    source: str  # yfinance, bse_filing, static, estimated
    confirmed: bool = True  # False for estimated dates


IMPACT_MAP: dict[str, str] = {
    "earnings": "high",
    "board_meeting": "high",
    "results_estimated": "high",
    "ex_dividend": "medium",
    "rbi_policy": "medium",  # "high" for banks — caller overrides
    "budget": "high",
    "sebi_meeting": "low",
    "mf_disclosure": "low",
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
