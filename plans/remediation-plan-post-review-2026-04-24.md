# Remediation plan — post-review of PRs #65/#67/#70/#71/#78

**Date:** 2026-04-24
**Source:** Deep audit + verification pass of 5 anchor PRs from Sprint 0, Sprint 1, Sprint 2, and the big-plan v2 fixes.
**Constraint:** Every PR in this plan is ≤500 LOC (hard cap). If a scope can't fit, split it further. No eval artifacts in code PRs.

---

## 0. Corrections to the initial review

Re-verification against current `main` invalidated several of the original audit's "critical" findings. Recording so the fix plan doesn't chase ghosts:

| Claim | Status | Evidence |
|---|---|---|
| `p10/p90` off-by-one in `analog_builder.py:682` | **FALSE** — math is correct nearest-rank (1-based → 0-based via `-1`) | N=10: `int(0.1*10)-1=0` → `sorted_r[0]` = 1st order stat ✓ |
| `feature_distance` skip-on-None bias still active | **FALSE** — fixed in #75; callers always pass `medians` via `_industry_medians()` | `analog_builder.py:613` |
| `listed_days` / `is_backfilled` flag missing | **FALSE** — present in `compute_feature_vector()`, schema, and agent briefing | `analog_builder.py:313,343-344`; `store.py:773-774`; `prompts.py:1550` |
| Multi-tier fallback ring absent | **FALSE** — `retrieve_top_k_analogs` loops `_RELAXATION_TIERS` and stamps `relaxation_level` | `analog_builder.py:529-534,618,642` |
| E11 basis-mismatch detection has no tests | **FALSE** — tested at `test_data_api.py:800-817` + `819+` (mismatch + PE downrank) | `data_api.py:623,649,2663-2674` |
| A1.3 scratchpad guard is assembly-only | **FALSE** — prompt-side tenet at `prompts.py:225` + assembly guard at `assembly.py:29-62` |
| Sector `_shared.md` have only prose, no structured metric lists | **FALSE** — 7/7 inspected contain bulleted primary-metric lists |

