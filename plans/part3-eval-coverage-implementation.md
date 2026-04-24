# Part 3 — Eval Coverage for Newer Agents: Implementation Plan

**Date:** 2026-04-24
**Parent plan:** `plans/historical-analog-and-fo-agents.md` §3
**Status:** Scaffolds shipped in PR #75 (commit `9d175c4`). This plan hardens, productionizes, and runs them.
**LOC cap per PR:** ≤500. No eval artifacts committed to code PRs (see remediation-plan PR-6).

---

## 0. Current state — what's already in the repo

PR #75 landed the skeleton; it is NOT production-ready. Inventory:

| Artifact | Path | State |
|---|---|---|
| Macro eval harness | `flow-tracker/flowtracker/research/autoeval/evaluate_macro.py` | Standalone script, 357 LOC. Works end-to-end against wall-clock. Imports `GRADE_MAP`, `AgentEvalResult`, `EvalIssue`, `ParameterGrade`, `_extract_json` from the IMMUTABLE `evaluate.py`. |
| Macro matrix | `flow-tracker/flowtracker/research/autoeval/eval_matrix_macro.yaml` | 4 dates (2025-11-01, 2025-12-15, 2026-02-01, 2026-03-15). Exit criteria says 4–6. |
| Backtest script | `flow-tracker/flowtracker/research/autoeval/backtest_historical_analog.py` | Standalone, 353 LOC. Uses `FLOWTRACK_AS_OF` env var to anchor `data_api`/`prompts` to the sample's as-of. |
| As-of plumbing | `data_api.py:186-207`, `prompts.py:2127-2148` | Live. Reads `FLOWTRACK_AS_OF=YYYY-MM-DD` and anchors temporal context + default as-of to it. |
| Forward-return table | `analog_forward_returns` | 17,898 rows total, 14,881 with 12m returns + outcome labels, range 2016-03-31 → 2026-03-31. Mature (≥450 days old) labeled population: **recovered 6,988 / sideways 5,090 / blew_up 2,306** — 14k+ eligible samples, far more than the 20-sample target. |
| CLI wiring | `flowtrack research autoeval` routes only to `evaluate.py` | Macro + backtest are **not** CLI-exposed today; operators invoke via `uv run python …/evaluate_macro.py`. |
| Cron | `flow-tracker/scripts/plists/` | No macro-eval or backtest plist. |
| Results TSV | `results_macro.tsv`, `backtest_results_analog.tsv` | Paths defined; files don't yet exist (nothing committed). |

**Implication:** Tier 1 and Tier 2 are 70% built. The remaining ~30% is the hard part — making the macro eval honest at backdated as-ofs, adding a leakage test for the backtest, wiring CLI + cron, and executing the first real runs.

---

## 1. Known gaps in the scaffolds

### 1.1 Macro harness (`evaluate_macro.py`)

1. **As-of lie (critical).** `run_macro_agent` invokes the CLI with the live system date; the rubric then grades the resulting report against the matrix's historical date. `fetch_anchor_catalog()` likewise reads the catalog as it stands today. So a "2025-11-01" eval actually grades *today's* regime against a rubric that says today is 2025-11-01 — anchor-exhaustion and stale-policy dimensions are meaningless at any date that isn't wall-clock.
2. **No retry / no timeout instrumentation.** `Popen` loop has a 1800s kill but no retry; Gemini 503s fail the whole cycle. `evaluate.py` already has a more robust pattern — mirror it.
3. **`results_macro.tsv` is append-only with no rotation/archive** — will grow until somebody cleans it up. `progress.py` doesn't know about the macro TSV.
4. **`placeholder_symbol: NIFTY` is a hidden coupling.** The macro agent writes to `~/vault/stocks/NIFTY/reports/macro.md`, which pollutes the stock vault. Needs a dedicated path like `~/vault/macro/YYYY-MM-DD/macro.md`.
5. **`--cycle` flag exists but is always `0`.** Cycle semantics don't apply to a flat-date matrix. Either make it meaningful (which batch of matrix eval this was) or drop.
6. **Anchor catalog is injected as comma-joined names only** — the Gemini grader has no way to know which are "complete" vs "pending"; it has to trust the harness filtered. Acceptable but worth a comment.

### 1.2 Backtest harness (`backtest_historical_analog.py`)

