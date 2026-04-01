"""Tests for consensus_estimates and earnings_surprises store methods."""

from __future__ import annotations

from flowtracker.store import FlowStore
from flowtracker.estimates_models import ConsensusEstimate, EarningsSurprise
from tests.fixtures.factories import make_consensus_estimate, make_earnings_surprises


# -- upsert + get round-trips --


def test_upsert_and_get_estimate_latest(store: FlowStore):
    """Upsert a consensus estimate and retrieve it by symbol."""
    est = make_consensus_estimate("SBIN")
    count = store.upsert_consensus_estimates([est])
    assert count >= 1

    result = store.get_estimate_latest("SBIN")
    assert result is not None
    assert result.symbol == "SBIN"
    assert result.target_mean == est.target_mean
    assert result.num_analysts == est.num_analysts
    assert result.recommendation == "buy"


def test_get_estimate_latest_returns_most_recent(store: FlowStore):
    """When multiple dates exist, latest date is returned."""
    old = ConsensusEstimate(
        symbol="SBIN", date="2025-12-01", target_mean=800.0,
        target_median=790.0, target_high=900.0, target_low=700.0,
        num_analysts=20, recommendation="hold", recommendation_score=3.0,
        forward_pe=10.0, forward_eps=80.0, eps_current_year=75.0,
        eps_next_year=85.0, earnings_growth=10.0, current_price=750.0,
    )
    new = make_consensus_estimate("SBIN")  # date=2026-03-28
    store.upsert_consensus_estimates([old, new])

    result = store.get_estimate_latest("SBIN")
    assert result is not None
    assert result.date == "2026-03-28"
    assert result.target_mean == new.target_mean


def test_get_estimate_latest_empty_db(store: FlowStore):
    """Returns None when no estimates exist for symbol."""
    assert store.get_estimate_latest("UNKNOWN") is None


def test_get_all_latest_estimates(store: FlowStore):
    """Returns latest estimate per symbol, all symbols covered."""
    sbin = make_consensus_estimate("SBIN")
    infy = make_consensus_estimate("INFY")
    store.upsert_consensus_estimates([sbin, infy])

    results = store.get_all_latest_estimates()
    symbols = {r.symbol for r in results}
    assert "SBIN" in symbols
    assert "INFY" in symbols
    assert len(results) == 2


def test_get_all_latest_estimates_empty_db(store: FlowStore):
    """Returns empty list when no estimates exist."""
    assert store.get_all_latest_estimates() == []


# -- earnings surprises --


def test_upsert_and_get_surprises(store: FlowStore):
    """Upsert earnings surprises and retrieve by symbol."""
    surprises = make_earnings_surprises("SBIN", n=4)
    count = store.upsert_earnings_surprises(surprises)
    assert count >= 4

    result = store.get_surprises("SBIN")
    assert len(result) == 4
    # Should be ordered by quarter_end DESC
    assert result[0].quarter_end >= result[-1].quarter_end
    assert result[0].symbol == "SBIN"


def test_get_surprises_empty_db(store: FlowStore):
    """Returns empty list when no surprises exist for symbol."""
    assert store.get_surprises("UNKNOWN") == []


def test_get_recent_surprises_date_filter(store: FlowStore):
    """get_recent_surprises filters by quarter_end relative to now."""
    surprises = make_earnings_surprises("SBIN", n=4)
    store.upsert_earnings_surprises(surprises)

    # With a very large window, should return all
    result = store.get_recent_surprises(days=3650)
    assert len(result) == 4

    # With a very small window (1 day), likely returns 0 since quarters are in 2025
    result_narrow = store.get_recent_surprises(days=1)
    assert len(result_narrow) == 0


def test_get_recent_surprises_ordered_by_abs_surprise(store: FlowStore):
    """Results are ordered by absolute surprise percentage DESC."""
    surprises = make_earnings_surprises("SBIN", n=4)
    store.upsert_earnings_surprises(surprises)

    result = store.get_recent_surprises(days=3650)
    if len(result) >= 2:
        # Verify ordering by absolute surprise_pct DESC
        for i in range(len(result) - 1):
            assert abs(result[i].surprise_pct or 0) >= abs(result[i + 1].surprise_pct or 0)


def test_upsert_consensus_estimates_idempotent(store: FlowStore):
    """Upserting same data twice doesn't create duplicates."""
    est = make_consensus_estimate("SBIN")
    store.upsert_consensus_estimates([est])
    store.upsert_consensus_estimates([est])

    result = store.get_all_latest_estimates()
    assert len(result) == 1
