## Pharma — Sector Agent

### Macro Context — US Drug Pricing, Generic Erosion Cycle, FX, KSM Supply
Pharma is among the most macro-cross-coupled sectors in Nifty because three distinct macro vectors interact: US drug-pricing policy, INR-USD, and China-linked KSM cost. No stock-level narrative is complete without anchoring to the macro regime. Pull the current regime from `get_market_context(section='macro')` and state these variables explicitly:
- **US drug-pricing policy regime** — the Inflation Reduction Act (IRA) 2022 introduced Medicare negotiation on top-10 (then top-20) innovator molecules from 2026; this reshapes innovator economics and creates a downstream generic opportunity as innovators respond with portfolio-pruning. Current regime FY24-25 is "pre-negotiation-implementation with generic-substitution momentum building."
- **US-generics-erosion cycle in top-500 molecules** — sector-wide price erosion averaged 8-12% per annum in FY16-20 (the "erosion cliff" era) and has moderated to 3-6% in FY22-25 as the post-settlement-regulatory regime and consolidated buyer structure (ESI / Red Oak / Walgreens Boots Alliance) stabilised pricing. Current regime is "post-erosion stabilisation with specialty / complex generics leadership premium emerging."
- **USD-INR trajectory** — sector revenue is ~50-65% USD-denominated for top-3 generics; every ₹1 of INR depreciation against USD is ~50-80 bps of reported gross margin tailwind before hedging.
- **KSM import cost (China linkage)** — China manufacturing / export-curb episodes (COVID 2020, 2022 energy-crunch, periodic environmental-closures) produce 15-30% KSM cost spikes with 12-18 month pass-through lag. PLI-bulk-drugs scheme (2020-24) partially de-risks but India's KSM-sufficiency is a 5-8Y build, not a near-term insulation.
- **India CPI-health inflation and DPCO pass-through** — DPCO allows annual price revision linked to WPI (non-scheduled molecules) and NPPA-notified ceilings (scheduled molecules). In a 4-6% CPI regime, India-branded players pass through 3-5% pricing annually.
- **US pharmaceutical tariff risk** — any shift toward targeted tariffs on Indian pharma imports to US (periodic policy noise, particularly in election cycles) is a tail risk for US-heavy exporters; track via `get_market_context(section='macro')` and news-flow.

### Sector Cycle Position
Pharma lives through four overlapping cycles — US generics price-erosion, India branded growth, specialty project-cycle, and ANDA-filing wave. Diagnose each before declaring sector direction:
- **US-generics erosion cycle (4-7Y)** — deep-erosion phase (8-12% per-annum price decline, launches barely offset base-book erosion, sector PE compressed 15-20×), stabilisation phase (5-7% erosion, specialty and complex-generics leadership premium emerging, sector PE re-rating to 20-25×), consolidation phase (large-player buying / exiting specific molecule segments, erosion moderating to 3-5%). Current FY24-25 regime is "stabilisation to consolidation."
- **India branded growth cycle** — steady-state 8-11% IPM growth (volume 4-6% + price 4-6% via DPCO + new-intro 2-3%); policy-shock cycles periodically compress margin (DPCO expansions, trade-margin revisions, NLEM revisions). Current regime FY24-25 is "steady-state with chronic therapies outgrowing acute."
- **Specialty project-cycle (2-4Y filing-to-approval + 3-5Y ramp)** — each specialty molecule has its own timeline; sector aggregate pivots to specialty-leadership when 4-6 molecules are in Yr 2-4 ramp simultaneously. Current regime FY24-25 is "mid-ramp for top-3 specialty platforms at SUNPHARMA / DRREDDY / BIOCON with 2-3 next-wave launches in FY26-27."
- **ANDA-filing wave** — historically sector filed 300-400 ANDAs/year across top-10 players; FY20-22 dropped to 250-300 as portfolio-pivoting toward complex generics happened; FY23-25 has re-accelerated with complex-injectable and peptide-ANDA cohorts. Filing cadence is a 3-5Y leading indicator for US revenue 3-5Y forward.

State which phase the sector is in for each of the four cycles; contradictory phases (e.g., India-branded expansion + US-generics deep-erosion) are the interesting setups that define sub-type outperformance windows.

