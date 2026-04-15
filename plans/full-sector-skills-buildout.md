# Plan: Full Sector-Skills Buildout to Playbook Compliance

**Created:** 2026-04-15
**Owner:** equity-research/flow-tracker
**Goal:** Every specialist agent + every eval-matrix sector has a playbook-compliant skill file; every agent system prompt conforms to the playbook's cross-agent invariants.

---

## 1. Current Coverage Audit

### Agent system prompts (conformance to playbook section 4.3)

| Agent | I-1 | I-2 | I-3 | I-4 | I-5 | I-6 | I-7 | I-8 | TOC-drill | Persona |
|---|---|---|---|---|---|---|---|---|---|---|
| financials | ✓ | ✓ | ✓ | ~ | ~ | ✓ | ✓ | n/a | ✓ | ✓ |
| ownership | ~ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| business | ✗ | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | ✗ | ✗ | ✓ |
| valuation | ✗ | ✗ | ✗ | ✗ | ✗ | ~ | ✗ | ✗ | ~ | ✓ |
| risk | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| technical | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | n/a | ✓ |
| sector | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

**Gap:** 5 agents (business, valuation, risk, technical, sector) need full cross-agent-invariant sweep.

### Sector skill-file coverage

| Agent | Files present | Sectors covered | Missing |
|---|---|---|---|
| financials | 23 | all sector dirs | 0 |
| ownership | 13 | eval-matrix only | 9 non-matrix sectors (if needed) |
| **business** | **0** | **none** | **23** |
| **valuation** | **0** | **none** | **23** |
| **risk** | **0** | **none** | **23** |
| **technical** | **0** | **none** | up to **23** (mostly not needed — see §3) |
| **sector** | **0** | **none** | **23** |

### Company-name contamination in `prompts.py`

7 violations across SHARED_PREAMBLE, business, valuation (×2), risk, sector. Full list in §2.

---

## 2. Phase 1 — Agent Prompt Harmonization

Goal: every specialist prompt conforms to playbook 4.3. Two-stage approach (from prior review).

### Stage A — Scrub + minimal compliance gate (low risk, high leverage)

**A-1. Scrub 7 company-name contaminations in `prompts.py`:**

| Line | Location | Fix |
|---|---|---|
| 102 | SHARED_PREAMBLE | `"VEDL promoter pledge rose..."` → sector-generic pledge example |
| 154 | BUSINESS Rule | `"Zerodha, Groww, Angel One"` → "top 3 customers/channels" |
| 464 | VALUATION SOTP | `"ICICI → ICICI Pru Life/Lombard; Bajaj → Bajaj Finance; Tata → TCS/Titan"` → "banks with AMC/insurance arms; industrial conglomerates with listed subs" |
| 468 | VALUATION | `"Kotak research shows..."` → "sell-side research consistently shows..." |
| 496 | VALUATION | `"Info Edge/NAUKRI, Bajaj Finserv holds Bajaj Finance"` → "internet-platform holdcos with listed subs; financial-services holdcos consolidating lending arms" |
| 530 | RISK persona | `"IL&FS, Yes Bank, DHFL"` → "infrastructure NBFCs, mid-tier private banks, housing-finance majors that blew up in 2018-2019 stress" |
| 705 | SECTOR | `"Kotak research..."` → "sell-side research consistently shows..." |

**A-2. Add `mandatory_metrics_status` field to briefing JSON** for business, valuation, risk, technical, sector.

**A-3. Add single-line Sector Compliance Gate step** to each of their WORKFLOW sections. Reuses financials pattern.

**A-4. Cap `open_questions` at 3-5** with explicit language in the briefing schema comment.

**Deliverable:** 1 commit, ~30-50 line diff. Validated by grep (zero matches) + briefing schema check.

### Stage B — Add missing cross-agent invariants (deeper rework)

For each of business/valuation/risk/technical/sector, add these rules (adapted to domain):

| Invariant | Adaptation by agent |
|---|---|
| **I-1 Anomaly→tools first** | Business: "Before flagging an unexplained revenue-mix shift, call concall_insights." Valuation: "Before citing a valuation gap, resolve via peer decomposition." Risk: "Before flagging a governance risk, call filings." etc. |
| **I-3 Hard-evidence override** | All agents: "Before narratively reclassifying a system-computed signal (composite score, F-Score, technicals, sector-percentile), cite 2+ independent data points." |
| **I-4 Single-period reclassification-first** | Business: "An anomalous single-quarter margin spike may be accounting (mix, one-off) — verify before narrating business change." Sector: "A single-quarter sector-flow spike may be index rebalance — check before narrating." etc. |
| **I-5 Open-questions ceiling** | Universal: cap at 3-5 with prose reasoning in the rule |
| **I-6 Numerical source-of-truth** | All agents: dedicated INSTRUCTIONS section (lifted from financials/ownership). Valuation especially — the most math-heavy. |
| **I-7 Structural absence ≠ informational** | Risk: "A PSU with zero promoter buying is structural, not signal." Sector: "Low FII flow in a regulated sector may be statutory cap-binding." etc. |

