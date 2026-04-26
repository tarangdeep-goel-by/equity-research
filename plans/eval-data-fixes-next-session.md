# Data-Fix Backlog from autoagent-pilot Night2/3 Evals

**Generated:** 2026-04-25 end-of-session, before next batch.
**Sources:** Full scan of `flow-tracker/flowtracker/research/autoeval/eval_history/2026042[345]T*.json` (172 DATA_FIX issues across 8 specialist agents × 16 benchmark stocks). Plus my hands-on investigation of the production DB.

This document is the **complete pending inventory** — cold-start ready. Read it, pick a theme, and execute.

---

## Summary

- **172 DATA_FIX issues** across 16 stocks
- **PR #107 closed: 8 themes** (~62 issues — F&O, macro G-Sec/VIX/brent, AR auditor partial, mf_changes, peer mcap, FII synthetic, NYKAA FCF, earnings quarter_end)
- **Remaining: 14 distinct themes (~110 issues)** organized below by leverage

### Companion plans
- `plans/screener-data-discontinuity.md` — universe-wide Screener reclassification problem (344 flags across 211 of 485 stocks). Read this BEFORE working on any trend/ratio fix because it dwarfs every per-stock issue listed below.

---

## Stocks ranked by remaining DATA_FIX issue count

```
HDFCBANK     18    INFY        11    NESTLEIND    7
SBIN         17    HDFCLIFE    10    SUNPHARMA    6
TCS          14    DRREDDY      9    POLICYBZR    6
BANKBARODA   14    ETERNAL      9
ICICIBANK    14    NYKAA        9
HINDALCO     12    VEDL         8
                   HINDUNILVR   8
```

The 4 BFSI stocks dominate (63 issues combined) — fixing BFSI-specific gaps gives outsized leverage.

---

## Pending themes — ranked by number of issues + cross-agent impact

### 🔴 P0 — Concall data / FY26 staleness (31 issues, 12 stocks, 5 agents)

**Status:** Concall sweep was launched in tmux session `concall-sweep` at end-of-session — verify completion before re-evaluating. If complete, this drops to a few residual extractor bugs.

**Pattern:** TCS/NESTLEIND/INFY/ETERNAL flagged as having missing or degraded FY26 concalls. Some stocks have FY26-Q3 transcripts but extraction is degraded.

**What to check next session:**
1. `tmux ls` — has `concall-sweep` finished? `tail -50 /tmp/concall-sweep.log`
2. Per-stock vault inventory:
   ```bash
   for s in SBIN BANKBARODA HDFCBANK ICICIBANK SUNPHARMA DRREDDY TCS INFY VEDL HINDALCO HINDUNILVR NESTLEIND ETERNAL NYKAA POLICYBZR HDFCLIFE; do
     echo -n "$s: "; ls /Users/tarang/vault/stocks/$s/filings/FY26-Q*/concall.pdf 2>/dev/null | wc -l
   done
   ```
