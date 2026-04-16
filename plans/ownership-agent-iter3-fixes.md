# Plan: Ownership Agent Iter3 Fixes

**Created:** 2026-04-16
**Owner:** equity-research/flow-tracker
**Source:** 44 Gemini-flagged issues across 15 sectors (post PR #6 merge; current state 11/15 PASS after NTPC fix)
**Prior iterations:** iter1 (PR #5 harmonization), iter2 (PR #6 — Tenet 14 canonical search sequence + Tenet 16 "Stop Before You Multiply" + Phase 4 §4.3 cross-section consistency pass)
**Save as:** `plans/ownership-agent-iter3-fixes.md` (this copy lives at `~/.claude/plans/rippling-twirling-thimble.md` for plan-mode review; copy to project plans/ when approved)
**Goal:** Close every substantive issue — not only the four near-miss sectors — while coordinating with the in-flight `plans/valuation-agent-comprehensive-fixes.md` so shared SHARED_PREAMBLE work lands once, benefits both agents, and does not merge-conflict.

---

## Context

Iter2 (PR #6) merged Phase 2-5 of `plans/post-overnight-fixes.md` plus iter2 refactor, producing 11/15 PASS on the full ownership eval matrix once NTPC was re-run. However, reading all 15 Gemini issue lists (44 issues total) surfaces **two iter2 regressions** (Tenet 16 "Stop Before You Multiply" and Tenet 14 canonical search sequence — both present in prompt, both ignored by the agent under pressure) plus several ownership-unique patterns not covered by the parallel valuation fix plan. This iter3 plan addresses all substantive issues per `feedback_substantive_fixes.md`, with explicit coordination against the valuation branch to avoid duplicate or conflicting SHARED_PREAMBLE work.

---

## 0. Framing — Why "Fix All", Again

Per `feedback_substantive_fixes.md`:
> "When running eval cycles on research agents, do not narrow the fix scope to only 'what passes the next eval'. Fix at SHARED_PREAMBLE / agent-tenet layer prevents 5× re-discovery."

Ownership is at 11/15 PASS. The naive route is "fix the 4 near-misses and ship." That route is wrong for three reasons:

1. Three of the 12 patterns (A3, A4, B9) are **iter2-regressions** — work that we *thought* landed but didn't change behaviour under load. Grade-chasing ignores the deeper mechanism failure: **prose tenets don't enforce anything the agent doesn't already want to do under token pressure**.
2. Half the issues sit at data-pipeline layers (A1, A2, B5, B6). No prompt iteration can solve them; they silently corrupt reports on sectors that "PASS" by luck today.
3. The valuation agent is going through the identical cycle *right now*. Two of its six root patterns (A = Fallback discipline, F = Open-questions escape hatch) are the same root cause as our A4, expressed in different vocabulary. Convergent fixes at the shared-preamble layer → pay once, cross-agent coverage. Divergent agent-local fixes → future rationalization tax during business/risk/sector eval cycles.

Not in scope: the 2 `NOT_OUR_PROBLEM` issues (LLM phrasing artifacts — same acceptance posture as the valuation plan's Pattern G).

---

## 1. Diagnosis — 12 Patterns

Pattern legend:
- `failure_mode` — what Gemini actually flagged
- `why` — root cause (prompt gap / tool gap / data gap / enforcement gap)
- `sectors` — count and list
- `layer` — where the fix lives (SHARED_PREAMBLE_V2 / OWNERSHIP_SYSTEM_V2 / OWNERSHIP_INSTRUCTIONS_V2 / sector_skills / data_pipeline / tools.py)
- `overlap` — relationship to `plans/valuation-agent-comprehensive-fixes.md` (`none` | `partial` | `full`)

### Tier A — High-frequency blockers

#### A1. `shareholder_detail` missing FII named holders (DATA_FIX)
- **Failure mode:** Agent writes "FII 34% but named-holder list shows only domestic institutions — no Vanguard, BlackRock, GIC data" and cannot execute Tenet 17 (FII decomposition by archetype).
- **Why:** `screener_client.py:1120-1190` calls Screener's `/api/3/<company_id>/investors/foreign_institutions/quarterly/`. Screener returns thin named-FII coverage. No fallback source wired.
- **Sectors (8):** bfsi, chemicals, fmcg, it_services, metals, pharma, platform, telecom.
- **Layer:** `data_pipeline` + `screener_client.py`/`nse_client.py`/`store.py`/`data_api.py::get_shareholder_detail` (data_api.py:1635).
- **Overlap:** `none`. Valuation Pattern E covers PE bands, DCF, SOTP subsidiaries — different data.

#### A2. `mf_changes` returns all schemes as `new_entry` (DATA_FIX)
- **Failure mode:** Agent reports "new MF entries: 42 schemes, exits: 0" — structurally impossible. Iter2 mandatory `mf_changes` drill produces useless data; Tenet 5 becomes hollow ceremony.
- **Why:** `data_api.py:~560-600` joins current month against prior month. When prior month has partial data (AMCs filed late, backfill holes), every row falls through to `change_type = "new_entry"` at `data_api.py:594`.
- **Sectors (5):** bfsi, metals, pharma, private_bank, telecom.
- **Layer:** `data_pipeline` (`data_api.py::get_mf_changes` + `mfportfolio_commands.py` ingestion + `store.py` coverage checks).
- **Overlap:** `none`. Pure ownership problem.

#### A3. Historical %pt × CURRENT mcap (COMPUTATION / PROMPT_FIX — regression)
- **Failure mode:** "₹12,400 Cr FII outflow" derived by multiplying 2022–2024 %pt change by today's mcap. Off by 20-50% for cyclicals and multi-baggers.
- **Why (iter2 regression):** We added "Historical Flow Values — Stop Before You Multiply" at `prompts.py:412`. Agent still ignores it under pressure. It's a **narrative tenet competing with an already-completed `calculate` tool invocation** — by the time the rule's relevance surfaces, the calculate call is done.
- **Sectors (3):** conglomerate, platform, telecom.
- **Layer:** needs **schema-level enforcement**, not more prose — see §4.1 below.
- **Overlap:** `partial`. Valuation Pattern C3 (per-share from MCap not EV) and C1 (calculate skipping) share "enforcement beyond prose" root. Our fix informs valuation's C1.

#### A4. Canonical search sequence ignored (PROMPT_FIX — regression)
- **Failure mode:** Agent identifies signal, promises lookup, moves on. Examples:
  - conglomerate/ADANIENT: "GQG block deals in March 2023" — didn't widen `bulk_block` to `days=1825`.
  - pharma/SUNPHARMA: "USFDA 483/EIR trajectory" — didn't run 5-step search.
  - telecom/BHARTIARTL: "Rights issue filing" — same.
  - regulated_power/NTPC: "NTPCGREEN listed subsidiary" — same.
- **Why (iter2 regression):** Tenet 14 (`prompts.py:381-391`) was rewritten in iter2 with the explicit 5-source canonical sequence. Agent still skips under pressure. Same class as A3.
- **Sectors (4):** conglomerate, pharma, telecom, regulated_power.
- **Layer:** SHARED_PREAMBLE candidate and/or tool-function encoding the sequence.
- **Overlap:** `full`. Same failure class as valuation Pattern A (11 sectors) + F (2 sectors). If valuation lifts A+F to SHARED_PREAMBLE (its rec #2), our Tenet 14 becomes a subset. **Biggest coordination point.**

### Tier B — 2-sector patterns

#### B5. MF AMC coverage limited to 5 AMCs (DATA_FIX)
- **Failure mode:** chemicals/PIDILITIND — "66.2% of MF owner base unanalyzed"; it_services/TCS — "missing HDFC, Nippon, Kotak".
- **Why:** `mfportfolio_commands.py:20` hard-codes `_SUPPORTED_AMCS = ["SBI", "ICICI", "PPFAS", "QUANT", "UTI"]`. HDFC MF alone has ₹6L Cr+ AUM.
- **Sectors (2 explicit; silent drag on most):** chemicals, it_services.
- **Layer:** `data_pipeline` / `mfportfolio_client.py` + commands.
- **Overlap:** `none`. Already in `plans/post-overnight-fixes.md` §1.2; carry forward.

#### B6. Public bucket sub-breakdown missing (DATA_FIX)
- **Failure mode:** Agent cannot cite "Retail X%, HNI Y%, Corporate Bodies Z%" when Public > 15%.
- **Why:** `store.py` has no table for SEBI sub-categories. `shareholder_detail` returns named holders only.
- **Sectors (3):** fmcg, metals, real_estate.
- **Layer:** `data_pipeline` / `store.py` + XBRL parser.
- **Overlap:** `none`. Carried forward from `plans/post-overnight-fixes.md` §1.1.

#### B7. Ownership % lacks peer/historical context (NEW — PROMPT_FIX)
- **Failure mode:** "FII is 12%" with no sector percentile or 5-yr/10-yr band context. Gemini asks "is 12% high or low for specialty chemicals?".
- **Why:** Tenet 4 ("cross-reference 2-3 signals") is about signal mixing. SHARED_PREAMBLE "No Orphan Numbers" (prompts.py:20-21) exists but isn't triggering for % stakes.
- **Sectors (2):** chemicals, it_services.
- **Layer:** `OWNERSHIP_SYSTEM_V2` — new short tenet.
- **Overlap:** `none`.

#### B8. IPO lock-in cycle mapping missing (NEW — PROMPT_FIX)
- **Failure mode:** auto/OLAELEC and broker/GROWW — agent doesn't map the 30/90/180/365-day lock-in calendar. Misses the single biggest supply catalyst for sub-2-year stocks.
- **Why:** No tenet or sector skill references SEBI ICDR lock-in schedule.
- **Sectors (2):** auto, broker.
- **Layer:** `OWNERSHIP_SYSTEM_V2` — new tenet (fires when `listed_since < 730d`); reinforce in `sector_skills/auto/ownership.md` + new `sector_skills/broker/ownership.md`.
- **Overlap:** `none`.

#### B9. Cross-section contradictions (PROMPT_FIX — regression)
- **Failure mode:** bfsi/SBIN: "FII exit" (§2) vs "FII re-entry" (§6), unreconciled. auto/OLAELEC: 2.19pp promoter drop vs "0 insider transactions" — the drop was the OFS at IPO, not insider selling.
- **Why:** Phase 4 step 7a (`prompts.py:442-447`) added the consistency check. It enumerates 3 contradictions to watch for but doesn't force the agent to WRITE the reconciliation in the report.
- **Sectors (2):** bfsi, auto.
- **Layer:** `OWNERSHIP_INSTRUCTIONS_V2` step 7a + briefing schema (add `reconciliations: []` field).
- **Overlap:** `partial`. Valuation Pattern G (accepted as noise) flags similar class. For ownership these are substantive logic errors, not LLM phrasing; must be fixed.

### Tier C — 1-sector, flag-worthy

#### C10. Wrong buyback math (PROMPT_FIX)
- **Failure mode:** TCS: "0.64pp drop is consistent with pro-rata non-participation in the buyback." **Wrong** — non-participation INCREASES %, since denominator shrinks.
- **Why:** No tenet covers buyback arithmetic. Agent misapplies new-equity-issue reasoning.
- **Sectors (1):** it_services.
- **Layer:** `OWNERSHIP_SYSTEM_V2` new tenet; reinforce in `sector_skills/it_services/ownership.md`.
- **Overlap:** `none`.

#### C11. Agent skipped `mf_holdings` workflow step (PROMPT_FIX)
- **Failure mode:** fmcg/HINDUNILVR — Tool Audit claims `mf_holdings` was called; execution log shows it wasn't. Both Tool Audit honesty violation AND drill skip.
- **Why:** Phase 2 Tool Audit strict-honesty rule exists. Agent still self-reports falsely under pressure. Same enforcement-gap class as A3/A4.
- **Sectors (1):** fmcg.
- **Layer:** `OWNERSHIP_INSTRUCTIONS_V2` + post-run verifier check against `evidence[]` in briefing envelope.
- **Overlap:** `partial`. Valuation Pattern A sub-instance shares root.

#### C12. `filings` tool failure for ADR data (DATA_FIX or PROMPT_FIX — ambiguous)
- **Failure mode:** private_bank/HDFCBANK, bfsi/SBIN — agent needs ADR/GDR outstanding counts for Tenet 12 aggregate-foreign-holding math; `get_company_context(section='filings', query='ADR')` returns empty.
- **Why:** Unclear — could be filings not tagging ADR docs (data), or wrong query string (prompt). Needs diagnostic.
- **Sectors (2):** bfsi, private_bank.
- **Layer:** TBD — diagnostic first.
- **Overlap:** `none`.

---

## 2. Pattern → Layer → Overlap Matrix

| Pattern | Sectors | Layer | # Issues | Overlap with valuation |
|---|---|---|---|---|
| A1 — FII named holders | 8 | data_pipeline | 8 | none |
| A2 — mf_changes stale baseline | 5 | data_pipeline | 5 | none |
| A3 — Historical × current mcap | 3 | schema-level | 3 | partial (C3/C1) |
| A4 — Canonical search ignored | 4 | SHARED_PREAMBLE candidate | 4 | full (A/F) |
| B5 — MF AMC 5→15 | 2 | data_pipeline | 2 | none |
| B6 — Public sub-breakdown | 3 | data_pipeline | 3 | none |
| B7 — Peer/history anchor | 2 | OWNERSHIP_SYSTEM_V2 | 2 | none |
| B8 — IPO lock-in cycle | 2 | OWNERSHIP_SYSTEM_V2 + skills | 2 | none |
| B9 — Cross-section contradictions | 2 | INSTRUCTIONS_V2 + schema | 2 | partial |
| C10 — Buyback math | 1 | OWNERSHIP_SYSTEM_V2 | 1 | none |
| C11 — Tool audit / drill skip | 1 | SHARED_PREAMBLE + verifier | 1 | partial |
| C12 — ADR filings | 2 | diagnostic-dependent | 2 | none |
| **Total** | | | **42 (of 44)** | |

Per sector:

| Sector | # | Patterns | Dominant layer |
|---|---|---|---|
| bfsi | 3 | A1 + A2 + B9 + C12 | data + workflow |
| chemicals | 3 | A1 + B5 + B7 | data + prompt |
| fmcg | 3 | A1 + B6 + C11 | data + workflow |
| it_services | 3 | A1 + B5 + B7 + C10 | data + prompt |
| metals | 3 | A1 + A2 + B6 | data |
| pharma | 3 | A1 + A2 + A4 | data + prompt |
| platform | 2 | A1 + A3 | data + schema |
| telecom | 4 | A1 + A2 + A3 + A4 | data + schema + prompt |
| private_bank | 3 | A2 + C12 | data |
| conglomerate | 2 | A3 + A4 | schema + prompt |
| regulated_power | 1 | A4 | prompt (NTPC fixed post-iter2) |
| auto | 2 | B8 + B9 | prompt + skill |
| broker | 1 | B8 | prompt + new skill |
| real_estate | 1 | B6 | data |
| insurance | 0 | — | already PASS |

---

## 3. Overlap Resolution Strategy

### Zone 1 — Fully shared (defer to valuation, layer on top)
Valuation's Pattern A + F = our A4. Valuation plan §1.4 + §9 rec #2 proposes lifting fallback discipline as cross-agent invariant **I-9** in SHARED_PREAMBLE.
- **Our behaviour:** Wait for valuation PR 1a to merge. Once I-9 lands, delete redundant text from Tenet 14 and leave only an ownership-specific 5-source adaptation line. Net effect: Tenet 14 shrinks, SHARED_PREAMBLE takes the load.
- **Contingency:** If valuation PR 1a defers I-9, iter3 strengthens Tenet 14 locally with the schema-level mechanism from §4.

### Zone 2 — Partially shared (cross-pollinate, own implementation)
- **A3 + valuation C3 + C1** all collapse to "agent bypasses calculate-tool enforcement at the moment it matters." Neither plan proposes a mechanism stronger than prose. **§4.1 of this plan proposes schema-level enforcement.** If it works on ownership (3 sectors), feed back to valuation.
- **B9** — if valuation Pattern G gets promoted from "accept" to "fix" later, B9 becomes cross-agent. For now, ownership-local.

### Zone 3 — Ownership-unique (ship independently)
A1, A2, B5, B6 (data), B7, B8, C10, C11, C12 (prompt/skill) — no merge-conflict risk with valuation branch.

### Explicit sequencing

| Step | Trigger | Action |
|---|---|---|
| S1 | Valuation PR 1a merges | Rebase iter3 branch; inspect whether I-9 landed |
| S2a | I-9 landed in SHARED_PREAMBLE | Iter3 strips Tenet 14 to 1-liner + 5-source list |
| S2b | I-9 deferred (valuation kept local) | Iter3 strengthens Tenet 14 in full + ships §4 schema mechanism |
| S3 | Iter3 Phase 1 merges | Phase 2 (sector skills) opens — independent of valuation Phase 2 |
| S4 | Phase 1+2 green on re-eval | Phase 3 (data pipeline) begins — 4-track independent PRs |
| S5 | All phases green | Propose Phase 4 cross-agent invariant lifts upstream |

---

## 4. Phase 1 — Ownership-unique Prompt Fixes

Does NOT touch SHARED_PREAMBLE (valuation's territory this week). Single PR, renumbered tenets, hash-safe.

### 4.1 Tier A3 — Re-engineer Tenet 16 via schema, not prose

**Problem statement.** "Stop Before You Multiply" (prompts.py:412-420) is prose. Agents ignore prose tenets when they're 4k tokens into their planning. Needs a **structural interrupt** that fires at the moment of the `calculate` call.

**Proposed mechanism — `calculate` tool schema extension:**

```python
# flow-tracker/flowtracker/research/tools.py — current (tools.py:1815)
async def calculate(args):
    # operation: str, a: float, b: float

# proposed
async def calculate(args):
    # operation, a, b
    # + inputs_as_of: str | None    — ISO quarter/date for a's context
    # + mcap_as_of: str | None      — ISO quarter/date for b's context (when b is mcap)
    # + buyback_adjusted: bool      — new op for C10 fix
```

Tool behaviour:
- If `operation in {"pct_of","multiply","shares_to_value_cr"}` AND `inputs_as_of != mcap_as_of` (and both provided): return a warning string the agent must echo in prose before citing the ₹Cr figure:
  > `HISTORICAL_MCAP_MISMATCH: %pt change from {inputs_as_of} multiplied by mcap from {mcap_as_of}. Result ₹X Cr is at {mcap_as_of} mcap — actual historical flow value may differ 20-50%. Either (a) pass mcap_as_of matching inputs_as_of, or (b) report change in %pt only.`
- If neither provided: back-compat, soft hint in tool audit: `_timestamp_discipline_missing`.

**Why schema-level beats prose:**
- Agents ignore rule #16. They cannot ignore a tool response that asserts "your answer contains a 20-50% error unless acknowledged."
- The warning string becomes a **load-bearing phrase** the agent must work around, not around.
- Tool audit row (with Phase 2 Tool-Audit-honesty) makes the discipline reviewer-verifiable.

**Prompt changes:**
- Replace prose block `OWNERSHIP_INSTRUCTIONS_V2:412-420` with:
  > `Historical-flow-value math: pass inputs_as_of and mcap_as_of to calculate() when converting %pt deltas to ₹Cr. The tool returns a HISTORICAL_MCAP_MISMATCH warning if dates diverge — echo the caveat verbatim in prose before citing the ₹Cr figure. See Tenet 16.`
- Shrink Tenet 16 (`OWNERSHIP_SYSTEM_V2:393-395`) to: "Timeframe alignment — default `bulk_block` window must cover the analyzed shift (see workflow step 2); historical-flow ₹Cr values require the calculate-tool's `inputs_as_of`/`mcap_as_of` schema (see INSTRUCTIONS)."

**Files touched:**
- `flow-tracker/flowtracker/research/tools.py:1815` — `calculate` signature + schema + warning generator
- `flow-tracker/flowtracker/research/data_api.py` — corresponding plumbing if wrapper
- `flow-tracker/flowtracker/research/prompts.py` — Tenet 16 + INSTRUCTIONS block trimmed
- `flow-tracker/tests/integration/test_mcp_tools_extended.py` — new test: `calculate(op="pct_of", inputs_as_of="2023-Q4", mcap_as_of="2026-Q1")` returns the warning substring

**Acceptance test:** re-run conglomerate, platform, telecom. Tool audit shows `inputs_as_of`/`mcap_as_of` args. Reports either match timestamps (correct) or echo the HISTORICAL_MCAP_MISMATCH caveat (correct and honest).

### 4.2 Tier A4 — Tenet 14, conditional on valuation PR 1a

**Fork A — valuation PR 1a lifts fallback discipline to SHARED_PREAMBLE (I-9):**
Tenet 14 becomes 1-liner:
> `See SHARED_PREAMBLE invariant I-9 for canonical-search exhaustion. Ownership's 5-source sequence: filings, documents, concall_insights, shareholder_detail, balance_sheet_detail.`
Open-questions ceiling (3-5) stays in Tenet 14 as ownership-specific.

**Fork B — valuation PR 1a does NOT lift I-9:**
Strengthen Tenet 14 with a **table-form** canonical-search sequence (tables read better under pressure than prose). Also ship §4.7 verifier audit-vs-evidence check to close the compliance loop.

```
### Canonical Search Sequence (invoke in order; Open Question only after all 5 empty)

| Step | Tool call | Answers |
|---|---|---|
| 1 | get_company_context(section='filings', query='<topic>') | DRHP/AR/regulatory filings |
| 2 | get_company_context(section='documents', query='<topic>') | Press releases/exchange disclosures |
| 3 | get_company_context(section='concall_insights', sub_section='management_commentary') | Concall Q&A |
| 4 | get_ownership(section='shareholder_detail') | Named holders incl. trust/sub entities |
| 5 | get_fundamentals(section='balance_sheet_detail') | Share-capital/treasury-share footnotes |
```

### 4.3 Tier B7 — New tenet: peer/historical anchor for ownership %s

Insert as **Tenet 19** (Sector Compliance Gate becomes Tenet 22 after renumber):
> **19. Every material ownership % needs peer and historical anchor.** A standalone "FII is 12%" or "promoter is 54%" is incomplete. For every % > 5% discussed narratively, cite (a) where it sits in this stock's own 5-year band (min/median/max from `shareholder_detail` quarters), and (b) sector percentile via `get_peer_sector(section='benchmarks')`. Exception: promoter pledge, where absolute thresholds (5%/20%/50%) carry meaning regardless of band/sector. This is the ownership application of SHARED_PREAMBLE "No Orphan Numbers", made explicit because quarterly ownership-trend data is uniquely suited to historical anchoring.

### 4.4 Tier B8 — IPO lock-in cycle tenet (gated on listing age)

Insert as **Tenet 20:**
> **20. IPO lock-in calendar is mandatory for stocks listed <730 days ago.** Per SEBI (ICDR) Reg 16/17, anchor allocations are locked 30/90 days post-listing; pre-IPO investor lock-ins vary (6/12/18 months); promoter lock-ins are 18 months minimum. For any stock with `listed_since < 730d` (from `_listed_since` metadata — see Phase 3 D-meta), construct a lock-in calendar: `{expiry_date, category_expiring, % of equity, current status}`. Supply overhangs concentrated in a 30-60 day window post-expiry are the single largest technical driver for recently-listed stocks and dominate the insider/bulk-block/delivery narrative during that window. If expiry dates are not determinable from tools, raise as a specific open question citing the DRHP page (not a generic "what are the lock-in dates?").

Sector-skill reinforcement: `sector_skills/auto/ownership.md` and new `sector_skills/broker/ownership.md` add a stock-specific lock-in table template.

### 4.5 Tier B9 — Cross-section consistency pass strengthening

Current step 7a (prompts.py:442-447) asks the agent to check 3 contradictions. Doesn't force the reconciliation into the report.

**Replace with:**
```
7a. **Cross-section reconciliation pass (MANDATORY output).** Before writing the report, list every claim in Sections 2, 5, 6 that could be reread as contradicting another section. For each, either (a) tighten language so timeframes/directionality are explicit, or (b) add a one-line reconciliation. Populate briefing envelope's `reconciliations: list[{"claims": [str, str], "reconciliation": str}]` with every reconciliation made — empty list is acceptable only if no contradictions existed.

   Common pitfalls:
   - Quarterly %pt trend vs short-window delivery/bulk-block activity (timeframe mismatch)
   - Headline % change vs composition change (reclassification ≠ selling)
   - Structural vs active signal (2.19pp promoter drop at IPO OFS ≠ "promoter selling")
```

**Briefing schema update:** add `reconciliations` field to the JSON schema in `OWNERSHIP_INSTRUCTIONS_V2:461-489`. `BriefingEnvelope.briefing` is free-form dict today — no pydantic change needed.

### 4.6 Tier C10 — Buyback math tenet

Insert as **Tenet 21:**
> **21. Buyback arithmetic: non-participants gain %, don't lose it.** When a company buys back shares, the denominator (shares outstanding) shrinks while non-participating holder X's absolute shares stay flat. Their % **increases**, not decreases. For holder X: new % = N_old / (S_old − B) > N_old / S_old. A promoter or FII % DROP during a buyback window is **active selling or non-tender acceptance at below-retention level**, NOT pro-rata non-participation. Before interpreting any drop, check `corporate_actions` for the buyback ratio and verify with `calculate(operation='buyback_adjusted_pct', ...)`.

**Optional tool support:** add `buyback_adjusted_pct(holder_shares, total_shares_before, buyback_shares)` to calculate tool — same mechanism class as §4.1.

### 4.7 Tier C11 — Workflow discipline via post-run verifier

**Problem statement.** Tool Audit honesty (SHARED_PREAMBLE:16-18) is strong in prose; agent still drifts. Root cause: **no consequence for drift**. Audit is a narrative assertion; evidence (`BriefingEnvelope.evidence[]` in `briefing.py:40-53`) is recorded independently; nobody cross-checks.

**Proposed fix:**
- Extend `flow-tracker/flowtracker/research/verifier.py` with one additional post-run check: for each row in `## Tool Audit`, confirm a matching `evidence[].tool + args` entry. Mismatches (claimed but not called; called but not claimed; claimed ∅ but evidence non-empty) → add as `corrections` in `VerificationResult`.
- **Mechanical check**, not LLM judgment — string match over evidence list against audit table.
- For mandatory drills (mf_changes, shareholder_detail, shareholding aggregate) with zero evidence calls, verifier returns `verdict: fail` → agent re-run on that section only.

**Files touched:**
- `flow-tracker/flowtracker/research/verifier.py` — audit-vs-evidence cross-check
- `flow-tracker/tests/integration/test_verifier.py` (create if absent) — mismatch detection test

**Why this beats more prose:** every iteration has added stronger warnings ("will be downgraded", "workflow violation"). Agent is self-graded. Non-LLM check closes the loop.

### 4.8 Tier C12 — ADR filings diagnostic

Day-1 spike (not a fix yet):
- Run `get_company_context(symbol='HDFCBANK', section='filings', query='ADR')`, `query='depositary receipts'`, `query='aggregate foreign'`. Inspect returned filings corpus.
- If ADRs tagged in BSE but query misses → fix is query-string in `sector_skills/private_bank/ownership.md`.
- If ADR-category disclosures absent from corpus → fix is `data_pipeline` ingestion (BSE pattern filings under "Outstanding ADR/GDR Programme" category).

Hand off to Phase 3 if data fix; to Phase 2 if prompt/skill fix.

---

## 5. Phase 2 — Ownership-unique Sector Skill Additions

Coordinates with `plans/full-sector-skills-buildout.md` Phase 2 and valuation plan §4 per-sector subagent dispatch model.

### Per-sector ownership.md adjustments

| Sector | Current file? | iter3 additions |
|---|---|---|
| **bfsi** | Yes | (a) Cross-section reconciliation template for FII exit-vs-reentry; (b) ADR/GDR query pattern once C12 diagnostic lands |
| **private_bank** | Yes | ADR/GDR query pattern for HDFCBANK; extend ESOP-dilution section |
| **pharma** | Yes | Canonical search sequence **worked example** for USFDA 483/EIR lookups — exact 5-tool walk |
| **telecom** | Yes | Worked example: rights-issue canonical search + historical-mcap caveat example (A3) |
| **regulated_power** | Yes | NTPCGREEN-style recent-subsidiary-IPO lookup pattern |
| **conglomerate** | Yes | GQG-style block deal worked example with `days=1825` |
| **platform** | Yes | Historical-mcap caveat example (A3) |
| **chemicals** | Yes | Peer/history anchor example (B7) — "12% FII in specialty chemicals is {percentile} vs peers, {band position} vs own 5Y" |
| **it_services** | Yes | B7 example + C10 buyback math worked example (TCS) |
| **auto** | Yes | B8 IPO lock-in calendar template for OLAELEC |
| **broker** | **NO — CREATE** | New file. GROWW-style IPO lock-in calendar + new-age broker unit economics |
| **metals** | Yes | B6 sub-breakdown pointer; A2 mf_changes caveat |
| **fmcg** | Yes | C11 mf_holdings discipline reminder; B6 pointer |
| **real_estate** | Yes | B6 pointer; no net-new content |
| **insurance** | Yes | Nothing new — PASSed iter2 |

### Generation method

Follow valuation plan §4 locked decision: one subagent per sector owns all specialist files. Feed subagent the table row + Gemini issue list for that sector.

---

## 6. Phase 3 — Ownership-unique Data Pipeline Fixes

Four independent tracks. None overlap with valuation Pattern E.

### 6.1 D1 — FII named-holder augmentation (A1; 8 sectors — highest leverage)

**Goal:** Populate `shareholder_detail` with named foreign institutional holders at ≥1% threshold.

**Candidate sources (evaluate in order):**
1. **BSE shareholding pattern XBRL** — `<PublicShareholding>/<ForeignInstitutionalInvestors>` nested elements. Partial NSE XBRL path already exists for B6.
2. **NSE equity-shareholding API** — similar XBRL payload.
3. **Screener yearly-view fallback** — on thin quarterly, re-query `/api/3/<id>/investors/foreign_institutions/yearly/`.

**Technical plan:**
- **Schema:** extend `shareholder_detail` or create `shareholder_detail_fii` with `(symbol, quarter_end, holder_name, holder_classification, subclassification, pct, url_source)`. `subclassification` = iter2 Tenet 17 archetype (sovereign_wealth / passive_etf / active_mandate / hedge_fund / unknown) — populated via allowlist in `data_api.py`.
- **Parser:** new `nse_client.py::parse_foreign_institutions_from_xbrl(xbrl_bytes)` + corresponding store method.
- **Classifier:** post-process FII rows with static name → archetype mapping (seed from top 40 names in iter2 Tenet 17). Unknown → `unknown`. Makes Tenet 17 trivially executable.

**Files:**
- `flow-tracker/flowtracker/store.py` — new table or columns
- `flow-tracker/flowtracker/nse_client.py` — XBRL parse
- `flow-tracker/flowtracker/screener_client.py` — yearly fallback
- `flow-tracker/flowtracker/research/data_api.py:1635` — classifier + augmented `get_shareholder_detail`

**Acceptance test:** all 8 affected sectors return ≥5 named FII each with archetype labels.

### 6.2 D2 — mf_changes prior-month baseline (A2; 5 sectors)

**Root cause:** `data_api.py:~567-594` joins current month against exactly `month − 1`. Partial prior-month data → every row falls through to `new_entry`.

**Fix (both):**
1. **Month coverage check** — before computing changes, `SELECT COUNT(DISTINCT amc) FROM mf_scheme_holdings WHERE month=prev_month`. If coverage < current, walk back up to 3 months to find complete baseline; annotate `_baseline_month` + `_baseline_coverage_note`.
2. **Per-AMC matching** — only classify as `new_entry` if AMC exists in both months. Missing AMCs → `change_type: "unknown_prior_coverage"`.

**Files:**
- `flow-tracker/flowtracker/research/data_api.py::get_mf_changes`
- `flow-tracker/tests/unit/test_data_api.py` — partial-coverage tests

**Acceptance test:** SBIN, VEDL, SUNPHARMA, HDFCBANK, BHARTIARTL return mixed change_types — not 100% new_entry.

### 6.3 D3 — MF AMC expansion 5 → 15 (B5; already specified in post-overnight-fixes §1.2)

Priority: HDFC, Nippon India, Kotak Mahindra, Axis, Aditya Birla, DSP, Tata, Motilal Oswal, Mirae Asset, Edelweiss.

Files: `flow-tracker/flowtracker/mfportfolio_client.py` (parsers), `flow-tracker/flowtracker/mfportfolio_commands.py:20` (expand list), `scripts/monthly-mfportfolio.sh`.

### 6.4 D4 — Public bucket sub-breakdown (B6; already specified in post-overnight-fixes §1.1)

New table `shareholding_public_breakdown` keyed on `(symbol, quarter_end, sub_category)` with categories `retail_upto_2L / hni_above_2L / corporate_bodies / nri / trust_others`. Parser reuses D1 XBRL work. Update `sector_skills/conglomerate/ownership.md` (already references planned tooling).

### 6.5 D-meta — `_listed_since` metadata on analytical_profile

Required for B8 tenet to fire conditionally. Cross-references Plan §1.3 (analytical_profile graceful degradation).
- Add `listing_date` column to `company_snapshot` (or compute from earliest chart-data date).
- `get_analytical_profile` surfaces `_listed_since: "YYYY-MM-DD"` in payload.

---

## 7. Phase 4 — Cross-agent Invariants to Propose Upstream

After Phases 1+2 green on ownership, propose to playbook / SHARED_PREAMBLE:

### 7.1 I-10 — Schema-level calculate-tool discipline

Derived from §4.1 + §4.6. Generalized:
> **I-10.** Where a calculate operation combines inputs whose timestamps or structural assumptions materially affect result, the tool schema carries the discipline: `inputs_as_of`, `mcap_as_of`, `buyback_adjusted`, etc. The tool returns `*_MISMATCH` when inputs violate discipline; agent must echo verbatim in prose. Prose tenets retained for readability; authority is in the tool signature.

Benefit to valuation: resolves Patterns C1, C2, C3, C4 with one mechanism.

### 7.2 I-9 — Canonical search exhaustion

Already proposed by valuation plan §9 rec #2. Ownership A4 + valuation A/F share the root.

### 7.3 I-11 — Cross-section reconciliation as universal

Derived from §4.5 (ownership B9). Propose `reconciliations` briefing field as cross-agent convention; each agent enforces via its INSTRUCTIONS step.

---

## 8. Execution Sequencing

Timeline (assuming valuation PR 1a merges Day 1):

| Day | Stream | PR | Output |
|---|---|---|---|
| Day 1 | — | Wait for valuation PR 1a | SHARED_PREAMBLE calculate strengthened; possibly I-9 lifted |
| Day 1 PM | Diagnose | spike | Check I-9 landed? Run C12 ADR diagnostic. Decide §4.2 Fork A vs B. |
| Day 2 | Prompt | **iter3-PR-A** — ownership-unique prompts | Tenets 16 (delegation), 19 (peer anchor), 20 (IPO lock-in), 21 (buyback math); step 7a strengthened; Tenet 14 conformed |
| Day 2 | Tools | **iter3-PR-B** — calculate schema + verifier | `calculate(inputs_as_of, mcap_as_of, buyback_adjusted)`, verifier audit-vs-evidence, tests |
| Day 3 | Re-eval | — | 15-sector ownership re-eval; expect 14/15 PASS |
| Day 3 | Skills | **iter3-PR-C** — sector skills | 11 ownership.md updates + new broker/ownership.md |
| Day 4 | Re-eval | — | 15-sector re-eval; target 15/15 PASS |
| Day 5–12 | Data | **iter3-PR-D1..D4** (independent) | FII names / mf_changes / AMC 5→15 / Public sub-breakdown |
| Day 13 | Re-eval | — | Full 15-sector; target 15/15 at A or higher on 8+ |
| Day 14 | Cross-agent | Playbook PR | Propose I-10 upstream |

Valuation branch proceeds parallel Day 2+ (its Phase 1b/c, Phase 2). Merge conflicts avoided because iter3 doesn't touch SHARED_PREAMBLE or VALUATION_*.

### PR split rationale

- **iter3-PR-A + B** bundled only if calculate schema change is strictly additive; otherwise split to contain blast radius (tools.py is shared by all agents).
- **iter3-PR-C** sector skills — independent, low risk, parallelize via subagent dispatch.
- **iter3-PR-D1..D4** — fully independent pipeline. D3 slowest (10 AMC parsers). D1 highest leverage.

---

## 9. Verification

### After iter3-PR-A + B (prompt + schema)

| Sector | Baseline | Expected | Patterns closed |
|---|---|---|---|
| conglomerate | PASS (near-miss) | PASS+ | A3, A4 |
| platform | PASS | PASS+ | A3 |
| telecom | FAIL (A1+A2+A3+A4) | PASS | A3, A4 (A1/A2 need data) |
| pharma | FAIL (A1+A2+A4) | PASS | A4 (A1/A2 need data) |
| it_services | PASS | PASS+ | B7, C10 |
| chemicals | PASS | PASS+ | B7 |
| auto | PASS | PASS+ | B8, B9 |
| broker | PASS | PASS+ | B8 |
| bfsi | FAIL (A1+A2+B9+C12) | likely still FAIL | B9 only |
| fmcg | PASS | PASS+ | C11 |

**Re-run cost:** 15 × ~$0.35 ownership + 15 × ~$0.50 grade ≈ ~$13.

### After iter3-PR-C (sector skills)

Worked examples guide agent through canonical sequence. Expect +0.5 to +1 grade bump on pharma, telecom, regulated_power.

### After iter3-PR-D1..D4 (data)

| Sector | Data closed | Expected delta |
|---|---|---|
| bfsi | A1 + A2 | FAIL → PASS (A) |
| pharma | A1 + A2 | FAIL → PASS (A) |
| telecom | A1 + A2 | FAIL → PASS (A) |
| private_bank | A2 | PASS → PASS+ |
| metals | A1 + A2 + B6 | PASS → PASS++ |
| fmcg | A1 + B6 | PASS → PASS+ |
| real_estate | B6 | PASS → PASS+ |
| chemicals | A1 + B5 | PASS → PASS+ |
| it_services | A1 + B5 | PASS → PASS+ |

**Total re-run cost:** ~$26 across 2 cycles.

### Regression watch
- After PR-A, **spot-check 2 valuation sectors** (auto, fmcg) for collateral impact from calculate schema change. Back-compat defaults should prevent regression but verify.
- After PR-C, **spot-check insurance** — was PASS; ensure no regression from sector-skill reorg.

---

## 10. Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Schema calculate change breaks other agents | Medium | Default args (back-compat); integration test covers all agents; spot-eval financials + valuation 2 sectors post-PR-B |
| Valuation PR 1a merges simultaneously → conflict | Low | Iter3 branches from valuation HEAD; rebase if needed |
| FII named-holder XBRL coverage varies by issuer discipline | High | Ship D1 with `_fii_coverage_note` in payload; agent caveats when <50% coverage. Partial better than nothing |
| iter2 regression repeats for B7/B8/C10 | Medium | §4.1 schema enforcement is the hedge — if prose fails a third time, promote to tool schema too |
| Verifier false positives (legitimate paraphrase in audit) | Medium | Start in **shadow mode** (log, don't fail) for 1 cycle; calibrate; then enforce |
| Cost creep | Low-Med | Two full re-evals ($26) + 2 spot-checks ($6). Cap at $40 |
| Gemini outage (per `feedback_gemini_outage_recovery`) | Medium | Save reports to disk; batch `--skip-run` regrade; never downgrade model |
| `feedback_no_model_fallback` accidentally violated | Low | Review every agent `ClaudeAgentOptions` touch — no `fallback_model` additions |

---

## 11. Definition of Done

- [ ] iter3-PR-A merged: Tenets 19/20/21 landed; 14 harmonized with valuation I-9 decision; 16 slimmed; step 7a rewritten; briefing schema updated
- [ ] iter3-PR-B merged: `calculate` schema extended; verifier audit-vs-evidence live
- [ ] iter3-PR-C merged: 11 ownership.md updates + new broker/ownership.md; worked examples present
- [ ] iter3-PR-D1 merged: FII named-holder parse; 8 target sectors return ≥5 named FII each
- [ ] iter3-PR-D2 merged: mf_changes coverage-aware; no sector returns 100% new_entry
- [ ] iter3-PR-D3 merged: 15+ AMCs; coverage ≥95% of MF AUM
- [ ] iter3-PR-D4 merged: public_breakdown table populated; 3 target sectors show sub-breakdown
- [ ] Full 15-sector re-eval: 15/15 PASS; ≥8 at A or better
- [ ] No regression on valuation or financials (2-sector spot-checks green)
- [ ] I-10, I-11 proposals opened as playbook PR
- [ ] NOT_OUR_PROBLEM count held flat (≤2 issues / 15 sectors)

---

## 12. Open Decisions for User

1. **Wait for valuation PR 1a, or proceed parallel?** Recommend **wait**. Valuation Phase 1.1 touches SHARED_PREAMBLE; merging iter3 on top avoids two passes. Cost of waiting: ~1 day.
2. **§4.1 schema-level calculate enforcement — ship iter3 or defer?** Recommend **ship in iter3**. Evidence-based response to iter2 prose-tenet regression; validates on contained scope (3 sectors).
3. **§4.7 verifier cross-check — shadow or enforce immediately?** Recommend **shadow 1 cycle, then enforce**. False-positive risk from paraphrase warrants 1 cycle of observation.
4. **C12 ADR filings — diagnose iter3 or hand off?** Recommend **Day-1 spike** (<1 hour); classification decides track.
5. **B8 IPO lock-in — prompt-only or structured tool?** Recommend **prompt-only first**. Universe is small (~5 stocks); promote to `get_ipo_lock_in_calendar(symbol)` tool only if Gemini still flags in iter4.
6. **I-10 upstream lift — now or after ownership empirical validation?** Recommend **wait one cycle**. Propose to playbook after §4.1 proves it closes A3+C10 on ownership side. Premature lift risks locking other agents into mechanism that needs tuning.
7. **D1 vs D2 first?** D2 (mf_changes fix) first — ~2 hours, unlocks 5 sectors. D1 (FII names) ~3-5 days, unlocks 8 sectors. Parallelize D3+D4 after D1.

---

## 13. Verification — End-to-end

After each phase, run:

```bash
cd flow-tracker
# after PR-A + PR-B merge — re-eval full 15
uv run flowtrack research autoeval -a ownership
# or spot-check specific sectors
uv run flowtrack research autoeval -a ownership --sectors conglomerate,platform,telecom
# regression check on valuation
uv run flowtrack research autoeval -a valuation --sectors auto,fmcg --skip-run
```

If Gemini 503 storm hits (per `feedback_gemini_outage_recovery`), reports are saved; regrade with `--skip-run` once recovered.

---

## 14. Appendix — Critical Files

- **Prompts:** `flow-tracker/flowtracker/research/prompts.py`
  - Ownership section: approx `prompts.py:358-492`
  - Tenet 16 "Stop Before You Multiply": `prompts.py:412`
  - Tenet 14 canonical search: `prompts.py:381-391`
  - Step 7a cross-section consistency: `prompts.py:442-447`
  - SHARED_PREAMBLE Tool Audit: `prompts.py:14-20`
- **Tool:** `flow-tracker/flowtracker/research/tools.py` — `async def calculate(args)` at `tools.py:1815`
- **Data API:** `flow-tracker/flowtracker/research/data_api.py`
  - `get_mf_changes` at approx `data_api.py:~560-600`
  - `new_entry` assignment: `data_api.py:594`
  - `get_shareholder_detail`: `data_api.py:1635`
- **Screener:** `flow-tracker/flowtracker/screener_client.py:1120-1190` (foreign_institutions endpoint)
- **Store:** `flow-tracker/flowtracker/store.py` (shareholder_details table)
- **Verifier:** `flow-tracker/flowtracker/research/verifier.py` (extend with audit cross-check)
- **Briefing:** `flow-tracker/flowtracker/research/briefing.py:40-53` (BriefingEnvelope.evidence)
- **MF AMCs:** `flow-tracker/flowtracker/mfportfolio_commands.py:20` (`_SUPPORTED_AMCS`)
- **Parallel branch:** `plans/valuation-agent-comprehensive-fixes.md`
- **Prior iteration:** `plans/post-overnight-fixes.md`
- **Sector-skills coordination:** `plans/full-sector-skills-buildout.md`
- **Playbook:** `flow-tracker/docs/agent-skills-playbook.md`
- **PR #6 merge baseline:** commit `b2e045e`
