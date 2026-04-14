## Telecom Infrastructure (Tower-Co) — Financials Agent

### Tenancy Ratio — The Core Economic Metric
Tenancy ratio (tenants per tower) is the single most important driver of tower-co economics. A tower has roughly the same fixed cost regardless of how many tenants occupy it — ground lease, power backup, maintenance, security are all largely fixed. That means each incremental tenant drops ~85% to tower-co EBITDA. Extract from `get_company_context(section='concall_insights')` or `sector_kpis`:
- Benchmark: tenancy starts at 1.0 at commissioning, reaches 1.7-2.2 at steady state, and 2.5+ is industry-leading
- Rising tenancy = operating leverage working; falling tenancy typically signals telco-customer consolidation (operator mergers, spectrum reallocation, weak-operator site exits) or site decommissioning
- A flat tenancy ratio with growing tower count masks economics — always analyze both together

### Rental Per Tenant — The Pricing Metric
Effective monthly rental per tenant (net of contracted discounts) is typically ₹35K-55K/month in India. Telco consolidation has suppressed rentals 20-30% from peak levels — telcos negotiating harder as their own sector has consolidated to three players. Any rental hardening in disclosures is a leading indicator that the telco sector is healing, which feeds back into tower-co bargaining power.

### Churn — The Hidden Risk
Churn (tenants exiting per year via site decommissioning) is the hidden erosion that gross tower additions can mask. Extract from concall — telcos publish their own site rationalization plans and tower-cos report churn figures.
- Benchmark: <3% annual is healthy, 5-8% signals an active consolidation wave, >10% is structural loss
- High churn eats backlog even if headline tenancy looks stable — always net churn against gross additions

### Lease Liability Bifurcation — The IndAS 116 Trap
Under IndAS 116, long-term rental contracts sit as Right-of-Use (ROU) assets with offsetting lease liabilities on the tower-co balance sheet. This inflates reported EBITDA by shifting ground-rental expense out of opex into depreciation + interest below the EBITDA line.
- Reported IndAS EBITDA margins look 60%+; pre-IndAS comparable margins are ~45-50%
- Pre-IndAS EBITDA = reported EBITDA − lease liability unwind (disclosed in notes)
- Always use the pre-IndAS number for peer comparison with global tower-cos on different accounting regimes to avoid apples-to-oranges errors. `get_fundamentals(section='cost_structure')` may surface lease costs separately

### Energy Pass-Through — Revenue But Not Margin
Diesel and power recovery from tenants is pass-through: cost in COGS, recovery in revenue. This inflates headline revenue without any margin contribution. Always compute EBITDA margin on core rental revenue (not total reported revenue) to get the true economic picture. Extract the energy revenue split from concall if disclosed — it's typically 20-30% of reported revenue.

### Receivables Concentration — Telco Payment Risk
Tower-cos have just 3-5 customers (telcos) and the book is highly concentrated. If any one customer — particularly a financially stressed operator — stretches payment terms or negotiates retrospective discounts, it hits cash flow immediately. Extract from `get_fundamentals(section='balance_sheet_detail')`:
- Receivable days >120 = stressed customer book
- Track one-time provisions for impaired receivables from any single stressed counterparty; such provisions often cluster over multiple quarters against the same name
- Customer-wise revenue concentration (if disclosed) matters more than for almost any other sector

### Cash Flow — Capex-Light, Distribution-Heavy
Mature tower-cos are structurally capex-light — maintenance capex ~5% of revenue. Any capex spike signals expansion (5G rollout, new circles, small cells) rather than recurring spend. Strong FCF typically funds 70-90% dividend payouts — this is the equity case for tower-cos. Check `get_events_actions(section='dividends')` for the payout trend; a falling payout ratio without a visible growth investment is a red flag.

### Balance Sheet — Leverage Is Structural, Not Distress
Tower-cos routinely operate at 2.5-4x Net Debt/EBITDA. This is justified by long-dated contracted revenue with credit-worthy counterparties — comparable to utility leverage. A sudden leverage rise usually signals acquisition, not distress. The real financial exposure is interest rate risk: always review debt maturity profile and the mix of fixed vs floating rate debt from `get_fundamentals(section='balance_sheet_detail')`.

### Valuation
- **EV/EBITDA (adjusted for lease accounting)** is the primary metric — 8-12x at steady state, 6-8x during consolidation phases. Call `get_valuation(section='band', metric='ev_ebitda')` for historical context
- **P/E is distorted** by high depreciation + lease interest under IndAS 116 — avoid as a primary metric
- **Dividend yield** of 5-8% is common for mature tower-cos — they are a yield play more than a growth play. Compare against sector median and 10Y G-Sec yield
