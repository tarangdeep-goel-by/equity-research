"""Tests for fda_client + fda_models — Wave 4-5 P2 (2026-04-25).

Covers:
- CSV manual-seed loader (`load_inspections_from_csv`)
- Summary aggregation (`aggregate_fda_summary`) — TTM windowing, active WL set,
  most-recent inspection selection
- Outcome normalization (`normalize_outcome`) — handles FDA terminology variants
- Live-fetch openFDA (`fetch_inspections`) — strategy2-ops follow-on (2026-04-29)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from textwrap import dedent

import httpx
import pytest
import respx

from flowtracker.fda_client import (
    OPENFDA_DRUG_ENFORCEMENT_URL,
    _parse_openfda_date,
    aggregate_fda_summary,
    fetch_inspections,
    load_inspections_from_csv,
)
from flowtracker.fda_models import (
    INSPECTION_OUTCOMES,
    FDAInspection,
    FdaInspection,
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


# ---------------------------------------------------------------------------
# Live-fetch (openFDA) — strategy2-ops 2026-04-29
# ---------------------------------------------------------------------------


def _fda_payload(records: list[dict]) -> dict:
    return {
        "meta": {
            "disclaimer": "test",
            "results": {"skip": 0, "limit": len(records), "total": len(records)},
        },
        "results": records,
    }


def _sample_record(**overrides) -> dict:
    base = {
        "status": "Terminated",
        "city": "Halol",
        "state": "Gujarat",
        "country": "India",
        "classification": "Class III",
        "product_type": "Drugs",
        "event_id": "76819",
        "recalling_firm": "Sun Pharmaceutical Industries Ltd",
        "recall_number": "D-0700-2017",
        "product_description": "Olanzapine Tablets, 7.5 mg",
        "recall_initiation_date": "20170322",
        "report_date": "20170517",
        "termination_date": "20180711",
    }
    base.update(overrides)
    return base


class TestParseOpenFDADate:
    def test_compact_yyyymmdd(self):
        assert _parse_openfda_date("20170322") == date(2017, 3, 22)

    def test_iso_format(self):
        assert _parse_openfda_date("2017-03-22") == date(2017, 3, 22)

    def test_none_returns_none(self):
        assert _parse_openfda_date(None) is None

    def test_empty_returns_none(self):
        assert _parse_openfda_date("") is None

    def test_malformed_returns_none(self):
        assert _parse_openfda_date("not-a-date") is None
        assert _parse_openfda_date("99999999") is None  # bogus YYYYMMDD


class TestFetchInspections:
    @pytest.mark.asyncio
    async def test_parses_basic_response(self):
        payload = _fda_payload([_sample_record()])
        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                return_value=httpx.Response(200, json=payload)
            )
            results = await fetch_inspections("Sun Pharmaceutical")

        assert len(results) == 1
        r = results[0]
        assert isinstance(r, FdaInspection)
        assert r.firm_name == "Sun Pharmaceutical Industries Ltd"
        assert r.fei_number == "D-0700-2017"
        assert r.inspection_date == date(2017, 3, 22)
        assert r.classification == "Class III"
        assert r.country == "India"
        assert r.posted_date == date(2017, 5, 17)
        assert "Olanzapine" in r.product_area

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        # Defensive — caller passing "" must not hit the network.
        results = await fetch_inspections("")
        assert results == []
        results = await fetch_inspections("   ")
        assert results == []

    @pytest.mark.asyncio
    async def test_404_treated_as_empty(self):
        """openFDA returns 404 with NOT_FOUND error on zero matches."""
        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                return_value=httpx.Response(
                    404, json={"error": {"code": "NOT_FOUND", "message": "No matches"}}
                )
            )
            results = await fetch_inspections("UnknownPharma XYZ")
        assert results == []

    @pytest.mark.asyncio
    async def test_5xx_retries_once_then_succeeds(self):
        """5xx triggers exactly one retry; second response is honored."""
        payload = _fda_payload([_sample_record()])
        with respx.mock:
            route = respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                side_effect=[
                    httpx.Response(503, text="upstream down"),
                    httpx.Response(200, json=payload),
                ]
            )
            results = await fetch_inspections("Sun Pharmaceutical")
        assert route.call_count == 2
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_5xx_after_retry_returns_empty(self):
        """Two 5xx in a row → empty list, no exception."""
        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                return_value=httpx.Response(500, text="boom")
            )
            results = await fetch_inspections("Sun Pharmaceutical")
        assert results == []

    @pytest.mark.asyncio
    async def test_handles_malformed_dates(self):
        """Bad date strings → field=None, row still kept."""
        rec = _sample_record(
            recall_initiation_date="not-a-date",
            report_date="",
        )
        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                return_value=httpx.Response(200, json=_fda_payload([rec]))
            )
            results = await fetch_inspections("Sun Pharmaceutical")
        assert len(results) == 1
        assert results[0].inspection_date is None
        assert results[0].posted_date is None

    @pytest.mark.asyncio
    async def test_empty_results_array(self):
        """200 with results=[] → empty list."""
        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                return_value=httpx.Response(200, json=_fda_payload([]))
            )
            results = await fetch_inspections("Sun Pharmaceutical")
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_records_parsed(self):
        recs = [
            _sample_record(recall_number="D-0001-2023", recall_initiation_date="20230101"),
            _sample_record(recall_number="D-0002-2023", recall_initiation_date="20230615"),
            _sample_record(recall_number="D-0003-2024", recall_initiation_date="20240220"),
        ]
        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(
                return_value=httpx.Response(200, json=_fda_payload(recs))
            )
            results = await fetch_inspections("Sun Pharmaceutical")
        assert len(results) == 3
        assert {r.fei_number for r in results} == {"D-0001-2023", "D-0002-2023", "D-0003-2024"}

    @pytest.mark.asyncio
    async def test_search_param_quotes_firm_name(self):
        """Verify the firm name is quoted into a phrase search param."""
        captured = {}
        def _capture(request):
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_fda_payload([]))

        with respx.mock:
            respx.get(url__startswith=OPENFDA_DRUG_ENFORCEMENT_URL).mock(side_effect=_capture)
            await fetch_inspections("Sun Pharmaceutical", limit=25)
        assert "recalling_firm" in captured["url"]
        assert "Sun" in captured["url"] and "Pharmaceutical" in captured["url"]
        assert "limit=25" in captured["url"]
