# Overnight Eval Run — Gemini Fix Collation

**Started:** 2026-04-15 (session kicked off after pull at main = 8bf7c56)
**Queue:** 14 runs (ownership 9 new + ownership 2 re-runs + financials 2 remaining + amortized ETERNAL×2)
**Source:** All fixes extracted from `flowtracker/research/autoeval/eval_history/*_all_for_<agent>.json`

## Final Tally

**12/14 PASS @ A- or better · 1 PROMOTED in retry (POLICYBZR B+88→A-90) · 1 PROMOTED in retry (SBIN B+86→A-92) · 1 FAIL (SUNPHARMA B+88 best after 2 tries — integrity issues)**

Financials now complete (all 15 sectors at A- or better incl. new ETERNAL A-92 + HDFCBANK A93).
Ownership now at 13/14 sectors PASS (SUNPHARMA outstanding).

## Cross-Cutting Themes (appear in 3+ evals — prioritize these)

### DATA_FIX (backend)
1. **Public float sub-breakdown missing** — Retail (<₹2L) / HNI (>₹2L) / Corporate Bodies not returned by `get_ownership('shareholder_detail')`. Flagged in: **HINDUNILVR, POLICYBZR, SBIN, PIDILITIND** (4 sectors). Required for conglomerate (Hindenburg-style analysis) + insurance (retail vs HNI). Pipeline fix in `data_api.get_shareholder_detail` or `shareholding` table schema.
2. **MF AMC coverage gap** — `mf_conviction` / `mf_holdings` only returns 2-4 AMCs (SBI, ICICI, UTI, QUANT). Missing HDFC, Nippon, Kotak. Flagged in: **ETERNAL, SUNPHARMA, PIDILITIND (implicit)** + past sessions. Root cause: AMFI data pipeline only covers subset of AMCs. Expand scraper.
3. **Empty analytical_profile for newly-listed stocks** — GROWW flagged. Backend needs to compute profile as soon as sufficient market data accrues.

### PROMPT_FIX (agent discipline)
4. **Hallucinated tool usage** (HIGH severity integrity issue) — agent claims to have used tools (`calculate`, `bulk_block`, `insider`) it never called. Flagged in: **GODREJPROP, SUNPHARMA**. Proposed rule: "Do not claim to have used tools in audit/sourcing tables that you did not actually execute. Tool Audit section must reflect only executed calls."
5. **Open questions used as escape hatch** instead of resolving via filings/documents — **GROWW** (IPO lock-up schedule), **POLICYBZR** (public bucket breakdown), **NTPC** (ADR/GDR), **ADANIENT follow-up**. Proposed rule: "Before listing any fact as an Open Question, attempt resolution via `get_company_context(filings)` or `'documents'`. Open Questions must state 'called X, got Y' trace."
6. **Timeframe misalignment** — default lookback windows applied to events outside that window. Flagged in: **SBIN** (365d bulk_block for 10-22mo-old FII exit), **NTPC** (current mcap × historical %pt delta). Proposed rule: "Align `days`/`quarters` parameters in tool calls with the actual timeframe of the shifts being analyzed."
7. **Monolithic category treatment** — FII as single block without top-holder decomposition. Flagged in: **PIDILITIND** (12% FII not split into SWF vs passive ETF vs hedge fund). Proposed rule: "Analyze top FII names from `shareholder_detail` with same rigor as MF schemes."

### Agent-boundary drift
8. **Out-of-scope content in ownership reports** — SBIN raised credit-quality SMA-1 account as open question (Risk/Financial scope). Reinforce boundary: ownership scope = shareholding / flows / caps / insider only.

## Status Table

