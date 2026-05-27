"""Tests for mf_nav_client.py — mfapi.in daily scheme NAV parser.

The endpoint returns ``{"meta": {...}, "status": "SUCCESS", "data":
[{"date": "DD-MM-YYYY", "nav": "<float-string>"}, ...]}`` newest-first.
We exercise the date normalisation, since-filter, and error path with
synthetic respx fixtures.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from flowtracker.mf_nav_client import (
    EQUITY_SCHEMES,
    MFNavClient,
    MFNavFetchError,
    _to_iso,
)


# ----- Date normalisation helper --------------------------------------------


class TestDateNormalisation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("26-05-2026", "2026-05-26"),
            ("01-01-2013", "2013-01-01"),
            ("31-12-1999", "1999-12-31"),
        ],
    )
    def test_well_formed_dates(self, raw, expected):
        assert _to_iso(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "bad-date",
            "2026-05-26",       # ISO order is not mfapi's format
            "26/05/2026",       # wrong separator
            "1-1-2026",         # zero-padding required
            "26-05-26",         # 2-digit year not accepted
        ],
    )
    def test_malformed_dates_return_none(self, raw):
        assert _to_iso(raw) is None


# ----- Curated universe shape -----------------------------------------------


class TestEquitySchemesUniverse:
    def test_universe_size(self):
        """The curated equity universe is exactly 30 schemes."""
        assert len(EQUITY_SCHEMES) == 30

    def test_universe_has_unique_codes(self):
        codes = [c for c, _ in EQUITY_SCHEMES]
        assert len(codes) == len(set(codes)), "scheme codes must be unique"

    def test_universe_codes_are_integers(self):
        for code, name in EQUITY_SCHEMES:
            assert isinstance(code, int)
            assert isinstance(name, str)
            assert name, "scheme name must be non-empty"


# ----- HTTP integration via respx -------------------------------------------


def _fake_mfapi_payload(scheme_code: int, scheme_name: str, rows: list[dict]) -> dict:
    return {
        "meta": {
            "fund_house": "Test AMC",
            "scheme_type": "Open Ended Schemes",
            "scheme_category": "Equity Scheme - Flexi Cap Fund",
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "isin_growth": "INF000K00000",
            "isin_div_reinvestment": None,
        },
        "status": "SUCCESS",
        "data": rows,
    }


@respx.mock
def test_fetch_scheme_parses_and_normalises_dates():
    payload = _fake_mfapi_payload(
        scheme_code=118955,
        scheme_name="HDFC Flexi Cap Fund - Growth Option - Direct Plan",
        rows=[
            {"date": "26-05-2026", "nav": "2158.76200"},
            {"date": "23-05-2026", "nav": "2155.00100"},
            {"date": "01-01-2013", "nav": "296.87600"},
        ],
    )
    respx.get("https://api.mfapi.in/mf/118955").mock(
        return_value=httpx.Response(200, json=payload)
    )

    with MFNavClient() as client:
        rows = client.fetch_scheme(118955)

    # 3 rows, oldest-first ordering
    assert [r.date for r in rows] == ["2013-01-01", "2026-05-23", "2026-05-26"]
    assert rows[0].nav == pytest.approx(296.876, rel=1e-4)
    assert rows[-1].nav == pytest.approx(2158.762, rel=1e-4)
    # Scheme name and code propagated from meta
    assert rows[0].scheme_code == 118955
    assert "HDFC Flexi Cap" in rows[0].scheme_name


@respx.mock
def test_fetch_scheme_since_filter_applies():
    payload = _fake_mfapi_payload(
        scheme_code=118955,
        scheme_name="HDFC Flexi Cap Fund",
        rows=[
            {"date": "26-05-2026", "nav": "2158.76200"},
            {"date": "01-01-2015", "nav": "500.00000"},
            {"date": "01-01-2013", "nav": "296.87600"},  # below cutoff
        ],
    )
    respx.get("https://api.mfapi.in/mf/118955").mock(
        return_value=httpx.Response(200, json=payload)
    )

    with MFNavClient() as client:
        rows = client.fetch_scheme(118955, since="2014-01-01")

    # Only the two on/after 2014-01-01 survive; sorted oldest-first
    assert [r.date for r in rows] == ["2015-01-01", "2026-05-26"]


@respx.mock
def test_fetch_scheme_skips_unparseable_nav():
    payload = _fake_mfapi_payload(
        scheme_code=118955,
        scheme_name="HDFC Flexi Cap Fund",
        rows=[
            {"date": "26-05-2026", "nav": "bad"},
            {"date": "25-05-2026", "nav": None},
            {"date": "24-05-2026", "nav": "100.5"},
        ],
    )
    respx.get("https://api.mfapi.in/mf/118955").mock(
        return_value=httpx.Response(200, json=payload)
    )

    with MFNavClient() as client:
        rows = client.fetch_scheme(118955)

    assert len(rows) == 1
    assert rows[0].date == "2026-05-24"
    assert rows[0].nav == 100.5


@respx.mock
def test_fetch_scheme_skips_unparseable_dates():
    payload = _fake_mfapi_payload(
        scheme_code=118955,
        scheme_name="HDFC Flexi Cap Fund",
        rows=[
            {"date": "junk", "nav": "100"},
            {"date": "26-05-2026", "nav": "200"},
        ],
    )
    respx.get("https://api.mfapi.in/mf/118955").mock(
        return_value=httpx.Response(200, json=payload)
    )

    with MFNavClient() as client:
        rows = client.fetch_scheme(118955)

    assert len(rows) == 1
    assert rows[0].date == "2026-05-26"


@respx.mock
def test_fetch_scheme_retries_then_raises():
    """All retries exhausted → MFNavFetchError."""
    respx.get("https://api.mfapi.in/mf/999999").mock(
        return_value=httpx.Response(500, text="server error")
    )

    with MFNavClient() as client:
        with pytest.raises(MFNavFetchError):
            client.fetch_scheme(999999)


@respx.mock
def test_fetch_universe_aggregates_and_skips_failures():
    """A failing scheme is logged and dropped; the rest succeed."""
    ok = _fake_mfapi_payload(
        scheme_code=118955,
        scheme_name="HDFC Flexi Cap Fund",
        rows=[{"date": "26-05-2026", "nav": "100.0"}],
    )
    respx.get("https://api.mfapi.in/mf/118955").mock(
        return_value=httpx.Response(200, json=ok)
    )
    respx.get("https://api.mfapi.in/mf/999999").mock(
        return_value=httpx.Response(500, text="boom")
    )

    with MFNavClient() as client:
        out = client.fetch_universe(
            schemes=[(118955, "HDFC Flexi Cap"), (999999, "Bogus")],
            polite_delay=0.0,
        )

    assert 118955 in out
    assert 999999 not in out
    assert len(out[118955]) == 1


def test_default_since_returns_iso_date():
    out = MFNavClient.default_since(years=10)
    assert isinstance(out, str)
    assert len(out) == 10
    assert out[4] == "-" and out[7] == "-"
