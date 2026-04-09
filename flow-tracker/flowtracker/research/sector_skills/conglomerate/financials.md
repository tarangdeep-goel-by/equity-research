## Conglomerate — Financials Agent

### Debt Maturity & Liquidity — Why It's the Key Risk for Conglomerates
Conglomerates often carry heavy debt across multiple entities. When consolidated Net Debt/EBITDA > 2x:
- Analyze debt maturity profile from `get_fundamentals(section='balance_sheet_detail')`: short-term vs long-term borrowings
- Flag near-term maturity concentration (>30% of debt maturing within 12 months = refinancing risk)
- Track absolute net debt trajectory, not just leverage ratios — ratios can look safe at cycle peaks
- Check interest coverage by segment if available from concall_insights — a profitable segment may be servicing debt for loss-making ones

### Segment-Level Financial Analysis
Consolidated numbers are blended averages — decompose where possible:
- Extract segment revenue, EBIT, and margins from `get_company_context(section='concall_insights')`
- Identify which segments are capital consumers vs cash generators
- Cross-subsidization flag: if one segment has negative EBIT but is receiving capex, the profitable segments are funding it