3. For stocks with <2 FY26 concalls, check whether the issue is BSE filings list (their concall just isn't disclosed yet — common for FY26-Q4 in late April), or our extractor failing.

**Likely residual fixes:**
- Concall extractor industry-hint not firing for certain stocks (e.g., NESTLEIND was being flagged as `not_a_deck` for 3 of 4 quarters)
- Q4 earnings season runs through May — some FY26-Q4 concalls genuinely don't exist yet

**Effort:** 1-2 hours after sweep completes; mostly a verification + extractor parameter tuning task.

---

### 🔴 P0 — AR image-rendered tables / OCR (30 issues, 13 stocks, 5 agents)

**Pattern:** Modern Indian ARs include critical tables as **rasterized images** rather than embedded text — segmental P&L, related-party transactions (Form AOC-2), Embedded Value rollforwards (life insurers), capacity tables (metals). Docling-based extraction returns empty for these sections.

**Specific instances:**
- **ETERNAL FY25** — segmental tables (Zomato/Blinkit splits) not extracted
- **HINDALCO FY25** — segmental tables (Aluminium/Copper/Novelis), nameplate-capacity tables
- **HINDUNILVR FY25** — Form AOC-2 (related-party transactions) image-only
- **VEDL FY25** — segmental tables for Aluminium/Zinc/Power/Iron Ore
- **HDFCLIFE FY25** — Embedded Value rollforward, VNB walk, ROEV computation tables
- **ICICIBANK FY25** — `notes_to_financials` returned only 36 chars (whole section is image-rendered)

**Fix surface:**
- `flow-tracker/flowtracker/research/annual_report_extractor.py` — add a vision-OCR fallback pass when section extraction yields <500 chars OR returns a known image-marker pattern
- Use Claude Vision via Agent SDK with the section's PDF page range (already available from heading_toc)
- Cache OCR'd output to avoid repeated vision calls

**Effort:** Medium — 1-2 days. Vision-OCR setup + heading detection extension + caching layer.

**Cost note:** Each vision OCR pass is ~$0.05-$0.15 per page. Pre-budget: 16 stocks × ~3 image sections × ~5 pages × $0.10 ≈ $24 one-time backfill, ~$5/quarter ongoing.

---

### 🟡 P1 — BFSI sector_kpis (NNPA/PCR/LCR/CASA/CRAR/CET-1/GNPA) (19 issues, 4 stocks)

**Pattern:** `get_sector_kpis(symbol, sector='bfsi')` returns null or stale values for the 6 banking-specific KPIs the BFSI sector needs. Affects every bank stock the sector/financials/business agents touch.

**Specific instances:**
- HDFCBANK: NNPA, PCR, LCR all null in sector_kpis
- ICICIBANK: same null pattern; CASA ratio not extracted from concall
- SBIN: GNPA + CRAR/CET-1 extraction fails
- BANKBARODA: same pattern

**Fix surface:**
- `flow-tracker/flowtracker/research/sector_kpis.py` — already has a BFSI config; need to verify its `extraction_keys` aliases match what concalls actually say
- `flow-tracker/flowtracker/research/concall_extractor.py` — sector hint should force CASA/NPA/LCR/CRAR extraction for `industry='bfsi'`
- `scripts/backfill_sector_kpis.py` exists — run it for the 4 banks after the concall sweep, then re-eval

**Effort:** Medium — 0.5-1 day. Largely operational once concall extraction is solid.

**Adjacency:** This is partly downstream of the concall sweep (P0) — wait for that first.

---

### 🟡 P1 — Chart rendering (`render_chart(expense_pie)` returns no data) (9 issues, 7 stocks)

**Pattern:** `render_chart(symbol, 'expense_pie')` returns `(no data)` for major stocks (SBIN, BANKBARODA, TCS, DRREDDY, HDFCBANK, etc.). The agent dutifully calls the tool, gets empty, narrates around it.

**Fix surface:**
- `flow-tracker/flowtracker/research/charts.py` — find the `expense_pie` chart type
- Likely root cause: it expects fields like `raw_material_cost / employee_cost / power_and_fuel / selling_and_admin / other_mfr_exp / other_expenses_detail` from `annual_financials`. For banks, most of those are NULL (banks have employee + other + interest only). For some companies, the most-recent FY row hasn't been ingested yet.
- Either: (a) gracefully degrade to a 2-3 slice pie when only employee+other are populated, or (b) compute from quarterly_results aggregates

**Effort:** Small — 2-4 hours. Just a chart-data validation + fallback path.

---

### 🟡 P1 — Valuation tools returning empty for major caps (~8 issues, 6 stocks)

**Cluster of broken valuation endpoints:**

1. **`get_valuation(band, metric='pb')` and `get_chart_data(pbv)` empty for banks** — HDFCBANK, ICICIBANK, BANKBARODA. PB band is the primary banking valuation tool. Likely `valuation_band` table doesn't have PB rows for banks; or the chart data path filters them out.

2. **`get_fair_value_analysis(section='dcf')` returns null for HINDUNILVR** — DCF returned null for a clean large-cap with 10+ years of stable FCF. Investigate `dcf_reason` (the DCF reason-code field) — likely "negative_fcf" misclassification or "growth_above_limits" hitting a sector cap.

3. **INFY DCF returns no projections** — same pattern as HINDUNILVR. Both are mega-caps with mature FCF.

4. **EV/EBITDA currency mismatch for TCS peers** — INFY (994x) and HCL Tech (1192x) showing absurd EV/EBITDA values. Almost certainly EV in INR Cr but EBITDA in USD-denominated reporting from a Yahoo/FMP path.

5. **`calculate` tool unit mismatch on BANKBARODA** — `total_cr_to_per_share` got 51,713.62 lakhs as input (should be raw share count). Either prompt confusion or tool docstring ambiguity.

**Fix surface:**
- `flow-tracker/flowtracker/research/data_api.py` — `get_valuation`, `get_chart_data`, `get_fair_value_analysis`
- `flow-tracker/flowtracker/research/wacc.py` — check WACC computation for mega-caps (HDFCLIFE Beta missing too)

**Effort:** Medium — 1 day. Multiple narrow fixes. PB-band-for-banks is highest priority because it's a structurally critical tool.

---

### 🟡 P1 — Macro anchor extraction quality (Economic Survey, RBI AR, IRDAI) (~7 issues, 6 stocks)

**Pattern:** `get_macro_anchor` and `rbi_ar_assessment` tools return tiny payloads (29 chars), 'not_found', or heading-mismatch errors. Affects every macro-agent run.

**Specific instances:**
- TCS: `rbi_ar_assessment` for "Prospects for 2025-26" returned only 29 chars
- ICICIBANK: same tool returned null for assessment + economic sections
- NESTLEIND, HINDUNILVR: Economic Survey "private consumption" / "consumer demand" chapters not found (heading mismatch)
- NYKAA: Economic Survey TRENDS + RBI MPR Consumer Price Inflation near-empty
- HDFCLIFE, POLICYBZR: IRDAI Annual Report not in macro vault at all
- BANKBARODA: relied on secondary news for RBI MPC FY27 GDP/inflation projections (MPC statement not in catalog)

**Fix surface:**
- `flow-tracker/flowtracker/research/macro_anchors.py` — extraction & cache
- `flow-tracker/flowtracker/research/heading_toc.py` — heading match heuristic for anchor docs (same family of issue as the AR auditor_report fix)
- Add IRDAI Annual Report to the anchor catalog (currently has Economic Survey, RBI AR, RBI MPR, Union Budget — missing IRDAI)

**Effort:** Medium — 1-2 days. Layered heading detection + new anchor source.

---

### 🟡 P1 — System-wide RBI credit/deposit data (6 issues, 4 stocks)

**Pattern:** Bank sector evaluations consistently flag "system-level credit-deposit gap unavailable in `get_market_context(macro)`". Banks need system-wide credit growth, deposit growth, CD ratio, money supply.

**Source:** RBI Weekly Statistical Supplement (WSS) — has all of these. Public, scrapeable, weekly cadence.

**Fix surface:**
- New `flow-tracker/flowtracker/macro_client.py` method `_fetch_rbi_wss()` that scrapes RBI WSS or pulls from `https://dbie.rbi.org.in/`
- New columns in `macro_daily` (or a new `macro_system_credit` table): system_credit_growth_yoy, system_deposit_growth_yoy, system_cd_ratio
- Surface in `get_macro_snapshot()` output

**Effort:** Small-Medium — 4-6 hours. RBI scraping is well-documented.

---

### 🟡 P1 — LME commodity prices (4 issues, 4 stocks)

**Pattern:** Tier 1F shipped Brent surfacing but explicitly deferred LME aluminium/zinc/lead/copper. Metals technical/macro analysis for VEDL/HINDALCO needs them.

**Fix surface:**
- `flowtracker/commodity_client.py` — add LME contracts via yfinance tickers (`ALI=F`, `HG=F`, `ZNC=F`, `PB=F`) or FMP commodities endpoint
- 1Y backfill, then daily fetch via cron
- Surface in `get_commodity_snapshot()` alongside gold/silver/brent (already wired)

**Effort:** Small — 2-3 hours. Same pattern as Brent surfacing.

---

### 🟡 P1 — Insurance KPIs (Embedded Value / VNB / ROEV) (3 issues, 2 stocks)

**Pattern:** HDFCLIFE and POLICYBZR — life-insurance specific KPIs not extracted from AR/concall. The agent has to estimate from secondary sources.

**Fix surface:**
- `flowtracker/research/concall_extractor.py` — sector hint for `industry='insurance'` should force EV / VNB / ROEV extraction
- `flowtracker/research/annual_report_extractor.py` — add insurance-specific sections (EV rollforward, VNB walk are usually in a dedicated chapter post-MD&A)
- `flowtracker/research/sector_kpis.py` — add insurance KPI config (EV growth, VNB margin, ROEV, persistency 13/25/49/61, solvency margin)

**Effort:** Medium — 1 day. Adjacent to BFSI sector_kpis work.

**Adjacency:** Best done after AR image-OCR (P0) lands, since EV/VNB tables are almost always image-rendered.

---

### 🟡 P1 — Deck extraction degraded (~9 issues, 8 stocks)

**Pattern:** Investor deck extraction returning empty or `not_a_deck` for benchmark stocks.
- HINDALCO FY26-Q3 deck — segment tables not parsed
- INFY decks stale (FY22 only — extraction failing on newer decks)
- NESTLEIND classified as `not_a_deck` for 3 of 4 quarters (PR #104 partial fix)

**Fix surface:**
- `flowtracker/research/deck_extractor.py`
- Same image-OCR theme as AR (P0) — decks are even more image-heavy than ARs

**Effort:** Medium — 1-2 days. Combine with AR image-OCR work.

---

### 🟢 P2 — AR section extraction failures (chairman_letter, MD&A, governance) (~7 issues, 4 stocks)

**Pattern:** Beyond the auditor_report extraction we already fixed, other sections return `section_not_found` or "cover page only":
- ICICIBANK FY25 — chairman_letter and mdna `section_not_found`
- DRREDDY — MD&A failure prevented R&D % extraction
- VEDL FY25 — corporate_governance thin (committee composition, director changes missing)
- POLICYBZR — board composition sparse (3,118 chars)
- ICICIBANK ownership AR — cover page only

**Fix surface:** Same `heading_toc.py` heuristic family as auditor_report — extend per-section anchors and end-detection. Combine with the SBIN/HDFCLIFE/HINDUNILVR auditor layout iteration that subagent A is currently running.

**Effort:** Small-Medium — extends the existing AR fix, 4-6 hours per section type.

---

### 🟢 P2 — yfinance / Screener-specific data quality bugs (5 issues)

Narrow, single-stock or single-tool issues:

1. **NESTLEIND yfinance share count off by 2×** — yfinance returned 1,928M shares vs Screener's correct 964M. Likely bonus-issue adjustment delta. Fix: prefer Screener's `num_shares` when both populated, OR add a sanity check that yfinance/Screener agree within 5%.

2. **HDFCLIFE Screener "Revenue" includes MTM gains/losses on policyholder funds** — wild swings make the data table misleading. Fix: for `industry='insurance'`, present "Net Premium Earned" instead of "Revenue" as the headline top-line.

3. **HDFCBANK adr_gdr stub null** — outstanding ADR units not populated, blocking foreign-headroom calc. Fix: add ADR tracking via NYSE filings or Bank of New York Mellon (sponsor bank) data.

4. **HDFCLIFE Beta vs Nifty 50 missing** — analytical_profile WACC computation fails. Fix: confirm `daily_stock_data.adj_close` populated for HDFCLIFE for ≥3 years (Beta needs that history).

5. **HINDALCO MACD/Bollinger/ADX returning null** in technicals — FMP path may have failed; fallback to local computation isn't covering MACD/BB/ADX.

**Effort:** Small — each is a targeted fix, 1-2 hours.

---

### 🟢 P2 — Public bucket / shareholding granularity (4 issues, 4 stocks)

**Pattern:** Beyond TCS FII names (already fixed), several other shareholding-granularity gaps:

- **VEDL** — public bucket sub-breakdown (Retail vs HNI vs Corporate Bodies) not surfaced
- **NYKAA** — ESOP pool size not in tools (critical for new-age tech dilution analysis)
- **POLICYBZR** — board composition detail sparse
- **HDFCBANK** — ADR/GDR outstanding units null

**Fix surface:**
- `flowtracker/research/data_api.py` — extend `get_ownership` with `public_breakdown` section (parse from BSE shareholding pattern XBRL)
- New tool / extension for ESOP tracking — Schedule III mandates ESOP disclosure in AR's Notes; could extract via existing AR pipeline

**Effort:** Medium — 0.5-1 day. Touches both ingestion (XBRL parse extension) and AR extraction.

---

### 🟢 P2 — Sector-specific gaps (events / capacity / regulatory) (~5 issues, 5 stocks)

Single-stock-but-load-bearing items:

- **SUNPHARMA Organon M&A deal details** — `get_events_actions(catalysts)` didn't return the structured deal info (agent had to use unstructured headlines)
- **SUNPHARMA US plant USFDA compliance** — not in structured data tools (warning-letter, 483 status, OAI)
- **SUNPHARMA gross-to-net (GTN) and US price erosion quantum** — not extractable
- **HINDALCO nameplate capacity (KT)** — needed for EV/tonne, missing from structured tools
- **ETERNAL total platform-economy TAM** — sector_kpis empty for `industry='platform'`

**Fix surface:**
- `flowtracker/catalyst_client.py` + `catalyst_models.py` — extend M&A catalyst with deal-size, target, status fields
- New extractor for FDA compliance — would need to scrape FDA inspection database (orangebook.fda.gov / FDA Form 483 search)
- Pharma KPIs: extend `sector_kpis.py` `pharma` config with R&D %, GTN, USFDA observations, ANDA pipeline count

**Effort:** Medium — 1-2 days for pharma sector pack; capacity tables are downstream of AR image-OCR.

---

### ⚫ Out of scope (no code fix — needs ops work)

- **FMP 403 errors** (4 stocks: SUNPHARMA, TCS, VEDL, POLICYBZR) — API key quota or domain block. Manual investigation needed; verify FMP subscription status, check whether `.NS` ticker mapping changed, possibly rotate API key. Not a code fix.

---

## Recommended next-session sequence

Optimized for **fastest leverage to the next eval**:

### Wave 1 (parallel, ~half day): operational + small fixes
1. **Verify concall sweep** completion + check vault FY26 inventory
2. **LME commodity prices** — same pattern as Brent (small fix)
3. **System-wide RBI credit/deposit** — small RBI WSS scraper
4. **`render_chart(expense_pie)` fallback** — chart graceful-degradation
5. **NESTLEIND yfinance 2× share-count fix** — sanity-check + prefer Screener
6. **HDFCLIFE/insurance "Net Premium" presentation** — sector-aware headline

These ship together as one PR — narrow surface, high stock-count impact.

### Wave 2 (medium effort, 1-2 days): banks + valuation
7. **PB band for banks** (HDFCBANK/ICICIBANK/BANKBARODA) — fix `get_valuation(band, metric='pb')` for banks
8. **DCF returns null for INFY/HINDUNILVR** — investigate `dcf_reason`
9. **EV/EBITDA currency mismatch** for TCS peers — USD/INR normalization in valuation matrix
10. **BFSI sector_kpis backfill** (after concall sweep verified)
11. **Macro anchor extraction quality** (heading_toc extension + IRDAI source)

### Wave 3 (large, 1-2 days each, can be parallel): vision OCR
12. **AR image-OCR** — segmentals, RPTs, EV rollforwards, ICICIBANK notes
13. **Deck image-OCR** — same harness as #12
14. **Insurance KPI extraction** — depends on #12 landing first

### Wave 4 (concurrent, 1-2 days): universe data quality
15. **Screener data discontinuity detector + flagging** — see `plans/screener-data-discontinuity.md` Strategy 1 (detect + warn). This is the silent-corruption fix that affects 211 of 485 stocks.
16. **AR 5-year highlights table extraction** — Strategy 2 from the same plan; provides the canonical restated trend source.

### Wave 5 (smaller polish, 0.5 day each)
17. AR section extraction beyond auditor_report (chairman_letter, MD&A, governance)
18. ADR/GDR + ESOP + public sub-breakdown
19. Pharma sector pack (USFDA compliance + GTN + R&D extraction)
20. Capacity tables for metals (HINDALCO KT) — folds into AR image-OCR

---

## What would move the needle most for the *next* eval grade

If the goal is "best autoagent-pilot score on next run", priority is:

1. **Concall sweep verification** — single biggest unlock for FY26-relevant stocks (12 of 16 affected)
2. **AR image-OCR** — unblocks 13 stocks across 5 agents; the deepest current data gap
3. **PB band for banks + BFSI sector_kpis** — directly fixes 4 of the most-evaluated stocks
4. **System credit / LME / RBI bulletin** — fixes the macro foundation every agent reads

Combined: Waves 1+2 + concall sweep + AR-OCR start = expected to flip 6-8 stocks from B/B+ to A- territory.

---

## Files to read first when picking this up

```
plans/screener-data-discontinuity.md          # universe discontinuity context
plans/eval-data-fixes-next-session.md         # this file
flow-tracker/flowtracker/research/data_api.py # ResearchDataAPI surface
flow-tracker/flowtracker/research/sector_kpis.py
flow-tracker/flowtracker/research/concall_extractor.py
flow-tracker/flowtracker/research/annual_report_extractor.py
flow-tracker/flowtracker/research/heading_toc.py
flow-tracker/flowtracker/research/macro_anchors.py
flow-tracker/flowtracker/macro_client.py
flow-tracker/flowtracker/commodity_client.py
flow-tracker/flowtracker/charts.py             # for expense_pie fix
```

## How to regenerate this inventory

```bash
cd flow-tracker
uv run python -c "
import json, glob
fixes = []
for f in glob.glob('flowtracker/research/autoeval/eval_history/2026042[345]T*.json'):
    d = json.load(open(f))
    for sk, res in d.get('results', {}).items():
        for iss in res.get('issues', []) or []:
            if iss.get('type') == 'DATA_FIX':
                fixes.append((res.get('stock'), res.get('agent') or sk, iss.get('section'), iss.get('issue')))
print(f'{len(fixes)} DATA_FIX issues')
"
```

Re-run after each eval cycle to track which themes have closed and which remain.
