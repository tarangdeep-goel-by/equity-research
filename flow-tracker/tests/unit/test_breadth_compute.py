"""Tests for `breadth_compute.compute_snapshot` / `compute_range`.

Seeds a deterministic fixture: 10 symbols × 250 trading days. The first
5 symbols trend up (always above 200DMA on the last day, close > prev_close);
the last 5 trend down (always below 200DMA on the last day, close < prev_close).
This lets us assert exact expected breadth values.

The fixture inserts directly into `daily_stock_data` + `index_constituents`
to keep the test independent of any client.
"""

from __future__ import annotations

from datetime import date, timedelta

from flowtracker.breadth_compute import (
    DEFAULT_INDICES,
    compute_range,
    compute_snapshot,
)
from flowtracker.scan_models import IndexConstituent
from flowtracker.store import FlowStore


# -- fixture helpers --


def _trading_dates(end: date, n: int) -> list[str]:
    """Return n consecutive weekday dates ending at `end` (oldest first)."""
    days: list[date] = []
    cursor = end
    while len(days) < n:
        if cursor.weekday() < 5:  # Mon-Fri
            days.append(cursor)
        cursor = cursor - timedelta(days=1)
    days.sort()
    return [d.isoformat() for d in days]


def _seed_symbol(
    store: FlowStore,
    symbol: str,
    dates: list[str],
    start_price: float,
    daily_drift: float,
) -> None:
    """Insert ``len(dates)`` rows for one symbol with linear price drift.

    daily_drift > 0 → uptrend (close always above 200DMA + advancing);
    daily_drift < 0 → downtrend (close always below 200DMA + declining).
    Adj_close is set equal to close (no corp actions in the fixture).
    """
    prev_close = start_price
    for i, d in enumerate(dates):
        close = start_price + i * daily_drift
        store._conn.execute(
            "INSERT OR REPLACE INTO daily_stock_data "
            "(date, symbol, open, high, low, close, prev_close, volume, "
            " turnover, adj_close, adj_factor) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                d, symbol, close, close, close, close, prev_close,
                10_000, 100.0, close, 1.0,
            ),
        )
        prev_close = close
    store._conn.commit()


def _seed_universe(store: FlowStore) -> tuple[list[str], list[str]]:
    """Seed a 10-symbol NIFTY 50 universe + 250 days. Returns (uptrend, downtrend)."""
    uptrend = [f"UP{i:02d}" for i in range(5)]
    downtrend = [f"DN{i:02d}" for i in range(5)]
    all_syms = uptrend + downtrend

    # Register them as constituents of NIFTY 50 so `_get_symbols` picks them up.
    constituents = [
        IndexConstituent(
            symbol=s, index_name="NIFTY 50",
            company_name=f"{s} Test Co", industry="Test",
        ) for s in all_syms
    ]
    store.upsert_index_constituents(constituents)

    end = date(2026, 5, 25)
    dates = _trading_dates(end, 250)
    for s in uptrend:
        _seed_symbol(store, s, dates, start_price=100.0, daily_drift=0.5)
    for s in downtrend:
        _seed_symbol(store, s, dates, start_price=500.0, daily_drift=-0.5)

    return dates, uptrend + downtrend


# -- tests --


def test_compute_snapshot_basic_breadth_math(store: FlowStore) -> None:
    """5 uptrend + 5 downtrend → 50% above 200DMA, 5 adv / 5 dec / A-D = 1.0."""
    dates, _ = _seed_universe(store)
    target = dates[-1]

    snap = compute_snapshot(store, target, "NIFTY 50")
    assert snap is not None
    assert snap.date == target
    assert snap.index_name == "NIFTY 50"
    assert snap.total == 10

    # 5 of 10 symbols are above their 200DMA on the last day.
    assert snap.pct_above_200dma == 50.0
    assert snap.advance == 5
    assert snap.decline == 5
    assert snap.unchanged == 0
    assert snap.ad_ratio == 1.0


