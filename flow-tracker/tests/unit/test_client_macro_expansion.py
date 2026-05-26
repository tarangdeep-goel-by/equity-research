"""Tests for CPI / IIP / PMI / yield-curve clients and the CCIL multi-tenor parser.

Covers:
* Seed loading + period lookup + backfill (CPI / IIP / PMI / yield-curve).
* Defensive regex parsers (MoSPI CPI / MoSPI IIP / S&P Global PMI).
* FRED CSV parser (CPI + IIP).
* CCIL multi-tenor HTML parser (extension to the existing 10Y-only test).
* Validation guards (period range, plausible-value ranges).

HTTP is mocked with respx so tests don't hit the network.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from flowtracker.cpi_client import (
    CPIClient,
    CPIClientError,
    parse_fred_csv as parse_cpi_fred_csv,
    parse_mospi_release_text,
)
from flowtracker.iip_client import (
    IIPClient,
    parse_fred_csv as parse_iip_fred_csv,
    parse_mospi_iip_text,
)
from flowtracker.macro_client import MacroClient, _parse_ccil_tenor
from flowtracker.pmi_client import PMIClient, parse_pmi_release_text
from flowtracker.yield_curve_client import YieldCurveClient


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cpi_seed() -> dict:
    return {
        "_meta": {"description": "test"},
        "collections": [
            {"period": "2024-01", "cpi_index": 185.4, "yoy_pct": 5.10, "source": "FRED"},
            {"period": "2024-02", "cpi_index": 186.0, "yoy_pct": 5.09, "source": "FRED"},
            {"period": "2024-03", "cpi_index": 186.7, "yoy_pct": 4.85, "source": "FRED"},
        ],
    }


@pytest.fixture
def iip_seed() -> dict:
    return {
        "_meta": {"description": "test"},
        "collections": [
            {"period": "2024-01", "iip_index": 151.7, "yoy_pct": 4.2, "source": "FRED"},
            {"period": "2024-02", "iip_index": 143.5, "yoy_pct": 5.6, "source": "FRED"},
        ],
    }


@pytest.fixture
def pmi_seed() -> dict:
    return {
        "_meta": {"description": "test"},
        "collections": [
            {"period": "2024-01", "services_pmi": 61.8, "manufacturing_pmi": 56.5},
            {"period": "2024-02", "services_pmi": 60.6, "manufacturing_pmi": 56.9},
        ],
    }


@pytest.fixture
def yield_curve_seed() -> dict:
    return {
        "_meta": {"description": "test"},
        "snapshots": [
            {"date": "2024-12-31", "gsec_1y": 6.61, "gsec_5y": 6.78, "gsec_10y": 6.76, "gsec_30y": 6.98},
            {"date": "2025-03-31", "gsec_1y": 6.45, "gsec_5y": 6.62, "gsec_10y": 6.58, "gsec_30y": 6.90},
        ],
    }


# ---------------------------------------------------------------------------
# CPI client
# ---------------------------------------------------------------------------


class TestCPIClientSeed:
    def test_fetch_month_returns_seed_row(self, cpi_seed):
        with CPIClient(seed=cpi_seed) as client:
            row = client.fetch_month("2024-02")
        assert row is not None
        assert row.cpi_index == pytest.approx(186.0)
        assert row.yoy_pct == pytest.approx(5.09)

    def test_fetch_month_unknown_period_returns_none(self, cpi_seed):
        with CPIClient(seed=cpi_seed) as client:
            assert client.fetch_month("2026-01") is None

    def test_fetch_latest(self, cpi_seed):
        with CPIClient(seed=cpi_seed) as client:
            latest = client.fetch_latest()
        assert latest is not None
        assert latest.period == "2024-03"

    def test_fetch_backfill_filters_to_range(self, cpi_seed):
        with CPIClient(seed=cpi_seed) as client:
            rows = client.fetch_backfill("2024-01", "2024-02")
        assert [r.period for r in rows] == ["2024-01", "2024-02"]

    def test_known_periods_sorted(self, cpi_seed):
        with CPIClient(seed=cpi_seed) as client:
            assert client.known_periods == ["2024-01", "2024-02", "2024-03"]

    def test_invalid_period_rejected(self, cpi_seed):
        with CPIClient(seed=cpi_seed) as client:
            with pytest.raises(ValueError):
                client.fetch_month("not-a-period")

    def test_invalid_seed_rejected(self):
        with pytest.raises(Exception):
            CPIClient(seed={"collections": "not-a-list"})


class TestCPIMoSPIParser:
    def test_extracts_yoy_from_press_release(self):
        text = "All India CPI Combined inflation for April 2025 stood at 3.16 per cent."
        out = parse_mospi_release_text(text)
        assert out["yoy_pct"] == pytest.approx(3.16)

    def test_headline_inflation_form(self):
        text = "Headline CPI inflation at 4.83% in April 2024."
        out = parse_mospi_release_text(text)
        assert out["yoy_pct"] == pytest.approx(4.83)

    def test_extracts_index_level(self):
        text = "All India CPI (Combined) index for April 2025 is 194.50."
        out = parse_mospi_release_text(text)
        assert out["cpi_index"] == pytest.approx(194.50)

    def test_implausible_value_dropped(self):
        # 50% inflation never happens; parser must drop, not crash.
        text = "All India CPI inflation 50.0 per cent."
        out = parse_mospi_release_text(text)
        assert out["yoy_pct"] is None

    def test_empty_text_returns_all_none(self):
        out = parse_mospi_release_text("")
        assert out == {"cpi_index": None, "yoy_pct": None}


class TestCPIFREDCSVParser:
    def test_parses_fred_csv(self):
        csv = (
            "observation_date,INDCPIALLMINMEI\n"
            "2024-01-01,185.40\n"
            "2024-02-01,186.03\n"
            "2024-03-01,.\n"  # missing data
        )
        rows = parse_cpi_fred_csv(csv)
        periods = [r.period for r in rows]
        assert periods == ["2024-01", "2024-02"]
        assert rows[0].cpi_index == pytest.approx(185.4)
        assert rows[0].source == "FRED"

    def test_empty_csv_returns_empty(self):
        assert parse_cpi_fred_csv("") == []
        assert parse_cpi_fred_csv("header\n") == []


class TestCPIClientLiveFetch:
    def test_fetch_csv_url_returns_period_row(self, cpi_seed):
        csv = (
            "observation_date,value\n"
            "2025-04-01,194.50\n"
            "2025-05-01,195.10\n"
        )
        with respx.mock(assert_all_called=False) as mock:
            mock.get(url__regex=r"fred").mock(
                return_value=Response(
                    200, content=csv.encode(),
                    headers={"content-type": "text/csv"},
                ),
            )
            with CPIClient(seed=cpi_seed) as client:
                row = client.fetch_month("2025-04", source_url="https://fred.example.com/data.csv")
        assert row is not None
        assert row.cpi_index == pytest.approx(194.50)
        assert row.source == "FRED"
        assert row.source_url == "https://fred.example.com/data.csv"

    def test_http_error_returns_none(self, cpi_seed):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(url__regex=r"example").mock(return_value=Response(500))
            with CPIClient(seed=cpi_seed) as client:
                assert client.fetch_month(
                    "2025-04",
                    source_url="https://example.test/cpi.pdf",
                ) is None


# ---------------------------------------------------------------------------
# IIP client
# ---------------------------------------------------------------------------


class TestIIPClientSeed:
    def test_fetch_month_returns_seed_row(self, iip_seed):
        with IIPClient(seed=iip_seed) as client:
            row = client.fetch_month("2024-01")
        assert row is not None
        assert row.iip_index == pytest.approx(151.7)
        assert row.yoy_pct == pytest.approx(4.2)

    def test_fetch_latest(self, iip_seed):
        with IIPClient(seed=iip_seed) as client:
            latest = client.fetch_latest()
        assert latest.period == "2024-02"


class TestIIPMoSPIParser:
    def test_extracts_yoy(self):
        text = "IIP General grew 2.7 per cent in April 2025."
        out = parse_mospi_iip_text(text)
        assert out["yoy_pct"] == pytest.approx(2.7)

    def test_contraction_persists(self):
        text = "Industrial production fell -57.3 per cent in April 2020."
        out = parse_mospi_iip_text(text)
        assert out["yoy_pct"] == pytest.approx(-57.3)


class TestIIPFREDCSV:
    def test_parses_fred_iip_csv(self):
        csv = (
            "observation_date,INDPROINDMISMEI\n"
            "2024-01-01,151.7\n"
            "2024-02-01,143.5\n"
        )
        rows = parse_iip_fred_csv(csv)
        assert [r.period for r in rows] == ["2024-01", "2024-02"]
        assert rows[0].iip_index == pytest.approx(151.7)


# ---------------------------------------------------------------------------
# PMI client
# ---------------------------------------------------------------------------


class TestPMIClientSeed:
    def test_fetch_month_returns_seed_row(self, pmi_seed):
        with PMIClient(seed=pmi_seed) as client:
            row = client.fetch_month("2024-01")
        assert row is not None
        assert row.services_pmi == pytest.approx(61.8)
        assert row.manufacturing_pmi == pytest.approx(56.5)


class TestPMIParser:
    def test_extracts_services(self):
        text = (
            "The S&P Global India Services PMI Business Activity Index stood "
            "at 58.5 in March 2025."
        )
        out = parse_pmi_release_text(text)
        assert out["services_pmi"] == pytest.approx(58.5)

    def test_extracts_manufacturing(self):
        text = "Headline S&P Global India Manufacturing PMI rose to 58.1 in March 2025."
        out = parse_pmi_release_text(text)
        assert out["manufacturing_pmi"] == pytest.approx(58.1)

    def test_extracts_both_in_combined_release(self):
        text = (
            "S&P Global India Services PMI: 58.5. "
            "S&P Global India Manufacturing PMI: 58.1."
        )
        out = parse_pmi_release_text(text)
        assert out["services_pmi"] == pytest.approx(58.5)
        assert out["manufacturing_pmi"] == pytest.approx(58.1)

    def test_implausible_value_dropped(self):
        """A 95.0 PMI print never happens; parser must reject."""
        text = "India Manufacturing PMI 95.0 in some-month."
        out = parse_pmi_release_text(text)
        assert out["manufacturing_pmi"] is None

    def test_empty_text(self):
        assert parse_pmi_release_text("") == {
            "services_pmi": None, "manufacturing_pmi": None,
        }


# ---------------------------------------------------------------------------
# Yield-curve client (seed loader)
# ---------------------------------------------------------------------------


class TestYieldCurveClient:
    def test_fetch_all_ordered_ascending(self, yield_curve_seed):
        client = YieldCurveClient(seed=yield_curve_seed)
        snaps = client.fetch_all()
        assert [s.date for s in snaps] == ["2024-12-31", "2025-03-31"]

    def test_fetch_in_range(self, yield_curve_seed):
        client = YieldCurveClient(seed=yield_curve_seed)
        snaps = client.fetch_in_range("2025-01-01", "2025-12-31")
        assert [s.date for s in snaps] == ["2025-03-31"]

    def test_to_macro_snapshots_only_sets_yields(self, yield_curve_seed):
        client = YieldCurveClient(seed=yield_curve_seed)
        macros = client.to_macro_snapshots()
        m = macros[1]
        assert m.date == "2025-03-31"
        assert m.gsec_1y == pytest.approx(6.45)
        assert m.gsec_10y == pytest.approx(6.58)
        assert m.usd_inr is None  # FX deliberately blank
        assert m.brent_crude is None

    def test_slope_property(self, yield_curve_seed):
        client = YieldCurveClient(seed=yield_curve_seed)
        snaps = client.fetch_all()
        # 2025-03-31: 10Y=6.58, 1Y=6.45 -> +13bps
        assert snaps[1].slope_10y_minus_1y == pytest.approx(13.0)
        # 30Y=6.90, 10Y=6.58 -> +32bps
        assert snaps[1].slope_30y_minus_10y == pytest.approx(32.0)


# ---------------------------------------------------------------------------
# CCIL multi-tenor parser (extension of existing test_client_macro.py)
# ---------------------------------------------------------------------------


# Realistic CCIL HTML fragment with the four tenors we care about.
_CCIL_HTML = """
<table>
  <tr><td>2025-05-26</td><td>0Y-1Y</td><td>6.40% GS 2026</td><td>6.45</td></tr>
  <tr><td>2025-05-26</td><td>4Y-5Y</td><td>6.99% GS 2031</td><td>6.62</td></tr>
  <tr><td>2025-05-26</td><td>9Y-10Y</td><td>6.33% GS 2035</td><td>6.58</td></tr>
  <tr><td>2025-05-26</td><td>19Y-Above</td><td>7.30% GS 2053</td><td>6.90</td></tr>
