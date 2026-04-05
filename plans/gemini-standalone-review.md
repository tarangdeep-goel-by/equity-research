# Gemini Standalone Architecture Review — Clean Slate

**Date:** 2026-04-05
**Model:** gemini-3.1-pro-preview (thinking mode)
**Context:** Fresh review with zero prior context. Given full architecture, prompts, pipeline, and goal. No prior recommendations shared.

## Overall Verdict

"This is one of the most thoughtfully designed financial multi-agent pipelines I have seen. Effectively a Level 4 Autonomous AI Researcher that heavily outperforms standard vanilla RAG approaches."

## Dimension Grades

| Dimension | Grade | Summary |
|-----------|-------|---------|
| Pipeline Design & Orchestration | A- | Phased approach excellent. Open Questions → Web Research is stellar. Risk: logic re-run loops |
| Model & Effort Allocation | B+ | Semantic model routing is textbook. Risk: Opus synthesis may be slower than Sonnet for same quality |
| Prompt Engineering | A | "No Orphan Numbers" and forced chart annotations cure classic LLM data-reading problems. Risk: prompt bloat |
| Tool Architecture & Context | A- | 80→11 macro tools brilliant. Pre-fetch tear sheet eliminates blank canvas. Risk: free API reliability |
| Sector Injection System | A | "Unparalleled domain accuracy." Conglomerates need SOTP exception |
| Verification & Correction | C+ | Auto-patching factual errors is elegant. THE HAIKU PARADOX: smaller model can't verify complex financial logic |
| Cost Efficiency | B | SQLite caching + budget caps good. Compare command (3 stocks) could cost $5-8 |
| Indian Market Domain | A | "You nailed it." Promoter pledge, FII→MF handoff, PSU cash, SEBI MPS all covered |
| Python Orchestrator Pre-Analysis | A+ | "Hidden gem. Perfectly marrying symbolic AI with generative AI" |

## Key Issues Found (unprompted, no prior context)

### 1. The Haiku Paradox (C+ grade — highest risk)
Haiku verifying Sonnet's complex financial logic (reverse DCF, DuPont) will generate false positives, forcing expensive re-runs.
**Fix:** Limit Haiku strictly to factual verification (number checking). Strip authority to judge logic errors. Let Python orchestrator handle basic logic checks.

### 2. Conglomerate Handling
Simple cascade will misclassify Reliance (O2C + Retail + Jio), ITC (FMCG + Tobacco + Hotels), L&T.
**Fix:** Add Conglomerate/SOTP sector injection triggered when ≥3 segments contribute >15% revenue each.

### 3. Context Window Pressure on Synthesis
7 JSON briefings + web research could exceed 100K tokens → "lost in the middle" degradation.
**Fix:** Pass only key_findings and signals to synthesis, strip verbose tables.

### 4. Missing Indian Market Risks
- **Related Party Transactions (RPTs):** #1 way promoters siphon money. Risk agent needs RPT tool.
- **SME to Mainboard Migration:** High manipulation risk for recently migrated stocks.
- **Holding Company Discount:** Bajaj Holdings, Tata Investment Corp → valuation agent will incorrectly say "UNDERVALUED."

### 5. Opus vs Sonnet for Synthesis
Benchmark needed. Sonnet may provide 95% quality at 20% latency.

### 6. Free API Reliability
NSE blocks scrapers. Screener has rate limits. Need aggressive caching and fallback routines.

### 7. Prompt Bloat
Specialist receives: preamble (780w) + specialist workflow + sector injection + baseline XML + 8-11 tool schemas. Less attention bandwidth for actual tool outputs.
**Fix:** Move universal rules to system prompt. Keep user prompt for baseline + workflow only.

## Recommendations (prioritized)

1. Fix verification: Haiku = number checker only. Python = logic checker.
2. Handle conglomerates: SOTP injection for multi-segment companies
3. Add RPT tracking to Risk agent
4. Optimize synthesis context: only key_findings + signals, not full briefings
5. Add --fast flag: single generalist agent for quick tear-sheets
6. Benchmark Opus vs Sonnet for synthesis latency/quality
