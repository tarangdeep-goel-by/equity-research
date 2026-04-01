"""Tests for filing_client.py — BSE corporate filing parsing."""

from __future__ import annotations

from flowtracker.filing_client import FilingClient, _safe_dirname, _filing_date_to_fy_quarter


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
