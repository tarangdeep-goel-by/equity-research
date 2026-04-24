## Metals & Mining — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across metals sub-types. For integrated steel it is commodity-price reversal and leverage-at-peak; for non-integrated steel it is input-price shock and conversion-spread collapse; for aluminium it is power-cost and carbon-regulation; for zinc/copper smelters it is TC/RC and ore-supply; for iron-ore mining it is royalty and resource-nationalism policy; for diversified private-group metals it is promoter-pledge and related-party extraction. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in metals surfaces earlier through capital-allocation and balance-sheet telemetry than through board drama:
- **Aggressive capex announcement at cycle peak** — the recurring capital-allocation error. 15-25% nameplate-capacity commitments made at peak HRC or peak LME prices typically land into a trough and produce 2-3 year ROCE collapse. Cross-check capex plans against cycle-phase diagnosis from the sector agent.
- **Promoter pledge in mid-cap diversified metals** — historically 40-60% pledge baseline in diversified mining groups; pledge drift +10 pp across 2-3 quarters is a late-cycle leverage distress signal. Always compute LTV and margin-call headroom for names like VEDL, HINDALCO, JSWENERGY, and family-promoted mid-caps via the ownership-agent handoff.
- **Inter-company related-party transactions in integrated groups** — captive-mine allocations, internal transfer pricing of iron ore / bauxite / coal between group entities, and dividend sweeps from cash-rich listed subsidiaries (HINDZINC, NATIONALUM) up to leveraged parent holdcos. Disclosed RPT that drifts from 3-5% of net worth toward 10-15% is an extraction signal.
- **Captive-mine allocation controversies** — allocations revisited by the Ministry of Mines or Supreme Court (recurring pattern since the 2014 coal-block cancellation) can wipe out the captive-RM moat overnight. Track via `get_company_context(section='filings')` for Supreme Court and NGT orders.
- **Auditor rotation or qualification** — rotation cycles that land in a quarter of a large impairment or environmental-clearance reversal are informational; qualifications on mine-resource accounting, asset-retirement obligations, or inter-company loan classification are forensic-grade tells.

### Regulatory Risk Taxonomy — Cite the Specific Regulator
Regulatory risk in metals is concrete and ministry-specific. Tie each risk to the specific regulator and statute:
- **MoEF&CC (Ministry of Environment, Forest & Climate Change)** — Environmental Clearance (EC) regime for new / expanded plants; delayed EC for a planned expansion defers the earnings narrative by 4-8 quarters. Cross-check any announced expansion against EC status via filings.
- **State Pollution Control Boards** — effluent, air, stack, and ambient-air standards; NGT orders can mandate partial shutdown. A 15-30-day enforced shutdown cuts the quarter's volume by 10-20% and flows through EBITDA/tonne.
- **Ministry of Mines** — mine-auction policy, captive-vs-merchant allocation rules, royalty rates (set statutorily under the MMDR Act), lease renewals and District Mineral Foundation (DMF) contributions.
- **IBM (Indian Bureau of Mines) Average Sale Price (ASP) regime** — royalty and auction premia under the post-2015 state-auction framework are indexed to IBM's monthly ASP for each mineral. Winning auction bids routinely clear at 80-110% premium over ASP, so a merchant miner's effective realisation after royalty + auction premium + DMF + NMET can be a thin 10-20% of gross FoB; a 10-15% drop in ASP with fixed auction premium flips the operation unprofitable. Cross-check auction-premium-vs-ASP for each declared mine.
- **CAMPA (Compensatory Afforestation Fund)** — Ministry-administered fund that holds back clearances until afforestation payments are made.
- **Iron-ore export duty** — policy-variable that Government of India adjusts; every 10% duty shift on iron-ore export reprices NMDC-style realization by a similar magnitude.
- **Steel safeguard and anti-dumping duties** — protect domestic producers from Chinese import flood; removal or reduction is the single biggest Indian steel regulatory risk.
- **PLI for specialty steel** — Production-Linked Incentive scheme subsidy; changes to PLI caps or eligibility reset specialty-steel economics.
- **EU CBAM (Carbon Border Adjustment Mechanism)** — effective phased from 2026 for steel, aluminium, cement, fertilizer, hydrogen, electricity. EU-facing Indian metal exports pay a carbon-cost surcharge tied to embedded-emissions intensity. For a typical Indian BF-BOF steel exporter (2.1-2.4 tCO₂ per tonne steel) at current EU ETS prices of €70-90/tCO₂, CBAM cost is ~€150-200/tonne on EU-destined volume from 2026, stepping up as the phase-in completes. DRI-EAF producers at 0.8-1.2 tCO₂/t face half the CBAM drag.

Name the specific master direction or circular when the risk crystallises; vague "per regulations" framing loses actionable traceability.

