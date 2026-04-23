"""Tests for split/bonus-adjusted close price computation (Sprint 0).

Hybrid architecture under test:
  - FlowStore.recompute_adj_close(symbol) — stored path, writes daily_stock_data.adj_close
  - ResearchDataAPI.get_adjusted_close_series(symbol, from_date, to_date) — dynamic helper
  - Drift between the two paths must be zero.

The bug this suite pins down: bonuses were previously ignored by the adjuster
inside get_price_performance. Any 1:N bonus produced phantom ~50% drawdowns.
"""

from __future__ import annotations

import pytest

from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.store import FlowStore


def _bhavcopy_row(
    date: str, symbol: str, close: float, prev_close: float | None = None,
) -> DailyStockData:
    """Tiny helper — the other OHLCV columns don't matter for adj_close tests.
    prev_close defaults to close (no cliff) but can be set explicitly to
    simulate ex-date cliffs (needed by the price-cliff verification guard).
    """
    return DailyStockData(
        date=date, symbol=symbol,
        open=close, high=close, low=close, close=close,
        prev_close=prev_close if prev_close is not None else close,
        volume=1_000_000, turnover=close * 1_000_000,
    )


def _seed_prices(store: FlowStore, symbol: str, series: list[tuple[str, float]]) -> None:
    """Seed prices with chronologically realistic prev_close.

    Each row's prev_close = previous row's close (enables the price-cliff
    verification guard to see real cliffs at ex-dates).
    """
    rows: list[DailyStockData] = []
    prior_close: float | None = None
    for date, close in series:
        rows.append(_bhavcopy_row(date, symbol, close, prev_close=prior_close))
        prior_close = close
    store.upsert_daily_stock_data(rows)


def _seed_action(
    store: FlowStore,
    symbol: str,
    ex_date: str,
    action_type: str,
    multiplier: float,
    ratio_text: str = "",
    source: str = "bse",
) -> None:
    store.upsert_corporate_actions([{
        "symbol": symbol, "ex_date": ex_date, "action_type": action_type,
        "multiplier": multiplier, "ratio_text": ratio_text or f"{multiplier}:1",
        "dividend_amount": None, "source": source,
    }])


def _adj(store: FlowStore, symbol: str, date: str) -> float | None:
    row = store._conn.execute(
        "SELECT adj_close FROM daily_stock_data WHERE symbol = ? AND date = ?",
        (symbol, date),
    ).fetchone()
    return row["adj_close"] if row else None


# ---------------------------------------------------------------------------
# Trivial cases
# ---------------------------------------------------------------------------

def test_recompute_no_actions_adj_equals_close(store: FlowStore) -> None:
    """With zero corporate actions, adj_close must mirror raw close."""
    _seed_prices(store, "XYZ", [
        ("2024-01-01", 100.0),
        ("2024-06-01", 120.0),
        ("2024-12-01", 150.0),
    ])
    store.recompute_adj_close("XYZ")

    assert _adj(store, "XYZ", "2024-01-01") == pytest.approx(100.0)
    assert _adj(store, "XYZ", "2024-06-01") == pytest.approx(120.0)
    assert _adj(store, "XYZ", "2024-12-01") == pytest.approx(150.0)


def test_recompute_empty_symbol_is_noop(store: FlowStore) -> None:
    """Recomputing a symbol with no prices must not error."""
    store.recompute_adj_close("NOSUCH")  # should not raise


# ---------------------------------------------------------------------------
# Single split
# ---------------------------------------------------------------------------

def test_recompute_single_split_halves_pre_split_prices(store: FlowStore) -> None:
    """PIDILITIND 2:1 split regression: pre-ex prices get divided by 2."""
    _seed_prices(store, "PIDILITIND", [
        ("2025-08-01", 2000.0),  # pre-split
        ("2025-09-01", 2100.0),  # pre-split
        ("2025-09-15", 1050.0),  # post-split (mechanical halving)
        ("2025-10-01", 1100.0),  # post-split
    ])
    _seed_action(store, "PIDILITIND", "2025-09-10", "split", 2.0, "2:1")
    store.recompute_adj_close("PIDILITIND")

    assert _adj(store, "PIDILITIND", "2025-08-01") == pytest.approx(1000.0)
    assert _adj(store, "PIDILITIND", "2025-09-01") == pytest.approx(1050.0)
    assert _adj(store, "PIDILITIND", "2025-09-15") == pytest.approx(1050.0)
    assert _adj(store, "PIDILITIND", "2025-10-01") == pytest.approx(1100.0)


