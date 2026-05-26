"""Tests for ipo_client.py — NSE + BSE IPO calendar/subscription/listings.

Covers the row parsers, the polymorphic ``_coerce_list`` envelope, and the
full ``fetch_*`` methods via respx mocking.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import respx
from httpx import Response

from flowtracker.ipo_client import (
    BSEIPOClient,
    NSEIPOClient,
    _classify_segment,
    _coerce_list,
    _parse_date,
    _parse_price_band,
)
from flowtracker.js_fetch import JSFetchError

_GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


# ---------------------------------------------------------------------------
# Helper parsing


class TestParseDate:
    def test_dd_mon_yyyy(self):
        assert _parse_date("10-Jun-2026") == "2026-06-10"

    def test_dd_mm_yyyy_slash(self):
        assert _parse_date("10/06/2026") == "2026-06-10"

    def test_iso(self):
        assert _parse_date("2026-06-10") == "2026-06-10"

    def test_iso_with_t(self):
        assert _parse_date("2026-06-10T00:00:00") == "2026-06-10"

    def test_none_and_blank(self):
        assert _parse_date(None) is None
        assert _parse_date("") is None
        assert _parse_date("-") is None

    def test_garbage_returns_none(self):
        assert _parse_date("garbage-string-no-date") is None


class TestParsePriceBand:
    def test_dash_band(self):
        assert _parse_price_band("100-110") == (100.0, 110.0)

    def test_with_rupee_and_to(self):
        assert _parse_price_band("₹950 to ₹1000") == (950.0, 1000.0)

    def test_single_price(self):
        assert _parse_price_band("85") == (85.0, 85.0)

    def test_blank(self):
        assert _parse_price_band("") == (None, None)
        assert _parse_price_band(None) == (None, None)


class TestClassifySegment:
    def test_eq_is_main(self):
        assert _classify_segment("EQ") == "MAIN"

    def test_sme_token(self):
        assert _classify_segment("SME") == "SME"
        assert _classify_segment("sme") == "SME"

    def test_unknown_defaults_main(self):
        assert _classify_segment(None) == "MAIN"
        assert _classify_segment("X") == "MAIN"


class TestCoerceList:
    def test_already_list(self):
        assert _coerce_list([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]

    def test_dict_with_data(self):
        assert _coerce_list({"data": [{"x": 1}]}) == [{"x": 1}]

    def test_dict_as_single_row(self):
        # NSE sometimes returns a single dict for a single row.
        assert _coerce_list({"companyName": "Foo", "symbol": "BAR"}) == [
            {"companyName": "Foo", "symbol": "BAR"}
        ]

    def test_empty(self):
        assert _coerce_list({}) == []
        assert _coerce_list([]) == []


# ---------------------------------------------------------------------------
# Row parsing


class TestParseUpcomingRow:
    def test_main_row(self):
        client = NSEIPOClient()
        row = {
            "companyName": "Jio Platforms Limited",
            "symbol": None,
            "series": "EQ",
            "issueStartDate": "10-Jun-2026",
            "issueEndDate": "12-Jun-2026",
            "listingDate": "18-Jun-2026",
            "issuePrice": "950-1000",
            "issueSize": 55000.00,
            "lotSize": 15,
        }
        issue = client._parse_upcoming_row(row, "MAIN")
        client.close()
        assert issue is not None
        assert issue.issuer_name == "Jio Platforms Limited"
        assert issue.symbol is None
        assert issue.segment == "MAIN"
        assert issue.exchange == "NSE"
        assert issue.open_date == "2026-06-10"
        assert issue.close_date == "2026-06-12"
        assert issue.listing_date == "2026-06-18"
        assert issue.price_band_low == 950.0
        assert issue.price_band_high == 1000.0
        assert issue.issue_size_cr == 55000.0
        assert issue.lot_size == 15

    def test_sme_row_default_segment(self):
        client = NSEIPOClient()
        row = {"companyName": "Foo SME Ltd", "series": "SME", "issuePrice": "85"}
        issue = client._parse_upcoming_row(row, "SME")
        client.close()
        assert issue is not None
        assert issue.segment == "SME"
        assert issue.price_band_low == 85.0

    def test_missing_issuer_returns_none(self):
        client = NSEIPOClient()
        assert client._parse_upcoming_row({"symbol": "X"}, "MAIN") is None
        client.close()


class TestParseSubscriptionRow:
    def test_full_row(self):
        client = NSEIPOClient()
        row = {
            "companyName": "Jio Platforms Limited",
            "qib": 4.5,
            "nII": 12.3,
            "rII": 8.75,
            "employee": 2.1,
            "total": 7.85,
        }
        sub = client._parse_subscription_row(row, "2026-06-11")
        client.close()
        assert sub is not None
        assert sub.issuer_name == "Jio Platforms Limited"
        assert sub.as_of_date == "2026-06-11"
        assert sub.qib_times == 4.5
        assert sub.nii_times == 12.3
        assert sub.retail_times == 8.75
        assert sub.employee_times == 2.1
        assert sub.total_times == 7.85

    def test_missing_issuer_returns_none(self):
        client = NSEIPOClient()
        assert client._parse_subscription_row({"qib": 1.0}, "2026-06-11") is None
        client.close()


class TestParseListingRow:
    def test_full_row(self):
        client = NSEIPOClient()
        row = {
            "symbol": "JIOPLAT",
            "companyName": "Jio Platforms Limited",
            "listingDate": "18-Jun-2026",
            "issuePrice": 1000.00,
            "lastTradedPrice": 1185.50,
            "pChange": 18.55,
        }
        listing = client._parse_listing_row(row)
        client.close()
        assert listing is not None
        assert listing.symbol == "JIOPLAT"
        assert listing.issuer_name == "Jio Platforms Limited"
        assert listing.listing_date == "2026-06-18"
        assert listing.listing_price == 1000.0
        assert listing.listing_day_close == 1185.50
        assert listing.listing_pop_pct == 18.55

    def test_pop_derived_when_missing(self):
        client = NSEIPOClient()
        row = {
            "symbol": "DERIVCO",
            "companyName": "DerivCo Ltd",
            "listingDate": "20-Jun-2026",
            "issuePrice": 100.0,
            "lastTradedPrice": 110.0,
        }
        listing = client._parse_listing_row(row)
        client.close()
        assert listing is not None
        # (110 - 100) / 100 * 100 = 10
        assert listing.listing_pop_pct == 10.0

    def test_missing_symbol_returns_none(self):
        client = NSEIPOClient()
        assert client._parse_listing_row({"companyName": "X Ltd"}) is None
        client.close()


# ---------------------------------------------------------------------------
# Fetch — respx integration


def _load_fixture(name: str):
    return json.loads((_GOLDEN / name).read_text())


class TestNSEFetchUpcoming:
    def test_fetch_upcoming_parses_mainboard_and_sme(self):
        ipo_fixture = _load_fixture("ipo_upcoming.json")
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(
                200, text="OK"
            )
            respx.get(url__regex=r"all-upcoming-issues\?category=ipo").respond(
                200, json=ipo_fixture,
            )
            respx.get(url__regex=r"all-upcoming-issues\?category=sme").respond(
                200, json=[],
            )
            with NSEIPOClient() as client:
                issues = client.fetch_upcoming()
        assert len(issues) == 3
        names = {i.issuer_name for i in issues}
        assert "Jio Platforms Limited" in names
        assert "Groww Technologies Ltd" in names
        # SME segment detection from `series == "SME"` even in the IPO list.
        sme = [i for i in issues if i.segment == "SME"]
        assert len(sme) == 1
        assert sme[0].issuer_name == "TestCo SME Solutions Ltd"

    def test_fetch_upcoming_empty_response(self):
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(
                200, text="OK"
            )
            respx.get(url__regex=r"all-upcoming-issues").respond(200, json=[])
            with NSEIPOClient() as client:
                issues = client.fetch_upcoming()
        assert issues == []


class TestNSEFetchSubscription:
    def test_fetch_subscription(self):
        fixture = _load_fixture("ipo_subscription.json")
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(
                200, text="OK"
            )
            respx.get(url__regex=r"ipo-current-issue").respond(200, json=fixture)
            with NSEIPOClient() as client:
                subs = client.fetch_subscription()
        assert len(subs) == 2
        jio = next(s for s in subs if s.issuer_name == "Jio Platforms Limited")
        assert jio.qib_times == 4.5
        assert jio.total_times == 7.85
        sme = next(s for s in subs if "SME" in s.issuer_name)
        assert sme.retail_times == 52.3
        # All snapshots get the same as_of_date (today)
        assert subs[0].as_of_date == subs[1].as_of_date


class TestNSEFetchListings:
    def test_fetch_listings(self):
        fixture = _load_fixture("ipo_listings.json")
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/market-data").respond(
                200, text="OK"
            )
            respx.get(url__regex=r"new-listing-today").respond(200, json=fixture)
            with NSEIPOClient() as client:
                listings = client.fetch_listings()
        assert len(listings) == 2
        jio = next(l for l in listings if l.symbol == "JIOPLAT")
        assert jio.listing_pop_pct == 18.55
        flop = next(l for l in listings if l.symbol == "SAMPLECO")
        assert flop.listing_pop_pct == -12.38


# ---------------------------------------------------------------------------
# BSE SME


class TestBSEIPOClient:
    def test_parse_sample_html(self):
        sample = (_GOLDEN / "bse_sme_upcoming.html").read_text()
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/PublicIssues").respond(
                200, text=sample,
            )
            with BSEIPOClient() as client:
                rows = client.fetch_upcoming_sme()
        # Both synthetic rows extracted
        assert len(rows) == 2
        first = rows[0]
        assert first.exchange == "BSE"
        assert first.segment == "SME"
        assert "Sample SME Ventures" in first.issuer_name
        # Dates parsed in any order — at least open/close present
        assert first.open_date == "2026-06-05"
        assert first.close_date == "2026-06-09"
        assert first.listing_date == "2026-06-14"
        assert first.price_band_low == 72.0
        assert first.price_band_high == 76.0

    def test_spa_shell_returns_empty(self):
        """When BSE returns the SPA shell (no <table>) and JS fallback is
        unavailable, parser yields ``[]``."""
        spa_shell = "<!DOCTYPE html><html><body><div id='app'></div></body></html>"
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/PublicIssues").respond(
                200, text=spa_shell,
            )
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                side_effect=JSFetchError("test: no browser"),
            ):
                with BSEIPOClient() as client:
                    rows = client.fetch_upcoming_sme()
        assert rows == []

    def test_http_failure_returns_empty(self):
        """Network failure is swallowed and JS fallback is also unavailable —
        caller treats SME as best-effort."""
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/PublicIssues").respond(
                503, text="Service Unavailable",
            )
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                side_effect=JSFetchError("test: no browser"),
            ):
                with BSEIPOClient() as client:
                    rows = client.fetch_upcoming_sme()
        assert rows == []

    def test_js_fallback_invoked_when_httpx_returns_spa_shell(self):
        """When httpx returns a shell, the JS-rendered fallback runs."""
        spa_shell = "<!DOCTYPE html><html><body><div id='app'></div></body></html>"
        # Synthetic rendered HTML that looks like a real BSE table.
        rendered = (
            "<html><body><table>"
            "<tr><th>Company</th><th>Open</th><th>Close</th><th>Price</th></tr>"
            "<tr><td>NewSME Issue Ltd</td><td>05-Jun-2026</td><td>09-Jun-2026</td>"
            "<td>72-76</td></tr>"
            "</table></body></html>"
        )
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/PublicIssues").respond(
                200, text=spa_shell,
            )
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                return_value=rendered,
            ) as mock_fetch:
                with BSEIPOClient() as client:
                    rows = client.fetch_upcoming_sme()
        mock_fetch.assert_called_once()
        assert mock_fetch.call_args.args[0] == (
            "https://www.bseindia.com/markets/PublicIssues/IPOIssues_new.aspx"
        )
        # Synthetic row extracted
        assert len(rows) == 1
        assert rows[0].issuer_name.startswith("NewSME")
        assert rows[0].exchange == "BSE"
        assert rows[0].segment == "SME"

    def test_js_fallback_access_denied_returns_empty(self):
        """Rendered fetch returns Akamai 'Access Denied' → []."""
        spa_shell = "<!DOCTYPE html><html><body><div id='app'></div></body></html>"
        access_denied = (
            "<html><head><title>Access Denied</title></head>"
            "<body><h1>Access Denied</h1></body></html>"
        )
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/PublicIssues").respond(
                200, text=spa_shell,
            )
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
                return_value=access_denied,
            ):
                with BSEIPOClient() as client:
                    rows = client.fetch_upcoming_sme()
        assert rows == []

    def test_real_table_in_httpx_skips_js_fallback(self):
        """If httpx already returns a parseable table, JS fallback is not
        called — we save the Playwright cold-start cost."""
        sample = (_GOLDEN / "bse_sme_upcoming.html").read_text()
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/markets/PublicIssues").respond(
                200, text=sample,
            )
            with patch(
                "flowtracker.js_fetch.fetch_rendered_html",
            ) as mock_fetch:
                with BSEIPOClient() as client:
                    rows = client.fetch_upcoming_sme()
        mock_fetch.assert_not_called()
        assert len(rows) == 2
