"""Tests for flowtracker.research.peer_refresh.

Covers:
- _resolve_peer_symbol: all three resolution strategies + failure.
- _has_fmp_data / _has_fresh_valuation: DB cache checks.
- _get_latest_metric: peer_comparison vs date-ordered tables, bad columns.
- _compute_benchmarks: metric iteration and sector_benchmarks upsert.
- refresh_peers end-to-end: empty peers, cached peers, fetch path with
  yfinance + FMP mocking, FMP init failure (403-like), benchmark counts.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from flowtracker.fund_models import ValuationSnapshot
from flowtracker.research.peer_refresh import (
    _BENCHMARK_METRICS,
    _compute_benchmarks,
    _get_latest_metric,
    _has_fmp_data,
    _has_fresh_valuation,
    _resolve_peer_symbol,
    refresh_peers,
)
from flowtracker.scan_models import IndexConstituent
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_peer_comparison(store: FlowStore, symbol: str, peers: list[dict]) -> int:
    """Insert rows into peer_comparison for a subject symbol."""
    return store.upsert_peers(symbol, peers)


def _seed_valuation_today(
    store: FlowStore, symbol: str, *, days_ago: int = 0, pe: float = 10.0
) -> None:
    """Insert a valuation_snapshot row N days ago."""
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
# _resolve_peer_symbol
# ---------------------------------------------------------------------------

class TestResolvePeerSymbol:
    """Symbol resolution has 3 branches: explicit, index lookup, ticker-like fallback."""

    def test_uses_explicit_peer_symbol(self, store: FlowStore):
        """peer_symbol set → used directly, exchange suffix stripped."""
        peer = {"peer_symbol": "RELIANCE.NS", "peer_name": "Reliance Industries"}
        assert _resolve_peer_symbol(peer, store._conn) == "RELIANCE"

    def test_strips_bo_suffix(self, store: FlowStore):
        """BSE .BO suffix also gets stripped."""
        peer = {"peer_symbol": "TCS.BO", "peer_name": "TCS"}
        assert _resolve_peer_symbol(peer, store._conn) == "TCS"

    def test_falls_back_to_index_constituents(self, store: FlowStore):
        """No peer_symbol → look up name in index_constituents."""
        store.upsert_index_constituents([
            IndexConstituent(
                symbol="INFY",
                index_name="NIFTY 50",
                company_name="Infosys Ltd",
                industry="IT - Software",
            ),
        ])
        peer = {"peer_symbol": None, "peer_name": "Infosys"}
        assert _resolve_peer_symbol(peer, store._conn) == "INFY"

    def test_returns_none_for_empty_name(self, store: FlowStore):
        """No peer_symbol and empty peer_name → None."""
        peer = {"peer_symbol": None, "peer_name": ""}
        assert _resolve_peer_symbol(peer, store._conn) is None

    def test_ticker_like_fallback(self, store: FlowStore):
        """No symbol, no index match, but name matches ticker regex."""
        peer = {"peer_symbol": None, "peer_name": "NAUKRI"}
        assert _resolve_peer_symbol(peer, store._conn) == "NAUKRI"

    def test_returns_none_when_no_match(self, store: FlowStore):
        """Company-like name that's not in constituents and not a ticker → None."""
        peer = {"peer_symbol": None, "peer_name": "Some Random Company Ltd"}
        assert _resolve_peer_symbol(peer, store._conn) is None


# ---------------------------------------------------------------------------
# _has_fmp_data / _has_fresh_valuation
# ---------------------------------------------------------------------------

