## Logistics — Financials Agent

### Volume vs. Yield (Realization) — The Core Decomposition
Revenue growth in logistics is meaningless until decomposed. 
- **Volume**: Tonnage, TEUs, or Shipments. This indicates market share and network throughput.
- **Yield / Realization**: Revenue per Tonne, per TEU, or per Shipment. This indicates pricing power, product mix (e.g., shifting to higher-yield express), and fuel-cost pass-through.
- **Rule**: Always extract both from `get_company_context(section='concall_insights', sub_section='operational_metrics')` or `get_deck_insights(sub_section='key_metrics')`. If revenue grew 15%, but volume was flat and yield grew 15% due to diesel price hikes, the business is stagnating, not growing.

### Margin Drivers & Fuel Pass-Through (FSC)
Fuel (diesel/ATF) constitutes 30-40% of operating costs for road and air express.
- **Fuel Surcharge (FSC) Mechanism**: Most organized B2B players have an FSC clause that passes diesel price changes to clients with a 30-45 day lag. 
- **The Margin Illusion**: When diesel prices spike, revenue inflates (due to FSC) and absolute EBITDA may remain flat, causing the **EBITDA margin % to optically compress**. Conversely, when diesel falls, margins optically expand. 
- **Action**: Do not call optical FSC-driven margin compression a "profitability crisis." Check absolute EBITDA per tonne/TEU.

### Asset-Light vs. Asset-Heavy P&L Signatures
Do not compare margins across different models:
- **Asset-Light (3PL/Express)**: High "Freight/Network Expenses" (paying third-party truck owners). Gross margins are low (15-25%), EBITDA margins are low (4-8%). But Asset Turnover is high (3-5x), leading to high ROCE (20%+).
- **Asset-Heavy (Rail/Owned Fleet)**: Low freight expenses (they own the assets). Gross margins are high, EBITDA margins are high (15-25%). But Asset Turnover is low (0.5-1x), leading to moderate ROCE (10-15%).
- **Metric to track**: Focus on **ROCE** from `get_fundamentals(section='cagr_table')` to equalize the models, rather than penalizing asset-light players for low EBITDA margins.

### Working Capital & Cash Flow
- **Receivables**: B2B and 3PL logistics have high receivables days (60-90 days) because corporate clients demand credit. B2C e-commerce logistics has very low receivables. Track DSO (Days Sales Outstanding) via `get_fundamentals(section='working_capital')`. A sudden spike in DSO indicates clients are stretching payables — a key stress signal.
- **Cash Flow Conversion**: OCF / EBITDA should be > 70% for mature players. For asset-heavy players, track Free Cash Flow (FCF) after maintenance capex (truck replacement, terminal upgrades).

### Empty Running / Return Load Metrics
For rail and road freight, profitability hinges on the return journey.
- **Empty Running Cost**: The cost of bringing an empty container/truck back. 
- **Imbalance**: If EXIM imports boom but exports collapse, rail operators (Concor) suffer massive empty running costs from the hinterland back to the port. 
- Extract commentary on "imbalance", "return loads", or "empty running" from `get_company_context(section='concall_insights', sub_section='management_commentary')`.

### Ind-AS 116 Lease Liabilities — Debt Check
Logistics companies lease heavily. 
- Check `get_fundamentals(section='balance_sheet_detail')`. 
- Distinguish between **Core Borrowings** (loans for working capital or buying trucks) and **Lease Liabilities** (capitalized rent for warehouses). 
- A high Net Debt / Equity ratio driven purely by Ind-AS 116 lease liabilities is a structural feature of asset-light models, not a solvency risk. State the split explicitly.
