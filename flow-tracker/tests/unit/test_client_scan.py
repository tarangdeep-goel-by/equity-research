"""Tests for scan_client.py — niftyindices.com CSV constituent fetch.

NSE retired ``/api/equity-stockIndices?index=<NAME>`` (genuine app-server 404
as of 2026-05-26). The client now downloads CSV from
``niftyindices.com/IndexConstituent/ind_<slug>list.csv`` — these tests mock
those CSV bodies via respx.
"""

from __future__ import annotations

import pytest
import respx

from flowtracker.scan_client import (
    _INDEX_TO_SLUG,
    _SECTORAL_INDICES,
    NSEIndexClient,
    NSEIndexError,
)


# -- CSV fixtures (real niftyindices.com format) --

_NIFTY_50_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018\n"
    "Tata Consultancy Services Ltd.,Information Technology,TCS,EQ,INE467B01029\n"
)

_NIFTY_50_CSV_WITH_NON_EQ = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018\n"
    "Tata Motors DVR Ltd.,Automobile,TATAMTRDVR,DR,INE155A04022\n"  # DR series — skip
    "Tata Consultancy Services Ltd.,Information Technology,TCS,EQ,INE467B01029\n"
)

_NIFTY_BANK_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "HDFC Bank Ltd.,Financial Services,HDFCBANK,EQ,INE040A01034\n"
    "ICICI Bank Ltd.,Financial Services,ICICIBANK,EQ,INE090A01021\n"
)

_EMPTY_CSV_HEADER_ONLY = "Company Name,Industry,Symbol,Series,ISIN Code\n"


# -- fetch_constituents (the renamed API surface) --


class TestFetchConstituents:
    """fetch_constituents pulls + parses a niftyindices CSV."""

    def test_parses_eq_series_constituents(self):
        with respx.mock:
            respx.get(
                "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
            ).respond(200, text=_NIFTY_50_CSV)
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY 50")

        assert len(constituents) == 2
        symbols = {c.symbol for c in constituents}
        assert symbols == {"RELIANCE", "TCS"}

    def test_skips_non_eq_series(self):
        """DVR / preference / debt series should be filtered out."""
        with respx.mock:
            respx.get(
                "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
            ).respond(200, text=_NIFTY_50_CSV_WITH_NON_EQ)
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY 50")

        symbols = {c.symbol for c in constituents}
        assert "TATAMTRDVR" not in symbols
        assert symbols == {"RELIANCE", "TCS"}

    def test_constituents_have_correct_fields(self):
        with respx.mock:
            respx.get(
                "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
            ).respond(200, text=_NIFTY_50_CSV)
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY 50")

        rel = next(c for c in constituents if c.symbol == "RELIANCE")
        assert rel.index_name == "NIFTY 50"
        assert rel.company_name == "Reliance Industries Ltd."
        assert rel.industry == "Oil Gas & Consumable Fuels"

    def test_empty_csv_raises_error(self):
        """Header-only CSV → 0 constituents → NSEIndexError."""
        with respx.mock:
            respx.get(
                "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
            ).respond(200, text=_EMPTY_CSV_HEADER_ONLY)
            with NSEIndexClient() as client:
                with pytest.raises(NSEIndexError, match="parsed to 0"):
                    client.fetch_constituents("NIFTY 50")

    def test_unknown_index_name_raises(self):
        """Indices we don't have a slug for fail fast (no network call)."""
        with NSEIndexClient() as client:
            with pytest.raises(NSEIndexError, match="Unknown index"):
                client.fetch_constituents("NIFTY MADE-UP 999")

    def test_index_name_is_preserved(self):
        """The display name (not the slug) flows into IndexConstituent."""
        with respx.mock:
            respx.get(
                "https://niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
            ).respond(200, text=_NIFTY_50_CSV)
            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY NEXT 50")

        assert all(c.index_name == "NIFTY NEXT 50" for c in constituents)


# -- Sectoral index coverage --


