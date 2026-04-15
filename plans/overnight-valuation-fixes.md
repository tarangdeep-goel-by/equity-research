# Valuation Agent — Overnight Eval Results (Sequential Baseline)

**Started:** 2026-04-15 09:48
**Agent:** `valuation` (first untested post-Phase-1 harmonization)
**Mode:** Sequential, one sector at a time, human-monitored
**Context:**
- Phase 1 (Stage A+B+C) merged in `1ba38ec` — `mandatory_metrics_status`, I-1 through I-7 cross-agent invariants, Sector Compliance Gate, capped open questions at 3-5
- ZERO sector skill files exist for valuation (the baseline runs without any per-sector guidance)
- Goal: surface sector-specific gaps that inform Phase 2 skill-file drafting

---

## Run Log

| # | Sector | Stock | Started | Grade | Status |
|---|---|---|---|---|---|
| 1 | bfsi | SBIN | 2026-04-15 09:48 | **A- (92)** | ✅ PASS |
| 2 | private_bank | HDFCBANK | 2026-04-15 18:52 | **A (93)** | ✅ PASS (re-graded round-2 00:30, 2 prompt_fixes) |
| 3 | it_services | TCS | 2026-04-15 19:14 | **B+ (88)** | ❌ FAIL (re-graded round-2 00:31, 2 prompt_fixes) |
| 4 | metals | VEDL | 2026-04-15 19:26 | **A- (91)** | ✅ PASS (re-graded 22:30, 2 prompt_fixes) |
| 5 | platform | ETERNAL | 2026-04-15 19:26 | **A- (90)** | ✅ PASS (re-graded 22:33, 2 prompt_fixes) |
| 6 | conglomerate | ADANIENT | 2026-04-15 19:26 | **A (93)** | ✅ PASS (re-graded 22:34, 2 prompt_fixes) |
| 7 | telecom | BHARTIARTL | 2026-04-15 19:39 | **B (85)** | ❌ FAIL (re-graded 22:35, 1 prompt_fix) |
| 8 | real_estate | GODREJPROP | 2026-04-15 19:39 | **A- (91)** | ✅ PASS (re-graded round-2 00:33, 3 prompt_fixes) |
| 9 | pharma | SUNPHARMA | 2026-04-15 19:39 | **A- (92)** | ✅ PASS (re-graded 22:38, 2 prompt_fixes) |
| 10 | regulated_power | NTPC | 2026-04-15 19:53 | **A (95)** | ✅ PASS (re-graded 22:39, 1 prompt_fix) |
| 11 | insurance | POLICYBZR | 2026-04-15 19:53 | **A- (92)** | ✅ PASS (re-graded round-2 00:34, 2 prompt_fixes) |
| 12 | broker | GROWW | 2026-04-15 19:53 | **A- (91)** | ✅ PASS (re-graded 22:41, 2 prompt_fixes) |
| 13 | auto | OLAELEC | 2026-04-15 20:08 | **B+ (89)** | ❌ FAIL (re-graded round-2 00:35, 2 prompt_fixes) |
| 14 | chemicals | PIDILITIND | 2026-04-15 22:31 (re-RUN) | **A- (90)** | ✅ PASS (3 prompt_fixes) |
| 15 | fmcg | HINDUNILVR | 2026-04-15 20:08 | **A- (92)** | ✅ PASS (re-graded 22:43, 2 prompt_fixes) |

---

## Final Grade Distribution

| Tier | Count | Sectors |
|---|---|---|
| **A (93-95)** | 3 | regulated_power=95, conglomerate=93, private_bank=93 |
| **A- (90-92)** | 9 | bfsi=92, fmcg=92, insurance=92, pharma=92, broker=91, metals=91, real_estate=91, chemicals=90, platform=90 |
| **B+ (88-89)** | 2 | auto=89, it_services=88 |
| **B (85)** | 1 | telecom=85 |

**12/15 PASS the A- bar (80%) on the harmonized agent's first end-to-end pass.** No re-runs (other than the PIDILITIND retry after Anthropic 500). Total spend ~$10.

---

## Cross-Cutting Themes (45 total Gemini issues bucketed)

Themes ranked by how many sectors they hit. Fix once → improves many.

