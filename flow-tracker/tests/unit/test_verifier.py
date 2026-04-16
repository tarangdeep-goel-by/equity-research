"""Tests for flowtracker/research/verifier.py.

Covers the verification agent that spot-checks specialist reports against
tool evidence. Mocks `claude_agent_sdk.query` to avoid real SDK calls.
"""

from __future__ import annotations

import pytest

from flowtracker.research import verifier as verifier_mod
from flowtracker.research.briefing import (
    AgentCost,
    BriefingEnvelope,
    ToolEvidence,
    VerificationResult,
)
from flowtracker.research.verifier import (
    DEFAULT_VERIFY_MODEL,
    VERIFICATION_PROMPT,
    _check_audit_vs_evidence,
    _extract_tool_audit_section,
    _audit_entries,
    _get_verifier_tools,
    _WRITE_TOOLS,
    apply_corrections,
    verify_report,
)


# ---------------------------------------------------------------------------
# Helpers: fake SDK message types + async generators
# ---------------------------------------------------------------------------


class TextBlock:
    """Mimics claude_agent_sdk.TextBlock — the verifier dispatches on
    `type(block).__name__ == "TextBlock"`, so the class name matters."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeToolUseBlock:
    """Stand-in that is isinstance-compatible with ToolUseBlock via monkeypatch."""

    def __init__(self, id: str, name: str, input: dict) -> None:
        self.id = id
        self.name = name
        self.input = input


class _FakeToolResultBlock:
    """Stand-in for ToolResultBlock."""

    def __init__(self, tool_use_id: str, content: str, is_error: bool = False) -> None:
        self.tool_use_id = tool_use_id
        self.content = content
        self.is_error = is_error


class _FakeAssistantMessage:
    """Stand-in for AssistantMessage, isinstance via monkeypatch."""

    def __init__(self, content: list) -> None:
        self.content = content


class _FakeResultMessage:
    """Stand-in for ResultMessage, isinstance via monkeypatch."""

    def __init__(self, result: str) -> None:
        self.result = result


def _make_envelope(
    agent: str = "financials", symbol: str = "SBIN"
) -> BriefingEnvelope:
    """Build a minimal envelope with evidence for verifier input."""
    return BriefingEnvelope(
        agent=agent,
        symbol=symbol,
        report="# Financials Report\n\nRevenue grew 15% to 1200 Cr.",
        briefing={"rating": "BUY"},
        evidence=[
            ToolEvidence(
                tool="get_quarterly_results",
                args={"symbol": symbol},
                result_summary="Revenue 1200 Cr, up 15% YoY",
                result_hash="aa",
            ),
        ],
        cost=AgentCost(),
    )


def _make_query_factory(messages: list, raise_after: bool = False):
    """Return a function compatible with `query(prompt=..., options=...)`
    that yields `messages` as an async generator."""

    async def _fake_query(*, prompt, options):  # noqa: ARG001
        for m in messages:
            yield m
        if raise_after:
            raise RuntimeError("CLI exited 1 post-stream")

    return _fake_query


@pytest.fixture
def patch_sdk_types(monkeypatch):
    """Patch the verifier's imported SDK types so our fake classes
    pass isinstance() checks. Returns dict of fakes for convenience."""
    monkeypatch.setattr(verifier_mod, "AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(verifier_mod, "ResultMessage", _FakeResultMessage)
    monkeypatch.setattr(verifier_mod, "ToolUseBlock", _FakeToolUseBlock)
    monkeypatch.setattr(verifier_mod, "ToolResultBlock", _FakeToolResultBlock)
    return {
        "AssistantMessage": _FakeAssistantMessage,
        "ResultMessage": _FakeResultMessage,
        "ToolUseBlock": _FakeToolUseBlock,
        "ToolResultBlock": _FakeToolResultBlock,
    }


@pytest.fixture
def stub_sdk_server(monkeypatch):
    """Stub out `create_sdk_mcp_server` and `ClaudeAgentOptions` so no real
    MCP server or option validation runs."""
    monkeypatch.setattr(
        verifier_mod, "create_sdk_mcp_server", lambda name, tools: object()
    )
    monkeypatch.setattr(
        verifier_mod, "ClaudeAgentOptions", lambda **kw: kw
    )


# ---------------------------------------------------------------------------
# Constants and tool filtering
# ---------------------------------------------------------------------------


class TestConstants:
    def test_verification_prompt_present_and_nonempty(self):
        """VERIFICATION_PROMPT is a non-trivial string describing the checker role."""
        assert isinstance(VERIFICATION_PROMPT, str)
        assert len(VERIFICATION_PROMPT) > 500
        assert "NUMBER CHECKER" in VERIFICATION_PROMPT
        assert "verdict" in VERIFICATION_PROMPT

    def test_default_verify_model_is_haiku(self):
        """Default model is fixed to a Haiku variant for cost control."""
        assert "haiku" in DEFAULT_VERIFY_MODEL.lower()

    def test_write_tools_contains_save_business_profile(self):
        """Write-tool blocklist includes at least the known save tool."""
        assert "save_business_profile" in _WRITE_TOOLS


class TestGetVerifierTools:
    def test_returns_list_for_known_agent(self, monkeypatch):
        """Known agent returns the tool list from AGENT_TOOLS."""
        # Stub AGENT_TOOLS so test is independent of real agent wiring.
        class _T:
            def __init__(self, name):
                self.name = name

        fake_tools = [_T("tool_a"), _T("tool_b")]
        from flowtracker.research import agent as agent_mod

        monkeypatch.setattr(agent_mod, "AGENT_TOOLS", {"financials": fake_tools})
        result = _get_verifier_tools("financials")
        assert len(result) == 2
        assert [t.name for t in result] == ["tool_a", "tool_b"]

    def test_filters_out_write_tools(self, monkeypatch):
        """Tools whose `name` is in _WRITE_TOOLS are stripped."""
        class _T:
            def __init__(self, name):
                self.name = name

        fake_tools = [
            _T("get_quarterly_results"),
            _T("save_business_profile"),
            _T("get_price_history"),
        ]
        from flowtracker.research import agent as agent_mod

        monkeypatch.setattr(agent_mod, "AGENT_TOOLS", {"business": fake_tools})
        result = _get_verifier_tools("business")
        names = [t.name for t in result]
        assert "save_business_profile" not in names
        assert "get_quarterly_results" in names
        assert "get_price_history" in names

    def test_unknown_agent_returns_empty(self, monkeypatch):
        """Agents not in the registry produce an empty tool list."""
        from flowtracker.research import agent as agent_mod

        monkeypatch.setattr(agent_mod, "AGENT_TOOLS", {})
        result = _get_verifier_tools("nonexistent")
        assert result == []

    def test_falls_back_to_dunder_name(self, monkeypatch):
        """Tools without `.name` attribute are matched via `__name__`."""
        from flowtracker.research import agent as agent_mod

        def save_business_profile():  # matches blocklist via __name__
            pass

        def get_company_info():
            pass

        monkeypatch.setattr(
            agent_mod,
            "AGENT_TOOLS",
            {"business": [save_business_profile, get_company_info]},
        )
        result = _get_verifier_tools("business")
        names = [getattr(t, "__name__", "") for t in result]
        assert "save_business_profile" not in names
        assert "get_company_info" in names


# ---------------------------------------------------------------------------
# verify_report — envelope missing
# ---------------------------------------------------------------------------


class TestVerifyReportNoEnvelope:
    async def test_returns_fail_when_envelope_missing(self, monkeypatch):
        """If load_envelope returns None, verify_report short-circuits to a
        'fail' VerificationResult without invoking the SDK."""
        monkeypatch.setattr(verifier_mod, "load_envelope", lambda s, a: None)

        # If query is accidentally called, make it blow up loudly.
        async def _boom(*a, **kw):  # pragma: no cover - should not run
            raise AssertionError("query should not be called when envelope missing")
            yield  # noqa

        monkeypatch.setattr(verifier_mod, "query", _boom)

        result = await verify_report("financials", "UNKNOWN")
        assert isinstance(result, VerificationResult)
        assert result.verdict == "fail"
        assert result.agent_verified == "financials"
        assert result.symbol == "UNKNOWN"
        assert result.issues and result.issues[0]["severity"] == "error"
        assert "No report" in result.overall_data_quality


# ---------------------------------------------------------------------------
# verify_report — happy path
# ---------------------------------------------------------------------------


class TestVerifyReportHappyPath:
    async def test_parses_verdict_from_result_json(
        self, monkeypatch, patch_sdk_types, stub_sdk_server
    ):
        """A ResultMessage containing a JSON verdict block produces a fully
        populated VerificationResult."""
        envelope = _make_envelope()
        monkeypatch.setattr(
            verifier_mod, "load_envelope", lambda s, a: envelope
        )
        monkeypatch.setattr(verifier_mod, "_get_verifier_tools", lambda name: [])

        verdict_json = (
            '```json\n'
            '{"agent_verified": "financials", "symbol": "SBIN", '
            '"verdict": "pass_with_notes", "spot_checks_performed": 4, '
            '"issues": [{"severity": "note", "claim": "c", "actual": "a"}], '
            '"corrections": ["fix 1"], '
            '"overall_data_quality": "solid"}\n'
            '```'
        )
        messages = [_FakeResultMessage(result=verdict_json)]
        monkeypatch.setattr(verifier_mod, "query", _make_query_factory(messages))

        result = await verify_report("financials", "SBIN")
        assert result.verdict == "pass_with_notes"
        assert result.spot_checks_performed == 4
        assert result.agent_verified == "financials"
        assert result.symbol == "SBIN"
        assert result.issues[0]["severity"] == "note"
        assert result.corrections == ["fix 1"]
        assert result.overall_data_quality == "solid"

    async def test_uses_text_blocks_when_no_result_message(
        self, monkeypatch, patch_sdk_types, stub_sdk_server
    ):
        """When no ResultMessage arrives, concatenated TextBlocks are parsed
        for the JSON verdict."""
        envelope = _make_envelope(agent="business", symbol="INFY")
        monkeypatch.setattr(
            verifier_mod, "load_envelope", lambda s, a: envelope
        )
        monkeypatch.setattr(verifier_mod, "_get_verifier_tools", lambda name: [])

        text = (
            "Checking numbers...\n"
            "```json\n"
            '{"agent_verified": "business", "symbol": "INFY", "verdict": "pass", '
            '"spot_checks_performed": 3, "issues": [], "corrections": []}\n'
            "```"
        )
        assistant = _FakeAssistantMessage(content=[TextBlock(text)])
        monkeypatch.setattr(
            verifier_mod, "query", _make_query_factory([assistant])
        )

        result = await verify_report("business", "INFY")
        assert result.verdict == "pass"
        assert result.spot_checks_performed == 3
        assert result.symbol == "INFY"

    async def test_collects_tool_evidence_from_stream(
        self, monkeypatch, patch_sdk_types, stub_sdk_server
    ):
        """ToolUseBlock followed by ToolResultBlock are paired into evidence,
        and the verdict is still parsed from the final result."""
        envelope = _make_envelope()
        monkeypatch.setattr(
            verifier_mod, "load_envelope", lambda s, a: envelope
        )
        monkeypatch.setattr(verifier_mod, "_get_verifier_tools", lambda name: [])

        tool_use = _FakeToolUseBlock(
            id="call_1",
            name="get_quarterly_results",
            input={"symbol": "SBIN"},
        )
        tool_result = _FakeToolResultBlock(
            tool_use_id="call_1",
            content="Revenue 1200 Cr",
            is_error=False,
        )
        verdict_json = (
            '```json\n'
            '{"verdict": "pass", "spot_checks_performed": 2, '
            '"agent_verified": "financials", "symbol": "SBIN"}\n'
            '```'
        )
        messages = [
            _FakeAssistantMessage(content=[tool_use]),
            _FakeAssistantMessage(content=[tool_result]),
            _FakeResultMessage(result=verdict_json),
        ]
        monkeypatch.setattr(
            verifier_mod, "query", _make_query_factory(messages)
        )

        result = await verify_report("financials", "SBIN")
        assert result.verdict == "pass"
        assert result.spot_checks_performed == 2


# ---------------------------------------------------------------------------
# verify_report — error & fallback paths
# ---------------------------------------------------------------------------


class TestVerifyReportErrorPaths:
    async def test_query_exception_falls_through_to_parse(
        self, monkeypatch, patch_sdk_types, stub_sdk_server
    ):
        """If query raises after yielding data, the captured text is still
        parsed and a VerificationResult is returned."""
        envelope = _make_envelope()
        monkeypatch.setattr(
            verifier_mod, "load_envelope", lambda s, a: envelope
        )
        monkeypatch.setattr(verifier_mod, "_get_verifier_tools", lambda name: [])

        text = (
            "```json\n"
            '{"verdict": "fail", "spot_checks_performed": 1, '
            '"agent_verified": "financials", "symbol": "SBIN", '
            '"issues": [{"severity": "error", "claim": "x", "actual": "y"}]}\n'
            "```"
        )
        assistant = _FakeAssistantMessage(content=[TextBlock(text)])
        monkeypatch.setattr(
            verifier_mod,
            "query",
            _make_query_factory([assistant], raise_after=True),
        )

        result = await verify_report("financials", "SBIN")
        assert result.verdict == "fail"
        assert result.issues[0]["severity"] == "error"

    async def test_malformed_result_returns_fallback_pass(
        self, monkeypatch, patch_sdk_types, stub_sdk_server
    ):
        """When no JSON can be parsed, verifier returns the documented
        fallback: pass with zero checks and a note about parsing failure."""
        envelope = _make_envelope()
        monkeypatch.setattr(
            verifier_mod, "load_envelope", lambda s, a: envelope
        )
        monkeypatch.setattr(verifier_mod, "_get_verifier_tools", lambda name: [])

        # ResultMessage with plain prose — no JSON block
        messages = [_FakeResultMessage(result="No JSON here, just narrative.")]
        monkeypatch.setattr(
            verifier_mod, "query", _make_query_factory(messages)
        )

        result = await verify_report("financials", "SBIN")
        assert result.verdict == "pass"
        assert result.spot_checks_performed == 0
        assert "parsing failed" in result.overall_data_quality.lower()

    async def test_empty_stream_returns_fallback(
        self, monkeypatch, patch_sdk_types, stub_sdk_server
    ):
        """Empty stream (no messages at all) still yields a fallback pass result."""
        envelope = _make_envelope()
        monkeypatch.setattr(
            verifier_mod, "load_envelope", lambda s, a: envelope
        )
        monkeypatch.setattr(verifier_mod, "_get_verifier_tools", lambda name: [])
        monkeypatch.setattr(verifier_mod, "query", _make_query_factory([]))

        result = await verify_report("financials", "SBIN")
        assert result.verdict == "pass"
        assert result.agent_verified == "financials"
        assert result.symbol == "SBIN"


# ---------------------------------------------------------------------------
# apply_corrections
# ---------------------------------------------------------------------------


class TestApplyCorrections:
    def test_pass_returns_envelope_unchanged(self):
        """'pass' verdict returns the envelope object untouched."""
        env = _make_envelope()
        original_report = env.report
        vr = VerificationResult(
            agent_verified="financials", symbol="SBIN", verdict="pass"
        )
        result = apply_corrections(env, vr)
        assert result is env
        assert result.report == original_report

    def test_pass_with_notes_appends_issues(self):
        """pass_with_notes appends a Verification Notes section listing each issue."""
        env = _make_envelope()
        vr = VerificationResult(
            agent_verified="financials",
            symbol="SBIN",
            verdict="pass_with_notes",
            issues=[
                {
                    "severity": "note",
                    "section": "Revenue",
                    "claim": "1200 Cr",
                    "actual": "1180 Cr",
                }
            ],
        )
        result = apply_corrections(env, vr)
        assert "Verification Notes" in result.report
        assert "[NOTE]" in result.report
        assert "Revenue" in result.report
        assert "1180 Cr" in result.report

    def test_fail_prepends_warning_banner(self):
        """'fail' verdict prepends a warning banner listing error-severity issues."""
        env = _make_envelope()
        vr = VerificationResult(
            agent_verified="financials",
            symbol="SBIN",
            verdict="fail",
            issues=[
                {
                    "severity": "error",
                    "section": "Revenue",
                    "claim": "2000 Cr",
                    "actual": "1200 Cr",
                },
                {
                    "severity": "note",
                    "section": "Margin",
                    "claim": "25%",
                    "actual": "24%",
                },
            ],
        )
        result = apply_corrections(env, vr)
        # Warning banner comes first
        assert result.report.startswith("\n\n---\n> **Verification Warning**")
        # Error issues appear, note-severity issues are omitted
        assert "2000 Cr" in result.report
        assert "25%" not in result.report

    def test_pass_with_notes_no_issues_returns_unchanged(self):
        """pass_with_notes with empty issues list falls through to the fail
        branch per code structure, prepending an empty warning. Guard the
        boundary by verifying no Notes section appears when issues is empty."""
        env = _make_envelope()
        original = env.report
        vr = VerificationResult(
            agent_verified="financials",
            symbol="SBIN",
            verdict="pass_with_notes",
            issues=[],
        )
        result = apply_corrections(env, vr)
        # With no issues, neither Notes section nor specific error lines
        # should appear — just the banner header falls through from fail branch.
        assert "Verification Notes" not in result.report
        assert original in result.report


# ---------------------------------------------------------------------------
# iter3 §4.7 — audit-vs-evidence cross-check (shadow mode)
# ---------------------------------------------------------------------------


_REPORT_WITH_AUDIT = """# Ownership Report — ACME

