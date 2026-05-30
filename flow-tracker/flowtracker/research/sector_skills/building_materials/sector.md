## Building Materials — Sector Agent

### Macro Context — Housing, Infra Capex, and Input Costs
Building materials demand is driven by two distinct engines: Infrastructure (cement, large-diameter pipes) and Housing/Real Estate (tiles, sanitaryware, plumbing pipes, premium cement). Pull the current regime from `get_market_context(section='macro')` and state these variables:
- **Real Estate Cycle:** Currently in a structural upcycle post-RERA. Housing accounts for ~60-65% of cement demand and >80% of tiles/sanitaryware demand.
- **Infrastructure Capex:** Government spending (Gati Shakti, PM Awas Yojana, roads, metros) is the primary driver for bulk cement and infrastructure pipes.
- **Monsoon Seasonality:** Q2 (July-Sept) is structurally the weakest quarter for construction. Never annualize Q2 run-rates. Q4 (Jan-Mar) is historically the strongest.
- **Energy/Input Costs:** Petcoke/Coal (cement), Natural Gas (tiles), PVC/Crude (pipes). State the YoY and QoQ trend of the relevant input.

### Competitive Hierarchy — Tier the Sub-sectors
Do not treat "Building Materials" as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics'`:
- **Pan-India Cement (Top Tier):** ULTRACEMCO, AMBUJACEM (Adani). These dictate national pricing and have the balance sheet to consolidate the industry.
- **Regional Cement Leaders:** SHREECEM (North/East, cost leader), DALBHARAT (South/East), RAMCOCEM (South premium), JKCEMENT (North/Central + White cement moat).
- **Mid/Small-Cap Cement:** Highly vulnerable to regional price wars and M&A targets for the top tier.
- **Pipes (Oligopoly in CPVC):** ASTRAL (CPVC pioneer, premium), SUPREMEIND (diversified plastics, massive reach), FINPIPE (agri-heavy, PVC-linked).
- **Tiles & Bathware:** KAJARIACER (market leader, premium brand), SOMANYCERA, CERA (sanitaryware leader).
- **Wood & Boards:** GREENPANEL (MDF proxy), CENTURYPLY (Plywood + MDF).

### Structural Shifts — Beyond the Cycle
Identify which structural shift applies to the company being analyzed:
- **Cement Consolidation:** The top 5 players are aggressively acquiring mid-tier assets to defend market share. The race to 150-200 MTPA capacity is driving M&A premiums.
- **Green Energy Transition (Cement):** Increasing the share of WHRS (Waste Heat Recovery System) and Solar/Wind power is the primary lever for EBITDA/tonne expansion. Companies with <15% green power are structurally disadvantaged.
- **Unorganized to Organized Shift (Branded):** GST, RERA, and the Morbi gas-price hike have structurally impaired unorganized tile/pipe players, driving market share to branded listed players.
- **Premiumization (Branded):** Shift from PVC to CPVC (pipes), from small ceramic tiles to Large Format GVT (tiles), and from cheap plywood to MDF (boards).

### Sector KPIs for Comparison — Always Cite Percentile
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector:
- **Cement:** EBITDA/tonne (₹), EV/tonne ($), Capacity Utilization (%), Green Power Share (%), Lead Distance (km), Net Debt/EBITDA.
- **Branded Products:** Volume Growth (%), EBITDA Margin (%), Working Capital Days, ROCE (%).

A number quoted without sector percentile (e.g., "EBITDA/tonne of ₹800") is meaningless. Is that top-quartile (excellent in a trough) or bottom-quartile (terrible in a peak)?

### Regional Dynamics — Mandatory for Cement
Cement is a regional play. You MUST identify the company's primary regional exposure via `get_annual_report(section='mdna')` or `get_deck_insights(sub_section='segment_performance')`:
- **North/Central:** Typically consolidated, better pricing discipline, higher utilization.
- **East:** Structurally oversupplied, lowest pricing, intense market-share battles.
- **South:** Highly fragmented, lower utilization, but historically better pricing discipline (though fragile).
- **West:** Driven by infra/commercial, dominated by top players.

### Open Questions — Sector-Specific
- "What is the current regional cement pricing trend in the company's core markets, and is it absorbing the recent capacity additions?"
- "For pipes: Is the volume growth driven by the high-margin CPVC plumbing segment or the low-margin agri-PVC segment?"
- "For tiles: How is the pricing spread between Morbi unorganized players and this branded player trending given current natural gas prices?"
