## Insurance Mode (Auto-Detected)

This company is an insurance company. Apply insurance-specific analysis:

**Sub-Type Detection:** Check industry — "Life Insurance" → life framework, "General Insurance" → general framework.

**Primary Metrics** (from `get_quality_scores` section='insurance' or 'all'):
- **ROE**: valid for insurance. Decompose using DuPont where possible
- **ROA**: Net Profit ÷ Total Assets. Lower than banks due to investment portfolio dominance
- **Opex Ratio**: Operating expenses ÷ Net Earned Premium. Lower = more efficient
- **Solvency Ratio**: Regulatory minimum 150%. Source from concall insights
- **Premium Growth**: YoY growth in Gross Written Premium

**Life Insurance Specific:**
- **VNB (Value of New Business)**: measures profitability of new policies sold. VNB margin >25% excellent
- **APE (Annualized Premium Equivalent)**: standardized new business metric
- **Persistency (13th/61st month)**: policy retention — 13M >85% good, 61M >50% good
- **Embedded Value (EV)**: present value of future profits from in-force book
- **Valuation**: P/EV (Price ÷ Embedded Value per share) is PRIMARY. P/VNB for growth. If EV data unavailable, fall back to P/B with stated limitations

**General Insurance Specific:**
- **Combined Ratio**: Loss Ratio + Expense Ratio. <100% = underwriting profit. <95% excellent
- **Loss Ratio**: Claims paid ÷ Net Earned Premium
- **Expense Ratio**: Operating expenses ÷ Net Written Premium
- **Valuation**: P/B (primary), target P/E acceptable for general insurers

**DO NOT USE for Insurance (these are MEANINGLESS):**
- EBITDA, EBIT margin, ROCE — not applicable to insurance P&L
- FCF (Free Cash Flow) — investment income and claim reserves distort cash flows
- Standard DCF / Reverse DCF — invalid for insurance. Do NOT include DCF sensitivity matrices
- Working capital metrics, inventory, capex cycle, gross margin
- CFO/PAT ratio — reserve movements and investment cash flows distort

**Fallback when concall KPIs unavailable:** If VNB/EV/combined ratio data is not available from tools, explicitly state this gap. For life insurance, fall back to P/B + ROE framework. For general insurance, use P/B + underwriting profit trends from P&L. Do NOT guess or estimate these KPIs.

**Emphasize:** Premium growth trajectory, product mix (protection vs savings for life), investment yield, solvency buffer above 150%, and claims ratio trend.
