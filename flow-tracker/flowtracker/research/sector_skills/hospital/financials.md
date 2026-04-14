## Hospital — Financials Agent

### ARPOB — The Pricing Power Metric
ARPOB (Average Revenue Per Occupied Bed per day) is the hospital industry's equivalent of ARPU — it compresses case mix, payer mix, and facility pricing into one headline number. Rising ARPOB signals either a richer case mix (complex tertiary cases), better insurance realization, or facility upgrades. Declining ARPOB almost always reflects a payer mix shift toward government schemes (AB-PMJAY rates are materially lower) or competitive pricing pressure in a saturated micro-market. Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **ARPOB** — ₹35K-55K typical for tier-1 multispecialty; ₹70K-100K+ for tertiary flagship units running high-acuity case mix (cardiac, oncology, transplant programs)
- **ARPOB growth YoY** — isolate price vs case-mix drivers from concall commentary

### Occupancy — The Utilization Engine
Occupancy of 65-75% is a mature hospital at steady state. Above 80% indicates pricing power and a capacity-constrained unit — which typically precedes a capex announcement. The math: Occupancy × ARPOB × Bed Count = inpatient revenue; multiply by (1 + OPD revenue ratio) for a rough total revenue check against reported numbers.
- Track occupancy split by old vs new beds — new beds drag the blended average down, masking strong mature-unit performance
- Compare against peer median via `get_peer_sector(section='benchmarks')` and the company's own 5Y trend

### Case Mix — The Margin Differentiator
Cardiac surgery, oncology, neuro, and organ transplant run ARPOB 2-3x the house average and EBITDA margins roughly 2x. Ortho, general medicine, and OB-GYN are volume drivers but lower margin. Within each specialty, payer mix stacks cash/insurance > PMJAY > CGHS > ECHS in realization order. A hospital with >40% PMJAY/CGHS exposure is structurally margin-dilutive — flag this explicitly from concall disclosures.

### Doctor Fee Structure — Employment vs Retainer
The employment model drives operating leverage: employed doctors earn fixed salaries, and the hospital captures the full margin above cost. The retainer/consultant model (typically 70-80% fee-share to the doctor) is variable-cost — the hospital earns on room charges, diagnostics, and pharmacy share instead. Operators run a spectrum from predominantly retainer-based to predominantly employed models; the ratio and its shift over time is a direct predictor of margin trajectory.

### New Bed Maturity Curve — Why Consolidated Margins Mislead
A newly commissioned hospital loses money for 2-4 years while occupancy ramps, doctors are onboarded, and the brand is built in the micro-market. During active expansion phases, consolidated EBITDA margin is dragged down by loss-making new units — this is a feature, not a problem, but it must be called out. Mature hospital EBITDA margin at steady state is 22-28%; anything below that at a mature unit is a red flag.
- Use `get_quality_scores(section='subsidiary')` or concall segment disclosure to separate mature vs maturing beds
- Ignore consolidated margin during expansion phase — focus on mature-unit margin as the true earnings power indicator

### Capital Intensity — Heavy Upfront, Sticky Cash Flow
Hospitals cost ₹1.5-3 Cr per bed to build out in tier-1 cities. Once built, maintenance capex drops to 7-10% of revenue. The cash flow profile is therefore U-shaped: negative during expansion, strongly positive once the unit matures.
- Track CFO/EBITDA conversion via `get_fundamentals(section='cash_flow_quality')` — should be 85%+ at steady state
- If conversion is chronically below 75% for a mature portfolio, investigate working capital or subsidiary leakage

### Working Capital — Receivables Are the Story
The insurance TPA (Third Party Administrator) cycle runs 45-90 days; government schemes (PMJAY, CGHS) take 90-180 days with non-trivial write-off risk. Rising receivable days combined with a rising government payer share is an early warning of cash collection stress — the P&L will look fine for several quarters before the balance sheet exposes it.
- Extract receivable days trend from `get_fundamentals(section='working_capital')`
- Cross-check against payer mix disclosures in concall

### Asset-Light Models — Operation & Maintenance (O&M)
Some hospital chains operate O&M contracts on third-party infrastructure (often overseas or airport-adjacent hospitals). These carry no asset capital but earn management fees plus a profit share — they dilute average ARPOB but are highly ROCE-accretive and should be valued separately from the owned-bed portfolio. Flag explicitly when present in the segment disclosure.

### Valuation
- Use **EV/EBITDA** as the primary valuation metric, not PE — capex-heavy depreciation distorts PE comparability across the peer set
- Premium valuations (22-28x EV/EBITDA) are justified when ARPOB is growing 8%+ YoY, blended occupancy is >70%, and the announced pipeline adds 20%+ to the bed count
- **₹ Cr per bed** is a useful cross-peer sanity check on EV — compare against `get_peer_sector(section='benchmarks')`
- Call `get_valuation(section='band', metric='ev_ebitda')` for historical band context
