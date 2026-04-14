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

### Liquidity Coverage Ratio — Complement Debt Maturity Analysis
When short-term debt is material (>30% of total borrowings) or Net Debt/EBITDA > 2x, reporting maturity walls is not enough — you must answer whether the company can actually pay from existing resources:
- Compute liquidity coverage: (Cash & equivalents + 12M forward CFO estimate) / ST debt maturities
- Coverage <1.0x = refinancing dependency; 1.0–1.5x = tight; >1.5x = comfortable buffer
- Don't just report debt maturity; answer "can they pay it from existing resources or must they refinance"
- Use `get_fundamentals(section='balance_sheet_detail')` for cash and `get_fundamentals(section='cash_flow_quality')` for CFO run-rate

### Entity-Level vs Group-Level News — Attribution Discipline
Conglomerates often operate under a common brand (Adani, Tata, Reliance) with multiple listed entities. Attribution mistakes are easy — and costly:
- A cement sector acquisition announced by "Adani Group" may be executed by Ambuja Cements or ACC (separate listed entities), not by Adani Enterprises — even though all three appear under the Adani brand
- Vedanta Ltd, Hindustan Zinc, and Cairn are distinct listed/unlisted entities — divestments and demergers in one do not mechanically flow to another
- The Tata brand covers 20+ listed entities — a "Tata announcement" rarely applies to all of them
- Before citing a major event as a direct balance sheet impact, verify it applies to THIS listed entity via `get_events_actions(section='corporate_actions')` or `get_company_context(doc_type='filings')` — don't trust group-brand associations

### Cross-Subsidization — Which Segments Are Funding Which
Decomposing segment margins from concall_insights tells you the capital flow within the group:
- Profitable segment (high EBIT) with capex < depreciation → generating cash to fund other segments
- Loss-making segment with capex > depreciation → consuming group resources
- Flag "cross-subsidization" when profitable segments funnel FCF into loss-makers — this delays thesis realization for the profitable parts
- Use segment capex from `get_company_context(section='concall_insights')` or annual report segment disclosure

### Promoter Funding & Related-Party Transactions
Conglomerates frequently have related-party loans, inter-corporate deposits, or guarantee exposures that don't show up in headline leverage:
- Check `get_fundamentals(section='balance_sheet_detail')` for inter-corporate items
- If material (>5% of net worth), flag — these can indicate cash siphoning or support for weaker group entities
- Pledge data (from ownership agent's domain) cross-references this — high promoter pledge + large related-party exposure = governance concern
