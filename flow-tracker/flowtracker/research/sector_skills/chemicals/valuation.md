## Chemicals — Valuation Agent

### Sub-type Routing — EV/EBITDA Primary Alongside PE
The most common valuation error in Indian chemicals is a PE-only triangle. Specialty chemicals, CDMO/CRAMS, fluorochem, and agrochem trade on EV/EBITDA because working-capital intensity and multi-year capex cycles distort reported earnings — depreciation steps up discretely as plants commission, and a PE read on the build-year understates cash-earning power while a PE read on the peak-utilization year overstates it. Route to the correct primary multiple by sub-type before loading peer comparables.

| Subtype | Primary multiple | Secondary | Commonly-misapplied multiples |
| :--- | :--- | :--- | :--- |
| **Specialty** | EV/EBITDA | PE | P/B (fixed-asset heavy but moat is molecule IP), DCF on peak margin |
| **CDMO / CRAMS** | EV/EBITDA | P/S (rapid-expansion names) | Trailing PE (lumpy commercial-phase revenue), peer PE vs specialty |
| **Agrochem** | EV/EBITDA | PE | PE on monsoon-normal year extrapolated into drought-risk year |
| **Commodity bulk** | EV/EBITDA | P/B (cycle-trough) | DCF (cycle-impossible), PE on peak-spread year |
| **Fluorochem** | EV/EBITDA | PE + HFO-transition capex premium | PE on HFC-phase-out peak pricing |
| **Pigments / dyes** | EV/EBITDA | PE | Global-peer PE without REACH-registration adjustment |
| **Custom synthesis** | EV/EBITDA | DCF on cash-generative 10Y+ molecule pipeline | PE on single-molecule spike year |

### Historical EV/EBITDA Band — Regime-Shift Caveats
Pull the 5Y historical band via `get_valuation(section='band', metric='ev_ebitda')` with `get_chart_data(chart_type='pe')` as the deep-history fallback when the EV/EBITDA band returns fewer than 20 quarterly observations. Current vs own 5Y median matters more than vs sector median given the dispersion across sub-types. Calibrated ranges:
- **Specialty chemicals** — 18-28× through-cycle EV/EBITDA; premium names anchored on multi-step process IP sit at the upper end.
- **CDMO / CRAMS** — 22-35× given multi-decade innovator-pipeline visibility and low capital turnover.
- **Commodity bulk** — 8-14× depending on cycle phase; trough 6-9×, peak 12-15×.
- **Fluorochem** — 18-30× hybrid band; the Montreal Protocol phase-down overlay adds a regulatory-tailwind premium that is not a permanent re-rate.
- **Agrochem** — 14-22× with a monsoon seasonality discount on drought-risk years.

Regime break: the FY21-23 China+1 boom lifted specialty EV/EBITDA prints 30-40% above the pre-FY20 band. Averaging across the boom window into a "10Y median" produces a misleading anchor. Always state whether the boom period is included in the band median and whether the current multiple is being compared against pre-boom, boom, or post-boom regime.

### Cycle Normalization — Don't Extrapolate Peak Margins
FY22-23 margins are not a valid base. A specialty-chem EBITDA margin of 30% in the boom window normalises to 20-24% through-cycle; applying a specialty PE of 30× on peak-margin earnings delivers ~40-45× on normalised earnings, which is what the re-rating math actually requires. Before applying any multiple:
1. Compute the through-cycle EBITDA margin (5-7Y average, excluding the FY22-23 boom peak if structurally non-repeatable).
2. Apply the primary multiple on **normalised EBITDA**, not trailing reported EBITDA.
3. Report both the trailing-EBITDA multiple and the normalised-EBITDA multiple; the gap between them is the cycle premium embedded in the stock.

Route the arithmetic through `calculate` with `through_cycle_margin`, `normalised_ebitda`, and `target_multiple` as named inputs.

