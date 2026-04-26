# Next session — after 2026-04-26 ops runs

Picks up where `next-session-2026-04-27.md` was executed today. Of the 5 held ops runs, #1, #2, #3 are done; #4 and #5 are running in tmux at session end (~17:15) and will land artifacts on disk regardless.

## Live tmux sessions still running at handoff

| Session | What | Output lands at |
|---|---|---|
| ~~`eval-fno`~~ | **KILLED at ~5/23 stocks** (SBIN, HDFCBANK, TCS, VEDL, ETERNAL completed) to save ~$2-3 API spend. Re-run next session: `tmux new -s eval-fno -d "cd flow-tracker && uv run flowtrack research autoeval -a fno_positioning"` — but **PR #131 must be merged first** (the fno_positioning CLI registry fix), or run off the `fix/fno-positioning-cli-registry` branch. 5 partial briefings preserved at `~/vault/stocks/{SBIN,HDFCBANK,TCS,VEDL,ETERNAL}/briefings/fno_positioning.md`. | (briefings only — no results.tsv rows yet) |
| ~~`analog-backtest`~~ | **KILLED at ~5/20 samples** to save ~$5-6 API spend. Re-run next session: `tmux new -s analog-backtest -d "cd flow-tracker && uv run flowtrack research analog-backtest --n 20 --seed 42 --note baseline-post-scaffolds"`. Partial briefings remain at `~/.local/share/flowtracker/backtest/` if you want a partial calibration via `--skip-run`. | (no artifacts written — backtest archives only at end-of-run) |

Reattach with `tmux a -t <session>`. Both will write final summaries to stdout when done; the F&O one prints an `AGENT SUMMARY` table, the backtest prints a `CALIBRATION SUMMARY` table.

## TODO — review the run outputs

When you're ready to look at results:

1. **F&O grades.** `cat flow-tracker/flowtracker/research/autoeval/results.tsv | grep fno_positioning` — look at grade per (sector, stock).
   - **A− or above across the matrix** → ship; F&O agent is operational
   - **<A− on subset** → prompt fix in `prompts.py::FNO_POSITIONING_*_V2` or sector-specific in `sector_skills/<sector>/fno_positioning.md`
2. **Backtest calibration.** `cat flow-tracker/flowtracker/research/autoeval/backtest_results_analog.tsv` + the eval_history JSON.
   - **Hit rate ≥ 5pp from chance (0.25) on any direction** → analog signal real → promote `directional_adjustments` to higher confidence weight in synthesis
   - **At chance** → tighten `analog_builder` distance metric / feature vector

## TODO — bugs surfaced by today's runs

1. **fno_positioning CLI registry** — fixed today, **PR #131 open**, awaiting your review/merge. 1-line addition to `VALID_AGENTS` in `flow-tracker/flowtracker/research_commands.py`. PR #108 (Sprint 3) had wired the agent through `agent.py` but missed the CLI whitelist; first real autoeval today exit-1'd all 23 stocks in <1s with "Unknown agent".

