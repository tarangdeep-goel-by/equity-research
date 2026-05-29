## Insurance Mode (Auto-Detected)

This company is an insurance company. Apply insurance-specific analysis:

**Sub-Type Detection:** Check industry — "Life Insurance" → life framework, "General Insurance" → general framework.

**Primary Metrics** (from `get_quality_scores` section='insurance' or 'all'):
- **ROE**: valid for insurance. Decompose using DuPont where possible
- **ROA**: Net Profit ÷ Total Assets. Lower than banks due to investment portfolio dominance
- **Opex Ratio**: Operating expenses ÷ premium. For life insurers, IRDAI's Expenses of Management (EoM) limit is computed against Gross Written Premium (GWP), not Net Earned Premium. Lower = more efficient
- **Solvency Ratio**: Regulatory minimum 150%. Source from concall insights
- **Premium Growth**: YoY growth in Gross Written Premium

**Life Insurance Specific:**
- **VNB (Value of New Business)**: measures profitability of new policies sold. Compare VNB margin against peer median via `get_peer_sector(section='benchmarks')` and the company's own trend
- **APE (Annualized Premium Equivalent)**: standardized new business metric
- **Persistency (13th/61st month)**: policy retention — higher is better. Compare against peer median and the company's own trend
- **Embedded Value (EV)**: present value of future profits from in-force book
- **Valuation**: P/EV (Price ÷ Embedded Value per share) is the primary metric because it captures the present value of future profits. P/VNB for growth. If EV data unavailable, fall back to P/B with stated limitations

**General Insurance Specific:**
- **Combined Ratio**: Loss Ratio + Expense Ratio. <100% = underwriting profit. Compare against peer median for context
- **Loss Ratio**: Net Incurred Claims (claims paid + change in outstanding-claim reserves) ÷ Net Earned Premium
- **Expense Ratio**: (Operating expenses + Net Commission) ÷ Net Written Premium (IRDAI NL-20 analytical-ratios definition)
- **Valuation**: P/B (primary), target P/E acceptable for general insurers

**Metrics that give misleading results for insurance:**
- **EBITDA, EBIT margin, ROCE** — insurance P&L structure is fundamentally different from manufacturing/services; these metrics are not applicable
- **FCF (Free Cash Flow)** — investment income and claim reserves distort cash flows, making FCF a formula artifact rather than a business signal
- **Standard DCF / Reverse DCF** — insurance cash flows are driven by actuarial reserves and investment portfolios, not operating free cash flow. DCF sensitivity matrices are not meaningful here
- **Working capital metrics, inventory, capex cycle, gross margin** — not applicable to the insurance business model
- **CFO/PAT ratio** — reserve movements and investment cash flows distort this ratio beyond usefulness

**Fallback when concall KPIs unavailable:** If VNB/EV/combined ratio data is not available from tools, explicitly state this gap. For life insurance, fall back to P/B + ROE framework. For general insurance, use P/B + underwriting profit trends from P&L. These are insurance-specific KPIs that require actuarial data — estimating them from standard financials would produce unreliable numbers.

**Emphasize:** Premium growth trajectory, product mix (protection vs savings for life), investment yield, solvency buffer above 150%, and claims ratio trend.

**Ind AS 117 / IFRS-17 transition (effective FY27, April 2026):** Indian insurers move from premium-driven top-line to fair-value / discounting-led measurement with the **Contractual Service Margin (CSM)** as the unearned-profit store. For FY27+ estimates, treat legacy premium-growth and reported-P&L metrics as partially obsolete: track CSM (and its release) as the new profitability KPI, expect discounting-rate-led earnings volatility, and flag that pre- vs post-transition financials are not directly comparable. If a company has disclosed transition impacts or a CSM build, surface it; if not, note the transition as a forward modelling caveat.

## Segment Separation for Insurance + Credit Marketplaces (new)

POLICYBZR and other insurance-marketplaces have two economically distinct segments (Policybazaar = insurance distribution; Paisabazaar = credit marketplace). Both MUST be analyzed separately — growth, unit economics, take rate, competitive position. Reporting only the insurance side while ignoring the credit side (or vice versa) is structurally incomplete.

## NPA Framing for Marketplaces (new)

If reporting NPAs for a marketplace business, clarify whether the company takes balance-sheet risk (FLDG arrangements, co-lending partnerships) or is a pure distribution marketplace. A pure marketplace should NOT have NPAs on its own book — if the JSON output contains an NPA field for a pure marketplace, it is reporting channel-partner data and MUST be framed as such, not attributed to the company's own credit risk.

## Valuation Basis — Conglomerate Insurance (new)

`get_valuation` output for listed insurance companies may mix standalone historical PE (Screener-derived) with consolidated forward EPS (FMP-derived). Flag and recompute with matching bases per shared-preamble A1.1 tenet. See E11 upgrade (`pe_basis` / `eps_basis` fields) for the tool-side warning.
