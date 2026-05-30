"""Compute US market-breadth metrics from `us_daily_prices` (US add-on).

Mirrors India breadth (`breadth_compute.py`) over the US universe instead of
`daily_stock_data` + `index_constituents`. The US universe lives in
`symbol_registry` (markets NASDAQ / NYSE); each symbol is bucketed into a GICS
sector via the same granular-industry classification the research layer uses
(`ResearchDataAPI._get_industry` → `sector_kpis.get_sector_for_symbol`).

Indices produced per `as_of` date:
    "US 500"        — the WHOLE US universe (every registered US symbol).
    "US <sector>"   — one per resolved GICS sector key (e.g. "US banks",
                      "US it_services").

Definitions match India exactly (so the two surfaces are comparable):
    200DMA  — simple mean of `adj_close` over the last 200 trading days
              (inclusive of today). `adj_close` falls back to `close` when
              null. Requires >=150 trading days to compute (else
              `pct_above_200dma` is None for that symbol's contribution).
    52w hi/lo — rolling 252-trading-day max/min of `adj_close` ending today.
    Advance/Decline — today's `adj_close` vs the PREVIOUS trading row's
              `adj_close` (us_daily_prices has no stored prev_close column,
              so prev is the prior row in the symbol's own series).

The rolling helpers are imported from `breadth_compute` — NOT reimplemented —
so the math is byte-identical to India. India breadth is untouched.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from flowtracker.breadth_compute import _rolling_extreme, _rolling_mean
from flowtracker.breadth_models import BreadthSnapshot
from flowtracker.store import FlowStore

# US markets that make up the US universe in symbol_registry.
_US_MARKETS: tuple[str, ...] = ("NASDAQ", "NYSE")

# Lookback windows in trading days — identical to India.
_MA_WINDOW = 200
_HILO_WINDOW = 252
_MIN_HISTORY_FOR_MA = 150

# Whole-universe pseudo-index name + per-sector prefix.
_TOTAL_INDEX = "US 500"
_SECTOR_PREFIX = "US "


def _group_symbols_by_sector(store: FlowStore) -> dict[str, list[str]]:
    """Build {sector_key: [symbol, ...]} for the US universe.

    Resolves each registered US symbol's sector via the research layer's
    granular-industry classification (the same path India peers/sector
    detection uses). Symbols whose sector cannot be resolved are bucketed
    under the literal ``"unknown"`` key so they still count toward "US 500"
    but get their own per-sector row only if several share that fate.
    """
    # Local import keeps the research package out of the import graph for
    # callers that only touch India breadth.
    from flowtracker.research.data_api import ResearchDataAPI
    from flowtracker.research.sector_kpis import get_sector_for_symbol

    api = ResearchDataAPI(store=store)
    groups: dict[str, list[str]] = defaultdict(list)
    for market in _US_MARKETS:
        for entry in store.get_symbol_registry(market=market):
            sym = (entry.get("symbol") or "").upper()
            if not sym:
                continue
            industry = api._get_industry(sym)
            sector = get_sector_for_symbol(sym, industry) or "unknown"
            groups[sector].append(sym)
    return dict(groups)


def _fetch_us_history(
    store: FlowStore, symbols: list[str], end_date: str,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Fetch `us_daily_prices` for ``symbols`` up to ``end_date``.

    Returns ``{symbol: (dates, closes)}`` — two parallel arrays sorted
    oldest->newest. ``closes`` is ``COALESCE(adj_close, close)`` as float64.
    Symbols absent from the result are omitted. No date floor is applied; the
    table is per-symbol bounded and the rolling helpers warm up from the start
    of each series.
    """
    if not symbols:
        return {}
    placeholders = ",".join("?" for _ in symbols)
    rows = store._conn.execute(
        f"SELECT symbol, date, COALESCE(adj_close, close) AS px "  # noqa: S608
        f"FROM us_daily_prices "
        f"WHERE date <= ? AND symbol IN ({placeholders}) "
        f"  AND COALESCE(adj_close, close) IS NOT NULL "
        f"ORDER BY symbol, date",
        (end_date, *symbols),
    ).fetchall()

    buckets: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in rows:
        buckets[r["symbol"]].append((r["date"], r["px"]))

    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for sym, hist in buckets.items():
        dates = np.array([h[0] for h in hist], dtype="U10")
        closes = np.array([h[1] for h in hist], dtype=float)
        out[sym] = (dates, closes)
    return out