### Theme 1 — Sector framework misalignment (9 issues, 7 sectors) — **highest leverage**

Agents apply generic frameworks instead of sector-correct ones, OR identify the right framework but never execute it. All PROMPT_FIX.

| Sector | Misalignment |
|---|---|
| private_bank | EV/Revenue shown for a bank (debt = raw material, not capital structure) |
| metals | Stated "EV/EBITDA is primary for cyclicals" then weighted PE 35% in fair value table |
| platform | Identified EV/GMV as primary multiple for 1P/3P accounting transition then never calculated it |
| chemicals | Missing EV/EBITDA framework alongside PE |
| it_services | Missing FCF Yield analysis (mandatory for mature IT services) |
| auto | Missing cash-runway calculation for cash-burning EV startup |
| insurance | Missing CAC/LTV/take-rate unit economics for insurtech marketplace |

**Fix:** Add **mandatory metric checklist per sector** to each `sector_skills/<sector>/valuation.md` file (when we build them in Phase 2 of full-sector-skills-buildout). For now, single-sentence rule in `VALUATION_SYSTEM_V2`: *"When you state a metric is the 'primary' or 'most appropriate' for the sector, you MUST execute that calculation in the Fair Value Triangle, not just name it."*

### Theme 2 — Narrow PE band (4 issues, 4 sectors)

`get_valuation(band)` returns a 4-week / 27-day window for many stocks (bfsi, it_services, real_estate, regulated_power flagged it; chemicals/conglomerate/pharma/broker noted it but compensated). Mix of DATA + PROMPT.

| Layer | Fix |
|---|---|
| **DATA_FIX** | `data_api.py::get_valuation_band()` — investigate why bands return only ~16-28 observations. Fix the SQL/cache to pull min 3-5Y history (~750+ obs daily, 60+ obs monthly). |
| **PROMPT_FIX** | `VALUATION_INSTRUCTIONS_V2` workflow: *"If `get_valuation(band)` returns <30 observations OR <90 days span, IMMEDIATELY call `get_chart_data(chart_type='pe')` for the 7yr history before computing fair value. Do not use the truncated band for fair-value scenarios."* |

### Theme 3 — `get_yahoo_peers` fallback never called (4 issues, 4 sectors)

When `get_peer_sector` returns thin/garbage peers (conglomerate had 0, fmcg got ITC for HUL, insurance got Paytm/PineLabs for POLICYBZR, metals got JAINREC for VEDL), agents flag the limitation but don't call the available `get_yahoo_peers` fallback.

**Fix (PROMPT_FIX):** Add explicit rule to `VALUATION_INSTRUCTIONS_V2`: *"If `get_peer_sector` returns <3 relevant peers OR returns peers with fundamentally different business models, you MUST call `get_yahoo_peers` to find direct comparables. Do not list 'find better peers' as an open question."*

### Theme 4 — FMP DCF empty (4 issues, 4 sectors)

`get_fair_value_analysis(section='dcf')` returns empty for chemicals (PIDILITIND), it_services (TCS), metals (VEDL), real_estate (GODREJPROP). All DATA_FIX.

