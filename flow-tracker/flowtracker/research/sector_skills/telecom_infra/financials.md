## Telecom Infrastructure (Tower-Co) — Financials Agent

### Tenancy Ratio — The Core Economic Metric
Tenancy ratio (tenants per tower) is the single most important driver of tower-co economics. A tower has roughly the same fixed cost regardless of how many tenants occupy it — ground lease, power backup, maintenance, security are all largely fixed. That means each incremental tenant drops ~85% to tower-co EBITDA. Extract from `get_company_context(section='concall_insights')` or `sector_kpis`:
- Benchmark: tenancy starts at 1.0 at commissioning and reaches ~1.6-1.7x at steady state (Indus Towers FY26 ~1.62x is the industry-leading level). With the Indian market consolidated to three private telcos (Jio, Airtel, Vi) plus BSNL, a portfolio-wide ratio above ~2.0x is not achievable — treat any model assuming 2.5+ as an error
- Rising tenancy = operating leverage working; falling tenancy typically signals telco-customer consolidation (operator mergers, spectrum reallocation, weak-operator site exits) or site decommissioning
- A flat tenancy ratio with growing tower count masks economics — always analyze both together

### Rental Per Tenant — The Pricing Metric
Effective monthly rental per tenant (net of contracted discounts) is typically ₹35K-55K/month in India. Telco consolidation has suppressed rentals 20-30% from peak levels — telcos negotiating harder as their own sector has consolidated to three players. Any rental hardening in disclosures is a leading indicator that the telco sector is healing, which feeds back into tower-co bargaining power.

### MSA Renewal Cycle & Exit Penalties — Contracted Visibility vs Repricing Risk
Tower revenue sits on long-dated Master Service Agreements (MSAs). Two things to track from concalls and the annual report:
- **Renewal repricing:** Many MSAs signed 10-15 years ago hit renewal in the 2026-2027 cycle. With the telco customer base consolidated to an oligopoly, telcos have strong leverage to negotiate lower rental escalations on renewal — monitor management commentary on negotiated escalation rates and any renewal-driven rental resets.
- **Exit/lock-in revenue:** MSAs carry an "Exit Amount" penalty (Indus MSA Clause 19.2 / Schedule 5) payable when a tenant exits a site before term. One-off exit charges can flatter revenue/EBITDA in a churn quarter — separate recurring rental from exit-penalty income so you do not extrapolate a one-time settlement as run-rate.

### Churn — The Hidden Risk
Churn (tenants exiting per year via site decommissioning) is the hidden erosion that gross tower additions can mask. Extract from concall — telcos publish their own site rationalization plans and tower-cos report churn figures.
- Benchmark: <3% annual is healthy, 5-8% signals an active consolidation wave, >10% is structural loss
- High churn eats backlog even if headline tenancy looks stable — always net churn against gross additions

### Lease Liability Bifurcation — The IndAS 116 Trap
Under IndAS 116, long-term rental contracts sit as Right-of-Use (ROU) assets with offsetting lease liabilities on the tower-co balance sheet. This inflates reported EBITDA by shifting ground-rental expense out of opex into depreciation + interest below the EBITDA line.
- Reported IndAS 116 EBITDA margins for the Indian sector leader run ~52-55% (Indus Towers FY26), not 60-80% — a margin computed on total reported revenue is further depressed by the zero/negative-margin energy pass-through (see below); pre-IndAS comparable margins are lower again
- Pre-IndAS EBITDA = reported EBITDA − lease liability unwind (disclosed in notes)
- Always use the pre-IndAS number for peer comparison with global tower-cos on different accounting regimes to avoid apples-to-oranges errors. `get_fundamentals(section='cost_structure')` may surface lease costs separately

### Energy Pass-Through — Revenue But Not Margin
Diesel and power recovery from tenants is pass-through: cost in COGS, recovery in revenue. It is NOT margin-neutral — energy recovery typically runs at a negative margin (Indus Towers reported energy margins of roughly -3.6% to -5.2% across FY26 quarters) because of T&D losses, diesel pilferage, fixed-energy contract structures, and weather-driven outages. So energy both inflates headline revenue and dilutes the blended margin. Always compute EBITDA margin on core rental revenue (not total reported revenue) to get the true economic picture. Energy is typically ~35-40% of reported revenue in India (Indus Towers FY26: ~₹116bn of ~₹325bn) — extract the exact split from concall and watch energy-margin trends as a fuel-mix/solarization KPI.

