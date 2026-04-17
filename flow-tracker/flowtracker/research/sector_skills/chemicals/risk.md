## Chemicals — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across chemicals sub-types. For specialty it is molecule/client concentration and process-IP erosion; for CRAMS it is innovator-client insourcing and patent cliffs; for commodity bulk it is China dumping and feedstock-spread compression; for agrochem it is monsoon and regulatory-deregistration; for fluorochem it is Montreal Protocol phase-down cadence; for pigments/dyes it is REACH restriction-list extensions and global textile demand; for custom synthesis it is single-molecule plant concentration. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in chemicals surfaces earlier through balance-sheet and segment-reporting telemetry than through board drama. Scan for:
- **Group-company related-party KSM or intermediate purchases** — a listed chemicals name sourcing 20-40% of its key starting material from a promoter-group entity at transfer-price is the single most common governance red flag. Margin flattery today becomes a valuation re-rate the quarter it is disclosed. Cross-check via `get_ownership(section='shareholder_detail')` and annual report related-party schedules.
- **Rapid capex without disclosed IRR or commissioning timeline** — capex-to-revenue >25% for 2+ years with vague "multi-year growth capacity" language rather than specific IRR targets, phase-gate milestones, or anchor-customer contracts.
- **Promoter-pledge in mid-cap specialty** — baseline is <5% for specialty per the chemicals ownership archetype. Pledge above 8-10% in a specialty name is a liquidity-stress tell; the same range is near-baseline in commodity chemicals, which routinely sit at 5-15% without distress signal due to cyclical working-capital borrowing. Cite the sub-type before narrating pledge severity. Verify via `get_ownership(section='promoter_pledge')`.
- **Segment-reporting opacity** — pulling specialty and commodity segments into a single P&L, or discontinuing prior molecule-tier disclosure, is a diagnostic hole that often precedes margin disappointments.
- **Auditor qualification on inventory valuation or goodwill** — capex-heavy chemicals with frequent bolt-on M&A carry real goodwill and intangibles; qualifications on either are forensic-grade tells. Cross-check via `get_events_actions(section='material_events')`.

### Regulatory Risk Taxonomy — Cite the Specific Regime
Regulatory risk in chemicals is concrete, not vague. Tie each risk to the specific regulator and, where possible, the specific directive:
- **CPCB / State Pollution Control Boards (SPCBs)** — effluent treatment plant (ETP) norms, zero-liquid-discharge mandates in water-stressed zones (Gujarat, Tamil Nadu, Telangana clusters), hazardous-waste rules, air-emissions standards. Non-compliance triggers show-cause notices, closure notices, or temporary shutdowns.
- **REACH (EU)** — registration requirements for any molecule exported to the EU; restriction-list extensions (SVHC candidates, authorisation list) periodically deregister flagship molecules and force product-mix resets.
- **TSCA (US)** — Toxic Substances Control Act registrations for US exports; EPA-level enforcement on specific molecule families.
- **USFDA cGMP** — pharma-intermediate plants require cGMP-compliant facilities; Form 483 observations, warning letters, or import alerts trigger revenue halts for affected molecule-plant combinations.
- **CII / BIS standards** — domestic product quality norms relevant for agrochem and industrial specialty.
- **Montreal Protocol HFC phase-down** — structurally reshapes the fluorochem portfolio over 5-10 years; HFC-23 byproduct rules and HFO transition capex are sub-sector-defining rather than cyclical.

Name the relevant regime when the risk crystallises; vague "environmental regulations" framing loses the traceability that makes the risk actionable.

