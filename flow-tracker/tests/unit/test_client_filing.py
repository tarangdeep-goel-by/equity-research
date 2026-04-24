"""Tests for filing_client.py — BSE corporate filing parsing."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from flowtracker.filing_client import (
    FilingClient,
    _filing_date_to_fy_quarter,
    _parse_bonus_multiplier,
    _parse_bse_date,
    _parse_dividend_amount,
    _parse_split_multiplier,
    _safe_dirname,
)
from flowtracker.filing_models import CorporateFiling


# -- Fixture data --

_BSE_FILING_ITEM = {
    "ATTACHMENTNAME": "Q3FY26_Results.pdf",
    "NEWS_DT": "2026-01-25T14:30:00",
    "CATEGORYNAME": "Result",
    "SUBCATNAME": "Financial Results",
    "HEADLINE": "Financial Results for Q3 FY2025-26",
    "PDFFLAG": 0,
    "Fld_Attachsize": 1024000,
    "NEWSID": "ABC12345",
}

_BSE_CONCALL_ITEM = {
    "ATTACHMENTNAME": "ConcallTranscript_Q3.pdf",
    "DT_TM": "2026-01-28T10:00:00",
    "CATEGORYNAME": "Company Update",
    "SUBCATNAME": "Earnings Call Transcript",
    "HEADLINE": "Transcript of Earnings Call for Q3 FY26",
    "PDFFLAG": 1,
    "Fld_Attachsize": 500000,
    "NEWSID": "DEF67890",
}

_BSE_NO_ATTACHMENT = {
    "ATTACHMENTNAME": "",
    "NEWS_DT": "2026-01-25T14:30:00",
    "CATEGORYNAME": "Board Meeting",
    "SUBCATNAME": "Board Meeting",
    "HEADLINE": "Board meeting notice",
    "PDFFLAG": 0,
}


class TestParseFiling:
    """Test FilingClient._parse_filing."""

    def test_financial_results(self):
        client = FilingClient()
        filing = client._parse_filing(_BSE_FILING_ITEM, "INDIAMART", "542726")
        assert filing is not None
        assert filing.symbol == "INDIAMART"
        assert filing.bse_scrip_code == "542726"
        assert filing.filing_date == "2026-01-25"
        assert filing.category == "Result"
        assert filing.subcategory == "Financial Results"
        assert filing.headline == "Financial Results for Q3 FY2025-26"
        assert filing.attachment_name == "Q3FY26_Results.pdf"
        assert filing.pdf_flag == 0
        assert filing.file_size == 1024000
        assert filing.news_id == "ABC12345"
        client.close()

    def test_concall_with_dt_tm(self):
        """Uses DT_TM when NEWS_DT is missing."""
        client = FilingClient()
        filing = client._parse_filing(_BSE_CONCALL_ITEM, "SBIN", "500112")
        assert filing is not None
        assert filing.filing_date == "2026-01-28"
        assert filing.subcategory == "Earnings Call Transcript"
        assert filing.pdf_flag == 1
        client.close()

    def test_no_attachment_returns_none(self):
        client = FilingClient()
        filing = client._parse_filing(_BSE_NO_ATTACHMENT, "SBIN", "500112")
        assert filing is None
        client.close()

    def test_invalid_date_still_parses(self):
        """If date is malformed, filing_date becomes empty string."""
        client = FilingClient()
        item = {**_BSE_FILING_ITEM, "NEWS_DT": "bad-date", "DT_TM": ""}
        filing = client._parse_filing(item, "SBIN", "500112")
        assert filing is not None
        assert filing.filing_date == ""
        client.close()

    def test_headline_truncation(self):
        """Headlines are truncated to 500 chars."""
        client = FilingClient()
        item = {**_BSE_FILING_ITEM, "HEADLINE": "X" * 600}
        filing = client._parse_filing(item, "SBIN", "500112")
        assert filing is not None
        assert len(filing.headline) == 500
        client.close()


class TestSafeDirname:
    """Test _safe_dirname helper."""

    def test_simple_category(self):
        assert _safe_dirname("Financial Results") == "financial_results"

    def test_slashes_and_special_chars(self):
        assert _safe_dirname("Analyst / Investor Meet") == "analyst_investor_meet"

    def test_empty_string(self):
        assert _safe_dirname("") == ""


class TestFilingDateToFyQuarter:
    """Test _filing_date_to_fy_quarter helper."""

    def test_jan_march_is_q3(self):
        assert _filing_date_to_fy_quarter("2026-01-25") == "FY26-Q3"
        assert _filing_date_to_fy_quarter("2026-02-15") == "FY26-Q3"
        assert _filing_date_to_fy_quarter("2026-03-31") == "FY26-Q3"

    def test_apr_june_is_q4(self):
        assert _filing_date_to_fy_quarter("2026-04-15") == "FY26-Q4"
        assert _filing_date_to_fy_quarter("2026-06-30") == "FY26-Q4"

    def test_jul_sep_is_q1(self):
        assert _filing_date_to_fy_quarter("2026-07-20") == "FY27-Q1"
        assert _filing_date_to_fy_quarter("2026-09-30") == "FY27-Q1"

    def test_oct_dec_is_q2(self):
        assert _filing_date_to_fy_quarter("2026-10-15") == "FY27-Q2"
        assert _filing_date_to_fy_quarter("2026-12-31") == "FY27-Q2"

    def test_invalid_date_returns_unknown(self):
        assert _filing_date_to_fy_quarter("bad") == "unknown"
        assert _filing_date_to_fy_quarter("") == "unknown"


# -- Helper to build a CorporateFiling quickly --

def _make_filing(**overrides) -> CorporateFiling:
    """Construct a CorporateFiling with sensible defaults for download tests."""
    defaults = {
        "symbol": "INDIAMART",
        "bse_scrip_code": "542726",
        "filing_date": "2026-01-25",
        "category": "Result",
        "subcategory": "Analyst Meet - Intimation",
        "headline": "Concall transcript Q3",
        "attachment_name": "file.pdf",
        "pdf_flag": 0,
        "file_size": None,
        "news_id": "N1",
    }
    defaults.update(overrides)
    return CorporateFiling(**defaults)


# -- BSE response payloads for fetch mocks --

_BSE_FETCH_PAGE_1 = {
    "Table": [
        {
            "ATTACHMENTNAME": "file1.pdf",
            "NEWS_DT": "2026-01-25T10:00:00",
            "CATEGORYNAME": "Result",
            "SUBCATNAME": "Financial Results",
            "HEADLINE": "Q3 Results",
            "PDFFLAG": 0,
            "Fld_Attachsize": 1000,
            "NEWSID": "A1",
        },
    ],
    "Table1": [{"ROWCNT": 1}],
}

_BSE_FETCH_EMPTY = {"Table": [], "Table1": [{"ROWCNT": 0}]}

_BSE_FETCH_RESEARCH_MIXED = {
    "Table": [
        # research-relevant (Earnings Call Transcript)
        {
            "ATTACHMENTNAME": "concall.pdf",
            "NEWS_DT": "2026-01-28T10:00:00",
            "CATEGORYNAME": "Company Update",
            "SUBCATNAME": "Earnings Call Transcript",
            "HEADLINE": "Concall transcript",
            "PDFFLAG": 0,
        },
        # research-relevant (Result category)
        {
            "ATTACHMENTNAME": "result.pdf",
            "NEWS_DT": "2026-01-25T10:00:00",
            "CATEGORYNAME": "Result",
            "SUBCATNAME": "Financial Results",
            "HEADLINE": "Financial Results",
            "PDFFLAG": 0,
        },
        # research-relevant (keyword in headline)
        {
            "ATTACHMENTNAME": "inv.pdf",
            "NEWS_DT": "2026-01-20T10:00:00",
            "CATEGORYNAME": "Company Update",
            "SUBCATNAME": "Other",
            "HEADLINE": "Investor Presentation for analysts",
            "PDFFLAG": 0,
        },
        # NOT research-relevant
        {
            "ATTACHMENTNAME": "bm.pdf",
            "NEWS_DT": "2026-01-15T10:00:00",
            "CATEGORYNAME": "Board Meeting",
            "SUBCATNAME": "Board Meeting",
            "HEADLINE": "Board meeting notice",
            "PDFFLAG": 0,
        },
    ],
    "Table1": [{"ROWCNT": 4}],
}


# -- Tests for module-level parse helpers --

class TestParseBseDate:
    """Test _parse_bse_date helper."""

    def test_dotnet_json_date(self):
        # 1735084800000 ms = 2024-12-25 UTC (~); accept non-empty iso-style result
        result = _parse_bse_date("/Date(1735084800000)/")
        assert result is not None
        assert len(result) == 10  # YYYY-MM-DD

    def test_dd_mon_yyyy(self):
        assert _parse_bse_date("14 Aug 2025") == "2025-08-14"

    def test_dd_slash_mm_yyyy(self):
        assert _parse_bse_date("14/08/2025") == "2025-08-14"

    def test_dd_dash_mm_yyyy(self):
        assert _parse_bse_date("14-08-2025") == "2025-08-14"

    def test_iso_datetime(self):
        assert _parse_bse_date("2025-08-14T10:00:00") == "2025-08-14"

    def test_yyyy_mm_dd(self):
        assert _parse_bse_date("2025-08-14") == "2025-08-14"

    def test_empty_returns_none(self):
        assert _parse_bse_date("") is None
        assert _parse_bse_date(None) is None

    def test_whitespace_stripped(self):
        assert _parse_bse_date("  2025-08-14  ") == "2025-08-14"

    def test_garbage_returns_none(self):
        assert _parse_bse_date("not a date") is None


class TestParseBonusMultiplier:
    """Test _parse_bonus_multiplier helper."""

    def test_one_for_one(self):
        # 1:1 bonus -> holder has 2 shares for every 1 -> multiplier 2.0
        assert _parse_bonus_multiplier("1:1") == 2.0

    def test_two_for_one(self):
        # 2 new for 1 existing -> 3 shares total for every 1 -> 3.0
        assert _parse_bonus_multiplier("2:1") == 3.0

    def test_one_for_two(self):
        # 1 new for 2 existing -> 3 total for every 2 -> 1.5
        assert _parse_bonus_multiplier("1:2") == 1.5

    def test_spaced_ratio(self):
        assert _parse_bonus_multiplier("1 : 1") == 2.0

    def test_empty_returns_none(self):
        assert _parse_bonus_multiplier("") is None
        assert _parse_bonus_multiplier(None) is None

    def test_zero_existing_returns_none(self):
        assert _parse_bonus_multiplier("1:0") is None

    def test_no_ratio_returns_none(self):
        assert _parse_bonus_multiplier("Bonus Issue") is None


class TestParseSplitMultiplier:
    """Test _parse_split_multiplier helper."""

    def test_rupees_to_rupees(self):
        assert _parse_split_multiplier("from Rs.10/- to Rs.2/-") == 5.0

    def test_from_to(self):
        assert _parse_split_multiplier("From Rs 10 To Rs 5") == 2.0

    def test_missing_from_returns_none(self):
        """Regex requires 'from' before first amount."""
        assert _parse_split_multiplier("Rs.10/- to Rs.2/-") is None

    def test_rupee_symbol(self):
        assert _parse_split_multiplier("from ₹10 to ₹1") == 10.0

    def test_empty_returns_none(self):
        assert _parse_split_multiplier("") is None
        assert _parse_split_multiplier(None) is None

    def test_zero_new_face_returns_none(self):
        assert _parse_split_multiplier("from Rs 10 to Rs 0") is None

    def test_no_match_returns_none(self):
        assert _parse_split_multiplier("Stock Split") is None


class TestParseDividendAmount:
    """Test _parse_dividend_amount helper."""

    def test_rs_slash(self):
        assert _parse_dividend_amount("Rs. 10/- Per Share") == 10.0

    def test_rs_no_dot(self):
        assert _parse_dividend_amount("Rs 5 Per Share") == 5.0

    def test_rupee_symbol(self):
        assert _parse_dividend_amount("₹2.50 per share") == 2.50

    def test_plain_number(self):
        assert _parse_dividend_amount("5.50") == 5.50

    def test_empty_returns_none(self):
        assert _parse_dividend_amount("") is None
        assert _parse_dividend_amount(None) is None

    def test_garbage_returns_none(self):
        assert _parse_dividend_amount("dividend paid") is None


# -- BSE candidate matching --

class TestMatchBseCandidate:
    """Test FilingClient._match_bse_candidate company-name matching."""

    def test_high_overlap_wins(self):
        client = FilingClient()
        candidates = [
            ("111111", "Haldyn Glass Limited"),
            ("542726", "Hindustan Aeronautics Limited"),
        ]
        best = client._match_bse_candidate(candidates, "Hindustan Aeronautics", "HAL")
        assert best == "542726"
        client.close()

    def test_no_good_match_returns_none(self):
        client = FilingClient()
        candidates = [("111111", "Completely Unrelated Corp")]
        best = client._match_bse_candidate(candidates, "Hindustan Aeronautics", "HAL")
        assert best is None
        client.close()

    def test_empty_known_name_returns_none(self):
        client = FilingClient()
        candidates = [("111111", "Some Ltd")]
        best = client._match_bse_candidate(candidates, "", "SYM")
        assert best is None
        client.close()

    def test_stop_words_ignored(self):
        """Stop words like 'Ltd' shouldn't boost match score."""
        client = FilingClient()
        candidates = [
            ("111111", "The Ltd Limited"),
            ("222222", "State Bank of India Ltd"),
        ]
        best = client._match_bse_candidate(candidates, "State Bank of India", "SBIN")
        assert best == "222222"
        client.close()


