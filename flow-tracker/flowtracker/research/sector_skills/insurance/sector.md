## Insurance — Sector Agent

### Macro Context — Rates, Household Financial Savings, Catastrophe Cycle
Insurance is highly macro-sensitive — life insurers on the rate cycle and household-savings share, general insurers on inflation and catastrophe frequency, insurtech on the VC-funding cycle. No stock-level narrative is complete without anchoring to the macro regime. Pull the regime from `get_market_context(section='macro')` and state these four variables explicitly:
- **Repo rate and 10Y G-sec trajectory** — current level, last 4 moves, RBI MPC stance. For life insurers, falling yields compress par-fund returns and non-par new-business pricing (−); for general insurers, falling yields compress float income (−) with a 4-6 quarter lag. Rising yields reverse both with lag.
- **Medical inflation (health)** — health insurance loss-ratio elasticity to medical inflation is roughly 0.5-0.8×; a 200 bps medical-inflation shock raises loss ratio by 100-160 bps unless pricing is reset within the renewal cycle.
- **GDP growth and household financial-savings share** — life-insurance penetration (currently <4% of GDP) is driven by rising household financial-savings allocation. A 100 bps rise in the financial-savings share of disposable income translates to 6-10% NBP growth above the volume baseline over 4-6 quarters.
- **Catastrophe frequency** — cyclone, flood, and earthquake frequency driven by climate trends has increased the baseline cat-loss ratio for Indian general insurers by 100-200 bps across the last decade; reinsurance costs have followed.

### Sector Cycle Position
Insurance lives through three overlapping cycles — life structural growth, general short-cycle, insurtech funding. Diagnose each before declaring sector direction:
- **Life insurance — structural growth** (penetration <4% of GDP, under-penetration driver intact) with cyclical overlays: rate cycle (investment yield + pricing), regulatory cycle (EoM and commission-cap amendments), and product-cycle (protection vs savings mix shift). A correctly-positioned life insurer is growing structurally even in a flat macro year.
- **General insurance — short-cycle** with two distinct cycles: motor-tariff cycle (periodic IRDAI re-pricing of motor TP rates lags underlying claim inflation) and health-loss-ratio cycle (medical inflation lagging price revisions). Catastrophe years sit on top as unpredictable shocks.
- **Insurtech — VC-funding cycle** overlaying a structural distribution-reshape thesis. During funding winters, CAC inflation drives smaller competitors out; survivors see contribution-margin acceleration. During funding booms, CAC inflates industry-wide and contribution margins compress.

State which phase the sub-sector is in for each cycle; contradictory phases (e.g., structurally-growing life penetration + regulatory tightening cycle) are the interesting setups.

### Competitive Hierarchy — Tier the Sub-sectors
Sector reports collapse when they treat insurance as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics'`:
- **Life insurers — top-3 by APE plus LICI** — LICI is a structural market-share shifter (private sector gains ~100-200 bps share annually against LIC over the last decade; the pace of shift is a watch variable). Top-3 private: SBILIFE, HDFCLIFE, ICICIPRULI. Mid-tier: MAXFIN (Max Life via holdco Max Financial), BAJAJFINSV (Bajaj Allianz Life via Bajaj Finserv).
- **General insurers — top-3 by GDPI** — public-sector general insurers (New India Assurance, National Insurance, United India, Oriental) and listed private (ICICIGI, BAJAJFINSV for Bajaj Allianz General). State-backed GIC is the reinsurer.
- **Standalone health insurers** — STARHEALTH and NIVABUPA as the listed standalone-health names; the retail-health category is the high-growth, higher-ROE segment.
- **Insurtech marketplaces** — POLICYBZR / PB Fintech as the listed platform; private competitors (ACKO, Ditto) materially smaller.
- **Reinsurers** — GIC Re is listed; state-backed reinsurance is the dominant market structure with foreign reinsurer branches (since IRDAI 2016 amendments) operating smaller books.

