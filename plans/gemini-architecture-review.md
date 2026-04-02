# Gemini Architecture Review — Full Multi-Agent Pipeline

> Reviewed: 2026-04-02 by Gemini 3.1 Pro
> Context: Post P-2 implementation (67 tools, 7 agents + synthesis + verification)

## Executive Verdict

Data foundation is magnificent. Pre-extracting concalls into structured JSON and building an expansive, multi-source SQLite database (especially including Indian-specifics like promoter pledge, delivery trends, and MF flows) puts you miles ahead of generic AI wrappers.

However, the execution layer — specifically the cognitive load on agents and prompt lengths — is bottlenecking the data layer. Agents are asked to do too much at once, reading too many instructions, with too many tools. Furthermore, the product positioning has a fundamental contradiction.

## A) Architecture & Flow

### What's Great
- Parallel execution saves massive time
- Programmatic cross-signals (detecting convergence/divergence before synthesis) is an elite-level architectural decision. Prevents Synthesis agent from hallucinating connections
- Concall JSON pre-extraction is a masterstroke for token efficiency and accuracy

### What's Broken
- **Verification Loop Danger:** Using Haiku 4.5 to verify Sonnet 4.6's math/formulas is a mistake. Haiku is less capable. It will either false-flag correct data or miss hallucinations. If Haiku fails Sonnet, you risk infinite loop of re-runs.
- **Overlap:** Financial and Valuation agents stepping on each other's toes (DCF relies entirely on Financials). Risk and Financial overlap on forensic accounting (Earnings Quality, M-Score).

### Directives
1. **Programmatic Verification:** Don't use LLMs to check math. Write Python scripts to verify formulas (e.g., Assets = Liabilities + Equity). Use Haiku only to check claim support (e.g., "Did the agent invent a quote?"). Hard circuit breaker: Max 1 retry per agent.
2. **Redefine Agent Boundaries:**
   - Financial Agent: Strictly historical/present performance (What happened?)
   - Valuation Agent: Strictly forward-looking (What is it worth based on what happened?)

## B) Tool Allocation

### What's Great
- Thought of every conceivable angle. Inclusion of `bfsi_metrics` and `delivery_trend` proves understanding of Indian market.

### What's Broken
- **Cognitive Collapse:** 33 tools (Financial) or 30 tools (Valuation) is an anti-pattern. Even Sonnet will suffer from "tool paralysis" — hallucinating tool names, passing wrong arguments, skipping vital tools because schema payload is too massive. 67 tools is too many.

### Directives
1. **Consolidate Tools ("Macro-Tools"):** Combine granular tools into single robust endpoints. Instead of `quarterly_balance_sheet`, `quarterly_cash_flow`, and `quarterly_results`, create one tool: `get_financial_statements(type=["pl", "bs", "cf"], period="quarterly")`. Shrink 67 tools to ~20 macro-tools. Aim for max 10-12 tools per agent.
2. **Offload Risk to Risk:** Remove M-Score, F-Score, Earnings Quality from Financial agent. Give them only to Risk.

## C) Prompt Quality

### What's Great
- Structured briefings (JSON output for Synthesis) ensure final report isn't garbled
- Mandating "no orphan numbers" via sector benchmarks is phenomenal discipline

### What's Broken
- **5,700-Word Prompts:** ~7,500 tokens before tool schemas. In 20-40 turn conversation, agent suffers "lost in the middle" syndrome. Forgets writing rules by turn 15.
- **The Paradox:** "Institutional quality... Target audience: beginner Indian retail." Cannot write Ambit/Marcellus deep-dive that also stops to explain EBITDA margin. Prompt is fighting itself.
- **Synthesis Agent Starvation:** Hardest job (weaving 7 reports) but shortest prompt (653 words). Will output boring mechanical summary.

### Directives
1. **Progressive Prompting:** Strip 5,000-word prompts to 1,500 words. Move dynamic instructions to Python layer. If stock is HDFC Bank, only inject BFSI framework; don't include standard framework.
2. **Solve Paradox via UI:** Agents write strictly institutional reports. In web UI, use lightweight LLM or glossary tagging to create hover-over definitions or "Explain like I'm a beginner" side-panels. Don't force analytical agents to be teachers.
3. **Beef up Synthesis:** Needs rules on narrative pacing, weighting conflicting evidence, writing definitive Buy/Hold/Sell thesis.

## D) Analytical Completeness

### What's Great
- Extensive ownership data (Promoter Pledge, MF flows, FII/DII streaks) — lifeblood of Indian momentum/mid-cap analysis
- Screener/BSE/AMFI integrations cover core ecosystem beautifully

### What's Missing (Marcellus/Ambit Standard)
1. **Related Party Transactions (RPTs):** In India, wealth often siphoned via RPTs. Risk agent needs RPT screener tool.
2. **Capital Allocation Track Record:** Need ROIC vs WACC spread over 10 years. Institutions buy companies earning above cost of capital.
3. **Auditor Quality/Resignations:** Frequent auditor changes = major red flag in India.
4. **Contingent Liabilities:** Often hidden off-balance sheet, sink Indian mid-caps.
5. **Promoter Remuneration:** Is promoter salary growing at 30% CAGR while PAT grows at 5%?

## E) Practical Concerns

- **Cost:** ~$4.55 per report. Excellent for B2B/premium SaaS ($20-$50/mo). Unsustainable for free/ad-supported retail.
- **Latency (UX Killer):** 7 agents × 30 turns = hundreds of API calls. 3-8 minutes to generate. Users close tab staring at spinner.
  - Fix: WebSockets. Stream internal monologues: "Valuation Agent running Reverse DCF..." → "Risk Agent found Promoter Pledge red flag..."
- **Token Context Pressure:** 40 turns with full financial JSON payloads blow context window and API bill.
  - Fix: Tools return truncated/summarized JSON. Don't return 10Y daily prices; return weekly aggregates.
- **WebFetch Robustness:** Will fail frequently (paywalls, captchas, 403s). Strict 10s timeout + fallback to pure LLM knowledge.

## Summary

"Ferrari engine, confusing steering wheel." Consolidate tools into Macro-Tools. Trim prompts by moving logic to Python routing layer. Decouple beginner education from main generation. Add RPT and ROIC checks.

## Action Items (Prioritized)

### P-3: Pre-compute & Consolidate (Architecture)
- Pre-compute all analytical metrics (F-Score, M-Score, DCF, etc.) in cron
- Store in analytical_snapshot table
- Consolidate 67 tools → ~20 macro-tools
- Reduce tools per agent to 10-12 max

### P-4: Prompt & Agent Optimization
- Strip prompts to 1,500 words
- Dynamic prompt injection (Python layer picks relevant sections)
- Beef up Synthesis agent prompt
- Redefine Financial vs Valuation boundaries

### P-5: Analytical Gaps
- RPT screener
- ROIC vs WACC spread
- Auditor change tracker
- Contingent liabilities
- Promoter remuneration analysis

### P-6: UX & Robustness
- Streaming/WebSocket report generation UI
- Programmatic math verification (replace Haiku for formulas)
- Tool response truncation
- WebFetch timeout + fallback
- Beginner layer in UI (hover tooltips)
