"""Tests for corporate_filings, screener_ids, company_profiles, and company_documents store methods."""

from __future__ import annotations

from flowtracker.store import FlowStore
from tests.fixtures.factories import make_filings


# -- corporate_filings --


def test_upsert_and_get_filings(store: FlowStore):
    """Upsert filings and retrieve by symbol."""
    filings = make_filings("SBIN")
    count = store.upsert_filings(filings)
    assert count >= 2

    result = store.get_filings("SBIN")
    assert len(result) == 2
    # Ordered by filing_date DESC
    assert result[0].filing_date >= result[1].filing_date
    assert result[0].symbol == "SBIN"


def test_get_filings_with_category_filter(store: FlowStore):
    """Category filter matches on category or subcategory via LIKE."""
    store.upsert_filings(make_filings("SBIN"))

    # Filter by "Result" should match the first filing (category="Result")
    result = store.get_filings("SBIN", category="Result")
    assert len(result) >= 1
    assert any("Result" in f.category for f in result)

    # Filter by "Investor" should match subcategory="Investor Presentation"
    result2 = store.get_filings("SBIN", category="Investor")
    assert len(result2) >= 1


def test_get_filings_empty_db(store: FlowStore):
    """Returns empty list when no filings exist for symbol."""
    assert store.get_filings("UNKNOWN") == []


def test_update_filing_path(store: FlowStore):
    """update_filing_path sets the local_path column."""
    store.upsert_filings(make_filings("SBIN"))

    store.update_filing_path("20260315001", "/tmp/Q3_results.pdf")

    result = store.get_filings("SBIN")
    matching = [f for f in result if f.news_id == "20260315001"]
    assert len(matching) == 1
    assert matching[0].local_path == "/tmp/Q3_results.pdf"


# -- screener_ids --


def test_upsert_and_get_screener_ids(store: FlowStore):
    """Round-trip screener IDs for a symbol."""
    store.upsert_screener_ids("SBIN", "12345", "67890")

    result = store.get_screener_ids("SBIN")
    assert result is not None
    assert result == ("12345", "67890")


def test_get_screener_ids_unknown_symbol(store: FlowStore):
    """Returns None for a symbol that doesn't exist."""
    assert store.get_screener_ids("UNKNOWN") is None


def test_upsert_screener_ids_update(store: FlowStore):
    """Upserting same symbol with new IDs overwrites."""
    store.upsert_screener_ids("SBIN", "12345", "67890")
    store.upsert_screener_ids("SBIN", "99999", "88888")

    result = store.get_screener_ids("SBIN")
    assert result == ("99999", "88888")


# -- company_profiles --


def test_upsert_and_get_company_profile(store: FlowStore):
    """Round-trip company profile with JSON key_points."""
    data = {
        "about_text": "SBI is a public sector bank.",
        "key_points": ["Largest PSU bank", "57.5% govt holding"],
        "screener_url": "https://screener.in/company/SBIN/",
    }
    store.upsert_company_profile("SBIN", data)

    result = store.get_company_profile("SBIN")
    assert result is not None
    assert result["about_text"] == "SBI is a public sector bank."
    assert result["screener_url"] == "https://screener.in/company/SBIN/"
    assert isinstance(result["key_points"], list)
    assert len(result["key_points"]) == 2
    assert "Largest PSU bank" in result["key_points"]


def test_get_company_profile_unknown_symbol(store: FlowStore):
    """Returns None for a symbol that doesn't exist."""
    assert store.get_company_profile("UNKNOWN") is None


# -- company_documents --


def test_upsert_and_get_documents(store: FlowStore):
    """Round-trip company documents with annual reports and concalls."""
    docs = {
        "annual_reports": [
            {"year": "FY26", "url": "https://example.com/ar26.pdf"},
            {"year": "FY25", "url": "https://example.com/ar25.pdf"},
        ],
        "concalls": [
            {
                "quarter": "Q3 FY26",
                "transcript_url": "https://example.com/transcript.pdf",
                "ppt_url": "https://example.com/ppt.pdf",
                "recording_url": "",
            },
        ],
    }
    count = store.upsert_documents("SBIN", docs)
    assert count >= 3  # 2 annual reports + 1 transcript + 1 ppt (no recording since empty)

    # Get all documents
    result = store.get_documents("SBIN")
    assert len(result) >= 3


def test_get_documents_with_doc_type_filter(store: FlowStore):
    """Filter documents by doc_type."""
    docs = {
        "annual_reports": [
            {"year": "FY26", "url": "https://example.com/ar26.pdf"},
        ],
        "concalls": [
            {
                "quarter": "Q3 FY26",
                "transcript_url": "https://example.com/transcript.pdf",
                "ppt_url": "",
                "recording_url": "",
            },
        ],
    }
    store.upsert_documents("SBIN", docs)

    ar_result = store.get_documents("SBIN", doc_type="annual_report")
    assert len(ar_result) >= 1
    assert all(d["doc_type"] == "annual_report" for d in ar_result)

    transcript_result = store.get_documents("SBIN", doc_type="concall_transcript")
    assert len(transcript_result) >= 1


def test_get_documents_empty_db(store: FlowStore):
    """Returns empty list when no documents exist for symbol."""
    assert store.get_documents("UNKNOWN") == []
