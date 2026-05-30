"""Tests for flowtracker/us_short_interest_client.py (Nasdaq short-interest).

Parsing is pure (no network) — most tests hit ``parse_short_interest`` /
``_to_float`` / ``_norm_date`` directly. One respx test covers the HTTP path
end-to-end, and a second covers graceful failure on a non-200.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from flowtracker.us_short_interest_client import (
    _norm_date,
    _to_float,
    fetch_us_short_interest,
    parse_short_interest,
)

_SAMPLE = {
    "data": {
        "symbol": "aapl",
        "shortInterestTable": {
            "rows": [
                {"settlementDate": "05/15/2026", "interest": "138,782,718",
                 "avgDailyShareVolume": "50,565,316", "daysToCover": 2.744623},
                {"settlementDate": "04/30/2026", "interest": "134,675,274",
                 "avgDailyShareVolume": "45,944,025", "daysToCover": 2.931290},
            ]
        },
    }
}


class TestParse:
    def test_happy_path(self):
        rows = parse_short_interest(_SAMPLE, "AAPL")
        assert len(rows) == 2
        r = rows[0]
        assert r["symbol"] == "AAPL"
        assert r["market"] == "NASDAQ"
        assert r["currency"] == "USD"
        assert r["settlement_date"] == "2026-05-15"
        assert r["short_interest"] == 138_782_718.0
        assert r["avg_daily_volume"] == 50_565_316.0
        assert r["days_to_cover"] == 2.744623

    def test_empty_and_malformed(self):
        assert parse_short_interest({}, "X") == []
        assert parse_short_interest({"data": {}}, "X") == []
        assert parse_short_interest({"data": {"shortInterestTable": {"rows": []}}}, "X") == []
        assert parse_short_interest(None, "X") == []
        assert parse_short_interest("nonsense", "X") == []

    def test_row_without_date_skipped(self):
        payload = {"data": {"shortInterestTable": {"rows": [
            {"interest": "100", "daysToCover": 1.0},  # no settlementDate
            {"settlementDate": "01/02/2026", "interest": "200", "daysToCover": 2.0},
        ]}}}
        rows = parse_short_interest(payload, "X")
        assert len(rows) == 1
        assert rows[0]["settlement_date"] == "2026-01-02"

    def test_to_float(self):
        assert _to_float("138,782,718") == 138_782_718.0
        assert _to_float(2.74) == 2.74
        assert _to_float("$1,234.5") == 1234.5
        assert _to_float("") is None
        assert _to_float("--") is None
        assert _to_float(None) is None
        assert _to_float("N/A") is None

    def test_norm_date(self):
        assert _norm_date("05/15/2026") == "2026-05-15"
        assert _norm_date("1/2/2026") == "2026-01-02"
        assert _norm_date(None) is None
        assert _norm_date("2026-05-15") == "2026-05-15"  # passthrough


class TestFetch:
    @respx.mock
    def test_fetch_ok(self):
        respx.get(url__regex=r"https://api\.nasdaq\.com/api/quote/AAPL/short-interest.*").mock(
            return_value=httpx.Response(200, json=_SAMPLE)
        )
        rows = fetch_us_short_interest("AAPL")
        assert len(rows) == 2
        assert rows[0]["days_to_cover"] == 2.744623

    @respx.mock
    def test_fetch_403_returns_empty(self):
        respx.get(url__regex=r"https://api\.nasdaq\.com/.*").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        assert fetch_us_short_interest("AAPL") == []
