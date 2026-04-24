## AMC (Asset Management) — Financials Agent

### Business Model Economics
AMCs earn management fees as % of AUM. Revenue = AUM × fee rate. Operating leverage is extreme — costs are mostly fixed (staff, technology, compliance), so AUM growth drops directly to profit.

### Fee Yield Compression — The Structural Risk
- **Yield on AUM** = Total Revenue / Average AUM — extract from `concall_insights` if available
- Indian AMC yields are compressing due to: SEBI TER (Total Expense Ratio) reductions, shift to passive/index funds (lower fee), direct plan growth (lower commission)
- If yield is falling faster than AUM is growing, revenue growth stalls despite AUM growth. Flag this explicitly
- If yield data unavailable from concalls, flag as open question — this is the single most important metric

### Revenue Quality
- Separate **core management fee income** from **MTM/treasury gains** — Other Income for AMCs often includes gains on own investments
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
- **Mcap as % of AUM** — Indian AMCs typically trade at 5-10% of equity AUM
- P/B is meaningless for asset-light AMCs
