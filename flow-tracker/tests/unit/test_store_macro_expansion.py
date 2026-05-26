"""Tests for the macro-expansion store methods (CPI / IIP / PMI / yield curve).

Round-trip pattern: upsert -> get_latest -> get_trend. Mirrors the existing
``test_store_gst.py`` pattern. Plus the yield-curve gsec_{1y,5y,30y}
columns being readable through ``get_macro_latest``.
"""

from __future__ import annotations

import pytest

from flowtracker.cpi_models import CPIMonth
from flowtracker.iip_models import IIPMonth
from flowtracker.macro_models import MacroSnapshot
from flowtracker.pmi_models import PMIMonth
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# CPI store round-trip
# ---------------------------------------------------------------------------


def test_cpi_upsert_then_get_latest(store: FlowStore) -> None:
    rows = [
        CPIMonth(period="2025-01", cpi_index=193.7, yoy_pct=4.31, source="FRED"),
        CPIMonth(period="2025-02", cpi_index=193.8, yoy_pct=3.61, source="FRED"),
    ]
    assert store.upsert_cpi_monthly(rows) == 2

    latest = store.get_cpi_latest()
    assert latest is not None
    assert latest.period == "2025-02"
    assert latest.cpi_index == pytest.approx(193.8)
    assert latest.yoy_pct == pytest.approx(3.61)
    assert latest.source == "FRED"


def test_cpi_get_latest_on_empty(store: FlowStore) -> None:
    assert store.get_cpi_latest() is None


def test_cpi_upsert_empty_is_noop(store: FlowStore) -> None:
    assert store.upsert_cpi_monthly([]) == 0


def test_cpi_upsert_idempotent_on_period(store: FlowStore) -> None:
    """Re-upserting the same period replaces, not duplicates."""
    store.upsert_cpi_monthly([CPIMonth(period="2025-01", cpi_index=193.0, yoy_pct=4.0)])
    store.upsert_cpi_monthly([CPIMonth(period="2025-01", cpi_index=193.7, yoy_pct=4.31)])
    rows = store.get_cpi_trend(months=12)
    assert len(rows) == 1
    assert rows[0]["yoy_pct"] == pytest.approx(4.31)


def test_cpi_trend_newest_first(store: FlowStore) -> None:
    store.upsert_cpi_monthly([
        CPIMonth(period="2025-01", cpi_index=193.7, yoy_pct=4.31),
        CPIMonth(period="2025-02", cpi_index=193.8, yoy_pct=3.61),
        CPIMonth(period="2025-03", cpi_index=194.0, yoy_pct=3.34),
    ])
    rows = store.get_cpi_trend(months=12)
    assert [r["period"] for r in rows] == ["2025-03", "2025-02", "2025-01"]


def test_cpi_trend_respects_limit(store: FlowStore) -> None:
    store.upsert_cpi_monthly([
        CPIMonth(period=f"2024-{m:02d}", cpi_index=180.0 + m, yoy_pct=4.0)
        for m in range(1, 13)
    ])
    rows = store.get_cpi_trend(months=3)
    assert len(rows) == 3
    assert rows[0]["period"] == "2024-12"


def test_cpi_trend_below_one_returns_empty(store: FlowStore) -> None:
    store.upsert_cpi_monthly([CPIMonth(period="2025-01", cpi_index=193.7, yoy_pct=4.31)])
    assert store.get_cpi_trend(months=0) == []


def test_cpi_partial_row_persists(store: FlowStore) -> None:
    """A defensive-parser row with only one numeric field still persists."""
    store.upsert_cpi_monthly([CPIMonth(period="2025-04", yoy_pct=3.16)])
    latest = store.get_cpi_latest()
    assert latest is not None
    assert latest.cpi_index is None
    assert latest.yoy_pct == pytest.approx(3.16)


# ---------------------------------------------------------------------------
# IIP store round-trip
# ---------------------------------------------------------------------------


def test_iip_upsert_then_get_latest(store: FlowStore) -> None:
    rows = [
        IIPMonth(period="2025-01", iip_index=156.4, yoy_pct=5.0, source="FRED"),
        IIPMonth(period="2025-02", iip_index=147.8, yoy_pct=2.9, source="FRED"),
    ]
    assert store.upsert_iip_monthly(rows) == 2

    latest = store.get_iip_latest()
    assert latest is not None
    assert latest.period == "2025-02"
    assert latest.iip_index == pytest.approx(147.8)
    assert latest.yoy_pct == pytest.approx(2.9)


def test_iip_upsert_idempotent(store: FlowStore) -> None:
    store.upsert_iip_monthly([IIPMonth(period="2025-01", iip_index=150.0, yoy_pct=4.0)])
    store.upsert_iip_monthly([IIPMonth(period="2025-01", iip_index=156.4, yoy_pct=5.0)])
    rows = store.get_iip_trend(months=12)
    assert len(rows) == 1
    assert rows[0]["iip_index"] == pytest.approx(156.4)


def test_iip_trend_handles_negative_yoy(store: FlowStore) -> None:
    """IIP April 2020 lockdown print was -57% — must round-trip cleanly."""
    store.upsert_iip_monthly([IIPMonth(period="2020-04", iip_index=53.6, yoy_pct=-57.3)])
    latest = store.get_iip_latest()
    assert latest is not None
    assert latest.yoy_pct == pytest.approx(-57.3)


# ---------------------------------------------------------------------------
# PMI store round-trip
# ---------------------------------------------------------------------------


