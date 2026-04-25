"""Wave 5 P2 -- granular shareholding breakdown tests.

Covers:
  - XBRL parser captures sub-categories (Retail/HNI/Bodies Corporate/NRI/FPI Cat-I/II)
    and ADR/GDR underlying-share counts.
  - Store round-trip of `shareholding_breakdown` rows.
  - data_api.get_public_breakdown surfaces the data.
  - data_api.get_adr_gdr prefers XBRL CustodianOrDRHolder over stub.
  - Manual seed table `adr_gdr_outstanding` overrides everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flowtracker.holding_client import NSEHoldingClient
from flowtracker.holding_models import ShareholdingBreakdown
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore


# Realistic XBRL fixture in decimal format with sub-category contexts the
# Wave 5 P2 parser cares about. Mirrors the real shape NSEArchives serves
# for newer filings (post-2019 SEBI v2 schema).
_XBRL_BREAKDOWN = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:in-shp="http://www.example.com/shareholding">
  <xbrli:context id="ShareholdingPattern_ContextI">
    <xbrli:entity><xbrli:identifier scheme="x">A</xbrli:identifier></xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="ShareholdingOfPromoterAndPromoterGroup_ContextI"/>
  <xbrli:context id="InstitutionsForeign_ContextI"/>
  <xbrli:context id="ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh_ContextI"/>
  <xbrli:context id="ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_ContextI"/>
  <xbrli:context id="BodiesCorporate_ContextI"/>
  <xbrli:context id="NonResidentIndians_ContextI"/>
  <xbrli:context id="InstitutionsForeignPortfolioInvestorCategoryOne_ContextI"/>
  <xbrli:context id="InstitutionsForeignPortfolioInvestorCategoryTwo_ContextI"/>
  <xbrli:context id="EmployeeBenefitsTrusts_ContextI"/>
  <xbrli:context id="CustodianOrDRHolder_ContextI"/>
  <xbrli:context id="Banks_ContextI"/>
  <xbrli:context id="MutualFundsOrUTI_ContextI"/>
  <xbrli:context id="NonInstitutions_ContextI"/>

  <!-- Decimal format total: sentinel value 1.0 -->
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingPattern_ContextI">1.0000</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <!-- Canonical 7-bucket mapping -->
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">0.5638</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsForeign_ContextI">0.1393</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_ContextI">0.0690</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="NonInstitutions_ContextI">0.1605</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <!-- Sub-category breakdown (Wave 5 P2) -->
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ResidentIndividualShareholdersHoldingNominalShareCapitalUpToRsTwoLakh_ContextI">0.1116</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_ContextI">0.0046</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="BodiesCorporate_ContextI">0.0321</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="NonResidentIndians_ContextI">0.0047</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsForeignPortfolioInvestorCategoryOne_ContextI">0.1336</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InstitutionsForeignPortfolioInvestorCategoryTwo_ContextI">0.0057</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="EmployeeBenefitsTrusts_ContextI">0.0014</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="CustodianOrDRHolder_ContextI">0.1530</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="Banks_ContextI">0.0004</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>

  <!-- ADR/GDR underlying-share count (the definitive Wave 5 P2 win) -->
  <in-shp:NumberOfSharesUnderlyingOutstandingDepositoryReceipts contextRef="CustodianOrDRHolder_ContextI">2056205886</in-shp:NumberOfSharesUnderlyingOutstandingDepositoryReceipts>
  <in-shp:NumberOfShares contextRef="CustodianOrDRHolder_ContextI">2056587444</in-shp:NumberOfShares>
</xbrli:xbrl>
"""


