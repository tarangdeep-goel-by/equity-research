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

import httpx
import pytest
import respx

from flowtracker.gst_client import (
    GSTClient,
    GSTClientError,
    _iter_periods,
    _validate_period,
    is_period_in_future,
    parse_press_release_text,
    period_to_display,
    period_to_release_label,
    previous_period,
    same_period_prior_year,
)
from flowtracker.gst_models import GSTCollectionMonth


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
