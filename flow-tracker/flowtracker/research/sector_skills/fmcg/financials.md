## FMCG / Consumer Staples — Financials Agent

### Volume vs Price Growth — The Most Important Split
Revenue growth is a blended number that hides pricing power. Extract from `concall_insights` or `sector_kpis`:
- **Volume growth %** — real demand signal. Compare against peer median and the company's own historical range via `get_peer_sector(section='benchmarks')`
- **Price/mix growth %** — pricing power + premiumization. Pure price growth without volume is unsustainable and signals demand destruction
- If this split isn't in concall data, flag as the #1 open question

### Gross Margin vs A&P Spend Trade-off
This is how FMCG companies manage earnings — it's a deliberate lever:
- Track **Gross Margin** expansion/contraction (commodity cost driven — palm oil, milk, wheat)
- Track **A&P spend as % of revenue** — from `get_fundamentals(section='cost_structure')` if in expense schedules, else from `concall_insights`
- The key insight: are they REINVESTING gross margin gains into A&P (brand building, market share defense) or DROPPING it to EBITDA (short-term profit maximization)?
- Gross margin expanding + A&P declining = future market share risk. Flag this explicitly

### Working Capital (Negative WC = Strength)
**AVAILABLE** from `get_quality_scores(section='sector_health')` for FMCG — returns WC trend.
- Top Indian FMCG companies (HUL, ITC, Dabur) operate on **negative working capital** — advance collections from distributors + tight receivable management
- If WC turns positive or negative WC is shrinking, distributor leverage is breaking down — flag as structural deterioration
- Use `get_fundamentals(section='working_capital')` for receivables/inventory/payables breakdown

### Rural vs Urban Demand
- Rural recovery/slowdown is a key cyclical driver for Indian FMCG. Extract rural/urban growth split from `concall_insights`
- Rural demand is a LEADING indicator for volume recovery

### Channel Health & Trade Margins
- Watch for **channel stuffing** signals: primary sales (company to distributor) growing materially faster than secondary sales (distributor to retailer) — extract from concall_insights if available
- Rising trade receivables + flat/declining secondary sales = stuffing risk
- **Trade margins / promotions** — FMCG companies use trade schemes to push volume. If gross margin looks stable but trade spends are rising (hidden in "selling expenses" or "sales promotion"), effective realization is falling. Check `get_fundamentals(section='cost_structure')` for selling expense trends