def test_compute_snapshot_52w_extremes_on_uptrend_and_downtrend(
    store: FlowStore,
) -> None:
    """Uptrend symbols hit new 52w highs on last day; downtrend hit new lows."""
    dates, _ = _seed_universe(store)
    snap = compute_snapshot(store, dates[-1], "NIFTY 50")
    assert snap is not None
    # Each of the 5 uptrend symbols is making a new 52w high on the last day.
    assert snap.new_52w_highs == 5
    # Each of the 5 downtrend symbols is making a new 52w low.
    assert snap.new_52w_lows == 5


def test_compute_snapshot_returns_none_for_unknown_index(store: FlowStore) -> None:
    """Index with no constituents → None."""
    assert compute_snapshot(store, "2026-05-25", "NIFTY MADE-UP 999") is None


def test_compute_snapshot_returns_none_when_no_prices_on_date(
    store: FlowStore,
) -> None:
    """Date with no constituent prices → None (even if constituents exist)."""
    constituents = [
        IndexConstituent(
            symbol="SOLO", index_name="NIFTY 50",
            company_name="Solo Co", industry="Test",
        )
    ]
    store.upsert_index_constituents(constituents)
    # Don't insert any daily_stock_data rows for the queried date.
    assert compute_snapshot(store, "2026-05-25", "NIFTY 50") is None


def test_pct_above_200dma_none_with_short_history(store: FlowStore) -> None:
    """With <150 days of history, pct_above_200dma is None (other fields still set)."""
    sym = "SHORT"
    store.upsert_index_constituents([
        IndexConstituent(
            symbol=sym, index_name="NIFTY 50",
            company_name="Short Co", industry="Test",
        ),
    ])
    end = date(2026, 5, 25)
    dates = _trading_dates(end, 100)  # only 100 trading days
    _seed_symbol(store, sym, dates, start_price=100.0, daily_drift=1.0)

    snap = compute_snapshot(store, dates[-1], "NIFTY 50")
    assert snap is not None
    assert snap.total == 1
    assert snap.pct_above_200dma is None  # below 150-day threshold
    # But advance/decline + 52w hi/lo are still meaningful.
    assert snap.advance == 1
    assert snap.new_52w_highs == 1


def test_nifty_500_falls_back_to_component_union(store: FlowStore) -> None:
    """When NIFTY 500 isn't in constituents, fall back to component union."""
    # Seed 2 symbols in NIFTY 50, 2 in NIFTY NEXT 50, 2 in NIFTY MIDCAP 150,
    # 2 in NIFTY SMALLCAP 250. No row at all for "NIFTY 500".
    setup = [
        ("A1", "NIFTY 50"), ("A2", "NIFTY 50"),
        ("B1", "NIFTY NEXT 50"), ("B2", "NIFTY NEXT 50"),
        ("C1", "NIFTY MIDCAP 150"), ("C2", "NIFTY MIDCAP 150"),
        ("D1", "NIFTY SMALLCAP 250"), ("D2", "NIFTY SMALLCAP 250"),
    ]
    store.upsert_index_constituents([
        IndexConstituent(
            symbol=s, index_name=idx,
            company_name=s, industry="Test",
        ) for s, idx in setup
    ])

    end = date(2026, 5, 25)
    dates = _trading_dates(end, 250)
    for s, _idx in setup:
        _seed_symbol(store, s, dates, start_price=100.0, daily_drift=1.0)

    snap = compute_snapshot(store, dates[-1], "NIFTY 500")
    assert snap is not None
    assert snap.total == 8  # union of components
    assert snap.pct_above_200dma == 100.0
    assert snap.advance == 8
    assert snap.decline == 0
    # decline=0 → ad_ratio is None (division-by-zero guard)
    assert snap.ad_ratio is None


def test_compute_range_emits_one_snapshot_per_trading_day(
    store: FlowStore,
) -> None:
    """compute_range walks every trading date in the window."""
    dates, _ = _seed_universe(store)
    # Run on the last 3 trading days only.
    window = dates[-3:]
    snaps = compute_range(store, window[0], window[-1], ["NIFTY 50"])

    # 3 dates × 1 index = 3 snapshots.
    assert len(snaps) == 3
    assert sorted({s.date for s in snaps}) == window
    assert all(s.index_name == "NIFTY 50" for s in snaps)


def test_default_indices_contains_expected_names() -> None:
    """Spec lock-in: the 4 standard indices the CLI defaults to."""
    assert DEFAULT_INDICES == (
        "NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250",
    )
