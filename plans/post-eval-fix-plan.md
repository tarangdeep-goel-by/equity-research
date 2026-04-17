# Post-Eval Fix Plan — 5-Level Prompt Hierarchy

**Created:** 2026-04-17
**Source:** 84-grade autoeval run (12 sectors × 7 agents) producing 119 Gemini issues
**Goal:** Deep triage of every flagged issue, mapped to the right prompt-hierarchy layer, with explicit "why this level" reasoning for each fix.

---

## 0. The 5 Levels

| # | Layer | Scope | Blast radius | Example |
|---|---|---|---|---|
| L1 | `SHARED_PREAMBLE_V2` | All agents, all sectors | 8 specialists | Calculate-tool discipline, open-question cap |
| L2 | `{AGENT}_SYSTEM_V2` + `{AGENT}_INSTRUCTIONS_V2` | One agent, all sectors | Single specialist | Valuation tenets 1-24, Ownership tenets 1-21 |
| L3 | `sector_skills/{sector}/_shared.md` | All agents, one sector | One sector's 4-7 agents | BFSI `_shared.md`, Metals `_shared.md` |
| L4 | `sector_skills/{sector}/{agent}.md` | One agent, one sector | Single agent-sector pair | `bfsi/valuation.md` |
| L5 | Tool / data / verifier (non-prompt) | Whole pipeline | All agents + reports | `calculate` tool signature, concall extractor, `store.py` |

**Decision rule for routing a flagged issue:**
- Appears in ≥3 agents AND ≥3 sectors → **L1** (universal)
- Appears in 1 agent AND ≥3 sectors → **L2** (agent-specific)
- Appears in ≥3 agents AND 1 sector → **L3** (sector-specific)
- Appears in 1 agent AND 1-2 sectors → **L4** (tight)
- Root cause is data/tool/mechanism → **L5**

---

## 1. Theme × Prevalence Matrix

