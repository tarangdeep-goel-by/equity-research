# Gemini Architecture Review — Post P-5

**Date:** 2026-04-03
**Model:** gemini-3.1-pro-preview (thinking mode)
**Context:** Full architecture review after P-5 agent intelligence & robustness

## Overall Grade: A-

"Shifted from a fragile, rigid pipeline into a resilient, probabilistic research engine."

## P-5 Execution Grades

| Item | Grade | Notes |
|------|-------|-------|
| 1. Synthesis narrative-first + orchestrator demotion | A+ | "Leveraging LLM for what it's good at: synthesizing qualitative text" |
| 2. Verifier re-scoped to fact-checking | A | "Only correct way to use smaller model to check larger one" |
| 3. Multi-section tool calls | A | Reduces tokens, cuts API round-trips, speeds parallel execution |
| 4. Graceful degradation | A+ | "Enterprise-grade system design" |
| 5. Market-cap personas | B+ | Good but hardcoded thresholds are brittle (₹4,900 vs ₹5,100 Cr) |
| 6. Comparison V2 prompt | (not separately graded) | Halving prompt size is a major win |

## New Issues Identified

### Issue 1: The "Lazy All" Trap
LLMs may default to `section="all"` instead of targeted lists, blowing up context windows.
**Fix:** Deprecate "all" for agents — force explicit section lists.

### Issue 2: Verification Loop Trap
If specialist fails verification because underlying data is missing, it'll loop 8 times pointlessly.
**Fix:** ONE retry only. If 2nd attempt fails → mark `status="failed"`, let Graceful Degradation handle it.

### Issue 3: Why Opus for Synthesis?
Claude 3.5 Sonnet outperforms Opus in logical synthesis, guideline adherence, and formatting — and is faster/cheaper.
**Recommendation:** Drop Opus for synthesis.

## Prompt Quality Assessment

**Strengths:**
- "No Orphan Numbers" & "First-Mention Definitions" = brilliant prompt engineering maxims
- Persona fidelity: "Seen IL&FS, Yes Bank blow-ups" roots model in local context
- Under 1,000 words per specialist = exact sweet spot

**The "Agent vs. Pipeline" Paradox:**
If we already know exactly which tools and sections an agent needs (hardcoded in workflow), why make the agent spend tokens calling tools? Pre-fetch standard sections, pass as context_payload. Only give tools for exploratory deep-dives.

## Orchestration Notes

**Confidence Caps Need Weighting:**
Not all agents are equal. If sector agent fails → 60% cap is fine. If financials or risk agent fails → should abort or cap at strict HOLD/UNVERIFIED. Weight agent failures by severity.

## P-6 Priorities (Gemini's Recommendation)

1. **Transition to Claude 3.5 Sonnet for Synthesis** — Drop Opus. Sonnet adheres to Narrative Primacy better, faster, cheaper.
2. **Data Freshness Opacity** (P-4 carryover) — Inject `as_of_date` and `latest_quarter_reported` into every tool return payload.
3. **Build NarrativeAgent** — Split Synthesis (analytical conclusions) from Narrative (formatted report). Synthesis = JSON-heavy CIO decisions. Narrative = copywriter rendering.
4. **Kill Verifier Retry Loop** — Restrict to max 2 retries. Failed twice → mark failed, let Graceful Degradation handle.
5. **Pre-Fetch Refactor** (optional, for scale) — Move from agent-fetches-data to data-augmented pipeline. Pre-fetch standard sections, pass as context. Tools only for dynamic/follow-up queries.

## Follow-Up Clarifications

### Opus 4 vs Sonnet 4 for Synthesis
**Corrected:** With Claude 4 family (Opus 4 = stronger reasoner, Sonnet 4 = fast parallel), keeping Opus 4 for synthesis is correct. It runs ONCE per company at the end as the final bottleneck/decision-maker. Pay the premium where it matters most.

### Hybrid Pre-Fetch ("Core + Explore")
Don't strip tools entirely — that kills the detective capability.
- **Core:** Orchestrator pre-fetches `analytical_profile` + baseline `fundamentals` (needed by 5/7 agents), inject as `<baseline_data>` in user prompt
- **Explore:** Keep tools enabled but instruct: "Do NOT use tools for standard data. ONLY use tools if you spot anomalies and need to investigate deeper."
- Saves 1-2 API roundtrips per agent (~30-40% latency reduction)

### Hiding "all" from Agents
Keep `"all"` in Python function (CLI works). Remove it from the Tool JSON Schema passed to Claude — LLM won't know "all" exists, forced to be precise.

### Weighted Agent Failure Tiers
| Tier | Agents | Weight | If Failed |
|------|--------|--------|-----------|
| 1: Dealbreakers | Risk, Financials, Valuation | Critical | Cap HOLD, 40% confidence, lead with disclaimer |
| 2: Core Context | Business, Ownership | Major | Cap 65% confidence |
| 3: Enhancers | Sector, Technical | Minor | Cap 85% confidence |

Pass structured payload: `failed_agents: [{"name": "risk", "tier": 1}]`

### Shared Preamble Token Cost
**Don't change.** 439 words = ~600 tokens × 7 agents = 4,200 tokens = fraction of a cent. Plus Claude Prompt Caching hits on identical preamble text across all agents, speeding up TTFT.

## Unresolved from P-4

- ❌ Data Freshness Opacity — still not addressed
- ⏳ Generalize BFSI → SectorProfileInjector — not yet
- ⏳ Human Feedback Loop — not yet
