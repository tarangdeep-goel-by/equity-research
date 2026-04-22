# Post-Eval Fix Plan v3 — Infra + Content Cleanup Before Next Re-eval

**Created:** 2026-04-22
**Source:** 2026-04-22 re-eval (53-cell failing-pairs run) + follow-up investigation of SDK subprocess crashes
**Baseline:** 2026-04-22 raw eval → 25/53 PASS (47%); post-recovery → 26/53 (49%); vs 2026-04-20/21 baseline → 30/53 (57%). Plan v2's projected 76-83% was masked by 7 SDK crashes + 12 degraded AR sections.
**Purpose:** Ship the remaining infra + content fixes that plan v2's re-eval exposed, then re-run the 53-cell cohort to measure true plan-v2 content lift minus infrastructure noise.

---

## 0. What's Already Landed

**PR #71 (plan v2 — 2026-04-21 merged):** L1 tenets A1.1–A1.6, 7 L2 agent iterations, L3 sector tightening, E10/E11/E12/E13/E14/E15/E16 data-layer fixes, E17 assembly scratchpad guard, E4 FII fix, E7 ADR/GDR stub.

**PR #72 (2026-04-22 merged):** SDK subprocess hygiene:
- AR retry filter (catches bare `Exception` via `_ClaudeSubprocessCrash`)
- Subprocess isolation (`setting_sources=[]` + `plugins=[]` in all 5 extractor call sites)
- Agent-run retry (`_run_specialist` in `agent.py`)
- Docling heading detector body-text fallback (SUNPHARMA mdna: 447 → 99KB slice)
- A1.6 named-op examples
- ADR/GDR live-read (stub still used when AR doesn't populate)
- F&O gap xfail contract test

**Concurrent with PR #72:**
- `scripts/backfill_sector_kpis.py` re-run (11 symbols) — currently running in tmux
- Stuck-cell recovery (HDFCBANK/NTPC/VEDL valuations + SUNPHARMA sector) — running in tmux

---

## 1. The 2026-04-22 eval feedback — residual issue inventory

After excluding the 10 infra-class failures (7 SDK crashes + 3 Gemini grader ERRs), the content-feedback themes ranked by prevalence across non-crashed reports were:

| Theme | # flags | Addressed by plan v2? | Addressed by PR #72? | Plan v3 item |
|---|---:|---|---|---|
| Calculate-tool batching / turn count | 39 | §9 deferred | — | **B** (turn cap) |
| BFSI structured-KPI data gaps | 12 | E2.2 fallback wired | — | **J** (backfill with `--force`) |
| AR extraction degraded | 12 | — | heading+retry fixed | **C** (re-extract with cache invalidation) |
| Mandatory-tool not called | 13 | B2/B4/B6 tenets added | — | **A** (code-level enforcement) |
| Pharma USFDA / R&D gaps | 3 | E13 config added | — | **J** (backfill) |
| Named-op misuse (`pct_of` vs `expr`) | 2 | A1.6 abstract | A1.6 examples added | watch for recurrence |
| F&O derivatives data missing | 4 | B6 tenet | xfail contract only | **H** (NSE derivatives ingestion) |
| SOTP freshness (HDBFS, NTPCGREEN) | 2 | E10 partial | — | **E10 follow-up** |
| Yahoo peer-swap mismatch | 2 | B3 tenet | — | **G** (enforcement) |
| FMCG UVG / channel mix | 2 | E13 config | — | **J** (backfill) |
| ADR/GDR stub | 2 | E7 stub | live-read wired | **I** (AR schema) |
| Sector-inappropriate charts (ROCE for banks) | 1 | — | — | **E** (chart x-metric kwarg) |
| Real-estate NAV not estimated | 1 | — | — | **F** (NAV tool/formula) |
| Weight-reallocation still recurring | 1 | A1.5 | — | watch |
| CFO-for-BFSI recurrence | 1 | B4/L3 bfsi | — | watch |
| Hypothesis-validation missing | 1 | B3 hint | — | watch |
| Stringified JSON tool args | 1 | — | — | **D** (tool-layer fix) |
| Tool-registry hallucination (`get_fundamentals` on platform valuation) | 1 | A1.6 | — | watch |

**Net interpretation.** Most of plan v2's content tenets DID land but three classes dominate residual failures: (1) unpopulated structured data (fixable by backfill + re-extract), (2) agents not obeying "MUST call X" prompts (fixable by code-level enforcement), (3) infrastructure gaps (F&O, NAV, charts).

---

## 2. Plan v3 — 12 items, grouped by theme

### Theme 1 — Data layer completion (highest ROI)

**J. KPI backfill with `--force` flag**
- `scripts/backfill_sector_kpis.py` currently skips cached concalls (`ensure_concall_data` completeness gate).
- Add `--force` kwarg to re-run extraction with the updated E13 config (pharma R&D, FMCG UVG, telecom ARPU).
- Target cohort: 11 eval-cohort symbols × last 4 concalls.
- **Scope:** ~30 lines in the backfill driver + 1 kwarg in `ensure_concall_data`.
- **Expected lift:** 5–8 eval cells (BFSI asset-quality + pharma R&D + FMCG UVG).

**C. AR cache selective invalidation + re-extract**
- Find all `~/vault/stocks/*/fundamentals/annual_report_FY*.json` where `_meta.missing_sections` is non-empty.
- Delete those files; re-run `ensure_annual_report_data` for the 11 eval symbols on the last 2 FYs.
- With the heading detector fix + retry logic from PR #72, these should re-extract cleanly.
- **Scope:** 1 script, ~30 lines; ~45 min wall-clock for 22 AR files.
- **Expected lift:** 8–12 eval cells (removes "AR degraded" flags + enables previously-empty sections).

**I. AR extractor schema update for ADR/GDR**
- PR #72 wired `get_adr_gdr` to read from `notes_to_financials`, but the AR extractor's `_SECTION_PROMPTS["notes_to_financials"]` doesn't surface ADR/GDR fields today.
- Add to the schema: `"adr_gdr_outstanding": {"units_mn": <number>, "listed_on": [...], "pct_of_total_equity": <number>}`.
- Update the extraction prompt to look for "depositary", "ADR", "GDR", "American Depositary".
- **Scope:** ~15 lines in `annual_report_extractor.py::_SECTION_PROMPTS["notes_to_financials"]`.
- **Expected lift:** 1–2 cells (HDFCBANK ownership, TCS ownership).

**H. F&O derivatives ingestion (bigger scope)**
- Task #17 produced an xfail contract test in `test_research_tools.py`. Follow-up scope outlined there: ~500–700 lines.
- New `flowtracker/derivatives_client.py` (NSE option-chain + quote-derivative endpoints, cookie handshake).
- New `derivatives_snapshot` + `fo_universe` tables in `store.py`.
- New Pydantic model `DerivativesSnapshot` in `derivatives_models.py`.
- Wire into `data_api.get_technical_indicators(symbol)` so `fo_enabled + pcr + open_interest + rollover_pct` are populated.
- Monthly cron to refresh `fo_universe` from `https://archives.nseindia.com/content/fo/fo_mktlots.csv`.
- Daily cron (post-bhavcopy, ~19:00 IST) to refresh derivatives snapshots for F&O symbols.
- **Scope:** 5–6 files, ~600 lines, full day of work.
- **Expected lift:** 3–4 cells (technical agent F&O compliance for HDFCBANK/GODREJPROP/ETERNAL/NTPC).

### Theme 2 — Agent enforcement

**A. Mandatory-tool post-run verifier**
- Current state: prompt says "MUST call `get_estimates(revisions)`" / "MUST call `get_company_context(sector_kpis)`". Agents skip anyway.
- Build a post-run verifier that:
  1. Parses the agent's actual tool-call log (already captured in `traces/`).
  2. Checks against a `MANDATORY_TOOLS_BY_AGENT_SECTOR` registry — per (agent, sector) tuple, what tools MUST appear.
  3. If any missing → return `WorkflowViolation(missing_tools=[...])`.
- Extension: on violation, trigger a targeted 2nd pass that invokes the missed tools and re-writes the affected section.
- **Scope:** ~150 lines (new `research/workflow_verifier.py` + registry + integration hook in `agent.py`).
- **Expected lift:** 10–13 cells (most "mandatory-tool not called" flags).

**G. Peer-swap enforcement**
- Same mechanism as A but targeted: when `get_yahoo_peers` returns > 50% sector-mismatch, verify `get_screener_peers` appears in the tool-call log. If not → workflow violation + 2nd-pass retry.
- **Scope:** ~40 lines (one entry in the registry + a similarity-check helper).
- **Expected lift:** 2–3 cells.

**B. Turn cap + sequential-calculate warning**
- Set `max_turns=25` on valuation/financials/business (SDK hard cap via `ClaudeAgentOptions`).
- Add a tool-layer hook: when `calculate` is called 3× within 30s with overlapping args, inject a warning into the next tool result: `"⚠ You made 3 sequential calculate calls with overlapping args — batch in a single assistant turn next time."`
- Opinionated change; risk of cutting off legitimate dependency-chain calcs. Ship behind a feature flag and A/B on one eval cycle.
- **Scope:** ~30 lines across `agent.py` + `tools.py::calculate`.
- **Expected lift:** ambiguous. Could be +3 to -5 cells depending on how agents react.

### Theme 3 — Content / tool-layer fixes

**D. Stringified-JSON tool args tolerance**
- Flagged once: `'["mf_changes", "insider"]'` passed as string instead of list to a `section=[...]` argument.
- Tool-layer fix: `section` args that are strings starting with `[` should `json.loads`; callers that pass real lists work as before.
- **Scope:** ~10 lines in `tools.py` (helper in MCP dispatcher).
- **Expected lift:** 0–1 cells (minor).

**E. Sector-appropriate chart x-metrics**
- `sector_valuation_scatter` hardcodes ROCE on x-axis. Banks don't have meaningful ROCE.
- Add `x_metric` kwarg to `render_chart(chart_type='sector_valuation_scatter')`. Default ROCE; override via sector skill (`bfsi/_shared.md` → `x_metric='roa_pct'`).
- Sector skills need a new field `preferred_chart_x_metric: <field>` that the sector agent reads and passes.
- **Scope:** ~40 lines across `charts.py` + 24 sector skill files (one-line addition each).
- **Expected lift:** 1–2 cells.

**F. Real-estate NAV tool/formula**
- Flagged on sector/real_estate: "Agent correctly identifies P/Adjusted-Book-Value as primary anchor but only analyzes stated P/B without estimating NAV."
- Option 1 (formula in sector skill): `nav_est = equity + undisclosed_land_mtm − debt_premium`, with each input sourced from existing tools.
- Option 2 (new tool): `get_nav_estimate(symbol)` computes it server-side.
- Preferred: Option 1 (sector skill) since it's sector-specific and cheaper.
- **Scope:** ~20 lines in `real_estate/_shared.md` + worked example.
- **Expected lift:** 1–2 cells (sector/business agents for real-estate names).

### Theme 4 — Valuation-agent polish (the stubborn 6/10)

**L. Valuation self-audit pass**
- Valuation fails 6/10 cells even post-recovery. Pattern: B+ (87-89) near-misses share recurring issues — weight reallocation drift, basis mixing, incomplete SOTP.
- Ship a lightweight self-audit: after valuation agent emits its draft, a cheap haiku pass re-reads the draft with a focused audit prompt: "Check (a) every PE/P-B citation names its basis, (b) any blended FV has a visible audit line if adjusted, (c) SOTP tables cover all disclosed subsidiaries, (d) no ghost numbers." Returns patches or approval.
- **Scope:** ~80 lines (new `research/valuation_audit.py` + integration in `agent.py::_run_specialist` for valuation only).
- **Expected lift:** 3–5 cells (biggest near-term lift on B+ near-misses).

### Theme 5 — Eval-layer

**K. Full 53-cell re-eval post all plan-v3 fixes**
- Once A, C, G, I, J, L land (minimum), re-run `eval-failing-pairs.sh`.
- Projected PASS rate: 35–40 / 53 (66-75%), approaching plan v2's original 76-83% projection.
- If F&O (H) lands as well: +2-3 cells.
- **Scope:** zero code; ~5hr wall-clock + caffeinate.

---

## 3. Execution order (priority by lift-per-effort)

| # | Item | Effort | Blast radius | Expected lift | Why this order |
|---|---|---|---|---:|---|
| 1 | **J** backfill `--force` | 30 min code + 3hr run | 15+ data gaps | 5–8 cells | Zero risk; unlocks other items |
| 2 | **C** AR cache invalidate + re-extract | 30 min code + 45 min run | 12 AR degradations | 8–12 cells | Zero risk; highest single-item lift |
| 3 | **I** AR schema ADR/GDR update | 15 min | 2 cells | 1–2 cells | Tiny; finishes task #16 properly |
| 4 | **L** valuation audit pass | 4 hr | 6 B+ cells | 3–5 cells | Biggest near-term valuation lift |
| 5 | **A + G** mandatory-tool verifier | 1 day | 13+ enforcement flags | 10–13 cells | Highest content lift but needs careful design |
| 6 | **K1** mid-cycle re-eval | 5 hr wall | measure | — | Checkpoint after items 1-5 |
| 7 | **E** chart x-metric | 2 hr | 1 cell | 1 cell | Small but worth doing |
| 8 | **F** real-estate NAV | 2 hr | 2 cells | 1–2 cells | Small sector-specific |
| 9 | **D** stringified-JSON tolerance | 30 min | 1 cell | 0–1 cells | Low priority |
| 10 | **H** F&O derivatives ingestion | 1 day | 4 cells | 3–4 cells | Medium; standalone effort |
| 11 | **B** turn cap + calc warning | 2 hr | risk | +3 to -5 | Opinionated; ship behind flag |
| 12 | **K2** final re-eval post-H | 5 hr wall | measure | — | Close the loop |

**Target cumulative PASS rate after plan v3:**

- After items 1–5: ~35/53 = 66% (plan v2's low-end projection)
- After items 1–8: ~38/53 = 72%
- After all items including H: ~42/53 = 79% (original plan v2 high-end projection met)

---

## 4. Appendix — Known-but-deferred items

- **Dashboard/UI** (memory `project_dashboard.md`) — user wants web dashboard for flow tracker. Not eval-related; parallel track.
- **Turn-count < 50 is acceptable per plan v2 §9** — unless item B lands, don't chase the 39 batching flags as FAIL-cause.
- **Gemini grader variance at A-/B+ boundary** — structural noise; a valuation audit pass (L) + a re-eval with stable infra (K) should show cleaner signal.
- **L4 single-cell cherry-pick (task #12)** — deferred indefinitely. Plan v2 §6 said "expected to resolve via L1/L2/L3, no L4-only work needed". Re-evaluate after K1.

---

## 5. Success criteria

- Items 1–5 land: tests pass, KPI/AR caches repopulated, valuation audit visible in trace logs.
- Mid-cycle K1 re-eval: 32–38 / 53 PASS. If below 32, investigate before proceeding.
- Full re-eval K2 post-H: 38–42 / 53 PASS. Plan v3 concludes when we hit plan v2's original 76-83% projection.

---

## 6. Links

- [Plan v2 (2026-04-21)](post-eval-fix-plan-v2.md)
- PR #71 (plan v2 implementation, merged 2026-04-21)
- PR #72 (SDK hygiene + follow-ups, merged 2026-04-22)
- Eval artifacts: `/tmp/eval-master-20260422-024701/`
- Recovery artifacts: `/tmp/eval-v2-recovery-*.log`, `/tmp/eval-recover-v2-*.log`, `/tmp/kpi-backfill-v2-*.log`
