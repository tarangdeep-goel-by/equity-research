"""WS-1 (Phase 3.5b): run-market context + hybrid resolution.

The LLM agent never differentiates market — market is resolved ONCE per run
(server-side) and tools route internally via a `_run_market` ContextVar. These
tests pin the foundation:

  * resolve_run_market() hybrid order (explicit flag → registry US row → NSE)
  * ResearchDataAPI(market=...) override on _market_of/_is_us
  * the _run_market ContextVar override (read by data_api + tools helpers)
  * India default stays NSE with no run context (regression)
  * refresh_us registers the symbol so later auto-resolution is reliable

Offline, temp-DB, no network/LLM.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.store import FlowStore


US_SYMBOL = "AAPL"
US_MARKET = "NASDAQ"


@pytest.fixture
def db(tmp_db: Path, monkeypatch) -> Path:
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    with FlowStore(db_path=tmp_db) as store:
        # India symbol with no US row (default-NSE path).
        store.upsert_symbol_registry("SBIN", "NSE", company_name="State Bank")
        # US symbol registered under NASDAQ.
        store.upsert_symbol_registry(
            US_SYMBOL, US_MARKET, company_name="Apple Inc.", cik="320193",
        )
    return tmp_db


# --------------------------------------------------------------------------- #
# resolve_run_market — hybrid order
# --------------------------------------------------------------------------- #
class TestResolveRunMarket:
    def test_explicit_us_flag_wins_even_when_unregistered(self, db):
        from flowtracker.research.data_api import resolve_run_market
        # Unregistered symbol + explicit us flag → defaults to NASDAQ.
        assert resolve_run_market("ZZZZ", "us") == "NASDAQ"

    def test_explicit_in_flag_forces_nse(self, db):
        from flowtracker.research.data_api import resolve_run_market
        # Even a registered US symbol forced to NSE when flag says india.
        assert resolve_run_market(US_SYMBOL, "in") == "NSE"

    def test_registry_us_row_resolves_without_flag(self, db):
        from flowtracker.research.data_api import resolve_run_market
        assert resolve_run_market(US_SYMBOL) == US_MARKET

    def test_default_nse_without_flag_or_us_row(self, db):
        from flowtracker.research.data_api import resolve_run_market
        assert resolve_run_market("SBIN") == "NSE"


# --------------------------------------------------------------------------- #
# ResearchDataAPI(market=...) override
# --------------------------------------------------------------------------- #
class TestApiMarketOverride:
    def test_market_override_forces_us(self, db):
        from flowtracker.research.data_api import ResearchDataAPI
        with ResearchDataAPI(market="NASDAQ") as api:
            # Any symbol resolves to the run market under an explicit override.
            assert api._is_us("ZZZZ") is True
            assert api._market_of("ZZZZ") == "NASDAQ"

    def test_no_override_uses_registry(self, db):
        from flowtracker.research.data_api import ResearchDataAPI
        with ResearchDataAPI() as api:
            assert api._is_us(US_SYMBOL) is True
            assert api._market_of(US_SYMBOL) == US_MARKET
            assert api._is_us("SBIN") is False
            assert api._market_of("SBIN") == "NSE"


# --------------------------------------------------------------------------- #
# _run_market ContextVar — read by data_api + tools helpers
# --------------------------------------------------------------------------- #
class TestRunMarketContextVar:
    def test_contextvar_override_in_data_api(self, db):
        from flowtracker.research.data_api import ResearchDataAPI, _run_market
        token = _run_market.set("NASDAQ")
        try:
            with ResearchDataAPI() as api:
                assert api._market_of("SBIN") == "NASDAQ"
        finally:
            _run_market.reset(token)
        # After reset, registry resolution returns.
        with ResearchDataAPI() as api:
            assert api._market_of("SBIN") == "NSE"

    def test_contextvar_read_by_tools_helpers(self, db):
        from flowtracker.research import tools as t
        from flowtracker.research.data_api import _run_market
        token = _run_market.set("NASDAQ")
        try:
            assert t._is_us_symbol("SBIN") is True
            assert t._market_of("SBIN") == "NASDAQ"
        finally:
            _run_market.reset(token)
        assert t._is_us_symbol("SBIN") is False


# --------------------------------------------------------------------------- #
# refresh_us registers the symbol
# --------------------------------------------------------------------------- #
class TestRefreshUsRegistersSymbol:
    def test_registers_symbol_even_when_sources_fail(self, tmp_db, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        import flowtracker.research.us_refresh as ur

        # CIK resolves; every live source raises (non-fatal, offline). The
        # registry upsert must still happen up front so later runs auto-resolve.
        monkeypatch.setattr(ur, "_resolve_symbol", lambda store, sym: ("320193", "NASDAQ"))

        def _boom(*a, **k):
            raise RuntimeError("offline test — no network")

        # Stub every network-bound source refresh_us reaches (imported lazily
        # inside the function, so patch them on their source modules).
        monkeypatch.setattr("flowtracker.edgar_client.EdgarClient", _boom)
        monkeypatch.setattr("flowtracker.edgar_ownership.EdgarOwnershipClient", _boom)
        monkeypatch.setattr("flowtracker.us_ingest.fetch_us_daily_prices", _boom)
        monkeypatch.setattr("flowtracker.us_ingest.fetch_us_valuation_snapshot", _boom)
        monkeypatch.setattr("flowtracker.us_ingest.fetch_us_consensus_estimates", _boom)

        with FlowStore(db_path=tmp_db) as store:
            ur.refresh_us("AAPL", store=store)
            entry = store.get_symbol_registry_entry("AAPL", "NASDAQ")
            assert entry is not None
            assert entry.get("cik") == "320193"
