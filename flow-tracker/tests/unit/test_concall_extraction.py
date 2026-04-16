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


# ---------------------------------------------------------------------------
# FY quarter sort helpers & Screener period conversion
# ---------------------------------------------------------------------------
from pathlib import Path

from flowtracker.research import concall_extractor as ce


class TestFyQuarterHelpers:
    """Coverage for _fy_sort_key, _fy_sort_key_from_str, _screener_period_to_fy_quarter."""

    def test_fy_sort_key_valid(self, tmp_path: Path):
        """FY26-Q3 parses to (26, 3)."""
        q = tmp_path / "FY26-Q3"
        q.mkdir()
        assert ce._fy_sort_key(q) == (26, 3)

    def test_fy_sort_key_ordering(self, tmp_path: Path):
        """Later FYs sort after earlier ones; Q4 sorts after Q1 within same FY."""
        (tmp_path / "FY25-Q1").mkdir()
        (tmp_path / "FY25-Q4").mkdir()
        (tmp_path / "FY26-Q1").mkdir()
        keys = [ce._fy_sort_key(d) for d in sorted(tmp_path.iterdir(), key=ce._fy_sort_key)]
        assert keys == [(25, 1), (25, 4), (26, 1)]

    def test_fy_sort_key_invalid_returns_zero(self, tmp_path: Path):
        """Malformed directory name returns (0, 0)."""
        bad = tmp_path / "notaquarter"
        bad.mkdir()
        assert ce._fy_sort_key(bad) == (0, 0)

    def test_fy_sort_key_from_str(self):
        """String form returns identical (fy, q) tuple."""
        assert ce._fy_sort_key_from_str("FY26-Q3") == (26, 3)
        assert ce._fy_sort_key_from_str("FY24-Q1") == (24, 1)

    def test_screener_period_jan_maps_to_q3(self):
        """Jan-Mar announcement → Q3 results (Oct-Dec)."""
        assert ce._screener_period_to_fy_quarter("Jan 2026") == "FY26-Q3"
        assert ce._screener_period_to_fy_quarter("Feb 2026") == "FY26-Q3"
        assert ce._screener_period_to_fy_quarter("Mar 2026") == "FY26-Q3"

    def test_screener_period_apr_maps_to_q4(self):
        """Apr-Jun announcement → Q4 results (prior FY Jan-Mar)."""
        assert ce._screener_period_to_fy_quarter("Apr 2026") == "FY26-Q4"
        assert ce._screener_period_to_fy_quarter("Jun 2026") == "FY26-Q4"

    def test_screener_period_jul_maps_to_q1_next_fy(self):
        """Jul-Sep announcement → Q1 of FY starting that April."""
        # Jul 2025 announcement is for Apr-Jun 2025 results → FY26-Q1
        assert ce._screener_period_to_fy_quarter("Jul 2025") == "FY26-Q1"
        assert ce._screener_period_to_fy_quarter("Sep 2025") == "FY26-Q1"

    def test_screener_period_oct_maps_to_q2(self):
        """Oct-Dec announcement → Q2 of the FY starting in prior April."""
        assert ce._screener_period_to_fy_quarter("Oct 2025") == "FY26-Q2"
        assert ce._screener_period_to_fy_quarter("Dec 2025") == "FY26-Q2"

    def test_screener_period_invalid_month_raises(self):
        """Unknown month prefix triggers KeyError."""
        with pytest.raises(KeyError):
            ce._screener_period_to_fy_quarter("Foo 2026")


# ---------------------------------------------------------------------------
# _quarter_label_from_path
# ---------------------------------------------------------------------------


class TestQuarterLabelFromPath:
    def test_returns_parent_dir_name(self, tmp_path: Path):
        """The label is simply the parent directory's name."""
        qdir = tmp_path / "FY26-Q3"
        qdir.mkdir()
        pdf = qdir / "concall.pdf"
        pdf.write_text("")
        assert ce._quarter_label_from_path(pdf) == "FY26-Q3"


