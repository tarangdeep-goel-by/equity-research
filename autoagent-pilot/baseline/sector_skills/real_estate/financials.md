## Real Estate — Financials Agent

### Regulatory Boundaries — Mandatory Lookup Before Liquidity / Revenue Analysis
**Before analyzing cash flow, free cash, or revenue trajectory, identify the binding regulatory constraints. Ignoring them will overstate financial flexibility by large multiples.**

| Constraint | Binding rule | Economic effect |
|---|---|---|
| **RERA escrow lock-up** | **70% of customer collections** must be held in a project-specific escrow, released only for that project's construction | Headline cash overstates fungible cash; 70% is not available for debt reduction, dividends, or cross-project deployment |
| **Ind-AS 115 revenue recognition** | Revenue booked only at substantial completion + possession — NOT at booking/collection | Reported revenue lags business momentum by 2-3 years |
| **JDA revenue share** | 40-60% of project revenue is due to the land contributor under Joint Development Agreements | Developer's reported margin is lower than outright-land peers — NOT a profitability gap, just structure |
| **Capitalized borrowing cost** | Interest on construction loans is capitalized into WIP inventory (IndAS 23) | P&L interest expense understates true debt burden; real ICR = EBIT / (P&L interest + capitalized interest) |
| **Project-specific SPV ring-fencing** | Each project is typically housed in a separate SPV; project-SPV debt does not automatically cross-guarantee | Aggregate consolidated debt hides per-project distress concentration |

Rule: state the RERA escrow balance and JDA share BEFORE claiming "free cash" or "net debt reduction capacity." Total cash ≠ fungible cash.

### P&L Revenue Is Backward-Looking — Why It Misleads
Under Ind-AS 115 (project completion method), revenue is recognized only when the project is substantially complete and possession is given. This means:
- **Reported revenue** reflects projects completed 2-3 years ago, not current business momentum
- A company can be selling aggressively today but show flat/declining revenue because completions haven't caught up
- Drawing conclusions about business trajectory from P&L revenue alone will produce wrong analysis

### The Real Metrics — Pre-Sales and Collections
Because P&L revenue lags reality by years, the actual business metrics live in concall disclosures. Call `get_company_context(section='concall_insights')` and `get_company_context(section='sector_kpis')` — without these, the report is analyzing backward-looking noise rather than current momentum.
- **Pre-sales (Booking Value in ₹ Cr)** — current demand signal. This IS the revenue equivalent for real estate
- **Pre-sales Volume (mn sq ft)** — physical demand, strips out ASP inflation
- **Collections (₹ Cr)** — cash actually received from customers. Compare to pre-sales for collection efficiency
- **Net Debt** — the most important balance sheet metric. Track absolute reduction over time

**Data-shape fallback:** if `get_sector_kpis(sub_section='pre_sales_value_cr'|'collections_cr'|'gdv_pipeline_cr'|'unsold_inventory_months')` returns `status='schema_valid_but_unavailable'`, the extractor has not captured that canonical KPI for this developer. Fall back to narrative extraction via `get_company_context(section='concall_insights', sub_section='management_commentary')` and `sub_section='operational_metrics'` — developers typically discuss quarterly pre-sales and collections prominently in opening remarks. Cite the specific quarter and verbatim figure source. Never omit pre-sales from a real-estate financials report because the structured tool lacked it — the narrative contains it.

### Cash Flow Is King
- Compare **Operating Cash Flow** against **Collections**. OCF should track collections closely
- If OCF << Collections, the company is burning cash on new land/construction faster than collecting
- Track Net Debt reduction as the primary measure of financial health. Real estate deleveraging = equity value creation

### What Structured Tools CAN Tell You
- `get_fundamentals(section='balance_sheet_detail')` — borrowing structure, cash position, net debt
- `get_fundamentals(section='cash_flow_quality')` — OCF trajectory, capex (land + construction)
- `get_fundamentals(section='working_capital')` — advances from customers (a GOOD sign in real estate = money collected before completion)
- `get_quality_scores(section='realestate')` — pre-computed real estate metrics if available

### Skip or Heavily Adapt Standard Frameworks
- **DuPont decomposition is misleading** — margin × turnover × leverage computed on Ind-AS 115 revenue produces meaningless numbers. If you include DuPont, compute it on pre-sales (from concalls) not reported revenue
- **Standard earnings quality checks** (CFO/PAT, accrual ratio) are distorted by project-based cash flows — advances from customers inflate CFO, completion timing distorts PAT

### Forward-Looking Metrics (from concall_insights)
- **GDV (Gross Development Value) of launch pipeline** — total potential revenue from planned launches. This is the growth signal
- **Unsold inventory** — in months (unsold units / monthly absorption rate). >18 months = oversupply risk, <6 months = pricing power
- **Realization per sq ft** — ASP trend. Rising realization = pricing power or product mix shift to premium