def _compute_group(
    history: dict[str, tuple[np.ndarray, np.ndarray]],
    symbols: list[str],
    index_name: str,
    as_of: str,
) -> BreadthSnapshot | None:
    """Compute one breadth snapshot for ``symbols`` on ``as_of``.

    Each symbol contributes only if its series has a row exactly on ``as_of``
    (i.e. it traded that day). Returns None when no symbol in the group traded
    on ``as_of``. ``pct_above_200dma`` is None when no symbol in the group has
    >=150 days of history.
    """
    total = 0
    advance = 0
    decline = 0
    new_highs = 0
    new_lows = 0
    above_num = 0
    above_denom = 0

    for sym in symbols:
        hd = history.get(sym)
        if hd is None:
            continue
        dates, closes = hd
        if dates.size == 0 or dates[-1] != as_of:
            # Symbol did not trade on as_of (its latest <= as_of row predates it).
            continue
        total += 1
        i = dates.size - 1

        # Advance / decline vs the previous trading row (us_daily_prices has no
        # stored prev_close, so prev is the prior row in this symbol's series).
        if i >= 1:
            prev = closes[i - 1]
            if closes[i] > prev:
                advance += 1
            elif closes[i] < prev:
                decline += 1

        # 52w hi/lo — inclusive rolling 252-day extreme ending today.
        hi = _rolling_extreme(closes, _HILO_WINDOW, kind="max")
        lo = _rolling_extreme(closes, _HILO_WINDOW, kind="min")
        if closes[i] >= hi[i]:
            new_highs += 1
        if closes[i] <= lo[i]:
            new_lows += 1

        # % above 200DMA (only when >=150 days history at this row).
        ma = _rolling_mean(closes, _MA_WINDOW, _MIN_HISTORY_FOR_MA)
        if not np.isnan(ma[i]):
            above_denom += 1
            if closes[i] > ma[i]:
                above_num += 1

    if total == 0:
        return None

    unchanged = total - advance - decline
    pct = round(100.0 * above_num / above_denom, 2) if above_denom > 0 else None
    ad_ratio = round(advance / decline, 3) if decline > 0 else None

    return BreadthSnapshot(
        date=as_of,
        index_name=index_name,
        total=total,
        pct_above_200dma=pct,
        advance=advance,
        decline=decline,
        unchanged=unchanged,
        new_52w_highs=new_highs,
        new_52w_lows=new_lows,
        ad_ratio=ad_ratio,
    )


def compute_us_breadth(
    store: FlowStore, as_of: str | None = None,
) -> list[BreadthSnapshot]:
    """Compute US breadth snapshots for ``as_of`` (default = latest US date).

    Produces one "US 500" snapshot over the whole US universe plus one
    "US <sector>" snapshot per resolved GICS sector key. Returns
    ``BreadthSnapshot`` rows (persist via ``store.upsert_us_breadth``). Returns
    an empty list when there is no US price data at all.
    """
    if as_of is None:
        row = store._conn.execute(
            "SELECT MAX(date) AS d FROM us_daily_prices"
        ).fetchone()
        as_of = row["d"] if row else None
    if as_of is None:
        return []

    groups = _group_symbols_by_sector(store)
    if not groups:
        return []

    all_symbols = sorted({s for syms in groups.values() for s in syms})
    history = _fetch_us_history(store, all_symbols, as_of)
    if not history:
        return []

    snapshots: list[BreadthSnapshot] = []

    # Whole-universe total first.
    total_snap = _compute_group(history, all_symbols, _TOTAL_INDEX, as_of)
    if total_snap is not None:
        snapshots.append(total_snap)

    # Per-sector rows, sector key alphabetical for stable display.
    for sector in sorted(groups):
        index_name = f"{_SECTOR_PREFIX}{sector}"
        snap = _compute_group(history, groups[sector], index_name, as_of)
        if snap is not None:
            snapshots.append(snap)

    return snapshots
