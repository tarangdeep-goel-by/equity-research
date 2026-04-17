## Auto — Valuation Agent

### Sub-type Routing — Primary Multiple Is Not Always PE
The most common valuation error in auto is defaulting to trailing PE for every sub-type. PE breaks down in three specific situations that together cover most of the sector: (1) a cyclical at peak earnings, (2) a loss-making EV pure-play with no E, (3) a multi-segment conglomerate where sub-type multiples diverge. Route to the correct primary multiple before loading any peer comparable:

| Subtype | Primary multiple | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- |
| **Mature ICE OEM — 4W / 2W / CV (cyclical)** | PE on **mid-cycle** EPS + EV/EBITDA on normalized volume | PE on peak-cycle earnings (over-values); DCF without mid-cycle normalization |
| **OEM — 3W (mature ICE Bajaj/M&M duopoly)** | PE on mid-cycle EPS + EV/EBITDA | PE on peak-cycle; ignoring EV-transition terminal value (EV share already >50%) |
| **OEM — 3W (pure-EV focused)** | EV/EBITDA on normalized margin + EV/Revenue band; cash runway if loss-making | Trailing PE (EV unit economics still scaling); peer-PE vs mature ICE 3W (wrong cohort) |
| **Premium 4W / SOTP-heavy OEM** | SOTP (per-business multiple) + holdco discount | Blended PE on consolidated earnings (blurs sub-business quality) |
| **EV pure-play (loss-making)** | EV/Revenue band + cash runway months | PE (no E); P/B (intangible capex heavy) |
| **EV pure-play (cash-flow positive, early)** | EV/Revenue + P/S + forward PE on disclosed guidance | Trailing PE on first year of positive E (overstates stability) |
| **Auto ancillary — Tier-1 (platform-integrated)** | EV/EBITDA + PE | P/B (asset-light, book understated); EV/Revenue (content-per-vehicle noise) |
| **Auto ancillary — Tier-2 (commodity-linked)** | PE + EV/EBITDA on normalized input costs | PE on a peak-commodity-pass-through quarter |
| **Battery / cell makers (pre-scale)** | EV/Revenue + runway + forward EV/EBITDA on disclosed capacity | Trailing PE (earnings are noise pre-scale) |
| **Aftermarket (tyres / lubricants / batteries)** | PE + EV/EBITDA; brand-premium justified by ROCE | EV/Revenue (misses margin structure) |

### Cycle Normalization — PE on Peak EPS Misleads
A 4W OEM at cycle peak looks "cheap" at 12-15× PE and "expensive" at 25-30× PE at cycle trough — the same business, inverted optics. The correct process: take the 5-7Y volume cycle, compute **mid-cycle volume** (the median of peak-to-trough), apply a **mid-cycle EBITDA margin** (the margin realized at that volume with normalized commodity input), and apply a sub-type-appropriate multiple to the mid-cycle earnings. For a 2W leader, mid-cycle EBITDA margin tends to 13-16%; mass 4W 8-12%; premium 4W 12-17%; CV 9-13% (with tractor segment at the higher end); Tier-1 ancillary 10-18% depending on content-per-vehicle mix. State the cycle phase (early / mid / late / downcycle) and the normalized-earnings inputs before quoting a target multiple.

### Cash Runway Months — Mandatory for Loss-Making EV Players
For EV pure-plays and pre-scale battery/cell makers running negative FCF, the cash runway is not a footnote — it is the primary valuation guard-rail. Compute:

`cash_runway_months = (cash + near-term receipts) ÷ quarterly_cash_burn × 3`

where `quarterly_cash_burn = -operating_cash_flow_quarterly + maintenance_capex_quarterly` (include maintenance capex even if growth capex is deferrable — the plant has to keep running). Name the threshold explicitly:
- **<12 months** — distress; going-concern disclosure watch; equity repricing 30-50% on dilution announcement.
- **12-18 months** — dilution imminent; QIP or strategic investor round likely within 2 quarters; model 15-25% share-count dilution into the price target.
- **18-30 months** — survival runway; time for the unit-economics path to play out; stress test against an adverse scenario (volume 20% below guidance).
- **>30 months** — comfortable; valuation can be driven by EV/Revenue and forward growth rather than by runway.

