## Pharma — Valuation Agent

### Sub-type Routing — Primary Multiple By Business Model
Pharma valuation fails when a "PE + EV/EBITDA triangle" is applied uniformly across sub-types whose cash-generation profiles and growth-runways diverge sharply. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple range | Secondary / validation | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- | :--- |
| **India-branded formulations** | PE 30-40× on forward earnings | EV/EBITDA 18-25×, FCF Yield 3-4% | DCF (branded cash flows are stable — DCF works but is over-engineering) |
| **US-generics-heavy** | PE 18-25× on normalised earnings | EV/EBITDA 12-15×, FCF Yield 5-7% | DCF on US generics (price-erosion tail hard to model), P/B (asset-light for formulators) |
| **Specialty (complex generics + innovative)** | PE 35-50× on forward earnings | EV/EBITDA 22-32×, Sum-of-molecule rNPV | Simple peer PE (pipeline optionality mis-priced), EV/EBITDA on pre-peak molecule |
| **CDMO / CMO** | PE 30-45× on forward earnings | EV/EBITDA 18-25×, EV/Revenue 4-7× | P/B (asset-heavy but capacity utilisation matters more), EV/EBITDA on under-utilised plant |
| **API / bulk drugs** | PE 20-30× on through-cycle earnings | EV/EBITDA 10-15× | PE on peak-spread year (KSM-price-driven spread volatility) |
| **Animal health** | PE 35-50× on forward earnings | EV/EBITDA 22-30× | PE on innovator-pharma benchmarks (animal-health has distinct demand profile) |
| **Consumer health / OTC** | PE 45-65× on forward earnings | EV/EBITDA 28-40× | Generics PE (misses brand-consumer multiple expansion) |

### FCF Yield — Mandatory for Pharma (Cash Generation Is the Quality Signal)
Pharma cash-conversion is the decisive quality signal because reported earnings carry R&D capitalisation judgments, GTN accrual estimates, and one-off launch profits that flatter accrual-basis metrics. **Compute FCF Yield = Free Cash Flow / Market Cap for every pharma valuation; it is not optional.** Draw FCF from `get_fundamentals(section='cash_flow')` using `CFO − capex` (or `CFO − capex − working-capital build`, if the company disclosed materially rising receivables on US launches). Route through `calculate` with `cfo`, `capex`, and `market_cap` as named inputs.

Interpretation bands:
- **FCF Yield 3-5%** — mature India-branded franchise or stable US generics at normalised margin; consistent with ~10-12% earnings growth priced at 30-35× PE.
- **FCF Yield <2%** — either the market is pricing in accelerated growth (specialty ramp, CDMO commercial-project inflection) or the earnings are inflated by non-cash items (R&D capitalisation, GTN accrual release). Dig for which.
- **FCF Yield >6%** — pricing in decline (base-book erosion, patent-cliff on specialty, idle-plant drag) or genuine undervaluation. Cross-check against ANDA pipeline and inspection status before calling it undervalued.

FCF Yield is especially load-bearing for US-generics-heavy names where accrual-basis earnings can overstate sustainable cash generation by 15-25% in a launch year; the validation check is "does the FCF Yield confirm the PE-implied growth, or does it contradict?"

### ETR-Normalized PE — The Hidden Peer-Comp Distortion
Effective Tax Rates (ETR) in Indian pharma vary 15-30% across segments due to SEZ units, IP-holding structures in tax-favourable jurisdictions, and R&D tax credits. A US-generics-heavy name with 18% ETR (SEZ / IP-holding benefit) trades at a lower headline PE than an India-branded peer with 25% ETR — but **the apparent discount is tax-geography, not business quality**. Before peer PE comparison, normalise ETR to 25% (India statutory base for apples-to-apples) using:

`Normalised PAT = PBT × (1 − 0.25)`
`Normalised PE = Market Cap / Normalised PAT`

Worked illustration: a US-generics player reporting PAT of 900 on PBT of 1,100 (ETR 18%) at market cap 25,000 trades at headline PE of 27.8×. Normalised PAT at 25% ETR = 1,100 × 0.75 = 825; normalised PE = 25,000 / 825 = 30.3×. The 2.5-turn "discount" to an India-branded peer at 31× evaporates. The apparent valuation gap was purely tax-structure, not business-quality. Route through `calculate` with `pbt`, `normalised_tax_rate = 0.25`, and `market_cap` as named inputs. Cross-reference ETR trajectory from `get_fundamentals(section='income_statement')` over 4-8 quarters — a rising ETR (SEZ benefits expiring, transfer-pricing challenges) is a forward-earnings headwind that should be explicitly modelled.

### Segment SOTP — Mandatory for Multi-Segment Players, With Explicit Margin Assumption Per Segment
For any pharma with US generics + India branded + specialty + CDMO + API mix, a consolidated PE or EV/EBITDA hides segment-mix-driven multiple distortion. **Build a segment SOTP with explicit margin assumption per segment, state the assumption, derive implied segment PAT, apply segment multiple, aggregate, and reconcile to consolidated EBITDA.** Skipping this (the "US Specialty margin not shown" failure mode flagged in prior valuation evals on SUNPHARMA) produces a report that cites SOTP relevance without building it.

