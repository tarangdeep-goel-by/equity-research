## IT Services — Financials Agent

### Critical IT-Specific KPIs
Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **Constant Currency (CC) revenue growth** — the real growth signal, strips out forex volatility. Reported growth can diverge from CC by 2-5pp depending on USD/INR moves
- **Total Contract Value (TCV)** / deal wins — leading indicator of future revenue. Large deals (>$50M) vs run-rate
- **Book-to-bill ratio** — TCV / trailing revenue. Above 1.0 = growing pipeline
- **Attrition rate** — talent cost pressure indicator. Compare against peer median and the company's own trend

If concall data doesn't contain these, flag as open questions. Guessing CC growth from reported numbers produces unreliable estimates because FX impact can be 2-5pp in either direction.

### TCV vs ACV vs Net-New Deal Wins — TCV Alone Is Gamed
Headline TCV is an easily manipulated number: vendors stretch deal tenure (a 5-year renewal booked as one $500M TCV inflates the quarter) and blend renewals with net-new wins. Institutional analysis requires the decomposition:
- **ACV (Annualized Contract Value)** — TCV / deal tenure. This is the real incremental run-rate signal; a vendor whose ACV is flat while TCV grows is just winning longer-duration contracts, not gaining share
- **Net-new TCV vs renewal TCV** — renewals carry lower margins (price concessions at renegotiation) and do not expand addressable revenue. A book-to-bill > 1.0 driven entirely by renewals is not growth
- Extract both from `concall_insights` if management discloses; otherwise flag as open question. Do not quote TCV in isolation without naming which slice it refers to.

### Client Concentration & Account Bucket Migration
Top-client dependence determines the durability of growth and the discount a mid-cap vendor trades at:
- **Top-5 / Top-10 client revenue share** — flag when Top-5 share > 40% (single-event risk on any renewal / insourcing decision)
- **Account bucket migration** — disclosed via concall as the number of $1M / $5M / $20M / $50M / $100M+ clients. Net upward migration (more clients crossing the $50M threshold QoQ) is the cleanest proof of account mining execution; stalled migration means growth is coming only from new logos
- Extract via `get_company_context(section='concall_insights')`. Compare migration trends to peers via `get_peer_sector(section='benchmarks')`

### Margin-Lever Headroom — Where The Next 100bps Comes From
Margins can expand only to the extent there is headroom on the four structural levers. Institutional analysis requires checking whether the levers are exhausted:
- **Utilization rate** — headroom above current vs the 82-86% sweet spot. At 88%+ the lever is tapped out and any wage-hike hit will flow straight to EBITDA
- **Offshore mix %** — headroom above current vs the 75-82% typical ceiling. A vendor already at 82% has no onshore-to-offshore shift left to run
- **Pyramid ratio** (junior/mid/senior mix) — younger pyramid = cheaper bench but higher attrition risk
- **Subcontractor %** — rising subcon % is a negative lead indicator on margin even before it shows up in cost structure
- Compare each lever against peer medians via `get_peer_sector(section='benchmarks')` — a vendor at 88%/82% has run out of runway; a peer at 81%/78% has 200+ bps of self-help margin

### Earnings Quality Checks
- **DSO (Days Sales Outstanding)**: AVAILABLE from `get_quality_scores(section='sector_health')` — returns `dso_days`, `dso_trend`, `dso_yoy_change`. Rising DSO while revenue slows = aggressive revenue recognition / unbilled revenue buildup. Flag if DSO increases >5 days YoY
- **FCF / PAT conversion**: AVAILABLE from `get_quality_scores(section='capex_cycle')` — returns `fcf_pat_ratio`. Indian IT should convert >80% of PAT to FCF. If below 70%, flag as earnings quality concern

### Margin Drivers
For IT services, margin moves are driven by:
1. **Utilization rate** (billable / total employees) — the biggest lever. 82-86% sweet spot
2. **Onshore/offshore mix** — every 1% shift to offshore improves margin ~30-50bps
3. **Subcontracting costs** — rises when demand > capacity (positive short-term, margin pressure)
4. **Wage hikes** — typically Q1 (Apr-Jun) impact, seasonal margin dip
5. **Currency tailwinds/headwinds** — explain cross-currency impact

Use `get_fundamentals(section='cost_structure')` to identify employee cost trends and subcontracting costs.

### FX Impact & Receivables
- If >30% of revenue is from exports (always true for IT), analyze currency translation impact on margins. Check Other Income for FX gains/losses and hedging gains
- Track receivables/unbilled revenue as % of revenue — rising ratio = revenue recognition risk
- DSO >90 days or receivables >20% of revenue needs ageing context

### Revenue Classification
- Break revenue by **vertical** (BFSI, retail, telecom, manufacturing) and **geography** (Americas, Europe, RoW) if available from concall_insights
- BFSI slowdowns disproportionately hit Indian IT — always flag BFSI revenue share