**Deliverable:** 5 separate commits (one per agent), each ~40-80 line diff in prompts.py. Tests where applicable.

### Stage C — TOC-then-drill workflow conversion

Agents with multi-section tool calls that risk MCP truncation:

| Agent | Current | Fix |
|---|---|---|
| **business** | step 3 calls `get_fundamentals(['annual_financials','ratios','cost_structure'])` — ~10KB, safe today but no TOC reflex | Add TOC-first convention: call `get_fundamentals()` with no section to learn waves, then drill |
| **valuation** | step 5 calls `get_valuation(['snapshot','band','pe_history','wacc','sotp'])` — 5 sections | Split into logical waves; add TOC if needed |
| **risk** | step 2 calls `get_fundamentals(['annual_financials','ratios','quarterly_balance_sheet','rate_sensitivity','cost_structure','working_capital'])` — 6 sections | Convert to 2-wave call |
| **sector** | step 3 calls `get_peer_sector(['sector_overview','sector_flows','sector_valuations','peer_comparison','peer_metrics','peer_growth','benchmarks'])` — 7 sections | **HIGH PRIORITY** — likely already hitting MCP truncation. Add TOC mode to `get_peer_sector` tool, wave the calls |

**Deliverable:** 2-3 commits. `get_peer_sector` TOC mode may need tool-layer work (similar to `get_fundamentals` TOC we just built).

---

## 3. Phase 2 — Sector Skill File Buildout

### 3.1 Value Matrix — which (sector × agent) pairs need dedicated files

Not every combination needs a unique skill. Criteria for "needs a dedicated file":
- The sector has a meaningfully different analytical framework for this agent's domain
- Generic prompt + `_shared.md` is insufficient to reach A- grade
- A pure-play peer comparison would be wrong without sector-specific adjustment

Proposed matrix (✓ = file needed, ~ = thin file or use `_shared.md` only, ✗ = not needed):

| Sector | Business | Valuation | Risk | Technical | Sector |
|---|---|---|---|---|---|
| **bfsi** | ✓ | ✓ | ✓ | ~ | ✓ |
| **it_services** | ✓ | ✓ | ✓ | ~ | ✓ |
| **metals** | ✓ | ✓ | ✓ | ~ | ✓ |
| **platform** | ✓ | ✓ | ✓ | ~ | ✓ |
| **conglomerate** | ✓ | ✓ | ✓ | ✗ | ✓ |
| **telecom** | ✓ | ✓ | ✓ | ~ | ✓ |
| **real_estate** | ✓ | ✓ | ✓ | ~ | ✓ |
| **pharma** | ✓ | ✓ | ✓ | ~ | ✓ |
| **regulated_power** | ✓ | ✓ | ✓ | ~ | ✓ |
| **fmcg** | ✓ | ✓ | ✓ | ✗ | ✓ |
| **auto** | ✓ | ✓ | ✓ | ~ | ✓ |
| **insurance** | ✓ | ✓ | ✓ | ✗ | ✓ |
| **broker** | ✓ | ✓ | ✓ | ~ | ✓ |
| **chemicals** | ✓ | ✓ | ✓ | ~ | ✓ |
| *non-matrix sectors below (Phase 3)* | | | | | |
| amc | ✓ | ✓ | ✓ | ~ | ✓ |
| capital_goods | ✓ | ✓ | ✓ | ✗ | ✓ |
| exchange | ✓ | ✓ | ✓ | ✗ | ✓ |
| gold_loan | ✓ | ✓ | ✓ | ~ | ✓ |
| holding_company | ✓ | ✓ | ✓ | ✗ | ✓ |
| hospital | ✓ | ✓ | ✓ | ✗ | ✓ |
| merchant_power | ✓ | ✓ | ✓ | ~ | ✓ |
| microfinance | ✓ | ✓ | ✓ | ~ | ✓ |
| telecom_infra | ✓ | ✓ | ✓ | ✗ | ✓ |

**Eval-matrix total: 14 sectors × (business + valuation + risk + sector) = 56 files** mandatory, plus selectively 4-5 technical files = ~60 files.
**Non-matrix total: 9 sectors × 4-5 files = ~40 files.**
**Grand total: ~100 sector skill files.**

### 3.2 Playbook-compliant skill file template (per playbook §3.2)

Every new file must follow this skeleton:

