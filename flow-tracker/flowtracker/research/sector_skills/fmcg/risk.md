## FMCG — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis differs across FMCG sub-types. For HPC leaders it is commodity input exposure and D2C disruption; for food & beverages it is FSSAI packaging-mandate shocks and cold-chain dependency; for packaged staples it is commodity-spread compression; for tobacco / alcobev it is state-excise and regulatory ban risk; for OTC / wellness it is Drugs-and-Cosmetics Act classification changes; for D2C / digital-native it is unit-economics and funding-cycle risk. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in FMCG surfaces earlier through operating telemetry than through board drama. Scan for:
- **Promoter pledge in mid-caps** — the FMCG structural baseline is 0% pledge (cash-generative business funds itself). Any non-zero pledge in a multi-gen family-promoter name signals capital diverted to non-FMCG ventures (real estate, infra, other group entities); cross-check via `get_ownership(section='promoter_pledge')`.
- **Related-party purchases drifting upward** — packaging material, distribution services, logistics sourced from promoter-group entities; if RPT as % of net worth drifts from 3-5% to 10-15% across 4 quarters, value is leaking to related parties.
- **KMP compensation rising faster than earnings** — CEO / CXO pay growing 20-30% YoY while EPS grows 8-12% is a pattern across 2-3 consecutive years that signals board-governance weakness; cross-check via `get_company_context(section='filings', sub_section='related_party_transactions')`.
- **Frequent restructuring / segment reclassification** — business-segment boundaries redrawn every 2-3 years obscures segment-level margin trends and makes peer benchmarking harder; flag repeated redefinitions as an information-asymmetry risk.
- **MNC royalty creep** — royalty + technology-fee % of revenue drifting from 1-2% toward 5% SEBI LODR materiality threshold (requires "majority of minority" approval above 5% of consolidated turnover) is the classic margin-siphon pattern for MNC subsidiaries.

### Regulatory Risk Taxonomy — Cite the Specific Regulator
Regulatory risk in FMCG is concrete. Tie each risk to the specific regulator and, where possible, the specific rule:
- **FSSAI (Food Safety & Standards Authority)** — food-safety standards, packaging-label mandates (front-of-pack warning labels, nutrient thresholds), additive approvals, state-level enforcement variability. FSSAI draft regulations on HFSS (high fat, sugar, salt) labeling have been in public consultation with material cost-to-implement for packaged-food leaders.
- **State excise departments (alcobev, tobacco)** — excise-duty rates vary state-by-state and change at each state budget; a single state raising excise 20-40% can compress segment EBITDA materially in that state.
- **GST Council** — category-specific rate changes (tobacco, aerated beverages, chocolates, ice-cream) reprice net realization; cess rates on sin-goods have been recalibrated multiple times since 2017 rollout.
- **Drugs and Cosmetics Act + CDSCO** — OTC / wellness products face classification risk (moving a product from FMCG-cosmetic to Drugs-schedule changes the regulatory burden, pricing freedom, and distribution economics).
- **CCI (Competition Commission)** — M&A clearance for category-leading acquisitions; market-dominance investigations in specific categories (e.g., instant noodles, packaged water).
- **Product-specific bans** — tobacco advertising (1995 Cable TV Act + subsequent amendments), state-level pan-masala or gutka bans, e-cigarette ban (2019), plastic single-use bans affecting packaging.
- **FDI rules** — tobacco manufacturing is FDI-prohibited (caps legacy foreign holdings); standard FMCG is 100% automatic-route; single-brand retail has separate norms that apply when FMCG issuers forward-integrate.

Name the specific act / rule when the risk crystallises; vague "per regulations" framing loses traceability.