class TestCacheChecks:
    """Cache-hit predicates used to skip network fetches."""

    def test_has_fmp_data_true_when_row_exists(self, populated_store: FlowStore):
        """populated_store seeds fmp_key_metrics for SBIN → cache hit."""
        assert _has_fmp_data(populated_store._conn, "fmp_key_metrics", "SBIN") is True

    def test_has_fmp_data_false_when_empty(self, store: FlowStore):
        """Empty table → False."""
        assert _has_fmp_data(store._conn, "fmp_key_metrics", "SBIN") is False

    def test_has_fresh_valuation_today(self, store: FlowStore):
        """Snapshot today → fresh (within 7 days)."""
        _seed_valuation_today(store, "SBIN", days_ago=0)
        assert _has_fresh_valuation(store._conn, "SBIN", days=7) is True

    def test_has_fresh_valuation_stale(self, store: FlowStore):
        """Snapshot 10 days old → not fresh with 7-day window."""
        _seed_valuation_today(store, "SBIN", days_ago=10)
        assert _has_fresh_valuation(store._conn, "SBIN", days=7) is False

    def test_has_fresh_valuation_no_row(self, store: FlowStore):
        """No snapshot at all → False."""
        assert _has_fresh_valuation(store._conn, "NOPE", days=7) is False


# ---------------------------------------------------------------------------
# _get_latest_metric
# ---------------------------------------------------------------------------

class TestGetLatestMetric:
    """Metric readers handle peer_comparison, valuation_snapshot, and fmp_* tables."""

    def test_peer_comparison_by_peer_symbol(self, store: FlowStore):
        """For peers, value is looked up via peer_symbol column."""
        _seed_peer_comparison(store, "SBIN", [
            {"name": "HDFC Bank", "peer_symbol": "HDFCBANK", "pe": 18.5, "market_cap": 900000.0},
        ])
        val = _get_latest_metric(store._conn, "peer_comparison", "pe", "HDFCBANK")
        assert val == pytest.approx(18.5)

    def test_peer_comparison_missing_returns_none(self, store: FlowStore):
        """No peer row for this symbol → None."""
        assert _get_latest_metric(store._conn, "peer_comparison", "pe", "NOPE") is None

    def test_valuation_snapshot_uses_latest_date(self, store: FlowStore):
        """Picks the most recent row by date."""
        _seed_valuation_today(store, "SBIN", days_ago=5, pe=8.0)
        _seed_valuation_today(store, "SBIN", days_ago=0, pe=9.5)
        val = _get_latest_metric(store._conn, "valuation_snapshot", "pe_trailing", "SBIN")
        assert val == pytest.approx(9.5)

    def test_fmp_table_returns_value(self, populated_store: FlowStore):
        """populated_store seeds fmp_key_metrics.roe=18.5 for SBIN."""
        val = _get_latest_metric(populated_store._conn, "fmp_key_metrics", "roe", "SBIN")
        assert val == pytest.approx(18.5)

    def test_bad_column_swallows_error(self, store: FlowStore):
        """Non-existent column → exception caught → None returned."""
        # _BENCHMARK_METRICS declares valuation_snapshot.profit_margins which doesn't
        # exist on the schema — the broad except in _get_latest_metric must handle it.
        _seed_valuation_today(store, "SBIN")
        assert _get_latest_metric(store._conn, "valuation_snapshot", "profit_margins", "SBIN") is None

    def test_null_value_returns_none(self, store: FlowStore):
        """Row exists but column is NULL → None."""
        _seed_peer_comparison(store, "SBIN", [
            {"name": "X", "peer_symbol": "XPEER", "pe": None, "market_cap": 5000.0},
        ])
        assert _get_latest_metric(store._conn, "peer_comparison", "pe", "XPEER") is None


# ---------------------------------------------------------------------------
# _compute_benchmarks
# ---------------------------------------------------------------------------

