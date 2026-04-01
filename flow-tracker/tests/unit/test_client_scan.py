"""Tests for scan_client.py — NSE index constituents fetch."""

from __future__ import annotations

import respx

from flowtracker.scan_client import NSEIndexClient, NSEIndexError
import pytest


# -- Fixture data mimicking NSE API response --

_INDEX_RESPONSE = {
    "data": [
        {
            "symbol": "RELIANCE",
            "priority": 0,
            "meta": {
                "companyName": "Reliance Industries Ltd",
                "industry": "Oil Gas & Consumable Fuels",
            },
        },
        {
            "symbol": "TCS",
            "priority": 0,
            "meta": {
                "companyName": "Tata Consultancy Services Ltd",
                "industry": "IT - Software",
            },
        },
        {
            "symbol": "NIFTY 50",
            "priority": 1,  # index row itself — should be skipped
            "meta": {
                "companyName": "Nifty 50",
                "industry": None,
            },
        },
    ],
}

_EMPTY_RESPONSE = {"data": []}


class TestFetchConstituents:
    """Test fetch_constituents with respx mocked NSE API."""

    def test_parses_constituents_skipping_priority_nonzero(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/equity-stockIndices").respond(
                200, json=_INDEX_RESPONSE,
            )
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY 50")

        assert len(constituents) == 2
        symbols = {c.symbol for c in constituents}
        assert symbols == {"RELIANCE", "TCS"}

    def test_constituents_have_correct_fields(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/equity-stockIndices").respond(
                200, json=_INDEX_RESPONSE,
            )
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY 50")

        rel = next(c for c in constituents if c.symbol == "RELIANCE")
        assert rel.index_name == "NIFTY 50"
        assert rel.company_name == "Reliance Industries Ltd"
        assert rel.industry == "Oil Gas & Consumable Fuels"

    def test_empty_response_raises_error(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/equity-stockIndices").respond(
                200, json=_EMPTY_RESPONSE,
            )
            with NSEIndexClient() as client:
                with pytest.raises(NSEIndexError, match="No constituents"):
                    client.fetch_constituents("NIFTY 50")

    def test_index_name_is_preserved(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/equity-stockIndices").respond(
                200, json=_INDEX_RESPONSE,
            )
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY NEXT 50")

        assert all(c.index_name == "NIFTY NEXT 50" for c in constituents)
