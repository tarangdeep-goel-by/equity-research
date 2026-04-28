"""Unit tests for AR section alias matching in heading_toc.py.

Track A from plans/ar-extraction-quality-fixes.md — expanded related_party
aliases to cover SEBI-AOC-2 / AS-18 / Schedule III heading variants observed
across the 16 benchmark cohort.
"""
from __future__ import annotations

import re

import pytest

from flowtracker.research.heading_toc import AR_SECTIONS, build_ar_section_index


def _matches(canonical: str, heading: str) -> bool:
    patterns = [re.compile(p, re.IGNORECASE) for p in AR_SECTIONS[canonical]]
    return any(rx.search(heading) for rx in patterns)


# Cases drawn directly from cohort `_docling.md` heading lines (Phase 0 audit).
# Each tuple: (heading_text, source_stock_for_provenance)
RELATED_PARTY_HEADINGS = [
    # AS-18 / Ind AS 24 disclosure variants
    ("12.5 Related Party Disclosures (Accounting Standard-18)", "BANKBARODA FY25"),
    ("d. Accounting Standard - 18 'Related Party Disclosures':", "SBIN FY25"),
    ("2.4 Accounting Standard-18 'Related Party Disclosures':", "SBIN FY25"),
    ("29.  Related party disclosures", "HDFCBANK FY25"),
    ("47.  Related party transactions", "ICICIBANK FY25"),
    ("33.  Related party disclosures", "ETERNAL FY25"),
    ("33.  Related party disclosures Names of related parties and "
     "related party relationship", "ETERNAL FY25"),
    ("30. Related party disclosures", "HINDALCO FY25"),
    ("41 RELATED PARTY DISCLOSURES", "NESTLEIND FY25"),
    ("NOTE 44 RELATED PARTY DISCLOSURES", "HINDUNILVR FY25"),
    # SEBI / Companies-Act AOC-2 wrapper headings
    ("Particulars of Contracts or Arrangements with Related Parties",
     "HDFCBANK FY25"),
    ("Annexure 2 - Particulars of contracts / arrangements made with "
     "related parties", "INFY FY25"),
    ("Particulars of contracts or arrangements made with related parties",
     "INFY FY25"),
    ("PARTICULARS OF CONTRACTS OR ARRANGEMENT WITH RELATED PARTIES",
     "POLICYBZR FY25"),
    # Schedule III lead-with-transactions form (note-numbered list items)
    ("ix. Transactions with related parties", "ETERNAL FY25"),
    ("19. Transactions with related parties", "TCS FY25"),
    ("xviii. Related party transactions", "ETERNAL FY25"),
    # Form AOC-2 standalone (used as separate section header in some ARs)
    ("FORM NO. AOC-2", "ICICIBANK FY25"),
    ("Form No. AOC-2", "HINDUNILVR FY25"),
    ("Form NO AOC 2", "synthetic — flexible spacing/punctuation"),
    # Pure plural/singular + numbered variants
    ("Related Party Transactions", "HDFCBANK FY25"),
    ("Related Party Transaction", "POLICYBZR FY25"),
    ("45  Related party transactions", "NYKAA FY25"),
    ("2.24 Related party transactions", "INFY FY25"),
]


@pytest.mark.parametrize("heading,source", RELATED_PARTY_HEADINGS,
                         ids=[s for _, s in RELATED_PARTY_HEADINGS])
def test_related_party_aliases_match_cohort_headings(heading: str, source: str) -> None:
    """Every cohort-observed related-party heading variant must be captured by
    at least one alias regex. Source attributions reference the FY25 AR PDF
    of each benchmark stock."""
    assert _matches("related_party", heading), (
        f"related_party alias regex did not match: {heading!r} (from {source})"
    )


def test_related_party_does_not_match_unrelated_headings() -> None:
    """Sanity: the aliases should not match unrelated headings."""
    for heading in [
        "Auditor's Report",
        "Management Discussion and Analysis",
        "Risk Management Framework",
        "Corporate Governance Report",
        "Notes to Financial Statements",
    ]:
        assert not _matches("related_party", heading), (
            f"related_party alias regex unexpectedly matched: {heading!r}"
        )