def test_recompute_split_on_exact_ex_date_treats_as_post(store: FlowStore) -> None:
    """Convention: ex_date row is already post-split; action applies strictly before ex_date."""
    _seed_prices(store, "ABC", [
        ("2024-01-01", 2000.0),  # pre
        ("2024-06-15", 1000.0),  # ex-date itself (post-split)
        ("2024-07-01", 1050.0),  # post
    ])
    _seed_action(store, "ABC", "2024-06-15", "split", 2.0, "2:1")
    store.recompute_adj_close("ABC")

    assert _adj(store, "ABC", "2024-01-01") == pytest.approx(1000.0)
    assert _adj(store, "ABC", "2024-06-15") == pytest.approx(1000.0)
    assert _adj(store, "ABC", "2024-07-01") == pytest.approx(1050.0)


# ---------------------------------------------------------------------------
# Single bonus — THIS IS THE LIVE BUG
# ---------------------------------------------------------------------------

def test_recompute_single_bonus_halves_pre_bonus_prices(store: FlowStore) -> None:
    """The bonus regression: 1:1 bonus (multiplier=2.0) must halve pre-ex prices.

    Before this fix, split_adjustment() only iterated action_type='split',
    so a bonus with multiplier=2 produced a phantom ~50% drawdown in returns.
    """
    _seed_prices(store, "RELIANCE", [
        ("2017-09-01", 1500.0),  # pre-bonus
        ("2017-09-20", 1500.0),  # pre-bonus
        ("2017-09-25", 750.0),   # ex-bonus (1:1 = +1 free share, price halves)
        ("2017-10-15", 800.0),   # post-bonus
    ])
    _seed_action(store, "RELIANCE", "2017-09-25", "bonus", 2.0, "1:1")
    store.recompute_adj_close("RELIANCE")

    assert _adj(store, "RELIANCE", "2017-09-01") == pytest.approx(750.0)
    assert _adj(store, "RELIANCE", "2017-09-20") == pytest.approx(750.0)
    assert _adj(store, "RELIANCE", "2017-09-25") == pytest.approx(750.0)
    assert _adj(store, "RELIANCE", "2017-10-15") == pytest.approx(800.0)


# ---------------------------------------------------------------------------
# Combined split + bonus
# ---------------------------------------------------------------------------

def test_recompute_split_then_bonus_applies_cumulative_factor(store: FlowStore) -> None:
    """Split 2:1 then bonus 1:1 means pre-everything prices divided by 4."""
    _seed_prices(store, "ABC", [
        ("2024-01-01", 4000.0),  # pre-both
        ("2024-07-01", 2000.0),  # between (post-split, pre-bonus)
        ("2025-01-01", 1000.0),  # post-both
    ])
    _seed_action(store, "ABC", "2024-06-01", "split", 2.0, "2:1")
    _seed_action(store, "ABC", "2024-12-01", "bonus", 2.0, "1:1")
    store.recompute_adj_close("ABC")

    # factor at 2024-01-01 = 2 * 2 = 4; 4000/4 = 1000
    assert _adj(store, "ABC", "2024-01-01") == pytest.approx(1000.0)
    # factor at 2024-07-01 = 2 (only bonus remains ahead); 2000/2 = 1000
    assert _adj(store, "ABC", "2024-07-01") == pytest.approx(1000.0)
    # factor at 2025-01-01 = 1 (both behind); 1000 unchanged
    assert _adj(store, "ABC", "2025-01-01") == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# Idempotency and adj_factor correctness
# ---------------------------------------------------------------------------

def test_recompute_idempotent(store: FlowStore) -> None:
    _seed_prices(store, "XYZ", [("2024-01-01", 2000.0), ("2024-12-01", 1100.0)])
    _seed_action(store, "XYZ", "2024-06-01", "split", 2.0, "2:1")

    store.recompute_adj_close("XYZ")
    first = _adj(store, "XYZ", "2024-01-01")
    store.recompute_adj_close("XYZ")
    second = _adj(store, "XYZ", "2024-01-01")

    assert first == pytest.approx(1000.0)
    assert first == pytest.approx(second)


