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
Conglomerates typically operate under a common group brand across many separately listed entities. Attribution mistakes are easy — and costly:
- A sector-level acquisition announced by "Group X" may be executed by a specific listed subsidiary under that brand, not the flagship listed entity you are analyzing — verify which exact legal entity bears the balance-sheet impact
- Distinct listed or unlisted sister entities within the same group carry different cash flows, debt stacks, and contingent liabilities — divestments and demergers in one do not mechanically flow to another
- A shared brand covering many listed entities means a "Group announcement" rarely applies uniformly; always confirm which specific listed entity the event attaches to
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

### Standalone vs Consolidated Debt — The Holdco Risk Metric
Consolidated leverage blends operating subs (which can service their own debt) with the parent (which depends on sub dividends). For conglomerates, always isolate:
- **Standalone (holdco) debt** — servicable only from dividends received, asset monetization, or equity raises. If standalone debt > 2× annual sub dividends received = refinancing dependency
- **Subsidiary debt** — operationally serviced. Less of a holdco risk, but matters if the sub is loss-making (cross-guarantee exposure)
- Extract both via `get_fundamentals(section='balance_sheet_detail')` — standalone and consolidated financials are usually both available
- Report the split explicitly; consolidated D/E alone is misleading for a holdco structure

### Core ROIC Excl. CWIP — For Incubation/Infrastructure Plays
Conglomerates in incubation mode — those building new infrastructure platforms — carry massive **Capital Work-in-Progress (CWIP)** on the balance sheet — capital deployed but not yet generating returns. Standard ROCE dilutes the return of operating assets.
- When `CWIP / Net Block > 0.2` (rough heuristic for incubation phase), compute **Core ROIC** = EBIT / (Capital Employed − CWIP − Cash & Equivalents)
- Core ROIC reflects the true return on operating assets; as CWIP commissions, headline ROCE should converge upward
- Use `calculate` for the math; cite both headline ROCE and Core ROIC in the report so the reader can see the gap
