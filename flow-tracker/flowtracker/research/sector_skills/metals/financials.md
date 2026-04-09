## Metals & Mining — Financials Agent

### Valuation Framework
- **EV/EBITDA** is the primary metric, not PE (cyclical trap — lowest PE at cycle peak, highest at trough)
- Call `get_valuation(section='band', metric='ev_ebitda')` for historical band. Current vs 5Y range
- Also present EV/tonne for mining companies when production data is available from concalls

### Commodity Cycle Position
- Identify cycle phase: expansion / peak / contraction / trough
- Margins are commodity-price-driven — separate price effect from volume effect in revenue growth
- Check capacity utilization from `concall_insights` to confirm cycle position

### Leverage — Track Absolute Net Debt, Not Just Ratios
- **AVAILABLE** from `get_quality_scores(section='metals')` — returns `net_debt` in absolute crores
- In peak cycles, EBITDA explodes making Net Debt/EBITDA look artificially safe. Track **absolute net debt trajectory** over 3-5 years
- Are they retiring debt or just riding cycle-peak EBITDA? Flag if absolute debt is rising despite "low" leverage ratio

### Capex: Maintenance vs Growth
- Extract from `concall_insights` — management typically discloses this split
- Metals require heavy maintenance capex. If CFO barely covers maintenance capex, dividend sustainability is at risk regardless of payout ratio
- If split unavailable, flag as open question

### Dividend Sustainability (CRITICAL for High-Yield Miners)
- MUST call `get_events_actions(section='dividends')` for actual payout history
- Compute Dividend / FCF coverage for 3+ years. Flag if >1.0x in any year
- For promoter-driven extraction (e.g., Vedanta), flag the cash-up mechanism explicitly

### Working Capital
- Inventory days are critical — rising inventory in falling commodity prices = balance sheet risk
- Receivables quality matters less (spot/short-term contracts)
