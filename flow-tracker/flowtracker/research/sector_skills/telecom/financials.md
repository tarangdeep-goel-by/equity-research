## Telecom — Financials Agent

### ARPU Flow-Through Analysis — Connecting KPI to Financials
ARPU is the single most important driver. But reporting ARPU in isolation is incomplete — the value lies in translating it to financial impact:
- Extract ARPU from `get_company_context(section='concall_insights')` or `sector_kpis`
- **Incremental EBITDA per ₹1 ARPU hike** = (ARPU increase × subscriber base) adjusted for variable costs. Telecom has ~80% incremental margins on ARPU hikes because the network is mostly fixed-cost
- Model: if ARPU rises ₹10 on 350M subscribers, revenue impact = ₹3,500 Cr/quarter. At 80% incremental margin = ₹2,800 Cr EBITDA uplift
- This connects the operational KPI (ARPU) to the financial impact — leaving them disconnected weakens the analysis

### Capex Intensity — Telecom Is a Capital Sink
ARPU growth is irrelevant if network investment consumes all of it. The real question is what's left after capex:
- **Capex/Sales ratio** — track this alongside ARPU
- OCF minus Capex is the only metric that shows true free cash generation after network investment
- OpFCF = EBITDA - Capex (available from `get_quality_scores(section='telecom')`)
- If Net Debt/EBITDA > 2x, analyze debt maturity profile from `get_fundamentals(section='balance_sheet_detail')`
- **CWIP / RoCE distortion during 5G:** telcos carry large Capital Work in Progress during the 5G rollout — capital that is in the capital-employed base but not yet generating revenue. Unadjusted RoCE/RoIC is therefore *understated* at peak rollout. When computing RoCE during the 5G-peak phase, show RoCE both including and excluding CWIP (i.e., on capitalised-and-operational assets only), and note the gap rather than reading the depressed headline RoCE as structural under-performance.

### Spectrum Amortization Distortion
- Extract spectrum amortization separately from regular depreciation if available from concall_insights
- Present EBITDA and EBITDAaL to show the true lease cost. **EBITDAaL deducts lease liabilities (Ind AS 116) only — it does NOT deduct spectrum amortisation**, which is an intangible-asset amortisation charge sitting below EBITDA. Do not describe EBITDAaL as "after lease/spectrum"; spectrum amortisation is removed at the PAT line, not the EBITDAaL line.

### International Segments
For operators with meaningful international operations (Africa, EMEA, SEA exposures):
- Segment-level revenue and EBITDA from concall_insights
- Currency translation impact on consolidated numbers (emerging-market currencies are often volatile against INR)
- If segment data unavailable, flag as open question for SOTP valuation

### AGR / Spectrum Dues as Quasi-Debt (Not Just a Current Liability)
Indian telecom carries material **Adjusted Gross Revenue (AGR) dues** and **deferred spectrum payments** owed to the government under extended moratoria. These are shown as current + non-current liabilities but economically behave as quasi-debt with non-trivial refinancing and equity-conversion risk:
- Include AGR + deferred spectrum in the **true Net Debt calculation** — consolidated Net Debt / EBITDA looks materially different once these liabilities are added back
- Track the **NPV of moratorium payouts** and the moratorium terms, which change materially with each relief package — do not assume a single fixed regime. The earlier 2021 reform package granted a 4-year interest-bearing moratorium; the April 2026 DoT relief package then gave Vodafone Idea a *new* 5-year moratorium after a ~27% AGR haircut to ₹64,046 Cr (from ~₹87,695 Cr) and froze further interest/penalties on the frozen dues until ~FY32. Always confirm the current moratorium's interest treatment and tenor from the latest filing rather than assuming
- Flag any concall commentary on equity-conversion clauses, government stake in telecom entities (the GoI holds ~49% of Vodafone Idea post the early-2025 ₹36,950 Cr debt-to-equity conversion), or moratorium extensions — each is a material dilution or liquidity signal
- Extract the AGR + deferred spectrum balance from `get_fundamentals(section='balance_sheet_detail')` notes; use `get_company_context(section='concall_insights', sub_section='management_commentary')` for servicing plans

### Tower-Consolidation Accounting — Adjust for the Indus Towers Step-Change
Bharti Airtel moved to a controlling stake in Indus Towers and began consolidating it (late 2024 / early 2025). Consolidation pulls the tower entity's revenue, EBITDA, capex and lease liabilities onto the Airtel consolidated statements, creating a step-change that breaks naive YoY comparisons:
- Consolidated EBITDA and capex jump for reasons that are *structural (scope change)*, not operational — do not narrate the YoY EBITDA-margin or capex move as mobile-business performance.
- For valid YoY **mobile-margin** comparison, either use the pre-consolidation comparable basis or strip the tower segment out of both periods. Flag the consolidation date and quantify the scope effect where the segment disclosure allows.
- The same consolidation also adds Indus's Ind AS 116 lease liabilities to consolidated Net Debt — reconcile this before reading the leverage trend.

### Active Subscriber (VLR) Ratio — Cutting Through Gross-Adds Inflation
Gross subscriber base is polluted by inactive SIMs, dual-SIM users counted twice, and seasonal tourist adds. The **VLR (Visitor Location Register) ratio** — active subscribers as a % of reported VLR base — is the operator-reported measure of the subscriber base that actually transacts:
- Benchmark: top players now run very high VLR ratios (Airtel ~99%, Jio ~92-94%); ~90%+ is clean for a top-3 operator and the old "85%+ is clean" benchmark is stale. A VLR ratio materially below ~88-90% for a leading operator signals inactive-SIM inflation (common after feature-phone customer churn or promotional aggressive adds)
- ARPU disclosed on VLR base (vs total reported base) is a meaningfully different number — always ask which denominator the operator is using
- 2G→4G→5G upgrade mix is the upgrade pipeline: disclose the % of subs still on 2G (lower ARPU, churn risk as networks sunset 2G) and the migration trajectory
- Extract from `get_company_context(section='sector_kpis')` or concall disclosures

### Segment-Level SOTP — Mobile B2C vs Enterprise vs FTTH vs Towers
Diversified telecom operators run 4-6 distinct businesses with very different multiples: low-growth mobile B2C, SaaS-like B2B/enterprise, sticky FTTH broadband, infra-like tower subsidiaries, and payments / digital platforms. A single EV/EBITDA multiple applied to the whole company under-prices the premium segments:
- Extract segment-level revenue, EBITDA, and capex from `get_company_context(section='concall_insights', sub_section='financial_metrics')` and segment reporting notes in filings
- Apply pure-play peer multiples per segment via `get_peer_sector(section='benchmarks')` — enterprise/B2B at 12-18x, FTTH at 10-15x, mobile B2C (Jio/Airtel core) currently ~12-15x EV/EBITDA, towers now ~6-8x (de-rated on tenant-concentration and Vi-receivables risk — see valuation.md) (indicative)
- The blended SOTP multiple typically lands 15-30% above a consolidated-telecom multiple — flag the gap explicitly when it is material
