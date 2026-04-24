## Conglomerate — Ownership Agent

### Public Float Sub-Breakdown — Mandatory for Conglomerates
The 'Public' shareholding bucket (the non-promoter, non-institutional holders) lumps together **retail investors (<2 lakh shares), Corporate Bodies/HNIs, and high-networth individuals** — three categories with very different signal value. For conglomerates (large Indian conglomerate groups with complex multi-entity structures), this sub-breakdown is a **mandatory analytical dimension**, not optional colour.

**Why this matters specifically for conglomerates:**
- Shell companies and related-party entities typically sit inside the 'Corporate Bodies' sub-bucket, not the promoter line
- Historical governance incidents (short-seller scrutiny events, past accounting-fraud exposures) involved Corporate Body holdings that turned out to be promoter-linked offshore vehicles
- A "free float" that is 60% Corporate Bodies is materially different from 60% retail — the former concentrates voting power, the latter disperses it

**How to extract:**
- `get_ownership(section='shareholder_detail', classification='Public')` — returns named Public holders above the 1% disclosure threshold with their classification. Corporate Body entries may include named offshore funds that have appeared in short-reports or SEBI proceedings.
- Cross-reference `get_company_context(section='filings')` for related-party disclosure filings that identify any Corporate Body holder as a group entity
- If a single Corporate Body holds >2% of the company, treat as material and name it explicitly in the report

**Reporting structure:**

| Public sub-category | % | Key names | Signal |
|---|---|---|---|
| Retail (<2L shares) | — | (aggregate) | dispersed holder base; low governance concentration |
| Corporate Bodies / Trusts | — | top 3 named | material if >5% aggregate; check for related-party linkages |
| HNIs / high-conc individuals | — | top 3 named | check for deemed-promoter classification history |

If Corporate Bodies account for >10% of total equity, flag it in the Institutional Verdict section as "concentrated-Public-float risk" — it's effectively a second promoter layer, not a true free float.

### Listed Subsidiaries — Cross-Entity Ownership Check
Conglomerates often have multiple listed entities within the same group (parent + several listed operating subsidiaries spanning ports/power/transmission/consumer verticals, etc.). When analyzing ownership of the parent, also check:

- Does the promoter hold the same %/value across all group entities?
- Are FII/DII stakes correlated across group entities (group-level flow) or divergent (single-entity specific)?
- Is the parent holding company itself inside any of the listed subsidiaries' promoter line?

Use `get_valuation(section='sotp')` for the listed-subsidiary map. If a group-level FII exit occurs, it usually hits ALL listed entities simultaneously — track the correlation.

### Promoter Pledge — Conglomerate-Specific Framing
The `margin_call_analysis` in `get_ownership(section='promoter_pledge')` already computes trigger prices. For conglomerates:

- Aggregate pledge across group entities, not just the current ticker — a 2% pledge in the parent/flagship entity may look benign until you see 40% in a group power/infrastructure subsidiary
- Cite the specific pledged-value Cr at current market price, and the net-debt-to-promoter-equity ratio if known
- Call out **Non-Disposal Undertakings (NDUs)** explicitly — conglomerates are the most common users of NDU structures to bypass pledge disclosure

### Short-Report Resilience Check
For groups that have been subject to short-seller scrutiny events, include a specific sub-section:

- FII trajectory pre-report / during-report / post-report (did sovereigns re-enter?)
- DII trajectory from major domestic institutional anchors (LIC, quasi-sovereign MFs — did they hold or buy?)
- Promoter pledge trajectory (did encumbrance rise to fund margin calls?)
- Any related-party Corporate Body holders named in the report still present?

### Mandatory Conglomerate Checklist (Write Before Report)
Before drafting the Institutional Verdict, explicitly confirm each row:

