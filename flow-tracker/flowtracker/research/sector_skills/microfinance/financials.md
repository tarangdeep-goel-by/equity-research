## Microfinance / NBFC — Financials Agent

### Key Difference from Banks — and SFB vs NBFC-MFI Split
First identify the entity structure, because funding economics differ sharply:
- **NBFC-MFIs** (e.g., CreditAccess Grameen, Fusion, Spandana) cannot take deposits — they rely on wholesale/market borrowings (bank term loans, NCDs, NABARD refinance). Funding cost is volatile and the NIM-minus-credit-cost spread is the entire business equation.
- **Small Finance Banks** (e.g., Equitas, Ujjivan) DO take retail deposits and rely heavily on CASA. CASA-funded low-cost deposits lower funding cost vs NBFC-MFIs, but SFBs carry CRR/SLR regulatory drag (idle reserves) that NBFC-MFIs don't, structurally capping NIM. Track CASA ratio, deposit cost, and CRR/SLR drag for SFBs; track borrowing mix and rollover risk for NBFC-MFIs.

### Core Metrics (from concall_insights / sector_kpis)
- **AUM (Assets Under Management)** — the scale metric. Defined in `sector_kpis` as `aum_cr`
- **Disbursement growth** — `sector_kpis` as `disbursements_cr`. Compare to AUM growth: high disbursements + low AUM growth = massive run-off/churn (portfolio quality issue)
- **Cost of Borrowings** — `sector_kpis` as `cost_of_funds_pct`. Track trend vs repo rate cycle
- **Capital Adequacy (CRAR)** — `sector_kpis` as `capital_adequacy_ratio_pct`. NBFC-MFIs require minimum 15% CRAR, of which **Tier-1 must be at least 10%** (RBI Master Direction). Buffer above minimum = growth runway without dilution. Note: RBI cut the risk weight on microfinance loans from 125% back to 100% (effective Feb 25, 2025), easing capital consumption vs the prior consumer-credit treatment

### Risk-Adjusted Margin — The Key Metric
- **NIM minus Credit Cost = Risk-Adjusted Margin**
- NIM from `get_quality_scores(section='bfsi')` (works for NBFCs too)
- Credit cost from concall_insights
- Compare risk-adjusted margin against peer median and the company's own history across cycles
- Track this over cycles — MFI credit costs spike violently in downturns (demonetization, COVID, Assam/Karnataka crises)

### Asset Quality — Different from Banks
- MFI/NBFC NPAs are MORE cyclical than banks — entire geographies can go bad simultaneously
- Track **PAR 30/60/90** (Portfolio at Risk) from concall_insights — more granular than GNPA
- Collection efficiency % — compare against peer median and the company's own trend across cycles
- Geographic concentration risk — if >30% of AUM is in one state, flag regulatory/political risk

### True Credit Cost — Ind AS 109 ECL + Technical Write-offs
- Reported GNPA/PAR is routinely **understated** by aggressive technical write-offs and management overlays. To get the true credit cost, **add technical write-offs back** to provision expense (true credit cost = P&L provisions + technical write-offs, annualized as % of AUM)
- Map PAR to ECL staging: **PAR-30 → Stage 2** (significant increase in credit risk), **PAR-90 → Stage 3** (credit-impaired). A rising Stage-2 pool is a leading indicator of future Stage-3 slippage and credit-cost spikes
- Watch for overlay release (one-off PBT boost) vs overlay build (conservative). A company cutting overlays into a deteriorating cycle is flattering earnings

### 2024-25 Asset Quality Stress Cycle (mandatory context)
The sector entered a sharp down-cycle in FY25 driven by borrower overleveraging, the Karnataka ordinance, and heatwave/election disruption. Sector GNPA rose to ~16% (from ~8.8% a year earlier) and PAR(31-180) to ~6.2% by Q4FY25. Major listed players swung to losses/profit collapse (CreditAccess profit fell ~88%, Fusion and Spandana posted full-year losses). Treat the prior up-cycle's credit costs and ROA as non-representative — anchor expectations to the through-cycle range and the recovery trajectory, not pre-FY25 peaks.

### Liquidity & ALM
- **ALM structure** — unlike typical NBFCs (borrow short, lend long), MFIs usually **lend short** (12-24 month micro-loans) while **borrowing longer** (2-3 year bank term loans / NABARD refinance), which tends to give them a *favourable* near-term ALM. Still check the maturity ladder: if short-term borrowings (CP, NCD maturities) exceed short-term asset inflows, flag liquidity risk
- Use `get_fundamentals(section='balance_sheet_detail')` for borrowing maturity structure
- Track CP/NCD dependence — high commercial paper reliance = rollover risk (IL&FS lesson)

### Valuation
- **P/B** is primary for NBFCs/MFIs (same as banks). ROA-adjusted P/B for comparison
- `get_quality_scores(section='bfsi')` returns equity_multiplier as leverage proxy