1. **No zero-leakage integration test.** The plan's exit criterion §3.3 explicitly requires one: "computing features for pre-2020 symbol touches no post-2020 data". The scaffolded docstring acknowledges residual leakage via cached vault JSONs. Need an assertion-style test, not just a docstring.
2. **Briefing path is destructive.** `load_briefing` reads `~/vault/stocks/{symbol}/briefings/historical_analog.json` — this is the same path used by live research runs. Backtesting `SBIN` with `as_of=2023-12-31` will overwrite the live SBIN briefing. Must write to a backtest-scoped path.
3. **`analog_forward_returns` doesn't carry `cohort_12m_pcts`.** The script computes quartiles by reading `top_analogs[*].return_12m_pct` from the briefing JSON. If the agent's cohort retrieval has drifted since materialization, ground-truth quartiles are biased. Either (a) snapshot the cohort at backtest time into the TSV for later audit, or (b) read cohort 12m returns from `historical_states` directly keyed on the agent's retrieval.
4. **Stratified sampler's top-up path checks `row not in sample`** — dicts in a list, equality comparison, `O(n²)`. Not a correctness bug; slow at N=20, broken at N=200.
5. **`datetime.utcnow()` deprecated** in py3.12. Use `datetime.now(timezone.utc)` like `evaluate_macro.py`.
6. **`--skip-run` path assumes briefings exist from a prior real run** — works, but deleting briefings between runs silently produces "No briefing produced" errors. Document, or fail louder.

### 1.3 Shared

- Neither harness writes to `eval_history/` JSON archive the way `evaluate.py` does (via `_archive_eval_run`). So there's no long-term, queryable record — just the TSVs.
- Neither harness is referenced from `research/autoeval/README.md`.
- Macro eval is not part of any cron; backtest isn't either. Monthly cadence is the plan's stated goal for backtest.

---

## 2. Scope of this plan

**In scope (~4 days effort):**
- Tier 1 Macro autoeval — fix the as-of lie, ship CLI wiring, run against 6 matrix dates, grade visibility in `results_macro.tsv`, lightweight cron.
- Tier 2 Historical Analog backtest — zero-leakage integration test, safe briefing path, zero-leakage-audit columns, ship CLI wiring, run N=20 on real data, publish calibration summary.
- CLI surface: `flowtrack research autoeval-macro`, `flowtrack research analog-backtest`.
- `progress.py` extension so macro + backtest TSVs render alongside specialist results.
- `eval_history/` archival parity.
- README updates.

**Out of scope (explicitly):**
- Tier 3 synthesis eval — hard and low-ROI per plan §3.2. Ship with a `# TODO` marker in `eval_matrix.yaml` only.
- Tier 4 F&O positioning eval — folds into Sprint 3 budget; not this plan.
- Backfilling historical `index_constituents`/`industry` for deeper leakage control on pre-2020 samples — that's remediation-plan PR-12/13 territory.
- Re-materializing `historical_states` after leakage fixes — deferred to its own PR (only if needed after the leakage test surfaces something).

---

## 3. PR decomposition — 6 scoped PRs

Ordered by dependency; Wave A and Wave B can run in parallel worktrees.

### Wave A — Macro autoeval (Tier 1)

#### PR-A1: fix(autoeval-macro): honest as-of semantics + safe vault path + retry [~250 LOC]

**Why:** The scaffold grades wall-clock runs against historical rubric dates. Until as-of is honest, the grade signal is meaningless on any non-today date.

