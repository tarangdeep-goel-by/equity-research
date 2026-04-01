"""Tests for the composite screening engine (screener_engine.py).

Tests the 8-factor scoring system: ownership, insider, valuation,
earnings, quality, delivery, estimates, risk — plus composite scoring
and screen_all ranking.
"""

from __future__ import annotations

import pytest

from flowtracker.screener_engine import ScreenerEngine, _clamp
from flowtracker.screener_models import FactorScore, StockScore
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# _clamp helper
# ---------------------------------------------------------------------------

class TestClamp:
    def test_clamp_within_range(self):
        assert _clamp(50.0) == 50.0

    def test_clamp_below_zero(self):
        assert _clamp(-10.0) == 0.0

    def test_clamp_above_hundred(self):
        assert _clamp(150.0) == 100.0

    def test_clamp_exact_boundaries(self):
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0


# ---------------------------------------------------------------------------
# score_stock — full composite
# ---------------------------------------------------------------------------

class TestScoreStock:
    def test_score_stock_returns_stock_score(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("SBIN")
        assert isinstance(result, StockScore)
        assert result.symbol == "SBIN"

    def test_composite_in_range(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("SBIN")
        assert 0 <= result.composite_score <= 100

    def test_all_eight_factors_present(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("SBIN")
        factor_names = {f.factor for f in result.factors}
        expected = {"ownership", "insider", "valuation", "earnings", "quality", "delivery", "estimates", "risk"}
        assert factor_names == expected

    def test_each_factor_score_in_range(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("SBIN")
        for f in result.factors:
            # -1 means no data, otherwise 0-100
            assert f.score == -1 or (0 <= f.score <= 100), f"{f.factor} score {f.score} out of range"

    def test_company_info_populated(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("SBIN")
        assert result.company_name == "State Bank of India"
        assert result.industry == "Banks"

    def test_unknown_symbol_returns_score(self, populated_store: FlowStore):
        """Unknown symbol should still return a StockScore — factors will be -1 (no data)."""
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("NONEXIST")
        assert isinstance(result, StockScore)
        assert result.symbol == "NONEXIST"

    def test_unknown_symbol_most_factors_negative(self, populated_store: FlowStore):
        """Most factors should be -1 for a symbol with no data.
        Risk is an exception — it starts at 70 (no risk = good) even without data."""
        engine = ScreenerEngine(populated_store)
        result = engine.score_stock("NONEXIST")
        no_data_factors = [f for f in result.factors if f.factor != "risk"]
        for f in no_data_factors:
            assert f.score == -1, f"{f.factor} should be -1 for unknown symbol"
        # Risk factor starts at 70 even with no data
        risk = next(f for f in result.factors if f.factor == "risk")
        assert risk.score >= 60

    def test_weight_redistribution_on_missing_factors(self, store: FlowStore):
        """When some factors have no data, remaining factors redistribute weight."""
        from tests.fixtures.factories import (
            make_index_constituents,
            make_valuation_snapshots,
            make_consensus_estimate,
        )
        store.upsert_index_constituents(make_index_constituents())
        store.upsert_valuation_snapshots(make_valuation_snapshots("SBIN"))
        store.upsert_consensus_estimates([make_consensus_estimate("SBIN")])

        engine = ScreenerEngine(store)
        result = engine.score_stock("SBIN")
        # Composite should still be a valid score despite missing factors
        assert 0 <= result.composite_score <= 100
        # At least some factors should be -1 (no data)
        no_data_count = sum(1 for f in result.factors if f.score == -1)
        assert no_data_count > 0


# ---------------------------------------------------------------------------
# Individual factor scoring
# ---------------------------------------------------------------------------

class TestOwnershipFactor:
    def test_ownership_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_ownership("SBIN")
        assert f.factor == "ownership"
        assert 0 <= f.score <= 100

    def test_ownership_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_ownership("NONEXIST")
        assert f.score == -1
        assert f.detail == "No data"


class TestInsiderFactor:
    def test_insider_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_insider("SBIN")
        assert f.factor == "insider"
        assert 0 <= f.score <= 100

    def test_insider_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_insider("NONEXIST")
        assert f.score == -1


class TestValuationFactor:
    def test_valuation_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_valuation("SBIN")
        assert f.factor == "valuation"
        assert 0 <= f.score <= 100

    def test_valuation_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_valuation("NONEXIST")
        assert f.score == -1


class TestEarningsFactor:
    def test_earnings_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_earnings("SBIN")
        assert f.factor == "earnings"
        assert 0 <= f.score <= 100

    def test_earnings_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_earnings("NONEXIST")
        assert f.score == -1


class TestQualityFactor:
    def test_quality_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_quality("SBIN")
        assert f.factor == "quality"
        assert 0 <= f.score <= 100

    def test_quality_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_quality("NONEXIST")
        assert f.score == -1


class TestDeliveryFactor:
    def test_delivery_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_delivery("SBIN")
        assert f.factor == "delivery"
        assert 0 <= f.score <= 100

    def test_delivery_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_delivery("NONEXIST")
        assert f.score == -1


class TestEstimatesFactor:
    def test_estimates_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_estimates("SBIN")
        assert f.factor == "estimates"
        assert 0 <= f.score <= 100

    def test_estimates_no_data(self, store: FlowStore):
        engine = ScreenerEngine(store)
        f = engine._score_estimates("NONEXIST")
        assert f.score == -1


class TestRiskFactor:
    def test_risk_score_with_data(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        f = engine._score_risk("SBIN")
        assert f.factor == "risk"
        assert 0 <= f.score <= 100

    def test_risk_starts_positive(self, store: FlowStore):
        """Risk starts at 70 (no risk = good). With no pledge/FII data, should stay high."""
        engine = ScreenerEngine(store)
        f = engine._score_risk("NONEXIST")
        # No pledge data → pledge_pct=0, no holdings → fii_pct=0 → score ~70
        assert f.score >= 60


# ---------------------------------------------------------------------------
# screen_all
# ---------------------------------------------------------------------------

class TestScreenAll:
    def test_screen_all_returns_ranked_list(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        results = engine.screen_all(symbols=["SBIN", "INFY"])
        assert len(results) == 2
        assert all(isinstance(r, StockScore) for r in results)
        # Should be sorted by composite descending
        assert results[0].composite_score >= results[1].composite_score

    def test_screen_all_ranks_assigned(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        results = engine.screen_all(symbols=["SBIN", "INFY"])
        assert results[0].rank == 1
        assert results[1].rank == 2

    def test_screen_all_single_factor_sort(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        results = engine.screen_all(symbols=["SBIN", "INFY"], factor="risk")
        # Should be sorted by risk factor score, not composite
        risk_scores = [
            next(f.score for f in r.factors if f.factor == "risk")
            for r in results
        ]
        assert risk_scores == sorted(risk_scores, reverse=True)

    def test_screen_all_empty_list(self, populated_store: FlowStore):
        engine = ScreenerEngine(populated_store)
        results = engine.screen_all(symbols=[])
        assert results == []
