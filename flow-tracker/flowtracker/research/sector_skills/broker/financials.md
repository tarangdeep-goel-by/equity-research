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

### Cash vs F&O Revenue Concentration — Regulatory & Cyclical Red Flag
Indian brokerage revenue mix has structurally tilted toward F&O (futures and options) over the past 3-5 years; retail options in particular now account for a dominant share of industry volumes. This is the single largest regulatory and cyclical risk a broker faces:
- **F&O concentration %** — revenue share from derivatives vs cash segment. Retail-options-heavy books (>60% F&O) carry acute exposure to SEBI's ongoing derivative tightening (lot size hikes, weekly-expiry reduction, higher margin requirements)
- SEBI measures already announced or under consultation can compress F&O volumes 20-40% — a broker with no cash-segment / distribution diversification will see direct revenue hit
- Extract the F&O vs cash split from `get_company_context(section='concall_insights')` or sector_kpis; use `get_company_context(section='filings')` for market-share disclosures
- Regulatory risk is high-probability and non-cyclical — discount valuations accordingly for pure F&O-dependent franchises

### Unit Economics — Active Client, CAC, ARPU Over Gross Adds
Gross client additions are vanity. Broker earnings durability rests on **active clients who trade repeatedly**, not on a demat count. The institutional framework:
- **NSE 12-Month Active Clients** — the regulator-published count of clients who traded at least once in the past 12 months. Active-to-total ratio below 40% signals a "zombie" client book that won't compound into revenue
- **CAC (Customer Acquisition Cost)** — marketing and referral spend / net client adds. Falling CAC with rising active-ratio is the gold standard; both metrics must move together
- **ARPU (Revenue per Active Client)** — the yield per actually-trading client. High ARPU with low active ratio is fragile (small power-user base carrying the P&L)
- **LTV / CAC** — payback period should be < 18 months for a sustainable franchise
- Extract from `get_company_context(section='sector_kpis')` — where not disclosed, flag as open question rather than ratioing against gross demat additions

### MTF / Margin Trading Asset Quality — ECL on Secured Books
The MTF (Margin Trading Funding) book is secured against equity collateral but is not risk-free. Flash crashes or single-stock volatility can overwhelm the collateral haircut and trigger losses. The disclosed metrics to watch:
- **ECL (Expected Credit Loss) provisions** — track trajectory as % of MTF book. Rising ECL with flat book = deteriorating asset quality
- **Collateral haircut structure** — what % of collateral is in illiquid mid/small-cap stocks vs large-cap and cash equivalents. A book collateralized 40%+ in mid/small-cap carries materially higher tail risk
- **Bad debt write-offs** — annualized loss rate on MTF. Industry norm is < 0.2% of book; > 0.5% is stressed
- Extract from `get_fundamentals(section='balance_sheet_detail')` for ECL reserves and concall disclosures for collateral composition — these are typically buried in notes-to-accounts rather than headlined
