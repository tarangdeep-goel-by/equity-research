## Metals & Mining — Financials Agent

### Valuation Framework
- **EV/EBITDA** is the primary metric, not PE. Cyclical earnings make PE misleading — PE is lowest at the cycle peak (inflated earnings) and highest at the trough (depressed earnings), which is the opposite of what you want for buy/sell signals
- Call `get_valuation(section='band', metric='ev_ebitda')` for historical band. Current vs 5Y range
- Also present EV/tonne for mining companies when production data is available from concalls

### Commodity Cycle Position
- Identify cycle phase: expansion / peak / contraction / trough
- Margins are commodity-price-driven — separate price effect from volume effect in revenue growth
- Check capacity utilization from `concall_insights` to confirm cycle position

### Debt Maturity & Leverage
- **Available** from `get_quality_scores(section='metals')` — returns `net_debt` in absolute crores
- In peak cycles, EBITDA explodes making Net Debt/EBITDA look artificially safe. Track **absolute net debt trajectory** over 3-5 years to see whether the company is actually retiring debt or just riding cycle-peak EBITDA
- Flag if absolute debt is rising despite "low" leverage ratio
- If Net Debt/EBITDA > 2x, analyze debt maturity from `get_fundamentals(section='balance_sheet_detail')`: what % is short-term vs long-term?

### Capex: Maintenance vs Growth
- Extract from `concall_insights` — management typically discloses this split
- Metals require heavy maintenance capex. If CFO barely covers maintenance capex, dividend sustainability is at risk regardless of what the payout ratio says
- If split unavailable, flag as open question

### Dividend Sustainability — Why It Matters for High-Yield Miners
Metals companies often sport high dividend yields, but cyclical earnings mean today's yield can vanish quickly. Promoter-driven group structures may pay unsustainable dividends to extract cash upstream to the holdco — the payout ratio alone won't reveal this; check whether the trailing dividend is funded from FCF or from borrowings.
- Call `get_events_actions(section='dividends')` for actual payout history
- Compute Dividend / FCF coverage for 3+ years. Flag if >1.0x in any year (paying more than free cash flow)
- For promoter-driven extraction, flag the cash-up mechanism explicitly

### Working Capital
- Inventory days are critical — rising inventory in falling commodity prices = balance sheet risk
- Receivables quality matters less (spot/short-term contracts)

### Cost-Curve Quartile — Captive RM Integration Drives Cycle Survival
The single biggest differentiator across global metals and mining operators is **position on the global cost curve** — not margin in the current quarter. A producer in the 1st quartile (lowest-cost 25%) stays profitable even at cycle troughs; a 4th-quartile producer loses money for years at a time. Cost-curve position is overwhelmingly determined by **captive raw material integration**:
- **Steel**: captive iron ore + coking coal vs merchant buying. Captive ore can be 40-60% cheaper per tonne than merchant spot
- **Aluminium**: captive bauxite + captive power (coal-fired or renewable) vs grid-bought. Power is ~35% of smelting cost
- **Copper / Zinc**: captive mine supply vs concentrate purchased from third parties (TC/RC dependence)
- Extract the integration profile from `get_company_context(section='concall_insights')` or investor presentations. Peers trading at similar multiples may sit in wildly different cost quartiles — always state the quartile view, not just absolute margin
- Compare via `get_peer_sector(section='benchmarks')` where disclosed

### Through-Cycle ROCE — 7-10 Year Average, Not Point-in-Time
Peak-cycle ROCE of 25-40% in a metals producer can mask trough years of 0-5%. A single-period ROCE is therefore misleading; the capital-intensive nature of metals only reveals itself across a full cycle.
- Compute **trailing 7-10Y average ROCE** using `get_fundamentals(section='cagr_table')` historical ROCE and `calculate`. This is the metric that should anchor valuation, not the current-year number
- A producer whose through-cycle ROCE exceeds cost of capital (~11-13% in India) is a real value creator; one whose through-cycle ROCE is below COC is destroying value even if the current year looks exceptional
- Flag companies where trough-year ROCE turns negative — these are pure price-takers with no moat

### Conversion Spreads — The Only True Operational Metric
Absolute commodity prices are noise — they move everyone at once. The real measure of operational efficiency is the **conversion spread** between the input RM cost and the product realization:
- **Steel**: HRC (hot-rolled coil) price − (iron ore cost × tonnage ratio + coking coal cost × tonnage ratio). Widening conversion spread signals genuine pricing power or cost improvement; narrowing spread signals commoditization even when absolute prices look healthy
- **Copper / Zinc smelters**: Treatment Charge / Refining Charge (TC/RC) spread vs concentrate cost. Industry-standard benchmark disclosed quarterly by smelter associations
- **Aluminium**: LME price − (alumina cost + power cost + carbon cost)
- Track QoQ and YoY; compare to peers via `get_peer_sector(section='benchmarks')`. Two producers with identical EBITDA margins can have very different conversion spread trajectories — only the latter predicts future margin direction
