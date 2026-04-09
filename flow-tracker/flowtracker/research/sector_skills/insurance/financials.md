## Insurance / Insurtech — Financials Agent

### Sub-Type: Aggregator vs Manufacturer
Detect from company profile whether this is an **aggregator/marketplace** (PB Fintech, InsuranceDekho) or an **insurance manufacturer** (HDFC Life, ICICI Lombard). Their P&Ls are completely different — do NOT mix frameworks.

### IF AGGREGATOR (e.g., Policybazaar):
**Take Rate vs Gross Margin — DIFFERENT metrics, never conflate:**
- **Take Rate** = Revenue / Total Premium Distributed (typically 10-15%). Measures pricing power
- **Gross Margin** = (Revenue - Direct Costs) / Revenue (typically 60-70%). Measures efficiency
- Present both separately

**Subsidiary drag sizing (CRITICAL):**
- Compare standalone vs consolidated P&L using `get_quality_scores(section='subsidiary')`
- Estimate: if standalone profitable but consolidated not, subsidiary loss = consolidated PAT - standalone PAT
- Flag which subsidiary (lending arm, direct insurance, new verticals) is the drag

**Aggregator KPIs from concall_insights:**
- New premium per policy (average ticket size), Renewal rate, LTV/CAC
- Core vs new business mix (insurance mature vs lending investment phase)

### IF LIFE INSURER:
Standard P&L financials are **distorted by actuarial accounting**. Extract from `concall_insights` or `sector_kpis`:
- **VNB (Value of New Business)** — profitability of new policies. VNB Margin >25% excellent
- **APE (Annualized Premium Equivalent)** — standardized new business volume metric
- **Embedded Value (EV)** — present value of in-force book + adjusted net worth
- **Persistency (13th/61st month)** — policy retention. 13M >85% good, 61M >50% good
- **Valuation**: P/EV is PRIMARY for life insurers. If EV unavailable, fall back to P/B with caveat

### IF GENERAL INSURER:
- **Combined Ratio** = Claims Ratio + Expense Ratio. <100% = underwriting profit
  - Break it down: **Claims Ratio** (underwriting quality) vs **Expense Ratio** (efficiency) — they tell different stories
- **Investment income yield** — float deployment quality
- **Solvency ratio** — regulatory minimum 150%, comfortable 180%+
