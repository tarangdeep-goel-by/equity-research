# Gemini Architecture Review — Post P-4

**Date:** 2026-04-03
**Model:** gemini-2.5-pro (thinking mode)
**Context:** Full V2 architecture review after P-4 tool consolidation + prompt optimization

## Overall Verdict

"Purpose-built race car" — upgraded from "Ferrari engine, confusing steering wheel"

## What's Great

1. **Tool Abstraction (Macro-Tools):** "The single best change you've made." Dramatically simplifies agent decision space. Instead of choosing between get_quarterly_results and get_annual_financials, the agent reasons: "I need financials, so I'll use get_fundamentals."

2. **Dynamic BFSI Injection:** "Superb architectural pattern." Clean base prompts + centralized specialist logic. Scalable, maintainable, computationally efficient.

3. **Prompt Engineering Discipline:** 81% reduction is "not just a cost saving; it's a clarity gain." New structure (Persona → Mission → Workflow → Sections → Rules) is best practice.

4. **Pre-computation Layer:** Weekly cron → analytical_snapshots → get_analytical_profile. "Massive optimization" — reduces latency, ensures consistency.

## Critical Issues

### 1. Verifier Logic — Still Flawed
Haiku verifying Sonnet is backwards. "Like asking a high-school student to proofread a PhD thesis."

**Recommendations:**
- A) Invert the stack: Haiku for draft, Sonnet for review
- B) Peer review model: Risk agent critiques Valuation output
- C) **Re-scope verifier to fact-checking only**: take report + tool evidence, check factual consistency ("report claims ROCE is 25%, does get_fundamentals confirm this?"). This is a task Haiku CAN do well. Let Synthesis handle logical consistency.

### 2. Macro-Tool Multi-Section Calls
Agent needing quarterly_results AND annual_financials from get_fundamentals makes 2 separate tool calls. Doubles turn count and latency.

**Fix:** Accept a list of sections: `get_fundamentals(symbol='RELIANCE', section=['quarterly_results', 'annual_financials'])`. Update prompts to encourage batching.

### 3. Synthesis Over-Reliance on Scores
Verdict Calibration ("Strong BUY >80%") is dangerously deterministic. Institutional research is about narrative and weighing conflicting evidence, not plugging numbers into a formula.

**Fix:** Soften calibration. Add rule: "If qualitative evidence from briefings contradicts the composite score, you MUST highlight the discrepancy and base your verdict on the qualitative evidence, explaining why you override the score."

### 4. Missing Analytical Dimension — News/Narrative/Sentiment
Current system is entirely based on structured, historical data. Missing: contract wins, plant shutdowns, negative media coverage, sentiment shifts, management commentary beyond concalls.

**Recommendation:** Create a NarrativeAgent with WebSearch/WebFetch. Mission: "Understand prevailing market narrative, recent news flow, management commentary. Is the story changing?"

### 5. Orchestrator Pre-Analysis Creates "Split Brain"
Python detects cross-signals AND Synthesis agent detects them = redundancy + potential conflict.

**Fix:** Reframe Python output as "Suggested Signals" — pass as hints, not facts. E.g., "Orchestrator analysis suggests a potential CONVERGENCE signal... Please investigate and validate."

### 6. Data Freshness Opacity
analytical_snapshots has no last_computed_ts. Agent can't tell if pre-computed data is stale (dangerous day after quarterly results).

**Fix:** Add last_computed_ts to analytical_snapshots and include in get_analytical_profile output. Prompt agents (Risk, Financials) to check timestamp.

## Additional Recommendations

### Generalize BFSI Pattern → SectorProfileInjector
Create sector-specific injections for IT_SERVICES, PHARMA, INDUSTRIALS, etc. Proves architecture scalability.

### Small-Cap Persona Injection
When market_cap < 5000 Cr, inject extra skepticism into Risk agent persona.

### Human Feedback Loop
Mechanism for users to rate reports and highlight errors. Store feedback for continuous prompt improvement.

### Prompt Length Assessment
~900 words per agent is "the sweet spot" — high signal-to-noise ratio. "Do not add more unless absolutely necessary."

## P-5 Priorities (Gemini's Recommendation)
1. Fix verification/synthesis loop
2. Introduce NarrativeAgent
3. Multi-section tool calls + data freshness timestamps
4. Generalize sector injection pattern
