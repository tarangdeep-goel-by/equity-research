"""Tests for flowtracker/research/agent.py — focus on _run_specialist retry.

Covers SDK subprocess hygiene Fix 3: _run_specialist retries the query()
subprocess when it crashes with no/negligible content captured, but preserves
partial output (> PARTIAL_OUTPUT_BYTES) on the existing graceful-degradation
path.

Mocks `claude_agent_sdk.query` so no real SDK subprocess spawns.
"""

from __future__ import annotations

import pytest

from flowtracker.research import agent as agent_mod


# ---------------------------------------------------------------------------
# Helpers: fake SDK message types mirroring the verifier test patterns
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    """type(block).__name__ == 'TextBlock' is what _run_specialist checks."""

    def __init__(self, text: str) -> None:
        self.text = text


# Ensure the type name matches what the specialist code checks.
_FakeTextBlock.__name__ = "TextBlock"


class _FakeAssistantMessage:
    def __init__(self, content: list) -> None:
        self.content = content
        # _run_specialist calls getattr(message, "usage", None)
        self.usage = {"input_tokens": 100, "output_tokens": 50}


class _FakeResultMessage:
    def __init__(self, result: str) -> None:
        self.result = result
        self.total_cost_usd = 0.01
        self.usage = {"input_tokens": 100, "output_tokens": 50}


def _make_query(
    attempts_behavior: list,
):
    """Build a fake `query()` that consults a per-call list of behaviors.

    Each entry is one of:
      - ("yield", [messages])       — yield messages cleanly
      - ("raise_empty", exc)        — raise immediately (no messages yielded)
      - ("yield_then_raise", [messages], exc) — yield messages then raise
    """
    call_index = {"i": 0}

    async def _fake_query(*, prompt, options):  # noqa: ARG001
        idx = call_index["i"]
        call_index["i"] += 1
        if idx >= len(attempts_behavior):
            raise AssertionError(
                f"_fake_query called {idx + 1} times but only "
                f"{len(attempts_behavior)} behaviors configured"
            )
        behavior = attempts_behavior[idx]
        kind = behavior[0]
        if kind == "yield":
            for m in behavior[1]:
                yield m
            return
        if kind == "raise_empty":
            # Generator function needs at least one yield-or-raise-from-body
            # statement; the raise below is fine. But asyncgen needs a yield
            # statement somewhere — use unreachable yield to keep Python happy.
            if False:  # pragma: no cover
                yield None
            raise behavior[1]
        if kind == "yield_then_raise":
            for m in behavior[1]:
                yield m
            raise behavior[2]
        raise AssertionError(f"unknown behavior kind: {kind}")

    return _fake_query, call_index


@pytest.fixture
def patch_sdk_types(monkeypatch):
    """Make the fake AssistantMessage / ResultMessage pass isinstance checks."""
    monkeypatch.setattr(agent_mod, "AssistantMessage", _FakeAssistantMessage)
    monkeypatch.setattr(agent_mod, "ResultMessage", _FakeResultMessage)


@pytest.fixture
def stub_heavy_deps(monkeypatch):
    """Stub the heavy post-query helpers so the test isolates the retry loop:
      - ClaudeAgentOptions: skip validation
      - create_sdk_mcp_server: no real MCP
      - _extract_briefing: return empty dict (Phase 2 isn't under test)
      - save_envelope: no-op (don't touch disk)
      - asyncio.sleep inside agent.py: no-op (instant retries)
    """
    monkeypatch.setattr(agent_mod, "ClaudeAgentOptions", lambda **kw: type("Opts", (), kw)())
    monkeypatch.setattr(agent_mod, "create_sdk_mcp_server", lambda name, tools: object())

    async def _fake_extract_briefing(name, symbol, report_text):
        return {}

    monkeypatch.setattr(agent_mod, "_extract_briefing", _fake_extract_briefing)
    monkeypatch.setattr(agent_mod, "save_envelope", lambda env: None)

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr(agent_mod.asyncio, "sleep", _no_sleep)


# ---------------------------------------------------------------------------
# _run_specialist retry behaviour
# ---------------------------------------------------------------------------


