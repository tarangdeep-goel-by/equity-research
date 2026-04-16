## Telecom — Risk Agent

### Sub-type Archetype — Dominant Risk Axis Differs
The dominant risk axis is not the same across telecom sub-types. For integrated wireless operators it is regulatory overhang (AGR, spectrum auctions) + tariff-war reprise risk; for tower infrastructure it is tenant-concentration risk (a distressed anchor-tenant operator can force lease-restructuring); for FTTH / wireline it is execution risk on homes-passed rollout + content-bundling competition; for enterprise B2B it is contract-concentration + cyber-security; for 5G FWA pure-plays it is monetisation-miss risk (ARPU lift needs to materialise). State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Telecom governance stress surfaces through balance-sheet and related-party telemetry rather than board drama:
- **Promoter-group leverage at the consolidated parent level** — telecom subsidiaries of highly-leveraged conglomerate groups carry latent pledge risk even when the listed-entity pledge % is zero. Cross-check the group-level aggregate pledge via the parent entity's disclosures; a 15-30% group pledge that has crept up over 4 quarters is a liquidity-cascade latent.
- **Intra-group related-party transactions** — tower rent paid to group-affiliated tower entities, enterprise-connectivity bought from group-affiliated data-centre entities, international-traffic settlements with group-affiliated carriers. Disclosed RPT as a % of revenue creeping from <5% to 10-15% across 4 quarters is a minority-shareholder-value-transfer signal.
- **Auditor qualifications on AGR / licence-fee provisions** — auditor emphasis-of-matter paragraphs on AGR provisioning adequacy are forensic-grade tells; the provisioning charge itself is regulatory-driven but auditor commentary on its sufficiency is a governance signal.
- **CEO / CFO transitions during spectrum-auction or tariff-decision windows** — leadership turnover at regulatory-decision inflection points is a decision-risk latent.
- **Multiple simultaneous capital-raise channels** — QIP + rights-issue + promoter pref-allotment within 12 months typically signals balance-sheet distress beyond what headline net-debt/EBITDA shows.

Cross-check via `get_events_actions(section='material_events')` and `get_company_context(section='filings')`.

### Regulatory Risk Taxonomy — Cite the Specific Authority
Regulatory risk in Indian telecom is concrete and must be tied to the specific regulator and, where possible, the specific Act, judgement, or circular:
- **DoT (Department of Telecommunications)** — licensing regime, spectrum allocation, AGR definition and recovery, licence-fee (typically 8% of AGR) and spectrum usage charge (typically 3-5% of AGR); the **Telecommunications Act 2023** grants sweeping licence-suspension powers on national-security grounds.
- **TRAI (Telecom Regulatory Authority of India)** — tariff regulation (forbearance regime with occasional interventions), **Quality-of-Service framework**, interconnection-usage charge (IUC), mobile-number-portability norms.
- **MeitY / MIB** — data-protection under the **Digital Personal Data Protection Act 2023**, intermediary-rules, OTT/content regulation overlap with traditional telecom.
- **TDSAT (Telecom Dispute Settlement Appellate Tribunal)** — appellate body for DoT / TRAI decisions; key disputes on spectrum, interconnection, licence-fee calculation land here before the Supreme Court.
- **Supreme Court** — the **AGR judgement of 2019** (Union of India vs Association of Unified Telecom Service Providers) crystallised the AGR definition to include non-telecom revenue; the resulting dues overhang continues to shape the sector's capital structure.
- **Spectrum-auction calendars** — DoT runs auctions roughly every 2-5 years; auction-outcome risk is concentrated in the ~12-month window around auction close.
- **National Broadband Mission** / **BharatNet** — sets rural-rollout targets that flow into licence conditions and USOF-fund allocation.

Name the relevant authority and judgement when the risk crystallises; "telecom regulation" without specificity is non-actionable framing.

### AGR / Spectrum-Dues as Permanent Shadow Liability
Indian telecom's most distinctive risk is the AGR + deferred-spectrum-payment liability, which sits as current + non-current liabilities on the balance sheet but behaves as quasi-debt with equity-conversion optionality:
- **Included in true Net debt** — consolidated net-debt/EBITDA with AGR + deferred-spectrum dues added back can be 2-3× headline net-debt/EBITDA for stressed operators.
- **Moratorium NPV** — several Indian telcos received 4-year moratoria on spectrum and AGR dues with interest accrual; the NPV of those payouts is material and declines if the government offers equity-conversion or early-settlement discounts.
- **Equity-conversion precedent** — the Government of India has converted spectrum / AGR dues into equity at a stressed private operator (taking a ~33% stake); treat any operator with AGR-linked conversion clauses in disclosed debt documents as a permanent dilution latent.
- **Pull via** `get_fundamentals(section='balance_sheet_detail')` for AGR + deferred-spectrum line; `get_company_context(section='concall_insights', sub_section='management_commentary')` for servicing plans and any conversion-clause commentary; `get_events_actions(section='material_events')` for Supreme Court / DoT rulings.

