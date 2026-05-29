"""Integration tests for the P3.6 consumption layer (US add-on).

Offline, temp-DB FlowStore, NO LLM / agent / network. Verifies:

1. Routed MCP tools (get_fundamentals, get_valuation, get_ownership insider,
   get_institutional_ownership) serve US data for a US-seeded symbol.
2. India-only MCP tools / sections (FII-DII flows, promoter pledge, MF holdings,
   delivery, F&O positioning) return an EXPLICIT not-applicable response for the
   US symbol — and STILL return normal data for an India symbol (regression).
3. The new get_institutional_ownership tool returns 13F data for US and an
   explicit n/a for an India (NSE) symbol.
4. eval_matrix_us.yaml parses and carries the expected tickers + agents.

MCP tools are plain async functions returning a {"content":[{"text": <json>}]}
envelope — we decode content[0]["text"] and assert on the payload.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml

from flowtracker.research import tools as t
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore
from tests.fixtures.factories import populate_all

US_SYMBOL = "AAPL"
US_MARKET = "NASDAQ"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _seed_us(store: FlowStore) -> None:
    """Seed a US symbol into symbol_registry + the us_* tables."""
    store.upsert_symbol_registry(
        US_SYMBOL, US_MARKET, company_name="Apple Inc.",
        sector="Technology", gics="Technology", cik="320193",
    )
    store.upsert_us_annual_financials([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "fiscal_year": 2024, "revenue": 391_035.0, "net_income": 93_736.0,
         "eps": 6.08, "shares_outstanding": 15_000_000_000},
    ])
    store.upsert_us_quarterly_financials([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "quarter_end": "2024-12-28", "fiscal_year": 2025, "fiscal_period": "Q1",
         "revenue": 124_300.0, "net_income": 36_330.0, "eps": 2.40},
    ])
    store.upsert_us_valuation_snapshot([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "date": "2025-05-29", "price": 207.5, "market_cap": 3_100_000.0,
         "pe_trailing": 32.0, "roe": 150.0},
    ])
    store.upsert_us_insider_transactions([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "filing_date": "2025-05-20", "transaction_date": "2025-05-18",
         "owner_name": "COOK TIMOTHY D", "owner_title": "CEO",
         "transaction_code": "S", "shares": 100_000.0, "price_per_share": 205.0,
         "value": 20_500_000.0, "shares_owned_after": 3_000_000.0,
         "is_director": 1, "is_officer": 1},
    ])
    store.upsert_us_institutional_holdings([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "cusip": "037833100", "manager_name": "VANGUARD GROUP INC",
         "manager_cik": "102909", "quarter_end": "2025-03-31",
         "shares": 1_300_000_000.0, "value_usd": 270_000.0},
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "cusip": "037833100", "manager_name": "BLACKROCK INC",
         "manager_cik": "1364742", "quarter_end": "2025-03-31",
         "shares": 1_050_000_000.0, "value_usd": 218_000.0},
    ])


@pytest.fixture
def db(tmp_db: Path, monkeypatch) -> Path:
    """Temp DB seeded with US (AAPL) + India (SBIN/INFY) data, env-wired so
    every ResearchDataAPI() the tools construct binds to it."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    with FlowStore(db_path=tmp_db) as store:
        populate_all(store)  # India regression data (SBIN, INFY)
        _seed_us(store)
    return tmp_db


def _payload(result: dict) -> dict | list:
    """Decode an MCP tool envelope's JSON text payload."""
    return json.loads(result["content"][0]["text"])


def _call(tool_obj, args: dict):
    """Invoke an MCP @tool's async handler and return the decoded payload."""
    result = asyncio.run(tool_obj.handler(args))
    return _payload(result)


# --------------------------------------------------------------------------- #
# 1. Routed tools serve US data
# --------------------------------------------------------------------------- #


class TestRoutedToolsServeUS:
    def test_market_resolver_sees_us(self, db):
        with ResearchDataAPI() as api:
            assert api._is_us(US_SYMBOL) is True
            assert api._market_of(US_SYMBOL) == US_MARKET
            assert api._is_us("SBIN") is False

    def test_fundamentals_routes_us(self, db):
        payload = _call(t.get_fundamentals, {"symbol": US_SYMBOL, "section": "annual_financials"})
        rows = payload["annual_financials"] if isinstance(payload, dict) and "annual_financials" in payload else payload
        assert rows, "expected US annual financials rows"
        blob = json.dumps(rows)
        assert "391035" in blob or "391035.0" in blob

    def test_valuation_routes_us(self, db):
        payload = _call(t.get_valuation, {"symbol": US_SYMBOL, "section": "snapshot"})
        assert "32.0" in json.dumps(payload) or "32" in json.dumps(payload)

    def test_ownership_insider_routes_us(self, db):
        payload = _call(t.get_ownership, {"symbol": US_SYMBOL, "section": "insider"})
        assert "COOK TIMOTHY D" in json.dumps(payload)

    def test_institutional_ownership_us(self, db):
        payload = _call(t.get_institutional_ownership, {"symbol": US_SYMBOL})
        assert payload["symbol"] == US_SYMBOL
        names = json.dumps(payload["holdings"])
        assert "VANGUARD GROUP INC" in names and "BLACKROCK INC" in names