### Valuation — NAV Is The Primary Metric (Don't Default to PE/PB)
- **P/E is misleading** due to lumpy Ind-AS 115 revenue recognition — a company completing a project spikes PAT; one in buildout shows compressed margins
- **NAV (Net Asset Value) is the institutional standard** for real estate: sum land bank market value + ongoing project GDV × margin − net debt − contingent liabilities
- If full NAV build-up isn't available from tools, at minimum compute **Price-to-NAV** using the **GDV of launched + to-be-launched pipeline** (from `concall_insights` sub_section='operational_metrics') as the NAV proxy. A report that cites only P/E and P/B for a real estate developer is incomplete
- **EV/Pre-sales** or **Mcap/Pre-sales** as a secondary proxy for PE when pre-sales is the current momentum signal
- Net Debt / Equity is the risk metric — >1.0x is elevated for Indian developers
- If Net Debt/EBITDA > 2x, analyze debt maturity from `get_fundamentals(section='balance_sheet_detail')`

### Cost of Debt — Mandatory for Leveraged Developers
Real estate is structurally leveraged (project loans, construction finance, lease-rental discounting). Cost of debt is a major earnings driver — a 50 bps shift at 2x Net Debt/Equity moves PAT by 3-5%.
- Compute **weighted average cost of debt** = interest expense / average total borrowings. Extract interest expense from `get_fundamentals(section='annual_financials')`; borrowings from `balance_sheet_detail`
- Track 3-year trajectory — rising rate environment compresses margins; post-RBI-cut cycle typically compresses funding cost by 50-100 bps with a 6-12 month lag
- Compare to sector peers via `get_peer_sector(section='benchmarks')`

### Borrowing Costs Capitalized Into WIP Inventory
Under IndAS, interest on construction loans is capitalized into **Work-in-Progress inventory** rather than hitting the P&L. This legally understates reported interest expense while the true debt burden sits on the balance sheet as inventory cost to be released when flats are sold and revenue is recognized.
- **P&L interest expense** is a lower-bound, not the total interest burden — the real number is P&L interest + capitalized interest
- Extract capitalized borrowing cost from `get_company_context(section='filings', sub_section='notes_to_accounts')` — typically disclosed in inventory notes or finance cost notes
- Headline **Interest Coverage Ratio** (EBIT / interest expense) looks artificially healthy when large amounts are being capitalized; compute an **adjusted Interest Coverage** = EBIT / (P&L interest + capitalized interest) to get the real picture
- A developer with rising capitalized interest while P&L interest looks flat is masking interest-burden growth — flag this

### JDA vs Outright Land — Structurally Different Economics
Indian real estate projects follow two structures with opposite financial signatures, and peer comparisons that don't adjust for this are meaningless:
- **Outright land purchase** — developer owns 100% of project economics, margins are higher (25-35% EBITDA), but ROCE is compressed because capital sits in land for 3-5 years
- **Joint Development Agreement (JDA)** — land owner contributes land in exchange for a revenue share (typically 40-60%); developer's capital requirement is slashed, ROCE jumps, but reported margins compress because the land-share is booked as cost
- A JDA-heavy developer showing lower margin than an outright-land peer is not less profitable — just asset-light. Peer margin/ROCE comparisons must adjust for this mix
- Extract project-structure mix from `get_company_context(section='concall_insights')` — management often discloses JDA % of launches or pipeline

### RERA Escrow Lock-Ups — Total Cash ≠ Fungible Cash
Under RERA, **70% of customer collections** must sit in a **project-specific escrow account**, released only for that project's construction. This is not available for debt reduction, dividends, or cross-project deployment. Consolidated cash balances therefore materially overstate financial flexibility:
- Separate **RERA-escrowed cash** from **free cash** when analyzing liquidity. Disclosed in `get_fundamentals(section='balance_sheet_detail')` and project-level notes in filings
- Net Debt reduction potential is limited to free cash, not total cash — a developer with ₹5,000 Cr headline cash of which ₹4,000 Cr is escrowed has only ₹1,000 Cr to deploy against debt

### Related-Party Advances / Unconsolidated JV Land Entities
Promoter-owned land-holding SPVs, unconsolidated joint ventures for land aggregation, and related-party advances are recurring governance leakage points in Indian real estate. Capital flows out to these entities disguised as "securing land rights" and may never return to minority shareholders on market terms.
- Check `get_company_context(section='filings', sub_section='related_party_transactions')` for advances to promoter entities and unconsolidated JVs
- Loans & advances spikes in standalone balance sheet often originate here — cross-reference with `get_fundamentals(section='balance_sheet_detail')`
- Flag when related-party exposures > 5% of net worth or when these balances grow faster than consolidated assets — both are governance signals, not operational growth