### Operational Risk — Concentration, Execution, Incident
Concentration and execution risks that aggregate-level advances-style diversification numbers miss:
- **Tenant concentration for tower infra** — anchor-tenant share of tower-infra revenue 40-55% typical; a distressed anchor operator forcing lease renegotiation can take tower EBITDA down 15-25% in a single negotiation round.
- **Spectrum-band concentration** — heavy reliance on a single band (e.g., 1800/2100 MHz) without sub-1GHz coverage-band depth is a network-quality latent that surfaces as subscriber churn over 6-12 months.
- **Geographic circle concentration** — top-4 circles can account for 50-60% of wireless revenue; a state-level regulatory event (tower-rollout ban, right-of-way dispute) disproportionately hits heavily-concentrated operators.
- **Capex-execution risk** — 5G rollout timelines slipping behind guidance by 6-12 months re-prices the operator's ARPU-lift trajectory.
- **Network-outage major events** — a multi-hour pan-India outage has reputational and regulatory-penalty consequences under the TRAI QoS framework.
- **Cybersecurity / data-breach incidents** — under DPDP Act penalty framework, a breach of subscriber-data at scale can attract material fines plus brand damage.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical Indian telecom drawdowns have recurring triggers; use these as the scaffolding:
- **Tariff-war reprise** — the 2016-19 new-entrant-led tariff collapse took incumbent operators down 40-60%; a new entrant or aggressive challenger restarting a price war is a structural-drawdown trigger. Threshold: industry ARPU falling >10% YoY.
- **Unfavourable spectrum-auction outcome** — losing access to critical coverage bands at a viable price repriced select operators 20-30% historically. Threshold: auction-close with shortfall in sub-1GHz or a key mid-band.
- **DoT regulatory re-interpretation** — AGR-adjacent receivables or licence-fee calculation methodology re-opened by DoT is a fresh-liability latent.
- **5G monetisation miss** — if ARPU does not lift 25-35% in the 2-3 years post-5G rollout, the 5G-capex cycle has destroyed value and the stock re-rates down 25-40%.
- **Promoter-group cascade** — a credit event at the listed telecom's conglomerate parent can force a stake-sale or pledge-invocation independent of the listed-entity's own fundamentals.
- **Cyber / network-integrity incident at scale** — 10-20% drawdown risk.

Quantify each as a thesis-breaker: the metric threshold beyond which the base-case is invalidated (e.g., "industry ARPU falling >8% YoY for 2 consecutive quarters" or "AGR-adjacent receivable re-opened by DoT with quantified demand >10% of net worth").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges for a top-3 Indian wireless operator:
- **ARPU −5% (₹10-12 drop)** — wireless EBITDA compresses 200-350 bps given high operating leverage on the mostly-fixed cost base.
- **Subscriber base −3%** — revenue falls 3% but fixed-cost deleverage worsens EBITDA margin by a further 100-200 bps; total EBITDA impact 400-600 bps.
- **Capex / revenue +20% (e.g., extended 5G peak)** — OpFCF yield compresses 50-100 bps, extending the deleveraging timeline.
- **AGR-adjacent demand +₹5,000 Cr** — net-debt/EBITDA worsens by 0.2-0.4× depending on operator scale.
- **Anchor-tenant lease renegotiation −15% rent** — tower-infra EBITDA compresses 8-12% given the tenant-concentration pass-through.
- **Spectrum-renewal cost 20% above guidance** — free-cash-flow timing shifts, net-debt peak delayed by 12-18 months.

Route the arithmetic through `calculate` with ARPU delta, subscriber delta, capex delta, and AGR demand as named inputs.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='telecom')` returns incomplete leverage or capex-intensity data, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end numbers; (2) `get_fundamentals(section='balance_sheet_detail')` for AGR + deferred-spectrum + net-debt reconstruction; (3) `get_events_actions(section='material_events')` for regulatory, governance, and auditor events. Cite the source quarter for every extracted number. Do not fabricate spectrum-holdings MHz or AGR-dues balances — the risk agent's credibility depends on citing what the operator and the regulator have actually disclosed.

### Open Questions — Telecom Risk-Specific
- "What is the current AGR + deferred-spectrum-dues balance, the moratorium-servicing schedule, and is there any equity-conversion clause in the disclosed debt documents?"
- "What share of wireless revenue is concentrated in the top-4 circles, and what share of tower-infra revenue comes from the single largest anchor tenant?"
- "Is any DoT / TRAI / MeitY circular or draft regulation currently in public consultation that would reprice licence-fee, spectrum-usage charge, QoS penalties, or DPDP-compliance costs?"
- "For operators with high group-level leverage: what is the consolidated group-level pledge %, and has it trended up materially over the last 4 quarters?"
- "If 5G capex is peaking in the current year, what is the ARPU lift and monetisation milestone that management is guiding for FY+2 and FY+3, and does the analyst consensus reflect it?"
