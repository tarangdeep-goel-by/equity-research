# Prompt Pattern Transfer — Cross-Agent Rule Lift (REVISED v2)

**Created:** 2026-05-28 · **Revised:** 2026-05-28 (post-audit) · **Status:** Approved, ready to execute · **Scope:** 7 specialist agents (business, financials, ownership, valuation, risk, technical, sector). **Out of scope:** macro, news, synthesis.

## Why this revision (vs v1)

v1 proposed adding 4 "new" rules to SHARED_PREAMBLE + 3 per-agent patterns. A line-by-line audit of `prompts.py` found:

- **3 of 4 v1 Tier-1 additions are redundant.** Anomaly-resolution, single-period-reclassification, and structural-absence rules are already present **verbatim across 5-6 of 7 specialists**. The internal-consistency self-audit is already in SHARED_PREAMBLE (lines 121 + 293-296). v1 would have added duplicates.
- **1 of 3 v1 Tier-2 patterns is redundant.** Hard-evidence rule is already in **7/7** specialists.
- **The biggest cheap, safe win is DEDUPING** the verbatim duplicates up into SHARED_PREAMBLE — not adding rules.
- **v1 missed 3 transferable patterns** the evals actually rewarded: JSON-prose parity, cross-section reconciliation OUTPUT (briefing field), and hypothesis validation.

This v2 reflects the corrected matrix, the DEDUPE-first sequencing, and the missed patterns.

## Actual pattern presence (verified)

| Pattern | SHARED | Bus | Fin | Own | Val | Risk | Tech | Sec | Action |
|---|---|---|---|---|---|---|---|---|---|
| Anomaly resolution: exhaust tools | partial (Fallback Chain) | ✓ L379 | T8 | — | T12 | ✓ L978 | ✓ L1093 | ✓ L1192 | **DEDUPE → SHARED** |
| Hard-evidence rule (≥2 indep) | — | ✓ L380 | T18 | T13 | T13 | ✓ L979 | ✓ L1094 | ✓ L1193 | **DEDUPE → SHARED** |
| Single-period reclassification-first | — | ✓ L381 | — | T11 (5pp only) | T14 | ✓ L980 | ✓ L1095 | ✓ L1194 | **DEDUPE → SHARED** |
| Structural absence ≠ informational | — | ✓ L382 | T17 | T9 | T15 | ✓ L981 | — | ✓ L1195 | **DEDUPE → SHARED** |
| Internal consistency self-audit | ✓ (121, 293-296) | — | — | — | T27 | — | — | — | KEEP (already universal) |
| Unit + time-period verification | partial (95, share count) | — | T21 | — | — | — | — | — | **NEW → SHARED** |
| One-off adjustment in multi-yr avg | — | — | T9 | — | — | — | — | — | **NEW → SHARED** |
| JSON-to-prose parity | — | — | — | — | — | ✓ L1055 | — | — | **NEW → SHARED** |
| Cross-section reconciliation field | — | — | — | ✓ L700 + `reconciliations[]` | — | — | — | — | **NEW → SHARED + briefing field** |
| Triangulation (2-3 indep signals) | — | — | T19 | T4 | T1 (methods) | — | — | — | **Per-agent → Bus, Sec, Risk, Tech** |
| Sensitivity on load-bearing assumption | — | — | — | — | T32 | — | — | — | **Per-agent → Fin, Risk, Sec** |
| Hypothesis validation (compute correction) | — | — | — | — | — | — | — | ✓ L1278 | **Per-agent → Bus, Fin, Risk, Tech** |

(Macro, News intentionally out of scope per user.)

---

## Phase 0 — DEDUPE (zero-risk cleanup, do this first)

Move 4 verbatim-duplicated patterns from per-agent INSTRUCTIONS/SYSTEM blocks into `SHARED_PREAMBLE`. Delete the per-agent copies. Net behavior change: **zero** (text moves up; every specialist still receives the rule because every specialist prompt includes SHARED_PREAMBLE).

### Patterns to lift

