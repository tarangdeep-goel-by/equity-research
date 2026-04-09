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