class TestParseXbrlBreakdown:
    """`_parse_xbrl_full` extracts the granular sub-category breakdown."""

    def test_decimal_format_sub_categories(self):
        client = NSEHoldingClient()
        records, pledge, breakdown = client._parse_xbrl_full(_XBRL_BREAKDOWN, "HDFCBANK")
        client.close()

        # Canonical bucket parsing still works
        cats = {r.category for r in records}
        assert "Promoter" in cats
        assert "FII" in cats
        assert "Public" in cats

        # Sub-category breakdown (decimal x 100)
        assert breakdown is not None
        assert breakdown.symbol == "HDFCBANK"
        assert breakdown.quarter_end == "2025-12-31"
        assert breakdown.retail_pct == 11.16
        assert breakdown.hni_pct == 0.46
        assert breakdown.bodies_corporate_pct == 3.21
        assert breakdown.nri_pct == 0.47
        assert breakdown.fpi_cat1_pct == 13.36
        assert breakdown.fpi_cat2_pct == 0.57
        assert breakdown.employee_benefit_trust_pct == 0.14
        assert breakdown.foreign_dr_holder_pct == 15.30
        assert breakdown.banks_pct == 0.04

        # ADR/GDR underlying share count -- the definitive number
        assert breakdown.dr_underlying_shares == 2_056_205_886
        assert breakdown.custodian_total_shares == 2_056_587_444

    def test_legacy_2tuple_unchanged(self):
        """`_parse_xbrl` legacy 2-tuple wrapper still returns (records, pledge)."""
        client = NSEHoldingClient()
        result = client._parse_xbrl(_XBRL_BREAKDOWN, "HDFCBANK")
        client.close()
        # Must remain a 2-tuple for backward-compat
        assert len(result) == 2
        records, pledge = result
        assert records  # non-empty
        # Pledge is None in this fixture (no pledge tags)
        assert pledge is None

    def test_no_breakdown_when_xbrl_lacks_sub_contexts(self):
        """An older-format XBRL with only top-level contexts → breakdown is None."""
        old_xbrl = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:in-shp="http://www.example.com/shareholding">
  <xbrli:context id="ShareholdingPattern_ContextI">
    <xbrli:period><xbrli:instant>2020-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="ShareholdingOfPromoterAndPromoterGroup_ContextI"/>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingPattern_ContextI">100.00</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
  <in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">50.00</in-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
