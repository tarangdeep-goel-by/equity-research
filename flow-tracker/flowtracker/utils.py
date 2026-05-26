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


# Domestic-institution leaf categories stored in the shareholding table. DII is
# *derived* as their sum (incl. the OtherDII reconciliation remainder), never
# stored as a peer category — that would double-count the NSE InstitutionsDomestic
# parent. The full leaf set makes derived DII == that parent. See
# holding_client._XBRL_CATEGORY_MAP / _DOMESTIC_LEAF_CATEGORIES.
DII_COMPONENTS = ("MF", "Insurance", "AIF", "Banks", "OtherFI", "NBFC", "Pension", "VC", "SovereignDomestic", "OtherDII")


def derive_dii(by_category: dict[str, float | None]) -> float | None:
    """Derived DII % = sum of the DII_COMPONENTS leaf categories present in the mapping.

    Returns None if none of the component categories are present (so a stock
    with no domestic-institution data reads as missing, not 0.0).
    """
    vals = [v for c in DII_COMPONENTS if (v := by_category.get(c)) is not None]
    return round(sum(vals), 2) if vals else None


def parse_nse_date(date_str: str) -> date:
    """Parse NSE date format: '17-Mar-2026' → date object."""
    return datetime.strptime(date_str.strip(), "%d-%b-%Y").date()


def format_display_date(d: date) -> str:
    """Format date for display: '17 Mar' (same year) or '17 Mar 2026' (different year)."""
    today = date.today()
    if d.year == today.year:
        return d.strftime("%-d %b")
    return d.strftime("%-d %b %Y")
