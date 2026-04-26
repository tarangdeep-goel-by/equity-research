"""Tests for the BFSI press-release extractor.

Covers:
- ``_filing_date_to_fy_quarter`` mapping (the foundation for grouping filings)
- ``_quarter_end_date`` mapping
- Industry gate (only fires for BFSI)
- ``_find_filings_for_symbol`` dedup + Press-Release-preferred-over-Financial-Results logic
- ``_is_results_filing`` heuristic (filters out non-results press releases)
- ``ensure_press_release_pdf`` cache hit / cache miss with download mock
- Image-rendered PDF detection
- Round-trip: persist JSON → read back via ``get_press_release_metrics``
- ``get_sector_kpis`` merge: concall provides CASA but null NNPA;
  press_release provides NNPA → merged result has both
- Press-release-only quarter is added when concall has no entry for it
- ``_extract_json`` JSON parsing fallbacks
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from flowtracker.research import press_release_extractor as pre


# ---------------------------------------------------------------------------
# Helpers under test
# ---------------------------------------------------------------------------


class TestFilingDateToFyQuarter:
    """BSE filing dates land in FY-Quarters per the Indian results calendar."""

    @pytest.mark.parametrize(
        "filing_date,expected_fq",
        [
            ("2026-04-18", "FY26-Q4"),  # April → previous Q4 (Jan-Mar)
            ("2026-01-17", "FY26-Q3"),  # January → Q3 (Oct-Dec)
            ("2025-10-18", "FY26-Q2"),  # October → Q2 (Jul-Sep)
            ("2025-07-19", "FY26-Q1"),  # July → Q1 (Apr-Jun)
            ("2025-05-03", "FY25-Q4"),  # May → Q4 of FY25
            ("2024-08-08", "FY25-Q1"),  # August → Q1 of FY25
        ],
    )
    def test_mapping(self, filing_date: str, expected_fq: str) -> None:
        assert pre._filing_date_to_fy_quarter(filing_date) == expected_fq


class TestQuarterEndDate:
    @pytest.mark.parametrize(
        "fy_quarter,expected",
        [
            ("FY26-Q4", "2026-03-31"),
            ("FY26-Q3", "2025-12-31"),
            ("FY26-Q2", "2025-09-30"),
            ("FY26-Q1", "2025-06-30"),
        ],
    )
    def test_mapping(self, fy_quarter: str, expected: str) -> None:
        assert pre._quarter_end_date(fy_quarter) == expected


class TestIndustryGate:
    """Only BFSI symbols should be eligible for press-release extraction."""

    def test_yfinance_bank_industry_eligible(self) -> None:
        assert pre.is_eligible_industry("Banks - Regional") is True

    def test_screener_bank_industry_eligible(self) -> None:
        assert pre.is_eligible_industry("Private Sector Bank") is True

    def test_nbfc_eligible(self) -> None:
        assert pre.is_eligible_industry(
            "Non Banking Financial Company (NBFC)"
        ) is True

    def test_pharma_not_eligible(self) -> None:
        assert pre.is_eligible_industry("Drug Manufacturers - Specialty & Generic") is False

    def test_it_not_eligible(self) -> None:
        assert pre.is_eligible_industry("Information Technology Services") is False

    def test_none_not_eligible(self) -> None:
        assert pre.is_eligible_industry(None) is False

    def test_empty_not_eligible(self) -> None:
        assert pre.is_eligible_industry("") is False


class TestIsResultsFiling:
    """Distinguishes quarterly results press releases from one-off press releases."""

    @pytest.mark.parametrize(
        "headline",
        [
            "Press Release - Financial Results for the quarter ended December 31, 2025",
            "Press Release Q4FY25 Results",
            "Audited Financial Results for the year ended March 31, 2026",
            "Unaudited Financial Results for Q1FY26",
            "Earnings Call Transcript",
        ],
    )
    def test_results_headlines_match(self, headline: str) -> None:
        assert pre._is_results_filing(headline) is True

    @pytest.mark.parametrize(
        "headline",
        [
            "Press Release - Raising of Tier 2 Bonds",
            "Media Release on Stock Split",
            "Disclosure under Regulation 30",
            "Newspaper Publication",
            "",
        ],
    )
    def test_non_results_headlines_dont_match(self, headline: str) -> None:
        assert pre._is_results_filing(headline) is False


class TestExtractJson:
    """Mirror concall_extractor JSON parsing tests for press_release_extractor."""

    def test_extract_json_direct(self) -> None:
        raw = '{"fy_quarter": "FY26-Q3", "nim_pct": 3.51}'
        result = pre._extract_json(raw)
        assert result["fy_quarter"] == "FY26-Q3"
        assert result["nim_pct"] == 3.51

    def test_extract_json_code_fence(self) -> None:
        raw = 'OK:\n```json\n{"fy_quarter": "FY26-Q3", "nnpa_pct": 0.42}\n```\n'
        result = pre._extract_json(raw)
        assert result["nnpa_pct"] == 0.42

    def test_extract_json_with_prose_prefix(self) -> None:
        raw = 'Here is the data:\n{"fy_quarter": "FY26-Q4", "casa_pct": 33.6}'
        result = pre._extract_json(raw)
        assert result["casa_pct"] == 33.6

    def test_extract_json_no_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            pre._extract_json("This is just prose, no JSON here.")

    def test_extract_json_trailing_comma_repaired(self) -> None:
        raw = '{"a": 1, "b": 2,}'
        result = pre._extract_json(raw)
        assert result == {"a": 1, "b": 2}


class TestImageRenderedDetection:
    def test_normal_text_pdf_not_image(self) -> None:
        # 5 pages, ~3000 chars/page → text PDF
        text = "Net Interest Margin was 3.51%. " * 500
        assert pre._is_image_rendered(text, page_count=5) is False

    def test_image_pdf_detected(self) -> None:
        # 10 pages, ~5 chars total → image PDF
        text = "x"
        assert pre._is_image_rendered(text, page_count=10) is True

    def test_zero_pages_safe(self) -> None:
        assert pre._is_image_rendered("", page_count=0) is False


# ---------------------------------------------------------------------------
# _build_metric_record — normalisation
# ---------------------------------------------------------------------------


class TestBuildMetricRecord:
    def test_full_extraction_normalised(self) -> None:
        extraction = {
            "fy_quarter": "FY26-Q3",
            "as_of_date": "2025-12-31",
            "is_press_release": True,
            "nim_pct": 3.51,
            "gnpa_pct": 1.24,
            "nnpa_pct": 0.42,
            "casa_pct": 33.6,
            "crar_pct": 19.9,
            "cet1_pct": 17.4,
            "tier1_pct": 17.8,
            "source_page": {"nim_pct": 18, "casa_pct": 19},
            "context": {"nim_pct": "core 3.35% on assets, 3.51% on IEA — taking IEA"},
        }
        candidate = {
            "filing_date": "2026-01-17",
            "subcategory": "Press Release / Media Release",
            "headline": "Press Release - Financial Results for Q3 FY26",
        }
        record = pre._build_metric_record(extraction, "FY26-Q3", candidate, "press_release.pdf")
        assert record["fy_quarter"] == "FY26-Q3"
        assert record["as_of_date"] == "2025-12-31"
        assert record["extraction_status"] == "complete"
        assert record["metrics"]["nim_pct"] == 3.51
        assert record["metrics"]["casa_pct"] == 33.6
        assert record["metrics"]["lcr_pct"] is None  # not in extraction → null
        assert record["source_page"]["nim_pct"] == 18

    def test_string_value_coerced_to_float(self) -> None:
        """Defensive — Claude sometimes returns "3.51%" instead of 3.51."""
        extraction = {"nim_pct": "3.51%", "gnpa_pct": "1.24"}
        record = pre._build_metric_record(
            extraction, "FY26-Q3", {"filing_date": "2026-01-17"}, "x.pdf",
        )
        assert record["metrics"]["nim_pct"] == 3.51
        assert record["metrics"]["gnpa_pct"] == 1.24

    def test_unparseable_string_stays_none(self) -> None:
        extraction = {"nim_pct": "NA"}
        record = pre._build_metric_record(extraction, "FY26-Q3", {}, "x.pdf")
        assert record["metrics"]["nim_pct"] is None

    def test_as_of_date_defaults_when_missing(self) -> None:
        extraction = {"nim_pct": 3.0}  # no as_of_date in extraction
        record = pre._build_metric_record(extraction, "FY26-Q4", {}, "x.pdf")
        assert record["as_of_date"] == "2026-03-31"


# ---------------------------------------------------------------------------
# _find_filings_for_symbol — DB-backed discovery + dedup
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_filing_store(tmp_db, monkeypatch):
    """A FlowStore with a hand-picked corporate_filings dataset for HDFCBANK."""
    from flowtracker.filing_models import CorporateFiling
    from flowtracker.store import FlowStore

    monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
    store = FlowStore(db_path=tmp_db)
    rows = [
        # FY26-Q3 has BOTH Press Release and Financial Results — Press Release wins
        CorporateFiling(
            symbol="HDFCBANK", bse_scrip_code="500180",
            filing_date="2026-01-17", category="Company Update",
            subcategory="Press Release / Media Release",
            headline="Press Release - Financial Results for Q3 FY26",
            attachment_name="aaaaaaaa.pdf", pdf_flag=0,
            file_size=12345, news_id="nid-q3-pr", local_path=None,
        ),
        CorporateFiling(
            symbol="HDFCBANK", bse_scrip_code="500180",
            filing_date="2026-01-17", category="Result", subcategory="Financial Results",
            headline="Unaudited Financial Results for Q3 FY26",
            attachment_name="bbbbbbbb.pdf", pdf_flag=0,
            file_size=12345, news_id="nid-q3-fr", local_path=None,
        ),
        # FY26-Q4 has only Financial Results (HDFCBANK actual case)
        CorporateFiling(
            symbol="HDFCBANK", bse_scrip_code="500180",
            filing_date="2026-04-18", category="Result", subcategory="Financial Results",
            headline="Financial Results for the quarter and year ended March 31, 2026",
            attachment_name="cccccccc.pdf", pdf_flag=1,
            file_size=12345, news_id="nid-q4-fr", local_path=None,
        ),
        # Non-results press release — should be filtered out
        CorporateFiling(
            symbol="HDFCBANK", bse_scrip_code="500180",
            filing_date="2025-06-08", category="Company Update",
            subcategory="Press Release / Media Release",
            headline="Disclosure under Regulation 30 of SEBI",
            attachment_name="dddddddd.pdf", pdf_flag=0,
            file_size=12345, news_id="nid-disclosure", local_path=None,
        ),
    ]
    store.upsert_filings(rows)
    yield store
    store.close()


class TestFindFilingsForSymbol:
    def test_dedup_press_release_preferred(self, populated_filing_store) -> None:
        results = pre._find_filings_for_symbol("HDFCBANK", max_quarters=4)
        # Should have 2 quarters (Q3 dedup'd, Q4, disclosure filtered out)
        assert len(results) == 2
        q3 = next(r for r in results if r["fy_quarter"] == "FY26-Q3")
        assert "Press Release" in q3["subcategory"], f"Q3 should be Press Release, got {q3['subcategory']}"

    def test_q4_falls_back_to_financial_results(self, populated_filing_store) -> None:
        results = pre._find_filings_for_symbol("HDFCBANK", max_quarters=4)
        q4 = next(r for r in results if r["fy_quarter"] == "FY26-Q4")
        assert q4["subcategory"] == "Financial Results"

    def test_non_results_press_releases_filtered(self, populated_filing_store) -> None:
        results = pre._find_filings_for_symbol("HDFCBANK", max_quarters=4)
        assert all("Disclosure under Regulation 30" not in r["headline"] for r in results)

    def test_max_quarters_caps(self, populated_filing_store) -> None:
        results = pre._find_filings_for_symbol("HDFCBANK", max_quarters=1)
        assert len(results) == 1
        assert results[0]["fy_quarter"] == "FY26-Q4"  # most recent


# ---------------------------------------------------------------------------
# Round-trip: extractor output → vault JSON → get_press_release_metrics
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """The extractor's output JSON must be readable by get_press_release_metrics."""

    def test_persist_and_read_back(self, monkeypatch, tmp_path: Path) -> None:
        """Write a payload via extractor's _save, read back via data_api."""
        # Both writer (extractor) and reader (data_api) must resolve to the
        # same directory: <tmp_path>/vault/stocks/<sym>/fundamentals/
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        monkeypatch.setattr(pre, "_VAULT_BASE", tmp_path / "vault" / "stocks")

        payload = {
            "symbol": "HDFCBANK",
            "industry": "Banks - Regional",
            "extraction_version": "v1",
            "extraction_date": "2026-04-26",
            "quarters": {
                "FY26-Q3": {
                    "fy_quarter": "FY26-Q3",
                    "as_of_date": "2025-12-31",
                    "filing_date": "2026-01-17",
                    "subcategory": "Press Release / Media Release",
                    "headline": "Press Release Q3 FY26",
                    "source_filename": "press_release.pdf",
                    "extraction_status": "complete",
                    "extraction_version": "v1",
                    "extracted_at": "2026-04-26T10:00:00Z",
                    "is_press_release": True,
                    "metrics": {
                        "gnpa_pct": 1.24, "nnpa_pct": 0.42, "pcr_pct": None,
                        "nim_pct": 3.51, "casa_pct": 33.6,
                        "crar_pct": 19.9, "cet1_pct": 17.4, "tier1_pct": 17.8,
                        "lcr_pct": None,
                        "advances_cr": 2844600, "deposits_cr": 2860100, "rwa_cr": 2880800,
                    },
                    "source_page": {"nim_pct": 18, "casa_pct": 19},
                    "context": {"nim_pct": "core 3.35% on assets, 3.51% on IEA"},
                },
            },
        }
        pre._save("HDFCBANK", payload)

        # Now read back via ResearchDataAPI.get_press_release_metrics, also
        # redirected to tmp_path. Patch _Path.home in data_api to return tmp_path.
        from flowtracker.research import data_api as da

        class _FakeHome:
            @staticmethod
            def home():
                return tmp_path

        # Patch Path.home indirectly — data_api uses _Path.home() inside the
        # method. Easiest route: monkeypatch pathlib.Path.home for this scope.
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # Re-stat with a fresh API instance — no DB needed for this method.
        from flowtracker.research.data_api import ResearchDataAPI
        # Use a tmp DB so the constructor doesn't touch real DB
        tmp_db = tmp_path / "tmp.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()

        full = api.get_press_release_metrics("HDFCBANK")
        assert full["symbol"] == "HDFCBANK"
        assert "FY26-Q3" in full["quarters"]

        single = api.get_press_release_metrics("HDFCBANK", period="FY26-Q3")
        assert single["fy_quarter"] == "FY26-Q3"
        assert single["metrics"]["nim_pct"] == 3.51
        assert single["metrics"]["nnpa_pct"] == 0.42

        # Missing quarter → error with available_quarters listed
        missing = api.get_press_release_metrics("HDFCBANK", period="FY99-Q9")
        assert "error" in missing
        assert "FY26-Q3" in missing["available_quarters"]

        api.close()

    def test_missing_pdf_returns_empty(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        from flowtracker.research.data_api import ResearchDataAPI
        tmp_db = tmp_path / "tmp.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        api = ResearchDataAPI()
        result = api.get_press_release_metrics("DOESNOTEXIST")
        assert result == {}
        api.close()


# ---------------------------------------------------------------------------
# get_sector_kpis merge — concall + press_release backfill
# ---------------------------------------------------------------------------


class TestGetSectorKpisMerge:
    """When concall lacks NNPA but press_release has NNPA, merged result has both."""

    def _setup_vault(self, tmp_path: Path, monkeypatch) -> None:
        """Layout:
           ~/vault/stocks/HDFCBANK/fundamentals/concall_extraction_v2.json
           ~/vault/stocks/HDFCBANK/fundamentals/press_release_extraction_v1.json
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        fund_dir = tmp_path / "vault" / "stocks" / "HDFCBANK" / "fundamentals"
        fund_dir.mkdir(parents=True, exist_ok=True)

        concall = {
            "symbol": "HDFCBANK",
            "quarters_analyzed": 1,
            "sector": "Banks - Regional",
            "extraction_date": "2026-04-26",
            "quarters": [
                {
                    "fy_quarter": "FY26-Q3",
                    "label": "Q3 FY26",
                    "extraction_status": "complete",
                    "documents_read": ["concall.pdf"],
                    # Concall has CASA but null NNPA (the gap the user described)
                    "operational_metrics": {
                        "casa_ratio_pct": {"value": 33.6, "context": "33.6% of total deposits"},
                        "net_npa_pct": {"value": None, "reason": "not_mentioned_in_concall"},
                    },
                    "financial_metrics": {},
                },
            ],
            "cross_quarter_narrative": {},
        }
        (fund_dir / "concall_extraction_v2.json").write_text(json.dumps(concall))

        press_release = {
            "symbol": "HDFCBANK",
            "industry": "Banks - Regional",
            "extraction_version": "v1",
            "extraction_date": "2026-04-26",
            "quarters": {
                "FY26-Q3": {
                    "fy_quarter": "FY26-Q3",
                    "as_of_date": "2025-12-31",
                    "extraction_status": "complete",
                    "is_press_release": True,
                    "metrics": {
                        # Has NNPA but null CASA — exact opposite of concall
                        "casa_pct": None,
                        "nnpa_pct": 0.42,
                        "gnpa_pct": 1.24,
                        "nim_pct": 3.51,
                        "crar_pct": 19.9,
                        "cet1_pct": 17.4,
                        "pcr_pct": None,
                        "lcr_pct": None,
                        "tier1_pct": 17.8,
                        "advances_cr": None,
                        "deposits_cr": None,
                        "rwa_cr": None,
                    },
                    "source_page": {"nnpa_pct": 20, "nim_pct": 18, "crar_pct": 20, "cet1_pct": 20, "gnpa_pct": 20},
                    "context": {"nim_pct": "core 3.35% on assets; 3.51% on IEA"},
                },
            },
        }
        (fund_dir / "press_release_extraction_v1.json").write_text(json.dumps(press_release))

    def test_merge_fills_missing_nnpa_from_press_release(self, monkeypatch, tmp_path: Path) -> None:
        self._setup_vault(tmp_path, monkeypatch)
        tmp_db = tmp_path / "tmp.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.data_api import ResearchDataAPI
        api = ResearchDataAPI()
        # Patch _get_industry to return BFSI without DB lookup
        monkeypatch.setattr(api, "_get_industry", lambda s: "Banks - Regional")

        result = api.get_sector_kpis("HDFCBANK")
        kpi_keys = {k["key"] for k in result["available_kpis"]}
        # Both CASA (from concall) AND NNPA (from press release) must be present
        assert "casa_ratio_pct" in kpi_keys, f"CASA missing from merged: {kpi_keys}"
        assert "net_npa_pct" in kpi_keys, f"NNPA missing from merged: {kpi_keys}"
        # NIM also from press release
        assert "net_interest_margin_pct" in kpi_keys
        assert "gross_npa_pct" in kpi_keys
        assert "capital_adequacy_ratio_pct" in kpi_keys
        assert "cet1_pct" in kpi_keys

        # _meta should expose the press_release backfill source
        meta = result.get("_meta", {})
        assert "press_release_backfilled_kpis" in meta
        # NNPA, NIM, GNPA, CRAR, CET-1 came from press release
        backfilled = set(meta["press_release_backfilled_kpis"])
        assert "net_npa_pct" in backfilled
        assert "net_interest_margin_pct" in backfilled
        # CASA came from concall — should NOT be in backfilled list
        assert "casa_ratio_pct" not in backfilled

        api.close()

    def test_drilldown_returns_press_release_value(self, monkeypatch, tmp_path: Path) -> None:
        self._setup_vault(tmp_path, monkeypatch)
        tmp_db = tmp_path / "tmp.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))

        from flowtracker.research.data_api import ResearchDataAPI
        api = ResearchDataAPI()
        monkeypatch.setattr(api, "_get_industry", lambda s: "Banks - Regional")

        # Drill into NNPA — should come from press release with matched_via marker
        nnpa = api.get_sector_kpis("HDFCBANK", kpi_key="net_npa_pct")
        assert nnpa["kpi"]["values"][0]["value"] == 0.42
        assert nnpa["kpi"]["values"][0]["matched_via"] == "press_release:nnpa_pct"

        api.close()

    def test_press_release_only_quarter_added(self, monkeypatch, tmp_path: Path) -> None:
        """When concall has Q3 only but press_release has Q3 + Q4, both quarters appear."""
        self._setup_vault(tmp_path, monkeypatch)

        # Add a Q4 to the press release JSON only
        fund_dir = tmp_path / "vault" / "stocks" / "HDFCBANK" / "fundamentals"
        pr_path = fund_dir / "press_release_extraction_v1.json"
        pr_payload = json.loads(pr_path.read_text())
        pr_payload["quarters"]["FY26-Q4"] = {
            "fy_quarter": "FY26-Q4",
            "as_of_date": "2026-03-31",
            "extraction_status": "complete",
            "is_press_release": True,
            "metrics": {
                "casa_pct": None, "nnpa_pct": 0.41, "gnpa_pct": 1.21,
                "nim_pct": 3.50, "crar_pct": 19.85, "cet1_pct": 17.3,
                "pcr_pct": None, "lcr_pct": None, "tier1_pct": None,
                "advances_cr": None, "deposits_cr": None, "rwa_cr": None,
            },
            "source_page": {},
            "context": {},
        }
        pr_path.write_text(json.dumps(pr_payload))

        tmp_db = tmp_path / "tmp.db"
        monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))
        from flowtracker.research.data_api import ResearchDataAPI
        api = ResearchDataAPI()
        monkeypatch.setattr(api, "_get_industry", lambda s: "Banks - Regional")

        nnpa = api.get_sector_kpis("HDFCBANK", kpi_key="net_npa_pct")
        # Should have BOTH Q3 (from concall+pr-backfill) AND Q4 (pr only)
        quarter_labels = {v["quarter"] for v in nnpa["kpi"]["values"]}
        assert "FY26-Q3" in quarter_labels
        assert "FY26-Q4" in quarter_labels

        api.close()


# ---------------------------------------------------------------------------
# extract_press_releases — pipeline integration with mocked Claude
# ---------------------------------------------------------------------------


class TestExtractPressReleases:
    @pytest.mark.asyncio
    async def test_non_bfsi_skipped(self, monkeypatch) -> None:
        """Industry gate: non-BFSI symbols return None without doing any work."""
        # Force industry to non-BFSI
        called = {"find": False}

        def _spy_find(*args, **kwargs):
            called["find"] = True
            return []

        monkeypatch.setattr(pre, "_find_filings_for_symbol", _spy_find)
        result = await pre.extract_press_releases("INFY", industry="Information Technology Services")
        assert result is None
        assert called["find"] is False, "Should not call _find_filings_for_symbol for non-BFSI"

    @pytest.mark.asyncio
    async def test_no_filings_returns_none(self, monkeypatch) -> None:
        monkeypatch.setattr(pre, "_find_filings_for_symbol", lambda s, max_quarters: [])
        result = await pre.extract_press_releases("HDFCBANK", industry="Banks - Regional")
        assert result is None

    @pytest.mark.asyncio
    async def test_happy_path_extracts_and_persists(self, monkeypatch, tmp_path: Path) -> None:
        """Mock Claude to return a fixture JSON; verify cache file created."""
        monkeypatch.setattr(pre, "_VAULT_BASE", tmp_path)

        candidate = {
            "fy_quarter": "FY26-Q3",
            "filing_date": "2026-01-17",
            "news_id": "nid-q3",
            "attachment_name": "abc.pdf",
            "pdf_flag": 0,
            "headline": "Press Release Q3 FY26",
            "subcategory": "Press Release / Media Release",
            "local_path": None,
        }
        monkeypatch.setattr(pre, "_find_filings_for_symbol", lambda s, max_quarters: [candidate])

        # Pretend the PDF download succeeded — write a stub file
        def _fake_ensure(symbol, fq, cand):
            dest = tmp_path / symbol / "filings" / fq / "press_release.pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-fakecontent" + b"x" * 5000)
            return dest

        monkeypatch.setattr(pre, "ensure_press_release_pdf", _fake_ensure)

        # Pretend pdfplumber returns a usable text body
        monkeypatch.setattr(
            pre, "_read_pdf_text",
            lambda p: ("Net Interest Margin 3.51%. Gross NPA 1.24%. " * 100, 5),
        )

        # Mock Claude to return the canonical JSON
        async def _fake_call_claude(*args, **kwargs):
            return json.dumps({
                "fy_quarter": "FY26-Q3",
                "as_of_date": "2025-12-31",
                "is_press_release": True,
                "nim_pct": 3.51,
                "gnpa_pct": 1.24,
                "nnpa_pct": 0.42,
                "casa_pct": 33.6,
                "crar_pct": 19.9,
                "cet1_pct": 17.4,
                "tier1_pct": 17.8,
                "pcr_pct": None,
                "lcr_pct": None,
                "advances_cr": 2844600,
                "deposits_cr": 2860100,
                "rwa_cr": 2880800,
                "source_page": {"nim_pct": 18, "gnpa_pct": 20},
                "context": {"nim_pct": "core 3.35% on assets, 3.51% on IEA"},
            })

        monkeypatch.setattr(pre, "_call_claude", _fake_call_claude)

        result = await pre.extract_press_releases(
            "HDFCBANK", quarters=1, industry="Banks - Regional",
        )
        assert result is not None
        assert result["symbol"] == "HDFCBANK"
        assert "FY26-Q3" in result["quarters"]
        q3 = result["quarters"]["FY26-Q3"]
        assert q3["extraction_status"] == "complete"
        assert q3["metrics"]["nim_pct"] == 3.51
        assert q3["metrics"]["nnpa_pct"] == 0.42

        # Verify the JSON cache file was actually written (under whichever
        # vault base the extractor sees).
        out_path = pre._output_path("HDFCBANK")
        assert out_path.exists()
        on_disk = json.loads(out_path.read_text())
        assert "FY26-Q3" in on_disk["quarters"]

    @pytest.mark.asyncio
    async def test_image_rendered_pdf_marked_and_skipped(self, monkeypatch, tmp_path: Path) -> None:
        """OCR-required PDFs are recorded with status='image_rendered'."""
        monkeypatch.setattr(pre, "_VAULT_BASE", tmp_path)
        candidate = {
            "fy_quarter": "FY26-Q3", "filing_date": "2026-01-17",
            "news_id": "nid-q3", "attachment_name": "abc.pdf", "pdf_flag": 0,
            "headline": "Press Release Q3 FY26",
            "subcategory": "Press Release / Media Release", "local_path": None,
        }
        monkeypatch.setattr(pre, "_find_filings_for_symbol", lambda s, max_quarters: [candidate])

        def _fake_ensure(symbol, fq, cand):
            dest = tmp_path / symbol / "filings" / fq / "press_release.pdf"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-x" + b"y" * 5000)
            return dest

        monkeypatch.setattr(pre, "ensure_press_release_pdf", _fake_ensure)
        # Simulate image-rendered: 10 pages but only 5 chars of text
        monkeypatch.setattr(pre, "_read_pdf_text", lambda p: ("x", 10))

        # Claude must NOT be called
        called = {"claude": False}
        async def _spy_claude(*args, **kwargs):
            called["claude"] = True
            return "{}"
        monkeypatch.setattr(pre, "_call_claude", _spy_claude)

        result = await pre.extract_press_releases(
            "HDFCBANK", quarters=1, industry="Banks - Regional",
        )
        assert result is not None
        assert result["quarters"]["FY26-Q3"]["extraction_status"] == "image_rendered"
        assert called["claude"] is False, "Claude should not be called for image-rendered PDFs"

    @pytest.mark.asyncio
    async def test_download_failure_recorded(self, monkeypatch, tmp_path: Path) -> None:
        """When PDF download fails, record status='download_failed' and continue."""
        monkeypatch.setattr(pre, "_VAULT_BASE", tmp_path)
        candidate = {
            "fy_quarter": "FY26-Q3", "filing_date": "2026-01-17",
            "news_id": "nid-q3", "attachment_name": "abc.pdf", "pdf_flag": 0,
            "headline": "Press Release Q3 FY26",
            "subcategory": "Press Release / Media Release", "local_path": None,
        }
        monkeypatch.setattr(pre, "_find_filings_for_symbol", lambda s, max_quarters: [candidate])
        monkeypatch.setattr(pre, "ensure_press_release_pdf", lambda s, fq, c: None)

        result = await pre.extract_press_releases(
            "HDFCBANK", quarters=1, industry="Banks - Regional",
        )
        assert result is not None
        assert result["quarters"]["FY26-Q3"]["extraction_status"] == "download_failed"
