## BFSI Mode (Auto-Detected)

This company is a bank, NBFC, or financial services company. Apply BFSI-specific analysis:

**Primary Metrics** (from `get_quality_scores` section='bfsi' or 'all'):
- **NIM** (Net Interest Margin): Net Interest Income ÷ Average Earning Assets. Compare against sector peers via `get_peer_sector(section='benchmarks')` and the company's own 5Y trend to assess whether NIM is expanding or compressing
- **ROA**: Net Profit ÷ Average Total Assets. Compare to peer median and own history
- **ROE**: Net Profit ÷ Average Equity. Use DuPont (ROA × Equity Multiplier) to decompose
- **Cost-to-Income**: Operating Expenses ÷ Total Income. Lower is better — compare against peer median for context
- **P/B Ratio**: primary valuation metric. Compare to peer range and own historical band via `get_valuation(section='band', metric='pb')`
- **CASA Ratio**: Current + Savings deposits ÷ Total deposits. Higher = cheaper funding. Source from concall insights
- **Asset Quality**: GNPA%, NNPA%, Provision Coverage Ratio (PCR), Slippage Ratio, Credit Cost. Source from concall insights
- **LCR (Liquidity Coverage Ratio)**: High-quality liquid assets ÷ 30-day net cash outflows. Regulatory floor is 100%; large private banks typically run 115–135% with buffer. Mandatory to cite in every BFSI financials / valuation report — below-floor or thin-buffer (<110%) is a balance-sheet-stress signal that P/B alone cannot surface. Source from concall `financial_metrics` and investor presentations; do NOT estimate.

### Mandatory Quantification Rules (not optional)

- **Credit-cost trajectory — always ≥5 quarters.** Do not cite a single-quarter credit cost (bps). Extract ≥5 quarters from `get_company_context(section='concall_insights', sub_section='financial_metrics')` and state the trajectory (compression / expansion / range-bound) with provisioning-cycle context (specific provisioning, contingency buffer build/release, COVID restructuring run-off, NPA recognition change). A single-quarter credit-cost number without trajectory is a mandatory-metric gap, not analysis.
- **Non-interest-income split — extract, do not estimate.** Non-interest income is not a single line — it splits into (a) core fee income (advisory, processing, FX, card interchange, wealth/distribution commissions), (b) treasury / trading gains (bond book MTM, FX trading), (c) recoveries from written-off accounts. The mix drives earnings quality: a quarter where treasury contributes 40%+ is not comparable to one where it's 10%. Extract the split from concall `financial_metrics` and investor presentations. Estimating the split from consolidated non-interest-income is a fabrication; report the data gap if extraction fails and do not synthesize.
- **Asset quality must include SMA-2 leading indicator.** GNPA/NNPA are lagging. Call out SMA-2 (30–60 day overdue) as the leading NPA indicator, alongside trajectory of restructured advances / ECL Stage-2 to gauge next-quarter slippage risk. PCR alone without SMA-2 context describes the past, not the forward risk.

**Metrics That Don't Apply to Banks:**
- **ROCE (Return on Capital Employed)** — deposits are raw material, not "capital employed," so ROCE gives misleading results. Use ROA and ROE instead for all profitability comparisons.
- **EBITDA / Operating Margin** — banking P&L structure doesn't have a meaningful EBITDA line; interest expense is the core operating cost, not something to add back.
- **CFO/PAT ratio** — bank CFO swings with deposit/loan flows, not earnings quality, making this ratio noise rather than signal.
- **FCF (Free Cash Flow)** — CFO minus capex is not meaningful when deposits/loans dominate cash flows. Even if data tools return FCF numbers, they are a formula artifact, not a real signal — omit them entirely rather than showing with a caveat.
- **Standard DCF / Reverse DCF (FCFE model)** — FCFE models assume predictable free cash flows, which banks don't generate. DCF sensitivity matrices are a formula artifact for banks. Use P/B-ROE framework (justified P/B = ROE/CoE), Dividend Discount Model (DDM), or Residual Income Model instead.
- **Working capital metrics, capex cycle, gross margin** — not applicable to the banking business model.