| # | Stock | Sector | Agent | Status | Grade | Notes |
|---|---|---|---|---|---|---|
| 1 | ETERNAL | platform | financials | ✅ PASS | A- (92) | 4 fresh concalls; 25m02s run |
| 2 | ETERNAL | platform | ownership | ✅ PASS | A (94) | 6m52s; amortized concall |
| 3 | HDFCBANK | private_bank | financials | ✅ PASS | A (93) | 10m39s |
| 4 | VEDL | metals | ownership | ✅ PASS | A- (90) | 8m48s; concalls were cached |
| 5 | GODREJPROP | real_estate | ownership | ✅ PASS | A- (91) | 6m58s; flagged hallucination |
| 6 | SUNPHARMA | pharma | ownership | ⚠️ FAIL | F(50)→B+(88) re-run | Real report now but grade below A- threshold |
| 7 | NTPC | regulated_power | ownership | ✅ PASS | A- (91) | 7m37s |
| 8 | GROWW | broker | ownership | ✅ PASS | A (93) | 6m42s |
| 9 | OLAELEC | auto | ownership | ✅ PASS | A- (92) | 8m59s |
| 10 | PIDILITIND | chemicals | ownership | ✅ PASS | A- (92) | Eval 503-retried |
| 11 | HINDUNILVR | fmcg | ownership | ✅ PASS | A (94) | 6m38s |
| 12 | SBIN | bfsi | ownership | ✅ PROMOTED | B+(86)→A-(92) | PSU cap fix working |
| 13 | POLICYBZR | insurance | ownership | ✅ PROMOTED | B+(88)→A-(90) | 4m50s; fixes from new skills working |
| 14 | SUNPHARMA | pharma | ownership (retry) | ⚠️ FAIL | B+ (88) | 5m44s; integrity issues (hallucinated tool use + date confusion + skipped mf_changes) |

---

## Gemini Feedback by Sector (will populate as evals land)

### ETERNAL financials — A- (92) PASS
**Per-parameter:** analytical_depth A(94) · logical_consistency A-(90) · completeness B+(88) · actionability A-(91) · sector_framework A-(92) · data_sourcing A(95)

**Issues (both PROMPT_FIX):**
1. **Rule of 40 with distorted headline revenue** — agent calculated Rule of 40 using 67.1% reported revenue growth right after warning it's distorted by 1P accounting transition. *Suggestion:* adjust Rule of 40 inputs to use underlying economic growth (GOV/NOV) when headline revenue is distorted by accounting policy changes.
2. **Per-order unit economics not derived** — agent noted unit economics weren't "explicitly disclosed" instead of computing from available data. *Suggestion:* instruct to mathematically derive per-order metrics (AOV, delivery cost per order, contribution per order) by dividing segment revenue/costs by order volumes using `calculate`, when explicit per-order disclosures are missing.

**Strengths:**
- Blinkit 1P accounting transition deconstruction
- "Lie-detector" on treasury income funding 175% of reported PAT
- Beneish M-Score receivables spike correctly framed as structural business-model change, not manipulation

**Summary:** "Institutional-quality financial teardown that brilliantly exposes the accounting illusions driving headline growth and profitability."

### ETERNAL ownership — A (94) PASS
**Per-parameter:** analytical_depth A(94) · logical_consistency A+(96) · completeness A-(92) · actionability A(94) · sector_framework A+(96) · data_sourcing A-(92)

**Issues:**
1. **PROMPT_FIX — Pre-IPO VC roster not retrieved.** Agent only looked at current (Sep 2025) shareholder details + 365-day block deal window. *Suggestion:* instruct agent to query historical shareholding with `quarters=12+` or expand `bulk_block` lookback period to track pre-IPO VC exits for newly-listed tech companies.
2. **DATA_FIX — MF coverage gap.** `get_ownership(section='mf_holdings')` only returns 4 AMCs (SBI, ICICI, UTI, QUANT), missing major players (HDFC, Kotak, Nippon) visible in Screener. *Suggestion:* expand AMFI data pipeline in backend to cover all major AMCs.

**Strengths:**
- Open-market FII distribution (zero block deals) creating persistent price overhang — high-quality deduction
- Correctly applied new-age tech frameworks: 0% promoter contextualization, ESOP dilution, passive vs active MF split

**Summary:** "Institutional-quality ownership report that brilliantly connects raw flow data to price action."

### HDFCBANK financials — A (93) PASS
**Per-parameter:** analytical_depth A(94) · logical_consistency A(92) · completeness B+(88) · actionability A(92) · sector_framework A+(97) · data_sourcing A(94)

**Issues:**
1. **PROMPT_FIX — Non-Interest Income decomposition missing.** Report missed breakdown of Non-Interest Income (fee income vs treasury), critical for bank operating profitability. *Suggestion:* add BFSI prompt rule requiring Non-Interest Income / Core Fee profile analysis when analyzing BFSI entities.
2. **PROMPT_FIX — SOTP tool not called for subsidiary.** Agent asked about HDB Financial IPO valuation as open question but didn't call `get_valuation(section='sotp')`. *Suggestion:* instruct to always call `get_valuation(section='sotp')` when company has known subsidiaries or subsidiary value is a catalyst.
3. **DATA_FIX — NNPA/PCR missing from concall extraction.** Net NPA and PCR not captured. *Suggestion:* ensure `get_quality_scores(section='bfsi')` or `get_fundamentals` reliably extract NNPA and PCR from standard quarterly filings when missing from concall narratives.