**Changes:**
1. `evaluate_macro.py::run_macro_agent` — set `FLOWTRACK_AS_OF=<as_of_date>` in child env (mirrors backtest). Also set new `FLOWTRACK_MACRO_OUT_DIR=~/vault/macro/{as_of_date}` if we add that plumbing (see step 3); otherwise use a tmp dir per-run to avoid polluting `~/vault/stocks/NIFTY/reports/macro.md`.
3. `research/agent.py::run_single_agent` (macro path) — read `FLOWTRACK_MACRO_OUT_DIR` with fallback to current behavior. Default keeps backwards compat; harness opts in.
4. `fetch_anchor_catalog()` — accept `as_of_date` arg and filter anchors to `publication_date <= as_of_date` OR flag if `get_macro_catalog` doesn't support date filtering (inspect `data_api.get_macro_catalog` signature; if no date param, fetch all and post-filter on `publication_date <= as_of`; emit a WARN in that branch so we don't silently skew).
5. Retry: wrap `run_macro_agent` subprocess in a 2-attempt retry with 30s back-off; mirror `evaluate.py`'s pattern. Gemini query in `eval_macro_report` — 2 retries on `asyncio.TimeoutError` / network exception.
6. `eval_history/` archival: on each date, dump `AgentEvalResult` + run metadata (as_of, anchors, report hash) to `eval_history/macro_{YYYY-MM-DD_HH-MM}.json`. Mirrors `evaluate.py::_archive_eval_run`.
7. Drop `--cycle` (unused), replace with `--note` free-form string written into the archive.

**Tests (~80 LOC):**
- `tests/unit/test_autoeval_macro.py`:
  - `fetch_anchor_catalog(as_of)` filters correctly given a mocked `get_macro_catalog` response with mixed `publication_date`s.
  - `run_macro_agent` passes `FLOWTRACK_AS_OF` to child env (monkeypatch `subprocess.Popen`, capture `env` kwarg).
  - `eval_macro_report` returns `grade=ERR` on Gemini JSON parse failure.
- `tests/integration/test_macro_out_dir.py`: run macro agent with `FLOWTRACK_MACRO_OUT_DIR=tmp`, assert report lands at `tmp/macro.md`, assert `~/vault/stocks/NIFTY/reports/macro.md` untouched.

**Verify:** `uv run python flowtracker/research/autoeval/evaluate_macro.py --dates 2026-03-15` succeeds. Anchor list in captured Gemini payload excludes any anchor with `publication_date > 2026-03-15`. `results_macro.tsv` appends one row.

**Fixes:** §1.1.1, §1.1.2, §1.1.4, §1.1.5, §1.3.

---

#### PR-A2: feat(autoeval-macro): CLI + progress + matrix expansion [~180 LOC]

**Why:** Scaffold is invocable only via raw Python; progress tooling ignores macro TSV; matrix is 4 dates vs plan's 4–6.

**Changes:**
1. `research_commands.py` — new Typer command `flowtrack research autoeval-macro` with flags `--dates`, `--skip-run`, `--note`. Dispatches to `evaluate_macro.main()`.
2. `autoeval/progress.py` — detect `results_macro.tsv` alongside `results.tsv`. Render a second block: "Macro eval — last N dates, pass/fail vs A- target".
3. `eval_matrix_macro.yaml` — add two dates: `2026-04-15` (post-April MPR) and `2026-04-22` (quarterly-results earnings-season peak). Total 6.
4. `autoeval/README.md` — new section "Macro autoeval" with usage + rubric summary.

**Tests (~40 LOC):**
- `tests/unit/test_smoke.py` — add `research autoeval-macro --help`.
- `tests/unit/test_progress.py` — assert macro block renders when `results_macro.tsv` present.

**Verify:** `uv run flowtrack research autoeval-macro --help` prints. `uv run flowtrack research autoeval --progress` shows macro block if TSV has rows.

**Fixes:** §1.1.3 partial (surfaces rot-detection), gaps in §1.3.

---

#### PR-A3: ops(autoeval-macro): monthly cron + run-log rotation [~80 LOC]

**Why:** No cadence means no feedback loop. Run once after the RBI MPR, once mid-month.

**Changes:**
1. `flow-tracker/scripts/monthly-macro-eval.sh` — runs `uv run flowtrack research autoeval-macro --dates <last-3-matrix-dates>` (last-3 rolling window, not the full matrix). Writes log to `~/.local/share/flowtracker/logs/monthly-macro-eval-YYYY-MM.log`, rotates monthly.
2. `scripts/plists/com.flowtracker.monthly-macro-eval.plist` — LaunchAgent, 14:00 IST on the 2nd and 17th of each month.
3. `scripts/setup-crons.sh` — register it.
4. `scripts/alerts/` directory + marker-file pattern per remediation-plan #19: on failure write `~/.local/share/flowtracker/alerts/monthly-macro-eval.failed`.

**Tests:** none (ops).

**Verify:** `launchctl list | grep monthly-macro-eval` shows the agent. Manual trigger: `launchctl start com.flowtracker.monthly-macro-eval`.