def test_pmi_upsert_then_get_latest(store: FlowStore) -> None:
    rows = [
        PMIMonth(period="2025-03", services_pmi=58.5, manufacturing_pmi=58.1),
        PMIMonth(period="2025-04", services_pmi=58.7, manufacturing_pmi=58.2),
    ]
    assert store.upsert_pmi_monthly(rows) == 2

    latest = store.get_pmi_latest()
    assert latest is not None
    assert latest.period == "2025-04"
    assert latest.services_pmi == pytest.approx(58.7)
    assert latest.manufacturing_pmi == pytest.approx(58.2)


def test_pmi_partial_row_persists(store: FlowStore) -> None:
    """A Manufacturing-only release (Services follow-up not yet out) persists
    cleanly with services_pmi=None."""
    store.upsert_pmi_monthly([PMIMonth(period="2025-05", manufacturing_pmi=57.5)])
    latest = store.get_pmi_latest()
    assert latest is not None
    assert latest.manufacturing_pmi == pytest.approx(57.5)
    assert latest.services_pmi is None


def test_pmi_idempotent(store: FlowStore) -> None:
    store.upsert_pmi_monthly([PMIMonth(period="2025-03", services_pmi=58.0)])
    store.upsert_pmi_monthly([PMIMonth(period="2025-03", services_pmi=58.5, manufacturing_pmi=58.1)])
    rows = store.get_pmi_trend(months=12)
    assert len(rows) == 1
    assert rows[0]["services_pmi"] == pytest.approx(58.5)
    assert rows[0]["manufacturing_pmi"] == pytest.approx(58.1)


# ---------------------------------------------------------------------------
# Yield curve — macro_daily extensions (gsec_1y/5y/30y)
# ---------------------------------------------------------------------------


def test_macro_snapshot_round_trips_full_curve(store: FlowStore) -> None:
    """gsec_1y / gsec_5y / gsec_30y round-trip through upsert -> get_latest."""
    snap = MacroSnapshot(
        date="2025-03-31",
        gsec_1y=6.45,
        gsec_5y=6.62,
        gsec_10y=6.58,
        gsec_30y=6.90,
    )
    store.upsert_macro_snapshots([snap])
    latest = store.get_macro_latest()
    assert latest is not None
    assert latest.date == "2025-03-31"
    assert latest.gsec_1y == pytest.approx(6.45)
    assert latest.gsec_5y == pytest.approx(6.62)
    assert latest.gsec_10y == pytest.approx(6.58)
    assert latest.gsec_30y == pytest.approx(6.90)


def test_yield_curve_history_orders_ascending(store: FlowStore) -> None:
    """get_yield_curve_history returns date ASC for chart-friendly consumption."""
    from datetime import date, timedelta
    today = date.today()
    d1 = (today - timedelta(days=30)).isoformat()
    d2 = (today - timedelta(days=10)).isoformat()
    d3 = (today - timedelta(days=20)).isoformat()
    store.upsert_macro_snapshots([
        MacroSnapshot(date=d1, gsec_1y=6.40, gsec_10y=6.55),
        MacroSnapshot(date=d2, gsec_1y=6.50, gsec_10y=6.62),
        MacroSnapshot(date=d3, gsec_1y=6.45, gsec_10y=6.58),
    ])
    history = store.get_yield_curve_history(days=365)
    dates = [r["date"] for r in history]
    assert dates == sorted(dates)
    assert dates[0] == d1
    assert dates[-1] == d2


def test_yield_curve_history_skips_null_only_rows(store: FlowStore) -> None:
    """Rows where every gsec_* is NULL (FX-only) should be filtered out."""
    from datetime import date, timedelta
    today = date.today()
    d1 = (today - timedelta(days=10)).isoformat()
    d2 = (today - timedelta(days=5)).isoformat()
    store.upsert_macro_snapshots([
        MacroSnapshot(date=d1, gsec_10y=6.58),
        MacroSnapshot(date=d2, usd_inr=85.0),  # no gsec_*
    ])
    history = store.get_yield_curve_history(days=365)
    assert len(history) == 1
    assert history[0]["date"] == d1


def test_yield_curve_latest_returns_most_recent_non_null_row(store: FlowStore) -> None:
    from datetime import date, timedelta
    today = date.today()
    d_curve = (today - timedelta(days=10)).isoformat()
    d_fx_only = (today - timedelta(days=5)).isoformat()
    store.upsert_macro_snapshots([
        MacroSnapshot(date=d_curve, gsec_1y=6.45, gsec_10y=6.58),
        MacroSnapshot(date=d_fx_only, usd_inr=85.0),  # null curve
    ])
    latest = store.get_yield_curve_latest()
    assert latest is not None
    assert latest["date"] == d_curve
    assert latest["gsec_10y"] == pytest.approx(6.58)


def test_backfill_missing_gsec_curve_patches_nulls(store: FlowStore) -> None:
    """``backfill_missing_gsec_curve`` fills NULL columns on recent rows
    without overwriting existing values."""
    # Two existing rows in the last week, both with NULL curve.
    from datetime import date, timedelta
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    two_days_ago = (today - timedelta(days=2)).isoformat()
    store.upsert_macro_snapshots([
        MacroSnapshot(date=yesterday, usd_inr=85.0),
        MacroSnapshot(date=two_days_ago, usd_inr=84.9, gsec_10y=6.50),  # 10Y already set
    ])
    updated = store.backfill_missing_gsec_curve({"1y": 6.45, "5y": 6.62, "10y": 6.58, "30y": 6.90})
    # 2 rows x 4 tenors = up to 8 updates, but the 10Y on two_days_ago is
    # already populated so 7 column-updates max.
    assert updated >= 6
    # Verify the 10Y that was already set is NOT overwritten.
    row = store._conn.execute(
        "SELECT gsec_10y FROM macro_daily WHERE date = ?", (two_days_ago,),
    ).fetchone()
    assert row["gsec_10y"] == pytest.approx(6.50)
