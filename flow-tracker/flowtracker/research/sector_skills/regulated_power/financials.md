## Regulated Power — Financials Agent

### Regulatory Parameters — Mandatory Lookup Before Modeling Returns
**Before analyzing earnings, identify which CERC/SERC normative parameters bind. Applying the wrong benchmark turns a "above-normative incentive" story into a "sub-normative penalty" story (or vice versa).**

| Regulated parameter | Binding normative level | Source / rule |
|---|---|---|
| **Base ROE on equity** | **15.5%** on regulated equity portion (pre-tax 19.36% grossed up) | **CERC Tariff Regulations** (current 2024-29 block) |
| **Notional D/E gearing** | **70:30** debt-to-equity project-cost basis | CERC normative — over-equitization drags blended ROE toward debt yields |
| **Station Heat Rate (SHR)** — thermal | ~2,350–2,450 kcal/kWh (supercritical); ~2,450–2,550 (subcritical) | CERC per plant vintage + fuel type |
| **Auxiliary Power Consumption (APC)** | ~5.5-7.5% of gross generation (coal); ~1-2% (hydro) | CERC norms |
| **Plant Availability Factor (NAPAF)** | ~85% target; incentive above, under-recovery below | CERC |
| **Return on renewable capacity (solar/wind)** | **bid-tariff-linked** (competitive reverse auctions) — not a cost-plus regime | SERC-approved PPAs |
| **Working capital normative** | 2 months O&M + 2 months receivables + 15 days fuel | CERC |

Rule: state the binding normative value for the plant vintage/fuel type BEFORE claiming incentive or penalty. An SHR of 2,400 is incentive-earning for a subcritical plant and penalty-earning for a supercritical one — same number, opposite conclusion.

### Regulated ROE Framework
Regulated utilities earn a guaranteed ROE on equity invested in regulated assets. The actual return can exceed the base ROE through incentives:
- **CERC base ROE**: currently 15.5% on equity portion of regulated assets
- **Incentive income**: earned through Plant Availability Factor (PAF) above normative levels, fuel efficiency, and ash utilization
- Extract PAF and incentive income from `get_company_context(section='concall_insights')` — this is the key driver of above-base returns
- If PAF data unavailable, flag as open question

### Revenue Is Not a Growth Metric
- Regulated revenue = fuel cost passthrough + capacity charges. Fuel cost passthrough inflates/deflates revenue without affecting profit
- Focus on **capacity charges** (the regulated return component) and **incentive income** as the real profit drivers
- Capacity addition (MW) is the growth metric, not revenue growth

### Receivables & SEB Risk
- State Electricity Boards (SEBs) are often slow payers. Track receivable days carefully
- If receivables > 90 days of revenue, analyze by counterparty if available from concall_insights
- Late payment surcharge (LPSC) income can be material — check if it's in Other Income

### Capex Cycle
- Regulated capex earns guaranteed returns — more capex = more regulated equity base = more profit
- Track capex pipeline (MW under construction) from concall_insights
- Green/renewable capacity additions vs thermal — the transition trajectory

### Regulatory Deferral Account Balances — PAT Can Outrun Cash
Under IndAS 114, disputed tariff claims (truing-up, change-in-law, fuel surcharge under-recoveries pending CERC/SERC approval) are booked as **Regulatory Deferral Account (RDA)** debit balances — revenue is recognized today even though cash collection is years out and subject to regulatory ruling. This creates a real EPS vs CFO divergence that consolidated ratios mask:
- Extract RDA debit balance and YoY movement from `get_fundamentals(section='balance_sheet_detail')` and notes in `get_company_context(section='filings')`
- Growing RDA balance alongside flat CFO means a rising share of reported profit is not cash — earnings quality is degrading even if headline PAT grows
- Call out any RDA balance > 10% of annual revenue as a material forward cash risk, and flag any specific disputed regulatory order that underpins a large RDA slab
- Cross-check CFO/PAT via `get_fundamentals(section='cash_flow_quality')` — persistent sub-80% conversion for a regulated utility is RDA buildup until proven otherwise

### CWIP / Gross Block Ratio + Commercial Operation Date (COD)
**CWIP earns zero ROE until the plant achieves COD and enters the regulated asset base.** Regulated utilities often carry large CWIP balances during build phases; each month of delay accumulates Interest During Construction (IDC) and destroys equity IRR on the project.
- Compute **CWIP / Gross Block** — rising ratio means capital parked outside the earning base; falling ratio means commissioning is running
- Track **COD slippage** from `get_company_context(section='concall_insights')` — commissioning delays of 6+ months against original timeline warrant flagging. For a ₹10,000 Cr project, a one-year delay at 11% WACC can burn 300-500 bps of project equity IRR
- Capitalized borrowing cost during CWIP (IDC) inflates the asset value that eventually enters the regulated base — rechecked at truing-up, so aggressive capitalization can be disallowed later
- Pipeline of MW under construction is the real forward-growth signal; a utility with zero CWIP is in harvesting mode, not growth mode

### SHR / APC / SFOC Benchmarking — The Normative Efficiency Parameters
Regulated tariffs include normative operating parameters for thermal plants: **Station Heat Rate (SHR)** — kcal/kWh, **Auxiliary Power Consumption (APC)** — % of gross generation, **Specific Fuel Oil Consumption (SFOC)** — ml/kWh, and **Plant Availability Factor (PAF)**. Performance **above** normative earns incentive; performance **below** normative triggers non-recoverable cost leakage — the operator eats the inefficiency.
- Extract actual SHR, APC, SFOC, PAF, NAPAF from `get_company_context(section='concall_insights')` or regulatory filings
- Compare against normative (disclosed by CERC per plant vintage and fuel type) — any breach below normative is a structural margin drag, not a one-time event
- Benchmark against peer plants via `get_peer_sector(section='benchmarks')` — a plant running 2 kcal/kWh above peer SHR is thermodynamically less efficient and structurally disadvantaged
- PAF shortfalls specifically cause under-recovery of fixed charges, which compound quarterly — always model the downside on base ROE, not just the upside from PAF incentives