### Peer Premium / Discount Decomposition
If the stock trades at an EV/EBITDA premium or discount vs sector median via `get_peer_sector(section='benchmarks')`, decompose the delta into at most five drivers:
- **Mix shift to specialty** — incremental specialty share of revenue vs peer; 10-15pp specialty-mix advantage justifies a 20-30% premium.
- **Molecule-tier diversification** — breadth of niche/scale/bulk mix reduces single-molecule earnings volatility and supports a 10-15% premium.
- **Customer-diversification index** — top-5-customer share <40% supports a premium; >60% discounts the multiple for single-event risk.
- **Export share** — a 50%+ export mix with multi-continent spread earns a currency-diversification and demand-diversification premium.
- **Gross-margin differential** — sustained 400-800 bps gross-margin advantage is the empirical test of process-IP moat; if the peer gap compresses, the premium is at risk of mean-reversion.

If the four-to-five drivers together do not account for more than half of the observed premium, the multiple is vulnerable to mean-reversion.

### FAT (Fixed Asset Turnover) Ceiling — The Archetype Sanity Check
Real specialty chemicals peak at **Fixed Asset Turnover (FAT) of ~1.2-1.8×** (Revenue / Gross Block). Commodity runs >2×. CRAMS runs 1.0-1.5× given higher capital intensity. A name claiming specialty margins with FAT >2.5× is either asset-light formulation (a different archetype deserving a different peer set) or mis-classified — apply peer multiples accordingly, not by headline margin.
- Compute FAT via `calculate` on data from `get_fundamentals(section='ratios')` or `balance_sheet_detail`.
- Benchmark against peers via `get_peer_sector(section='benchmarks')`.
- **ZLD / ESG-compliance capex caveat** — mandated zero-liquid-discharge, effluent upgrade, and carbon-reduction capex inflates gross block without adding revenue capacity, mechanically lowering the peak FAT ceiling for compliant players vs their own pre-2020 historical bands. A 10-20% FAT compression from this source is structural, not a mix-degradation signal.

### What Fails for Chemicals — Name These Explicitly
- **Simple PE without EV/EBITDA triangulation** — mis-signals during capex-build and ramp phases; depreciation step-ups distort earnings.
- **DCF on commodity bulk** — cycle-sensitive free cash flow produces false-precision terminal values; use P/B at cycle troughs instead.
- **P/B** for asset-heavy specialty — the productive asset is the molecule IP and process know-how, not the fixed asset base; P/B under-prices the franchise.
- **Peer PE without mix adjustment** — a consumer-adjacent specialty (adhesives, paints-adjacent) cannot be compared to a commodity chlor-alkali name on headline PE.
- **Peak-margin DCF** — discounting FY22-23 peak margins to perpetuity double-counts the boom cycle in the terminal value.

### Data-shape Fallback for EV/EBITDA Band
If `get_fair_value_analysis(section='dcf')` is empty (common for FMP Indian coverage across mid-cap specialty), use reverse-DCF on normalised EBITDA and state the assumed `g` and WACC. If `get_valuation(section='band', metric='ev_ebitda')` returns a narrow 2-3Y band, call `get_chart_data(chart_type='pe')` for the deeper history and reconstruct the EV/EBITDA path from EV and EBITDA series where available; flag the reconstruction.

### Gordon-Style Growth — Carry `g` Through
For any justified-multiple or reverse-DCF math, the Gordon framework requires an explicit `g` assumption. Realistic sustainable `g` for Indian chemicals sits in the 8-12% range nominal (retention × incremental ROCE gives the steady-state). Dropping `g` to zero when computing `Justified EV/EBITDA = (1 − reinvestment rate) ÷ (WACC − g)` mechanically under-estimates the multiple by 30-50%. State `g` explicitly and carry it through; sensitivity of 1pp on `g` moves the justified multiple materially, so the growth assumption is as load-bearing as the WACC input.

### Open Questions — Chemicals Valuation-Specific
- "What through-cycle EBITDA margin was used to normalise the multiple, and does it exclude the FY22-23 China+1 boom peak?"
- "Does the current EV/EBITDA premium to sector median reconcile with the mix + diversification + gross-margin decomposition, or is there a residual multiple gap?"
- "If FAT is materially above the specialty range, is the peer set the right archetype, or should a formulation / consumer-adjacent peer set apply?"
- "For CRAMS: how was the commercial-vs-development phase revenue split reflected in the multiple, and what discount was applied to development-phase contribution?"
- "Is the trailing PE distorted by forex other-income, capex-commissioning depreciation step-ups, or one-off M&A inclusions that should be normalised before peer comparisons?"