### Competitive Hierarchy — Tier the Sector
Sector reports collapse when they treat pharma as monolithic. Tier via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:
- **Tier-1 Indian pharma with top-3 US exposure** — SUNPHARMA, DRREDDY, CIPLA; 40-65% US revenue share, specialty platforms in build/ramp, ₹500-1,500 Cr R&D/year. These carry the sector-ETF flow and specialty-premium multiple.
- **Mid-cap India-branded leaders** — MANKIND, ABBOTINDIA, ALKEM, TORNTPHARM, IPCA, JBCHEMPHAR; India-branded share 55-85%, chronic-therapy focus, MR productivity and brand-rank-in-therapy are the differentiators. Typically trade at 30-40× PE on branded-franchise steadiness.
- **Specialty / complex-generics specialists** — LUPIN (respiratory / specialty), GLENMARK (inhalers / dermatology), BIOCON (biosimilars), NATCOPHAR (oncology); focused portfolios with higher concentration risk but specialty-margin profile.
- **CDMO / CMO pure-plays** — DIVISLAB, SYNGENE, GLAND, LAURUSLABS (CDMO segment), PIRAMAL (CDMO segment of Piramal Pharma Ltd); innovator-client-pipeline-driven with 18-28% EBITDA margin.
- **API / bulk drugs specialists** — DIVISLAB (API), LAURUSLABS (API), GRANULES, AUROPHARMA (API); backward-integrated supply to own formulations plus merchant API; PLI-beneficiary set.
- **Animal health niche** — ZYDUSLIFE (animal health segment), others; distinct demand profile (livestock + companion).
- **MNC India subsidiaries** — ABBOTINDIA, GLAXO India, Pfizer India; parent-sourced portfolio, repatriation focus, low float.
- **Hospitals / diagnostics / integrated healthcare** — APOLLOHOSP and similar; fundamentally different economic framework (occupancy × ARPOB vs pharma unit economics); sector agent should flag if the target falls outside formulations / API / CDMO and note that hospital / diagnostics framework is required.

### Institutional-Flow Patterns — Pharma-Specific
Pharma carries a 5-7% weight in Nifty; the flow mechanics are structurally different from BFSI's index-anchored flows:
- **FII-active in US-heavy names during US-drug-pricing cycles** — FII accumulation spikes when specialty platforms inflect (FY21-23 Ilumya / Cequa ramp at SUNPHARMA drove FII +3-5pp in 8 quarters) and FII exits when USFDA cycle turns adverse (Halol / Goa / Bachupally warning-letter episodes produced 2-4pp FII exits over 2-3 quarters).
- **DII (MF + insurance) structurally overweight in branded leaders** — India-branded names (MANKIND, ABBOTINDIA, TORNTPHARM) carry DII share 15-25% because branded-franchise steadiness and chronic-therapy growth fit MF mandates for defensive-growth allocation.
- **Sector-fund flows** — pharma-sector MFs periodically rotate within the sub-sector (US-specialty → India-branded → CDMO) based on macro regime; this produces single-name FII / DII movement not visible at sector aggregate.
- **FII-ETF / passive flows** — Nifty Pharma and Nifty Healthcare index-ETF flows hit top-5 names; rebalance windows produce mechanical flow independent of fundamentals.
- **Event-driven FII concentration spikes** — patent-cliff approvals, paragraph-IV FTF wins, complex-generic first-approval events drive short-duration FII spikes that are momentum-driven, not structural; treat these as cyclical flows.

