"""Tests for indexpe_client.py — niftyindices.com PE/PB/Div-Yield parser.

The endpoint returns a JSON envelope wrapping a stringified JSON array
(see flowtracker.indexpe_client docstring). We exercise the parser
against a golden fixture captured live from
``Backpage.aspx/getpepbHistoricaldataDBtoString`` plus a couple of
synthetic edge-case payloads.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from flowtracker.indexpe_client import (
    INDEX_NAME_MAP,
    IndexValuationClient,
    IndexValuationFetchError,
    parse_pepb_response,
)


# ----- golden-fixture parser tests -------------------------------------------


def _load_golden(golden_dir: Path) -> str:
    return (golden_dir / "nifty50_pe_sample.json").read_text()


class TestParser:
    def test_golden_fixture_parses(self, golden_dir: Path):
        body = _load_golden(golden_dir)
        rows = parse_pepb_response(body, "NIFTY 50")

        assert rows, "golden fixture should contain at least one row"
        first = rows[0]
        assert first.index_name == "NIFTY 50"
        assert first.date.startswith("2025-01-")
        # Sanity-check the numeric ranges typical for Nifty 50 in early 2025.
        assert 15 < first.pe < 35
        assert 2.0 < first.pb < 6.0
        assert 0.5 < first.dividend_yield < 2.5

    def test_empty_outer_returns_empty_list(self):
        assert parse_pepb_response('{"d":""}', "NIFTY 50") == []
        assert parse_pepb_response('{"d":"[]"}', "NIFTY 50") == []
        assert parse_pepb_response('{"d":[]}', "NIFTY 50") == []
        assert parse_pepb_response('{}', "NIFTY 50") == []

    def test_invalid_outer_json_returns_empty(self):
        assert parse_pepb_response("not json at all", "NIFTY 50") == []

    def test_skips_rows_with_unparseable_date(self):
        body = json.dumps({"d": json.dumps([
            {"DATE": "junk", "pe": "20", "pb": "3", "divYield": "1"},
            {"DATE": "01 Jan 2025", "pe": "20", "pb": "3", "divYield": "1"},
        ])})
        rows = parse_pepb_response(body, "NIFTY 50")
        assert len(rows) == 1
        assert rows[0].date == "2025-01-01"

    def test_handles_none_and_dash_numeric_fields(self):
        body = json.dumps({"d": json.dumps([
            {"DATE": "01 Jan 2025", "pe": "-", "pb": None, "divYield": ""},
            {"DATE": "02 Jan 2025", "pe": "21.5", "pb": "3.4", "divYield": "1.2"},
        ])})
        rows = parse_pepb_response(body, "NIFTY 50")
        assert len(rows) == 2
        assert rows[0].pe is None
        assert rows[0].pb is None
        assert rows[0].dividend_yield is None
        assert rows[1].pe == 21.5


# ----- HTTP integration via respx --------------------------------------------


@respx.mock
def test_fetch_range_posts_correct_payload_and_parses():
    """End-to-end check: client builds the correct POST body and ingests rows."""
    captured: dict[str, object] = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode()
        body = json.dumps({"d": json.dumps([
            {"DATE": "10 Jan 2025", "pe": "21.59", "pb": "3.49", "divYield": "1.28"},
            {"DATE": "09 Jan 2025", "pe": "21.68", "pb": "3.51", "divYield": "1.28"},
        ])})
        return httpx.Response(200, text=body)

    respx.post(
        "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString",
    ).mock(side_effect=_responder)

    with IndexValuationClient() as client:
        rows = client.fetch_range(
            "NIFTY 50", date(2025, 1, 9), date(2025, 1, 10),
        )

    # Two rows, dedupe + oldest-first
    assert [r.date for r in rows] == ["2025-01-09", "2025-01-10"]
    assert rows[0].pe == 21.68
    # Body sanity: the canonical name and `cinfo` envelope are present.
    assert "cinfo" in captured["body"]
    assert "NIFTY 50" in captured["body"]
    assert "09-Jan-2025" in captured["body"]
    assert "10-Jan-2025" in captured["body"]


@respx.mock
def test_fetch_range_paginates_over_long_window():
    """Windows >360 days get split into multiple POSTs."""
    call_count = {"n": 0}

    def _responder(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, text=json.dumps({"d": json.dumps([])}))

    respx.post(
        "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString",
    ).mock(side_effect=_responder)

    with IndexValuationClient() as client:
        rows = client.fetch_range(
            "NIFTY 50", date(2023, 1, 1), date(2025, 1, 1),
        )

    assert rows == []
    # ~730 days / 360 page-size → at least 3 chunks
    assert call_count["n"] >= 3


@respx.mock
def test_smallcap_250_uses_trading_name_abbreviation():
    """NIFTY SMALLCAP 250 must POST with `name='NIFTY SMLCAP 250'` —
    the niftyindices PE endpoint returns [] for the full word."""
    captured: dict[str, str] = {}

    def _responder(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return httpx.Response(200, text=json.dumps({"d": json.dumps([])}))

    respx.post(
        "https://www.niftyindices.com/Backpage.aspx/getpepbHistoricaldataDBtoString",
    ).mock(side_effect=_responder)

    with IndexValuationClient() as client:
        client.fetch_range(
            "NIFTY SMALLCAP 250", date(2025, 1, 1), date(2025, 1, 5),
        )

    body = captured["body"]
    assert "NIFTY SMLCAP 250" in body
    assert "'indexName':'NIFTY SMALLCAP 250'" in body


def test_unknown_index_raises():
    with IndexValuationClient() as client:
        with pytest.raises(IndexValuationFetchError):
            client.fetch_range("NIFTY 99", date(2025, 1, 1), date(2025, 1, 5))


def test_index_name_map_covers_required_indices():
    """Lock the spec: these four broad-market indices must always be supported."""
    required = {"NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"}
    assert required.issubset(INDEX_NAME_MAP.keys())