**Note:** cron-dependent. If remediation-plan PR-7 (plist templating + alert infra) is landing in parallel, sync with that PR author — the alert marker pattern should be shared. If PR-7 is not yet merged, use a local `.failed` file and migrate when PR-7 lands.

**Fixes:** cadence gap.

---

### Wave B — Historical Analog backtest (Tier 2)

#### PR-B1: feat(analog-backtest): zero-leakage integration test [~150 LOC]

**Why:** Plan exit criterion §3.3 requires a leakage test; scaffold only has a docstring.

**Approach:** Monkeypatch `ResearchDataAPI` and `FlowStore` methods to raise on any read with `date > as_of_date`. Call `compute_feature_vector(SYMBOL, as_of=2020-Q1)`. Assert no raise. Iterate through every `data_api` method the agent touches; hard-fail list of tainted accesses.

**Changes:**
1. `tests/integration/test_analog_zero_leakage.py` — new file. Uses a real `FlowStore(tmp_db)` populated with 3 years of daily-stock-data for one symbol, half of which is pre-2020, half post. Instrument `_conn.execute` with a decorator that inspects bound SQL params and raises if any date param > `as_of_date`.
2. `analog_builder.py` — if the test surfaces leakage, add minimal bounds: explicit `date <= :as_of` in queries where the as-of wasn't bound. (This is exploratory; cap at 2 fixes or escalate per Rule 2.)
3. Mark the test `-m slow` so it doesn't gate the fast suite.

**Tests:** the test itself is the deliverable. Separately, add a unit test for any new bound (if fixes needed).

**Verify:** `uv run pytest tests/integration/test_analog_zero_leakage.py -v` passes.

**Fixes:** §1.2.1.

---

#### PR-B2: fix(analog-backtest): safe vault path + cohort audit columns + sampler fix [~200 LOC]

**Why:** Current backtest overwrites live briefings at `~/vault/stocks/{symbol}/briefings/…`; quartile ground truth is read from potentially drifted briefings; sampler is `O(n²)` and `datetime.utcnow()` is deprecated.

**Changes:**
1. `backtest_historical_analog.py::run_analog_agent_as_of` — set `FLOWTRACK_BACKTEST_OUT_DIR=~/.local/share/flowtracker/backtest/{as_of}/{symbol}` in child env.
2. `research/agent.py` / `research/briefing.py` — read `FLOWTRACK_BACKTEST_OUT_DIR` for briefing save path when set. Default unchanged.
3. `load_briefing(symbol, as_of)` — read from the backtest dir when env set, else legacy path.
4. TSV schema: add `cohort_n`, `cohort_p25_12m`, `cohort_p75_12m`, `relaxation_level` columns. Snapshot from briefing at scoring time; lets us audit whether quartile drift is a real concern.
5. Sampler: replace `row not in sample` (`O(n²)`) with a set of `(symbol, as_of_date)` tuples.
6. Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.
7. `--skip-run` — if no briefing found, fail with clear message naming the expected path.

**Tests (~80 LOC):**
- `test_analog_backtest.py::test_stratified_sampler_no_dup` — N=50 with a 200-row population.
- `test_analog_backtest.py::test_score_sample_records_cohort_stats` — a fixture briefing, assert TSV row has `cohort_n` matching `len(top_analogs)`.
- `test_analog_backtest.py::test_backtest_out_dir_isolation` — run one sample, assert `~/vault/stocks/SBIN/briefings/historical_analog.json` is untouched when `FLOWTRACK_BACKTEST_OUT_DIR` is set.

**Verify:** `uv run python flowtracker/research/autoeval/backtest_historical_analog.py --n 3 --seed 7` completes without touching `~/vault/stocks/.../briefings/`.

**Fixes:** §1.2.2, §1.2.3, §1.2.4, §1.2.5.

---

#### PR-B3: feat(analog-backtest): CLI + run 20-sample baseline + eval_history archive [~170 LOC]

**Why:** Produce the first numbers — calibration hit rates — and make the run repeatable via CLI.