Cross-check the sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation. A single stock's FII % change is not a sector signal unless corroborated across 3-4 peer names.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping pharma economics over 3-5 years:
- **India branded growth re-acceleration post-DPCO stabilisation** — the post-2019 DPCO-expansion wave compressed branded margins, and chronic-therapy growth re-accelerated FY22-25 as the post-COVID chronic-disease burden (cardio, diabetes, mental-health) compounded. Chronic-therapy-heavy portfolios (MANKIND, ABBOTINDIA, TORNTPHARM) are the structural beneficiaries.
- **US biosimilars opportunity (10-15Y trajectory)** — the global biosimilars market is in early commercial phase (post-Humira biosimilar launches 2023); Indian players (BIOCON, DRREDDY, LUPIN, CIPLA) with biosimilar development investments 2015-22 are entering commercial phase FY24-28. This is a structural revenue engine 5-10Y out, not a near-term ramp.
- **CDMO scale-up from biologics / continuous-manufacturing** — the innovator-pharma outsourcing wave accelerated post-COVID; Indian CDMOs (DIVISLAB, SYNGENE, LAURUSLABS, GLAND) with biologics / sterile-injectable / peptide capability are capturing share from Chinese CDMOs (China+1 tailwind). 5-8Y commercial-project visibility window.
- **PLI-led API reshoring** — the 2020-24 PLI-bulk-drugs scheme (₹15,000 Cr outlay) is backing 41 identified KSM / API molecules; beneficiary players include domestic API manufacturers with PLI-approved capacity. Production milestones over FY25-29 determine real-versus-nominal benefit.
- **IRA Medicare negotiation reshaping US innovator economics** — the 2026-30 implementation window compresses innovator pricing on top-10/20 molecules; downstream generic-substitution opportunity post-LOE is the Indian-generics prize. Molecule-level watchlist (gJardiance, gEliquis, gImbruvica, gJanuvia) against Indian-player ANDA portfolios is the correct monitoring frame.
- **Complex-generics / 505(b)(2) shift** — simple-molecule ANDAs have eroded to commodity-margin; the specialty / complex-generic / 505(b)(2) cohort is where differentiated margin sits. Filing cadence at top-5 Indian players shifted 2019-24 from simple ANDA to complex / 505(b)(2); revenue-impact peaks FY26-28.
- **India-innovator biosimilar rise** — domestic biosimilar launches in oncology, insulins, and autoimmune are displacing innovator imports; BIOCON, DRREDDY, CIPLA lead. 15-25% annual growth in India biosimilar market vs 8-11% IPM overall.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "specialty transformation" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. The sector-agent-relevant KPIs by sub-sector:
- **All pharma** — Revenue growth YoY%, EBITDA margin% (segment-wise if disclosed), Net debt / EBITDA, ROCE%, FCF Yield%, ETR%, FCF conversion% (CFO/EBITDA).
- **US-generics-heavy** — US revenue%, ANDA filings pending, ANDA approvals YTD, USFDA plant count + clean-inspection%, US specialty revenue share%, US revenue per ANDA.
- **India-branded-heavy** — India-branded revenue%, chronic therapy share%, MR count, MR productivity (₹ revenue / MR / year), brand-rank-in-therapy for top-5 brands, IPM outperformance.
- **Specialty** — Specialty revenue%, specialty molecule count, specialty gross margin%, R&D-to-revenue%, specialty molecule launch calendar.
- **CDMO / CMO** — Active project count by phase (Ph1/Ph2/Ph3/commercial), capacity utilisation%, revenue per active project, commercial-project revenue share%.
- **API / bulk drugs** — API gross margin%, KSM backward-integration%, DMF count filed/approved, captive vs merchant API revenue split.

A number quoted without sector percentile (e.g., "US revenue share of 40%") omits whether that is top-quartile, median, or bottom-quartile; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable names in the target's sub-type) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the sector weight and index-flow context and `get_market_context(section='macro')` for the top-down US-pricing / FX / KSM context. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's stated sector view — explicitly label it as management-sourced rather than independently benchmarked. For sub-type hierarchy (e.g., comparing a CDMO pure-play against the right peer set rather than against formulation-heavy majors), state which peer set is applied and why.

### Open Questions — Pharma Sector-Specific
- "Where is the sector in the US-generics-erosion cycle, the India-branded-growth cycle, the specialty project-cycle, and the ANDA-filing-wave cycle? Are the four phases aligned or divergent, and which sub-types benefit in the current alignment?"
- "What is the current US-branded molecule exclusivity-expiry calendar for the FY26-28 window, and which Indian-generics players' ANDA portfolios are positioned for each expiry?"
- "Is any NPPA / DPCO / NLEM expansion in public consultation that would reprice India-branded affected portfolios in the next 4-8 quarters?"
- "What is the current sector FII / DII flow trajectory, and is it concentrated in US-specialty names, India-branded-leaders, or CDMO / API pure-plays?"
- "For structural shifts (biosimilars, CDMO scale-up, PLI, IRA Medicare negotiation): what share of incremental sector growth is coming from each structural channel vs base-book growth?"
- "Where is KSM supply-chain concentration across the sector today, and is any upstream China disruption or policy shift in progress that would compress sector gross margin?"
