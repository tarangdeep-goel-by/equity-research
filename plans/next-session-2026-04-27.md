# Next session — 2026-04-27 (or later)

Ranked by payoff, not order. Written 2026-04-26 after a 14-PR session that closed out the 4-sprint Historical Analog + F&O plan and Part 3 eval-coverage scaffolding.

## Where we landed today

**Across the original `historical-analog-and-fo-agents.md` plan:**
- ✅ Sprint 0 — corp-action infrastructure (shipped earlier)
- ✅ Sprint 1 — Historical Analog Agent (shipped earlier)
- ✅ Sprint 2 — F&O ingestion pipeline (shipped earlier)
- ✅ **Sprint 3 — F&O Positioning Agent** (today: PR #108)

**Across `remediation-plan-post-review-2026-04-24.md`:**
- ✅ Wave 1 (correctness): PRs #82–#86 (earlier)
- ✅ Wave 2 (ops cleanup): PRs #87–#89 (earlier)
- ✅ Wave 3 (agent prompt wiring): PRs #90–#92 (earlier)
- ✅ **Wave 4** (today): PR #112 (industry as-of) + PR #118 (survivorship + delisted_symbols + cliffs)
- ✅ **Wave 5** (today): PR #117 (SOTP discovery) + PR #122 (chart invalidation lite)

**Across `part3-eval-coverage-implementation.md`:**
- ✅ **Tier 1 Macro autoeval** (today): PR #120 (A1 — honest as-of) + PR #124 (A2 — CLI/progress/matrix→6) + PR #127 (A3 — fortnightly cron + alert marker)
- ✅ **Tier 2 Backtest harness** (today): PR #123 (B2 — safe vault path + cohort cols + sampler) + PR #128 (B1 — zero-leakage proof, **no leakage found**) + PR #129 (B3 — CLI + eval_history archive; live N=20 baseline held)

**Plus today:** PR #109 (Tier 4 F&O autoeval scaffold) + PR #111 (date-rot test fixes).

**14 PRs merged this session:** #108, #109, #111, #112, #117, #118, #120, #122, #123, #124, #127, #128, #129 (when CI clears) + the test-fix #111 unblocker.

## 🔥 Highest ROI — fire the held operational runs

These were **explicitly held in their PRs** because each one is operational/expensive. All gated work is now satisfied:

```bash
cd flow-tracker

# 1. Backfill the new historical_states columns from PR-12 (industry_as_of_date + industry_source).
#    ~10-15 min, $0. Idempotent via INSERT OR REPLACE.
uv run python scripts/materialize_analog_states.py

# 2. Backfill delisted_symbols + unresolved_cliffs from PR-13.
#    ~minutes, $0. Surfaces the 454 candidate delisted symbols.
uv run python -c "from flowtracker.store import FlowStore; \
    s=FlowStore(); rows=s.detect_delisted_from_gaps(180); \
    s.upsert_delisted_symbols(rows); print(len(rows))"
uv run python scripts/reconcile_price_cliffs.py

# 3. Macro autoeval seed run (the cron will fire it fortnightly, but a one-shot now seeds results_macro.tsv).
#    ~10min, ~$1-2. Fires against the 6 matrix dates from PR #124.
uv run flowtrack research autoeval-macro --note "session-2026-04-27 seed"

# 4. F&O autoeval sweep (PR #109 deferred this until Wave 4 + Part 3 landed — both done).
#    ~30min, ~$3-5.
uv run flowtrack research autoeval -a fno_positioning

# 5. The marquee result: backtest N=20 baseline.
#    ~3hr, ~$8. The empirical calibration numbers Part 3 was built for.
#    Run in tmux. Closes Sprint 1 / Part 3 with hard data.
tmux new -s analog-backtest -d
tmux send-keys -t analog-backtest \
    "cd flow-tracker && uv run flowtrack research analog-backtest --n 20 --seed 42 --note 'baseline-post-scaffolds'" Enter
```

**Branching logic after the runs:**
- If macro grades land **A− or above** → cron continues; revisit only on regression alerts.
- If F&O agent grades land **<A−** → iterate on `prompts.py::FNO_POSITIONING_*_V2` against the failing sectors.
- If backtest **calibration hit-rate is meaningfully off chance** (≥5pp from 0.25 for any direction/tail) → analog agent is producing real signal; can promote `directional_adjustments` to a higher confidence weight in synthesis.
- If hit-rate is at chance → tighten `analog_builder` distance metric or feature vector.

## 🧱 Build-on-prior wins (small, high-signal)

From `next-session-2026-04-25.md`, still unaddressed:
1. **Wire alias normalization into `annual_report_extractor` + `deck_extractor`.** PR #99 only wired it for concalls. AR/deck extractors have their own canonical lists that suffer the same LLM-drift bug. Est: 1-2hr.
2. **Verify `get_sector_kpis` MCP tool surfaces the 6 new sectors** (capital_goods, hospitals, retail, amc, durables, logistics). Quick grep + test stock from each new sector: L&T, Apollo, Trent, HDFC AMC, Havells, Indigo. ~30min.
3. **Triage HINDUNILVR FY25-Q1 `0/13` zero-KPI quarter.** Single-symbol single-quarter; 15-30min triage to determine if PDF is a lemon or extractor drifted.
4. **`backfill_sector_kpis --force` on broader cohort** (24 sectors with skill files vs the 11-stock cohort today). Operational, populates synthesis context for stocks beyond the eval matrix.

## 📦 Plan items still pending

| Item | Why deferred | When to revisit |
|---|---|---|
| **PR-15 full** — `migrations/` directory refactor (~250 LOC) | Too risky during the parallel session's table churn (data_quality_flags, screener_discontinuity, fno_*, delisted_symbols, unresolved_cliffs all added in last 2 days) | When table churn settles for ≥1 week |
| **Tier 3 synthesis eval** | Explicitly low-ROI per Part 3 §3.2 — meta-rubric over already-graded specialists | When all specialists clear A− across the full sector matrix; or when synthesis quality regresses noticeably |
| **F&O agent Phase 2** (IV history surface, cross-stock cohort) | Per `historical-analog-and-fo-agents.md` §2.10 — needs months of accumulated option-chain snapshots | After ≥3 months of daily IV ingestion |
| **`fno universe refresh` CSV format fix** | NSE migrated CSV format; was worked around by SQL bootstrap from `fno_contracts`. Parallel session's PR #107 may have fixed this in the bhavcopy parser; verify | When you next need to refresh the F&O eligibility list |
| **L4 tight fixes** from post-eval v2 (6 deferred agent-sector pairs: VEDL valuation, GODREJPROP valuation, technical/GODREJPROP, valuation/ETERNAL, risk/POLICYBZR, financials/SBIN) | Most likely absorbed by the L1/L2/L3 lifts and recent data-quality work | After running the F&O sweep — re-grade tells you what actually still fails |

## 🔄 Side-thread context (parallel-session work today)

The other session shipped a **Strategy 1 data-quality initiative** (PRs #110, #113, #115, #116, #126) plus a **screener discontinuity detector** (PR #110). At handoff their open PRs were #114 (wave 1), #119 (wave 2), #125 (wave 4-5), #130 (finishing bundle), #131 (fno_positioning CLI fix), #132 (Strategy 2 wiring), #133 (IRDAI net premium), #134 (BFSI press-release extractor), #136 (Gemini #7 aggregate bridging) — **all 9 merged 2026-04-26**. Their worktrees `equity-research-{wave1,wave2,wave45,finish,s2wire,netprem,bfsipr,gemini7}` are now stale and can be pruned.

## 🆕 Side-thread late-day additions (2026-04-26 PM)

After the four wave PRs merged, the parallel session shipped **4 more PRs** closing the rest of the data-quality / pre-OCR backlog:

- **PR #132 — Strategy 2 wiring**: `get_five_year_summary()` added to `ResearchDataAPI`; DuPont / F-score / CAGR / common-size now prefer `ar_five_year_summary` as canonical restated trend source when it covers the window, fall back to Strategy 1 narrowing otherwise. Annotation contract: `data_source ∈ {ar_five_year_summary, screener_annual, mixed, screener_annual_bridged}`. Includes 24 unit tests for the previously-untested `five_year_parser`. ICICIBANK now has 11 AR rows surfacing (Schedule III restated).

- **PR #133 — IRDAI Net Premium ingestion**: curated `flowtracker/data/irdai_net_premium.json` (52 rows × 4 listed life insurers, FY24-FY25 annual + FY24-Q1..FY26-Q3 quarterly) sourced from IRDAI L-1-A-RA Revenue Account. Wave 1's `_apply_insurance_headline` swap-layer now flips `data_quality_note` off — HDFCLIFE FY25 NPE ₹70,537 Cr replaces the Schedule III ₹92,922 Cr (MTM-bundled). 38 new tests.

- **PR #134 — BFSI press-release text extractor** (no OCR): pulls quarterly NIM / NNPA / PCR / GNPA / CASA / CRAR / CET-1 / LCR from BSE-filed press-release PDFs via Claude SDK. Verified live: HDFCBANK Q3 NIM 3.51 / NNPA 0.42; ICICIBANK Q4 NIM 4.32; SBIN Q2 NIM 3.09; KOTAKBANK Q4 NIM 4.97. Lifts HDFCBANK `get_sector_kpis` from 8→11. **HDFCBANK FY26-Q4 PDF turned out image-rendered → correctly deferred to OCR session.** AXISBANK skipped (no `corporate_filings` rows ingested yet). 53 new tests.

- **PR #136 — Gemini review #7 aggregate bridging** (stacked on #132): when sub-component reshuffles but parent aggregate (`total_expenses` for P&L within ±10pp of revenue YoY; `total_assets` for BS within ±15% absolute) is conserved, suppress per-component flag for ratio computation. **HDFCBANK DuPont restored from 1y → 3y** (FY26 other_expenses_detail bridges; FY24 HDFC-merger flag correctly does NOT). **INFY DuPont restored to full 10y** (parent total_expenses gap only 0.58pp despite +3129% line shift). F-score for both stocks moves from `abstain` to computed score=5 with `bridged_via_aggregate=true`. 26 new tests.

**Operational backfills also done by side-thread:**
- AR re-extract: ICICIBANK / DRREDDY / VEDL / POLICYBZR — fresh per-year JSONs with PR #125's heading slicer
- BFSI sector_kpis: HDFCBANK / ICICIBANK / SBIN / BANKBARODA — 3 new quarters (458s)
- Pharma sector_kpis: SUNPHARMA / DRREDDY / CIPLA — already current after concall sweep, 0 new
- M&A catalyst: NO-OP (parser fires live in `gather_catalysts`; surfaces on next eval run)

## 🔥 Side-thread carry-over to next session

These are the held items from the data-quality / pre-OCR work that were intentionally deferred to next session (the user said "no evals today, defer to later"):

### A. Autoeval validation slice — confirm all the wave merges actually moved grader scores

```bash
cd /Users/tarang/Documents/Projects/equity-research

# 5 stocks × ~4 most-impacted agents = 20 runs. ~$5-8 in Gemini grading. ~30-45 min.
# Run after the macro/F&O autoevals from §"Highest ROI" above complete (rate-limit headroom).
for stock in HDFCBANK ICICIBANK SBIN INFY SUNPHARMA; do
  case $stock in
    HDFCBANK|ICICIBANK|SBIN) sector=bfsi ;;
    INFY) sector=it_services ;;
    SUNPHARMA) sector=pharma ;;
  esac
  ./scripts/eval-pipeline.sh $sector $stock financials sector valuation business
done
```

Expected uplift vs night2/night3 baseline: financials + sector should move on BFSI (PR #134 press-release backfill); valuation should move on INFY (PR #119 DCF / EV-EBITDA fixes); business should move on pharma (PR #125 24-KPI pharma config + sector_kpis backfill).

### B. AR 5-year highlights backfill — universe-wide (Strategy 2 needs data to be useful)

PR #132 wires Strategy 2 into the trend methods, but `ar_five_year_summary` table currently has only **1 stock × 11 rows (ICICIBANK)**. HDFCBANK / INFY / SUNPHARMA / 50+ Nifty names need their 5-yr highlights table parsed + persisted before the wiring helps them.

```bash
# Re-extract all ARs with the new heading slicer + 5-yr parser. ~30 min, ~$2 (rate-limited).
# Pareto: top-50 Nifty universe is enough for first pass; full 500 can run overnight.
for s in $(uv run python -c "from flowtracker.store import FlowStore; \
  print('\n'.join(FlowStore()._conn.execute('SELECT symbol FROM company_snapshot WHERE market_cap_cr > 50000 ORDER BY market_cap_cr DESC LIMIT 50').fetchall() | jq))"); do
  uv run flowtrack filings extract-ar -s $s --force
done
```

After this lands, smoke-test by running `get_dupont_decomposition` on HDFCBANK + 5 other large-caps and confirming `data_source` shows `ar_five_year_summary` (or `mixed`) instead of `screener_annual_bridged`.

### C. AR image-OCR session — the deferred big rock

The remaining gap surfaced by today's PRs:

1. **HDFCBANK AR is image-rendered** — Strategy 2 gives it nothing until OCR; falls through to Strategy 1 narrowing + Gemini #7 bridging (which works for FY26 but not FY24)
2. **HDFCBANK FY26-Q4 press release is image-rendered** — PR #134 correctly skipped; OCR would unlock the most-recent quarter's NIM/NNPA/PCR
3. **AR segmentals / RPTs / EV rollforwards / ICICIBANK notes** — original P0 from `eval-data-fixes-next-session.md`
4. **Insurance KPIs (EV / VNB / ROEV / persistency / solvency)** — depends on AR image-OCR
5. **Deck image-OCR** — same harness as #3
6. **HINDALCO nameplate-capacity tables** — folds into AR image-OCR

This is the next big workstream. Plan it as its own multi-day effort with a vision-OCR fallback pass in `annual_report_extractor.py` (cost-budget: ~$24 one-time backfill at $0.10/page × 16 stocks × 3 image sections × 5 pages, ~$5/quarter ongoing).

### D. Truly low-priority (post-OCR, optional)

- FDA inspection auto-fetch from `datadashboard.fda.gov` (PR #125 ships CSV-seed; works for now)
- ADR/GDR programmatic ingestion from BNY Mellon (PR #125 XBRL `CustodianOrDRHolder` covers filers; external scrape pending)
- yfinance share-count sanity gate (NESTLEIND 2× bug) — covered partially in PR #114, but a generic Screener-vs-yfinance reconciliation pass would catch the long tail

## 🏗️ Long-parked

- **Re-eval cycle 2** — autoagent-pilot's last run was night2/3 (PRs #102–#106) on the 7 original specialists. Today's data-quality fixes + new fno_positioning agent + auto-discovered SOTP candidates likely move grades further. A clean re-grade across all 11 agents on the 16-stock matrix would refresh the baseline. Est: ~12-15hrs in tmux per the autoagent-pilot pattern.

## Checkpointed state at session handoff

- **Main:** post-#129 merge (run `git pull --ff-only` to confirm)
- **Worktrees:** my work cleaned (analog-survivorship, sotp-discovery, macro-eval-asof, macro-cli, backtest-safe, chart-invalidation, macro-cron, analog-leak-test, backtest-cli all removed). Parallel session's 5 worktrees still reserved.
- **Local branches:** all merge-deleted by `gh pr merge --delete-branch`
- **eval_matrix_macro.yaml:** 6 dates (2025-11-01, 2025-12-15, 2026-02-01, 2026-03-15, 2026-04-15, 2026-04-22)
- **eval_matrix.yaml:** Tier 3 deferral TODO comment at top
- **historical_states schema:** 2 new columns from PR-12 — NULL on existing 17,898 rows until step #1 above runs
- **delisted_symbols + unresolved_cliffs tables:** empty until step #2 runs
- **results_macro.tsv:** doesn't exist yet — created by step #3
- **F&O autoeval results:** none yet — created by step #4
- **backtest_results_analog.tsv + eval_history/analog_backtest_*.json:** don't exist yet — created by step #5

## One-sentence orientation for future-you

> Today closed every pending plan item from the 4-sprint Historical Analog + F&O initiative + the Wave 4/5 correctness remediation + Part 3 eval-coverage; the next session is ALL operational — fire the 5 held runs in priority order, then iterate based on what they surface (calibration → analog tweaks; F&O grades → prompt tuning; KPI gaps → backfill).
