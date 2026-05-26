"""Tests for `market_breadth_daily` store methods."""

from __future__ import annotations

from flowtracker.breadth_models import BreadthSnapshot
from flowtracker.store import FlowStore


_SENTINEL = object()


def _snap(
    date: str = "2026-05-25",
    index_name: str = "NIFTY 500",
    *,
    total: int = 480,
    pct_above_200dma: float | None = 32.5,
    advance: int = 250,
    decline: int = 220,
    unchanged: int = 10,
    new_52w_highs: int = 12,
    new_52w_lows: int = 4,
    ad_ratio: float | None | object = _SENTINEL,
) -> BreadthSnapshot:
    # Default ad_ratio: derive from advance/decline. Pass `None` to force null.
    if ad_ratio is _SENTINEL:
        ad_ratio = round(advance / decline, 3) if decline else None
    return BreadthSnapshot(
        date=date,
        index_name=index_name,
        total=total,
        pct_above_200dma=pct_above_200dma,
        advance=advance,
        decline=decline,
        unchanged=unchanged,
        new_52w_highs=new_52w_highs,
        new_52w_lows=new_52w_lows,
        ad_ratio=ad_ratio,
    )


def test_upsert_and_get_latest_round_trip(store: FlowStore) -> None:
    """A snapshot upserted comes back out unchanged via get_breadth_latest."""
    snap = _snap()
    count = store.upsert_breadth_snapshots([snap])
    assert count == 1

    result = store.get_breadth_latest("NIFTY 500")
    assert result is not None
    assert result.date == snap.date
    assert result.index_name == "NIFTY 500"
    assert result.total == 480
    assert result.pct_above_200dma == 32.5
    assert result.advance == 250
    assert result.decline == 220
    assert result.unchanged == 10
    assert result.new_52w_highs == 12
    assert result.new_52w_lows == 4
    assert result.ad_ratio is not None
    assert abs(result.ad_ratio - 250 / 220) < 1e-3


def test_upsert_is_idempotent_on_date_index_unique(store: FlowStore) -> None:
    """Re-upserting the same (date, index) overwrites — no duplicates."""
    s1 = _snap(pct_above_200dma=30.0)
    s2 = _snap(pct_above_200dma=45.0)
    store.upsert_breadth_snapshots([s1])
    store.upsert_breadth_snapshots([s2])

    rows = store._conn.execute(
        "SELECT COUNT(*) AS n FROM market_breadth_daily "
        "WHERE date = ? AND index_name = ?",
        (s1.date, s1.index_name),
    ).fetchone()
    assert rows["n"] == 1

    latest = store.get_breadth_latest("NIFTY 500")
    assert latest is not None
    assert latest.pct_above_200dma == 45.0  # last write wins


def test_get_breadth_latest_returns_most_recent_date(store: FlowStore) -> None:
    """When multiple dates exist, latest is returned."""
    older = _snap(date="2026-05-01", pct_above_200dma=20.0)
    newer = _snap(date="2026-05-25", pct_above_200dma=40.0)
    store.upsert_breadth_snapshots([older, newer])

    latest = store.get_breadth_latest("NIFTY 500")
    assert latest is not None
    assert latest.date == "2026-05-25"
    assert latest.pct_above_200dma == 40.0


def test_get_breadth_latest_returns_none_when_empty(store: FlowStore) -> None:
    assert store.get_breadth_latest("NIFTY 500") is None


def test_get_breadth_latest_per_index(store: FlowStore) -> None:
    """Different indices return their own latest row."""
    a = _snap(index_name="NIFTY 50", total=50)
    b = _snap(index_name="NIFTY 500", total=480)
    store.upsert_breadth_snapshots([a, b])

    assert store.get_breadth_latest("NIFTY 50").total == 50
    assert store.get_breadth_latest("NIFTY 500").total == 480


def test_get_breadth_trend_orders_newest_first(store: FlowStore) -> None:
    """Trend returns up to N rows for one index, newest date first."""
    snaps = [
        _snap(date=f"2026-05-{d:02d}", pct_above_200dma=float(d))
        for d in range(20, 26)
    ]
    store.upsert_breadth_snapshots(snaps)

    trend = store.get_breadth_trend("NIFTY 500", days=10)
    assert len(trend) == 6
    assert trend[0].date == "2026-05-25"
    assert trend[-1].date == "2026-05-20"
    # pct_above_200dma should walk down monotonically (newest first)
    for i in range(len(trend) - 1):
        assert trend[i].pct_above_200dma >= trend[i + 1].pct_above_200dma


def test_get_breadth_trend_respects_limit(store: FlowStore) -> None:
    snaps = [
        _snap(date=f"2026-05-{d:02d}") for d in range(1, 26)
    ]
    store.upsert_breadth_snapshots(snaps)
    assert len(store.get_breadth_trend("NIFTY 500", days=5)) == 5


def test_get_breadth_for_date_returns_all_indices(store: FlowStore) -> None:
    """For a given date, all indices' snapshots come back."""
    snaps = [
        _snap(index_name="NIFTY 50"),
        _snap(index_name="NIFTY 500"),
        _snap(index_name="NIFTY MIDCAP 150"),
        _snap(index_name="NIFTY SMALLCAP 250"),
    ]
    store.upsert_breadth_snapshots(snaps)

    rows = store.get_breadth_for_date("2026-05-25")
    assert len(rows) == 4
    assert {r.index_name for r in rows} == {
        "NIFTY 50", "NIFTY 500", "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250",
    }


def test_pct_above_200dma_none_round_trip(store: FlowStore) -> None:
    """`pct_above_200dma=None` survives the round trip (insufficient history)."""
    snap = _snap(pct_above_200dma=None, ad_ratio=None)
    store.upsert_breadth_snapshots([snap])
    latest = store.get_breadth_latest("NIFTY 500")
    assert latest is not None
    assert latest.pct_above_200dma is None
    assert latest.ad_ratio is None
