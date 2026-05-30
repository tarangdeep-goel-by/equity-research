## Packaging & Paper — Financials Agent

### The Pass-Through Lag — The Primary Earnings Driver for Converters
For converters (EPL, TCPL, Huhtamaki), raw material (polymer/paper) makes up 55-65% of revenue. They operate on cost-plus contracts with FMCG clients, but there is a **lag of 30 to 90 days** in passing on price changes.
- **When RM prices spike:** Gross margins compress this quarter (inventory is consumed at higher replacement cost, but selling prices haven't adjusted). 
- **When RM prices fall:** Gross margins optically expand (selling prices remain high for a month while input costs drop).
**Rule:** When analyzing a QoQ margin contraction or expansion, cross-reference the underlying commodity price (crude/polymer/pulp) via `get_market_context(section='macro')`. Explicitly state if the margin move is structural or just a temporary pass-through lag.

### Inventory Gains and Losses
For upstream producers (Paper mills, Film producers), inventory valuation creates massive P&L swings.
- A paper mill holding 60 days of wood pulp inventory will report massive "inventory gains" in EBITDA when global pulp prices surge.
- This is non-recurring. Strip out inventory gains/losses when computing core operating EBITDA/tonne. Look for management quantification of inventory effects in `get_company_context(section='concall_insights', sub_section='management_commentary')`.

### Working Capital Intensity — The Cash Flow Bleed
Packaging is highly working-capital intensive. FMCG and Pharma clients are powerful and dictate terms, often stretching payables to 90-120 days.
- Extract Debtor Days and Inventory Days from `get_fundamentals(section='working_capital')`.
- A structural increase in debtor days signals that the packaging company is losing bargaining power or extending credit to win volumes.
- **Operating Cash Flow (OCF) vs. EBITDA:** Compare these. If EBITDA is growing but OCF is stagnant, the company is trapping capital in receivables.

### Capex Lumps and ROCE Dilution
Capacity additions in packaging (a new glass furnace, a new BOPP line, a new paper machine) are large, lumpy, and take 18-24 months to commission.
- **The ROCE J-Curve:** When a new ₹500 Cr line is commissioned, Gross Block spikes immediately, but utilization takes 2-3 years to ramp up to optimal levels (80%+). ROCE will mechanically crash in year 1 and recover by year 3.
- Do not penalize a company for a temporary ROCE dip if it coincides with a major capacity commissioning. Check `get_company_context(section='concall_insights', sub_section='operational_metrics')` for the utilization ramp-up trajectory of new lines.

### Leverage — Net Debt / EBITDA
Because capex is lumpy, debt levels oscillate. 
- Extract Net Debt from `get_fundamentals(section='balance_sheet_detail')`.
- For cyclical producers, a Net Debt / EBITDA ratio > 2.5x at the *peak* of a cycle is a massive red flag. When spreads mean-revert and EBITDA halves, that 2.5x leverage ratio will instantly blow out to 5.0x, triggering distress.
- For stable converters, 1.5x - 2.0x Net Debt / EBITDA is comfortable due to predictable cash flows.

### Operating Leverage
Track **Capacity Utilization %**. Packaging has high fixed costs (power, depreciation on heavy machinery). 
- Below 65% utilization, margins bleed.
- The sweet spot for margin expansion is the journey from 70% to 85% utilization. Above 85%, the company must announce new capex, starting the cycle over.
