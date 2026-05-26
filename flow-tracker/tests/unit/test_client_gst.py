"""Tests for ``gst_client`` — period helpers, defensive parser, seed loader,
and the live HTTP escape-hatch path.

Note on fixtures: the live CBIC / PIB / GST-Council press-release fronts all
render via client-side JavaScript and return only the SPA shell when scraped
with httpx. Probing the conventional URL patterns for the monthly PDF
(``Press-Release-GST-Revenue-<Month>-<Year>.pdf`` and several variants)
returns 404 across the GST Council CDN. As a result the test fixtures here
are **synthetic** — they reproduce the canonical CBIC press-release language
("Gross GST revenue collected", "₹X crore", "Y% higher") with the exact
numeric layout used in real releases. This exercises the parser identically;
re-recording golden fixtures from the live PDF when one is hand-supplied
is trivial.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from flowtracker.gst_client import (
    GSTClient,
    GSTClientError,
    _extract_pdf_url,
    _find_collection_link,
    _iter_periods,
    _normalise_gst_url,
    _validate_period,
    is_period_in_future,
    parse_gst_pdf_table,
    parse_press_release_text,
    period_to_display,
    period_to_release_label,
    period_to_release_label_short,
    previous_period,
    same_period_prior_year,
)
from flowtracker.gst_models import GSTCollectionMonth
from flowtracker.js_fetch import JSFetchError


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------


class TestValidatePeriod:
    @pytest.mark.parametrize("period,expected", [
        ("2024-04", (2024, 4)),
        ("2025-01", (2025, 1)),
        ("2025-12", (2025, 12)),
        ("  2024-04  ", (2024, 4)),  # whitespace tolerated
    ])
    def test_valid_periods(self, period, expected):
        assert _validate_period(period) == expected

    @pytest.mark.parametrize("period", [
        "2024-4",       # not zero-padded
        "2024/04",      # wrong separator
        "April 2024",   # not numeric
        "2024-13",      # month out of range
        "2024-00",      # month out of range
        "2015-04",      # year too early (GST started July 2017)
        "",
        "garbage",
    ])
    def test_invalid_periods_raise(self, period):
        with pytest.raises(ValueError):
            _validate_period(period)


class TestIterPeriods:
    def test_single_month_range(self):
        assert _iter_periods("2024-04", "2024-04") == ["2024-04"]

    def test_three_month_range(self):
        assert _iter_periods("2024-04", "2024-06") == [
            "2024-04", "2024-05", "2024-06",
        ]

    def test_crosses_year_boundary(self):
        assert _iter_periods("2023-11", "2024-02") == [
            "2023-11", "2023-12", "2024-01", "2024-02",
        ]

    def test_reversed_range_raises(self):
        with pytest.raises(ValueError):
            _iter_periods("2024-06", "2024-04")


class TestPeriodFormatters:
    def test_period_to_display(self):
        assert period_to_display("2024-04") == "Apr-2024"
        assert period_to_display("2025-01") == "Jan-2025"

    def test_period_to_release_label(self):
        assert period_to_release_label("2024-04") == "April 2024"
        assert period_to_release_label("2025-01") == "January 2025"

    def test_previous_period(self):
        assert previous_period("2024-04") == "2024-03"
        assert previous_period("2024-01") == "2023-12"

    def test_same_period_prior_year(self):
        assert same_period_prior_year("2024-04") == "2023-04"
        assert same_period_prior_year("2025-01") == "2024-01"

    def test_is_period_in_future(self):
        assert is_period_in_future("2099-12", today=date(2025, 6, 1)) is True
        assert is_period_in_future("2025-06", today=date(2025, 6, 1)) is False
        assert is_period_in_future("2025-07", today=date(2025, 6, 1)) is True
        assert is_period_in_future("2025-05", today=date(2025, 6, 1)) is False


# ---------------------------------------------------------------------------
# Defensive parser — synthetic canonical-layout fixtures
# ---------------------------------------------------------------------------


# Synthetic fixture for April 2025 collection (released 1 May 2025). The
# language follows the standard CBIC press-release template; numbers match
# the real April-2025 release per the bundled seed.
_APRIL_2025_RELEASE = """
Press Release
1 May 2025