class TestRunSpecialistRetry:
    @pytest.mark.asyncio
    async def test_run_specialist_retries_on_subprocess_crash(
        self, patch_sdk_types, stub_heavy_deps, monkeypatch
    ):
        """Two consecutive crashes with no content → third attempt succeeds.

        Expect 3 query() invocations and a populated envelope.
        """
        good_messages = [
            _FakeAssistantMessage([_FakeTextBlock("# Heading\n\nBody text here.")]),
            _FakeResultMessage("# Heading\n\nBody text here."),
        ]
        fake_query, counter = _make_query([
            ("raise_empty", Exception("Command failed with exit code 1")),
            ("raise_empty", Exception("Command failed with exit code 1")),
            ("yield", good_messages),
        ])
        monkeypatch.setattr(agent_mod, "query", fake_query)

        envelope, trace = await agent_mod._run_specialist(
            name="business",
            symbol="TESTCO",
            system_prompt="test prompt",
            tools=[],  # skip MCP server branch
            max_turns=1,
            max_budget=0.10,
            model="claude-sonnet-4-6",
        )

        # Three attempts were made (2 crashes + 1 success).
        assert counter["i"] == 3
        # Envelope has real content from the successful attempt.
        assert len(envelope.report) > 0
        assert "Body text here." in envelope.report
        assert trace.status == "success"
        # Retry telemetry recorded the 2 retries.
        subprocess_retries = [r for r in trace.retries if r.cause == "subprocess_crash"]
        assert len(subprocess_retries) == 2

    @pytest.mark.asyncio
    async def test_run_specialist_preserves_partial_output(
        self, patch_sdk_types, stub_heavy_deps, monkeypatch
    ):
        """If the SDK raises AFTER emitting >PARTIAL_OUTPUT_BYTES of content,
        _run_specialist must NOT retry — it keeps the partial output (existing
        graceful-degradation behaviour)."""
        # Build >400 bytes of content so retry is suppressed.
        big_text = "# Partial Report\n\n" + ("some analytical content. " * 40)
        assert len(big_text) > agent_mod.PARTIAL_OUTPUT_BYTES

        partial_stream = [
            _FakeAssistantMessage([_FakeTextBlock(big_text)]),
        ]
        fake_query, counter = _make_query([
            ("yield_then_raise", partial_stream, Exception("Command failed with exit code 1")),
        ])
        monkeypatch.setattr(agent_mod, "query", fake_query)

        envelope, trace = await agent_mod._run_specialist(
            name="business",
            symbol="TESTCO",
            system_prompt="test prompt",
            tools=[],
            max_turns=1,
            max_budget=0.10,
            model="claude-sonnet-4-6",
        )

        # Only one attempt — no retry because content was captured.
        assert counter["i"] == 1
        # Partial content preserved.
        assert "Partial Report" in envelope.report
        # No subprocess_crash retry events recorded.
        subprocess_retries = [r for r in trace.retries if r.cause == "subprocess_crash"]
        assert subprocess_retries == []

    @pytest.mark.asyncio
    async def test_run_specialist_gives_up_after_all_retries(
        self, patch_sdk_types, stub_heavy_deps, monkeypatch
    ):
        """If every attempt crashes with no content → agent_status == 'failed'
        and four attempts were made (1 initial + 3 retries)."""
        fake_query, counter = _make_query([
            ("raise_empty", Exception("Command failed with exit code 1")),
            ("raise_empty", Exception("Command failed with exit code 1")),
            ("raise_empty", Exception("Command failed with exit code 1")),
            ("raise_empty", Exception("Command failed with exit code 1")),
        ])
        monkeypatch.setattr(agent_mod, "query", fake_query)

        envelope, trace = await agent_mod._run_specialist(
            name="business",
            symbol="TESTCO",
            system_prompt="test prompt",
            tools=[],
            max_turns=1,
            max_budget=0.10,
            model="claude-sonnet-4-6",
        )

        # 1 initial + 3 retries = 4 attempts.
        assert counter["i"] == 4
        # Downstream code overrides "failed" → "empty" when no report_text
        # remains, so accept either terminal status.
        assert trace.status in ("failed", "empty")
        assert envelope.report == ""
        subprocess_retries = [r for r in trace.retries if r.cause == "subprocess_crash"]
        assert len(subprocess_retries) == 3


class TestSpecialistOptionsIsolation:
    """_run_specialist and _extract_briefing must construct ClaudeAgentOptions
    with setting_sources=[""] and plugins=[] to isolate their subprocesses
    from user hooks/plugins/skills.

    [""] (not []) is the SDK #794 workaround — empty list is falsy and the
    --setting-sources flag never reaches the CLI, letting
    ~/.claude/settings.json hooks leak in.
    https://github.com/anthropics/claude-agent-sdk-python/issues/794
    """

    def test_setting_sources_workaround_in_run_specialist(self):
        import inspect

        src = inspect.getsource(agent_mod._run_specialist)
        assert 'setting_sources=[""]' in src
        assert "setting_sources=[]" not in src
        assert "plugins=[]" in src

    def test_setting_sources_workaround_in_extract_briefing(self):
        import inspect

        src = inspect.getsource(agent_mod._extract_briefing)
        assert 'setting_sources=[""]' in src
        assert "setting_sources=[]" not in src
        assert "plugins=[]" in src