**P0.1 — Anomaly resolution: exhaust tools first.** Source text (financial T8 is the most general):
> When you spot a P&L anomaly, share count discontinuity, or unexplained spike, call `get_company_context(section='concall_insights')`, `get_events_actions(section='corporate_actions')`, or `get_fundamentals(section='expense_breakdown')` before escalating to open questions — these tools usually contain the answer. Open questions are for things genuinely outside your tool data.

Generalize: "When you spot an unexplained anomaly — P&L spike, share-count discontinuity, ownership jump, valuation step-change, technical spike, sector flow surge — call your domain's three canonical context tools (concall_insights, corporate_actions, your domain's deep-drill tool) before escalating to open questions. Each agent's INSTRUCTIONS names the specific tool trio."

**Where to lift to:** New sub-section under "Fallback Chain Exhaustion" (line 298). Title: "Anomaly resolution — exhaust tools before asking."

**Per-agent deletions:** Business L379 (one bullet), Fin T8, Val T12, Risk system block ~L978 (one bullet), Tech system block ~L1093, Sector system block ~L1192. Six deletions.

**Per-agent retention:** Each agent's INSTRUCTIONS already names the *specific* tool trio appropriate to its domain — keep those one-line trio references. The general rule moves up; the agent-specific tool names stay where they are.

---

**P0.2 — Hard-evidence rule for overriding system-classified signals.** Source text (financial T18):
> Do NOT narratively reclassify system-classified signals unless you cite AT LEAST 2 INDEPENDENT DATA POINTS supporting the alternative reading. A [low F-Score / DEEP_VALUE / accumulation] with a contrary narrative on the same numbers is speculation disguised as analysis — either cite the two independent data points that flip the reading, or let the system signal stand and note the apparent tension in open questions.

**Where to lift to:** New sub-section in SHARED_PREAMBLE after "Trust Tool Outputs Over Manual Computation" (line 96). Title: "Hard-evidence rule for overriding system-classified signals."

**Per-agent deletions:** All 7 — Bus L380, Fin T18, Own T13, Val T13, Risk L979, Tech L1094, Sector L1193.

---

**P0.3 — Single-period anomaly → reclassification hypothesis first.** Source text (business L381):
> A single-quarter margin spike, revenue jump, or mix shift > 20% QoQ defaults to "accounting / one-off / reclassification" before "business trajectory change". Verify via `concall_insights` / `corporate_actions` before narrating it as a real business inflection.

