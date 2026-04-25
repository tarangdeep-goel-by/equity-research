"""Round-trip tests for data_quality_flags store methods."""
from __future__ import annotations

from flowtracker.data_quality import Flag


def _f(symbol: str, curr_fy: str, line: str, severity: str = "MEDIUM") -> Flag:
    return Flag(
        symbol=symbol, prior_fy="2024-03-31", curr_fy=curr_fy, line=line,
        prior_val=100.0, curr_val=400.0, jump_pct=300.0,
        revenue_change_pct=5.0, flag_type="RECLASS", severity=severity,
    )


def test_upsert_and_get(store):
    n = store.upsert_data_quality_flags([
        _f("HDFCBANK", "2025-03-31", "other_expenses_detail", "MEDIUM"),
        _f("HDFCBANK", "2025-03-31", "borrowings", "HIGH"),
        _f("INFY", "2025-03-31", "other_expenses_detail", "HIGH"),
    ])
    assert n == 3
    rows = store.get_data_quality_flags("HDFCBANK")
    assert len(rows) == 2
    assert {r["line"] for r in rows} == {"other_expenses_detail", "borrowings"}


def test_severity_filter(store):
    store.upsert_data_quality_flags([
        _f("X", "2025-03-31", "a", "LOW"),
        _f("X", "2025-03-31", "b", "MEDIUM"),
        _f("X", "2025-03-31", "c", "HIGH"),
    ])
    assert {r["line"] for r in store.get_data_quality_flags("X")} == {"a", "b", "c"}
    assert {r["line"] for r in store.get_data_quality_flags("X", min_severity="MEDIUM")} == {"b", "c"}
    assert {r["line"] for r in store.get_data_quality_flags("X", min_severity="HIGH")} == {"c"}


def test_idempotent_reupsert_same_key(store):
    """(symbol, curr_fy, line) is the unique key — re-upsert replaces in place."""
    store.upsert_data_quality_flags([_f("X", "2025-03-31", "a", "LOW")])
    rows = store.get_data_quality_flags("X")
    assert len(rows) == 1 and rows[0]["severity"] == "LOW"

    # Same key, new severity — should overwrite, not duplicate
    store.upsert_data_quality_flags([_f("X", "2025-03-31", "a", "HIGH")])
    rows = store.get_data_quality_flags("X")
    assert len(rows) == 1 and rows[0]["severity"] == "HIGH"


def test_clear_scoped_to_symbol(store):
    store.upsert_data_quality_flags([
        _f("X", "2025-03-31", "a"),
        _f("Y", "2025-03-31", "a"),
    ])
    store.clear_data_quality_flags("X")
    assert store.get_data_quality_flags("X") == []
    assert len(store.get_data_quality_flags("Y")) == 1


def test_clear_all(store):
    store.upsert_data_quality_flags([
        _f("X", "2025-03-31", "a"),
        _f("Y", "2025-03-31", "a"),
    ])
    store.clear_data_quality_flags(None)
    assert store.get_data_quality_flags("X") == []
    assert store.get_data_quality_flags("Y") == []


def test_get_returns_empty_for_unknown_symbol(store):
    assert store.get_data_quality_flags("NONEXISTENT") == []


def test_symbol_normalized_to_uppercase(store):
    store.upsert_data_quality_flags([_f("hdfcbank", "2025-03-31", "a")])
    assert len(store.get_data_quality_flags("HDFCBANK")) == 1
    assert len(store.get_data_quality_flags("hdfcbank")) == 1  # get also normalizes
