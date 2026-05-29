"""Shared store infrastructure used by FlowStore and all domain mixins
(refactor P1.4).

Lives in its own module so domain mixins can import these helpers without a
circular dependency on ``store.py`` (which imports the mixins for its bases).
Holds the validation cluster, the derived-DII shareholding CTE, and the
percentile helper. The sqlite connection, schema DDL, and DB-path constants
stay in ``store.py`` (owned by FlowStore's lifecycle).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowtracker.market import Market

_val_logger = logging.getLogger("flowtracker.validation")

# Shareholding rows with a derived DII category (MF + Insurance + AIF) synthesized
# on the fly. DII is never stored — this CTE body lets ownership-trend queries
# reference a 'DII' category without double-counting. Any legacy stored DII rows
# are filtered out so pre/post-migration results match.
_SHAREHOLDING_WITH_DII = """
    SELECT symbol, quarter_end, category, percentage
    FROM shareholding WHERE category != 'DII'
    UNION ALL
    SELECT symbol, quarter_end, 'DII' AS category, ROUND(SUM(percentage), 2) AS percentage
    FROM shareholding WHERE category IN ('MF', 'Insurance', 'AIF', 'Banks', 'OtherFI', 'NBFC', 'Pension', 'VC', 'SovereignDomestic', 'OtherDII')
    GROUP BY symbol, quarter_end
