## FMCG — Valuation Agent

### Sub-type Routing — Primary Multiple by Archetype
FMCG multiples look superficially similar across sub-types but have sharply different trading bands and normalization approaches. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple | Historical trading band | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- | :--- |
| **HPC leader (personal care)** | PE (forward) | 45-60× (10-15Y average) | DCF (terminal-value sensitivity), P/B (asset-light) |
| **Mid-cap HPC / premium personal care** | PE + EV/EBITDA | 25-40× PE, 20-30× EV/EBITDA | Peer PE vs HPC-leader (structurally un-comparable) |
| **Food & beverages** | PE + EV/EBITDA | 20-30× PE, 15-22× EV/EBITDA | P/B (asset-light), DCF on short-cycle commodity businesses |
| **Packaged staples (edible oil, flour)** | EV/EBITDA + PE | 10-18× EV/EBITDA, 15-22× PE | Consumer-PE framework (it's a commodity-spread business) |
| **Tobacco / alcobev** | PE + dividend yield | 18-28× PE, 3-5% yield | EV/EBITDA (tax-gross vs net confusion), P/B |
| **OTC / wellness** | PE + EV/EBITDA | 30-50× PE | Pharma-sector peer PE (OTC brand-economics differ) |
| **D2C / digital-native** | EV/Sales + P/GMV during growth phase | 4-10× EV/Sales; revisit to PE post-profitability | PE (usually loss-making), EV/EBITDA (usually negative) |

### Margin-Normalization (Not Cycle-Normalization) Is the Lever
FMCG is structurally growing, so the Gordon-cyclicality lens used in metals / chemicals does not apply. The correct normalization axis is **margin**, not cycle. Commodity input spikes (palm oil 2022, wheat 2023) compress EBITDA margin 200-400 bps for 2-3 quarters while the company passes prices with a lag; mean-reversion is reliable. The common valuation error is anchoring forward EBITDA margin to the peak-of-commodity-crash trough (understates) or the peak-of-pass-through window (overstates). Use a 3-5Y margin average — but cross-check against current management guidance (see next section).

### Management Guidance Anchoring — The Load-Bearing FMCG Rule
When projecting next-year EBITDA margin or gross margin, **anchor the base case to management's explicit guidance, not the 3Y historical average**. If the concall states "we are guiding to 22-23% EBITDA margin for FY+1" but the 3Y historical average is 24.5%, the base case uses 22-23%. Rationale: FMCG management teams have high-fidelity visibility into input costs (next 1-2 quarter hedges in place), trade-promotion intensity (already-negotiated schemes), and ad-spend plans — their guidance incorporates information the historical average cannot. When the model output contradicts management guidance cited in the same section, management wins; flag the divergence explicitly and state the 3Y-average number as a "if guidance is missed by X pp" sensitivity. Source guidance from `get_company_context(section='concall_insights', sub_section='management_commentary')` and `sub_section='guidance')`. Route the arithmetic through `calculate` with `revenue_fy1`, `ebitda_margin_guided`, and `ebitda_margin_historical_3y_avg` as named inputs so both numbers appear.

### Historical PE Band Context — FMCG Premium to Nifty
A 5-10Y PE band via `get_chart_data(chart_type='pe')` gives the long-arc context. FMCG leaders structurally trade at a 25-40% premium to Nifty PE, justified by earnings visibility, negative-working-capital economics, and defensive-cash-flow profile. The common eval error is citing "trading at 50× PE, expensive vs Nifty at 22×" without the sector-premium context — 50× against a 10Y FMCG-leader median of 52× is closer to fair than stretched. Always report: current PE vs 5Y/10Y sector median vs 5Y/10Y own-stock median. Anchor the band via `get_valuation(section='band', metric='pe')` with `get_chart_data(chart_type='pe')` as the deep-history fallback when the band call returns fewer than 20 quarterly observations.

### Peer Premium / Discount Decomposition
If the stock trades at a PE premium or discount vs FMCG sub-sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into at most four drivers: (a) **volume-growth CAGR delta** — 200-300 bps of sustained volume-CAGR advantage justifies 15-25% PE premium; (b) **ROCE delta** — 500-1000 bps of ROCE advantage justifies 20-30% premium; (c) **brand-equity via ad-spend-to-revenue** — 200-400 bps of sustained ad-intensity advantage points to deeper moat and justifies 10-15% premium; (d) **rural-market reach** — measurable via distribution-outlet count and rural-share-of-revenue. If (a) through (d) together account for less than half of the observed premium, the multiple is vulnerable to mean-reversion and the bull-case is leaning on re-rating rather than on earnings growth. Source peer metrics via `get_peer_sector(section='benchmarks')`; route the decomposition through `calculate` with peer deltas as named inputs.

### SOTP for Conglomerate FMCG
For diversified conglomerates where FMCG is one segment (hotels, paperboards, agri-business, unlisted retail), SOTP is the valuation lever. Enumerate:
1. Call `get_valuation(section='sotp')` for the tool-computed view.
2. For the FMCG segment, apply a sub-type-appropriate EV/EBITDA multiple (15-22× for food / HPC at sector-median quality; 22-30× for HPC leaders).
3. For non-FMCG segments (hotels, paperboards), apply the relevant sector multiple — do not contaminate with the FMCG consumer-premium multiple.
4. Apply a 15-25% holding-company discount to the aggregate value before comparing to the current market cap.
5. Back out the implied FMCG-segment multiple the market is paying — this is the re-rating lever if the non-core is being discounted.

### What Fails for FMCG — Name These Explicitly
- **DCF on short-cycle commodity-input-dependent businesses** — terminal-value sensitivity to the steady-state EBITDA margin (which oscillates ±300 bps across input cycles) makes DCF fair-value estimates spuriously precise. Use it as a cross-check only, not a primary multiple.
- **P/B** — FMCG is asset-light (capex intensity 2-4% of sales); book value is a fraction of market cap and P/B ratios of 15-30× are structural, not informational.
- **EV/EBITDA on tobacco / alcobev** — excise duties distort EBITDA (gross-of-tax reporting inflates the multiple); shift to PE and dividend yield for sin-goods.
- **Simple PE on a commodity-spike year** — FY23 palm oil squeeze collapsed HPC EBITDA 300-400 bps; trailing PE looked optically high that year while normalized PE was 20% lower. Always distinguish trailing PE from normalized-margin PE.
- **D2C PE** — most D2C businesses are loss-making during growth phase; PE is meaningless. Use EV/Sales and path-to-profitability metrics until the business turns profitable.

### Data-shape Fallback for Valuation Inputs
If `get_peer_sector(section='benchmarks')` returns a sparse peer set (<5 comparable FMCG names) or `get_valuation(section='band', metric='pe')` returns fewer than 20 quarterly observations, fall back to `get_chart_data(chart_type='pe')` for the deep-history PE series and `get_market_context(section='macro')` for the top-down rate / inflation context that anchors CoE. If management guidance for next-year margin is missing from `concall_insights`, explicitly label the base case as "historical-average-anchored (guidance unavailable)" and add the guidance gap to Open Questions.

### Open Questions — FMCG Valuation-Specific
- "What is management's explicit guidance on FY+1 EBITDA margin, and does the model's forward-margin assumption match or diverge? If diverging, by how many pp?"
- "What is the current PE vs the 5Y / 10Y sector-median PE and the 5Y / 10Y own-stock-median PE — all three, not just one?"
- "For peer-premium decomposition: do volume-CAGR + ROCE + ad-intensity + rural-reach deltas together account for at least half of the observed multiple gap?"
- "For conglomerates: what implied EV/EBITDA is the market paying for the FMCG segment after stripping out non-core value at appropriate sector multiples?"
- "What commodity input cycle is priced into the current multiple — trough, normalizing, or peak pass-through?"
