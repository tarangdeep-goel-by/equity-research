## BFSI Mode (Auto-Detected)

This company is a bank, NBFC, or financial services company. Apply BFSI-specific analysis:

**Primary Metrics** (from `get_quality_scores` section='bfsi' or 'all'):
- **NIM** (Net Interest Margin): Net Interest Income ÷ Average Earning Assets. >3% good, >4% excellent for Indian banks
- **ROA**: Net Profit ÷ Average Total Assets. 1-2% is excellent for banks
- **ROE**: Net Profit ÷ Average Equity. Use DuPont (ROA × Equity Multiplier) to decompose
- **Cost-to-Income**: Operating Expenses ÷ Total Income. <45% efficient, >55% inefficient
- **P/B Ratio**: primary valuation metric. >2.5x = premium, <1x = distressed/PSU
- **CASA Ratio**: Current + Savings deposits ÷ Total deposits. Higher = cheaper funding. Source from concall insights
- **Asset Quality**: GNPA%, NNPA%, Provision Coverage Ratio (PCR), Slippage Ratio, Credit Cost. Source from concall insights

**DO NOT USE for BFSI (these are MEANINGLESS for banks):**
- **ROCE (Return on Capital Employed)** — deposits are raw material, not "capital employed". Do NOT include ROCE in peer comparison tables. Use ROA and ROE instead for all profitability comparisons.
- EBITDA / Operating Margin — not applicable to banking P&L structure
- CFO/PAT ratio — bank CFO swings with deposit/loan flows, not earnings quality
- **FCF (Free Cash Flow)** — CFO minus capex is meaningless when deposits/loans dominate cash flows. Do NOT report FCF CAGRs, FCF trends, or FCF CAGR tables for banks. If the data tools return FCF numbers, IGNORE them entirely — do not even show them with a caveat.
- **Standard DCF / Reverse DCF (FCFE model)** — invalid for banks. Do NOT include DCF sensitivity matrices or FCFE-based reverse DCF. Use P/B-ROE framework (justified P/B = ROE/CoE), Dividend Discount Model (DDM), or Residual Income Model instead.
- Working capital metrics, capex cycle, gross margin

**Emphasize for BFSI:** NIM trend (the single most important metric), book value growth, CASA ratio, credit cost trajectory, advances vs deposit growth, asset quality (GNPA/NNPA), P/B-based valuation, and **Credit-Deposit (CD) ratio** (pre-computed in `get_quality_scores` bfsi section as `cd_ratio_pct` — >78% stretched, >85% risky).

**Valuation:** Use P/B band (primary), P/B vs ROE framework (justified P/B = ROE/CoE), Residual Income Model, or Gordon Growth for mature PSU banks. For conglomerates with listed subsidiaries, use Sum-of-the-Parts (SOTP): value core bank on P/ABV + listed subsidiary values per share with 20-25% holding company discount.

**Insider Transactions:** For board-managed banks (0% promoter holding), absence of open-market insider buying is NORMAL — executives are compensated via ESOPs. Track insider SELLING (ESOP disposals above normal) as the governance signal, not absence of buying.

**Beta Caveat:** yfinance beta is calculated against S&P 500 (global), not Nifty 50. Indian bank betas against Nifty are typically 0.9-1.3x. Do NOT cite yfinance beta as-is for Indian market sensitivity analysis — note the global benchmark limitation.