# --------------------------------------------------------------------------- #
# 2. India-only tools degrade for US, still serve India (regression)
# --------------------------------------------------------------------------- #


def _is_not_applicable(payload) -> bool:
    if isinstance(payload, dict):
        if payload.get("status") == "not_applicable":
            return True
        meta = payload.get("_meta")
        if isinstance(meta, dict) and meta.get("status") == "not_applicable":
            return True
    return False


class TestIndiaOnlyDegradesForUS:
    def test_promoter_pledge_na_for_us(self, db):
        payload = _call(t.get_ownership, {"symbol": US_SYMBOL, "section": "promoter_pledge"})
        assert _is_not_applicable(payload)

    def test_mf_holdings_na_for_us(self, db):
        payload = _call(t.get_ownership, {"symbol": US_SYMBOL, "section": "mf_holdings"})
        assert _is_not_applicable(payload)

    def test_delivery_na_for_us(self, db):
        payload = _call(t.get_market_context, {"symbol": US_SYMBOL, "section": "delivery"})
        assert _is_not_applicable(payload)

    def test_fii_dii_flows_na_for_us(self, db):
        payload = _call(t.get_market_context, {"symbol": US_SYMBOL, "section": "fii_dii_flows"})
        assert _is_not_applicable(payload)

    def test_fno_positioning_na_for_us(self, db):
        payload = _call(t.get_fno_positioning, {"symbol": US_SYMBOL})
        assert _is_not_applicable(payload)

    def test_institutional_ownership_na_for_india(self, db):
        payload = _call(t.get_institutional_ownership, {"symbol": "SBIN"})
        assert _is_not_applicable(payload)
        assert payload["market"] == "NSE"


class TestIndiaStillWorks:
    """Regression: India symbols keep returning real data, not the US marker."""

    def test_promoter_pledge_india(self, db):
        payload = _call(t.get_ownership, {"symbol": "SBIN", "section": "promoter_pledge"})
        assert not _is_not_applicable(payload)

    def test_delivery_india(self, db):
        payload = _call(t.get_market_context, {"symbol": "SBIN", "section": "delivery"})
        assert not _is_not_applicable(payload)
        assert payload, "expected India delivery rows"

    def test_fii_dii_flows_india(self, db):
        # Market-wide series — not symbol-bound, must never carry the US marker.
        payload = _call(t.get_market_context, {"symbol": "SBIN", "section": "fii_dii_flows"})
        assert not _is_not_applicable(payload)

    def test_ownership_all_india_unaffected(self, db):
        payload = _call(t.get_ownership, {"symbol": "SBIN", "section": "all"})
        # India 'all' keeps the real India sections (no not-applicable markers).
        assert not _is_not_applicable(payload.get("promoter_pledge"))
        assert not _is_not_applicable(payload.get("mf_holdings"))


# --------------------------------------------------------------------------- #
# 3. eval_matrix_us.yaml scaffold parses
# --------------------------------------------------------------------------- #


class TestUSEvalMatrixScaffold:
    def test_yaml_parses_and_has_expected_shape(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "flowtracker" / "research" / "autoeval" / "eval_matrix_us.yaml"
        )
        assert path.exists(), f"missing scaffold: {path}"
        data = yaml.safe_load(path.read_text())

        # Agents: standard specialist list (fno omitted — n/a for US).
        agents = set(data["agents"])
        assert {"business", "financials", "ownership", "valuation",
                "risk", "technical", "sector"}.issubset(agents)
        assert "fno_positioning" not in agents

        # Tickers: the US validation universe.
        tickers = {cell["stock"] for cell in data["sectors"].values()}
        assert {"AAPL", "MSFT", "NVDA", "JPM", "XOM", "UNH"}.issubset(tickers)

        # Every sector cell mirrors the India format: stock/type/why.
        for cell in data["sectors"].values():
            assert {"stock", "type", "why"}.issubset(cell.keys())


