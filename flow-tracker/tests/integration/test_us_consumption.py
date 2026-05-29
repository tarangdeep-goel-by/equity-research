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
    # 5 fiscal years of full-column AAPL-like annuals (USD millions) so the
    # multi-year forensic methods (Piotroski, Altman, incremental ROCE,
    # operating leverage, projections) compute. AAPL reports total_equity but
    # not the equity_capital/reserves split — the WS-3 adapter reconciles it.
    _ANNUALS = [
        (2020, 274_515.0, 57_411.0, 3.28, 80_674.0, 73_365.0, 66_288.0, 67_091.0,
         9_680.0, 11_056.0, 323_888.0, 65_339.0, 112_436.0, 38_016.0, 36_766.0,
         16_120.0, 4_061.0, 105_392.0, -4_289.0, -86_820.0, 18_752.0, 6_829.0, 19_916.0),
        (2021, 365_817.0, 94_680.0, 5.61, 104_038.0, 92_953.0, 108_949.0, 109_207.0,
         14_527.0, 11_284.0, 351_002.0, 63_090.0, 124_719.0, 34_940.0, 39_440.0,
         26_278.0, 6_580.0, 125_481.0, -14_545.0, -93_353.0, 21_914.0, 7_906.0, 21_973.0),
        (2022, 394_328.0, 99_803.0, 6.11, 122_151.0, 111_443.0, 119_437.0, 119_103.0,
         19_300.0, 11_104.0, 352_755.0, 50_672.0, 120_069.0, 23_646.0, 42_117.0,
         28_184.0, 4_946.0, 153_982.0, -22_354.0, -110_749.0, 26_251.0, 9_038.0, 25_094.0),
        (2023, 383_285.0, 96_995.0, 6.13, 110_543.0, 99_584.0, 114_301.0, 113_736.0,
         16_741.0, 11_519.0, 352_583.0, 62_146.0, 111_088.0, 29_965.0, 43_715.0,
         29_508.0, 6_331.0, 145_308.0, 3_705.0, -108_488.0, 29_915.0, 10_833.0, 24_932.0),
        (2024, 391_035.0, 93_736.0, 6.08, 118_254.0, 108_807.0, 123_216.0, 123_485.0,
         29_749.0, 11_445.0, 364_980.0, 56_950.0, 106_629.0, 29_943.0, 45_680.0,
         33_410.0, 7_286.0, 176_392.0, 2_935.0, -121_983.0, 31_370.0, 11_688.0, 26_097.0),
    ]
    store.upsert_us_annual_financials([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "fiscal_year": fy, "fiscal_year_end": f"{fy}-09-28",
         "revenue": rev, "net_income": ni, "eps": eps,
         "operating_cash_flow": ocf, "free_cash_flow": fcf,
         "operating_profit": op, "profit_before_tax": pbt, "tax": tax,
         "depreciation": depr, "interest": 0.0,
         "total_assets": ta, "total_equity": te, "total_debt": td,
         "total_cash": tc, "cash_and_bank": tc, "net_block": nb,
         "receivables": recv, "inventory": inv, "other_liabilities": ol,
         "borrowings": td, "cwip": 0.0,
         "num_shares": 15_000_000_000.0 + (2024 - fy) * 150_000_000.0,
         "shares_outstanding": 15_000_000_000.0 + (2024 - fy) * 150_000_000.0,
         "cfi": cfi, "cff": cff,
         "rnd_expense": rnd, "stock_based_comp": sbc, "sga": sga}
        for (fy, rev, ni, eps, ocf, fcf, op, pbt, tax, depr, ta, te, td, tc,
             nb, recv, inv, ol, cfi, cff, rnd, sbc, sga) in _ANNUALS
    ])
    store.upsert_us_quarterly_financials([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "quarter_end": qe, "fiscal_year": fy, "fiscal_period": fp,
         "revenue": rev, "net_income": ni, "eps": eps}
        for (qe, fy, fp, rev, ni, eps) in [
            ("2024-12-28", 2025, "Q1", 124_300.0, 36_330.0, 2.40),
            ("2024-09-28", 2024, "Q4", 94_930.0, 14_736.0, 0.97),
            ("2024-06-29", 2024, "Q3", 85_777.0, 21_448.0, 1.40),
            ("2024-03-30", 2024, "Q2", 90_753.0, 23_636.0, 1.53),
        ]
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
    store.upsert_us_consensus_estimates([
        {"symbol": US_SYMBOL, "market": US_MARKET, "currency": "USD",
         "date": "2025-05-29", "target_mean": 230.0, "target_high": 300.0,
         "target_low": 170.0, "num_analysts": 40, "eps_next_year": 7.50},
    ])
    # ~60 daily bars so technicals (MACD/BB/ADX need 30+) + price-perf + WACC
    # beta have something to read (WS-4).
    rows = []
    base = 180.0
    for i in range(60):
        d = f"2025-{3 + i // 30:02d}-{1 + i % 28:02d}"
        px = base + i * 0.4
        rows.append({"symbol": US_SYMBOL, "market": US_MARKET, "date": d,
                     "open": px, "high": px + 1, "low": px - 1, "close": px,
                     "volume": 50_000_000})
    store.upsert_us_daily_prices(rows)


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


# --------------------------------------------------------------------------- #
# 5. WS-3 adapter bridge — US financials map to the India key contract so the
#    forensic methods consume them unchanged.
# --------------------------------------------------------------------------- #


class TestWS3AdapterBridge:
    def test_annual_financials_have_india_keys(self, db):
        from flowtracker.research.data_api import _run_market

        token = _run_market.set(US_MARKET)
        try:
            with ResearchDataAPI() as api:
                rows = api.get_annual_financials(US_SYMBOL)
        finally:
            _run_market.reset(token)

        assert rows, "expected mapped US annual rows"
        # Latest-first, matching the India path.
        assert rows[0]["fiscal_year_end"] == "2024-09-28"
        assert rows[1]["fiscal_year_end"] == "2023-09-28"

        top = rows[0]
        # India model_dump keys must all be present.
        for key in ("symbol", "fiscal_year_end", "revenue", "net_income",
                    "operating_profit", "depreciation", "interest",
                    "profit_before_tax", "tax", "equity_capital", "reserves",
                    "borrowings", "other_liabilities", "total_assets",
                    "net_block", "cwip", "receivables", "inventory",
                    "cash_and_bank", "num_shares", "cfo", "cfi", "cff",
                    "net_cash_flow", "eps"):
            assert key in top, f"missing India key: {key}"

        # cfo ← operating_cash_flow (not the raw column name).
        assert top["cfo"] == 118_254.0
        # net_cash_flow = cfo + cfi + cff.
        assert top["net_cash_flow"] == pytest.approx(118_254.0 + 2_935.0 - 121_983.0)

        # Equity reconciliation: equity_capital + reserves == US total_equity.
        assert top["equity_capital"] + top["reserves"] == pytest.approx(56_950.0)
        assert top["total_equity"] == 56_950.0

    def test_quarterly_results_have_india_keys(self, db):
        from flowtracker.research.data_api import _run_market

        token = _run_market.set(US_MARKET)
        try:
            with ResearchDataAPI() as api:
                rows = api.get_quarterly_results(US_SYMBOL)
        finally:
            _run_market.reset(token)

        assert rows
        top = rows[0]
        for key in ("symbol", "quarter_end", "revenue", "net_income", "eps",
                    "gross_profit", "operating_income", "ebitda", "eps_diluted",
                    "operating_margin", "net_margin", "expenses", "other_income",
                    "depreciation", "interest", "profit_before_tax", "tax_pct",
                    "net_premium_earned"):
            assert key in top, f"missing India quarterly key: {key}"
        assert top["revenue"] == 124_300.0
        # Sparse fields are explicit None, never KeyError.
        assert top["ebitda"] is None

    def test_piotroski_routes_for_us(self, db):
        from flowtracker.research.data_api import _run_market

        token = _run_market.set(US_MARKET)
        try:
            with ResearchDataAPI() as api:
                score = api.get_piotroski_score(US_SYMBOL)
        finally:
            _run_market.reset(token)

        assert not score.get("error"), score.get("error")
        assert isinstance(score.get("score"), int)
        assert 0 <= score["score"] <= score["max_score"]

    def test_india_annual_financials_unchanged(self, db):
        # Regression: India path must NOT route through the US mapper.
        with ResearchDataAPI() as api:
            rows = api.get_annual_financials("SBIN")
        assert rows
        top = rows[0]
        assert top["symbol"] == "SBIN"
        # India fiscal year end is March; never the US Sept date.
        assert top["fiscal_year_end"].endswith("-03-31")
        # India headline transform still applied.
        assert "headline_revenue" in top


# --------------------------------------------------------------------------- #
# 6. WS-4 — compute/price gaps routed for US; India-only computes degraded.
# --------------------------------------------------------------------------- #


from contextlib import contextmanager


@contextmanager
def _us_run():
    from flowtracker.research.data_api import _run_market
    token = _run_market.set(US_MARKET)
    try:
        yield
    finally:
        _run_market.reset(token)


class TestWS4ComputeRoutesForUS:
    def test_wacc_ke_in_us_band(self, db, monkeypatch):
        # Force the deterministic offline rf fallback (0.043) so the test does
        # not depend on a live ^TNX fetch.
        import flowtracker.research.data_api as dapi
        monkeypatch.setattr(dapi, "_us_risk_free_rate", lambda: (0.043, True))
        with _us_run(), ResearchDataAPI() as api:
            w = api.get_wacc_params(US_SYMBOL)
        ke = w.get("ke")
        assert ke is not None, "expected a US cost of equity"
        # rf≈0.043, beta fallback≈1.0, US_ERP=4.6% → Ke in the ~8–11% band.
        assert 0.07 <= ke <= 0.12, f"Ke {ke} out of US band"
        # rf-default flag fires when the fallback is used.
        assert "rf_default" in w.get("reliability_flags", [])

    def test_fair_value_has_signal(self, db):
        with _us_run(), ResearchDataAPI() as api:
            fv = api.get_fair_value(US_SYMBOL)
        assert fv["signal"] in (
            "DEEP VALUE", "UNDERVALUED", "FAIR VALUE", "EXPENSIVE",
        ), fv.get("signal")
        rng = fv["fair_value_range"]
        assert rng["bear"] < rng["base"] < rng["bull"]
        assert fv["combined_fair_value"] > 0

    def test_technicals_non_empty_for_us(self, db):
        with _us_run(), ResearchDataAPI() as api:
            t_rows = api.get_technical_indicators(US_SYMBOL)
        assert t_rows, "expected non-empty US technicals"
        row = t_rows[0]
        # 60 seeded bars → MACD + Bollinger present.
        assert row.get("macd") is not None
        assert row.get("bollinger_upper") is not None
        assert row.get("rsi_14") is not None

    def test_price_performance_routes_for_us(self, db):
        with _us_run(), ResearchDataAPI() as api:
            pp = api.get_price_performance(US_SYMBOL)
        assert "error" not in pp
        assert pp["periods"], "expected at least one period return"

    def test_fcf_yield_routes_for_us(self, db):
        with _us_run(), ResearchDataAPI() as api:
            fcf = api.get_fcf_yield(US_SYMBOL)
        # EV now derived in get_valuation_snapshot → no EV error.
        assert "error" not in fcf, fcf.get("error")
        assert fcf.get("ev_cr", 0) > 0

    def test_growth_rates_route_for_us(self, db):
        payload = _call(t.get_fundamentals, {"symbol": US_SYMBOL, "section": "growth_rates"})
        assert not _is_not_applicable(payload)
        rows = payload.get("growth_rates", payload) if isinstance(payload, dict) else payload
        assert rows and rows[0].get("revenue_growth") is not None

    def test_analytical_profile_degrades_for_us(self, db):
        # Graceful non-error envelope (compute_on_demand), not ERROR.
        with _us_run(), ResearchDataAPI() as api:
            prof = api.get_analytical_profile(US_SYMBOL)
        assert "error" not in prof
        assert prof.get("status") == "compute_on_demand"


class TestWS4IndiaOnlyDegradesForUS:
    def test_pe_history_na_for_us(self, db):
        payload = _call(t.get_valuation, {"symbol": US_SYMBOL, "section": "pe_history"})
        assert _is_not_applicable(payload)

    def test_quarterly_balance_sheet_na_for_us(self, db):
        payload = _call(t.get_fundamentals, {"symbol": US_SYMBOL, "section": "quarterly_balance_sheet"})
        assert _is_not_applicable(payload)

    def test_ratios_na_for_us(self, db):
        payload = _call(t.get_fundamentals, {"symbol": US_SYMBOL, "section": "ratios"})
        assert _is_not_applicable(payload)

    def test_shareholding_na_for_us(self, db):
        payload = _call(t.get_ownership, {"symbol": US_SYMBOL, "section": "shareholding"})
        assert _is_not_applicable(payload)

    def test_beneish_na_for_us(self, db):
        payload = _call(t.get_quality_scores, {"symbol": US_SYMBOL, "section": "beneish"})
        assert _is_not_applicable(payload)

    def test_dcf_history_na_for_us(self, db):
        payload = _call(t.get_fair_value_analysis, {"symbol": US_SYMBOL, "section": "dcf_history"})
        assert _is_not_applicable(payload)


class TestWS4IndiaStillRoutes:
    """Regression: the same sections/computes return real data for India."""

    def test_pe_history_india_routes(self, db):
        payload = _call(t.get_valuation, {"symbol": "SBIN", "section": "pe_history"})
        assert not _is_not_applicable(payload)

    def test_ratios_india_routes(self, db):
        payload = _call(t.get_fundamentals, {"symbol": "SBIN", "section": "ratios"})
        assert not _is_not_applicable(payload)

    def test_shareholding_india_routes(self, db):
        payload = _call(t.get_ownership, {"symbol": "SBIN", "section": "shareholding"})
        assert not _is_not_applicable(payload)

    def test_beneish_india_not_degraded(self, db):
        with ResearchDataAPI() as api:
            score = api.get_beneish_score("SBIN")
        # India never returns the US not_applicable envelope.
        assert score.get("status") != "not_applicable"

    def test_wacc_india_uses_gsec_rf(self, db):
        with ResearchDataAPI() as api:
            w = api.get_wacc_params("SBIN")
        # India rf comes from gsec_10y (seeded), not the US Treasury fallback.
        assert w.get("ke") is not None
        assert "rf_default" not in w.get("reliability_flags", [])


# --------------------------------------------------------------------------- #
# WS-6 — US-native functions (R&D intensity, SBC dilution)
# --------------------------------------------------------------------------- #


class TestWS6USNativeFunctions:
    def test_rnd_intensity_routes_for_us(self, db):
        with ResearchDataAPI() as api:
            data = api.get_rnd_intensity(US_SYMBOL)
        assert data.get("status") != "not_applicable"
        assert data["series"], "expected an R&D intensity series for US"
        latest = data["series"][0]
        assert latest["rnd_intensity_pct"] is not None and latest["rnd_intensity_pct"] > 0
        assert data["latest_rnd_intensity_pct"] is not None

    def test_sbc_dilution_routes_for_us(self, db):
        with ResearchDataAPI() as api:
            data = api.get_sbc_dilution(US_SYMBOL)
        assert data.get("status") != "not_applicable"
        assert data["series"], "expected an SBC series for US"
        assert data["latest_sbc_pct_revenue"] is not None
        # num_shares grows in the seed -> net dilution proxy present.
        assert "share_count_cagr_pct" in data

    def test_rnd_intensity_na_for_india(self, db):
        with ResearchDataAPI() as api:
            data = api.get_rnd_intensity("SBIN")
        assert data.get("status") == "not_applicable"

    def test_sbc_dilution_na_for_india(self, db):
        with ResearchDataAPI() as api:
            data = api.get_sbc_dilution("SBIN")
        assert data.get("status") == "not_applicable"

    def test_rnd_intensity_tool_us(self, db):
        payload = _call(t.get_rnd_intensity, {"symbol": US_SYMBOL})
        assert not _is_not_applicable(payload)
        assert payload["series"]

    def test_sbc_dilution_tool_india_na(self, db):
        payload = _call(t.get_sbc_dilution, {"symbol": "SBIN"})
        assert _is_not_applicable(payload)


# --------------------------------------------------------------------------- #
# WS-7 — live-data fixes (no phantom latest annual row; US DuPont branch)
# --------------------------------------------------------------------------- #


class TestWS7LiveDataFixes:
    def test_no_phantom_latest_annual_row(self, db):
        # Every US annual row must carry P&L (revenue or net_income) — a row with
        # only balance-sheet values is a phantom from an interim instant.
        with ResearchDataAPI() as api:
            annuals = api.get_annual_financials(US_SYMBOL, years=12)
        assert annuals
        for a in annuals:
            assert a.get("revenue") is not None or a.get("net_income") is not None, \
                f"phantom annual row (no P&L): {a.get('fiscal_year_end')}"

    def test_us_dupont_decomposition_non_empty(self, db):
        with ResearchDataAPI() as api:
            d = api.get_dupont_decomposition(US_SYMBOL)
        assert d.get("data_source") == "us_annual"
        assert d.get("years"), "expected a US DuPont year series"
        row = d["years"][0]
        assert row["roe_dupont"] is not None
        # ROE ≈ net_profit_margin × asset_turnover × equity_multiplier.
        approx = row["net_profit_margin"] * row["asset_turnover"] * row["equity_multiplier"]
        assert abs(approx - row["roe_dupont"]) < 1e-3

    def test_india_dupont_unchanged(self, db):
        with ResearchDataAPI() as api:
            d = api.get_dupont_decomposition("SBIN")
        # India never takes the us_annual branch.
        assert d.get("data_source") != "us_annual"


class TestConsensusTargetRange:
    def test_fair_value_full_range_from_consensus_high_low(self, db):
        # target_high/low are now persisted -> fair_value emits the consensus
        # low/mean/high directly as bear/base/bull (no PE-fallback).
        with ResearchDataAPI() as api:
            fv = api.get_fair_value(US_SYMBOL)
        rng = fv.get("fair_value_range") or {}
        assert rng.get("bear") == 170.0
        assert rng.get("base") == 230.0
        assert rng.get("bull") == 300.0
        assert fv.get("consensus_range") == {"low": 170.0, "mean": 230.0, "high": 300.0}

    def test_consensus_high_low_round_trip(self, db):
        with ResearchDataAPI() as api:
            rows = api._store.get_us_consensus_estimates(US_SYMBOL, US_MARKET)
        assert rows and rows[0].get("target_high") == 300.0 and rows[0].get("target_low") == 170.0
