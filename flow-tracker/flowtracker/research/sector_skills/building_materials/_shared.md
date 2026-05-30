## Building Materials Mode (Auto-Detected)

This company is in the Building Materials sector. You MUST immediately bifurcate the analysis into one of two distinct sub-archetypes, as their economics and valuation frameworks are entirely different:
1. **Heavy Building Materials (Cement)** — Capital-intensive, regional, freight-heavy, cyclical commodity.
2. **Branded Building Products (Pipes, Tiles, Sanitaryware, MDF/Plywood)** — Asset-lighter, brand/distribution-led, working-capital-sensitive compounders.

**Primary Valuation Metrics by Sub-Archetype:**
- **Cement:** **EV/EBITDA** (primary) and **EV/tonne of capacity** (cross-check). PE is misleading because earnings swing violently with global petcoke/coal cycles and regional price wars.
- **Branded Products:** **P/E** (primary) and **EV/EBITDA**. These are valued as consumer-discretionary compounders where ROCE and volume growth drive the multiple.

**Metrics that mislead in this sector:**
- **PE for Cement:** Earnings are cyclically inflated when petcoke/coal prices crash, and depressed when fuel spikes. Using PE in isolation traps you into buying at the cycle peak and selling at the trough.
- **Consolidated Margin for Pipes without adjusting for Inventory Gains/Losses:** PVC resin prices are highly volatile. A sudden drop in PVC prices causes massive inventory losses, temporarily crushing margins. Do not extrapolate a single-quarter margin without checking the PVC price trend.

### Mandatory KPI Backbone
Every building materials report must extract and cite the following metrics (source via `get_company_context(section='sector_kpis')` or `get_deck_insights(sub_section='key_metrics')`):

**For Cement:**
- **Capacity & Utilization:** Installed capacity (MTPA) and current utilization %.
- **Volume:** Sales volume in Million Tonnes (MT).
- **Realization/tonne (₹/t):** Net sales divided by volume. Indicates regional pricing power.
- **EBITDA/tonne (₹/t):** The ultimate measure of cement profitability. ₹1,000-1,200/t is typically mid-cycle for efficient players.
- **Power & Fuel Cost/tonne (₹/t):** Tracks energy efficiency and fuel mix (petcoke vs. imported coal vs. green power).
- **Freight Cost/tonne (₹/t) & Lead Distance:** Cement is cheap but heavy; you cannot transport it far. Lower lead distance = higher margin.

**For Branded Products (Pipes, Tiles, Boards):**
- **Volume Growth (%):** Strips out pricing/inflation to show true market-share gains.
- **EBITDA Margin (%):** Track QoQ to spot input-cost pressures (PVC for pipes, natural gas for tiles, timber for MDF).
- **Working Capital Days:** The true moat of a branded player is channel financing. Rising debtor days signals channel stuffing or weak demand.
- **Dealer/Distributor Count:** The proxy for distribution reach and barrier to entry.

### Macro & Input Cost Backbone
Building materials margins are inverse derivatives of energy/commodity inputs. You MUST cite the relevant input trend via `get_market_context(section='macro')`:
- **Cement:** US Gulf Petcoke, South African Coal, and domestic diesel (freight).
- **Pipes:** PVC resin prices (linked to crude) vs. CPVC prices.
- **Tiles/Sanitaryware:** Spot vs. Contract Natural Gas prices (Morbi cluster pricing).
- **MDF/Plywood:** Domestic timber prices.

### Annual Report & Investor Deck — High-Signal Sections

**AR high-signal sections:**
- `mdna` — Regional demand-supply dynamics (for cement), unorganized-to-organized market share shifts (for tiles/pipes), capacity addition timelines.
- `segmental` — White cement vs. Grey cement; PVC vs. CPVC; MDF vs. Plywood. Margins differ drastically across these.
- `notes_to_financials` — Breakdown of power & fuel costs, freight & forwarding expenses, and dealer incentives/discounts.
- `auditor_report` — KAMs on inventory valuation (critical for pipes during PVC price crashes) and dealer-discount provisioning.

**Deck high-signal sub_sections:**
- `key_metrics` — Per-tonne metrics (cement) or volume/value growth splits (branded).
- `outlook_and_guidance` — Greenfield vs. brownfield capex phasing, targeted capacity by FY-end, and targeted green-energy share (WHRS/Solar).
- `segment_performance` — Regional volume splits (North/South/East/West/Central) — crucial because cement pricing is highly localized.
