# Plan: Comprehensive Valuation Agent Fixes

**Created:** 2026-04-16 (after first end-to-end eval of harmonized valuation agent across 15 sectors)
**Owner:** equity-research/flow-tracker
**Source:** `plans/overnight-valuation-fixes.md` (eval results) + 45 Gemini-flagged issues across 15 sectors
**Goal:** Address every substantive issue, not just the ones blocking the A- bar. Treat Gemini's feedback as the analytical critique it is.

---

## 0. Framing — Why "Fix All"

The valuation agent is post-Phase-1-harmonization (commit `1ba38ec`) and produced 12/15 PASS on first end-to-end run — strongest baseline of any new agent. **But "passing" is not the goal.** Three reasons to fix everything Gemini flagged, not just the 3 below-bar sectors:

1. **The same root patterns will surface in the other untested agents** (business, risk, sector). Fixing them at the SHARED_PREAMBLE / agent-tenet layer prevents 5× re-discovery.
2. **An A- with 3 known unfixed issues is fragile.** A future stock that triggers a single missing-fallback path drops to B+ silently. Closing fallback gaps now hardens every future run.
3. **Some "passing" reports have analytical voids** — pharma A- still misses explicit margin assumption in SOTP derivation; private_bank A still skips Net NPA deduction in P/ABV. These are the kind of detail an institutional reader notices even when the grade looks fine.

The 3 NOT_OUR_PROBLEM issues (LLM phrasing artifacts) are explicitly **out of scope** — accepted as inherent LLM behavior.

---

## 1. Diagnosis — Six Root Patterns

The 45 Gemini issues collapse into 6 patterns + 1 accepted-noise bucket. Patterns ordered by reach (sectors hit) and by leverage (one fix → many sectors improve).

### Pattern A — Fallback tool discipline (12 issues, 9 sectors)

**Failure mode:** When a primary tool returns weak/empty data, the agent identifies the limitation in prose ("PE band only 27 days", "0 peers returned") but does not call the registered fallback tool (`get_chart_data`, `get_yahoo_peers`, manual `get_valuation(snapshot)` per ticker). The agent has the tool, knows the gap exists, names the gap — and moves on.

**Why it happens:** The current agent prompt lists tools in the registry but does not encode an *if-primary-fails-call-fallback* decision tree. The agent treats each tool as independent rather than as primary/fallback pairs.

**Sectors:** bfsi, chemicals, conglomerate, fmcg, insurance, it_services, metals, pharma, real_estate, regulated_power, telecom

**Sub-instances:**
- Narrow PE band (4-28 day window) → no fallback to `get_chart_data(chart_type='pe')` or `get_valuation(section='pe_history', years=5)` — 7 sectors
- Thin/garbage peers from `get_peer_sector` → no fallback to `get_yahoo_peers` — 4 sectors
- Empty SOTP → no manual per-ticker `get_valuation(snapshot)` walk — 3 sectors

**Layer:** `VALUATION_INSTRUCTIONS_V2` workflow + an explicit "Fallback Tool Map" section.

### Pattern B — Sector framework execution gap (9 issues, 7 sectors)

**Failure mode:** Agent names the correct sector-specific framework in prose but doesn't execute it — defaulting back to PE-anchored math.

**Why it happens:** The harmonized prompt has good sector identification (the agent correctly says "EV/GMV is primary for platforms in 1P/3P transition" etc.) but no rule that *naming a primary metric obligates the calculation*.

**Sub-instances:**
- platform / ETERNAL: identified EV/GMV as primary metric for 1P/3P revenue distortion — never calculated
- metals / VEDL: stated EV/EBITDA primary for cyclicals — assigned PE 35% weight in fair-value table  
- private_bank / HDFCBANK: included EV/Revenue for a bank (debt = raw material, not capital structure)
- chemicals / PIDILITIND: missing EV/EBITDA framework alongside PE
- it_services / TCS: missing FCF Yield analysis (mandatory for mature IT services)
- auto / OLAELEC: missing cash-runway calculation for cash-burning EV maker
- insurance / POLICYBZR: missing CAC/LTV/take-rate unit economics for insurtech marketplace
- real_estate / GODREJPROP: stated "realization per sqft is key operational signal" — never extracted

