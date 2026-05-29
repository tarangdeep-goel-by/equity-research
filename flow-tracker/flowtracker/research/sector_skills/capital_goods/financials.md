## Capital Goods / Industrials — Financials Agent

### Order Book Analysis — The Key Metric
Extract from `get_company_context(section='concall_insights')` or `sector_kpis`:
- **Order inflow** (₹ Cr) — current quarter and trailing 12M
- **Order book** (₹ Cr) — total unexecuted orders
- **Book-to-Bill ratio** = order inflow / revenue. >1.0x = pipeline growing
- **Order book / TTM revenue** = execution visibility in years

If not available from concalls, flag as the #1 open question — for capital goods companies, order book visibility matters more than current P&L because revenue is a lagging indicator of orders won quarters ago.

### Margin Risk from Contract Type
- **Lump-sum fixed-price contracts** carry full input cost risk — if RM costs spike, margins get crushed with no passthrough
- **Price Variation Clauses (PVC)** are the standard Indian mitigant on fixed-price orders — escalation/de-escalation is passed to the buyer via IEEMA price indices and the RBI WPI. PVC-covered fixed-price ≠ lump-sum risk. Cost-plus is a separate, distinct contract type. Track the PVC-covered vs lump-sum vs cost-plus mix from concall_insights
- Margin trajectory must be analyzed in context of contract mix: expanding margins on genuine lump-sum fixed-price = real efficiency; expanding margins on PVC/cost-plus = just input cost passthrough timing

### Working Capital & Receivables — The Structural Cash Trap
Capital goods companies have structurally long working capital cycles because projects span months to years, and large customers (especially government/PSU) pay slowly. This means reported profits can look healthy while cash is trapped in receivables and WIP inventory.
- Use `get_fundamentals(section='working_capital')` for receivable/inventory/payable days
- **Receivables aging matters more than a flat 90-day cut** — in B2G/PSU EPC, receivables structurally stretch well beyond 90 days; that alone is not a red flag. Under Ind AS 109 the simplified ECL aging matrix triggers heavy provisioning much further out (commonly ~100% only past 180 days, and B2G books run to 365+). Flag counterparty risk on receivables >180 days, rising ECL provisions, and a widening gap between billed receivables and cash collected
- **Advances from customers / mobilisation advances** = under Ind AS 115 these are **Contract Liabilities** (consideration received ahead of performance), not generic "advances." Positive signal for capital goods (customer-funded WC); analyze in tandem with Contract Assets (see below)
- **Ind AS 115 contract-asset cash trap** — revenue booked over time (cost-to-complete) creates **Contract Assets / Unbilled Revenue** (a conditional right to payment, not yet billable). Aggressive unbilled-revenue build = profit recognized without cash. Track Contract Assets (Unbilled Revenue) as % of revenue and its trend; flag **Retention Money** aging >2 years (5-10% of contract value held back until the Defect Liability Period ends)
- Track CCC trend: improving CCC = management quality signal

### Off-Balance-Sheet & Payables Risks
- **Contingent liabilities / Bank Guarantees** — EPC and capital goods players run on non-fund-based limits (Performance BGs, Advance BGs). These off-balance-sheet exposures can wipe out equity instantly if invoked by a PSU/government counterparty. Calculate contingent liabilities (especially Bank Guarantees) as a % of Net Worth; flag if >100% or rapidly expanding
- **MSME payables squeeze (Sec 43B(h))** — from FY25 (AY 2024-25), payments to Micro & Small registered vendors not settled within 45 days (15 days absent a written agreement) are disallowed as tax deductions until actually paid. This forces fast vendor payment against slow government receivables, squeezing working capital. Check trade-payables aging for Micro/Small dues >45 days and flag potential tax outgo/disallowance under Sec 43B(h)

### FX Impact
If >30% revenue from exports, analyze currency impact on margins and competitive positioning. Check Other Income for FX gains/losses.
