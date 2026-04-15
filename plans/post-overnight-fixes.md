# Post-Overnight Fix Plan — Ownership + Financials Improvements

**Created:** 2026-04-15 (after overnight eval run at commit 8bf7c56)
**Scope:** 8 cross-cutting themes + 12 single-sector issues surfaced by 14 Gemini evaluations
**Target:** SUNPHARMA → A-, all other A- sectors → A, prevent regressions

---

## Fix Layer Map (where each fix lives)

| Layer | When to use | Example |
|---|---|---|
| **`SHARED_PREAMBLE_V2`** | Agent-agnostic rules (integrity, boundaries, payload discipline). Loaded by all 8 specialists + synthesis + explainer. | Tool-audit honesty, truncation discipline |
| **`OWNERSHIP_SYSTEM_V2`** / **`FINANCIAL_SYSTEM_V2`** (tenets) | Agent-specific + sector-agnostic. Applies to all sectors for that agent. | "Cross-reference 2-3 signals", "Public float >15% drilldown" |
| **`{AGENT}_INSTRUCTIONS_V2`** (workflow + sections) | Agent-specific workflow. Same for all sectors. | "Always call mf_changes alongside mf_holdings" |
| **`sector_skills/<sector>/{agent}.md`** | Sector-specific + company-agnostic. 13 sector files exist for ownership. | "Private bank foreign cap = 74%", "Pharma R&D intensity mandatory" |
| **Data pipeline** (`data_api.py`, `store.py`, `screener_client.py`, etc.) | Backend data/schema issues. No prompt change will fix missing data. | Public bucket sub-breakdown, AMC coverage |

---

## Phase 1 — DATA_FIX Pipeline Work (3 backend fixes, highest leverage)

These fixes resolve issues that no prompt change can address. Flagged in 3+ evals each.

### 1.1. Public float sub-breakdown (Retail/HNI/Corporate) — ❌ data missing entirely

**Flagged in:** HINDUNILVR, POLICYBZR, SBIN, PIDILITIND, ADANIENT follow-up

**Current state:**
- `shareholding` table stores only 7 aggregate categories: `FII, DII, MF, Public, Promoter, Insurance, AIF`
- `shareholder_detail` table stores named holders but only for: `promoters, foreign_institutions, domestic_institutions, public`
- The "Public" classification from Screener returns only the top NAMED holders (usually 1% threshold), **not the SEBI sub-categories** (Retail<₹2L / HNI>₹2L / Corporate Bodies / NRIs / Trusts)
- OWNERSHIP_SYSTEM_V2 Tenet 8 already says "mandatory when Public > 15%" — prompt is there, data isn't

**Fix location:**

| File | Change |
|---|---|
| `store.py` | New table `shareholding_public_breakdown`: `(symbol, quarter_end, sub_category, percentage, shares)`. Sub-categories: `retail_upto_2L`, `hni_above_2L`, `corporate_bodies`, `nri`, `trust_others`. |
| `screener_client.py` + `nse_client.py` | Parse XBRL shareholding pattern filings (available from BSE `https://www.bseindia.com/xml-data/corpfiling/AttachHis/...` or NSE equity-shareholding API). XBRL `<PublicShareholding>` has nested `<Category>` elements for each sub-type. |
| `data_api.py` | New accessor `get_public_float_breakdown(symbol)`; hook into `get_shareholder_detail` response so it returns both named-holder list AND aggregate sub-breakdown at top. |
| `tools.py::get_ownership` | TOC: add `public_float_sub_breakdown` section. Drill: `get_ownership(section='public_breakdown')` returns the sub-category table. |

**Acceptance test:** HINDUNILVR, POLICYBZR, SBIN, PIDILITIND all return populated retail/HNI/corporate percentages. Agent can cite "Retail = X%, HNI = Y%, Corporate Bodies = Z%" and Gemini's completeness dock is resolved.

---

### 1.2. MF AMC coverage expansion (5 → 15+)

**Flagged in:** ETERNAL, SUNPHARMA, PIDILITIND, HDFCBANK (prior session), ADANIENT (prior)

**Current state:**
- `mf_scheme_holdings` table has only **5 AMCs**: SBI, ICICI, PPFAS, QUANT, UTI
- `_SUPPORTED_AMCS` in `mfportfolio_commands.py` is hard-coded to these 5
- Missing the largest: **HDFC AMC, Nippon India, Kotak Mahindra, Axis, Aditya Birla Sun Life, DSP, Tata, Motilal Oswal, Edelweiss, Mirae Asset**
- HDFC alone has ₹6L Cr+ AUM — omitting it distorts mf_conviction analysis for nearly every stock

