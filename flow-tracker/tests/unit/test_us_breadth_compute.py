"""US market breadth — compute + store round-trip (US add-on, Phase 3).

Mirrors India breadth over `us_daily_prices` grouped by GICS sector. India
breadth (`compute_snapshot` / `market_breadth_daily`) must stay untouched.
All temp-DB, no network.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from flowtracker.breadth_models import BreadthSnapshot
from flowtracker.store import FlowStore
from flowtracker.us_breadth_compute import compute_us_breadth

US = "NASDAQ"
N_DAYS = 260

# 8 US symbols across 2 GICS sectors (granular yfinance industries that the
# keystone classifier resolves: banks + it_services). Per-symbol price shape:
#   "up"   — monotone rising → above 200DMA, at a new 52w high, advancing.
#   "down" — monotone falling → below 200DMA, at a new 52w low, declining.
SYMBOLS: list[tuple[str, str, str, str]] = [
    # (symbol, granular industry, expected sector key, shape)
    ("JPM", "Banks - Diversified", "banks", "up"),
    ("BAC", "Banks - Diversified", "banks", "up"),
    ("WFC", "Banks - Diversified", "banks", "down"),
    ("C", "Banks - Diversified", "banks", "down"),
    ("NVDA", "Semiconductors", "it_services", "up"),
    ("MSFT", "Software - Infrastructure", "it_services", "up"),
    ("AMD", "Semiconductors", "it_services", "up"),
    ("INTC", "Semiconductors", "it_services", "down"),
]


def _series(shape: str) -> list[float]:
    """Return N_DAYS of synthetic closes for a given trend shape."""
    if shape == "up":
        return [100.0 + i for i in range(N_DAYS)]      # ends at its 52w high
    # "down": monotone decline, ends at its 52w low, below its own 200DMA.
    return [400.0 - i for i in range(N_DAYS)]


@pytest.fixture
def store(tmp_path) -> FlowStore:
    db = tmp_path / "us_breadth.db"
    with FlowStore(db_path=db) as s:
        dates = [
            (date(2025, 1, 1) + timedelta(days=d)).isoformat()
            for d in range(N_DAYS)
        ]
        for sym, industry, _sector, shape in SYMBOLS:
            s.upsert_symbol_registry(
                sym, US, company_name=f"{sym} Inc.", industry=industry,
            )
            closes = _series(shape)
            rows = [
                {
                    "symbol": sym, "market": US, "date": dt,
                    "open": px, "high": px, "low": px, "close": px,
                    "volume": 1000, "adj_close": px,
                }
                for dt, px in zip(dates, closes)
            ]
            s.upsert_us_daily_prices(rows)
        yield s


def test_compute_us_breadth_total_and_sectors(store: FlowStore):
    snaps = compute_us_breadth(store)
    by_name = {s.index_name: s for s in snaps}

    # US 500 (whole universe) + one per sector.
    assert "US 500" in by_name
    assert "US banks" in by_name
    assert "US it_services" in by_name

    total = by_name["US 500"]
    assert total.total == 8                      # all 8 symbols traded as_of
    banks = by_name["US banks"]
    it = by_name["US it_services"]
    assert banks.total == 4
    assert it.total == 4

    # Advance/decline: 2 up + 2 down in banks; 3 up + 1 down in IT.
    assert banks.advance == 2 and banks.decline == 2
    assert it.advance == 3 and it.decline == 1
    assert total.advance == 5 and total.decline == 3
    # unchanged is the residual.
    assert total.unchanged == total.total - total.advance - total.decline

    # 52w highs/lows: every "up" symbol ends at its high, every "down" at its low.
    assert total.new_52w_highs == 5
    assert total.new_52w_lows == 3

    # pct_above_200dma plausible: up symbols above, down below → 5/8 = 62.5%.
    assert total.pct_above_200dma == pytest.approx(62.5, abs=0.01)
    assert banks.pct_above_200dma == pytest.approx(50.0, abs=0.01)
    assert it.pct_above_200dma == pytest.approx(75.0, abs=0.01)

    # ad_ratio = advance / decline when decline > 0.
    assert total.ad_ratio == pytest.approx(5 / 3, abs=0.01)


def test_us_breadth_store_round_trip(store: FlowStore):
    snaps = compute_us_breadth(store)
    written = store.upsert_us_breadth(snaps)
    assert written == len(snaps)

    latest = store.get_us_breadth_latest()
    assert {s.index_name for s in latest} == {s.index_name for s in snaps}
    assert all(isinstance(s, BreadthSnapshot) for s in latest)

    total = next(s for s in latest if s.index_name == "US 500")
    assert total.total == 8

    # History for one index.
    hist = store.get_us_breadth_history("US 500", days=10)
    assert len(hist) == 1
    assert hist[0].index_name == "US 500"

    # Idempotent recompute (same date overwrites, no row growth).
    store.upsert_us_breadth(snaps)
    assert len(store.get_us_breadth_latest()) == len(snaps)


def test_india_breadth_untouched(store: FlowStore):
    """US breadth never writes to or reads from the India breadth surface."""
    from flowtracker import breadth_compute

    # India compute helpers import + run clean on an India-empty DB.
    assert breadth_compute.compute_snapshot(store, "2025-09-01", "NIFTY 50") is None

    # Computing + persisting US breadth leaves market_breadth_daily empty.
    store.upsert_us_breadth(compute_us_breadth(store))
    india_rows = store._conn.execute(
        "SELECT COUNT(*) AS n FROM market_breadth_daily"
    ).fetchone()["n"]
    assert india_rows == 0
    us_rows = store._conn.execute(
        "SELECT COUNT(*) AS n FROM us_market_breadth_daily"
    ).fetchone()["n"]
    assert us_rows > 0