**Layer:** Mix of `VALUATION_SYSTEM_V2` (the universal "name = execute" rule) + per-sector `sector_skills/<sector>/valuation.md` files (sector-specific mandatory metric checklists).

### Pattern C — Computation bypass and propagation gaps (8 issues, 7 sectors)

**Failure mode:** Two sub-types:
- **(C1) Calculate tool skipped** despite hard SHARED_PREAMBLE rule. Agent does mental math for percentages, blended averages, growth rates.
- **(C2) Override-propagation** — agent overrides a model input (WACC, projection margin, growth rate) but does not recalculate dependent outputs that used the original input.
- **(C3) Math integrity** — telecom's COMPUTATION error using EV instead of Market Cap to derive per-share fair value (5-point grade hit).
- **(C4) Implicit assumptions** — pharma derived US Specialty PAT from revenue without stating implied net margin; private_bank cited P/ABV but didn't show Net NPA per share deduction; platform mixed trailing FY25 SOTP with forward FY26 EV/Rev (duration mismatch).

**Why it happens:** Calculate-tool rule is in SHARED_PREAMBLE but enforcement is soft. Override-propagation isn't in any rule — it's an intuition the agent doesn't have.

**Layer:** `SHARED_PREAMBLE_V2` (calculate enforcement strengthening) + new `VALUATION_SYSTEM_V2` tenet (override-propagation) + per-sector valuation.md files (show-the-math conventions).

### Pattern D — Projection model trust without sanity override (3 issues, 3 sectors)

**Failure mode:** Agent uses model outputs without applying contextual sanity:
- fmcg / HINDUNILVR: base case projection used 24.9% EBITDA margin, contradicting management guidance of 22-23% cited in the same paragraph
- insurance / POLICYBZR: projection tool used 3-yr avg margin (0.3%) including loss years for a now-profitable turnaround → negative EPS projections
- chemicals / PIDILITIND: assigned 70% weight to analyst consensus despite explicitly flagging 46% dispersion as "highly uncertain"

**Why it happens:** No rule encodes "management guidance > model output for base case" or "weight = inverse of dispersion".

**Layer:** `VALUATION_SYSTEM_V2` tenet — base-case anchoring rule + dispersion-aware weighting rule.

### Pattern E — Data infrastructure gaps (12 issues, 10 sectors)

**Failure mode:** Backend tools return incomplete, narrow, or empty data that no prompt can compensate for.

**Sub-instances:**
- **PE band depth** — `get_valuation(section='band')` returns 4-28 day windows (~16-28 observations) instead of 5Y. Hits: bfsi, it_services, real_estate, regulated_power explicitly; chemicals, conglomerate, pharma, broker noted but worked around (8 sectors total)
- **FMP DCF empty** — `get_fair_value_analysis(section='dcf')` returns empty. Hits: chemicals, it_services, metals, real_estate (4 sectors)
- **Subsidiary mapping** — `get_valuation(sotp)` missing recent IPOs and unlisted material subs. Hits: regulated_power (NTPCGREEN), telecom (BHARTIHEXA + INDUSTOWER), bfsi (SBI General Insurance unlisted) — 3 sectors  
- **P/B chart series empty** — `get_chart_data(chart_type='pbv')` returns empty for HDFCBANK (1 sector, but BFSI-critical)
- **Asset quality / CASA missing for banks** — `get_quality_scores(bfsi)` not returning GNPA/NNPA/PCR/CASA reliably (1 sector — bfsi; same issue surfaced in financials evals → confirmed cross-agent)
- **Turnaround margin baseline** — projection tool uses naive 3-yr avg margin including loss years (insurance — 1 sector but high impact for newly-profitable companies)

**Layer:** Data pipeline (`data_api.py`, `store.py`, `screener_client.py`, `fmp_client.py`).

### Pattern F — Open-questions escape hatch (2 issues, 2 sectors)

**Failure mode:** Agent raises items as "open questions" when fallback tools were available to resolve them.

**Sub-instances:**
- telecom: left INDUSTOWER out of SOTP as open question instead of querying its market cap directly
- insurance: asked for "global peers" in open questions instead of calling `get_yahoo_peers`

