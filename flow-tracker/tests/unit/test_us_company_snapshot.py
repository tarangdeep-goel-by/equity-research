"""Tests for the US company-snapshot machinery (US add-on, feat/us-snapshot-peers).

Covers the store round-trip, the data_api US routing for
``get_company_snapshot`` / ``get_valuation_matrix`` / ``get_peer_comparison`` /
``get_sector_benchmarks``, the <2-peer graceful status, and an India regression
asserting India symbols still read ``company_snapshot`` (byte-identical path).

No network: yfinance ``.info`` is never invoked because the builder is not run
here — snapshots are seeded directly via ``upsert_us_company_snapshot``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# A 4-symbol US tech cohort that all resolve to the SAME sector key
# (it_services) via their granular registry industries, so they bucket as peers.
_US_TECH = {
    "AAPL": ("NASDAQ", "Software - Infrastructure"),  # subject
    "MSFT": ("NASDAQ", "Software - Infrastructure"),
    "NVDA": ("NASDAQ", "Semiconductors"),
    "ORCL": ("NYSE", "Software - Application"),
}

# Seeded us_company_snapshot rows (USD millions for market_cap; percent for
# margins/returns/growth; raw ratios for pe/pb/peg/ev_ebitda/beta/d-e).
_SNAPSHOTS = {
    "AAPL": dict(name="Apple Inc.", cmp=185.64, market_cap=2_900_000.0,
                 pe_trailing=30.2, pe_forward=27.5, pb=45.1, ev_ebitda=22.0,
                 peg=2.5, div_yield=0.5, operating_margin=30.1, net_margin=25.3,
                 roe=147.0, roa=27.5, roce=55.0, roic=50.0, fcf_yield=3.4,
                 revenue_growth=2.1, earnings_growth=13.0, beta=1.28,
                 debt_to_equity=1.5, current_ratio=1.0, high_52w=199.6, low_52w=164.0),
    "MSFT": dict(name="Microsoft Corp.", cmp=370.0, market_cap=2_750_000.0,
                 pe_trailing=35.0, pe_forward=31.0, pb=12.0, ev_ebitda=24.0,
                 peg=2.2, div_yield=0.8, operating_margin=44.0, net_margin=36.0,
                 roe=39.0, roa=18.0, roce=28.0, roic=26.0, fcf_yield=2.8,
                 revenue_growth=12.0, earnings_growth=20.0, beta=0.9,
                 debt_to_equity=0.4, current_ratio=1.7, high_52w=384.0, low_52w=245.0),
    "NVDA": dict(name="NVIDIA Corp.", cmp=480.0, market_cap=1_200_000.0,
                 pe_trailing=65.0, pe_forward=40.0, pb=40.0, ev_ebitda=55.0,
                 peg=1.1, div_yield=0.03, operating_margin=50.0, net_margin=48.0,
                 roe=70.0, roa=45.0, roce=60.0, roic=58.0, fcf_yield=1.5,
                 revenue_growth=125.0, earnings_growth=300.0, beta=1.7,
                 debt_to_equity=0.5, current_ratio=3.5, high_52w=505.0, low_52w=140.0),
    "ORCL": dict(name="Oracle Corp.", cmp=105.0, market_cap=290_000.0,
                 pe_trailing=33.0, pe_forward=20.0, pb=50.0, ev_ebitda=18.0,
                 peg=1.9, div_yield=1.5, operating_margin=27.0, net_margin=18.0,
                 roe=200.0, roa=9.0, roce=22.0, roic=20.0, fcf_yield=3.0,
                 revenue_growth=18.0, earnings_growth=27.0, beta=1.0,
                 debt_to_equity=8.0, current_ratio=0.9, high_52w=132.0, low_52w=80.0),
}


@pytest.fixture
def us_api(tmp_db: Path, populated_store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI on a store with India fixtures (SBIN/INFY) plus a 4-symbol
    US tech cohort registered + snapshotted in us_company_snapshot."""
    store = populated_store
    for sym, (market, industry) in _US_TECH.items():
        store.upsert_symbol_registry(
            sym, market, company_name=_SNAPSHOTS[sym]["name"],
            sector="Technology", gics="Information Technology", industry=industry,
        )
        store.upsert_us_company_snapshot(sym, market, {"industry": industry, **_SNAPSHOTS[sym]})
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI(store=store)
    yield a


# ---------------------------------------------------------------------------
# Store round-trip
# ---------------------------------------------------------------------------

