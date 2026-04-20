"""Tests for the Historical Analog Agent builder (Sprint 1).

Covers:
  - Feature-vector computation with strict as_of_date cutoff (no leakage).
  - Forward-return computation over adj_close (Sprint 0 dependency).
  - Outcome-label thresholds.
  - k-NN retrieval with industry + mcap hard filters.
  - Distance metric symmetry + z-score normalization.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seed_prices(store: FlowStore, symbol: str, series: list[tuple[str, float]]) -> None:
    """Seed daily_stock_data with chronologically realistic prev_close + adj_close."""
    rows: list[DailyStockData] = []
    prior: float | None = None
    for d, close in series:
        rows.append(DailyStockData(
            date=d, symbol=symbol, open=close, high=close, low=close, close=close,
            prev_close=prior if prior is not None else close,
            volume=1_000_000, turnover=close * 1_000_000,
            delivery_qty=500_000, delivery_pct=50.0,
        ))
        prior = close
    store.upsert_daily_stock_data(rows)
    # Populate adj_close since tests use raw-priced symbols (no actions)
    store.recompute_adj_close(symbol)


def _seed_shareholding(
    store: FlowStore, symbol: str, quarter_end: str, category: str, pct: float,
) -> None:
    store._conn.execute(
        "INSERT OR REPLACE INTO shareholding (symbol, quarter_end, category, percentage) "
        "VALUES (?, ?, ?, ?)",
        (symbol, quarter_end, category, pct),
    )
    store._conn.commit()


# ---------------------------------------------------------------------------
# Feature vector: leakage + shape
# ---------------------------------------------------------------------------

def test_feature_vector_shape_and_keys(store: FlowStore) -> None:
    from flowtracker.research.analog_builder import compute_feature_vector

    # Seed minimum data so the builder can populate most fields
    _seed_prices(store, "XYZ", [
        ((date(2024, 3, 31) - timedelta(days=i)).isoformat(), 100.0 + i * 0.1)
        for i in range(250)
    ])
    _seed_shareholding(store, "XYZ", "2024-03-31", "Promoter", 55.0)
    _seed_shareholding(store, "XYZ", "2024-03-31", "FII", 18.0)
    _seed_shareholding(store, "XYZ", "2024-03-31", "MF", 12.0)

    vec = compute_feature_vector(store, "XYZ", "2024-03-31")

    expected_keys = {
        "pe_trailing", "pe_percentile_10y",
        "roce_current", "roce_3yr_delta",
        "revenue_cagr_3yr", "opm_trend",
        "promoter_pct", "fii_pct", "fii_delta_2q",
        "mf_pct", "mf_delta_2q", "pledge_pct",
        "price_vs_sma200", "delivery_pct_6m", "rsi_14",
        "industry", "mcap_bucket",
    }
    assert expected_keys <= set(vec.keys()), f"Missing: {expected_keys - set(vec.keys())}"
    assert vec["promoter_pct"] == pytest.approx(55.0)
    assert vec["fii_pct"] == pytest.approx(18.0)


def test_feature_vector_no_leakage_past_as_of(store: FlowStore) -> None:
    """Computing features for (X, 2020-Q1) must only use data with date <= 2020-03-31."""
    from flowtracker.research.analog_builder import compute_feature_vector

    # Seed shareholding at 2 quarters prior (2019-09-30), 1 quarter prior, as_of, and post-as_of
    _seed_shareholding(store, "LEAK", "2019-09-30", "FII", 10.0)
    _seed_shareholding(store, "LEAK", "2019-12-31", "FII", 12.0)
    _seed_shareholding(store, "LEAK", "2020-03-31", "FII", 15.0)  # as_of
    _seed_shareholding(store, "LEAK", "2020-06-30", "FII", 25.0)  # AFTER as_of — must NOT appear
    _seed_shareholding(store, "LEAK", "2020-09-30", "FII", 30.0)  # future

    vec = compute_feature_vector(store, "LEAK", "2020-03-31")

    assert vec["fii_pct"] == pytest.approx(15.0), (
        f"Feature leaked future data. Got fii_pct={vec['fii_pct']}, expected 15.0"
    )
    # fii_delta_2q: 15 (as_of) − 10 (2q prior) = +5
    assert vec["fii_delta_2q"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Forward returns
# ---------------------------------------------------------------------------

def test_forward_returns_use_adj_close_not_raw(store: FlowStore) -> None:
    """Forward-return must read adj_close. Raw-close return across a split
    would be a phantom -50% on a true flat-performance stock."""
    from flowtracker.research.analog_builder import compute_forward_returns

    # Flat-economic-value stock with a 2:1 split in the middle
    as_of = (date.today() - timedelta(days=400)).isoformat()
    mid = (date.today() - timedelta(days=200)).isoformat()
    end_3m = (date.today() - timedelta(days=400 - 90)).isoformat()
    end_12m = (date.today() - timedelta(days=400 - 365)).isoformat()

    _seed_prices(store, "SPLIT1", [
        (as_of, 2000.0),
        (end_3m, 2000.0),
        (mid, 1000.0),   # post-split mechanical halving
        (end_12m, 1020.0),
    ])
    # Register the split between as_of and end_12m
    store.upsert_corporate_actions([{
        "symbol": "SPLIT1", "ex_date": mid,
        "action_type": "split", "multiplier": 2.0, "ratio_text": "2:1",
        "dividend_amount": None, "source": "bse",
    }])
    # upsert_corporate_actions auto-triggers recompute_adj_close via Sprint 0 hook

    rets = compute_forward_returns(store, "SPLIT1", as_of)

    # 3M horizon lands pre-split — both prices are raw 2000, return 0%
    assert abs(rets["return_3m_pct"]) < 2.0, (
        f"3M return {rets['return_3m_pct']}% — expected ~0% (pre-split both sides)"
    )
    # 12M horizon lands post-split. Raw: 2000→1020 = -49%. Adj: 1000→1020 = +2%.
    assert abs(rets["return_12m_pct"]) < 5.0, (
        f"12M return {rets['return_12m_pct']}% — expected ~0% (flat adj prices)"
    )


def test_outcome_label_thresholds(store: FlowStore) -> None:
    """recovered: +20%+ 12m. blew_up: -20%+ 12m. sideways: in between."""
    from flowtracker.research.analog_builder import classify_outcome

    assert classify_outcome(return_12m_pct=25.0) == "recovered"
    assert classify_outcome(return_12m_pct=-25.0) == "blew_up"
    assert classify_outcome(return_12m_pct=5.0) == "sideways"
    assert classify_outcome(return_12m_pct=-15.0) == "sideways"
    assert classify_outcome(return_12m_pct=None) is None


# ---------------------------------------------------------------------------
# k-NN retrieval
# ---------------------------------------------------------------------------

def test_retrieval_excludes_same_symbol_within_2yr(store: FlowStore) -> None:
    """Data leakage guard: target's own recent history can't be its own analog."""
    from flowtracker.research.analog_builder import retrieve_top_k_analogs

    # Seed two historical_states rows for the same symbol — one recent, one 3yr old
    today = date.today()
    recent_qtr = (today - timedelta(days=180)).isoformat()
    old_qtr = (today - timedelta(days=365 * 3)).isoformat()

    for qtr in [recent_qtr, old_qtr]:
        store._conn.execute(
            "INSERT INTO historical_states "
            "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
            " mf_pct, industry, mcap_bucket) "
            "VALUES (?, ?, 25.0, 20.0, 50.0, 15.0, 10.0, 'Chemicals', 'midcap')",
            ("TGT", qtr),
        )
    # Plus one peer row as a valid analog
    store._conn.execute(
        "INSERT INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
        " mf_pct, industry, mcap_bucket) "
        "VALUES ('PEER', ?, 25.0, 20.0, 50.0, 15.0, 10.0, 'Chemicals', 'midcap')",
        (recent_qtr,),
    )
    store._conn.commit()

    target_features = {
        "pe_trailing": 25.0, "roce_current": 20.0, "promoter_pct": 50.0,
        "fii_pct": 15.0, "mf_pct": 10.0, "industry": "Chemicals",
        "mcap_bucket": "midcap",
    }
    analogs = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=today.isoformat(),
        target_features=target_features, k=10,
    )

    symbols = [a["symbol"] for a in analogs]
    # Recent TGT row must be excluded (within 2 years)
    assert not any(a["symbol"] == "TGT" and a["quarter_end"] == recent_qtr for a in analogs)
    # Old TGT row (>2yr ago) is allowed
    # Peer row present
    assert "PEER" in symbols


def test_retrieval_industry_hard_filter(store: FlowStore) -> None:
    """Analogs must share industry (or adjacent) + mcap bucket."""
    from flowtracker.research.analog_builder import retrieve_top_k_analogs

    recent = (date.today() - timedelta(days=365 * 3)).isoformat()

    # Seed one chemicals peer and one pharma stranger — identical otherwise
    store._conn.executemany(
        "INSERT INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
        " mf_pct, industry, mcap_bucket) "
        "VALUES (?, ?, 25.0, 20.0, 50.0, 15.0, 10.0, ?, 'midcap')",
        [("CHEM1", recent, "Chemicals"), ("PHARMA1", recent, "Pharmaceuticals")],
    )
    store._conn.commit()

    target_features = {
        "pe_trailing": 25.0, "roce_current": 20.0, "promoter_pct": 50.0,
        "fii_pct": 15.0, "mf_pct": 10.0, "industry": "Chemicals",
        "mcap_bucket": "midcap",
    }
    analogs = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=date.today().isoformat(),
        target_features=target_features, k=10,
    )

    symbols = [a["symbol"] for a in analogs]
    assert "CHEM1" in symbols
    assert "PHARMA1" not in symbols, "Industry hard-filter leaked a pharma peer into chemicals cohort"


def test_distance_metric_symmetry_and_z_score(store: FlowStore) -> None:
    """Distance(a, b) == Distance(b, a); z-score normalizes feature scale so
    pe_trailing (5-50 range) doesn't dominate over pledge_pct (0-30 range)."""
    from flowtracker.research.analog_builder import feature_distance

    a = {"pe_trailing": 25.0, "roce_current": 20.0, "pledge_pct": 5.0}
    b = {"pe_trailing": 30.0, "roce_current": 22.0, "pledge_pct": 8.0}
    stds = {"pe_trailing": 10.0, "roce_current": 5.0, "pledge_pct": 3.0}

    d_ab = feature_distance(a, b, stds)
    d_ba = feature_distance(b, a, stds)
    assert d_ab == pytest.approx(d_ba)

    # Identical points have distance 0
    assert feature_distance(a, a, stds) == pytest.approx(0.0)

    # None values should be ignored, not crash
    c = {"pe_trailing": 25.0, "roce_current": None, "pledge_pct": 5.0}
    _ = feature_distance(a, c, stds)  # must not raise


# ---------------------------------------------------------------------------
# Cohort stats
# ---------------------------------------------------------------------------

def test_cohort_base_rates_aggregation(store: FlowStore) -> None:
    """cohort_stats returns recovery %, median return, blow-up rate — math correct."""
    from flowtracker.research.analog_builder import cohort_stats

    # Synthetic cohort: 10 analogs with known outcomes
    cohort = [
        {"return_12m_pct": r, "outcome_label": label}
        for r, label in [
            (25, "recovered"), (30, "recovered"), (40, "recovered"),
            (50, "recovered"), (22, "recovered"), (35, "recovered"),
            (-25, "blew_up"),
            (5, "sideways"), (10, "sideways"), (15, "sideways"),
        ]
    ]

    stats = cohort_stats(cohort)
    assert stats["count"] == 10
    assert stats["recovery_rate_pct"] == pytest.approx(60.0)  # 6/10 recovered
    assert stats["blow_up_rate_pct"] == pytest.approx(10.0)   # 1/10 blew up
    # Sorted: [-25, 5, 10, 15, 22, 25, 30, 35, 40, 50] → median = avg(22, 25) = 23.5
    assert stats["median_return_12m_pct"] == pytest.approx(23.5)