2. **`evaluate_macro.py:136` calls `api.get_macro_catalog()` — no such method on `ResearchDataAPI`.** Currently soft-fails with `[WARN] get_macro_catalog failed: 'ResearchDataAPI' object has no attribute 'get_macro_catalog'` and proceeds with empty anchor list (so anchor-exhaustion check can't be enforced). Fix: either add `get_macro_catalog(self) -> dict` to `ResearchDataAPI` that wraps `flowtracker.research.macro_anchors.list_current_anchors()`, OR change `evaluate_macro.py` to import `list_current_anchors` directly. The MCP tool `tools.py:get_macro_catalog` is the canonical implementation — mirror its 2-line body.

3. **Macro Gemini grading failed all 6 dates today.** Each macro agent run succeeded (35-46K char reports archived to `eval_history/macro_2026-04-26_*.json` + sha256), but `Gemini attempt 1/3 failed... 2/3 failed` on every grade with `Command failed with exit code 1`. Could be:
   - Gemini API outage (per memory `feedback_gemini_outage_recovery.md` — pattern matches)
   - Or a real bug in the Gemini prompt construction in `evaluate_macro.py`
   To re-grade after Gemini is healthy: `flowtrack research autoeval-macro --skip-run --note regrade-2026-04-XX` (if --skip-run path works for macro; verify in code first since this is the first time the run was held). The 6 reports are ready for re-grading without re-running the agents.

## Still-pending items from the original 2026-04-27 plan

Untouched today:
1. **Wire alias normalization into `annual_report_extractor` + `deck_extractor`** (PR #99 only did concalls). Est: 1-2hr.
2. **Verify `get_sector_kpis` MCP tool surfaces the 6 new sectors** (capital_goods, hospitals, retail, amc, durables, logistics). Quick grep + test stock from each: L&T, Apollo, Trent, HDFC AMC, Havells, Indigo. ~30min.
3. **Triage HINDUNILVR FY25-Q1 `0/13` zero-KPI quarter.** Single-symbol single-quarter; 15-30min.
4. **`backfill_sector_kpis --force` on broader cohort** (24 sectors with skill files vs the 11-stock cohort today).

Plus the long-parked items from that plan: PR-15 migrations refactor, Tier 3 synthesis eval, F&O Phase 2 (IV history surface + cross-stock cohort), `fno universe refresh` CSV format fix, L4 tight fixes from post-eval v2.

## New development backlog (added 2026-04-26 EOD)

Surfaced today as either gap-shaped lessons from the ops run or net-new product surface that's never been planned. Ranked by leverage.

### Quick / surgical (1-2hr each, dev hygiene)

1. **CI test asserting `VALID_AGENTS` covers every agent in the autoeval matrix.** Today's fno_positioning CLI registry bug (PR #131) would have failed CI instead of breaking a $5 ops run. Test: load `eval_matrix.yaml` agents list, intersect with `VALID_AGENTS` from `research_commands.py`, assert no gaps. Also assert every agent in `agent.py::AGENT_MODEL_MAP` is in both. ~15min.
2. **Set `PYTHONUNBUFFERED=1` in the `flowtrack` entry point** (or pass `python -u`). Today's "is the backtest hung?" investigation came from blocked stdout when piped through `tee` (Python defaults to block-buffered for non-tty stdout). Affects every long-running CLI command. ~5min.
3. **Fix `evaluate_macro.py::fetch_anchor_catalog` (line 132-139)** to call `flowtracker.research.macro_anchors.list_current_anchors()` directly, OR add a `get_macro_catalog(self) -> dict` method on `ResearchDataAPI` that wraps it. (Already in "TODO — bugs surfaced" above; restated here for completeness.) ~15min.

### Real new initiatives (never planned — need plan-mode session first)

4. **IPO pre-listing module.** Per memory `project_next_directions.md` this is flagged as the *primary* next direction but no plan file exists. Genuinely net-new product surface — DRHP/RHP parsing, anchor-investor extraction, peer benchmarking against the IPO's claimed comparables, GMP tracking, listing-day mechanics. Open question: which data sources are reliable for IPO calendar (NSE/BSE issue-list, Chittorgarh API, manual scraping). Ideal for a plan-mode session before any code lands.
5. **Web dashboard / UI.** Long-standing user wish (memory `project_dashboard.md`: "terminal tables hard to read"). Could be a thin Streamlit/FastAPI layer over `ResearchDataAPI` — no business logic moves, just presentation. The data layer (~150 methods, 50 tables) is already done. Open questions: read-only viewer vs. interactive workflows, single-tenant local server vs. served, charts via existing matplotlib outputs vs. plotly/recharts. Plan-mode candidate.

### Latent-but-known (already in plans, not done today)

6. **L4 tight fixes** from post-eval v2 — 6 specific deferred agent-sector pairs: VEDL valuation, GODREJPROP valuation, GODREJPROP technical, ETERNAL valuation, POLICYBZR risk, SBIN financials. Bounded, finite. Most likely already lifted by L1/L2/L3 + recent data-quality work — re-grade after F&O sweep tells you what actually still fails.
7. **Re-eval cycle 2** across all 11 agents × 16-stock matrix. ~12-15hr autoeval in tmux per the autoagent-pilot pattern. Refreshes the post-data-quality baseline; orthogonal to F&O & macro work. Run in tmux, walk away.
8. **Alias normalization for AR + deck extractors** (PR #99 only did concalls). Same canonical-list pattern, two more modules. Est 1-2hr. (Also listed under "still-pending from 2026-04-27" above; restated here under dev hygiene since the pattern is proven.)

## Checkpointed state at handoff

- **Branch:** `fix/fno-positioning-cli-registry` (NOT main). PR #131 open.
- **Untracked plan files:** `plans/eval-data-fixes-next-session.md`, `plans/screener-data-discontinuity.md`, `plans/next-session-2026-04-27.md` (today's plan, mostly executed), `plans/next-session-after-2026-04-26-ops.md` (this file).
- **Stale tmux sessions:** `ar-reextract4`, `autoagent-iter2`, `autoagent-regress`, `eval-recover`, `eval-v2`, `kpi-backfill` from prior days — kill on next session start with `tmux kill-session -t <name>`.
- **Parallel-session worktrees still reserved:** `equity-research-finish`, `wave1`, `wave2`, `wave45`. Stay clear.
- **Today's data backfills (DONE):** `historical_states.industry_as_of_date` populated for 17,898 rows; `delisted_symbols` has 454 rows; `unresolved_cliffs` has 1199 rows.

## One-sentence orientation

> Today fired the 5 held ops runs from `next-session-2026-04-27.md`; #1/#2/#3 finished cleanly, #4/#5 were stopped early to conserve API budget; pick up by re-running #4 + #5 (after merging PR #131), fixing the 3 quick dev-hygiene gaps surfaced today, then choosing between the IPO pre-listing module or web dashboard for net-new product work.