def test_adj_factor_column_populated(store: FlowStore) -> None:
    """adj_factor = close / adj_close — must round-trip."""
    _seed_prices(store, "XYZ", [("2024-01-01", 2000.0), ("2024-12-01", 1100.0)])
    _seed_action(store, "XYZ", "2024-06-01", "split", 2.0, "2:1")
    store.recompute_adj_close("XYZ")

    row = store._conn.execute(
        "SELECT close, adj_close, adj_factor FROM daily_stock_data "
        "WHERE symbol = ? AND date = ?",
        ("XYZ", "2024-01-01"),
    ).fetchone()

    assert row["adj_factor"] == pytest.approx(2.0)
    assert row["close"] / row["adj_factor"] == pytest.approx(row["adj_close"])


# ---------------------------------------------------------------------------
# Deduplication with corporate_actions source priority
# ---------------------------------------------------------------------------

def test_null_multiplier_inferred_from_price_cliff(store: FlowStore) -> None:
    """Real data edge case: some corporate_actions rows have NULL multiplier
    despite a clear ~10x cliff in daily prices (ANGELONE 2026-02-26 was the
    spot-check example). The adjuster infers multiplier from prev_close/close
    at ex_date rather than silently dropping these actions.
    """
    # Seed a real 10x cliff
    _seed_prices(store, "INFER1", [
        ("2024-01-01", 2500.0),
        ("2024-05-31", 2500.0),
        ("2024-06-03", 250.0),   # ex-date: cliff 10x (prev_close 2500 / close 250)
        ("2024-12-01", 260.0),
    ])
    # Action row with NULL multiplier (as happens in real data)
    store._conn.execute(
        "INSERT INTO corporate_actions (symbol, ex_date, action_type, "
        "multiplier, source) VALUES (?, ?, ?, NULL, 'bse')",
        ("INFER1", "2024-06-03", "split"),
    )
    store._conn.commit()
    store.recompute_adj_close("INFER1")

    # Inferred multiplier ~10.0 → pre-cliff prices get divided by 10
    assert _adj(store, "INFER1", "2024-01-01") == pytest.approx(250.0, abs=1.0)
    assert _adj(store, "INFER1", "2024-05-31") == pytest.approx(250.0, abs=1.0)
    assert _adj(store, "INFER1", "2024-06-03") == pytest.approx(250.0)
    assert _adj(store, "INFER1", "2024-12-01") == pytest.approx(260.0)


def test_reverse_split_consolidation_inflates_pre_prices(store: FlowStore) -> None:
    """Reverse split (consolidation): multiplier < 1. 5:1 consolidation →
    multiplier 0.2 means 5 old shares become 1 new share; price jumps 5x on
    ex-date. Pre-ex prices should be INFLATED (multiplied by 5) to reflect
    current-share-equivalent value.
    """
    _seed_prices(store, "REV1", [
        ("2024-01-01", 20.0),    # pre-consolidation (cheap shares)
        ("2024-05-31", 20.0),    # pre
        ("2024-06-03", 100.0),   # ex-date: price jumps 5x (prev=20 → close=100)
        ("2024-12-01", 110.0),   # post
    ])
    # 5:1 reverse split = multiplier 0.2 (5 old → 1 new)
    _seed_action(store, "REV1", "2024-06-03", "split", 0.2, "1:5", source="bse")
    store.recompute_adj_close("REV1")

    # Pre-consolidation adj_close = 20 / 0.2 = 100 (inflated to current-share terms)
    assert _adj(store, "REV1", "2024-01-01") == pytest.approx(100.0)
    assert _adj(store, "REV1", "2024-05-31") == pytest.approx(100.0)
    assert _adj(store, "REV1", "2024-06-03") == pytest.approx(100.0)
    assert _adj(store, "REV1", "2024-12-01") == pytest.approx(110.0)


