## Auto — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across auto sub-types. For mature ICE OEMs it is cycle-turn and EV-disruption terminal value; for 2W leaders it is rural real-wage cyclicality and 2W-EV transition speed; for CVs it is infra-capex and GST/e-way-bill fleet-turnover linkage; for EV pure-plays it is cash runway and unit-economics path; for Tier-1 ancillaries it is customer concentration and content-per-vehicle disruption; for Tier-2 ancillaries it is commodity pass-through lag and working-capital strain; for aftermarket it is channel stability and counterfeit competition. State the sub-type's dominant risk axis in the opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in auto surfaces through specific balance-sheet and related-party telemetry rather than only through board drama. Scan for:
- **Chronic pledge at conglomerate-linked promoter group** — auto is the headline asset inside diversified family groups; family-group liquidity distress shows up as rising promoter pledge at the listed auto entity even when the auto business itself is healthy. Any pledge >5% at a family-promoted OEM warrants a group-level debt check via `get_ownership(section='promoter_pledge')` and `get_company_context(section='filings')`.
- **Related-party transfer pricing with captive ancillaries** — OEMs that source tires, batteries, or electrical components from group-owned ancillaries at non-arm's-length prices extract value from the listed entity to the private holdco. Track RPT as % of net worth and % of cost of goods sold; creep from 5-8% to 12-15% of COGS over 4-6 quarters is a transfer-price-leak telltale.
- **Rapid capex into unproven EV platform without disclosed IRR hurdle** — a ₹3,000-10,000 Cr cell-plant or EV-platform capex announced without disclosed capacity targets, cost-per-kWh trajectory, or IRR hurdle rate is a capital-allocation red flag distinct from the EV thesis itself.
- **CEO / R&D-chief churn** — in a 10-15Y EV transition cycle, the CTO / R&D-head role is the single most load-bearing management seat; churn at that seat (>2 transitions in 3 years) signals platform-strategy instability and 4-8 quarter execution drift. Cross-check via `get_events_actions(section='material_events')`.
- **Auditor rotation or qualification** on inventory provisioning, warranty provisions, or capitalized development — the three auto-specific accounting pressure points; qualifications here are forensic-grade tells.
- **Parent-conglomerate governance** for listed OEM / ancillary subsidiaries — a credit event, SEBI show-cause, or liquidity downgrade at the parent propagates to the listed subsidiary's funding cost and royalty-rate negotiations within 1-2 weeks.

