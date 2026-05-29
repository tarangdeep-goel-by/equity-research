"""Tests for ResearchDataAPI US-stock routing (US add-on, Phase 3.5).

Market-bound read methods route to the ``us_*`` tables when the symbol is a
US listing (has a US row in ``symbol_registry``). India behavior is unchanged:
a symbol with no US registry row reads the India tables exactly as before.

Seeds a US symbol (AAPL / NASDAQ / Technology) into symbol_registry, inserts
rows into the us_* tables, and asserts the routed methods return them. The
India regression case uses the populated fixture store (SBIN/INFY).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


@pytest.fixture
def us_api(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI on a store that has BOTH India fixtures (SBIN/INFY)
    and a seeded US symbol (AAPL) with us_* rows."""
    store = populated_store
    # Seed US registry entry (market=NASDAQ, GICS-style sector)
    store.upsert_symbol_registry(
        "AAPL", "NASDAQ", company_name="Apple Inc.", sector="Technology",
        gics="Information Technology", cik="320193",
    )
    # us_annual_financials
    store.upsert_us_annual_financials([
        {"symbol": "AAPL", "fiscal_year": 2023, "revenue": 383285.0,
         "net_income": 96995.0, "eps": 6.13, "shares_outstanding": 15600.0},
        {"symbol": "AAPL", "fiscal_year": 2022, "revenue": 394328.0,
         "net_income": 99803.0, "eps": 6.11},
    ])
    # us_quarterly_financials
    store.upsert_us_quarterly_financials([
        {"symbol": "AAPL", "quarter_end": "2023-12-30", "fiscal_year": 2024,
         "fiscal_period": "Q1", "revenue": 119575.0, "net_income": 33916.0, "eps": 2.18},
    ])
    # us_valuation_snapshot
    store.upsert_us_valuation_snapshot([
        {"symbol": "AAPL", "date": "2024-01-02", "price": 185.64,
         "market_cap": 2900000.0, "pe_trailing": 30.2, "pe_forward": 27.5,
         "pb": 45.1, "beta": 1.28},
    ])
    # us_consensus_estimates
    store.upsert_us_consensus_estimates([
        {"symbol": "AAPL", "date": "2024-01-02", "target_mean": 200.0,
         "num_analysts": 40, "recommendation": "Buy", "forward_pe": 27.5,
         "forward_eps": 6.75},
    ])
    # us_insider_transactions
    store.upsert_us_insider_transactions([
        {"symbol": "AAPL", "transaction_date": "2023-11-15", "owner_name": "COOK TIMOTHY",
         "owner_title": "CEO", "transaction_code": "S", "shares": 511000.0,
         "price_per_share": 180.0, "value": 91980000.0, "is_officer": 1},
    ])
    # us_institutional_holdings
    store.upsert_us_institutional_holdings([
        {"symbol": "AAPL", "manager_cik": "1067983", "manager_name": "BERKSHIRE HATHAWAY",
         "quarter_end": "2023-12-31", "shares": 905560000.0, "value_usd": 174000000000.0},
    ])

    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI(store=store)
    yield a
    # store owned by populated_store fixture; don't double-close


# ---------------------------------------------------------------------------
# Market resolver
# ---------------------------------------------------------------------------

class TestMarketResolver:
    def test_us_symbol_resolves_to_nasdaq(self, us_api: ResearchDataAPI):
        assert us_api._market_of("AAPL") == "NASDAQ"
        assert us_api._is_us("AAPL") is True

    def test_india_symbol_defaults_to_nse(self, us_api: ResearchDataAPI):
        assert us_api._market_of("SBIN") == "NSE"
        assert us_api._is_us("SBIN") is False

    def test_unknown_symbol_defaults_to_nse(self, us_api: ResearchDataAPI):
        assert us_api._market_of("NONEXIST") == "NSE"
        assert us_api._is_us("NONEXIST") is False


# ---------------------------------------------------------------------------
# Routed reads — US symbol
# ---------------------------------------------------------------------------

