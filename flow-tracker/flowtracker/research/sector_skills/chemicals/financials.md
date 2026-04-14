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

### Molecule / Client Concentration in CSM & Specialty Books
Contract-manufacturing (CSM) and CDMO-style specialty chemicals often report healthy margins that ride on 1-2 innovator molecules or 1-3 global innovator clients. When a patent cliff hits, a molecule de-stocks, or a client insources — the entire margin profile craters regardless of the company's moat narrative.
- Extract **top molecule / top client revenue share** from `get_company_context(section='concall_insights')` — management occasionally discloses; filings sometimes carry it
- Benchmarks: top-1 molecule > 25% of segment revenue is high concentration; top-3 clients > 50% of CSM revenue is a single-event-risk book
- Combine this with commercial-scale vs development-phase revenue split — a specialty book that looks diversified by client count but is 40% loaded on one Phase-III molecule that may not commercialize is not diversified
- Flag explicitly; the margin narrative is meaningless without the concentration context

### Fixed Asset Turnover Peak Ceiling — The "Specialty" Sanity Check
Real complex synthesis — multi-step specialty molecules, regulatory-approved intermediates, exotic materials — peaks at **Fixed Asset Turnover (FAT) of 1.5-2.0x** (Revenue / Gross Block). FAT materially above 3x is a strong signal that the business is not truly specialty — it's low-capital-intensity blending, formulation, or trading masquerading as specialty. The market eventually re-rates these to commodity multiples once the misclassification is spotted.
- Compute FAT = Revenue / Gross Block via `calculate` using data from `get_fundamentals(section='ratios')` or `balance_sheet_detail`
- Benchmark against peers via `get_peer_sector(section='benchmarks')` — the **peer FAT range** anchors the correct archetype
- If reported margins are specialty-range (EBITDA 20-30%) but FAT is commodity-range (>3x), this is either (a) genuinely asset-light formulation that deserves a distinct peer group, or (b) a product-mix misclassification. Either way, flag it — don't apply specialty-peer multiples on commodity FAT

### Peer Capacity Overhang — Model the Industry, Not Just the Company
Chemicals capex is visible 18-24 months in advance because plants of this scale can't be hidden. Modeling 20-25% ROCE on new capacity is fatal when 3-4 peers commission identical capacity in the same quarter — the guaranteed result is a price war that compresses gross margins for 3-5 years.
- Extract **industry-wide capacity additions** across peers via `get_peer_sector(section='benchmarks')` and `get_company_context(section='concall_insights')` for each major peer
- Flag whenever a company's own capacity additions coincide with 2+ peers commissioning comparable capacity in the same 12-month window — utilization ramp assumptions must be haircut in this case
- Historically, sub-sector cycles of this kind (fluorochem, bromine derivatives, certain agrochem actives) have destroyed 40-60% of peak EBITDA when peer capacity floods the market — the company's ROCE modeling is only as good as the peer-supply side of the equation
