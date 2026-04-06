"""Tests for get_material_events — classifies corporate filings into material event types."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_filing(
    store: FlowStore,
    symbol: str,
    filing_date: str,
    subcategory: str,
    headline: str,
    news_id: str,
    category: str = "Company Update",
) -> None:
    """Insert a single corporate filing into the store."""
    store._conn.execute(
        "INSERT INTO corporate_filings "
        "(symbol, bse_scrip_code, filing_date, category, subcategory, headline, attachment_name, pdf_flag, news_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (symbol, "999999", filing_date, category, subcategory, headline, "doc.pdf", 0, news_id),
    )
    store._conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api(tmp_db: Path, store: FlowStore, monkeypatch) -> ResearchDataAPI:
    """ResearchDataAPI backed by the temp test database with filings pre-populated."""
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


# ---------------------------------------------------------------------------
# TestMaterialEvents
# ---------------------------------------------------------------------------


class TestMaterialEvents:
    """Tests for ResearchDataAPI.get_material_events classification and filtering."""

    def test_classifies_credit_rating(self, tmp_db, store, monkeypatch):
        _insert_filing(store, "TESTCO", "2026-03-18", "Credit Rating", "Credit rating upgraded to AA+", "cr1")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert len(result["events"]) == 1
        assert result["events"][0]["event_type"] == "credit_rating"

    def test_classifies_order_win(self, tmp_db, store, monkeypatch):
        _insert_filing(
            store, "TESTCO", "2026-03-10",
            "Award of Order / Receipt of Order",
            "Received order worth Rs 500 Cr from Indian Railways",
            "ow1",
        )
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert len(result["events"]) == 1
        assert result["events"][0]["event_type"] == "order_win"

    def test_high_signal_flag(self, tmp_db, store, monkeypatch):
        """Credit rating is high signal, Financial Results is not."""
        _insert_filing(store, "TESTCO", "2026-03-18", "Credit Rating", "Rating upgraded", "hs1")
        _insert_filing(store, "TESTCO", "2026-03-15", "Financial Results", "Q3 results declared", "hs2")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")

        events_by_type = {e["event_type"]: e for e in result["events"]}
        assert events_by_type["credit_rating"]["high_signal"] is True
        assert events_by_type["results"]["high_signal"] is False
        assert result["high_signal_count"] == 1

    def test_filters_by_days(self, tmp_db, store, monkeypatch):
        """Filing older than the requested days window should be excluded."""
        old_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
        recent_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        _insert_filing(store, "TESTCO", old_date, "Credit Rating", "Old rating", "fd1")
        _insert_filing(store, "TESTCO", recent_date, "Credit Rating", "Recent rating", "fd2")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO", days=365)
        assert result["total"] == 1
        assert result["events"][0]["headline"] == "Recent rating"

    def test_ignores_unclassified_filings(self, tmp_db, store, monkeypatch):
        """Filing with subcategory not in the mapping should be excluded."""
        _insert_filing(store, "TESTCO", "2026-03-15", "General", "Some general update", "uc1")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert result["total"] == 0
        assert result["events"] == []
        assert result["summary"] == {}

    def test_summary_counts(self, tmp_db, store, monkeypatch):
        """Verify summary dict counts events by type."""
        _insert_filing(store, "TESTCO", "2026-03-18", "Credit Rating", "Rating 1", "sc1")
        _insert_filing(store, "TESTCO", "2026-03-17", "Credit Rating", "Rating 2", "sc2")
        _insert_filing(store, "TESTCO", "2026-03-16", "Change in Management", "New CEO appointed", "sc3")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert result["summary"]["credit_rating"] == 2
        assert result["summary"]["management_change"] == 1
        assert result["total"] == 3

    def test_sorted_by_date_desc(self, tmp_db, store, monkeypatch):
        """Events should be returned newest first."""
        _insert_filing(store, "TESTCO", "2026-01-10", "Credit Rating", "Oldest", "sd1")
        _insert_filing(store, "TESTCO", "2026-03-18", "Credit Rating", "Newest", "sd2")
        _insert_filing(store, "TESTCO", "2026-02-14", "Credit Rating", "Middle", "sd3")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        dates = [e["date"] for e in result["events"]]
        assert dates == sorted(dates, reverse=True)
        assert result["events"][0]["headline"] == "Newest"
        assert result["events"][-1]["headline"] == "Oldest"

    def test_empty_symbol(self, tmp_db, store, monkeypatch):
        """No filings for a symbol should return empty structure."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("NOSYMBOL")
        assert result["events"] == []
        assert result["summary"] == {}
        assert result["total"] == 0
        assert result["high_signal_count"] == 0

    def test_management_change_variants(self, tmp_db, store, monkeypatch):
        """Multiple subcategory strings should map to management_change."""
        _insert_filing(store, "TESTCO", "2026-03-18", "Change in Directorate", "New director appointed", "mc1")
        _insert_filing(store, "TESTCO", "2026-03-17", "Resignation of Director", "Director resigned", "mc2")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        for event in result["events"]:
            assert event["event_type"] == "management_change", (
                f"Expected management_change for subcategory, got {event['event_type']}"
            )
        assert result["summary"]["management_change"] == 2

    def test_acquisition_classified(self, tmp_db, store, monkeypatch):
        _insert_filing(store, "TESTCO", "2026-03-10", "Acquisition", "Acquired XYZ Corp", "ac1")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert result["events"][0]["event_type"] == "acquisition"
        assert result["events"][0]["high_signal"] is True

    def test_auditor_resignation_classified(self, tmp_db, store, monkeypatch):
        _insert_filing(
            store, "TESTCO", "2026-03-10",
            "Resignation of Statutory Auditors",
            "Auditors resigned due to concerns",
            "ar1",
        )
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert result["events"][0]["event_type"] == "auditor_resignation"
        assert result["events"][0]["high_signal"] is True

    def test_press_release_not_high_signal(self, tmp_db, store, monkeypatch):
        _insert_filing(
            store, "TESTCO", "2026-03-10",
            "Press Release / Media Release",
            "Company announces new product launch",
            "pr1",
        )
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert result["events"][0]["event_type"] == "press_release"
        assert result["events"][0]["high_signal"] is False

    def test_fund_raise_classified(self, tmp_db, store, monkeypatch):
        _insert_filing(store, "TESTCO", "2026-03-10", "Raising of Funds", "QIP of Rs 2000 Cr", "fr1")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert result["events"][0]["event_type"] == "fund_raise"
        assert result["events"][0]["high_signal"] is True

    def test_event_has_expected_keys(self, tmp_db, store, monkeypatch):
        """Each event dict should have all expected keys."""
        _insert_filing(store, "TESTCO", "2026-03-18", "Credit Rating", "Rating upgraded to AA+", "ek1")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        event = result["events"][0]
        assert "date" in event
        assert "event_type" in event
        assert "headline" in event
        assert "subcategory" in event
        assert "high_signal" in event

    def test_result_has_expected_top_level_keys(self, tmp_db, store, monkeypatch):
        """Return dict should have events, summary, total, high_signal_count."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        with ResearchDataAPI() as api:
            result = api.get_material_events("TESTCO")
        assert "events" in result
        assert "summary" in result
        assert "total" in result
        assert "high_signal_count" in result


# ---------------------------------------------------------------------------
# TestEventsActionsRouting
# ---------------------------------------------------------------------------


class TestEventsActionsRouting:
    """Verify _get_events_actions_section routes material_events correctly."""

    def test_material_events_routes(self, tmp_db, store, monkeypatch):
        """Calling get_events_actions with section='material_events' should route to get_material_events."""
        _insert_filing(store, "TESTCO", "2026-03-18", "Credit Rating", "Rating upgraded", "rt1")
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.tools import _get_events_actions_section

        with ResearchDataAPI() as api:
            data = _get_events_actions_section(api, "TESTCO", "material_events", {})

        assert isinstance(data, dict)
        assert "events" in data
        assert data["total"] >= 1

    def test_unknown_section_returns_error(self, tmp_db, store, monkeypatch):
        """Unknown section names should return an error dict."""
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.tools import _get_events_actions_section

        with ResearchDataAPI() as api:
            data = _get_events_actions_section(api, "TESTCO", "nonexistent_section", {})

        assert "error" in data
