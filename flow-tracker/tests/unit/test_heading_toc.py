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
