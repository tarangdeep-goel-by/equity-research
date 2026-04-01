"""Integration tests: client → store pipeline with mocked HTTP.

Each test mocks the HTTP layer with respx, calls the client's fetch method,
stores the result in FlowStore, then queries and verifies correctness.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# NSE FII/DII → store
# ---------------------------------------------------------------------------


class TestNSEFiiDiiPipeline:
    """NSE FII/DII client → upsert_flows → verify in store."""

    def test_fetch_daily_and_store(self, store: FlowStore):
        with respx.mock:
            # Preflight cookie request
            respx.get(url__regex=r"nseindia\.com/reports").respond(200, text="OK")
            # API endpoint
            respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact").respond(
                200,
                json=[
                    {
                        "category": "FII/FPI *",
                        "date": "28-Mar-2026",
                        "buyValue": "12,000.00",
                        "sellValue": "13,500.00",
                        "netValue": "-1,500.00",
                    },
                    {
                        "category": "DII *",
                        "date": "28-Mar-2026",
                        "buyValue": "8,000.00",
                        "sellValue": "7,200.00",
                        "netValue": "800.00",
                    },
                ],
            )

            from flowtracker.client import NSEClient

            with NSEClient() as client:
                flows = client.fetch_daily()

        count = store.upsert_flows(flows)
        assert count == 2

        latest = store.get_latest()
        assert latest is not None
        assert latest.fii.net_value == pytest.approx(-1500.0)
        assert latest.dii.net_value == pytest.approx(800.0)
        assert latest.date == date(2026, 3, 28)

    def test_fii_category_normalized(self, store: FlowStore):
        """Verify 'FII/FPI *' normalizes to 'FII'."""
        with respx.mock:
            respx.get(url__regex=r"nseindia\.com/reports").respond(200, text="OK")
            respx.get(url__regex=r"nseindia\.com/api/fiidiiTradeReact").respond(
                200,
                json=[
                    {
                        "category": "FII/FPI *",
                        "date": "27-Mar-2026",
                        "buyValue": "10,000.00",
                        "sellValue": "11,000.00",
                        "netValue": "-1,000.00",
                    },
                    {
                        "category": "DII *",
                        "date": "27-Mar-2026",
                        "buyValue": "6,000.00",
                        "sellValue": "5,000.00",
                        "netValue": "1,000.00",
                    },
                ],
            )

            from flowtracker.client import NSEClient

            with NSEClient() as client:
                flows = client.fetch_daily()

        assert all(f.category in ("FII", "DII") for f in flows)


# ---------------------------------------------------------------------------
# Bhavcopy CSV → store
# ---------------------------------------------------------------------------


class TestBhavcopyPipeline:
    """Bhavcopy CSV client → upsert_daily_stock_data → verify in store."""

    _CSV = (
        " SYMBOL, SERIES, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE,"
        " PREV_CLOSE, TTL_TRD_QNTY, TURNOVER_LACS, DELIV_QTY, DELIV_PER \n"
        " SBIN, EQ, 815.00, 825.00, 810.00, 820.00,"
        " 818.00, 15000000, 12300.50, 9000000, 60.00 \n"
        " INFY, EQ, 1840.00, 1860.00, 1830.00, 1850.00,"
        " 1845.00, 8000000, 14800.00, 5000000, 62.50 \n"
        " RELIANCE, BE, 2500.00, 2520.00, 2480.00, 2510.00,"
        " 2505.00, 3000000, 7530.00, 2000000, 66.67 \n"
    )

    def test_fetch_and_store(self, store: FlowStore):
        target = date(2026, 3, 28)
        url_date = target.strftime("%d%m%Y")

        with respx.mock:
            respx.get(url__regex=rf"sec_bhavdata_full_{url_date}").respond(
                200, text=self._CSV,
            )

            from flowtracker.bhavcopy_client import BhavcopyClient

            with BhavcopyClient() as client:
                records = client.fetch_day(target)

        # Only EQ series should be parsed (RELIANCE is BE, should be skipped)
        assert len(records) == 2
        assert {r.symbol for r in records} == {"SBIN", "INFY"}

        store.upsert_daily_stock_data(records)

        delivery = store.get_stock_delivery("SBIN", days=30)
        assert len(delivery) >= 1
        assert delivery[0].close == pytest.approx(820.0)

    def test_404_returns_empty(self, store: FlowStore):
        """Holiday/weekend returns empty list, not an error."""
        target = date(2026, 3, 29)  # Sunday
        url_date = target.strftime("%d%m%Y")

        with respx.mock:
            respx.get(url__regex=rf"sec_bhavdata_full_{url_date}").respond(404)

            from flowtracker.bhavcopy_client import BhavcopyClient

            with BhavcopyClient() as client:
                records = client.fetch_day(target)

        assert records == []


# ---------------------------------------------------------------------------
# FMP DCF → store
# ---------------------------------------------------------------------------


class TestFMPDcfPipeline:
    """FMP DCF client → upsert_fmp_dcf → verify in store."""

    def _mock_fmp_env(self, tmp_path: Path, monkeypatch):
        """Create a fake fmp.env and patch _CONFIG_PATH."""
        env_file = tmp_path / "fmp.env"
        env_file.write_text("FMP_API_KEY=test_key_123\n")
        monkeypatch.setattr("flowtracker.fmp_client._CONFIG_PATH", env_file)

    def test_fetch_dcf_and_store(self, store: FlowStore, tmp_path: Path, monkeypatch):
        self._mock_fmp_env(tmp_path, monkeypatch)

        with respx.mock:
            respx.get(url__regex=r"financialmodelingprep\.com/api/v3/discounted-cash-flow").respond(
                200,
                json=[{"date": "2026-03-28", "dcf": 950.0, "Stock Price": 820.0}],
            )

            from flowtracker.fmp_client import FMPClient

            client = FMPClient()
            dcf = client.fetch_dcf("SBIN")

        assert dcf is not None
        assert dcf.dcf == pytest.approx(950.0)
        assert dcf.stock_price == pytest.approx(820.0)

        store.upsert_fmp_dcf([dcf])
        latest = store.get_fmp_dcf_latest("SBIN")
        assert latest is not None
        assert latest.dcf == pytest.approx(950.0)

    def test_fetch_key_metrics_and_store(self, store: FlowStore, tmp_path: Path, monkeypatch):
        self._mock_fmp_env(tmp_path, monkeypatch)

        with respx.mock:
            respx.get(url__regex=r"financialmodelingprep\.com/api/v3/key-metrics").respond(
                200,
                json=[{
                    "date": "2026-03-28",
                    "revenuePerShare": 200.0,
                    "netIncomePerShare": 70.0,
                    "operatingCashFlowPerShare": 85.0,
                    "freeCashFlowPerShare": 60.0,
                    "cashPerShare": 56.0,
                    "bookValuePerShare": 450.0,
                    "tangibleBookValuePerShare": 420.0,
                    "shareholdersEquityPerShare": 440.0,
                    "interestDebtPerShare": 220.0,
                    "marketCap": 732000.0,
                    "enterpriseValue": 805000.0,
                    "peRatio": 9.5,
                    "priceToSalesRatio": 1.5,
                    "pbRatio": 1.8,
                    "evToSales": 2.1,
                    "enterpriseValueOverEBITDA": 7.5,
                    "evToOperatingCashFlow": 9.5,
                    "evToFreeCashFlow": 13.4,
                    "earningsYield": 10.5,
                    "freeCashFlowYield": 7.3,
                    "debtToEquity": 0.4,
                    "debtToAssets": 0.25,
                    "dividendYield": 1.5,
                    "payoutRatio": 20.0,
                    "roe": 18.5,
                    "returnOnTangibleAssets": 1.2,
                    "roic": 14.0,
                    "netProfitMargin": 35.0,
                    "assetTurnover": 0.05,
                }],
            )

            from flowtracker.fmp_client import FMPClient

            client = FMPClient()
            metrics = client.fetch_key_metrics("SBIN")

        assert len(metrics) == 1
        assert metrics[0].pe_ratio == pytest.approx(9.5)

        store.upsert_fmp_key_metrics(metrics)

    def test_fetch_analyst_grades_and_store(self, store: FlowStore, tmp_path: Path, monkeypatch):
        self._mock_fmp_env(tmp_path, monkeypatch)

        with respx.mock:
            respx.get(url__regex=r"financialmodelingprep\.com/api/v3/grade").respond(
                200,
                json=[
                    {"date": "2026-03-15", "gradingCompany": "Morgan Stanley", "previousGrade": "Equal-Weight", "newGrade": "Overweight"},
                    {"date": "2026-02-20", "gradingCompany": "Goldman Sachs", "previousGrade": "Buy", "newGrade": "Conviction Buy"},
                ],
            )

            from flowtracker.fmp_client import FMPClient

            client = FMPClient()
            grades = client.fetch_analyst_grades("SBIN")

        assert len(grades) == 2
        assert grades[0].grading_company == "Morgan Stanley"

        store.upsert_fmp_analyst_grades(grades)
