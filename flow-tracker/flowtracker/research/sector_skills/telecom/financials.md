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

### Spectrum Amortization Distortion
- Extract spectrum amortization separately from regular depreciation if available from concall_insights
- Present EBITDA and EBITDAaL (after lease/spectrum) to show true cost of spectrum

### International Segments
For operators with meaningful international operations (Africa, EMEA, SEA exposures):
- Segment-level revenue and EBITDA from concall_insights
- Currency translation impact on consolidated numbers (emerging-market currencies are often volatile against INR)
- If segment data unavailable, flag as open question for SOTP valuation

### AGR / Spectrum Dues as Quasi-Debt (Not Just a Current Liability)
Indian telecom carries material **Adjusted Gross Revenue (AGR) dues** and **deferred spectrum payments** owed to the government under extended moratoria. These are shown as current + non-current liabilities but economically behave as quasi-debt with non-trivial refinancing and equity-conversion risk:
- Include AGR + deferred spectrum in the **true Net Debt calculation** — consolidated Net Debt / EBITDA looks materially different once these liabilities are added back
- Track the **NPV of moratorium payouts** — current moratoria are interest-bearing, and several thousand crores of NPV reduction can be available if the government offers equity conversion (dilutive) or early-settlement discounts
- Flag any concall commentary on equity-conversion clauses, government stake in telecom entities, or moratorium extensions — each is a material dilution or liquidity signal
- Extract the AGR + deferred spectrum balance from `get_fundamentals(section='balance_sheet_detail')` notes; use `get_company_context(section='concall_insights', sub_section='management_commentary')` for servicing plans

### Active Subscriber (VLR) Ratio — Cutting Through Gross-Adds Inflation
Gross subscriber base is polluted by inactive SIMs, dual-SIM users counted twice, and seasonal tourist adds. The **VLR (Visitor Location Register) ratio** — active subscribers as a % of reported VLR base — is the operator-reported measure of the subscriber base that actually transacts:
- Benchmark: 85%+ is clean; <80% signals significant inactive-SIM inflation (common after feature-phone customer churn or promotional aggressive adds)
- ARPU disclosed on VLR base (vs total reported base) is a meaningfully different number — always ask which denominator the operator is using
- 2G→4G→5G upgrade mix is the upgrade pipeline: disclose the % of subs still on 2G (lower ARPU, churn risk as networks sunset 2G) and the migration trajectory
- Extract from `get_company_context(section='sector_kpis')` or concall disclosures

### Segment-Level SOTP — Mobile B2C vs Enterprise vs FTTH vs Towers
Diversified telecom operators run 4-6 distinct businesses with very different multiples: low-growth mobile B2C, SaaS-like B2B/enterprise, sticky FTTH broadband, infra-like tower subsidiaries, and payments / digital platforms. A single EV/EBITDA multiple applied to the whole company under-prices the premium segments:
- Extract segment-level revenue, EBITDA, and capex from `get_company_context(section='concall_insights', sub_section='financial_metrics')` and segment reporting notes in filings
- Apply pure-play peer multiples per segment via `get_peer_sector(section='benchmarks')` — enterprise/B2B at 12-18x, FTTH at 10-15x, towers at 8-12x, mobile B2C at 7-10x (indicative)
- The blended SOTP multiple typically lands 15-30% above a consolidated-telecom multiple — flag the gap explicitly when it is material