**Strengths:**
- Exceptional BFSI framework application — explicit rejection of irrelevant metrics (FCF, EBITDA)
- Navigated HDFC merger + 1:1 bonus structural breaks to find true organic growth
- Identified a flaw in the rate sensitivity tool's logic and manually computed correct net economic impact

**Summary:** "Institutional-quality report that expertly navigates HDFC merger + bonus. Only notable gap: non-interest/fee income profile."

### VEDL ownership — A- (90) PASS
**Per-parameter:** analytical_depth A-(90) · logical_consistency B+(87) · completeness A-(90) · actionability A(93) · sector_framework B+(88) · data_sourcing A-(92)

**Issues:**
1. **PROMPT_FIX — LTV left as open question.** Agent asked LTV of encumbered shares as open question despite having both numerator ($4.8B debt) and denominator (₹1,65,802 Cr collateral) in context. *Suggestion:* instruct agent to always attempt LTV and margin-call trigger price computation using available debt/collateral data before defaulting to open question.

**Strengths:**
- SEBI pledge-to-NDU reclassification trap correctly identified
- 2.06x LIC-to-MF absorption ratio quantified

**Summary:** "Sophisticated report that correctly identifies critical encumbrance risks. To reach A+ tighten practical float (FII headroom) and proactively compute derived metrics like LTV."

### GODREJPROP ownership — A- (91) PASS ⚠️ hallucination flagged
**Per-parameter:** analytical_depth A(94) · logical_consistency A-(90) · completeness B+(88) · actionability A(93) · sector_framework A+(97) · data_sourcing B(84)

**Issues:**
1. **PROMPT_FIX (HIGH SEVERITY) — Hallucinated tool results.** Agent claimed "No block/bulk deals in last 365 days" and "0 insider transactions" BUT execution log shows it never called `get_ownership(section='bulk_block')` or `get_ownership(section='insider')`. *Suggestion:* strict rule in system prompt — forbid claiming zero activity for data endpoints unless the specific tool/section was explicitly called and returned empty. This is worth elevating to a compliance-gate rule.
2. **NOT_OUR_PROBLEM — SEBI terminology conflation.** Agent wrote "Promoter at 47.17% is well below the SEBI 75% Minimum Public Shareholding cap" — confuses 75% max promoter holding with 25% MPS rule. Minor LLM phrasing quirk.

