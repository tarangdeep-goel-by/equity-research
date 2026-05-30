"""US monthly macro econ client (US add-on, feat/us-econ-series).

Covers the FRED CSV parser + fetchers for US CPI (CPIAUCSL) and Industrial
Production (INDPRO). All offline — fetchers are mocked with httpx via respx;
the parser is exercised against a recorded inline FRED CSV fixture.

Asserts:
  * YoY% = (idx_t / idx_{t-12} - 1) * 100, computed correctly
  * rows tagged with the right series ('cpi' / 'iip')
  * period normalized to FRED first-of-month 'YYYY-MM-01'
  * missing observations ('.', '', 'NA') skipped defensively
  * HTTP failure / empty parse raise USMacroEconClientError
"""

from __future__ import annotations

import httpx
import pytest
import respx

from flowtracker.us_macro_econ_client import (
    USMacroEconClientError,
    fetch_us_cpi,
    fetch_us_iip,
    parse_fred_monthly_csv,
)

# Recorded FRED-shape CSV: 13 monthly rows (2024-01 .. 2025-01) so the last
# row has a 12-month predecessor for a deterministic YoY check. 2024-06 is a
# '.' sentinel (missing observation) — must be skipped without crashing.
_CPI_CSV = """observation_date,CPIAUCSL
2024-01-01,308.417
2024-02-01,310.326
2024-03-01,312.230
2024-04-01,313.207
2024-05-01,313.225
2024-06-01,.
2024-07-01,313.534
2024-08-01,314.121
2024-09-01,314.686
2024-10-01,315.454
2024-11-01,316.449
2024-12-01,317.603
2025-01-01,319.086
"""


class TestParseFredMonthlyCsv:
    def test_yoy_and_series_tag(self):
        rows = parse_fred_monthly_csv(_CPI_CSV, series="cpi")
        # 13 lines, 1 missing ('.') -> 12 rows.
        assert len(rows) == 12
        # All tagged 'cpi'.
        assert all(r["series"] == "cpi" for r in rows)
        # Source defaults to FRED.
        assert all(r["source"] == "FRED" for r in rows)
        # Ascending by period; 2024-06 skipped.
        periods = [r["period"] for r in rows]
        assert periods[0] == "2024-01-01"
        assert "2024-06-01" not in periods
        assert periods[-1] == "2025-01-01"

    def test_yoy_computed_correctly(self):
        rows = parse_fred_monthly_csv(_CPI_CSV, series="cpi")
        by_period = {r["period"]: r for r in rows}
        # 2025-01 vs 2024-01: (319.086 / 308.417 - 1) * 100 = 3.46%
        jan25 = by_period["2025-01-01"]
        expected = round((319.086 / 308.417 - 1.0) * 100.0, 2)
        assert jan25["yoy_pct"] == expected
        assert expected == pytest.approx(3.46, abs=0.01)
        # Rows without a 12-month predecessor get yoy_pct None.
        assert by_period["2024-01-01"]["yoy_pct"] is None

    def test_index_value_passthrough_rounded(self):
        rows = parse_fred_monthly_csv(_CPI_CSV, series="cpi")
        by_period = {r["period"]: r for r in rows}
        assert by_period["2024-01-01"]["index_value"] == 308.42

    def test_source_url_threaded(self):
        rows = parse_fred_monthly_csv(_CPI_CSV, series="iip", source_url="http://x")
        assert all(r["series"] == "iip" for r in rows)
        assert all(r["source_url"] == "http://x" for r in rows)

    def test_empty_and_header_only(self):
        assert parse_fred_monthly_csv("", series="cpi") == []
        assert parse_fred_monthly_csv("observation_date,CPIAUCSL", series="cpi") == []

    def test_na_and_blank_skipped(self):
        csv = (
            "observation_date,INDPRO\n"
            "2024-01-01,100.0\n"
            "2024-02-01,NA\n"
            "2024-03-01,\n"
            "2024-04-01,101.5\n"
        )
        rows = parse_fred_monthly_csv(csv, series="iip")
        assert len(rows) == 2
        assert [r["period"] for r in rows] == ["2024-01-01", "2024-04-01"]


class TestFetchers:
    @respx.mock
    def test_fetch_us_cpi_happy(self):
        respx.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
        ).mock(return_value=httpx.Response(200, text=_CPI_CSV))
        rows = fetch_us_cpi()
        assert len(rows) == 12
        assert all(r["series"] == "cpi" for r in rows)
        assert rows[-1]["period"] == "2025-01-01"
        # source_url points at the FRED endpoint.
        assert "CPIAUCSL" in rows[0]["source_url"]

    @respx.mock
    def test_fetch_us_iip_happy(self):
        csv = (
            "observation_date,INDPRO\n"
            "2024-01-01,102.0\n"
            "2025-01-01,104.04\n"
        )
        respx.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO"
        ).mock(return_value=httpx.Response(200, text=csv))
        rows = fetch_us_iip()
        assert len(rows) == 2
        assert all(r["series"] == "iip" for r in rows)
        # YoY = (104.04 / 102.0 - 1) * 100 = 2.0%
        assert rows[-1]["yoy_pct"] == pytest.approx(2.0, abs=0.01)

    @respx.mock
    def test_fetch_http_error_raises(self):
        respx.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
        ).mock(return_value=httpx.Response(500))
        with pytest.raises(USMacroEconClientError):
            fetch_us_cpi()

    @respx.mock
    def test_fetch_empty_parse_raises(self):
        respx.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO"
        ).mock(return_value=httpx.Response(200, text="observation_date,INDPRO\n"))
        with pytest.raises(USMacroEconClientError):
            fetch_us_iip()
