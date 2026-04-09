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
