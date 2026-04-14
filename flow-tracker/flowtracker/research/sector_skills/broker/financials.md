## Broker — Financials Agent

### Revenue Mix Decomposition — Why It Matters
For a broker, the revenue mix tells you more than total revenue. Three streams behave very differently and need to be isolated before drawing any conclusions on growth quality:
- **Broking fees** — transaction-linked, pro-cyclical with market volumes. Falls sharply in bear phases
- **Interest income** — MTF (Margin Trading Funding) book + float on client balances. Near-zero cost to generate and highly sensitive to the interest rate cycle
- **Distribution income** — MF commissions, insurance, fixed income. Sticky, annuity-like, the closest thing to recurring revenue a broker has

Extract mix from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`. Interest yield (NII on MTF book) is a critical driver — a 100bp move in funding cost vs lending rate swings PAT significantly, so always quantify the spread rather than stopping at absolute interest income.

### SEBI Ring-Fencing — Critical Balance Sheet Rule
Client assets (margin deposits, settlement obligations) are ring-fenced by SEBI regulations. They cannot fund the broker's proprietary lending or investment book. When analyzing balance sheet funding:
- Client payables (liability) must be matched by client-segregated assets — fixed deposits, government securities, bank balances held in client name
- The MTF loan book must be funded from the broker's own net worth plus external borrowings, NOT from client float
- If the loan book exceeds net worth + disclosed borrowings, there is a funding gap that needs explaining before concluding the balance sheet is healthy

### MTF Yield & Float Income — The Margin Engine
- **MTF yield** = interest income from MTF book / average MTF outstanding. Benchmark ~14-16% (capped at repo + spread per SEBI norms)
- **Float income** = interest earned on client deposits held by broker awaiting settlement. Sensitive to overnight rates and CRR cycle
- Declining yields with stable book = intensifying competition. Rising book with stable yield = pure growth. Rising book with falling yield = share grab at the cost of margin — flag this

### Regulatory Costs — Not Buried in Expenses
SEBI turnover fees, STT, stamp duty are typically pass-through items (grossed up in revenue and expenses). When analyzing "true" operating margin, strip these from both lines for a cleaner picture — otherwise margin comparisons across brokers with different accounting conventions become meaningless. Check `get_fundamentals(section='expense_breakdown')` — regulatory/transaction charges should appear as a named line.

### IPO & Listing-Linked Anomalies
Pre-IPO accounting distortions (ESOP charges, IPO expenses, deferred revenue on subscription plans) can distort 2-3 years of financials. Before leaving such anomalies as open questions, call `get_company_context(doc_type='filings')` or `get_events_actions(section='corporate_actions')` — DRHP/RHP documents disclose these in granular detail and usually reconcile the "reported vs normalized" gap.

### Return Metrics — ROE vs ROA
- ROE can be artificially low in pre-IPO years due to IPO-raised capital sitting idle on the balance sheet
- **Core ROE** = PAT / (Tangible net worth − IPO cash idle) is more meaningful than headline ROE
- Post-IPO normalized ROE typically takes 2-3 years to reveal itself as IPO proceeds are deployed into the MTF book or product expansion

### Valuation Basis
- Use **PE on normalized earnings** (stripping pre-IPO one-offs, ESOP charges, exceptional items) as the primary metric
- **P/B** as a secondary check — brokers should trade at a premium to book due to the capital-light nature of fee income, unlike banks where book value anchors valuation
- Call `get_valuation(section='band', metric='pe')` for historical PE band context and compare against fintech/platform peers rather than pure-play banks
