"""Round-trip tests for FlowStore FDA inspection methods.

Covers `upsert_fda_inspections` + `get_fda_inspections` against the
`fda_inspections` table added in feat/strategy2-ops (2026-04-29).
"""

from __future__ import annotations

from datetime import date

from flowtracker.fda_models import FdaInspection
from flowtracker.store import FlowStore


def _rec(**overrides) -> FdaInspection:
    base = {
        "firm_name": "Sun Pharmaceutical Industries Ltd",
        "fei_number": "D-0700-2017",
        "inspection_date": date(2017, 3, 22),
        "classification": "Class III",
        "product_area": "Olanzapine Tablets, 7.5 mg",
        "country": "India",
        "posted_date": date(2017, 5, 17),
    }
    base.update(overrides)
    return FdaInspection(**base)


def test_upsert_then_get_round_trip(store: FlowStore):
    rows = [_rec()]
    n = store.upsert_fda_inspections("SUNPHARMA", rows)
    assert n == 1

    fetched = store.get_fda_inspections("SUNPHARMA")
    assert len(fetched) == 1
    r = fetched[0]
    assert r["symbol"] == "SUNPHARMA"
    assert r["firm_name"] == "Sun Pharmaceutical Industries Ltd"
    assert r["fei_number"] == "D-0700-2017"
    assert r["inspection_date"] == "2017-03-22"
    assert r["classification"] == "Class III"
    assert r["country"] == "India"
    assert r["posted_date"] == "2017-05-17"


def test_upsert_empty_list_returns_zero(store: FlowStore):
    assert store.upsert_fda_inspections("SUNPHARMA", []) == 0
    assert store.get_fda_inspections("SUNPHARMA") == []


def test_get_unknown_symbol_returns_empty(store: FlowStore):
    assert store.get_fda_inspections("NOSUCHSYM") == []


def test_upsert_idempotent_on_same_pk(store: FlowStore):
    """Same (symbol, fei_number, inspection_date) re-upserts as REPLACE, not duplicate."""
    rec = _rec(classification="Class III")
    store.upsert_fda_inspections("SUNPHARMA", [rec])
    rec2 = _rec(classification="Class II")  # severity downgraded after re-grade
    store.upsert_fda_inspections("SUNPHARMA", [rec2])

    rows = store.get_fda_inspections("SUNPHARMA")
    assert len(rows) == 1
    assert rows[0]["classification"] == "Class II"


def test_multiple_distinct_records_persist(store: FlowStore):
    recs = [
        _rec(fei_number="D-0001-2024", inspection_date=date(2024, 1, 1)),
        _rec(fei_number="D-0002-2024", inspection_date=date(2024, 6, 1)),
        _rec(fei_number="D-0003-2025", inspection_date=date(2025, 3, 1)),
    ]
    n = store.upsert_fda_inspections("SUNPHARMA", recs)
    assert n == 3
    rows = store.get_fda_inspections("SUNPHARMA")
    assert len(rows) == 3
    # newest inspection_date first
    assert rows[0]["inspection_date"] == "2025-03-01"
    assert rows[-1]["inspection_date"] == "2024-01-01"


def test_handles_none_dates_via_sentinel(store: FlowStore):
    """Records with no inspection_date / fei_number persist via empty-string PK sentinel."""
    rec = _rec(fei_number=None, inspection_date=None, posted_date=None)
    n = store.upsert_fda_inspections("SUNPHARMA", [rec])
    assert n == 1
    rows = store.get_fda_inspections("SUNPHARMA")
    assert len(rows) == 1
    assert rows[0]["fei_number"] == ""
    assert rows[0]["inspection_date"] == ""
    assert rows[0]["posted_date"] is None  # posted_date is non-PK, persists as NULL


def test_symbol_case_insensitive(store: FlowStore):
    """Lookup uses uppercased symbol regardless of input casing."""
    store.upsert_fda_inspections("sunpharma", [_rec()])
    assert len(store.get_fda_inspections("SunPharma")) == 1
    assert len(store.get_fda_inspections("SUNPHARMA")) == 1


def test_limit_respected(store: FlowStore):
    recs = [
        _rec(fei_number=f"D-{i:04d}-2024", inspection_date=date(2024, 1, 1 + i))
        for i in range(5)
    ]
    store.upsert_fda_inspections("SUNPHARMA", recs)
    rows = store.get_fda_inspections("SUNPHARMA", limit=2)
    assert len(rows) == 2