**Where to lift to:** Same sub-section as P0.2 (they're paired discipline). Or its own sub-section "Single-period anomaly: default to reclassification" after the new hard-evidence rule.

**Per-agent deletions:** Bus L381, Own T11 (partial — keep the 5pp-jumps-specific text + ownership-specific causes; delete only the generic "default to reclassification" framing), Val T14, Risk L980, Tech L1095, Sector L1194. Five-and-a-half deletions.

---

**P0.4 — Structural signal absence ≠ informational signal.** Source text (business L382):
> Before drawing conclusions from the absence of an action, check whether the action is structurally possible for this company type. A PSU executive not buying shares on the open market is structural (IAS-cadre compensation, not ESOP) — not a conviction read. A regulated-utility not announcing capex guidance is structural (CERC tariff-order-dependent), not a "harvesting" signal.

**Where to lift to:** New sub-section in SHARED_PREAMBLE right after P0.2/P0.3 (all three are paired "don't over-read signals" rules).

**Per-agent deletions:** Bus L382, Fin T17, Own T9, Val T15, Risk L981, Sector L1195. Six deletions.

### Phase 0 verification

1. **Static:** Extend `tests/unit/test_prompt_gaps.py` with 4 assertions — each pattern's text appears in SHARED_PREAMBLE. Existing per-agent assertions (if any) get inverted to assert the rule does NOT duplicate.
2. **Hash invariant:** `_SHARED_PREAMBLE_HASH` will update — confirm the runtime assertion in `build_specialist_prompt` still passes.
3. **Behavioral:** None required. Text-only move; no agent loses any rule. Skip eval validation for Phase 0 — re-run once after Phase 1 lands.

### Phase 0 size estimate

- SHARED_PREAMBLE grows by ~50-80 lines (4 new sub-sections, each 10-20 lines).
- Per-agent prompts shrink by ~120-180 lines total (24 deletions × 5-7 lines each on average).
- **Net:** prompts.py shrinks by ~60-100 lines. PR is mostly diff-friendly move/delete.

---

## Phase 1 — Add genuinely-new universal rules (SHARED_PREAMBLE)

After Phase 0 ships and tests pass, add 4 net-new rules. These are the patterns evals reward that aren't currently anywhere.

### P1.1 — Unit + time-period verification gate

**Source:** Financial T21.
**Why universal:** Every agent cites operating metrics with units (ARPU, NIM, %, ₹Cr, lakhs, MT). Currently only Fin enforces.

**Text to add (new sub-section under "Indian Conventions", after line 31):**

```
## Unit + Time-Period Verification (mandatory before any computation)

Before citing or multiplying any operating metric, confirm its unit AND
its time basis against the source tool output:

- **Per-period basis:** ARPU is usually ₹/sub/month but some sources
  report quarterly. A 3× error compounds into every downstream revenue +
  margin number.
- **Counts in millions vs crores:** 1 crore = 10 million. Subscriber
  counts, store counts, transaction volumes — confirm before multiplying.
- **Volume vs price unit:** MT vs kT vs MMSCM must match the price unit
  ($/MT vs $/T) for a correct revenue bridge.
- **TTM vs FY vs YTD vs annualized:** when the tool returns a window
  that doesn't match the table you're filling, state the conversion
  explicitly ("9M FY26 × 4/3 annualized assumes flat seasonality").

When the tool output doesn't label the unit, do NOT guess — emit a
data_gap entry (see Data Exhaustion Reconciliation) and proceed with
the unit you've explicitly inferred, naming the assumption inline.
```

**Test:** assertion for the section title + key phrases.

**Per-agent deletion:** Fin T21 (becomes redundant once shared).

### P1.2 — One-off adjustment in multi-year averages

**Source:** Financial T9.
**Why universal:** Any agent computing CAGR, multi-year averages, or trend ratios.

**Text to add (after "Reclassification Breaks", line 49):**

```
## One-Off Adjustment Discipline (multi-period averages)

Before computing or citing any multi-year average / CAGR / trend ratio
(margin trajectory, ROCE 10Y avg, payout ratio, ownership-share 5Y mean,
peer-median historical), check the period window for known exceptional
items:

- Demerger / merger years (revenue + cost structure both reset)
- Tax credit / write-back years
- Land sale / one-time other-income spikes
- Pandemic-era anomalies (FY21 in particular)
- One-off impairments or provisions

If any year in your window contains a flagged exceptional, present BOTH:
(a) the raw average across the full window, and (b) the adjusted average
excluding the exceptional year(s) with a one-line explanation of the
exclusion. State which one you're using for the thesis call.
```

**Test:** assertion for section title + key phrases.

**Per-agent deletion:** Fin T9 (becomes redundant once shared).

### P1.3 — JSON-to-prose parity (briefing-prose consistency)

**Source:** Risk iter1 (L1055).
**Why universal:** Every specialist emits a structured briefing JSON + a prose report. Without an enforced parity rule, the JSON fields silently drift from the narrative — graders flag it as inconsistency, and the synthesis agent gets misled by the JSON.

**Text to add (extension of "Internal Consistency & Source Reconciliation" at line 293):**

```
### JSON-to-prose parity (mandatory)

Every numeric field in your structured briefing JSON (key_metrics,
mandatory_metrics_status, data_gaps, top_risks, etc.) MUST have a
corresponding narrative sentence in the prose report with interpretation,
and every prose number must have a JSON entry where the schema provides
one. JSON-populated-but-silent-in-prose leaves the metric undiscussed
where the reader looks for it; prose-quoted-but-absent-from-JSON breaks
the synthesis agent's downstream merge.
```

**Test:** assertion for "JSON-to-prose parity" + key phrases.

**Per-agent deletion:** Risk iter1 first bullet at L1055 (becomes redundant).

### P1.4 — Cross-section reconciliation OUTPUT (briefing field)

**Source:** Ownership pattern (L700 + `reconciliations[]` field).
**Why universal:** Stronger than a prose self-audit rule because the OUTPUT field is detectable — emptiness can be verified, drift can be measured. Currently only Ownership emits it.

**Text to add (new sub-section in SHARED, paired with self-audit at line 293+):**

```
### Cross-section reconciliation (mandatory output)

Before writing your report, list every claim across sections that could
be reread as contradicting another section in the same report. For each,
EITHER (a) tighten language so timeframes / directionality are explicit,
OR (b) add a one-line reconciliation. Populate the briefing envelope's
`reconciliations` field with each reconciliation you made — an empty list
is acceptable only if no contradictions existed.

Common pitfalls: timeframe mismatch (quarterly vs short-window), same %pt
change labeled differently in two sections, structural vs active read
conflict, "improving" in one section and "deteriorating" in another
without explaining which window matters more.

```json
"reconciliations": [
  {
    "claims": ["<short paraphrase of section A claim>",
               "<short paraphrase of section B claim>"],
    "reconciliation": "<one-line resolution — timeframe / basis / scope>"
  }
]
```

A report whose sections contradict each other is internally inconsistent
no matter how strong either section is alone.
```

**Per-agent additions:** Add `reconciliations` field to every specialist's briefing JSON schema (Bus, Fin, Own already has it, Val, Risk, Tech, Sec).

**Per-agent deletion:** Ownership L700 entire bullet (the reconciliation rule itself moves up; the ownership-specific common-pitfalls list at L702-709 stays since it's ownership-specific).

### Phase 1 verification

1. **Static:** 4 new assertions in `test_prompt_gaps.py` (one per rule).
2. **Schema:** confirm `BriefingEnvelope.briefing: dict` still accepts the `reconciliations` key (it's `dict[str, Any]`, no migration needed).
3. **Behavioral:** small eval batch — 2 stocks × 2 strong agents (Val + Fin) to confirm no regression; 1 stock × 1 weak agent (Bus) to spot-check the lift. **5 evals, ~$125.**

---

## Phase 2 — Per-agent adaptive patterns

These need agent-specific adaptation. Skip Macro and News per scope.

### P2.1 — Triangulation rule (2-3 independent signals)

Add to: **Business, Sector, Risk, Technical** (Fin + Own already have it; Val has the methods-triangulation equivalent at T1).

| Agent | Major conclusion type | Signal trio (2-of-3 minimum) |
|---|---|---|
| Business | Moat sustainability | pricing power (price hike % vs CPI) + market share gain + capex efficiency (capex/revenue ratio trend) |
| Sector | Industry direction | volume growth + pricing trend + capacity utilization |
| Risk | Stress severity | leverage trend (D/E + interest coverage) + cash buffer (CFO 4Q vs short-term debt) + asset quality (write-offs, contingent liabilities) |
| Technical | Trend conviction | volume vs 20D avg + delivery % vs 6M avg + market breadth (% above 200DMA for the sector) |

**Diff template (per agent):**

```
N. **Triangulate major conclusions with 2-3 independent signals.** Every
major thesis claim — <agent-specific list> — must rest on at least 2-3
independent data points, not one suggestive number. For <agent's primary
output type>:

- <Output type>: <signal A> + <signal B> + <signal C> (2-of-3 minimum)

A single data point pointing in a direction is a hypothesis; three
pointing the same way is analysis. One countervailing data point does
NOT flip a 2-of-3 consensus.
```

### P2.2 — Sensitivity on load-bearing assumption

Add to: **Financial, Risk, Sector** (Val already has T32). Sensitivity in the Financials/Risk/Sector contexts gives the reader fragility info that's currently only in Val.

| Agent | Load-bearing input to sensitize | Sensitivity step |
|---|---|---|
| Financial | RM cost trend, working-capital days | margin at ±200 bps RM, CFO at +1 quarter WC build |
| Risk | recovery rate, default probability, asset coverage | stress severity at ±10% recovery, 2× default rate |
| Sector | industry growth rate, capacity-cycle timing | sector earnings at recession vs base |

### P2.3 — Hypothesis validation (compute the correction)

**Source:** Sector iter (L1278).
**Why adaptable:** When any agent identifies a distortion (cash drag inflating PB, segment cross-subsidy hiding true margin, one-time impairment skewing ROE), the rule is: don't *state* the hypothesis — *validate* it by computing the corrected value.

Add to: **Business, Financials, Risk, Technical** (Sec has it; Val + Own less central — skip).

**Diff template:**

```
N. **Hypothesis validation — compute the correction.** If you identify
a distortion (e.g., "20% ROCE is depressed by ₹X Cr of unutilized cash
on the balance sheet", "OPM trend masks segment-mix shift"), you MUST
compute the corrected value via `calculate` (ex-cash ROCE, segment-pure
margin, normalized number). Stating the hypothesis without validation
is hand-waving — make the calc, cite it, then frame the verdict on the
corrected number.
```

### Phase 2 verification

1. **Static:** assertions per agent that the triangulation / sensitivity / hypothesis-validation language appears.
2. **Behavioral:** 1 stock per affected agent (5 stocks total) — verify the new rule actually changed agent behavior. **~$125.**

---

## Phase 3 — Validation matrix

Combined regression + lift confirmation:

- **Regression evals (no break on strong agents):** Val + Fin × 3 stocks (HUL, ADANIENT, NTPC) = 6 evals.
- **Lift spot-check (weak agents):** Bus + Own + Risk + Sec + Tech × 1 stock each = 5 evals.
- **Total: 11 evals, ~$275-300.**

Compare to v1's proposed 21 evals at ~$500. Same signal, half the cost.

Pass criteria:
- Val + Fin grades hold or improve (no regression).
- Bus/Own/Risk/Sec/Tech show +1-2 pts in logical_consistency or completeness.
- `data_gaps` emission still well-formed (Lever 2 doesn't break).
- `reconciliations` field populated in ≥80% of weak-agent runs.

---

## Sequencing

1. **Phase 0 (DEDUPE)** — 1 day. Zero behavioral risk. Ship as standalone PR. No eval needed.
2. **Phase 1 (4 new SHARED rules + briefing field)** — 1.5 days + 5 evals. Ship after Phase 0 merges.
3. **Phase 2 (per-agent: triangulation + sensitivity + hypothesis-validation)** — 2 days + 5 evals. Ship after Phase 1 merges.
4. **Phase 3 (final validation)** — 1 day + 11 evals.

**Total ≈ 5.5 days + ~$300 eval budget.** Compare to v1's 3-4 days + ~$1K (but v1 had inaccurate matrix and missed Phase 0 cleanup).

---

## Open decisions (deferred to per-phase PRs)

1. **Phase 0 — tombstone comments?** When deleting per-agent duplicates, leave a one-line `# moved to SHARED_PREAMBLE Anomaly Resolution` comment, or delete silently? Recommend: silent deletion + clear PR description; tombstones rot.
2. **Phase 2 — sector-specific triangulation trios.** The trio content for Business / Risk / Sector / Technical (P2.1) is sector-dependent. Two options: (a) put a generic trio per agent in INSTRUCTIONS and let sector skills override (current pattern), (b) put trios entirely in `sector_skills/{sector}/{agent}.md`. Recommend (a) — keeps the rule discoverable per the layering rule `[[feedback_prompt_layering]]`.
3. **Phase 2 — sensitivity for Risk.** Risk already has a "Pre-Mortem: Bear Case" section. Confirm sensitivity adds value vs duplicating, or replace pre-mortem's hand-waved % with sensitivity-driven number.

---

## Next step

Branch + worktree off main:
```
git worktree add equity-research-promxfer -b feat/prompt-pattern-transfer-phase0 main
```
Execute Phase 0 first (lowest risk, mechanical move-and-delete). Run `pytest tests/ -m "not slow"`. Open PR. Eval validation deferred to Phase 1.
