# Agent prompt-cache control — investigation notes

**Date:** 2026-04-16
**Context:** After Tier-3 telemetry landed (PR #8), the SBIN BFSI eval surfaced 43 turns producing 407k of `cache_creation_input_tokens` against 1.86M of `cache_read_input_tokens` (hit rate 82.1%). Unit-break analysis showed only ~82k of unique new content was written — the remaining ~325k is the same volatile per-turn framing being re-cached at each AssistantMessage boundary. Question: can we tell Anthropic's cache *which* blocks to retain long-term so the volatile bits stop evicting stable content?

## SDK finding — cache_control is not reachable from ClaudeAgentOptions

Investigated `claude-agent-sdk>=0.1.56` (pinned) and `0.1.59` (latest as of 2026-04-13).

- `ClaudeAgentOptions` has **no** `cache_control`, `extra_body`, or `extra_headers` field.
- The SDK does **not** call the Anthropic Python SDK — it wraps the `claude` CLI subprocess via `SubprocessCLITransport`. All HTTP traffic happens inside the CLI; whatever cache_control the CLI applies is opaque to Python callers.
- Only cache-adjacent knob available: `system_prompt={"type": "preset", "preset": "claude_code", "exclude_dynamic_sections": True}` (v0.1.57+). This strips per-user dynamic sections (cwd, git status, auto-memory) from the system prompt into the first user message — a *cross-user* cache optimisation. We use raw-string system prompts (`flowtracker/research/agent.py:520`), not presets, so this knob doesn't apply.

## Workaround options

| # | Approach | Effort | Risk | Expected benefit |
|---|---|---|---|---|
| A | Upgrade to SDK preset + `exclude_dynamic_sections=True` | small | low | ~zero (we're single-user; no cross-user pollution to strip) |
| B | `options.extra_args = {...}` — pass CLI flags | unknown | unknown | speculative; not documented |
| C | Subclass `Transport`, intercept the JSON envelope sent to the CLI, inject `cache_control: {"type": "ephemeral"}` on stable system/tools blocks | ~3-4h | medium (breaks on SDK upgrades) | unknown — still requires the CLI to honour injected markers |
| D | File a feature request with Anthropic for `ClaudeAgentOptions.cache_control_blocks` | external | external | right answer long-term |

## Recommendation

**Defer.** The 82.1% hit rate we observe is already respectable, and the cost_efficiency F grade from the SBIN eval was driven by **43 turns** (prompt/agent-level concern) — not cache inefficiency. Turn count reduction is the higher-leverage lever. If total cost starts becoming problematic at scale (many concurrent agents, nightly matrix), revisit option C or escalate to Anthropic.

## Actionable win from the same investigation

Added an explicit `Cache hit rate: XX.X%` line to the `format_agent_evidence()` output (`autoeval/evaluate.py`). Gemini's `cost_efficiency` rubric now has a direct number to read instead of deriving it from the four raw token counts. Reduces grade variance and makes the rubric thresholds (A ≥70%, B+ 50-70%, C 30-50%, F <30%) verifiable without math.

## Out of scope for this ticket

- Extending `_tool_result_cache` (tools.py) to persist across agents in a pipeline run
- Disk-backed `FundClient` yfinance cache (cross-session TTL)
- Screener client HTTP cache keyed on (symbol, endpoint)

These are separate cache layers (tool-result, HTTP) with their own ROI; documented here so the list isn't lost.