# -- get_bse_code --

class TestGetBseCode:
    """Test FilingClient.get_bse_code HTTP + caching."""

    def test_cache_hit_skips_http(self):
        client = FilingClient()
        client._scrip_cache["INDIAMART"] = "542726"
        # Should return from cache — no HTTP needed
        assert client.get_bse_code("INDIAMART") == "542726"
        client.close()

    def test_single_candidate_returned(self):
        html = "liclick('542726','IndiaMART InterMESH Ltd')"
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/BseIndiaAPI/api/PeerSmartSearch").respond(
                200, text=html,
            )
            with FilingClient() as client:
                with patch.object(client, "_get_known_company_name", return_value=None):
                    code = client.get_bse_code("INDIAMART")
            assert code == "542726"

    def test_multiple_candidates_matched_by_name(self):
        html = (
            "liclick('111111','Haldyn Glass Ltd')"
            "liclick('542726','Hindustan Aeronautics Ltd')"
        )
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/BseIndiaAPI/api/PeerSmartSearch").respond(
                200, text=html,
            )
            with FilingClient() as client:
                with patch.object(
                    client, "_get_known_company_name",
                    return_value="Hindustan Aeronautics Limited",
                ):
                    code = client.get_bse_code("HAL")
            assert code == "542726"

    def test_no_candidates_returns_none(self):
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/BseIndiaAPI/api/PeerSmartSearch").respond(
                200, text="<html>no results</html>",
            )
            with FilingClient() as client:
                code = client.get_bse_code("UNKNOWN")
            assert code is None

    def test_http_error_returns_none(self):
        with respx.mock:
            respx.get(url__regex=r"bseindia\.com/BseIndiaAPI/api/PeerSmartSearch").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            with FilingClient() as client:
                # Reduce retries for speed: monkey-patch _request_with_retry to fail fast
                with patch("time.sleep"):
                    code = client.get_bse_code("BADSYM")
            assert code is None