**Fix location:**

| File | Change |
|---|---|
| `mfportfolio_client.py` | Add parsers for remaining AMCs. Each AMC publishes monthly portfolio PDFs/Excel on their website. Discovery URLs vary per AMC. |
| `mfportfolio_commands.py` | Expand `_SUPPORTED_AMCS` list to 15+ AMCs. |
| `scripts/monthly-mfportfolio.sh` | Ensure cron fetches all new AMCs. |
| `data_api.py::get_mf_conviction` | Already uses scheme-type classifier. Payload will scale — may need to re-check TOC size with 15 AMCs (could grow from ~6K to ~30K; re-apply top_n cap if needed). |

**Priority AMCs (by AUM rank):**
1. HDFC — largest, most-missed
2. Nippon India — second largest retail
3. Kotak Mahindra — institutional-heavy
4. Axis — broad coverage
5. Aditya Birla Sun Life
6. DSP
7. Tata
8. Motilal Oswal — flexible cap
9. Mirae Asset
10. Edelweiss

**Acceptance test:** `get_mf_conviction('ETERNAL')` returns >5 AMCs. Gemini will no longer flag "missing HDFC, Kotak, Nippon" as DATA_FIX.

---

### 1.3. `analytical_profile` for newly-listed stocks

**Flagged in:** GROWW (new listing)

**Current state:**
- `get_analytical_profile` computes F-Score, M-Score, DuPont, capex cycle — all require 5-10Y history
- Newly-listed stocks (<2 years) have insufficient data → returns `{"error": "No analytical snapshot..."}` (not an empty dict)
- Agent shows "get_analytical_profile returned error" in its Tool Audit — embarrassing for first-look reports

**Fix location:**

| File | Change |
|---|---|
| `data_api.py::get_analytical_profile` | Replace the current `{"error": "No analytical snapshot..."}` early-return path. Compute what's possible (composite score on available data, price performance from IPO date, common-size P&L if 2+ years) + include `_insufficient_history_warning: "Listed X months ago — F-Score/M-Score require 10Y; reverse DCF requires 5Y stable cashflow"` and `_listed_since: "2025-05-09"` metadata. |
| `prompts.py` SHARED_PREAMBLE_V2 | Add: "If `_insufficient_history_warning` surfaces, note in Data Sources section and use alternative metrics (listing-date price performance, post-listing ratios)." |

**Acceptance test:** GROWW re-run shows `_insufficient_history_warning` + available post-listing metrics, not "No analytical snapshot" error in Tool Audit.

---

## Phase 2 — `SHARED_PREAMBLE_V2` Changes (agent-agnostic integrity)

### 2.1. Tool Audit strict honesty

**Problem:** GODREJPROP claimed no block/insider activity without calling those tools. SUNPHARMA claimed `calculate` tool usage that never happened. Both reports had hollow Tool Audit sections.

**Current state (line 16):**
> "Before starting your report, output a brief `## Tool Audit` listing each workflow step and whether the tool was called (✓) or returned empty (∅)."

**Replace with tighter formulation:**
```
Before starting your report, output a `## Tool Audit` listing each workflow step
and whether the tool was called (✓) or returned empty (∅). Each row MUST
correspond to an actual tool call in your execution log — do not list steps you
did not execute. Do not mark `∅` for tool calls you did not attempt; reserve
`∅` for calls that executed and returned empty data. Reviewers cross-verify
the audit against the execution log; claims without corresponding tool calls
are workflow violations.

Conversely, if you state "no bulk deals" or "no insider activity" in your
narrative, the corresponding tool MUST have been called and returned empty.
Never narrate zero activity on data endpoints you did not query.
```

**Where:** `prompts.py` line 14-16, inside `SHARED_PREAMBLE_V2`.

---

### 2.2. Hallucinated `calculate` tool citations

**Problem:** SUNPHARMA cited `calculate` in sourcing table; execution log shows it never called `calculate` at all.

**Fix:** Same Tool Audit strengthening as 2.1 — combined rule covers both patterns.

---

## Phase 3 — `OWNERSHIP_SYSTEM_V2` Tenet Additions (sector-agnostic ownership)

### 3.1. New Tenet: Timeframe alignment

**Problem:** SBIN used default 365-day bulk_block window for a 10-22-month-old FII exit. NTPC used current mcap × historical %pt delta to value past flows.

**Add as Tenet 16** (inserted after current Tenet 15 ESOP trust; current Tenet 16 Sector Compliance Gate shifts to 18 once §3.2 also lands):
```
16. **Timeframe alignment in tool calls and derived metrics.**
    - Lookback windows must match the timeframe of the event being analyzed.
      When investigating an ownership shift that occurred >12 months ago, pass
      `days=1825` (5 years) or a custom window covering the shift — not the
      default 365.
    - Historical flow values require historical market caps. When converting
      a past period's %pt change to ₹Cr flow, multiply by the market cap at
      THAT quarter end, not today's mcap. If historical mcap isn't available,
      explicitly label the output "₹X Cr at current mcap" and caveat that
      actual flow value may differ 20-50%.
