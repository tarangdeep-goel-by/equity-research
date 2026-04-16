# Plan: Comprehensive Valuation Agent Fixes

**Created:** 2026-04-16 (after first end-to-end eval of harmonized valuation agent across 15 sectors)
**Revised:** 2026-04-16 (post-review: corrected Phase 3.1 diagnosis, split Phase 1 into 1a/1b/1c, locked Phase 2 merge model, flagged tenet structural conversion)
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

**Where:** `flow-tracker/flowtracker/research/prompts.py`, `VALUATION_SYSTEM_V2`.

**Structural prerequisite (verified 2026-04-16):** `VALUATION_SYSTEM_V2` is currently a bullet-point "Key Rules" block (~14 bullets, prompts.py:495-524), NOT numbered tenets. `OWNERSHIP_SYSTEM_V2` uses numbered tenets (e.g., Tenet 14 at prompts.py:381). Before adding new rules, **convert `VALUATION_SYSTEM_V2` to numbered tenet format** to match the ownership convention. ~30-line restructure, no semantic change. This pays off when reasoning across agent prompts and when other agents (business/risk/sector) follow the same harmonization.

**Add as new tenets after the existing converted ones:**

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

### 1.6 — Cross-agent invariant lifts to `SHARED_PREAMBLE_V2` (Patterns A + F)

**Where:** `flow-tracker/flowtracker/research/prompts.py`, `SHARED_PREAMBLE_V2`.

**Decision:** §11 #2 locked — lift now rather than re-discover when business/risk/sector/technical agents hit their eval cycles.

**Add as a new shared invariant block:**

> **Fallback tool discipline (Pattern A).** Each agent's tool registry distinguishes primary tools from fallbacks. When a primary tool returns partial/weak/empty data (narrow time window, fewer than the natural minimum observations, empty results, business-mismatched outputs), call the registered fallback before composing your section. Naming the gap in prose is not a substitute for calling the fallback. Your INSTRUCTIONS_V2 contains the agent-specific fallback map; consult it during the workflow's data-collection step.
>
> **Open-questions discipline (Pattern F).** Open questions are reserved for items genuinely unverifiable from your tool registry. Before raising any open question, confirm you have called every fallback tool relevant to the gap. Open questions outside your agent's domain belong to other agents and waste the 3-5 budget. (Lifted from `OWNERSHIP_SYSTEM_V2` Tenet 14 to apply across all specialists.)

**Affects all 8 specialist agents.** The valuation-specific Fallback Tool Map (§1.3) and ownership's open-questions ceiling stay in their agent-specific systems — the shared layer just ensures every agent has the same default discipline. When business/risk/sector/technical agents are harmonized, each will need its own fallback map populated; the shared invariant ensures the rule is already in place when those maps land.

**Regression watch:** the same spot-check from §1.1 covers this — running 2 sectors each through ownership + financials post-Phase-1 confirms no regression from either §1.1 or §1.6.

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

### Generation method — locked: merge with `full-sector-skills-buildout.md` Phase 2

**Decision (locked 2026-04-16):** Execute jointly with `full-sector-skills-buildout.md` Phase 2. Single subagent dispatch model:

- **One subagent per sector** owns ALL specialist files for that sector (business + valuation + risk + sector + any missing financials/ownership). Coherent cross-file framing per sector beats parallel dispatch by file-type, which would split context across 4 subagents per sector.
- **Per-subagent input:** sector eval results (Gemini-flagged issues for that sector across all agents), playbook §3.2 template, the Mandatory Metric Checklist row from §4 above, links to existing `_shared.md` / `financials.md` / `ownership.md` for consistency.
- **Per-subagent output:** drafts of all missing specialist files for that sector. Subagent also flags inconsistencies it finds across the existing files.
- **Review gate:** Gemini review per sector batch → orchestrator spot-checks 3 sectors (1 BFSI, 1 cyclical, 1 platform/IT) for cross-file coherence → revise → merge.

