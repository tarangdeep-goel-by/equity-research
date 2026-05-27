"""Tests for FlowStore MF-NAV methods (upsert + getters)."""

from __future__ import annotations

from flowtracker.mf_nav_models import MFSchemeNav


def _make(code: int, date: str, nav: float, name: str = "HDFC Flexi Cap Fund") -> MFSchemeNav:
    return MFSchemeNav(scheme_code=code, date=date, scheme_name=name, nav=nav)


class TestUpsertSchemeNavs:
    def test_inserts_new_rows(self, store):
        rows = [
            _make(118955, "2026-05-26", 100.0),
            _make(118955, "2026-05-25", 99.5),
        ]
        n = store.upsert_mf_scheme_navs(rows)
        assert n == 2

    def test_upsert_is_idempotent_on_pk(self, store):
        rows = [_make(118955, "2026-05-26", 100.0)]
        store.upsert_mf_scheme_navs(rows)
        # Re-upsert with new NAV — must overwrite, not duplicate
        store.upsert_mf_scheme_navs([_make(118955, "2026-05-26", 101.0)])
        latest = store.get_mf_scheme_nav_latest(118955)
        assert latest is not None
        assert latest.nav == 101.0

    def test_empty_list_returns_zero(self, store):
        assert store.upsert_mf_scheme_navs([]) == 0

    def test_supports_multiple_schemes_in_one_call(self, store):
        rows = [
            _make(118955, "2026-05-26", 100.0, "HDFC Flexi Cap Fund"),
            _make(122639, "2026-05-26", 200.0, "Parag Parikh Flexi Cap Fund"),
        ]
        store.upsert_mf_scheme_navs(rows)
        l1 = store.get_mf_scheme_nav_latest(118955)
        l2 = store.get_mf_scheme_nav_latest(122639)
        assert l1 and l1.scheme_name == "HDFC Flexi Cap Fund"
        assert l2 and l2.scheme_name == "Parag Parikh Flexi Cap Fund"


class TestQueryHelpers:
    def test_latest_returns_most_recent_date(self, store):
        store.upsert_mf_scheme_navs([
            _make(118955, "2026-05-26", 100.0),
            _make(118955, "2026-05-25", 99.5),
            _make(118955, "2026-05-24", 99.0),
        ])
        latest = store.get_mf_scheme_nav_latest(118955)
        assert latest is not None
        assert latest.date == "2026-05-26"
        assert latest.nav == 100.0

    def test_latest_returns_none_when_no_rows(self, store):
        assert store.get_mf_scheme_nav_latest(999999) is None

    def test_history_returns_oldest_first(self, store):
        store.upsert_mf_scheme_navs([
            _make(118955, "2026-05-26", 100.0),
            _make(118955, "2026-05-25", 99.5),
            _make(118955, "2026-05-24", 99.0),
        ])
        rows = store.get_mf_scheme_nav_history(118955)
        assert [r.date for r in rows] == ["2026-05-24", "2026-05-25", "2026-05-26"]

    def test_universe_summary(self, store):
        store.upsert_mf_scheme_navs([
            _make(118955, "2026-05-25", 99.5, "HDFC Flexi Cap Fund"),
            _make(118955, "2026-05-26", 100.0, "HDFC Flexi Cap Fund"),
            _make(122639, "2026-05-26", 200.0, "Parag Parikh Flexi Cap Fund"),
        ])
        universe = store.get_mf_scheme_nav_universe()
        # Sorted by scheme_code asc
        assert [r[0] for r in universe] == [118955, 122639]
        # HDFC: 2 rows, first 25th, last 26th
        hdfc = universe[0]
        assert hdfc[1] == "HDFC Flexi Cap Fund"
        assert hdfc[2] == "2026-05-25"
        assert hdfc[3] == "2026-05-26"
        assert hdfc[4] == 2
        # Parag Parikh: 1 row
        pp = universe[1]
        assert pp[4] == 1