```

**Final numbering after §3.1 + §3.2 land:** `16 = timeframe alignment, 17 = FII decomposition, 18 = Sector Compliance Gate`. No prompt-integrity hash exists in `agent.py` (the sha256 there hashes tool *results* for evidence logging) — no hash update needed.

---

### 3.2. New Tenet: FII decomposition (not monolith)

**Problem:** PIDILITIND treated 12% FII as single block — didn't decompose into Sovereign Wealth vs Passive ETF vs Hedge Fund.

**Add as Tenet 17** (after timeframe alignment; Sector Compliance Gate then moves to 18):
```
17. **Decompose FII by holder type, not as a monolith.** Top FII names in
    `shareholder_detail` (foreign_institutions classification) usually reveal
    three archetypes: (a) Sovereign wealth / endowments (Vanguard, Norges Bank,
    Abu Dhabi IA, GIC) — stickiest money, signals long-term quality view; (b)
    Passive ETFs (BlackRock/iShares, Vanguard index tranches) — mechanical,
    follows MSCI/FTSE weight; (c) Active mandates (Capital Group, T. Rowe,
    Fidelity) and hedge funds (Tiger, Millennium-style) — flow-driven, signal
    conviction. Analyze each bucket's weight and trajectory with the same
    rigor you apply to MF schemes. A 12% FII stake that's 70% passive reads
    differently from 12% that's 70% active.
```

**Where:** `prompts.py` OWNERSHIP_SYSTEM_V2 after Tenet 16 (timeframe, newly inserted in §3.1).

---

### 3.3. Sharpen boundary — out-of-scope open questions

**Problem:** SBIN raised credit-quality ₹9,000 Cr SMA-1 account in Ownership Open Questions — Risk/Financial scope.

**Modify current Tenet 14 (open questions ceiling):** Add one line.

Current text (line 366):
> "14. **Open Questions ceiling: 3-5 per report.** ... Resolve structural/arithmetic queries yourself (post-conversion share counts, headroom math, cumulative flow totals). Reserve open questions for genuinely unverifiable-from-tools items."

**Add after the last sentence:**
```
Open questions must be ownership-scope only: shareholding dynamics, institutional
flows, regulatory caps (foreign holding, MPS), insider activity, pledge/NDU,
free float. Do NOT raise credit quality, earnings drivers, valuation multiples,
or macro thesis — those belong to Risk, Financials, Valuation, and Macro
agents. Open questions outside your agent scope are dropped by the web research
agent and waste the 3-5 budget.
```

---

### 3.4. Sharpen Tenet 15 — ESOP narrative required

**Problem:** POLICYBZR flagged ESOP data in JSON briefing but omitted ESOP discussion from main report text.

**Modify current Tenet 15** (ESOP trust movements):

Current text (line 367):
> "15. **ESOP Trust movements are structural, not directional.** For platform/tech cos and other ESOP-heavy listcos, ESOP trust buckets appear in `shareholder_detail`..."

**Add at the end:**
```
For new-age tech platforms (platform, broker, insurtech sectors), ESOP trust
holdings + dilution dynamics MUST appear in the main report narrative, not
only in the JSON briefing. Even when exact trust data is thin, discuss: (a)
current ESOP pool as % of equity (from filings / AGM notices), (b) observed
vesting-cycle trust-to-public distributions, (c) effective float dilution
trajectory. A silent main text with "ESOP" mentioned only in JSON is a
workflow violation — the reader needs it in prose to size the continuous
supply.
```

---

## Phase 4 — `OWNERSHIP_INSTRUCTIONS_V2` Workflow Changes

### 4.1. Make `mf_changes` strictly mandatory (close the loophole)

**Problem:** SUNPHARMA skipped `get_ownership(section='mf_changes')`. Tenet 5 already says "ALWAYS call mf_changes alongside mf_holdings" — agent still skipped.

**Fix:** Move from tenet to workflow hard requirement.

**Current workflow step 2 (line 386-394):** The drill pattern list mentions mf_changes only implicitly.

**Replace step 2 drill pattern list to force mf_changes into a guaranteed drill:**
```
   - **Mandatory drills** (call these every time — they answer different questions):
     - `get_ownership(section=['shareholding','changes','promoter_pledge','mf_conviction'])` — aggregate trends
     - `get_ownership(section='mf_changes')` — MF velocity (buying vs trimming vs new entries). REQUIRED — static mf_holdings without velocity is an incomplete picture. Skipping this is a workflow violation.
     - `get_ownership(section='shareholder_detail')` — top 20 named holders
   - **Conditional drills** (only if TOC flags activity):
     - `get_ownership(section='mf_holdings')` if MF concentration > 10% or surfaced by TOC
     - `get_ownership(section='insider')` if buy_count > 0 or sell_count > 0 in TOC insider summary
     - `get_ownership(section='bulk_block')` if deal_count > 0 in TOC. Pass `days=1825` if analyzing an ownership shift older than 12 months.
