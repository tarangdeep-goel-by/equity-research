"""E2E tests: full screener pipeline from populated store to ranked scores.

Uses populated_store with SBIN + INFY data. Tests the ScreenerEngine's
score_stock and screen_all flows end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.screener_engine import ScreenerEngine
from flowtracker.screener_models import StockScore
from flowtracker.store import FlowStore


class TestScreenAllPipeline:
    def test_screen_all_produces_ranked_scores(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        engine = ScreenerEngine(populated_store)
        scores = engine.screen_all(symbols=["SBIN", "INFY"])

        assert len(scores) == 2
        for s in scores:
            assert isinstance(s, StockScore)
            assert 0 <= s.composite_score <= 100
            assert s.rank > 0

    def test_single_stock_scoring(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        engine = ScreenerEngine(populated_store)
        score = engine.score_stock("SBIN")

        assert score is not None
        assert score.symbol == "SBIN"
        assert len(score.factors) == 8
        factor_names = {f.factor for f in score.factors}
        expected = {"ownership", "insider", "valuation", "earnings", "quality", "delivery", "estimates", "risk"}
        assert factor_names == expected

    def test_composite_sort_order(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        engine = ScreenerEngine(populated_store)
        scores = engine.screen_all(symbols=["SBIN", "INFY"])

        # Verify descending sort by composite
        composites = [s.composite_score for s in scores]
        assert composites == sorted(composites, reverse=True)

    def test_rank_assignment(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        engine = ScreenerEngine(populated_store)
        scores = engine.screen_all(symbols=["SBIN", "INFY"])

        ranks = [s.rank for s in scores]
        assert ranks == [1, 2]

    def test_factor_sort(self, tmp_db: Path, populated_store: FlowStore, monkeypatch):
        """Sorting by a single factor re-orders by that factor's score."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        engine = ScreenerEngine(populated_store)
        scores = engine.screen_all(symbols=["SBIN", "INFY"], factor="risk")

        risk_scores = [
            next(f.score for f in s.factors if f.factor == "risk")
            for s in scores
        ]
        assert risk_scores == sorted(risk_scores, reverse=True)
