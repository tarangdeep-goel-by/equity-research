## Capital Goods / Industrials — Financials Agent

### Order Book Analysis (THE Key Metric)
Extract from `get_company_context(section='concall_insights')` or `sector_kpis`:
- **Order inflow** (₹ Cr) — current quarter and trailing 12M
- **Order book** (₹ Cr) — total unexecuted orders
- **Book-to-Bill ratio** = order inflow / revenue. >1.0x = pipeline growing
- **Order book / TTM revenue** = execution visibility in years

If not available from concalls, flag as the #1 open question — this is more important than P&L analysis for capital goods.

### Margin Risk from Contract Type
- **Fixed-price contracts** carry input cost risk — if RM costs spike, margins get crushed with no passthrough
- **Cost-plus / escalation contracts** protect margins — track the mix from concall_insights
- Margin trajectory must be analyzed in context of contract mix: expanding margins on fixed-price = genuine efficiency; expanding margins on cost-plus = just input cost deflation

### Working Capital & Receivables (CRITICAL)
Capital goods companies have structurally long working capital cycles:
- Use `get_fundamentals(section='working_capital')` for receivable/inventory/payable days
- **Receivables >90 days of revenue** = flag counterparty payment risk. Government/PSU orders pay slower
- **Advances from customers** (liability side) = positive signal for capital goods (customer-funded WC)
- Track CCC trend: improving CCC = management quality signal

### FX Impact
If >30% revenue from exports, analyze currency impact on margins and competitive positioning. Check Other Income for FX gains/losses.