```markdown
## {Sector Name} — {Agent Name} Agent

### {Section 1 — sub-type / archetype identification}
{1-2 sentences on why classifying sub-type matters here.}
{Bulleted sub-types OR archetype table (playbook §3.3) when sub-types diverge materially.}

### {Regulatory Boundaries — Mandatory Lookup} (IF sector has binding regulatory constraints)
{Table per playbook §3.3b.}

### {Section 2+ — mandatory analytical frameworks / metrics for this agent's domain}
{Prose-first paragraph on WHY. Bulleted metrics + tool refs inline. Thresholds as ranges.}

### {Valuation basis / risk basis / business model basis — one of these per agent}
{Which frameworks apply, which fail.}

### {Data-shape fallback} (when canonical KPIs likely to be missing)
{Per playbook §3.5b — "if sector_kpis returns schema_valid_but_unavailable, fall back to narrative extraction via concall management_commentary."}

### Mandatory {Sector-Agent} Checklist (optional, prose alternative to structured gate)
- [ ] {checklist items}

### Open Questions — {Sector}-Specific
- "{3-5 sector-specific open-question templates}"
```

**Length target: 40-80 lines per file** (playbook §3.6 P-7).

### 3.3 Agent-specific content required per sector file

**business.md** must cover:
- Sub-type archetype and typical business model
- Revenue decomposition (A × B levers)
- Moat typology for this sector (switching/network/scale/intangible/cost)
- Unit economics framework (per-unit, per-customer, per-order, per-transaction as appropriate)
- Capital-cycle position (for cyclicals)
- Sector-specific red flags for business quality

**valuation.md** must cover:
- Which multiple is primary (PE/PB/EV-EBITDA/NAV/P-EV/EV-ton/price-to-ARR) and why alternatives fail
- Historical band context (5-10Y range, current vs median)
- Sector-specific valuation adjustments (SOTP for holdcos, NAV discount for real estate, P/B for financials)
- Forward-multiple sanity checks
- Peer premium/discount decomposition for this sector

**risk.md** must cover:
- Sector-specific governance red flags (RPTs for promoter-heavy, pledge for conglomerates, auditor for small-caps)
- Regulatory risk taxonomy (RBI/SEBI/FDA/TRAI/CERC etc.)
- Operational-risk concentration (customer / geography / supplier / commodity)
- Sector-specific bear-case scenarios (what has historically caused 30-50% drawdowns in this sector?)
- Sector-specific stress tests (rate-rise for BFSI, FDA-ban for pharma, commodity crash for metals, etc.)

**technical.md** (only where sector has distinct technical traits) must cover:
- Sector-specific liquidity norms (real estate illiquid, BFSI high-ADV)
- Delivery-% interpretation quirks by sector
- Passive-flow vulnerability (large-caps heavily indexed)

**sector.md** must cover:
- Top-down macro context (rates, currency, commodity, regulatory tailwind/headwind)
- Sector cycle position (early growth / maturity / decline)
- Competitive hierarchy and market-share dynamics
- Sector-specific institutional-flow patterns
- Sector-specific structural shifts (technology, policy, demand patterns)

### 3.4 Generation method — subagent dispatch with Gemini review

Same pattern we used for ownership scrub and financials deepening:

**Per agent × sector file:**
1. **Draft phase** — Subagent reads `_shared.md`, the generic agent prompt, existing `financials.md` / `ownership.md` for format reference, and drafts the skill file per playbook template
2. **Gemini review** — Subagent sends draft + playbook compliance criteria to Gemini, collects gap analysis
3. **Revision** — Subagent applies Gemini feedback, re-verifies against playbook §3.6 principles
4. **Verification** — Orchestrator greps for company-name contamination, length check, structure check

**Parallelism budget:**
- 14 eval-matrix sectors × 4 agents (business/valuation/risk/sector) = 56 files
- Dispatch 4 subagents per batch (one per agent), each handling all 14 sectors sequentially
- Total: 4 parallel subagent runs, each ~30 min = 4 waves × 30 min = ~2 hours wall time
- OR: dispatch 14 subagents (one per sector), each handling all 4 agent files for that sector — 1 wave, ~45 min

### 3.5 Validation gating

No subagent-generated file is merged until:

- [ ] Passes grep for company-name contamination (playbook §4.2 pattern)
- [ ] Length 40-80 lines (playbook §3.6 P-7)
- [ ] Structure matches template §3.2 (has ≥5 required sections)
- [ ] Thresholds expressed as ranges, not single points
- [ ] No MUST/CRITICAL/NEVER
- [ ] References existing tools correctly (no hallucinated tool names/sections)
- [ ] Orchestrator spot-checks 3 random files per batch by reading them

---

## 4. Phase 3 — Non-eval-matrix Sectors

