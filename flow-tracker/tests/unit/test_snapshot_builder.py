"""Tests for the company_snapshot builder (research/snapshot_builder.py).

Covers the three private collectors (_build_screener, _build_yfinance,
_build_ownership), the public builder (build_company_snapshot), missing-data
paths, Screener-over-yfinance priority for shared fields, and write-through
to the company_snapshot table.

All tests use a real FlowStore at a temp path (via the `store` / `populated_store`
conftest fixtures). yfinance is never called over the network — FundClient is
monkeypatched where `_build_yfinance` exercises the live sector/industry path.
"""

from __future__ import annotations

from typing import Any

import pytest

from flowtracker.fund_models import LiveSnapshot
# Pre-import FundClient at module load time so the (slow) yfinance/pandas import
# cost is paid during test collection, not inside a per-test 10s timeout.
from flowtracker import fund_client as _fund_client_mod  # noqa: F401
from flowtracker.research.snapshot_builder import (
    _build_ownership,
    _build_screener,
    _build_yfinance,
    build_company_snapshot,
)
from flowtracker.store import FlowStore
from tests.fixtures.factories import (
    make_promoter_pledges,
    make_quarterly_results,
    make_screener_ratios,
    make_shareholding,
    make_valuation_snapshots,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeFundClient:
    """Stand-in for FundClient that returns a canned LiveSnapshot."""

    def __init__(self, sector: str | None = "Financial Services", industry: str | None = "Banks - Public Sector") -> None:
        self._sector = sector
        self._industry = industry

    def get_live_snapshot(self, symbol: str) -> LiveSnapshot:
        return LiveSnapshot(symbol=symbol, sector=self._sector, industry=self._industry)


def _patch_fund_client(monkeypatch: pytest.MonkeyPatch, client: Any) -> None:
    """Patch the FundClient class used inside _build_yfinance."""
    monkeypatch.setattr(
        "flowtracker.fund_client.FundClient",
        lambda *a, **kw: client,
    )


def _raising_fund_client(*_a: Any, **_kw: Any) -> Any:
    raise RuntimeError("network unavailable")


# ---------------------------------------------------------------------------
# _build_screener — per-field coverage
# ---------------------------------------------------------------------------


class TestBuildScreener:
    def test_name_and_industry_from_index_constituents(self, populated_store: FlowStore) -> None:
        """Name + industry come from index_constituents, not company_profiles."""
        data = _build_screener("SBIN", populated_store)
        assert data["name"] == "State Bank of India"
        assert data["industry"] == "Banks"

    def test_cmp_and_pe_fallback_to_valuation_snapshot(self, populated_store: FlowStore) -> None:
        """With no peer_comparison data seeded, cmp/pe_trailing must be filled from valuation_snapshot."""
        data = _build_screener("SBIN", populated_store)
        # make_valuation_snapshots seeds 30 days ending today; latest price sits in the drift range
        assert data.get("cmp") is not None
        assert 700 < data["cmp"] < 900  # SBIN fixture range
        assert data.get("pe_trailing") is not None
        assert 5 < data["pe_trailing"] < 15
        assert data.get("market_cap") is not None

    def test_roce_from_screener_ratios_latest(self, populated_store: FlowStore) -> None:
        """ROCE must come from the most recent screener_ratios row."""
        data = _build_screener("SBIN", populated_store)
        # Fixture: roce_pct = 18.0 + i*0.5 for i=0..4 → latest (fy=2026-03-31) is 20.0
        assert data.get("roce") == pytest.approx(20.0)

    def test_quarterly_yoy_variance(self, populated_store: FlowStore) -> None:
        """sales_qtr/np_qtr come from latest quarter; YoY variance compares to Q-4."""
        data = _build_screener("SBIN", populated_store)
        assert data.get("sales_qtr") is not None
        assert data.get("np_qtr") is not None
        # 8 quarters seeded → YoY deltas must be computed (Q0 vs Q4)
        assert data.get("qtr_sales_var") is not None
        assert data.get("qtr_profit_var") is not None
        # Fixture trajectory is monotonically growing → positive YoY for both
        assert data["qtr_sales_var"] > 0
        assert data["qtr_profit_var"] > 0

    def test_peer_comparison_wins_over_valuation_snapshot(self, store: FlowStore) -> None:
        """When a peer_comparison self-row exists, its cmp/pe/market_cap beat the snapshot fallback."""
        # Seed a valuation snapshot first (fallback source)
        store.upsert_valuation_snapshots(make_valuation_snapshots("SBIN", n=2))
        # Seed a peer_comparison row for SBIN referencing itself — this should win
        store.upsert_peers("SBIN", [{
            "name": "State Bank of India",
            "peer_symbol": "SBIN",
            "cmp": 999.0,
            "pe": 12.3,
            "market_cap": 555000.0,
        }])
        data = _build_screener("SBIN", store)
        assert data["cmp"] == 999.0
        assert data["pe_trailing"] == 12.3
        assert data["market_cap"] == 555000.0

    def test_empty_store_returns_empty_dict(self, store: FlowStore) -> None:
        """With no seeded data at all, _build_screener returns an empty dict."""
        data = _build_screener("UNKNOWN", store)
        assert data == {}

    def test_only_one_quarter_skips_yoy(self, store: FlowStore) -> None:
        """With <5 quarters stored, YoY variance keys must be absent (no Q-4 to compare)."""
        store.upsert_quarterly_results(make_quarterly_results("SBIN", n=1))
        data = _build_screener("SBIN", store)
        assert data.get("sales_qtr") is not None
        assert data.get("np_qtr") is not None
        assert "qtr_sales_var" not in data
        assert "qtr_profit_var" not in data


# ---------------------------------------------------------------------------
# _build_yfinance
# ---------------------------------------------------------------------------


class TestBuildYfinance:
    def test_valuation_fields_populated(self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch) -> None:
        """All yfinance-owned valuation/profitability fields flow from the latest valuation_snapshot."""
        _patch_fund_client(monkeypatch, _FakeFundClient())
        data = _build_yfinance("SBIN", populated_store)
        assert data["pe_forward"] is not None
        assert data["pb"] == pytest.approx(1.8)
        assert data["ev_ebitda"] == pytest.approx(7.5)
        assert data["peg"] == pytest.approx(0.6)
        assert data["div_yield"] == pytest.approx(1.5)
        assert data["operating_margin"] == pytest.approx(42.0)
        assert data["net_margin"] == pytest.approx(35.0)
        assert data["roe"] == pytest.approx(18.5)
        assert data["roa"] == pytest.approx(1.2)
        assert data["revenue_growth"] == pytest.approx(12.0)
        assert data["earnings_growth"] == pytest.approx(15.0)
        assert data["beta"] == pytest.approx(1.1)
        assert data["debt_to_equity"] == pytest.approx(0.4)
        assert data["current_ratio"] == pytest.approx(1.2)
        assert data["high_52w"] is not None
        assert data["low_52w"] is not None

    def test_sector_industry_from_fund_client(self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch) -> None:
        """Live sector/industry override come from FundClient.get_live_snapshot."""
        _patch_fund_client(monkeypatch, _FakeFundClient(sector="Technology", industry="Information Technology Services"))
        data = _build_yfinance("SBIN", populated_store)
        assert data["sector"] == "Technology"
        assert data["industry"] == "Information Technology Services"

    def test_fund_client_failure_swallowed(self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch) -> None:
        """If FundClient raises, the non-critical sector/industry lookup is skipped silently."""
        monkeypatch.setattr("flowtracker.fund_client.FundClient", _raising_fund_client)
        data = _build_yfinance("SBIN", populated_store)
        # The rest of the valuation-backed fields still get populated
        assert data["pb"] == pytest.approx(1.8)
        # But no sector/industry because the live call blew up
        assert "sector" not in data
        # industry only ever comes from the live call in _build_yfinance
        assert "industry" not in data

    def test_no_snapshot_returns_empty(self, store: FlowStore) -> None:
        """No valuation_snapshot rows → early return with empty dict (no FundClient hit)."""
        data = _build_yfinance("GHOST", store)
        assert data == {}

    def test_live_snapshot_with_none_fields_skipped(self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch) -> None:
        """When live snapshot has no sector/industry, neither key is written."""
        _patch_fund_client(monkeypatch, _FakeFundClient(sector=None, industry=None))
        data = _build_yfinance("SBIN", populated_store)
        assert "sector" not in data
        assert "industry" not in data


# ---------------------------------------------------------------------------
# _build_ownership
# ---------------------------------------------------------------------------


class TestBuildOwnership:
    def test_promoter_holding_from_latest_quarter(self, populated_store: FlowStore) -> None:
        """Promoter % comes from the most recent shareholding quarter only."""
        data = _build_ownership("SBIN", populated_store)
        # Fixture: Promoter base 57.5 with drift -(3-1)*0.1 = -0.2 at latest quarter → 57.3
        assert data.get("promoter_holding") == pytest.approx(57.3, abs=0.5)

    def test_promoter_pledge_from_latest_quarter(self, populated_store: FlowStore) -> None:
        """Pledge % comes from the most recent promoter_pledge row."""
        data = _build_ownership("SBIN", populated_store)
        # Fixture: 2.5 - 3*0.5 = 1.0 at latest (2025-12-31)
        assert data.get("promoter_pledge") == pytest.approx(1.0)

    def test_empty_store_returns_empty_dict(self, store: FlowStore) -> None:
        """No shareholding/pledge rows seeded → empty dict, no KeyError."""
        data = _build_ownership("NONEXIST", store)
        assert data == {}

    def test_promoters_plural_category_recognised(self, store: FlowStore) -> None:
        """Category label "Promoters" (plural, case-insensitive) must also map to promoter_holding."""
        from flowtracker.holding_models import ShareholdingRecord
        store.upsert_shareholding([
            ShareholdingRecord(symbol="ACME", quarter_end="2025-12-31", category="PROMOTERS", percentage=60.0),
            ShareholdingRecord(symbol="ACME", quarter_end="2025-12-31", category="Public", percentage=40.0),
        ])
        data = _build_ownership("ACME", store)
        assert data.get("promoter_holding") == pytest.approx(60.0)

    def test_ownership_without_pledge(self, store: FlowStore) -> None:
        """Shareholding present but no pledge row → only promoter_holding is set."""
        store.upsert_shareholding(make_shareholding("ACME", n=1))
        data = _build_ownership("ACME", store)
        assert "promoter_holding" in data
        assert "promoter_pledge" not in data


# ---------------------------------------------------------------------------
# build_company_snapshot — public API + persistence
# ---------------------------------------------------------------------------


class TestBuildCompanySnapshot:
    def test_happy_path_writes_all_three_sections(
        self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fully populated store → True, and company_snapshot row has fields from all three builders."""
        _patch_fund_client(monkeypatch, _FakeFundClient())
        wrote = build_company_snapshot("SBIN", populated_store)
        assert wrote is True

        row = populated_store.get_company_snapshot("SBIN")
        assert row is not None
        # Screener fields
        assert row["name"] == "State Bank of India"
        assert row["cmp"] is not None
        assert row["pe_trailing"] is not None
        assert row["roce"] is not None
        assert row["sales_qtr"] is not None
        # yfinance fields
        assert row["pb"] is not None
        assert row["sector"] == "Financial Services"
        # Ownership fields
        assert row["promoter_holding"] is not None
        assert row["promoter_pledge"] is not None

    def test_unknown_symbol_is_normalised_to_upper(
        self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mixed-case input must be upper-cased before persistence."""
        _patch_fund_client(monkeypatch, _FakeFundClient())
        wrote = build_company_snapshot("sbin", populated_store)
        assert wrote is True
        # Row stored under SBIN, not sbin
        assert populated_store.get_company_snapshot("SBIN") is not None

    def test_completely_empty_store_returns_false(self, store: FlowStore) -> None:
        """No data at all for symbol → no rows written, returns False."""
        wrote = build_company_snapshot("GHOST", store)
        assert wrote is False
        assert store.get_company_snapshot("GHOST") is None

    def test_only_ownership_data_still_writes(self, store: FlowStore) -> None:
        """With just shareholding/pledge seeded, the ownership section alone is persisted."""
        store.upsert_shareholding(make_shareholding("ACME", n=1))
        store.upsert_promoter_pledges(make_promoter_pledges("ACME", n=1))
        wrote = build_company_snapshot("ACME", store)
        assert wrote is True
        row = store.get_company_snapshot("ACME")
        assert row is not None
        assert row["promoter_holding"] is not None
        # No Screener/yfinance data was present → those columns stay NULL
        assert row["name"] is None
        assert row["pb"] is None

    def test_rebuild_updates_existing_row(
        self, populated_store: FlowStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Running the builder twice keeps a single row (upsert semantics)."""
        _patch_fund_client(monkeypatch, _FakeFundClient())
        build_company_snapshot("SBIN", populated_store)
        build_company_snapshot("SBIN", populated_store)
        # Only one row for SBIN in company_snapshot
        count_row = populated_store._conn.execute(
            "SELECT COUNT(*) AS c FROM company_snapshot WHERE symbol = ?", ("SBIN",)
        ).fetchone()
        assert count_row["c"] == 1

    def test_screener_only_seed_writes_screener_columns(
        self, store: FlowStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Seed only Screener-side data: quarterly + ratios → screener section persists."""
        _patch_fund_client(monkeypatch, _FakeFundClient())
        store.upsert_quarterly_results(make_quarterly_results("ACME", n=8))
        store.upsert_screener_ratios(make_screener_ratios("ACME", n=2))
        wrote = build_company_snapshot("ACME", store)
        assert wrote is True
        row = store.get_company_snapshot("ACME")
        assert row is not None
        assert row["sales_qtr"] is not None
        assert row["qtr_sales_var"] is not None
        assert row["roce"] is not None
        # No valuation_snapshot seeded → yfinance columns stay NULL
        assert row["pb"] is None
        assert row["beta"] is None
