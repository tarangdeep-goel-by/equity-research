## Platform — Sector Agent

### Macro Context — Discretionary Spend, UPI, Smartphone Penetration, VC Funding
Platform economics are macro-sensitive in ways that are distinct from traditional discretionary consumption; no stock-level narrative is complete without anchoring to the macro regime. Pull the current regime from `get_market_context(section='macro')` and state these five variables explicitly:
- **Urban discretionary income trajectory** — platform GMV is 80%+ driven by urban tier-1/tier-2 households. Real-wage growth and urban CPI for discretionary items (eating-out, mobility, apparel) set the demand ceiling for 12-18 months forward.
- **UPI / digital-payments volume growth** — the rail that makes everything else work. UPI TPV growth >30% YoY is the tailwind regime; <20% would be a structural concern for new-user acquisition economics.
- **Smartphone + broadband penetration** — still expanding at the tier-3/tier-4 edge; 700-800 Mn smartphone users today, headroom to ~1.1 Bn by 2028. The incremental user has lower ARPU and higher price-sensitivity than the metro cohort.
- **VC / PE funding cycle** — when growth-stage tech funding is open (2020-22 regime), new entrants pour capital into CAC and compress unit economics for incumbents. When it is closed (2023 tech-winter), discipline returns across the cohort.
- **Tech-talent availability and cost** — engineering-salary inflation and attrition rates set fixed-cost trajectory; 2023-24 saw meaningful compression after the 2021-22 bubble.

### Sector Cycle Position — Platforms Are Cohort-Specific
The Indian platform cohort is in a 3-5 year discipline-enforcement phase post the 2022 tech-winter, but different sub-sectors are at different phases within that super-cycle:
- **Food-delivery** — mature duopoly, category-leader contribution-margin-per-order inflecting positive, operating-EBITDA transition under way. Late-stage unit-economics regime.
- **Quick-commerce** — scale phase. Top-3 players compete on dark-store density and AOV expansion. Contribution margin per order turned positive for leaders in 2024; EBITDA positive ambition is 2026-27.
- **E-commerce marketplaces** — horizontal top-2 is mature, vertical niches (beauty, fashion, pharmacy, grocery-horizontal) are in growth-to-profitability transition.
- **Mobility / ride-hailing** — mature top-2 (domestic) competing with global carved-out Indian arms. Unit economics workable; growth modest; monetisation via ads and fintech cross-sell.
- **Payments** — mature top-3. Post-payments-bank carve-out reset. Revenue diversification into lending distribution, merchant services, and wealth-tech.
- **Insurtech (distribution)** — post-IRDAI EoM reset (2023 amendment), commission pool compression ongoing; the business model that worked pre-2023 was re-cut in one fiscal.
- **Edtech** — post-COVID consolidation phase, many exits. The category is smaller and more disciplined than 2021 peak.

State the specific platform's phase (growth-at-any-cost / unit-economics-pivot / path-to-profitability / mature-profitable) before extrapolating trends.

### Competitive Hierarchy — Tier the Sub-Sector
Sector reports collapse when they treat "platforms" as monolithic. Tier the sub-sector via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:
- **Food-delivery duopoly** — top-2 by order-share; #3 (if present) is capital-dependent.
- **Quick-commerce top-3** — each pursuing a different store-count and AOV strategy; category is still consolidating.
- **E-commerce horizontal top-2** — with foreign-FDI-policy-constrained operating models; domestic-FDI-compliant entrants at the third tier.
- **E-commerce vertical niches** — beauty leader, fashion leaders, pharmacy leaders — each sub-niche has its own top-2.
- **Mobility top-2** — domestic vs global carve-out; driver-partner network is the moat.
- **Payments leaders** — top-3 with distinct merchant-vs-consumer mix; UPI-share and lending-distribution mix differentiate.
- **Insurtech** — 2 listed leaders with overlap to the insurance sub-sector; product-mix and distribution-channel mix differentiate.
- **Edtech** — post-consolidation 2-3 names with different product models (test-prep, K-12, up-skilling).

