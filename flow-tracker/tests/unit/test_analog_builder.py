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


def test_feature_vector_is_backfilled_for_newly_listed(store: FlowStore) -> None:
    """Recently-listed tickers (listed_days < 1500) with a populated
    roce_3yr_delta are flagged is_backfilled — the 3-year accounting window
    precedes the listing date, so the feature reflects provider bookkeeping
    rather than lived market state.
    """
    from flowtracker.research.analog_builder import compute_feature_vector

    # Ticker with 120 trading days of bhavcopy (simulates a fresh demerger)
    as_of = date(2026, 3, 31)
    first_day = as_of - timedelta(days=120)
    _seed_prices(
        store, "NEWCO",
        [
            ((first_day + timedelta(days=i)).isoformat(), 100.0 + i * 0.1)
            for i in range(120)
        ],
    )
    # Populate 4 FYs of annual financials so ROCE 3yr delta is not None
    # (this is the data that backs "backfill" — the provider supplies it
    # despite the ticker only having 120 days on NSE).
    for years_back in range(4):
        fy_end = (as_of - timedelta(days=years_back * 365)).isoformat()
        store._conn.execute(
            "INSERT INTO annual_financials (symbol, fiscal_year_end, "
            "total_assets, net_income, borrowings, reserves, equity_capital, revenue) "
            "VALUES (?, ?, 1000, 100, 200, 300, 100, 1000)",
            ("NEWCO", fy_end),
        )
    store._conn.commit()

    vec = compute_feature_vector(store, "NEWCO", as_of.isoformat())
    assert vec["listed_days"] == 120
    assert vec["roce_3yr_delta"] is not None
    assert vec["is_backfilled"] is True


def test_feature_vector_not_backfilled_for_mature_ticker(store: FlowStore) -> None:
    """Mature tickers (listed_days >= 1500) are never flagged is_backfilled."""
    from flowtracker.research.analog_builder import compute_feature_vector

    as_of = date(2026, 3, 31)
    first_day = as_of - timedelta(days=1800)
    _seed_prices(
        store, "OLDCO",
        [
            ((first_day + timedelta(days=i)).isoformat(), 100.0 + i * 0.01)
            for i in range(1800)
        ],
    )
    for years_back in range(4):
        fy_end = (as_of - timedelta(days=years_back * 365)).isoformat()
        store._conn.execute(
            "INSERT INTO annual_financials (symbol, fiscal_year_end, "
            "total_assets, net_income, borrowings, reserves, equity_capital, revenue) "
            "VALUES (?, ?, 1000, 100, 200, 300, 100, 1000)",
            ("OLDCO", fy_end),
        )
    store._conn.commit()

    vec = compute_feature_vector(store, "OLDCO", as_of.isoformat())
    assert vec["listed_days"] >= 1500
    assert vec["is_backfilled"] is False


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
    result = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=today.isoformat(),
        target_features=target_features, k=10, min_unique_symbols=1,
    )
    analogs = result["analogs"]

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
    # min_unique_symbols=1 keeps strict tier in play; otherwise fallback would
    # widen to mcap-only and surface the pharma row.
    result = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=date.today().isoformat(),
        target_features=target_features, k=10, min_unique_symbols=1,
    )
    analogs = result["analogs"]

    symbols = [a["symbol"] for a in analogs]
    assert "CHEM1" in symbols
    assert "PHARMA1" not in symbols, "Industry hard-filter leaked a pharma peer into chemicals cohort"
    assert result["relaxation_level"] == 0
    assert result["relaxation_label"] == "strict"


def test_retrieval_strict_tier_when_enough_unique_symbols(store: FlowStore) -> None:
    """When strict (industry+mcap) yields >=5 unique symbols, stay at tier 0."""
    from flowtracker.research.analog_builder import retrieve_top_k_analogs

    recent = (date.today() - timedelta(days=365 * 3)).isoformat()
    # Seed 6 distinct chemical-midcap peers — strict tier should satisfy
    peer_rows = [
        (f"CHEM{i}", recent, "Chemicals", "midcap") for i in range(1, 7)
    ]
    # Plus a pharma row that must NOT surface at strict tier
    peer_rows.append(("PHARMA_X", recent, "Pharmaceuticals", "midcap"))
    store._conn.executemany(
        "INSERT INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
        " mf_pct, industry, mcap_bucket) "
        "VALUES (?, ?, 25.0, 20.0, 50.0, 15.0, 10.0, ?, ?)",
        peer_rows,
    )
    store._conn.commit()

    target_features = {
        "pe_trailing": 25.0, "roce_current": 20.0, "promoter_pct": 50.0,
        "fii_pct": 15.0, "mf_pct": 10.0, "industry": "Chemicals",
        "mcap_bucket": "midcap",
    }
    result = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=date.today().isoformat(),
        target_features=target_features, k=20,
    )
    assert result["relaxation_level"] == 0
    assert result["relaxation_label"] == "strict"
    assert result["unique_symbols"] >= 5
    symbols = {a["symbol"] for a in result["analogs"]}
    assert "PHARMA_X" not in symbols


