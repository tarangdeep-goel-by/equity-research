## Building Materials — Financials Agent

### Cement Cost Structure — The Margin Engine
Cement is a game of pennies. You must decompose the cost structure per tonne. Extract these from `get_company_context(section='sector_kpis')`, `get_deck_insights(sub_section='key_metrics')`, or `get_annual_report(section='notes_to_financials')`:
1. **Power & Fuel Cost (₹/t):** Typically 25-30% of total cost. Driven by petcoke/imported coal prices. Track the **Green Power Share (WHRS + Solar/Wind)** — every 10% increase in green power share structurally reduces power cost by ₹50-80/t.
2. **Freight & Forwarding Cost (₹/t):** Typically 25-30% of total cost. Driven by diesel prices and **Lead Distance** (average distance cement travels from plant to market). A lead distance >300 km destroys margins. Track the rail vs. road mix.
3. **Raw Material Cost (₹/t):** Limestone mining cost, fly ash, and slag. Track the **Clinker Factor** (clinker-to-cement ratio). Lower clinker factor (more blended cement like PPC/PSC) = lower cost and higher margin.

### Branded Products — Working Capital is the Real Moat
For Pipes, Tiles, and Boards, manufacturing is relatively commoditized; the real moat is distribution and channel financing.
- **Debtor Days:** Extract from `get_fundamentals(section='working_capital')`. A structural increase in debtor days means the company is pushing inventory to dealers (channel stuffing) or losing pricing power.
- **Inventory Days:** Critical for pipes. High inventory days entering a period of falling PVC prices guarantees massive P&L inventory losses.
- **Cash Conversion Cycle (CCC):** Top-tier players operate on negative or very low CCC. Deterioration here precedes margin collapse.

### Revenue Quality — Volume vs. Realization
Never accept headline revenue growth at face value. Decompose it:
- **Volume Growth (%):** The true indicator of market share and demand.
- **Realization Growth (%):** Driven by price hikes or product mix (e.g., selling more premium CPVC vs. agri-PVC, or more blended cement vs. OPC).
- If revenue is up 15% but volume is flat (growth entirely price-led), flag it as low-quality growth vulnerable to commodity price reversals.

### Capex and Leverage — The Cement Treadmill
Cement requires constant capex to maintain market share.
- **Greenfield vs. Brownfield:** Brownfield expansion (adding a line to an existing plant) is cheaper (~$50-60/t) and faster than Greenfield (~$80-100/t). Check `get_deck_insights(sub_section='outlook_and_guidance')` for the capex mix.
- **Net Debt / EBITDA:** Extract from `get_fundamentals(section='balance_sheet_detail')`. Cement companies with Net Debt / EBITDA > 3x entering a downcycle are at severe risk of distress or forced asset sales.
- **Operating Cash Flow (OCF) vs. Capex:** Is the capacity expansion funded by internal accruals or debt? Top-tier players fund 15-20 MTPA expansions entirely via OCF.

### Inventory Gains/Losses — Mandatory Check for Pipes
PVC resin prices are highly volatile.
- When PVC prices rise, pipe companies sell low-cost inventory at higher market prices = **Inventory Gain** (margins spike artificially).
- When PVC prices fall, they must cut product prices while holding expensive resin = **Inventory Loss** (margins collapse).
- Always cross-check the QoQ EBITDA margin against the PVC price trend via `get_market_context(section='macro')`. Strip out these transient gains/losses to find the core margin.

### What Structured Tools CAN Tell You
- `get_fundamentals(section='cagr_table')` — 5Y/10Y margin stability (separates compounders from cyclicals).
- `get_fundamentals(section='working_capital')` — Debtor/Inventory days trajectory (crucial for branded products).
- `get_fundamentals(section='cash_flow_quality')` — CFO/EBITDA conversion (should be >80% for top-tier cement and branded players).
