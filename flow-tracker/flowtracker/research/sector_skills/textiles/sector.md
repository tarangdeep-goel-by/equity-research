## Textiles & Apparel — Sector Agent

### Macro Context — Cotton, US Retail, and Tariffs
Textiles spans agriculture, manufacturing, and consumer discretionary. Pull the current regime from `get_market_context(section='macro')` and state these variables explicitly:
- **Domestic vs International Cotton Parity:** The spread between Indian Shankar-6 cotton and ICE (US) cotton futures. When Indian cotton is at a premium, domestic spinners lose global market share to Vietnam and Bangladesh.
- **US/EU Retail Inventory Cycle:** For exporters (Home Textiles, Garments), US retail destocking/restocking is the primary demand driver. Track commentary on US big-box retailer (Target, Walmart, Macy's) inventory levels.
- **Domestic Consumption (Urban vs Rural):** For domestic brands/retail, urban premiumization is driving luxury/ethnic (Manyavar) and fast fashion (Zudio), while rural stress impacts mass-market innerwear and value apparel.
- **Trade Pacts & Tariffs:** Bangladesh enjoys LDC (Least Developed Country) duty-free access to the EU/UK. India faces ~9-12% duties. Any progress on the India-UK or India-EU FTA is a massive structural catalyst for Indian garment exporters.
- **Red Sea / Freight Rates:** Textiles are bulky, low-value-to-weight cargo. Spikes in container freight rates (e.g., Red Sea crisis) compress margins for FOB exporters and delay revenue recognition.

### Competitive Hierarchy — Tier the Sub-sectors
Do not treat "Textiles" as a monolith. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics'`:
- **Branded Retail / Fast Fashion (Top Tier):** TRENT, PAGEIND, VEDANTFASH, ABFRL. High ROCE, brand moats, valued on consumer-discretionary multiples.
- **Home Textiles (Oligopoly):** WELSPUNLIV, TRIDENT, INDOCOUNT. India dominates global terry towel and bedsheet exports. Highly sensitive to US housing/retail cycles and cotton prices.
- **Garment Exporters (China+1 plays):** GOKEX, KPRMILL, SPAL. Labor-intensive, asset-light relative to spinning. Benefiting structurally from global brands diversifying sourcing away from China.
- **Integrated Textile Mills:** ARVIND, RAYMOND. Legacy players with complex structures (real estate, brands, and commodity textiles mixed). Require SOTP.
- **Commodity Spinners/Weavers:** VTL (Vardhman), NITINSPIN. Capital-intensive, cyclical, price-takers. Lowest multiples in the sector.

### Institutional-Flow Patterns — Textiles-Specific
- **FIIs crowd the Brands:** Foreign flows concentrate heavily in TRENT, PAGEIND, and VEDANTFASH due to high ROCE and clean consumer narratives. They largely ignore commodity spinners.
- **DIIs play the Cycle and China+1:** Domestic funds actively rotate into spinners at cycle troughs (when P/B is low) and hold structural overweight positions in garment exporters (GOKEX, KPRMILL) playing the China+1 theme.
- **Promoter Pledging:** Historically a red flag in mid-cap textiles. Check `get_company_context(section='info')` for pledge percentages.

### Structural Shifts — Beyond the Cotton Cycle
Cyclical reads miss the slow-moving structural shifts reshaping textile economics:
- **China+1 and Vendor Consolidation:** Global brands are reducing their reliance on China and consolidating their vendor base to larger, compliant players. Indian garmenters with ESG-compliant facilities are gaining structural market share.
- **The Fast Fashion Disruption:** The "Zudio effect" (Trent) is structurally destroying the pricing power of legacy mid-tier apparel brands. Value-fashion is the fastest-growing segment, relying on hyper-efficient supply chains rather than seasonal collections.
- **PLI Scheme & RoDTEP:** The GoI's Production Linked Incentive (PLI) for Man-Made Fibres (MMF) and technical textiles is forcing a shift away from India's traditional cotton-heavy mix. RoDTEP (export incentive) rates directly pad exporter margins; track any government notifications altering these rates.
- **Formalization of Ethnic/Occasion Wear:** Shift from unorganized local tailors/boutiques to branded players (Vedant Fashions/Manyavar, ABFRL's ethnic portfolio) driven by rising wedding-ticket sizes.

### Sector KPIs for Comparison — Always Cite Percentile
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank:
- **Retail/Brands:** SSSG (%), Revenue per sq. ft., Store count YoY growth, Gross Margin (%).
- **Exporters:** Export revenue share (%), RoCE (%), Working Capital days.
- **Spinners:** EBITDA/kg (₹), Capacity utilization (%), Net Debt/EBITDA.

### Open Questions — Textiles Sector-Specific
- "Where is domestic Shankar-6 cotton priced relative to ICE cotton parity, and what does this imply for the export competitiveness of the spinning/garmenting divisions?"
- "For retail brands: Is the current SSSG driven by volume (footfalls/conversion) or purely by price hikes/premiumization?"
- "For exporters: What is the management's commentary on US/EU channel inventory destocking — are we at the end of the destocking cycle?"
- "What percentage of the company's revenue is derived from GoI export incentives (RoDTEP/RoSCTL), and are there any pending receivables from the government?"