### Operational Risk Concentration
Portfolio diversity at the SKU level hides concentration risk at the category level. Examine:
- **Single-brand concentration** — >30% of revenue from one brand (common in food and wellness) exposes the company to category-specific demand shocks, regulatory reclassification, or competitive disruption in that narrow pocket.
- **Commodity input exposure** — palm oil (HPC), wheat / sugar / milk (food), crude-derivatives (HPC packaging), tobacco-leaf (sin-goods), grains (packaged staples). A single commodity representing >20% of COGS is a concentration risk; hedging policy disclosure (1-2 quarter horizon typical) should be scanned.
- **Distribution dependence on specific modern-trade chain** — >15% of revenue through a single MT chain or QC platform creates a monopsony risk; the platform can reprice terms unilaterally.
- **Monsoon-linked rural demand** — companies with >35-40% rural-share-of-revenue are exposed to crop-cycle and MNREGA-wage variability. A below-normal monsoon can compress rural volume 8-15% for 2-3 quarters.
- **Geographic concentration** — >40% of revenue from a single state or region (common for regional FMCG mid-caps) exposes the book to state-level regulatory and weather shocks.

### Bear-Case Scenarios — 20-40% Drawdown Triggers
Historical FMCG drawdowns have recurring triggers; use these as scaffolding:
- **Commodity-spike margin compression** — palm oil 2022 (crude palm oil doubled from $800 to $1,900/MT in 8 months) compressed HPC EBITDA margin 300-500 bps for 2-3 quarters; wheat 2023 squeezed biscuit / bread makers similarly. Bear case: margin hit persists 3-4 quarters before pass-through normalizes.
- **Rural demand collapse** — a -10% rural volume shock from crop-cycle or wage-stagnation transmits directly to HPC / food volumes; top HPC names reported 12-18 months of rural growth <0% during FY23 slowdown.
- **Regulatory packaging-mandate cost shock** — front-of-pack warning labels, HFSS thresholds, or extended-producer-responsibility (EPR) for plastic packaging add one-time capex 1-3% of sales + 50-150 bps ongoing margin.
- **D2C disruption** — legacy HPC / food names losing 300-500 bps category share to digital-natives in skin, hair, or health; the de-rating compounds with the share loss (valuation compresses 15-25% even before EPS impact shows up).
- **State-level ban / excise shock** — pan-masala state bans (multiple states), alcobev prohibition (Bihar, Gujarat), tobacco GST hike — can wipe 10-25% of segment revenue overnight.
- **Product-recall / food-safety event** — maggi-2015-style regulatory ban compressed valuations 20-30% in 2-3 weeks; full reputational recovery takes 4-6 quarters.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "rural volume declining >5% for 2 consecutive quarters" or "FSSAI HFSS labeling notified as mandatory with <12-month compliance window").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **Raw material +15% at 60% pass-through** — EBITDA margin hit 150-250 bps for HPC; 200-350 bps for food & beverages; 300-450 bps for packaged staples.
- **5% volume drop (rural shock)** — EBITDA margin hit 50-100 bps from operating deleverage; revenue hit compounds via realization weakness (promo intensity rises to defend share).
- **+200 bps ad-spend to defend share** — absolute EBITDA hit 150-200 bps; if sustained, offsetting 8-10% volume growth contribution is required to hold margin.
- **QC platform take-rate +500 bps** — mix-weighted margin hit 30-80 bps for leaders with 8-12% QC share; larger for digital-first brands.
- **State excise +20% (tobacco / alcobev)** — net realization drops 8-12% for the affected state; consumer-price elasticity absorbs 40-60% in volume over 2-3 quarters.

Route the arithmetic through `calculate` with input assumptions as named parameters rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='fmcg')` or `section='sector_health')` returns missing cost-structure, working-capital, or related-party metrics, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarterly trends; (2) `get_company_context(section='filings', sub_section='related_party_transactions')` for RPT / royalty trajectories; (3) `get_events_actions(section='material_events')` for governance events, product-recalls, and regulatory actions. Cite the source quarter for every extracted number.

### Open Questions — FMCG Risk-Specific
- "For MNC subsidiaries: what is the current royalty + technology-fee as % of revenue, and has there been any AGM vote or board proposal to raise the cap toward the 5% SEBI LODR threshold?"
- "What is the single-largest commodity input as % of COGS, and what hedging horizon has management disclosed?"
- "For family-promoter names: is the promoter pledge strictly 0%, and is any group-level entity showing liquidity stress that could propagate back?"
- "Are any FSSAI, GST, or state-excise draft regulations in public consultation that would materially reprice the category in the next 12-18 months?"
- "For D2C / digital-native exposure: what is the incremental QC / e-comm share, and is it cannibalising GT or generating incremental demand?"
