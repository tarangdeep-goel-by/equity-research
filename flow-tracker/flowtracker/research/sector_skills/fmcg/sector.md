## FMCG — Sector Agent

### Macro Context — Rural Wages, Monsoon, Inflation, Commodity Cycle
FMCG is macro-sensitive through consumption and input-cost channels simultaneously. No stock-level narrative is complete without anchoring to the macro regime. Pull the current regime from `get_market_context(section='macro')` and state these six variables explicitly:
- **Rural wage cycle** — MNREGA wage rates, agri-commodity realization to farmers, crop-cycle output (rabi + kharif). Rural wage growth in mid-single-digits sustains rural FMCG volume at 4-6%; below 3% wage growth typically correlates with <2% rural FMCG volume.
- **Monsoon progression** — IMD cumulative rainfall vs long-period average (LPA). A +/-10% deviation from LPA across the June-September window shifts rural demand trajectory for the following 2-3 quarters.
- **Inflation (CPI-food, CPI-core)** — high CPI-food compresses household discretionary wallet, shifting mix down-trade (economy SKUs grow, premium slows); high CPI-core with weak wage growth compresses urban discretionary.
- **Commodity input cycle** — palm oil (HPC), wheat (biscuits / packaged foods), milk (dairy), crude-derivatives (HPC packaging, detergents), sugar (beverages, confectionery), tobacco-leaf (sin-goods). Call out the specific commodity regime (trough, rising, peak, normalizing) for the most-exposed input.
- **Urban disposable income** — tracked via IT-services wage growth, white-collar hiring data, urban consumption index. Premium FMCG (skin, hair, premium personal care, packaged coffee) correlates with urban disposable-income momentum.
- **Tax regime on sin-goods** — GST-Council cess rates on tobacco / alcobev, state-excise duty trajectories; each state budget can reprice segment economics materially.

### Sector Cycle Position — Three Overlapping Cycles
FMCG lives through three overlapping cycles — rural, urban, and commodity input. Diagnose each before declaring sector direction:
- **Rural cycle (2-3Y mini-cycle)** — drivers are monsoon, agri-income, MNREGA wages, rural-infra spend. Current phase (FY24-25): recovering from 4-quarter slowdown that started mid-FY23; volume growth returning to mid-single-digits.
- **Urban cycle (structural premiumization + cyclical discretionary)** — drivers are urban wage growth, financial-asset wealth effect, premium-product adoption. Current phase: premiumization intact, mass-segment slower than premium, e-comm + QC reshaping urban channel economics.
- **Commodity input cycle** — palm, wheat, milk, crude-derivatives. Current phase: stable / normalizing post-2022-23 spikes; most leaders have passed through prior inflation and margins are near 3Y-average.

State which phase the sector is in for each of the three cycles; contradictory phases (e.g., recovering rural + premiumizing urban + stable commodity) are the constructive setup; aligned-negative phases (rural weak + urban slowing + commodity rising) are the stress setup.

### Competitive Hierarchy — Tier the Sector
Sector reports collapse when they treat FMCG as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:
- **Top-3 HPC leaders** — scale in ad-spend, distribution, procurement; near-irrecoverable lead in core soaps / detergents / skin / hair.
- **Top-3 food & beverage leaders** — biscuits, dairy, beverages, chocolates — tier-1 names dominate category share with cold-chain + plant footprint.
- **Top-2 tobacco / alcobev leaders** — regulatory-entrenched scale; FDI prohibition (tobacco) + state-excise architecture protect incumbent position.
- **Packaged staples (edible oil, flour, salt) leaders** — thin-margin commodity-spread businesses with brand-premium overlay; top players capture scale procurement.
- **Mid-cap HPC / food specialists** — category-focused (hair oil, confectionery, premium personal care) with 10-25% market share in their specific pocket; valuation sensitivity to category-share loss is high.
- **D2C disruptors** — fast-growing in skin, hair, health, coffee, and snacking; collectively 3-8% of urban category revenue and rising.