```

### 4.2. New workflow step — sector-flow cross-check for FII moves

**Problem:** HINDUNILVR asked "is FII exit sector-wide?" as open question — didn't call `get_peer_sector(section='sector_flows')` which exists.

**Current step 5 (line 398):**
> "5. **Sector context**: Call `get_peer_sector` with `section="benchmarks"` for sector percentile rankings..."

**Modify:**
```
5. **Sector context**: Call `get_peer_sector` with section=['benchmarks','sector_flows']
   — benchmarks for percentile rankings (PE, ROCE, mcap), sector_flows for
   macro-vs-micro FII/MF attribution. If your FII analysis raises "is this
   stock-specific or sector-wide?", sector_flows must be cited in the answer,
   not left as an open question.
```

### 4.3. New workflow step — self-contradiction check

**Problem:** PIDILITIND — Section 2 said LIC supply "fully absorbed, no distress"; Section 5 said "persistent order-book pressure". Flat contradiction.

**Add as step 7a (before Visualize step 7):**
```
7a. **Cross-section consistency pass.** Before writing your report, verify
    that your Money Flow Story (Section 2), Risk Signals (Section 5), and
    Institutional Verdict (Section 6) tell a consistent story. Common
    contradictions to check:
    - Did you call supply "absorbed" in one section and "overhang" in another?
    - Did you cite the same %pt change as "bullish accumulation" and
      "bearish distribution"?
    - Did you use quarterly shareholding timeframe and 4-week delivery
      timeframe interchangeably?
    Reconcile the timeframes explicitly — "quarterly absorption was clean
    (Section 2), but short-window delivery shows residual pressure (Section
    5)" is consistent; two un-reconciled claims are a logical error.