def test_no_cliff_no_adjustment_even_with_action(store: FlowStore) -> None:
    """BAJFINANCE 2016 pattern: corporate_actions row exists but daily_stock_data
    shows no cliff at ex_date (NSE bhavcopy was already adjusted upstream).
    Adjustment should be skipped — otherwise we'd phantom-amplify historical
    prices.
    """
    _seed_prices(store, "PREAD1", [
        ("2020-01-01", 100.0),
        ("2020-06-10", 102.0),   # pre-"ex"
        ("2020-06-11", 101.0),   # "ex" — no real cliff (data already adjusted)
        ("2020-12-01", 110.0),
    ])
    # Corporate_actions says 5:1 split — but prices don't show the cliff
    _seed_action(store, "PREAD1", "2020-06-11", "split", 5.0, "5:1", source="bse")
    store.recompute_adj_close("PREAD1")

    # Expected: adjustment REJECTED by price-cliff verification — adj_close
    # should equal raw close across all dates (no phantom 5x reduction)
    assert _adj(store, "PREAD1", "2020-01-01") == pytest.approx(100.0)
    assert _adj(store, "PREAD1", "2020-06-10") == pytest.approx(102.0)
    assert _adj(store, "PREAD1", "2020-06-11") == pytest.approx(101.0)
    assert _adj(store, "PREAD1", "2020-12-01") == pytest.approx(110.0)


def test_compound_action_same_date_split_plus_bonus(store: FlowStore) -> None:
    """BAJFINANCE-style edge case: genuine compound action — 1:2 split AND
    1:4 bonus on the same ex_date — total multiplier 10. Both rows must be
    preserved; dedup is per (ex_date, action_type), not per ex_date.
    """
    _seed_prices(store, "CMPD", [
        ("2024-06-13", 9331.0),  # pre-compound
        ("2024-06-17", 933.1),   # post-compound (raw / 10)
    ])
    # 1:2 split (multiplier 2.0) + 1:4 bonus (multiplier 5.0) same date
    _seed_action(store, "CMPD", "2024-06-16", "split", 2.0, "1:2", source="bse")
    _seed_action(store, "CMPD", "2024-06-16", "bonus", 5.0, "1:4", source="bse")
    store.recompute_adj_close("CMPD")

    # Pre-compound adj_close = 9331 / 10 = 933.1 (same as post-compound raw)
    assert _adj(store, "CMPD", "2024-06-13") == pytest.approx(933.1)
    assert _adj(store, "CMPD", "2024-06-17") == pytest.approx(933.1)


def test_same_date_same_multiplier_dedups_across_sources(store: FlowStore) -> None:
    """Common case: yfinance reports a bonus as 'split' with multiplier 2.0,
    BSE reports the same event as 'bonus' with multiplier 2.0. Dedup must
    recognize them as one event and avoid double-multiplying.
    """
    _seed_prices(store, "DUAL", [
        ("2024-01-01", 2000.0),
        ("2024-12-01", 1050.0),
    ])
    _seed_action(store, "DUAL", "2024-06-01", "split", 2.0, "2:1", source="yfinance")
    _seed_action(store, "DUAL", "2024-06-01", "bonus", 2.0, "1:1", source="bse")
    store.recompute_adj_close("DUAL")

    # Factor must be 2.0 (not 4.0) — same event described two ways
    assert _adj(store, "DUAL", "2024-01-01") == pytest.approx(1000.0)


def test_recompute_dedupes_bse_over_yfinance(store: FlowStore) -> None:
    """If both BSE and yfinance report the same ex-date, use BSE (canonical).

    get_split_bonus_actions already dedupes at the query layer — this test
    asserts the adjustment compose correctly when both sources exist.
    """
    _seed_prices(store, "ABC", [("2024-01-01", 2000.0), ("2024-12-01", 1050.0)])
    # Same ex-date reported by both sources; multiplier identical here.
    _seed_action(store, "ABC", "2024-06-01", "split", 2.0, "2:1", source="bse")
    _seed_action(store, "ABC", "2024-06-01", "split", 2.0, "2:1", source="yfinance")

    store.recompute_adj_close("ABC")

    # Should apply factor 2 exactly once (not squared to 4).
    assert _adj(store, "ABC", "2024-01-01") == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# Dynamic helper (ResearchDataAPI path) + drift detection
# ---------------------------------------------------------------------------

def test_dynamic_helper_matches_stored_path(store: FlowStore) -> None:
    """get_adjusted_close_series must return identical values to the stored path.

    This is the core invariant of the hybrid approach: stored column and
    computed helper agree up to numeric epsilon.
    """
    from flowtracker.research.data_api import ResearchDataAPI

    _seed_prices(store, "XYZ", [
        ("2024-01-01", 4000.0),
        ("2024-07-01", 2000.0),
        ("2025-01-01", 1000.0),
    ])
    _seed_action(store, "XYZ", "2024-06-01", "split", 2.0, "2:1")
    _seed_action(store, "XYZ", "2024-12-01", "bonus", 2.0, "1:1")
    store.recompute_adj_close("XYZ")

    api = ResearchDataAPI(store=store)
    series = dict(api.get_adjusted_close_series("XYZ", "2024-01-01", "2025-01-01"))

    for date_str in ["2024-01-01", "2024-07-01", "2025-01-01"]:
        stored = _adj(store, "XYZ", date_str)
        assert series[date_str] == pytest.approx(stored), (
            f"Drift at {date_str}: stored={stored}, computed={series[date_str]}"
        )