- [ ] Public bucket broken out: Retail / Corporate Bodies / HNIs (top 3 named corporates if >1% each)
- [ ] Any single Corporate Body >2% flagged with governance risk classification
- [ ] Listed subsidiary map from `get_valuation(section='sotp')` checked for cross-entity patterns
- [ ] Promoter pledge + NDU status stated with specific ₹ Cr pledged value and trigger price
- [ ] Short-report resilience: FII/DII/pledge trajectory across the incident window (if applicable)
- [ ] LIC / domestic quasi-sovereign MF anchor position stated (even if 0%)

### Open Questions — Conglomerate-Specific
Prefer these over generic ones:

- "Is any named Corporate Body holder above 1% registered as an offshore fund with prior connection to the promoter group? (RTI / filings lookup)"
- "What is the promoter's aggregate pledge across all group-listed entities (not just this ticker)? SEBI disclosure requires per-entity but group aggregate is the real risk metric."
- "Are there pending SEBI proceedings / ED investigations that could trigger FPI reclassification or Corporate Body deemed-promoter tagging?"
- "Has any published short report flagged specific Corporate Body holders — and are those holders still on the register?"

### Planned Public Float Sub-Breakdown Tooling
**Public float sub-breakdown tooling:** Once `get_public_float_breakdown(symbol)` (planned in Phase 1 of post-overnight-fixes) lands, use it to split the Public bucket into retail (<₹2L nominal), HNI (>₹2L), corporate bodies, NRIs, and trusts. Until the pipeline ships, cite the top-named holders from `shareholder_detail` with classification='public' as the best available proxy and flag the aggregate sub-breakdown gap as a data limitation (not an open question).

### Conglomerate FII Anchor Events — Canonical Search Worked Pattern
Conglomerate ownership narratives are frequently dominated by a single multi-quarter FII-group anchor — a sizeable structured entry by one institutional investor that persists across several quarters and defines the foreign-flow framing. The default `get_ownership(section='bulk_block', days=365)` window is insufficient; widen to `days=1825` when the anchor event sits beyond the trailing year, otherwise the defining trade disappears from the record. The *full 5-source canonical search* applies once the anchor entry date is triangulated.

1. `get_company_context(section='filings', query='open market|bulk deal|block deal|preferential allotment')` — exchange disclosures carrying the anchor's acquisition-day SEBI reporting and any preferential-allotment resolutions.
2. `get_company_context(section='documents', query='anchor|strategic investor|capital raise|preferential allotment')` — press releases announcing the anchor institutional entry, the structured-investment rationale, and any co-investor roster.
3. `get_company_context(section='concall_insights', sub_section='management_commentary')` — capital-raise rationale, use-of-proceeds, and management's own framing of the anchor's strategic intent (passive bet vs long-cycle aligned capital).
4. `get_ownership(section='shareholder_detail')` — the anchor's stake trajectory across subsequent quarters; subsequent top-ups or trims materially change the narrative.
5. `get_fundamentals(section='balance_sheet_detail')` — *skip — not applicable to anchor-entry analysis* (anchor buys in the secondary market or via preferential allotment; share count changes only on fresh issue).

If the anchor's SEBI filing is older than the default window, raise a SPECIFIC open question naming the investor and quarter (e.g. *"GQG March 2023 block deals on ADANIENT — `bulk_block(days=365)` returns empty; rerun with `days=1825` to recover the defining entry?"*) rather than a generic "who are the FII holders?".

*Pattern applies to*: ADANIENT ↔ GQG Partners 2023 anchor, Adani Green ↔ IHC (International Holding Co) structured investment, Vedanta ↔ Twin Star / Volcan Investments — same 5-source path whenever the ownership narrative invokes a named multi-quarter FII-group anchor.

### Historical-MCAP Discipline for Conglomerate FII %pt Conversions
Conglomerates holding cyclical or resource-exposed verticals (ports, power, metals, airports) have endured episodic mcap compressions and expansions of 3-5x within a 24-month window; converting a historical FII %pt shift to ₹Cr against the current mcap systematically misstates the flow. Always pass `inputs_as_of` / `mcap_as_of` to `calculate()` when sourcing pre-rerating %pt changes. See Tenet 16.