# ---------------------------------------------------------------------------
# PDF text extraction (_read_pdf_text) — mocks pdfplumber
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, text: str | None):
        self._text = text

    def extract_text(self):
        return self._text


class _FakePdf:
    """Mimics pdfplumber.open() context manager returning .pages."""

    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestReadPdfText:
    def test_joins_nonempty_pages(self, monkeypatch, tmp_path: Path):
        """Each page's text is joined with double newlines."""
        pdf_path = tmp_path / "concall.pdf"
        pdf_path.write_bytes(b"fake-pdf-bytes")

        pages = [_FakePage("Page one text."), _FakePage("Page two text.")]
        import pdfplumber

        monkeypatch.setattr(pdfplumber, "open", lambda p: _FakePdf(pages))
        result = ce._read_pdf_text(pdf_path)
        assert "Page one text." in result
        assert "Page two text." in result
        assert "\n\n" in result

    def test_skips_pages_with_none_text(self, monkeypatch, tmp_path: Path):
        """Pages where extract_text() returns None are skipped."""
        pdf_path = tmp_path / "concall.pdf"
        pdf_path.write_bytes(b"fake")

        pages = [_FakePage(None), _FakePage("Only page with text.")]
        import pdfplumber

        monkeypatch.setattr(pdfplumber, "open", lambda p: _FakePdf(pages))
        result = ce._read_pdf_text(pdf_path)
        assert result == "Only page with text."

    def test_empty_pdf_returns_empty_string(self, monkeypatch, tmp_path: Path):
        """PDF with zero pages yields empty string."""
        pdf_path = tmp_path / "concall.pdf"
        pdf_path.write_bytes(b"fake")

        import pdfplumber

        monkeypatch.setattr(pdfplumber, "open", lambda p: _FakePdf([]))
        result = ce._read_pdf_text(pdf_path)
        assert result == ""


# ---------------------------------------------------------------------------
# _find_supplementary_pdfs — currently hard-coded to return []
# ---------------------------------------------------------------------------


class TestFindSupplementaryPdfs:
    def test_always_returns_empty_list(self, tmp_path: Path):
        """PPT reading is disabled — function always returns []."""
        # Even with matching files present, current code returns [].
        (tmp_path / "investor_deck.pdf").write_text("")
        (tmp_path / "concall_ppt.pdf").write_text("")
        assert ce._find_supplementary_pdfs(tmp_path) == []


# ---------------------------------------------------------------------------
# _find_concall_pdfs — vault scan logic
# ---------------------------------------------------------------------------


class TestFindConcallPdfs:
    def test_returns_empty_when_no_filings(self, monkeypatch, tmp_path: Path):
        """With no vault PDFs and no Screener docs, returns empty."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        # Prevent ensure_transcript_pdfs from hitting the real DB
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)
        result = ce._find_concall_pdfs("TEST", quarters=4)
        assert result == []

    def test_finds_recent_quarters(self, monkeypatch, tmp_path: Path):
        """Existing FYxx-Qy/concall.pdf files are returned newest-first within window."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings"
        for q in ("FY26-Q3", "FY26-Q2", "FY26-Q1", "FY25-Q4"):
            d = filings / q
            d.mkdir(parents=True)
            (d / "concall.pdf").write_bytes(b"pdf")

        result = ce._find_concall_pdfs("TEST", quarters=4)
        assert len(result) == 4
        # Newest first
        assert result[0].parent.name == "FY26-Q3"
        assert result[-1].parent.name == "FY25-Q4"

    def test_respects_quarters_limit(self, monkeypatch, tmp_path: Path):
        """Only up to `quarters` PDFs returned even when more exist."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings"
        for q in ("FY26-Q3", "FY26-Q2", "FY26-Q1", "FY25-Q4"):
            d = filings / q
            d.mkdir(parents=True)
            (d / "concall.pdf").write_bytes(b"pdf")

        result = ce._find_concall_pdfs("TEST", quarters=2)
        assert len(result) == 2
        assert result[0].parent.name == "FY26-Q3"
        assert result[1].parent.name == "FY26-Q2"

    def test_ignores_non_fy_dirs(self, monkeypatch, tmp_path: Path):
        """Directories not matching FY??-Q? pattern are ignored."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings"
        (filings / "FY26-Q3").mkdir(parents=True)
        (filings / "FY26-Q3" / "concall.pdf").write_bytes(b"pdf")
        # Random other dirs should be skipped
        (filings / "random_dir").mkdir()
        (filings / "random_dir" / "concall.pdf").write_bytes(b"pdf")

        result = ce._find_concall_pdfs("TEST", quarters=4)
        assert len(result) == 1
        assert result[0].parent.name == "FY26-Q3"