### Receivables Concentration — Telco Payment Risk
Tower-cos have just 3-5 customers (telcos) and the book is highly concentrated. If any one customer — particularly a financially stressed operator — stretches payment terms or negotiates retrospective discounts, it hits cash flow immediately. Extract from `get_fundamentals(section='balance_sheet_detail')`:
- Receivable days >120 = stressed customer book
- Track one-time provisions for impaired receivables from any single stressed counterparty; such provisions often cluster over multiple quarters against the same name
- Customer-wise revenue concentration (if disclosed) matters more than for almost any other sector

### Cash Flow — Capex-Light, Distribution-Heavy
Mature tower-cos are structurally capex-light — maintenance capex ~5% of revenue. Any capex spike signals expansion (5G rollout, new circles, small cells) rather than recurring spend. Strong FCF normally funds high dividend payouts (70-90%) — but do NOT treat this as a static yield: Indian tower-cos suspend dividends entirely during anchor-customer stress and resume only once collections normalize (Indus Towers paid no dividend for ~3 years and resumed in FY26 after Vodafone Idea began clearing dues). Check `get_events_actions(section='dividends')` for the payout trend and tie any resumption/suspension to anchor-customer receivable collection commentary; a falling payout without a visible growth investment is a red flag.

### Balance Sheet — Leverage Is Structural, Not Distress
Global tower-cos routinely operate at 2.5-4x Net Debt/EBITDA, justified by long-dated contracted revenue with credit-worthy counterparties — comparable to utility leverage. India's dominant tower-co is far more conservative: Indus Towers runs at ~1.4x Net Debt/EBITDA (and well under 1.0x on a pre-lease basis), reflecting its reluctance to lever up while anchor-customer (Vodafone Idea) collection risk was elevated. Do not assume global leverage norms for Indian names. A sudden leverage rise usually signals acquisition, not distress. The real financial exposure is interest rate risk: always review debt maturity profile and the mix of fixed vs floating rate debt from `get_fundamentals(section='balance_sheet_detail')`.

### Tower Mix — Macro Towers vs Lean Towers / 5G Loading
Not all tower additions are equal. 5G rollout often does NOT require expensive new macro towers — much of it is "loading" 5G radios onto existing sites (incremental tenancy/co-location at high drop-through) or building "lean towers"/small cells that command lower rental but need far lower capex. Differentiate macro additions from lean/loading additions: lean towers and loading dilute average rental per tower yet boost ROCE, so a falling rental-per-tower can actually be margin/return-accretive. Pull the additions mix from concall before reading rental-per-tower trends as pricing weakness.

### Bharti Consolidation & Data-Centre Adjacency — Structural Shifts
Indus Towers is no longer a neutral-host independent: Bharti Airtel holds ~51% and consolidates Indus into its accounts from the Mar-2025 quarter (Vodafone Idea has been exiting its stake). This (a) tilts Indus toward a captive-Airtel relationship that can pressure neutral-host pricing for Vi/Jio, and (b) opens data-centre adjacency — Airtel has flagged intent to combine Indus with its Nxtra data-centre business. Track the consolidation/ownership trajectory and any tower-to-data-centre/edge expansion, as it changes both the counterparty-risk profile and the growth optionality versus a pure passive tower-co.

### Valuation
- **EV/EBITDA (adjusted for lease accounting)** is the primary metric — 8-12x at steady state, 6-8x during consolidation phases. Call `get_valuation(section='band', metric='ev_ebitda')` for historical context
- **P/E is distorted** by high depreciation + lease interest under IndAS 116 — avoid as a primary metric
- **Dividend yield** of 5-8% is common for mature tower-cos — they are a yield play more than a growth play. Compare against sector median and 10Y G-Sec yield
