# Plan: Drive All Financials Sectors to A-

**Created:** 2026-04-14
**Owner:** equity-research/flow-tracker
**Goal:** Every sector × `financials` agent reaches A- (≥90 numeric) in autoeval
**Current state:** BFSI/SBIN + several sectors stuck at B+ (87-89); 8 sectors have no `financials.md` skill file at all

---

## Root Cause Analysis

Synthesized from 32 financials eval runs (2026-04-07 → 2026-04-09). Three root causes, **not one**:

| # | Root cause | Fix type | Leverage |
|---|---|---|---|
| **R1** | **Rules exist but aren't enforced.** 12 core tenets + 8 workflow steps + sector skill files already instruct the agent to exhaust tools before writing open questions. Agent bypasses them when tools return partial data. | Workflow restructure (compliance gate) | HIGH |
| **R2** | **Structural gaps.** 8 sectors lack `financials.md`. Conglomerate has a stub (14 lines). Eval matrix tests 3 of these → guaranteed under-grading. | Additive skill files | MED |
| **R3** | **Tool-layer friction.** BFSI CAGR table returns EBITDA (wrong for banks); asset quality (GNPA/NNPA) may not be in `concall_insights`; `expense_breakdown` may not surface R&D cleanly for pharma. | Data pipeline fix | HIGH for BFSI/pharma |

### Evidence of R1 (rules-exist-but-bypassed)

Prompts already contain:
- `FINANCIAL_SYSTEM_V2` Rule #8: *"Anomaly resolution — exhaust tools first. Call `get_company_context(concall_insights)`, `get_events_actions`, or `get_fundamentals(expense_breakdown)` before escalating to open questions."*
- Workflow step 8: *"Investigate before writing"* with good-vs-bad examples
- `bfsi/financials.md`: explicitly lists GNPA/NNPA/PCR/slippages/credit cost as mandatory
- `real_estate/financials.md`: pre-sales is the key metric
- `pharma/financials.md`: R&D ratio mandatory

Yet Gemini flags these same gaps repeatedly. → Problem is enforcement, not missing content.

### Cross-sector patterns observed (all 12 latest evals)

1. **"Open Questions" as an escape hatch** (5/12) — agent leaves historical anomalies unanswered when tools exist to resolve them
2. **Identifies problem, doesn't do the math** (5/12) — flags FY22 exceptional but doesn't compute adjusted CAGR
3. **Sector-specific mandatory metrics missing** (every sector — see table)
4. **Tool-call discipline lapses** (2/12) — missing param, truncated output → gives up instead of retrying

---

## Phase 0 · Diagnose (1 eval cycle, no prompt changes)

**Goal:** Stop guessing. See what's actually in the agent's tool outputs for 3 failing cases.

- Re-run `financials` on SBIN (BFSI), SUNPHARMA (pharma), GROWW (broker) with tool-call traces captured in logs
- Manually inspect:
  - Does `concall_insights` contain GNPA/NNPA for SBIN?
  - Does `get_fundamentals(expense_breakdown)` return an R&D line for SUNPHARMA?
  - Does `concall_insights` or filings doc_type resolve the ₹1,337 Cr FY24 GROWW charge?
- **Decision point:** data missing → R3 (fix tools). Data present but ignored → R1 (fix enforcement).

**Deliverable:** 3-line diagnosis per sector in `fix_tracker.md`.

## Phase 1 · Structural gap fill (parallel, 9 subagents)

**Goal:** Every tested sector has a `financials.md` with a mandatory-metrics checklist.

| Sector | File | Spec |
|---|---|---|
| broker | **new** | Revenue mix (broking/interest/distribution); SEBI ring-fencing (client float ≠ loan book funding); MTF yield; resolve IPO-linked charges via `get_company_context(doc_type='filings')` |
| chemicals | **new** | Specialty vs commodity mix; capex payback via incremental ROCE; working capital days; resolve M&A spikes via `concall_insights` |
| exchange | **new** | Revenue by segment (txn/listing/data/clearing); transaction yield; C/I ratio; float income |
| gold_loan | **new** | LTV%, auction losses%, AUM mix, NIM, branch productivity |
| holding_company | **new** | Holdco discount math; dividend income from subs; segment-level EBIT |
| hospital | **new** | ARPOB, occupancy, case mix, doctor fee structure, maturity curve of new beds |
| merchant_power | **new** | PLF, tariff realization, merchant vs PPA mix, fuel cost pass-through |
| telecom_infra | **new** | Tenancy ratio, rental per tower, churn, lease liability bifurcation |
| conglomerate | **expand** | Add debt maturity concentration check when Net Debt/EBITDA > 2x; liquidity buffer vs ST maturities; LLM context-bleed safeguard |

