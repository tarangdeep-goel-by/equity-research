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

### analog-backtest — Part 3 PR-B3 — KEPT
**Date:** 2026-04-26
**What:** CLI command + eval_history archive added.
**Result:** baseline run held — operator triggers via `flowtrack research analog-backtest --n 20 --seed 42 --note "baseline-post-scaffolds"` post-merge.
**Commit:** <fill on commit>

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

### business/* — All 14 sectors — Baseline with tighter prompt — KEPT
**Date:** 2026-04-07 08:00–13:00 UTC
**Stocks:** ADANIENT, POLICYBZR, OLAELEC, HINDUNILVR, GODREJPROP, BHARTIARTL, NTPC, SUNPHARMA, GROWW, PIDILITIND
**Changes applied before this batch:**
- Eval prompt: grade calibration (harsh grading, arithmetic mean constraint, multi-agent context)
- WebSearch/WebFetch removed from business + sector agents
- Agent budgets increased (business $1.00→$1.50)
- Eval timeout 600→900s
- Stderr streaming for live tool call logs
**Result:** All 14 sectors pass A-. Range: A- (91) to A (93). No iteration needed.

| Sector | Stock | Grade | Completeness | Sector Framework |
|--------|-------|-------|-------------|-----------------|
| conglomerate | ADANIENT | A- (92) | 90 | 94 |
| insurance | POLICYBZR | A (93) | 90 | 95 |
| auto | OLAELEC | A- (92) | 89 | 93 |
| fmcg | HINDUNILVR | A- (91) | 87 | 87 |
| real_estate | GODREJPROP | A- (91) | 88 | 97 |
| telecom | BHARTIARTL | A- (91) | 87 | 95 |
| regulated_power | NTPC | A- (92) | 91 | — |
| pharma | SUNPHARMA | A- (91) | 87 | 93 |
| broker | GROWW | A- (92) | 89 | 87 |
| chemicals | PIDILITIND | A- (91) | 86 | 92 |

**Commit:** 6162d4e

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

## Backlog — Fixes to Implement

Prioritized list from business agent eval. Each fix includes data pipeline verification.

### PROMPT fixes (business agent)

