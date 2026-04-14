## Chemicals — Financials Agent

### Specialty vs Commodity Mix — Drives the Entire Margin Profile
Consolidated margin means little for a chemicals company without the specialty/commodity split. Specialty products (adhesives, agrochem actives, pigments, performance polymers) earn 20-30% EBITDA margins because customers qualify specs over 12-18 months and switch reluctantly — pricing power is real. Commodity products (caustic, chlor-alkali, basic intermediates) run 8-15% EBITDA with profitability dictated by input cost pass-through and cycle timing. A "declining margin" reads very differently depending on which bucket is compressing: specialty compression is structural (competitor qualified, moat weakening), commodity compression is cyclical (China dumping, feedstock spike).
- Extract mix from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`
- If mix isn't disclosed quantitatively, flag as an open question rather than averaging both into one narrative

### Raw Material Pass-Through Ability
Specialty businesses can pass through RM costs with a 1-2 quarter lag because customers lock in specs, not prices — so gross margin should hold or widen over a full cycle. Commodity businesses get squeezed at both ends (input up, output capped by competition) and GM tracks the spread. The single cleanest test of pricing power: does gross margin widen despite input cost inflation? If yes, pricing power is confirmed empirically, not just claimed on the concall.
- Compare gross margin trend vs crude/benzene/caustic/ethylene price trends from concall commentary

### Capex Cycles & Incremental ROCE — Don't Panic on Asset Turnover Decline
Chemicals is capex-heavy: ₹500-2,000 Cr plants take 2-3 years to commission and ramp. During the capex build phase, asset turnover drops and ROCE compresses mechanically — this is not a deteriorating business, it's gross block ahead of revenue. The real question is incremental ROCE once the new capacity ramps (typical curve: ~60% utilization in Y1, ~85% by Y3). Penalizing headline ROCE during the build without modeling the ramp misreads the setup entirely.
- Call `get_quality_scores(section='incremental_roce')` when available, or compute manually via `calculate` using delta-EBIT vs delta-capital-employed
- Read `concall_insights` for management guidance on commissioning timeline and utilization ramp

### Working Capital — High by Design
Chemicals carries high raw material inventory (60-90 days) because of import dependencies and feedstock price volatility — companies pre-stock to avoid production halts. Receivable days vary sharply by channel: B2B industrial customers run 90+ days, distribution-led businesses 30 days. Rising inventory days can be pre-emptive buying ahead of RM inflation (positive) or slowing offtake (negative) — the two look identical in the numbers, only the concall can distinguish them.
- Extract CCC and components from `get_fundamentals(section='working_capital')`
- Cross-check the direction against concall commentary before concluding

### Forex & Export Mix
Exports often run 30-60% of revenue, so INR depreciation flatters reported growth and appreciation compresses it. Forex gains/losses routinely hit Other Income and can distort PAT — check before extrapolating a quarter's earnings.
- Pull FX impact via `get_fundamentals(section='cash_flow_quality')` or concall notes
- Note the hedging horizon (typically 6-12 months forward); unhedged exporters carry more quarterly volatility

### M&A Spikes — Resolve via Filings, Don't Guess
Chemicals companies do frequent bolt-on acquisitions (distribution arms, API platforms, specialty technology tuck-ins). Revenue spikes, PAT anomalies, or sudden goodwill jumps are often M&A artifacts. Guessing the acquisition name or deal size is a credibility hit — verify before writing.
- Call `get_company_context(doc_type='filings')` or `get_events_actions(section='corporate_actions')` to resolve the event
- If still unresolved, list as an open question rather than speculating

### R&D Intensity — Specialty vs Commodity
For specialty chemicals, R&D of 2-4% of sales is healthy and signals a live pipeline of new molecules. R&D intensity declining while revenue stays flat reads as harvesting mode — short-term margin flattery, long-term pipeline risk. Commodity chemicals don't need this intensity; judging them by specialty R&D benchmarks is miscalibrated.
- Pull via `get_fundamentals(section='expense_breakdown')` or `sector_kpis`

### Valuation
The PE band is wide across the sector: specialty names trade 40-60x, commodity 12-20x, and the peer group must match the product mix. EV/EBITDA is generally cleaner than PE because heavy depreciation from capex cycles distorts reported earnings.
- Call `get_valuation(section='band', metric='pe')` and `get_valuation(section='band', metric='ev_ebitda')` for historical context
- Anchor the multiple to the peer set identified in `_shared.md` — a consumer-adjacent specialty chemical doesn't deserve commodity multiples, and vice versa