"""
        client = NSEHoldingClient()
        records, pledge, breakdown = client._parse_xbrl_full(old_xbrl, "OLDCO")
        client.close()
        assert records  # canonical still parses
        # No sub-contexts, no DR shares → breakdown is None (treated as no-op)
        assert breakdown is None


class TestStoreBreakdownRoundTrip:
    """Round-trip `shareholding_breakdown` rows through the store."""

    def test_upsert_and_get_latest(self, tmp_path: Path):
        db = tmp_path / "test.db"
        s = FlowStore(db)
        b = ShareholdingBreakdown(
            symbol="HDFCBANK",
            quarter_end="2025-12-31",
            retail_pct=11.16,
            hni_pct=0.46,
            bodies_corporate_pct=3.21,
            nri_pct=0.47,
            fpi_cat1_pct=13.36,
            fpi_cat2_pct=0.57,
            foreign_dr_holder_pct=15.30,
            employee_benefit_trust_pct=0.14,
            dr_underlying_shares=2_056_205_886,
            custodian_total_shares=2_056_587_444,
        )
        n = s.upsert_shareholding_breakdown([b])
        assert n == 1

        out = s.get_latest_shareholding_breakdown("HDFCBANK")
        assert out is not None
        assert out.retail_pct == 11.16
        assert out.foreign_dr_holder_pct == 15.30
        assert out.dr_underlying_shares == 2_056_205_886

    def test_upsert_replaces_on_duplicate_quarter(self, tmp_path: Path):
        """Re-upserting the same (symbol, quarter_end) overwrites prior values."""
        db = tmp_path / "test.db"
        s = FlowStore(db)
        b1 = ShareholdingBreakdown(
            symbol="X", quarter_end="2025-12-31", retail_pct=10.0,
        )
        b2 = ShareholdingBreakdown(
            symbol="X", quarter_end="2025-12-31", retail_pct=11.5,
        )
        s.upsert_shareholding_breakdown([b1])
        s.upsert_shareholding_breakdown([b2])
        rows = s.get_shareholding_breakdown("X")
        assert len(rows) == 1
        assert rows[0].retail_pct == 11.5

    def test_get_breakdown_history_ordered_desc(self, tmp_path: Path):
        db = tmp_path / "test.db"
        s = FlowStore(db)
        rows = [
            ShareholdingBreakdown(symbol="X", quarter_end="2025-03-31", retail_pct=8.0),
            ShareholdingBreakdown(symbol="X", quarter_end="2025-12-31", retail_pct=10.0),
            ShareholdingBreakdown(symbol="X", quarter_end="2025-09-30", retail_pct=9.0),
        ]
        s.upsert_shareholding_breakdown(rows)
        out = s.get_shareholding_breakdown("X", limit=4)
        assert [r.quarter_end for r in out] == ["2025-12-31", "2025-09-30", "2025-03-31"]


class TestPublicBreakdownDataApi:
    """`data_api.get_public_breakdown` surfaces the granular fields."""

    def test_returns_unavailable_when_no_data(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        api = ResearchDataAPI()
        out = api.get_public_breakdown("UNKNOWN")
        assert out["available"] is False
        assert "reason" in out

    def test_surfaces_latest_breakdown(self, tmp_path: Path, monkeypatch):
        db = tmp_path / "test.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(db))

        with FlowStore() as s:
            s.upsert_shareholding_breakdown([
                ShareholdingBreakdown(
                    symbol="HDFCBANK", quarter_end="2025-12-31",
                    retail_pct=11.0, hni_pct=0.5, bodies_corporate_pct=3.2,
                    nri_pct=0.5, foreign_dr_holder_pct=15.3,
                    fpi_cat1_pct=13.0, fpi_cat2_pct=0.6,
                    dr_underlying_shares=2_056_205_886,
                ),
                ShareholdingBreakdown(
                    symbol="HDFCBANK", quarter_end="2025-09-30",
                    retail_pct=10.5, hni_pct=0.4, foreign_dr_holder_pct=15.0,
                ),
            ])

        api = ResearchDataAPI()
        out = api.get_public_breakdown("HDFCBANK")
        assert out["available"] is True
        assert out["as_of_quarter"] == "2025-12-31"
        assert out["public_breakdown"]["retail_pct"] == 11.0
        assert out["fpi_breakdown"]["fpi_cat1_pct"] == 13.0
        assert out["fpi_breakdown"]["foreign_dr_holder_pct"] == 15.3
        assert out["adr_gdr_underlying"]["underlying_shares_outstanding"] == 2_056_205_886
        # QoQ change present
        assert out["qoq_changes"]["retail_pct"] == round(11.0 - 10.5, 2)


class TestAdrGdrXbrlPreferred:
    """`get_adr_gdr` prefers XBRL CustodianOrDRHolder over stub."""

    def test_xbrl_data_returned_when_available(self, tmp_path: Path, monkeypatch):
        db = tmp_path / "test.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(db))

        with FlowStore() as s:
            s.upsert_shareholding_breakdown([
                ShareholdingBreakdown(
                    symbol="HDFCBANK", quarter_end="2025-12-31",
                    foreign_dr_holder_pct=15.30,
                    dr_underlying_shares=2_056_205_886,
                ),
            ])

        api = ResearchDataAPI()
        out = api.get_adr_gdr("HDFCBANK")
        assert out["source"] == "XBRL_CustodianOrDRHolder"
        assert out["pct_of_total_equity"] == 15.30
        assert out["underlying_shares_outstanding"] == 2_056_205_886
        assert out["as_of_date"] == "2025-12-31"
        assert out["data_quality_note"]
        assert out["_meta"]["stub"] is False

    def test_manual_seed_overrides_xbrl(self, tmp_path: Path, monkeypatch):
        """Manual `adr_gdr_outstanding` row takes precedence over XBRL."""
        db = tmp_path / "test.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(db))

        with FlowStore() as s:
            # Both XBRL and manual seed populated
            s.upsert_shareholding_breakdown([
                ShareholdingBreakdown(
                    symbol="HDFCBANK", quarter_end="2025-12-31",
                    foreign_dr_holder_pct=15.30,
                    dr_underlying_shares=2_056_205_886,
                ),
            ])
            s.upsert_adr_gdr_outstanding(
                "HDFCBANK", "2026-03-31",
                listed_on="NYSE",
                sponsor_bank="BNY Mellon",
                adr_ratio="1 ADR = 3 shares",
                underlying_shares_outstanding=2_100_000_000,
                pct_of_total_equity=15.5,
                source="BNY_Mellon_position_report",
                notes="March 2026 sponsor-bank position report",
            )

        api = ResearchDataAPI()
        out = api.get_adr_gdr("HDFCBANK")
        # Seed wins
        assert out["source"] == "BNY_Mellon_position_report"
        assert out["pct_of_total_equity"] == 15.5
        assert out["sponsor_bank"] == "BNY Mellon"
        assert out["adr_ratio"] == "1 ADR = 3 shares"
        assert out["as_of_date"] == "2026-03-31"

    def test_falls_back_to_stub_when_no_data(self, tmp_path: Path, monkeypatch):
        """Symbol with no XBRL DR data and no seed → stub payload."""
        db = tmp_path / "test.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(db))

        api = ResearchDataAPI()
        out = api.get_adr_gdr("HDFCBANK")
        # No data at all → still in known-issuer list, returns stub with note
        assert out["listed_on"] == ["NYSE"]
        assert out["source"] in ("stub",)
        assert out["pct_of_total_equity"] is None


class TestEsopSummaryDataApi:
    """`data_api.get_esop_summary` reads ar_esop_summary rows."""

    def test_returns_unavailable_when_empty(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        api = ResearchDataAPI()
        out = api.get_esop_summary("NYKAA")
        assert out["available"] is False

    def test_surfaces_headline_and_history(self, tmp_path: Path, monkeypatch):
        import json as _json
        db = tmp_path / "test.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(db))

        plans = [
            {"name": "FSN ESOP 2017", "year_introduced": 2017,
             "options_outstanding_fy_end": 14_000_000, "type": "ESOP"},
            {"name": "FSN RSU 2021", "year_introduced": 2021,
             "options_outstanding_fy_end": 1_000_000, "type": "RSU"},
        ]
        with FlowStore() as s:
            s.upsert_ar_esop_summary(
                "NYKAA", "FY25",
                total_plans=2,
                options_outstanding=15_000_000,
                options_outstanding_pct_paidup=5.2,
                options_granted_fy=2_000_000,
                options_exercised_fy=500_000,
                options_lapsed_fy=300_000,
                weighted_avg_exercise_price=180.5,
                plans_json=_json.dumps(plans),
            )
            s.upsert_ar_esop_summary(
                "NYKAA", "FY24",
                total_plans=2,
                options_outstanding=12_000_000,
                options_outstanding_pct_paidup=4.5,
            )

        api = ResearchDataAPI()
        out = api.get_esop_summary("NYKAA")
        assert out["available"] is True
        assert out["latest_fy"] == "FY25"
        assert out["headline"]["options_outstanding"] == 15_000_000
        assert out["headline"]["options_outstanding_pct_paidup"] == 5.2
        assert out["headline"]["weighted_avg_exercise_price"] == 180.5
        assert out["fy_flow"]["options_granted_fy"] == 2_000_000
        assert len(out["plans"]) == 2
        assert len(out["history"]) == 2
        # History latest-first
        assert [r["fiscal_year"] for r in out["history"]] == ["FY25", "FY24"]


class TestEsopPersistenceFromAr:
    """`_persist_esop_to_store` mirrors AR JSON into ar_esop_summary."""

    def test_persists_when_business_field_present(self, tmp_path: Path, monkeypatch):
        from flowtracker.research.annual_report_extractor import _persist_esop_to_store
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        _persist_esop_to_store("NYKAA", "FY25", {
            "total_plans": 2,
            "options_outstanding": 15_000_000,
            "options_outstanding_pct_paidup": 5.2,
            "plans": [{"name": "FSN ESOP 2017"}],
            "_chars_extracted_from": 10000,
        })
        with FlowStore() as s:
            rows = s.get_ar_esop_summary("NYKAA")
        assert len(rows) == 1
        assert rows[0]["options_outstanding_pct_paidup"] == 5.2

    def test_skips_when_section_not_found(self, tmp_path: Path, monkeypatch):
        from flowtracker.research.annual_report_extractor import _persist_esop_to_store
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        _persist_esop_to_store("X", "FY25", {"status": "section_not_found_or_empty", "chars": 0})
        with FlowStore() as s:
            assert s.get_ar_esop_summary("X") == []

    def test_skips_when_extraction_error(self, tmp_path: Path, monkeypatch):
        from flowtracker.research.annual_report_extractor import _persist_esop_to_store
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        _persist_esop_to_store("X", "FY25", {"extraction_error": "JSON parse: ..."})
        with FlowStore() as s:
            assert s.get_ar_esop_summary("X") == []

    def test_skips_when_all_business_fields_null(self, tmp_path: Path, monkeypatch):
        """Schema-shaped placeholder with no real data → not persisted."""
        from flowtracker.research.annual_report_extractor import _persist_esop_to_store
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        _persist_esop_to_store("X", "FY25", {
            "total_plans": None, "options_outstanding": None,
            "plans": [], "_chars_extracted_from": 1000,
        })
        with FlowStore() as s:
            assert s.get_ar_esop_summary("X") == []

    def test_persists_when_only_plans_present(self, tmp_path: Path, monkeypatch):
        from flowtracker.research.annual_report_extractor import _persist_esop_to_store
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_path / "test.db"))
        _persist_esop_to_store("X", "FY25", {
            "total_plans": None, "options_outstanding": None,
            "plans": [{"name": "Founders ESOP"}],
        })
        with FlowStore() as s:
            rows = s.get_ar_esop_summary("X")
        assert len(rows) == 1
        assert rows[0]["plans_json"]
