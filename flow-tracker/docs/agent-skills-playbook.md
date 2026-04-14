# Agent Skills Playbook

**Status:** living document. This is the single source of truth for how to write agent system prompts and sector skill files. Follow it deterministically; deviations should be explicit and defensible.

---

## 1. Architecture at a Glance

The specialist-agent pipeline has **two layers** of prompt content, both written as Markdown-ish text:

```
AGENT_PROMPTS_V2[agent] = (SYSTEM, INSTRUCTIONS)
                                │
                                ├─ Generic prompt        ← Part A below
                                │   (persona + rules + workflow + briefing schema)
                                │
                                └─ Sector skill injection ← Part B below
                                    sector_skills/{sector}/{agent}.md
                                    sector_skills/{sector}/_shared.md  (optional)
```

**Generic prompt** is loaded unconditionally from `prompts.py`.
**Sector skill** is loaded conditionally by `build_specialist_prompt(agent, symbol)` based on the detected sector. It is appended to the system prompt.

---

## 2. Part A — Agent System Prompts (Generic)

Every agent prompt in `AGENT_PROMPTS_V2[agent_name]` is a `(SYSTEM, INSTRUCTIONS)` tuple. Both strings must follow the skeleton below.

### 2.1 SYSTEM string — required structure

```
# {Agent Display Name} Agent

## Persona
{2-3 sentences. Archetype: an institutional analyst with a specific background
and signature analytical reflex. Must evoke a point of view — not generic.}

## Mission
{One declarative sentence. "Decode X. Analyze Y. Produce Z."}

## Key Rules (Core Tenets)
1. **{Bolded principle}.** {1-3 sentences: what, when, and how — with tool/section references where relevant.}
2. ...
N. ...
```

### 2.2 INSTRUCTIONS string — required structure

```
## Tool Loading (optional — include only when tool registry is large)
{Hint to pre-load tools via ToolSearch, including calculate.}

## Workflow
0. **Baseline**: Review the <company_baseline> in the user message.
1. **Snapshot**: Call get_analytical_profile.
2. **Core data**: Call agent-specific primary tools.
3. **Management context**: Call get_company_context for concall_insights, sector_kpis.
...
7. **Visualizations**: Call render_chart for agent-relevant chart types.
8. **Investigate before writing**: Scan collected data for unexplained gaps.
   Resolve via tool calls before raising open questions.
9. **Sector Compliance Gate** (MANDATORY — SEE 2.4): Enumerate mandatory
   metrics from sector skill file and populate mandatory_metrics_status.

## Report Sections
1. **{Section name}** — {one-line content spec}
2. ...

## Structured Briefing
End with a JSON code block matching the schema in 2.4.
```

### 2.3 Cross-agent invariants (every specialist must have these)

These five rules appear — in the same spirit, adapted to the agent's domain — in **every** agent's SYSTEM prompt. Don't omit.

| # | Invariant | Financials equivalent | Ownership equivalent |
|---|---|---|---|
| **I-1** | **Anomaly resolution via tools first.** Before raising an open question, attempt 2+ tool calls. Open questions are for things genuinely outside tool data. | Rule 8 | Implicit in Rule 14 |
| **I-2** | **Sector Compliance Gate.** Populate `mandatory_metrics_status` with extracted/attempted/not_applicable for each mandatory metric in the sector skill file. `attempted` needs 2+ tool-call traces. | Rule 9 (workflow step) | Rule 16 |
| **I-3** | **Hard-evidence for overriding system signals.** When a system-classified signal (from `get_analytical_profile`, `get_market_context`, etc.) is reclassified, cite 2+ independent data points. One countervailing fact = speculation. | (add when missing) | Rule 13 |
| **I-4** | **Single-period anomaly → reclassification hypothesis first.** >5pp ownership jumps or >20% single-quarter P&L moves default to "corporate action / reclassification / accounting change" before "active directional". | (embedded in Rule 8) | Rule 11 |
| **I-5** | **Open-questions ceiling: 3-5 per report.** More than that = agent is punting resolvable lookups. | (embedded in Rule 8) | Rule 14 |