# --------------------------------------------------------------------------- #
# 4. WS-5 graceful degradation — genuinely-absent-for-US data returns an
#    explicit not_applicable envelope; India keeps returning real data.
# --------------------------------------------------------------------------- #


class TestWS5DegradesForUS:
    """Representative INCLUDE-list tools return not_applicable for a US symbol."""

    def test_yahoo_peers_na_for_us(self, db):
        assert _is_not_applicable(_call(t.get_yahoo_peers, {"symbol": US_SYMBOL}))

    def test_screener_peers_na_for_us(self, db):
        assert _is_not_applicable(_call(t.get_screener_peers, {"symbol": US_SYMBOL}))

    def test_peer_sector_na_for_us(self, db):
        # Whole-tool guard: any section degrades for US.
        assert _is_not_applicable(
            _call(t.get_peer_sector, {"symbol": US_SYMBOL, "section": "peer_table"})
        )

    def test_data_quality_flags_na_for_us(self, db):
        assert _is_not_applicable(_call(t.get_data_quality_flags, {"symbol": US_SYMBOL}))

    def test_chart_data_na_for_us(self, db):
        assert _is_not_applicable(
            _call(t.get_chart_data, {"symbol": US_SYMBOL, "chart_type": "price"})
        )

    def test_annual_report_na_for_us(self, db):
        assert _is_not_applicable(_call(t.get_annual_report, {"symbol": US_SYMBOL}))

    def test_historical_analogs_na_for_us(self, db):
        assert _is_not_applicable(_call(t.get_historical_analogs, {"symbol": US_SYMBOL}))

    def test_company_context_documents_na_for_us(self, db):
        assert _is_not_applicable(
            _call(t.get_company_context, {"symbol": US_SYMBOL, "section": "filings"})
        )

    def test_company_context_info_still_routed_for_us(self, db):
        # info/profile must STAY routed for US (now reads symbol_registry).
        payload = _call(t.get_company_context, {"symbol": US_SYMBOL, "section": "info"})
        assert not _is_not_applicable(payload)
        assert "Apple" in json.dumps(payload)

    def test_estimates_surprises_na_for_us(self, db):
        assert _is_not_applicable(
            _call(t.get_estimates, {"symbol": US_SYMBOL, "section": "surprises"})
        )

    def test_estimates_consensus_still_routed_for_us(self, db):
        # consensus is EXCLUDE-list — must NOT be degraded for US.
        payload = _call(t.get_estimates, {"symbol": US_SYMBOL, "section": "consensus"})
        assert not _is_not_applicable(payload)

    def test_events_dividends_na_for_us(self, db):
        assert _is_not_applicable(
            _call(t.get_events_actions, {"symbol": US_SYMBOL, "section": "dividends"})
        )

    def test_macro_tools_na_for_us_run(self, db):
        # Macro tools read the run-market ContextVar (no symbol arg).
        from flowtracker.research.data_api import _run_market
        token = _run_market.set(US_MARKET)
        try:
            assert _is_not_applicable(_call(t.get_macro_catalog, {}))
            assert _is_not_applicable(
                _call(t.get_macro_anchor, {"doc_type": "economic_survey"})
            )
            assert _is_not_applicable(_call(t.get_macro_indicators, {}))
            assert _is_not_applicable(_call(t.get_fii_derivative_flow, {}))
        finally:
            _run_market.reset(token)


class TestWS5IndiaStillWorks:
    """Regression: India symbols keep returning real (non-degraded) data."""

    def test_peer_sector_india(self, db):
        payload = _call(t.get_peer_sector, {"symbol": "SBIN", "section": "peer_table"})
        assert not _is_not_applicable(payload)

    def test_company_context_filings_india(self, db):
        payload = _call(t.get_company_context, {"symbol": "SBIN", "section": "filings"})
        assert not _is_not_applicable(payload)

    def test_estimates_surprises_india(self, db):
        payload = _call(t.get_estimates, {"symbol": "SBIN", "section": "surprises"})
        assert not _is_not_applicable(payload)

    def test_events_dividends_india(self, db):
        payload = _call(t.get_events_actions, {"symbol": "SBIN", "section": "dividends"})
        assert not _is_not_applicable(payload)

    def test_data_quality_flags_india(self, db):
        payload = _call(t.get_data_quality_flags, {"symbol": "SBIN"})
        assert not _is_not_applicable(payload)

    def test_macro_tools_india_run(self, db):
        # No run-market set (India default) → macro tools return real data.
        assert not _is_not_applicable(_call(t.get_macro_catalog, {}))
        assert not _is_not_applicable(_call(t.get_macro_indicators, {}))
        assert not _is_not_applicable(_call(t.get_fii_derivative_flow, {}))