# ---------------------------------------------------------------------------
# _download_transcript_from_url — mocks httpx
# ---------------------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, status_code: int, content: bytes):
        self.status_code = status_code
        self.content = content


class _FakeHttpxClient:
    """Context-manager client stub used to replace httpx.Client."""

    def __init__(self, response=None, raise_exc=None):
        self._response = response
        self._raise_exc = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._response


class TestDownloadTranscriptFromUrl:
    def test_success_writes_file(self, monkeypatch, tmp_path: Path):
        """HTTP 200 with > 1KB content is written to dest_path."""
        import httpx

        content = b"x" * 2000
        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **kw: _FakeHttpxClient(_FakeHttpResponse(200, content)),
        )
        dest = tmp_path / "subdir" / "concall.pdf"
        ok = ce._download_transcript_from_url("http://example.com/x.pdf", dest)
        assert ok is True
        assert dest.exists()
        assert dest.read_bytes() == content

    def test_small_response_not_saved(self, monkeypatch, tmp_path: Path):
        """HTTP 200 but tiny content (<1KB) is not treated as success."""
        import httpx

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **kw: _FakeHttpxClient(_FakeHttpResponse(200, b"tiny")),
        )
        dest = tmp_path / "out.pdf"
        ok = ce._download_transcript_from_url("http://example.com", dest)
        assert ok is False
        assert not dest.exists()

    def test_403_returns_false_no_retry(self, monkeypatch, tmp_path: Path):
        """Permanent 403 short-circuits without retry."""
        import httpx

        calls = {"n": 0}

        def _factory(**kw):
            calls["n"] += 1
            return _FakeHttpxClient(_FakeHttpResponse(403, b""))

        monkeypatch.setattr(httpx, "Client", _factory)
        dest = tmp_path / "out.pdf"
        ok = ce._download_transcript_from_url("http://example.com", dest)
        assert ok is False
        assert calls["n"] == 1  # no retry on permanent failure

    def test_generic_exception_returns_false(self, monkeypatch, tmp_path: Path):
        """Any non-timeout exception returns False without retry."""
        import httpx

        monkeypatch.setattr(
            httpx,
            "Client",
            lambda **kw: _FakeHttpxClient(raise_exc=RuntimeError("boom")),
        )
        dest = tmp_path / "out.pdf"
        ok = ce._download_transcript_from_url("http://example.com", dest)
        assert ok is False


# ---------------------------------------------------------------------------
# _recover_json_from_prose + _call_claude — mock Claude SDK
# ---------------------------------------------------------------------------