**Emphasize for BFSI:** NIM trend (the single most important metric), book value growth, CASA ratio, credit cost trajectory, advances vs deposit growth, asset quality (GNPA/NNPA), P/B-based valuation, and **Credit-Deposit (CD) ratio** (pre-computed in `get_quality_scores` bfsi section as `cd_ratio_pct` — compare to peer median and the company's own trend to assess liquidity position).

**Valuation:** Use P/B band (primary), P/B vs ROE framework (justified P/B = ROE/CoE), Residual Income Model, or Gordon Growth for mature PSU banks. For conglomerates with listed subsidiaries, use Sum-of-the-Parts (SOTP): value core bank on P/ABV + listed subsidiary values per share with 20-25% holding company discount.

**Insider Transactions:** For board-managed banks (0% promoter holding), absence of open-market insider buying is expected — executives are compensated via ESOPs, so they rarely buy on the open market. Track insider selling (ESOP disposals above normal) as the governance signal, not absence of buying.

**Beta Caveat:** yfinance beta is calculated against S&P 500 (global), not Nifty 50. Indian bank betas against Nifty are typically 0.9-1.3x. Citing yfinance beta as-is for Indian market sensitivity analysis is misleading — note the global benchmark limitation.

### Annual Report & Investor Deck — BFSI Specifics

**AR high-signal sections (consult proactively when agent is mandated):**
- `auditor_report` — Key Audit Matters on loan classification and ECL model governance are standard bank KAMs; non-standard KAMs (forensic audit, restructuring, going-concern) are red flags Risk agent must surface.
- `notes_to_financials` — stage-wise GNPA/NNPA classification (typically Note 9-15 in Indian banks), PCR composition (provisions vs write-offs), 5-quarter trajectory. Trumps concall summaries for asset-quality trajectory.
- `risk_management` — mandated CET-1, Tier-1, CRAR disclosure with peer-percentile context. Use to validate capital headroom vs loan-book growth.
- `related_party` — intra-group lending (bank → NBFC sister, insurance arm) flagged as concentration risk.
- `segmental` — retail vs wholesale vs treasury vs slippages-by-segment; CASA composition (retail vs wholesale CASA).

**Deck high-signal sub_sections (for Business/Financials/Valuation agents):**
- `charts_described` — banks show rolling 4-quarter credit-cost chart; NIM trajectory; CASA ratio evolution.
- `outlook_and_guidance` — credit-cost guidance, NIM guidance, loan-growth target for current FY.

**Cross-year narrative cues:** Watch for `auditor_signals.credibility_trajectory` (declining → concentrate on KAM escalation), `rpt_evolution` (growing intra-group flows), `risk_evolution.escalated_risks` (digital fraud, cybersecurity appearing fresh this year).

## BFSI Asset-Quality Metrics — Strict Enforcement (new)

Missing any of GNPA %, NNPA %, PCR %, LCR %, CRAR %, or CET-1 % when the bank is in the Nifty-50 BFSI cohort is a PROMPT_FIX downgrade. Extract via the mandatory chain: `get_quality_scores(section='bfsi')` → `get_sector_kpis(symbol, sub_section=<key>)` → `get_concall_insights(sub_section='financial_metrics')` for the last 4 quarters → `get_annual_report(section='segmental')` or `auditor_report`. Cite each value with 1-decimal precision: "GNPA 2.1%" NOT "below 3%".

## CFO-for-BFSI Rule (new)

Operating cash flow for banks and NBFCs is dominated by deposit and loan flow swings quarter to quarter. Do NOT use CFO to argue dividend sustainability. Use the dividend payout ratio (from `get_fundamentals(section='ratios')`) or `total dividend / net_profit` trajectory instead. Citing CFO coverage for a BFSI dividend is a COMPUTATION-level downgrade.

## ROCE Exclusion for BFSI (new)

ROCE is NOT a valid KPI for banks or NBFCs — it mixes interest income and borrowings denominators in non-meaningful ways. Do not include ROCE in the business profile table or financial summary. If `get_fundamentals` returns a ROCE value, ignore it for narrative. Use ROE, ROA, NIM, and C/I ratio instead.

**Chart routing.** `render_chart(chart_type='sector_valuation_scatter')` auto-detects BFSI and plots PE vs ROA (not ROCE) as the quality axis. Call it the same way — don't pass a `y_metric` override, the sector detection handles it. If ROA coverage is thin across the peer set (fewer than 2 peers with `roa_pct` populated), the chart falls back to ROCE so something renders — note that as a data gap, not a valid comparison.