class TestComputeBenchmarks:
    """Benchmark computation iterates _BENCHMARK_METRICS and writes sector_benchmarks."""

    def test_benchmarks_written_for_available_metrics(self, store: FlowStore):
        """Subject + peer data present → sector_benchmarks populated with median/pct."""
        # Seed the subject
        _seed_peer_comparison(store, "SBIN", [
            {"name": "HDFC Bank", "peer_symbol": "HDFCBANK", "pe": 18.0, "market_cap": 900000.0,
             "roce": 16.0, "div_yield": 1.2},
            {"name": "ICICI Bank", "peer_symbol": "ICICIBANK", "pe": 17.0, "market_cap": 700000.0,
             "roce": 17.5, "div_yield": 0.8},
        ])
        # Subject row needs to live in peer_comparison keyed by peer_symbol=SBIN too,
        # because _get_latest_metric always reads peer_comparison via peer_symbol.
        # Seed by linking SBIN as a peer-of-peers (any parent symbol works).
        store.upsert_peers("PARENT", [
            {"name": "SBI", "peer_symbol": "SBIN", "pe": 9.5, "market_cap": 730000.0,
             "roce": 18.0, "div_yield": 1.5},
        ])

        count = _compute_benchmarks(store, "SBIN", ["HDFCBANK", "ICICIBANK"], console=None)

        # At minimum, the 4 peer_comparison metrics should yield benchmarks
        assert count >= 4

        bench = store.get_sector_benchmark("SBIN", "pe")
        assert bench is not None
        assert bench["peer_count"] == 2
        assert bench["sector_median"] == pytest.approx(17.5)
        # SBIN pe=9.5, both peers higher → percentile 0
        assert bench["percentile"] == pytest.approx(0.0)

    def test_skips_metrics_with_no_data(self, store: FlowStore):
        """No rows anywhere → no benchmarks written."""
        count = _compute_benchmarks(store, "EMPTY", ["ALSO_EMPTY"], console=None)
        assert count == 0
        assert store.get_sector_benchmark("EMPTY", "pe") is None

    def test_benchmark_metrics_registry_shape(self):
        """Sanity-check the metric registry — required for downstream iteration."""
        assert len(_BENCHMARK_METRICS) > 10
        for metric, table, column in _BENCHMARK_METRICS:
            assert isinstance(metric, str) and metric
            assert table in {"peer_comparison", "valuation_snapshot",
                             "fmp_key_metrics", "fmp_financial_growth"}
            assert isinstance(column, str) and column


# ---------------------------------------------------------------------------
# refresh_peers — end-to-end
# ---------------------------------------------------------------------------

