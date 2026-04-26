"""Tests for macro_anchors heading-match + section-end heuristics.

Covers:
  - Fuzzy heading matching: case-insensitive, section-prefix tolerance,
    dash normalization, word-order swap.
  - Smart section-end detection: numbered-parent heading skips Box/un-numbered
    same-level sub-headings; ends at next NUMBERED sibling.
  - Body-text fallback: when no heading matches, anchor on first body
    occurrence of the query.
  - Backwards compatibility: existing exact-substring queries still match.
  - Catalog: IRDAI Annual Report + RBI MPC statement entries are present.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowtracker.research import macro_anchors as ma
from flowtracker.research.macro_anchors import (
    _ANCHORS,
    _SCRAPERS,
    _body_text_anchor,
    _find_anchor_section_end,
    _match_heading,
    _normalize_heading,
    get_anchor_content,
)


# ---------------------------------------------------------------------------
# _normalize_heading
# ---------------------------------------------------------------------------

class TestNormalizeHeading:
    def test_lowercases(self):
        assert _normalize_heading("Aggregate Demand") == "aggregate demand"

    def test_strips_arabic_section_prefix(self):
        assert _normalize_heading("3. Prospects for 2025-26") == "prospects for 2025-26"

    def test_strips_roman_section_prefix(self):
        assert _normalize_heading("I.2 Commodity Prices") == "commodity prices"

    def test_strips_dotted_decimal_prefix(self):
        assert _normalize_heading("II.1.1 Money Market") == "money market"

    def test_strips_parenthesised_prefix(self):
        assert _normalize_heading("(ii) Foreign Exchange") == "foreign exchange"

    def test_normalizes_em_dash(self):
        assert _normalize_heading("Prospects for 2025—26") == "prospects for 2025-26"

    def test_normalizes_en_dash(self):
        assert _normalize_heading("Prospects for 2025–26") == "prospects for 2025-26"

    def test_strips_trailing_punctuation(self):
        assert _normalize_heading("Aggregate Demand.") == "aggregate demand"
        assert _normalize_heading("Aggregate Demand:") == "aggregate demand"

    def test_collapses_multi_space(self):
        # Docling sometimes emits double-spaces between section number and title
        assert _normalize_heading("I.2  Commodity Prices") == "commodity prices"


# ---------------------------------------------------------------------------
# _match_heading — multi-pass fuzzy matcher
# ---------------------------------------------------------------------------

@pytest.fixture
def rbi_mpr_headings():
    """A representative slice of RBI MPR L2 headings (real shape)."""
    return [
        {"level": 2, "text": "Executive Summary", "char_offset": 100},
        {"level": 2, "text": "I.  External Environment", "char_offset": 500},
        {"level": 2, "text": "I.1 Global Economic Conditions", "char_offset": 1000},
        {"level": 2, "text": "I.2  Commodity Prices and Inflation", "char_offset": 2000},
        {"level": 2, "text": "Consumer Price Inflation", "char_offset": 3000},
        {"level": 2, "text": "Box I.1 Bubble Dynamics in Gold Prices?", "char_offset": 3500},
        {"level": 2, "text": "I.3  Monetary Policy Stance", "char_offset": 5000},
        {"level": 2, "text": "III.1 Aggregate Demand", "char_offset": 8000},
        {"level": 2, "text": "V.2  Inflation Outlook", "char_offset": 12000},
    ]


class TestMatchHeading:
    def test_legacy_substring_match(self, rbi_mpr_headings):
        # Pass 1 — backwards compat
        idx = _match_heading("Aggregate Demand", rbi_mpr_headings)
        assert idx is not None
        assert "Aggregate Demand" in rbi_mpr_headings[idx]["text"]

    def test_case_insensitive(self, rbi_mpr_headings):
        idx = _match_heading("AGGREGATE DEMAND", rbi_mpr_headings)
        assert rbi_mpr_headings[idx]["text"] == "III.1 Aggregate Demand"

    def test_handles_section_prefix_mismatch(self, rbi_mpr_headings):
        # User says "I.2 Commodity Prices" — heading has DOUBLE space.
        idx = _match_heading("I.2 Commodity Prices", rbi_mpr_headings)
        assert idx is not None
        assert "Commodity Prices" in rbi_mpr_headings[idx]["text"]

    def test_em_dash_tolerance(self, rbi_mpr_headings):
        # Even if user query uses em-dash for hyphen
        rbi_mpr_headings.append({"level": 2, "text": "3. Prospects for 2025-26", "char_offset": 13000})
        idx = _match_heading("Prospects for 2025—26", rbi_mpr_headings)
        assert rbi_mpr_headings[idx]["text"] == "3. Prospects for 2025-26"

    def test_word_order_swap(self, rbi_mpr_headings):
        # "Inflation Outlook" matches via direct substring — so add a swap case
        # that requires word-set logic.
        idx = _match_heading("Outlook Inflation", rbi_mpr_headings)
        assert idx is not None
        assert "Inflation Outlook" in rbi_mpr_headings[idx]["text"]

    def test_no_match_returns_none(self, rbi_mpr_headings):
        assert _match_heading("Quantum Cryptography", rbi_mpr_headings) is None

    def test_short_query_with_no_match(self, rbi_mpr_headings):
        # 'xyz' has no occurrence — should NOT match anything.
        assert _match_heading("xyz", rbi_mpr_headings) is None

    def test_empty_query(self, rbi_mpr_headings):
        assert _match_heading("", rbi_mpr_headings) is None
        assert _match_heading("   ", rbi_mpr_headings) is None

    def test_empty_headings(self):
        assert _match_heading("anything", []) is None


# ---------------------------------------------------------------------------
# _find_anchor_section_end — smart end-detection
# ---------------------------------------------------------------------------

class TestFindAnchorSectionEnd:
    def test_numbered_parent_skips_unnumbered_sibling(self):
        """'3. Prospects for 2025-26' L2 is followed by un-numbered L2
        'Global Economy' / 'Domestic Economy' sub-sections. The section
        should extend to the next NUMBERED sibling ('4. Conclusion')."""
        md = "x" * 10000
        headings = [
            {"level": 2, "text": "3. Prospects for 2025-26", "char_offset": 100},
            {"level": 2, "text": "Global Economy", "char_offset": 200},
            {"level": 2, "text": "Domestic Economy", "char_offset": 500},
            {"level": 2, "text": "4. Conclusion", "char_offset": 1500},
        ]
        end = _find_anchor_section_end(md, headings, 0)
        assert end == 1500

    def test_numbered_parent_skips_box_subheading(self):
        """'I.2 Commodity Prices' followed by 'Box I.1 ...' — section should
        extend past the Box."""
        md = "x" * 10000
        headings = [
            {"level": 2, "text": "I.2 Commodity Prices", "char_offset": 100},
            {"level": 2, "text": "Box I.1 Bubble Dynamics", "char_offset": 200},
            {"level": 2, "text": "I.3 Monetary Policy Stance", "char_offset": 1000},
        ]
        end = _find_anchor_section_end(md, headings, 0)
        assert end == 1000

    def test_unnumbered_parent_skips_box_subheading(self):
        """Even an UN-numbered parent like 'Consumer Price Inflation' should
        extend past Box sub-headings — Box/Table/Figure are always sub-content."""
        md = "x" * 10000
        headings = [
            {"level": 2, "text": "Consumer Price Inflation", "char_offset": 100},
            {"level": 2, "text": "Box I.1 Bubble Dynamics", "char_offset": 200},
            {"level": 2, "text": "I.3 Monetary Policy Stance", "char_offset": 1000},
        ]
        end = _find_anchor_section_end(md, headings, 0)
        assert end == 1000

    def test_unnumbered_parent_default_ends_at_next_unnumbered(self):
        """Backwards-compat: 'Global Economy' (un-numbered) ends at next
        un-numbered same-level heading (existing behavior)."""
        md = "x" * 10000
        headings = [
            {"level": 2, "text": "Global Economy", "char_offset": 100},
            {"level": 2, "text": "Domestic Economy", "char_offset": 500},
        ]
        end = _find_anchor_section_end(md, headings, 0)
        assert end == 500

    def test_higher_level_heading_always_ends(self):
        """Any L1 heading after a L2 heading ends the section — no matter
        whether the parent is numbered or not."""
        md = "x" * 10000
        headings = [
            {"level": 2, "text": "3. Prospects for 2025-26", "char_offset": 100},
            {"level": 2, "text": "Global Economy", "char_offset": 200},
            {"level": 1, "text": "PART TWO: ANNUAL ACCOUNTS", "char_offset": 500},
        ]
        end = _find_anchor_section_end(md, headings, 0)
        assert end == 500

    def test_eod_when_no_sibling(self):
        md = "x" * 10000
        headings = [
            {"level": 2, "text": "3. Prospects for 2025-26", "char_offset": 100},
            {"level": 2, "text": "Global Economy", "char_offset": 200},
        ]
        end = _find_anchor_section_end(md, headings, 0)
        assert end == 10000


# ---------------------------------------------------------------------------
# _body_text_anchor — fallback when no heading matches
# ---------------------------------------------------------------------------

class TestBodyTextAnchor:
    def test_finds_phrase_in_body(self):
        md = (
            "## Demand side: Domestic drivers\n\n"
            "Foo bar baz private consumption growth has been strong.\n"
            "More text about consumption and savings.\n\n"
            "## Next Section\n"
        )
        headings = [
            {"level": 2, "text": "Demand side: Domestic drivers", "char_offset": 0},
            {"level": 2, "text": "Next Section", "char_offset": md.find("## Next Section")},
        ]
        result = _body_text_anchor(md, headings, "private consumption")
        assert result is not None
        assert result["containing_heading"] == "Demand side: Domestic drivers"
        assert result["matched_offset"] > 0

    def test_returns_none_for_short_query(self):
        md = "the the the"
        headings = []
        # Query length < _BODY_FALLBACK_MIN_QUERY_LEN
        assert _body_text_anchor(md, headings, "the") is None

    def test_returns_none_when_phrase_missing(self):
        md = "## Section\n\nbody about something else\n"
        headings = [{"level": 2, "text": "Section", "char_offset": 0}]
        assert _body_text_anchor(md, headings, "private consumption") is None


# ---------------------------------------------------------------------------
# get_anchor_content — integration (uses real vault if present)
# ---------------------------------------------------------------------------

class TestGetAnchorContentIntegration:
    """These tests use the real vault if it's populated. They're skipped
    cleanly when the vault is empty (e.g. CI without backfill)."""

    def _vault_has(self, doc_type: str) -> bool:
        catalog_path = Path.home() / "vault" / "macro" / "meta" / "catalog.json"
        if not catalog_path.exists():
            return False
        cat = json.loads(catalog_path.read_text())
        entry = cat.get("anchors", {}).get(doc_type, {})
        return entry.get("status") == "complete"

    def test_prospects_for_2025_26_returns_substantial_slice(self):
        """The original failure: returned 29 chars. Should now return ≥ 1KB."""
        if not self._vault_has("rbi_ar_assessment"):
            pytest.skip("rbi_ar_assessment not in vault")
        r = get_anchor_content("rbi_ar_assessment", section="Prospects for 2025-26")
        assert r["status"] == "ok"
        # Smart end-detection should aggregate across un-numbered sub-sections
        # like "Global Economy" / "Domestic Economy".
        assert r["chars"] > 1000, f"expected >1KB; got {r['chars']}"

    def test_consumer_price_inflation_returns_substantial_slice(self):
        """Originally returned 140 chars. Box sub-heading skip should fix it."""
        if not self._vault_has("rbi_mpr"):
            pytest.skip("rbi_mpr not in vault")
        r = get_anchor_content("rbi_mpr", section="Consumer Price Inflation")
        assert r["status"] == "ok"
        assert r["chars"] > 1000, f"expected >1KB; got {r['chars']}"

    def test_legacy_exact_substring_still_works(self):
        if not self._vault_has("rbi_mpr"):
            pytest.skip("rbi_mpr not in vault")
        # Existing passing query.
        r = get_anchor_content("rbi_mpr", section="Executive Summary")
        assert r["status"] == "ok"
        assert "Executive Summary" in r["heading"]


# ---------------------------------------------------------------------------
# Catalog — IRDAI + RBI MPC entries
# ---------------------------------------------------------------------------

class TestCatalogEntries:
    def test_irdai_annual_report_in_catalog(self):
        doc_types = [a.doc_type for a in _ANCHORS]
        assert "irdai_annual_report" in doc_types

    def test_rbi_mpc_statement_in_catalog(self):
        doc_types = [a.doc_type for a in _ANCHORS]
        assert "rbi_mpc_statement" in doc_types

    def test_irdai_scraper_registered(self):
        assert "_scrape_irdai_annual_report" in _SCRAPERS

    def test_rbi_mpc_scraper_registered(self):
        assert "_scrape_rbi_mpc_statement" in _SCRAPERS

    def test_irdai_anchor_metadata(self):
        spec = next(a for a in _ANCHORS if a.doc_type == "irdai_annual_report")
        assert "IRDAI" in spec.title
        assert spec.scraper == "_scrape_irdai_annual_report"

    def test_mpc_anchor_metadata(self):
        spec = next(a for a in _ANCHORS if a.doc_type == "rbi_mpc_statement")
        assert "MPC" in spec.title or "Monetary Policy" in spec.title
        assert spec.scraper == "_scrape_rbi_mpc_statement"
