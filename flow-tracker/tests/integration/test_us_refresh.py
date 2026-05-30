"""Integration tests for research/us_refresh.refresh_us (US add-on, P3.4).

Every network client is MOCKED (EdgarClient, the us_ingest yfinance fetchers,
EdgarOwnershipClient) to return small canned rows — NO network is touched.
Persistence is verified by reading rows back from a temp-DB FlowStore (the
``store`` fixture). Mirrors the mocking style in tests/unit/test_us_ingest.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from flowtracker.research.us_refresh import refresh_us


@pytest.fixture(autouse=True)
def _stub_short_interest():
    """Default-stub the Nasdaq short-interest fetch to [] so no test in this
    module touches the network. The happy-path test overrides this with its own
    `with patch(...)` (which takes precedence inside its block)."""
    with patch("flowtracker.us_short_interest_client.fetch_us_short_interest",
               return_value=[]):
        yield


# --------------------------------------------------------------------------- #
# Canned rows (keyed for the us_* upserts)
# --------------------------------------------------------------------------- #

def _annual_rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "fiscal_year": 2024, "revenue": 391_035.0, "net_income": 93_736.0,
         "eps": 6.08, "shares_outstanding": 15_000_000_000},
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "fiscal_year": 2023, "revenue": 383_285.0, "net_income": 96_995.0,
         "eps": 6.13, "shares_outstanding": 15_500_000_000},
    ]


def _quarterly_rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "quarter_end": "2024-12-28", "fiscal_year": 2025, "fiscal_period": "Q1",
         "revenue": 124_300.0, "net_income": 36_330.0, "eps": 2.40},
    ]


def _price_rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "market": "NASDAQ", "date": "2025-05-28",
         "open": 205.0, "high": 210.0, "low": 204.0, "close": 208.0,
         "volume": 45_000_000, "adj_close": 207.5},
    ]


def _valuation_row() -> dict:
    return {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
            "date": "2025-05-29", "price": 207.5, "market_cap": 3_100_000.0,
            "pe_trailing": 32.0, "roe": 150.0}


def _consensus_row() -> dict:
    return {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
            "date": "2025-05-29", "target_mean": 240.0, "num_analysts": 40,
            "recommendation": "buy"}


def _insider_rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "filing_date": "2025-05-20", "transaction_date": "2025-05-18",
         "owner_name": "COOK TIMOTHY D", "owner_title": "CEO",
         "transaction_code": "S", "shares": 100_000.0, "price_per_share": 205.0,
         "value": 20_500_000.0, "shares_owned_after": 3_000_000.0,
         "is_director": 1, "is_officer": 1},
    ]


def _13f_rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "cusip": "037833100", "manager_name": "BERKSHIRE HATHAWAY",
         "manager_cik": "1067983", "quarter_end": "2025-03-31",
         "shares": 300_000_000.0, "value_usd": 60_000.0,
         "investment_discretion": "SOLE", "put_call": ""},
    ]


def _short_interest_rows() -> list[dict]:
    return [
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "settlement_date": "2026-05-15", "short_interest": 138_782_718.0,
         "avg_daily_volume": 50_565_316.0, "days_to_cover": 2.74},
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "settlement_date": "2026-04-30", "short_interest": 134_675_274.0,
         "avg_daily_volume": 45_944_025.0, "days_to_cover": 2.93},
    ]


# --------------------------------------------------------------------------- #
# Patch helpers
# --------------------------------------------------------------------------- #

def _edgar_client_mock() -> MagicMock:
    """A context-manager EdgarClient whose facts → canned annual/quarterly rows."""
    inst = MagicMock()
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = False
    inst.cik_for.return_value = "0000320193"
    inst.fetch_company_facts.return_value = {"facts": {"us-gaap": {}}}
    inst.normalize_annual.return_value = _annual_rows()
    inst.normalize_quarterly.return_value = _quarterly_rows()
    return inst


def _ownership_client_mock() -> MagicMock:
    inst = MagicMock()
    inst.__enter__.return_value = inst
    inst.__exit__.return_value = False
    inst.fetch_insider_transactions.return_value = _insider_rows()
    inst.fetch_13f_for_manager.return_value = _13f_rows()
    return inst


def _seed_registry(store) -> None:
    store.upsert_symbol_registry("AAPL", "NASDAQ", cik="320193", sector="Technology")


# --------------------------------------------------------------------------- #
# Happy path — every source succeeds, rows persist
# --------------------------------------------------------------------------- #

def test_refresh_us_pulls_every_source_and_persists(store):
    _seed_registry(store)
    edgar = _edgar_client_mock()
    ownership = _ownership_client_mock()

    with patch("flowtracker.edgar_client.EdgarClient", return_value=edgar), \
         patch("flowtracker.edgar_ownership.EdgarOwnershipClient", return_value=ownership), \
         patch("flowtracker.fund_client.FundClient._info", return_value={"sector": "Technology"}), \
         patch("flowtracker.us_ingest.fetch_us_daily_prices", return_value=_price_rows()), \
         patch("flowtracker.us_ingest.fetch_us_valuation_snapshot", return_value=_valuation_row()), \
         patch("flowtracker.us_ingest.fetch_us_consensus_estimates", return_value=_consensus_row()), \
         patch("flowtracker.us_short_interest_client.fetch_us_short_interest", return_value=_short_interest_rows()):
        summary = refresh_us("AAPL", store=store)

    # summary dict carries the expected source keys
    assert set(summary) == {
        "annual_financials", "quarterly_financials", "daily_prices",
        "valuation_snapshot", "consensus_estimates", "insider_transactions",
        "institutional_13f", "registry_sector", "company_snapshot",
        "short_interest",
    }
    assert summary["annual_financials"] == 2
    assert summary["quarterly_financials"] == 1
    assert summary["daily_prices"] == 1
    assert summary["valuation_snapshot"] == 1
    assert summary["consensus_estimates"] == 1
    assert summary["insider_transactions"] == 1
    # 13F skipped by default (manager-indexed)
    assert summary["institutional_13f"] == 0
    # denormalized snapshot built from the valuation + annual rows just fetched
    assert summary["company_snapshot"] == 1
    # short interest persisted (2 settlement dates)
    assert summary["short_interest"] == 2
    assert len(store.get_us_short_interest("AAPL")) == 2
    snap = store.get_us_company_snapshot("AAPL", "NASDAQ")
    assert snap is not None and snap["currency"] == "USD"

    # each source called once with the resolved ticker
    edgar.fetch_company_facts.assert_called_once()
    ownership.fetch_insider_transactions.assert_called_once()
    ownership.fetch_13f_for_manager.assert_not_called()

    # rows actually landed in every us_* table read back from the temp DB
    assert len(store.get_us_annual_financials("AAPL")) == 2
    assert len(store.get_us_quarterly_financials("AAPL")) == 1
    assert len(store.get_us_daily_prices("AAPL")) == 1
    assert len(store.get_us_valuation_snapshot("AAPL")) == 1
    assert len(store.get_us_consensus_estimates("AAPL")) == 1
    assert len(store.get_us_insider_transactions("AAPL")) == 1
    # no 13F rows since it was skipped
    assert store.get_us_institutional_holdings("AAPL") == []


# --------------------------------------------------------------------------- #
# A failing source is reported as skip WITHOUT aborting the rest
# --------------------------------------------------------------------------- #

def test_refresh_us_failing_source_is_isolated(store):
    _seed_registry(store)
    edgar = _edgar_client_mock()
    ownership = _ownership_client_mock()

    # Prices fetch raises — must not stop the other sources from persisting.
    with patch("flowtracker.edgar_client.EdgarClient", return_value=edgar), \
         patch("flowtracker.edgar_ownership.EdgarOwnershipClient", return_value=ownership), \
         patch("flowtracker.fund_client.FundClient._info", return_value={"sector": "Technology"}), \
         patch("flowtracker.us_ingest.fetch_us_daily_prices", side_effect=RuntimeError("yf down")), \
         patch("flowtracker.us_ingest.fetch_us_valuation_snapshot", return_value=_valuation_row()), \
         patch("flowtracker.us_ingest.fetch_us_consensus_estimates", return_value=_consensus_row()):
        summary = refresh_us("AAPL", store=store)

    # failing source reported as skip (count 0), key still present
    assert summary["daily_prices"] == 0
    assert store.get_us_daily_prices("AAPL") == []

    # every other source still ran + persisted
    assert summary["annual_financials"] == 2
    assert summary["valuation_snapshot"] == 1
    assert summary["consensus_estimates"] == 1
    assert summary["insider_transactions"] == 1
    assert len(store.get_us_annual_financials("AAPL")) == 2
    assert len(store.get_us_valuation_snapshot("AAPL")) == 1
    assert len(store.get_us_insider_transactions("AAPL")) == 1


# --------------------------------------------------------------------------- #
# Unregistered symbol → CIK resolved live via EdgarClient.cik_for
# --------------------------------------------------------------------------- #

def test_refresh_us_resolves_cik_when_unregistered(store):
    # No registry seed — symbol must be resolved via EdgarClient.cik_for.
    edgar = _edgar_client_mock()
    ownership = _ownership_client_mock()

    with patch("flowtracker.edgar_client.EdgarClient", return_value=edgar), \
         patch("flowtracker.edgar_ownership.EdgarOwnershipClient", return_value=ownership), \
         patch("flowtracker.fund_client.FundClient._info", return_value={"sector": "Technology"}), \
         patch("flowtracker.us_ingest.fetch_us_daily_prices", return_value=_price_rows()), \
         patch("flowtracker.us_ingest.fetch_us_valuation_snapshot", return_value=_valuation_row()), \
         patch("flowtracker.us_ingest.fetch_us_consensus_estimates", return_value=_consensus_row()):
        summary = refresh_us("AAPL", store=store)

    edgar.cik_for.assert_called_with("AAPL")
    assert summary["annual_financials"] == 2
    assert len(store.get_us_annual_financials("AAPL")) == 2


# --------------------------------------------------------------------------- #
# 13F pulled when explicit manager CIKs are provided
# --------------------------------------------------------------------------- #

def test_refresh_us_pulls_13f_with_manager_ciks(store):
    _seed_registry(store)
    edgar = _edgar_client_mock()
    ownership = _ownership_client_mock()

    with patch("flowtracker.edgar_client.EdgarClient", return_value=edgar), \
         patch("flowtracker.edgar_ownership.EdgarOwnershipClient", return_value=ownership), \
         patch("flowtracker.fund_client.FundClient._info", return_value={"sector": "Technology"}), \
         patch("flowtracker.us_ingest.fetch_us_daily_prices", return_value=_price_rows()), \
         patch("flowtracker.us_ingest.fetch_us_valuation_snapshot", return_value=_valuation_row()), \
         patch("flowtracker.us_ingest.fetch_us_consensus_estimates", return_value=_consensus_row()):
        summary = refresh_us("AAPL", store=store, manager_ciks=["1067983"])

    ownership.fetch_13f_for_manager.assert_called_once()
    assert summary["institutional_13f"] == 1
    assert len(store.get_us_institutional_holdings("AAPL")) == 1


# --------------------------------------------------------------------------- #
# Bug 4: refresh_us captures the yfinance sector and persists it on the
# symbol_registry so industry resolves (not "Unknown") downstream.
# --------------------------------------------------------------------------- #

def test_refresh_us_sets_registry_sector(store):
    """yfinance sector → symbol_registry.sector/gics, COALESCE-safe, non-fatal."""
    _seed_registry(store)  # sector pre-seeded; ensure refresh keeps it populated
    edgar = _edgar_client_mock()
    ownership = _ownership_client_mock()

    with patch("flowtracker.edgar_client.EdgarClient", return_value=edgar), \
         patch("flowtracker.edgar_ownership.EdgarOwnershipClient", return_value=ownership), \
         patch("flowtracker.fund_client.FundClient._info", return_value={"sector": "Technology"}), \
         patch("flowtracker.us_ingest.fetch_us_daily_prices", return_value=_price_rows()), \
         patch("flowtracker.us_ingest.fetch_us_valuation_snapshot", return_value=_valuation_row()), \
         patch("flowtracker.us_ingest.fetch_us_consensus_estimates", return_value=_consensus_row()):
        summary = refresh_us("AAPL", store=store)

    assert summary["registry_sector"] == 1
    entry = store.get_symbol_registry_entry("AAPL", "NASDAQ")
    assert entry["sector"] == "Technology"
    assert entry["gics"] == "Technology"

    # Downstream: get_company_info maps the GICS sector to a sector_kpis
    # industry string (Technology → IT - Software), not "Unknown".
    from flowtracker.research.data_api import ResearchDataAPI

    api = ResearchDataAPI(store=store)
    assert api.get_company_info("AAPL")["industry"] == "IT - Software"


def test_refresh_us_sector_pull_non_fatal(store):
    """A failing yfinance sector pull is reported as skip, never aborts the run."""
    _seed_registry(store)
    edgar = _edgar_client_mock()
    ownership = _ownership_client_mock()

    with patch("flowtracker.edgar_client.EdgarClient", return_value=edgar), \
         patch("flowtracker.edgar_ownership.EdgarOwnershipClient", return_value=ownership), \
         patch("flowtracker.fund_client.FundClient._info", side_effect=RuntimeError("yf down")), \
         patch("flowtracker.us_ingest.fetch_us_daily_prices", return_value=_price_rows()), \
         patch("flowtracker.us_ingest.fetch_us_valuation_snapshot", return_value=_valuation_row()), \
         patch("flowtracker.us_ingest.fetch_us_consensus_estimates", return_value=_consensus_row()):
        summary = refresh_us("AAPL", store=store)

    assert summary["registry_sector"] == 0
    # other sources still persisted
    assert summary["annual_financials"] == 2
    assert len(store.get_us_annual_financials("AAPL")) == 2
