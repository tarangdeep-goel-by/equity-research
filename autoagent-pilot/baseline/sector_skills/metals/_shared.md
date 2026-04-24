## Metals/Mining Mode (Auto-Detected)

This company is in the metals, mining, or steel sector. Apply cyclical-sector analysis:

**The Cyclical PE Trap:**
PE is inverted for commodity companies — the lowest PE often marks the cycle peak (earnings temporarily inflated), and the highest PE often marks the trough (earnings temporarily depressed). Using PE in isolation for valuation gives the opposite signal from what you'd expect.

**How to assess cycle position:**
- Compare current EV/EBITDA to the company's 5-year average (available in `get_quality_scores` metals section). If current << average → likely at cycle peak. If current >> average → likely at cycle trough.
- Check commodity price trends relative to marginal cost of production
- Review capacity utilization levels from concall data

**Primary Valuation Metrics:**
- **EV/EBITDA**: primary metric. Compare to 5Y average and global peers
- **P/B at trough**: book value provides floor valuation at cycle bottom
- **Net Debt/EBITDA**: key leverage metric for cyclicals. Compare to company's own 5Y average and cycle position
- **Dividend yield**: relevant for mature miners with low reinvestment needs

**These metrics are misleading in isolation for cyclicals:**
- PE ratio — inverted signal as described above. Only cite PE alongside cycle position context
- PEG ratio — assumes compounding growth, but cyclical growth is mean-reverting, making PEG ratios not meaningful

**Emphasize:** Net Debt/EBITDA trajectory, commodity price sensitivity, capex cycle (expansion vs maintenance), EBITDA margins vs historical range, capacity utilization, and cost curve position.

**Concall KPIs to surface if available:** Production volumes, realization per tonne, cost per tonne, capacity utilization %, expansion capex vs maintenance capex.

### Mandatory — Commodity Trend Backbone

Metals equity price action is a lagging derivative of the underlying commodity. Every metals report from the **sector** and **technical** agents must cite:
- The relevant LME / benchmark commodity spot trend (copper, aluminium, zinc, lead, iron ore 62% Fe, HRC steel, coking coal) for the last 6-12 months, via `get_market_context(section='macro')`. Commodity break of 50-DMA / 200-DMA routinely front-runs equity price action by 3-10 sessions — this is not optional flavour, it is the primary technical input for the sector.
- The marginal-cost-of-production context: is current commodity price above / below the 2nd-quartile cost curve? Above = full cycle pricing; below = imminent supply rationalization.

A metals sector or technical report that does NOT open with the commodity trend is structurally incomplete — peer-relative returns and stock-level indicators are secondary to the commodity.

### EBITDA Cross-Check

For a cyclical, cross-check reported EBITDA against EBITDA-per-tonne (quoted in concall) × production volume. If the recomputation differs by >15%, trust the concall recomputation and flag the divergence (possible one-offs, inventory gains/losses, or stripping-cost capitalization changes).

### Annual Report & Investor Deck — Metals Specifics

**AR high-signal sections:**
- `risk_management` — commodity-hedging policy, open hedge positions, mark-to-market exposure, policy changes YoY (key signal — many Indian metal cos run unhedged positions, increasing or decreasing hedge % is material).
- `notes_to_financials` — impairment tests on mining assets, restoration/rehabilitation provisions, royalty disputes, deferred-tax implications of capacity expansion.
- `mdna` — realization per tonne by product (flat vs long vs alloy), energy-cost pass-through lag, EBITDA/tonne target vs achieved, inventory days trajectory.
- `auditor_report` — going-concern notes on smaller/leveraged players, KAMs on inventory valuation at year-end (spot vs average price).
- `segmental` — geography + product split, captive-power contribution, downstream vs upstream margin.

**Deck high-signal sub_sections:**
- `charts_described` — spot-price chart with realized-price overlay, cost-curve position, capacity-utilisation quarterly trajectory.
- `outlook_and_guidance` — volume guidance, EBITDA/tonne target, capex phasing.

**Cross-year narrative cues:** `capital_allocation_shifts` reveal capex-cycle positioning (expansion vs deleveraging); `narrative_shifts` in hedging language signal policy change worth tracking.
