"""Tests for the Historical Analog backtest harness (Part 3 Tier 2)."""

from __future__ import annotations

import pytest

from flowtracker.research.autoeval.backtest_historical_analog import (
    BacktestSample,
    realized_quartile_within_cohort,
    score_sample,
    stratified_sample,
    summarize_calibration,
)


def test_stratified_sampler_balances_outcome_buckets() -> None:
    """Sampler must draw from all three outcome buckets when available."""
    population = (
        [{"symbol": f"R{i}", "as_of_date": "2024-01-01", "return_12m_pct": 30,
          "outcome_label": "recovered"} for i in range(30)]
        + [{"symbol": f"S{i}", "as_of_date": "2024-01-01", "return_12m_pct": 5,
            "outcome_label": "sideways"} for i in range(30)]
        + [{"symbol": f"B{i}", "as_of_date": "2024-01-01", "return_12m_pct": -25,
            "outcome_label": "blew_up"} for i in range(30)]
    )
    sample = stratified_sample(population, n=15, seed=42)
    assert len(sample) == 15
    counts = {lbl: 0 for lbl in ("recovered", "sideways", "blew_up")}
    for row in sample:
        counts[row["outcome_label"]] += 1
    # Each bucket should get ~5 (n // 3 = 5)
    for lbl, c in counts.items():
        assert c >= 5, f"Bucket {lbl} only got {c} samples; expected >= 5"


def test_stratified_sampler_falls_back_when_bucket_empty() -> None:
    """Missing buckets should not crash; sampler tops up from what's there."""
    population = [
        {"symbol": f"R{i}", "as_of_date": "2024-01-01", "return_12m_pct": 30,
         "outcome_label": "recovered"} for i in range(20)
    ]
    sample = stratified_sample(population, n=10, seed=42)
    assert len(sample) == 10
    assert all(s["outcome_label"] == "recovered" for s in sample)


def test_realized_quartile_math() -> None:
    cohort = [-20.0, -10.0, 0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    # -20 is the min — bottom quartile
    assert realized_quartile_within_cohort(-20.0, cohort) == 1
    # 50 is the max — top quartile
    assert realized_quartile_within_cohort(50.0, cohort) == 4
    # 10 → pct = 4/8 = 0.5 → quartile 2 (boundary handling)
    assert realized_quartile_within_cohort(10.0, cohort) == 2
    # Empty cohort returns 0 sentinel
    assert realized_quartile_within_cohort(5.0, []) == 0


def test_score_sample_downside_thicker_hit() -> None:
    """Agent calls downside: Thicker, realized lands in bottom quartile → hit."""
    sample_meta = {
        "symbol": "ABC", "as_of_date": "2024-01-01", "return_12m_pct": -30.0,
    }
    briefing = {
        "directional_adjustments": {"upside": "Thinner", "base": "Unchanged", "downside": "Thicker"},
        "top_analogs": [
            {"return_12m_pct": -10}, {"return_12m_pct": 5},
            {"return_12m_pct": 15}, {"return_12m_pct": 35},
        ],
    }
    result = score_sample(sample_meta, briefing)
    assert result.realized_quartile == 1
    assert result.downside_hit is True
    # Upside: Thinner call + realized NOT in top quartile → hit
    assert result.upside_hit is True


def test_score_sample_downside_thicker_miss() -> None:
    """Agent calls downside: Thicker, realized lands in top quartile → miss."""
    sample_meta = {
        "symbol": "ABC", "as_of_date": "2024-01-01", "return_12m_pct": 60.0,
    }
    briefing = {
        "directional_adjustments": {"upside": "Thinner", "base": "Unchanged", "downside": "Thicker"},
        "top_analogs": [
            {"return_12m_pct": -10}, {"return_12m_pct": 5},
            {"return_12m_pct": 15}, {"return_12m_pct": 35},
        ],
    }
    result = score_sample(sample_meta, briefing)
    assert result.realized_quartile == 4
    assert result.downside_hit is False
    # Upside: Thinner + realized IN top quartile → miss
    assert result.upside_hit is False


def test_summarize_calibration_hit_rate_and_threshold() -> None:
    """Calibration summary computes per-direction hit rates + pass/fail."""
    # 4 samples: agent said downside:Thicker, 3 of 4 landed in quartile 1
    samples = [
        BacktestSample(symbol=f"S{i}", as_of_date="2024-01-01",
                       realized_12m_pct=-20 if i < 3 else 20,
                       realized_quartile=1 if i < 3 else 4,
                       directional_call={"downside": "Thicker", "upside": "Unchanged", "base": "Unchanged"},
                       downside_hit=(i < 3))
        for i in range(4)
    ]
    cal = summarize_calibration(samples)
    assert "downside_Thicker" in cal
    assert cal["downside_Thicker"]["n"] == 4
    assert cal["downside_Thicker"]["hit_rate"] == pytest.approx(0.75)
    # 75% >> 0.35 threshold → pass
    assert cal["downside_Thicker"]["passed"] is True
