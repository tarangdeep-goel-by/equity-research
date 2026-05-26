"""Compute market-breadth metrics from existing price + constituent tables.

Pure Python — no external HTTP. Reads `daily_stock_data` +
`index_constituents` via FlowStore, produces `BreadthSnapshot`s.

Indices supported:
    NIFTY 50, NIFTY MIDCAP 150, NIFTY SMALLCAP 250 — direct lookup.
    NIFTY 500 — composed from (NIFTY 50 + NIFTY NEXT 50 + NIFTY MIDCAP 150
                + NIFTY SMALLCAP 250); we don't currently store NIFTY 500
                as a single row in `index_constituents`. If `NIFTY 500`
                is ever added there, this fallback becomes unreachable.

Definitions used here:
    200DMA  — simple mean of `adj_close` over the last 200 trading days
              (inclusive of today). `adj_close` falls back to `close`
              when null. Requires ≥150 trading days to compute (returns
              None for `pct_above_200dma` otherwise — the rest of the
              breadth fields are still computed).
    52w hi/lo — rolling 252-trading-day max/min of `adj_close` ending today.
    Advance/Decline — `close > prev_close` / `close < prev_close` from
              today's row. `unchanged` is the residual (covers equal and
              missing-prev cases).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import numpy as np

from flowtracker.breadth_models import BreadthSnapshot
from flowtracker.store import FlowStore

# Indices we compute breadth for. Order = display order in `breadth latest`.
DEFAULT_INDICES: tuple[str, ...] = (
    "NIFTY 50",
    "NIFTY 500",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250",
)

# Component indices used to synthesize NIFTY 500 when the index isn't
# stored directly. Order is irrelevant — symbols are deduped via set.
_NIFTY_500_COMPONENTS: tuple[str, ...] = (
    "NIFTY 50",
    "NIFTY NEXT 50",
    "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250",
)

# Lookback windows in trading days (calendar-day approx in SQL).
_MA_WINDOW = 200
_HILO_WINDOW = 252
_MIN_HISTORY_FOR_MA = 150

# Generous calendar-day pad to cover weekends/holidays when we want the
# last ``_HILO_WINDOW`` trading days of history before a target date.
# Trading days are ~252/year → ~365 calendar days per 252 trading days.
# 3× provides plenty of slack for long holiday runs.
_LOOKBACK_PAD_DAYS = max(_HILO_WINDOW * 3, 400)


def _get_symbols(store: FlowStore, index_name: str) -> list[str]:
    """Return the symbol universe for a named index.

    NIFTY 500 falls back to the union of NIFTY 50 + NIFTY NEXT 50 +
    NIFTY MIDCAP 150 + NIFTY SMALLCAP 250 when it isn't present in
    `index_constituents` directly.
    """
    row = store._conn.execute(
        "SELECT COUNT(*) AS n FROM index_constituents WHERE index_name = ?",
        (index_name,),
    ).fetchone()
    if row["n"] > 0:
        rows = store._conn.execute(
            "SELECT symbol FROM index_constituents WHERE index_name = ?",
            (index_name,),
        ).fetchall()
        return [r["symbol"] for r in rows]

    if index_name == "NIFTY 500":
        placeholders = ",".join("?" for _ in _NIFTY_500_COMPONENTS)
        rows = store._conn.execute(
            f"SELECT DISTINCT symbol FROM index_constituents "
            f"WHERE index_name IN ({placeholders})",
            _NIFTY_500_COMPONENTS,
        ).fetchall()
        return [r["symbol"] for r in rows]

    return []


def _fetch_window(
    store: FlowStore,
    symbols: list[str],
    end_date: str,
    window: int,
) -> dict[str, list[tuple[str, float, float | None]]]:
    """Fetch last ``window`` trading days of price data ending on ``end_date``.

    Returns ``{symbol: [(date, close, prev_close), ...]}`` ordered oldest→newest.
    Uses `adj_close` when present, else `close`. ``prev_close`` is the raw
    bhavcopy prev_close — used only for advance/decline, which is a same-day
    delta and so doesn't need adjustment.

    Kept for backward compatibility; the bulk path now uses
    :func:`_fetch_symbol_history` directly.
    """
    if not symbols:
        return {}

    # Fetch a generous calendar-day window (3× trading days) to cover
    # weekends/holidays, then trim per-symbol to the last `window` rows.
    cal_window_days = max(window * 3, 400)
    placeholders = ",".join("?" for _ in symbols)
    rows = store._conn.execute(
        f"SELECT symbol, date, close, prev_close, "
        f"       COALESCE(adj_close, close) AS adj_close "
        f"FROM daily_stock_data "
        f"WHERE date <= ? "
        f"  AND date >= date(?, ? || ' days') "
        f"  AND symbol IN ({placeholders}) "
        f"ORDER BY symbol, date",
        (end_date, end_date, f"-{cal_window_days}", *symbols),
    ).fetchall()

    out: dict[str, list[tuple[str, float, float | None]]] = defaultdict(list)
    for r in rows:
        out[r["symbol"]].append((r["date"], r["adj_close"], r["prev_close"]))

    # Trim per-symbol to last `window` rows.
    return {sym: hist[-window:] for sym, hist in out.items()}


def _rolling_mean(arr: np.ndarray, window: int, min_periods: int) -> np.ndarray:
    """Rolling mean with the same semantics as pandas ``rolling(...).mean()``.

    O(N) via cumulative-sum differencing; returns ``np.nan`` for positions
    whose effective window length is below ``min_periods``.
    """
    n = arr.size
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    cum = np.empty(n + 1, dtype=float)
    cum[0] = 0.0
    np.cumsum(arr, out=cum[1:])
    # For position i (0-indexed), effective window = min(i+1, window).
    # The window covers indices [i - eff + 1, i].
    idx = np.arange(n)
    eff = np.minimum(idx + 1, window)
    mask = eff >= min_periods
    if not mask.any():
        return out
    starts = idx + 1 - eff
    ends = idx + 1
    sums = cum[ends] - cum[starts]
    out[mask] = sums[mask] / eff[mask]
    return out


def _rolling_extreme(
    arr: np.ndarray, window: int, *, kind: str,
) -> np.ndarray:
    """Rolling max or min (``kind='max'`` or ``kind='min'``) with min_periods=1.

    Uses :func:`numpy.lib.stride_tricks.sliding_window_view` for the
    full-window section and falls back to a Python loop for the warm-up
    prefix where the window is shorter than ``window``. O(N × window) in
    the worst case, which for window=252 and N≤2600 (10y) is ~650K ops
    per symbol — fast enough; the dominant cost remains the SQL fetch.
    """
    n = arr.size
    out = np.empty(n, dtype=float)
    if n == 0:
        return out

    reducer = np.max if kind == "max" else np.min
    if n < window:
        # Whole series is shorter than the window; just expanding-window.
        for i in range(n):
            out[i] = reducer(arr[: i + 1])
        return out

    # Warm-up: positions 0..window-2 use expanding window [0..i].
    for i in range(window - 1):
        out[i] = reducer(arr[: i + 1])
    # Stable section: positions window-1..n-1 use rolling window of fixed size.
    windows = np.lib.stride_tricks.sliding_window_view(arr, window)
    out[window - 1:] = reducer(windows, axis=1)
    return out


def _fetch_symbol_history(
    store: FlowStore,
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Fetch `daily_stock_data` for ``symbols`` in [start_date, end_date].

    Returns ``{symbol: (dates, adj_close, prev_close)}``: three parallel
    arrays sorted oldest→newest. ``dates`` is a string array (``<U10``);
    ``adj_close`` is float64; ``prev_close`` is float64 with ``np.nan`` for
    missing values. Symbols absent from the SQL result are omitted from
    the returned mapping.

    Caller is responsible for padding ``start_date`` backwards to include
    the 200-day warm-up window — this function does no padding of its own.
    """
    if not symbols:
        return {}

    placeholders = ",".join("?" for _ in symbols)
    rows = store._conn.execute(
        f"SELECT symbol, date, COALESCE(adj_close, close) AS adj_close, "
        f"       prev_close "
        f"FROM daily_stock_data "
        f"WHERE date BETWEEN ? AND ? "
        f"  AND symbol IN ({placeholders}) "
        f"ORDER BY symbol, date",
        (start_date, end_date, *symbols),
    ).fetchall()

    buckets: dict[str, list[tuple[str, float, float | None]]] = defaultdict(list)
    for r in rows:
        buckets[r["symbol"]].append(
            (r["date"], r["adj_close"], r["prev_close"]),
        )

    out: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for sym, hist in buckets.items():
        dates = np.array([h[0] for h in hist], dtype="U10")
        closes = np.array([h[1] for h in hist], dtype=float)
        prevs = np.array(
            [h[2] if h[2] is not None else np.nan for h in hist],
            dtype=float,
        )
        out[sym] = (dates, closes, prevs)
    return out