Route the arithmetic through `calculate` with `cash`, `quarterly_cash_burn`, and `maintenance_capex` as named inputs. Source cash via `get_fundamentals(section='balance_sheet')`; burn via `get_fundamentals(section='cash_flow_quality')` and `concall_insights`.

### P/S or EV/Revenue Band — When PE Is Empty
When trailing PE is not meaningful (loss-making), anchor valuation to the **historical P/S or EV/Revenue band**. Use `get_chart_data(chart_type='price')` for share-price history and divide by revenue per share from `get_fundamentals(section='financial_summary')` to reconstruct the 3-5Y P/S band. State median / trough / peak and where the current multiple sits; caveat regime breaks (pre-listing vs post-listing P/S is not comparable, pre-EV-pivot vs post-EV-pivot P/S is not comparable). For the EV/Revenue peer comparison, cross-check against the disclosed `get_yahoo_peers` set, filtered to sub-type-matched names (EV pure-play is peered against EV pure-plays, not against mature ICE OEMs).

### Dilution Risk Flag — Embed in the Valuation Bridge
When cash runway is <18 months AND ongoing capex is disclosed (e.g., cell-plant ramp, new model platform), the valuation bridge must carry an explicit dilution flag. Model the next raise: expected size (typically 10-20% of current market cap at the runway-exit point), expected pricing (discount 10-15% to then-CMP for a QIP, wider for distressed), resulting share-count lift, and per-share impact on the base-case target. Do not bury this in a footnote — it is a live P/L event with timing risk and should be called out in the valuation verdict.

### SOTP — For Auto Majors with Listed Arms or Complex Structure
For auto majors housing JLR-style overseas luxury businesses, listed tech / R&D services arms, captive NBFCs, battery ventures, or listed financial-services sub-companies, SOTP is often the lever that re-rates the stock. The mechanical error surfaced in prior evals was an "empty SOTP" — the agent cited SOTP as relevant but didn't build it. Enumerate:
1. Call `get_valuation(section='sotp')` for the tool-computed view.
2. For each **listed subsidiary**, take market cap × parent's stake % → per-share contribution.
3. For each **unlisted segment**, apply a sub-type multiple: overseas luxury auto arm at **5-8× EBITDA** (premium brand), captive NBFC at **1.0-2.0× book** (calibrated to ROA), listed IT services arm at its own market cap × stake, battery/cell venture on **EV/Revenue** with explicit runway caveat.
4. Apply a **20-25% holding-company discount** to the aggregate sub-value.
5. Back out implied multiple on the **standalone** auto business — this is what the market is paying for the core OEM franchise.

### Peer-Premium / Discount Decomposition
If the stock trades at a PE premium or discount vs sub-type peer median via `get_peer_sector(section='benchmarks')`, decompose the delta into at most four drivers: (a) **volume-CAGR differential** — 500-800 bps of sustained volume advantage justifies 15-25% premium, (b) **segment-mix premium** — premium-4W earns 2-3× ancillary multiples, so a mix shift toward premium is a multiple driver even at constant EBITDA margin, (c) **export-mix / FX optionality** — >25% export mix with INR-tailwind justifies 10-15% premium, (d) **EV / structural-transition credibility** — a disclosed EV roadmap with funded capex and on-plan volume milestones carries a 10-20% premium. If (a) through (d) together do not account for more than half of the observed premium, the multiple is leaning on re-rating rather than on earnings growth and is vulnerable to mean-reversion.