"""

# Ranges designed to catch unit errors (rupees stored as crores).
# A ₹500 Cr company in rupees = 5,000,000,000 — must exceed upper bound.
# Lower bounds catch reverse errors or nonsense values.
_VALIDATION_RULES: dict[str, dict[str, tuple[float, float]]] = {
    "annual_financials": {
        "revenue": (1, 1_500_000),          # ₹1 Cr to ₹15L Cr (Reliance ~9L Cr)
        "net_income": (-50_000, 500_000),   # losses capped, profits ~5L Cr max
        "total_assets": (1, 50_000_000),    # SBI ~60L Cr, but most < 50L
        "num_shares": (100_000, 50_000_000_000),  # at least 1L shares
        "eps": (-500, 5_000),               # per-share rupees
    },
    "valuation_snapshot": {
        "market_cap": (50, 25_000_000),     # ₹50 Cr to ₹25L Cr
        "enterprise_value": (-500_000, 30_000_000),
        "total_cash": (0.01, 10_000_000),   # at least 1L, max 10L Cr
        "total_debt": (0.01, 30_000_000),
        "free_cash_flow": (-200_000, 200_000),
        "operating_cash_flow": (-200_000, 300_000),
        "price": (1, 200_000),              # ₹1 to ₹2L per share
        "pe_trailing": (-500, 2000),
        # P-3B.2: Percentage fields (stored as 25.0 = 25%)
        "operating_margin": (-100, 100),
        "net_margin": (-100, 100),
        "gross_margin": (-50, 100),
        "roe": (-200, 200),
        "roa": (-100, 100),
        "revenue_growth": (-100, 500),
        "earnings_growth": (-500, 1000),
        "dividend_yield": (0, 50),
    },
    "quarterly_results": {
        "revenue": (0.1, 400_000),          # quarterly — max ~4L Cr
        "net_income": (-30_000, 200_000),
        # P-3B.2: Percentage fields
        "operating_margin": (-100, 100),
        "net_margin": (-100, 100),
    },
    "insider_transactions": {
        "value": (0, 10_000),               # max ~₹10K Cr single trade
    },
    "mf_scheme_holdings": {
        "market_value_cr": (0.01, 50_000),  # ₹1L to ₹50K Cr per scheme holding
        "pct_of_nav": (0.001, 25),          # max 25% NAV in one stock
    },
    "fmp_key_metrics": {
        "market_cap": (50, 25_000_000),
        "enterprise_value": (-500_000, 30_000_000),
    },
    "quarterly_balance_sheet": {
        "total_assets": (1, 50_000_000),
        "total_debt": (0.01, 30_000_000),
    },
    "quarterly_cash_flow": {
        "operating_cf": (-200_000, 300_000),
        "free_cf": (-200_000, 200_000),
    },
}


# US add-on (Phase 3) — USD-millions magnitude bounds for the us_* monetary
# tables. Values are stored in USD millions (market magnitude_divisor = 1e6),
# so a $3.5T market cap (Apple) = 3,500,000 mn must fit under the upper bound.
# Per-share / price values are raw USD. Percentage/ratio fields reuse the
# currency-agnostic handling (see ``_CURRENCY_AGNOSTIC_FIELDS``); they're listed
# here so the same [lo, hi] sanity bounds apply. These rules are selected by
# ``_validate_row`` ONLY when currency == 'USD'; INR/NSE behavior is untouched.
_USD_VALIDATION_RULES: dict[str, dict[str, tuple[float, float]]] = {
    "us_annual_financials": {
        "revenue": (0, 1_000_000),          # up to ~$1T (Walmart ~$650B)
        "net_income": (-200_000, 300_000),  # losses capped; profits ~$100B+ (Apple)
        "total_assets": (0, 10_000_000),    # banks (JPM ~$4T)
        "total_equity": (-200_000, 1_000_000),
        "total_debt": (0, 1_000_000),
        "total_cash": (0, 1_000_000),
        "operating_cash_flow": (-200_000, 300_000),
        "free_cash_flow": (-200_000, 300_000),
        "eps": (-1_000, 5_000),             # per-share USD
        "shares_outstanding": (1_000, 100_000_000_000),
        # Phase 3.5b wide fields — USD millions magnitude (same convention as
        # revenue/net_income); num_shares is a raw diluted count.
        "equity_capital": (-200_000, 1_000_000),
        "reserves": (-500_000, 1_000_000),  # accumulated deficit can be deeply negative
        "borrowings": (0, 1_000_000),
        "interest": (-100_000, 200_000),
        "profit_before_tax": (-200_000, 400_000),
        "tax": (-200_000, 200_000),
        "operating_profit": (-200_000, 400_000),
        "depreciation": (-50_000, 200_000),
        "num_shares": (1_000, 100_000_000_000),
        "net_block": (0, 1_000_000),
        "cwip": (0, 1_000_000),
        "cash_and_bank": (0, 1_000_000),
        "receivables": (0, 1_000_000),
        "inventory": (0, 1_000_000),
        "other_liabilities": (-200_000, 1_000_000),
        "cfi": (-500_000, 500_000),
        "cff": (-500_000, 500_000),
        "rnd_expense": (0, 200_000),
        "stock_based_comp": (0, 200_000),
        "sga": (0, 300_000),
    },
    "us_quarterly_financials": {
        "revenue": (0, 300_000),            # quarterly
        "net_income": (-100_000, 100_000),
        "eps": (-1_000, 5_000),
    },
    "us_valuation_snapshot": {
        "price": (0.01, 1_000_000),         # raw USD per share (BRK.A high)
        "market_cap": (0, 5_000_000),       # up to ~$5T
        "enterprise_value": (-1_000_000, 6_000_000),
        "total_cash": (0, 1_000_000),
        "total_debt": (0, 1_000_000),
        "free_cash_flow": (-200_000, 300_000),
        "pe_trailing": (-500, 2000),
        "pe_forward": (-500, 2000),
        "pb": (-100, 1000),
        # Percentage fields (25.0 = 25%) — currency-agnostic bounds.
        "operating_margin": (-100, 100),
        "net_margin": (-100, 100),
        "roe": (-200, 200),
        "dividend_yield": (0, 50),
    },
}


# Phase-2 (multi-market) parameterization split.
#
# The bounds in ``_VALIDATION_RULES`` above mix two conceptually different
# kinds of check:
#   1. Monetary / absolute-magnitude bounds (revenue, market_cap, price, ...)
#      — these encode INR-crore magnitudes and only make sense for markets
#      that store values in crores (NSE/BSE → INR). A USD market_cap of
#      ``3.5e12`` ($3.5T, e.g. Apple) is perfectly valid yet would blow past
#      the ₹25L-Cr crore bound, so the crore bounds MUST NOT apply to non-INR
#      currencies.
#   2. Ratio / percentage bounds (margins, returns, growth, yields, PE) —
#      these are currency-independent. A net margin of 250% is nonsense in any
#      currency, so these bounds apply to every market.
#
# ``_CURRENCY_AGNOSTIC_FIELDS`` enumerates the percentage/ratio fields. For
# INR markets we apply the full ``_VALIDATION_RULES`` (monetary + agnostic) —
# byte-identical to pre-phase-2 behavior. For any non-INR currency we apply
# ONLY the agnostic subset (Phase 3 will add per-market monetary rulesets).
_CURRENCY_AGNOSTIC_FIELDS: frozenset[str] = frozenset({
    "operating_margin",
    "net_margin",
    "gross_margin",
    "roe",
    "roa",
    "revenue_growth",
    "earnings_growth",
    "dividend_yield",
    "pct_of_nav",
    "pe_trailing",
    "pe_forward",
    "pb",
})


def _resolve_currency(market: "Market | str", currency: str) -> str:
    """Normalize ``currency`` for an explicit market/currency pair.

    Accepts ``market`` as a ``Market`` enum or a plain string. The currency
    argument is authoritative (callers pass the row's currency); ``market`` is
    accepted for symmetry / forward-compat and to let future per-market rules
    key off it. Returned value is upper-cased for comparison.
    """
    # Normalize market to a string in case a future caller keys off it.
    _ = getattr(market, "value", market)  # tolerate Market enum or str
    return (currency or "INR").upper()


def _validate_row(
    table: str,
    row: dict,
    market: "Market | str" = "NSE",
    currency: str = "INR",
) -> list[str]:
    """Return list of validation warnings for ``row`` in ``table``. Empty = valid.

    Phase-2 (multi-market) parameterization
    ---------------------------------------
    Validation is now keyed by market/currency. ``_VALIDATION_RULES`` holds the
    INR-crore ruleset (used by NSE/BSE). It contains two kinds of bound:
    currency-specific *monetary* bounds (crore magnitudes) and currency-agnostic
    *ratio/percentage* bounds (margins, returns, growth, yields, PE — see
    ``_CURRENCY_AGNOSTIC_FIELDS``).

    * For INR currencies (NSE/BSE): apply the FULL ruleset — identical to the
      pre-phase-2 behavior, so the same inputs produce the same warnings.
    * For non-INR currencies (e.g. USD on NASDAQ/NYSE): the crore-magnitude
      bounds don't apply, so skip the monetary bounds and apply ONLY the
      currency-agnostic ratio/percentage bounds. (Phase 3 adds a per-market
      monetary ruleset.)

    ``market`` may be a ``Market`` enum or a string; ``currency`` is the row's
    currency and is authoritative for which bounds apply. Both default to
    NSE/INR to preserve existing behavior for callers not yet market-aware.
    """
    errors = []
    resolved = _resolve_currency(market, currency)
    is_inr = resolved == "INR"
    if resolved == "USD" and table in _USD_VALIDATION_RULES:
        # US add-on (Phase 3): apply the USD-millions ruleset for the us_* tables.
        # It carries both monetary (USD-magnitude) and percentage/ratio bounds,
        # so every field in it is checked — the INR crore bounds never apply.
        # Legacy (India) tables queried with currency='USD' fall through to the
        # Phase-2 agnostic-only path below (byte-identical behavior).
        rules = _USD_VALIDATION_RULES[table]
        for field, (lo, hi) in rules.items():
            val = row.get(field)
            if val is not None and (val < lo or val > hi):
                errors.append(f"{field}={val} outside [{lo}, {hi}]")
        return errors
    rules = _VALIDATION_RULES.get(table, {})
    for field, (lo, hi) in rules.items():
        # Non-INR currencies skip monetary/magnitude bounds (crore-specific);
        # only the currency-agnostic ratio/percentage bounds are checked.
        if not is_inr and field not in _CURRENCY_AGNOSTIC_FIELDS:
            continue
        val = row.get(field)
        if val is not None and (val < lo or val > hi):
            errors.append(f"{field}={val} outside [{lo}, {hi}]")
    return errors


def _percentile_rank(value: float | None, series: list[float]) -> float | None:
    """Percentile rank of ``value`` within ``series`` (0-100, inclusive).

    Uses the "<= value" definition: percentile = 100 * (# observations
    <= value) / N. Returns None when either input is empty/None.
    """
    if value is None or not series:
        return None
    n = len(series)
    leq = sum(1 for x in series if x <= value)
    return round(100.0 * leq / n, 2)