# -- fetch_filings (with mocked HTTP) --

class TestFetchFilings:
    """Test FilingClient.fetch_filings pagination + filtering."""

    def test_returns_empty_when_no_bse_code(self):
        with FilingClient() as client:
            with patch.object(client, "get_bse_code", return_value=None):
                filings = client.fetch_filings("NONEXISTENT")
        assert filings == []

    def test_single_page_fetch(self):
        with respx.mock:
            respx.get(url__regex=r"AnnSubCategoryGetData").respond(
                200, json=_BSE_FETCH_PAGE_1,
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    with patch("time.sleep"):
                        filings = client.fetch_filings(
                            "INDIAMART",
                            from_date=date(2026, 1, 1),
                            to_date=date(2026, 3, 31),
                        )
            assert len(filings) == 1
            assert filings[0].symbol == "INDIAMART"
            assert filings[0].headline == "Q3 Results"

    def test_empty_table_ends_pagination(self):
        with respx.mock:
            respx.get(url__regex=r"AnnSubCategoryGetData").respond(
                200, json=_BSE_FETCH_EMPTY,
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    filings = client.fetch_filings("INDIAMART")
            assert filings == []

    def test_uses_default_dates_when_none(self):
        """When from_date/to_date are None, defaults are used (today and 3y back)."""
        with respx.mock:
            route = respx.get(url__regex=r"AnnSubCategoryGetData").respond(
                200, json=_BSE_FETCH_EMPTY,
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    client.fetch_filings("INDIAMART")
            assert route.called

    def test_http_failure_breaks_pagination_gracefully(self):
        """When an HTTP error happens mid-pagination, we return what we have."""
        with respx.mock:
            respx.get(url__regex=r"AnnSubCategoryGetData").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    with patch("time.sleep"):
                        filings = client.fetch_filings("INDIAMART")
            assert filings == []


class TestFetchResearchFilings:
    """Test FilingClient.fetch_research_filings filtering."""

    def test_filters_to_research_only(self):
        with respx.mock:
            respx.get(url__regex=r"AnnSubCategoryGetData").respond(
                200, json=_BSE_FETCH_RESEARCH_MIXED,
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    with patch("time.sleep"):
                        filings = client.fetch_research_filings("INDIAMART")
            # 3 research-relevant, 1 board-meeting filtered out
            assert len(filings) == 3
            headlines = {f.headline for f in filings}
            assert "Board meeting notice" not in headlines


class TestFetchAnnualReports:
    """Test FilingClient.fetch_annual_reports (NSE)."""

    def test_parses_nse_annual_reports(self):
        nse_data = {
            "data": [
                {
                    "fromYr": "2024",
                    "toYr": "2025",
                    "fileName": "https://example.com/ar.pdf",
                    "companyName": "Test Ltd",
                },
                {
                    "fromYr": "2023",
                    "toYr": "2024",
                    "fileName": "https://example.com/ar2.pdf",
                    "companyName": "Test Ltd",
                },
            ],
        }
        with respx.mock:
            respx.get("https://www.nseindia.com/").respond(200, text="ok")
            respx.get(url__regex=r"nseindia\.com/api/annual-reports").respond(
                200, json=nse_data,
            )
            with FilingClient() as client:
                with patch("time.sleep"):
                    reports = client.fetch_annual_reports("TEST")
        assert len(reports) == 2
        assert reports[0]["from_year"] == "2024"
        assert reports[0]["url"] == "https://example.com/ar.pdf"
        assert reports[0]["company_name"] == "Test Ltd"

    def test_nse_error_returns_empty(self):
        with respx.mock:
            respx.get("https://www.nseindia.com/").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            with FilingClient() as client:
                reports = client.fetch_annual_reports("TEST")
        assert reports == []


# -- Download tests --

class TestDownloadFiling:
    """Test FilingClient.download_filing with tmp_path."""

    def test_download_concall_classifies_type(self, tmp_path: Path):
        filing = _make_filing(
            headline="Transcript of Earnings Call",
            subcategory="Earnings Call Transcript",
            attachment_name="concall.pdf",
            filing_date="2026-01-25",
        )
        content = b"%PDF-1.4" + b"x" * 1000
        with respx.mock:
            respx.get(url__regex=r"AttachLive/concall\.pdf").respond(
                200, content=content,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is not None
        assert result.name == "concall.pdf"
        assert "FY26-Q3" in str(result)
        assert result.read_bytes() == content

    def test_download_investor_presentation(self, tmp_path: Path):
        filing = _make_filing(
            headline="Investor presentation Q3",
            subcategory="Investor Presentation",
            attachment_name="deck.pdf",
        )
        with respx.mock:
            respx.get(url__regex=r"AttachLive/deck\.pdf").respond(
                200, content=b"%PDF" + b"y" * 500,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is not None
        assert result.name == "investor_deck.pdf"

    def test_download_financial_results_skipped(self, tmp_path: Path):
        """Financial results are not consumed by the research pipeline — skipped."""
        filing = _make_filing(
            headline="Financial Results Q3",
            subcategory="Financial Results",
            attachment_name="results.pdf",
        )
        with FilingClient() as client:
            result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_download_annual_report(self, tmp_path: Path):
        filing = _make_filing(
            headline="Annual Report 2025",
            subcategory="General",
            attachment_name="ar.pdf",
        )
        with respx.mock:
            respx.get(url__regex=r"AttachLive/ar\.pdf").respond(
                200, content=b"%PDF" + b"a" * 500,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is not None
        assert result.name == "annual_report.pdf"

    def test_download_unknown_type_is_skipped(self, tmp_path: Path):
        """Unknown filing types (not concall / investor_deck / annual_report) are skipped."""
        filing = _make_filing(
            headline="Some random filing",
            subcategory="Board Meeting",
            attachment_name="bm.pdf",
        )
        with FilingClient() as client:
            result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_download_pdf_flag_one_uses_attach_his(self, tmp_path: Path):
        filing = _make_filing(attachment_name="hist.pdf", pdf_flag=1)
        with respx.mock:
            route = respx.get(url__regex=r"AttachHis/hist\.pdf").respond(
                200, content=b"%PDF" + b"h" * 500,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is not None
        assert route.called

    def test_download_404_returns_none_no_retry(self, tmp_path: Path):
        filing = _make_filing(attachment_name="gone.pdf")
        with respx.mock:
            route = respx.get(url__regex=r"AttachLive/gone\.pdf").respond(404)
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None
        # 404 is terminal — should only be called once
        assert route.call_count == 1

    def test_download_500_retries_then_gives_up(self, tmp_path: Path):
        filing = _make_filing(attachment_name="err.pdf")
        with respx.mock:
            route = respx.get(url__regex=r"AttachLive/err\.pdf").respond(500)
            with FilingClient() as client:
                with patch("time.sleep"):
                    result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None
        # 3 attempts: initial + 2 retries
        assert route.call_count == 3

    def test_download_exception_retries_then_returns_none(self, tmp_path: Path):
        filing = _make_filing(attachment_name="boom.pdf")
        with respx.mock:
            respx.get(url__regex=r"AttachLive/boom\.pdf").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            with FilingClient() as client:
                with patch("time.sleep"):
                    result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_download_empty_content_returns_none(self, tmp_path: Path):
        """If response is 200 but <100 bytes, treat as failure."""
        filing = _make_filing(attachment_name="tiny.pdf")
        with respx.mock:
            respx.get(url__regex=r"AttachLive/tiny\.pdf").respond(
                200, content=b"tiny",
            )
            with FilingClient() as client:
                with patch("time.sleep"):
                    result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_download_skips_when_file_already_exists(self, tmp_path: Path):
        """If the canonical file already exists, return it without re-downloading."""
        filing = _make_filing(
            headline="Concall transcript Q3",
            subcategory="Analyst Meet - Intimation",
            attachment_name="cached.pdf",
            filing_date="2026-01-25",
            file_size=2000,
        )
        target_dir = tmp_path / "INDIAMART" / "filings" / "FY26-Q3"
        target_dir.mkdir(parents=True)
        target = target_dir / "concall.pdf"
        target.write_bytes(b"x" * 2000)  # > 1KB to pass size sanity check

        with respx.mock:
            # No HTTP call should be made
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result == target

    def test_existing_fresh_file_returned_without_download(self, tmp_path: Path):
        """Fresh (mtime < 30 days), non-corrupt (size > 1KB) → returns cached path, no HTTP."""
        filing = _make_filing(
            headline="Concall transcript Q3",
            subcategory="Earnings Call Transcript",
            attachment_name="fresh.pdf",
            filing_date="2026-01-25",
        )
        target_dir = tmp_path / "INDIAMART" / "filings" / "FY26-Q3"
        target_dir.mkdir(parents=True)
        target = target_dir / "concall.pdf"
        target.write_bytes(b"%PDF" + b"x" * 2000)  # > 1KB

        with respx.mock:
            # No routes defined — any HTTP call would raise
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result == target

    def test_existing_stale_file_warns_but_reuses(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ):
        """Stale (mtime > 30 days) → return cached path + WARNING logged."""
        import os
        import time as _time

        filing = _make_filing(
            headline="Concall transcript Q3",
            subcategory="Earnings Call Transcript",
            attachment_name="stale.pdf",
            filing_date="2026-01-25",
        )
        target_dir = tmp_path / "INDIAMART" / "filings" / "FY26-Q3"
        target_dir.mkdir(parents=True)
        target = target_dir / "concall.pdf"
        target.write_bytes(b"%PDF" + b"x" * 2000)
        # Backdate mtime to 45 days ago
        old_ts = _time.time() - (45 * 86400)
        os.utime(target, (old_ts, old_ts))

        with respx.mock:
            with caplog.at_level("WARNING", logger="flowtracker.filing_client"):
                with FilingClient() as client:
                    result = client.download_filing(filing, base_dir=tmp_path)
        assert result == target
        assert any("stale" in r.message.lower() for r in caplog.records)

    def test_force_refresh_bypasses_cache(self, tmp_path: Path):
        """force_refresh=True → HTTP call made even with fresh cache."""
        filing = _make_filing(
            headline="Concall transcript Q3",
            subcategory="Earnings Call Transcript",
            attachment_name="refresh.pdf",
            filing_date="2026-01-25",
        )
        target_dir = tmp_path / "INDIAMART" / "filings" / "FY26-Q3"
        target_dir.mkdir(parents=True)
        target = target_dir / "concall.pdf"
        target.write_bytes(b"%PDF" + b"old" * 1000)

        new_content = b"%PDF" + b"new" * 1000
        with respx.mock:
            route = respx.get(url__regex=r"AttachLive/refresh\.pdf").respond(
                200, content=new_content,
            )
            with FilingClient() as client:
                result = client.download_filing(
                    filing, base_dir=tmp_path, force_refresh=True,
                )
        assert result == target
        assert route.called
        assert target.read_bytes() == new_content

    def test_corrupt_small_file_triggers_redownload(self, tmp_path: Path):
        """Existing file < 1KB → treat as cache miss and re-download."""
        filing = _make_filing(
            headline="Concall transcript Q3",
            subcategory="Earnings Call Transcript",
            attachment_name="small.pdf",
            filing_date="2026-01-25",
        )
        target_dir = tmp_path / "INDIAMART" / "filings" / "FY26-Q3"
        target_dir.mkdir(parents=True)
        target = target_dir / "concall.pdf"
        target.write_bytes(b"tinycorrupt")  # < 1024 bytes

        new_content = b"%PDF" + b"full" * 500
        with respx.mock:
            route = respx.get(url__regex=r"AttachLive/small\.pdf").respond(
                200, content=new_content,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result == target
        assert route.called
        assert target.read_bytes() == new_content


class TestDisclosureCoverLetterGuard:
    """Regression guards for the 2026-04-24 filing-fetch audit — Reg 30
    "audio recording of earnings call" cover letters were being filed under
    "Analyst / Investor Meet" with "EARNINGS CALL: ..." headlines and
    classified as concalls. Audit found 570/5378 concall.pdf files were
    cover letters across 31 always-broken symbols (AXISBANK, ADANIENT,
    JSWSTEEL, ABCAPITAL, LICHSGFIN, ...).
    """

    def test_audio_recording_headline_is_skipped(self, tmp_path: Path):
        """Reg 30 cover letter ("AUDIO RECORDING of earnings call...") must
        not be downloaded as a concall — headline contains the disclosure
        marker 'audio recording' which indicates the filing is announcing
        a call, not containing one."""
        filing = _make_filing(
            symbol="AXISBANK",
            bse_scrip_code="532215",
            headline=(
                "AUDIO RECORDING OF EARNINGS CALL OF AXIS BANK LIMITED "
                "FOR THE QUARTER AND HALF YEAR ENDED SEPTEMBER 30, 2025"
            ),
            subcategory="Analyst / Investor Meet",
            filing_date="2025-10-15",
            attachment_name="axis_cover.pdf",
        )
        with FilingClient() as client:
            # No respx stub — if the classifier returned "concall" and tried
            # to download, respx-less call would raise. Disclosure marker
            # should short-circuit before any network call.
            result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_schedule_of_analyst_meet_is_skipped(self, tmp_path: Path):
        """'Schedule of analysts/institutional investors meet' is a calendar
        intimation — not a transcript and not a presentation."""
        filing = _make_filing(
            headline="Schedule of analysts/institutional investors meet",
            subcategory="Analyst / Investor Meet",
            attachment_name="sched.pdf",
        )
        with FilingClient() as client:
            result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_intimation_of_board_meeting_is_skipped(self, tmp_path: Path):
        filing = _make_filing(
            headline="Intimation of Board Meeting — Audited results",
            subcategory="Board Meeting",
            attachment_name="bm.pdf",
        )
        with FilingClient() as client:
            result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_earnings_without_transcript_keyword_is_skipped(self, tmp_path: Path):
        """Old classifier accepted any 'earnings' + 'Analyst' subcategory
        as concall. New rule: explicit 'transcript' or 'concall' required.
        This test pins the tightening.
        """
        filing = _make_filing(
            headline="EARNINGS CALL: AUDITED FINANCIAL RESULTS OF THE BANK",
            subcategory="Analyst / Investor Meet",
            attachment_name="call.pdf",
        )
        with FilingClient() as client:
            result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None

    def test_transcript_keyword_still_classifies_as_concall(self, tmp_path: Path):
        """Sanity: the tightening must NOT regress real transcript filings."""
        filing = _make_filing(
            headline="Transcript of Earnings Call — Q3 FY26",
            subcategory="Earnings Call Transcript",
            attachment_name="transcript.pdf",
            filing_date="2026-01-25",
        )
        with respx.mock:
            respx.get(url__regex=r"AttachLive/transcript\.pdf").respond(
                200, content=b"%PDF-1.4" + b"x" * 2000,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        # Sanity filter will call _looks_like_real_transcript on a fake PDF;
        # pypdfium2 fails to parse junk bytes → helper returns True (accept).
        assert result is not None
        assert result.name == "concall.pdf"


class TestTranscriptSanityFilter:
    """Post-download sanity check — concall PDFs that look like cover letters
    (≤3 pages, <3000 chars, contain 'audio recording' / 'transcript is
    available' markers in body) must be rejected and deleted.
    """

    def test_cover_letter_pdf_is_rejected(self, tmp_path: Path, monkeypatch):
        """If _looks_like_real_transcript returns False, the file must be
        deleted and download_filing returns None."""
        from flowtracker import filing_client as fc_mod

        monkeypatch.setattr(fc_mod, "_looks_like_real_transcript", lambda p: False)

        filing = _make_filing(
            headline="Transcript of Earnings Call",
            subcategory="Earnings Call Transcript",
            attachment_name="cover_looking.pdf",
            filing_date="2026-01-25",
        )
        with respx.mock:
            respx.get(url__regex=r"AttachLive/cover_looking\.pdf").respond(
                200, content=b"%PDF-1.4 cover letter content here" * 10,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is None
        # File must be cleaned up (no zombie cover-letter in vault)
        expected_path = tmp_path / "INDIAMART" / "filings" / "FY26-Q3" / "concall.pdf"
        assert not expected_path.exists()

    def test_real_transcript_pdf_is_kept(self, tmp_path: Path, monkeypatch):
        from flowtracker import filing_client as fc_mod

        monkeypatch.setattr(fc_mod, "_looks_like_real_transcript", lambda p: True)

        filing = _make_filing(
            headline="Transcript of Earnings Call",
            subcategory="Earnings Call Transcript",
            attachment_name="real.pdf",
            filing_date="2026-01-25",
        )
        with respx.mock:
            respx.get(url__regex=r"AttachLive/real\.pdf").respond(
                200, content=b"%PDF-1.4 real transcript" * 100,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is not None
        assert result.exists()

    def test_sanity_filter_does_not_apply_to_investor_deck(self, tmp_path: Path, monkeypatch):
        """The sanity check is concall-specific — a 1-page deck must still
        be accepted (some decks are 1-2 summary pages)."""
        from flowtracker import filing_client as fc_mod

        called_for_deck = False
        def _spy(path):
            nonlocal called_for_deck
            called_for_deck = True
            return False
        monkeypatch.setattr(fc_mod, "_looks_like_real_transcript", _spy)

        filing = _make_filing(
            headline="Investor Presentation Q3",
            subcategory="Investor Presentation",
            attachment_name="deck.pdf",
        )
        with respx.mock:
            respx.get(url__regex=r"AttachLive/deck\.pdf").respond(
                200, content=b"%PDF" + b"y" * 500,
            )
            with FilingClient() as client:
                result = client.download_filing(filing, base_dir=tmp_path)
        assert result is not None
        assert called_for_deck is False


class TestLooksLikeRealTranscript:
    """Unit tests for the content-based sanity helper itself."""

    def test_missing_file_accepts(self, tmp_path: Path):
        """Helper must never hard-fail on missing file — if we can't check,
        we accept (caller keeps the PDF)."""
        from flowtracker.filing_client import _looks_like_real_transcript
        assert _looks_like_real_transcript(tmp_path / "does_not_exist.pdf") is True

    def test_corrupt_pdf_accepts(self, tmp_path: Path):
        """Unparseable bytes → accept (err on side of keeping)."""
        from flowtracker.filing_client import _looks_like_real_transcript
        p = tmp_path / "bad.pdf"
        p.write_bytes(b"not a pdf at all")
        assert _looks_like_real_transcript(p) is True


class TestDownloadUrl:
    """Test FilingClient.download_url for direct URL downloads (NSE annual reports)."""

    def test_download_ok(self, tmp_path: Path):
        with respx.mock:
            respx.get("https://example.com/ar.pdf").respond(
                200, content=b"%PDF" + b"x" * 500,
            )
            with FilingClient() as client:
                result = client.download_url(
                    "https://example.com/ar.pdf",
                    "TEST", "annual", "ar_2024_2025.pdf",
                    base_dir=tmp_path,
                )
        assert result is not None
        assert result.name == "ar_2024_2025.pdf"
        assert "annual" in str(result)

    def test_existing_file_skipped(self, tmp_path: Path):
        """Pre-existing non-empty file short-circuits download."""
        target_dir = tmp_path / "TEST" / "filings" / "annual"
        target_dir.mkdir(parents=True)
        target = target_dir / "existing.pdf"
        target.write_bytes(b"existing data")

        with FilingClient() as client:
            # No respx — would raise if HTTP actually attempted
            result = client.download_url(
                "https://example.com/never-called.pdf",
                "TEST", "annual", "existing.pdf",
                base_dir=tmp_path,
            )
        assert result == target

    def test_404_returns_none(self, tmp_path: Path):
        with respx.mock:
            respx.get("https://example.com/missing.pdf").respond(404)
            with FilingClient() as client:
                result = client.download_url(
                    "https://example.com/missing.pdf",
                    "TEST", "annual", "missing.pdf",
                    base_dir=tmp_path,
                )
        assert result is None

    def test_exception_returns_none(self, tmp_path: Path):
        with respx.mock:
            respx.get("https://example.com/boom.pdf").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            with FilingClient() as client:
                result = client.download_url(
                    "https://example.com/boom.pdf",
                    "TEST", "annual", "boom.pdf",
                    base_dir=tmp_path,
                )
        assert result is None


# -- Corporate actions --

_BSE_CORP_ACTIONS = {
    "Table1": [
        # Bonus
        {"BCRD_FROM": "2025-06-15T00:00:00", "VALUE": "1:1"},
    ],
    "Table2": [
        # Stock split
        {
            "purpose_code": "SS",
            "Ex_date": "2024-09-10T00:00:00",
            "Details": "From Rs.10/- to Rs.2/-",
        },
        # Spinoff
        {
            "purpose_code": "SO",
            "Ex_date": "2023-05-20T00:00:00",
            "Details": "Demerger of business",
        },
        # Buyback
        {
            "purpose_code": "BGM",
            "Ex_date": "2022-12-01T00:00:00",
            "Details": "Tender offer @ Rs.500",
        },
        # Dividend
        {
            "purpose_code": "DP",
            "Ex_date": "2024-07-15T00:00:00",
            "Details": "Rs.10/- Per Share",
        },
        # No ex_date — should be skipped
        {
            "purpose_code": "DP",
            "Ex_date": "",
            "Details": "Rs.5/- Per Share",
        },
        # Unknown purpose_code — ignored
        {
            "purpose_code": "XX",
            "Ex_date": "2024-01-01T00:00:00",
            "Details": "unknown",
        },
    ],
}


class TestFetchCorporateActions:
    """Test FilingClient.fetch_corporate_actions BSE parsing."""

    def test_returns_empty_when_no_bse_code(self):
        with FilingClient() as client:
            with patch.object(client, "get_bse_code", return_value=None):
                actions = client.fetch_corporate_actions("NONE")
        assert actions == []

    def test_parses_all_action_types(self):
        with respx.mock:
            respx.get(url__regex=r"CorporateAction/w").respond(
                200, json=_BSE_CORP_ACTIONS,
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    actions = client.fetch_corporate_actions("indiamart")

        types = {a["action_type"] for a in actions}
        assert "bonus" in types
        assert "split" in types
        assert "spinoff" in types
        assert "buyback" in types
        assert "dividend" in types

        # Bonus multiplier computed
        bonus = next(a for a in actions if a["action_type"] == "bonus")
        assert bonus["multiplier"] == 2.0
        assert bonus["symbol"] == "INDIAMART"  # uppercased
        assert bonus["source"] == "bse"

        # Split multiplier computed
        split = next(a for a in actions if a["action_type"] == "split")
        assert split["multiplier"] == 5.0

        # Dividend amount parsed
        div = next(a for a in actions if a["action_type"] == "dividend")
        assert div["dividend_amount"] == 10.0

    def test_deduplicates_by_symbol_date_type(self):
        """Bonus appearing in both Table1 and Table2 should dedupe."""
        payload = {
            "Table1": [{"BCRD_FROM": "2025-06-15T00:00:00", "VALUE": "1:1"}],
            "Table2": [
                # Would dedupe... but Table2 bonuses aren't parsed at all — only Table1.
                # Add a second bonus same-date to Table1 structure via a 2nd entry
                # that mirrors the first.
            ],
        }
        payload["Table1"].append({"BCRD_FROM": "2025-06-15T00:00:00", "VALUE": "1:1"})
        with respx.mock:
            respx.get(url__regex=r"CorporateAction/w").respond(200, json=payload)
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    actions = client.fetch_corporate_actions("TEST")
        # 2 identical bonus rows -> dedupes to 1
        assert len(actions) == 1

    def test_http_error_returns_empty(self):
        with respx.mock:
            respx.get(url__regex=r"CorporateAction/w").mock(
                side_effect=httpx.ConnectError("boom"),
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    with patch("time.sleep"):
                        actions = client.fetch_corporate_actions("TEST")
        assert actions == []

    def test_empty_tables_returns_empty(self):
        with respx.mock:
            respx.get(url__regex=r"CorporateAction/w").respond(
                200, json={"Table1": [], "Table2": []},
            )
            with FilingClient() as client:
                with patch.object(client, "get_bse_code", return_value="542726"):
                    actions = client.fetch_corporate_actions("TEST")
        assert actions == []


# -- Context manager --

class TestContextManager:
    """Test FilingClient context manager protocol."""

    def test_enter_returns_self(self):
        client = FilingClient()
        assert client.__enter__() is client
        client.close()

    def test_exit_closes_client(self):
        client = FilingClient()
        client.__exit__(None, None, None)
        # After close, httpx.Client is closed
        assert client._client.is_closed

    def test_with_statement(self):
        with FilingClient() as client:
            assert client is not None
        assert client._client.is_closed


# -- Retry logic --

class TestRequestWithRetry:
    """Test FilingClient._request_with_retry backoff behavior."""

    def test_success_first_attempt(self):
        with respx.mock:
            respx.get("https://example.com/ok").respond(200, text="ok")
            with FilingClient() as client:
                resp = client._request_with_retry("GET", "https://example.com/ok")
        assert resp.status_code == 200

    def test_transient_then_success(self):
        """Fail first, succeed second."""
        with respx.mock:
            route = respx.get("https://example.com/flaky")
            route.side_effect = [
                httpx.Response(500),
                httpx.Response(200, text="ok"),
            ]
            with FilingClient() as client:
                with patch("time.sleep"):
                    resp = client._request_with_retry(
                        "GET", "https://example.com/flaky", max_retries=2,
                    )
        assert resp.status_code == 200
        assert route.call_count == 2

    def test_exhausts_retries_raises(self):
        with respx.mock:
            respx.get("https://example.com/dead").respond(500)
            with FilingClient() as client:
                with patch("time.sleep"):
                    with pytest.raises(httpx.HTTPStatusError):
                        client._request_with_retry(
                            "GET", "https://example.com/dead", max_retries=2,
                        )


# -- yfinance corporate actions --

class _FakeTicker:
    """Stand-in for yfinance.Ticker used in tests."""
    def __init__(self, splits=None, dividends=None):
        self.splits = splits
        self.dividends = dividends


class _DateIdx:
    """Stand-in for pandas DatetimeIndex entries (has strftime)."""
    def __init__(self, s: str):
        self._s = s

    def strftime(self, fmt: str) -> str:
        # Only used with "%Y-%m-%d" — return stored value verbatim
        return self._s


class _Series:
    """Minimal stand-in for pandas Series — supports len() and .items()."""
    def __init__(self, pairs: list[tuple[_DateIdx, float]]):
        self._pairs = pairs

    def __len__(self) -> int:
        return len(self._pairs)

    def items(self):
        return iter(self._pairs)


class TestFetchYfinanceCorporateActions:
    """Test FilingClient.fetch_yfinance_corporate_actions with mocked yfinance."""

    def test_parses_splits_and_dividends(self):
        fake_ticker = _FakeTicker(
            splits=_Series([
                (_DateIdx("2024-09-10"), 5.0),   # meaningful split
                (_DateIdx("2024-01-01"), 1.0),   # ignored (no change)
                (_DateIdx("2023-01-01"), 0),     # ignored
            ]),
            dividends=_Series([
                (_DateIdx("2024-07-15"), 10.0),
                (_DateIdx("2024-03-15"), 0),     # ignored
            ]),
        )
        import yfinance as yf
        with patch.object(yf, "Ticker", return_value=fake_ticker):
            with FilingClient() as client:
                actions = client.fetch_yfinance_corporate_actions("indiamart")

        types = {a["action_type"] for a in actions}
        assert "split" in types
        assert "dividend" in types
        # Only 1 split (1.0 and 0 filtered) + 1 dividend (0 filtered)
        assert len(actions) == 2
        split = next(a for a in actions if a["action_type"] == "split")
        assert split["multiplier"] == 5.0
        assert split["symbol"] == "INDIAMART"
        assert split["source"] == "yfinance"
        div = next(a for a in actions if a["action_type"] == "dividend")
        assert div["dividend_amount"] == 10.0

    def test_empty_splits_and_dividends(self):
        fake_ticker = _FakeTicker(splits=_Series([]), dividends=_Series([]))
        import yfinance as yf
        with patch.object(yf, "Ticker", return_value=fake_ticker):
            with FilingClient() as client:
                actions = client.fetch_yfinance_corporate_actions("TEST")
        assert actions == []

    def test_none_splits_and_dividends(self):
        fake_ticker = _FakeTicker(splits=None, dividends=None)
        import yfinance as yf
        with patch.object(yf, "Ticker", return_value=fake_ticker):
            with FilingClient() as client:
                actions = client.fetch_yfinance_corporate_actions("TEST")
        assert actions == []

    def test_exception_returns_empty(self):
        import yfinance as yf
        with patch.object(yf, "Ticker", side_effect=RuntimeError("network down")):
            with FilingClient() as client:
                actions = client.fetch_yfinance_corporate_actions("TEST")
        assert actions == []


# -- _get_known_company_name --

class TestGetKnownCompanyName:
    """Test FilingClient._get_known_company_name DB lookup."""

    def test_returns_name_from_store(self, tmp_db):
        """When index_constituents has a matching symbol, returns company_name."""
        from flowtracker.store import FlowStore
        s = FlowStore(db_path=tmp_db)
        s._conn.execute(
            "INSERT OR REPLACE INTO index_constituents (symbol, company_name, index_name) "
            "VALUES (?, ?, ?)",
            ("SBIN", "State Bank of India", "NIFTY50"),
        )
        s._conn.commit()
        s.close()

        # Patch FlowStore() constructor inside the method to use our tmp_db
        with patch("flowtracker.store.FlowStore") as mock_store_cls:
            mock_store_cls.return_value.__enter__.return_value = FlowStore(db_path=tmp_db)
            mock_store_cls.return_value.__exit__.return_value = None
            with FilingClient() as client:
                name = client._get_known_company_name("SBIN")
        assert name == "State Bank of India"

    def test_returns_none_when_symbol_missing(self, tmp_db):
        from flowtracker.store import FlowStore
        s = FlowStore(db_path=tmp_db)
        s.close()

        with patch("flowtracker.store.FlowStore") as mock_store_cls:
            mock_store_cls.return_value.__enter__.return_value = FlowStore(db_path=tmp_db)
            mock_store_cls.return_value.__exit__.return_value = None
            with FilingClient() as client:
                name = client._get_known_company_name("NONEXISTENT")
        assert name is None

    def test_exception_returns_none(self):
        """When FlowStore raises (e.g., table missing), method returns None quietly."""
        with patch("flowtracker.store.FlowStore", side_effect=RuntimeError("db error")):
            with FilingClient() as client:
                name = client._get_known_company_name("ANY")
        assert name is None