def test_aoc2_alias_handles_dash_and_space_variants() -> None:
    """AOC-2 alias should match Form-AOC-2 with all observed dash/space/period
    variants. The "Form" prefix is required to avoid false positives on stray
    paragraph mentions of AOC-2 elsewhere in the AR."""
    for heading in ["FORM NO. AOC-2", "Form No. AOC-2", "Form NO AOC 2",
                    "Form AOC-2", "Form AOC2"]:
        assert _matches("related_party", heading), (
            f"AOC-2 alias regex did not match: {heading!r}"
        )


def test_section_index_finds_related_party_with_new_alias() -> None:
    """End-to-end: a synthetic markdown + heading list with a BANKBARODA-style
    'Related Party Disclosures' heading should produce a related_party entry
    in the section index. Pre-Track-A this would have returned an empty dict
    for related_party."""
    md = (
        "## 12.5 Related Party Disclosures (Accounting Standard-18)\n"
        + "Body content with at least some plain text describing the "
          "transactions with key managerial personnel and subsidiaries.\n"
        * 200
        + "## 12.6 Next Section\n"
        + "Different content.\n" * 20
    )
    headings = [
        {"level": 2, "text": "12.5 Related Party Disclosures (Accounting Standard-18)",
         "char_offset": 0},
        {"level": 2, "text": "12.6 Next Section",
         "char_offset": md.index("## 12.6 Next Section")},
    ]
    idx = build_ar_section_index(md, headings)
    assert "related_party" in idx, (
        f"related_party not found in section_index: {list(idx.keys())}"
    )
    entry = idx["related_party"]
    assert entry["matched_heading"].startswith("12.5"), entry
    assert entry["size_chars"] > 100, entry


# ============================================================================
# Track B (2026-04-28) — heading_toc tie-breakers and rejection patterns
# ============================================================================

NOTES_TO_FINANCIALS_HEADINGS = [
    # Standard form
    ("Notes to the Consolidated Financial Statements", "ETERNAL FY25"),
    ("Notes to the Standalone Financial Statements", "POLICYBZR FY25"),
    ("NOTES TO FINANCIAL STATEMENTS", "DRREDDY FY25"),
    # `accounts` variant (Indian banks)
    ("Notes to Accounts", "HDFCBANK FY25 schedule-18 ref"),
    ("SCHEDULE 18: NOTES TO ACCOUNTS", "SBIN FY25"),
    ("SCHEDULE 18 - NOTES TO ACCOUNTS:", "SBIN FY25"),
    # `forming part of` variants (consolidated/standalone, financial-statements/accounts)
    ("NOTES FORMING PART OF THE STANDALONE FINANCIAL STATEMENTS FOR THE YEAR "
     "ENDED 31 st MARCH, 2025", "NESTLEIND FY25"),
    ("NOTES FORMING PART OF CONSOLIDATED FINANCIAL STATEMENTS", "TCS FY25"),
    ("NOTES FORMING PART OF THE ACCOUNTS", "ICICIBANK FY25"),
    # `notes on` variant (BANKBARODA Schedule-19 form)
    ("Notes on the Consolidated Financial Statements", "BANKBARODA FY25"),
    # Schedule-prefixed
    ("Schedule-19 : Notes on the Consolidated Financial Statements (CFS) for "
     "the year ended 31 st March 2025", "BANKBARODA FY25"),
    ("Schedule 18 - Notes to Accounts", "SBIN-style"),
]


@pytest.mark.parametrize("heading,source", NOTES_TO_FINANCIALS_HEADINGS,
                         ids=[s for _, s in NOTES_TO_FINANCIALS_HEADINGS])
def test_notes_to_financials_aliases_match_cohort_headings(
        heading: str, source: str) -> None:
    assert _matches("notes_to_financials", heading), (
        f"notes_to_financials alias did not match: {heading!r} (from {source})"
    )


def test_notes_to_financials_does_not_match_significant_accounting_policies() -> None:
    """Track B.5: Removed `significant accounting policies` from the alias list
    because it consistently mis-routed to a < 200-char SAP slice instead of the
    real notes data section. Verify it no longer matches."""
    for heading in [
        "SIGNIFICANT ACCOUNTING POLICIES",
        "SCHEDULE 17: SIGNIFICANT ACCOUNTING POLICIES",
        "Schedule 17 - Significant accounting policies appended to and forming "
        "part of the Standalone Balance Sheet",
        "SIGNIFICANT ACCOUNTING POLICIES FOR THE YEAR ENDED MARCH 31, 2025",
    ]:
        assert not _matches("notes_to_financials", heading), (
            f"notes_to_financials alias matched SAP heading: {heading!r}"
        )