class TestStoreRoundTrip:
    def test_upsert_and_get_single(self, store: FlowStore):
        store.upsert_us_company_snapshot("AAPL", "NASDAQ", {
            "name": "Apple Inc.", "industry": "Software - Infrastructure",
            "market_cap": 2_900_000.0, "pe_trailing": 30.2, "roe": 147.0,
        })
        snap = store.get_us_company_snapshot("AAPL", "NASDAQ")
        assert snap is not None
        assert snap["symbol"] == "AAPL"
        assert snap["market"] == "NASDAQ"
        assert snap["currency"] == "USD"
        assert snap["market_cap"] == 2_900_000.0
        assert snap["pe_trailing"] == 30.2
        assert snap["roe"] == 147.0

    def test_get_missing_returns_none(self, store: FlowStore):
        assert store.get_us_company_snapshot("NOPE", "NASDAQ") is None

    def test_coalesce_safe_upsert_preserves_existing(self, store: FlowStore):
        store.upsert_us_company_snapshot("AAPL", "NASDAQ", {"market_cap": 100.0, "roe": 50.0})
        # Re-upsert with roe omitted (None) — market_cap updates, roe preserved.
        store.upsert_us_company_snapshot("AAPL", "NASDAQ", {"market_cap": 200.0})
        snap = store.get_us_company_snapshot("AAPL", "NASDAQ")
        assert snap["market_cap"] == 200.0
        assert snap["roe"] == 50.0  # not nulled

    def test_get_multiple(self, store: FlowStore):
        store.upsert_us_company_snapshot("AAPL", "NASDAQ", {"market_cap": 1.0})
        store.upsert_us_company_snapshot("MSFT", "NASDAQ", {"market_cap": 2.0})
        store.upsert_us_company_snapshot("ORCL", "NYSE", {"market_cap": 3.0})
        rows = store.get_us_company_snapshots(["AAPL", "MSFT", "ORCL"], "NASDAQ")
        # ORCL is NYSE — not returned for a NASDAQ query.
        assert {r["symbol"] for r in rows} == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------------
# data_api routing
# ---------------------------------------------------------------------------

class TestCompanySnapshotRouting:
    def test_us_reads_us_company_snapshot(self, us_api: ResearchDataAPI):
        snap = us_api.get_company_snapshot("AAPL")
        assert snap["symbol"] == "AAPL"
        assert snap["market"] == "NASDAQ"
        assert snap["currency"] == "USD"
        assert snap["market_cap"] == 2_900_000.0

    def test_india_regression_reads_company_snapshot(self, us_api: ResearchDataAPI):
        # SBIN is India (no US registry row) — must use company_snapshot path.
        assert us_api._is_us("SBIN") is False
        # Seed an India snapshot and confirm it round-trips through the India path.
        us_api._store.upsert_snapshot_screener("SBIN", {"name": "SBI", "market_cap": 700000.0})
        snap = us_api.get_company_snapshot("SBIN")
        assert snap.get("name") == "SBI"
        assert snap.get("market_cap") == 700000.0


class TestValuationMatrixRouting:
    def test_us_matrix_uses_us_peers(self, us_api: ResearchDataAPI):
        m = us_api.get_valuation_matrix("AAPL")
        assert m["subject"]["symbol"] == "AAPL"
        peer_syms = {p["symbol"] for p in m["peers"]}
        assert peer_syms == {"MSFT", "NVDA", "ORCL"}
        assert m["peer_count"] == 3
        # USD-correct market_cap survives into the matrix.
        assert m["subject"]["market_cap"] == 2_900_000.0
        # sector_stats computed over subject+peers for a shared metric.
        assert "pe_trailing" in m["sector_stats"]
        assert m["sector_stats"]["pe_trailing"]["min"] == 30.2  # AAPL is lowest PE


class TestPeerComparisonRouting:
    def test_us_peer_comparison(self, us_api: ResearchDataAPI):
        pc = us_api.get_peer_comparison("AAPL")
        assert pc["source"] == "us_registry_sector"
        assert pc["peer_count"] == 3
        assert {p["symbol"] for p in pc["peers"]} == {"MSFT", "NVDA", "ORCL"}
        assert pc["subject"]["symbol"] == "AAPL"

    def test_insufficient_peers_graceful_status(self, us_api: ResearchDataAPI):
        # A US energy name with no same-sector peers → graceful status, NOT error.
        us_api._store.upsert_symbol_registry(
            "XOM", "NYSE", company_name="Exxon", sector="Energy",
            gics="Energy", industry="Oil & Gas Integrated",
        )
        us_api._store.upsert_us_company_snapshot("XOM", "NYSE", {"market_cap": 450000.0})
        pc = us_api.get_peer_comparison("XOM")
        assert pc["status"] == "insufficient_peers"
        assert pc["peer_count"] == 0
        assert "reason" in pc


