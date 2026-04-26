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

The other session shipped a **Strategy 1 data-quality initiative** (PRs #110, #113, #115, #116, #126) plus a **screener discontinuity detector** (PR #110). Their open PRs at handoff: #114 (data-fixes wave 1), #119 (wave 2). Their reserved worktrees: `equity-research-wave1`, `wave2`, `wave45`, `dq-fixes`, `comparable-growth`. Stay clear of those branches.

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