**Implication:** The Sprint-1 Historical Analog stack (post #75 hardening) is in better shape than the first-pass review implied. Real problems lie elsewhere.

---

## 1. Confirmed issue inventory (post-verification)

### P0 — Correctness / data integrity
| # | Issue | File | Scope |
|---|---|---|---|
| 1 | OPTSTK row with empty `StrikePric` silently sets `strike=None`, maps to sentinel `-1`, causes `INSERT OR REPLACE` collision on PK | `fno_client.py:414-419` + `store.py:4507-4511` | Small |
| 2 | `adj_close` recompute hook fires on INSERT of `corporate_actions` but not on DELETE — rollbacks leave stale `adj_close` | `store.py:4062-4091` | Small |
| 3 | Survivorship bias in `historical_states` — universe drawn from current `index_constituents` only; delisted tickers excluded → upward bias in cohort base rates | `materialize_analog_states.py:45-54` | Medium |
| 4 | Industry-ID temporal drift — `_industry()` returns current industry for historical quarter-ends; analog comparisons mix reclassified tickers | `analog_builder.py:215-223` | Medium |
| 5 | Non-deterministic tie-break in cohort scoring — `scored.sort(key=distance)` preserves SQL iteration order on ties | `analog_builder.py:635` | Trivial |
| 6 | `adj_close` recompute composes compound actions via unordered SQL → audit log can show split+bonus in different order run-to-run | `store.py:4142-4149` | Trivial |
| 7 | Filing-client refiling silently returns stale non-zero-byte files; zero-byte triggers retry but corrupt/stale does not | `filing_client.py:419` | Small |
| 8 | Option-chain `strptime("%d-%b-%Y")` has no fallback; single NSE format change breaks live chain | `fno_client.py:291` | Trivial |

### P1 — Agent quality / prompt wiring
| # | Issue | File | Scope |
|---|---|---|---|
| 9 | E12 sector-aware D&A works at data-layer but **zero specialist prompts pass `industry=` when calling `get_financial_projections`** → always defaults to 2% | `prompts.py` (8 specialists) | Small |
| 10 | E13 sector_kpis backfill script exists but was never run for eval cohort → `get_sector_kpis()` empty for SUNPHARMA/BHARTIARTL/HINDUNILVR/ETERNAL/POLICYBZR etc. | `scripts/backfill_sector_kpis.py` | Operational |
| 11 | E10 SOTP subsidiary freshness — no `bhavcopy`/`index_constituents` discovery of newly-listed children (HDBFS, NTPCGREEN); manual SOTP is the only path | `data_api.py::get_valuation` | Medium |
| 12 | VEDL regression (scratchpad leak + commodity-framework mis-apply) documented in plan v2 §0 but **no regression test** ensures it can't recur | `tests/unit/test_assembly.py` | Small |
| 13 | `FLOWTRACK_AS_OF` plumbed for FNO only (Sprint 3 prep) — analog builder + materialization still read wall-clock; backtests contaminate | `materialize_analog_states.py:34`, `analog_builder.py` | Small |
| 14 | Participant OI parser assumes exactly 6 categories — NSE adding/removing a column silently zero-fills via `_parse_int` fallback | `fno_client.py:60-67,255` | Small |
| 15 | Backfill `--skip-existing` is day-level all-or-nothing — one failed symbol poisons the whole day for re-runs | `fno_commands.py:133-139` | Small |

### P2 — Operational / dev-experience
| # | Issue | File | Scope |
|---|---|---|---|
| 16 | 452 eval artifacts + run_logs committed to git; `.gitignore` has no autoeval patterns → every re-run bloats the diff | `.gitignore`, `autoeval/eval_history/*`, `autoeval/run_logs/*` | Trivial |
| 17 | LaunchAgent plists hardcode `/Users/tarang/...` in 8+ files — breaks on any other user | `flow-tracker/scripts/plists/*.plist` | Small |
| 18 | No `instrument` index on `fno_contracts` — "all FUTSTK" queries full-scan | `store.py:4512-4513` | Trivial |
| 19 | Cron scripts log `[FAIL]` after retry exhaustion but send no alert | `daily-fno.sh`, `nightly-adj-close.sh`, etc. | Small |
| 20 | Screener chart invalidation missing — cached charts remain pre-split after corporate action | `screener_client.py::fetch_chart_data_by_type`, `store.py::upsert_corporate_actions` | Small |
| 21 | Test fixtures hardcode 2026-04-17 / 2026-04-23 across 5+ files (`test_fno_*.py`, `test_deck_extractor.py`, `test_annual_report.py`) — will rot | relevant test files | Small |
| 22 | No migrations/rollback infrastructure; schema is created inline in `store.py` | `store.py::_ensure_schema` | Medium |
| 23 | Sprint 0 §0.11 parked symbols (LICMFGOLD, DELPHIFX, BESTAGRO, etc.) — no flag, no reconciliation, no test asserting intentional absence | new tool | Medium |
| 24 | `cron.log` grows unbounded; no rotation | shell scripts | Trivial |

### P3 — Lower priority / defer
| # | Issue | Reason to defer |
|---|---|---|
| 25 | `prompts.py` is 2387 LOC — refactor candidate | Risky without extensive tests; hold until prompts stabilize |
| 26 | No foreign keys on F&O tables | SQLite FK enforcement is off by default; low impact |
| 27 | Naive `datetime.now()` in `fno_client.py:328` (metadata only) | Not used for comparisons |
| 28 | MCAP bucket edge instability (₹4,999Cr vs ₹5,001Cr) | Tier 2 fallback absorbs flipping |
| 29 | Forward-return `±20%` inclusive boundary | Internally consistent; cosmetic |
| 30 | L4 tight fixes deferred from PR #71 (6 pairs) | Blocked on re-eval; may be absorbed by L1-L3 |

---

## 2. Execution plan — 14 scoped PRs

Each PR ≤500 LOC. Ordered by dependency + priority. Worktree per PR (per CLAUDE.md rule 6).

### Wave 1 — Correctness (P0, independent, can parallelize)

**PR-1: fix(fno): validate OPTSTK strike on bhavcopy ingestion** [~80 LOC]
- `fno_client.py:414-419`: raise `FnoFetchError` when `instrument == "OPTSTK"` and `StrkPric` empty; allow None for futures only.
- Add 3 tests: OPTSTK with empty strike raises; OPTSTK with valid strike parses; FUTSTK with empty strike still None.
- Fixes issue #1.

**PR-2: fix(store): adj_close hook fires on DELETE + UPDATE of corporate_actions** [~60 LOC]
- `store.py:4062-4091`: extend `_corporate_actions_sync_hook` to trigger on DELETE/UPDATE (capture affected symbol before DELETE).
- Add test: insert bonus, verify adj_close recomputed; delete bonus, verify adj_close reverted.
- Fixes issue #2.

**PR-3: fix(analog): deterministic tie-break in cohort ranking + compound-action ordering** [~30 LOC]
- `analog_builder.py:635`: `scored.sort(key=lambda r: (r["distance"], r["symbol"], r["as_of_date"]))`.
- `store.py:4142`: `ORDER BY ex_date, action_type` in `get_corporate_actions` fetch used for adj_close.
- Add test: two identical-distance analogs always return in (symbol, date) order across runs.
- Fixes issues #5, #6.

**PR-4: fix(filing_client): detect stale + corrupt cached filings; add refresh path** [~120 LOC]
- `filing_client.py:419`: log warning for files older than 30 days; add `force_refresh=False` kwarg to `download_filing`; treat files <1KB as suspect.
- Add 4 tests: existing fresh file returned; existing 30-day-old file warns; force_refresh re-downloads; <1KB triggers re-download.
- Fixes issue #7.

**PR-5: fix(fno): option-chain expiry format fallback + participant OI validation** [~70 LOC]
- `fno_client.py:291`: try `"%d-%b-%Y"`, fall back to `"%d-%b-%y"` and ISO; raise only if all fail.
- `fno_client.py:60-67,255`: validate column count against expected categories; log warning and skip row if mismatch.
- Add 2 tests: short-year format parses; extra participant column warned.
- Fixes issues #8, #14.

### Wave 2 — Operational cleanup (trivial gain, no dependencies)

**PR-6: chore: gitignore eval artifacts + purge from history going forward** [~20 LOC + delete]
- `.gitignore`: add `flow-tracker/flowtracker/research/autoeval/eval_history/*`, `flow-tracker/flowtracker/research/autoeval/run_logs/*`, `flow-tracker/flowtracker/research/autoeval/last_run.json`, `flow-tracker/flowtracker/research/autoeval/results.tsv`.
- `git rm --cached` the 452 artifact files. Keep an `eval_history/.gitkeep`.
- Document in `CLAUDE.md`: "Never commit eval outputs."
- Fixes issue #16.

**PR-7: chore(ops): templatize LaunchAgent plists + instrument index + cron alerts** [~150 LOC]
- `scripts/plists/*.plist.tmpl` + `scripts/install-launch-agents.sh` that substitutes `$HOME`.
- `store.py`: add `CREATE INDEX IF NOT EXISTS ix_fno_instrument ON fno_contracts(instrument)`.
- `scripts/*.sh`: on final-retry failure, write marker file `~/.local/share/flowtracker/alerts/<script>.failed` (consumable by separate alerting cron).
- Fixes issues #17, #18, #19.

**PR-8: chore(tests): freeze time via freezegun in date-sensitive fixtures** [~200 LOC]
- `pyproject.toml`: add `freezegun` dev-dep.
- Refactor hardcoded-date fixtures in `test_fno_*.py`, `test_deck_extractor.py`, `test_annual_report.py` to use `@freeze_time("2026-04-23")` or relative arithmetic.
- Fixes issue #21.

### Wave 3 — Agent prompt wiring (P1)

**PR-9: feat(agents): wire industry hint to get_financial_projections** [~180 LOC]
- For each of the 8 specialists that can call projections (Valuation, Financials, Business, Sector), add to their INSTRUCTIONS_V2:
  > "When calling `get_financial_projections`, resolve the company's industry via `get_company_context(symbol).industry` and pass `industry=<that token>`. Do not default — if industry is Unknown, say so in the report."
- Add test that asserts each prompt contains the rule.
- Fixes issue #9.

**PR-10: feat(regression): VEDL-style scratchpad + commodity-framework regression tests** [~120 LOC]
- `tests/unit/test_assembly.py`: add golden-file test that rejects report containing `<thinking>`, `[SCRATCH]`, `Let me think`, `Actually,`, `Wait —`.
- `tests/unit/test_prompts.py`: assert commodity-sector agents have explicit "use commodity framework, not DCF/PE" tenet in their V2 prompt (regression guard against VEDL misapply).
- Fixes issue #12.

**PR-11: chore(ops): run sector_kpis backfill for eval cohort + autoeval hook** [operational + ~50 LOC]
- Run: `uv run scripts/backfill_sector_kpis.py --symbols SUNPHARMA BHARTIARTL HINDUNILVR ETERNAL POLICYBZR VEDL SBIN HDFCBANK ADANIENT GODREJPROP INFY TCS` and commit the resulting vault data.
- Wire: add a guard in autoeval that `SKIP`s agents requiring sector_kpis if the cohort row is missing, printing a clear message so it's visible in logs.
- Fixes issue #10.

### Wave 4 — Temporal & survivorship (P0/P1 schema work)

**PR-12: feat(analog): historical industry tracking + FLOWTRACK_AS_OF plumbing** [~350 LOC]
- Schema: add `industry_as_of_date TEXT` column to `historical_states`; backfill from `index_constituents` history (or Screener archive) where available, current industry as fallback with `industry_source` flag.
- `analog_builder._industry()`: accept `as_of_date` parameter.
- `materialize_analog_states.py`: read `FLOWTRACK_AS_OF` env var, default `date.today()`.
- `analog_builder` forward-return computation: gate by `as_of_date` consistently.
- Tests: feature vector for 2018-Q1 uses 2018 industry classification (if historical data exists); env var override works.
- Fixes issues #4, #13.

**PR-13: feat(analog): survivorship-aware universe + parked-symbol flagging** [~400 LOC]
- `materialize_analog_states.py`: accept `--include-delisted` flag; query `daily_stock_data` for tickers with ≥ 3000 observations regardless of current index membership.
- New table `delisted_symbols(symbol, last_active_date, reason)` populated from daily_stock_data gaps > 180 days.
- Reconciliation script `scripts/reconcile_price_cliffs.py`: flag symbol-dates where |day-over-day return| > 40% AND no `corporate_actions` entry → writes to `unresolved_cliffs` table for manual triage.
- Test: 14 §0.11 symbols + 5 synthetic delisted tickers appear in delisted_symbols table.
- Fixes issues #3, #23.

### Wave 5 — Medium/longer items (P1/P2)

**PR-14: feat(valuation): E10 SOTP subsidiary discovery from recent listings** [~250 LOC]
- `data_api::get_valuation(section='sotp')`: augment subsidiary list with listings from `bhavcopy` in trailing 180 days where parent holds >50% (from shareholding data).
- Emit `subsidiary_freshness_meta` in output so agent can caveat if auto-SOTP is incomplete.
- Tests: mock a parent + recently-listed child, verify discovery.
- Fixes issue #11.

**PR-15: feat(ops): migrations/ directory + versioned schema + screener chart invalidation** [~300 LOC]
- `flow-tracker/flowtracker/migrations/`: move inline schema from `store.py::_ensure_schema` into numbered migration files (0001_base.sql, 0002_adj_close.sql, ... 00NN_current.sql). Keep `_ensure_schema` as migration-runner.
- `upsert_corporate_actions` hook: call `screener_client.invalidate_charts(symbol)` when action is split/bonus.
- Fixes issues #20, #22.

### P3 — Deferred

Items #25, #26, #27, #28, #29, #30 are tracked but not in this plan. Re-evaluate after Wave 4.

---

## 3. Dependency graph

```
Wave 1 (independent, parallel):    PR-1  PR-2  PR-3  PR-4  PR-5
Wave 2 (independent, parallel):    PR-6  PR-7  PR-8
Wave 3 (Wave 2 done):              PR-9  PR-10 PR-11
Wave 4 (Wave 1 done):              PR-12 → PR-13
Wave 5 (Wave 4 done):              PR-14 → PR-15
```

Waves 1+2 can ship same day (5 + 3 worktrees parallel). Total calendar estimate: **~3.5 working days** if dispatched properly.

---

## 4. Testing strategy

- Every PR follows TDD: failing test first, implementation second (CLAUDE.md rule 5).
- No mocked-database tests (feedback_testing memory): use real temp-SQLite fixture.
- No hardcoded dates in new tests: use `freezegun` from PR-8 onward.
- Each PR must pass `uv run pytest tests/ -m "not slow"` in < 30s before merge.
- After Wave 4 lands, re-run the post-eval v2 re-eval to measure lift. Only then claim "fixed."

---

## 5. Out-of-scope / parked for future cycles

- **Post-eval v3 work** (`post-eval-fix-plan-v3.md`) — separate track, not part of this remediation.
- **Sprint 3 F&O Positioning agent** — builds on PR #78 data layer; start once PR-1 + PR-5 + PR-7 land.
- **Scratchpad leak regression re-eval on VEDL** — needs a full re-run to prove fix; owner + schedule TBD.
- **prompts.py refactor** — park until prompts stabilize (post-re-eval).

---

## 6. Rules of engagement (enforce via CLAUDE.md update)

Add to `/Users/tarang/Documents/Projects/equity-research/CLAUDE.md`:

> **Never commit eval artifacts.** `eval_history/`, `run_logs/`, `results.tsv`, `last_run.json` are `.gitignore`d.
> **Hard cap on PR size: 500 LOC.** Exceptions require a written split-plan in the PR body.
> **One plan phase = one PR.** If a plan document names phases A/B/C, each phase ships separately.
> **No design-only fixes.** Every plan line item has a code change AND a test assertion, or it's not shipped.
> **No post-merge TODOs for operational work.** If a script must run, run it in the PR.
> **Regressions block merge.** VEDL B+ → F should have blocked PR #70. A regression is not a "next-PR" item.
