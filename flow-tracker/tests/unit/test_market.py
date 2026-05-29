"""Tests for the market dimension module (flowtracker.market)."""

from __future__ import annotations

import pytest

from flowtracker.fund_client import nse_symbol
from flowtracker.market import (
    DEFAULT_MARKET,
    MARKETS,
    Market,
    infer_market,
    market_config,
    market_symbol,
)


class TestMarketSymbol:
    def test_nse_appends_suffix(self):
        assert market_symbol("RELIANCE", Market.NSE) == "RELIANCE.NS"

    def test_bse_appends_suffix(self):
        assert market_symbol("RELIANCE", Market.BSE) == "RELIANCE.BO"

    def test_us_has_no_suffix(self):
        assert market_symbol("MSFT", Market.NASDAQ) == "MSFT"
        assert market_symbol("BRK.B", Market.NYSE) == "BRK.B"

    def test_default_market_is_nse(self):
        assert market_symbol("TECHM") == "TECHM.NS"

    @pytest.mark.parametrize("ticker", ["RELIANCE.NS", "RELIANCE.BO"])
    def test_already_suffixed_is_idempotent(self, ticker):
        assert market_symbol(ticker, Market.NSE) == ticker
        # idempotent even across markets
        assert market_symbol(ticker, Market.NASDAQ) == ticker


class TestNseSymbolBackcompat:
    """nse_symbol must remain behavior-identical to its pre-refactor form."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("TECHM", "TECHM.NS"),
            ("RELIANCE.NS", "RELIANCE.NS"),
            ("RELIANCE.BO", "RELIANCE.BO"),
            ("techm", "techm.NS"),  # original did not change case
        ],
    )
    def test_matches_legacy_behavior(self, raw, expected):
        assert nse_symbol(raw) == expected


class TestInferMarket:
    def test_ns_suffix(self):
        assert infer_market("RELIANCE.NS") == Market.NSE

    def test_bo_suffix(self):
        assert infer_market("RELIANCE.BO") == Market.BSE

    def test_bare_defaults_to_nse(self):
        assert infer_market("MSFT") == DEFAULT_MARKET == Market.NSE


class TestMarketConfig:
    def test_nse_is_inr_crores(self):
        cfg = market_config(Market.NSE)
        assert cfg.currency == "INR"
        assert cfg.currency_symbol == "₹"
        assert cfg.magnitude_label == "Cr"
        assert cfg.magnitude_divisor == 1e7
        assert cfg.fiscal_year_end_month == 3

    def test_us_is_usd_millions_calendar(self):
        cfg = market_config(Market.NASDAQ)
        assert cfg.currency == "USD"
        assert cfg.currency_symbol == "$"
        assert cfg.magnitude_divisor == 1e6
        assert cfg.fiscal_year_end_month == 12
        assert cfg.yfinance_suffix == ""

    def test_every_market_has_config(self):
        for m in Market:
            assert m in MARKETS
            assert MARKETS[m].code == m

    def test_market_serializes_as_plain_string(self):
        # str-mixin enum → stored cleanly in a `market` column
        assert Market.NSE == "NSE"
        assert f"{Market.NASDAQ}" == "Market.NASDAQ"  # repr form
        assert Market.NASDAQ.value == "NASDAQ"