def test_dynamic_helper_independent_of_stored_column(store: FlowStore) -> None:
    """Drift-detection foundation: helper must produce correct values even when
    adj_close is stale/NULL, because it never reads the stored column.
    """
    from flowtracker.research.data_api import ResearchDataAPI

    _seed_prices(store, "XYZ", [("2024-01-01", 2000.0), ("2024-12-01", 1050.0)])
    _seed_action(store, "XYZ", "2024-06-01", "split", 2.0, "2:1")
    # Deliberately skip recompute_adj_close → adj_close column stays NULL

    api = ResearchDataAPI(store=store)
    series = dict(api.get_adjusted_close_series("XYZ", "2024-01-01", "2024-12-01"))
    assert series["2024-01-01"] == pytest.approx(1000.0)
    assert series["2024-12-01"] == pytest.approx(1050.0)


# ---------------------------------------------------------------------------
# Sync trigger — recompute fires after new corporate_actions
# ---------------------------------------------------------------------------

def test_recompute_on_new_action_updates_existing_prices(store: FlowStore) -> None:
    """When a new corporate action lands for a symbol, running recompute
    must re-write adj_close for all its prior rows. This is the sync-hook
    contract: filing_client.py calls recompute_adj_close(symbol) after upsert.
    """
    # State 1: no actions yet, adj_close initialized to raw close
    _seed_prices(store, "ABC", [
        ("2024-01-01", 2000.0),
        ("2024-12-01", 1050.0),
    ])
    store.recompute_adj_close("ABC")
    assert _adj(store, "ABC", "2024-01-01") == pytest.approx(2000.0)

    # State 2: a split lands (as filing_client.py would upsert)
    _seed_action(store, "ABC", "2024-06-01", "split", 2.0, "2:1")
    # Sync-hook contract: call recompute after upsert
    store.recompute_adj_close("ABC")

    # adj_close for the pre-split row must now reflect the new action
    assert _adj(store, "ABC", "2024-01-01") == pytest.approx(1000.0)
    assert _adj(store, "ABC", "2024-12-01") == pytest.approx(1050.0)


def test_upsert_corporate_actions_auto_triggers_recompute(store: FlowStore) -> None:
    """The sync-hook integration: upsert_corporate_actions with default
    recompute_adj_close=True must leave adj_close consistent with the
    newly-inserted actions — no manual recompute call from the caller.

    This is the contract that refresh.py + any other caller depends on.
    """
    _seed_prices(store, "SYNC1", [
        ("2024-01-01", 2000.0),
        ("2024-12-01", 1050.0),
    ])
    # adj_close starts NULL (migration adds column, no recompute yet)
    assert _adj(store, "SYNC1", "2024-01-01") is None

    # Single upsert with a split action — hook should fire recompute
    store.upsert_corporate_actions([{
        "symbol": "SYNC1", "ex_date": "2024-06-01",
        "action_type": "split", "multiplier": 2.0, "ratio_text": "2:1",
        "dividend_amount": None, "source": "bse",
    }])

    # adj_close populated WITHOUT the caller invoking recompute_adj_close
    assert _adj(store, "SYNC1", "2024-01-01") == pytest.approx(1000.0)
    assert _adj(store, "SYNC1", "2024-12-01") == pytest.approx(1050.0)


def test_upsert_corporate_actions_dividend_does_not_trigger_recompute(
    store: FlowStore,
) -> None:
    """Dividends don't affect price adjustment, so dividend-only upserts
    shouldn't trigger recompute (avoids unnecessary work during daily
    dividend refreshes)."""
    _seed_prices(store, "DIV1", [("2024-01-01", 100.0)])
    # adj_close NULL initially
    assert _adj(store, "DIV1", "2024-01-01") is None

    store.upsert_corporate_actions([{
        "symbol": "DIV1", "ex_date": "2024-06-01",
        "action_type": "dividend", "multiplier": None, "dividend_amount": 5.0,
        "source": "bse",
    }])
    # adj_close still NULL — no recompute triggered for dividends
    assert _adj(store, "DIV1", "2024-01-01") is None