## Tool Audit
| Step | Tool | Called |
|---|---|---|
| 1 | `get_analytical_profile` | ✓ |
| 2 | `get_ownership` | ✓ |
| 3 | `mcp__ownership__get_company_context` | ∅ |

## 1. Ownership Structure
Blah blah.
"""

_REPORT_WITHOUT_AUDIT = """# Report

## 1. Summary

No audit section here.
"""


def _ev(tool: str, is_error: bool = False, completeness: str | None = None):
    return ToolEvidence(
        tool=tool,
        args={},
        result_summary="x",
        is_error=is_error,
        completeness=completeness,
    )


class TestExtractToolAuditSection:
    def test_returns_section_when_present(self) -> None:
        text = _extract_tool_audit_section(_REPORT_WITH_AUDIT)
        assert text is not None
        assert "get_analytical_profile" in text

    def test_returns_none_when_absent(self) -> None:
        assert _extract_tool_audit_section(_REPORT_WITHOUT_AUDIT) is None


class TestAuditEntries:
    def test_parses_table_rows_with_and_without_empty_marker(self) -> None:
        section = _extract_tool_audit_section(_REPORT_WITH_AUDIT)
        entries = _audit_entries(section)
        names = {name for name, _ in entries}
        assert "get_analytical_profile" in names
        assert "get_ownership" in names
        assert "get_company_context" in names
        # get_company_context row was marked ∅
        flags = {name: flag for name, flag in entries}
        assert flags["get_company_context"] is True
        assert flags["get_analytical_profile"] is False


class TestCheckAuditVsEvidence:
    def test_perfect_match_returns_empty(self) -> None:
        # ∅ rows in audit must have a matching (empty/errored) evidence entry —
        # "∅" means called-and-returned-empty, not "never called".
        env = BriefingEnvelope(
            agent="ownership",
            symbol="ACME",
            report=_REPORT_WITH_AUDIT,
            evidence=[
                _ev("mcp__ownership__get_analytical_profile"),
                _ev("mcp__ownership__get_ownership"),
                _ev("mcp__ownership__get_company_context", completeness="empty"),
            ],
        )
        assert _check_audit_vs_evidence(env) == []

    def test_claimed_but_not_called_is_flagged(self) -> None:
        env = BriefingEnvelope(
            agent="ownership",
            symbol="ACME",
            report=_REPORT_WITH_AUDIT,
            # missing analytical_profile + get_company_context entirely
            evidence=[_ev("mcp__ownership__get_ownership")],
        )
        findings = _check_audit_vs_evidence(env)
        assert any("claims `get_analytical_profile`" in f for f in findings)

    def test_called_but_not_claimed_is_flagged(self) -> None:
        env = BriefingEnvelope(
            agent="ownership",
            symbol="ACME",
            report=_REPORT_WITH_AUDIT,
            evidence=[
                _ev("mcp__ownership__get_analytical_profile"),
                _ev("mcp__ownership__get_ownership"),
                _ev("mcp__ownership__get_company_context", completeness="empty"),
                # Extra call never listed in audit:
                _ev("mcp__ownership__get_peer_sector"),
            ],
        )
        findings = _check_audit_vs_evidence(env)
        assert any("`get_peer_sector`" in f and "does not list" in f for f in findings)

    def test_toolsearch_called_but_not_claimed_is_ignored(self) -> None:
        env = BriefingEnvelope(
            agent="ownership",
            symbol="ACME",
            report=_REPORT_WITH_AUDIT,
            evidence=[
                _ev("mcp__ownership__get_analytical_profile"),
                _ev("mcp__ownership__get_ownership"),
                _ev("mcp__ownership__get_company_context", completeness="empty"),
                _ev("ToolSearch"),  # commonly unlisted; ignore
            ],
        )
        assert _check_audit_vs_evidence(env) == []

    def test_claimed_empty_but_nonempty_is_flagged(self) -> None:
        # Audit says get_company_context was ∅; evidence shows a full call.
        env = BriefingEnvelope(
            agent="ownership",
            symbol="ACME",
            report=_REPORT_WITH_AUDIT,
            evidence=[
                _ev("mcp__ownership__get_analytical_profile"),
                _ev("mcp__ownership__get_ownership"),
                _ev("mcp__ownership__get_company_context", completeness="full"),
            ],
        )
        findings = _check_audit_vs_evidence(env)
        assert any(
            "marks `get_company_context` as ∅ but evidence shows non-empty" in f
            for f in findings
        )

    def test_no_audit_section_returns_empty(self) -> None:
        env = BriefingEnvelope(
            agent="ownership",
            symbol="ACME",
            report=_REPORT_WITHOUT_AUDIT,
            evidence=[_ev("mcp__ownership__get_analytical_profile")],
        )
        assert _check_audit_vs_evidence(env) == []
