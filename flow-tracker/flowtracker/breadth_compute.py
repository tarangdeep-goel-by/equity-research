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


def compute_snapshot(
    store: FlowStore, date: str, index_name: str,
) -> BreadthSnapshot | None:
    """Compute one breadth snapshot for (date, index_name).

    Returns None when the index has no constituents *or* no symbol in the
    index has any price on ``date`` (totally empty universe — caller should
    treat as "no data for this date yet"). When some symbols have data
    but few have ≥150 days history, `pct_above_200dma` is set to None on
    the returned snapshot but advance/decline/52w fields are still filled.
    """
    symbols = _get_symbols(store, index_name)
    if not symbols:
        return None

    # Pull the full 252-day window — that covers the 200DMA, 52w hi/lo, and
    # today's row (last entry of each list).
    hist = _fetch_window(store, symbols, date, _HILO_WINDOW)
    if not hist:
        return None

    # Filter to symbols with a price ON `date` (last entry's date == date).
    # A symbol can be in the index but have no bar today (recent IPO,
    # suspended, etc.) — exclude from `total` so percentages are clean.
    todays = {
        sym: rows for sym, rows in hist.items()
        if rows and rows[-1][0] == date
    }
    if not todays:
        return None

    total = len(todays)
    advance = 0
    decline = 0
    unchanged = 0
    new_highs = 0
    new_lows = 0
    above_ma_num = 0
    above_ma_denom = 0  # symbols that have ≥150 days of history

    for sym, rows in todays.items():
        today_date, today_close, today_prev_close = rows[-1]

        # Advance/decline based on today's row's prev_close (raw, same-day).
        if today_prev_close is None:
            unchanged += 1
        elif today_close > today_prev_close:
            advance += 1
        elif today_close < today_prev_close:
            decline += 1
        else:
            unchanged += 1

        # 52w high/low — inclusive of today, over up to 252 trading days.
        closes_252 = [c for _, c, _ in rows]
        hi_252 = max(closes_252)
        lo_252 = min(closes_252)
        if today_close >= hi_252:
            new_highs += 1
        if today_close <= lo_252:
            new_lows += 1

        # 200DMA — last 200 trading days inclusive of today.
        closes_200 = closes_252[-_MA_WINDOW:]
        if len(closes_200) >= _MIN_HISTORY_FOR_MA:
            ma = sum(closes_200) / len(closes_200)
            above_ma_denom += 1
            if today_close > ma:
                above_ma_num += 1

    pct_above_200dma: float | None = (
        round(100.0 * above_ma_num / above_ma_denom, 2)
        if above_ma_denom > 0
        else None
    )
    ad_ratio: float | None = (
        round(advance / decline, 3) if decline > 0 else None
    )

    return BreadthSnapshot(
        date=date,
        index_name=index_name,
        total=total,
        pct_above_200dma=pct_above_200dma,
        advance=advance,
        decline=decline,
        unchanged=unchanged,
        new_52w_highs=new_highs,
        new_52w_lows=new_lows,
        ad_ratio=ad_ratio,
    )


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
    """
    index_list = list(index_names)
    rows = store._conn.execute(
        "SELECT DISTINCT date FROM daily_stock_data "
        "WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    ).fetchall()
    trading_days = [r["date"] for r in rows]

    out: list[BreadthSnapshot] = []
    for d in trading_days:
        for idx in index_list:
            snap = compute_snapshot(store, d, idx)
            if snap is not None:
                out.append(snap)
    return out