# IMPORTANT: concall_extractor dispatches TextBlock via `type(b).__name__`,
# so the class must be named exactly "TextBlock".
class TextBlock:
    """Mimics claude_agent_sdk.TextBlock — dispatched via type(b).__name__."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAssistantMessage:
    def __init__(self, content):
        self.content = content


class _FakeResultMessage:
    def __init__(self, result):
        self.result = result


def _make_query_factory(messages, raise_after=False):
    async def _fake_query(*, prompt, options):  # noqa: ARG001
        for m in messages:
            yield m
        if raise_after:
            raise RuntimeError("post-stream error")

    return _fake_query


@pytest.fixture
def patch_claude_sdk(monkeypatch):
    """Patch ClaudeAgentOptions + AssistantMessage/ResultMessage in the concall module."""
    monkeypatch.setattr(ce, "AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(ce, "ResultMessage", _FakeResultMessage)
    monkeypatch.setattr(ce, "ClaudeAgentOptions", lambda **kw: type("O", (), kw)())


class TestCallClaude:
    async def test_returns_result_message_text(self, monkeypatch, patch_claude_sdk):
        """ResultMessage result is preferred over TextBlock content."""
        messages = [_FakeResultMessage('{"label": "FY26-Q3"}')]
        monkeypatch.setattr(ce, "query", _make_query_factory(messages))
        out = await ce._call_claude("sys", "user", "claude-sonnet-4-6")
        assert out == '{"label": "FY26-Q3"}'

    async def test_fallback_to_text_blocks_when_no_result(
        self, monkeypatch, patch_claude_sdk
    ):
        """If only TextBlocks arrive (no ResultMessage.result), blocks are joined."""
        assistant = _FakeAssistantMessage(content=[TextBlock("chunk one"), TextBlock("chunk two")])
        monkeypatch.setattr(ce, "query", _make_query_factory([assistant]))
        out = await ce._call_claude("sys", "user", "claude-sonnet-4-6")
        assert "chunk one" in out
        assert "chunk two" in out

    async def test_exception_with_captured_content_is_swallowed(
        self, monkeypatch, patch_claude_sdk
    ):
        """Exception after some content is captured should not propagate."""
        assistant = _FakeAssistantMessage(content=[TextBlock("partial data")])
        monkeypatch.setattr(
            ce, "query", _make_query_factory([assistant], raise_after=True)
        )
        out = await ce._call_claude("sys", "user", "claude-sonnet-4-6")
        assert "partial data" in out

    async def test_exception_with_no_content_reraises(
        self, monkeypatch, patch_claude_sdk
    ):
        """Exception with no content captured propagates out."""

        async def _fail_immediately(*, prompt, options):  # noqa: ARG001
            raise RuntimeError("no content at all")
            yield  # pragma: no cover

        monkeypatch.setattr(ce, "query", _fail_immediately)
        with pytest.raises(RuntimeError):
            await ce._call_claude("sys", "user", "claude-sonnet-4-6")

    async def test_respects_output_format_kwarg(self, monkeypatch, patch_claude_sdk):
        """output_format kwarg is forwarded into options without error."""
        messages = [_FakeResultMessage("{}")]
        monkeypatch.setattr(ce, "query", _make_query_factory(messages))
        out = await ce._call_claude(
            "sys", "user", "claude-sonnet-4-6", output_format={"type": "json_schema"}
        )
        assert out == "{}"


class TestRecoverJsonFromProse:
    async def test_recovery_returns_parsed_json(self, monkeypatch, patch_claude_sdk):
        """Recovery path feeds prose to cheap model and returns parsed JSON."""
        recovered = '{"label": "FY26-Q3", "fy_quarter": "FY26-Q3", "key_numbers_mentioned": {}}'
        messages = [_FakeResultMessage(recovered)]
        monkeypatch.setattr(ce, "query", _make_query_factory(messages))

        result = await ce._recover_json_from_prose(
            prose="Revenue was 1200 crore, up 15%.",
            quarter_label="FY26-Q3",
            symbol="TEST",
            model="claude-sonnet-4-6",
        )
        assert result["label"] == "FY26-Q3"
        assert "key_numbers_mentioned" in result


# ---------------------------------------------------------------------------
# _extract_single_quarter — integration of PDF + SDK + extraction
# ---------------------------------------------------------------------------


class TestExtractSingleQuarter:
    async def test_happy_path_complete_extraction(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """Well-formed JSON response yields extraction_status='complete'."""
        qdir = tmp_path / "FY26-Q3"
        qdir.mkdir()
        pdf = qdir / "concall.pdf"
        pdf.write_bytes(b"fake")

        # PDF returns some text
        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("Q3 concall content")])
        )
        # Claude returns valid JSON
        response_json = (
            '{"label": "Q3 FY26", "fy_quarter": "FY26-Q3", '
            '"operational_metrics": {"arpu": {"value": "68000"}}, '
            '"financial_metrics": {"consolidated": {"revenue_from_operations_cr": {"value": 1200}}}}'
        )
        monkeypatch.setattr(
            ce, "query", _make_query_factory([_FakeResultMessage(response_json)])
        )

        result = await ce._extract_single_quarter(
            pdf_path=pdf, symbol="TEST", model="claude-sonnet-4-6", industry=None
        )
        assert result["extraction_status"] == "complete"
        assert result["fy_quarter"] == "FY26-Q3"
        assert result["documents_read"] == ["concall.pdf"]
        assert "extraction_duration_seconds" in result
        assert result["operational_metrics"]["arpu"]["value"] == "68000"

    async def test_recovery_path_on_prose_response(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """When primary returns prose, recovery path produces extraction_status='recovered'."""
        qdir = tmp_path / "FY26-Q2"
        qdir.mkdir()
        pdf = qdir / "concall.pdf"
        pdf.write_bytes(b"fake")

        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("concall text " * 100)])
        )

        # The SDK is called twice — primary extraction returns prose,
        # recovery returns JSON. Sequence responses with a counter.
        call_count = {"n": 0}

        async def _seq_query(*, prompt, options):  # noqa: ARG001
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Primary: prose, longer than 200 chars, no JSON
                prose = "Revenue grew strongly this quarter. " * 20
                yield _FakeResultMessage(prose)
            else:
                # Recovery: valid JSON
                yield _FakeResultMessage(
                    '{"label": "FY26-Q2", "fy_quarter": "FY26-Q2", "key_numbers_mentioned": {}}'
                )

        monkeypatch.setattr(ce, "query", _seq_query)

        result = await ce._extract_single_quarter(
            pdf_path=pdf, symbol="TEST", model="claude-sonnet-4-6", industry=None
        )
        assert result["extraction_status"] == "recovered"
        assert call_count["n"] == 2  # primary + recovery

    async def test_short_prose_response_yields_failed_status(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """If primary returns < 200 chars of prose, extraction_status='failed'."""
        qdir = tmp_path / "FY26-Q1"
        qdir.mkdir()
        pdf = qdir / "concall.pdf"
        pdf.write_bytes(b"fake")

        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("text")])
        )
        monkeypatch.setattr(
            ce, "query", _make_query_factory([_FakeResultMessage("tiny")])
        )

        result = await ce._extract_single_quarter(
            pdf_path=pdf, symbol="TEST", model="claude-sonnet-4-6", industry=None
        )
        assert result["extraction_status"] == "failed"
        assert "Empty or very short" in result["extraction_error"]

    async def test_industry_injects_canonical_kpis(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """Industry param triggers canonical KPI validation in operational_metrics."""
        qdir = tmp_path / "FY26-Q3"
        qdir.mkdir()
        pdf = qdir / "concall.pdf"
        pdf.write_bytes(b"fake")

        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("bank concall")])
        )
        # JSON with only a subset of KPIs — missing ones must get filled in with null+reason
        response_json = (
            '{"label": "FY26-Q3", "fy_quarter": "FY26-Q3", '
            '"operational_metrics": {"casa_ratio_pct": {"value": "42"}}}'
        )
        monkeypatch.setattr(
            ce, "query", _make_query_factory([_FakeResultMessage(response_json)])
        )

        result = await ce._extract_single_quarter(
            pdf_path=pdf,
            symbol="TEST",
            model="claude-sonnet-4-6",
            industry="Private Sector Bank",
        )
        ops = result["operational_metrics"]
        # The single mentioned KPI survives
        assert ops["casa_ratio_pct"]["value"] == "42"
        # Missing KPIs are filled with not_mentioned_in_concall
        assert ops["gross_npa_pct"]["value"] is None
        assert ops["gross_npa_pct"]["reason"] == "not_mentioned_in_concall"


# ---------------------------------------------------------------------------
# _generate_cross_quarter_narrative
# ---------------------------------------------------------------------------


class TestGenerateCrossQuarterNarrative:
    async def test_fewer_than_two_quarters_returns_empty(self, patch_claude_sdk):
        """Single-quarter input short-circuits to empty dict."""
        result = await ce._generate_cross_quarter_narrative(
            [{"fy_quarter": "FY26-Q3"}], "TEST", "claude-sonnet-4-6"
        )
        assert result == {}

    async def test_happy_path_returns_parsed_narrative(
        self, monkeypatch, patch_claude_sdk
    ):
        """Two quarters + valid JSON yields a parsed narrative dict."""
        cross_json = (
            '{"key_themes": ["theme one"], "biggest_positive": "growth", '
            '"biggest_concern": "margins"}'
        )
        monkeypatch.setattr(
            ce, "query", _make_query_factory([_FakeResultMessage(cross_json)])
        )

        result = await ce._generate_cross_quarter_narrative(
            [{"fy_quarter": "FY26-Q3"}, {"fy_quarter": "FY26-Q2"}],
            "TEST",
            "claude-sonnet-4-6",
        )
        assert result["key_themes"] == ["theme one"]
        assert result["biggest_positive"] == "growth"

    async def test_prose_response_falls_back_gracefully(
        self, monkeypatch, patch_claude_sdk
    ):
        """Prose response triggers recovery; if that also fails, returns extraction_error dict."""
        call_count = {"n": 0}

        async def _fake_query(*, prompt, options):  # noqa: ARG001
            call_count["n"] += 1
            # Both primary and recovery return prose (no JSON).
            yield _FakeResultMessage("Just a long prose analysis. " * 20)

        monkeypatch.setattr(ce, "query", _fake_query)
        result = await ce._generate_cross_quarter_narrative(
            [{"fy_quarter": "FY26-Q3"}, {"fy_quarter": "FY26-Q2"}],
            "TEST",
            "claude-sonnet-4-6",
        )
        assert "extraction_error" in result
        assert call_count["n"] >= 1


# ---------------------------------------------------------------------------
# extract_concalls — top-level entry point
# ---------------------------------------------------------------------------


class TestExtractConcalls:
    async def test_raises_when_no_pdfs(self, monkeypatch, patch_claude_sdk, tmp_path: Path):
        """FileNotFoundError when no concall PDFs found."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)
        with pytest.raises(FileNotFoundError):
            await ce.extract_concalls("TEST", quarters=4)

    async def test_happy_path_writes_output(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """End-to-end: PDF → JSON extraction → file written under vault."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings"
        for q in ("FY26-Q3", "FY26-Q2"):
            d = filings / q
            d.mkdir(parents=True)
            (d / "concall.pdf").write_bytes(b"fake")

        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("concall text")])
        )

        # Every SDK call (per-quarter + cross) returns valid JSON
        async def _fake_query(*, prompt, options):  # noqa: ARG001
            yield _FakeResultMessage(
                '{"label": "Q", "fy_quarter": "FY26-Q3", '
                '"operational_metrics": {}, "key_themes": ["x"]}'
            )

        monkeypatch.setattr(ce, "query", _fake_query)

        result = await ce.extract_concalls("TEST", quarters=2)
        assert result["symbol"] == "TEST"
        assert result["quarters_analyzed"] == 2
        assert len(result["quarters"]) == 2
        # Cross-quarter narrative populated
        assert "cross_quarter_narrative" in result
        # Output written to vault path
        out_path = tmp_path / "TEST" / "fundamentals" / "concall_extraction_v2.json"
        assert out_path.exists()


# ---------------------------------------------------------------------------
# ensure_concall_data — per-quarter caching behavior
# ---------------------------------------------------------------------------


class TestEnsureConcallData:
    async def test_returns_none_when_no_pdfs(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """No PDFs → None, no SDK calls."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)
        result = await ce.ensure_concall_data("TEST", quarters=4)
        assert result is None

    async def test_fast_path_all_quarters_cached(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """All quarters already extracted → no re-extraction, returns existing."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings" / "FY26-Q3"
        filings.mkdir(parents=True)
        (filings / "concall.pdf").write_bytes(b"fake")

        # Pre-populate existing extraction
        out_dir = tmp_path / "TEST" / "fundamentals"
        out_dir.mkdir(parents=True)
        existing = {
            "symbol": "TEST",
            "quarters_analyzed": 1,
            "quarters": [
                {
                    "fy_quarter": "FY26-Q3",
                    "extraction_status": "complete",
                    "data": "cached",
                }
            ],
            "cross_quarter_narrative": {},
        }
        (out_dir / "concall_extraction_v2.json").write_text(json.dumps(existing))

        # SDK must not be called
        async def _boom(**kw):  # pragma: no cover
            raise AssertionError("SDK should not be called on fast path")
            yield

        monkeypatch.setattr(ce, "query", _boom)

        result = await ce.ensure_concall_data("TEST", quarters=4)
        assert result is not None
        assert result["_new_quarters_extracted"] == 0
        assert result["quarters"][0]["data"] == "cached"

    async def test_extracts_only_missing_quarters(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """Existing extraction + new PDF → extracts only the new quarter."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings"
        for q in ("FY26-Q3", "FY26-Q2"):
            d = filings / q
            d.mkdir(parents=True)
            (d / "concall.pdf").write_bytes(b"fake")

        # Pre-cache only Q2
        out_dir = tmp_path / "TEST" / "fundamentals"
        out_dir.mkdir(parents=True)
        existing = {
            "symbol": "TEST",
            "quarters_analyzed": 1,
            "quarters": [
                {
                    "fy_quarter": "FY26-Q2",
                    "extraction_status": "complete",
                    "label": "FY26-Q2",
                }
            ],
            "cross_quarter_narrative": {},
        }
        (out_dir / "concall_extraction_v2.json").write_text(json.dumps(existing))

        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("new Q3 content")])
        )

        call_count = {"n": 0}

        async def _counting_query(*, prompt, options):  # noqa: ARG001
            call_count["n"] += 1
            yield _FakeResultMessage(
                '{"label": "FY26-Q3", "fy_quarter": "FY26-Q3", '
                '"operational_metrics": {}, "key_themes": []}'
            )

        monkeypatch.setattr(ce, "query", _counting_query)

        result = await ce.ensure_concall_data("TEST", quarters=4)
        assert result is not None
        assert result["_new_quarters_extracted"] == 1
        # 2 quarters present: cached Q2 + new Q3
        assert result["quarters_analyzed"] == 2
        fy_quarters = sorted(q["fy_quarter"] for q in result["quarters"])
        assert fy_quarters == ["FY26-Q2", "FY26-Q3"]

    async def test_corrupt_existing_json_falls_back_to_fresh_extraction(
        self, monkeypatch, patch_claude_sdk, tmp_path: Path
    ):
        """Corrupt extraction JSON is treated as empty; all quarters extracted."""
        monkeypatch.setattr(ce, "_VAULT_BASE", tmp_path)
        monkeypatch.setattr(ce, "ensure_transcript_pdfs", lambda s, max_quarters=6: 0)

        filings = tmp_path / "TEST" / "filings" / "FY26-Q3"
        filings.mkdir(parents=True)
        (filings / "concall.pdf").write_bytes(b"fake")

        out_dir = tmp_path / "TEST" / "fundamentals"
        out_dir.mkdir(parents=True)
        (out_dir / "concall_extraction_v2.json").write_text("not json {{{")

        import pdfplumber

        monkeypatch.setattr(
            pdfplumber, "open", lambda p: _FakePdf([_FakePage("q3 text")])
        )

        async def _fake_query(*, prompt, options):  # noqa: ARG001
            yield _FakeResultMessage(
                '{"label": "FY26-Q3", "fy_quarter": "FY26-Q3", '
                '"operational_metrics": {}}'
            )

        monkeypatch.setattr(ce, "query", _fake_query)

        result = await ce.ensure_concall_data("TEST", quarters=4)
        assert result is not None
        assert result["_new_quarters_extracted"] == 1