def _compute_index_range(
    store: FlowStore,
    index_name: str,
    range_dates: list[str],
) -> list[BreadthSnapshot]:
    """Compute one index's breadth snapshots across every date in ``range_dates``.

    Single-pass algorithm:

    1. Load constituents once.
    2. One SQL fetch of `daily_stock_data` covering
       ``[earliest_date - _LOOKBACK_PAD_DAYS calendar days, latest_date]``
       — wide enough to back-fill the 200-day rolling window for the
       first requested date.
    3. Per symbol, compute rolling 200-day mean of ``adj_close`` (O(N) via
       cumsum) and rolling 252-day max/min (O(N × 252)) — vectorised
       with numpy.
    4. For every requested date, accumulate the per-symbol contribution
       into per-date counters (advance / decline / new highs / new lows /
       above-200DMA numerator+denominator), then emit one
       :class:`BreadthSnapshot`.

    Memory budget: ~8 numeric arrays × N_symbols × N_days × 8 bytes —
    well under 100 MB even for 10y × 280 symbols.
    """
    symbols = _get_symbols(store, index_name)
    if not symbols or not range_dates:
        return []

    start_date = range_dates[0]
    end_date = range_dates[-1]

    # SQL date arithmetic for the lookback start: subtract enough calendar
    # days from the first range date to comfortably cover 252 trading days.
    row = store._conn.execute(
        "SELECT date(?, ? || ' days') AS d",
        (start_date, f"-{_LOOKBACK_PAD_DAYS}"),
    ).fetchone()
    fetch_start = row["d"]

    history = _fetch_symbol_history(store, symbols, fetch_start, end_date)
    if not history:
        return []

    # Per-date accumulators, keyed by date string.
    total: dict[str, int] = defaultdict(int)
    advance: dict[str, int] = defaultdict(int)
    decline: dict[str, int] = defaultdict(int)
    new_highs: dict[str, int] = defaultdict(int)
    new_lows: dict[str, int] = defaultdict(int)
    above_ma_num: dict[str, int] = defaultdict(int)
    above_ma_denom: dict[str, int] = defaultdict(int)

    range_set = set(range_dates)

    for sym, (dates, closes, prevs) in history.items():
        if dates.size == 0:
            continue

        ma = _rolling_mean(closes, _MA_WINDOW, _MIN_HISTORY_FOR_MA)
        hi = _rolling_extreme(closes, _HILO_WINDOW, kind="max")
        lo = _rolling_extreme(closes, _HILO_WINDOW, kind="min")

        # Per-row contribution to its date bucket — vectorised over symbol's rows.
        prev_notnull = ~np.isnan(prevs)
        adv_mask = (closes > prevs) & prev_notnull
        dec_mask = (closes < prevs) & prev_notnull
        # 52w hi/lo are inclusive (today is part of its own rolling window).
        hi_mask = closes >= hi
        lo_mask = closes <= lo
        ma_mask = ~np.isnan(ma)
        above_mask = ma_mask & (closes > ma)

        for i, d in enumerate(dates):
            if d not in range_set:
                continue
            total[d] += 1
            if adv_mask[i]:
                advance[d] += 1
            elif dec_mask[i]:
                decline[d] += 1
            if hi_mask[i]:
                new_highs[d] += 1
            if lo_mask[i]:
                new_lows[d] += 1
            if ma_mask[i]:
                above_ma_denom[d] += 1
                if above_mask[i]:
                    above_ma_num[d] += 1

    snapshots: list[BreadthSnapshot] = []
    for d in range_dates:
        t = total.get(d, 0)
        if t == 0:
            continue
        a = advance.get(d, 0)
        dec = decline.get(d, 0)
        unchanged = t - a - dec

        denom = above_ma_denom.get(d, 0)
        if denom > 0:
            pct: float | None = round(
                100.0 * above_ma_num.get(d, 0) / denom, 2,
            )
        else:
            pct = None

        ad_ratio: float | None = round(a / dec, 3) if dec > 0 else None

        snapshots.append(
            BreadthSnapshot(
                date=d,
                index_name=index_name,
                total=t,
                pct_above_200dma=pct,
                advance=a,
                decline=dec,
                unchanged=unchanged,
                new_52w_highs=new_highs.get(d, 0),
                new_52w_lows=new_lows.get(d, 0),
                ad_ratio=ad_ratio,
            )
        )

    return snapshots


