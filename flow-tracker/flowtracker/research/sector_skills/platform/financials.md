## Platform / Internet — Financials Agent

### Unit Economics (THE Core Analysis)
Platform P&Ls are meaningless at the aggregate level. Decompose into unit economics from `get_company_context(section='concall_insights')` or `sector_kpis`:
- **Revenue per order** — monetization metric
- **Contribution margin per order** — after variable costs (delivery, payment gateway, packaging)
- **EBITDA per order** — after fixed costs allocation
- If these aren't in concall data, derive contribution margin from `get_fundamentals(section='cost_structure')` — delivery/logistics costs are typically in "Other Expenses"

### Expense Decomposition (CRITICAL)
Platform "Other Costs" often exceed 50% of revenue. MUST call `get_fundamentals(section='expense_breakdown')`:
- **Delivery/logistics costs** — the biggest variable cost for food delivery / quick commerce
- **Marketing/CAC** — customer acquisition spend. Track as % of revenue — should be declining for mature platforms
- **Technology costs** — relatively fixed, provides operating leverage
- **Employee costs** — often high for tech-heavy platforms

### Business Mix Shift
Many Indian platforms are shifting business models (e.g., Zomato: food delivery → quick commerce → going-out):
- Track revenue contribution by segment from concall_insights
- New segments typically have WORSE unit economics initially — flag if consolidated margins are being dragged by a new segment
- Separate mature segment profitability from investment-phase segments

### ESOP Adjustment (CRITICAL for New-Age Tech)
New-age companies routinely exclude ESOP costs from "Adjusted EBITDA" — this hides real cash burn.
- Always compute **EBITDA including ESOP costs** (reported EBITDA minus ESOP expense add-back)
- If the company reports "Adjusted EBITDA" that excludes ESOPs, flag: "Adjusted EBITDA of ₹X Cr excludes ₹Y Cr ESOP costs — true EBITDA is ₹Z Cr"
- ESOP expense is in `get_fundamentals(section='cost_structure')` under employee costs or as a separate line
- Annual dilution from ESOPs: check share count growth YoY. >2% annual dilution is material

### Cash Burn & Balance Sheet
- Track **quarterly cash burn** = change in cash + investments
- **Cash runway** = current cash / quarterly burn rate
- Flag equity dilution risk if cash runway < 8 quarters
- Use `get_fundamentals(section='balance_sheet_detail')` for cash position
