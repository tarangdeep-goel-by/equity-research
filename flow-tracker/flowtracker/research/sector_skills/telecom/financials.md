## Telecom — Financials Agent

### ARPU Flow-Through Analysis (CRITICAL)
ARPU is the single most important driver. But don't just report ARPU — analyze the financial flow-through:
- Extract ARPU from `get_company_context(section='concall_insights')` or `sector_kpis`
- **Incremental EBITDA per ₹1 ARPU hike** = (ARPU increase × subscriber base) adjusted for variable costs. Telecom has ~80% incremental margins on ARPU hikes (mostly fixed-cost network)
- Model: if ARPU rises ₹10 on 350M subscribers, revenue impact = ₹3,500 Cr/quarter. At 80% incremental margin = ₹2,800 Cr EBITDA uplift
- This connects the operational KPI (ARPU) to the financial impact — don't leave them disconnected

### Capex Intensity (CRITICAL — Telecom is a Capital Sink)
- **Capex/Sales ratio** — track this alongside ARPU. ARPU growth is irrelevant if Capex/Sales outpaces it
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