def compute_snapshot(
    store: FlowStore, date: str, index_name: str,
) -> BreadthSnapshot | None:
    """Compute one breadth snapshot for (date, index_name).

    Returns None when the index has no constituents *or* no symbol in the
    index has any price on ``date`` (totally empty universe — caller should
    treat as "no data for this date yet"). When some symbols have data
    but few have ≥150 days history, `pct_above_200dma` is set to None on
    the returned snapshot but advance/decline/52w fields are still filled.

    Thin wrapper around :func:`_compute_index_range` — preserved for API
    compatibility. For backfilling many dates use :func:`compute_range`
    directly; it amortises the SQL fetch + rolling-window setup across
    the whole range.
    """
    snaps = _compute_index_range(store, index_name, [date])
    return snaps[0] if snaps else None


def compute_range(
    store: FlowStore,
    start: str,
    end: str,
    index_names: Iterable[str],
) -> list[BreadthSnapshot]:
    """Compute snapshots for every (date, index) in [start, end].

    Dates are restricted to those present in `daily_stock_data` (trading
    days only). Snapshots returned in (date, index_name) order. Indices
    with no data on a given date are silently skipped.

    Algorithm (single-pass per index):

    For each index in ``index_names`` we issue *one* SQL fetch covering
    the full range plus a ``_LOOKBACK_PAD_DAYS`` warm-up tail (so the
    200-day rolling mean is populated for the very first requested date),
    then compute rolling 200-day mean and rolling 252-day max/min per
    symbol via numpy. All per-date breadth aggregates (advance/decline
    counts, % above 200DMA, new 52w hi/lo) are accumulated as we walk
    each symbol's series once.

    Runtime is **O(N_symbols × N_days)** per index — i.e. linear in the
    universe size and the range length — versus the legacy O(N² × dates)
    that re-issued one SQL fetch per (date, index) pair. Empirically this
    is **10–50× faster** on multi-year backfills; the 28-index ×
    10-year backfill is fully unblocked.

    Memory footprint per index is bounded (~90 MB for a 10y × 280-symbol
    universe). Indices are processed one at a time, so peak memory stays
    constant in the number of indices.
    """
    index_list = list(index_names)
    rows = store._conn.execute(
        "SELECT DISTINCT date FROM daily_stock_data "
        "WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    ).fetchall()
    trading_days = [r["date"] for r in rows]
    if not trading_days:
        return []

    # Build per-index snapshot batches, then interleave back into
    # (date, index_name) order to preserve the legacy emit order.
    by_index: dict[str, dict[str, BreadthSnapshot]] = {}
    for idx in index_list:
        snaps = _compute_index_range(store, idx, trading_days)
        by_index[idx] = {s.date: s for s in snaps}

    out: list[BreadthSnapshot] = []
    for d in trading_days:
        for idx in index_list:
            snap = by_index.get(idx, {}).get(d)
            if snap is not None:
                out.append(snap)
    return out
