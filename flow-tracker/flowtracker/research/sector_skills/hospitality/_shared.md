## Hospitality Mode (Auto-Detected)

This company is in the hospitality sector, which encompasses **Hotels/Lodging**, **Quick Service Restaurants (QSR)**, and **Travel Services**. 

**The Ind AS 116 Distortion — Why Standard Metrics Fail:**
For Hotels and QSRs, Ind AS 116 (Leases) fundamentally distorts the P&L and Balance Sheet. Rent expense is removed from operating expenses and replaced with depreciation (on Right-of-Use assets) and finance costs (on lease liabilities). 
- **EBITDA is artificially inflated** (Post-Ind AS 116 EBITDA > Pre-Ind AS 116 EBITDA).
- **Net Debt is artificially inflated** (lease liabilities are capitalized as debt).
- **ROCE is depressed** (capital employed swells with ROU assets).
Always specify whether you are quoting Pre-Ind AS 116 or Post-Ind AS 116 EBITDA/Margins. For QSRs, peer comparisons are invalid unless both are on the same Ind AS 116 basis.

**Primary Valuation Metrics:**
- **Hotels:** **EV/EBITDA** (primary) and **EV/Room** (replacement cost cross-check). Asset-light (management contract) mix drives the target multiple.
- **QSR:** **EV/EBITDA** and **P/E**. Multiples are highly sensitive to **SSSG** (Same-Store Sales Growth) — a QSR with negative SSSG will see severe multiple compression regardless of aggressive store additions.
- **Travel/Platform:** **P/E** and **EV/FCF**.

**Metrics that mislead in isolation:**
- **QoQ Growth:** Hospitality is highly seasonal. Q3 (Oct-Dec, festive/wedding/holiday season) is the strongest; Q2 (monsoon) is the weakest. **Always use YoY comparisons** for revenue, RevPAR, and SSSG. QoQ analysis is structurally flawed here.
- **Consolidated Revenue Growth (QSR):** Top-line growth driven purely by new store additions while SSSG is negative masks deteriorating unit economics. 
- **P/E for Asset-Heavy Hotels:** High depreciation and operating leverage make P/E wildly volatile across the cycle.

### Mandatory KPI Backbone
Every hospitality report must explicitly extract and cite the following from `get_company_context(section='sector_kpis')` or `get_deck_insights(sub_section='key_metrics')`:

**For Hotels (INDHOTEL, EIH, LEMONTRE, CHALET):**
1. **RevPAR (Revenue Per Available Room):** The ultimate hotel KPI (= ARR × Occupancy).
2. **ARR (Average Room Rate) & Occupancy %:** Decompose RevPAR growth — is it rate-driven (high pricing power) or occupancy-driven?
3. **Pipeline & Mix:** Total operational keys vs. pipeline keys. Crucially, state the **Owned vs. Managed (Asset-Light)** mix.

**For QSR (JUBLFOOD, DEVYANI, SAPPHIRE, WESTLIFE):**
1. **SSSG (Same-Store Sales Growth):** The single most important QSR metric.
2. **Store Additions & Total Count:** Gross vs. net additions.
3. **ADS (Average Daily Sales) / AUV (Average Unit Volume):** Revenue per store.
4. **ROM (Restaurant Operating Margin):** Store-level profitability before corporate overheads.

**For Travel (IRCTC, EASEMYTRIP, THOMASCOOK):**
1. **GBV (Gross Booking Value) / Transaction Volume.**
2. **Take-Rate / Net Revenue Margin:** The actual cut the platform keeps.

### Annual Report & Investor Deck — High-Signal Sections

**AR high-signal sections:**
- `mdna` — SSSG trends, RevPAR trajectory, tier-2/3 expansion strategy, food inflation commentary.
- `segmental` — Dine-in vs. Delivery mix (QSR); F&B vs. Room revenue (Hotels); Ticketing vs. Catering (IRCTC).
- `notes_to_financials` — Ind AS 116 lease liability schedules, franchise royalty rates (crucial for master franchisees like Devyani/Jubilant).
- `risk_management` — Aggregator dependency (Zomato/Swiggy), franchise agreement renewal risks, input cost volatility (dairy, poultry, wheat).

**Deck high-signal sub_sections:**
- `key_metrics` — SSSG, RevPAR, ARR, Occupancy, Store count trajectory.
- `segment_performance` — Brand-wise breakdown (e.g., KFC vs. Pizza Hut for Devyani/Sapphire) or Geography breakdown.
- `outlook_and_guidance` — Store addition guidance (QSR) or signing/opening guidance (Hotels).

**Cross-year narrative cues:** `capital_allocation_shifts` reveal the pivot from asset-heavy to asset-light (Hotels) or format shifts (e.g., smaller delivery-focused stores in QSR).
