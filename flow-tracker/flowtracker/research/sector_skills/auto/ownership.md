## Auto — Ownership Agent

### Auto Archetypes & Baseline Ownership
| Subtype | Typical Promoter Structure | Typical Range | Pledge Baseline | Key Analytical Dimensions |
| --- | --- | --- | --- | --- |
| **OEM — Passenger Vehicle (PV)** | Family-led or Foreign MNC Parent | 40-75% | Zero/Low | Tech/platform dependence; parent royalty payout rates; listed sub complexity (e.g., family-promoted OEMs with overseas subsidiaries, MNC-subsidiary OEMs, and foreign JV subsidiaries). |
| **OEM — Two-Wheeler (2W)** | Legacy Family-promoter | 40-55% | Low (<5%) | Historical foreign-JV separation (e.g., legacy family-foreign JV splits); niche unlisted stakes in overseas niche-vehicle makers. |
| **OEM — Commercial Vehicle / Tractor** | Conglomerate Family or MNC Parent | 45-75% | Low | Deep cyclicality; agri/infra linkages; parent tech tie-ups (e.g., tractor makers partnering with foreign industrial groups, CV makers owned by diversified Indian conglomerates). |
| **EV Pure-Play / New-Age** | Founder + VC Consortium | 20-40% | Varies | Cap-table dilution; cash-burn intensity; pre-IPO holdco complexity (e.g., listed EV pure-plays and potential new-age 2W EV listings). |
| **Auto Ancillaries / Tier-1** | Foreign MNC JV or Local Family | 50-75% | Low | Cross-holdings with OEMs; localized vs global parent supply-chain integration (e.g., MNC-subsidiary component makers, large family-owned global ancillaries, multi-entity domestic component groups). |
| **Dealership / Auto Retail** | Founder / Corporate franchisee | 40-60% | Moderate | Low margin; working-capital intensity; OEM dependency risk (e.g., listed multi-brand auto retailers). |
| **EV Battery / Charging Infra** | Legacy Corp / Family transitioning | 40-60% | Low | Tech-transition capex; foreign tech JVs for cell chemistry (e.g., legacy lead-acid battery makers transitioning to Li-ion via foreign JVs). |

### The Foreign-Parent vs FII Classification Rule
Foreign parent / collaborator structures are central to the Indian auto sector. Do not conflate "foreign holding" with FII/FPI liquidity. 100% FDI is allowed under the automatic route for automobile manufacturing under FEMA. Many listed OEMs and tier-1 ancillaries (e.g., MNC-subsidiary OEMs and MNC-JV component makers) have a foreign parent holding 40-75% as the promoter, with the Indian listed entity acting as a subsidiary or JV. Use `get_ownership(section='shareholder_detail')` to confirm legal classification. If the foreign entity is classified as a **promoter**, treat the holding as permanent / strategic capital, not floating FII capital subject to global risk-on/risk-off cycles. Misclassifying inverts the free-float thesis.

### Family-Promoter vs MNC-Subsidiary Dichotomy
The sector is fundamentally split by governance structure:
- **Family-promoter setups** (legacy Indian auto families): typically 40-55%, stable family-led boards, prioritize local reinvestment and market-share defense.
- **MNC-subsidiary setups** (foreign-parent listed subs): foreign parent 55-75%. Governed by parent-subsidiary dynamics — higher dividend payout ratios, strict royalty-fee agreements, strategic decisions dictated by the global parent's architecture.

Differentiate your valuation baseline and capital-allocation expectations accordingly.

### EV Pure-Play: VC Dilution & Holdco Structure
Treat EV pure-plays (listed and prospective new-age EV issuers) closer to the platform/tech sector than legacy auto. Founders often hold minimal direct stakes, with economic interest parked in unlisted parent holdcos. The cap table is VC-heavy (global sovereign and growth-stage funds typical of Indian new-age tech). Manufacturing capex ramp-up requires immense cash, leading to continuous dilution via QIPs and fresh issues. Track pre-IPO lock-in expiries via `shareholder_detail`, as VC exits create heavy technical overhangs distinct from legacy auto ownership.