**Why it happens:** Same root as Pattern A but expressed differently — agent uses open-questions list as a parking lot for things tools could answer.

**Layer:** `VALUATION_SYSTEM_V2` tenet — Open-Questions discipline (lift the existing OWNERSHIP_SYSTEM_V2 Tenet 14 pattern).

### Pattern G (out of scope) — LLM phrasing artifacts (3 issues, 3 sectors)

**Sub-instances:**
- auto: minor FY27/FY28 mix-up in bull scenario text
- broker: confusing phrasing "(bear ₹302/base ₹324/bull ₹340 × forward EPS ₹4.70)"
- fmcg: narrative says valuation is "ATTRACTIVE", JSON briefing says `signal_direction: "mixed"`

**Decision:** Accept. These are LLM phrasing inconsistencies inherent to autoregressive generation. Cost of a "consistency check" final pass (extra LLM call per report) outweighs the analytical impact. Document as known noise and move on.

---

## 2. Issue → Pattern → Fix Layer Matrix

| Sector | # Issues | Patterns | Fix Layers |
|---|---|---|---|
| auto | 3 | B + A + G | sector_skill + workflow + accept |
| bfsi | 3 | E + E + A | data + data + sector_skill |
| broker | 3 | C1 + B + G | preamble + sector_skill + accept |
| chemicals | 4 | A + E + D + B | workflow + data + tenet + sector_skill |
| conglomerate | 2 | A + A | workflow ×2 |
| fmcg | 3 | A + D + G | workflow + tenet + accept |
| insurance | 3 | A + E + B | workflow + data + sector_skill |
| it_services | 4 | A + B + E + E | workflow + sector_skill + data ×2 |
| metals | 3 | A + B + E | workflow + sector_skill + data |
| pharma | 2 | C4 + A | sector_skill + workflow |
| platform | 2 | B + C4 | sector_skill ×2 |
| private_bank | 3 | E + B + C4 | data + sector_skill + sector_skill |
| real_estate | 4 | C2 + C1 + B + E | tenet + preamble + sector_skill + data |
| regulated_power | 3 | E + E + C2 | data ×2 + tenet |
| telecom | 3 | C3 + F + E | tenet (math) + tenet (open-q) + data |

---

## 3. Phase 1 — Prompt-Only Patches (highest leverage, ~2-3 hrs)

These ride entirely in `prompts.py` and `playbook` updates. Single PR. No sector skill files yet (those come Phase 2). No data pipeline (Phase 3).

### 1.1 — `SHARED_PREAMBLE_V2` strengthening (Pattern C1)

**Where:** `flow-tracker/flowtracker/research/prompts.py`, `SHARED_PREAMBLE_V2`, the existing `calculate` rule.

**Add to existing calculate-tool rule:**
> Before writing any quantitative section, list the calculate-tool calls you made for each derived number in your Tool Audit. Examples: blended fair-value averages, margin of safety, growth rates, percentages, multipliers. Mental math for "trivial" arithmetic introduces the same drift as mental math for hard arithmetic — both must use the calculate tool.

**Affects all 8 specialist agents** (preamble is shared). Mild risk of regression in agents that had passing reports; mitigated because the rule is additive (stricter, not contradictory).

**Test:** Re-run broker, real_estate, auto valuations; expect Tool Audit to enumerate calculate calls, no more "calculated in head" Gemini flags.

### 1.2 — `VALUATION_SYSTEM_V2` new tenets (Patterns B, C2, C3, C4, D, F)

**Where:** `flow-tracker/flowtracker/research/prompts.py`, `VALUATION_SYSTEM_V2` tenets section.

**Add as new tenets (numbering follows current last tenet):**

**Tenet — Sector framework: name = execute (Pattern B)**
> When you state in prose that a particular metric is the "primary", "most appropriate", or "anchor" valuation framework for the sector, you must execute that calculation in the Fair Value Triangle and assign it the highest weight. Naming a framework without computing it leaves the report inconsistent — your prose and your math should agree.

**Tenet — Override propagation (Pattern C2)**
> When you override a model input (WACC, base-case margin, projection growth rate, peer multiple), you must recalculate every dependent output that used the original input — particularly the reverse DCF implied growth, fair value range, and any peer-relative multiple comparisons. A single-point override that leaves dependent outputs stale is worse than no override.