class TestUsRouting:
    def test_annual_financials(self, us_api: ResearchDataAPI):
        rows = us_api.get_annual_financials("AAPL")
        assert isinstance(rows, list) and len(rows) == 2
        assert rows[0]["fiscal_year"] == 2023
        assert rows[0]["revenue"] == 383285.0

    def test_quarterly_results(self, us_api: ResearchDataAPI):
        rows = us_api.get_quarterly_results("AAPL")
        assert isinstance(rows, list) and len(rows) == 1
        assert rows[0]["quarter_end"] == "2023-12-30"
        assert rows[0]["revenue"] == 119575.0

    def test_valuation_snapshot(self, us_api: ResearchDataAPI):
        snap = us_api.get_valuation_snapshot("AAPL")
        assert isinstance(snap, dict) and snap
        assert snap["price"] == 185.64
        assert snap["pe_trailing"] == 30.2

    def test_consensus_estimate(self, us_api: ResearchDataAPI):
        est = us_api.get_consensus_estimate("AAPL")
        assert isinstance(est, dict) and est
        assert est["target_mean"] == 200.0
        assert est["num_analysts"] == 40

    def test_insider_transactions(self, us_api: ResearchDataAPI):
        rows = us_api.get_insider_transactions("AAPL")
        assert isinstance(rows, list) and len(rows) == 1
        assert rows[0]["owner_name"] == "COOK TIMOTHY"
        assert rows[0]["transaction_code"] == "S"

    def test_institutional_holdings(self, us_api: ResearchDataAPI):
        rows = us_api.get_institutional_holdings("AAPL")
        assert isinstance(rows, list) and len(rows) == 1
        assert rows[0]["manager_name"] == "BERKSHIRE HATHAWAY"
        assert rows[0]["shares"] == 905560000.0


# ---------------------------------------------------------------------------
# India-only methods return empty for US symbols (no fabrication)
# ---------------------------------------------------------------------------

class TestUsIndiaOnlyGraceful:
    def test_shareholding_empty(self, us_api: ResearchDataAPI):
        assert us_api.get_shareholding("AAPL") == []

    def test_promoter_pledge_empty(self, us_api: ResearchDataAPI):
        assert us_api.get_promoter_pledge("AAPL") == []

    def test_delivery_trend_empty(self, us_api: ResearchDataAPI):
        assert us_api.get_delivery_trend("AAPL") == []

    def test_institutional_holdings_india_empty(self, us_api: ResearchDataAPI):
        # India symbol has no us_institutional_holdings — graceful empty.
        assert us_api.get_institutional_holdings("SBIN") == []


# ---------------------------------------------------------------------------
# Sector detection via registry for US symbols
# ---------------------------------------------------------------------------

class TestUsSectorDetection:
    def test_industry_from_registry(self, us_api: ResearchDataAPI):
        # _get_industry should resolve the US GICS sector via the registry.
        industry = us_api._get_industry("AAPL")
        assert industry and industry != "Unknown"

    def test_sector_kpis_resolves(self, us_api: ResearchDataAPI):
        from flowtracker.research.sector_kpis import get_sector_for_industry
        industry = us_api._get_industry("AAPL")
        assert get_sector_for_industry(industry) == "it_services"


# ---------------------------------------------------------------------------
# India regression — symbols with no US registry row read India tables
# ---------------------------------------------------------------------------

class TestIndiaRegression:
    def test_annual_financials_india(self, us_api: ResearchDataAPI):
        rows = us_api.get_annual_financials("SBIN")
        assert isinstance(rows, list) and len(rows) > 0
        assert "revenue" in rows[0]

    def test_quarterly_results_india(self, us_api: ResearchDataAPI):
        rows = us_api.get_quarterly_results("SBIN")
        assert isinstance(rows, list) and len(rows) > 0
        assert "quarter_end" in rows[0]

    def test_insider_india(self, us_api: ResearchDataAPI):
        rows = us_api.get_insider_transactions("SBIN")
        assert isinstance(rows, list)

    def test_shareholding_india_nonempty(self, us_api: ResearchDataAPI):
        rows = us_api.get_shareholding("SBIN")
        assert isinstance(rows, list) and len(rows) > 0
