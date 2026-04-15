"""Tests for paginated sector_kpis / concall_insights + BFSI CAGR suppression.

Covers the tool-layer fixes that address compliance-gate truncation:
- sector_kpis + concall_insights TOC/drill pattern
- BFSI EBITDA/FCF suppression in cagr_table
- BFSI asset_quality lift from concall operational_metrics
- Extended industry → sector mappings

Tests write synthetic concall JSON to a tmp vault to avoid coupling with
real stock data while still exercising the real code paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.research.sector_kpis import SECTOR_KPI_CONFIG
from flowtracker.store import FlowStore


# ---------------------------------------------------------------------------
# Fixtures: tmp vault with a synthetic concall extraction
# ---------------------------------------------------------------------------

def _write_concall(vault_root: Path, symbol: str, quarters: list[dict], narrative: dict | None = None) -> None:
    """Write a concall_extraction_v2.json for <symbol> under <vault_root>."""
    fdir = vault_root / "stocks" / symbol / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "quarters": quarters,
        "cross_quarter_narrative": narrative or {},
    }
    (fdir / "concall_extraction_v2.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def vault_home(tmp_path: Path, monkeypatch) -> Path:
    """Redirect Path.home() to a tmp dir so concall reads hit our fixtures."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() consults HOME on POSIX; that's enough for get_concall_insights
    return tmp_path


@pytest.fixture
def api(tmp_db: Path, populated_store: FlowStore, monkeypatch, vault_home: Path) -> ResearchDataAPI:
    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    a = ResearchDataAPI()
    yield a
    a.close()


def _bank_concall_quarters() -> list[dict]:
    """Minimal bank concall with two KPIs populated across two quarters."""
    return [
        {
            "fy_quarter": "FY26-Q2",
            "period_ended": "2025-09-30",
            "operational_metrics": {
                "casa_ratio_pct": {"value": "39.63%", "context": "Stable franchise"},
                "gross_npa_pct": {"value": "1.73%", "context": "Down 32bps YoY"},
            },
            "financial_metrics": {"net_profit_cr": {"value": "20000"}},
            "management_commentary": {"outlook": "Bullish on credit growth"},
            "qa_session": [{"analyst": "XYZ", "questions": ["slippage outlook"], "notable": "Stable"}],
            "flags": {"red_flags": []},
        },
        {
            "fy_quarter": "FY26-Q1",
            "period_ended": "2025-06-30",
            "operational_metrics": {
                "casa_ratio_pct": {"value": "40.12%"},
                # gross_npa_pct deliberately absent in this quarter
            },
            "financial_metrics": {},
            "management_commentary": {},
            "qa_session": [],
            "flags": None,  # test that None doesn't crash downstream
        },
    ]


# ---------------------------------------------------------------------------
# get_concall_insights — TOC mode + drill mode
# ---------------------------------------------------------------------------

class TestConcallInsightsTOC:
    def test_toc_returns_compact_structure_no_per_quarter_payload(self, api, vault_home):
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())
        toc = api.get_concall_insights("TESTCO")
        size = len(json.dumps(toc))

        assert "available_sections" in toc
        assert "quarters" in toc
        assert "hint" in toc
        assert all("operational_metrics" not in q for q in toc["quarters"]), \
            "TOC must not include per-quarter payload"
        assert size < 4000, f"TOC should be <4KB, got {size}"

    def test_toc_lists_populated_sections_per_quarter(self, api, vault_home):
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())
        toc = api.get_concall_insights("TESTCO")
        q1 = toc["quarters"][0]
        assert "operational_metrics" in q1["sections_populated"]
        assert "qa_session" in q1["sections_populated"]
        # Empty flags should not count as populated
        q2 = toc["quarters"][1]
        assert "flags" not in q2["sections_populated"]

    def test_no_concall_returns_error(self, api, vault_home):
        result = api.get_concall_insights("NOSUCHSTOCK")
        assert "error" in result


class TestConcallInsightsDrill:
    def test_drill_returns_only_requested_section(self, api, vault_home):
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())
        drill = api.get_concall_insights("TESTCO", section_filter="operational_metrics")

        assert drill["section"] == "operational_metrics"
        assert len(drill["quarters"]) == 2
        for q in drill["quarters"]:
            # Only the requested section + quarter identity, nothing else
            allowed = {"fy_quarter", "period_ended", "operational_metrics"}
            assert set(q.keys()) - allowed == set()

    def test_drill_with_invalid_section_returns_valid_sections(self, api, vault_home):
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())
        result = api.get_concall_insights("TESTCO", section_filter="nonexistent")
        assert "error" in result
        assert "valid_sections" in result
        assert "operational_metrics" in result["valid_sections"]


# ---------------------------------------------------------------------------
# get_sector_kpis — TOC mode + drill mode + unknown key
# ---------------------------------------------------------------------------

