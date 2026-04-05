# Gemini Standalone Architecture Review V2 — Clean Slate (Post All Fixes)

**Date:** 2026-04-05
**Model:** gemini-3.1-pro-preview (thinking mode)
**Context:** Fresh review with zero prior context. Full current architecture including system/user split, verifier number-checker, synthesis trimming, conglomerate/holding co injections.

## Dimension Grades

| # | Dimension | Grade | Key Verdict |
|---|-----------|-------|-------------|
| 1 | Pipeline Design | A- | Pre-fetch is "best-in-class." Risk: sync matplotlib bottleneck, Phase 0 failure cascade |
| 2 | Model/Effort Allocation | A | Effort mapping "perfectly matches cognitive load." Downgrade web_research to medium |
| 3 | Prompt Architecture | A- | System/user split "perfectly aligned with Claude's attention." Wrap constraints in XML tags |
| 4 | Tool Design | B | 80 tools is massive — but agents already get strict subsets (7-11 each). Corporate actions gap |
| 5 | Sector Injection System | **A+** | "Crown jewel of the architecture." Keyword detection still fragile |
| 6 | Verification & Correction | B+ | Haiku number-checker is "brilliant weak-to-strong validation." Risk: derived math false positives |
| 7 | Synthesis Design | A | Trimmed briefings + orchestrator pre-analysis is "outstanding." Target price should be inherited not recalculated |
| 8 | Cost Efficiency | A | "Institutional workflow for under $5 that would usually cost $15-$20" |
| 9 | Indian Market Domain | **A+** | "Deeply accurate. Immense buy-side expertise" |
| 10 | Gaps/Blind Spots | — | RPT tool, auditor resignations, NDU vs pledge, SME half-yearly, tool timeouts |

## What Improved vs Previous Standalone (same session, different Gemini instance)

| Dimension | Previous | Now | Delta |
|-----------|----------|-----|-------|
| Pipeline Design | A- | A- | Same (sync charts still flagged) |
| Model/Effort | B+ | **A** | Tiered effort fully validated |
| Prompt Architecture | A | A- | System/user split noted as correct. Mild concern on total system prompt length |
| Tool Design | A- | B | More concern about 80 tools (but they're already scoped per agent) |
| Sector Injections | A | **A+** | "Crown jewel" — holding co + conglomerate gave it the edge |
| Verification | C+ | **B+** | Haiku number-checker completely addressed the paradox |
| Synthesis | (not separately graded) | **A** | Trimmed context validated |
| Cost | B | **A** | Tiered effort + auto-patching validated |
| Indian Domain | A | **A+** | RPT flag + conglomerate + holding co pushed it over |
| Orchestrator | A+ | (folded into synthesis A) | Still praised as "outstanding" |

## New Issues Identified

### 1. Derived Math False Positives in Verifier
Haiku can't recognize derived calculations (e.g., Trailing 12M Revenue = sum of 4 quarters). Will flag as "error" because the sum doesn't appear verbatim in source data.
**Fix:** Give Haiku a `python_calculator` tool for deriving sums before flagging.

### 2. Synchronous Matplotlib Bottleneck
25 chart types rendered synchronously in Phase 3 assembly.
**Fix:** Async chart generation during Phase 1.5/2.

### 3. SME Half-Yearly Reporting
SME stocks report half-yearly, not quarterly. Financial agent expecting 12Q data will fail.
**Fix:** Deterministic check in Phase 0: if SME, switch Financial prompt from "12Q" to "6 half-yearly periods."

### 4. Auditor Resignations
#1 red flag in Indian mid-caps. Not currently checked.
**Fix:** Add to Risk agent as mandatory open question (like RPT).

### 5. Pledge vs NDU (Non-Disposal Undertaking)
Promoters use NDUs to bypass pledge reporting. Ownership agent should treat NDUs with same severity.
**Fix:** Add to Ownership agent Key Rules.

### 6. Tool Timeouts During Market Hours
NSE/BSE throttle during 9:15 AM - 3:30 PM IST.
**Fix:** Exponential backoff + proxy rotation for production use.

### 7. Web Research Effort
"high" effort for fact-retrieval is overkill.
**Fix:** Downgrade to "medium".

### 8. Corporate Actions
Stock splits/bonus/rights destroy historical data alignment.
**Fix:** Add `check_corporate_actions` deterministic check in Phase 0.

## Confirmed Working Well (no issues)
- Pre-fetch tear sheet architecture
- Effort tiering strategy
- Number-only verification with auto-patching
- Synthesis context trimming to 30 fields
- Orchestrator cross-signal detection
- Tiered failure handling
- RPT open question in Risk
- Conglomerate SOTP as additive overlay
- Holding company as cascade position 0
- Budget caps per agent
