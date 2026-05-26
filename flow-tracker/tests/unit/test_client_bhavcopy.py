"""Tests for bhavcopy_client.py — modern + legacy URL paths."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from flowtracker.bhavcopy_client import (
    _LEGACY_BASE_URL,
    BhavcopyClient,
)
from flowtracker.bhavcopy_models import DailyStockData

GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


# -- Modern (2020+) CSV fixture --

_MODERN_CSV = (
    " SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE,"
    " LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS,"
    " NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
    " SBIN, EQ, 02-JAN-2024, 600.00, 605.00, 615.00, 600.00,"
    " 610.00, 612.00, 608.00, 1000000, 6080.00, 5000, 500000, 50.00\n"
    " INFY, EQ, 02-JAN-2024, 1500.00, 1505.00, 1520.00, 1495.00,"
    " 1510.00, 1515.00, 1510.00, 500000, 7550.00, 3000, 250000, 60.00\n"
    " SBIN, BE, 02-JAN-2024, 600.00, 605.00, 615.00, 600.00,"
    " 610.00, 612.00, 608.00, 1000, 6.08, 50, 500, 50.00\n"
)


def _modern_url(target: date) -> str:
    return (
        "https://nsearchives.nseindia.com/products/content/"
        f"sec_bhavdata_full_{target.strftime('%d%m%Y')}.csv"
    )


def _legacy_url(target: date) -> str:
    return (
        f"{_LEGACY_BASE_URL}/{target.year}/{target.strftime('%b').upper()}/"
        f"cm{target.strftime('%d%b%Y').upper()}bhav.csv.zip"
    )


# -- Modern path --


class TestModern:
    """Modern CSV URL path (2020+)."""

    def test_parses_modern_csv(self):
        client = BhavcopyClient()
        records = client._parse_csv(_MODERN_CSV, "2024-01-02")
        client.close()

        assert len(records) == 2  # BE series excluded
        assert {r.symbol for r in records} == {"SBIN", "INFY"}

        sbin = next(r for r in records if r.symbol == "SBIN")
        assert sbin.date == "2024-01-02"
        assert sbin.open == 605.00
        # In the modern CSV the column after LAST_PRICE is CLOSE_PRICE; row value = 612
        assert sbin.close == 612.00
        assert sbin.volume == 1_000_000
        assert sbin.turnover == 6080.00
        assert sbin.delivery_qty == 500_000
        assert sbin.delivery_pct == 50.00

    def test_fetch_day_uses_modern_url(self):
        target = date(2024, 1, 2)
        with respx.mock:
            respx.get(_modern_url(target)).mock(
                return_value=httpx.Response(200, text=_MODERN_CSV),
            )
            with BhavcopyClient() as client:
                records = client.fetch_day(target)

        assert len(records) == 2
        assert all(r.delivery_pct is not None for r in records)


# -- Legacy fallback --


class TestLegacyFallback:
    """Legacy URL fallback for pre-2020 dates."""

    def test_modern_404_falls_back_to_legacy(self):
        target = date(2008, 1, 2)
        zip_bytes = (GOLDEN / "bhavcopy_legacy_2008.zip").read_bytes()

        with respx.mock(assert_all_called=False) as rsx:
            # Modern 404
            rsx.get(_modern_url(target)).mock(return_value=httpx.Response(404))
            # Cookie preflight
            rsx.get("https://www.nseindia.com/").mock(
                return_value=httpx.Response(200, text="<html></html>"),
            )
            # Legacy returns the zip
            legacy_route = rsx.get(_legacy_url(target)).mock(
                return_value=httpx.Response(
                    200,
                    content=zip_bytes,
                    headers={"content-type": "application/zip"},
                ),
            )
            with BhavcopyClient() as client:
                records = client.fetch_day(target)

        assert legacy_route.called, "legacy URL should be hit after modern 404"
        assert len(records) > 0, "should parse rows from the legacy zip"
        # Delivery columns must be NULL in legacy data
        assert all(r.delivery_qty is None for r in records)
        assert all(r.delivery_pct is None for r in records)
        # Spot-check the date carries through
        assert all(r.date == "2008-01-02" for r in records)

    def test_legacy_flag_skips_modern(self):
        target = date(2008, 1, 2)
        zip_bytes = (GOLDEN / "bhavcopy_legacy_2008.zip").read_bytes()

        with respx.mock(assert_all_called=False) as rsx:
            modern_route = rsx.get(_modern_url(target)).mock(
                return_value=httpx.Response(200, text=_MODERN_CSV),
            )
            rsx.get("https://www.nseindia.com/").mock(
                return_value=httpx.Response(200, text="<html></html>"),
            )
            rsx.get(_legacy_url(target)).mock(
                return_value=httpx.Response(200, content=zip_bytes),
            )
            with BhavcopyClient() as client:
                records = client.fetch_day(target, legacy=True)

        assert not modern_route.called, "legacy=True must skip the modern URL"
        assert len(records) > 0

    def test_both_404_returns_empty(self):
        target = date(2008, 1, 1)  # holiday in legacy archive too
        with respx.mock(assert_all_called=False) as rsx:
            rsx.get(_modern_url(target)).mock(return_value=httpx.Response(404))
            rsx.get("https://www.nseindia.com/").mock(
                return_value=httpx.Response(200, text=""),
            )
            rsx.get(_legacy_url(target)).mock(return_value=httpx.Response(404))
            with BhavcopyClient() as client:
                records = client.fetch_day(target)

        assert records == []


# -- Legacy parser --


class TestLegacyParser:
    """Parser handles legacy CSV column set + missing delivery columns."""

    def test_parses_real_2008_csv(self):
        zip_bytes = (GOLDEN / "bhavcopy_legacy_2008.zip").read_bytes()
        with BhavcopyClient() as client:
            records = client._parse_legacy_zip(zip_bytes, "2008-01-02")

        assert len(records) > 100, "real 2008 bhavcopy should have many EQ rows"
        # All from this date
        assert all(r.date == "2008-01-02" for r in records)
        # All have NULL delivery (legacy CSV has no delivery columns)
        assert all(r.delivery_qty is None for r in records)
        assert all(r.delivery_pct is None for r in records)
        # OHLCV present, positive
        sample = records[0]
        assert sample.open > 0
        assert sample.close > 0
        assert sample.volume > 0

    def test_legacy_only_returns_eq_series(self):
        # Construct minimal legacy CSV with EQ + non-EQ rows
        csv_text = (
            "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,"
            "TOTTRDQTY,TOTTRDVAL,TIMESTAMP,\n"
            "GOODSTOCK,EQ,100,110,95,105,104,99,10000,1050000,2-JAN-2008,\n"
            "BADSTOCK,BE,50,55,48,52,52,49,500,26000,2-JAN-2008,\n"
            "OTHER,BL,200,210,195,205,205,200,100,20500,2-JAN-2008,\n"
        )
        with BhavcopyClient() as client:
            records = client._parse_legacy_csv(csv_text, "2008-01-02")

        assert len(records) == 1
        assert records[0].symbol == "GOODSTOCK"
        assert records[0].open == 100
        assert records[0].close == 105
        assert records[0].volume == 10000
        # TOTTRDVAL (1,050,000 rupees) -> 10.5 lakhs
        assert records[0].turnover == pytest.approx(10.5)
        assert records[0].delivery_qty is None
        assert records[0].delivery_pct is None

    def test_legacy_handles_stripped_field_names(self):
        # Some legacy files have trailing/leading whitespace in headers
        csv_text = (
            " SYMBOL , SERIES , OPEN , HIGH , LOW , CLOSE , LAST , PREVCLOSE ,"
            " TOTTRDQTY , TOTTRDVAL , TIMESTAMP ,\n"
            "SBIN,EQ,1500,1520,1490,1510,1505,1495,100000,151000000,2-APR-2007,\n"
        )
        with BhavcopyClient() as client:
            records = client._parse_legacy_csv(csv_text, "2007-04-02")

        assert len(records) == 1
        assert records[0].symbol == "SBIN"
        assert records[0].close == 1510
        # 151_000_000 rupees -> 1510 lakhs
        assert records[0].turnover == pytest.approx(1510.0)