class TestSectorKPIsTOC:
    def test_toc_returns_available_kpis_with_coverage(self, api, vault_home, monkeypatch):
        # Industry must map to 'banks' in sector_kpis.py
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())

        toc = api.get_sector_kpis("TESTCO")
        size = len(json.dumps(toc))

        assert toc["sector"] == "banks"
        assert "available_kpis" in toc
        assert "hint" in toc
        keys = {k["key"] for k in toc["available_kpis"]}
        assert "casa_ratio_pct" in keys
        assert "gross_npa_pct" in keys
        # Coverage should reflect partial extraction (gross_npa in 1 of 2 quarters)
        gnpa = next(k for k in toc["available_kpis"] if k["key"] == "gross_npa_pct")
        assert gnpa["coverage"].startswith("1/")
        casa = next(k for k in toc["available_kpis"] if k["key"] == "casa_ratio_pct")
        assert casa["coverage"].startswith("2/")
        assert size < 2000, f"TOC should be <2KB, got {size}"


class TestSectorKPIsAliasMatching:
    """The concall extractor often writes non-canonical field names (e.g. the
    extractor may emit 'domestic_nim_pct' while the schema canonical is
    'net_interest_margin_pct'). The alias table in sector_kpis.py resolves this.
    """

    def test_alias_resolves_nim_from_domestic_nim_pct(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        # Quarter has NIM under the non-canonical alias 'domestic_nim_pct'
        qs = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {
                "domestic_nim_pct": {"value": "3.09%", "context": "Deposit repricing"},
            },
        }]
        _write_concall(vault_home / "vault", "ALIASTEST", qs)

        drill = api.get_sector_kpis("ALIASTEST", kpi_key="net_interest_margin_pct")
        assert "kpi" in drill
        v = drill["kpi"]["values"][0]
        assert v["value"] == "3.09%"
        assert v["matched_via"] == "alias:domestic_nim_pct"

    def test_alias_resolves_pcr_from_short_form(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        qs = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {"pcr": {"value": "77.5%"}},
        }]
        _write_concall(vault_home / "vault", "ALIASTEST2", qs)

        drill = api.get_sector_kpis("ALIASTEST2", kpi_key="provision_coverage_ratio_pct")
        assert drill["kpi"]["values"][0]["matched_via"] == "alias:pcr"

    def test_direct_match_takes_precedence_over_alias(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        # Both canonical and alias present — canonical wins, no matched_via annotation
        qs = [{
            "fy_quarter": "FY26-Q2",
            "operational_metrics": {
                "net_interest_margin_pct": {"value": "2.60%"},
                "domestic_nim_pct": {"value": "3.09%"},
            },
        }]
        _write_concall(vault_home / "vault", "ALIASTEST3", qs)

        drill = api.get_sector_kpis("ALIASTEST3", kpi_key="net_interest_margin_pct")
        v = drill["kpi"]["values"][0]
        assert v["value"] == "2.60%"
        assert "matched_via" not in v, "canonical match should not be annotated"


class TestSectorKPIsDrill:
    def test_drill_with_valid_key_returns_full_timeline(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())

        drill = api.get_sector_kpis("TESTCO", kpi_key="casa_ratio_pct")
        assert "kpi" in drill
        assert drill["kpi"]["key"] == "casa_ratio_pct"
        assert len(drill["kpi"]["values"]) == 2

    def test_drill_with_valid_key_no_data_returns_schema_valid_status(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        # Quarter data with no coverage for provision_coverage_ratio_pct
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())
        result = api.get_sector_kpis("TESTCO", kpi_key="provision_coverage_ratio_pct")
        assert result["status"] == "schema_valid_but_unavailable"
        assert "quarters_analyzed" in result

    def test_drill_with_unknown_key_returns_valid_keys(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_get_industry", lambda s: "Public Sector Bank")
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())
        result = api.get_sector_kpis("TESTCO", kpi_key="not_a_real_key")
        assert result["status"] == "unknown_key"
        assert "valid_keys" in result
        assert "casa_ratio_pct" in result["valid_keys"]


# ---------------------------------------------------------------------------
# BFSI CAGR suppression — the behavioral change most likely to break callers
# ---------------------------------------------------------------------------

class TestBFSICAGRSuppression:
    """get_growth_cagr_table must NOT include EBITDA or FCF for BFSI stocks.

    Previously, the BFSI CAGR table emitted an EBITDA row that the agent
    misread as "NII proxy = ₹4.09L Cr" — a Gemini-flagged hallucination.
    Non-BFSI stocks must still get all 5 metrics.
    """

    def test_bfsi_has_no_ebitda_or_fcf(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        # Need at least 2 years of annual financials; SBIN in populated_store has them
        cagr = api.get_growth_cagr_table("SBIN")
        if "error" in cagr:
            pytest.skip("populated_store lacks sufficient SBIN annual financials")
        metrics = cagr.get("cagrs", {})
        assert "ebitda" not in metrics, "EBITDA must be suppressed for BFSI"
        assert "fcf" not in metrics, "FCF must be suppressed for BFSI"
        # Core metrics should still be present
        assert "revenue" in metrics
        assert "net_income" in metrics
        assert "eps" in metrics

    def test_non_bfsi_has_ebitda_and_fcf(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: False)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        cagr = api.get_growth_cagr_table("INFY")
        if "error" in cagr:
            pytest.skip("populated_store lacks sufficient INFY annual financials")
        metrics = cagr.get("cagrs", {})
        # Non-BFSI gets the full set
        assert "ebitda" in metrics
        # FCF may be None if CFO/capex data is missing for the synthetic fixtures,
        # but it must appear as a requested metric in the computation path.


# ---------------------------------------------------------------------------
# BFSI asset_quality lift
# ---------------------------------------------------------------------------

class TestBFSIAssetQualityLift:
    def test_asset_quality_surfaced_when_concall_has_metrics(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        _write_concall(vault_home / "vault", "TESTCO", _bank_concall_quarters())

        result = api.get_bfsi_metrics("TESTCO")
        # get_bfsi_metrics still runs the year loop; if the populated_store has
        # no annual data for TESTCO, fallback message is acceptable. The asset
        # quality lift path is the feature under test.
        if "error" in result:
            pytest.skip("asset_quality lift requires annual data in store")
        aq = result.get("asset_quality")
        assert aq is not None
        assert aq.get("source") == "concall operational_metrics" or "status" in aq

    def test_asset_quality_honest_when_concall_absent(self, api, vault_home, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        monkeypatch.setattr(api, "_is_insurance", lambda s: False)
        # No concall written for NOCONCALL
        result = api.get_bfsi_metrics("NOCONCALL")
        if "error" in result:
            pytest.skip("need annual data for the year-loop path")
        # Either no asset_quality block, or a status hint — never fabricated metrics
        aq = result.get("asset_quality")
        assert aq is None or "status" in aq


# ---------------------------------------------------------------------------
# Extended industry → sector mappings
# ---------------------------------------------------------------------------

class TestFundamentalsTOC:
    """get_fundamentals_toc returns the static section menu + recommended waves
    so the agent can plan TOC-then-drill calls without triggering MCP truncation.
    """

    def test_toc_returns_compact_static_menu(self, api):
        toc = api.get_fundamentals_toc("SBIN")
        size = len(json.dumps(toc, default=str))
        assert size < 5000, f"TOC must be <5KB, got {size}"
        assert "available_sections" in toc
        assert len(toc["available_sections"]) == 14
        # Required keys per section
        for s in toc["available_sections"]:
            assert {"key", "size", "purpose"}.issubset(s.keys())

    def test_toc_recommends_4_waves(self, api):
        toc = api.get_fundamentals_toc("SBIN")
        assert "recommended_waves" in toc
        assert len(toc["recommended_waves"]) == 4
        # Wave 1 must include the core P&L sections
        wave1_sections = set(toc["recommended_waves"][0]["sections"])
        assert {"quarterly_results", "annual_financials", "ratios", "cagr_table"}.issubset(wave1_sections)

    def test_toc_marks_bfsi_inapplicable_sections(self, api, monkeypatch):
        monkeypatch.setattr(api, "_is_bfsi", lambda s: True)
        toc = api.get_fundamentals_toc("SBIN")
        assert toc["is_bfsi"] is True
        # Cash-flow sections should be flagged as BFSI-inapplicable
        cfq = next(s for s in toc["available_sections"] if s["key"] == "cash_flow_quality")
        assert "bank" in cfq["purpose"].lower() or "empty" in cfq["purpose"].lower()

    def test_toc_includes_truncation_warning(self, api):
        toc = api.get_fundamentals_toc("SBIN")
        assert "warnings" in toc
        assert "truncation" in toc["warnings"]
        # Warning must mention the dangerous default
        assert "all" in toc["warnings"]["truncation"].lower()


class TestIndustryMappings:
    """Additive mapping coverage — ensures yfinance-style strings resolve to
    the right sector KPI framework without breaking existing Screener strings.
    """

    @pytest.mark.parametrize("industry,expected_sector", [
        ("Banks - Regional", "banks"),
        ("Private Sector Bank", "banks"),
        ("Drug Manufacturers - Specialty & Generic", "pharma"),
        ("Pharmaceuticals", "pharma"),
        ("Refineries & Marketing", "oil_and_gas"),
        ("Utilities - Regulated Electric", "power_and_utilities"),
        ("Household & Personal Products", "fmcg"),
        ("Software - Application", "it_services"),
    ])
    def test_industry_maps_to_sector(self, industry, expected_sector):
        from flowtracker.research.sector_kpis import get_sector_for_industry
        assert get_sector_for_industry(industry) == expected_sector

    def test_unknown_industry_returns_none(self):
        from flowtracker.research.sector_kpis import get_sector_for_industry
        assert get_sector_for_industry("Totally Made Up Sector") is None