9 sectors not in eval matrix but present as dirs: amc, capital_goods, exchange, gold_loan, holding_company, hospital, merchant_power, microfinance, telecom_infra

**Question for prioritization:** should we cover these now or only when a stock in one of these sectors enters the eval matrix?

**Recommendation:** defer to Phase 5. The eval-matrix sectors are where grader feedback lands; we should stabilize those first and generalize patterns that surface.

---

## 5. Phase 4 — Validation Evals

After Phase 1 + Phase 2 eval-matrix completion:

**Full matrix eval:**
- `autoeval -a business` across all 14 sectors
- `autoeval -a valuation` across all 14 sectors
- `autoeval -a risk` across all 14 sectors
- `autoeval -a technical` across all 14 sectors
- `autoeval -a sector` across all 14 sectors

**Expected cost:** 14 × 5 = 70 agent runs + 70 Gemini grading calls = ~$70 + ~$20 Gemini = ~$90

**Success criteria:**
- 12/14 sectors at A- or higher per agent (matches financials bar)
- Zero company-name contamination in any skill file
- `mandatory_metrics_status` populated in every briefing

**Targeted remediation loop:** for any sector stuck at B+ or below, pull Gemini feedback, apply skill-file patch, re-run.

---

## 6. Execution Sequence

### Week 1 — Phase 1 Stage A + B
- Day 1: Stage A scrub + add `mandatory_metrics_status` (single PR, merge)
- Day 2-3: Stage B deeper invariants (5 PRs, one per agent, each reviewed separately)

### Week 2 — Phase 1 Stage C + Phase 2 scaffolding
- Day 1-2: TOC-then-drill for business/valuation/risk (prompt-level)
- Day 3: Add `get_peer_sector` TOC mode at tool layer
- Day 4-5: Dispatch subagent batch for eval-matrix sector×agent matrix (56 files)

### Week 3 — Phase 2 Gemini review + deepening
- Day 1-3: Gemini review pass — 14 sector × 4 agents = 56 review calls in 4 parallel batches
- Day 4-5: Apply review feedback

### Week 4 — Phase 4 Validation
- Day 1-3: Run full eval matrix on all 5 new-to-playbook agents
- Day 4-5: Targeted remediation for any sector-agent below A-

### Week 5+ — Phase 3 non-matrix sectors (optional, scope-dependent)

---

## 7. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Gemini review quality varies — some drafts may pass review but still fail eval | Run 1-2 test evals after Phase 2 before dispatching the rest; calibrate |
| Subagent drafts may not cohere across agents for the same sector — e.g., risk.md and business.md for BFSI might have inconsistent moat framings | Orchestrator runs a "coherence sweep" after subagent batch: reads all 5 files for 1 sector, flags contradictions |
| Company-name contamination sneaks in despite subagent instructions | Grep check is mandatory; any hit → sent back to subagent for scrub |
| Playbook itself has gaps that surface during generation | Treat playbook as living doc per its own Part 7; update as patterns emerge |
| `get_peer_sector` TOC work blocks Phase 2 sector.md generation | Decouple: sector.md drafts can reference the to-be-built TOC pattern without blocking on tool-layer work |
| Length bloat — subagent files exceed 80 lines | Orchestrator enforces line count; files over 80 lines get refactored with content split into `_shared.md` |

---

## 8. Definition of Done

- [ ] All 7 company-name contaminations in `prompts.py` scrubbed
- [ ] All 5 remaining agents have Sector Compliance Gate + `mandatory_metrics_status` + capped open-questions
- [ ] All 5 remaining agents have I-1 through I-7 invariants (adapted to domain)
- [ ] All 14 eval-matrix sectors have business / valuation / risk / sector skill files (technical selectively)
- [ ] Every new skill file passes playbook §4.2 grep check + structure check
- [ ] Full eval matrix run on 5 newly-harmonized agents returns 12/14 at A- per agent
- [ ] Playbook updated with any new patterns that emerged during generation
- [ ] `fix_tracker.md` updated with any per-sector Gemini-flagged fixes that apply cross-sector

---

## 9. Open Decisions for User

1. **Proceed with full Phase 1 + Phase 2 now**, or stage Phase 1 first with a re-eval gate before committing to Phase 2?
2. **Parallelism model** — 4 subagents × 14 sectors each, or 14 subagents × 4 agents each? Latter is faster but higher orchestration load.
3. **Coverage model for non-eval-matrix sectors** — defer to Phase 5 (recommended) or include in Phase 2 scope?
4. **Technical skill files** — minimal (5-7 files) or skip entirely and rely on generic + `_shared.md`?
5. **get_peer_sector TOC tool work** — block Phase 2 on this, or ship skill files with wave-call workflow guidance and add TOC mode later?
