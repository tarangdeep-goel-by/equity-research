"""Tests for ``gst_collections_monthly`` store methods (feat/gst-collections).

Round-trip: upsert → get_latest → get_trend → get_yoy_series.
"""

from __future__ import annotations

import pytest

from flowtracker.gst_models import GSTCollectionMonth
from flowtracker.store import FlowStore


def _make_row(period: str, gross: float, **extra) -> GSTCollectionMonth:
    """Build a minimal but realistic GST row. ``extra`` overrides any field."""
    base = {
        "period": period,
        "gross_collection_cr": gross,
        "cgst_cr": round(gross * 0.20, 1),
        "sgst_cr": round(gross * 0.25, 1),
        "igst_cr": round(gross * 0.48, 1),
        "cess_cr": round(gross * 0.07, 1),
        "domestic_cr": round(gross * 0.82, 1),
        "imports_cr": round(gross * 0.18, 1),
        "growth_yoy_pct": 10.0,
        "source_url": f"https://example.test/gst/{period}.pdf",
    }
    base.update(extra)
    return GSTCollectionMonth(**base)


# ---------------------------------------------------------------------------
# upsert + get_latest
# ---------------------------------------------------------------------------


def test_upsert_then_get_latest_round_trip(store: FlowStore) -> None:
    rows = [
        _make_row("2024-04", 210267.0, growth_yoy_pct=12.4),
        _make_row("2024-05", 172739.0, growth_yoy_pct=10.0),
    ]
    n = store.upsert_gst_collections(rows)
    assert n == 2

    latest = store.get_gst_latest()
    assert latest is not None
    assert latest.period == "2024-05"
    assert latest.gross_collection_cr == pytest.approx(172739.0)
    assert latest.growth_yoy_pct == pytest.approx(10.0)
    assert latest.source_url == "https://example.test/gst/2024-05.pdf"


def test_get_latest_on_empty_table_returns_none(store: FlowStore) -> None:
    assert store.get_gst_latest() is None


def test_upsert_empty_list_is_noop(store: FlowStore) -> None:
    assert store.upsert_gst_collections([]) == 0
    assert store.get_gst_latest() is None


# ---------------------------------------------------------------------------
# Idempotency / upsert semantics
# ---------------------------------------------------------------------------


def test_upsert_is_idempotent_on_period(store: FlowStore) -> None:
    """Re-upserting the same period replaces (UNIQUE(period) constraint)."""
    row_v1 = _make_row("2024-04", 200000.0, growth_yoy_pct=10.0)
    row_v2 = _make_row("2024-04", 210267.0, growth_yoy_pct=12.4)  # revised
    store.upsert_gst_collections([row_v1])
    store.upsert_gst_collections([row_v2])

    rows = store.get_gst_trend(months=12)
    assert len(rows) == 1
    assert rows[0]["gross_collection_cr"] == pytest.approx(210267.0)
    assert rows[0]["growth_yoy_pct"] == pytest.approx(12.4)


def test_upsert_partial_row_persists_none_fields(store: FlowStore) -> None:
    """A parser that only resolved gross + YoY should still persist the row."""
    partial = GSTCollectionMonth(
        period="2024-04",
        gross_collection_cr=210267.0,
        growth_yoy_pct=12.4,
        # cgst_cr / sgst_cr / igst_cr / cess_cr / domestic_cr / imports_cr / source_url
        # all default to None — defensive parser scenario from the plan.
    )
    store.upsert_gst_collections([partial])
    latest = store.get_gst_latest()
    assert latest is not None
    assert latest.cgst_cr is None
    assert latest.source_url is None
    assert latest.gross_collection_cr == pytest.approx(210267.0)


# ---------------------------------------------------------------------------
# get_gst_trend
# ---------------------------------------------------------------------------


def test_trend_returns_newest_first(store: FlowStore) -> None:
    rows = [
        _make_row("2024-01", 172129.0),
        _make_row("2024-02", 168337.0),
        _make_row("2024-03", 178484.0),
        _make_row("2024-04", 210267.0),
    ]
    store.upsert_gst_collections(rows)
    trend = store.get_gst_trend(months=12)
    assert [r["period"] for r in trend] == ["2024-04", "2024-03", "2024-02", "2024-01"]


def test_trend_respects_months_limit(store: FlowStore) -> None:
    rows = [_make_row(f"2024-{m:02d}", 170000.0 + m * 1000) for m in range(1, 13)]
    store.upsert_gst_collections(rows)
    trend = store.get_gst_trend(months=3)
    assert len(trend) == 3
    assert [r["period"] for r in trend] == ["2024-12", "2024-11", "2024-10"]


def test_trend_months_below_one_returns_empty(store: FlowStore) -> None:
    store.upsert_gst_collections([_make_row("2024-04", 210267.0)])
    assert store.get_gst_trend(months=0) == []


def test_trend_on_empty_table_returns_empty(store: FlowStore) -> None:
    assert store.get_gst_trend(months=12) == []


# ---------------------------------------------------------------------------
# get_gst_yoy_series — computed YoY (not the published one)
# ---------------------------------------------------------------------------


def test_yoy_series_computes_correctly_year_over_year(store: FlowStore) -> None:
    """Two months × two years → one YoY pair per shared month."""
    store.upsert_gst_collections([
        _make_row("2023-04", 187035.0),
        _make_row("2024-04", 210267.0),  # YoY = +12.42%
    ])
    series = store.get_gst_yoy_series()
    assert len(series) == 1
    row = series[0]
    assert row["period"] == "2024-04"
    assert row["gross_cr"] == pytest.approx(210267.0)
    assert row["prior_year_gross_cr"] == pytest.approx(187035.0)
    # (210267 - 187035) / 187035 * 100 = 12.4156...
    assert row["computed_yoy_pct"] == pytest.approx(12.42, abs=0.01)


def test_yoy_series_orders_ascending_and_skips_unpaired_months(
    store: FlowStore,
) -> None:
    """Months without a prior-year peer must NOT appear in the series."""
    store.upsert_gst_collections([
        _make_row("2023-04", 187035.0),
        _make_row("2023-05", 157090.0),
        _make_row("2024-04", 210267.0),
        # 2024-05 has no peer => excluded
        _make_row("2024-06", 174000.0),  # no peer => excluded
    ])
    series = store.get_gst_yoy_series()
    assert [r["period"] for r in series] == ["2024-04"]


def test_yoy_series_handles_zero_prior_year_without_divbyzero(
    store: FlowStore,
) -> None:
    """A zero prior-year value must yield NULL YoY, not a crash."""
    store.upsert_gst_collections([
        _make_row("2023-04", 0.0),
        _make_row("2024-04", 210267.0),
    ])
    series = store.get_gst_yoy_series()
    assert len(series) == 1
    assert series[0]["computed_yoy_pct"] is None


def test_yoy_series_empty_table(store: FlowStore) -> None:
    assert store.get_gst_yoy_series() == []
