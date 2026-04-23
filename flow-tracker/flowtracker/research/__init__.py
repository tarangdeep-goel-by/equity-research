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
