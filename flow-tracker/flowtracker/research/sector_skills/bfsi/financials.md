## BFSI — Financials Agent

### Asset Quality Metrics
Asset quality is the most critical dimension for bank analysis. Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **GNPA** (Gross Non-Performing Assets) ratio — 5Y+ trend
- **NNPA** (Net NPA) ratio — 5Y+ trend
- **PCR** (Provision Coverage Ratio) — higher = more conservative
- **Slippages** — fresh additions to NPA, as % of advances
- **Credit Cost** — provisions as % of average advances
- **Provisioning / Operating Profit** — what share of core earnings are consumed by bad loans? Rising ratio = deteriorating quality even if headline NPA is stable

If concall data doesn't contain these, flag as open questions — do NOT fabricate asset quality numbers.

### Available Structured BFSI Metrics
`get_quality_scores(section='bfsi')` returns: NIM%, ROA%, Cost-to-Income%, P/B, Equity Multiplier, CD Ratio. Use these directly.

### Liability Franchise (CRITICAL for Indian Banks)
Extract from `concall_insights` or `sector_kpis`:
- **CASA Ratio** — Current + Savings deposits / Total deposits. Higher = cheaper funding = wider NIM. CASA >40% is strong for private banks, >35% for PSU banks
- **Cost of Funds** — tracks funding cost trajectory. Compare to repo rate cycle

### Operating Profit Quality
Other Income for banks mixes core fee income (processing fees, insurance distribution, wealth management) with volatile treasury gains (bond MTM). If Other Income spiked in a quarter, the spike is likely treasury — don't extrapolate it. Flag when Other Income growth materially exceeds NII growth.

### Valuation Basis
- Use **P/B** (Price to Book) as the primary valuation metric, not PE
- When computing implied core bank P/B (after stripping subsidiary value), use **standalone BVPS** — never consolidated BVPS. Consolidated book includes subsidiary goodwill/investments that distort the core bank multiple
- Call `get_valuation(section='band', metric='pb')` for historical P/B band context

### NIM Analysis
- NIM compression/expansion must be explained with CAUSE: deposit competition, rate cycle, CASA mix shift, bulk deposit reliance
- Compare NIM to sector median from `get_peer_sector(section='benchmarks')`
