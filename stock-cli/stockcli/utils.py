"""Number formatting and symbol normalization utilities."""

from __future__ import annotations


def fmt_number(value: float | int | None, decimals: int = 2) -> str:
    """Format a number with commas and fixed decimal places."""
    if value is None:
        return "N/A"
    if isinstance(value, int) or value == int(value):
        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:,.{decimals}f}B"
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:,.{decimals}f}M"
        if abs(value) >= 1_000:
            return f"{value / 1_000:,.{decimals}f}K"
    return f"{value:,.{decimals}f}"


CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$",
    "INR": "\u20b9",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
    "CNY": "\u00a5",
}


def _cur(currency: str | None) -> str:
    """Get currency symbol from ISO code."""
    return CURRENCY_SYMBOLS.get(currency or "USD", currency or "$")


def fmt_large(value: float | int | None, currency: str | None = None) -> str:
    """Format large numbers with B/M/K suffix."""
    if value is None:
        return "N/A"
    c = _cur(currency)
    if abs(value) >= 1_000_000_000:
        return f"{c}{value / 1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"{c}{value / 1_000_000:,.2f}M"
    if abs(value) >= 1_000:
        return f"{c}{value / 1_000:,.2f}K"
    return f"{c}{value:,.2f}"


def fmt_pct(value: float | None) -> str:
    """Format a ratio/percentage value."""
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def fmt_ratio(value: float | None) -> str:
    """Format a ratio (PE, PB, etc.)."""
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def fmt_price(value: float | None, currency: str | None = None) -> str:
    """Format a price with currency symbol and 2 decimals."""
    if value is None:
        return "N/A"
    return f"{_cur(currency)}{value:,.2f}"


def normalize_symbol(symbol: str) -> str:
    """Normalize stock symbol — uppercase, strip whitespace."""
    return symbol.strip().upper()