### Institutional-Flow Patterns — Platform-Specific
Platforms carry 2-4% weight in Nifty as the post-IPO cohort has listed; the flow mechanics are distinct from old-economy sectors:
- **FII-heavy from global tech / internet allocation** — global EM tech funds, China-plus-one Asia-tech allocators, and global-internet sector-specialists drive the bulk of active FII flow into Indian platforms. Foreign funds use global-peer multiples (US / China tech) to anchor their frameworks.
- **DII growing exposure as profitability materialises** — pre-2023, DII under-weighted the platform cohort because of the loss-making profile. Post-2024 path-to-EBITDA clarity, DII allocation is rising, especially MF equity-scheme fresh inflows.
- **Passive ETF flows** — as platforms enter Nifty 50 / Nifty Next 50, mechanical passive inflows add a stability bid. Index-entry events compress historical volatility.
- **Pre-IPO VC unlock cycles** — 30-day, 6-month, 12-month lock-up expiries are outsized technical events in this sector because the pre-IPO roster is concentrated. A single fund's exit can absorb 3-6 months of steady-state volume.
- **Private-peer funding marks as a forward valuation catalyst** — when a private peer raises at an up-round (or down-round), the public listed cohort re-rates in sympathy within weeks — positive marks set a new implicit floor on EV/GMV or EV/Revenue comps and negative marks compress the band. Track private-peer primary / secondary round valuations as a forward-looking re-rating catalyst for listed names; the mark-transmission is fastest in sub-sectors where the private-peer is the closest operating comparable (quick-commerce, e-commerce vertical, insurtech).

Cross-check the sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping platform economics over 3-5 years:
- **Quick-commerce displacing traditional e-commerce** in metros for FMCG — sub-30-min delivery is resetting SKU-level share economics; traditional e-commerce is retaining share in bulky / large-basket categories and ceding share in impulse / replenishment.
- **ONDC protocol effect** — the Open Network for Digital Commerce is a policy-led shift toward protocol-based discovery and fulfilment; the equilibrium impact on marketplace take-rates and merchant-acquisition costs is still uncertain but directionally dilutive for incumbent take-rate.
- **Advertising-tech monetisation** — ad-revenue as % of platform revenue is rising 100-300 bps per year for category leaders, providing a high-margin revenue diversifier that supports the EBITDA trajectory.
- **Global expansion by Indian platforms** — marginal contribution today; a handful of names pursue SEA and MENA; not yet a material valuation driver.
- **Embedded lending / fintech cross-sell** — platforms monetising user-base via co-branded credit, BNPL, or merchant lending; the take-rate on the fintech line exceeds core-commerce take-rate materially.
- **Data-protection regime (DPDP Act)** — raises compliance cost uniformly; harder on smaller players without compliance engineering.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "digital transformation" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. Platform-relevant KPIs:
- **All platforms** — GMV growth%, take-rate%, orders growth%, MTU / MAU growth%, AOV trend, contribution margin per order, operating EBITDA margin%, cash burn / runway (months), cohort retention M1 / M6 / M12.
- **Marketplace liquidity KPIs (leading indicators)** — zero-result-search rate, fulfilment rate (orders fulfilled ÷ orders placed), ETA accuracy, NPS — these front-run GMV trajectory by 1-2 quarters; peer-relative percentile on liquidity KPIs is more predictive of forward share-gain than trailing GMV growth itself.
- **Food-delivery / quick-commerce** — orders per MAU per month, contribution margin per order, dark-store count (quick-commerce), orders per store per day (quick-commerce).
- **E-commerce** — active-buyer growth, repeat-rate, private-label mix%, ad-revenue % of revenue.
- **Payments** — TPV growth, MDR-revenue share, lending-distribution revenue share, merchant base growth.
- **Mobility** — trips per driver-hour, active-driver-partner growth, surge-pricing realisation.
- **Insurtech** — premium GWP growth, 13-month persistency%, commission-pool-to-revenue%.
- **Edtech** — paid-subscriber growth, completion rate, ARPU trend.

A number quoted without percentile (e.g., "GMV growth 30%") omits whether that is top-quartile, median, or decelerating-faster-than-peer; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 4 comparable names, common for nascent sub-sectors like quick-commerce), fall back to `section='sector_flows')` for the index-weight context and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked.

### Open Questions — Platform Sector-Specific
- "Where is the specific sub-sector in its capital cycle — growth-at-any-cost / unit-economics-pivot / path-to-profitability / mature-profitable — and is the cycle phase aligned across the top-3 or divergent?"
- "What share of sub-sector GMV is captured by the top-2, and is share concentration rising or being eroded by a new entrant?"
- "Are any MeitY / RBI / CCI / IRDAI draft circulars in public consultation that would reprice take-rate, MDR, commission, or fulfilment economics for this sub-type?"
- "What is the FII-active vs FII-passive flow share into the cohort over the last 4 quarters, and has DII allocation shifted structurally with the path-to-profitability narrative?"
- "For structural shifts (ONDC adoption, ad-tech monetisation, embedded lending): what share of incremental revenue growth is coming from the new channel vs legacy commerce?"
