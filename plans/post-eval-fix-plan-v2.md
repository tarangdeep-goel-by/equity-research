# Post-Eval Fix Plan v2 — 5-Level Hierarchy (April 2026 Re-eval)

**Created:** 2026-04-21
**Source:** 53-grade overnight re-eval (12 sectors × failing-agent subset) triggered on `eval-failing-pairs.sh` between 2026-04-20 21:06 → 2026-04-21 09:53
**Baseline it's measured against:** 2026-04-17 autoeval (84 grades, 119 issues), for which [`plans/post-eval-fix-plan.md`](post-eval-fix-plan.md) v1 was executed (11 PRs merged).
**Purpose:** Plan v1 lifted pass rate 35% → 57%. This plan targets the residual failure modes visible after v1 shipped.

---

## 0. Summary of this eval

| Metric | Baseline (2026-04-17) | Re-run (2026-04-20/21) |
|---|---|---|
| Grades attempted | 84 | 53 (only baseline failures) |
| PASS (≥A-/90) | 42 (50% of 84) | 30 (57% of 53) |
| ERR (Gemini-side) | 20 | 3 (ADANIENT valuation/technical, ETERNAL ownership) |
| Issue count | 119 | 92 (64 PROMPT_FIX + 28 DATA_FIX) |
| Issues/grade | 1.42 | 1.74 |
| Biggest win | — | HDFCBANK valuation F(53)→A-(90) +37; ETERNAL valuation F(50)→B+(88) +38 |
| Regression | — | VEDL valuation B+(87)→F(53) −34 (scratchpad leak + commodity framework mis-apply) |

**Interpretation.** Plan v1 landed the meta-fixes (calculate discipline, framework tenets, L3 sector shared files, E1/E2 data bugs). This plan handles residuals that v1 didn't target and a handful of new patterns that surfaced.

---

## 1. The 5 Levels (same framework)

| # | Layer | Scope | Blast radius |
|---|---|---|---|
| L1 | `SHARED_PREAMBLE_V2` | All specialists | 8 agents |
| L2 | `{AGENT}_SYSTEM_V2` + `{AGENT}_INSTRUCTIONS_V2` | One agent, all sectors | 1 specialist |
| L3 | `sector_skills/{sector}/_shared.md` | One sector, all agents | 1 sector × N agents |
| L4 | `sector_skills/{sector}/{agent}.md` | Single agent-sector pair | Tight |
| L5 | Tool / data / verifier / assembly | Whole pipeline | All reports |

**Decision rule.** Appears in ≥3 agents AND ≥3 sectors → **L1**. 1 agent AND ≥3 sectors → **L2**. ≥3 agents AND 1 sector → **L3**. 1 agent AND 1 sector → **L4**. Root cause is data/tool/assembly → **L5**.

---

## 2. Theme × Prevalence Matrix (from 92 issues)

| Theme | # | agents | sectors | Route |
|---|---:|---:|---:|---|
| Calculate-batching / turn-count | 27 | 7 | 11 | **L1** (known; low priority — ceiling, not FAIL cause) |
| Basis mixing (standalone↔consolidated, argue-then-use) | 8 | 3 | 7 | **L1** (NEW) |
| Giving-up / open-question escape hatch | 5 | 4 | 4 | **L1** (NEW) |
| BFSI structured metric gaps (GNPA/NNPA/PCR/LCR) | 7 | 4 | 2 | **L3 bfsi/private_bank** + **L5 E2.2 data** |
| Segment/subsidiary coverage incomplete | 6 | 4 | 5 | **L2 business/sector** |
| Manual-SOTP fallback when tool empty | 4 | 3 | 3 | **L1** or **L2 valuation** |
| Weight-reallocation silent | 3 | 1 | 3 | **L2 valuation iter3** |
| Scratchpad / monologue leak | 1 | 1 | 1 | **L1 assembly guard** (severe — caused VEDL F regression) |
| Technical-depth gaps (MACD/Bollinger, PCR/OI, estimates) | 4 | 1 | 4 | **L2 technical iter2** |
| Sector-specific data missing (Africa, Vi ARPU, USFDA, UVG) | 6 | 3 | 5 | **L5 E13 sector_kpis** |
| Peer-swap discipline (Yahoo mismatch not handled) | 2 | 1 | 2 | **L2 sector iter2** |
| Reverse-DCF reconciliation | 1 | 1 | 1 | **L2 sector iter2** |
| Named-operation misuse (calculate ops) | 3 | 3 | 3 | **L1 or tool sanity** |
| Tool-registry hallucination | 1 | 1 | 1 | **L1** (covered by plan v1 but still recurring; strengthen) |
| get_valuation basis-mismatch bug | 1 | 1 | 1 | **L5 E11** |
| Projections tool misapplied (manufacturing D&A on platform) | 1 | 1 | 1 | **L5 E12** |
| AR extraction degraded (multi-sector) | 6 | 5 | 5 | **L5 E14** |
| JSON-to-prose consistency | 1 | 1 | 1 | **L2 risk iter1** |
| Framing without quantification | 1 | 1 | 1 | **L2 risk iter1** |
| Macro-via-company-tools routing error | 1 | 1 | 1 | **L2 financials iter2** |
| CFO-for-BFSI applicability | 1 | 1 | 1 | **L2 financials iter2** + **L3 bfsi** |
| SOTP tool newly-listed subsidiary gaps | 2 | 1 | 2 | **L5 E10** |
| ADR/GDR data still missing | 1 | 1 | 1 | **L5 E7** (unfinished from v1) |
| Named FII holders still missing | 1 | 1 | 1 | **L5 E4** (unfinished from v1) |

---

## 3. Phase A — L1 tenets (universal, `SHARED_PREAMBLE_V2` additions)

**PR A1 — Cross-agent tenets from re-eval**

### A1.1. Basis discipline — standalone vs consolidated (NEW, high blast)

**Evidence:** 8 occurrences, 3 agents, 7 sectors. Flavors:
- SBIN valuation: standalone-ROE-derived P/B applied directly to consolidated BVPS
- POLICYBZR valuation: historical standalone PE × consolidated forward EPS
- GODREJPROP valuation: argues PE is meaningless (IndAS 115) then uses 35–40x PE on FY28 EPS
- HDFCBANK business: cites ROCE then notes "ROCE meaningless for banks"
- SBIN financials: 5Y cumulative CFO as dividend-sustainability proxy, then flags CFO as structurally meaningless for BFSI