### Operational-Risk Concentration
Operational risk in metals clusters around input-cost volatility, power dependence, and single-plant / single-mine concentration:
- **Raw-material cost volatility** — coking coal (imported from Australia for most Indian integrated steel) spot swings 30-80% annually; alumina and power for aluminium swing 15-40% annually. A 20% coking-coal spike compresses steel EBITDA/tonne by $30-60/t at merchant pricing.
- **Power-cost shock (aluminium)** — aluminium is 35-40% power-cost; a 15% tariff rise or a captive-power-plant outage reshapes EBITDA-per-tonne by $80-150/t. Coastal smelters dependent on imported coal for captive power carry FX-plus-coal-price double exposure.
- **Mine-shutdown risk** — weather (monsoon-linked iron-ore mine shutdowns), NGT or Supreme Court orders (recurring for Goa iron-ore, Karnataka iron-ore), or local-community disputes. A 3-6 month shutdown at a feeder mine cascades into smelter under-utilization.
- **Railway / logistics disruption** — iron-ore and coal move primarily by rail; rake allocation constraints or Konkan-railway monsoon disruption hit utilization directly.
- **Labor relations in PSU metals** — PSU metals (SAIL, NMDC, HINDCOPPER, NATIONALUM, MOIL) have unionised workforces; wage-revision cycles and strike risk show up every 3-5 years.
- **Industrial-accident / fire risk** — blast-furnace outages, smelter pot-line shutdowns, gas leaks. A major incident typically means 6-18 months to restore full capacity. Check via `get_events_actions(section='material_events')`.
- **Inventory-valuation risk (non-integrated steel, re-rollers, pipe makers)** — conversion-spread business models carry 30-60 days of HRC / slab inventory; a 15% mid-quarter HRC drop can wipe out the entire 5-8% conversion margin via unhedged inventory write-downs and NRV adjustments. Integrated producers with captive-RM feed are insulated because the cost basis is internal-transfer-priced. Flag inventory days vs HRC-price delta quarterly.

### Bear-Case Scenarios — 30-60% Drawdown Triggers
Historical metals drawdowns have recurring triggers; use these as the scaffolding for a bear case:
- **China steel supply flood (post-stimulus unwinding)** — 2015-16 China over-capacity episode repriced global steel 40-50%; Indian steel equities lost 50-70% from peak. The analogue risk is a post-2024 China property-stimulus reversal.
- **Global demand slowdown −10%** — commodity-price reset; EBITDA/tonne drops 25-40% with realization compression and fixed-cost deleverage; leveraged producers lose 50-60% equity value.
- **CBAM carbon-cost shock on EU-facing volume (2026+)** — for exporters with >20% EU volume share at BF-BOF carbon intensity, CBAM reprices the export book 10-30% and forces either DRI / EAF conversion capex (5-8Y payback) or volume reset to domestic markets at lower realization.
- **Environmental-clearance revocation at a major plant** — Supreme Court or NGT ordered shutdown; the 2012-14 Goa iron-ore and Karnataka iron-ore episodes took NMDC and Sesa-Goa-type producers down 30-50%.
- **Industrial accident / fire** — 6-18 month shutdown; a single-plant producer can lose 40-60% market cap in 2 weeks.
- **Promoter-group liquidity cascade** — pledge-linked margin calls at peak-leverage cycles; repeat of the 2018-19 and 2023 episodes.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "HRC falling below $580/t sustained 2 quarters" or "CBAM implementation date confirmed with no phase-in relief").

### Stress Tests — Quantify the Sensitivity
Metals stress tests run on commodity-price and cost-input moves:
- **HRC / LME primary −10%** → EBITDA −25-40% at current leverage; captive-integrated producers −20-30%; non-integrated −35-45%.
- **Coking coal +20%** → steel EBITDA/tonne −$30-60/t → steel EBITDA margin −200-400 bps.
- **Aluminium power cost +15%** → aluminium EBITDA −250-450 bps margin.
- **Iron-ore royalty +5 pp** → iron-ore mining EBITDA-per-tonne −$3-7/t.
- **USDINR −5% (INR strength)** → realized export prices compress by ~5% on export volume; for exporters >20% of volume the EBITDA hit is 4-8%.
- **CBAM at €90/tCO₂ on 30% EU-export share for BF-BOF producer** → export-book EBITDA/tonne −$150-200/t, equivalent to 8-15% total-EBITDA hit from 2026.

Route stress-test arithmetic through `calculate` with commodity delta, cost delta, and FX as named inputs rather than hand-waving.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='metals')` returns missing leverage or operating metrics, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end leverage, capacity-utilization, and EBITDA/tonne; (2) `get_company_context(section='filings')` for the most recent BSE disclosure, NGT orders, MoEF&CC actions, and Supreme Court rulings; (3) `get_events_actions(section='material_events')` for plant-outages, accidents, and ratings actions. Cite the source quarter for every extracted number. Do not fabricate commodity sensitivity — cite the company's own disclosed price-assumption guidance where available.

### Open Questions — Metals Risk-Specific
- "What is the HRC / LME price assumption embedded in the current leverage guidance, and what is the net-debt/EBITDA trajectory if the commodity mean-reverts to 10Y average?"
- "For EU-export-facing volume: what is the estimated CBAM carbon-cost per tonne from 2026, and is a DRI-EAF conversion or low-carbon-power plan announced with realistic payback?"
- "Is any environmental-clearance, mine-lease-renewal, or NGT / Supreme Court challenge pending that could force a partial shutdown in the next 4-6 quarters?"
- "For private diversified metals groups: what is the aggregate group-level promoter pledge and the LTV headroom to margin call on the foreign-debt-servicing vehicle?"
- "Are captive-mine allocations (iron ore, coal, bauxite) stable, or is any Ministry of Mines review / auction revisiting the allocation pending?"
