"""Regression guard — importing flowtracker.research must set
CLAUDE_CODE_STREAM_CLOSE_TIMEOUT so the Claude Agent SDK's initialize
handshake has >60s to complete.

Context: 2026-04-23 K1-narrow run showed specialists (ADANIENT business,
HINDUNILVR valuation) deterministically failing at 60s with
"Control request timeout: initialize" because the SDK reads this env var
from the *parent* Python process, not from ClaudeAgentOptions.env."""
from __future__ import annotations

import importlib
import os


def test_research_package_sets_initialize_timeout():
    """Importing flowtracker.research must elevate the initialize-timeout env var."""
    # Unset first so we can verify the module is the one setting it
    os.environ.pop("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", None)

    import flowtracker.research  # noqa: F401 — import for side effect
    importlib.reload(flowtracker.research)

    val = os.environ.get("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT")
    assert val is not None, "research package did not set CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"
    assert int(val) >= 120000, (
        f"initialize timeout is {val}ms; must be ≥120000ms to survive concurrent "
        f"specialist starts (60s default caused 2026-04-23 ADANIENT/HINDUNILVR regressions)"
    )


def test_existing_env_value_is_preserved():
    """setdefault semantics — caller-provided value wins over module default."""
    os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"] = "600000"

    import flowtracker.research
    importlib.reload(flowtracker.research)

    assert os.environ["CLAUDE_CODE_STREAM_CLOSE_TIMEOUT"] == "600000"

    # cleanup for next test
    os.environ.pop("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", None)