**Changes:**
1. `research_commands.py` — new Typer command `flowtrack research analog-backtest` with flags `--n`, `--seed`, `--skip-run`, `--cutoff-days`, `--note`. Dispatches to `backtest_historical_analog.main()`.
2. `backtest_historical_analog.py` — on completion, dump run metadata + samples + calibration summary to `eval_history/analog_backtest_{YYYY-MM-DD_HH-MM}.json`.
3. README section "Analog backtest" with (a) how to run, (b) how to interpret calibration thresholds, (c) monthly cadence recommendation.
4. Tier 3 deferral marker: add `# TODO Tier 3 synthesis eval — deferred, see plans/historical-analog-and-fo-agents.md §3.2` to the top of `eval_matrix.yaml`.

**Execute (not code, but part of the PR):**
5. Run `uv run flowtrack research analog-backtest --n 20 --seed 42 --note "baseline-post-scaffolds"`. Confirm:
   - Wall-clock < 3 hours (20 samples × ~5 min each).
   - Calibration summary printed.
   - `eval_history/analog_backtest_*.json` + `backtest_results_analog.tsv` produced.
6. Commit the summary to `autoeval/changelog.md` — NOT the artifacts themselves (remediation-plan PR-6 excludes them from git).

**Tests (~30 LOC):**
- `tests/unit/test_smoke.py` — add `research analog-backtest --help`.

**Verify:** CLI help prints. Baseline run completes. Calibration summary lists ≥3 direction/tail keys (so we have signal, not all-Unchanged calls).

**Fixes:** CLI gap, ops gap, deferral marker.

---

## 4. Dependency graph

```
A1 ──▶ A2 ──▶ A3
              (A3 soft-depends on rem-plan PR-7 plist templating; fallback to local)
B1 ──▶ B2 ──▶ B3
              (B3 requires B2 so 20-sample run doesn't overwrite live briefings)
A-wave and B-wave are independent — different files, different rubrics, different agents.
```

**Parallelizable:** A1 || B1 || B2 (three worktrees). A2 blocks on A1 completion (same file region). A3 blocks on A2. B3 blocks on B2.

---

## 5. Exit criteria (restated from plan §3.3 + tightened)

### Tier 1 Macro
- [ ] `results_macro.tsv` has ≥6 graded entries spanning 2025-11-01 → 2026-04-22.
- [ ] Every row has `grade` ∈ {A+…F} (not ERR).
- [ ] Anchor-exhaustion rubric injection is filtered by `publication_date <= as_of`, verified in a unit test.
- [ ] At least one regression observed (grade_numeric variance across matrix > 3 points) — if every date scores identical, something is stuck.
- [ ] Monthly cron registered; one successful fired run captured in `logs/`.
- [ ] `progress.py` displays macro block.

### Tier 2 Backtest
- [ ] Zero-leakage integration test passes under `-m slow`.
- [ ] N=20 baseline run completes without overwriting any `~/vault/stocks/*/briefings/historical_analog.json`.
- [ ] Calibration summary has ≥3 non-empty (tail, direction) keys with n≥3 each.
- [ ] For at least one direction, calibration hit rate is meaningfully off chance (≥5 pts from 0.25) so we know the signal isn't noise.
- [ ] `eval_history/analog_backtest_*.json` persisted.
- [ ] CLI `flowtrack research analog-backtest --help` documented in README.

### Deferred (acknowledged)
- [ ] Tier 3 synthesis eval: `# TODO` marker committed in `eval_matrix.yaml`.
- [ ] Tier 4 F&O eval: folds into Sprint 3.

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Macro agent CLI fails silently under `FLOWTRACK_AS_OF=<past>` because a downstream tool reads wall-clock | Smoke test A1: run once with `FLOWTRACK_AS_OF=2025-11-01`, inspect macro report for any "today = 2026-04-…" leakage. Grep `_build_temporal_context` consumers. |
| `analog_forward_returns` cohort quartiles drift from live `top_analogs` after relaxation-tier changes | B2 snapshots cohort stats at score time; if drift is meaningful we move to reading cohort from `historical_states` directly in a follow-up. |
| 20-sample calibration is too thin to be statistically meaningful | Plan accepts this — Tier 2 is "does the agent output correlate with reality at all", not "is the correlation 5σ". Follow-up can scale to N=100 monthly. |
| Gemini rate-limit / 503 mid-run | A1 retry + `--skip-run` recovery path (per feedback memory: batch `--skip-run` after outage). |
| Running 20 backtest agents overwrites cache and costs ~$8 total | Acceptable; $0.40/run × 20 = $8. Budget flagged in PR-B3 description. |
| Researcher's vault briefings get shadowed during a concurrent backtest | B2's `FLOWTRACK_BACKTEST_OUT_DIR` isolation; backtest docs advise not running alongside live `research thesis`. |

