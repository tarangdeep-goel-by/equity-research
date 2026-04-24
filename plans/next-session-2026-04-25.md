# Next session — 2026-04-25 (or later)

Ranked by payoff, not order. Written 2026-04-24 after shipping 18 PRs (#82–#99) that cleaned the concall vault (89% → 99.7%), expanded the sector-KPI schema 14→20 sectors / ~134→222 KPIs per Gemini 3.1 Pro institutional review, and re-extracted the 11-symbol eval cohort with the new schema. Context: see `plans/remediation-plan-post-review-2026-04-24.md` + today's 2026-04-24 daily.

## 🔥 Highest ROI — re-grade the eval cohort

**Run autoeval against the new 222-KPI schema to measure the lift.** Every piece of today's work was plumbing; this is where you find out whether it moved the needle.

```bash
cd flow-tracker

# Priority sectors (where we added the most tier-2 KPIs)
uv run flowtrack research autoeval -a business --sectors bfsi fmcg pharma telecom

# Or full matrix in tmux
tmux new -s eval-v3 -d
tmux send-keys -t eval-v3 "cd flow-tracker && uv run flowtrack research autoeval" Enter
```

**Baseline to beat: 57% PASS** (2026-04-21 re-eval).

**Hypothesis:** clean concalls (PR #95/#96) + expanded sector KPIs (PR #97–99) + alias normalization should push several previously-failing stocks (HUL / AXISBANK / BHARTIARTL) into PASS on sector-specific evidence they previously lacked.

If the re-eval result is:
- **≥65% PASS** → pivot to Sprint 3 (F&O Positioning agent — see below)
- **57–65%** → inspect the still-failing pairs; cherry-pick from the L4 deferred list
- **<57%** → regression; run debug-escalation; compare new KPI population vs old to see if alias normalization is silently losing data

## 🧱 Build on today's work (small, high-signal)

1. **Wire alias normalization into `annual_report_extractor` + `deck_extractor`.** PR #99 only wired `canonicalize_operational_metrics` for concalls. AR and deck extractors have their own canonical lists but can suffer the same LLM-drift bug. Est: 1–2hr.
2. **Verify the 6 new sectors surface via `get_sector_kpis` MCP tool.** The tool may still hardcode the 14-sector list. Quick grep + test stock from each new sector: L&T (capital_goods), Apollo (hospitals), Trent (retail), HDFC AMC (amc_capital_markets), Havells (consumer_durables), Indigo (logistics).
3. **Investigate HINDUNILVR FY25-Q1 `0/13 [recovered]`.** Every other HUL quarter populated 10–16 KPIs; this one returned prose requiring JSON recovery and zeroed out. Is the PDF a lemon or did the extractor drift? Single-symbol single-quarter — 15-30 min to triage.
4. **Run `backfill_sector_kpis --force` on a broader cohort** (e.g. the 24 sectors where skill files exist) to populate data for synthesis + autoeval expansion beyond the 11-stock cohort.

## 📦 Wave 4/5 of remediation plan — needs green-light

From `plans/remediation-plan-post-review-2026-04-24.md`:

- **PR-12** — historical industry tracking + `FLOWTRACK_AS_OF` plumbing through `analog_builder` (~350 LOC, schema change to `historical_states`). Fixes the **industry-ID temporal drift** bug — currently `_industry()` returns current industry for historical quarter-ends, which leaks future classifications into analog cohort comparisons.
- **PR-13** — survivorship-aware universe + `delisted_symbols` + `unresolved_cliffs` reconciliation (~400 LOC, new tables). Fixes the **survivorship bias** in Historical Analog cohorts — current materialization selects from current `index_constituents` only, so cohort base rates systematically exclude delisted tickers (upward bias in forward returns).
- **PR-14** — E10 SOTP subsidiary discovery for newly-listed children (~250 LOC). HDBFS/NTPCGREEN-style recent listings never enter SOTP calcs.
- **PR-15** — `migrations/` dir + versioned schema + Screener chart invalidation on corp-action (~300 LOC). QoL/hardening.

**Priority order:** PR-12 + PR-13 are the highest-value pair — they fix correctness bugs in the analog base rates synthesis relies on. Do these if the re-eval shows synthesis-level failures. PR-14/15 are QoL; can defer.

## 🏗️ Long-parked

- **Sprint 3 — F&O Positioning Agent** (per `plans/historical-analog-and-fo-agents.md` Part 2): ~4 days. 5 MCP tools + agent prompt + `_SYNTHESIS_FIELDS` additions + autoeval F&O-eligible sector sweep. Data layer is in place from Sprint 2 (PR #78); all that's needed is wiring. Start in worktree `../equity-research-fno-agent`.
- **L4 tight fixes from post-eval v2** — 6 deferred agent-sector pairs (VEDL valuation, GODREJPROP valuation, technical/GODREJPROP, valuation/ETERNAL, risk/POLICYBZR, financials/SBIN). Re-grade will tell you if L1/L2/L3 absorbed them; cherry-pick only what still fails on the new schema.

## 🧹 Cleanup / opportunistic

- **Concall backfill for the ~400 Screener-uncovered remaining symbols.** Most are the 31 always-broken symbols flagged in today's audit (AXISBANK, ADANIENT, JSWSTEEL, ABCAPITAL, LICHSGFIN, …). Options: scrape company websites directly (heavy), or accept they'll always SKIP via PR #92's guard (light).
- **Unit harmonization** — Gemini flagged `credit_cost_bps` (banks) vs `credit_cost_pct` (nbfcs). Left as-is today because they're legitimately different reporting conventions; revisit only if cross-sector financial comparison becomes an actual use case.
- **Latest-quarter concalls** — AXISBANK FY26-Q3 + several others have no concall PDF on disk; next `quarterly-filings.sh` cron cycle (25th of Feb/May/Aug/Nov) will pick them up.

## Checkpointed state at session handoff

- **Main:** `1f7d05f` (post-#99 merge)
- **Worktrees:** all cleaned up — only main + `equity-research-autoagent-pilot` remain
- **Local branches:** cleaned (all merge-deleted + `git branch -D`)
- **Task list:** all tasks #14–#17 completed
- **Vault concall state:** 4965 files, 99.7% valid
- **sector_kpis cache:** 40 new quarters, 11/11 eval cohort symbols populated with new 222-KPI schema, alias normalization active
- **Open PRs:** none
- **Dirty working tree on main:** watch for any uncommitted `CLAUDE.md` / `.gitignore` linter edits that auto-accumulate between sessions

## One-sentence orientation for future-you

> Today shipped 18 PRs that cleaned the data and grew the sector-KPI schema 1.6× with institutional-grade Indian-market coverage. The next session should run autoeval against that schema to measure the lift vs the 57% PASS baseline — if it clears the bar, pivot to Sprint 3 (F&O agent); if it doesn't, cherry-pick the L4 tight fixes the re-eval surfaces, or ship Wave 4 (PR-12/13) if the misses are at the synthesis / analog-base-rate layer.