### Promoter Pledge: The "Zero-Baseline" Anomaly
Historically, promoter pledging in the Indian family-auto sector is exceptionally low (baseline <5% across legacy family-promoter OEMs) and virtually non-existent for MNC subsidiaries. Consequently, **any spike in promoter pledges is an anomalous, high-conviction red flag**. It rarely signals auto-business needs; instead, it flags extreme non-auto, group-level liquidity distress or failed unrelated ventures by the family. Run `get_ownership(section='promoter_pledge')` routinely — if >5%, investigate group-level debt immediately via `filings`.

### SOTP Complexity & OEM-Ancillary Cross-Holdings
Auto groups frequently operate via listed subsidiaries and complex cross-holdings. Large diversified OEM groups house varying divisions (PV, CV, Tractors, unlisted overseas luxury subs) and listed adjacencies across IT services, logistics, and financing. Additionally, track cross-holdings between OEMs and their Tier-1 suppliers, or within ancillary families (multi-entity component-group overlaps). These affect true free float and apparent independence. Always execute `get_valuation(section='sotp')` to value the core auto business independently from the holdco discount applied to group subsidiaries.

### Global Parent Cyclicality & Profit Repatriation
MNC subsidiaries face capital-allocation pressure from their global parent. A global distress event, global EV-transition burden, or worldwide recall at the foreign MNC parent can trigger sudden local stake sales, altered royalty agreements, or shifted R&D mandates. Conversely, watch for cash repatriation via unusual corporate actions. Execute `get_events_actions(section='corporate_actions')` to flag sudden buybacks or large special dividends — these are frequently used by foreign parents as tax-efficient mechanisms to sweep excess cash from the Indian subsidiary back to the global holdco.

### PLI / FAME Subsidy Reliance & Capex Execution
Government subsidy structures (EV PLI, FAME, Auto-Component PLI) tie financial incentives directly to production-volume and local-value-addition milestones. Stable promoter ownership correlates strongly with the ability to execute the multi-year capex required to meet these thresholds. Look for QIPs meant to fund PLI-linked capacity. Interrogate `get_company_context(section='concall_insights')` to connect ownership structure's capital-raising ability with management commentary on realizing PLI / FAME subsidy cash flows.

### Mandatory Auto Ownership Checklist
1. [ ] **Promoter origin check**: Is the promoter a legacy Indian family, a VC-holdco, or a global MNC? (`shareholder_detail`)
2. [ ] **FDI vs FII verification**: Ensure high foreign shareholding is correctly bucketed (Promoter vs FPI)
3. [ ] **Pledge anomaly test**: flag any family-promoter pledge >5% as group-level liquidity distress (`promoter_pledge`)
4. [ ] **Corporate action repatriation**: check buybacks / special dividends in MNC subs indicating parent cash extraction (`corporate_actions`)
5. [ ] **Subsidiary SOTP**: run for complex diversified auto groups to strip out cross-holdings (`sotp`)
6. [ ] **EV pure-play lock-in map**: list VC-backer unlocks if applicable (sovereign / growth-stage funds on new-age EV cap tables)
7. [ ] **Cycle positioning**: `mf_changes` for DII entry/exit to identify consensus on auto-cycle tops and bottoms

### Open Questions
- Is the MNC parent adjusting royalty rates upwards, signaling a shift in how it extracts value from the listed Indian entity?
- For EV pure-plays: when do the lock-ins for major VC backers expire, and how does this align with scheduled QIPs for battery-cell capex?
- Are cross-holdings within the ancillary group diluting the operational independence and capital efficiency of the specific listed entity being evaluated?
- Does the family promoter's capital allocation outside the auto sector present a systemic risk to the listed OEM?
- For bailout / distress-adjacent MNC subs: is the parent's global condition stable enough that the Indian subsidiary's dividend policy can be relied on?