Extracted from 119 issues; each theme carries (# occurrences, # distinct agents, # distinct sectors):

| Theme | # | agents | sectors | Route |
|---|---:|---:|---:|---|
| turn_count (30-47 turns) | 47 | 7 | 12 | **L1** ✓ PR #41 |
| op_hallucination (cagr, ^, pct_change) | 12 | 5 | 10 | **L1** ✓ PR #41 |
| calc_batching (sequential calls) | 9 | 4 | 8 | **L1** ✓ PR #41 |
| tool_section_halluc (invalid section=) | 9 | 5 | 6 | **L1** (PR #42 has business-only; LIFT) |
| ghost_numbers (prose ≠ calc) | 7 | 5 | 5 | **L1** (NEW) |
| data_ebitda_bug | 7 | 4 | 4 | **L5** (tool fix) |
| sector_kpis_coverage (0/8, 1/8) | 6 | 3 | 5 | **L5** (extractor) |
| missing_breakdowns (segment, channel) | 6 | 4 | 5 | **L3** per-sector |
| bfsi_metrics (GNPA/NNPA/LCR/PCR) | 5 | 3 | 2 | **L3** (bfsi + private_bank) + **L5** (data) |
| fii_named_holders | 5 | 1 | 5 | **L2** (ownership) + **L5** (data) |
| computation (ghost # variant) | 5 | 4 | 3 | **L1** (covered by ghost_numbers tenet) |
| framework_misuse (PE when Presales stated) | 3 | 3 | 3 | **L1** (PR #42 has business-only; LIFT) |
| signal_mismatch | 2 | 1 | 2 | **L2** covered in PR #42; monitor |
| mf_new_entry | 2 | 2 | 2 | **L5** (data) |
| fv_framing (near current price) | 2 | 2 | 2 | **L1** (PR #42 has business; LIFT) |
| tool_audit_halluc | 1 | 1 | 1 | **L5** (verifier enforcement) |

---

## 2. Work Already Shipped

### PR #41 — SHARED_PREAMBLE calculate-discipline (L1)
Added tenets:
- **Calculate-batching discipline** — 3+ calcs in one assistant turn (parallel tool_use blocks)
- **Operation discipline** — no invented ops; `^` not supported; prefer named over `expr`
- **`cagr` named operation** — promoted to first-class op in `tools.py` (was most-hallucinated missing op)

Expected impact: kills `turn_count` (47), `op_hallucination` (12), `calc_batching` (9) = 68 issues across all agents.

### PR #42 — Business agent iter1 (L2, business-only)
Added tenets:
- **Name = execute** (framework alignment)
- **Signal consistency with narrative**
- **Current-price framing precision**
- **Tool-registry discipline** (business scope)

Expected impact: business-agent 0/12 → 3-5 PASS. But 3 of the 4 tenets are applicable to ALL agents — **must lift to L1** in next PR.

---

## 3. Phase A — L1 Lifts (Universal Tenets)

**PR #43 — Cross-agent tenet lifts to `SHARED_PREAMBLE_V2`**

Rationale: 4 patterns that PR #42 addressed for business appear in multiple agents. Leaving them at L2 would force duplicate work across 7 agents.

### A1. Tool-registry discipline (L1)
**Current:** business-only in #42.
**Evidence:** 9 occurrences, 5 agents, 6 sectors. Hits technical (`get_estimates` not in registry), valuation (`get_fundamentals` not in registry), sector (`estimates` section invalid).
**Tenet:** "Do NOT invent tool sections or sub_sections. When unsure, call a tool with no section first to get the TOC. Valid sections for each tool are enumerated in its description — re-read before guessing."

### A2. No ghost numbers / prose-calc sync (NEW — L1)
**Evidence:** 7 occurrences, 5 agents, 5 sectors. Includes the 5 COMPUTATION errors (blended-FV ghost #, ROE mismatch, typos).
**Tenet:** "Every number cited in prose must trace to a `calculate` call in your Tool Audit. Before writing, verify: (1) the values going INTO each calculate call match what you state in prose; (2) the blended/derived outputs cited in narrative match the calc output exactly (no re-rounding, no 're-blending without recomputing'). Prose-vs-calc mismatches are a COMPUTATION downgrade."

### A3. Framework alignment — name = execute (L1)
**Current:** business-only in #42.
**Evidence:** 3 occurrences, 3 agents, 3 sectors. Mirrors valuation-agent Pattern B from iter1.
**Tenet:** "When you state in prose that a particular framework is the correct primary (e.g., P/Presales for real-estate developers, EV/GMV for platforms, P/ABV for banks), you must derive the final fair value / signal using that framework — not fall back to a rejected one (e.g., PE). If the correct framework lacks inputs, raise as an open question instead of contradicting yourself with the wrong tool."

### A4. Current-price framing precision (L1)
**Current:** business-only in #42.
**Evidence:** 2 occurrences, 2 agents, applicable universally.
**Tenet:** "When citing a fair-value range vs current price, state the numeric delta (via `margin_of_safety`) before applying any qualitative label like 'near current', 'well below', 'overvalued'."

### A5. Signal-narrative consistency (L1)
**Current:** business-only in #42.
**Evidence:** 2 occurrences in business+financials but applicable universally — all 7 agents emit a `signal` field.
**Tenet:** "The `signal` field must be consistent with the report's top findings. 'Mixed' is reserved for genuine tension (e.g., strong operations + poor valuation), not a cop-out when findings are directional."

**Cost:** 1 PR, ~60 line diff. Expected lift: ~15 B+ reports to A-.

---

## 4. Phase B — L2 Agent Iterations

For each agent, decide whether a single agent-system pass is needed, based on the residual B+/FAIL rate after L1 lifts.

### B1. Ownership agent — SKIP (already at 58% PASS, iter3 recent)
Residuals after L1 lifts = mostly data issues (L5).

### B2. Risk agent — SKIP (58% PASS)
Residuals = data + scope-specific. Revisit after data fixes.

### B3. Technical agent iter1 — NEEDED (L2)
**Pass rate:** 58% — but only because many data gaps are out-of-scope.
**Issues:**
- Missing relative-strength vs SECTOR index (not just Nifty 50) — 2 sectors
- Missing derivatives data (PCR, OI, Rollover) for F&O-included stocks — 3 sectors
- Missing sector-specific technical drivers (commodity price for metals)
- Tool-registry (`get_estimates` not in technical registry) — covered by L1 lift

**New tenets:**
- **Relative-strength-dual-index**: compare against Nifty 50 AND the sector index (BankNifty, NiftyIT, NiftyPharma) — the sector-relative is the differentiable signal.
- **Derivatives-data fallback**: when a stock is F&O-listed (check `get_market_context(technicals).fo_enabled`) and core technicals are empty, attempt `get_market_context(section='technicals', sub='derivatives')`; if also empty, raise as specific open question naming PCR / OI / rollover — do not silently omit.
- **Sector-technical-driver discipline**: for metals, always reference underlying commodity (HRC, LME primary aluminum, zinc) trend as a driver; for BFSI, bond yield; for IT, USD-INR. Missing this is a PROMPT_FIX.

### B4. Sector agent iter1 — NEEDED (L2)
**Pass rate:** 42%.
**Issues:**
- Empty `get_peer_sector(peer_growth)` handled as open question instead of fallback — 1 sector (pharma)
- Segment-level breakdown missing for large-caps (HUL HC/BPC/F&R) — 1 sector
- `sector_kpis` 0/8 or 1/8 coverage forced partial analysis — 3 sectors

**New tenets:**
- **Peer-growth fallback**: when `get_peer_sector(peer_growth)` empty, call `get_peer_sector(peer_metrics)` (has growth sub-fields), and as last resort pull per-peer annual_financials via looped `get_fundamentals`.
- **Segment-P&L for multi-segment large-caps**: when consolidated revenue exceeds ₹25,000 Cr AND the company is a multi-segment conglomerate/FMCG/platform, present the segment-level revenue & EBITDA split. If `get_fundamentals(section='revenue_segments')` empty, extract from concall_insights or annual_report.
- **sector_kpis → concall fallback**: when `sector_kpis` returns 0-1 of N canonical KPIs, drill `concall_insights(sub_section='operational_metrics' | 'financial_metrics')` for the gaps. Cite quarter for each extracted value.

### B5. Financials agent iter1 — NEEDED (L2)
**Pass rate:** 17% — second worst.
**Issues:**
- Unit/time-period math errors (telecom ARPU × users × 1 missing ×12 ×1e-7) — 1 sector but severe
- Non-interest income decomposition missed — 1 sector (already in fmcg/financials.md — not enforced)
- Missing subsidiary value catalyst analysis (SBI listed subs) — 1 sector
- BFSI: LCR missed despite elevated CD ratio signals — 2 sectors (also in business)
- Signal `mixed` default when narrative bullish — 1 sector

**New tenets:**
- **Unit/time-period verification**: when computing ₹-Cr aggregates from per-user / per-unit figures, write the unit-expansion as a calculate call with labelled inputs: `(₹/user/month × users_mn × 12) ÷ 10`. Any calc that spans both units AND time dimensions must be routed through `calculate` with a prose double-check line.
- **Subsidiary-value catalysts**: for diversified / multi-segment names, list listed subsidiary market caps × parent-stake × holdco discount as a standalone catalyst when material (>10% of consolidated MCap).
- **BFSI mandatory-metric-set** for financials agent (cross-ref to bfsi/financials.md): LCR, CD ratio, credit cost trajectory, non-interest income split (fee vs treasury). Missing LCR when CD ratio >80% is a PROMPT_FIX.

### B6. Valuation agent iter2 — NEEDED (L2, beyond Phase 1)
**Pass rate:** 17% (2 F are SDK crashes, not content).
**Issues:**
- Blended fair value computation bugs — 2 sectors (ghost #, ROE mismatch — covered by A2)
- Weight reallocation when DCF empty (fmcg: 55% PE weight → 80% without rationale)
- Per-share derivation still slipping despite Phase 1 Tenet 22

**New tenets:**
- **Weight-reallocation discipline**: when a component of the blended fair value is unavailable (e.g., DCF empty), explicitly restate the reallocation logic: "Original weights: PE 40% / DCF 30% / Peer 30%. DCF unavailable → reallocated proportionally: PE 57% / Peer 43%." Do NOT silently shift to an unexplained split.
- **Per-share reconciliation gate**: every cited "target price / share" must be the output of `calculate(operation='total_cr_to_per_share', a=target_mcap_cr, b=shares)` — not a derived-in-prose blended value. (Cross-ref Phase 1 Tenet 22 which is being violated.)

---

## 5. Phase C — L3 Sector `_shared.md` Iterations

Sectors where multiple agents lost points on the SAME sector-specific content. These go in `sector_skills/{sector}/_shared.md` so all specialists inherit.

### C1. BFSI (bfsi + private_bank) — HIGHEST PRIORITY
**Affects:** business, financials, risk, sector agents (5 issues across 2 sectors).
**Gaps:**
- LCR analysis expected whenever CD ratio >78-80% or in rising-rate regime — missed by business AND financials reports
- Credit cost / provisioning trend analysis missed (2 reports) despite being core to any bank P&L assessment
- Non-interest income **estimation** (not extraction) — agents make it up instead of pulling from concall or cash_flow_quality
- ADR/GDR % check missed in private_bank (already in `private_bank/ownership.md` but not enforced cross-agent)

**`bfsi/_shared.md` additions:**
- "Mandatory for business/financials/risk agents: LCR + CD ratio + credit cost trajectory + non-interest income split. If `get_quality_scores(bfsi)` doesn't return them, fall back to concall_insights(financial_metrics). Missing any of these when the bank is in top-20-by-MCap is a PROMPT_FIX."
- "Cross-agent ADR/GDR check: for private banks listed on NYSE/LSE, business and valuation agents must cite combined (direct-FPI + ADR) foreign holding, not just reported FPI%. Use the 5-source canonical search from `private_bank/ownership.md`."

### C2. Metals (VEDL) — DATA BUG PRIORITY
**Data bug:** `get_quality_scores(metals)` extracts depreciation as EBITDA → flawed Net Debt/EBITDA for financials AND risk agents. **L5 fix required.**
**Prompt additions to `metals/_shared.md`:**
- "Until `get_quality_scores(metals)` EBITDA-field bug is fixed [TICKET], derive EBITDA from `get_fundamentals(section='annual_financials')` (Operating Profit) — not quality_scores. Cross-check with `get_fundamentals(section='cost_structure')` D&A line."
- "Commodity price trend analysis is mandatory for technical + sector agents: HRC / LME primary / zinc prices vs 3Y-5Y band should be referenced."

### C3. Telecom (BHARTIARTL) — SECTOR-UNIQUE RISKS
**Gaps:**
- Nigeria / Naira currency devaluation risk missed by business — historically 20-30% of consolidated reported-INR revenue impact
- ARPU × users calculation unit errors by financials (million→crore AND monthly→annual)
- `get_quality_scores(telecom)` EBITDA = D&A (same bug class as metals)

**`telecom/_shared.md` additions:**
- "Africa / emerging-market currency devaluation risk is mandatory for multi-national telecoms (BHARTIARTL via Airtel Africa). Reported-INR revenue constant-currency growth vs reported growth should be disaggregated."
- "ARPU × subscribers × months arithmetic: always route through calculate with explicit unit labels. ARPU is ₹/month/user; subscribers in millions; to get ₹Cr annual: `₹47 × 365_000_000 users × 12 months ÷ 10_000_000 = ₹20,586 Cr`."
- Same EBITDA workaround as metals (derive from annual_financials).

### C4. FMCG (HUL) — SECTOR-SKILL GAPS
**Gaps:**
- Channel mix (GT vs MT vs e-com) breakdown missing across business + sector
- Segment P&L (Home Care, BPC, Foods & Refreshment) missing — fundamental to HUL/Nestle/Britannia analysis
- Volume vs price split not consistently extracted

**`fmcg/_shared.md` additions:**
- "Channel mix breakdown (GT / MT / Modern Trade / e-commerce / D2C) is mandatory for any FMCG with >₹10,000 Cr revenue. Extract from concall_insights(financial_metrics) or concall(management_commentary). If unavailable after both tries, raise as specific open question naming the channel."
- "Segment-level P&L (where disclosed): Home Care / Beauty & Personal Care / Foods & Refreshment for HPC-diversified; premium / mass / rural for homogeneous brands. Required for financial, sector, business agents."

### C5. Platform (ETERNAL) — DATA-HEAVY
**Gaps mostly L5:** ESOP cost not separately disclosed, GMV/take-rate/MTU missing from sector_kpis, named FII holders missing.
**`platform/_shared.md` minimal addition:**
- "When `sector_kpis` returns 0-1 canonical platform KPIs (GMV, take_rate, MTU), drill `concall_insights(operational_metrics)` for management-disclosed values. Cite quarter for each. If concall silent, raise specific open question."

### C6. Real Estate — Ghost-number cluster
**Gaps already covered by A2 (no-ghost-numbers L1 tenet).** No additional L3 work needed.

---

## 6. Phase D — L4 Tight Fixes

Single agent-sector pairs with unique content gaps after L1/L2/L3. Tight, low-priority. Examples:
- `risk/real_estate`: input-typo guard ("if you fed X into calculator when prose says Y, verify"). Probably covered by A2.
- `technical/it_services`: structural note that `get_estimates` is not in registry (covered by A1 lift).
- `ownership/conglomerate`: Retail/HNI/Corporate sub-breakdown — deferred until `shareholding_public_breakdown` DB table lands (L5).

**Action:** after L1-L3 shipped + re-eval, cherry-pick remaining L4 fixes per sector-agent pair. Defer until data.

---

## 7. Phase E — L5 Non-Prompt (Tool + Data + Verifier)

Prioritized by number of reports affected × severity:

### E1. CRITICAL: `get_quality_scores` EBITDA field mapping bug (metals, telecom)
**Affects:** financials, risk, valuation agents on metals + telecom (4+ reports).
**Bug:** tool returns depreciation value in the EBITDA field — ratios become nonsense.
**Fix:** `research/data_api.py::get_quality_scores` sector-specific branches — audit field mapping against `annual_financials` ground truth.

### E2. BFSI asset quality extraction (GNPA/NNPA/PCR/CRAR)
**Affects:** 6 reports across bfsi + private_bank (business/risk/sector/financials).
**Fix:** extend concall extractor's `operational_metrics` schema for BFSI OR pull from BSE filings XBRL. Matches `plans/valuation-agent-comprehensive-fixes.md` §3.4 and `plans/ownership-agent-iter3-fixes.md` Phase 3 D1.

### E3. sector_kpis coverage backfill (pharma/fmcg/platform/telecom)
**Affects:** 6 reports.
**Fix:** run concall extractor with expanded KPI schema across historical concalls. New canonical keys: `gmv_cr`, `take_rate_bps`, `mtu_mn`, `volume_growth_pct`, `realization_growth_pct`, `channel_gt_pct`, etc.

### E4. Named FII holders in `shareholder_detail`
**Affects:** 5 reports (ownership).
**Fix:** already planned in `plans/ownership-agent-iter3-fixes.md` Phase 3 D1. Parse BSE XBRL for named foreign-institutional holders at ≥1% threshold.

### E5. `mf_changes` coverage-aware baseline
**Affects:** 2 reports.
**Fix:** already planned in `plans/ownership-agent-iter3-fixes.md` Phase 3 D2.

### E6. `get_chart_data(ev_ebitda)` backfill for metals + telecom
**Affects:** 1-2 reports (valuation).
**Fix:** Screener chart-data scraper needs `ev_ebitda` chart type added.

### E7. ADR/GDR outstanding extraction
**Affects:** 1 report (private_bank ownership).
**Fix:** BSE annual report parsing for depositary-receipt notes; currently caught by canonical-search but data missing.

### E8. Verifier: tool-audit enforcement
**Affects:** 1 report (risk/it_services — "claimed to call get_company_context(filings) but log shows never").
**Status:** already shipped in iter3 PR #15 per `project_iter3_complete.md` memory. Confirm it's firing and tune.

### E9. SDK crash stderr capture
**Status:** shipped (commit 1d530a2).
**Next step:** next valuation crash will surface actual stderr — use that to diagnose or file upstream bug (see `github.com/anthropics/claude-agent-sdk-python/issues/701`).

---

## 8. Execution Sequence (Optimized)

| Step | PR | Scope | Risk | Expected Lift |
|---|---|---|---|---|
| 1 | #41 (DONE) | L1: calculate-discipline | All agents | +15 reports from turn-count alone |
| 2 | #42 (DONE) | L2: business iter1 | Business only | +3-5 business PASSes |
| 3 | **#43** | L1: lift A1-A5 (tool-registry, no-ghost, framework, framing, signal) | All agents | +8-12 reports |
| 4 | **#44** | L2: financials iter1 | Financials only | +3-5 financials PASSes |
| 5 | **#45** | L2: sector iter1 | Sector only | +2-3 sector PASSes |
| 6 | **#46** | L2: technical iter1 | Technical only | +2-3 technical PASSes |
| 7 | **#47** | L2: valuation iter2 | Valuation only | +2-3 valuation PASSes |
| 8 | **#48** | L3: bfsi _shared.md | BFSI + private_bank | +3-4 reports |
| 9 | **#49** | L3: telecom/metals/fmcg/platform _shared.md | 4 sectors | +4-6 reports |
| 10 | **Re-eval** | all | full 15-sector × 7-agent | measure lift |
| 11 | **L5 sprint** (parallel) | data/tools | pipeline | unlocks remaining FAIL→PASS |
| 12 | **Re-eval final** | all | target 70-80% PASS | — |

**Estimated pass-rate trajectory (after each step, rolling):**
- Now: 35% (after PR #41/#42 merge untested)
- After #43: ~46%
- After #44-47 (agent iter1s): ~62%
- After #48-49 (sector _shared): ~70%
- After L5 data sprint: ~80%

---

## 9. What NOT to Change (Accepted / Out of Scope)

Per `feedback_gemini_outage_recovery.md` and `feedback_substantive_fixes.md` philosophies:

- **NOT_OUR_PROBLEM** (5 issues): LLM phrasing artifacts, minor FY-year confusions. Accept as inherent noise.
- **SDK crashes** (3 F grades): known upstream bug, not prompt-fixable; telemetry-captured for post-mortem.
- **Gemini 503 ERRs** (20 issues): infra flakiness, not content. Re-grade when Gemini recovers.

---

## 10. Open Decisions

1. **Should A5 (signal-narrative consistency) lift to L1 now** or stay at L2 in business only until 2+ agents show the same mismatch?  
   **Recommendation:** lift now — the `signal` field is emitted by all 7 agents; universal tenet is cheap.
2. **Should L3 sector _shared.md work happen before or after a mid-cycle re-eval?**  
   **Recommendation:** after. Let #43-47 (L1+L2) land and re-eval first — may reveal that some L3 gaps no longer surface.
3. **L5 data-pipeline sprint scope:** 4 items (E1 EBITDA bug, E2 BFSI extraction, E3 sector_kpis backfill, E4 FII names) or narrow to just E1+E2 as highest-leverage?  
   **Recommendation:** E1 + E2 first — CRITICAL data correctness issue + largest report-count lever. E3/E4 parallel track.

---

## 11. Appendix — Raw Feedback Dump

Machine-readable TSV at `/tmp/feedback_matrix.tsv` (119 rows, columns: `agent / sector / grade / num / issue_type / issue_text`). Used to generate the theme-count table in §1.

Full Gemini grading JSONs at `flow-tracker/flowtracker/research/autoeval/eval_history/20260417T*.json` — per-agent-per-sector detailed parameter grades + specific issue lists + Gemini verbatim rationale.
