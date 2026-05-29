"""Phase-2 market-parameterized row validation (`_validate_row`).

Locks NSE/INR behavior (regression) and exercises the non-INR (USD) path,
where crore-magnitude bounds are skipped but currency-agnostic ratio/percentage
bounds still apply.
"""
from __future__ import annotations

from flowtracker.market import Market
from flowtracker.store_domains._shared import _validate_row


# --- NSE/INR regression lock -------------------------------------------------

def test_nse_inr_flags_out_of_range_magnitude():
    # market_cap below the ₹50 Cr lower bound → flagged.
    warnings = _validate_row("valuation_snapshot", {"market_cap": 10})
    assert any("market_cap" in w for w in warnings)


def test_nse_inr_valid_row_no_warnings():
    # A plausible NSE row: ₹1L Cr cap, ₹1500 price, 18% margins, sane PE.
    row = {
        "market_cap": 100_000,
        "price": 1500,
        "pe_trailing": 28,
        "operating_margin": 18.0,
        "net_margin": 12.0,
        "roe": 15.0,
    }
    assert _validate_row("valuation_snapshot", row) == []


def test_default_args_match_explicit_nse_inr():
    # Defaulting (no market/currency) must equal explicit NSE/INR — behavior
    # for legacy callers is preserved byte-for-byte.
    row = {"market_cap": 10, "net_margin": 250}
    assert _validate_row("valuation_snapshot", row) == _validate_row(
        "valuation_snapshot", row, market="NSE", currency="INR"
    )


def test_market_enum_accepted():
    # Passing a Market enum behaves the same as the equivalent string.
    row = {"market_cap": 10}
    assert _validate_row(
        "valuation_snapshot", row, market=Market.NSE, currency="INR"
    ) == _validate_row("valuation_snapshot", row, market="NSE", currency="INR")


def test_bse_inr_applies_crore_bounds():
    # BSE is also INR → crore magnitude bounds still apply.
    warnings = _validate_row(
        "valuation_snapshot", {"market_cap": 10}, market="BSE", currency="INR"
    )
    assert any("market_cap" in w for w in warnings)


# --- non-INR (USD) path ------------------------------------------------------

def test_usd_skips_crore_magnitude_bound():
    # $3.5T market cap (3.5e12) would violate the INR-crore upper bound, but for
    # USD the crore magnitude bounds don't apply → NOT flagged.
    warnings = _validate_row(
        "valuation_snapshot", {"market_cap": 3_500_000_000_000},
        market="NASDAQ", currency="USD",
    )
    assert warnings == []


def test_usd_still_flags_percentage_bound():
    # Currency-agnostic percentage bound still applies: net_margin=250 is
    # nonsense in any currency → flagged even on the USD path.
    warnings = _validate_row(
        "valuation_snapshot",
        {"market_cap": 3_500_000_000_000, "net_margin": 250},
        market="NASDAQ", currency="USD",
    )
    assert any("net_margin" in w for w in warnings)
    # ...and the out-of-crore-range market_cap is NOT among the warnings.
    assert not any("market_cap" in w for w in warnings)


def test_usd_pe_trailing_is_agnostic():
    # pe_trailing is currency-agnostic; an absurd PE is flagged on USD too.
    warnings = _validate_row(
        "valuation_snapshot", {"pe_trailing": 99_999},
        market="NASDAQ", currency="USD",
    )
    assert any("pe_trailing" in w for w in warnings)
