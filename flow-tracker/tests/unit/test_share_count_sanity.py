"""Tests for share_count_sanity — Screener-vs-yfinance share-count divergence.

Covers single-symbol checks (within threshold, over threshold, NESTLEIND-class
2x bug, missing-side cases) and the universe scanner's sort + filtering.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flowtracker.share_count_sanity import (
    check_share_count_divergence,
    scan_universe_divergence,
)
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _populate_screener_shares(store: FlowStore, symbol: str, shares: float) -> None:
    """Seed quarterly_balance_sheet so _get_screener_shares finds it."""
    store.upsert_quarterly_balance_sheet(
        symbol,
        [
            {
                "quarter_end": "2026-03-31",
                "shares_outstanding": shares,
            }
        ],
    )


def _seed_company_snapshot(store: FlowStore, symbol: str) -> None:
    """Insert a minimal company_snapshot row so universe scan picks it up."""
    store.upsert_snapshot_screener(
        symbol,
        {
            "name": symbol,
            "cmp": 100.0,
            "market_cap": 10000.0,
            "pe_trailing": 20.0,
            "roce": 15.0,
            "sales_qtr": 500.0,
            "qtr_sales_var": 5.0,
            "np_qtr": 50.0,
            "qtr_profit_var": 5.0,
        },
    )


def _mock_yf_ticker(shares: float | None):
    """Build a patched yf.Ticker side_effect returning the given shares value."""
    def _factory(_symbol):
        t = MagicMock()
        t.info = {"sharesOutstanding": shares} if shares is not None else {}
        return t
    return _factory


# ---------------------------------------------------------------------------
# Single-symbol divergence
# ---------------------------------------------------------------------------

class TestCheckShareCountDivergence:
    def test_within_threshold_not_flagged(self, store: FlowStore):
        # 893M Screener vs 900M yfinance -> ~0.78% divergence
        _populate_screener_shares(store, "SBIN", 893_000_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(900_000_000)):
            result = check_share_count_divergence("SBIN", store=store)

        assert result["symbol"] == "SBIN"
        assert result["screener_shares"] == 893_000_000
        assert result["yfinance_shares"] == 900_000_000
        assert result["divergence_pct"] < 1.0
        assert result["flagged"] is False

    def test_over_threshold_flagged(self, store: FlowStore):
        # 100M vs 120M -> 16.67% divergence (> default 10%)
        _populate_screener_shares(store, "TESTCO", 100_000_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(120_000_000)):
            result = check_share_count_divergence("TESTCO", store=store)

        assert result["flagged"] is True
        assert result["divergence_pct"] == pytest.approx(16.6666, rel=1e-3)

    def test_nestleind_class_2x_bug_flagged(self, store: FlowStore):
        # Classic NESTLEIND-pattern: one source has 2x the other
        # 96.4M Screener vs 192.8M yfinance -> 50% divergence (max-denom formula)
        _populate_screener_shares(store, "NESTLEIND", 96_415_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(192_830_000)):
            result = check_share_count_divergence("NESTLEIND", store=store)

        assert result["flagged"] is True
        assert result["divergence_pct"] == pytest.approx(50.0, abs=0.01)

    def test_missing_screener_side(self, store: FlowStore):
        # No quarterly_balance_sheet row at all
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(500_000_000)):
            result = check_share_count_divergence("EMPTY", store=store)

        assert result == {"symbol": "EMPTY", "status": "missing_screener"}

    def test_missing_yfinance_side(self, store: FlowStore):
        _populate_screener_shares(store, "ONLYSCR", 100_000_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(None)):
            result = check_share_count_divergence("ONLYSCR", store=store)

        assert result == {"symbol": "ONLYSCR", "status": "missing_yfinance"}

    def test_both_missing(self, store: FlowStore):
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(None)):
            result = check_share_count_divergence("GHOST", store=store)

        assert result == {"symbol": "GHOST", "status": "both_missing"}

    def test_threshold_override(self, store: FlowStore):
        # 16.67% divergence: flagged at default 10%, NOT flagged at 25%
        _populate_screener_shares(store, "BORDER", 100_000_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(120_000_000)):
            result = check_share_count_divergence(
                "BORDER", threshold_pct=25.0, store=store
            )

        assert result["flagged"] is False

    def test_symbol_uppercased(self, store: FlowStore):
        _populate_screener_shares(store, "TCS", 100_000_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(101_000_000)):
            result = check_share_count_divergence("tcs", store=store)
        assert result["symbol"] == "TCS"


# ---------------------------------------------------------------------------
# Universe scan
# ---------------------------------------------------------------------------

class TestScanUniverseDivergence:
    def test_default_universe_is_company_snapshot(self, store: FlowStore):
        _seed_company_snapshot(store, "AAA")
        _seed_company_snapshot(store, "BBB")
        _populate_screener_shares(store, "AAA", 100_000_000)
        _populate_screener_shares(store, "BBB", 200_000_000)

        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(101_000_000)):
            results = scan_universe_divergence(store=store)

        symbols = {r["symbol"] for r in results}
        assert symbols == {"AAA", "BBB"}

    def test_sorted_by_divergence_desc(self, store: FlowStore):
        # Three stocks with increasing divergence
        _seed_company_snapshot(store, "LOW")
        _seed_company_snapshot(store, "MID")
        _seed_company_snapshot(store, "HIGH")
        _populate_screener_shares(store, "LOW", 100_000_000)
        _populate_screener_shares(store, "MID", 100_000_000)
        _populate_screener_shares(store, "HIGH", 100_000_000)

        # yfinance returns same number for all (mocked) — flip per-call
        yfinance_values = {
            "LOW.NS": 101_000_000,    # ~1% div
            "MID.NS": 120_000_000,    # ~16.7% div
            "HIGH.NS": 200_000_000,   # 50% div
        }

        def factory(sym):
            t = MagicMock()
            t.info = {"sharesOutstanding": yfinance_values[sym]}
            return t

        with patch("flowtracker.share_count_sanity.yf.Ticker", side_effect=factory):
            results = scan_universe_divergence(store=store)

        symbols_in_order = [r["symbol"] for r in results]
        assert symbols_in_order == ["HIGH", "MID", "LOW"]

    def test_missing_data_rows_sort_to_end(self, store: FlowStore):
        _seed_company_snapshot(store, "GOOD")
        _seed_company_snapshot(store, "MISSING")
        _populate_screener_shares(store, "GOOD", 100_000_000)
        # MISSING has no quarterly_balance_sheet row

        def factory(sym):
            t = MagicMock()
            t.info = {"sharesOutstanding": 200_000_000}
            return t

        with patch("flowtracker.share_count_sanity.yf.Ticker", side_effect=factory):
            results = scan_universe_divergence(store=store)

        assert results[0]["symbol"] == "GOOD"
        assert results[-1]["symbol"] == "MISSING"
        assert results[-1]["status"] == "missing_screener"

    def test_explicit_symbol_list(self, store: FlowStore):
        # Universe is empty but we pass an explicit list
        _populate_screener_shares(store, "EXPLICIT", 100_000_000)
        with patch("flowtracker.share_count_sanity.yf.Ticker",
                   side_effect=_mock_yf_ticker(101_000_000)):
            results = scan_universe_divergence(symbols=["EXPLICIT"], store=store)
        assert len(results) == 1
        assert results[0]["symbol"] == "EXPLICIT"
