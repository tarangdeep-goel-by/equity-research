## Textiles & Apparel Mode (Auto-Detected)

This company is in the textiles, apparel manufacturing, or branded retail sector. 

**The Sector Bifurcation Trap — Why Standard Analysis Fails:**
"Textiles" is not one sector; it is two fundamentally different business models masquerading under one classification. Treating them as the same sector is the single most common analytical failure.
1. **Commodity Manufacturing (Spinners, Weavers, Processors):** Highly cyclical, capital-intensive, low-margin B2B businesses driven by global cotton prices and capacity utilization. (e.g., Vardhman Textiles, Nitin Spinners).
2. **Branded Retail / Fast Fashion:** High-ROCE, asset-light, consumer-discretionary businesses driven by brand moat, store expansion, and Same-Store Sales Growth (SSSG). (e.g., Trent, Page Industries, Vedant Fashions).
*Garment Exporters (Gokaldas) and Home Textiles (Welspun, Trident) sit in the middle: B2B but with higher value-add and sticky customer relationships.*

**Primary Valuation Metrics by Sub-type:**
- **Branded Retail / Fast Fashion:** **P/E** and **EV/EBITDA** on forward earnings. High multiples (40-80x) are justified *only* if ROCE > 25% and store-expansion runway is intact.
- **Commodity Spinners/Weavers:** **EV/EBITDA** (compare to 5Y average) and **P/B** at trough. 
- **Garment Exporters / Home Textiles:** **EV/EBITDA** (typically 8-15x depending on US/EU demand cycle and China+1 market share gains).

**Metrics that mislead for Textiles:**
- **P/E for Commodity Spinners:** Inverted signal. Lowest PE marks the cycle peak (cotton inventory gains artificially inflate PAT); highest PE marks the trough.
- **Branded Multiples for B2B Exporters:** A garment manufacturer is a vendor, not a brand. Applying a consumer-discretionary P/E to a B2B garment exporter because they "make clothes" is a fatal valuation error.

### Mandatory — The Cotton Price & Inventory MTM Backbone
For any manufacturing-heavy textile company, earnings are a derivative of the underlying raw material. Every report from the **sector** and **financials** agents MUST cite:
- **Domestic Cotton Price Trend (Shankar-6 benchmark):** Pull from `get_market_context(section='macro')`. Compare domestic prices to international (ICE cotton) parity. If domestic cotton is priced higher than international, Indian spinners lose export competitiveness instantly.
- **The Inventory MTM Cycle:** Spinners buy cotton during the season (Nov-March) and hold 3-5 months of inventory. If cotton prices *rise*, they book massive inventory gains (inflated margins). If cotton prices *crash*, they suffer brutal mark-to-market (MTM) inventory losses. You must cross-check the cotton price trajectory against the company's inventory days to forecast the upcoming quarter's margin shock or windfall.

### Mandatory KPI Backbone (Sector Compliance Gate)
The following KPIs must be extracted via `get_company_context(section='sector_kpis')` or `get_deck_insights(sub_section='key_metrics')`:
- **For Spinners/Weavers:** Cotton-Yarn Spread (₹/kg), EBITDA/kg, Capacity Utilization (%), Spindle count.
- **For Exporters/Home Textiles:** Export vs. Domestic revenue mix (%), US vs. EU mix, Order book visibility.
- **For Branded Retail:** Store count (additions/closures), Same-Store Sales Growth (SSSG %), Revenue per sq. ft., Branded vs. Private Label mix.

### Annual Report & Investor Deck — Textiles Specifics

**AR high-signal sections:**
- `notes_to_financials` — Inventory valuation policy (FIFO vs Weighted Average — critical for MTM impacts), lease liabilities (Ind AS 116 capitalization for retail stores), contingent liabilities (export obligation defaults).
- `mdna` — Cotton price outlook, channel inventory levels in US/EU (for exporters), rural vs urban demand commentary (for domestic brands).
- `segmental` — B2B (Yarn/Fabric) vs B2C (Garments/Brands) revenue and EBIT margins. This split dictates the valuation multiple.

**Deck high-signal sub_sections:**
- `segment_performance` — SSSG, store economics (capex per store, payback period), EBITDA/kg trends.
- `outlook_and_guidance` — Store addition targets, capex guidance (spindle additions vs garmenting machines), export demand commentary.

**Cross-year narrative cues:** `capital_allocation_shifts` reveal movement up the value chain (e.g., a spinner stopping yarn capacity expansion to invest in garmenting/processing to capture higher margins).
