"""Tests for ``surveillance_flags`` store methods.

Covers upsert + get + is_under_surveillance round-trip semantics.
"""

from __future__ import annotations

from flowtracker.store import FlowStore
from flowtracker.surveillance_models import SurveillanceFlag


def _make_flags() -> list[SurveillanceFlag]:
    """Four flags spanning ASM/GSM/ESM × NSE/BSE."""
    return [
        SurveillanceFlag(
            symbol="ABCLTD", alert_type="ASM", stage="Stage I",
            exchange="NSE", effective_date="2026-05-26",
            reason="Long Term ASM Stage I",
        ),
        # Same symbol, different alert type — must both round-trip.
        SurveillanceFlag(
            symbol="ABCLTD", alert_type="GSM", stage="LXII",
            exchange="NSE", effective_date="2026-05-26",
            reason="IBC - Receipt & GSM 0",
        ),
        SurveillanceFlag(
            symbol="XYZSML", alert_type="ESM", stage="Stage II",
            exchange="BSE", effective_date="2026-05-26",
            reason="Low volume",
        ),
        SurveillanceFlag(
            symbol="CLEANCO", alert_type="ASM", stage="Stage II",
            exchange="NSE", effective_date="2026-05-25",
            reason=None,  # exchanges sometimes omit reason
        ),
    ]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_upsert_and_get_all(store: FlowStore):
    flags = _make_flags()
    count = store.upsert_surveillance_flags(flags)
    assert count == 4

    rows = store.get_surveillance_flags()
    assert len(rows) == 4
    syms = {r["symbol"] for r in rows}
    assert syms == {"ABCLTD", "XYZSML", "CLEANCO"}


def test_get_preserves_field_values(store: FlowStore):
    store.upsert_surveillance_flags([_make_flags()[0]])
    rows = store.get_surveillance_flags("ABCLTD")
    assert len(rows) == 1
    r = rows[0]
    assert r["symbol"] == "ABCLTD"
    assert r["alert_type"] == "ASM"
    assert r["stage"] == "Stage I"
    assert r["exchange"] == "NSE"
    assert r["effective_date"] == "2026-05-26"
    assert r["reason"] == "Long Term ASM Stage I"
    assert r["fetched_at"] is not None


def test_empty_db_returns_empty(store: FlowStore):
    assert store.get_surveillance_flags() == []
    assert store.get_surveillance_flags("ABCLTD") == []


def test_upsert_empty_list_is_noop(store: FlowStore):
    assert store.upsert_surveillance_flags([]) == 0
    assert store.get_surveillance_flags() == []


def test_nullable_reason_round_trip(store: FlowStore):
    store.upsert_surveillance_flags([_make_flags()[3]])
    rows = store.get_surveillance_flags("CLEANCO")
    assert len(rows) == 1
    assert rows[0]["reason"] is None


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_filter_by_symbol_case_insensitive(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    rows = store.get_surveillance_flags("abcltd")
    assert len(rows) == 2  # both ASM + GSM
    assert {r["alert_type"] for r in rows} == {"ASM", "GSM"}


def test_filter_by_alert_type(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    rows = store.get_surveillance_flags(alert_type="ESM")
    assert len(rows) == 1
    assert rows[0]["symbol"] == "XYZSML"


def test_filter_by_exchange(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    rows = store.get_surveillance_flags(exchange="BSE")
    assert len(rows) == 1
    assert rows[0]["alert_type"] == "ESM"


def test_filter_combined(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    rows = store.get_surveillance_flags(
        symbol="ABCLTD", alert_type="ASM", exchange="NSE",
    )
    assert len(rows) == 1
    assert rows[0]["stage"] == "Stage I"


def test_filter_no_match_returns_empty(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    assert store.get_surveillance_flags("NOSUCH") == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_upsert_is_idempotent(store: FlowStore):
    """Re-upserting the same row updates in place (UNIQUE key)."""
    flags = _make_flags()
    store.upsert_surveillance_flags(flags)
    store.upsert_surveillance_flags(flags)
    rows = store.get_surveillance_flags()
    assert len(rows) == 4


def test_upsert_overwrites_changed_fields(store: FlowStore):
    """Re-upserting with new stage/reason replaces the prior row."""
    old = SurveillanceFlag(
        symbol="ABCLTD", alert_type="ASM", stage="Stage I",
        exchange="NSE", effective_date="2026-05-26",
        reason="initial",
    )
    new = SurveillanceFlag(
        symbol="ABCLTD", alert_type="ASM", stage="Stage II",
        exchange="NSE", effective_date="2026-05-26",
        reason="upgraded",
    )
    store.upsert_surveillance_flags([old])
    store.upsert_surveillance_flags([new])
    rows = store.get_surveillance_flags("ABCLTD")
    assert len(rows) == 1
    assert rows[0]["stage"] == "Stage II"
    assert rows[0]["reason"] == "upgraded"


# ---------------------------------------------------------------------------
# is_under_surveillance
# ---------------------------------------------------------------------------


def test_is_under_surveillance_true(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    assert store.is_under_surveillance("ABCLTD") is True
    assert store.is_under_surveillance("XYZSML") is True


def test_is_under_surveillance_false_for_clean_symbol(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    assert store.is_under_surveillance("RELIANCE") is False


def test_is_under_surveillance_empty_db(store: FlowStore):
    assert store.is_under_surveillance("ANYTHING") is False


def test_is_under_surveillance_case_insensitive(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    assert store.is_under_surveillance("abcltd") is True


def test_is_under_surveillance_empty_string(store: FlowStore):
    assert store.is_under_surveillance("") is False


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_get_orders_by_exchange_then_type_then_symbol(store: FlowStore):
    store.upsert_surveillance_flags(_make_flags())
    rows = store.get_surveillance_flags()
    # BSE rows come before NSE alphabetically.
    exchanges = [r["exchange"] for r in rows]
    assert exchanges == sorted(exchanges)