### Justified PE — Carry g and Payout Through (Sub-type-Calibrated)
For a mature ICE OEM, the Gordon-derived justified PE is `1 ÷ (CoE − g)` adjusted for payout; for a franchise with stable growth: `Justified PE ≈ payout × (1 + g) / (CoE − g)`. Indian auto `g` in nominal terms sits in the 8-12% range (combination of volume growth, realization lift, and segment-mix premium). **Payout ratio varies sharply by sub-type and is as load-bearing as `g`** — do not default to a single payout assumption across sub-types:
- **Tier-1 OEMs (mass 4W / 2W / CV)** — payout **30-50%** (tax-heavy PAT with meaningful dividend distribution; mature franchises return cash).
- **EV pure-plays** — payout **0%** (cash-preservation mandatory; any dividend at sub-scale economics is a red flag).
- **Tier-1 ancillaries** — payout **40-60%** (asset-light, high-ROE, low reinvestment need once platform lock-in is established).

**Always carry `g` AND `payout` through** — three worked lines spanning the sub-type range:
- **Mass 4W OEM at cycle mid**: CoE 13%, g 10%, payout 40% → justified PE ≈ 0.40 × 1.10 / (0.13 − 0.10) = ~15× (vs a 20× market PE would be stretched unless ROE is expanding).
- **EV pure-play (cash-preservation, 0% payout)**: PE formula collapses (numerator → 0 as payout → 0); justified PE is undefined at 0% payout, confirming that for pre-cash-return EV players the primary multiple must be EV/Revenue + cash runway, not PE. Once the company crosses to cash-return phase (typically 2-4 years post-breakeven), re-evaluate with payout 10-20%.
- **Tier-1 ancillary with platform lock-in**: CoE 12%, g 11%, payout 50% → justified PE ≈ 0.50 × 1.11 / (0.12 − 0.11) = ~55× (ceiling case; a market PE of 30-40× IS defensible for best-in-class ancillaries with sticky OEM platforms).

A 1-pp shift in `g` moves the justified multiple by 25-40%; a 10-pp shift in payout moves it by ~20%. Route through `calculate` with `payout`, `CoE`, `g` as named inputs.

### What Fails for Auto — Name These Explicitly
- **DCF on a cyclical ICE OEM without mid-cycle normalization** — terminal value is dominated by the assumed steady-state margin, and using peak-cycle margin inflates TV by 30-60%.
- **P/B for asset-light Tier-1 ancillaries** — book understates the real economic capital (brand, engineering IP, OEM relationships); P/B is structurally low even for high-ROE names.
- **PE for loss-making EV pure-plays** — undefined; use EV/Revenue + cash runway.
- **Trailing PE on a post-commodity-pass-through quarter** — for Tier-2 ancillaries, a quarter where input cost dropped and pricing hadn't re-adjusted yet shows expanded margins that mean-revert within 2 quarters.
- Use instead: mid-cycle EPS for cyclicals; EV/Revenue + runway for EV pure-plays; EV/EBITDA for ancillaries; SOTP for conglomerate structures; and sub-type-specific multiples above.

### Data-shape Fallback for Valuation Inputs
When `get_valuation(section='band')` returns fewer than 20 observations, fall back to `get_chart_data(chart_type='pe')` for deep history and `get_chart_data(chart_type='price')` combined with revenue per share for EV/Revenue reconstruction. For mid-cycle normalization inputs (volume, margin), pull from `get_fundamentals(section='financial_summary')` 5-10Y history and compute the median explicitly; cite the years used for the median. For cash runway inputs, if quarterly cash flow is not cleanly split, fall back to `concall_insights` for management-disclosed quarterly burn.

### Open Questions — Auto Valuation-Specific
- "What cycle phase is the sector in, and is the applied multiple calibrated against mid-cycle earnings or peak-cycle? Show the mid-cycle volume and margin inputs used."
- "For EV pure-plays: what is the current cash runway in months, what is the next capex tranche, and has dilution been embedded into the per-share target?"
- "For SOTP: what multiples were applied to each unlisted subsidiary, and what holdco discount was used? Back out the implied multiple on the standalone auto business."
- "Is the peer PE / EV/EBITDA premium accounted for by volume-CAGR + segment-mix + export-mix + EV-transition credibility, or is there a residual multiple gap vulnerable to mean-reversion?"
- "What `g` was used in the justified-PE calibration, and is it consistent with the company's 5-10Y nominal revenue CAGR?"