Gross GST Revenue collected in April 2025 is ₹2,36,716 crore — a record
all-time high — marking 12.6% higher than the gross GST revenue in April 2024.
Of this, CGST is ₹48,634 crore, SGST is ₹59,372 crore, IGST is ₹1,15,259
crore (including ₹47,069 crore collected on import of goods), and Cess is
₹13,451 crore (including ₹1,054 crore collected on import of goods).

Revenue from domestic transactions is ₹1,94,314 crore and revenue from
imports is ₹42,402 crore.
"""

# Synthetic fixture for May 2024 collection (released 1 June 2024) — values
# match the real CBIC release for that month.
_MAY_2024_RELEASE = """
Press Release: GST revenue collection for May 2024

Gross GST revenue collected in May 2024 stood at ₹1,72,739 crore, a growth
of 10.0% Y-o-Y. The breakdown: CGST ₹32,409 crore, SGST ₹40,265 crore,
IGST ₹87,781 crore, Cess ₹12,284 crore.

From domestic transactions: ₹1,39,404 crore. From imports: ₹33,335 crore.
"""


class TestParser:
    def test_april_2025_full_extraction(self):
        out = parse_press_release_text(_APRIL_2025_RELEASE)
        assert out["gross_collection_cr"] == pytest.approx(236716.0)
        assert out["cgst_cr"] == pytest.approx(48634.0)
        assert out["sgst_cr"] == pytest.approx(59372.0)
        assert out["igst_cr"] == pytest.approx(115259.0)
        assert out["cess_cr"] == pytest.approx(13451.0)
        assert out["domestic_cr"] == pytest.approx(194314.0)
        assert out["imports_cr"] == pytest.approx(42402.0)
        assert out["growth_yoy_pct"] == pytest.approx(12.6)

    def test_may_2024_full_extraction(self):
        out = parse_press_release_text(_MAY_2024_RELEASE)
        assert out["gross_collection_cr"] == pytest.approx(172739.0)
        assert out["cgst_cr"] == pytest.approx(32409.0)
        assert out["sgst_cr"] == pytest.approx(40265.0)
        assert out["igst_cr"] == pytest.approx(87781.0)
        assert out["cess_cr"] == pytest.approx(12284.0)
        assert out["domestic_cr"] == pytest.approx(139404.0)
        assert out["imports_cr"] == pytest.approx(33335.0)
        assert out["growth_yoy_pct"] == pytest.approx(10.0)

    def test_empty_text_returns_all_none(self):
        out = parse_press_release_text("")
        assert all(v is None for v in out.values())

    def test_garbage_text_returns_all_none(self):
        """Random non-GST text should yield all-None, not crash."""
        out = parse_press_release_text(
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            "This is not a GST press release at all.",
        )
        assert all(v is None for v in out.values())

    def test_normalizes_whitespace_and_linebreaks(self):
        """PDF-extracted text often has odd line breaks mid-sentence."""
        wrapped = (
            "Gross GST revenue collected\nin April 2025 is\n"
            "₹2,36,716 crore — 12.6% higher than April 2024."
        )
        out = parse_press_release_text(wrapped)
        assert out["gross_collection_cr"] == pytest.approx(236716.0)
        assert out["growth_yoy_pct"] == pytest.approx(12.6)

    def test_handles_alternate_growth_phrasing(self):
        """'growth of X%' and 'Y-o-Y growth of X%' must both match."""
        a = parse_press_release_text(
            "Gross GST revenue collected in April 2025 is ₹2,36,716 crore. "
            "Growth of 12.6% recorded.",
        )
        assert a["growth_yoy_pct"] == pytest.approx(12.6)

        b = parse_press_release_text(
            "Gross GST revenue collected in April 2025 is ₹2,36,716 crore. "
            "Y-o-Y growth of 12.6%.",
        )
        assert b["growth_yoy_pct"] == pytest.approx(12.6)


# ---------------------------------------------------------------------------
# GSTClient — bundled seed
# ---------------------------------------------------------------------------


class TestGSTClientSeed:
    def test_loads_bundled_seed_without_crash(self):
        """Sanity: the shipped seed JSON is valid and parses to >=1 row."""
        client = GSTClient()
        assert client.known_periods, "seed must contain at least one period"
        assert client.meta.get("description"), "seed meta must carry description"
        client.close()

    def test_fetch_latest_returns_max_period(self):
        client = GSTClient(seed={
            "_meta": {},
            "collections": [
                {"period": "2024-04", "gross_collection_cr": 210267.0},
                {"period": "2024-05", "gross_collection_cr": 172739.0},
                {"period": "2024-03", "gross_collection_cr": 178484.0},
            ],
        })
        latest = client.fetch_latest()
        assert latest is not None
        assert latest.period == "2024-05"
        client.close()

    def test_fetch_latest_on_empty_seed_returns_none(self):
        client = GSTClient(seed={"_meta": {}, "collections": []})
        assert client.fetch_latest() is None
        client.close()

    def test_fetch_month_resolves_from_seed(self):
        client = GSTClient(seed={
            "_meta": {},
            "collections": [
                {"period": "2024-04", "gross_collection_cr": 210267.0},
            ],
        })
        row = client.fetch_month("2024-04")
        assert row is not None
        assert row.gross_collection_cr == pytest.approx(210267.0)
        client.close()

    def test_fetch_month_missing_period_returns_none(self):
        client = GSTClient(seed={"_meta": {}, "collections": []})
        assert client.fetch_month("2024-04") is None
        client.close()

    def test_fetch_month_invalid_period_raises(self):
        client = GSTClient(seed={"_meta": {}, "collections": []})
        with pytest.raises(ValueError):
            client.fetch_month("bad-period")
        client.close()

    def test_fetch_backfill_returns_only_present_periods(self):
        client = GSTClient(seed={
            "_meta": {},
            "collections": [
                {"period": "2024-01", "gross_collection_cr": 1.0},
                {"period": "2024-03", "gross_collection_cr": 3.0},
                {"period": "2024-04", "gross_collection_cr": 4.0},
                # 2024-02 missing on purpose
            ],
        })
        rows = client.fetch_backfill("2024-01", "2024-04")
        assert [r.period for r in rows] == ["2024-01", "2024-03", "2024-04"]
        client.close()

    def test_fetch_backfill_reversed_range_raises(self):
        client = GSTClient(seed={"_meta": {}, "collections": []})
        with pytest.raises(ValueError):
            client.fetch_backfill("2024-06", "2024-04")
        client.close()

    def test_seed_must_be_a_dict_with_collections_list(self):
        with pytest.raises(GSTClientError):
            GSTClient(seed={"_meta": {}, "collections": "not a list"})

    def test_bad_row_in_seed_is_logged_and_skipped(self):
        """A malformed row must not abort the whole seed load."""
        client = GSTClient(seed={
            "_meta": {},
            "collections": [
                {"period": "2024-04", "gross_collection_cr": 210267.0},
                {"period": "bad-period", "gross_collection_cr": "not-a-number"},
            ],
        })
        # Good row survives
        assert client.fetch_month("2024-04") is not None
        # Bad row was skipped (not in known_periods)
        assert "bad-period" not in client.known_periods
        client.close()

    def test_context_manager_closes_http(self):
        with GSTClient(seed={"_meta": {}, "collections": []}) as client:
            # Just verify __enter__ returns the client and __exit__ runs cleanly
            assert client is not None


# ---------------------------------------------------------------------------
# GSTClient — live HTTP escape-hatch path
# ---------------------------------------------------------------------------


_SOURCE_URL = "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2125087"


class TestGSTClientLiveFetch:
    def test_parses_html_payload_via_source_url(self):
        """When source_url is given, client fetches + parses the HTML body."""
        # Wrap the synthetic release in minimal HTML so the BS4 stripper
        # has structure to ignore.
        html_payload = (
            "<html><body><div class='content'>"
            + _APRIL_2025_RELEASE
            + "</div></body></html>"
        )
        with GSTClient(seed={"_meta": {}, "collections": []}) as client:
            with respx.mock:
                respx.get(_SOURCE_URL).mock(
                    return_value=httpx.Response(
                        200,
                        text=html_payload,
                        headers={"content-type": "text/html; charset=utf-8"},
                    ),
                )
                row = client.fetch_month("2025-04", source_url=_SOURCE_URL)

        assert row is not None
        assert row.period == "2025-04"
        assert row.source_url == _SOURCE_URL
        assert row.gross_collection_cr == pytest.approx(236716.0)
        assert row.growth_yoy_pct == pytest.approx(12.6)

    def test_http_error_returns_none(self):
        """5xx / network error → None, no exception."""
        with GSTClient(seed={"_meta": {}, "collections": []}) as client:
            with respx.mock:
                respx.get(_SOURCE_URL).mock(
                    return_value=httpx.Response(503, text="upstream down"),
                )
                row = client.fetch_month("2025-04", source_url=_SOURCE_URL)
        assert row is None

    def test_unparseable_body_returns_row_with_all_none_fields(self):
        """Body has no GST language → row persists with everything None
        (so the analyst sees we tried), source_url retained for retry."""
        with GSTClient(seed={"_meta": {}, "collections": []}) as client:
            with respx.mock:
                respx.get(_SOURCE_URL).mock(
                    return_value=httpx.Response(
                        200,
                        text="<html><body>Page not found</body></html>",
                        headers={"content-type": "text/html"},
                    ),
                )
                row = client.fetch_month("2025-04", source_url=_SOURCE_URL)

        assert row is not None
        assert row.period == "2025-04"
        assert row.source_url == _SOURCE_URL
        assert row.gross_collection_cr is None
        assert row.cgst_cr is None
        assert row.growth_yoy_pct is None


# ---------------------------------------------------------------------------
# Tabular parser (new tutorial.gst.gov.in PDF format)
# ---------------------------------------------------------------------------


_GOLDEN = Path(__file__).parent.parent / "fixtures" / "golden"


@pytest.fixture
def apr2026_pdf_text() -> str:
    """First 3000 chars of pdfplumber-extracted text from the Apr-2026 PDF.

    Captured from the live ``tutorial.gst.gov.in`` PDF — represents the
    structured table layout used from FY26 onward.
    """
    return (_GOLDEN / "gst_apr2026_pdftext.txt").read_text(encoding="utf-8")


class TestTabularParser:
    def test_apr2026_full_extraction(self, apr2026_pdf_text):
        """Real Apr-2026 PDF text — must extract gross + CGST/SGST/IGST +
        domestic + imports + YoY."""
        out = parse_gst_pdf_table(apr2026_pdf_text)
        assert out["gross_collection_cr"] == pytest.approx(242702.0)
        assert out["cgst_cr"] == pytest.approx(52140.0)
        assert out["sgst_cr"] == pytest.approx(61331.0)
        assert out["igst_cr"] == pytest.approx(129232.0)
        assert out["domestic_cr"] == pytest.approx(185122.0)
        assert out["imports_cr"] == pytest.approx(57580.0)
        assert out["growth_yoy_pct"] == pytest.approx(8.7)
        # New PDF format does not break out cess separately
        assert out["cess_cr"] is None

    def test_empty_text(self):
        out = parse_gst_pdf_table("")
        assert all(v is None for v in out.values())

    def test_disambiguates_gross_vs_refunds(self):
        """The PDF has CGST rows in 4 sub-sections (A.1 / A.3 / B.1 / C.1).
        We must pick A.3 Gross GST Revenue, not B.1 Domestic Refunds."""
        text = (
            "A.1. Domestic CGST 100 200 SGST 100 200 "
            "A.3. Gross GST Revenue CGST 48,634 52,140 SGST 59,372 61,331 "
            "IGST 1,15,259 1,29,232 "
            "Total Gross GST Revenue 2,23,265 2,42,702 8.7% "
            "B.1. Domestic Refunds CGST 3,231 5,253 "
        )
        out = parse_gst_pdf_table(text)
        assert out["cgst_cr"] == pytest.approx(52140.0)
        assert out["sgst_cr"] == pytest.approx(61331.0)


# ---------------------------------------------------------------------------
# Release-label-short / link discovery helpers
# ---------------------------------------------------------------------------


class TestReleaseLabelShort:
    def test_apr_2026(self):
        assert period_to_release_label_short("2026-04") == "Apr, 2026"

    def test_jan_2025(self):
        assert period_to_release_label_short("2025-01") == "Jan, 2025"


class TestFindCollectionLink:
    def test_finds_matching_month(self):
        html = """
        <ul>
          <li><a href="/newsandupdates/read/659">Gross and Net GST revenue
              collections for the month of Apr, 2026</a></li>
          <li><a href="/newsandupdates/read/658">Introduction of IMS Offline
              Tool</a></li>
          <li><a href="/newsandupdates/read/654">Gross and Net GST revenue
              collections for the month of Mar, 2026</a></li>
        </ul>
        """
        href = _find_collection_link(html, "Apr, 2026")
        assert href == "/newsandupdates/read/659"

    def test_skips_non_collection_link(self):
        """The label must coexist with the word 'collection' — random
        advisory containing 'Apr, 2026' should not match."""
        html = '<a href="/newsandupdates/read/700">Advisory for Apr, 2026</a>'
        assert _find_collection_link(html, "Apr, 2026") is None

    def test_returns_none_when_label_missing(self):
        html = (
            '<a href="/newsandupdates/read/659">Gross and Net GST revenue '
            "collections for the month of Apr, 2026</a>"
        )
        assert _find_collection_link(html, "Mar, 2026") is None

    def test_handles_absolute_href(self):
        html = (
            '<a href="//www.gst.gov.in/newsandupdates/read/659">'
            "Gross and Net GST revenue collections for the month of Apr, 2026</a>"
        )
        href = _find_collection_link(html, "Apr, 2026")
        assert href == "//www.gst.gov.in/newsandupdates/read/659"


class TestExtractPdfUrl:
    def test_picks_first_pdf(self):
        html = (
            "<html>some text "
            "<a href='https://tutorial.gst.gov.in/downloads/news/for_publishing_"
            "monthly_gst_data_for_apr_2026.pdf'>PDF</a></html>"
        )
        assert _extract_pdf_url(html) == (
            "https://tutorial.gst.gov.in/downloads/news/"
            "for_publishing_monthly_gst_data_for_apr_2026.pdf"
        )

    def test_no_pdf_returns_none(self):
        assert _extract_pdf_url("<html>no link here</html>") is None


class TestNormaliseGstUrl:
    def test_protocol_relative(self):
        assert _normalise_gst_url("//www.gst.gov.in/foo") == "https://www.gst.gov.in/foo"

    def test_path_only(self):
        assert _normalise_gst_url("/foo") == "https://www.gst.gov.in/foo"

    def test_absolute(self):
        assert _normalise_gst_url("https://example.com/x") == "https://example.com/x"


# ---------------------------------------------------------------------------
# fetch_month_live — Playwright session mocked, PDF download via respx
# ---------------------------------------------------------------------------


_PDF_URL = (
    "https://tutorial.gst.gov.in/downloads/news/"
    "for_publishing_monthly_gst_data_for_apr_2026.pdf"
)


def _make_fake_session(*, listing_html: str, detail_html: str):
    """Build a fake :class:`JSFetchSession` returning canned HTML.

    ``session.fetch(url, ...)`` returns ``listing_html`` for the first call
    and ``detail_html`` for the second. The fixture is patched into the
    module that ``fetch_month_live`` imports it from.
    """
    fake = MagicMock(name="JSFetchSession")
    # Make context-manager protocol work: with FakeSession() as s: ...
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    fake.fetch.side_effect = [listing_html, detail_html]
    return fake


class TestFetchMonthLive:
    """The full live path: Playwright discovers the link + PDF URL, then
    httpx downloads the PDF. We mock the JSFetchSession and httpx the
    PDF download via respx."""

    def _good_listing(self) -> str:
        return (
            "<ul>"
            "<li><a href='/newsandupdates/read/659'>"
            "Gross and Net GST revenue collections for the month of Apr, 2026"
            "</a></li>"
            "</ul>"
        )

    def _good_detail(self) -> str:
        return f"<html>PDF: <a href='{_PDF_URL}'>download</a></html>"

    @pytest.fixture
    def pdf_bytes(self) -> bytes:
        return (_GOLDEN / "gst_apr2026_release.pdf").read_bytes()

    def test_full_live_path(self, pdf_bytes):
        fake = _make_fake_session(
            listing_html=self._good_listing(),
            detail_html=self._good_detail(),
        )
        with patch(
            "flowtracker.js_fetch.JSFetchSession", return_value=fake,
        ):
            with respx.mock:
                respx.get(_PDF_URL).mock(
                    return_value=httpx.Response(
                        200,
                        content=pdf_bytes,
                        headers={"content-type": "application/pdf"},
                    ),
                )
                with GSTClient(
                    seed={"_meta": {}, "collections": []},
                ) as client:
                    row = client.fetch_month_live("2026-04")
        assert row is not None
        assert row.period == "2026-04"
        assert row.source_url == _PDF_URL
        assert row.gross_collection_cr == pytest.approx(242702.0)
        assert row.growth_yoy_pct == pytest.approx(8.7)

    def test_no_link_found_returns_none(self):
        """Listing has no Apr, 2026 entry — return None gracefully."""
        fake = _make_fake_session(
            listing_html="<ul><li>nothing relevant</li></ul>",
            detail_html="",  # never fetched
        )
        with patch(
            "flowtracker.js_fetch.JSFetchSession", return_value=fake,
        ):
            with GSTClient(seed={"_meta": {}, "collections": []}) as client:
                row = client.fetch_month_live("2026-04")
        assert row is None
        # Only listing was fetched (detail page not reached)
        assert fake.fetch.call_count == 1

    def test_detail_page_missing_pdf_returns_none(self):
        fake = _make_fake_session(
            listing_html=self._good_listing(),
            detail_html="<html>no PDF link here</html>",
        )
        with patch(
            "flowtracker.js_fetch.JSFetchSession", return_value=fake,
        ):
            with GSTClient(seed={"_meta": {}, "collections": []}) as client:
                row = client.fetch_month_live("2026-04")
        assert row is None

    def test_playwright_failure_returns_none(self):
        """JSFetchError on the listing fetch → return None, don't raise."""
        fake = MagicMock(name="JSFetchSession")
        fake.__enter__.return_value = fake
        fake.__exit__.return_value = False
        fake.fetch.side_effect = JSFetchError("browser missing")
        with patch(
            "flowtracker.js_fetch.JSFetchSession", return_value=fake,
        ):
            with GSTClient(seed={"_meta": {}, "collections": []}) as client:
                row = client.fetch_month_live("2026-04")
        assert row is None

    def test_pdf_download_404_returns_none(self):
        fake = _make_fake_session(
            listing_html=self._good_listing(),
            detail_html=self._good_detail(),
        )
        with patch(
            "flowtracker.js_fetch.JSFetchSession", return_value=fake,
        ):
            with respx.mock:
                respx.get(_PDF_URL).mock(
                    return_value=httpx.Response(404, text="not found"),
                )
                with GSTClient(seed={"_meta": {}, "collections": []}) as client:
                    row = client.fetch_month_live("2026-04")
        assert row is None

    def test_invalid_period_raises(self):
        with GSTClient(seed={"_meta": {}, "collections": []}) as client:
            with pytest.raises(ValueError):
                client.fetch_month_live("bad-period")
