## IT Services — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not uniform across IT services sub-types. For tier-1 services it is US-discretionary-spend cycle and AI-disruption pricing pressure; for mid-cap specialists it is top-5 client concentration and vertical-cycle beta; for ER&D it is regulated-vertical compliance and single-customer-platform risk; for platform/product it is churn and CAC-payback deterioration; for IT consulting / GCC disruptors it is captive-insourcing competition. State the sub-type's dominant risk axis in the opening paragraph before enumerating generic risks.

### Sector-Specific Governance Red Flags
Governance stress in IT services surfaces through ownership and capital-allocation patterns more than through board drama:
- **Chronic ESOP dilution >1% per year** — particularly for mid-caps during attrition-spike years. Structural dilution masks per-share growth; share-count normalisation is required before per-share metric comparisons. Cross-check via `get_ownership(section='shareholder_detail')` and `get_events_actions(section='corporate_actions')` for buyback history offsetting dilution.
- **Promoter-driven mid-caps with family-trust complexity** — layered holding structures (founder-family investment vehicles, private trusts) create related-party complexity. Trace UBO via `get_ownership(section='shareholder_detail')`; flag when trust-structure opacity prevents clean UBO mapping.
- **Related-party services** between the listed entity and private family businesses (real-estate leases, IT services to captive group entities) at non-arm's-length pricing. Cross-check via `get_company_context(section='filings')` for annual-report RPT disclosures.
- **Subsidiary governance in US-acquired entities** — IT services companies frequently acquire US consultancies and retain the target management under earn-out structures. Subsidiary governance gaps (separate audit, delayed integration) surface as goodwill write-downs 2-3 years post-acquisition.
- **Auditor qualifications or rotation** timed with revenue-guidance misses are informational; qualifications on revenue recognition or deferred costs are forensic-grade tells.

### Regulatory Risk Taxonomy — Cite the Specific Rule
Regulatory risk in IT services is concrete; tie each risk to the regulator and the specific rule where possible:
- **US immigration** — H-1B visa cap (65k + 20k US Masters exemption), L-1 intra-company transfer rules, H-1B spouse (H-4) work authorisation, proposed merit-based reforms. US administration changes drive policy swings — the Trump-era 2017-20 pattern (RFI volume, denial rates, USCIS interpretive memos) materially raised onshore cost base and pressured offshore-onshore mix.
- **Indian SEZ sunset** — the SEZ Act income-tax holiday sunset (effective post-April 2020 for new SEZ units) compressed the margin tailwind that top-tier vendors historically enjoyed. Legacy SEZ units retain benefits until their individual sunset.
- **GST services treatment** — export-of-services GST refund cycle (typically 6-9 months) ties up working capital; any rule change in the place-of-supply interpretation for offshore-delivered services is a P&L event.
- **IT Act intermediary rules** — for platform companies and BPO/KPO with user-facing UX, Section 79 safe-harbour revisions tighten liability exposure.
- **State IT-park subsidies** — Karnataka, Tamil Nadu, Telangana, Maharashtra periodically revise IT-park tax incentives; multi-state vendors must model the subsidy-mix.
- **EU data regulations** — GDPR, Data Act, AI Act apply to services delivered into EU clients; compliance uplift is a margin drag for EU-revenue-heavy vendors.

Name the specific rule or framework when the risk crystallises; vague "regulatory risk" framing loses the traceability that makes the risk actionable.

### Operational-Risk Concentration
Concentration risk is the quietest risk in IT services because aggregate portfolios look diversified until a single vertical or client moves:
- **Top-5 client concentration** — >40% share exposes the book to any one client's insourcing decision, cost-takeout round, or M&A-driven vendor consolidation. For mid-caps, >50% is a structural discount driver.
- **Single-vertical concentration** — BFSI-heavy (>40% of revenue) during a banking stress cycle compresses growth 500-800 bps; healthcare-heavy during US Medicare-rate-revision cycles; retail-heavy during discretionary-soft phases.
- **US-geography concentration** — tier-1s draw 55-65% of revenue from the US; mid-caps often >70%. US-recession exposure dominates; a EU/UK recession is a secondary shock on ~20-30% of revenue.
- **Talent-skill concentration** — cloud-migration, AI/ML, data-engineering skills are priced at 40-80% wage premiums to generalist services. A vendor under-hiring in these skills loses deal competitiveness; one over-hiring pays margin tax.
- **AI-productivity erosion of pricing power** — classic T&M work shrinks billable hours as GenAI tools enter enterprise workflows; vendors without fixed-fee / outcome-linked exposure face structural pricing pressure in 2026-28.

