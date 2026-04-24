## Insurance / Insurtech — Financials Agent

### Sub-Type Determines the Entire Analysis — Aggregator vs Underwriter
First, determine the sub-type from company profile. These are completely different businesses with different economics, and applying one's metrics to the other produces garbage analysis:
- **Aggregator / Insurtech platform**: earns commissions on policies sold on behalf of underwriters. Has Take Rate, unit economics, tech-platform P&L. Combined Ratio or VNB don't apply — aggregators don't bear underwriting risk or manufacture policies.
- **Life Insurer**: manufactures long-duration policies. Has VNB, APE, Embedded Value. Take Rate doesn't apply — insurers set premiums, they don't earn commissions on someone else's product.
- **General Insurer** (includes standalone health): underwrites risk on annual policies. Has Combined Ratio, Claims Ratio. Life insurance metrics (VNB, APE, persistency) are structurally different because general insurance policies are annual, not long-duration.

### IF AGGREGATOR:
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

### Product Mix Drives VNB (Life Insurers) / Combined Ratio (General)
For life insurers, headline VNB growth is entirely mix-driven. Product categories have radically different margin profiles:
- **Non-Par / Guaranteed-Return / Protection (term)**: 60-90% VNB margins — highest-value mix
- **Participating (Par)**: 15-25% VNB margins — mid-tier
- **ULIP (market-linked)**: 10-18% VNB margins, equity-market sensitive, lower quality
- A life insurer growing premium strongly in ULIPs while VNB margin compresses is reporting vanity growth. Mix trajectory (Protection / Non-Par share %, QoQ) is the real forward signal
- Extract product-mix % from `get_company_context(section='concall_insights')` or `sector_kpis`

For general insurers, the blended Combined Ratio masks toxic segments. Motor Third-Party (regulated tariff) routinely runs 130%+ combined (pure loss), Retail Health runs 90-95% (profitable), Group Health runs 100-110% (loss-leader for cross-sell). A CR improvement that is mix-driven (pulling back from Motor TP) is different from one that is pricing/claims-driven — only the latter compounds.
- Extract segment-wise CR from `get_company_context(section='concall_insights', sub_section='financial_metrics')` and call out mix vs claims-driven moves separately

### Distribution Channel Mix — Banca vs Agency vs Direct vs Broker
Distribution channel mix determines both cost structure and counterparty risk. Each channel has different implications:
- **Bancassurance** — low-cost, high-volume; but parent-bank renegotiation risk. Bank-sponsored insurers carry renewal risk on the distribution agreement itself
- **Agency (tied agents)** — higher-cost (commissions 20-35%), better persistency control, slower growth
- **Direct (digital + own branches)** — cheapest at scale, but requires tech and customer-acquisition investment in build years
- **Third-party brokers / corporate agents** — flexible, but thinner margins and lower persistency
- Extract channel mix % from `get_company_context(section='sector_kpis')` or concall — track trajectory. Heavy banca reliance is a structural vulnerability even when near-term VNB margin is strong

### Operating RoEV — The True Capital-Compounding Metric
Reported EV growth blends three effects: (1) operating performance, (2) mark-to-market of investments, (3) economic assumption changes. Only (1) reflects management execution.
- **Operating RoEV** = (Opening EV × expected return + VNB added + expected unwind + operating variance) / Opening EV — strips out MTM noise
- **Total RoEV** is the reported number but includes MTM swings that can swing 300-500 bps in a bad equity year
- Life insurers with consistent 18-22% Operating RoEV are genuinely compounding; those whose RoEV is being carried by equity-market MTM will underperform in a flat market
- Extract Operating vs Total RoEV split from `get_company_context(section='concall_insights')` — most life insurers disclose both. If only total RoEV is available, flag that the reported number includes MTM noise
