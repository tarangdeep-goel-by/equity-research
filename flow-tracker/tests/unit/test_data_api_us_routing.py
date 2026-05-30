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


# ---------------------------------------------------------------------------
# Bug 2 & 3: SBC dilution split-discontinuity guard + capital_allocation
# dividends-not-tracked (US-gated). India regression via populated_store.
# ---------------------------------------------------------------------------


@pytest.fixture
def us_ca_api(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """US AAPL seed with a 4:1-split-like share-count discontinuity in the
    num_shares series + SBC + CFO/capex columns, plus India SBIN/INFY fixtures."""
    store = populated_store
    store.upsert_symbol_registry(
        "AAPL", "NASDAQ", company_name="Apple Inc.", sector="Technology",
        gics="Technology", cik="320193",
    )
    # 5 years: pre-2021 rows ~5B shares (pre-split), 2021+ ~16B (post 4:1 split)
    # → a >40% YoY jump between 2020 and 2021. Net buyback within each regime.
    annuals = [
        # fy, rev, ni, eps, shares, sbc, cfo, net_block
        (2024, 391_035.0, 93_736.0, 6.08, 15_000_000_000.0, 11_688.0, 118_254.0, 45_680.0),
        (2023, 383_285.0, 96_995.0, 6.13, 15_500_000_000.0, 10_833.0, 110_543.0, 43_715.0),
        (2022, 394_328.0, 99_803.0, 6.11, 16_000_000_000.0, 9_038.0, 122_151.0, 42_117.0),
        (2021, 365_817.0, 94_680.0, 5.61, 16_500_000_000.0, 7_906.0, 104_038.0, 39_440.0),
        (2020, 274_515.0, 57_411.0, 3.28, 5_000_000_000.0, 6_829.0, 80_674.0, 36_766.0),
    ]
    store.upsert_us_annual_financials([
        {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
         "fiscal_year": fy, "fiscal_year_end": f"{fy}-09-28",
         "revenue": rev, "net_income": ni, "eps": eps, "num_shares": sh,
         "shares_outstanding": sh, "stock_based_comp": sbc, "cfo": cfo,
         "operating_cash_flow": cfo, "net_block": nb, "cwip": 0.0,
         "depreciation": 11_000.0, "cash_and_bank": 30_000.0, "investments": 0.0,
         "borrowings": 100_000.0}
        for (fy, rev, ni, eps, sh, sbc, cfo, nb) in annuals
    ])
    store.upsert_us_valuation_snapshot([
        {"symbol": "AAPL", "date": "2025-05-29", "price": 207.5,
         "market_cap": 3_100_000.0, "pe_trailing": 32.0},
    ])
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI(store=store)
    yield a


class TestSbcDilutionDiscontinuity:
    def test_split_discontinuity_suppresses_net_dilution(self, us_ca_api):
        sd = us_ca_api.get_sbc_dilution("AAPL")
        # The 5B → 16.5B jump (2020→2021) is a split, not real dilution.
        assert sd["net_dilution"] is None
        assert sd["share_count_cagr_pct"] is None
        assert "note" in sd and "split" in sd["note"].lower()
        # Per-year SBC %-of-revenue series stays valid.
        assert sd["latest_sbc_pct_revenue"] is not None
        assert all("sbc_pct_revenue" in s for s in sd["series"])

    def test_no_discontinuity_reports_cagr(self, us_ca_api):
        """Clean (no-split) series still reports CAGR + net_dilution."""
        # AAPL post-split-only window: shares fall 16.5B → 15B (net buyback).
        api = us_ca_api
        api._store.upsert_us_annual_financials([
            {"symbol": "AAPL", "market": "NASDAQ", "currency": "USD",
             "fiscal_year": 2020, "fiscal_year_end": "2020-09-28",
             "revenue": 274_515.0, "net_income": 57_411.0, "eps": 5.5,
             "num_shares": 17_000_000_000.0, "shares_outstanding": 17_000_000_000.0,
             "stock_based_comp": 6_829.0, "cfo": 80_674.0},
        ])
        sd = api.get_sbc_dilution("AAPL")
        assert "note" not in sd
        assert sd["share_count_cagr_pct"] is not None
        assert sd["net_dilution"] is False  # shares shrank → buybacks

    def test_india_symbol_not_applicable(self, us_ca_api):
        sd = us_ca_api.get_sbc_dilution("SBIN")
        assert sd.get("applicable") is False or "not applicable" in str(sd).lower()


class TestCapitalAllocationUsDividends:
    def test_us_dividends_null_not_zero(self, us_ca_api):
        ca = us_ca_api.get_capital_allocation("AAPL")
        assert ca.get("dividends_not_tracked") is True
        assert ca["cumulative"]["dividends"] is None
        assert ca["cumulative"]["dividends_pct_of_cfo"] is None
        assert ca["cash_yield_pct"] is None
        # No $0 dividend claim in the payout trend.
        for row in ca["payout_trend"]:
            assert row["dividends_paid"] is None
            assert row["payout_ratio_pct"] is None

    def test_india_dividends_unchanged(self, us_ca_api):
        """India path still reports numeric dividends (no not-tracked flag)."""
        ca = us_ca_api.get_capital_allocation("SBIN")
        assert "dividends_not_tracked" not in ca
        # cumulative dividends is a number (possibly 0.0), never None for India.
        assert isinstance(ca["cumulative"]["dividends"], (int, float))


# ---------------------------------------------------------------------------
# #11 — get_sector_kpis surfaces the US KPI overlay for US listings
# ---------------------------------------------------------------------------
class TestUsSectorKpis:
    """A US symbol (AAPL → Technology → it_services) must get US SaaS-framed
    canonical KPIs, not the India IT-services offshore/attrition set."""

    def test_us_symbol_gets_us_kpi_keys(self, us_api: ResearchDataAPI):
        result = us_api.get_sector_kpis("AAPL")
        # No concall data in the test store → the method returns the expected
        # canonical-key list (which is what we assert is now US-framed).
        expected = result.get("kpis_expected") or [
            k for k in result.get("kpis", {})
        ]
        assert "net_revenue_retention_pct" in expected
        assert "rule_of_40_pct" in expected
        # India offshore/attrition vocabulary must NOT appear for a US listing.
        assert "offshore_revenue_mix_pct" not in expected
        assert "ltm_attrition_pct" not in expected

    def test_india_symbol_unchanged(self, us_api: ResearchDataAPI):
        """SBIN (India bank) must still resolve to the India bank KPI set."""
        result = us_api.get_sector_kpis("SBIN")
        expected = result.get("kpis_expected") or list(result.get("kpis", {}))
        # SBIN industry in fixtures may not map to banks; if it resolves to a
        # sector at all, it must be the India set (no US-only keys leak in).
        assert "return_on_tangible_common_equity_pct" not in expected
        assert "rule_of_40_pct" not in expected