### Regulatory Risk Taxonomy — Cite the Specific Policy
Regulatory risk in auto is concrete and scheduled; tie each risk to the specific regulator, policy, and effective date where disclosed:
- **MORTH / CPCB** — **BS6 to BS6.2 transition** (April 2023 cutover already absorbed; BS7 (Euro-7-modelled) draft consultation is in the mid/end-2025 window with implementation targeted ~2027, carrying a 300-800 Cr per-platform re-engineering capex for each OEM). **CAFE-III (Corporate Average Fuel Economy)** norms apply from **1 April 2027** (through FY32), tightening fleet-wide CO2 from ~113 g/km toward ~91.7 g/km (draft proposals go lower), with super-credits for BEV (3.0×), PHEV (2.5×) and strong-hybrid (1.6×) sales. Assess the OEM's fleet-emission trajectory vs CAFE-III: an ICE-heavy fleet faces penalties or forced margin-dilutive EV/hybrid mix to earn super-credits. **Bharat NCAP** star-rating regime drives safety-content upgrade capex on legacy platforms.
- **MoHI (Ministry of Heavy Industries)** — **PM E-DRIVE** scheme (₹10,900 Cr outlay — the active EV demand-incentive regime; FAME-II expired March 2024 and the interim EMPS has sunset, so any "FAME-II cliff" framing is stale). The scheme was extended (March 2026 notification) within the same outlay: **e-2W subsidies sunset 31 July 2026; e-3W and e-buses extended to 31 March 2028**. The e-2W incentive was cut to **₹2,500/kWh, capped at ₹5,000/vehicle**; e-3W capped at ₹12,500/vehicle. Re-express any "FAME-II cliff" as these PM E-DRIVE per-kWh caps and sunset dates. **Auto + Auto-component PLI** has a ₹25,938 Cr corpus (advanced-automotive-technology, with capacity and DVA thresholds); the often-quoted ₹26,058 Cr figure is the combined Auto-PLI + Drone-PLI outlay, not a standalone "EV PLI." Battery-cell incentives sit under the separate **ACC PLI** (₹18,100 Cr).
- **GST Council** — post the 56th GST Council (Sept 2025, GST 2.0; effective 22 Sept 2025) the blanket 28% + cess regime is gone. Current slabs: **18%** on small cars (petrol/CNG/LPG <1,200cc, diesel <1,500cc, length <4m), two-wheelers ≤350cc, and three-wheelers; **40%** on large cars / SUVs (above those engine/length thresholds) and 2W >350cc; **5%** on EVs (unchanged, to incentivize transition). Rate changes on specific segments reshape affordability overnight.
- **DVA (Domestic Value Addition) compliance** — PLI and PM E-DRIVE EV subsidies require a minimum **50% DVA** to qualify; failing an MHI audit halts disbursements and can trigger retroactive refund/penalty. For any OEM/component maker booking PLI or PM E-DRIVE receivables, check DVA-certification status; if under MHI investigation, stress-test a partial-to-full write-off of subsidy receivables.
- **State-level EV subsidies** — direct demand incentives (state-specific, ₹5,000-40,000 per 2W) with expiry schedules; the end-of-subsidy cliff tests the underlying TCO-parity economics.
- **Scrappage policy** — the voluntary vehicle scrapping policy creates incremental demand but execution has been uneven; the fleet-turnover math is sensitive to state-level enforcement.
- **SEBI** — disclosure norms on corporate actions and related-party transactions. **Royalty/brand-usage payments to a related party (e.g., a foreign parent) exceeding 5% of annual consolidated turnover require majority-of-minority shareholder approval under SEBI LODR** — flag any MNC-subsidiary OEM/ancillary approaching or breaching this 5% line as a value-extraction governance risk.

Name the relevant policy when the risk crystallises; vague "per regulations" framing loses the traceability that makes the risk actionable.

### Auto-Financing / NBFC Subvention Risk
Roughly 75-80% of Indian 2W and CV sales (and ~80-85% of new-4W sales) are financed, so OEM volumes and margins are tightly coupled to the financing channel. Two distinct exposures:
- **Subvention cost** — OEMs subsidize interest/processing to financiers to push low-EMI schemes; rising subvention (in a high-rate or competitive-discounting environment) flows straight through to EBITDA. Track disclosed subvention/marketing spend per unit.
- **Financing availability / LTV** — an NBFC liquidity squeeze or RBI tightening of auto-loan LTV directly compresses demand at the affordability margin (worst for entry 2W and first-time CV operators).
Pull financing-penetration and subvention commentary from `concall_insights`; a rising subvention cost alongside slowing retail offtake is a margin-and-demand double-hit. Captive-NBFC OEMs additionally carry the NBFC's own asset-quality and funding-cost risk on the consolidated book.

