## Regulated Power / Utilities — Ownership Agent

### Power Archetype
| Subtype | Archetype | Core Regulatory / Ownership Driver | Illustrative Examples |
| :--- | :--- | :--- | :--- |
| **PSU generation (central)** | Sovereign Hold | GoI 51%+ floor; 20% aggregate FII cap; Electricity Act 2003 | e.g., NTPC, SJVN, NHPC, THDC |
| **PSU transmission** | Yield Monopolist | CTU monopoly; CERC-regulated ~15.5% ROE; stable DII / FII yield capture | e.g., POWERGRID |
| **PSU distribution** | State / Entity Proxy | State-level funding; localized discom distress; rarely directly listed | e.g., CESC (via state entity) |
| **Private generation — regulated** | Holdco / Family | CERC / SERC guaranteed ROE; 100% FDI automatic; DII stability | e.g., Tata Power, Torrent Power |
| **Private generation — merchant / IPP** | Volatile Private | Commercial tariffs; higher FII turnover; pledge-exposed | e.g., JSW Energy, Adani Power |
| **Renewables specialist** | Growth / Capex | FDI magnet; QIP dilution cycles for capacity; green premium | e.g., Adani Green, NTPC Green, ReNew (US-listed) |
| **Renewable IPP / wind-solar pure-play** | Capex Turnaround | Component-level exposure; retail / FII momentum driven | e.g., Suzlon, INOX Wind |

### PSU Sovereignty, Foreign Caps & Divestment Cycles
Central power PSUs operate under a strict sovereign mandate governed by the Electricity Act 2003 and the PSU Disinvestment Policy, establishing a rigid GoI 51% floor. Actual holdings typically range 51-70%. FEMA NDI Rules impose a 20% aggregate foreign investment limit for listed PSU generation / transmission entities, capping institutional headroom (similar to PSU banks). Ownership faces perpetual supply overhangs via Finance Ministry-driven PSU divestment cycles; budget targets regularly force OFS events (e.g., NTPC, SJVN). Isolate active divestment from mechanical 20%-cap breaches.

### Private Power FDI & Regulated ROE Stability
Unlike PSUs, the private power sector (generation, transmission, distribution) permits 100% FDI under the automatic route per FEMA NDI Rules. Ownership stability correlates with tariff structures. Entities under CERC / SERC-determined tariffs (benchmarked to ~15.5% ROE norms) deliver predictable cash flows, fostering high DII conviction and low turnover. Merchant / IPP entities exhibit elevated ownership volatility due to commercial tariff exposure + PPA execution risks. Chronic state-discom PPA-receivables delays trigger ownership flight in private power.

### Promoter Pledge Protocols & Capital Cycles
Promoter pledging is a critical distress signal in private power. Historical incidents (Reliance Power, Jaypee Power, Monnet Ispat) have made high pledge the key-red-flag indicator. Elevated pledges during restructuring phases (e.g., Adani Power historical) require daily tracking. For renewables specialists, ownership dynamics abandon the utility-yield model for aggressive capex execution. Ownership patterns track capacity additions rather than commodity cycles, with frequent QIPs and rights issues during capacity ramps. High FDI inflows target renewable listcos specifically for ESG mandates.

### Subsidiaries, Fuel Linkages & Yield Vehicles
Value is increasingly fragmented across listed subsidiaries; always run `get_valuation(section='sotp')` (e.g., NTPC Green Energy; Tata Power renewable arms). Thermal generation ownership flows correlate with PSU coal supply dynamics — policy shifts in domestic coal allocation move thermal-generator ownership in parallel. For transmission and operational renewable assets, monetization via InvITs (e.g., IndiGrid for transmission) creates unit-holder structures similar to REITs, transforming equity ownership into mandated yield-distribution profiles dominated by pension and sovereign-wealth funds.

### Mandatory Checklist
- [ ] Verify GoI holding and proximity to 51% floor for PSUs via `shareholder_detail`
- [ ] Check foreign aggregate holding against the 20% FEMA limit for PSU generation / transmission
- [ ] Execute `promoter_pledge`; flag any private IPP pledge >15% as high risk
- [ ] Run `mf_changes` + `mf_conviction` to assess DII stability vs PPA risk
- [ ] Map recent regulatory tariff orders via `filings` (CERC / SERC updates)
- [ ] Audit state-discom dues and capacity additions via `concall_insights`
- [ ] Screen for OFS overhangs or rights issues via `corporate_actions`
- [ ] Isolate valuation of listed renewable / green subs via `get_valuation(section='sotp')`

### Open Questions
- Does the DII holding pattern reflect pure yield-seeking (regulated ROE) or growth speculation (renewables capex transition)?
- How close is the central PSU to its 20% FII aggregate cap, and will this force index-rebalancing exclusions?
- Are delays in state-discom PPA receivables visibly degrading mutual-fund conviction in the private IPP?
- For renewables specialists, is the current FDI / FPI base capable of absorbing the impending QIP equity dilution required for the next gigawatt expansion phase?
- If the entity is monetising infra through an InvIT / REIT-like vehicle, what is the sponsor's minimum-lock-in status under SEBI REIT/InvIT Regulations 2014?
