# AutoEval Changelog

Single source of truth for experiments, fixes, and learnings.

---

## Experiment Log

Each entry: what changed → what resulted → kept or reverted.

```
### {agent}/{sector} — Cycle {N} — {grade_before} → {grade_after} — {KEPT|REVERTED}
**Date:** YYYY-MM-DD HH:MM UTC
**Stock:** {SYMBOL}
**Change:** {file path + brief description}
**Result:** {new grade} — {kept or reverted and why}
**Commit:** {short sha}
```

---

### business/* — Cycle 1 — Baseline — KEPT
**Date:** 2026-04-07 06:44 UTC
**Stocks:** SBIN, TCS, VEDL, ETERNAL
**Change:** Initial baseline run — no prompt changes. Reports generated from existing prompts + sector skills.
**Result:**
- bfsi/SBIN: A+ (96) — PASS
- it_services/TCS: A (94) — PASS
- metals/VEDL: A (95) — PASS
- platform/ETERNAL: A+ (96) — PASS

All 4 sectors passed A- on first run. No fixes needed.
**Commit:** 8f81700

### business/bfsi — Cycle 2 — A+ → A+ — KEPT
**Date:** 2026-04-07 07:38 UTC
**Stock:** SBIN
**Change:** Re-eval only (--skip-run) — new report from fresh agent run with updated prompts (render_chart, save_business_profile instructions already in prompts.py).
**Result:** A+ (96) — maintained. Chart rendering fix not yet testable (report predates prompt change).
**Commit:** 8f81700

---

## Pending Fixes

Issues from Gemini evals. Status: `applied` / `skipped` / `blocked` / `pending`.

| # | Agent | Sector | Stock | Cycle | Type | Issue | Status | Notes |
|---|-------|--------|-------|-------|------|-------|--------|-------|
| 1 | business | bfsi | SBIN | 1 | PROMPT_FIX | render_chart never called for 10yr trends/peers | applied | prompts.py:202 — explicit render_chart step added |
| 2 | business | bfsi | SBIN | 1 | PROMPT_FIX | save_business_profile not called | applied | prompts.py:127 — mandatory save step added |
| 3 | business | it_services | TCS | 1 | PROMPT_FIX | render_chart ignored despite rich 10yr data | applied | Same fix as #1 — general prompt change |
| 4 | business | it_services | TCS | 1 | DATA_FIX | calculate/save_business_profile "Stream closed" | skipped | Likely hallucinated — evidence shows tools succeeded (see README) |
| 5 | business | it_services | TCS | 1 | DATA_FIX | Concall data missing for TCS | blocked | Concall pipeline gap — outside autoeval scope |
| 6 | business | metals | VEDL | 1 | PROMPT_FIX | Should retry failed tool calls before fallback | applied | prompts.py:49 — "retry once before giving up" rule added |
| 7 | business | metals | VEDL | 1 | PROMPT_FIX | render_chart not called for trends/SOTP | applied | Same fix as #1 |
| 8 | business | platform | ETERNAL | 1 | PROMPT_FIX | render_chart not called for revenue mix/margins | applied | Same fix as #1 |
| 9 | business | platform | ETERNAL | 1 | DATA_FIX | calculate tool "stream closed" | skipped | Same as #4 — likely hallucinated |
| 10 | business | bfsi | SBIN | 2 | PROMPT_FIX | render_chart still not called (report predates fix) | applied | Fix already in prompts.py — untested on fresh run |
| 11 | business | bfsi | SBIN | 2 | DATA_FIX | calculate tool "stream closed" | skipped | Same as #4 |

---

## Learnings

Cross-cutting insights from experiments. Updated after each cycle.

### What Works
- Business agent prompts are strong out of the box — all 4 baseline sectors passed A- without iteration
- Sector skills (_shared.md) provide enough context for BFSI/metals/platform specialization
- Agent execution evidence (tools called/unused/errors) helps Gemini distinguish PROMPT_FIX from DATA_FIX

### What Doesn't Work
- Gemini flags "Stream closed" errors that may be hallucinated by the agent — check tool_logs before treating as real DATA_FIX
- render_chart was available but agents ignored it until explicitly mandated in workflow steps

### Sector-Specific Notes
- **BFSI:** NIM/CASA/asset quality frameworks well-handled. SOTP for SBI subsidiaries is a strength. P/B valuation correctly prioritized over P/E.
- **IT Services:** Deal pipeline and attrition analysis strong. Concall data gap limits management commentary depth.
- **Metals:** Cyclical positioning and commodity-link analysis handled well. Manual math accurate when calculate tool "fails."
- **Platform:** Unit economics and path-to-profitability frameworks applied correctly. GMV metrics well-covered.