class TestBuilder:
    def test_build_assembles_row_no_network(self, store: FlowStore, monkeypatch):
        """Builder assembles cmp/valuation from us_valuation_snapshot + computed
        ev_ebitda/roce/roic/fcf_yield from us_annual_financials, with the
        network .info call stubbed."""
        from flowtracker.research import us_snapshot_builder as b

        store.upsert_symbol_registry(
            "AAPL", "NASDAQ", company_name="Apple Inc.", sector="Technology",
            gics="Information Technology", industry="Software - Infrastructure",
        )
        store.upsert_us_valuation_snapshot([{
            "symbol": "AAPL", "date": "2024-01-02", "price": 185.64,
            "market_cap": 2_900_000.0, "enterprise_value": 2_950_000.0,
            "pe_trailing": 30.2, "pe_forward": 27.5, "pb": 45.1,
            "dividend_yield": 0.5, "beta": 1.28,
            "operating_margin": 30.1, "net_margin": 25.3, "roe": 147.0,
        }])
        store.upsert_us_annual_financials([
            {"symbol": "AAPL", "fiscal_year": 2023, "operating_profit": 114000.0,
             "depreciation": 11000.0, "profit_before_tax": 113000.0, "tax": 17000.0,
             "total_equity": 62000.0, "total_debt": 110000.0,
             "equity_capital": 1000.0, "reserves": 61000.0, "borrowings": 110000.0,
             "cash_and_bank": 30000.0, "free_cash_flow": 99000.0},
            {"symbol": "AAPL", "fiscal_year": 2022, "operating_profit": 119000.0},
        ])
        # Stub the yfinance .info pull (no network).
        monkeypatch.setattr(b, "_from_info", lambda sym, mkt: {
            "name": "Apple Inc.", "peg": 2.5, "high_52w": 199.6, "low_52w": 164.0,
            "current_ratio": 1.0, "debt_to_equity": 1.5,
            "revenue_growth": 2.1, "earnings_growth": 13.0, "roa": 27.5,
        })

        assert b.build_us_company_snapshot("AAPL", store) is True
        snap = store.get_us_company_snapshot("AAPL", "NASDAQ")
        assert snap["name"] == "Apple Inc."
        assert snap["industry"] == "Software - Infrastructure"
        assert snap["cmp"] == 185.64
        assert snap["market_cap"] == 2_900_000.0
        assert snap["pe_trailing"] == 30.2
        assert snap["roe"] == 147.0
        assert snap["peg"] == 2.5
        # ev_ebitda = EV / (operating_profit + depreciation) = 2,950,000 / 125,000
        assert snap["ev_ebitda"] == round(2_950_000.0 / 125_000.0, 2)
        # roce = op / (equity + debt) = 114000 / 172000 * 100
        assert snap["roce"] == round(114000.0 / 172000.0 * 100, 2)
        # fcf_yield = fcf / mcap = 99000 / 2,900,000 * 100
        assert snap["fcf_yield"] == round(99000.0 / 2_900_000.0 * 100, 2)
        assert snap["roic"] is not None

    def test_build_no_data_returns_false(self, store: FlowStore, monkeypatch):
        from flowtracker.research import us_snapshot_builder as b

        store.upsert_symbol_registry("ZZZZ", "NASDAQ")
        monkeypatch.setattr(b, "_from_info", lambda sym, mkt: {})
        assert b.build_us_company_snapshot("ZZZZ", store) is False


class TestSectorBenchmarksRouting:
    def test_us_benchmarks_all_metrics(self, us_api: ResearchDataAPI):
        rows = us_api.get_sector_benchmarks("AAPL")
        assert isinstance(rows, list)
        by_metric = {r["metric"]: r for r in rows}
        pe = by_metric["pe_trailing"]
        assert pe["subject_symbol"] == "AAPL"
        assert pe["subject_value"] == 30.2
        assert pe["peer_count"] == 3  # MSFT, NVDA, ORCL
        # median of peer PEs {35.0, 65.0, 33.0} = 35.0
        assert pe["sector_median"] == 35.0
        assert pe["sector_min"] == 33.0
        assert pe["sector_max"] == 65.0
        # AAPL PE 30.2 is below all 3 peers → 0th percentile.
        assert pe["percentile"] == 0.0

    def test_us_benchmarks_single_metric(self, us_api: ResearchDataAPI):
        row = us_api.get_sector_benchmarks("AAPL", metric="roe")
        assert row["metric"] == "roe"
        assert row["subject_value"] == 147.0
        assert row["peer_count"] == 3

    def test_us_benchmarks_insufficient_peers(self, us_api: ResearchDataAPI):
        us_api._store.upsert_symbol_registry(
            "XOM", "NYSE", company_name="Exxon", sector="Energy",
            gics="Energy", industry="Oil & Gas Integrated",
        )
        us_api._store.upsert_us_company_snapshot("XOM", "NYSE", {"market_cap": 450000.0, "roe": 20.0})
        allm = us_api.get_sector_benchmarks("XOM")
        assert allm["status"] == "insufficient_peers"
        # Single-metric call on insufficient peers → empty dict.
        assert us_api.get_sector_benchmarks("XOM", metric="roe") == {}
