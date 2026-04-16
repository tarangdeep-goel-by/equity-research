## Real Estate — Sector Agent

### Macro Context — Rates, Affordability, Income Growth, FDI
Real estate is among the most macro-sensitive sectors; no stock-level narrative is complete without anchoring to the macro regime. Pull the current regime from `get_market_context(section='macro')` and state these five variables explicitly:
- **Repo rate and home-loan rate trajectory** — the home-loan rate (typically repo + 150-200 bps) is the first-derivative driver of affordability. A 100 bps home-loan rate move shifts the qualifying-income threshold for a ₹1 Cr home-loan by 12-15% — that is the buyer-pool expansion or compression that moves residential presales.
- **Household income growth** — urban formal-sector wage growth (CII, IT-sector hiring, BFSI services compensation) feeds directly into mid and premium segment demand. Current cycle: premium cohort (top-20% urban income) has expanded 2-3× over the 2020-25 period, which is the structural driver of the premium upcycle.
- **Urban employment and net migration** — IT-hubs (Bengaluru, Hyderabad, Pune), financial-hubs (Mumbai, GIFT), and capital-city government-services (Delhi-NCR) drive inter-city differentials. Bengaluru's 2023 tech-hiring slowdown hit presales in that micro-market 15-20% while Mumbai was flat.
- **GDP growth — commercial / office demand anchor** — commercial office absorption correlates 0.6-0.8 with services-GDP growth with a 2-3 quarter lag; warehousing absorption correlates with e-commerce GMV growth and manufacturing PMI.
- **FDI inflows and REIT investor base** — FDI in construction-development under the 100% automatic route (FEMA NDI Rules) is cyclical with global-developer-sentiment; REIT investor base is increasingly domestic (insurance, pension, retail via listed units) post-2022.

### Sector Cycle Position — Three Overlapping Cycles
Real estate lives through three overlapping cycles — residential demand, commercial / office, and specialty (warehousing, data-centre). Diagnose each before declaring sector direction:
- **Residential cycle — 4-6Y** — currently in year 4 of the post-2020 upcycle (RERA-cohort rationalisation + premium-affordability expansion). Premium / luxury cohort is mid-cycle; affordable is lagging. A normal cycle ends with a demand-shock (tax, regulation, macro) or a supply-shock (over-launching); current metrics do not suggest imminent rollover but warrant quarterly vigilance.
- **Commercial / office cycle — 6-10Y** — in year 3 of post-2022 recovery after WFH-driven 2020-22 compression. Net absorption has normalised; cap rates have compressed 50-75 bps from 2022 peak. Cycle duration is longer than residential because lease terms are longer and vacancy clears slowly.
- **Specialty cycles** — **warehousing** in sustained up-cycle since 2020 (e-commerce + manufacturing PLI tailwinds, 8-12% annual rent growth in prime micro-markets); **data-centre** in an early expansion cycle tied to AI/cloud build-out.

State which phase the sub-sector is in; contradictory phases (e.g., premium residential upcycle + commercial mid-recovery + warehousing structural up-cycle, all concurrent) are the current regime and make a generic "real-estate sector" call meaningless.

### Competitive Hierarchy — Tier the Sub-sectors
Sector reports collapse when they treat "real estate" as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:
- **Top-5 residential developers by presales value** — typically DLF, LODHA (MACROTECH), GODREJPROP, PRESTIGE, OBEROIRLTY with a rotating fifth seat (SOBHA, BRIGADE). This cohort captures ~35-45% of listed-developer presales and is the primary vehicle for institutional flow into the sector.
- **Top-3 REITs by AUM** — EMBASSY, MINDSPACE, BIRET (Brookfield India REIT) for office; NEXUS for retail malls; the SM-REIT pipeline adds new listings from 2024 onwards.
- **Integrated developer pure-plays** — PRESTIGE, BRIGADE, DLF combine residential + leasing + hospitality on one balance sheet; analytically distinct from pure-residential or pure-REIT peers.
- **City-specialist developers** — Bengaluru-heavy (SOBHA, BRIGADE, PRESTIGE), NCR-heavy (DLF, ANANTRAJ, SIGNATURE), Mumbai-heavy (OBEROIRLTY, LODHA, SUNTECK), Pune-heavy (KOLTEPATIL, PURVANKARA Pune exposure).
- **Specialty — warehousing specialist** post-2020 listed cohort; **data-centre** emerging listings.
- **ARVIND-SMART** sits in an integrated-township category distinct from pure-residential.