def _build_index_with_two_candidates(
        canonical: str, heading_a: str, heading_b: str,
        body_a: str = "policy text without numbers.",
        body_b: str = "Revenue 12,345 Cr. Expenses 8,901 Cr. PAT 3,444 Cr.",
        repeat_b: int = 100,
) -> dict:
    """Helper: build a two-candidate markdown where heading_b's body is more
    data-rich. Used to test policy-rejection and digit-density tie-breakers."""
    body_a_block = (body_a + " ") * 50
    body_b_block = (body_b + " ") * repeat_b
    md = (
        f"## {heading_a}\n\n{body_a_block}\n\n"
        f"## Some unrelated heading\n\nfiller content\n\n"
        f"## {heading_b}\n\n{body_b_block}\n\n"
        f"## End\n"
    )
    headings = [
        {"level": 2, "text": heading_a, "char_offset": md.index(f"## {heading_a}")},
        {"level": 2, "text": "Some unrelated heading",
         "char_offset": md.index("## Some unrelated heading")},
        {"level": 2, "text": heading_b, "char_offset": md.index(f"## {heading_b}")},
        {"level": 2, "text": "End", "char_offset": md.index("## End")},
    ]
    return build_ar_section_index(md, headings)


def test_track_b_policy_letter_prefix_rejection_for_segmental() -> None:
    """Track B.1: `n) Segment reporting` (ETERNAL FY25 accounting policy) must
    be rejected when a real data heading exists."""
    idx = _build_index_with_two_candidates(
        "segmental",
        "n) Segment reporting",
        "Summarised segment information for the year ended March 31, 2025",
    )
    entry = idx.get("segmental")
    assert entry is not None
    assert "Summarised" in entry["matched_heading"], (
        f"policy-letter prefix not rejected; got: {entry['matched_heading']!r}"
    )


def test_track_b_agm_notice_rejection_for_related_party() -> None:
    """Track B.2: AGM-notice resolutions must be rejected for related_party.
    TCS FY25 had an 82KB AGM-resolution slice; INFY had an Item-no-N slice.
    """
    idx = _build_index_with_two_candidates(
        "related_party",
        "To approve material related party transactions with Tata Capital Limited",
        "22) Related party transactions",
    )
    entry = idx.get("related_party")
    assert entry is not None
    assert "22)" in entry["matched_heading"], (
        f"AGM 'To approve...' not rejected; got: {entry['matched_heading']!r}"
    )

    idx2 = _build_index_with_two_candidates(
        "related_party",
        "Item no. 5 - Material related party transactions of Infosys Limited",
        "2.24 Related party transactions",
    )
    entry2 = idx2.get("related_party")
    assert entry2 is not None
    assert "2.24" in entry2["matched_heading"], (
        f"AGM 'Item no. N' not rejected; got: {entry2['matched_heading']!r}"
    )


def test_track_b_digit_density_tiebreaker() -> None:
    """Track B.3: when two candidates match, the one with more numeric runs
    (table-like data) wins over policy-text or forward-references.
    HDFCBANK FY25 had a 1633ch policy block + a richer disclosure block —
    density picks the richer one.
    """
    # Both candidates pass alias matching; only digit content distinguishes
    # them. Make body_a (first candidate) prose-only, body_b numeric-heavy.
    idx = _build_index_with_two_candidates(
        "related_party",
        "Related Party Transactions",  # first occurrence — policy text
        "29. Related party disclosures",  # second occurrence — data
        body_a="The Company has policies covering related party transactions "
               "in line with applicable regulations.",
        body_b="Tata Sons Pvt Ltd 12,345 Cr. Tata Capital 6,789 Cr. ICICI Bank 4,567 Cr.",
    )
    entry = idx.get("related_party")
    assert entry is not None
    assert "29." in entry["matched_heading"], (
        f"density tie-breaker did not pick data-rich candidate; "
        f"got: {entry['matched_heading']!r}"
    )