### 2.4 Briefing schema — required fields

Every agent's briefing JSON must include these fields (plus agent-specific fields):

```json
{
  "agent": "<agent_name>",
  "symbol": "<SYMBOL>",
  "confidence": 0.0,
  "<agent_specific_metrics>": "...",
  "key_findings": ["<finding1>", "<finding2>", "<finding3>"],
  "mandatory_metrics_status": {
    "<metric_name>": {
      "status": "<extracted|attempted|not_applicable>",
      "value": "<value with unit, or null>",
      "source": "<tool(section=...), or null>",
      "attempts": ["<tool_call_1>", "<tool_call_2>"]
    }
  },
  "open_questions": ["<question tied to a metric marked 'attempted' above>"],
  "signal": "<bullish|bearish|neutral|mixed>"
}
```

`mandatory_metrics_status` is non-negotiable — it makes compliance machine-gradable and unblocks the Gemini grader.

### 2.5 Agent-specific invariants

Domain-specific rules that also must be present per agent:

**Financials (`FINANCIAL_SYSTEM_V2`)** — Rules 13-16 cross-cutting earnings-quality lenses:
- Capitalization vs expensing discipline
- Cash conversion lie-detector (OCF/EBITDA, FCF/PAT, accrual ratio)
- IndAS 116 lease distortion
- Segment-level peer benchmarking

**Ownership (`OWNERSHIP_SYSTEM_V2`)** — already has 15 tenets; invariants include:
- Foreign-holding cap aggregation (FPI + ADR/GDR + NRI)
- SEBI MPS 75% rule — near-cap promoter silence is regulatory, not signal
- Institutional handoff pattern (FII exit + DII entry = medium-term bullish)
- ESOP Trust movements are structural

**Business (`BUSINESS_SYSTEM_V2`)** — required invariants include:
- Moat typology (switching cost / network effect / scale / intangible / cost advantage) distinct from market-share narrative
- Unit economics separate from aggregate P&L
- Cycle-phase awareness for cyclical sectors

**Valuation** — required invariants include:
- Multiple selection by sector archetype (not default PE)
- Discount-rate discipline (WACC, country-risk premium, equity risk premium)
- Bear/base/bull range over point target

**Risk** — required invariants include:
- Scenario branching (macro × micro × governance × regulatory)
- Tail-event awareness
- Quantified thesis-breakers

