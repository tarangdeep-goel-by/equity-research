## Real Estate — Valuation Agent

### Sub-type Routing — Primary Multiple Is Not PE
The recurring valuation error in real estate is defaulting to a PE + EV/EBITDA triangle. IndAS 115 revenue recognition creates 2-3Y presales-to-revenue lag that makes trailing PE oscillate between "optically cheap" (handover cluster year) and "optically expensive" (buildout year) without business quality changing. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple | Secondary cross-check | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- | :--- |
| **Residential developer** (DLF, GODREJPROP, OBEROIRLTY, LODHA, PRESTIGE, SOBHA, BRIGADE, KOLTEPATIL, PURVANKARA, SIGNATURE) | **NAV per share** (sum of per-project NPV + land-bank market value − net debt) | EV / Presales, P / Adj-Book | PE (lumpy completions), DCF-FCFE (WC swings), P/B on historical cost land |
| **Commercial / Office REIT** (EMBASSY, MINDSPACE, BIRET) | **NOI / Cap rate** (direct cap) | Distribution yield, P/NAV | PE, EV/EBITDA without cap-rate anchor |
| **Retail-Mall REIT** (NEXUS) | **NOI / Cap rate** (8-10% cap) | Distribution yield, P/NAV | PE on percentage-rent tail in a recovery year |
| **Integrated developer** (PRESTIGE, BRIGADE, DLF) | **SOTP**: residential NAV + leasing NOI/cap + hospitality multiple | P/NAV consolidated | Single-engine multiple — destroys annuity vs transactional signal |
| **Land-bank / township** (ANANTRAJ, ARVSMART) | **NAV per acre × monetisation discount** | P/Adj-Book | PE (pre-monetisation), DCF |
| **Specialty — warehousing / data-centre** (EMBASSY-like specialty, emerging plays) | **NOI / Cap rate** (7-8% warehousing, 9-11% data-centre) | P/FFO, distribution yield | PE on ramp-year earnings |

### NAV per sqft — The Primary Valuation Metric for Developers
For residential and land-bank plays, NAV per share is the institutional primary metric. Build it explicitly:
1. **Land bank** at current market value (₹ per sqft of developable area × developable sqft), NOT historical acquisition cost. Current market value ranges ₹2,000-15,000 psf depending on city and micro-location; source from management disclosure in investor-presentation, or imply from recent peer land-deals in the same micro-market.
2. **Projects under construction** at stage-of-completion NPV — remaining presales × realization per sqft × EBITDA margin, discounted at the developer's CoE.
3. **Completed-unsold inventory** at realizable value (current market ASP less selling costs).
4. **Less net debt** (including capitalized borrowing cost trapped in WIP inventory, as flagged in `financials.md`).
5. **Less RERA-escrow restricted cash** — not available to equity holders for distribution; deduct or state net-of.
6. Divide by diluted shares outstanding.

Apply a **stage-of-development factor** and a **discount for time and execution risk**: land-bank at acquisition stage carries a 30-40% discount to "at-launch" NAV, under-construction at 10-20% discount, completed inventory at 0-5% discount. Route the arithmetic through `calculate` with `land_bank_sqft`, `market_value_psf`, `net_debt`, `rera_escrow`, `shares_out` as named inputs.

### Realization per sqft Is Mandatory Data — Extract, Don't Just Name
Prior eval pattern B flagged this for GODREJPROP: realization-per-sqft was named as the "key operational signal" but never extracted into the report. The valuation desk needs the latest-quarter number with source quarter cited, the 8-quarter trajectory, and the segment-mix split. Sources: `get_company_context(section='concall_insights', sub_section='operational_metrics')`, `get_fundamentals(section='revenue_segments')`, or investor-presentation via `filings`. Without this extracted, the valuation model is building presales × realization on an unknown realization and cannot be stress-tested.

### Presales vs Revenue Lag — Build the Bridge Explicitly
Under IndAS 115 (transfer of control on possession), revenue is recognised at handover. Presales booked in FY+1 become reported revenue in FY+2 or FY+3 depending on construction cadence. Forecast models need both tracks:
- **Presales track**: FY+1 presales = prior-book + new bookings.
- **Revenue track**: FY+1 revenue = handovers from the FY-2 and FY-3 presales cohorts.

A developer with strong FY+1 presales but weak FY+1 revenue is in buildout phase — the PE looks expensive and the model's DCF on current CFO looks weak, but the underlying business is compounding. Inverting this read is a common mistake. Extract construction-stage tables from investor-presentations to build the bridge; cite the source quarter.

### RERA Escrow — Deduct From Net Cash in Valuation
RERA mandates 70% of customer collections sit in project-specific escrow, released only for that project's construction. Headline cash on the balance sheet overstates distributable-to-equity cash. For NAV computation and for any reverse-DCF-implied CoE, deduct the escrow-trapped portion from net-cash (equivalently, use free-cash not total cash as the adjustment). Extract escrow balance from `get_fundamentals(section='balance_sheet_detail')` notes or from project-level filings. A developer with ₹5,000 Cr headline cash of which ₹4,000 Cr is escrowed has only ₹1,000 Cr of equity-deployable cash.

### Cap-Rate Valuation for Commercial / REITs
For lease-income operators use direct capitalisation: `Value = NOI / cap rate`. Current Indian regime:
- **Prime Mumbai / Bengaluru / Hyderabad office**: 6-7% cap.
- **Tier-2 office / suburban**: 7-9% cap.
- **Retail malls**: 8-10% cap (percentage-rent tail adds cap-rate variability).
- **Warehousing**: 7-8% cap (improving as asset class matures).
- **Data-centre**: 9-11% cap (wider range reflecting power-tariff and tenancy risk).