**Dispatch pattern:** one subagent per file in parallel, each with full Gemini spec + reference to `bfsi/financials.md` as format template. Orchestrator verifies consistency.

## Phase 2 · Tool/data layer fixes

Informed by Phase 0 diagnosis.

2.1. **BFSI CAGR table** — strip EBITDA rows when sector ∈ {bfsi, microfinance, gold_loan} at the `cagr_table` generator.

2.2. **Asset quality extraction** — verify concall_extractor captures GNPA/NNPA/PCR/slippages. Extend extractor prompt if missing.

2.3. **Expense breakdown visibility** — pharma R&D should be a named line item, not buried in "Other Costs". Audit + wire up.

2.4. **Pre-sales in sector_kpis for real estate** — verify GODREJPROP returns booking value. Extend concall extraction schema if missing.

## Phase 3 · Enforcement mechanism (the R1 fix — highest leverage)

Add a new workflow step (#9) — **Sector Compliance Gate** — that fires after step 8 and before writing:

```
9. **Sector Compliance Gate.** Before writing, produce a `## Sector Compliance Check` section listing each mandatory metric from your sector skill file. For each, state:
   - ✓ Extracted: <value> from <tool/section>
   - ✗ Missing: called <tool/section>, got <empty|error>. Retried with <alternative tool>, got <empty|error>.
   Only metrics marked ✗ with at least 2 attempted tool calls may appear as open questions. A ✗ without attempt trace is a workflow violation.
```

**Why this works where prose rules failed:** produces a visible artifact. Gemini can grade it directly. Pattern shifts from "trust me, I tried" to "here is my trace."

**Mitigation (risk of ballooning report length):** place the gate in a scratchpad section stripped from the final HTML; keep it only in the briefing envelope and logs for auditing.

## Phase 4 · Re-eval loop

- Run full matrix: `autoeval -a financials` on all 14 sectors
- Target: 12/14 at A-, 2/14 at B+ acceptable tail
- For stragglers: use Gemini feedback for targeted skill-file edits
- Iterate once if needed

---

## Orchestration model (Medium+ task, per CLAUDE.md)

- **Phase 0** — sequential (eval runs take time; findings inform Phase 2)
- **Phase 1** — embarrassingly parallel: 9 subagents in one dispatch batch, orchestrator verifies
- **Phase 2** — sequential diagnosis → fix per tool; additive-only changes
- **Phase 3** — single coordinated change to `prompts.py` + eval grading criteria (orchestrator does directly)
- **Phase 4** — serial eval runs (autoeval harness is shared)

## Risks & checkpoints

| Risk | Mitigation |
|---|---|
| Compliance gate balloons report length, hurts explainer/synthesis | Place gate in scratchpad section, strip from final HTML |
| New skill files regress currently-passing sectors | Phase 4 re-evals **all** sectors, not just failing ones |
| Tool-layer changes affect CLI / thesis pipeline callers | Additive-only changes; no API removals |
| Phase 3 enforcement doesn't catch every bypass pattern | After first re-eval, iterate the gate spec based on observed failures |

## Success criteria

- [ ] All 14 sectors in eval matrix reach A- (≥90) on `financials` agent
- [ ] No regressions on sectors currently at A- or A
- [ ] Phase 3 compliance gate appears in every report, populated with real tool-call traces
- [ ] `fix_tracker.md` records root cause per sector for future reference

## Mandatory sector metrics (reference table — for Phase 1 & skill file audits)

| Sector | Mandatory financials metric(s) |
|---|---|
| BFSI | GNPA/NNPA/PCR/Credit costs; NIM, CASA, C/I, DuPont ROE; strip EBITDA from CAGR |
| Pharma | R&D ratio; geography margin split; FDA status; ANDA pipeline |
| Real estate | Pre-sales bookings (₹ Cr + mn sq ft); collections; liquidity when ST debt > 50% |
| Food/Q-comm | `expense_breakdown` when Other Costs > 20%; per-order economics |
| Broker | Revenue mix (broking/interest/distribution); SEBI ring-fencing; MTF yield |
| Auto/EV | Per-unit economics; subsidy income split (FAME/PLI vs core) |
| Regulated utility | PAF, incentive income, receivables ageing (>6M vs <6M) |
| Telecom | Incremental EBITDA on ARPU growth; spectrum amortization |
| FMCG | Cash conversion cycle (CCC, DSO/DPO/DIO) |
| Aggregator/platform | Take rate (Rev/GMV) distinct from gross margin |
| Conglomerate | Debt maturity profile, liquidity buffer, segment-level EBIT |