**Technical** — required invariants include:
- Trend + momentum + volume triangulation
- Anchored to fundamentals (don't flip technical-only bullish against fundamental bearish without caveat)
- Delivery % discipline

**Sector** — required invariants include:
- Top-down macro context (rates, currency, commodity)
- Structural shift awareness (policy, technology, demand)
- Relative positioning within sector

### 2.6 Persona archetypes — one per agent

| Agent | Persona |
|---|---|
| **financials** | Chartered accountant turned buy-side analyst — reads financials like a detective reads a crime scene. Specialty: DuPont decomposition, earnings-quality forensics, spotting buried one-time items. |
| **ownership** | Former institutional dealer turned ownership intelligence analyst — reads shareholding data like a tracker reads animal footprints. Specialty: institutional handoffs, smart money accumulation, pledge red flags. |
| **business** | Ex-strategy consultant turned investor — obsesses over competitive moats, unit economics, and capital-cycle position. Signature reflex: translating management commentary into durability-of-returns math. |
| **valuation** | Rates + credit-desk veteran turned equity analyst — discount-rate disciplined, wary of reflexive PE multiples. Signature reflex: stress-testing the terminal-growth assumption that's doing the lifting. |
| **risk** | Buy-side risk officer — scenario thinker, tail-event aware. Signature reflex: quantifying the thesis-breakers rather than just listing them. |
| **technical** | Quant-adjacent discretionary trader — chart and flow interpreter. Signature reflex: separating mechanical passive flow from active fundamental conviction. |
| **sector** | Sector specialist — macro top-down + structural-shift awareness. Signature reflex: distinguishing cyclical tailwind from structural-reset shift. |

---

## 3. Part B — Sector Skill Files

### 3.1 File location and naming

```
sector_skills/
  {sector}/                       # e.g., bfsi, pharma, real_estate
    _shared.md                    # optional: content applicable to ALL agents in this sector
    {agent}.md                    # e.g., financials.md, ownership.md
```

Sector names must match keys in `SECTOR_KPI_CONFIG` in `sector_kpis.py`.

### 3.2 Required skill file structure

```markdown
## {Sector Display Name} — {Agent Display Name} Agent

### {Section 1 — the sector-type identification / archetype section}
{1-2 sentences on why classifying the sub-type matters here.}
{Bulleted sub-types OR an archetype table (see 3.3).}

### {Section 2 — the first mandatory-metric group}
{Opening paragraph explaining WHY this metric matters for the sector.}
{Bulleted metrics with tool-call references inline.}

### {Sections 3-6 — additional mandatory metrics / frameworks}

### {Valuation basis section}
{Which multiples apply and why. What alternatives fail for this sector.}

### {Optional: Mandatory Checklist}
(See 3.4)

### {Optional: Open Questions — Sector-Specific}
(See 3.5)
```

### 3.3 Archetype table pattern (recommended when sub-types diverge materially)

```markdown
| Subtype | Typical profile | Key distinguishing metric | Valuation anchor |
| :--- | :--- | :--- | :--- |
| **{Subtype A}** | {range of parameter 1} | {metric specific to subtype} | {multiple} |
| **{Subtype B}** | ... | ... | ... |
```

Use when insurance (life / general / aggregator), broker (discount / full-service / wealthtech), holding (pure investment / operating), gold_loan (pure / diversified), etc.

### 3.4 Mandatory Checklist pattern (light-touch alternative to structured gate)

```markdown
### Mandatory {Sector} Checklist (Write Before Report)
Before drafting the final section, explicitly confirm each row:

- [ ] {Sub-type identified and stated}
- [ ] {Primary metric 1 extracted or attempted with trace}
- [ ] {Primary metric 2 ...}
- [ ] {Valuation basis anchored to correct multiple for this sector}
- [ ] {Sector-specific red flag check}
```

**Note:** the structured `mandatory_metrics_status` in the briefing (I-2 invariant) is **preferred** over the prose checklist because the grader can parse it. Prose checklists are a fallback when the agent otherwise has trouble self-enumerating.

### 3.5 Open Questions templates

```markdown
### Open Questions — {Sector}-Specific
Prefer these over generic questions:
- "{Question 1 that cannot be answered from tool data but materially affects thesis}"
- "{Question 2 ...}"
- "{Question 3 ...}"
```

Limit to 3-5 templates per skill file.

### 3.6 Consistency principles (non-negotiable)

**P-1. Sector-generic, never company-specific.**
- NO specific company names as illustrations ("SBIN", "HDFCBANK", "Bharti Airtel", "TCS", …)
- NO hardcoded point-in-time stakes (e.g., "SBIN's 55.5%")
- NO dated historical events (e.g., "HDFC-HDFCBANK 2023") — describe the pattern
- NO specific fund names (e.g., "Elara India Opportunities Fund") — describe the category

**KEEP:** statutory / regulatory references (SEBI, RBI, IRDAI, CERC, DoT, USFDA, FEMA, IndAS 38/115/116, Basel III, LODR clauses), government scheme names (PMJAY, CGHS, ECHS, FAME, PLI, AB-PMJAY), regulatory landmarks (LIC as an institution-category name, MSCI, FTSE, NIFTY), and sector concept terms (AGR, ANDA, NIM, GNPA, VNB, ARPOB, SHR, PAF, JDA, RERA, etc.).

**P-2. Prose-first, bullets second.**
- Each H3 section opens with a paragraph that explains WHY
- Bullets for enumerable metrics, thresholds, tool calls
- Don't open a section with a bulleted list

**P-3. Tool references always inline and always specific.**
- Good: ``"Extract `get_company_context(section='concall_insights', sub_section='operational_metrics')` — without this the report is analyzing backward-looking noise"``
- Bad: ``"Use concall insights"`` (no tool binding)
- Bad: ``"Call the tool"`` (no section/sub_section specificity)

**P-4. Thresholds as ranges, not single points.**
- Good: ``"Combined Ratio <100% = underwriting profit; >105% stressed"``
- Bad: ``"Combined Ratio must be exactly 97%"``

**P-5. Explain WHY, not just WHAT.**
- Good: ``"ARPU growth is irrelevant if network investment consumes all of it — the real question is what's left after capex"``
- Bad: ``"Track OpFCF"``

**P-6. No MUST / CRITICAL / NEVER directives.**
- Reasoning-led: ``"A report that cites only P/E and P/B for a real estate developer is incomplete"``
- Not directive: ``"You MUST use NAV"``

**P-7. Length budget: 40-80 lines.**
- Tight enough to fit in the agent's prompt without bloat
- Long enough to carry the sector's analytical texture
- If a file exceeds 80 lines, consider splitting: move cross-agent content to `_shared.md`

### 3.7 Minimum content checklist

Every sector skill file must cover:

1. **Sector-type identification** — how to recognize the sector's sub-types when multiple exist
2. **3-6 mandatory metrics** — agent is expected to extract these or mark as attempted
3. **Sector-specific distortions** — accounting quirks, regulatory artifacts, cyclical biases that mislead standard frameworks
4. **Valuation basis** — which multiples apply and why alternatives fail for this sector
5. **Red flags / risk indicators** — specific tells of governance or business stress for this sector

### 3.8 Recommended additions (when applicable)

- **Archetype typology table** (3.3) when sub-types diverge materially
- **Peer-benchmarking angles** specific to the sector
- **Cross-agent notes** (e.g., "Pledge data — from ownership agent's domain — cross-references this")
- **Historical cycle context** (for cyclical sectors)
- **Regulatory landmarks** (for regulated sectors)

---

## 4. Part C — Consistency Checks

### 4.1 Pre-commit checklist for a new or modified skill file

- [ ] No specific company names (see 3.6 P-1)
- [ ] No hardcoded point-in-time stakes or dates
- [ ] Every H3 section opens with prose, not a bullet
- [ ] Tool calls referenced inline with section/sub_section
- [ ] Thresholds expressed as ranges
- [ ] No MUST / CRITICAL / NEVER
- [ ] Length 40-80 lines
- [ ] Covers all 5 minimum content areas (3.7)

### 4.2 Grep command for company-name contamination

Run before every commit that touches `sector_skills/`:

```bash
grep -nErw --include="*.md" \
  "SBI|SBIN|HDFC|ICICI|Axis|PNB|BoB|Canara|Kotak|IDFC|Indusind|Federal|HUL|ITC|Nestle|Dabur|Marico|Britannia|Colgate|GCPL|Godrej|Tata|Reliance|Adani|Bharti|Airtel|Jio|Vodafone|VIL|Indus|TCS|Infosys|Wipro|INFY|Mahindra|Maruti|Bajaj|Hero|TVS|Ola|Zomato|Swiggy|Nykaa|Paytm|Policybazaar|Sun Pharma|SUNPHARMA|Cipla|Lupin|Dr Reddy|Aurobindo|Divi|Vedanta|VEDL|NMDC|Hindalco|JSW|SAIL|NTPC|Torrent|JSW Energy|Muthoot|Manappuram|LIC|SBI Life|HDFC Life|ICICI Pru|Max Life|Apollo|Fortis|Medanta|Max Health|GROWW|Zerodha|Angel|Motilal|Pidilite|Asian Paints|SRF|UPL|Aarti|Atul|Navin|Deepak Nitrite|PI Industries|Godrej Properties|GODREJPROP|DLF|Oberoi|Prestige|Brigade|Sobha|Lodha|Macrotech|Phoenix|Elara|ETERNAL|OLAELEC|POLICYBZR|Ambuja|ACC|Hindenburg|Satyam|Unitech|Jaiprakash|Zee|Essel" \
  sector_skills/
```

Must return zero matches. Government schemes (PMJAY, CGHS, FAME, PLI), regulators (RBI, SEBI, IRDAI), and LIC as a category name are preserved — they are NOT company references.

### 4.3 Cross-agent audits (periodic)

Verify for each specialist agent in `AGENT_PROMPTS_V2`:

- [ ] SYSTEM prompt has all 5 cross-agent invariants (2.3)
- [ ] SYSTEM prompt has agent-specific invariants (2.5)
- [ ] INSTRUCTIONS workflow ends with a Sector Compliance Gate step
- [ ] Briefing schema includes `mandatory_metrics_status` and caps `open_questions` at 3-5
- [ ] Persona matches the archetype in 2.6

---

## 5. Part D — When to Add / When Not to Add

### 5.1 When to add a sector skill file

**Add when:**
- The sector has accounting or economic quirks the generic prompt doesn't handle
- Peer comparisons require sector-specific benchmarks
- Sub-types within the sector have materially different metrics
- An eval on a sector member has flagged a pattern that applies to all members

**Don't add when:**
- The sector is well-covered by generic rules
- The observation is company-specific, not sector-specific
- The guidance would be a single-line addition — put it in the generic prompt instead

### 5.2 When to modify the generic agent prompt

**Modify when:**
- The pattern applies across 3+ sectors
- The rule is a cross-cutting earnings-quality / ownership / valuation / risk principle
- Eval feedback shows the same gap across multiple sector evals

**Don't modify when:**
- The pattern is specific to one sector — put it in that sector's skill file
- The rule is already covered — edit the existing tenet instead

### 5.3 When to add content to `_shared.md` vs `{agent}.md`

Use `_shared.md` when the content applies to **every** specialist analyzing this sector (e.g., sector-wide cycle context, a mode-activation banner, sector-wide regulatory landmarks).

Use `{agent}.md` when the content is specific to one agent's domain (e.g., financial-ratio definitions for financials, pledge-calculation nuances for ownership).

When in doubt: start in `{agent}.md`. If you find yourself copying the same paragraph into 3+ agent skill files for the same sector, refactor into `_shared.md`.

---

## 6. Part E — Worked Examples (reference patterns)

**Good sector file examples (adhere to all principles):**
- `sector_skills/bfsi/financials.md` — archetype-free, ranges, inline tools, WHY-first
- `sector_skills/pharma/financials.md` — geography-first structure
- `sector_skills/real_estate/financials.md` — handles standard-framework invalidation elegantly (DuPont / CFO / PAT caveats)
- `sector_skills/insurance/financials.md` — three-sub-type branching (aggregator / life / general)

**Good generic-prompt examples:**
- `FINANCIAL_SYSTEM_V2` — Rules 13-16 demonstrate cross-cutting earnings-quality tenets
- `OWNERSHIP_SYSTEM_V2` — Rules 11, 13, 14, 16 demonstrate the invariants from 2.3

---

## 7. Change Log

Record changes to this playbook as numbered entries when they happen:

- **2026-04-15 — v1.0**: Initial playbook created covering financials + ownership agents plus archetype/pattern guidance for the 5 remaining specialist agents.
