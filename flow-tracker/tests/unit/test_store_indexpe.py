"""Round-trip + percentile tests for FlowStore index-valuation methods.

Covers the `index_valuation_daily` table introduced in feat/indexpe.
"""

from __future__ import annotations

from datetime import date, timedelta

from flowtracker.indexpe_models import IndexValuation
from flowtracker.store import FlowStore, _percentile_rank


def _row(d: str, pe: float, pb: float = 3.0, divy: float = 1.0) -> IndexValuation:
    return IndexValuation(
        date=d, index_name="NIFTY SMALLCAP 250",
        pe=pe, pb=pb, dividend_yield=divy,
    )


# ----- upsert / get round-trip ------------------------------------------------


def test_upsert_then_get_history(store: FlowStore):
    rows = [_row("2025-01-01", 28.0), _row("2025-01-02", 29.5)]
    assert store.upsert_index_valuations(rows) == 2

    history = store.get_index_valuation_history("NIFTY SMALLCAP 250")
    assert [r.date for r in history] == ["2025-01-01", "2025-01-02"]
    assert history[0].pe == 28.0
    assert history[1].pe == 29.5


def test_get_history_days_filter(store: FlowStore):
    today = date.today()
    rows = [
        _row((today - timedelta(days=400)).isoformat(), 25.0),
        _row((today - timedelta(days=10)).isoformat(), 30.0),
        _row(today.isoformat(), 31.0),
    ]
    store.upsert_index_valuations(rows)

    last_30 = store.get_index_valuation_history("NIFTY SMALLCAP 250", days=30)
    assert len(last_30) == 2  # 10 days ago + today
    full = store.get_index_valuation_history("NIFTY SMALLCAP 250")
    assert len(full) == 3


def test_upsert_idempotent_on_pk(store: FlowStore):
    """Re-upserting the same (date, index_name) overwrites rather than dupes."""
    store.upsert_index_valuations([_row("2025-01-01", 28.0)])
    store.upsert_index_valuations([_row("2025-01-01", 28.5)])  # value updated

    history = store.get_index_valuation_history("NIFTY SMALLCAP 250")
    assert len(history) == 1
    assert history[0].pe == 28.5


def test_upsert_empty_list_returns_zero(store: FlowStore):
    assert store.upsert_index_valuations([]) == 0


def test_latest_returns_most_recent(store: FlowStore):
    store.upsert_index_valuations([
        _row("2025-01-01", 28.0),
        _row("2025-01-05", 29.0),
        _row("2025-01-03", 28.5),
    ])
    latest = store.get_index_valuation_latest("NIFTY SMALLCAP 250")
    assert latest is not None
    assert latest.date == "2025-01-05"
    assert latest.pe == 29.0


def test_latest_returns_none_when_empty(store: FlowStore):
    assert store.get_index_valuation_latest("NIFTY SMALLCAP 250") is None


def test_index_name_uppercased_on_write(store: FlowStore):
    """Lookups are case-insensitive because rows are upserted upper-cased."""
    store.upsert_index_valuations([
        IndexValuation(date="2025-01-01", index_name="nifty smallcap 250",
                       pe=28.0, pb=3.0, dividend_yield=1.0),
    ])
    assert store.get_index_valuation_history("Nifty Smallcap 250")
    assert store.get_index_valuation_latest("NIFTY SMALLCAP 250") is not None


# ----- percentile math --------------------------------------------------------


def test_percentile_helper_basic():
    """Sanity-check the standalone percentile ranker (<=v semantics)."""
    series = [10.0, 20.0, 30.0, 40.0, 50.0]
    # value equal to the max → 100th percentile
    assert _percentile_rank(50.0, series) == 100.0
    # value equal to the min → 20th percentile (1 of 5 obs are <=)
    assert _percentile_rank(10.0, series) == 20.0
    # median → 60% (3 of 5 are <= 30)
    assert _percentile_rank(30.0, series) == 60.0
    assert _percentile_rank(None, series) is None
    assert _percentile_rank(50.0, []) is None


def test_percentile_seeded_10yr_distribution(store: FlowStore):
    """Seed a known distribution and assert percentile correctness.

    PE values are evenly spread 15..40 in 0.5 increments over ~10 years.
    The latest row is PE=39.0 → percentile = (# obs <=39.0) / 51.
    """
    base = date(2015, 1, 1)
    pe_values = [15.0 + 0.5 * i for i in range(51)]  # 15.0, 15.5, ..., 40.0
    rows: list[IndexValuation] = []
    for i, pe in enumerate(pe_values[:-1]):
        rows.append(IndexValuation(
            date=(base + timedelta(days=i)).isoformat(),
            index_name="NIFTY SMALLCAP 250",
            pe=pe, pb=3.0, dividend_yield=1.0,
        ))
    # "current" / latest row
    rows.append(IndexValuation(
        date=(base + timedelta(days=200)).isoformat(),
        index_name="NIFTY SMALLCAP 250",
        pe=39.0, pb=4.0, dividend_yield=0.8,
    ))
    store.upsert_index_valuations(rows)

    payload = store.get_index_valuation_percentile("NIFTY SMALLCAP 250")
    assert payload["index_name"] == "NIFTY SMALLCAP 250"
    assert payload["sample_size"] == 51
    assert payload["current"]["pe"] == 39.0

    # 49 values in 15..38.5 are < 39, plus the 39.0 row itself = 50 obs <=
    expected_pct = round(100.0 * 50 / 51, 2)
    assert payload["pe_percentile"] == expected_pct
    # PB is 3.0 for all but the latest (4.0) → percentile = 100
    assert payload["pb_percentile"] == 100.0
    # 50 of 51 div-yield observations are 1.0 (and latest is 0.8 < 1.0) →
    # only the latest is <= 0.8, so percentile = 1/51
    assert payload["divy_percentile"] == round(100.0 * 1 / 51, 2)


def test_percentile_empty_history_returns_empty(store: FlowStore):
    assert store.get_index_valuation_percentile("NIFTY SMALLCAP 250") == {}
