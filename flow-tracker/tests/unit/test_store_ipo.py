"""Round-trip tests for FlowStore IPO methods.

Covers the three tables added in feat/ipo-pipeline (2026-05-26):
  - ipo_calendar
  - ipo_subscription
  - ipo_listings
"""

from __future__ import annotations

from flowtracker.ipo_models import IPOIssue, IPOListing, IPOSubscription
from flowtracker.store import FlowStore


def _issue(**overrides) -> IPOIssue:
    base = dict(
        issuer_name="Jio Platforms Limited",
        symbol=None,
        segment="MAIN",
        exchange="NSE",
        open_date="2026-06-10",
        close_date="2026-06-12",
        listing_date="2026-06-18",
        price_band_low=950.0,
        price_band_high=1000.0,
        issue_size_cr=55000.0,
        lot_size=15,
    )
    base.update(overrides)
    return IPOIssue(**base)


def _sub(**overrides) -> IPOSubscription:
    base = dict(
        issuer_name="Jio Platforms Limited",
        as_of_date="2026-06-11",
        qib_times=4.5,
        nii_times=12.3,
        retail_times=8.75,
        employee_times=2.1,
        total_times=7.85,
    )
    base.update(overrides)
    return IPOSubscription(**base)


def _listing(**overrides) -> IPOListing:
    base = dict(
        symbol="JIOPLAT",
        issuer_name="Jio Platforms Limited",
        listing_date="2026-06-18",
        listing_price=1000.0,
        listing_day_close=1185.5,
        listing_pop_pct=18.55,
    )
    base.update(overrides)
    return IPOListing(**base)


# ---------------------------------------------------------------------------
# Calendar


class TestIPOCalendar:
    def test_upsert_then_get(self, store: FlowStore):
        n = store.upsert_ipo_calendar([_issue()])
        assert n == 1
        rows = store.get_ipo_upcoming()
        assert len(rows) == 1
        r = rows[0]
        assert r.issuer_name == "Jio Platforms Limited"
        assert r.segment == "MAIN"
        assert r.exchange == "NSE"
        assert r.price_band_high == 1000.0
        assert r.issue_size_cr == 55000.0
        assert r.lot_size == 15

    def test_upsert_empty_returns_zero(self, store: FlowStore):
        assert store.upsert_ipo_calendar([]) == 0
        assert store.get_ipo_upcoming() == []

    def test_upsert_replaces_on_same_issuer_open_date(self, store: FlowStore):
        """UNIQUE(issuer_name, open_date) → second upsert replaces band/size."""
        store.upsert_ipo_calendar([_issue(price_band_high=1000.0)])
        store.upsert_ipo_calendar([_issue(price_band_high=1050.0)])
        rows = store.get_ipo_upcoming()
        assert len(rows) == 1
        assert rows[0].price_band_high == 1050.0

    def test_multiple_distinct_issues(self, store: FlowStore):
        store.upsert_ipo_calendar([
            _issue(issuer_name="A Ltd", open_date="2026-06-10"),
            _issue(issuer_name="B Ltd", open_date="2026-06-15"),
            _issue(issuer_name="C SME Ltd", open_date="2026-06-20", segment="SME"),
        ])
        rows = store.get_ipo_upcoming()
        assert len(rows) == 3
        # Sorted by open_date ascending
        assert [r.issuer_name for r in rows] == ["A Ltd", "B Ltd", "C SME Ltd"]

    def test_past_issues_filtered_out(self, store: FlowStore):
        """Calendar drops issues whose open_date is > 7 days in the past."""
        store.upsert_ipo_calendar([
            _issue(issuer_name="Ancient IPO Ltd", open_date="2020-01-01"),
            _issue(issuer_name="Future IPO Ltd", open_date="2030-12-01"),
        ])
        names = {r.issuer_name for r in store.get_ipo_upcoming()}
        assert "Ancient IPO Ltd" not in names
        assert "Future IPO Ltd" in names

    def test_null_open_date_persists_and_lists_last(self, store: FlowStore):
        store.upsert_ipo_calendar([
            _issue(issuer_name="Future Ltd", open_date="2030-12-01"),
            _issue(issuer_name="No Date Ltd", open_date=None),
        ])
        rows = store.get_ipo_upcoming()
        assert len(rows) == 2
        # Null open_date comes last
        assert rows[-1].issuer_name == "No Date Ltd"


