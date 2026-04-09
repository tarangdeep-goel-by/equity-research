## Regulated Power — Financials Agent

### Regulated ROE Framework
Regulated utilities earn a guaranteed ROE on equity invested in regulated assets. The actual return can exceed the base ROE through incentives:
- **CERC base ROE**: currently 15.5% on equity portion of regulated assets
- **Incentive income**: earned through Plant Availability Factor (PAF) above normative levels, fuel efficiency, and ash utilization
- Extract PAF and incentive income from `get_company_context(section='concall_insights')` — this is the key driver of above-base returns
- If PAF data unavailable, flag as open question

### Revenue Is Not a Growth Metric
- Regulated revenue = fuel cost passthrough + capacity charges. Fuel cost passthrough inflates/deflates revenue without affecting profit
- Focus on **capacity charges** (the regulated return component) and **incentive income** as the real profit drivers
- Capacity addition (MW) is the growth metric, not revenue growth

### Receivables & SEB Risk
- State Electricity Boards (SEBs) are often slow payers. Track receivable days carefully
- If receivables > 90 days of revenue, analyze by counterparty if available from concall_insights
- Late payment surcharge (LPSC) income can be material — check if it's in Other Income

### Capex Cycle
- Regulated capex earns guaranteed returns — more capex = more regulated equity base = more profit
- Track capex pipeline (MW under construction) from concall_insights
- Green/renewable capacity additions vs thermal — the transition trajectory