**Tenet text:**
> Every multiple or ratio you cite (PE, P/B, EV/EBITDA, ROCE, P/Presales, CFO-coverage, etc.) has an implicit basis — standalone or consolidated, pre-tax or post-tax, trailing or forward. You MUST: (a) state the basis of the inputs AND the basis of the multiplicand before computing a fair value; (b) refuse to mix bases (e.g., standalone ROE → standalone P/B, applied to *consolidated* BVPS is forbidden); (c) if you dismiss a metric as inapplicable to the sector in one paragraph ("ROCE is meaningless for banks", "CFO is structurally meaningless for BFSI", "PE misleads for IndAS 115 companies"), you MUST NOT use that metric for conclusions elsewhere in the same report. Consistency is a COMPUTATION-level check.

### A1.2. AR → Deck → Concall fallback chain (NEW, high blast)

**Evidence:** 5 explicit give-up issues + "open question" escape hatch appearing in 4 sectors.
- SUNPHARMA sector: USFDA status left as open question without checking deck/AR
- GODREJPROP risk: city-level presales only checked concalls, ignored investor presentation
- BHARTIARTL ownership: skipped 3Y bulk/block query citing "budget constraints"
- HINDUNILVR business: segment revenue missing — AR degraded, no deck fallback attempted
- ETERNAL valuation: didn't attempt manual SOTP after automated SOTP returned empty

**Tenet text:**
> Before raising any "open question" for a missing metric, you MUST exhaust the mandatory fallback chain and document each step in your Tool Audit: **(1)** the structured tool (`get_fundamentals`, `get_quality_scores`, `get_sector_kpis`) — if empty, **(2)** `get_annual_report(section=X)` — if degraded or empty, **(3)** `get_deck_insights(sub_section=Y)` — if empty, **(4)** `get_concall_insights(sub_section=Z)`. Only after all four fail may you raise it as an open question, and the question MUST name each step you attempted. "Budget constraints" is NEVER a valid reason to skip a mandatory-metric query. "The tool returned empty" is the START of your work, not the end.

### A1.3. Scratchpad / monologue assembly guard (L1 + L5 hybrid)

**Evidence:** 1 catastrophic occurrence — VEDL valuation dropped F(53) because the agent output its internal monologue instead of the report.

**Tenet text + L5 enforcement:**
> (Prompt) The first line of your report MUST be the report header. Internal thinking (`<thinking>`, `Let me think...`, scratchpad tables) must NEVER appear in the report body. (L5) `assembly.py` hard-aborts the report if it contains `<thinking>`, `</thinking>`, `[SCRATCH]`, `Let me think`, `Actually,`, `Wait —`, or similar monologue markers at the top level — surfaces as COMPUTATION-grade failure for regrade.

### A1.4. Manual-SOTP fallback (NEW)

**Evidence:** 3 occurrences — HDFCBANK valuation (HDBFS missing), NTPC valuation (NTPCGREEN missing), ETERNAL valuation (food-delivery/Blinkit SOTP not attempted).

**Tenet text:**
> When `get_valuation(section='sotp')` returns empty, incomplete, or stale, you MUST attempt a manual SOTP using `get_company_context(subsidiaries)` + `get_fundamentals(section='revenue_segments')` per subsidiary/segment. Table structure required: `[Segment | Revenue FYxx | Multiple applied | Basis | Implied Value Cr | % of blended FV]`. Only skip manual SOTP when zero segments/subsidiaries disclose standalone revenue.

### A1.5. Weight-reallocation audit line (TIGHTEN v1 Phase 1 Tenet 22)

**Evidence:** Still recurring despite shipping in PR #47. Flavors:
- SUNPHARMA valuation: manually adjusted to 55/45 but cited tool's unadjusted 50/50 blend as final
- HINDUNILVR valuation: DCF empty, reallocated DCF weight without note
- NTPC valuation: weight handling implicit

**Tenet text:**
> When any component of the blended fair value is empty, removed, or downweighted, the report MUST include a single dedicated line immediately before the blended-FV figure: `Blend adjustment: original 40/30/30 (PE/DCF/Peer) → [reason for change] → final weights 57/0/43`. If you cite any tool's auto-blended number AFTER adjusting weights manually, that's a COMPUTATION violation — recompute the blend with your weights.

### A1.6. Named-operation discipline for `calculate` (EXTEND v1)

**Evidence:** 3 occurrences — POLICYBZR ownership (used `pct_of` to extract value from a percentage; `growth_rate` for pp differences), GODREJPROP technical (used `margin_of_safety` for price vs SMA % delta), SUNPHARMA ownership (duplicate calcs).

**Tenet text:**
> Named `calculate` operations have strict input semantics. `pct_of(a,b)` returns `a as % of b`, not "extract a from percentage b". `growth_rate` is for time-series, NOT for percentage-point differences. `margin_of_safety(fv,price)` is for valuation gap, NOT for price vs SMA delta. Read the tool description before using. Using a named op for the wrong purpose is a PROMPT_FIX violation. Duplicate calls with identical inputs are also flagged — check your Tool Audit before recomputing.

**PR A1 total cost:** 1 PR, ~120 line diff in prompts.py + ~20 line assembly.py guard. **Expected lift:** +6–10 reports.

---

## 4. Phase B — L2 agent iterations

### B1. Valuation iter3

**Residuals after v1:** 10 PROMPT_FIX + 2 DATA_FIX (VEDL F, NTPC SOTP gap, POLICYBZR basis mismatch, HINDUNILVR DCF empty reallocation, GODREJPROP tool hallucination, ETERNAL manual SOTP not attempted, SUNPHARMA weight math).

