## Pharma — Financials Agent

### Geography Mix Drives Everything
The geography split completely alters margin profile. Extract from `concall_insights` or `sector_kpis`:
- **US Generics** — high volume, high price erosion (5-15% annually), lumpy (product launches drive revenue steps)
- **India Branded Formulations** — sticky revenue, high margin (25-30% EBITDA), steady growth
- **Emerging Markets / API** — moderate margins, FX exposure

If revenue split is available, analyze margin trajectory for each geography separately. Consolidated margin is a blended number that hides US erosion.

### US Price Erosion (CRITICAL)
- Track **Gross Margin trajectory** specifically — declining gross margin with stable EBITDA margin means the company is cutting costs to offset US pricing pressure. This is a ticking clock
- The question is always: is the ANDA pipeline (new launches) enough to offset base business erosion?

### R&D Investment
- **R&D as % of sales** — from `concall_insights` or `sector_kpis` (defined as `r_and_d_spend_pct`)
- Also check `get_fundamentals(section='cost_structure')` — R&D may appear in expense schedules
- 5-7% of sales is standard for mid-cap Indian pharma, 8-12% for specialty/innovators
- Rising R&D % with flat revenue = pipeline investment. Declining R&D % = harvesting mode (short-term profit, long-term risk)

### Pipeline Metrics (from concall_insights)
- **ANDA filed/approved** — defined in `sector_kpis` as `anda_filed_number`, `anda_approved_number`
- Approval-to-launch conversion matters more than raw filings
- **FDA compliance status** — any warning letters, import alerts, or OAI observations. This is binary risk — one FDA warning letter can wipe out an entire facility's revenue

### FX Impact (CRITICAL for Export-Heavy Pharma)
- If >30% revenue from exports, analyze currency translation impact on margins and consolidated debt
- Check Other Income for FX gains/losses. Note hedging policy and horizon from concall_insights
- USD depreciation compresses margins for US-facing revenue; INR strengthening hurts reported growth

### Specialty vs Generics
- If the company has a specialty portfolio (patented/complex generics/biosimilars), separate this from base generics
- Specialty commands premium valuation (higher margins, lower competition, longer lifecycle)
