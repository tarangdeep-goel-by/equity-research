## Pharma — Financials Agent

### Geography Mix Drives Everything
The geography split completely alters margin profile. Extract from `concall_insights` or `sector_kpis`:
- **US Generics** — high volume, high price erosion (5-15% annually), lumpy (product launches drive revenue steps)
- **India Branded Formulations** — sticky revenue, high margin (25-30% EBITDA), steady growth
- **Emerging Markets / API** — moderate margins, FX exposure

If revenue split is available, analyze margin trajectory for each geography separately. Consolidated margin is a blended number that hides US erosion.

### US Price Erosion — The Ticking Clock for Generics
Track **Gross Margin trajectory** specifically — declining gross margin with stable EBITDA margin means the company is cutting costs to offset US pricing pressure. This buys time but isn't sustainable indefinitely — eventually cost-cutting runs out of room while price erosion continues.
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

### FX Impact — Material for Export-Heavy Pharma
For companies with >30% revenue from exports, currency swings directly impact margins and can distort growth figures. USD depreciation compresses margins for US-facing revenue; INR strengthening hurts reported growth.
- Analyze currency translation impact on margins and consolidated debt
- Check Other Income for FX gains/losses. Note hedging policy and horizon from concall_insights

### Specialty vs Generics
- If the company has a specialty portfolio (patented/complex generics/biosimilars), separate this from base generics
- Specialty commands premium valuation (higher margins, lower competition, longer lifecycle)

### Gross-to-Net Adjustments — The US Revenue Quality Check
US pharma revenue is reported **net** of rebates, chargebacks, shelf-stock accruals, failure-to-supply penalties, and return reserves. These Gross-to-Net (GTN) adjustments are management-estimated — and are a well-known earnings-smoothing lever. A small tweak to GTN estimates (20-50 bps of gross sales) materially flatters or flatters EPS.
- Track **GTN reserve / gross revenue** trajectory where disclosed in filings or concall — typical range is 45-60% of gross for US generics
- A sudden step-down in GTN accruals signals either real channel improvement or accrual release (pulling revenue forward) — check `get_company_context(section='filings', sub_section='notes_to_accounts')` for the US revenue reserve walk
- Rising returns / stability issues (recalls, failure-to-supply) show up here first — a company that expands US launches while GTN accruals don't scale proportionally is hiding near-term provisioning
- Flag the risk even when data isn't granular — US revenue recognition is where pharma earnings quality issues most often emerge

### Facility Utilization / Fixed Asset Turnover — The Idle-Plant Drag
Pharma manufacturing plants are capex-heavy (₹500-2,000 Cr for a mid-size USFDA-compliant facility) and must clear FDA inspections before they can supply regulated markets. A plant under an FDA warning letter, import alert, or OAI status can sit idle for 2-4 years while remediation runs — during which fixed costs continue to bleed.
- Compute **Fixed Asset Turnover** = Revenue / Gross Block via `calculate` using `get_fundamentals(section='ratios')`. Compare against peer median via `get_peer_sector(section='benchmarks')`
- A FAT 30-40% below peer median signals idle capacity — either under-utilized plants or an FDA-halted facility still on the books earning zero return
- Cross-reference FDA status from `get_company_context(section='concall_insights')` — any mentioned warning letter, 483 observations, or OAI classification on a material facility is a structural ROCE drag until cleared
- Flag capacity utilization explicitly; a pharma report that ignores FDA compliance on manufacturing facilities is missing a binary risk

### API Backward Integration / KSM Sourcing
Gross margin resilience during supply shocks hinges on **Key Starting Material (KSM)** and API backward integration. Indian pharma historically sources 60-70% of KSMs from China; any disruption (pandemic, export curbs, logistics crunch) hits margin directly, and the lag before domestic or alternative-country sourcing catches up is 12-18 months.
- Extract API/KSM sourcing mix from `get_company_context(section='concall_insights')` — management often discloses "% of KSM imported from China" or "% of API produced in-house"
- A vertically integrated producer (captive API for own formulations) carries materially lower gross-margin volatility through supply disruptions than a pure formulator
- China+1 sourcing strategies and India-specific PLI benefits for bulk drugs are live policy tailwinds — note if the company is positioned to capture them