### Operational-Risk Concentration
Concentration is the quietest risk in auto because aggregate P&L can look diversified until a single platform, single OEM customer, or single commodity input breaks. Examine:
- **Single-platform revenue concentration** — a 4W OEM with >30% of volume from one platform faces model-cycle-timing risk at platform refresh (typically year 5-7 of the lifecycle). A failed refresh collapses the segment for 6-10 quarters.
- **Single-OEM customer concentration (Tier-1 ancillaries)** — >40% of revenue from one OEM is structural risk; that OEM's volume decline flows through 1-for-1, and contract re-negotiation power sits with the OEM.
- **Geographic concentration** — a 2W OEM with >35% revenue from 3-4 rural-heavy states is exposed to state-election farm-loan waivers, rainfall shocks, and state-specific GST changes.
- **Commodity input exposure** — steel and aluminum for all OEMs; rare earths (neodymium, dysprosium) for EV motor magnets; lithium and nickel for cells. A 2W OEM importing 30%+ of raw material has FX exposure layered on commodity exposure.
- **Export-market concentration** — >40% of exports to a single region (Africa, LatAm, Asia ex-India) exposes to that region's FX and trade-policy risk.
- **Captive-dealer concentration (dealerships / auto retail)** — >60% revenue from one OEM franchise is structural risk on that OEM's product success.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical auto drawdowns have recurring triggers; use these as the scaffolding for a bear case:
- **Systemic volume shock** — COVID-style 35-45% 4W volume drop in a single year (FY21 was -18% for PV, -38% for M&HCV); bear-case stress the EBITDA against the trough-year volume with fixed-cost unabsorbed.
- **Metro diesel ban / regulatory retrofit** — SC-mandated 10-year-diesel / 15-year-petrol curbs in NCR historically compressed resale values and new-diesel demand; a metro-wide diesel ban would halve the diesel-heavy segment of the OEM's order book.
- **EV disruption collapsing ICE resale values** — once 2W EV share crosses 25-30%, ICE-2W resale values compress 20-35% over 4-6 quarters, dragging dealer-inventory write-downs and new-sale conversion rates.
- **Overseas parent / subsidiary shock** — for auto majors with JLR-scale overseas luxury businesses, a China slowdown, a regulatory-import ban in a major market, or a forex-led margin shock at the subsidiary propagates to the consolidated P&L and the SOTP lever.
- **Commodity super-cycle** — a 30-40% steel / aluminum move not absorbable through pricing (because of competitive pressure) compresses gross margin 500-900 bps for 2-4 quarters; most historical auto drawdowns have a commodity-move leg.
- **EV pure-play dilution cascade** — runway below 12 months with failed QIP pricing can trigger 40-60% single-event drawdowns; the path to recovery requires a strategic investor or distressed round.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "4W volume YoY turning -15% with inventory >50 days" or "EV pure-play runway dropping below 15 months with no announced funding").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **10% volume drop** — operating-leverage flow-through is 2-3× on EBITDA margin (so a 10% volume drop produces 200-300 bps EBITDA-margin compression for a fixed-cost-heavy OEM). Route via `calculate`.
- **Raw material +15% with pricing capped** — 300-500 bps gross-margin compression before pass-through lag; 150-300 bps after a 2-3 quarter lag. Segment-specific: 4W mass is more pass-through-constrained than 2W or premium 4W.
- **FX 5% INR move** — on exporters (a 2W leader with 40% exports, a Tier-1 ancillary with 50% exports), 150-300 bps of EBITDA margin; on importers (high raw-material imports), 100-200 bps of margin compression.
- **EV-volume 2x above guidance** (downside for ICE) — ICE-heavy OEM losing incremental 2W EV share at 3-5pp per year faster than planned collapses 3-5Y PAT CAGR by 400-700 bps.
- **Dealer inventory reset** — a one-time destocking to clear 45+ day inventory back to 25-30 days costs 1-2 quarters of wholesale volume (effectively a -15% to -25% wholesale quarter).

Route the arithmetic through `calculate` with volume-delta, input-cost-delta, FX-delta as named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores` returns missing risk ratios, fall back in order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end capex, inventory, and warranty numbers; (2) `get_company_context(section='filings')` for BSE disclosures on material contracts, guarantees, and RPT; (3) `get_events_actions(section='material_events')` for governance events, auditor transitions, and corporate actions; (4) `get_events_actions(section='corporate_actions')` for buybacks / special dividends that may signal parent cash extraction in MNC subs. Cite the source quarter for every extracted number. Do not fabricate volumes, inventory days, or capex — the risk agent's credibility depends on citing what the company actually disclosed.

### Open Questions — Auto Risk-Specific
- "What is the single-platform revenue concentration and single-OEM customer concentration, and has either crossed the 30-40% structural threshold?"
- "Is the current capex cycle (EV platform / cell plant / new model) matched by disclosed IRR hurdles, capacity targets, and funding sources? Any unfunded tranche in the next 4-6 quarters?"
- "What is the dealer inventory days trajectory, and is the current wholesale-retail gap building toward a production-cut quarter?"
- "For MNC / parent-subsidiary OEMs: is the foreign parent's global condition stable enough to avoid royalty-rate shocks, cash-repatriation via special dividends, or mandated R&D reallocation?"
- "For EV pure-plays: what is the cash runway, the next capex tranche, and the specific dilution scenario already embedded into the price target?"