**New tenets (beyond L1):**
- **Per-share derivation chain** — every "target price" MUST have a visible chain: `blended_fv_cr → /shares → per_share_target`. Use `calculate(operation='total_cr_to_per_share')`, not in-prose division.
- **Tool-registry re-reminder** — `get_quality_scores` valid sections are `bfsi | metals | telecom | default`. No other sections exist. If you need cashflow quality, use `get_fundamentals(section='cash_flow_quality')` — different tool.
- **Auto-SOTP is best-effort** — treat tool output as seed, always cross-check against current market caps for listed subsidiaries via `get_market_context(section='peer_metrics')` when available.

**L5 dependency:** E11 (get_valuation basis bug) and E12 (projections depreciation) must ship before this fully lifts. Without E11, POLICYBZR valuation will re-fail on basis mismatch.

### B2. Business iter2 — highest-issue-count agent (18 issues, 10 sectors)

**Recurring patterns:**
- Sector-applicability contradictions (ROCE for banks, NPAs for marketplaces, PE for real-estate)
- Mandatory tool not dispatched (conglomerate business agent didn't call `get_valuation(sotp)` for ADANIENT)
- Segment coverage incomplete (ETERNAL ignored Hyperpure/District; BHARTIARTL missing segmental revenue)
- Missing sector KPIs (Top-5/10 client concentration for IT services)

**New tenets:**
- **Sector-applicability filter** — before citing ANY ratio in a business profile table, check the sector-skill's applicable-metrics list. Don't show ROCE in a BFSI business table. Don't show PE as a primary ratio for real-estate developers. If no applicable metric exists in a category, omit the row — don't fill with a caveated one.
- **Mandatory tool dispatch per sector-type:**
  - Conglomerate → `get_valuation(section='sotp')` + `get_company_context(section='subsidiaries')` BOTH required
  - BFSI → `get_quality_scores(section='bfsi')` + concall asset-quality drill if structured empty
  - Platform / Multi-segment → `get_fundamentals(section='revenue_segments')` + deck `segment_performance`
  - IT Services → `get_company_context(section='client_concentration')` if present, otherwise concall drill
- **Segment completeness** — if the company discloses N segments in its FY AR or deck, the business profile MUST have N segment rows (or explicit "consolidated only" declaration with reason).

### B3. Sector iter2

**Recurring patterns (12 issues, 9 sectors):**
- Peer-swap not attempted after Yahoo mismatch detected (BHARTIARTL)
- Reverse-DCF implied growth >> historical, verdict doesn't reconcile (BHARTIARTL)
- Multi-segment conglomerate coverage (POLICYBZR Paisabazaar, ETERNAL Hyperpure)
- Channel/mix extraction (HINDUNILVR)

**New tenets:**
- **Peer-swap discipline** — if `get_yahoo_peers` returns a set with >50% sector-mismatch (e.g., ZOMATO → IRFC/JIOFIN/LICI), you MUST call `get_screener_peers` and reconcile. Noting the mismatch without swapping is a PROMPT_FIX.
- **Reverse-DCF reconciliation** — if your implied-growth output says "price assumes X% growth" and X > 1.5× the 5Y historical CAGR, the verdict section MUST explicitly acknowledge this gap (e.g., "Requires acceleration from 14% to 21% growth — a high-conviction bet on [specific catalyst]"). Don't output bullish verdicts without this reconciliation.
- **Multi-segment economics mandatory** — for companies where any segment is ≥15% of revenue or valuation, the sector report MUST have a segment-economics subsection (not just a mention in overview). Applies across platform, insurance+credit, conglomerates, BFSI+BFSI-subsidiaries.

### B4. Financials iter2

**Recurring (11 issues):**
- Macro data via company tools (NTPC searched 10Y G-sec via company-specific tools)
- CFO-for-BFSI applicability (SBIN)
- UVG/price decomposition missing for FMCG (HINDUNILVR)

**New tenets:**
- **Macro routing guard** — macro series (10Y G-sec, inflation, commodity spot, USD-INR, WACC inputs) MUST route through `get_market_context(section='macro')`. Company-specific tools (`get_fundamentals`, `get_quality_scores`, `get_concall_insights`) do NOT contain macro data. If you search them, you're wasting turns.
- **CFO-for-BFSI guard** — for banks and NBFCs, operating cashflow is dominated by deposit/loan flow and is NOT a dividend-sustainability signal. Use `dividend_payout_ratio` or `total dividend / net_profit` instead. Citing CFO coverage for a BFSI dividend is a COMPUTATION-downgrade.
- **Volume-vs-price decomposition for FMCG** — for any FMCG with >₹10,000 Cr revenue, the financials report MUST extract historical UVG (underlying volume growth) vs price-led growth split for the last 4 quarters. Source chain: structured tool → concall financial_metrics → deck charts_described. If all empty, raise as specific open question per A1.2.

### B5. Risk iter1 (NEW — skipped in v1)

**Residuals (5 issues):**
- JSON-to-prose consistency (SUNPHARMA KSM/China in JSON, not in text)
- Framing without quantification (POLICYBZR CAC vs LTV stated, not quantified)
- Deck consult missed for sector-specific risks (GODREJPROP city-level presales)
- Leading-indicator gaps (TCS utilization, headcount additions)

**New tenets:**
- **JSON-to-prose parity** — every metric in the `mandatory_metrics` JSON section MUST have a corresponding narrative sentence with interpretation. JSON without prose is a PROMPT_FIX.
- **Framing-quantification symmetry** — any risk axis you frame (CAC vs LTV, commodity vs margin, interest coverage) MUST be quantified with specific numbers in the cost-structure or risk-decomposition section. Framing without numbers is hand-waving.
- **Sector-specific leading indicators** — risk agent per-sector mandatory set:
  - IT Services: utilization %, headcount additions, attrition, sub-100-day accounts concentration
  - BFSI: SMA-2, restructured book, AIF/AT1 exposure
  - Real Estate: city-level presales, inventory velocity, debt maturity profile
  - Platform: CAC payback, cohort retention, take-rate trend
  - Pharma: KSM/China dependency %, USFDA facility status, regulatory pipeline risk
- **Deck-primary risks** — state-level presales (real estate), capacity-mix (metals), utilization (IT) primarily live in the deck, not the concall. Risk agent MUST consult deck for these.

### B6. Technical iter2

**Residuals (4 issues):**
- Dedicated indicators skipped (HDFCBANK MACD/Bollinger)
- Derivatives missing for F&O stocks (NTPC PCR/OI)
- `get_estimates` skipped, relied on proxy (SUNPHARMA)
- Misused named operations (GODREJPROP `margin_of_safety` for % vs SMA)

**New tenets:**
- **Indicator completeness** — if `get_market_context(technicals)` returns MACD, Bollinger, or ADX, you MUST use them. Screener SMAs + RSI alone is not sufficient for an institutional technical report. Add explicit note ONLY if the indicator data is genuinely empty.
- **F&O derivatives mandatory** — for any stock where `get_market_context(technicals).fo_enabled == true`, PCR, OI, and rollover metrics MUST appear in the technical report. If the sub-section returns empty, explicit open question per A1.2.
- **Estimate revision momentum** — `get_estimates(section='revision_history')` is the authoritative source for analyst revision momentum. Using a composite proxy from the analytical profile is a PROMPT_FIX downgrade.

### B7. Ownership iter4 (NEW iteration — was iter3 before)

**Residuals (4 issues):**
- "Budget constraint" skip of mandatory metrics (BHARTIARTL 3Y bulk/block)
- Named-op misuse (POLICYBZR)
- Redundant calculation (SUNPHARMA duplicate LIC valuation)

**New tenets:**
- **No mandatory-metric skips** — the mandatory-metrics list in OWNERSHIP_INSTRUCTIONS is non-negotiable. "Budget constraints" / "to save turns" / "tool returned slowly" are NOT valid reasons. If a mandatory metric's tool truly errors out, raise a specific open question naming the tool and the error — don't silently omit.
- **Calc-dedup awareness** — before calling `calculate`, review your Tool Audit for existing identical invocations. Redundant calls are PROMPT_FIX downgrades.

---

## 5. Phase C — L3 sector `_shared.md` iterations

### C1. bfsi / private_bank (HIGH priority — E2 still leaking)

**Residuals:** 4 issues across SBIN + HDFCBANK. Plan v1's bfsi/_shared.md said "mandatory for business/financials/risk agents: LCR + CD ratio + credit cost trajectory + non-interest income split" — but it's still being missed.

**Additions:**
- **Tighten enforcement wording** — change "mandatory for … agents" to "Missing GNPA / NNPA / PCR / LCR / CRAR / CET-1 when the bank is in the Nifty-50 BFSI cohort is a PROMPT_FIX downgrade. Extract from the chain: `get_quality_scores(bfsi)` → `get_sector_kpis(banks)` → `get_concall_insights(financial_metrics)` → AR `segmental`. Cite the value with 1-decimal precision (e.g., GNPA 2.1%, not 'below 3%')."
- **CFO-for-BFSI clarification** — add: "Operating cash flow for banks is dominated by deposit/loan flow swings. Do NOT use CFO to argue dividend sustainability. Use dividend payout % or (dividend_paid / net_profit) instead."
- **ROCE exclusion** — add: "ROCE is NOT a valid KPI for BFSI. Do not include it in the business profile or financial summary table. If `get_fundamentals` returns ROCE, ignore it for narrative purposes."

### C2. conglomerate (HIGH priority)

**Residuals:** ADANIENT business skipped `get_valuation(sotp)` despite identifying SOTP as "only honest framework".

**Additions:**
- "Any conglomerate report (business or valuation) without a SOTP table is structurally incomplete. `get_valuation(section='sotp')` is mandatory; if it returns empty, manual SOTP per L1 A1.4 is mandatory."
- "Subsidiary market cap refresh: since auto-SOTP may be stale for recently-listed subsidiaries (e.g., HDBFS Jul 2025, NTPCGREEN 2025), cross-check with `get_market_context(section='peer_metrics')` or direct symbol lookup when available."

### C3. platform (MEDIUM)

**Residuals:** ETERNAL — Hyperpure/District ignored, manual SOTP not attempted, projections tool applies manufacturing depreciation.

**Additions:**
- "Multi-vertical platforms (food + quick commerce + B2B + payments) — every vertical ≥5% of GMV or ≥10% of revenue MUST have its own section in business report AND separate valuation component in the SOTP."
- "Projections tool caveat: `get_projections(section='income_statement')` applies default 5% D&A assumption suitable for manufacturing. For asset-light platforms, override with asset-turnover-based projection (revenue × 0.5–1.5% D&A) or note the mis-applied assumption explicitly."

### C4. insurance (MEDIUM)

**Residuals:** POLICYBZR — standalone-vs-consolidated basis mismatch in `get_valuation`, Paisabazaar segment under-covered, marketplace NPAs unclear.

**Additions:**
- "POLICYBZR / insurance-marketplaces have two economically distinct segments (Policybazaar = insurance distribution; Paisabazaar = credit marketplace). Both MUST be analyzed separately. Reporting only the insurance side is incomplete."
- "If reporting NPAs for a marketplace, clarify whether the company takes balance-sheet risk (FLDG, co-lending) or is pure-marketplace. A pure marketplace should not have NPAs — if the JSON contains NPA, it's reporting channel-partner data and MUST be framed as such."
- "Valuation basis for conglomerate insurance — `get_valuation` may return fair values that mix standalone historical PE with consolidated forward EPS. Flag and recompute with matching bases per L1 A1.1."

### C5. real_estate (MEDIUM — TIGHTEN)

**Residuals:** GODREJPROP risk skipped investor deck for city-level presales.

**Additions:**
- **Escalation wording:** "Investor deck is the PRIMARY source for city-level presales, absorption rates, and book velocity — NOT concalls and NOT structured tools. Risk and business agents MUST call `get_deck_insights(sub_section='segment_performance' | 'charts_described')` before raising any city-level or project-level gap as an open question."
- "Real-estate valuation framework priority (unchanged from v1): P/Presales > NAV > P/Ops > Peer > PE. If prose argues against PE (IndAS 115 distortion), valuation MUST NOT blend PE-based numbers in later — per L1 A1.1."

### C6. fmcg (TIGHTEN)

**Residuals:** HINDUNILVR — channel mix still not extracted, UVG/price decomp missing.

**Additions:**
- Already has channel-mix mandate from plan v1. Tighten: "If `get_fundamentals(revenue_segments)` returns 0 channel fields (GT/MT/e-comm), you MUST open `get_deck_insights(sub_section='charts_described')` — HUL and similar cos disclose channel splits in their deck charts, not in Screener's structured feed."
- "FMCG financials agent: historical UVG vs price decomposition is mandatory (last 4 quarters). Chain: concall `financial_metrics` → deck `highlights`. Missing this is a PROMPT_FIX."

### C7. it_services (NEW — TCS)

**Residuals:** TCS — Top 5/10 client concentration missed, utilization/headcount missed.

**Additions:**
- "IT Services business/risk agents MUST cite: (a) Top-5 and Top-10 client concentration %, (b) utilization rate (onsite/offshore), (c) net headcount additions latest quarter, (d) attrition (LTM). Source chain: `get_company_context(client_concentration)` → concall `operational_metrics` → deck `highlights`. All four are mandatory for a Tier-1 IT report."

---

## 6. Phase D — L4 tight fixes

Tight, agent-sector-pair issues. Cherry-pick post-L1-L3 re-eval.

- **valuation/VEDL/metals** — scratchpad leak (L1 A1.3 + L5 assembly guard). Primary fix already at L1/L5.
- **valuation/GODREJPROP/real_estate** — `get_quality_scores(sections=['cash_flow_quality','capital_allocation'])` hallucination (L1 covers tool-registry, but this specific mis-use suggests adding a hard-list to `get_quality_scores`'s tool description).
- **technical/GODREJPROP/real_estate** — `margin_of_safety` op misuse for price-vs-SMA (L1 A1.6 covers).
- **valuation/ETERNAL/platform** — manual SOTP skip (L1 A1.4 + L3 platform cover).
- **risk/POLICYBZR/insurance** — CAC/LTV framing without quantification (L2 B5 covers).
- **financials/SBIN/bfsi** — CFO-for-BFSI contradiction (L2 B4 + L3 bfsi cover).

All expected to resolve via L1/L2/L3 above. No L4-only work needed.

---

## 7. Phase E — L5 non-prompt (tool / data / assembly / verifier)

### E1 (from v1) — status: SHIPPED via PRs #52 + #53. No further action.

### E2.2. BFSI asset-quality extraction revisited — NEW, HIGH blast
**From v1:** PR #51 updated concall extractor for GNPA/NNPA/PCR. But re-eval shows SBIN financials + HDFCBANK financials still missing these from structured data.

**Hypothesis:** PR #51 updated the concall extraction prompt but:
- `get_quality_scores(bfsi)` schema may still not return them
- `get_sector_kpis(banks)` canonical keys may not be populated
- Legacy extracted concalls pre-#51 won't have them (need re-extraction)

**Fix:**
1. Audit `get_quality_scores(bfsi)` return shape — ensure GNPA/NNPA/PCR/CRAR/CET-1 are first-class fields
2. Force re-extraction of all BFSI stocks' last 4 concalls with the updated prompt
3. Add `get_sector_kpis(banks)` fallback that reads from `concall_insights.financial_metrics`
4. Peer_metrics table for BFSI sector — include NIM, GNPA, C/I for peer-compare

**Affects:** 4+ reports across bfsi + private_bank.

### E4 (from v1) — Named FII holders in `shareholder_detail`
**Status:** Still not shipped. BHARTIARTL ownership: "shareholder_detail failed to return named FII holders".
**Fix:** parse BSE XBRL for named foreign-institutional holders at ≥1% threshold. Same as v1.

### E7 (from v1) — ADR/GDR extraction
**Status:** Still not shipped. HDFCBANK ownership: "ADR/GDR outstanding data is missing".
**Fix:** BSE annual report parsing for depositary-receipt notes. Same as v1.

### E10. SOTP tool freshness for newly-listed subsidiaries — NEW
**Evidence:** HDB Financial Services (listed Jul 2025) absent from `get_valuation(sotp)` output for HDFCBANK. NTPCGREEN Energy (listed 2025) absent from `get_valuation(sotp)` for NTPC.

**Root cause:** `get_valuation(sotp)` seeds its subsidiary list from a cached holdings table, not from the live BSE/NSE listing calendar.

**Fix:**
1. `research/data_api.py::get_valuation` — subsidiary list should query `index_constituents` + recent listings from `bhavcopy` (last 180 days) filtered by parent-ownership metadata.
2. Or: add a `subsidiaries_listed_recently` field that flags newly-listed entities for agent attention.
3. Manual SOTP fallback (L1 A1.4) partially mitigates.

### E11. `get_valuation` basis-mismatch bug — NEW, HIGH blast
**Evidence:** POLICYBZR valuation — "tool computes fair value by multiplying historical standalone-basis PE multiples against consolidated forward EPS, creating a massive basis mismatch."

**Root cause:** The tool doesn't check whether the PE history cache (from Screener) and the EPS projection (from FMP / our projections) are on the same basis.

**Fix:**
1. `data_api.py::get_valuation` — add `pe_basis` and `eps_basis` fields to the output
2. Return a structured warning when bases don't match
3. When mismatch, downrank the PE-band component weight to 0 (or let the agent do it explicitly)

**Affects:** Every conglomerate-structure valuation where standalone/consolidated differs materially (POLICYBZR, banks-with-listed-subs, ADANIENT).

### E12. Projections tool sector-aware depreciation — NEW
**Evidence:** ETERNAL valuation — "The projections tool applies manufacturing-company depreciation logic (5.1% of revenue) to an asset-light platform, resulting in broken EPS projections."

**Root cause:** `get_projections` uses a single default D&A-as-%-of-revenue across all industries.

**Fix:**
1. `research/projections.py` — route D&A ratio by industry:
   - Manufacturing / metals / cement: 4–6% of revenue (current default)
   - IT Services / Platform / Insurance: 0.5–1.5% of revenue
   - BFSI: project from `depreciation` line item directly, not % of revenue
   - Real Estate: project from fixed-asset base
2. Add `_projection_assumptions` meta field so the agent sees which basis was used and can caveat.

### E13. sector_kpis coverage expansion — CONTINUING from v1 E3
**Evidence:**
- pharma R&D spend %, USFDA facility status — still gaps (SUNPHARMA)
- FMCG UVG vs price decomposition — still missing (HINDUNILVR)
- Telecom Vi ARPU, Airtel Africa constant-currency growth — still missing (BHARTIARTL)

**Fix:** Extend concall extractor `sector_kpis` config:
- `pharma`: `rd_pct`, `usfda_facility_status`, `anda_approvals_ltm`, `key_molecule_pipeline`
- `fmcg`: `uvg_pct`, `price_growth_pct`, `channel_gt_pct`, `channel_mt_pct`, `channel_ecom_pct`, `rural_urban_split`
- `telecom`: `arpu_inr`, `subscribers_mn`, `africa_cc_growth_pct`, `africa_fx_devaluation_pct`

Run backfill extractor against last 4 concalls of all Nifty-250 stocks in these sectors.

### E14. AR extraction robustness — NEW, MEDIUM blast
**Evidence:** 6 degraded-extraction issues across the run. Sections that timed out or returned partial:
- SUNPHARMA FY24/25 `mdna`, `auditor_report` — degraded
- NTPC `segmental` — degraded (NGEL ownership % missing)
- NTPC `regulatory` — degraded (RDA balance missing)
- HINDUNILVR FY25 segmental — timed out, forced agents to estimate
- ETERNAL FY25 `auditor_report` — returned only CARO Annexure B, missing KAMs
- POLICYBZR FY25 `notes_to_financials` + `auditor_report` — degraded

**Root cause:** Claude-subprocess crashes (the known SDK `exit 1` class) + large-section timeouts. Current extractor logs warning and moves on without retry.

**Fix:**
1. Per-section retry with exponential backoff (3 tries, 30s/60s/120s waits)
2. Section-chunking for large sections (>80 KB) — split and concatenate extracts
3. When all retries fail, flag `_meta.degraded_quality: true` AND write a specific `_meta.missing_sections: [...]` list so downstream agents know the exact gap
4. BRSR already opt-in (shipped earlier today); this fix targets the non-opt-in sections

### E15. `projections` + `get_fair_value_analysis` DCF empty fallback — NEW
**Evidence:** HINDUNILVR valuation — "get_fair_value_analysis(dcf) returned empty, forcing the agent to reallocate DCF weight entirely." NTPC valuation had similar pattern (pbv chart also empty).

**Fix:** When DCF empty, return a reason code (`insufficient_history`, `negative_fcf`, `growth_above_limits`) so the agent can decide between (a) manual DCF, (b) explicit DCF-N/A note, (c) reallocation with documented reason.

### E16. Sector-index coverage — NEW, LOW blast
**Evidence:** HDFCBANK technical — "Sector index returned null for 'Banks-Regional' classification." GODREJPROP technical — `perf_sector_index` null.

**Fix:** Map sub-sector classifications (Banks-Regional, REIT, Platform) to their actual NSE sector indices (BANKNIFTY, or fallback to NIFTY FINANCE). Missing indices default to Nifty-500 rather than null.

### E17. Assembly-time scratchpad guard — PAIRED WITH L1 A1.3
**Fix:** In `research/assembly.py`, before writing the final report:
```python
MONOLOGUE_MARKERS = [r"<thinking>", r"</thinking>", r"\[SCRATCH\]",
                     r"^Let me think", r"^Actually,", r"^Wait —",
                     r"^OK so", r"^Hmm[ ,]"]
if any(re.search(p, report_text[:2000], re.MULTILINE) for p in MONOLOGUE_MARKERS):
    raise ReportAssemblyError("Scratchpad/monologue detected in report body — rerun agent")
```
This catches the VEDL-style failure at assembly time before the grade is wasted.

---

## 8. Execution Sequence

| # | PR | Scope | Risk | Expected lift |
|---|---|---|---|---|
| 1 | **L1 A1.1–A1.6** (basis, fallback chain, scratchpad tenet, manual SOTP, weight audit, named-op) + **L5 E17** assembly guard | All 7 agents | Low | +6–10 reports, prevents VEDL-class regressions |
| 2 | **L5 E11** get_valuation basis bug + **L5 E12** projections sector-aware | Tool layer | Medium | Unblocks valuation iter3; fixes POLICYBZR/ETERNAL |
| 3 | **L3** bfsi+private_bank, conglomerate, insurance, platform, fmcg, real_estate, it_services | 7 sector families | Low | +5–8 reports |
| 4 | **L2 B2** business iter2 (highest issue count) | Business agent only | Low | +3–4 reports |
| 5 | **L2 B3** sector iter2 | Sector agent only | Low | +2–3 reports |
| 6 | **L2 B5** risk iter1 (first iteration for this agent) | Risk agent only | Medium | +2–4 reports |
| 7 | **L5 E2.2 + E13** BFSI extraction revisited + sector_kpis expansion | Data layer | Medium | +4–5 reports |
| 8 | **L2 B4** financials iter2 + **L2 B6** technical iter2 + **L2 B7** ownership iter4 + **L2 B1** valuation iter3 | 4 agents | Low | +4–6 reports |
| 9 | **L5 E14** AR robustness + **E10** SOTP freshness + **E15** DCF fallback + **E16** sector index | Data layer | Medium | +2–3 reports + fewer "degraded" flags |
| 10 | **L5 E4** named FII + **E7** ADR/GDR (carry-over from v1) | Data layer | Low | +1–2 reports |
| 11 | **Re-eval** failing-pairs + 3 ERRs | All | — | measure |
| 12 | **L4** cherry-pick (post re-eval) | Single cells | Low | +1–2 reports |

**Estimated pass-rate trajectory:**
- Now: 57%
- After #1+#2 (L1 + critical L5 bugs): ~68%
- After #3+#4+#5 (L3 sector + L2 business/sector): ~76%
- After #6+#7+#8 (remaining L2 + BFSI data): ~83%
- After #9+#10 (data layer completion): ~87%
- Target: **85–90% pass rate**

---

## 9. What NOT to Change (accepted)

Per `feedback_substantive_fixes.md` + `feedback_gemini_outage_recovery.md`:

- **Calculate-batching / turn-count as PROMPT_FIX** — Gemini flags ~27 times but user-confirmed (2026-04-21) that sequential calcs aren't the primary FAIL cause as long as the data is used. Dependency-chain sequential is legitimate. Cost ceiling concern only. **Do not chase unless an individual agent exceeds 50 turns or $2/report.**
- **Gemini-side ERRs (3 from this run)** — regrade with `--skip-run` when convenient; no prompt change needed.
- **`NOT_OUR_PROBLEM` class (2 issues)** — LLM phrasing artifacts; accept as noise.

---

## 10. Open Decisions

1. **Should L1 A1.3 scratchpad guard abort agent or attempt auto-cleanup?** Recommendation: abort with explicit error. Cleaning up scratchpad text-edits can mask real report-quality issues.
2. **L5 E12 projections default for "unknown" industry** — if industry classifier can't resolve, default to 2% D&A (midpoint) with explicit caveat flag, not the manufacturing 5%.
3. **L3 bfsi metric enforcement level** — should we add a hard verifier check that GNPA/NNPA/PCR appear in BFSI reports? Recommendation: yes, as verifier-audit tenet in PR #1 alongside L1 lifts. Small addition.
4. **Re-extraction scope for E2.2** — all Nifty-250 BFSI concalls (~40 stocks × 4 quarters = 160 extracts) or only the 5 BFSI names we eval against? Start narrow (eval stocks) to validate fix, then broadcast.

---

## 11. Appendix — Issue inventory (raw)

- **64 PROMPT_FIX** grouped by agent in conversation transcripts (2026-04-21 session).
- **28 DATA_FIX** listed verbatim in same transcripts.
- Full Gemini JSONs: `flow-tracker/flowtracker/research/autoeval/eval_history/20260420T17*_all_for_*.json` through `20260421T04*_all_for_*.json` (53 files).
- Grade delta vs 2026-04-17 baseline: 32 wins (+3 or more), 17 flat, 1 content regression (VEDL valuation), 3 Gemini ERRs.

**Plan doc for v1:** [`plans/post-eval-fix-plan.md`](post-eval-fix-plan.md) — 11 PRs merged 2026-04-17.

---

## 12. Appendix B — Agent-level diagnostic (sector-agnostic)

This view complements §4 (agent iterations) by looking at each agent's failure modes across all sectors at once, independent of sector specifics. It exposes which agents are the weakest and what their characteristic failure shapes are.

### 12.1 Pass-rate ranking

| Agent | Runs | Passes | PASS rate (ex-ERR) | Avg score | # Issues | Status |
|---|---:|---:|---:|---:|---:|---|
| **technical** | 5 | 4 | **100%** (4/4) | 93.0 | 7 | best |
| **risk** | 5 | 5 | **100%** (5/5) | 91.0 | 7 | best |
| **ownership** | 5 | 3 | 75% (3/4) | 90.2 | 6 | OK |
| **valuation** | 10 | 7 | 78% (7/9) | 86.1 | 18 | content-heavy |
| **business** | 12 | 6 | 50% | 88.9 | 23 | WEAK |
| **financials** | 9 | 3 | 33% | 89.4 | 19 | WEAK |
| **sector** | 7 | 2 | 29% | 89.0 | 16 | WEAKEST |

**Reading the ranking.** The three weak agents (business, financials, sector) share one property — they synthesize content across many tools for a wide topic. The strong agents (technical, risk, ownership) are narrower in scope, closer to single-source analysis. The valuation agent sits in the middle because its scope is focused but every mistake has high content weight.

### 12.2 Business — sector-agnostic patterns (50% PASS, 23 issues)

1. **Sector-applicability contradictions.** Agent cites a ratio then caveats it as meaningless in the same report (ROCE for banks, NPAs for a pure marketplace, PE for IndAS-115 real-estate). Fix: **sector-aware metric filter** — hard-omit non-applicable ratios per sector-skill applicable-list. Routed to **§4 B2** (business iter2).
2. **Mandatory tool not dispatched.** Conglomerate agents skip `get_valuation(sotp)` even when they name SOTP as the right framework. BFSI agents miss GNPA/NNPA/PCR despite L3 bfsi/_shared.md. Fix: **sector-type → mandatory-tool map** in BUSINESS_INSTRUCTIONS_V2. Routed to **§4 B2**.
3. **Segment coverage incomplete.** N disclosed segments, N-k rows in the profile table — common in conglomerates, platforms, insurance+credit. Fix: **segment-completeness gate**. Routed to **§4 B2**.
4. **JSON-to-prose gap.** Mandatory-metrics JSON populated but narrative silent. Routed to **§4 B5 risk iter1** (same tenet applies to business).

### 12.3 Financials — sector-agnostic patterns (33% PASS, 19 issues)

1. **Metric-consistency violations (use-then-disavow).** Same shape as business but here it hits CFO-for-BFSI most often. Routed to **§3 A1.1** (L1 basis + consistency discipline).
2. **Macro-routing error.** Agent searches company-specific tools for macro data (10Y G-sec, inflation). Fix: **explicit macro guard**. Routed to **§4 B4**.
3. **Forward-guidance extraction.** Agent identifies WIP or order-book but misses the management's delivery schedule (mn sq ft completions, UVG/price split). Fix: **deck-primary for forward guidance**. Routed to **§4 B4**.
4. **Heavy data-gap exposure.** 8 of 19 issues are DATA_FIX (BFSI metrics, RDA for regulated power, CAC for platform, AR degraded sections). Financials is the agent that surfaces tool gaps first because its scope demands structured numbers. Routed to **§7 E2.2, E13, E14**.

### 12.4 Sector — sector-agnostic patterns (29% PASS, 16 issues — WEAKEST)

1. **Peer-swap discipline.** Agent notices Yahoo peer mismatch (e.g., ZOMATO → LICI/IRFC) but doesn't call `get_screener_peers`. Fix: **mismatch → swap mandatory**. Routed to **§4 B3**.
2. **Reverse-DCF vs verdict reconciliation.** Reverse DCF implies growth well above historical, verdict still bullish without reconciliation. Fix: **if implied > 1.5× historical, verdict must acknowledge**. Routed to **§4 B3**.
3. **Multi-segment coverage for conglomerate-structure businesses.** Insurance+credit, food+QC, bank+holdco — agent focuses on the headline segment only. Fix: **any segment ≥15% gets its own sub-section**. Routed to **§4 B3**.
4. **Fallback chain not exhausted.** Most frequent pattern — R&D missed when AR degraded, channel mix missed when structured tool empty, metals KPIs not found in structured DB. Routed to **§3 A1.2** (L1 AR → Deck → Concall chain).
5. **Hypothesis without validation.** Agent deduces a distortion (e.g., "20% ROCE depressed by ₹22,665 Cr cash") but doesn't compute the corrected value (ex-cash ROCE). Fix: **validate-your-hypotheses tenet**. Routed to **§4 B3**.

### 12.5 Valuation — sector-agnostic patterns (78% PASS, 18 issues)

1. **Basis mixing** (top issue, 5 sectors). Standalone inputs + consolidated multiplicands, or argue-against-then-use patterns. Routed to **§3 A1.1**.
2. **Manual-SOTP fallback skipped** (3 sectors). When auto-SOTP returns empty/stale, agent doesn't attempt manual. Routed to **§3 A1.4** + **§7 E10** (auto-SOTP freshness).
3. **Weight-reallocation silence** (3 sectors). Agent adjusts weights manually but cites tool's unadjusted blended output as final. Routed to **§3 A1.5**.
4. **Scratchpad leak** (1 severe — VEDL F regression). Routed to **§3 A1.3** + **§7 E17** (assembly guard).
5. **Computation sign errors** (1 — SUNPHARMA EV bridge). Routed to **verifier**: detect formula-vs-result sign mismatch.
6. **Tool-registry hallucination** (1 — GODREJPROP). Routed to **§3 A1.6** + tool-description tightening.

### 12.6 Ownership — sector-agnostic patterns (75% PASS, 6 issues)

1. **Mandatory-metric skip via excuse.** "Budget constraints", "to save turns" — these are NEVER valid. Routed to **§4 B7** (ownership iter4).
2. **Named-op misuse.** `pct_of`, `growth_rate` used incorrectly. Routed to **§3 A1.6**.
3. **Redundant calcs.** Same computation done twice in different turns. Routed to **§4 B7** (calc-dedup awareness).
4. **Data gaps.** ADR/GDR + named FII holders — both carry-overs from plan v1, never shipped. Routed to **§7 E4, E7**.

### 12.7 Risk — sector-agnostic patterns (100% PASS, 7 issues — first dedicated iteration warranted)

1. **Leading indicators by sector.** IT utilization+headcount, real-estate city-level presales, pharma KSM/China dependency. Routed to **§4 B5**.
2. **JSON-to-prose parity.** Metrics in mandatory-metrics JSON but missing from narrative. Routed to **§4 B5**.
3. **Framing without quantification.** Risk axis stated, not quantified. Routed to **§4 B5**.
4. **Deck-primary risks.** City-level presales, capacity mix, utilization typically live in deck. Agent only checks concalls. Routed to **§4 B5** + **§3 A1.2**.

### 12.8 Technical — sector-agnostic patterns (100% PASS, 7 issues)

1. **Indicator completeness.** Skips MACD/Bollinger/ADX claiming SMAs+RSI sufficient. Routed to **§4 B6** (technical iter2).
2. **F&O derivatives mandatory.** PCR, OI, rollover must appear for F&O-listed stocks. Routed to **§4 B6**.
3. **Estimate-revision via proxy.** Skips `get_estimates(revision_history)` for composite proxy. Routed to **§4 B6**.
4. **Named-op misuse.** `margin_of_safety` for price vs SMA %. Routed to **§3 A1.6**.
5. **Data gaps.** Sector-index null for sub-classifications (Banks-Regional). Routed to **§7 E16**.

### 12.9 Cross-agent theme matrix

How each theme spreads across agents:

| Theme | Agents hit |
|---|---|
| Sequential calculate / turn count | 7 / 7 (universal; low leverage — don't chase) |
| AR → Deck → Concall fallback chain not exhausted | business, financials, sector, risk, valuation (5) |
| Named-operation misuse | ownership, technical, valuation (3) |
| Mandatory tool not dispatched | business, financials, valuation (3) |
| Sector-metric applicability contradictions | business, financials (2) |
| Segment coverage incomplete | business, sector (2) |
| JSON-to-prose parity | business, risk (2) |
| Manual-SOTP fallback skipped | valuation (1, but 3 sectors) |
| Weight-reallocation silence | valuation (1, but 3 sectors) |
| Scratchpad leak | valuation (1, severe) |
| Data-layer gaps as root cause | financials, valuation (2 heaviest) |

### 12.10 L2 iteration priority (reordered by lift-per-effort)

| Priority | Agent | Rationale |
|---:|---|---|
| 1 | **business iter2** | Most issues (23), 50% PASS, clear per-sector mandatory-tool map makes this high-lift |
| 2 | **sector iter2** | Lowest PASS rate (29%); peer-swap + reverse-DCF reconcile + multi-segment are three distinct tenets |
| 3 | **financials iter2** | 33% PASS; macro routing guard + consistency are quick wins; data-layer fixes unblock the rest |
| 4 | **valuation iter3** | Already partly covered by L1 lifts (basis, manual SOTP, weight audit); just needs residual tightening |
| 5 | **risk iter1** | First dedicated iteration; 5 tenets but 100% PASS means we're optimizing the ceiling |
| 6 | **technical iter2** | Narrow, 100% PASS; indicator-completeness + F&O-mandatory are tight additions |
| 7 | **ownership iter4** | Smallest issue count (6); no-skip rule + dedup are trivial additions |

### 12.11 Key takeaway

The three weakest agents (business, financials, sector) fail mostly on **discipline gaps that extend across sectors**, not on sector-specific knowledge. That's why L1 lifts (basis discipline, fallback chain, named-op) get such leverage on them — one tenet fix shows up in 3–5 of their reports. The strong agents (technical, risk, ownership) need narrower L2 refinements rather than universal lifts. **Order of attack: L1 universal → L2 for the weak trio → L2 for the strong trio → L5 data fixes in parallel throughout.**
