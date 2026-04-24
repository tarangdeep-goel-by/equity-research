## Auto / EV — Financials Agent

### Per-Unit Economics
Auto companies should be analyzed per-unit alongside aggregate financials. Extract unit volumes from `get_company_context(section='concall_insights')` or `sector_kpis`:
- **Revenue per unit** = Total Revenue / Units Sold — tracks ASP trends
- **EBITDA per unit** — operating profitability per vehicle
- If unit volumes available, use `calculate` tool to derive. If not, flag as open question

### Wholesale vs Retail Gap — Why Dispatches Can Mislead
Companies report wholesale (factory dispatches) for revenue, but actual demand = retail sales. The gap between these two accumulates as dealer inventory, and when it gets too high, production cuts and margin pressure follow — often with a 1-2 quarter lag.
- Extract **Dealer Inventory Days** from `concall_insights` — defined in `sector_kpis` as `dealer_inventory_days`
- Rising dealer inventory = imminent production cuts and margin pressure
- 20-30 days normal for PVs, 40+ days is a red flag

### Operating Leverage
Auto is high-fixed-cost. During volume upcycles, check if operating leverage is playing out:
- Gross margin should be relatively stable (commodity-driven)
- EBITDA margin should expand faster than gross margin (fixed cost absorption)
- If EBITDA margin isn't expanding with volume growth, fixed costs are bloating — flag this

### Subsidy/Incentive Separation (EV manufacturers)
- Separate **FAME/PLI subsidy income** from core revenue — check `concall_insights`
- If subsidy >10% of revenue, flag dependency risk (policy expiry, rate cuts)
- If not disclosed, flag as open question

### Capacity Utilization
- **Capacity utilization %** = production / rated capacity — from `concall_insights`
- Below 50% = negative operating leverage. Trend matters: rising = margin expansion catalyst

### Cost Structure
Use `get_fundamentals(section='cost_structure')` to analyze:
- Raw material cost as % of revenue — commodity exposure (steel, aluminium, rubber with 1-2Q lag)
- Employee cost trend — operating leverage signal

### Strip Captive Finance (NBFC) From Core Auto Analysis
Many large OEMs run captive NBFCs that book the bulk of dealer financing and retail auto loans. Consolidated financials blend a high-ROA manufacturer with a high-asset lender — producing ratios that describe neither business accurately:
- Net Debt / Equity at consolidated level is inflated by NBFC borrowings (which are match-funded against loan receivables, not risk debt)
- Consolidated EV/EBITDA is distorted because NBFC net interest margin flows into revenue while NBFC borrowings add to EV
- Core ROCE on the manufacturing business is understated once hundreds of crores of NBFC receivables sit on the balance sheet
- Extract segment-level financials from `get_company_context(section='filings')` and concall disclosures — segment reporting usually separates Automotive from Financial Services
- Report **two views**: (a) standalone / automotive-segment financials for operating analysis, (b) consolidated financials only where the captive NBFC is economically integrated (e.g., providing incremental volume via dealer financing)

### R&D Capitalization vs Expensing — EV-Cycle Earnings Quality Lever
The EV and connected-vehicle transition is driving R&D intensity to 3-6% of revenue for global auto, up from 1-3% historically. Under IndAS 38, development expenditure is capitalized once technical and commercial feasibility are established — and the choice materially flatters near-term EBITDA:
- Rising **capitalized R&D / total R&D ratio** signals aggressive accounting; a peer that expenses 100% is more conservative
- Check `get_fundamentals(section='cash_flow_quality')` for capitalized development spend in investing activities, and `get_company_context(section='filings', sub_section='notes_to_accounts')` for the capitalization policy disclosure
- Flag when capitalized R&D exceeds 40% of gross R&D — this is where accounting, not business economics, is driving reported EPS
- For peer benchmarking, compute a normalized EPS that expenses all R&D; the gap to reported EPS measures the accounting tailwind

### Warranty Provisioning Trend — The EV Reliability Timebomb
Warranty provisions are management-estimated reserves for future repair obligations. For legacy ICE vehicles, these run ~2-3% of revenue with predictable patterns. For EVs and software-heavy platforms, battery recalls, OTA failure modes, and evolving durability data make historical provisioning meaningfully under-reserved:
- Extract warranty provision trajectory from `get_company_context(section='filings', sub_section='notes_to_accounts')` and compare to revenue growth
- Provisions growing in line with or below revenue despite rising EV mix is a yellow flag; outright declining provision % as EV mix rises is a red flag — future quarters will see catch-up provisioning that compresses margin
- Any single large recall or software-update-linked provision disclosed in concall should be called out separately, not netted into routine warranty expense