**Updates to `full-sector-skills-buildout.md`:** Phase 2 of that plan must be cross-referenced to point at this plan's §4 mandatory-metric checklists as the input spec for the valuation files.

### Coverage note — `private_bank` doesn't yet have skill files

`private_bank/` exists with `_shared.md`, `financials.md`, `ownership.md` (verified 2026-04-16). Missing only `valuation.md`. Phase 2 generates it as part of the per-sector subagent dispatch.

---

## 5. Phase 3 — Data Pipeline Fixes (Pattern E)

**Scope locked (§11 #5):** 3.1 + 3.3 + 3.4 in this cycle. 3.2 deferred (cross-agent FMP coordination), 3.5 deferred (single-stock impact). Order by leverage:

### 3.1 — PE/PB band depth (8+ sectors affected)

**Where:** `flow-tracker/flowtracker/research/data_api.py::ResearchDataAPI.get_valuation_band()` (and downstream caching layer).

**Original diagnosis was wrong.** `days` default is already **2500 (~6.8yr)** at `data_api.py:429`, not 30. The real root cause is somewhere else in the call chain.

**Diagnostic step (DO THIS FIRST, before any fix):**
1. Run `get_valuation(symbol='HDFCBANK', section='band')` (or any of bfsi / it_services / real_estate / regulated_power tickers that hit the issue) and capture the actual returned obs count + date range.
2. Trace the call chain: `data_api.get_valuation_band` → store query → Screener chart parsing → cache layer. Identify which layer truncates 2500 → ~28.
3. Candidate culprits to inspect:
   - **(a)** Cache layer storing only the most recent month per symbol (TTL or row-cap on the cached chart series).
   - **(b)** Screener `pe` chart endpoint returning full history, but the parser/store retaining only the latest N rows (check store.py insert logic for the chart series table).
   - **(c)** Agent passing a non-default `days` value at the call site — search for `get_valuation(.*band.*days=` in agent prompts/tools to confirm.
   - **(d)** Daily EPS (TTM) gap — if daily EPS isn't backfilled, the JOIN that produces daily PE drops to whatever rows the EPS series has.

**Fix:** Determined by diagnostic step. Document the actual root cause in this section before patching.

**Test:** All 4 sectors (bfsi, it_services, real_estate, regulated_power) re-run; confirm band returns >500 observations and spans >3 years.

### 3.2 — FMP DCF coverage for Indian equities (4+ sectors affected, also financials agent) — **DEFERRED**

**Status (§11 #5):** Deferred from this cycle. Pre-existing issue and cross-agent (financials also affected). Will be picked up alongside the next financials-agent eval cycle when cross-agent coordination is natural.

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

### 3.4 — BFSI asset quality + CASA (1 sector here, also flagged in financials agent) — **COORDINATE, DON'T DOUBLE-TRACK**

**Status (§11 #5):** In scope for this cycle but executed as part of `post-overnight-fixes.md` Phase 6 (concall extractor `bfsi_asset_quality` schema). Do NOT re-implement here. Action: confirm Phase 6 status before Phase 4 cycle B; if not yet shipped, prioritize alongside Phase 3.1/3.3 work.

### 3.5 — Turnaround margin baseline for projections (1 sector but high impact) — **DEFERRED**

**Status (§11 #5):** Deferred. Only insurance/POLICYBZR triggers this in the current eval matrix. Revisit when a second turnaround stock joins the matrix and the pattern is more than n=1.

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

**Phase 1 split into three PRs (revised 2026-04-16)** to isolate cross-agent regression risk. The original "single PR" approach bundled an 8-agent SHARED_PREAMBLE change with valuation-only patches — too much blast radius for one merge.

| Step | Phase | Output | Risk |
|---|---|---|---|
| Day 1 morning | **PR 1a** — SHARED_PREAMBLE patches (§1.1 + §1.6) | Calculate-tool rule strengthening + Pattern A (fallback discipline) lift + Pattern F (open-questions discipline) lift | High — affects all 8 specialists. Spot-check ownership + financials with 2 sectors each before merge. |
| Day 1 afternoon | **PR 1b** — Valuation-only prompt patches (§1.2 + §1.3 + §1.5) | Convert VALUATION_SYSTEM_V2 to numbered tenets, add 6 new tenets, Fallback Tool Map, briefing schema additions | Low — single agent. Re-run 3 below-bar sectors (telecom, auto, it_services) before merge. |
| Day 1 evening | **PR 1c** — Playbook update (§1.4) | I-9 invariant added | Trivial — docs only. |
| Day 2 | Phase 4 cycle A | Re-eval 15 sectors with new prompts, expect 3-5 grade lifts | — |
| Day 3 | Phase 3.1 diagnostic | Trace `get_valuation_band` truncation chain on HDFCBANK; document root cause in §3.1 | — |
| Day 3-4 | Phase 2 | All missing specialist sector files (incl. 14 valuation.md + private_bank gap closure) via per-sector subagent batch, Gemini-reviewed, merged | Medium — coordinate with `full-sector-skills-buildout.md` Phase 2. |
| Day 5 | Phase 4 cycle B | Re-eval 15 sectors, expect more A- → A | — |
| Day 5-7 | Phase 3 | Data pipeline fixes (PE band root cause from §3.1 diagnostic, FMP DCF, subsidiary mapping, turnaround margins) | Medium — touches store/data_api. |
| Day 7 | Phase 4 cycle C | Final re-eval, target 14/14 A- with most A | — |

**Total elapsed:** ~1 week (caveat: Gemini outage history per `feedback_gemini_outage_recovery` may extend by 1-2 days)
**Total cost:** ~$60 (3 eval cycles + Phase 2 generation + Gemini reviews)
**Net deliverable:** valuation agent at production-grade quality with hardened fallback discipline that informs the next 4 agent harmonizations

---

## 11. Locked Decisions (resolved 2026-04-16)

1. **Phase 1 SHARED_PREAMBLE edit** — **LOCKED: strengthen at SHARED_PREAMBLE_V2** with regression spot-check on ownership + financials (2 sectors each) before merge. Affects all 8 specialists. Risk accepted in exchange for one-shot cross-agent benefit. → Implemented in PR 1a (§10).
2. **Cross-agent invariant lifting** — **LOCKED: lift Patterns A (fallback discipline) and F (open-questions discipline) to SHARED_PREAMBLE_V2 now.** Cheap insurance vs. 4× re-discovery cost when business/risk/sector/technical agents hit eval cycles. → Implemented in PR 1a (§10) alongside Decision 1; new §1.6 covers it.
3. **Phase 2 parallelism** — **LOCKED: merge with `full-sector-skills-buildout.md` Phase 2.** Per-sector subagent dispatch (1 subagent owns business + valuation + risk + sector + missing financials/ownership for that sector → coherent framing). → Already documented in §4 "Generation method".
4. **Pattern G acceptance** — **LOCKED: accept and document as known LLM noise** in `fix_tracker.md`. No final-pass consistency-check LLM call. Revisit only if grade ceiling becomes apparent across multiple eval cycles.
5. **Phase 3 prioritization** — **LOCKED: 3.1 + 3.3 + 3.4 only.** Defer 3.2 (FMP DCF — pre-existing, needs cross-agent coordination with financials agent) and 3.5 (turnaround margin baseline — only 1 stock in eval matrix triggers it; revisit when a second turnaround joins). 3.4 (BFSI asset quality) coordinates with `post-overnight-fixes.md` Phase 6 — do not double-track.

---

## 12. Appendix — Linked Artifacts

- Per-sector full Gemini reviews (45 issues, all sectors): `/tmp/valuation_issues_dump.md` (should promote to `plans/valuation-eval-results-detail.md`)
- Eval results summary table: `plans/overnight-valuation-fixes.md`
- Cross-agent playbook: `flow-tracker/docs/agent-skills-playbook.md`
- Existing financials/ownership eval patterns to emulate: `plans/post-overnight-fixes.md`
- Phase-1 harmonization commit: `1ba38ec`
