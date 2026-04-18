"""Tests for flowtracker.research.peer_refresh.

Post-inversion (2026-04-18): Yahoo Finance is the source of truth for peer
selection (peer_links table); company_snapshot supplies all benchmark metrics.

Covers:
- _has_fmp_data / _has_fresh_valuation: DB cache checks.
- _get_snapshot_metric: company_snapshot reads, bad columns, NaN/NULL handling.
- _compute_benchmarks: reads from company_snapshot, writes sector_benchmarks.
- refresh_peers end-to-end: <3 Yahoo peers early-return, cached peers,
  fetch path with yfinance + FMP mocking, FMP init failure, benchmark counts.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
import respx

from flowtracker.fund_models import ValuationSnapshot
from flowtracker.research.peer_refresh import (
    _BENCHMARK_METRICS,
    _compute_benchmarks,
    _get_snapshot_metric,
    _has_fmp_data,
    _has_fresh_valuation,
    refresh_peers,
)
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_peer_links(store: FlowStore, symbol: str, peers: list[dict]) -> int:
    """Insert Yahoo peers into peer_links for a subject symbol."""
    return store.upsert_peer_links(symbol, peers)


def _seed_snapshot(
    store: FlowStore,
    symbol: str,
    *,
    pe_trailing: float | None = None,
    market_cap: float | None = None,
    roce: float | None = None,
    div_yield: float | None = None,
    pb: float | None = None,
    beta: float | None = None,
) -> None:
    """Write minimal company_snapshot rows via the store's upsert methods."""
    screener_data: dict = {}
    if pe_trailing is not None:
        screener_data["pe_trailing"] = pe_trailing
    if market_cap is not None:
        screener_data["market_cap"] = market_cap
    if roce is not None:
        screener_data["roce"] = roce
    if screener_data:
        store.upsert_snapshot_screener(symbol, screener_data)

    yf_data: dict = {}
    if div_yield is not None:
        yf_data["div_yield"] = div_yield
    if pb is not None:
        yf_data["pb"] = pb
    if beta is not None:
        yf_data["beta"] = beta
    if yf_data:
        store.upsert_snapshot_yfinance(symbol, yf_data)


def _seed_valuation_today(
    store: FlowStore, symbol: str, *, days_ago: int = 0, pe: float = 10.0
) -> None:
    """Insert a valuation_snapshot row N days ago (yfinance cache check)."""
    d = (date.today() - timedelta(days=days_ago)).isoformat()
    snap = ValuationSnapshot(
        symbol=symbol,
        date=d,
        price=100.0,
        market_cap=10000.0,
        pe_trailing=pe,
        pb_ratio=2.0,
        beta=1.1,
    )
    store.upsert_valuation_snapshot(snap)


# ---------------------------------------------------------------------------
# _has_fmp_data / _has_fresh_valuation
# ---------------------------------------------------------------------------

class TestCacheChecks:
    """Cache-hit predicates used to skip network fetches."""

    def test_has_fmp_data_true_when_row_exists(self, populated_store: FlowStore):
        assert _has_fmp_data(populated_store._conn, "fmp_key_metrics", "SBIN") is True

    def test_has_fmp_data_false_when_empty(self, store: FlowStore):
        assert _has_fmp_data(store._conn, "fmp_key_metrics", "SBIN") is False

    def test_has_fresh_valuation_today(self, store: FlowStore):
        _seed_valuation_today(store, "SBIN", days_ago=0)
        assert _has_fresh_valuation(store._conn, "SBIN", days=7) is True

    def test_has_fresh_valuation_stale(self, store: FlowStore):
        _seed_valuation_today(store, "SBIN", days_ago=10)
        assert _has_fresh_valuation(store._conn, "SBIN", days=7) is False

    def test_has_fresh_valuation_no_row(self, store: FlowStore):
        assert _has_fresh_valuation(store._conn, "NOPE", days=7) is False


# ---------------------------------------------------------------------------
# _get_snapshot_metric
# ---------------------------------------------------------------------------

class TestGetSnapshotMetric:
    """Reads a single column from company_snapshot for a symbol."""

    def test_returns_value_when_present(self, store: FlowStore):
        _seed_snapshot(store, "SBIN", pe_trailing=9.5)
        val = _get_snapshot_metric(store._conn, "pe_trailing", "SBIN")
        assert val == pytest.approx(9.5)

    def test_returns_none_when_symbol_missing(self, store: FlowStore):
        assert _get_snapshot_metric(store._conn, "pe_trailing", "NOPE") is None

    def test_returns_none_when_column_null(self, store: FlowStore):
        _seed_snapshot(store, "SBIN", market_cap=5000.0)  # row exists, pe_trailing unset
        assert _get_snapshot_metric(store._conn, "pe_trailing", "SBIN") is None

    def test_returns_none_for_invalid_column(self, store: FlowStore):
        """Non-existent column → exception caught → None returned."""
        _seed_snapshot(store, "SBIN", pe_trailing=9.5)
        assert _get_snapshot_metric(store._conn, "no_such_col", "SBIN") is None


