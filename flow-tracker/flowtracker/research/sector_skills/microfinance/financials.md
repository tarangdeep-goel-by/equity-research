## Microfinance / NBFC — Financials Agent

### Key Difference from Banks
NBFCs/MFIs don't have CASA deposits — they rely on wholesale/market borrowings. This makes their funding cost volatile and the NIM-credit cost spread is the entire business equation.

### Core Metrics (from concall_insights / sector_kpis)
- **AUM (Assets Under Management)** — the scale metric. Defined in `sector_kpis` as `aum_cr`
- **Disbursement growth** — `sector_kpis` as `disbursements_cr`. Compare to AUM growth: high disbursements + low AUM growth = massive run-off/churn (portfolio quality issue)
- **Cost of Borrowings** — `sector_kpis` as `cost_of_funds_pct`. Track trend vs repo rate cycle
- **Capital Adequacy (CRAR)** — `sector_kpis` as `capital_adequacy_ratio_pct`. Regulatory minimum varies (15% for MFIs, 15% for NBFCs). Buffer above minimum = growth runway without dilution

### Risk-Adjusted Margin (THE Key Metric)
- **NIM minus Credit Cost = Risk-Adjusted Margin**
- NIM from `get_quality_scores(section='bfsi')` (works for NBFCs too)
- Credit cost from concall_insights
- A risk-adjusted margin of >3% is strong, <2% means the business model is thin
- Track this over cycles — MFI credit costs spike violently in downturns (demonetization, COVID, Assam/Karnataka crises)

### Asset Quality — Different from Banks
- MFI/NBFC NPAs are MORE cyclical than banks — entire geographies can go bad simultaneously
- Track **PAR 30/60/90** (Portfolio at Risk) from concall_insights — more granular than GNPA
- Collection efficiency % — should be >98% in normal times. Below 95% is distress
- Geographic concentration risk — if >30% of AUM is in one state, flag regulatory/political risk

### Liquidity & ALM
- **ALM mismatch** — NBFCs borrow short and lend long. If short-term borrowings > short-term assets, flag liquidity risk
- Use `get_fundamentals(section='balance_sheet_detail')` for borrowing maturity structure
- Track CP/NCD dependence — high commercial paper reliance = rollover risk (IL&FS lesson)

### Valuation
- **P/B** is primary for NBFCs/MFIs (same as banks). ROA-adjusted P/B for comparison
- `get_quality_scores(section='bfsi')` returns equity_multiplier as leverage proxy