def test_split_bonus_invalidates_screener_price_chart(store: FlowStore) -> None:
    """When a split/bonus lands, cached Screener price chart rows for that
    symbol must be deleted — they're stale pre-adjustment data that would
    show a discontinuity cliff at ex-date. PE chart (ratio) stays untouched.
    """
    _seed_prices(store, "CHART1", [("2024-01-01", 2000.0)])
    # Pretend Screener fetched some price + PE history already
    store._conn.executescript("""
        INSERT INTO screener_charts (symbol, chart_type, metric, date, value)
        VALUES ('CHART1', 'price', 'Price', '2023-01-01', 1500);
        INSERT INTO screener_charts (symbol, chart_type, metric, date, value)
        VALUES ('CHART1', 'price', 'Price', '2024-01-01', 2000);
        INSERT INTO screener_charts (symbol, chart_type, metric, date, value)
        VALUES ('CHART1', 'pe', 'PE', '2024-01-01', 25.0);
    """)
    store._conn.commit()

    # Split lands
    store.upsert_corporate_actions([{
        "symbol": "CHART1", "ex_date": "2024-06-01",
        "action_type": "split", "multiplier": 2.0, "ratio_text": "2:1",
        "dividend_amount": None, "source": "bse",
    }])

    # Price chart rows deleted (will be re-fetched next refresh); PE untouched
    price_rows = store._conn.execute(
        "SELECT COUNT(*) AS c FROM screener_charts WHERE symbol = ? AND chart_type = 'price'",
        ("CHART1",),
    ).fetchone()
    pe_rows = store._conn.execute(
        "SELECT COUNT(*) AS c FROM screener_charts WHERE symbol = ? AND chart_type = 'pe'",
        ("CHART1",),
    ).fetchone()
    assert price_rows["c"] == 0, "Screener price chart should be invalidated on split"
    assert pe_rows["c"] == 1, "PE chart is adjustment-invariant — should stay"


def test_upsert_opt_out_of_recompute_for_batch(store: FlowStore) -> None:
    """Batch backfill paths can pass recompute_adj_close=False to defer
    recompute until end of run (avoids N redundant recomputes during
    universe-scale backfill)."""
    _seed_prices(store, "BULK1", [("2024-01-01", 2000.0)])

    store.upsert_corporate_actions(
        [{
            "symbol": "BULK1", "ex_date": "2024-06-01",
            "action_type": "split", "multiplier": 2.0, "ratio_text": "2:1",
            "dividend_amount": None, "source": "bse",
        }],
        recompute_adj_close=False,
    )
    # adj_close remains NULL — caller is expected to drive recompute themselves
    assert _adj(store, "BULK1", "2024-01-01") is None


def test_adj_close_recomputes_on_corporate_action_delete(store: FlowStore) -> None:
    """Deleting a corporate action must trigger adj_close recompute so stale
    adjustments don't linger after a data correction."""
    # Seed with natural cliff: prior close 2000 → ex-date close 1000 (2:1 split)
    _seed_prices(store, "DEL1", [
        ("2024-01-01", 2000.0),
        ("2024-06-01", 1000.0),
    ])
    store.upsert_corporate_actions([{
        "symbol": "DEL1", "ex_date": "2024-06-01", "action_type": "split",
        "multiplier": 2.0, "ratio_text": "2:1",
        "dividend_amount": None, "source": "bse",
    }])
    assert _adj(store, "DEL1", "2024-01-01") == pytest.approx(1000.0)

    # Delete the action — adj_close must revert to raw close on next read
    store.delete_corporate_action("DEL1", "2024-06-01", "split", source="bse")
    assert _adj(store, "DEL1", "2024-01-01") == pytest.approx(2000.0)
    assert _adj(store, "DEL1", "2024-06-01") == pytest.approx(1000.0)