**Fix:** Investigate FMP `/stable/discounted-cash-flow` endpoint coverage for Indian equities. Either:
- (a) FMP's paid plan doesn't cover these specific symbols → add upfront empty handling
- (b) Symbol mapping issue (`.NS` suffix not always working for Indian large-caps)
- (c) Implement project-based NAV calculator for real estate (DCF doesn't fit anyway)

Same backend issue surfaced in earlier financials evals — coordinated fix opportunity.

### Theme 5 — SOTP missing subsidiaries (3 issues, 2 sectors)

| Sector | Missing |
|---|---|
| telecom (BHARTIARTL) | INDUSTOWER (~70% owned), BHARTIHEXA (listed) |
| regulated_power (NTPC) | NTPCGREEN (major IPO) |
| bfsi (SBIN — separate report) | SBI General Insurance (unlisted) |

| Layer | Fix |
|---|---|
| **DATA_FIX** | Update subsidiary mapping table in `store.py` for: NTPC→NTPCGREEN, BHARTIARTL→{INDUSTOWER, BHARTIHEXA}, HDFCBANK→{HDFCAMC, HDFCLIFE, HDB Financial pre-IPO}. Source: BSE/NSE corporate disclosures. |
| **PROMPT_FIX** | *"If `get_valuation(sotp)` returns 'No listed subsidiaries found' but you know subsidiaries exist (from concall, business profile, news), MANUALLY query each subsidiary's market cap via `get_valuation(snapshot)` using their ticker, and build the SOTP yourself. Never leave a known SOTP gap as an 'open question'."* |

### Theme 6 — `calculate` tool skipped (3 issues, 3 sectors)

Recurring issue. Already in Rule 5 of SHARED_PREAMBLE. Need stronger enforcement.

**Fix:** Add to `VALUATION_INSTRUCTIONS_V2` workflow as a hard step: *"Before writing the Fair Value Triangle, ENUMERATE every numeric output (PE × EPS, growth %, blended averages, MoS %) and confirm each came from a `calculate` call. List the calc IDs in the Tool Audit table."*

### Theme 7 — Open questions outside agent scope (2 issues, 2 sectors)

telecom (left INDUSTOWER as "open question" instead of querying), insurance (left "global peers" as open question instead of calling `get_yahoo_peers`). Same root cause as Themes 3 + 5 — agents punt to open-questions when tools were available.

**Fix:** Strengthen the existing Tenet-14-style open-questions ceiling rule (already in OWNERSHIP_SYSTEM_V2) by lifting it into VALUATION_SYSTEM_V2: *"Open questions are reserved for items genuinely unverifiable from your toolset. Before raising any open question, confirm you have called every fallback tool registered for valuation (`get_yahoo_peers`, `get_chart_data`, manual SOTP via `get_valuation(snapshot)` per ticker)."*

---

## Below-Bar Sectors — Targeted Patches

### telecom — BHARTIARTL → B (85) — **biggest lift**

Single COMPUTATION error tanked 5 points. Math: used `Current Price × Target EV / Current MCap` → should have been `Target MCap / Shares Outstanding`. Inflated Base Fair Value from ₹2,720 to ₹2,966.

**Patch:** Hard sector rule in `sector_skills/telecom/valuation.md` (when built) OR a `VALUATION_SYSTEM_V2` rule: *"Per-share fair value = Target MARKET CAP ÷ Shares Outstanding. NEVER use Enterprise Value as a numerator for per-share derivation. EV→equity conversion = EV − Net Debt = Market Cap."*

### it_services — TCS → B+ (88)

Two PROMPT_FIX, two DATA_FIX:
- Used flawed 27-day PE band for fair-value scenarios (Theme 2)
- Missing FCF Yield analysis (Theme 1)
- DATA: 27-day PE band (Theme 2), empty DCF (Theme 4)

Fixing Themes 1 + 2 above will lift this to A-.

### auto — OLAELEC → B+ (89) — **closest to bar**

Two PROMPT_FIX:
- Missing cash-runway calculation for ₹3,600 Cr/yr cash-burning EV maker (Theme 1)
- Failed to fall back to P/S or EV/Rev historical bands when PE band was empty

**Patch:** Fixing Theme 1 (mandatory cash-runway for negative-FCF/negative-EPS companies) lifts this to A-.

---

## Recommended Implementation Order

| # | Fix | Layer | Effort | Lift |
|---|---|---|---|---|
| 1 | Theme 6 patch (calculate tool enforcement) | `VALUATION_SYSTEM_V2` | 5 min | Telecom +5 (closes COMPUTATION gap) |
| 2 | Theme 1 patch (sector framework execution) | `VALUATION_SYSTEM_V2` + sector_skills | 30 min | All 3 below-bar → A-, several A- → A |
| 3 | Theme 2 prompt half (band fallback to chart_data) | `VALUATION_INSTRUCTIONS_V2` | 10 min | Lift remaining narrow-band sectors |
| 4 | Theme 3 patch (yahoo_peers mandatory fallback) | `VALUATION_INSTRUCTIONS_V2` | 10 min | Lift 4 sectors with thin peers |
| 5 | Theme 5 + 7 patch (SOTP fallback + open-q ceiling) | `VALUATION_SYSTEM_V2` | 15 min | Telecom + reg_power + bfsi |
| 6 | Theme 2 data half (band depth) | `data_api.py` | 1-2 hr | All sectors get 5Y band |
| 7 | Theme 4 (FMP DCF) | data pipeline | 2-3 hr | All sectors, also lifts financials agent |
| 8 | Theme 5 (subsidiary mapping) | `store.py` + ingestion | 1-2 hr | Telecom + reg_power + bfsi |

**Prompt-only patches (#1-5)** are 70 min total work, expected to lift telecom + it_services + auto over the A- bar with no data work. Do these first → re-run the 3 below-bar sectors → confirm grade lift.

---

## Detailed Per-Sector Reviews

Full per-sector strengths + Gemini issues archived at `/tmp/valuation_issues_dump.md` (also generated for thread record). Should we promote that to the plan archive?

---

## API Health Notes

- **Gemini gemini-3.1-pro-preview** has been returning 503 UNAVAILABLE since ~19:00 IST. Test re-grade attempt at 21:34 hung indefinitely — outage continuing 3+ hours.
- **Anthropic API** (Claude Agent SDK) hit one 500 Internal Server Error during PIDILITIND batch-4 run. Retry hit "Control request timeout: initialize" — looks like upstream stress. Other agents during the same window completed fine.
- **Reports preserved:** 13 of 15 sector reports saved at `~/vault/stocks/<STOCK>/reports/valuation.md`. PIDILITIND needs re-run.
- **Plan:** wait for Gemini recovery, batch `--skip-run` re-grade the 13 saved reports, then re-run PIDILITIND, then update issue summaries below.

---

## Per-Sector Gemini Issues

_Appended after each eval completes — PROMPT_FIX / DATA_FIX / COMPUTATION buckets with line refs._

### 1. bfsi — SBIN  → A- (92) PASS

**Agent runtime:** 639s (10.7 min) · **Report:** 37,784 chars · **Tools:** 11/13 used · **Cost:** $0.68 · **Eval:** 42s

**Summary (Gemini):** Institutional-quality report applying correct BFSI frameworks with exceptional analytical depth, particularly peer premium decomposition and justified P/B analysis. Primary gap: asset quality (GNPA/NNPA) and CASA metrics missing due to data pipeline failure (agent correctly flagged and couldn't resolve).

**Issues:**
1. **[DATA_FIX]** §8 — `get_quality_scores(bfsi)` / `get_company_context` didn't return GNPA/NNPA/PCR/CASA. → Fix BFSI quality-scores or sector_kpis to reliably extract these.  *(Known cross-agent issue — same one flagged in post-overnight-fixes.md Phase 6 for HDFCBANK financials.)*
2. **[DATA_FIX]** §2A — `get_valuation(band)` returned only 16 observations covering a 4-week window, rendering historical band mathematically useless. → Fix band tool to pull minimum 3-5Y history.
3. **[PROMPT_FIX]** §6 SOTP — Only valued listed subsidiaries + SBIMF IPO; missed SBI General Insurance and other unlisted subs. → Instruct valuation agent to search for + estimate material unlisted subsidiaries (AUM/Premium multiples) in SOTP.

**Strengths:**
- Brilliant decomposition of 59% PE premium into basis-point contributors (franchise size, subsidiaries, governance discount)
- Critical override of projection model's 19.2% base growth with management's guided 12-15%
- Flawless BFSI framework application — Justified P/B (ROE/Ke) + explicit rejection of standard FCFE DCF

### 2. private_bank — HDFCBANK  → ERR (Gemini 503, agent OK)

**Agent:** done: success 34,457 chars, 24 calls, 12/13 tools, 615s, $1.03 · Report saved at `~/vault/stocks/HDFCBANK/reports/valuation.md`

**Gemini grading:** 503 UNAVAILABLE ("high demand") on first attempt; `--skip-run` re-grade hung for 7 min on stuck HTTPS connection to Gemini before being killed. Likely region-wide Gemini capacity issue.

**Action:** batch re-grade at end of sequence once Gemini recovers. Agent report is intact.

### 3. it_services — TCS
_running — started 19:14_