### Institutional-Flow Patterns — Real-Estate-Specific
Real estate is ~2-3% of Nifty weight; flows have sector-specific mechanics that the sector and ownership agents should both reflect:
- **FII-active in premium developers and REITs** — foreign long-only funds concentrate in the top-5 by presales and the listed REITs; passive-FII flows arrive on index-rebalance windows.
- **DII positioning is cycle-dependent** — LIC and large domestic MFs are structurally underweight real estate relative to Nifty weight due to legacy governance concerns; DII accumulation above 10% of holding often marks mid-to-late cycle re-rating and has historically (2010, 2017, 2021) preceded cycle-peak signals within 4-6 quarters (see `ownership.md` DII-breakthrough framing).
- **REIT distribution-yield base** — attracts income-seeking retail and insurance-pool capital; distribution-yield compression vs G-sec is the key mood indicator.
- **PE / sovereign-wealth-fund secondary participation** — Blackstone, Brookfield, GIC, CPPIB, and similar pools are active in REIT sponsor positions and primary office / warehousing transactions; their monetisation cycles (lock-in expiries) create unit-supply overhangs.

Cross-check sector flow via `get_market_context(section='fii_dii_flows')` before claiming sector-level rotation. A single stock's FII % change is not a sector signal unless corroborated at sub-sector aggregate.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping real-estate economics over 3-5 years:
- **Premiumisation** — luxury (>₹5Cr ticket) and premium (₹1.5-5Cr) share of listed-developer presales has risen from ~30% pre-2020 to ~50-55% in the current cohort. Developers with no luxury exposure are structurally under-exposed to the wealth-cycle tailwind.
- **REIT listing pipeline expanding** — EMBASSY (2019) and MINDSPACE (2020) were the first wave; BIRET and NEXUS followed; the **SEBI SM-REIT framework (2024)** brings smaller assets to market and expands the listed-lease-annuity universe.
- **Warehousing as a thematic** — post-2020 e-commerce GMV growth and post-2020 manufacturing-PLI incentives drive 8-12% annual rent growth in prime logistics micro-markets; warehouse-specialist listed plays are a distinct investable universe.
- **Data-centre REITs emerging** — AI and cloud workloads drive MW-capacity demand; data-centre specialist listings are at an early stage in Indian markets.
- **Fractional-ownership / SM-REIT regulation** — SEBI's 2024 SM-REIT framework formalises fractional commercial ownership at the ₹10-50 Cr asset size; it broadens the retail-accessible lease-annuity market.
- **Post-RERA structural improvement** — the unorganised-developer share of new-home sales has compressed from ~70% pre-2017 to ~40-45% in 2024; listed-developer cohort gains structural share every cycle.
- **Built-to-suit and integrated-township formats** — land-plus-build models are expanding as customer preferences shift toward gated-community living with integrated amenities.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "urbanisation tailwind" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. The sector-agent-relevant KPIs by sub-sector:
- **Residential developers** — presales value (₹Cr), presales volume (mn sqft), realization per sqft (₹), land bank (mn sqft developable), projects under construction (units / mn sqft), collection efficiency (collections / presales %), delivered-to-sold ratio, Net Debt / Equity, Net Debt / EBITDA.
- **REITs (office)** — NOI (₹Cr), cap rate (%), distribution yield (%), WALE (years), occupancy (%), in-place-vs-market rent gap (%), NOI growth YoY (%), leasing volume (mn sqft / quarter).
- **REITs (retail)** — NOI, cap rate, trading-density (footfall × conversion), tenant-sales growth, minimum-guarantee vs percentage-rent mix, anchor-tenant concentration.
- **Specialty — warehousing** — occupancy, WALE, rent psf, built-to-suit vs multi-client mix, top-tenant concentration.
- **Specialty — data-centre** — MW commissioned, MW under construction, occupancy by MW, cap rate, revenue per MW.

A number quoted without sector percentile (e.g., "presales ₹5,000 Cr") omits whether that is top-quartile, median, or bottom-quartile; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable names within the sub-sector) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for index-weight context and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's stated sector view — explicitly label it as management-sourced rather than independently benchmarked.

### Open Questions — Real-Estate Sector-Specific
- "Where is the sector in the residential cycle, the commercial cycle, and the specialty (warehousing / data-centre) cycle, and are the three phases aligned or divergent?"
- "What is the current home-loan rate and the implied affordability index for the mid (₹50L-1.5Cr) and premium (₹1.5-5Cr) ticket-size segments?"
- "Is any state-RERA, SEBI REIT, or SEBI SM-REIT draft circular in public consultation that would reprice developer or REIT economics?"
- "What is the DII positioning trajectory across the listed-developer cohort — is it converging toward sector-neutral Nifty weight or still structurally underweight?"
- "For specialty (warehousing / data-centre): what share of incremental sector AUM is coming from the new format versus legacy office / residential, and what cap-rate differential supports the shift?"