def test_retrieval_falls_back_to_industry_only(store: FlowStore) -> None:
    """When strict has <5 unique symbols, widen to industry-only (cross-mcap)."""
    from flowtracker.research.analog_builder import retrieve_top_k_analogs

    recent = (date.today() - timedelta(days=365 * 3)).isoformat()
    # 2 midcap chemicals peers (strict tier) + 5 largecap chemicals peers (industry-only tier)
    rows = [(f"MID{i}", recent, "Chemicals", "midcap") for i in range(1, 3)]
    rows += [(f"LARGE{i}", recent, "Chemicals", "largecap") for i in range(1, 6)]
    store._conn.executemany(
        "INSERT INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
        " mf_pct, industry, mcap_bucket) "
        "VALUES (?, ?, 25.0, 20.0, 50.0, 15.0, 10.0, ?, ?)",
        rows,
    )
    store._conn.commit()

    target_features = {
        "pe_trailing": 25.0, "roce_current": 20.0, "promoter_pct": 50.0,
        "fii_pct": 15.0, "mf_pct": 10.0, "industry": "Chemicals",
        "mcap_bucket": "midcap",
    }
    result = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=date.today().isoformat(),
        target_features=target_features, k=20,
    )
    assert result["relaxation_level"] == 1
    assert result["relaxation_label"] == "industry_only"
    assert result["unique_symbols"] >= 5
    # All returned rows must still be Chemicals (cross-mcap only)
    assert all(a["industry"] == "Chemicals" for a in result["analogs"])
    # Every row is stamped with the tier that produced the cohort
    assert all(a["relaxation_level"] == 1 for a in result["analogs"])


def test_retrieval_falls_back_to_mcap_only(store: FlowStore) -> None:
    """When industry-only still has <5 unique symbols, widen to mcap-only."""
    from flowtracker.research.analog_builder import retrieve_top_k_analogs

    recent = (date.today() - timedelta(days=365 * 3)).isoformat()
    # 1 chemicals midcap + 0 chemicals largecap + 6 pharma midcaps
    rows = [("CHEM_NARROW", recent, "Chemicals", "midcap")]
    rows += [(f"PHARMA_{i}", recent, "Pharmaceuticals", "midcap") for i in range(1, 7)]
    store._conn.executemany(
        "INSERT INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
        " mf_pct, industry, mcap_bucket) "
        "VALUES (?, ?, 25.0, 20.0, 50.0, 15.0, 10.0, ?, ?)",
        rows,
    )
    store._conn.commit()

    target_features = {
        "pe_trailing": 25.0, "roce_current": 20.0, "promoter_pct": 50.0,
        "fii_pct": 15.0, "mf_pct": 10.0, "industry": "Chemicals",
        "mcap_bucket": "midcap",
    }
    result = retrieve_top_k_analogs(
        store, target_symbol="TGT", target_date=date.today().isoformat(),
        target_features=target_features, k=20,
    )
    assert result["relaxation_level"] == 2
    assert result["relaxation_label"] == "mcap_only"
    assert result["unique_symbols"] >= 5
    symbols = {a["symbol"] for a in result["analogs"]}
    # Pharma peers surface because we've relaxed industry
    assert any(s.startswith("PHARMA_") for s in symbols)


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


def test_feature_distance_imputes_null_with_supplied_medians() -> None:
    """Skip-on-None biases toward sparse candidates. With medians provided,
    NULL dims get imputed to the sector median so partial-match candidates
    pay a real distance cost for their gaps."""
    from flowtracker.research.analog_builder import feature_distance

    stds = {"pe_trailing": 10.0, "roce_current": 5.0, "pledge_pct": 3.0}
    medians = {"pe_trailing": 25.0, "roce_current": 20.0, "pledge_pct": 5.0}

    # Target: far from the median across all dims (50, 40, 20)
    target = {"pe_trailing": 50.0, "roce_current": 40.0, "pledge_pct": 20.0}
    # Full-feature candidate exactly at the median
    full = {"pe_trailing": 25.0, "roce_current": 20.0, "pledge_pct": 5.0}
    # Sparse candidate — only pe_trailing reported, others null
    sparse = {"pe_trailing": 25.0, "roce_current": None, "pledge_pct": None}

    # Without medians: skip-on-None means sparse only compares 1 dim, gets
    # a small sum-of-squares, looks artificially close.
    d_full_skip = feature_distance(target, full, stds)
    d_sparse_skip = feature_distance(target, sparse, stds)
    # With medians: sparse's nulls get imputed to the medians, so its distance
    # should match full (both candidates land at identical imputed values).
    d_full_imp = feature_distance(target, full, stds, medians=medians)
    d_sparse_imp = feature_distance(target, sparse, stds, medians=medians)

    assert d_full_imp == pytest.approx(d_sparse_imp), (
        f"Imputation should equalize sparse vs full-feature candidates at the "
        f"same imputed values; got {d_sparse_imp=} vs {d_full_imp=}"
    )
    # And the imputed sparse distance should be larger than the skip-on-None
    # sparse distance — skip bias is the very thing this fix removes.
    assert d_sparse_imp > d_sparse_skip


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