# ---------------------------------------------------------------------------
# _compute_benchmarks
# ---------------------------------------------------------------------------

class TestComputeBenchmarks:
    """Benchmarks iterate _BENCHMARK_METRICS and read from company_snapshot."""

    def test_benchmarks_written_for_available_metrics(self, store: FlowStore):
        """Subject + peer snapshots present → sector_benchmarks populated."""
        _seed_snapshot(store, "SBIN", pe_trailing=9.5, market_cap=730000.0,
                       roce=18.0, div_yield=1.5)
        _seed_snapshot(store, "HDFCBANK", pe_trailing=18.0, market_cap=900000.0,
                       roce=16.0, div_yield=1.2)
        _seed_snapshot(store, "ICICIBANK", pe_trailing=17.0, market_cap=700000.0,
                       roce=17.5, div_yield=0.8)

        count = _compute_benchmarks(store, "SBIN", ["HDFCBANK", "ICICIBANK"], console=None)

        # pe_trailing, market_cap, roce, div_yield all have data
        assert count >= 4

        bench = store.get_sector_benchmark("SBIN", "pe_trailing")
        assert bench is not None
        assert bench["peer_count"] == 2
        assert bench["sector_median"] == pytest.approx(17.5)
        # SBIN pe_trailing=9.5, both peers higher → percentile 0
        assert bench["percentile"] == pytest.approx(0.0)

    def test_skips_metrics_with_no_data(self, store: FlowStore):
        count = _compute_benchmarks(store, "EMPTY", ["ALSO_EMPTY"], console=None)
        assert count == 0
        assert store.get_sector_benchmark("EMPTY", "pe_trailing") is None

    def test_benchmark_metrics_registry_shape(self):
        """Registry is a flat list of snapshot column names."""
        assert len(_BENCHMARK_METRICS) > 10
        for metric in _BENCHMARK_METRICS:
            assert isinstance(metric, str) and metric
            # Must be lowercase snake_case — matches company_snapshot columns
            assert metric.islower()


# ---------------------------------------------------------------------------
# refresh_peers — end-to-end
# ---------------------------------------------------------------------------

