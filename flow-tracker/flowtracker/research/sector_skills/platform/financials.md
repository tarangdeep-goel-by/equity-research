## Platform / Internet — Financials Agent

### Unit Economics — The Core Analysis
Platform P&Ls are meaningless at the aggregate level — high growth masks whether the underlying economics work. Decompose into unit economics from `get_company_context(section='concall_insights')` or `sector_kpis`:
- **Revenue per order** — monetization metric
- **Contribution margin per order** — after variable costs (delivery, payment gateway, packaging)
- **EBITDA per order** — after fixed costs allocation
- If these aren't in concall data, derive contribution margin from `get_fundamentals(section='cost_structure')` — delivery/logistics costs are typically in "Other Expenses"

### Expense Decomposition — Where the Money Actually Goes
Platform "Other Costs" often exceed 50% of revenue, making it the largest line item. Without breaking this down via `get_fundamentals(section='expense_breakdown')`, you're analyzing a black box:
- **Delivery/logistics costs** — the biggest variable cost for food delivery / quick commerce
- **Marketing/CAC** — customer acquisition spend. Track as % of revenue — should be declining for mature platforms
- **Technology costs** — relatively fixed, provides operating leverage
- **Employee costs** — often high for tech-heavy platforms

### Business Mix Shift
Many Indian platforms are shifting business models (e.g., Zomato: food delivery → quick commerce → going-out):
- Track revenue contribution by segment from concall_insights
- New segments typically have WORSE unit economics initially — flag if consolidated margins are being dragged by a new segment
- Separate mature segment profitability from investment-phase segments

### ESOP Adjustment — Why "Adjusted EBITDA" Understates Real Costs
New-age companies routinely exclude ESOP costs from "Adjusted EBITDA." ESOPs are real economic cost — they dilute shareholders and would otherwise need to be paid as cash compensation. Excluding them hides the true cost of running the business.
- Always compute **EBITDA including ESOP costs** (reported EBITDA minus ESOP expense add-back)
- If the company reports "Adjusted EBITDA" that excludes ESOPs, flag: "Adjusted EBITDA of ₹X Cr excludes ₹Y Cr ESOP costs — true EBITDA is ₹Z Cr"
- ESOP expense is in `get_fundamentals(section='cost_structure')` under employee costs or as a separate line
- Annual dilution from ESOPs: check share count growth YoY. >2% annual dilution is material

### Cash Burn & Balance Sheet
- Track **quarterly cash burn** = change in cash + investments
- **Cash runway** = current cash / quarterly burn rate
- Flag equity dilution risk if cash runway < 8 quarters
- Use `get_fundamentals(section='balance_sheet_detail')` for cash position

### Take Rate — Distinct From Revenue-per-Order
Revenue-per-order conflates ticket-size inflation (cart value growing because people buy pricier items) with genuine monetization gains. The correct metric is **Take Rate = Platform Revenue / Gross Merchandise Value (GMV or GOV)**:
- For marketplaces / commerce: Take Rate = Revenue / GMV (typically 10-25%)
- For food delivery / quick commerce: Take Rate = Revenue / Gross Order Value (typically 18-25% including delivery fee + platform fee + commissions)
- Rising Take Rate with stable GMV growth = real pricing power over merchants or users
- Stable Take Rate with rising AOV = no monetization gain, just inflation tailwind
- Declining Take Rate = competition, merchant pushback, or strategic subsidy
- Extract GMV/GOV and platform revenue separately from `get_company_context(section='concall_insights', sub_section='operational_metrics')` — compute Take Rate via `calculate` when not directly disclosed

### Treasury / Float Other Income vs Core Operating PAT
Indian internet companies often sit on ₹5,000–30,000 Cr of IPO proceeds invested in short-term debt + deposits, earning 7-8% yields. This generates material "Other Income" that can flatter or even create reported PAT while core operations are still loss-making:
- Isolate **Other Income from core operating PAT**: Core Operating PAT = Reported PAT − (Other Income × (1 − tax rate))
- If Other Income > 50% of reported PAT, flag the dependency explicitly — a return to profitability that comes from float yield rather than operating leverage is not a durable thesis
- Track trajectory: as IPO cash is deployed into acquisitions or dark-store capex, Other Income should decline — which means headline PAT can deteriorate even as core operations improve
- Check `get_fundamentals(section='annual_financials')` for Other Income line and `balance_sheet_detail` for cash & investments composition

### Rule of 40 — Peer Benchmark for Growth-Stage Internet
Standard P/E comparisons fail for loss-making platforms. The institutional-standard test is the **Rule of 40**: Revenue Growth % + FCF Margin % (or adjusted EBITDA margin % if still pre-FCF):
- **>40%** = justified valuation premium; growth is outpacing cash burn
- **20-40%** = acceptable but needs monitoring; dilution risk depends on runway
- **<20%** = growth has decelerated without a commensurate margin gain — the thesis is breaking
- Track the metric quarterly (annualized): Revenue YoY Growth % + FCF / Revenue %. Compare to pure-play peers via `get_peer_sector(section='benchmarks')`
- This is the only benchmark that holds across pre-profit, transitioning, and mature-profit platform stages