def test_cohort_informative_N_and_unique_symbols(store: FlowStore) -> None:
    """Gross N includes all retrieved rows; informative_N_* only counts rows
    whose forward window at that horizon has closed."""
    from flowtracker.research.analog_builder import cohort_stats

    # 8 analogs: 5 have 12m returns, 8 have 3m returns. 3 unique symbols.
    cohort = [
        {"symbol": "A", "return_3m_pct": 4, "return_12m_pct": 20, "outcome_label": "recovered"},
        {"symbol": "A", "return_3m_pct": -2, "return_12m_pct": 8, "outcome_label": "sideways"},
        {"symbol": "B", "return_3m_pct": 6, "return_12m_pct": -25, "outcome_label": "blew_up"},
        {"symbol": "B", "return_3m_pct": 1, "return_12m_pct": 30, "outcome_label": "recovered"},
        {"symbol": "C", "return_3m_pct": 3, "return_12m_pct": 40, "outcome_label": "recovered"},
        # 3 rows with 3m populated but 12m still open
        {"symbol": "A", "return_3m_pct": 2, "return_12m_pct": None, "outcome_label": None},
        {"symbol": "B", "return_3m_pct": -1, "return_12m_pct": None, "outcome_label": None},
        {"symbol": "C", "return_3m_pct": 5, "return_12m_pct": None, "outcome_label": None},
    ]

    stats = cohort_stats(cohort)
    assert stats["count"] == 8
    assert stats["gross_N"] == 8
    assert stats["unique_symbols"] == 3
    assert stats["informative_N_3m"] == 8
    assert stats["informative_N_12m"] == 5
    # 12m horizon has informative_N=5, so p10/p90 emit
    assert "p10_return_pct" in stats["per_horizon"]["12m"]


def test_cohort_suppresses_p10_p90_when_small_sample(store: FlowStore) -> None:
    """When informative_N < 5, suppress p10/p90 and emit individual outcomes
    (mathematically honest — tail estimates on N=3 are fabricated precision)."""
    from flowtracker.research.analog_builder import cohort_stats

    cohort = [
        {"symbol": "A", "return_12m_pct": 15, "outcome_label": "sideways"},
        {"symbol": "B", "return_12m_pct": -30, "outcome_label": "blew_up"},
        {"symbol": "C", "return_12m_pct": 45, "outcome_label": "recovered"},
    ]

    stats = cohort_stats(cohort)
    twelve = stats["per_horizon"]["12m"]
    assert twelve["informative_N"] == 3
    assert "p10_return_pct" not in twelve, "p10/p90 must suppress on N<5"
    assert "p90_return_pct" not in twelve
    assert twelve["individual_outcomes"] == [-30, 15, 45]


def test_cohort_ranking_is_deterministic_on_distance_ties(store: FlowStore) -> None:
    """Two candidates with identical distance must return in stable
    (distance, symbol, quarter_end) order regardless of SQL iteration order."""
    from flowtracker.research.analog_builder import retrieve_top_k_analogs

    recent = (date.today() - timedelta(days=365 * 3)).isoformat()

    # Seed two peers with identical feature values → identical distance to
    # the target. Insert in reverse-alphabetical order so that SQL iteration
    # without a stable tie-break would surface BETA before ALPHA.
    store._conn.executemany(
        "INSERT INTO historical_states "
        "(symbol, quarter_end, pe_trailing, roce_current, promoter_pct, fii_pct, "
        " mf_pct, industry, mcap_bucket) "
        "VALUES (?, ?, 25.0, 20.0, 50.0, 15.0, 10.0, 'Chemicals', 'midcap')",
        [("ZETA", recent), ("BETA", recent), ("ALPHA", recent)],
    )
    store._conn.commit()

    target_features = {
        "pe_trailing": 25.0, "roce_current": 20.0, "promoter_pct": 50.0,
        "fii_pct": 15.0, "mf_pct": 10.0, "industry": "Chemicals",
        "mcap_bucket": "midcap",
    }

    seen_orders: list[list[str]] = []
    for _ in range(3):
        result = retrieve_top_k_analogs(
            store, target_symbol="TGT", target_date=date.today().isoformat(),
            target_features=target_features, k=10, min_unique_symbols=1,
        )
        seen_orders.append([a["symbol"] for a in result["analogs"]])

    # All three runs must yield the same order (determinism).
    assert seen_orders[0] == seen_orders[1] == seen_orders[2], (
        f"Non-deterministic order across runs: {seen_orders}"
    )
    # And that order must be ascending by symbol after the distance tie.
    assert seen_orders[0] == ["ALPHA", "BETA", "ZETA"], (
        f"Expected (distance, symbol, quarter_end) tie-break; got {seen_orders[0]}"
    )