def test_adj_close_recomputes_on_corporate_action_update(store: FlowStore) -> None:
    """Upserting a new multiplier for the same (symbol, ex_date, action_type,
    source) row must re-fire the recompute with the updated ratio."""
    _seed_prices(store, "UPD1", [
        ("2024-01-01", 3000.0),
        ("2024-06-01", 1500.0),  # 2:1 cliff vs prior 3000
    ])
    store.upsert_corporate_actions([{
        "symbol": "UPD1", "ex_date": "2024-06-01", "action_type": "bonus",
        "multiplier": 2.0, "ratio_text": "1:1",
        "dividend_amount": None, "source": "bse",
    }])
    assert _adj(store, "UPD1", "2024-01-01") == pytest.approx(1500.0)

    # Correct the ratio to 3:1 (multiplier 3.0); cliff supports up to 3x.
    store._conn.execute(
        "UPDATE daily_stock_data SET close = ?, open = ?, high = ?, low = ? "
        "WHERE symbol = ? AND date = ?",
        (1000.0, 1000.0, 1000.0, 1000.0, "UPD1", "2024-06-01"),
    )
    store._conn.commit()
    store.upsert_corporate_actions([{
        "symbol": "UPD1", "ex_date": "2024-06-01", "action_type": "bonus",
        "multiplier": 3.0, "ratio_text": "2:1",
        "dividend_amount": None, "source": "bse",
    }])
    assert _adj(store, "UPD1", "2024-01-01") == pytest.approx(1000.0)


def test_recompute_handles_action_deletion_via_fresh_query(store: FlowStore) -> None:
    """If an action is corrected (deleted + re-added with different multiplier),
    the next recompute must reflect the new state, not stale in-memory data.
    """
    _seed_prices(store, "XYZ", [("2024-01-01", 2000.0)])
    _seed_action(store, "XYZ", "2024-06-01", "split", 2.0, "2:1")
    store.recompute_adj_close("XYZ")
    assert _adj(store, "XYZ", "2024-01-01") == pytest.approx(1000.0)

    # Simulate a correction: delete the action row + re-recompute
    store._conn.execute(
        "DELETE FROM corporate_actions WHERE symbol = ? AND ex_date = ?",
        ("XYZ", "2024-06-01"),
    )
    store._conn.commit()
    store.recompute_adj_close("XYZ")

    # With no actions, adj_close should revert to raw close
    assert _adj(store, "XYZ", "2024-01-01") == pytest.approx(2000.0)


# ---------------------------------------------------------------------------
# Regression: get_price_performance on bonus-only stocks was distorted pre-fix
# ---------------------------------------------------------------------------

def test_get_price_performance_with_bonus_is_correct_after_refactor(
    store: FlowStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression pin: before Sprint 0, get_price_performance ignored bonuses,
    producing ~50% phantom drops. After refactor to read adj_close, bonuses
    adjust correctly.

    Setup: stock with 1:1 bonus 6 months ago; raw prices show mechanical
    halving at ex-date but no true economic change. Expected return: ~0%.
    """
    from datetime import date, timedelta
    from flowtracker.research.data_api import ResearchDataAPI

    today = date.today()
    # Seed prices at exactly the lookup dates used by get_price_performance
    # (today, today-30, today-90, today-180, today-365). Bonus fires between
    # today-180 and today-90 → earlier prices are pre-bonus (raw 2x inflated).
    series = [
        ((today - timedelta(days=365)).isoformat(), 1000.0),  # pre-bonus
        ((today - timedelta(days=180)).isoformat(), 1000.0),  # pre-bonus
        ((today - timedelta(days=90)).isoformat(), 500.0),    # post-bonus
        ((today - timedelta(days=30)).isoformat(), 500.0),    # post-bonus
        (today.isoformat(), 500.0),                           # today, flat
    ]
    _seed_prices(store, "BONUS1", series)
    bonus_date = (today - timedelta(days=120)).isoformat()
    _seed_action(store, "BONUS1", bonus_date, "bonus", 2.0, "1:1")
    store.recompute_adj_close("BONUS1")

    # After refactor: get_price_performance reads adj_close → a flat-priced
    # stock with a bonus midway must show ~0% return at every horizon.
    api = ResearchDataAPI(store=store)
    monkeypatch.setattr(api, "_get_industry", lambda sym: "Chemicals")

    result = api.get_price_performance("BONUS1", index_cache={"^NSEI": {}})
    assert "error" not in result, result

    # Every horizon should show ~0% return (flat-priced stock ex-bonus)
    for period in result["periods"]:
        assert abs(period["stock_return"]) < 5.0, (
            f"Bonus not adjusted at {period['period']}: "
            f"stock_return={period['stock_return']}% — expected ~0%"
        )
