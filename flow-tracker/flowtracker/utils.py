"""Formatting and parsing utilities."""

from __future__ import annotations

import json
import re
from datetime import date, datetime


def _clean(obj):
    """Force all values to JSON-serializable Python types (handles numpy, Decimal, etc.)."""
    return json.loads(json.dumps(obj, default=str))


def fmt_crores(value: float | None) -> str:
    """Format value in crores with sign: '+1,234.56' or '-567.89'."""
    if value is None:
        return "N/A"
    return f"{value:+,.2f}"


def fmt_crores_label(value: float | None) -> str:
    """Format value with rupee sign and Cr suffix: '₹1,234.56 Cr'."""
    if value is None:
        return "N/A"
    return f"₹{value:,.2f} Cr"


def parse_period(period: str) -> int:
    """Parse period string like '7d' or '30d' to number of days."""
    match = re.match(r"^(\d+)d$", period.strip().lower())
    if not match:
        raise ValueError(f"Invalid period '{period}' — use format like '7d' or '30d'")
    return int(match.group(1))


def normalize_category(raw: str) -> str:
    """Normalize NSE category name: 'FII/FPI *' → 'FII', 'DII *' → 'DII'."""
    upper = raw.strip().upper()
    if upper.startswith("FII") or upper.startswith("FPI"):
        return "FII"
    if upper.startswith("DII"):
        return "DII"
    return raw.strip()


def parse_nse_date(date_str: str) -> date:
    """Parse NSE date format: '17-Mar-2026' → date object."""
    return datetime.strptime(date_str.strip(), "%d-%b-%Y").date()


def format_display_date(d: date) -> str:
    """Format date for display: '17 Mar' (same year) or '17 Mar 2026' (different year)."""
    today = date.today()
    if d.year == today.year:
        return d.strftime("%-d %b")
    return d.strftime("%-d %b %Y")