# ---------------------------------------------------------------------------
# Subscription


class TestIPOSubscription:
    def test_upsert_then_get_by_issuer(self, store: FlowStore):
        store.upsert_ipo_subscription([_sub()])
        rows = store.get_ipo_subscription("Jio Platforms Limited")
        assert len(rows) == 1
        assert rows[0].qib_times == 4.5
        assert rows[0].total_times == 7.85

    def test_substring_match(self, store: FlowStore):
        store.upsert_ipo_subscription([_sub()])
        # Partial name → still matches
        rows = store.get_ipo_subscription("jio")
        assert len(rows) == 1

    def test_unknown_issuer_empty(self, store: FlowStore):
        assert store.get_ipo_subscription("nosuchissuer") == []

    def test_upsert_replaces_on_same_issuer_date(self, store: FlowStore):
        store.upsert_ipo_subscription([_sub(total_times=5.0)])
        store.upsert_ipo_subscription([_sub(total_times=12.5)])
        rows = store.get_ipo_subscription("Jio")
        assert len(rows) == 1
        assert rows[0].total_times == 12.5

    def test_multiple_snapshots_sort_ascending(self, store: FlowStore):
        store.upsert_ipo_subscription([
            _sub(as_of_date="2026-06-12", total_times=18.0),
            _sub(as_of_date="2026-06-10", total_times=2.0),
            _sub(as_of_date="2026-06-11", total_times=7.85),
        ])
        rows = store.get_ipo_subscription("Jio")
        assert [r.as_of_date for r in rows] == [
            "2026-06-10", "2026-06-11", "2026-06-12",
        ]
        # Verify the bull-top oversubscription pattern is observable
        assert rows[-1].total_times == 18.0

    def test_empty_upsert_returns_zero(self, store: FlowStore):
        assert store.upsert_ipo_subscription([]) == 0


# ---------------------------------------------------------------------------
# Listings


class TestIPOListings:
    def test_upsert_then_get(self, store: FlowStore):
        store.upsert_ipo_listings([_listing()])
        rows = store.get_ipo_listings(days=30)
        assert len(rows) == 1
        assert rows[0].symbol == "JIOPLAT"
        assert rows[0].listing_pop_pct == 18.55

    def test_symbol_upper_cased(self, store: FlowStore):
        store.upsert_ipo_listings([_listing(symbol="jioplat")])
        rows = store.get_ipo_listings(days=30)
        assert rows[0].symbol == "JIOPLAT"

    def test_days_window_filters_old(self, store: FlowStore):
        """Listings older than `days` window are excluded."""
        store.upsert_ipo_listings([
            _listing(symbol="OLDCO", listing_date="2020-01-01"),
            _listing(symbol="NEWCO", listing_date="9999-12-30"),
        ])
        rows = store.get_ipo_listings(days=30)
        syms = {r.symbol for r in rows}
        assert "OLDCO" not in syms
        assert "NEWCO" in syms

    def test_upsert_replaces_on_same_symbol_date(self, store: FlowStore):
        store.upsert_ipo_listings([_listing(listing_day_close=1200.0)])
        store.upsert_ipo_listings([_listing(listing_day_close=1500.0)])
        rows = store.get_ipo_listings(days=365 * 10)
        assert len(rows) == 1
        assert rows[0].listing_day_close == 1500.0

    def test_listings_sort_desc(self, store: FlowStore):
        store.upsert_ipo_listings([
            _listing(symbol="A", listing_date="9999-06-15"),
            _listing(symbol="B", listing_date="9999-06-18"),
            _listing(symbol="C", listing_date="9999-06-10"),
        ])
        rows = store.get_ipo_listings(days=365 * 1000)
        assert [r.symbol for r in rows] == ["B", "A", "C"]

    def test_empty_upsert_returns_zero(self, store: FlowStore):
        assert store.upsert_ipo_listings([]) == 0
