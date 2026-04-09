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

### Africa/International Segments
For companies with international operations (e.g., Bharti Airtel Africa):
- Segment-level revenue and EBITDA from concall_insights
- Currency translation impact on consolidated numbers (Africa currencies are volatile)
- If segment data unavailable, flag as open question for SOTP valuation