class TestRefreshPeers:
    """High-level orchestration including caching + yfinance + FMP mocking."""

    def _point_flowstore_at(self, monkeypatch: pytest.MonkeyPatch, tmp_db) -> None:
        """Force refresh_peers' FlowStore() to use the test DB."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

    def test_returns_zeros_when_no_peers(self, tmp_db, monkeypatch: pytest.MonkeyPatch):
        """No rows in peer_comparison → early-return dict with zeros."""
        self._point_flowstore_at(monkeypatch, tmp_db)
        # Stub FMPClient init so missing fmp.env doesn't matter on the early-return path.
        with patch("flowtracker.fmp_client._load_api_key", return_value="test_key"):
            result = refresh_peers("NOPEERS")
        assert result == {
            "peers_found": 0,
            "peers_fetched": 0,
            "peers_cached": 0,
            "peers_skipped": 0,
            "benchmarks_computed": 0,
        }

    def test_skips_peers_with_fresh_cache(self, tmp_db, monkeypatch: pytest.MonkeyPatch):
        """A peer with a fresh valuation_snapshot is counted as cached, no fetch."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        # Seed peer_comparison + cached valuation for the peer
        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_comparison(s, "SBIN", [
                {"name": "HDFC Bank", "peer_symbol": "HDFCBANK", "pe": 18.0,
                 "market_cap": 900000.0},
            ])
            _seed_valuation_today(s, "HDFCBANK", days_ago=0)

        # FMP and Fund clients should NOT be hit because the peer is cached.
        fund_mock = MagicMock()
        with (
            patch("flowtracker.fmp_client._load_api_key", return_value="test_key"),
            patch("flowtracker.fund_client.FundClient", return_value=fund_mock),
            respx.mock(assert_all_called=False) as rsx,
        ):
            # Any FMP call that *did* happen would 403 — proves we didn't call it.
            rsx.get(url__regex=r"financialmodelingprep\.com").respond(403)
            result = refresh_peers("SBIN")

        assert result["peers_found"] == 1
        assert result["peers_cached"] == 1
        assert result["peers_fetched"] == 0
        fund_mock.fetch_valuation_snapshot.assert_not_called()

    def test_fetches_peer_when_not_cached(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """Peer without cache triggers yfinance + FMP fetch (both mocked)."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_comparison(s, "SBIN", [
                {"name": "HDFC Bank", "peer_symbol": "HDFCBANK", "pe": 18.0,
                 "market_cap": 900000.0, "roce": 16.0, "div_yield": 1.2},
            ])
            # Seed subject in peer_comparison too (as any parent's peer)
            s.upsert_peers("ANY", [
                {"name": "SBI", "peer_symbol": "SBIN", "pe": 9.5, "market_cap": 730000.0,
                 "roce": 18.0, "div_yield": 1.5},
            ])

        # Mock yfinance snapshot fetch
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
            patch("flowtracker.research.peer_refresh.time.sleep"),  # skip sleeps
            respx.mock(assert_all_called=False) as rsx,
        ):
            # FMP endpoints return empty → fetch path runs without errors but stores nothing.
            rsx.get(url__regex=r"financialmodelingprep\.com/api/v3/key-metrics.*").respond(
                200, json=[]
            )
            rsx.get(
                url__regex=r"financialmodelingprep\.com/api/v3/financial-growth.*"
            ).respond(200, json=[])
            result = refresh_peers("SBIN")

        assert result["peers_found"] == 1
        assert result["peers_fetched"] == 1
        assert result["peers_cached"] == 0
        fund_mock.fetch_valuation_snapshot.assert_called_once_with("HDFCBANK")
        # Benchmarks should have been computed for at least the Screener-peer metrics.
        assert result["benchmarks_computed"] >= 1

    def test_fmp_init_failure_allows_fetch_to_continue(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """FileNotFoundError from FMPClient → fmp=None, yfinance still runs."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_comparison(s, "SBIN", [
                {"name": "HDFC Bank", "peer_symbol": "HDFCBANK", "pe": 18.0,
                 "market_cap": 900000.0},
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

        assert result["peers_fetched"] == 1
        fmp_ctor.assert_called_once()  # attempted, failed gracefully
        fund_mock.fetch_valuation_snapshot.assert_called_once()

    def test_unresolvable_peer_is_skipped(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """A peer row with no peer_symbol and no match anywhere is dropped."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            # Raw dict insert so we can bypass upsert_peers' field remapping
            s._conn.execute(
                "INSERT INTO peer_comparison (symbol, peer_name, peer_symbol) "
                "VALUES (?, ?, ?)",
                ("SBIN", "Mystery Co Pvt Ltd", None),
            )
            s._conn.commit()

        with (
            patch("flowtracker.fmp_client._load_api_key", return_value="test_key"),
            patch("flowtracker.fund_client.FundClient", return_value=MagicMock()),
            patch("flowtracker.research.peer_refresh.time.sleep"),
        ):
            result = refresh_peers("SBIN")

        assert result["peers_found"] == 1
        # Not resolved → not fetched, not cached
        assert result["peers_fetched"] == 0
        assert result["peers_cached"] == 0

    def test_yfinance_exception_is_swallowed(
        self, tmp_db, monkeypatch: pytest.MonkeyPatch
    ):
        """yfinance raising does not break the pipeline — peer is still counted fetched."""
        self._point_flowstore_at(monkeypatch, tmp_db)

        with FlowStore(db_path=tmp_db) as s:
            _seed_peer_comparison(s, "SBIN", [
                {"name": "HDFC Bank", "peer_symbol": "HDFCBANK", "pe": 18.0,
                 "market_cap": 900000.0},
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

        # peer_refresh catches inner yfinance errors and continues, marking peer as fetched
        assert result["peers_fetched"] == 1
        assert result["peers_skipped"] == 0