class TestFetchSectoralIndex:
    """Sectoral indices (NIFTY BANK, NIFTY IT, …) ride the same CSV path."""

    def test_fetch_nifty_bank_parses_constituents(self):
        with respx.mock:
            route = respx.get(
                "https://niftyindices.com/IndexConstituent/ind_niftybanklist.csv",
            ).respond(200, text=_NIFTY_BANK_CSV)

            with NSEIndexClient() as client:
                constituents = client.fetch_constituents("NIFTY BANK")

        # The exact slug was hit (no fallback to a different URL).
        assert route.called
        assert "ind_niftybanklist.csv" in str(route.calls[0].request.url)

        assert len(constituents) == 2
        symbols = {c.symbol for c in constituents}
        assert symbols == {"HDFCBANK", "ICICIBANK"}
        assert all(c.index_name == "NIFTY BANK" for c in constituents)

    def test_fetch_sectoral_indices_returns_per_index_mapping(self):
        """`fetch_sectoral_indices` returns a dict keyed by index name."""
        with respx.mock:
            respx.get(
                "https://niftyindices.com/IndexConstituent/ind_niftybanklist.csv",
            ).respond(200, text=_NIFTY_BANK_CSV)

            with NSEIndexClient() as client:
                # Only fetch one to keep the test fast (no time.sleep loop).
                by_index = client.fetch_sectoral_indices(["NIFTY BANK"])

        assert set(by_index.keys()) == {"NIFTY BANK"}
        assert len(by_index["NIFTY BANK"]) == 2

    def test_sectoral_indices_constant_covers_required_set(self):
        """Spec lock-in: the 11 sectoral / extra broad indices we fetch."""
        assert set(_SECTORAL_INDICES) == {
            "NIFTY MIDCAP 100",
            "NIFTY BANK",
            "NIFTY IT",
            "NIFTY PHARMA",
            "NIFTY AUTO",
            "NIFTY FMCG",
            "NIFTY METAL",
            "NIFTY ENERGY",
            "NIFTY REALTY",
            "NIFTY PSU BANK",
            "NIFTY FINANCIAL SERVICES",
        }

    def test_every_default_and_sectoral_index_has_a_slug(self):
        """Every index name the CLI commands can request must map to a slug."""
        from flowtracker.scan_client import _NIFTY_INDICES, _SECTORAL_INDICES

        for name in (*_NIFTY_INDICES, *_SECTORAL_INDICES):
            assert name in _INDEX_TO_SLUG, f"{name} missing from _INDEX_TO_SLUG"


# -- Theme-index fetch (12 sectoral + thematic) --

# NSE archives CSV format: header + comma-delimited rows.
_DEFENCE_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Hindustan Aeronautics Ltd.,Aerospace & Defense,HAL,EQ,INE066F01020\n"
    "Bharat Electronics Ltd.,Aerospace & Defense,BEL,EQ,INE263A01024\n"
)


class TestFetchThemeIndices:
    """Tests for ``fetch_theme_indices`` — the 12-index batch fetcher.

    The implementation pulls from
    ``nsearchives.nseindia.com/content/indices/<csv_filename>``
    (NOT the `/api/equity-stockIndices` JSON endpoint — that endpoint
    404s for all indices as of 2026-05-26).
    """

    def test_defence_index_parses_archive_csv_with_canonical_name(self, monkeypatch):
        """Defence CSV parses → 2 stocks with index_name stamped to
        canonical 'NIFTY INDIA DEFENCE'. Other 11 indices land in
        `failed` because we stub their CSVs as 404."""
        # 12 indices × 1s sleep = 11s of waiting; skip pacing in unit tests.
        monkeypatch.setattr("flowtracker.scan_client.time.sleep", lambda _s: None)
        with respx.mock:
            # Defence CSV — primary path under test.
            respx.get(
                "https://nsearchives.nseindia.com/content/indices/"
                "ind_niftyindiadefence_list.csv"
            ).respond(200, text=_DEFENCE_CSV)
            # All other archive CSVs 404 so they surface as `failed`.
            respx.get(
                url__regex=r"nsearchives\.nseindia\.com/content/indices/.*\.csv"
            ).respond(404, text="not found")

            with NSEIndexClient() as client:
                all_consts, failed = client.fetch_theme_indices()

        defence = [c for c in all_consts if c.index_name == "NIFTY INDIA DEFENCE"]
        assert len(defence) == 2
        assert {c.symbol for c in defence} == {"HAL", "BEL"}
        hal = next(c for c in defence if c.symbol == "HAL")
        assert hal.company_name == "Hindustan Aeronautics Ltd."
        assert hal.industry == "Aerospace & Defense"
        # All other 11 names 404'd → land in `failed`.
        assert "NIFTY INDIA DEFENCE" not in failed
        assert len(failed) == 11