class TestRefreshPeers:
    """Yahoo peer_links drives the pipeline; <3 peers triggers early-return."""

    def _point_flowstore_at(self, monkeypatch: pytest.MonkeyPatch, tmp_db) -> None:
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    def test_returns_zeros_when_no_peers(self, tmp_db, monkeypatch: pytest.MonkeyPatch):
        """Empty peer_links → early return zeros (< 3 threshold)."""
        self._point_flowstore_at(monkeypatch, tmp_db)
        with patch("flowtracker.fmp_client._load_api_key", return_value="test_key"):
            result = refresh_peers("NOPEERS")
        assert result == {
            "peers_found": 0,
            "peers_fetched": 0,
            "peers_cached": 0,
            "peers_skipped": 0,
            "benchmarks_computed": 0,
        }

    def test_returns_zeros_when_less_than_three_peers(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """<3 Yahoo peers → skip benchmarks, agent can call get_screener_peers."""
        self._point_flowstore_at(monkeypatch, tmp_db)
        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_links(s, "SBIN", [
                {"peer_symbol": "HDFCBANK", "score": 0.1},
                {"peer_symbol": "ICICIBANK", "score": 0.2},
            ])

        with patch("flowtracker.fmp_client._load_api_key", return_value="test_key"):
            result = refresh_peers("SBIN")

        assert result["peers_found"] == 2
        assert result["peers_fetched"] == 0
        assert result["benchmarks_computed"] == 0

    def test_skips_peers_with_fresh_cache(self, tmp_db, monkeypatch: pytest.MonkeyPatch):
        """Peers with fresh valuation_snapshot are counted as cached, no fetch."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_links(s, "SBIN", [
                {"peer_symbol": "HDFCBANK", "score": 0.1},
                {"peer_symbol": "ICICIBANK", "score": 0.2},
                {"peer_symbol": "AXISBANK", "score": 0.3},
            ])
            for sym in ("HDFCBANK", "ICICIBANK", "AXISBANK"):
                _seed_valuation_today(s, sym, days_ago=0)

        fund_mock = MagicMock()
        with (
            patch("flowtracker.fmp_client._load_api_key", return_value="test_key"),
            patch("flowtracker.fund_client.FundClient", return_value=fund_mock),
            respx.mock(assert_all_called=False) as rsx,
        ):
            rsx.get(url__regex=r"financialmodelingprep\.com").respond(403)
            result = refresh_peers("SBIN")

        assert result["peers_found"] == 3
        assert result["peers_cached"] == 3
        assert result["peers_fetched"] == 0
        fund_mock.fetch_valuation_snapshot.assert_not_called()

    def test_fetches_peer_when_not_cached(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """Peers without cache trigger yfinance + FMP fetch (both mocked)."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_links(s, "SBIN", [
                {"peer_symbol": "HDFCBANK", "score": 0.1},
                {"peer_symbol": "ICICIBANK", "score": 0.2},
                {"peer_symbol": "AXISBANK", "score": 0.3},
            ])
            _seed_snapshot(s, "SBIN", pe_trailing=9.5, market_cap=730000.0)

        fake_snap = ValuationSnapshot(
            symbol="HDFCBANK",
            date=date.today().isoformat(),
            price=1600.0,
            market_cap=900000.0,
            pe_trailing=18.0,
            pb_ratio=2.5,
            beta=0.9,
        )
        fund_mock = MagicMock()
        fund_mock.fetch_valuation_snapshot.return_value = fake_snap

        with (
            patch("flowtracker.fmp_client._load_api_key", return_value="test_key"),
            patch("flowtracker.fund_client.FundClient", return_value=fund_mock),
            patch("flowtracker.research.peer_refresh.time.sleep"),
            respx.mock(assert_all_called=False) as rsx,
        ):
            rsx.get(url__regex=r"financialmodelingprep\.com/api/v3/key-metrics.*").respond(
                200, json=[]
            )
            rsx.get(
                url__regex=r"financialmodelingprep\.com/api/v3/financial-growth.*"
            ).respond(200, json=[])
            result = refresh_peers("SBIN")

        assert result["peers_found"] == 3
        assert result["peers_fetched"] == 3
        assert result["peers_cached"] == 0
        assert fund_mock.fetch_valuation_snapshot.call_count == 3

    def test_fmp_init_failure_allows_fetch_to_continue(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """FileNotFoundError from FMPClient → fmp=None, yfinance still runs."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_links(s, "SBIN", [
                {"peer_symbol": "HDFCBANK", "score": 0.1},
                {"peer_symbol": "ICICIBANK", "score": 0.2},
                {"peer_symbol": "AXISBANK", "score": 0.3},
            ])

        fake_snap = ValuationSnapshot(
            symbol="HDFCBANK",
            date=date.today().isoformat(),
            price=1600.0,
            market_cap=900000.0,
        )
        fund_mock = MagicMock()
        fund_mock.fetch_valuation_snapshot.return_value = fake_snap

        fmp_ctor = MagicMock(side_effect=FileNotFoundError("fmp.env missing"))

        with (
            patch("flowtracker.fmp_client.FMPClient", fmp_ctor),
            patch("flowtracker.fund_client.FundClient", return_value=fund_mock),
            patch("flowtracker.research.peer_refresh.time.sleep"),
        ):
            result = refresh_peers("SBIN")

        assert result["peers_fetched"] == 3
        fmp_ctor.assert_called_once()
        assert fund_mock.fetch_valuation_snapshot.call_count == 3

    def test_yfinance_exception_is_swallowed(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """yfinance raising does not break the pipeline — peers still counted fetched."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_links(s, "SBIN", [
                {"peer_symbol": "HDFCBANK", "score": 0.1},
                {"peer_symbol": "ICICIBANK", "score": 0.2},
                {"peer_symbol": "AXISBANK", "score": 0.3},
            ])

        fund_mock = MagicMock()
        fund_mock.fetch_valuation_snapshot.side_effect = RuntimeError("yfinance blew up")

        with (
            patch("flowtracker.fmp_client._load_api_key", return_value="test_key"),
            patch("flowtracker.fund_client.FundClient", return_value=fund_mock),
            patch("flowtracker.research.peer_refresh.time.sleep"),
            respx.mock(assert_all_called=False) as rsx,
        ):
            rsx.get(url__regex=r"financialmodelingprep\.com").respond(200, json=[])
            result = refresh_peers("SBIN")

        assert result["peers_fetched"] == 3
        assert result["peers_skipped"] == 0