---

## 7. Effort estimate

| PR | LOC | Agent-work |
|---|---|---|
| A1 as-of fix | ~250 | 0.6 day |
| A2 CLI + progress + matrix | ~180 | 0.4 day |
| A3 cron | ~80 | 0.2 day |
| B1 leakage test | ~150 | 0.5 day |
| B2 safe path + cohort + sampler | ~200 | 0.5 day |
| B3 CLI + run + archive | ~170 + run | 0.8 day (incl. live baseline execution) |
| **Total** | **~1030** | **~3 days** agent-time + wall-clock for the live 20-sample run |

Matches plan §3.4 budget (~3 days Tier 1 + Tier 2).

---

## 8. Execution plan — suggested order

1. **Day 1 morning:** dispatch A1 + B1 + B2 into three worktrees in parallel.
2. **Day 1 afternoon:** review subagent output, land A1 and B1 and B2 (verify tests locally first).
3. **Day 2 morning:** A2 + B3 in parallel (different files).
4. **Day 2 afternoon:** land A2. Start the N=20 backtest run in tmux from the B3 worktree. Move to A3 while it runs.
5. **Day 3 morning:** land A3 + B3 (baseline now captured). Final verification sweep: macro matrix run of 6 dates, progress output, calibration summary screenshot into changelog.

Worktree paths (per CLAUDE.md rule 6):
- `equity-research-macro-eval-asof` — A1
- `equity-research-macro-eval-cli` — A2 (branches from A1)
- `equity-research-macro-eval-cron` — A3
- `equity-research-analog-leak-test` — B1
- `equity-research-analog-backtest-safe` — B2
- `equity-research-analog-backtest-cli` — B3

---

## 9. What NOT to do in this plan

- Do not touch `evaluate.py` except to add named exports. It is IMMUTABLE by convention (line 4 docstring).
- Do not re-materialize `historical_states` as part of this work. If the leakage test in B1 demands feature re-compute, that's a follow-up PR with its own regression sweep (plan §3 "production DB has 17,701 materialized state rows — re-materialize only if feature-vector logic changes").
- Do not bundle Tier 3 synthesis eval. Marker-only.
- Do not commit eval artifacts to git. `eval_history/` and `results_macro.tsv` must be git-ignored per remediation-plan PR-6.
- Do not reuse `COMPOSE_PROJECT_NAME` across worktrees (CLAUDE.md rule 6).

---

## 10. Open questions

1. **Macro out-dir plumbing:** does `agent.py::_run_specialist` have a clean hook for output path, or will A1 need to pass a param through `run_all_agents` → `_run_specialist` → assembly? If the latter, A1 might balloon past 500 LOC — consider splitting the plumbing into its own PR-A0.
2. **Cohort drift in B2:** reading 12m returns from `historical_states` directly would be cleaner than from `top_analogs` in the briefing. Should B2 do that now, or defer? Defer — keep B2 within 200 LOC.
3. **N for baseline backtest:** plan says 20; is the cost ($8) acceptable for an initial signal read? Confirm with user before B3 runs live.
4. **Calibration thresholds in the backtest (0.35 / 0.15):** are they the right calls for a first baseline, or too strict given cohort size variance? Keep as-is; first run tells us whether to loosen.

---

## Next-session resume card

**Start here:** PR-A1 (macro as-of honesty) + PR-B1 (leakage test). These are the two PRs that make the rest of the work trustworthy.

**Quick win path:** if bandwidth is tight and you just want to see a number, skip A1/A3 and ship B2+B3 only. The backtest gives hard calibration signal; macro eval without A1's as-of fix still produces a grade but the grade is suspect at any non-today date.

**Do not start Sprint 3 before:** this plan ships. Sprint 3's autoeval slot (§2.12 F&O-eligible sector sweep) is the fourth Tier; it should reuse the patterns landed here (archive, progress integration, CLI, cron).
