"""Tests for pure functions in flowtracker/research/assembly.py."""

from __future__ import annotations

import pytest

from flowtracker.research.assembly import _find_section, _split_by_headers, _strip_preamble


# ---------------------------------------------------------------------------
# _strip_preamble — strips text before first # heading or ---
# ---------------------------------------------------------------------------
class TestStripPreamble:
    def test_strips_preamble_before_heading(self):
        report = "I'll start by analyzing...\nLet me pull the data.\n# Business Overview\nGreat company."
        result = _strip_preamble(report)
        assert result == "# Business Overview\nGreat company."

    def test_strips_preamble_before_dashes(self):
        report = "Thinking about this...\n---\n# Report\nContent here."
        result = _strip_preamble(report)
        assert result == "---\n# Report\nContent here."

    def test_no_preamble_heading_first(self):
        report = "# Title\nContent."
        result = _strip_preamble(report)
        assert result == "# Title\nContent."

    def test_no_heading_returns_as_is(self):
        report = "Just some plain text without any markdown headings."
        result = _strip_preamble(report)
        assert result == report

    def test_empty_string(self):
        assert _strip_preamble("") == ""

    def test_h2_heading(self):
        report = "Preamble stuff.\n## Section One\nContent."
        result = _strip_preamble(report)
        assert result == "## Section One\nContent."

    def test_preserves_content_after_heading(self):
        report = "Preamble.\n# Title\nParagraph 1.\n## Sub\nParagraph 2."
        result = _strip_preamble(report)
        assert result.startswith("# Title")
        assert "Paragraph 2." in result

    def test_dashes_in_first_line(self):
        report = "---\nFrontmatter"
        result = _strip_preamble(report)
        assert result == "---\nFrontmatter"

    def test_whitespace_before_heading(self):
        """Heading with leading spaces should still be detected (stripped comparison)."""
        report = "Preamble.\n  # Indented Heading\nContent."
        result = _strip_preamble(report)
        assert result == "  # Indented Heading\nContent."


# ---------------------------------------------------------------------------
# _split_by_headers — splits markdown on ## headers
# ---------------------------------------------------------------------------
class TestSplitByHeaders:
    def test_basic_split(self):
        text = "## Verdict\nBuy.\n## Summary\nGood company."
        sections = _split_by_headers(text)
        assert "Verdict" in sections
        assert "Summary" in sections
        assert "Buy." in sections["Verdict"]
        assert "Good company." in sections["Summary"]

    def test_preserves_header_line_in_content(self):
        text = "## Verdict\nBuy."
        sections = _split_by_headers(text)
        assert sections["Verdict"].startswith("## Verdict")

    def test_no_headers(self):
        text = "Just plain text with no headers at all."
        sections = _split_by_headers(text)
        assert sections == {}

    def test_empty_string(self):
        sections = _split_by_headers("")
        assert sections == {}

    def test_h1_not_split(self):
        """Only ## headers are split, not # headers."""
        text = "# Title\nIntro.\n## Section\nContent."
        sections = _split_by_headers(text)
        assert "Section" in sections
        # The # Title should not create its own section
        assert "Title" not in sections

    def test_multiple_sections(self):
        text = "## A\na content\n## B\nb content\n## C\nc content"
        sections = _split_by_headers(text)
        assert len(sections) == 3
        assert "a content" in sections["A"]
        assert "b content" in sections["B"]
        assert "c content" in sections["C"]

    def test_text_before_first_header_ignored(self):
        text = "Preamble text.\n## First\nContent."
        sections = _split_by_headers(text)
        assert len(sections) == 1
        assert "First" in sections

    def test_header_with_special_chars(self):
        text = "## Key Signals & Catalysts\nBig things ahead."
        sections = _split_by_headers(text)
        assert "Key Signals & Catalysts" in sections


# ---------------------------------------------------------------------------
# _find_section — case-insensitive keyword search in section headers
# ---------------------------------------------------------------------------
class TestFindSection:
    def test_exact_match(self):
        sections = {"Verdict": "## Verdict\nBuy.", "Summary": "## Summary\nOK."}
        result = _find_section(sections, "Verdict")
        assert result is not None
        assert "Buy." in result

    def test_case_insensitive(self):
        sections = {"Executive Summary": "## Executive Summary\nContent."}
        result = _find_section(sections, "executive summary")
        assert result is not None
        assert "Content." in result

    def test_partial_keyword(self):
        sections = {"Key Signals & Catalysts": "## Key Signals & Catalysts\nBig news."}
        result = _find_section(sections, "Catalysts")
        assert result is not None
        assert "Big news." in result

    def test_not_found(self):
        sections = {"Verdict": "content"}
        result = _find_section(sections, "NonExistent")
        assert result is None

    def test_empty_sections(self):
        assert _find_section({}, "anything") is None

    def test_first_match_wins(self):
        """If multiple headers contain the keyword, the first match is returned."""
        from collections import OrderedDict
        sections = OrderedDict([
            ("Big Question for Investors", "first"),
            ("Another Big Question", "second"),
        ])
        result = _find_section(sections, "Big Question")
        assert result == "first"