### Operational-Risk Concentration
Chemicals risk concentration is rarely balanced — the "diversified portfolio" narrative masks single-point failures:
- **Single-plant concentration** — specialty and fluorochem names frequently have 50-70% of output at one large integrated complex. A fire, ETP shutdown, or major compliance incident takes out half the P&L for 6-18 months.
- **KSM / intermediate import dependency on China** — >60% for some molecule families. Even with 2-3 steps of backward integration, the earliest steps in the chain often remain China-dependent. A China policy shock (2020, 2022, 2023 episodes) disrupts supply for 2-4 quarters.
- **Single-customer in CRAMS / specialty** — top-1 customer share >25% of segment revenue is single-event risk. Innovator insourcing, portfolio rationalization, or quality-failure events are the historical rupture triggers.
- **Single-molecule concentration in CRAMS** — top-1 molecule share >30% of segment EBITDA means the entire margin profile rides on one patent window and one customer's commercial strategy.
- **ETP / effluent non-compliance shutdown risk** — state-level closure orders in water-stressed chemical clusters have historically been sudden (3-7 day enforcement window) and lasted 6-12 months.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical chemicals drawdowns have recurring triggers; use these as the bear-case scaffolding:
- **China-restart flooding specialty supply** — happened in 2023 for several specialty molecules; compressed realization 20-40% and EBITDA margins 600-1200 bps in affected sub-sectors within 2-3 quarters.
- **Innovator-customer insourcing a flagship molecule** — structural CRAMS risk; typical revenue loss 15-30% of segment, EBITDA loss disproportionately higher because the lost molecule was a margin-leader.
- **Environmental-incident plant shutdown** — 6-18 month revenue gap, plus remediation capex of ₹50-300 Cr, plus reputational damage affecting customer qualification cycles.
- **REACH restriction-list addition** — deregistration of a flagship molecule from EU markets closes 20-40% of revenue for the affected molecule and forces inventory writedowns.
- **Feedstock-spread compression in commodity bulk** — a 20-30% input cost spike without realization pass-through can halve reported EBITDA within a single quarter.
- **Monsoon-drought in agrochem** — 15-25% volume drop at formulation level, plus channel-inventory writedowns, plus receivable-days blowout from distressed dealers.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "EBITDA/tonne falling below through-cycle floor" or "top-1 molecule share crossing 35% without diversification capex announced").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **15% volume drop at 65% capacity utilization** — margin drops 400-700 bps for specialty; 600-1000 bps for commodity bulk (higher operating leverage).
- **KSM cost +25% without realization pass-through** — gross margin compression of 300-500 bps for specialty, 500-900 bps for commodity.
- **INR +5% vs USD on a 50% export mix** — top-line translation drag of 2.5% and gross-margin drag of 150-250 bps for unhedged exporters.
- **Single-molecule loss of top-1 CRAMS customer** — segment revenue loss of 20-35% with disproportionate EBITDA loss (margin-mix impact).
- **ETP shutdown at the largest plant for 6 months** — revenue loss of 25-35% of annual, plus remediation capex 100-300 Cr.

Route the arithmetic through `calculate` with volume delta, KSM cost delta, and currency delta as named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='chemicals')` returns missing utilization, single-plant share, or customer-concentration, the concall extractor did not capture these in `operational_metrics`. Fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='management_commentary')` for management-disclosed qualitative ranges; (2) `get_company_context(section='filings')` for the most recent BSE disclosure including CPCB correspondence; (3) `get_events_actions(section='material_events')` for governance events, plant incidents, and auditor transitions. Cite the source quarter for every extracted number. Do not fabricate molecule or customer concentrations — the risk agent's credibility depends on citing what the company actually disclosed.

### Open Questions — Chemicals Risk-Specific
- "What is the current top-1 and top-3 molecule revenue share within the specialty / CRAMS segment, and has it trended up or down over the last 8 quarters?"
- "What share of the largest plant contributes to consolidated EBITDA, and what ETP / environmental compliance events have been disclosed over the last 2 years?"
- "Is there any CPCB / SPCB show-cause or closure notice active at any operating plant, and what is the remediation timeline?"
- "What percentage of KSM / intermediate needs remains China-dependent after disclosed backward-integration capex commissions?"
- "For fluorochem: where does the portfolio sit on the HFC-to-HFO transition curve, and what is the capex-return profile (no dedicated PLI for fluorochem is notified as of FY26, so model returns on unincentivised HFO capex)?"
