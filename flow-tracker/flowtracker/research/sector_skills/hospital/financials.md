## Hospital — Financials Agent

### ARPOB — The Pricing Power Metric
ARPOB (Average Revenue Per Occupied Bed per day) is the hospital industry's equivalent of ARPU — it compresses case mix, payer mix, and facility pricing into one headline number. Rising ARPOB signals either a richer case mix (complex tertiary cases), better insurance realization, or facility upgrades. Declining ARPOB almost always reflects a payer mix shift toward government schemes (AB-PMJAY rates are materially lower) or competitive pricing pressure in a saturated micro-market. Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **ARPOB** — ₹35K-55K typical for tier-1 multispecialty; ₹70K-100K+ for tertiary flagship units running high-acuity case mix (cardiac, oncology, transplant programs)
- **ARPOB growth YoY** — isolate price vs case-mix drivers from concall commentary. Watch for a 5% GST on non-ICU rooms billed >₹5,000/day inflating headline ARPOB — confirm growth is organic, not tax/inflation pass-through
- **ALOS (Average Length of Stay)** — a core KPI, not a footnote. Organised chains run 3-5 days. ALOS is **inversely related to ARPOB**: billing is front-loaded with diagnostics and surgery in the first 48 hours, so a shorter stay raises both per-day realization and bed turnover. The healthy signature is falling ALOS *with* rising ARPOB and stable/rising occupancy; rising ALOS at flat ARPOB signals case-mix dilution or operational slack

### Occupancy — The Utilization Engine
Occupancy of 65-75% is a mature hospital at steady state. Above 80% indicates pricing power and a capacity-constrained unit — which typically precedes a capex announcement. The math: Occupancy × ARPOB × Bed Count = inpatient revenue; multiply by (1 + OPD revenue ratio) for a rough total revenue check against reported numbers.
- Track occupancy split by old vs new beds — new beds drag the blended average down, masking strong mature-unit performance
- Compare against peer median via `get_peer_sector(section='benchmarks')` and the company's own 5Y trend

### Case Mix — The Margin Differentiator
Cardiac surgery, oncology, neuro, and organ transplant run ARPOB 2-3x the house average and EBITDA margins roughly 2x. Ortho, general medicine, and OB-GYN are volume drivers but lower margin. Within each specialty, payer mix stacks cash/insurance > PMJAY > CGHS > ECHS in realization order. A hospital with >40% PMJAY/CGHS exposure is structurally margin-dilutive — flag this explicitly from concall disclosures. Note AB-PMJAY package rates are widely flagged by operators as below cost-recovery for tertiary procedures, so the Oct-2024 expansion to all citizens 70+ (irrespective of income, ₹5L family cover) is a volume tailwind but margin-dilutive — assess whether a chain is leaning into or rationing scheme volume.

### Doctor Fee Structure — Employment vs Retainer
The employment model drives operating leverage: employed doctors earn fixed salaries, and the hospital captures the full margin above cost. The retainer/consultant model is variable-cost — the doctor takes 70-80% of the *consultation/surgical professional-fee component of the bill only* (not 70-80% of the total bill), while the hospital earns on room charges, diagnostics, and pharmacy share instead. At the P&L level, total doctor payouts (employed-doctor salaries + retainer professional fees) typically run ~15-22% of total operating revenue — do not conflate the per-fee share with the consolidated cost line. Operators run a spectrum from predominantly retainer-based to predominantly employed models; the ratio and its shift over time is a direct predictor of margin trajectory.

### New Bed Maturity Curve — Why Consolidated Margins Mislead
A newly commissioned hospital loses money for 2-4 years while occupancy ramps, doctors are onboarded, and the brand is built in the micro-market. During active expansion phases, consolidated EBITDA margin is dragged down by loss-making new units — this is a feature, not a problem, but it must be called out. Mature hospital EBITDA margin at steady state is 22-28%; anything below that at a mature unit is a red flag.
- Use `get_quality_scores(section='subsidiary')` or concall segment disclosure to separate mature vs maturing beds
- Ignore consolidated margin during expansion phase — focus on mature-unit margin as the true earnings power indicator

### Capital Intensity — Heavy Upfront, Sticky Cash Flow
Hospitals cost ₹1.5-3 Cr per bed to build out in tier-1 cities. Once built, **maintenance (routine) capex is only ~2-4% of revenue** — keep this distinct from growth/expansion capex, which is far larger and lumpy. The cash flow profile is therefore U-shaped: negative during expansion, strongly positive once the unit matures.
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
- **Adjust for Ind AS 116 (Leases) before comparing EV/EBITDA across the peer set.** For asset-light/leased chains, operating rent is reclassified below EBITDA (as ROU depreciation + lease interest), inflating reported EBITDA by ~15-50% vs an asset-heavy owned-bed operator, and EV must include lease liabilities. Normalise pre/post-Ind AS 116 (or use a rent-adjusted/EV-incl-leases basis) so owned vs leased models are comparable
- Premium valuations (22-28x EV/EBITDA) are justified when ARPOB is growing 8%+ YoY, blended occupancy is >70%, and the announced pipeline adds 20%+ to the bed count
- **Regulatory pricing risk flag**: monitor concall commentary on the Supreme Court's 2024 push for standardized procedure rates (interim threat of CGHS rates, often 40-50% below private list) and Clinical Establishments Act enforcement — a binding cap is the largest downside to premium-ARPOB valuations
- **₹ Cr per bed** is a useful cross-peer sanity check on EV — compare against `get_peer_sector(section='benchmarks')`
- Call `get_valuation(section='band', metric='ev_ebitda')` for historical band context
