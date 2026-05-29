"""Market dimension — the spine of multi-market support.

Today the codebase is implicitly India-only: a symbol *is* ``.NS``, money *is*
₹ crores, a fiscal year *is* Apr–Mar. This module makes ``market`` an explicit
value so India becomes "just one market." It is intentionally **additive and
backward-compatible**: everything defaults to ``Market.NSE`` / INR, so existing
call sites behave identically until they opt into a different market.

Phase 1 (this module): market identity + symbol formatting. Currency formatting
and calendar/fiscal logic build on the config defined here in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Market(str, Enum):
    """A listing venue. ``str`` mixin so values serialize as plain strings
    (e.g. stored in a ``market`` column as ``"NSE"``)."""

    NSE = "NSE"      # National Stock Exchange of India
    BSE = "BSE"      # Bombay Stock Exchange
    NASDAQ = "NASDAQ"
    NYSE = "NYSE"


@dataclass(frozen=True)
class MarketConfig:
    """Descriptive properties of a market — the single source of truth for
    currency, units, ticker formatting, and fiscal convention.

    ``magnitude_divisor`` is what a raw native-currency amount is divided by to
    reach the canonical stored aggregate unit (₹1 Cr = 1e7 rupees; USD is stored
    in millions = 1e6). ``fiscal_year_end_month`` is 3 for India (Apr–Mar) and
    12 for calendar-year markets.
    """

    code: Market
    country: str
    currency: str            # ISO 4217, e.g. "INR", "USD"
    currency_symbol: str     # "₹", "$"
    magnitude_label: str     # "Cr", "mn"
    magnitude_divisor: float  # raw-currency → stored-aggregate-unit
    yfinance_suffix: str     # ".NS", ".BO", "" (US needs none)
    fiscal_year_end_month: int  # 3 = Apr–Mar (India), 12 = calendar


MARKETS: dict[Market, MarketConfig] = {
    Market.NSE: MarketConfig(
        code=Market.NSE, country="IN", currency="INR", currency_symbol="₹",
        magnitude_label="Cr", magnitude_divisor=1e7, yfinance_suffix=".NS",
        fiscal_year_end_month=3,
    ),
    Market.BSE: MarketConfig(
        code=Market.BSE, country="IN", currency="INR", currency_symbol="₹",
        magnitude_label="Cr", magnitude_divisor=1e7, yfinance_suffix=".BO",
        fiscal_year_end_month=3,
    ),
    Market.NASDAQ: MarketConfig(
        code=Market.NASDAQ, country="US", currency="USD", currency_symbol="$",
        magnitude_label="mn", magnitude_divisor=1e6, yfinance_suffix="",
        fiscal_year_end_month=12,
    ),
    Market.NYSE: MarketConfig(
        code=Market.NYSE, country="US", currency="USD", currency_symbol="$",
        magnitude_label="mn", magnitude_divisor=1e6, yfinance_suffix="",
        fiscal_year_end_month=12,
    ),
}

DEFAULT_MARKET = Market.NSE

# yfinance suffixes we recognize as "already a market ticker" so we never
# double-suffix. (US tickers carry no suffix, hence not listed.)
_KNOWN_SUFFIXES = (".NS", ".BO")


def market_config(market: Market = DEFAULT_MARKET) -> MarketConfig:
    """Config for a market (defaults to NSE)."""
    return MARKETS[market]


def market_symbol(symbol: str, market: Market = DEFAULT_MARKET) -> str:
    """Format a bare symbol into its yfinance/FMP ticker for ``market``.

    NSE: ``RELIANCE`` → ``RELIANCE.NS``. US: ``MSFT`` → ``MSFT`` (no suffix).
    An already-suffixed Indian ticker (``.NS``/``.BO``) is returned unchanged so
    re-formatting is idempotent. This generalizes the legacy ``nse_symbol()``;
    with ``market=NSE`` it is behavior-identical to it.
    """
    if symbol.endswith(_KNOWN_SUFFIXES):
        return symbol
    return f"{symbol}{MARKETS[market].yfinance_suffix}"


def to_aggregate(raw: float | None, market: Market = DEFAULT_MARKET) -> float | None:
    """Convert a raw native-currency amount to the market's canonical stored
    aggregate unit. NSE: rupees → crores (÷1e7). US: dollars → millions (÷1e6).

    Generalizes the legacy ``_to_cr`` helpers; with ``market=NSE`` it is
    behavior-identical (÷1e7). ``None`` passes through.
    """
    if raw is None:
        return None
    return raw / MARKETS[market].magnitude_divisor


def fmt_monetary(value: float | None, market: Market = DEFAULT_MARKET) -> str:
    """Format an aggregate value with the market's currency symbol + magnitude
    label. NSE: ``₹1,234.56 Cr``. US: ``$1,234.56 mn``. ``None`` → ``"N/A"``.

    Generalizes ``utils.fmt_crores_label`` (NSE output is identical).
    """
    if value is None:
        return "N/A"
    cfg = MARKETS[market]
    return f"{cfg.currency_symbol}{value:,.2f} {cfg.magnitude_label}"


def infer_market(ticker: str) -> Market:
    """Reverse-detect the market from a ticker suffix. Bare tickers (no known
    suffix) default to NSE — preserving today's India-only assumption until
    call sites pass an explicit market."""
    if ticker.endswith(".NS"):
        return Market.NSE
    if ticker.endswith(".BO"):
        return Market.BSE
    return DEFAULT_MARKET


from flowtracker.market.calendar import MarketCalendar  # noqa: E402

__all__ = [
    "Market",
    "MarketConfig",
    "MARKETS",
    "DEFAULT_MARKET",
    "market_config",
    "market_symbol",
    "infer_market",
    "to_aggregate",
    "fmt_monetary",
    "MarketCalendar",
]