### Institutional-Flow Patterns — FMCG-Specific
FMCG accounts for 8-10% of Nifty weight (HPC leaders + tobacco + food specialists combined), driving specific flow mechanics:
- **DII structurally defensively overweight** — MF + insurance pools tilt overweight FMCG through cycles for the earnings-visibility and low-beta profile; DII share in large HPC names commonly runs 12-18%.
- **FII active in premium / growth names** — foreign active funds drive the premium names' multiples; passive FII shows up around Nifty / MSCI rebalance windows.
- **Concentrated MF ownership in MNC subs** — MNC subsidiaries with promoter >60% have densely concentrated MF free-float (top 3-5 fund houses together hold 35-45% of the MF share); a single fund-house reallocation produces outsized absolute-₹Cr moves that aggregate `mf_conviction` summaries hide (the ownership agent carries the detailed rule; the sector agent should corroborate sector-level flow via the aggregated flow lens).
- **Tobacco FII rotation** — legacy foreign holdings in tobacco (via historical intermediary vehicles) overhang block-deal risk; tax-regime shifts (GST cess recalibrations) drive episodic FII rotation between 4-5% yield sin-goods and 2-3% yield MNC personal-care subs.

Cross-check sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation. A single stock's FII % change is not a sector signal unless corroborated at the sub-segment level.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping FMCG economics over 3-5 years:
- **D2C penetration** — 5-8% of urban personal-care revenue, projected to reach 12-18% by FY28. Legacy HPC incumbents respond via acquisitions (mid-teens EV/Sales multiples for acquired D2C brands) and organic digital-first launches. Category losses concentrated in skin, hair, health, coffee, snacking.
- **Quick-commerce (10-minute commerce)** — reshaping distribution economics for urban India. Platform take-rates (15-25%) compress gross margin; premium-SKU skew (higher ASP) partly offsets; dark-store discounting pressure is category-specific. QC share in urban personal-care + packaged-food leaders now 6-12% and rising 200-300 bps/year.
- **Modern-trade share rise** — 20-25% of urban distribution and rising; MT receivables (45-60 days) compress the negative-working-capital advantage that defined GT economics. Leaders with <60% GT-share are structurally different businesses from leaders with >80% GT-share.
- **Premium-mass-economy tier shifts with household income** — each ₹1 lakh p.a. increment in household income shifts 8-12% of category spend up-tier; the premiumization tail is a 15-20Y structural tailwind for top-tier FMCG but requires NPD cadence to capture.
- **Private-label penetration in MT** — tier-1 MT chains reach 15-20% private-label share in select categories (detergents, packaged staples); creates gross-margin pressure on mid-tier brands and selective on leaders.
- **Regulatory packaging mandates (FSSAI labelling, EPR plastic norms)** — one-time capex 1-3% of sales + ongoing 50-150 bps gross-margin impact; implementation windows differ by sub-category.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "digital transformation" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. The sector-agent-relevant KPIs by sub-type:
- **HPC leaders** — volume growth %, realization growth %, premium-share %, rural-share %, EBITDA margin %, gross margin %, ad-spend-to-revenue %, ROCE %, distribution outlets (lakhs), direct reach vs peer.
- **Food & beverages** — volume growth %, realization growth %, category-mix %, EBITDA margin %, gross margin %, cold-chain capex %, ROCE %.
- **Packaged staples** — volume (MT) growth %, commodity spread (gross margin after input cost) %, capacity utilisation %, EBITDA margin %.
- **Tobacco / alcobev** — stick / case volume growth %, net realization growth %, EBITDA margin (gross + net of excise), dividend yield %, ROCE %.
- **OTC / wellness** — volume growth %, category-mix premium %, gross margin %, EBITDA margin %, prescription-driven vs pull-driven split %.
- **D2C** — customer growth %, repeat rate %, AOV, contribution margin %, CAC payback (months), GMV growth %, EV/Sales.

A number quoted without sector percentile (e.g., "EBITDA margin 21%") omits whether that is top-quartile, median, or bottom-quartile; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable names in the sub-type) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the index-weight context and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked.

### Open Questions — FMCG Sector-Specific
- "Where is the sector in the rural cycle, the urban cycle, and the commodity-input cycle — and are the three phases aligned-constructive or contradictory?"
- "What is the current D2C + QC share of urban revenue for the sub-sector, and is the incremental share GT-cannibalising or incremental demand?"
- "Are any FSSAI, GST, or state-excise draft regulations in public consultation that would reprice the sub-sector within 12-18 months?"
- "What is the passive-ETF-driven FII flow share vs active FII flow share in FMCG over the last 4 quarters, and is there a sub-segment rotation pattern (HPC vs tobacco vs food)?"
- "For the premium-mass-economy tier shift: what share of incremental growth is coming from premium SKUs vs economy SKUs across peer leaders?"