```

---

## Phase 5 — Sector Skill File Updates

### 5.1. BFSI sector skill gaps (ownership + financials)

**File: `sector_skills/bfsi/ownership.md`**
- **Already covers:** 74% private cap, 20% PSU cap, LIC anchor. (From earlier session's fix — working correctly per SBIN re-run A-92.)
- **Add:** "When analyzing FII exit older than 12 months, pass `days=1825` to bulk_block — 365 default will miss the supply distribution."

**File: `sector_skills/bfsi/financials.md` (expand with HDFCBANK learnings)**
- **Add:** Non-Interest Income decomposition: "For banks, split Other Income into fee income (stable, moat) vs treasury income (volatile, rate-sensitive). Fee income ÷ Total Income = fee moat strength. Target: fee/total >20% = strong moat; 10-20% = moderate; <10% = thin (over-reliance on NII)."
- **Add:** SOTP trigger for private banks with listed subsidiaries: "HDFC Bank has HDB Financial (IPO-bound), HDFC AMC, HDFC Life. ICICI Bank has ICICI Pru Life, ICICI Lombard, ICICI Prudential AMC. Call `get_valuation(section='sotp')` whenever subsidiary value is a potential catalyst."

### 5.2. `sector_skills/private_bank/` — create new directory

**Status:** Directory does NOT exist yet. Must be created from scratch. HDFCBANK eval ran against generic BFSI skill; a dedicated private-bank skill will sharpen the private-bank archetype (versus PSU-bank archetype already covered under BFSI).

**Create:**
- `sector_skills/private_bank/_shared.md` — inherits BFSI core + private-bank specifics
- `sector_skills/private_bank/ownership.md` — 74% FII cap emphasis, ADR/GDR aggregation
- `sector_skills/private_bank/financials.md` — Non-interest income decomposition, SOTP for listed subs

### 5.3. Platform sector (ETERNAL — both agents)

**File: `sector_skills/platform/financials.md` (check if exists; if not, create)**
- **Add:** Rule of 40 adjustment when headline revenue distorted: "For platforms transitioning accounting treatment (e.g. 1P→3P, net-to-gross revenue), the Rule of 40 cannot use reported headline revenue growth — use GOV/NOV growth from concall insights or segment-level pass-through metrics."
- **Add:** Per-order unit economics derivation: "When `operational_metrics` in concall gives total orders and financial segment gives segment revenue, DERIVE per-order metrics via `calculate`: AOV = revenue_cr × 1e7 / order_count. Delivery cost per order = delivery_cost_cr × 1e7 / order_count. Contribution per order = (AOV − variable_cost_per_order)."

### 5.4. Pharma sector (SUNPHARMA)

**File: `sector_skills/pharma/ownership.md`**
- **Add:** Family trust structure framing: "Sun Pharma's Shanghvi family holds 54.48% via a family trust structure (not direct personal holdings). Zero open-market promoter activity is STRUCTURAL for family-trust holdcos, not informational. Do not infer low conviction from flat promoter pledge trajectory."

### 5.5. Metals sector (VEDL — LTV compute)

**File: `sector_skills/metals/ownership.md`**
- **Add:** "When pledge data surfaces encumbered shares for a foreign-debt-servicing vehicle (Vedanta Resources for VEDL, similar for others), ALWAYS compute LTV = foreign_debt_usd × USDINR / (encumbered_shares × current_price). Margin-call trigger = LTV × 1.3 (typical covenant). Do not leave this as open question — all inputs are in your tools."

### 5.6. Conglomerate sector (ADANIENT + generalization)

**File: `sector_skills/conglomerate/ownership.md`** (already exists from yesterday)
- **Verify** it includes: Public bucket sub-breakdown (retail/HNI/corporate), Hindenburg-style resilience patterns, listed-subsidiary cross-check, aggregate pledge exposure across group entities.
- If (1.1 data fix) lands, update to reference `get_public_float_breakdown` tool.

### 5.7. Auto sector (OLAELEC — AIF growth drilldown)

**File: `sector_skills/auto/ownership.md`**
- **Add:** "New-age EV / listed-startup autos: any ownership category that grows >100% relatively in a single quarter (even if absolute <2%) warrants investigation. AIF growth can signal VC rotation post-lockup, or structured-finance vehicle entry. Drill via `get_ownership(section='shareholder_detail', classification='alternative_investment_funds')` when category-level growth is abnormal."

### 5.8. FMCG / Consumer (HINDUNILVR — MNC subsidiary archetype)

**File: `sector_skills/fmcg/ownership.md`**
- Tenet 9 already covers MNC-subsidiary insider framing. Verify the sector skill includes: "Unilever parent at 61.9% — insider sales are ESOP-routine, not informational. Track insider BUYING instead for signal."

### 5.9. Insurance / Insurtech (POLICYBZR — ESOP narrative)

**Status:** `sector_skills/insurance/ownership.md` does NOT exist (only `_shared.md` and `financials.md` present). Must be CREATED, not modified.

**File: `sector_skills/insurance/ownership.md` (CREATE)**
- Inherit `_shared.md` macros (regulatory caps, IRDAI framing).
- **Add core content:** "For insurtech platforms (POLICYBZR, STARHEALTH, etc.), ESOP trust holdings + vesting-cycle distributions MUST appear in the main report narrative, not only in the JSON briefing. Quantify ESOP pool as % equity, track distributions as effective float expansion."
- **Add standard insurance-sector ownership framing:** promoter (often foreign insurer parent) stickiness, 74% FII cap, LIC anchor positions, institutional conviction on embedded value growth.

---

## Phase 6 — Concall Extractor Fix (NNPA/PCR)

**Problem:** HDFCBANK financials — NNPA and PCR were not captured in concall extraction, leaving a gap in BFSI asset quality reporting.

**Current state:**
- `concall_extractor.py` has structured schema for operational/financial metrics
- BFSI-specific metrics (NNPA, PCR, CRAR, CET1, Credit Cost, Slippages) may not be in the schema

**Fix:**

| File | Change |
|---|---|
| `concall_extractor.py::_CONCALL_EXTRACTION_SCHEMA` | Add explicit `bfsi_asset_quality` section to schema with fields: `gnpa_pct`, `nnpa_pct`, `pcr_pct`, `slippage_ratio_pct`, `credit_cost_pct`, `crar_pct`, `cet1_pct`, `restructured_book_pct`. |
| `concall_extractor.py` prompt | Instruct: "If the company is a bank/NBFC/lender (check `_shared.md` sector = bfsi), populate `bfsi_asset_quality` fields. These are always disclosed in BFSI concall presentations (usually slide 5-10 or in opening remarks)." |
| `data_api.py::get_concall_insights` | Expose `bfsi_asset_quality` sub-section so ownership/financials agents can drill. |
| `tools.py::get_fundamentals` | Consider a `bfsi_asset_quality` section alias to quality_scores bfsi routing. |

**Acceptance test:** HDFCBANK financials agent cites NNPA/PCR/CRAR from concall or quality_scores. Same for SBIN, PNB, future BFSI runs.

---

## Phase 7 — Execution Order

**Sequence to minimize re-runs:**

1. **Phase 2 (SHARED_PREAMBLE_V2 Tool Audit)** — 30 min effort, surgical text change + hash update. Smallest scope, biggest integrity impact. Do first.
2. **Phase 3 (OWNERSHIP_SYSTEM_V2 tenets)** — 1-2 hours, prompt-only changes. Update tenet numbering carefully.
3. **Phase 4 (OWNERSHIP_INSTRUCTIONS_V2 workflow)** — prompt-only changes, 1 hour.
4. **Phase 5 (sector skill files)** — additive markdown-only, can parallelize by subagent (9 files). 2-3 hours.
5. **Phase 6 (concall extractor BFSI)** — schema + prompt change + re-extract affected BFSI concalls (~1 hour + re-extract time).
6. **Phase 1 (data pipeline)** — highest-impact but longest. Run last in priority order:
   - 1.2 MF AMC expansion — 1-2 days (each new AMC needs its own parser).
   - 1.3 analytical_profile graceful degradation — 2-3 hours.
   - 1.1 Public float sub-breakdown — 1-2 days (XBRL parser + schema migration + UI surface).

**After Phase 2-5:** re-run the 14-eval matrix. Expected outcomes:
- SUNPHARMA → A- (Tool Audit honesty + mf_changes mandatory workflow + timeframe-aware insider window)
- Multiple A- → A upgrades as hallucination/escape-hatch fixes land
- No regressions since changes are additive

**After Phase 6:** re-run BFSI evals (SBIN, HDFCBANK, both financials + ownership). Expected: NNPA/PCR populated in reports; HDFCBANK financials B+88 completeness → A.

**After Phase 1:** re-run only sectors that flagged those specific DATA_FIX issues (HINDUNILVR, POLICYBZR, SBIN, PIDILITIND for public float; ETERNAL, SUNPHARMA for MF AMC). Expected grade lift of 1-3 points each.

---

## Summary Table — Fix Distribution by Layer

| Layer | # Fixes | Files touched | Est. effort |
|---|---|---|---|
| SHARED_PREAMBLE_V2 | 1 (Tool Audit) | `prompts.py` | 30 min |
| OWNERSHIP_SYSTEM_V2 | 4 tenets (timeframe, FII decomp, boundary tighten, ESOP narrative) | `prompts.py` | 1-2 hrs |
| OWNERSHIP_INSTRUCTIONS_V2 | 3 (mf_changes mandatory, sector_flows, consistency pass) | `prompts.py` | 1 hr |
| FINANCIAL_SYSTEM_V2 | 2 (non-interest decomp, SOTP trigger) | `prompts.py` | 30 min |
| Sector skills | 9 files (bfsi ownership+financials, private_bank new×3, platform fin, pharma ownership, metals ownership, conglomerate ownership, auto ownership, fmcg ownership, insurance ownership) | `sector_skills/*.md` | 2-3 hrs (parallelizable) |
| Data pipeline | 3 (public float, AMC coverage, analytical_profile) | `store.py`, `screener_client.py`, `mfportfolio_client.py`, `data_api.py`, `tools.py` | 2-4 days |
| Concall extractor | 1 (BFSI asset quality schema) | `concall_extractor.py`, `data_api.py` | 1-2 hrs + re-extract |

**Total prompt changes:** ~5-7 hours. **Total data pipeline:** ~3-4 days.
**Prompt-only grade lift expected:** SUNPHARMA B+88 → A-, 3-4 sectors A- → A.
