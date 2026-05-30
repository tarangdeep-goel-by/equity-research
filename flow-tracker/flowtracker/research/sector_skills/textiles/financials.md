## Textiles & Apparel — Financials Agent

### Working Capital is Destiny
Textiles is one of the most working-capital-intensive sectors in the market. A company's ability to manage its cash conversion cycle dictates its survival during cotton price crashes.
- **Inventory Days:** Spinners and integrated mills must hold 3-5 months of cotton inventory. Track inventory days via `get_fundamentals(section='working_capital')`. A sudden spike in inventory days during a period of falling cotton prices is a massive red flag — it signals impending mark-to-market (MTM) write-downs.
- **Receivable Days:** For exporters, receivables can stretch to 90-120 days. Cross-check receivables against revenue growth. If receivables are growing much faster than revenue, channel partners are struggling.
- **Export Incentives as Receivables:** GoI export incentives (RoDTEP/RoSCTL) are booked as revenue but often sit as receivables for quarters until the government disburses cash. High "Other Current Assets" or "Receivables from Government" drains operating cash flow.

### The Cotton Inventory MTM Dynamic (Mandatory Check)
You must decompose gross margins for manufacturing players:
- **Rising Cotton Prices:** Companies consume older, cheaper cotton inventory while selling yarn/fabric at new, higher market prices. Gross margins artificially expand.
- **Falling Cotton Prices:** Companies consume older, expensive cotton inventory while selling yarn/fabric at new, lower market prices. Gross margins collapse, often turning negative.
- *Action:* Always correlate the QoQ Gross Margin trajectory from `get_fundamentals(section='quarterly_financials')` with the spot cotton price trend from `get_market_context(section='macro')`. If management claims a margin expansion is due to "operational efficiency" but cotton prices rose 15% that quarter, flag the inventory gain.

### Unit Economics — The Real Margin Drivers
P&L percentages hide operational realities. Extract physical unit economics from `get_company_context(section='concall_insights', sub_section='operational_metrics')` or `get_deck_insights(sub_section='segment_performance')`:
- **Spinners:** **EBITDA per kg (₹/kg)**. This strips out the inflation/deflation of the underlying cotton price. A spinner maintaining ₹20-25/kg EBITDA through a cycle has pricing power; one fluctuating from ₹5 to ₹40 is a pure price-taker.
- **Retail/Brands:** **Same-Store Sales Growth (SSSG %)** and **Revenue per sq. ft.** SSSG must be decomposed into Volume (footfalls/conversion) vs. Value (price hikes). If SSSG is 8% but price hikes were 10%, footfalls actually shrank.

### Debt and Leverage — The Capex Trap
Textile spinning and weaving are highly capital intensive. Companies frequently debt-fund capacity expansions at the exact peak of the cycle (when cash flows look great).
- Compute **Net Debt / EBITDA**. But crucially, compute it on *normalized* EBITDA, not peak EBITDA. A 2.0x Net Debt/EBITDA at cycle peak can instantly become 6.0x at cycle trough when margins compress.
- Track **Capital Work in Progress (CWIP)** from `get_fundamentals(section='balance_sheet_detail')`. High CWIP means a new facility is coming online — check concalls for the expected commercialization date, as this will trigger a jump in depreciation and interest costs, depressing PAT until utilization ramps up.

### Ind AS 116 — Retail Debt Illusion
For retail brands (Trent, ABFRL, Manyavar), Ind AS 116 capitalizes future lease payments as "Lease Liabilities" on the balance sheet and "Right of Use (ROU) Assets".
- This massively inflates reported Total Debt.
- When assessing financial risk, separate **Core Borrowings** (bank debt, NCDs) from **Lease Liabilities**. A retailer with ₹2,000 Cr of lease liabilities and zero bank debt is not "highly leveraged" in the traditional sense — they just have a lot of stores.
- Extract the debt split from `get_company_context(section='filings', sub_section='notes_to_accounts')`.

### Export Incentives — Below-the-Line Padding
Garment and Home Textile exporters receive RoDTEP and RoSCTL incentives (typically 2-5% of FOB value).
- These are often reported under "Other Operating Revenue" or "Other Income".
- Because these incentives have zero associated cost of goods sold, they flow 100% to the EBITDA line. For many mid-tier exporters, GoI incentives account for 40-60% of total PBT.
- *Rule:* Always quantify the quantum of export incentives as a % of EBITDA. It highlights regulatory vulnerability.
