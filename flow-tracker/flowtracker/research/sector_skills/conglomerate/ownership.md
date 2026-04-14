## Conglomerate — Ownership Agent

### Public Float Sub-Breakdown — Mandatory for Conglomerates
The 'Public' shareholding bucket (the non-promoter, non-institutional holders) lumps together **retail investors (<2 lakh shares), Corporate Bodies/HNIs, and high-networth individuals** — three categories with very different signal value. For conglomerates with complex group structures (Adani, Reliance, Bajaj family, Tata, Mahindra), this sub-breakdown is a **mandatory analytical dimension**, not optional colour.

**Why this matters specifically for conglomerates:**
- Shell companies and related-party entities typically sit inside the 'Corporate Bodies' sub-bucket, not the promoter line
- Historical governance incidents (Adani-Hindenburg 2023, Satyam, some Unitech issues) involved Corporate Body holdings that turned out to be promoter-linked offshore vehicles
- A "free float" that is 60% Corporate Bodies is materially different from 60% retail — the former concentrates voting power, the latter disperses it

**How to extract:**
- `get_ownership(section='shareholder_detail', classification='Public')` — returns named Public holders above the 1% disclosure threshold with their classification. Corporate Body entries will include company names (e.g. "Elara India Opportunities Fund", "LTS Investment Fund").
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
Conglomerates often have multiple listed entities within the group (Adani Enterprises / Adani Ports / Adani Green / Adani Power / Adani Transmission / Adani Wilmar, etc.). When analyzing ownership of the parent, also check:

- Does the promoter hold the same %/value across all group entities?
- Are FII/DII stakes correlated across group entities (group-level flow) or divergent (single-entity specific)?
- Is the parent holding company itself inside any of the listed subsidiaries' promoter line?

Use `get_valuation(section='sotp')` for the listed-subsidiary map. If a group-level FII exit occurs, it usually hits ALL listed entities simultaneously — track the correlation.

### Promoter Pledge — Conglomerate-Specific Framing
The `margin_call_analysis` in `get_ownership(section='promoter_pledge')` already computes trigger prices. For conglomerates:

- Aggregate pledge across group entities, not just the current ticker — a 2% pledge in Adani Enterprises may look benign until you see 40% in Adani Power
- Cite the specific pledged-value Cr at current market price, and the net-debt-to-promoter-equity ratio if known
- Call out **Non-Disposal Undertakings (NDUs)** explicitly — conglomerates are the most common users of NDU structures to bypass pledge disclosure

### Hindenburg / Short-Report Resilience Check
For groups that have been subject to short-seller or short-report scrutiny (Adani, Vedanta, Indiabulls historically), include a specific sub-section:

- FII trajectory pre-report / during-report / post-report (did sovereigns re-enter?)
- DII trajectory (LIC, SBI MF — did they hold or buy?)
- Promoter pledge trajectory (did encumbrance rise to fund margin calls?)
- Any related-party Corporate Body holders named in the report still present?

### Mandatory Conglomerate Checklist (Write Before Report)
Before drafting the Institutional Verdict, explicitly confirm each row:

- [ ] Public bucket broken out: Retail / Corporate Bodies / HNIs (top 3 named corporates if >1% each)
- [ ] Any single Corporate Body >2% flagged with governance risk classification
- [ ] Listed subsidiary map from `get_valuation(section='sotp')` checked for cross-entity patterns
- [ ] Promoter pledge + NDU status stated with specific ₹ Cr pledged value and trigger price
- [ ] Short-report resilience: FII/DII/pledge trajectory across the incident window (if applicable)
- [ ] LIC / SBI MF / ICICI MF — domestic quasi-sovereign anchor position stated (even if 0%)

### Open Questions — Conglomerate-Specific
Prefer these over generic ones:

- "Is any named Corporate Body holder above 1% registered as an offshore fund with prior connection to the promoter group? (RTI / filings lookup)"
- "What is the promoter's aggregate pledge across all group-listed entities (not just this ticker)? SEBI disclosure requires per-entity but group aggregate is the real risk metric."
- "Are there pending SEBI proceedings / ED investigations that could trigger FPI reclassification or Corporate Body deemed-promoter tagging?"
- "Has any short report (Hindenburg, Adani Watch, others) flagged specific Corporate Body holders — and are those holders still on the register?"
