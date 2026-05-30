## Logistics Mode (Auto-Detected)

This company operates in the logistics, freight, shipping, or supply-chain sector. The sector spans highly divergent business models — from asset-light express delivery to asset-heavy rail and cyclical marine shipping. 

**Model Bifurcation — The First Step:**
You must immediately classify the company into one of three buckets before applying any framework:
1. **Asset-Light / Express / 3PL** (e.g., Delhivery, Blue Dart, TCI, Mahindra Logistics): High asset turnover, lower EBITDA margins, valued on growth, network density, and operating leverage.
2. **Asset-Heavy / Infrastructure** (e.g., Concor, Gateway Distriparks, VRL Logistics): High capital intensity, higher EBITDA margins, valued on capacity utilization and ROCE.
3. **Marine Shipping / Shipyards** (e.g., GE Shipping, Cochin Shipyard): Pure global cyclical (shipping) or defense/PSU capex-driven (shipyards). 

**Primary Valuation Metrics:**
- **EV/EBITDA**: The primary anchor for asset-heavy logistics (Rail, FTL Trucking, CFS/ICD).
- **PE / Forward PE**: Primary for mature asset-light Express/3PL players where operating leverage translates volume directly to the bottom line.
- **P/B at trough**: The floor valuation for cyclical marine shipping.
- **EV/Sales**: Only acceptable for early-stage or temporarily unprofitable Express/E-commerce logistics players (e.g., Delhivery during investment phases), but must be accompanied by a path-to-profitability check.

**These metrics are misleading in isolation:**
- **EBITDA Margin comparisons across models**: Asset-light 3PLs report 4-8% EBITDA margins; asset-heavy rail/trucking report 15-25%. Comparing them directly is a structural error. Compare ROCE instead.
- **PE for Marine Shipping**: Inverted cyclical trap (like metals). Lowest PE marks the freight-rate peak; highest PE marks the trough.
- **Headline Debt without Ind-AS 116 adjustment**: Logistics companies lease warehouses and trucks. Ind-AS 116 capitalizes these leases, artificially inflating EBITDA and Debt. Always check if debt is "borrowings" or "lease liabilities".

**Emphasize:** Volume vs. Yield (Realization) growth, fuel-cost pass-through mechanisms (FSC), network density/utilization, Dedicated Freight Corridor (DFC) transition, and client concentration (especially e-commerce/auto).

### Mandatory — Logistics KPI Backbone
Every logistics report from the **sector** and **financials** agents must extract and cite:
- **Volume**: TEUs (Twenty-foot Equivalent Units) for rail/shipping, Tonnes for PTL/FTL trucking, or Number of Shipments for Express/B2C.
- **Realization / Yield**: Revenue per TEU, Revenue per Tonne-km, or Revenue per Shipment. Revenue growth MUST be decomposed into Volume Growth vs Yield Growth.
- **Network Capacity**: Warehousing space (mn sqft), number of branches/hubs, or fleet size (owned vs leased).
- **Asset-Light Mix**: % of fleet/warehouses leased vs owned, or % of revenue from 3PL/contract logistics.

A logistics report that cites revenue growth without decomposing it into Volume vs Yield is structurally incomplete. Pull these from `get_company_context(section='concall_insights', sub_section='operational_metrics')` or `get_deck_insights(sub_section='key_metrics')`.

### Annual Report & Investor Deck — Logistics Specifics

**AR high-signal sections:**
- `mdna` — volume vs realization breakdown, fuel-cost pass-through lag, Dedicated Freight Corridor (DFC) impact, e-way bill trends.
- `segmental` — Express vs PTL (Part Truck Load) vs FTL (Full Truck Load) vs Supply Chain (3PL). Each has radically different margins.
- `risk_management` — client concentration (e.g., % of revenue from top 5 e-commerce or auto clients), fuel price volatility, driver shortage.
- `notes_to_financials` — Ind-AS 116 lease liabilities breakdown, contingent liabilities (tax disputes on waybills).

**Deck high-signal sub_sections:**
- `key_metrics` — network utilization %, tonnage handled, shipment volumes, warehousing capacity additions.
- `segment_performance` — B2B vs B2C express mix, EXIM (Export-Import) vs Domestic rail mix.
- `outlook_and_guidance` — volume guidance, capex for new hubs/sorters, margin expansion targets via operating leverage.

**Cross-year narrative cues:** `capital_allocation_shifts` reveal transitions from asset-heavy to asset-light models (e.g., selling owned trucks to lease them); `narrative_shifts` in client mix (e.g., pivoting from B2C e-commerce to B2B heavy freight).
