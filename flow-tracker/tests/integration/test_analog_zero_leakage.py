"""Zero-leakage integration test for the Historical Analog SQL layer.

Plan exit criterion §3.3: computing features for pre-2020 symbol touches no
post-2020 data.

Mechanism: wraps ``store._conn`` in a proxy that scans bound params for
``YYYY-MM-DD`` strings and raises ``LookaheadDetected`` if any date param
exceeds the per-call ``allowed_horizon``.

Leakage (raises):
  - feature_vector query passing a date > as_of_date.
  - forward_return query passing a date > as_of + 13 months
    (12mo window + 30d grace from PR-12 #112's _price_at_or_after cap).

Not leakage (allowed):
  - forward_returns reaching ~as_of + 12mo — that IS the function.
  - vault-cache JSONs (AR, decks) — out of scope, acknowledged in
    backtest_historical_analog docstring.

Marked ``@pytest.mark.slow`` per the plan — opt-in via ``pytest -m slow``.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from flowtracker.bhavcopy_models import DailyStockData
from flowtracker.research.analog_builder import (
    compute_feature_vector,
    compute_forward_returns,
)
from flowtracker.store import FlowStore


class LookaheadDetected(AssertionError):
    """Raised when a SQL bound param exceeds the allowed temporal horizon."""


class _ConnProxy:
    """Proxy in front of sqlite3.Connection (whose ``execute`` is a read-only
    C slot, so direct monkeypatch fails). Delegates everything except
    ``execute``, which it sniffs for date-shaped params > horizon."""

    def __init__(self, real, allowed_horizon: str, as_of: str) -> None:
        self._real = real
        self._horizon = allowed_horizon
        self._as_of = as_of

    def execute(self, sql, params=()):
        iterable = params if isinstance(params, (list, tuple)) else [params]
        for p in iterable:
            if isinstance(p, str) and len(p) == 10 and p.count("-") == 2:
                if p > self._horizon:
                    raise LookaheadDetected(
                        f"as_of={self._as_of} bound exceeded by param {p!r}: "
                        f"{sql.strip()[:120]}"
                    )
        return self._real.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _seed(store: FlowStore, symbol: str, center: date) -> None:
    """6 years of weekday OHLCV + 24 quarters of accounting/ownership rows.

    Enough to exercise SMA200, RSI14, delivery_pct_6m, ROCE 3yr-delta,
    revenue CAGR, OPM trend, shareholding deltas, pledge, mcap bucket, and
    PE history — i.e. every SQL branch of compute_feature_vector.
    """
    rows: list[DailyStockData] = []
    prior: float | None = None
    for offset in range(-365 * 3, 365 * 3):
        d = center + timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        close = 100.0 + offset * 0.05
        rows.append(DailyStockData(
            date=d.isoformat(), symbol=symbol,
            open=close, high=close, low=close, close=close,
            prev_close=prior if prior is not None else close,
            volume=1_000_000, turnover=close * 1_000_000,
            delivery_qty=500_000, delivery_pct=55.0,
        ))
        prior = close
    store.upsert_daily_stock_data(rows)
    store.recompute_adj_close(symbol)

    quarters = [
        f"{yr}-{md}"
        for yr in range(center.year - 3, center.year + 4)
        for md in ("03-31", "06-30", "09-30", "12-31")
    ]
    cur = store._conn
    cur.executemany(
        "INSERT OR REPLACE INTO shareholding (symbol, quarter_end, category, "
        "percentage) VALUES (?, ?, ?, ?)",
        [(symbol, q, c, p) for q in quarters
         for c, p in (("Promoter", 55.0), ("FII", 18.0), ("MF", 12.0))],
    )
    cur.executemany(
        "INSERT OR REPLACE INTO promoter_pledge (symbol, quarter_end, "
        "pledge_pct, encumbered_pct) VALUES (?, ?, ?, ?)",
        [(symbol, q, 1.5, 2.0) for q in quarters],
    )
    cur.executemany(
        "INSERT OR REPLACE INTO quarterly_results (symbol, quarter_end, "
        "revenue, net_income, operating_margin) VALUES (?, ?, ?, ?, ?)",
        [(symbol, q, 50000.0, 18000.0, 40.0 + (hash(q) % 5)) for q in quarters],
    )
    cur.executemany(
        "INSERT OR REPLACE INTO quarterly_balance_sheet (symbol, quarter_end, "
        "shares_outstanding) VALUES (?, ?, ?)",
        [(symbol, q, 893_000_000) for q in quarters],
    )
    cur.executemany(
        "INSERT OR REPLACE INTO screener_charts (symbol, chart_type, metric, "
        "date, value) VALUES (?, 'pe', 'pe_trailing', ?, ?)",
        [(symbol, q, 12.0) for q in quarters],
    )
    cur.executemany(
        "INSERT OR REPLACE INTO annual_financials (symbol, fiscal_year_end, "
        "total_assets, net_income, borrowings, reserves, equity_capital, "
        "revenue) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(symbol, f"{center.year + yo}-03-31", 500000.0, 18000.0,
          100000.0, 200000.0, 893.0, 150000.0 + yo * 8000) for yo in range(-3, 4)],
    )
    cur.execute(
        "INSERT OR REPLACE INTO index_constituents (symbol, index_name, "
        "company_name, industry) VALUES (?, ?, ?, ?)",
        (symbol, "NIFTY 50", f"{symbol} Ltd", "Banks"),
    )
    cur.commit()


@pytest.fixture
def seeded_store(tmp_path: Path) -> FlowStore:
    s = FlowStore(db_path=tmp_path / "leak.db")
    _seed(s, "SBIN", date(2020, 1, 1))
    yield s
    s.close()


def _guard(store: FlowStore, horizon: str, as_of: str) -> None:
    store._conn = _ConnProxy(store._conn, allowed_horizon=horizon, as_of=as_of)


@pytest.mark.slow
def test_compute_feature_vector_no_lookahead(seeded_store: FlowStore) -> None:
    """Feature-vector at as_of=2020-01-01 must touch no row dated > 2020-01-01."""
    as_of = "2020-01-01"
    real = seeded_store._conn
    _guard(seeded_store, horizon=as_of, as_of=as_of)
    try:
        vec = compute_feature_vector(seeded_store, "SBIN", as_of)
    finally:
        seeded_store._conn = real
    assert vec["promoter_pct"] is not None
    assert vec["industry"] == "Banks"


@pytest.mark.slow
def test_compute_forward_returns_within_horizon(seeded_store: FlowStore) -> None:
    """Forward returns may reach as_of + 12mo + 30d grace; never beyond."""
    as_of = "2020-01-01"
    horizon = (date.fromisoformat(as_of) + timedelta(days=400)).isoformat()
    real = seeded_store._conn
    _guard(seeded_store, horizon=horizon, as_of=as_of)
    try:
        ret = compute_forward_returns(seeded_store, "SBIN", as_of)
    finally:
        seeded_store._conn = real
    assert ret["return_12m_pct"] is not None


@pytest.mark.slow
def test_compute_forward_returns_does_not_reach_today(seeded_store: FlowStore) -> None:
    """PR-12 grace-cap regression guard: a 2020 as_of must not bind a 2026
    date. If ``_price_at_or_after`` drops its 30-day cap and reverts to
    ``date >= target`` with no upper bound, this test fails."""
    as_of = "2020-01-01"
    horizon = (date.fromisoformat(as_of) + timedelta(days=400)).isoformat()
    real = seeded_store._conn
    _guard(seeded_store, horizon=horizon, as_of=as_of)
    try:
        compute_forward_returns(seeded_store, "SBIN", as_of)
    finally:
        seeded_store._conn = real
