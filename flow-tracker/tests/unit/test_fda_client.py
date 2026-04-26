"""Tests for fda_client + fda_models — Wave 4-5 P2 (2026-04-25).

Covers:
- CSV manual-seed loader (`load_inspections_from_csv`)
- Summary aggregation (`aggregate_fda_summary`) — TTM windowing, active WL set,
  most-recent inspection selection
- Outcome normalization (`normalize_outcome`) — handles FDA terminology variants
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

import pytest

from flowtracker.fda_client import (
    aggregate_fda_summary,
    load_inspections_from_csv,
)
from flowtracker.fda_models import (
    INSPECTION_OUTCOMES,
    FDAInspection,
    normalize_outcome,
)


# ---------------------------------------------------------------------------
# Outcome normalization
# ---------------------------------------------------------------------------

class TestNormalizeOutcome:
    @pytest.mark.parametrize("raw,expected", [
        ("NAI", "NAI"),
        ("VAI", "VAI"),
        ("OAI", "OAI"),
        ("warning_letter", "warning_letter"),
        ("Warning Letter", "warning_letter"),
        ("WARNING LETTER ISSUED", "warning_letter"),
        ("import alert", "import_alert"),
        ("Import Alert 66-40", "import_alert"),
        ("consent decree", "consent_decree"),
        ("no action indicated", "NAI"),
        ("No Observations", "NAI"),
    ])
    def test_known_outcomes(self, raw, expected):
        assert normalize_outcome(raw) == expected

    def test_unknown_echoed_lowercase(self):
        # Unknown tokens are echoed back as-is (lowercased) — caller filters.
        assert normalize_outcome("XYZ") == "xyz"

    def test_empty_returns_unknown(self):
        assert normalize_outcome("") == "unknown"


# ---------------------------------------------------------------------------
# CSV loader
# ---------------------------------------------------------------------------

class TestLoadCSV:
    def _write_csv(self, tmp_path: Path, body: str) -> Path:
        csv_path = tmp_path / "fda.csv"
        csv_path.write_text(body, encoding="utf-8")
        return csv_path

    def test_round_trip_basic(self, tmp_path):
        body = dedent("""\
            symbol,plant_location,audit_date,outcome,form_483_observation_count,warning_letter_active
            SUNPHARMA,"Halol, Gujarat, India",2026-02-10,483_issued,9,false
            SUNPHARMA,"Mohali, India",2026-01-05,NAI,0,false
            DRREDDY,"Bachupally, India",2026-03-12,warning_letter,12,true
        """)
        csv_path = self._write_csv(tmp_path, body)
        rows = load_inspections_from_csv(csv_path)
        assert len(rows) == 3

        sun_halol = next(r for r in rows if r.plant_location.startswith("Halol"))
        assert sun_halol.symbol == "SUNPHARMA"
        assert sun_halol.form_483_observation_count == 9
        assert sun_halol.warning_letter_active is False

        drr = next(r for r in rows if r.symbol == "DRREDDY")
        assert drr.warning_letter_active is True
        assert drr.outcome == "warning_letter"

    def test_skips_rows_missing_required_fields(self, tmp_path):
        body = dedent("""\
            symbol,plant_location,audit_date,outcome
            SUNPHARMA,"Halol, India",2026-02-10,483_issued
            ,"Mohali, India",2026-01-05,NAI
            SUNPHARMA,,2026-03-01,NAI
            SUNPHARMA,"Sikkim, India",,NAI
        """)
        csv_path = self._write_csv(tmp_path, body)
        rows = load_inspections_from_csv(csv_path)
        assert len(rows) == 1
        assert rows[0].plant_location.startswith("Halol")

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_inspections_from_csv(tmp_path / "nonexistent.csv")


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

class TestAggregateSummary:
    def _rec(self, **kwargs) -> FDAInspection:
        defaults = {
            "symbol": "SUNPHARMA",
            "plant_location": "Halol, India",
            "audit_date": "2026-02-10",
            "outcome": "VAI",
            "form_483_observation_count": 5,
            "warning_letter_active": False,
        }
        defaults.update(kwargs)
        return FDAInspection(**defaults)

    def test_empty_inspections_returns_zero_summary(self):
        s = aggregate_fda_summary([], "SUNPHARMA", as_of=date(2026, 4, 25))
        assert s.symbol == "SUNPHARMA"
        assert s.plants_audited_ttm == 0
        assert s.most_recent_inspection is None

    def test_ttm_window_filters_old_inspections(self):
        recs = [
            self._rec(audit_date="2026-02-10", form_483_observation_count=3),
            self._rec(audit_date="2024-02-10", form_483_observation_count=99,
                      plant_location="Sikkim, India"),
        ]
        # TTM cut at 2026-04-25 - 365d = 2025-04-25, so 2024-02-10 is excluded.
        s = aggregate_fda_summary(recs, "SUNPHARMA", as_of=date(2026, 4, 25))
        assert s.plants_audited_ttm == 1
        assert s.total_form_483_observations_ttm == 3

    def test_active_warning_letter_count(self):
        recs = [
            self._rec(plant_location="Halol, India", warning_letter_active=True),
            self._rec(plant_location="Mohali, India", warning_letter_active=True),
            self._rec(plant_location="Sikkim, India", warning_letter_active=False),
        ]
        s = aggregate_fda_summary(recs, "SUNPHARMA", as_of=date(2026, 4, 25))
        assert s.active_warning_letters == 2
        assert sorted(s.active_warning_letter_plants) == ["Halol, India", "Mohali, India"]

    def test_most_recent_inspection_wins(self):
        recs = [
            self._rec(audit_date="2025-06-10", form_483_observation_count=2),
            self._rec(audit_date="2026-02-10", form_483_observation_count=8),
            self._rec(audit_date="2025-12-10", form_483_observation_count=4),
        ]
        s = aggregate_fda_summary(recs, "SUNPHARMA", as_of=date(2026, 4, 25))
        assert s.most_recent_inspection is not None
        assert s.most_recent_inspection.audit_date == "2026-02-10"
        assert s.most_recent_inspection.form_483_observation_count == 8

    def test_only_returns_rows_for_target_symbol(self):
        recs = [
            self._rec(symbol="SUNPHARMA"),
            self._rec(symbol="DRREDDY", form_483_observation_count=99),
        ]
        s = aggregate_fda_summary(recs, "SUNPHARMA", as_of=date(2026, 4, 25))
        assert s.plants_audited_ttm == 1
        assert s.total_form_483_observations_ttm == 5  # only SUNPHARMA's 5


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------

class TestModelShape:
    def test_inspection_outcomes_taxonomy_complete(self):
        # Wave 4-5 plan called for: warning letters, Form 483, OAI, ANDA pipeline.
        # We don't enforce ANDA here (it's an event, not an inspection outcome),
        # but the inspection outcome taxonomy must include the four pillar
        # tokens: NAI / VAI / OAI / warning_letter.
        assert "NAI" in INSPECTION_OUTCOMES
        assert "VAI" in INSPECTION_OUTCOMES
        assert "OAI" in INSPECTION_OUTCOMES
        assert "warning_letter" in INSPECTION_OUTCOMES
