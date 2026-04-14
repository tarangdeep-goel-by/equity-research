## BFSI — Financials Agent

### Asset Quality Metrics
Asset quality is the most critical dimension for bank analysis — a single quarter of slippage spikes can wipe out years of earnings. Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **GNPA** (Gross Non-Performing Assets) ratio — 5Y+ trend
- **NNPA** (Net NPA) ratio — 5Y+ trend
- **PCR** (Provision Coverage Ratio) — higher = more conservative
- **Slippages** — fresh additions to NPA, as % of advances
- **Credit Cost** — provisions as % of average advances
- **Provisioning / Operating Profit** — what share of core earnings are consumed by bad loans? Rising ratio = deteriorating quality even if headline NPA is stable

If concall data doesn't contain these, flag as open questions — fabricated asset quality numbers are worse than no numbers, since even small errors in NPA/slippage data can completely change the investment thesis.

### Available Structured BFSI Metrics
`get_quality_scores(section='bfsi')` returns: NIM%, ROA%, Cost-to-Income%, P/B, Equity Multiplier, CD Ratio. Use these directly.

### Liability Franchise — Why It Drives Long-Term NIM
Indian banks compete primarily on deposit cost, not lending rates (which are largely repo-linked). A bank with a strong CASA franchise has structurally cheaper funding, which translates directly into wider NIMs that persist through rate cycles. This is why CASA is the single best predictor of sustainable profitability.
- Extract from `concall_insights` or `sector_kpis`:
- **CASA Ratio** — Current + Savings deposits / Total deposits. Higher = cheaper funding = wider NIM. Compare against peer median via `get_peer_sector(section='benchmarks')` and the bank's own trend
- **Cost of Funds** — tracks funding cost trajectory. Compare to repo rate cycle

### Operating Profit Quality
Other Income for banks mixes core fee income (processing fees, insurance distribution, wealth management) with volatile treasury gains (bond MTM). If Other Income spiked in a quarter, the spike is likely treasury — don't extrapolate it. Flag when Other Income growth materially exceeds NII growth.

### Capital Adequacy — Mandatory When Discussing Capital Actions
Banks are regulated on **CRAR** (Capital to Risk-weighted Assets Ratio, Basel III minimum ~11.5% incl. CCB) and **CET1** (Common Equity Tier-1, minimum ~7-8%). These are non-negotiable regulatory floors; management decisions on lending growth, QIPs, and dividend payouts are constrained by them.
- Whenever discussing an equity raise (QIP, rights issue), sub-debt issuance, or accelerated credit growth, cite the **pre- and post-action CRAR/CET1**
- Canonical key via `get_sector_kpis(sub_section='capital_adequacy_ratio_pct')`
- CET1 compression below ~10% in a growing bank is a warning — either dilution is imminent or growth slows
- All forward BVPS or CRAR projections (BVPS × (1+g)^years) must go through the `calculate` tool — compound interest in your head produces errors that reviewers catch

### Valuation Basis
- Use **P/B** (Price to Book) as the primary valuation metric, not PE
- When computing implied core bank P/B (after stripping subsidiary value), use **standalone BVPS** — never consolidated BVPS. Consolidated book includes subsidiary goodwill/investments that distort the core bank multiple
- Call `get_valuation(section='band', metric='pb')` for historical P/B band context

### NIM Analysis
- NIM compression/expansion must be explained with CAUSE: deposit competition, rate cycle, CASA mix shift, bulk deposit reliance
- Compare NIM to sector median from `get_peer_sector(section='benchmarks')`