**Strengths:**
- ISIN-based equity vs debt segregation for MF conviction (fix #2 from ADANIENT working)
- QIP contextualization (Tenet 11)
- Real estate sector-specific frameworks (pledge norms, DII cycle-top indicators)

**Summary:** "Insightful and structurally sound, but primary flaw is a HALLUCINATION about missing insider/bulk deal activity — agent skipped those tool calls and still drew conclusions. Worth a compliance-gate tightening."

### SUNPHARMA ownership — F (50) RATE-LIMIT FAILURE
**Status:** Agent ran 31m59s, 24 tool calls, but final LLM response was literal string "Request timed out" (17 chars total). Rate limit pressure. NOT a prompt/skill issue.

**Action:** Re-ran successfully 2nd time. Below.

### SUNPHARMA ownership (RE-RUN) — B+ (88) FAIL
**Per-parameter:** analytical_depth A-(90) · logical_consistency B(85) · completeness B+(86) · actionability A-(90) · sector_framework A(94) · data_sourcing B-(82)

**CRITICAL Issues (multiple integrity-related):**
1. **PROMPT_FIX (HIGH) — Hallucinated tool usage.** Agent claimed to have used `calculate` tool for monetary derivations but execution log shows it was never invoked. Integrity issue. *Suggestion:* strict rule: "Do not claim to have used tools in audit/sourcing tables that you did not actually execute."
2. **PROMPT_FIX — Skipped mandatory `mf_changes` tool call.** Agent relied on static trend proxy, missing velocity data for institutional flows. *Suggestion:* make `mf_changes` mandatory in ownership prompt.
3. **NOT_OUR_PROBLEM — Chronological hallucination.** Confused Mar 2024 (Q4 FY24) with Mar 2025. Date reasoning error.
4. **DATA_FIX — mf_conviction only 2 AMCs (SBI, ICICI).** Missing HDFC, Nippon, etc. Same pattern as HDFCBANK/ETERNAL/ADANIENT.

**Strengths:**
- 115% FII-to-DII absorption ratio well-framed
- Promoter 0% open-market correctly attributed to family trust structure (not lack of conviction)

**Summary:** "Solid core narrative but held back by 3 integrity issues: hallucinated tool usage, skipped mandatory tool, date confusion. Worth a targeted fix pass + 3rd re-run to see if hallucination is SUNPHARMA-specific or systemic."



### NTPC ownership — A- (91) PASS
**Per-parameter:** analytical_depth A(94) · logical_consistency B+(88) · completeness A-(91) · actionability A-(90) · sector_framework A(95) · data_sourcing B+(88)

**Issues:**
1. **COMPUTATION — Historical FII flow valuation.** Agent multiplied historical 2.36pp change by *current* market cap (₹8,839 Cr). *Suggestion:* explicitly label as "₹X Cr at current market cap" or use historical average market caps.
2. **PROMPT_FIX — ADR/GDR left as open question.** Standard disclosure in NSE shareholding patterns. *Suggestion:* check 'shareholding' data for 'Shares underlying DRs' before declaring unknown.

**Strengths:**
- PSU-specific traits well-contextualized: 51% statutory floor, zero pledge, zero insider trading
- Mechanical ETF trimming vs active thematic buying (ICICI Energy Fund) properly differentiated

**Summary:** "Institutional-grade FII-to-DII handoff + bond-proxy appeal to insurers. Primary flaw: math error using current mcap for historical flow value."

### GROWW ownership — A (93) PASS
**Per-parameter:** analytical_depth A(94) · logical_consistency A(95) · completeness A-(90) · actionability A-(92) · sector_framework A(94) · data_sourcing A-(91)

**Issues:**
1. **PROMPT_FIX — IPO lock-up not pursued to prospectus.** Agent correctly flagged May 2026 lock-up expiry as critical risk but left exact tranche schedule as open question instead of calling `get_company_context('documents')` or `'filings'` for DRHP/prospectus. *Suggestion:* instruct agent to actively search DRHP/RHP via documents/filings tools for newly-listed companies.
2. **DATA_FIX — Empty analytical_profile.** `get_analytical_profile` returned empty for GROWW (new listing). *Suggestion:* ensure backend computes profile for newly-listed stocks as soon as sufficient market data is available.

**Strengths:**
- -54pp FII "exit" correctly identified as post-IPO category reclassification artifact (not flight)
- AMFI mutual fund data artifact: correctly identified that reported holdings were for Groww's ETF products, not GROWW equity
- Insider selling framed as structural ESOP monetization, not bearish signal — new-age tech sector framework applied cleanly

**Summary:** "Exceptional analytical reasoning, debunking multiple false signals. Only gap: IPO prospectus lookup for lock-up quantification."

### OLAELEC ownership — A- (92) PASS
**Per-parameter:** analytical_depth A(93) · logical_consistency A-(92) · completeness B+(89) · actionability A-(92) · sector_framework A(94) · data_sourcing A(93)

**Issues:**
1. **PROMPT_FIX — AIF growth not drill-downed.** Report noted AIF holdings surged from 0.05% to 1.65% (33× relative growth) but didn't investigate who these AIFs are. *Suggestion:* require drill-down into any ownership category that grows >100% relatively, even if absolute % is small.
2. **NOT_OUR_PROBLEM — Apples-to-oranges volume comparison.** Compared 4-day cumulative bulk sell (313M shares) vs single-day volume (378M). Should compare to cumulative volume over same 4 days.

**Strengths:**
- HFT bulk selling + low delivery + speculative churn synthesis to disprove "accumulation" narrative
- Cross-venture contamination risk: Krutrim AI 0% promoter listing linked to OLAELEC 8.25% pledge escalation

**Summary:** "Outstanding bearish thesis connecting HFT selling, low delivery, and cross-venture promoter pledges. Missing: drilldown on residual VC in 'Public' + AIF identity."

### POLICYBZR ownership (RE-RUN) — A- (90) PASS (promoted from B+88)
**Per-parameter:** analytical_depth A(93) · logical_consistency A-(90) · completeness B+(87) · actionability A-(90) · sector_framework B+(87) · data_sourcing A-(90)

**Issues:**
1. **PROMPT_FIX — ESOP dilution omitted from main text.** JSON flagged missing ESOP trust data but main text ignored it. Critical for tech platforms (continuous supply source). *Suggestion:* explicitly require ESOP discussion in narrative for new-age tech/platform companies even when data is thin (use estimates or alternative tools).
2. **PROMPT_FIX — Gave up on Public float breakdown.** After `get_ownership` lacked granularity, didn't fall back to `get_company_context(filings)` or `'documents'` to extract from annual report. *Suggestion:* train filings/documents fallback for granular shareholding data.

**Strengths:**
- FII exit w/o bulk/block deals → persistent on-market supply overhang (good deduction)
- Handled `new_entry` MF tag pipeline artifact correctly — didn't take raw tool output at face value
- 212% DII absorption ratio quantified to prove genuine conviction

**Summary:** "Promoted from B+88 → A-90. FII-to-DII handoff captured well. Remaining gaps: ESOP narrative + granular public float split."

### HINDUNILVR ownership — A (94) PASS
**Issues:**
1. **PROMPT_FIX — FII sector-wide check not done.** Agent asked if FII exit was sector-wide but didn't call `get_peer_sector(section='sector_flows')`. *Suggestion:* require sector flow tool for macro-vs-micro FII exit analysis.
2. **DATA_FIX — Public float sub-breakdown missing from pipeline.** *Suggestion:* ensure `get_ownership(section='shareholder_detail')` reliably extracts retail/HNI/corporate sub-categories.

**Strengths:**
- MNC subsidiary archetype context: insider sales = routine ESOP monetization, zero pledge = structural baseline (not unique strength)
- Passive ETF vs active stock-picking separation for true institutional sentiment

**Summary:** "Outstanding MNC-subsidiary-archetype framing. Only gap: sector flow lookup to settle whether FII exit is HUL-specific."

### SBIN ownership (RE-RUN) — A- (92) PASS (promoted from B+86)
**Per-parameter:** analytical_depth A(95) · logical_consistency A-(90) · completeness A-(91) · actionability A(94) · sector_framework A(95) · data_sourcing B+(88)

**Issues:**
1. **PROMPT_FIX — Timeframe misalignment in bulk_block.** Agent used default 365-day window to check bulk/block deals for an FII exit that occurred 10-22 months ago (Jun 2024 - Jun 2025). *Suggestion:* instruct to align `days` parameter in `get_ownership(bulk_block)` with the actual timeframe of ownership shifts being analyzed (e.g., `days=1825`).
2. **DATA_FIX — Public float sub-breakdown missing.** Same issue as HINDUNILVR/POLICYBZR — `shareholder_detail` not returning standard Retail<₹2L / HNI>₹2L / Corporate Bodies split.
3. **PROMPT_FIX — Out-of-scope open question.** Agent raised ₹9,000 Cr SMA-1 account as open question — credit quality is Risk/Financial agent scope, not Ownership. *Suggestion:* reinforce agent-boundary rules; ownership open questions must relate to shareholding/flows/caps/insider only.

**Strengths:**
- PSU frameworks: 51% statutory floor, 20% FII cap, structural LIC position (all correctly applied — fix from last session's skill file working!)
- MF conviction strips passive index mandates + flags SBI MF's conflict-of-interest with outsized holdings
- Lack of insider buying framed as structural IAS/banking cadre reality, not bearish signal

**Summary:** "Promoted from B+86 → A-92. BFSI ownership skill file's 20% PSU cap rule working correctly. Gap: chronological mismatch on bulk_block lookback."

### PIDILITIND ownership — A- (92) PASS
**Per-parameter:** analytical_depth A(94) · logical_consistency A-(90) · completeness B+(88) · actionability A-(91) · sector_framework A-(92) · data_sourcing A(95)

**Issues:**
1. **PROMPT_FIX — Self-contradiction on price impact.** Section 2 said LIC supply "fully absorbed with no visible price distress"; Section 5 said distributed supply "creating persistent order-book pressure". *Suggestion:* instruct agent to reconcile time horizons (quarterly shareholding vs 4-week delivery trends) before making market-impact claims.
2. **PROMPT_FIX — FII treated as monolith.** 12% FII stake not decomposed (Sovereign Wealth vs Passive ETF vs Hedge Fund). *Suggestion:* analyze top FII names from `shareholder_detail` payload the same way MF schemes are analyzed.
3. **DATA_FIX — Public bucket breakdown missing.** Same pattern as 3 other sectors — `shareholder_detail` only returns DII named entities. Retail/HNI/corporate (9.41%) not breakable.

**Strengths:**
- "Institutional Handoff" (Insurance → MF/FII) quantified at 113% absorption ratio
- MF thematic positioning (Bharat Consumption, Innovation) explains *why* holdings exist
- Transparency about tool limitations — raised gaps as open questions vs guessing

**Summary:** "Highly analytical; calculated absorption ratios + AMC concentration risk make it actionable. Gaps: FII monolith + logical contradiction on market impact."



