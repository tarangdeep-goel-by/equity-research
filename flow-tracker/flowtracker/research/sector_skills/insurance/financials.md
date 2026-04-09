## Insurance / Insurtech — Financials Agent

### Sub-Type Determines the Entire Analysis — Aggregator vs Underwriter
First, determine the sub-type from company profile. These are completely different businesses with different economics, and applying one's metrics to the other produces garbage analysis:
- **Aggregator/Platform** (PB Fintech/Policybazaar, InsuranceDekho): earns commissions on policies sold. Has Take Rate, unit economics, tech-platform P&L. Combined Ratio or VNB don't apply — aggregators don't bear underwriting risk or manufacture policies.
- **Life Insurer** (HDFC Life, SBI Life, ICICI Pru Life): manufactures policies. Has VNB, APE, Embedded Value. Take Rate doesn't apply — insurers set premiums, they don't earn commissions on someone else's product.
- **General Insurer** (ICICI Lombard, Star Health): underwrites risk. Has Combined Ratio, Claims Ratio. Life insurance metrics (VNB, APE, persistency) are structurally different because general insurance policies are annual, not long-duration.

### IF AGGREGATOR (e.g., Policybazaar):
**Take Rate vs Gross Margin — different metrics that answer different questions:**
- **Take Rate** = Revenue / Total Premium Distributed (typically 10-15%). Measures pricing power over insurance partners
- **Gross Margin** = (Revenue - Direct Costs) / Revenue (typically 60-70%). Measures operational efficiency
- Present both separately — conflating them misrepresents both pricing power and efficiency

**Subsidiary drag sizing — quantify, don't just note:**
Aggregators typically run loss-making subsidiaries (lending, direct insurance, new verticals) that obscure the core platform's profitability.
- Compare standalone vs consolidated P&L using `get_quality_scores(section='subsidiary')`
- **Compute the magnitude**: subsidiary loss = consolidated PAT - standalone PAT. Present as ₹ Cr AND as % of consolidated revenue
- Flag which subsidiary is the drag
- Track the trend: is the subsidiary drag narrowing (path to breakeven) or widening?

**Aggregator KPIs from concall_insights:**
- New premium per policy (average ticket size), Renewal rate, LTV/CAC
- Core vs new business mix (insurance mature vs lending investment phase)

### IF LIFE INSURER:
Standard P&L financials are **distorted by actuarial accounting** — reported profits reflect reserve movements, not business performance. Extract from `concall_insights` or `sector_kpis`:
- **VNB (Value of New Business)** — profitability of new policies. Compare VNB Margin against peer median via `get_peer_sector(section='benchmarks')` and the company's own trend
- **APE (Annualized Premium Equivalent)** — standardized new business volume metric
- **Embedded Value (EV)** — present value of in-force book + adjusted net worth
- **Persistency (13th/61st month)** — policy retention. Higher is better — compare against peer median and the company's own trend
- **Valuation**: P/EV is the primary metric for life insurers because it captures the value of the in-force book. If EV unavailable, fall back to P/B with caveat

### IF GENERAL INSURER:
- **Combined Ratio** = Claims Ratio + Expense Ratio. <100% = underwriting profit
  - Break it down: **Claims Ratio** (underwriting quality) vs **Expense Ratio** (efficiency) — they tell different stories
- **Investment income yield** — float deployment quality
- **Solvency ratio** — regulatory minimum 150%. Compare buffer above minimum against peer median