**Tenet — Per-share fair value derivation (Pattern C3, telecom-specific math)**
> Per-share fair value derives from target Market Cap, never from Enterprise Value. The relationship: target equity per share = target MCap ÷ shares outstanding; target MCap = target EV − net debt − minority interest + investments. Confirm this conversion explicitly when bridging from EV-based multiples (EV/EBITDA, EV/Sales) to a price target.

**Tenet — Show segment math (Pattern C4)**
> When deriving a segment-level PAT or fair value from revenue/EBITDA estimates, state the implied margin assumption explicitly and confirm that segment PATs reconcile to consolidated PAT (within rounding). When citing book value derivatives (P/ABV, P/Embedded Value), show the math: ABV = BVPS − Net NPA per share; EV = NAV + present value of in-force business.

**Tenet — Base-case anchoring (Pattern D)**
> Base-case projections must anchor to management guidance when present and credible. Reserve historical averages for cases where guidance is absent, withdrawn, or stale by >2 quarters. When a model output (projection tool, analyst consensus) contradicts management guidance cited in the same section, flag the divergence and lead with management guidance for the base case.

**Tenet — Dispersion-aware consensus weighting (Pattern D)**
> When analyst consensus shows high dispersion (coefficient of variation >25-30% or explicit "wide range" flagged by the tool), reduce its weight in the blended fair value proportionally. Dispersion of 30-50% suggests consensus weight ≤ 20%; >50% means consensus is informational only and should not anchor fair value.

**Tenet — Open-questions discipline (Pattern F)**
> Open questions are reserved for items genuinely unverifiable from your tool registry. Before raising any open question, confirm you have called every fallback tool relevant to the gap (`get_yahoo_peers` for thin peers, `get_chart_data` for narrow time-series, manual `get_valuation(snapshot)` per ticker for missing SOTP subs). Open questions outside the valuation domain (governance, business model, sector cycle) belong to other agents and waste the 3-5 budget.

**Affects valuation agent only.** ~6 new tenets. Renumber existing Sector Compliance Gate accordingly.

### 1.3 — `VALUATION_INSTRUCTIONS_V2` workflow additions (Pattern A)

**Where:** `flow-tracker/flowtracker/research/prompts.py`, `VALUATION_INSTRUCTIONS_V2`, workflow section.

**Add new workflow step + Fallback Tool Map:**

**Insert as a numbered step in the workflow (right after data-collection, before fair-value composition):**
> N. **Fallback resolution pass.** For each primary-tool output that returned partial/empty/narrow data, call the registered fallback tool before composing the Fair Value Triangle. Reference the fallback map below. Do not advance to fair-value composition with a known weak input that has an available fallback.

**Add at end of workflow section as a reference table:**

