## Real Estate — Financials Agent

### P&L Revenue Is Backward-Looking — Why It Misleads
Under Ind-AS 115 (project completion method), revenue is recognized only when the project is substantially complete and possession is given. This means:
- **Reported revenue** reflects projects completed 2-3 years ago, not current business momentum
- A company can be selling aggressively today but show flat/declining revenue because completions haven't caught up
- Drawing conclusions about business trajectory from P&L revenue alone will produce wrong analysis

### The Real Metrics — Pre-Sales and Collections
Because P&L revenue lags reality by years, the actual business metrics live in concall disclosures. Call `get_company_context(section='concall_insights')` and `get_company_context(section='sector_kpis')` — without these, the report is analyzing backward-looking noise rather than current momentum.
- **Pre-sales (Booking Value in ₹ Cr)** — current demand signal. This IS the revenue equivalent for real estate
- **Pre-sales Volume (mn sq ft)** — physical demand, strips out ASP inflation
- **Collections (₹ Cr)** — cash actually received from customers. Compare to pre-sales for collection efficiency
- **Net Debt** — the most important balance sheet metric. Track absolute reduction over time

### Cash Flow Is King
- Compare **Operating Cash Flow** against **Collections**. OCF should track collections closely
- If OCF << Collections, the company is burning cash on new land/construction faster than collecting
- Track Net Debt reduction as the primary measure of financial health. Real estate deleveraging = equity value creation

### What Structured Tools CAN Tell You
- `get_fundamentals(section='balance_sheet_detail')` — borrowing structure, cash position, net debt
- `get_fundamentals(section='cash_flow_quality')` — OCF trajectory, capex (land + construction)
- `get_fundamentals(section='working_capital')` — advances from customers (a GOOD sign in real estate = money collected before completion)
- `get_quality_scores(section='realestate')` — pre-computed real estate metrics if available

### Skip or Heavily Adapt Standard Frameworks
- **DuPont decomposition is misleading** — margin × turnover × leverage computed on Ind-AS 115 revenue produces meaningless numbers. If you include DuPont, compute it on pre-sales (from concalls) not reported revenue
- **Standard earnings quality checks** (CFO/PAT, accrual ratio) are distorted by project-based cash flows — advances from customers inflate CFO, completion timing distorts PAT

### Forward-Looking Metrics (from concall_insights)
- **GDV (Gross Development Value) of launch pipeline** — total potential revenue from planned launches. This is the growth signal
- **Unsold inventory** — in months (unsold units / monthly absorption rate). >18 months = oversupply risk, <6 months = pricing power
- **Realization per sq ft** — ASP trend. Rising realization = pricing power or product mix shift to premium

### Valuation
- **P/E is misleading** due to lumpy revenue recognition. Use NAV (Net Asset Value) based on land bank + ongoing projects
- **EV/Pre-sales** or **Mcap/Pre-sales** as a proxy for PE
- Net Debt / Equity is the risk metric — >1.0x is elevated for Indian developers
- If Net Debt/EBITDA > 2x, analyze debt maturity from `get_fundamentals(section='balance_sheet_detail')`
