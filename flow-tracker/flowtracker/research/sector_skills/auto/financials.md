## Auto / EV — Financials Agent

### Per-Unit Economics
Auto companies should be analyzed per-unit alongside aggregate financials. Extract unit volumes from `get_company_context(section='concall_insights')` or `sector_kpis`:
- **Revenue per unit** = Total Revenue / Units Sold — tracks ASP trends
- **EBITDA per unit** — operating profitability per vehicle
- If unit volumes available, use `calculate` tool to derive. If not, flag as open question

### Wholesale vs Retail Gap (CRITICAL)
Companies report wholesale (factory dispatches) for revenue, but actual demand = retail sales.
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