**1. Management quality section skipped** (BHARTIARTL, NTPC, GROWW)
- **Data check: BLOCKED.** `company_info` = 3 fields (symbol, name, industry). No board composition, CXO tenure, compensation. Concalls not extracted for any of these. Insider txns: 0 for BHARTIARTL. Making mandatory would force speculation.
- **Action:** Wait for concall extraction (fix #6). Reassess after.

**2. Bear/bull multiples must match identified peer group** (PIDILITIND)
- **Data check: OK.** `get_valuation(symbol, 'snapshot')` can fetch PE for ANY symbol. Asian Paints PE (54.4x) available. Agent just didn't think to call it for alternate peers.
- **Action:** Add to BUSINESS_INSTRUCTIONS: "if you identify a peer mismatch, call `get_valuation` for correct peers to get their multiples." Yahoo peers (fix #5) is the proper long-term fix.

**3. Secondary segment quantification** (POLICYBZR, PIDILITIND)
- **Data check: BLOCKED.** No segment P&L in any tool. Quarterly results are consolidated only. Expense breakdown = line items, not segments. Only source = concalls (not extracted).
- **Action:** Wait for concall extraction (fix #6).

**4. Mental math instead of calculate tool** (NTPC)
- **Data check: N/A** — behavioral.
- **Action:** Strengthen SHARED_PREAMBLE. Already says "Never compute in your head" — agent ignores it. Consider repeating in per-agent instructions.

### DATA fixes (pipeline)

**5. Yahoo Finance recommended peers** — NEW SOURCE
- Endpoint: `query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{SYMBOL}.NS`
- Verified: PIDILITIND → Asian Paints (0.24), Berger (0.18), Nestle, HUL, Britannia. Correct peers.
- Single HTTP call, no auth, free.
- **Action:** Add to refresh → store in DB → surface in `get_peer_sector`.

**6. Concall extraction — 13/14 eval stocks missing** ← HIGHEST IMPACT
- Only ETERNAL has concalls. All others missing.
- Blocks: management quality (#1), segment data (#3), sector KPIs (#8).
- **Action:** Run concall extraction for all 14 eval matrix stocks.

**7. SOTP subsidiary mcap** (ADANIENT — Adani Energy Solutions)
- 5/6 subsidiaries have mcap. AEL returns `mcap: 0`.
- Root cause: yfinance 404 for `ADANIENERGY.NS` — wrong symbol.
- **Action:** Fix symbol mapping. Check NSE for correct ticker (may be `ADANIENSOL.NS`).

**8. Power sector KPIs / PAF** (NTPC)
- Framework exists: `power_and_utilities` with 7 KPIs (PAF, PLF, regulated equity, etc.)
- But KPIs populated from concall data — blocked by fix #6.
- **Action:** Runs automatically once NTPC concalls are extracted.

### EVAL fixes

**9. "Stream closed" hallucination** (6/14 stocks)
- Agent claims tools failed; traces show `is_error=False` for all calls.
- But traces are half-blind — Agent SDK doesn't expose ToolResultBlock, so `result_summary` is always empty.
- **Action:** Add tool-side logging in `tools.py` (log input/output before return). Also add to SHARED_PREAMBLE: "Do not claim a tool failed unless you received an explicit error response."

---

## Learnings

Cross-cutting insights from experiments. Updated after each cycle.

### What Works
- Business agent prompts are strong out of the box — all 14 sectors passed A- without iteration
- Sector skills (_shared.md) provide enough context — real_estate got A+ (97) on Sector Framework
- Multi-agent context in eval prompt helps Gemini judge within scope (added mid-session)
- Tighter grade calibration works — scores dropped from 94-96 to 91-93 range, more honest
- Agent execution evidence (tools called/unused/errors) helps Gemini distinguish PROMPT_FIX from DATA_FIX
- Open questions mechanism working well — 7-8 sharp questions per stock, correctly delegating to web research

### What Doesn't Work
- Agent hallucinates "Stream closed" tool errors — traces show all tools succeeded (6/14 stocks)
- render_chart still not called despite explicit workflow step — agents ignore it
- Completeness is consistently the weakest dimension (86-91) — mostly segment gaps + missing management section
- Running 2 agents in parallel causes timeouts from API rate contention — run sequentially
- `subprocess.run(capture_output=True)` prevents live log streaming — switched to Popen

### Sector-Specific Notes
- **BFSI:** NIM/CASA/asset quality frameworks well-handled. SOTP for SBI subsidiaries is a strength. P/B valuation correctly prioritized over P/E.
- **IT Services:** Deal pipeline and attrition analysis strong. Concall data gap limits management commentary depth.
- **Metals:** Cyclical positioning and commodity-link analysis handled well. Manual math accurate when calculate tool "fails."
- **Platform:** Unit economics and path-to-profitability frameworks applied correctly. GMV metrics well-covered.
- **Conglomerate:** SOTP correctly identified as primary framework. Rejected flawed Screener peer classification.
- **Insurance:** Platform economics (take rate, loss ratio) correctly applied over traditional BFSI (NIM/CASA). Paisabazaar segment gap.
- **Auto/EV:** Unit economics and cash burn frameworks applied. Manufacturing ramp analysis strong.
- **FMCG:** Traditional frameworks applied but missed Quick Commerce disruption (sector agent's scope).
- **Real Estate:** Best Sector Framework score (A+ 97). Presales vs revenue recognition handled correctly.
- **Telecom:** Spectrum amortization and ARPU frameworks strong. EV-to-equity bridge incomplete.
- **Regulated Power:** Regulated ROE and fuel passthrough frameworks correct. PAF data missing from pipeline.
- **Pharma:** FDA pipeline and specialty vs generics frameworks good. R&D not broken out from other expenses.
- **Broker/Fintech:** Platform frameworks strong but NBFC/MF arms need quantification (loan book, AUM, GNPA).
- **Chemicals:** Correctly identified peer misclassification (consumer vs chemicals). Yahoo peers confirmed agent's thesis.