```
### Fallback Tool Map

| Primary tool returns | Fallback to call |
|---|---|
| `get_valuation(band)` returns <30 obs OR <90-day span | `get_chart_data(chart_type='pe')` (7yr) OR `get_valuation(section='pe_history', years=5)` |
| `get_valuation(band, metric='pb')` empty | `get_chart_data(chart_type='pbv')` |
| `get_peer_sector` returns <3 relevant peers OR business-model-mismatched peers | `get_yahoo_peers` |
| `get_valuation(sotp)` returns "no listed subsidiaries" but subsidiaries are known to exist (from concall, business profile, news) | `get_valuation(snapshot)` per subsidiary ticker manually; for unlisted, value via sector multiples (AMC: 3-5% AUM; insurance: 1.5-3× embedded value; lender: 1.0-2.5× book) |
| `get_fair_value_analysis(dcf)` empty | Reverse DCF as primary; manual DCF via `calculate` if required for sector (utility, mature consumer); skip DCF entirely for sectors where it doesn't fit (banks, real estate, IPO-stage) |
| `get_quality_scores(bfsi)` missing GNPA/NNPA/PCR/CASA | `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed values |
```

**Affects valuation agent only.**

### 1.4 — Playbook update

**Where:** `flow-tracker/docs/agent-skills-playbook.md`

**Add new section under cross-agent invariants:**
> **I-9 — Fallback tool discipline.** Each agent's prompt must enumerate primary→fallback tool pairs for its domain. When a primary returns partial/weak data, the fallback is mandatory before writing the report. The "fallback map" lives in the agent's INSTRUCTIONS_V2 and is regenerated whenever new tools are added to the registry.

**Affects future agent harmonization** — when business/risk/sector agents go through the same eval cycle, this invariant catches the same gap.

### 1.5 — Compliance gate update

`mandatory_metrics_status` in valuation briefing schema is already in place from Phase 1. Add to the list of required metric checks: `fallback_chain_complete: bool` indicating whether all fallback tools were called for partial primary outputs. Optional but useful as a self-check.

---

## 4. Phase 2 — Sector Skill Files (intersects `full-sector-skills-buildout.md`)

Build 14 `sector_skills/<sector>/valuation.md` files informed by Pattern B (sector framework execution gap) and the per-sector specifics surfaced in Gemini reviews. This intersects with the existing Phase 2 of `full-sector-skills-buildout.md` — execute together.

### Per-sector mandatory-metric checklist (informed by Gemini)

Each `sector_skills/<sector>/valuation.md` must contain a "Mandatory Metric Checklist" section with sector-specific items. Drafts informed by the eval results:

| Sector | Mandatory metric additions (beyond generic PE/PB) |
|---|---|
| **bfsi** (PSU bank) | P/ABV with explicit Net NPA deduction shown; CASA mix; GNPA/NNPA/PCR; SOTP including unlisted subs (SBI General Insurance via 1.5-3× embedded value, etc.) |
| **private_bank** | Same as bfsi + strip ALL EV-based metrics from snapshot; HDFC merger DPS/share-count adjustments shown explicitly |
| **it_services** | FCF Yield mandatory; revenue per employee; deal-pipeline disclosed coverage; offshore/onshore margin mix |
| **metals** | EV/EBITDA primary anchor (highest weight); EV/ton normalized capacity; commodity price sensitivity; SOTP isolating listed subs |
| **platform** | EV/GMV mandatory (extract GMV from concall when revenue distorted by 1P/3P); contribution margin per order; cohort retention; cash burn months |
| **conglomerate** | SOTP with holdco discount decomposition (governance / complexity / leverage); Reverse DCF as sanity check; per-vertical EV/EBITDA |
| **telecom** | EV/EBITDA primary; OpFCF; ARPU; spectrum amortization adjustment to PE; per-share derivation explicitly Target MCap÷shares (closes telecom's COMPUTATION error) |
| **real_estate** | NAV/sqft of land bank; presales (booking value) vs revenue recognition lag; realization per sqft (must extract, not just name); RERA escrow position |
| **pharma** | FCF Yield; ETR-normalized PE; segment SOTP with explicit margin assumption per segment; FDA-pipeline-conditional bull case |
| **regulated_power** | P/B vs Regulated ROE (Damodaran framework); dividend yield vs G-sec spread; SOTP including recent IPO subs; WACC override propagation enforced |
| **insurance** | EV (Embedded Value) and VNB (Value of New Business); P/EV vs FY+1 P/EV; for insurtech: CAC, LTV, take rates, contribution margin; turnaround margin baseline override |
| **broker** | Active client growth + ADTV mandatory (call sector_kpis); F&O concentration; per-account unit economics (CAC, ARPU); reject FCFE for brokers (client float distorts) |
| **auto** (EV pure-play) | Cash runway months mandatory for negative-FCF; P/S or EV/Rev band when PE empty; capacity utilization curve; dilution risk if cash runway <18 months |
| **chemicals** | EV/EBITDA primary alongside PE; molecule/client concentration; FAT (Fixed Asset Turnover) ceiling for specialty |
| **fmcg** | Volume vs price growth split; rural/urban mix; premiumization ratio; base case = management guidance margin (no model-vs-guidance contradiction) |

### Sector skill files structure (per playbook §3.2)

Each file follows the mandatory template:
1. Sub-type / archetype identification
2. Regulatory boundaries (IF binding caps exist — bfsi 74% FII, telecom spectrum, etc.)
3. Mandatory metric checklist (above)
4. Valuation basis (which multiple is primary, which fail and why)
5. Data-shape fallback (when canonical KPIs missing — fall back to concall management commentary)
6. Sector-specific open-questions templates (3-5)

### Generation method — same as ownership/financials

Per-sector subagent dispatch (1 subagent owns business + valuation + risk + sector files for 1 sector → coherent framing). Drafts → Gemini review → revise → orchestrator spot-check.

### Coverage note — `private_bank` doesn't yet have skill files

Just bfsi exists. Phase 2 should create `sector_skills/private_bank/` with valuation.md + ownership.md + financials.md (the latter two already noted in `post-overnight-fixes.md`).

---

## 5. Phase 3 — Data Pipeline Fixes (Pattern E)

Four discrete data fixes. Each unblocks multiple sectors. Order by leverage:

### 3.1 — PE/PB band depth (8+ sectors affected)

**Where:** `flow-tracker/flowtracker/research/data_api.py::ResearchDataAPI.get_valuation_band()` (and downstream caching layer).

**Diagnosis needed:** Why does `get_valuation(band)` return 4-week windows? Likely candidates:
- (a) The Screener `pe` chart endpoint returns full history but the wrapping function filters/caches only the last 30 days
- (b) Daily price × daily EPS (TTM) requires daily EPS — if daily EPS isn't available, function falls back to weekly/monthly and only the most recent month exists in DB
- (c) `days` parameter default is 30 instead of 1825 (5Y)

**Fix:** Investigate, likely change default `days` from 30 → 1825 in `get_valuation_band` and re-verify Screener chart parsing handles the longer range.

**Test:** All 4 sectors (bfsi, it_services, real_estate, regulated_power) re-run; confirm band returns >500 observations and spans >3 years.

### 3.2 — FMP DCF coverage for Indian equities (4+ sectors affected, also financials agent)

**Where:** `flow-tracker/flowtracker/fmp_client.py` + `flow-tracker/flowtracker/research/data_api.py::get_fair_value_analysis(section='dcf')`.

**Diagnosis needed:** Does FMP's `/stable/discounted-cash-flow?symbol=X.NS&apikey=...` return data for these symbols on the current paid plan? Three outcomes possible:
- (a) Plan doesn't cover Indian equity DCF → document, return `_unsupported_for_indian_equity` flag, agent uses reverse DCF as primary
- (b) Symbol mapping (`.NS` suffix) inconsistent → fix symbol normalization
- (c) Specific sectors (real estate especially) don't fit DCF model → return `_dcf_not_applicable_for_sector` flag, point agent to NAV-based alternative

**Fix:** Add explicit non-empty-or-flag contract. If empty, return `{_status: 'unavailable', reason: '...'}` instead of `{}`. Updates SHARED_PREAMBLE rule that says agents should treat `_status: unavailable` as non-empty (use the reason in Tool Audit).

**Test:** chemicals/PIDILITIND, it_services/TCS, metals/VEDL, real_estate/GODREJPROP re-runs — confirm DCF empty handled gracefully without "investigate FMP" Gemini flag.

### 3.3 — Subsidiary mapping for SOTP (3 sectors affected)

**Where:** `flow-tracker/flowtracker/store.py` — there's likely a `subsidiary_mappings` table or the mapping is computed from concall extraction. Need to identify and update.

**Updates required:**
- BHARTIARTL → INDUSTOWER (~70%), BHARTIHEXA (listed sub)
- NTPC → NTPCGREEN (recent IPO)
- SBIN → SBI General Insurance (unlisted, value via embedded value × 1.5-3×), SBI Cards (listed sub), SBIMF (pre-IPO 2026)
- HDFCBANK → HDFC AMC (listed), HDFC Life (listed), HDB Financial (pre-IPO)
- TATAMOTORS → JLR + listed Tata Tech, etc.

**Source:** BSE/NSE corporate disclosures + Screener subsidiary list per company.

**Fix:** Either (a) refresh the mapping table from a recent corporate-disclosures pull, or (b) make `get_valuation(sotp)` query Screener's company-level subsidiary list dynamically rather than relying on a static cache.

**Test:** telecom/BHARTIARTL, regulated_power/NTPC, bfsi/SBIN, private_bank/HDFCBANK SOTP returns named listed + unlisted subs. Closes telecom's biggest grade gap.

### 3.4 — BFSI asset quality + CASA (1 sector here, also flagged in financials agent)

Already documented in `post-overnight-fixes.md` Phase 6 (concall extractor `bfsi_asset_quality` schema). Coordinate.

### 3.5 — Turnaround margin baseline for projections (1 sector but high impact)

**Where:** `flow-tracker/flowtracker/research/projections.py` — projection tool uses naive 3-yr average margin.

**Fix:** Detect turnaround / newly-profitable companies (margin trajectory shows 2+ recent quarters above 3-yr average by significant margin, OR earliest quarter in window had losses). Use TTM or forward-consensus margin as base instead of historical average.

**Test:** insurance/POLICYBZR re-run — confirm projection no longer outputs negative EPS for now-profitable company.

---

## 6. Phase 4 — Verification

After each phase, re-run the full 14-eval-matrix matrix for valuation agent. Compare:

| Phase | Expected outcome |
|---|---|
| After Phase 1 (prompt-only) | telecom B(85) → A- (closes COMPUTATION + SOTP fallback); auto B+(89) → A- (cash runway from name=execute rule); it_services B+(88) → A- (FCF yield from name=execute rule); existing A- sectors stable or +1; conglomerate A(93) and reg_power A(95) stable |
| After Phase 2 (sector skill files) | More A- → A upgrades as sector-specific frameworks land. Pharma SOTP margin assumption, metals weighting alignment, platform EV/GMV calculation lift their grades. |
| After Phase 3 (data pipeline) | Remaining DATA_FIX flags clear. Bands, DCFs, SOTPs all populate. |

### Re-run cost estimate

- 14 sectors × ~$0.70/agent run = ~$10
- 14 sectors × ~$0.50/Gemini grade = ~$7
- Per re-run cycle: ~$17
- 3 re-run cycles total (after Phase 1, 2, 3) = ~$50

### Regression watch

After Phase 1.1 (SHARED_PREAMBLE strengthening), spot-check 1-2 sectors of each OTHER agent (financials, ownership) to confirm no regression — the calculate-tool change is shared.

---

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Phase 1 prompt patches over-constrain → A- sectors regress | Each tenet uses range language ("highest weight", not "must = 60%"). Spot-check all current A-/A sectors after Phase 1 re-run. |
| SHARED_PREAMBLE strengthening (1.1) hits other agents | Run 2-3 sector spot evals on ownership + financials agent post-Phase-1 before declaring Phase 1 done. |
| Sector skill files contradict each other (e.g., bfsi.md vs private_bank.md disagree on EV-metric handling) | Coherence sweep after batch generation — orchestrator reads bfsi+private_bank valuation.md side-by-side. |
| Subsidiary mapping fix (3.3) requires data engineering work that blocks Phase 1 | Decouple — Phase 1 prompt fix already includes manual SOTP fallback rule that works without DB fix. |
| Gemini outage repeats during validation | Save reports to disk regardless (already proven), batch `--skip-run` re-grade later. |
| Pattern G LLM artifacts persist | Accept. Document. Move on. |

---

## 8. Definition of Done

- [ ] All Phase 1 patches landed in `prompts.py` + `agent-skills-playbook.md`
- [ ] All Phase 2 sector skill files created (14 valuation.md + private_bank gap closure)
- [ ] All Phase 3 data pipeline fixes landed
- [ ] Re-eval all 15 sectors — every one at A- or higher
- [ ] No Pattern A/B/C/D/F issues in any sector's Gemini issues list
- [ ] Pattern E DATA_FIX issues all show `_status: 'unavailable'` flag handling, no raw `(empty)`
- [ ] `fix_tracker.md` updated with cross-cutting patches that other agents should pick up
- [ ] No NOT_OUR_PROBLEM increase (Pattern G held flat at ~3 issues/15 sectors)
- [ ] Spot-check on financials + ownership agents post-Phase-1 — no regression

---

## 9. Cross-agent benefit (why this isn't just a valuation fix)

Several patterns will surface identically when the other 4 untested agents (business, risk, sector, technical) hit their own eval cycles:

| Pattern | Likely impact on other agents |
|---|---|
| A — Fallback tool discipline | Universal. Business agent will under-call concall_insights when peer revenue mix queries return empty; risk agent will under-call governance flag fallbacks. |
| B — Sector framework execution | Universal. Risk agent identifies "spectrum auctions are key risk for telecom" then doesn't quantify; business identifies "switching cost is moat" then doesn't measure. |
| C — Computation discipline | Already in SHARED_PREAMBLE; strengthening here helps all. |
| D — Projection model trust | Specific to financials/valuation agents using projection tool. |
| E — Data infrastructure | All agents that touch fundamentals/valuation. |
| F — Open-questions discipline | Already in OWNERSHIP_SYSTEM_V2; lifting to SHARED_PREAMBLE helps all. |

**Recommendation:** When this plan's Phase 1 lands, lift Patterns A, C, F into SHARED_PREAMBLE (not just VALUATION_SYSTEM_V2). Single cross-agent invariant addition vs. 5× re-discovery cost.

---

## 10. Execution Sequence (optimized)

| Day | Phase | Output |
|---|---|---|
| Day 1 (now) | 1.1 + 1.2 + 1.3 + 1.4 + 1.5 | Single PR `feat/valuation-prompt-patches`, ~150-200 line diff, merged after spot-check |
| Day 1 evening | Phase 4 cycle A | Re-eval 15 sectors with new prompts, expect 3-5 grade lifts |
| Day 2-3 | Phase 2 | 14 valuation.md sector skill files via subagent batch, Gemini-reviewed, merged |
| Day 3 evening | Phase 4 cycle B | Re-eval 15 sectors, expect more A- → A |
| Day 4-7 | Phase 3 | 4-5 data pipeline fixes (PE band, FMP DCF, subsidiary mapping, turnaround margins) |
| Day 7 | Phase 4 cycle C | Final re-eval, target 14/14 A- with most A |

**Total elapsed:** ~1 week
**Total cost:** ~$60 (3 eval cycles + Phase 2 generation + Gemini reviews)
**Net deliverable:** valuation agent at production-grade quality with hardened fallback discipline that informs the next 4 agent harmonizations

---

## 11. Open Decisions for User

1. **Phase 1 SHARED_PREAMBLE edit** — strengthen calculate-tool rule for ALL agents now (riskier — may regress others) OR keep within VALUATION_SYSTEM_V2 only? Recommend: strengthen at SHARED_PREAMBLE with regression spot-check.
2. **Cross-agent invariant lifting** — Patterns A/F to SHARED_PREAMBLE now or wait until business/risk/sector eval cycles surface the same? Recommend: lift now (cheap insurance).
3. **Phase 2 parallelism** — execute alongside the in-flight `full-sector-skills-buildout.md` Phase 2, or sequence (this plan's Phase 2 first, then the buildout)? Recommend: merge — generate all 4 specialist sector files per sector together in one subagent batch (already the buildout's recommended model).
4. **Pattern G acceptance** — formally document NOT_OUR_PROBLEM as accepted noise, OR add a final-pass consistency-check LLM call (cost: ~$3/run, +1-2 min)? Recommend: accept for now, revisit if grade ceiling becomes apparent.
5. **Phase 3 prioritization** — fix all 5 data items, OR only the 2 that block grade lifts (band depth + subsidiary mapping)? FMP DCF empty is a known pre-existing issue, turnaround margin only hits 1 sector. Recommend: do 3.1 and 3.3 as part of the "fix all" remit; defer 3.2 (FMP) to coordinated cross-agent fix; defer 3.5 (turnaround) until a second turnaround stock joins eval matrix.

---

## 12. Appendix — Linked Artifacts

- Per-sector full Gemini reviews (45 issues, all sectors): `/tmp/valuation_issues_dump.md` (should promote to `plans/valuation-eval-results-detail.md`)
- Eval results summary table: `plans/overnight-valuation-fixes.md`
- Cross-agent playbook: `flow-tracker/docs/agent-skills-playbook.md`
- Existing financials/ownership eval patterns to emulate: `plans/post-overnight-fixes.md`
- Phase-1 harmonization commit: `1ba38ec`
