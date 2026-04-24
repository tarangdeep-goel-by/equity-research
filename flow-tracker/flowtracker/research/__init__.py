"""Research report generation package."""

import os as _os

# Raise Claude Agent SDK's initialize-control-request timeout from the 60s
# default to 5 minutes. The SDK reads this env var from the *parent* process
# (claude_agent_sdk._internal.client: initialize_timeout_ms = int(os.environ.
# get("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", "60000"))) and uses it for the
# initialize handshake that happens before the first AssistantMessage.
#
# The env name is misleading — it's reused as initialize_timeout inside
# Query.initialize() (_internal/query.py:150-160) — but 60s is too tight
# when the specialist has many MCP tools and the subprocess is competing
# with other SDK subprocesses during a research run. Symptom: "Control
# request timeout: initialize" cascading across retries, all specialist
# output dropped, report graded as ERR (2026-04-23 K1-narrow: ADANIENT and
# HINDUNILVR both died this way on 4 retries each).
#
# Passing CLAUDE_CODE_STREAM_CLOSE_TIMEOUT via ClaudeAgentOptions.env only
# affects the subprocess environment — it does NOT influence the parent
# process's initialize_timeout because the SDK reads os.environ on the
# parent side. So the setdefault has to happen at module import time on
# the Python process — subprocess env is already being set at each call
# site for its own reasons (stream-close behaviour in the CLI itself).
_os.environ.setdefault("CLAUDE_CODE_STREAM_CLOSE_TIMEOUT", "300000")


# ---------------------------------------------------------------------------
# Suppress SDK's post-success "Fatal error in message reader: Command failed
# with exit code 1" noise.
#
# See https://github.com/anthropics/claude-agent-sdk-python/issues/800 — the
# bundled CLI occasionally exits non-zero during shutdown even though a
# successful ResultMessage (subtype='success', is_error=False) already
# landed. The SDK's message reader logs this at ERROR with a hard-coded
# stderr literal "Check stderr output for details" (the actual subprocess
# stderr is never captured into the exception), making every extractor run
# look catastrophic in logs.
#
# Our _call_claude wrappers in concall_extractor / annual_report_extractor
# already handle this correctly — they return the captured content when
# the exception fires post-content. The log line is pure noise. Filter it
# out at the SDK logger, but only the exact post-exit message so genuine
# stream errors still surface.
# ---------------------------------------------------------------------------
import logging as _logging


class _PostExitMessageReaderFilter(_logging.Filter):
    """Drop the known-spurious post-success 'Fatal error in message reader'."""

    _PREFIX = "Fatal error in message reader: Command failed with exit code"

    def filter(self, record: _logging.LogRecord) -> bool:
        msg = record.getMessage()
        if record.levelno >= _logging.ERROR and msg.startswith(self._PREFIX):
            # Demote to DEBUG so it's still captured at debug log level,
            # but doesn't pollute default runs.
            record.levelno = _logging.DEBUG
            record.levelname = "DEBUG"
        return True


_logging.getLogger("claude_agent_sdk._internal.query").addFilter(
    _PostExitMessageReaderFilter()
)
