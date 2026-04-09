## IT Services — Financials Agent

### Critical IT-Specific KPIs
Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **Constant Currency (CC) revenue growth** — the real growth signal, strips out forex volatility. Reported growth can diverge from CC by 2-5pp depending on USD/INR moves
- **Total Contract Value (TCV)** / deal wins — leading indicator of future revenue. Large deals (>$50M) vs run-rate
- **Book-to-bill ratio** — TCV / trailing revenue. Above 1.0 = growing pipeline
- **Attrition rate** — talent cost pressure indicator. <15% healthy, >20% margin risk

If concall data doesn't contain these, flag as open questions. Do NOT guess CC growth from reported numbers.

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

### Revenue Classification
- Break revenue by **vertical** (BFSI, retail, telecom, manufacturing) and **geography** (Americas, Europe, RoW) if available from concall_insights
- BFSI slowdowns disproportionately hit Indian IT — always flag BFSI revenue share
