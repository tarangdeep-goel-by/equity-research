"""Tests for concall extraction helpers in flowtracker/research/concall_extractor.py."""

from __future__ import annotations

import json

import pytest

from flowtracker.research.concall_extractor import _build_partial_extraction, _extract_json


# ---------------------------------------------------------------------------
# _extract_json — robust JSON extraction from Claude responses
# ---------------------------------------------------------------------------
class TestExtractJson:
    def test_extract_json_direct(self):
        """JSON starting with { is parsed directly."""
        raw = '{"label": "FY26-Q3", "revenue": 100}'
        result = _extract_json(raw)
        assert result["label"] == "FY26-Q3"
        assert result["revenue"] == 100

    def test_extract_json_code_fence(self):
        """JSON wrapped in ```json ``` is extracted and parsed."""
        raw = 'Here is the data:\n```json\n{"label": "FY26-Q3", "value": 42}\n```\nDone.'
        result = _extract_json(raw)
        assert result["label"] == "FY26-Q3"
        assert result["value"] == 42

    def test_extract_json_with_prose_prefix(self):
        """Text before JSON — finds first { to last }."""
        raw = 'Let me extract the data for you.\n\n{"label": "FY25-Q4", "metric": "test"}'
        result = _extract_json(raw)
        assert result["label"] == "FY25-Q4"

    def test_extract_json_no_json_raises(self):
        """Pure prose with no JSON raises JSONDecodeError."""
        raw = "This is a summary of the quarterly results. Revenue grew by 15%."
        with pytest.raises(json.JSONDecodeError):
            _extract_json(raw)

    def test_extract_json_whitespace_around(self):
        """JSON with leading/trailing whitespace is handled."""
        raw = '   \n  {"key": "val"}  \n  '
        result = _extract_json(raw)
        assert result["key"] == "val"

    def test_extract_json_nested(self):
        """Nested JSON objects are parsed correctly."""
        raw = '{"outer": {"inner": [1, 2, 3]}, "flag": true}'
        result = _extract_json(raw)
        assert result["outer"]["inner"] == [1, 2, 3]
        assert result["flag"] is True


# ---------------------------------------------------------------------------
# _build_partial_extraction — preserves partial data from prose responses
# ---------------------------------------------------------------------------
class TestBuildPartialExtraction:
    def test_preserves_quarter_label(self):
        """Quarter label and status are set correctly."""
        result = _build_partial_extraction(
            "Revenue was strong at 500 crore.", "FY26-Q3", ["concall.pdf"]
        )
        assert result["label"] == "FY26-Q3"
        assert result["fy_quarter"] == "FY26-Q3"
        assert result["extraction_status"] == "partial"
        assert result["documents_read"] == ["concall.pdf"]

    def test_extracts_some_key_numbers(self):
        """Extracts revenue/profit numbers mentioned in prose."""
        prose = (
            "The company reported strong results. Revenue of 1,234 crore was up 15% YoY. "
            "EBITDA margin improved to 22.5%. Net profit stood at 456 crore."
        )
        result = _build_partial_extraction(prose, "FY26-Q2", ["concall.pdf"])
        assert result["extraction_status"] == "partial"
        assert "key_numbers_mentioned" in result
        assert len(result["key_numbers_mentioned"]) > 0

    def test_empty_response(self):
        """Handles empty/short response gracefully."""
        result = _build_partial_extraction("", "FY25-Q4", ["concall.pdf"])
        assert result["extraction_status"] == "partial"
        assert result["label"] == "FY25-Q4"
        # No key_numbers_mentioned when nothing to extract
        assert "key_numbers_mentioned" not in result

    def test_raw_response_truncated(self):
        """Raw response is truncated to 4000 chars."""
        long_prose = "x" * 10000
        result = _build_partial_extraction(long_prose, "FY26-Q1", ["concall.pdf"])
        assert len(result["raw_response"]) == 4000


# ---------------------------------------------------------------------------
# Sector KPI hint injection
# ---------------------------------------------------------------------------
class TestSectorHintInjection:
    def test_sector_hint_in_prompt(self):
        """Verify that build_extraction_hint produces canonical KPI names for a known sector."""
        from flowtracker.research.sector_kpis import build_extraction_hint

        hint = build_extraction_hint("Private Sector Bank")
        assert "casa_ratio_pct" in hint
        assert "gross_npa_pct" in hint
        assert "CANONICAL" in hint.upper() or "canonical" in hint.lower()

    def test_sector_hint_empty_for_unknown(self):
        """Unknown industry returns empty hint."""
        from flowtracker.research.sector_kpis import build_extraction_hint

        hint = build_extraction_hint("Underwater Basket Weaving")
        assert hint == ""
