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
- **ESOP charge to P&L** — the non-cash compensation line (see ESOP Adjustment below); critical for a tech platform's true profitability

**When `expense_breakdown` returns only an aggregate "Other Expenses" %** (no marketing / logistics / tech split — a known data limitation), do not silently drop CAC / contribution-margin. Pull the split from the AR other-expense schedule (`get_company_context(section='annual_report', sub_section='notes_to_financials')`) or concall `operational_metrics`. If it is genuinely undisclosed, state the gap explicitly — CAC and contribution margin are critical platform metrics, not optional. A silent omission reads as an analytical miss; a stated gap reads as diligence.

### Business Mix Shift
Many Indian platforms are shifting business models (e.g., Zomato: food delivery → quick commerce → going-out):
- Track revenue contribution by segment from concall_insights
- New segments typically have WORSE unit economics initially — flag if consolidated margins are being dragged by a new segment
- Separate mature segment profitability from investment-phase segments

### ESOP Adjustment — Why "Adjusted EBITDA" Understates Real Costs
New-age companies routinely exclude ESOP costs from "Adjusted EBITDA." ESOPs are real economic cost — they dilute shareholders and would otherwise need to be paid as cash compensation. Excluding them hides the true cost of running the business.
- Always anchor on **EBITDA including ESOP costs**. Under Ind AS 102, the ESOP expense is already a charge in the statutory P&L, so *reported/statutory EBITDA already includes the ESOP cost* — do NOT subtract it again (that double-counts). The adjustment runs the other way: companies present an "Adjusted EBITDA" that ADDS BACK the ESOP charge to flatter the number, so true EBITDA = Adjusted EBITDA − ESOP add-back.
- If the company reports "Adjusted EBITDA" that excludes ESOPs, flag: "Adjusted EBITDA of ₹X Cr adds back ₹Y Cr of ESOP cost — true (ESOP-inclusive) EBITDA is ₹Z Cr"
- ESOP expense is in `get_fundamentals(section='cost_structure')` under employee costs or as a separate line
- Annual dilution from ESOPs: check share count growth YoY. >2% annual dilution is material

### Ind AS 116 (Leases) — EBITDA Inflation for Dark-Store / Warehouse-Heavy Models
For quick-commerce and any fulfilment-heavy platform with a large leased dark-store / warehouse footprint, Ind AS 116 capitalises the leases as right-of-use (ROU) assets. The economic rent is then split out of operating cost and re-routed BELOW EBITDA — into ROU-asset depreciation (D&A) and lease-liability interest (finance cost). Net effect: **reported/adjusted EBITDA is structurally inflated** versus a variable-cost (rent-as-opex) fulfilment model, and the inflation scales with store count. To compare like-for-like and to gauge true cash generation:
- Compute a **cash-EBITDA** by deducting the principal repayment of lease liabilities (the cash-rent equivalent) from reported EBITDA — pull lease-liability principal/interest from `get_fundamentals(section='cash_flow')` (financing section) and the ROU/lease notes via `get_company_context(section='annual_report', sub_section='notes_to_financials')`.
- Flag the gap explicitly: "Reported EBITDA ₹X Cr includes the Ind AS 116 benefit of ₹Y Cr (ROU depreciation + lease interest moved below the line); cash-EBITDA after lease principal is ₹Z Cr."
- This also distorts EV/EBITDA peer comparisons between dark-store-heavy and asset-light platforms — note the lease-accounting basis before comparing multiples.

### GST / Tax Contingent Liabilities on Delivery Fees
Food-delivery and quick-commerce platforms face live, large retrospective indirect-tax exposure that is often parked in contingent liabilities rather than provisioned. The DGGI / state GST authorities have issued 18% GST demands on **delivery fees** (treated as platform supply rather than pass-through to gig workers) — e.g. ~₹400-800+ Cr show-cause/demand notices to Zomato (incl. a ~₹803 Cr Maharashtra demand for Oct-2019–Mar-2022) and ~₹300+ Cr to Swiggy. These can also recur prospectively (the Council clarification creates an ongoing ~₹180-200 Cr/yr industry liability). Always:
- Read the **contingent-liabilities note** (`get_company_context(section='annual_report', sub_section='notes_to_financials')`) and recent filings (`get_company_context(section='filings')`) for DGGI/GST/income-tax notices on delivery fees, and total the exposure.
- Compare the aggregate exposure to the cash + investments balance and to annual operating cash flow — a multi-hundred-crore contingent liability that is not provisioned is a real downside-case hit to net cash and to the valuation floor.
- Distinguish "disclosed and disputed (contingent)" from "provided for" — an unprovisioned, advanced-stage demand is the more dangerous read.

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

## Rule of 40 Adjustment for Accounting Transitions
For platforms mid-transition in revenue recognition (1P → 3P accounting, net-to-gross revenue treatment, GMV→net revenue restatement), the Rule of 40 cannot use reported headline revenue growth — the reported number conflates unit-economic progress with accounting optics. Instead:
- Use **GOV/NOV growth** or **Bookings growth** from `get_company_context(section='concall_insights', sub_section='operational_metrics')`
- Use **segment-level pass-through revenue** (not consolidated) where possible
- If concall gives a like-for-like restated prior-period number, use that; otherwise caveat the Rule of 40 score with the accounting-basis note.

Rule of 40 formula still applies: `revenue_growth% + ebitda_margin% ≥ 40`. Direction of the accounting optic matters under Ind AS 115: shifting **3P→1P (agent→principal) grosses revenue UP** (you book the full GMV instead of only the commission), inflating headline growth and depressing margin %; shifting **1P→3P (principal→agent) nets revenue DOWN** (you book only the commission), which optically depresses headline growth while expanding margin %. Either way, strip the accounting effect and benchmark Rule of 40 on like-for-like GOV/bookings growth — a platform whose headline revenue is distorted by a 1P/3P recognition change can look stronger or weaker than its true unit economics warrant.

## Per-Order Unit Economics Derivation
When `get_company_context(section='concall_insights', sub_section='operational_metrics')` gives total orders and the financial segment gives segment revenue, DERIVE per-order metrics via `calculate`:
- **AOV (avg order value)** = `gov_cr × 1e7 / order_count` — AOV is basket size, so the numerator MUST be Gross Order Value (GOV) / GMV, not platform revenue. `revenue_cr × 1e7 / order_count` gives **revenue-per-order** (the platform's cut per order), a different and much smaller metric — never label it AOV. Use revenue-per-order and AOV side-by-side: revenue-per-order ÷ AOV ≈ the realised take-rate per order.
- **Delivery cost per order** = `delivery_cost_cr × 1e7 / order_count`
- **Contribution margin per order** = `(AOV − variable_cost_per_order) / AOV × 100`

These unit metrics are what platform investors track — reported EBITDA margin is a lagging aggregate. For quick-commerce, food-delivery, and hyperlocal platforms, a 200bp contribution-margin improvement per order at scale (1M+ orders/day) signals multi-year operating leverage ahead of consolidated EBITDA turning positive.