Segment margin bands for the assumption stack:
- **US generics** — 5-20% EBITDA margin (trough-to-peak); apply 12-15× EV/EBITDA.
- **India-branded formulations** — 25-35% EBITDA margin; apply 18-25× EV/EBITDA.
- **Specialty (complex generics + innovative)** — 30-45% EBITDA margin; apply 22-32× EV/EBITDA.
- **CDMO / CMO** — 18-28% EBITDA margin; apply 18-25× EV/EBITDA.
- **API / bulk drugs** — 18-25% EBITDA margin; apply 10-15× EV/EBITDA.

Process:
1. Call `get_fundamentals(section='revenue_segments')` for segment revenue. If sparse, fall back to `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed segment mix.
2. For each segment, state the margin assumption explicitly ("US Specialty EBITDA margin assumed at 35%, mid-band"). Compute segment EBITDA = segment revenue × segment margin.
3. Apply segment multiple. Sum to EV.
4. Reconcile: the sum of segment EBITDA must reconcile to consolidated EBITDA within ±5%; if the reconciliation gap is larger, the segment margin assumptions or segment revenue disclosure are inconsistent — flag and adjust.
5. Derive implied segment value-per-share contribution for the report table.
6. Compare segment-SOTP EV to current EV; the gap is either an SOTP unlock narrative or a signal that the consolidated multiple already bakes in the segment premium.

Worked pattern — SUNPHARMA-style multi-segment: US Specialty revenue 8,000 at 35% EBITDA margin → 2,800; apply 25× → ₹70,000 Cr. India-branded 12,000 at 28% → 3,360; apply 22× → ₹74,000 Cr. US Generics 14,000 at 15% → 2,100; apply 13× → ₹27,300 Cr. API 4,000 at 20% → 800; apply 12× → ₹9,600 Cr. Total EV ~₹180,900 Cr; reconcile consolidated EBITDA 9,000 vs sum-of-segments 9,060 (within 1% — consistent). The specialty segment alone contributes ~39% of EV despite ~21% of revenue — this is the re-rating narrative that gets lost in a consolidated 22× EV/EBITDA print.

### FDA-Pipeline-Conditional Bull Case
Beyond the base business valuation, pharma carries an optionality layer from the ANDA / 505(b)(2) / NDA filing pipeline that materialises only on approval. The bull case must be stated conditionally with the assumption stack explicit:

`Bull-case pipeline NPV = Σ (expected launch value × probability-of-approval × probability-of-launch-competitiveness) discounted at sector CoE`

Components to specify:
- **ANDA / 505(b)(2) filings pending** — extract from `get_company_context(section='concall_insights', sub_section='operational_metrics')`; typical filing-to-approval timeline 18-36 months (ANDA) / 24-48 months (505(b)(2)).
- **Expected peak sales per launch** — tied to the molecule's US market size × expected share × post-launch price. For a typical first-to-file with 180-day exclusivity, Yr-1 revenue can hit 30-50% of innovator peak sales; post-exclusivity, it steps down to 10-20%.
- **US-competitor exclusivity expiry calendar** — track the innovator patent / Orange Book exclusivity expiry dates for named molecules (gRevlimid, gTasigna, complex injectables, specialty inhalers). A competitor's exclusivity loss is the pharma bull-case trigger.
- **Probability-of-approval** — first-cycle approval rate in FY24-25 is ~35-45% for standard ANDA, higher for paragraph-IV first-to-file (Orange Book challenged); specialty 505(b)(2) is 25-35%.
- **Probability-of-launch-competitiveness** — 5-8 competitors on approval day for a non-complex molecule collapses pricing 60-80% in the first 2 quarters; complex generics and 505(b)(2) with limited competition hold 40-60% of innovator price.

State the bull-case multiplier (e.g., "pipeline NPV adds ₹8,500 Cr to base-case EV, a 12% uplift; dependent on 4 specific gAstaZeneca-style launches in the next 18 months") rather than a diffuse "pipeline potential" framing.

### Historical Band Context — Regime-Shift Caveats
A 5-10Y PE band via `get_valuation(section='band', metric='pe')` with `get_chart_data(chart_type='pe')` as deep-history fallback gives long-arc context (current vs median vs trough-peak). The band has regime breaks:
- **Post-2017 US generics trough** — the FY17-FY20 US price-erosion cycle compressed sector PE from 25-30× to 15-20×; pre-2017 medians are not directly comparable.
- **Post-COVID specialty re-rating** — FY21-23 saw specialty names (SUNPHARMA's Ilumya ramp, DRREDDY's biosimilars) re-rate from 22-25× to 30-40× as the specialty revenue share crossed 20% threshold; the pre-specialty-share-expansion median understates.
- **2023-25 CDMO / API re-rating** — PLI-scheme announcement, China+1 tailwind, and biologics CDMO wave re-rated DIVISLAB / LAURUSLABS / SYNGENE from 25-35× to 35-50×; averaging across the pre-PLI and post-PLI series produces a misleading median.

Always state the regime break when citing "current vs 10Y median PE" — a SUNPHARMA PE of 30× is "at 10Y median" on a blended series but "top-quartile" post-2020 specialty re-rating regime.

### Peer Premium / Discount Decomposition
If the stock trades at a PE premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into at most six drivers with justified `g`:
- **US / India revenue mix** — each 10 pp of US Specialty share justifies 2-3 turns of PE premium; each 10 pp of US generics share justifies a 1-2 turn discount (erosion risk).
- **Segment mix (specialty / CDMO / API share)** — specialty-share >25% justifies 5-8 turns of premium; CDMO-share >30% justifies 3-5 turns.
- **ETR-normalized PE delta** — state before vs after ETR normalisation; the apparent gap often collapses 30-60% once taxed at 25%.
- **R&D productivity (ANDA approvals per ₹ Cr of R&D)** — a name approving 12-15 ANDAs per ₹100 Cr R&D vs peer median 6-8 justifies 2-4 turns of premium.
- **USFDA plant compliance status** — all plants clean-inspection vs peer with an OAI or warning letter justifies 3-5 turns of premium (risk-asymmetry).
- **Growth runway `g`** — sustainable earnings growth; pharma `g` typically 10-15% nominal for branded-formulations-heavy names, 8-12% for US-generics-heavy, 15-20% for specialty-heavy CDMO-leverage names. Apply the Gordon framework sanity-check: `Justified PE ≈ (1 + g) / (CoE − g)` for a no-growth-reinvestment benchmark, or the more rigorous `Justified PE ≈ (payout × (1+g)) / (CoE − g)` for steady-state payers. A specialty name at ROE 18%, CoE 12%, `g` 15%, payout 30% carries justified forward PE of ~35× at these inputs; dropping `g` to 10% collapses it to ~19×, so the growth assumption is as load-bearing as the ROE / CoE inputs. Carry `g` through the formula explicitly — dropping it to zero is the Phase-1 BFSI lesson that applies equally here.

If drivers (a) through (f) together do not account for more than half the observed premium, the multiple is vulnerable to mean-reversion and the bull-case is leaning on re-rating rather than on earnings growth.

### What Fails for Pharma — Name These Explicitly
- **EV/EBITDA on a single-segment multi-geography player** — the segment-mix hides the multiple; US generics EBITDA and India branded EBITDA fold into a blended 22-24× that misrepresents both segments. Use segment SOTP instead.
- **DCF on US generics** — the price-erosion tail (5-8% annual, 10-15Y compounding) is hard to model; small assumption changes on terminal erosion rate produce 30-50% fair-value swings. The model produces false precision.
- **P/B on asset-light generics formulators** — book mostly captures receivables and intangibles from M&A, not operating-asset value; P/B fluctuates with goodwill cycles, not business quality.
- **PE on peak-launch-year earnings** — a US launch year can add 20-30% to EPS that base-book erosion unwinds over the following 2-3 years; trailing PE is optically attractive at the peak. Normalise to through-cycle earnings before peer PE comparison.
- **PE on pre-peak specialty molecule** — a specialty ramp in Yr 1-2 has 30-40% of steady-state revenue and 40-60% of steady-state margin; trailing PE looks expensive while forward PE on Yr-4 earnings is reasonable. Use forward PE on steady-state.
- **EV/Revenue for CDMO on under-utilised capacity** — an EV/Revenue of 5× with 55% utilisation misrepresents the 8× at 80% utilisation that the same asset would command; normalise utilisation before comparison.

### Data-shape Fallback for Segment and Pipeline
When `get_fundamentals(section='revenue_segments')` returns aggregate-only and `get_sector_kpis` returns `schema_valid_but_unavailable` for segment mix, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed segment revenue and margin; (2) `get_company_context(section='filings')` for 20-F / 10-K-equivalent disclosures that carry US pharma segment granularity; (3) `get_company_context(section='concall_insights', sub_section='management_commentary')` for qualitative mix commentary. Cite the quarter. If all three degrade, add to Open Questions with the specific segment name and state that segment SOTP cannot be computed rigorously — do not back-solve segment margins from consolidated, that is circular.

### Open Questions — Pharma Valuation-Specific
- "What ETR was used for the trailing PE computation, and after normalisation to 25% India statutory rate, does the apparent peer discount persist?"
- "For segment SOTP: what margin was assumed for US Specialty, India branded, US generics, CDMO, and API respectively? Does the sum-of-segment EBITDA reconcile to consolidated within ±5%?"
- "What is the FCF Yield (CFO − capex) / Market Cap, and does it confirm or contradict the PE-implied growth rate?"
- "For pipeline-conditional bull case: which specific ANDA / 505(b)(2) / NDA filings underpin the uplift, and what are the expected approval timelines, launch prices, and competitor-exclusivity calendars?"
- "What `g` was used in the justified PE / P/B framework, and at ±2 pp sensitivity on `g`, what is the multiple range?"
- "Is the trailing PE distorted by a US launch-year earnings peak, a specialty pre-peak margin ramp, or a one-off FX or divestment gain that should be normalised before peer comparison?"