Cap rates are regime-sensitive to 10Y G-sec yield — a 100 bps G-sec rally compresses cap rate 50-75 bps, driving 10-15% NAV uplift; the reverse holds on yield spikes. State the current G-sec anchor and the cap-rate spread over it as the macro link.

### What Fails for Real Estate — Name These Explicitly
- **Simple PE on trailing earnings** — lumpy completions distort; a handover cluster year shows peak EPS, a buildout year shows compressed EPS, neither reflects business quality.
- **DCF on FCFE** — working-capital swings from land acquisition and construction payments produce enormous CFO oscillation; FCFE terminal values are false-precision.
- **P/B on reported book** — land acquired 10 years ago at ₹1,000 psf is carried at cost while current market is ₹10,000 psf; book materially understates economic value. Use P/Adj-Book only with explicit land-revaluation adjustment.
- **EV/EBITDA** — EBITDA is noisy because of revenue-recognition timing and capitalized-interest treatment (capitalized borrowing cost inflates inventory not interest expense, so EBIT and EBITDA are artificially clean).
- **Sector-relative PE without presales normalisation** — peer PE comparisons across developers in different points of the presales-to-revenue bridge produce inverted rankings.

### Forward-Multiple Sanity — Justified P/NAV with `g`
For mature developers, a rough sanity on justified P/NAV is the same Gordon framework used elsewhere, applied to NAV compounding: `Justified P/NAV = (NAV-ROE − g) ÷ (CoE − g)`, where `g` is the sustainable NAV-compounding rate (earnings retention × return on incremental NAV, typically 8-12% for Indian residential developers in the current regime). Worked calibrations at CoE ~13-14%:
- Top premium residential developer: NAV-ROE 18%, CoE 13%, g 11% → justified P/NAV = (18−11)/(13−11) = 3.5× — a 1.5-2× observed P/NAV is a discount, not a premium, if the growth is real.
- Mid-tier developer: NAV-ROE 14%, CoE 13%, g 9% → justified P/NAV = (14−9)/(13−9) = 1.25× — the same 1.5× observed P/NAV is now stretched.
- Land-bank play with slow monetisation: NAV-ROE 10%, CoE 14%, g 6% → justified P/NAV = (10−6)/(14−6) = 0.50× — deep discount warranted.

Always carry `g` through the formula; dropping it to zero understates fair P/NAV by 40-60%. Sensitivity: a 1-pp change in `g` moves justified P/NAV by ~30-50%. Route via `calculate` with `NAV_ROE`, `CoE`, `g` as named inputs; pull CoE from `get_market_context(section='macro')` or the WACC helper.

### Peer Premium / Discount Decomposition
If the stock trades at a P/NAV (or P/Adj-Book) premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose into at most four drivers: (a) **land-bank quality** — Tier-1 metro share, micro-location premium — 20-40% of premium; (b) **brand pricing power** — realization premium vs nearest comparable at launch — 10-20% of premium; (c) **execution history** — on-time-delivery track record — 5-15% of premium; (d) **balance-sheet capacity** — low Net Debt / Equity giving acquisition optionality — 5-15% of premium. If (a) through (d) do not account for the observed premium, the multiple is leaning on cycle re-rating and is vulnerable to mean-reversion.

### SOTP for Integrated Developers
For PRESTIGE, BRIGADE, DLF, and other integrated names, SOTP is the lever that re-rates the stock. The residential NAV, leasing NOI/cap-rate block, hospitality multiple, and retail-mall block each have distinct valuation regimes; a single blended multiple loses the annuity-vs-transactional signal. Steps:
1. Call `get_valuation(section='sotp')` for tool-computed subsidiary / segment value where available.
2. For the leasing block, apply sub-type cap rate (6-9% office, 8-10% retail) to latest disclosed NOI.
3. For the residential block, apply NAV per share as above.
4. For hospitality, apply EV/Room or EV/EBITDA as applicable.
5. Apply a **15-20% holding-company discount** to aggregate segment value if the developer is structured as a holdco with listed subsidiaries; zero discount for pure single-entity operator.
6. Back out the implied residential-only multiple — this is the number the market is paying for the core development engine ex-annuity.

### Data-shape Fallback for Valuation Inputs
When `get_quality_scores(section='realestate')` returns missing realization-per-sqft, presales, or land-bank figures, the extractor did not capture them. Fall back to `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `sub_section='management_commentary')` and pull from the narrative; cite the specific quarter. If the concall is silent, add to Open Questions with the specific input missing and explain that NAV cannot be rigorously computed without (e.g.) current-market land-bank revaluation.

### Open Questions — Real-Estate Valuation-Specific
- "What is the current-market land-bank value per sqft used in the NAV build-up, and how does it reconcile with recent peer land-deal comparables in the same micro-market?"
- "What is the latest quarterly realization per sqft (by segment), and what 8-quarter trajectory supports the valuation model?"
- "How much of the headline cash is RERA-escrow restricted, and what is the equity-deployable cash after that deduction?"
- "For REITs: what cap-rate spread over 10Y G-sec is being applied, and is it consistent with recent primary transactions in the same asset class?"
- "For integrated developers: does SOTP ex-annuity imply a residential-block multiple that is richer or cheaper than pure-play residential peers, and what explains the gap?"
