"""Tests for deals_client.py — NSE bulk/block deal parsing and fetch."""

from __future__ import annotations

import respx
from httpx import Response

from flowtracker.deals_client import DealsClient


# -- Fixture data --

_BLOCK_DEAL = {
    "BD_DT_DATE": "26-Mar-2026",
    "BD_SYMBOL": "  SBIN  ",
    "BD_CLIENT_NAME": "Goldman Sachs Fund",
    "BD_BUY_SELL": " buy ",
    "BD_QTY_TRD": "500000",
    "BD_TP_WATP": "820.50",
}

_BULK_DEAL = {
    "BD_DT_DATE": "25/03/2026",
    "BD_SYMBOL": "INFY",
    "BD_CLIENT_NAME": "Morgan Stanley",
    "BD_BUY_SELL": "SELL",
    "BD_QTY_TRD": "1200000",
    "BD_TP_WATP": "1455.75",
}

_SHORT_DEAL = {
    "BD_DT_DATE": "2026-03-26",
    "BD_SYMBOL": "RELIANCE",
    "BD_CLIENT_NAME": "Citadel",
    "BD_BUY_SELL": "SELL",
    "BD_QTY_TRD": "100000",
    "BD_TP_WATP": "2300.00",
}

_API_RESPONSE = {
    "BLOCK_DEALS_DATA": [_BLOCK_DEAL],
    "BULK_DEALS_DATA": [_BULK_DEAL],
    "SHORT_SELLING_DATA": [_SHORT_DEAL],
}


class TestParseDeal:
    """Test DealsClient._parse_deal with fixture dicts."""

    def test_parse_block_deal(self):
        client = DealsClient()
        deal = client._parse_deal(_BLOCK_DEAL, "BLOCK")
        assert deal is not None
        assert deal.symbol == "SBIN"
        assert deal.deal_type == "BLOCK"
        assert deal.date == "2026-03-26"
        assert deal.client_name == "Goldman Sachs Fund"
        assert deal.buy_sell == "BUY"
        assert deal.quantity == 500000
        assert deal.price == 820.50
        client.close()

    def test_parse_bulk_deal(self):
        client = DealsClient()
        deal = client._parse_deal(_BULK_DEAL, "BULK")
        assert deal is not None
        assert deal.symbol == "INFY"
        assert deal.deal_type == "BULK"
        assert deal.date == "2026-03-25"
        assert deal.buy_sell == "SELL"
        assert deal.quantity == 1200000
        assert deal.price == 1455.75
        client.close()

    def test_parse_short_deal(self):
        client = DealsClient()
        deal = client._parse_deal(_SHORT_DEAL, "SHORT")
        assert deal is not None
        assert deal.symbol == "RELIANCE"
        assert deal.deal_type == "SHORT"
        assert deal.date == "2026-03-26"
        client.close()

    def test_parse_deal_missing_symbol_returns_none(self):
        client = DealsClient()
        item = {**_BLOCK_DEAL, "BD_SYMBOL": "  "}
        deal = client._parse_deal(item, "BLOCK")
        assert deal is None
        client.close()

    def test_parse_deal_no_price(self):
        client = DealsClient()
        item = {**_BLOCK_DEAL, "BD_TP_WATP": None}
        deal = client._parse_deal(item, "BLOCK")
        assert deal is not None
        assert deal.price is None
        client.close()

    def test_parse_deal_invalid_quantity_returns_none(self):
        client = DealsClient()
        item = {**_BLOCK_DEAL, "BD_QTY_TRD": "abc"}
        deal = client._parse_deal(item, "BLOCK")
        assert deal is None  # ValueError caught
        client.close()


class TestParseDate:
    """Test DealsClient._parse_date with various formats."""

    def test_dd_mon_yyyy(self):
        assert DealsClient._parse_date("26-Mar-2026") == "2026-03-26"

    def test_dd_mm_yyyy_dash(self):
        assert DealsClient._parse_date("25-03-2026") == "2026-03-25"

    def test_dd_mm_yyyy_slash(self):
        assert DealsClient._parse_date("25/03/2026") == "2026-03-25"

    def test_yyyy_mm_dd(self):
        assert DealsClient._parse_date("2026-03-26") == "2026-03-26"

    def test_unparseable_returns_as_is(self):
        assert DealsClient._parse_date("garbage") == "garbage"

    def test_whitespace_stripped(self):
        assert DealsClient._parse_date("  26-Mar-2026  ") == "2026-03-26"


class TestParseResponse:
    """Test DealsClient._parse_response with combined data."""

    def test_all_deal_types(self):
        client = DealsClient()
        deals = client._parse_response(_API_RESPONSE)
        assert len(deals) == 3
        types = {d.deal_type for d in deals}
        assert types == {"BLOCK", "BULK", "SHORT"}
        client.close()

    def test_empty_response(self):
        client = DealsClient()
        deals = client._parse_response({})
        assert deals == []
        client.close()

    def test_partial_response(self):
        client = DealsClient()
        deals = client._parse_response({"BLOCK_DEALS_DATA": [_BLOCK_DEAL]})
        assert len(deals) == 1
        assert deals[0].deal_type == "BLOCK"
        client.close()


class TestFetchDeals:
    """Test full fetch_deals with respx mocking."""

    def test_fetch_deals_success(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/snapshot").respond(
                200, json=_API_RESPONSE,
            )
            with DealsClient() as client:
                deals = client.fetch_deals()
            assert len(deals) == 3

    def test_fetch_deals_empty_data(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/snapshot").respond(
                200, json={"BLOCK_DEALS_DATA": [], "BULK_DEALS_DATA": []},
            )
            with DealsClient() as client:
                deals = client.fetch_deals()
            assert deals == []