</table>
"""


class TestCCILMultiTenorParser:
    def test_parses_each_tenor(self):
        # 0Y-1Y
        assert _parse_ccil_tenor(
            _CCIL_HTML,
            r"0\s*Y?\s*[-–]\s*1\s*Y",
            label="1y",
        ) == pytest.approx(6.45)
        # 4Y-5Y
        assert _parse_ccil_tenor(
            _CCIL_HTML,
            r"4\s*Y?\s*[-–]\s*5\s*Y",
            label="5y",
        ) == pytest.approx(6.62)
        # 9Y-10Y
        assert _parse_ccil_tenor(
            _CCIL_HTML,
            r"9\s*Y?\s*[-–]\s*10\s*Y",
            label="10y",
        ) == pytest.approx(6.58)
        # 19Y-Above
        assert _parse_ccil_tenor(
            _CCIL_HTML,
            r"19\s*Y\s*[-–]\s*Above",
            label="30y",
        ) == pytest.approx(6.90)

    def test_returns_none_for_missing_tenor(self):
        """A tenor pattern not present in the page returns None."""
        assert _parse_ccil_tenor(
            _CCIL_HTML,
            r"100\s*Y\s*[-–]\s*200\s*Y",
            label="bogus",
        ) is None

    def test_value_outside_band_dropped(self):
        """The 'security coupon' column at 0.05% must NOT be matched —
        it's outside the [3.0, 12.0] plausible-yield band."""
        bogus_html = (
            "<table><tr><td>9Y-10Y</td><td>0.05% GS 2035</td><td>0.10</td></tr></table>"
        )
        assert _parse_ccil_tenor(
            bogus_html,
            r"9\s*Y?\s*[-–]\s*10\s*Y",
            label="10y",
        ) is None

    def test_fetch_gsec_curve_returns_all_four_tenors(self):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(url__regex=r"ccilindia").mock(
                return_value=Response(200, text=_CCIL_HTML),
            )
            with MacroClient() as client:
                curve = client._fetch_gsec_curve()
        assert curve == {
            "1y": pytest.approx(6.45),
            "5y": pytest.approx(6.62),
            "10y": pytest.approx(6.58),
            "30y": pytest.approx(6.90),
        }

    def test_fetch_gsec_yield_legacy_wrapper_returns_10y(self):
        """The legacy single-tenor wrapper still works (used by cron)."""
        with respx.mock(assert_all_called=False) as mock:
            mock.get(url__regex=r"ccilindia").mock(
                return_value=Response(200, text=_CCIL_HTML),
            )
            with MacroClient() as client:
                value = client._fetch_gsec_yield()
        assert value == pytest.approx(6.58)

    def test_network_failure_returns_all_nones(self):
        with respx.mock(assert_all_called=False) as mock:
            mock.get(url__regex=r"ccilindia").mock(return_value=Response(500))
            with MacroClient() as client:
                curve = client._fetch_gsec_curve()
        assert curve == {"1y": None, "5y": None, "10y": None, "30y": None}