### Bear-Case Scenarios — 20-40% Drawdown Triggers
Historical IT-services drawdowns have recurring triggers:
- **US recession -3-5% GDP** — discretionary IT services spend typically cuts 10-15% in the first 2-3 quarters; tier-1 USD growth -3-5pp and margin -100-200 bps. Historical references: 2008-09 (USD growth flat, margin -300 bps), 2020 COVID (2-quarter collapse then V-shape).
- **H-1B / visa tightening cycle** — onshore cost spike 200-400 bps as subcontracting and local-hire costs rise; offshore-onshore mix-shift can take 4-6 quarters to recalibrate.
- **AI-productivity re-pricing** — fixed-fee / outcome-based replaces T&M on ~15-25% of legacy book over 2-3 years; short-term revenue contracts 5-8% before volume expansion catches up on reduced unit pricing.
- **BFSI-client stress (2008-09, 2020-style)** — discretionary cut 20%+ from BFSI clients drops vertical-heavy mid-caps 30-40%; diversified tier-1s drop 15-25%.
- **Large-client insourcing / vendor consolidation** — a single top-10 client losing 30-50% of share to insourcing or GCC build-out is a single-quarter revenue hit 2-4% for a mid-cap.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "BFSI-vertical CC growth turning negative for 2 consecutive quarters" or "top-5 client CC growth -10% QoQ").

### Sector-Specific Stress Tests
Quantify sensitivity, don't just describe it:
- **USD-revenue -5% sensitivity** — operating leverage is roughly 1.3-1.5× on the downside for tier-1s (22% operating margin, fixed-cost base of rent + tech + management), so PAT -7-8%.
- **INR 5% move (exporter currency impact)** — roughly 3-4% on the reported margin; CC revenue strips this. Hedging-gain recognition often masks the underlying impact for 2-3 quarters.
- **Wage inflation +300 bps** — margin hit 200-250 bps at 60% employee-cost-to-revenue ratio, partly offset by pyramid-optimisation (fresher hiring) within 2-3 quarters.
- **Utilisation -200 bps sustained** — margin -60-100 bps; reversing requires either demand pickup or restructuring charge.
- **Attrition +500 bps above peer** — hidden replacement-hiring cost typically 30-50% of annual compensation for the replaced role; margin -50-120 bps over 3-4 quarters.

Route the arithmetic through `calculate` with named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='sector_health')` returns missing DSO, attrition, or utilisation, fall back in order: (1) `get_company_context(section='concall_insights', sub_section='operational_metrics')` for management-disclosed quarter-end metrics; (2) `get_company_context(section='filings')` for the most recent BSE disclosure and annual-report risk-factor section; (3) `get_events_actions(section='material_events')` for governance events, auditor transitions, large-client announcements. Cite the source quarter for every extracted number. Do not fabricate attrition, utilisation, or client-concentration metrics — credibility depends on citing what the company actually disclosed.

### Open Questions — IT Services Risk-Specific
- "What is the top-5 client revenue share, and is it trending up or down over the last 4 quarters?"
- "For BFSI-heavy vendors: what share of BFSI revenue comes from top-10 US / EU banks, and what is the current discretionary-spend-cut disclosure?"
- "Is the H-1B visa approval rate and onsite-mix trajectory consistent with historical, or is there a structural shift upward in onshore cost?"
- "What share of current revenue sits in classic T&M work exposed to AI-productivity re-pricing vs fixed-fee / outcome-linked / platform IP insulated from the disruption?"
- "Are any regulatory draft circulars (US H-1B reforms, EU AI Act implementation, Indian SEZ sunset phase) in public consultation that would materially reprice the cost base over the next 4-8 quarters?"
