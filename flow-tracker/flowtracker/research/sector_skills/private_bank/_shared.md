## Private Bank Mode (Auto-Detected)

This company is a large or mid-size Indian private-sector bank. The private-bank framework **inherits the full BFSI core** (see `bfsi/_shared.md`) for NII, NIM, CASA, CD ratio, GNPA/NNPA, PCR, CRAR/CET1, P/B-ROE valuation, and Bank DuPont. This file adds the private-bank-specific distinctions, archetype contrasts vs PSU banks, and SOTP framing for conglomerate bank groups.

### Private Bank vs PSU — Archetype Distinctions
| Dimension | PSU Bank | Private Bank |
|---|---|---|
| **RoA (steady-state)** | 0.4-0.9% | 1.2-1.8% |
| **RoE (steady-state)** | 8-12% | 14-20% |
| **Fee-income share of total income** | 8-15% | 20-30% |
| **Aggregate foreign-holding cap** | 20% (SBI Act / Bank Acquisition Acts) | **74%** (RBI Master Direction on FDI in banks) |
| **Promoter/sponsor structure** | Govt of India ≥ 51% statutory floor | Varies — individual promoter (KOTAK), post-merger no-promoter (HDFCBANK), family group (INDUSINDBK) |
| **Subsidiary structure** | Typically standalone | Often conglomerate — listed insurance / AMC / brokerage subsidiaries drive SOTP |
| **Insider culture** | IAS/banking cadre, no ESOP | ESOP-driven — track insider selling clusters, not buying |

### Foreign Holding Cap — 74% Ceiling Binds
- Aggregate foreign holding = FDI + FPI + ADR/GDR + NRI; all four combined subject to 74% cap
- Large private banks often sit close to the cap — HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK, INDUSINDBK have historically been in the 65-74% aggregate range
- When aggregate >70%, MSCI/FTSE passive rebalance demand is already largely consumed — incremental foreign flow rate plateaus and then depends on active-manager decisions, not index flow
- ADR/GDR aggregation is mandatory for large private banks — see `private_bank/ownership.md` Tenet 12 framing

### Conglomerate Bank → SOTP Valuation
Private banks that own listed subsidiaries (HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK) are not single-entity banks — standalone P/B alone understates fair value. When listed-subsidiary value > 15% of standalone bank market cap, Sum-of-the-Parts is the correct primary valuation:
- **Core bank**: Standalone BVPS × justified P/ABV (P/B adjusted for net NPAs)
- **Listed subsidiary values**: market-cap × ownership %, apply 20-25% holding-company discount
- **Unlisted subsidiaries**: book value or implied embedded value from last capital raise
- Sum, divide by bank shares outstanding → SOTP target per share
- Call `get_valuation(section='sotp')` when subsidiary value >15% of standalone mcap

### Cross-Sell Depth Drives Fee Income
Private-bank fee income is largely driven by distribution of in-group insurance, AMC, and brokerage products. Tighter subsidiary linkage = higher fee-income ratio. Banks with standalone structure (no AMC/insurance subsidiary in the group) see thinner fee-income ratios and are more NIM-dependent for RoA.

### Private Bank Universe
- **Top 5 large-caps**: HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK, INDUSINDBK
- **Mid-tier**: IDFCFIRSTB, FEDERALBNK, RBLBANK, BANDHANBNK
- **Smaller listed privates**: CSBBANK, CUB (City Union Bank), DCBBANK, KARURVYSYA, SOUTHBANK

### Mandatory Metrics for Private Bank Reports (Cross-Cutting)
Every private-bank report — from both the ownership and financials agents — must state or reference:
- **NIM** (Net Interest Margin) — trend, peer-relative, deposit-cost-driven cause
- **NII growth** — YoY and QoQ
- **GNPA / NNPA** — trend, vs peer median, with SMA-2 leading indicator
- **PCR** (Provision Coverage Ratio)
- **CRAR / CET1** — headroom to Basel III minimums, dilution risk if CET1 < 13%
- **Credit-Deposit ratio** — liquidity positioning
- **CASA ratio** — liability-franchise strength driver
- **Fee-income share** — cross-sell moat indicator (>25% strong, 15-25% moderate, <15% thin)
- **Slippage ratio** — fresh NPA additions % of advances
- **Credit-cost trajectory (≥5 quarters)** — not a single-quarter number; with provisioning-cycle context (see `bfsi/_shared.md` mandatory rules)
- **Non-interest-income split (fee / treasury / recoveries)** — extracted from concall `financial_metrics`, not estimated from consolidated non-int-inc
- **LCR (Liquidity Coverage Ratio)** — vs 100% regulatory floor; private banks typically 115–135%; <110% is balance-sheet-stress signal
- **Aggregate foreign holding (FDI + FPI + ADR/GDR + NRI)** — explicit breakdown vs the 74% cap. Do NOT report the FPI component in isolation for large private banks; the four-component aggregate is the binding constraint. When aggregate >70% note the passive-flow ceiling (MSCI/FTSE rebalance demand substantially consumed)
- **RoA / RoE** — decomposed via bank DuPont (see bfsi/financials.md)
- **SOTP value** — where listed subsidiaries contribute >15% of standalone mcap

### Valuation
- Use **P/B** (or P/ABV after net NPA adjustment) as primary. Consolidated BVPS for conglomerate groups; standalone BVPS when stripping subsidiary value for core bank multiple
- For HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK → SOTP as primary; standalone P/B as cross-check
- Peer band via `get_valuation(section='band', metric='pb')` and `get_peer_sector(section='benchmarks')`

### Metrics That Don't Apply
Same exclusions as BFSI core (see bfsi/_shared.md): ROCE, EBITDA, FCF, standard DCF, working capital, gross margin — all formula artifacts for banks. Do not present.

## BFSI Asset-Quality Metrics — Strict Enforcement (new)

Missing any of GNPA %, NNPA %, PCR %, LCR %, CRAR %, or CET-1 % when the bank is in the Nifty-50 BFSI cohort is a PROMPT_FIX downgrade. Extract via the mandatory chain: `get_quality_scores(section='bfsi')` → `get_sector_kpis(symbol, sub_section=<key>)` → `get_concall_insights(sub_section='financial_metrics')` for the last 4 quarters → `get_annual_report(section='segmental')` or `auditor_report`. Cite each value with 1-decimal precision: "GNPA 2.1%" NOT "below 3%".

## CFO-for-BFSI Rule (new)

Operating cash flow for banks and NBFCs is dominated by deposit and loan flow swings quarter to quarter. Do NOT use CFO to argue dividend sustainability. Use the dividend payout ratio (from `get_fundamentals(section='ratios')`) or `total dividend / net_profit` trajectory instead. Citing CFO coverage for a BFSI dividend is a COMPUTATION-level downgrade.

## ROCE Exclusion for BFSI (new)

ROCE is NOT a valid KPI for banks or NBFCs — it mixes interest income and borrowings denominators in non-meaningful ways. Do not include ROCE in the business profile table or financial summary. If `get_fundamentals` returns a ROCE value, ignore it for narrative. Use ROE, ROA, NIM, and C/I ratio instead.