### Institutional-Flow Patterns — Insurance-Specific
Insurance carries 2-3% of Nifty weight — smaller than BFSI but with distinct flow mechanics that the ownership and sector agents must both reflect:
- **LIC as institutional holder** — LIC is typically the largest single institutional holder across listed insurers (4-9% in private life insurers, 3-6% in general insurers); treat LIC the same way BFSI treats it — quasi-sovereign structural floor, not tactical conviction.
- **DII structurally overweight** — insurance-sector MFs, BFSI sector funds, and index weight together produce structural DII overweight in listed life insurers. DII share in SBILIFE, HDFCLIFE, ICICIPRULI routinely runs 18-30%.
- **FII flows concentrated in the top 3 private life insurers** — foreign active funds anchor the premium valuations; passive FII flows show up around Nifty and MSCI rebalance windows.
- **LICI (LIC listed itself)** — the Govt of India is promoter; LIC's own stake in its scheme inventory is disclosed but not a conviction signal. Private insurers' share shift against LIC is the structural-flow watch.

Cross-check sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak'` before claiming sector-level institutional rotation. A single insurer's FII% change is not a sector signal unless corroborated at the index-weight level.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping insurance economics over 3-5 years:
- **Rising penetration of health + protection** — under-penetration of retail health (currently 5-7% of GDP vs 10-12% for developed markets) and term protection (currently <1% of GDP vs 5-8% for developed markets) is a multi-decade tailwind; any GST cut or sum-insured mandate accelerates adoption.
- **Regulatory evolution — risk-based capital** — India's transition to Ind AS 117 / IFRS-17-aligned reporting and risk-based capital changes how VNB, reserves, and solvency are disclosed; the peer-ranking reshuffle is a 2-3 year event.
- **Insurtech distribution reshape** — POLICYBZR and similar platforms are reshaping the agent-to-direct economics of term protection and retail health; traditional agency-heavy insurers face a structural margin hit on the protection line.
- **GST cut potential** — current 18% GST on insurance premium is a recurring political-debate item; any cut to 5% would be a multi-year tailwind but is not base-case.
- **LIC market-share shift** — private sector has gained ~100-200 bps share annually over the last decade; the pace is the watch variable, as structural change in LIC's own business (post-listing corporate governance, product-approval pace) would alter the shift trajectory.
- **Climate-driven catastrophe repricing** — reinsurance prices have risen globally 20-40% over 2022-24 on catastrophe frequency; Indian general insurers face higher reinsurance cost and therefore lower retention, compressing ROE through the cycle.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. The sector-agent-relevant KPIs by sub-sector:
- **Life insurers** — VNB margin %, APE growth %, NBP growth %, 13-month persistency %, 61-month persistency %, solvency %, operating RoEV %, protection-and-non-par share of APE %.
- **General insurers** — combined ratio %, loss ratio %, expense ratio %, GDPI growth %, solvency %, retention ratio %, segment-wise CR (motor OD, motor TP, retail health, group health, property).
- **Standalone health insurers** — retail-health share of GDPI %, retail-loss-ratio %, group-loss-ratio %, claims-frequency trend, net-promoter-score (where disclosed).
- **Insurtech / marketplaces** — visitor-to-buyer conversion %, CAC, LTV, LTV/CAC, contribution margin %, standalone (ex-subsidiary) operating margin %.

A number quoted without sector percentile (e.g., "combined ratio 106%") omits whether that is top-quartile, median, or bottom-quartile within Indian general insurers; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable names) or `section='benchmarks'` returns null on a KPI, fall back to `get_yahoo_peers` for global insurer comparables (Prudential PLC, Ping An, AIA, Allianz for life; Munich Re, Swiss Re for reinsurance) and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked. Do not park "need global peers" as an Open Question when `get_yahoo_peers` is available.

### Open Questions — Insurance Sector-Specific
- "Where are we in the life-insurance regulatory cycle (time since last EoM amendment) and the general-insurance catastrophe cycle (cat-loss ratio vs 10-year trend)?"
- "What is the private-sector share shift trajectory vs LIC over the last 4-8 quarters, and is it accelerating, stable, or decelerating?"
- "Are any IRDAI draft circulars (surrender-charge, commission-cap, product-approval, risk-based capital) currently in public consultation that would reshuffle sub-sector economics?"
- "What is the insurtech funding-cycle state — tightening (CAC discipline) or loosening (CAC inflation) — and how does that translate to the listed platform's competitive position?"
- "For structural shifts (risk-based capital transition, GST cut potential, retail-health penetration): what share of sector growth is coming from the new driver vs legacy APE / GDPI origination?"
