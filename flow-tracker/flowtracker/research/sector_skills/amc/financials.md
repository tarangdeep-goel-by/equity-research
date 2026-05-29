## AMC (Asset Management) — Financials Agent

### Business Model Economics
AMCs earn management fees as % of AUM. Revenue = AUM × fee rate. Operating leverage is extreme — costs are mostly fixed (staff, technology, compliance), so AUM growth drops directly to profit.

### Fee Yield Compression — The Structural Risk
- **Yield on AUM** = Operating (core management fee) Revenue / Average AUM — extract from `concall_insights` if available. Use operating revenue, NOT total revenue: total revenue folds in volatile treasury/MTM gains on the AMC's own book and overstates core fee realization. Prefer **QAAUM (Quarterly Average AUM)** over closing AUM as the denominator — AMCs accrue fees on daily AUM, so QAAUM is the accurate base for yields and market share
- Indian AMC yields are compressing due to: the April 2026 SEBI shift from bundled TER to a Base Expense Ratio (BER) plus retained AUM-based telescopic slabs, shift to passive/index funds (lower fee), direct plan growth (lower commission). Assess yield compression through the BER lens and model telescopic-slab pressure as AUM scales
- If yield is falling faster than AUM is growing, revenue growth stalls despite AUM growth. Flag this explicitly
- If yield data unavailable from concalls, flag as open question — this is the single most important metric

### Revenue Quality
- Separate **core management fee income** from **MTM/treasury gains** — Other Income for AMCs often includes gains on own investments
- SEBI mandates seed capital / skin-in-the-game investments in the AMC's own schemes, so Other Income carries structural MTM volatility that swings PAT independent of core-business performance — attribute Other Income moves to seed-capital MTM, not fee momentum
- Use `get_fundamentals(section='cost_structure')` to check Other Income volatility
- Don't extrapolate a quarter with high Other Income — it's likely market-linked

### Operating Leverage
- **Staff cost as % of revenue** — AVAILABLE from `get_fundamentals(section='cost_structure')`
- This should be DECLINING over time if operating leverage is playing out
- If staff cost % is rising, the AMC is hiring faster than AUM is growing — flag as margin risk

### AUM Composition
From `concall_insights`:
- **Equity AUM vs Debt AUM** — equity AUM earns 2-3x the fee rate of debt. Shift toward equity = yield tailwind
- **Active vs Passive AUM** — passive AUM earns minimal fees. Rising passive share compresses yield
- **SIP book** — monthly SIP flows are the most predictable revenue source. SIP book growth rate is a forward indicator

### Valuation
- P/E is the primary metric (predictable earnings). Compare to own history, not banks
- **Mcap as % of AUM** — Indian AMCs typically trade at ~5-15% of *total* AUM (e.g. HDFC AMC ~12-13%), equivalent to ~15-25% of *equity* AUM. Always state which AUM base (total vs equity) you divide by; the two percentages differ sharply
- P/B is meaningless for asset-light AMCs
