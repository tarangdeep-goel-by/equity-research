## Merchant Power / IPP — Financials Agent

### Merchant vs PPA Mix — The Volatility Dial
The single most important variable for an IPP is the split between merchant sales (sold into IEX/power exchanges at spot rates) and long-term PPA revenue (25-year fixed-tariff contracts with discoms, with inflation escalators). Merchant slice provides huge upside in tight markets and brutal downside in off-season; PPA slice is annuity-like but capped. Most IPPs run a 60-80% PPA / 20-40% merchant blend, and the merchant layer is where the optionality lives. A company labelled "merchant power" in the consolidated narrative may in fact earn 70% of revenue from PPAs — always verify the mix before drawing conclusions.
- Extract PPA vs merchant split from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`
- Flag as open question if split is not disclosed — the consolidated EBITDA is meaningless without it

### PLF (Plant Load Factor) — The Utilization Metric
PLF = actual generation / (installed capacity × hours in period). It is the cleanest measure of whether a plant is earning its keep. Rising PLF without tariff compression is operating leverage kicking in; falling PLF points to fuel shortage (coal), seasonal weakness (renewables), or unscheduled outages.
- Benchmarks: coal thermal 70-85%, solar 18-22%, hydro 30-40% (highly seasonal), wind 22-28%
- Track PLF by fuel type if the portfolio is diversified — a blended number hides the story
- Source: `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`

### Tariff Realization — Decompose to Fixed + Variable
Indian power tariffs have two components: a **fixed charge** (capacity payment, earned if the plant is available regardless of despatch) and a **variable charge** (energy payment, earned per unit generated, meant to cover fuel + O&M). The fixed charge protects downside at low PLF; the variable charge compresses when fuel inflation outruns the pass-through lag.
- Extract tariff breakup by plant from `get_company_context(section='concall_insights')`
- A plant with high fixed-charge share is lower-risk but lower-upside; high variable-charge share leverages fuel cost movements

### Fuel Cost Pass-Through — The Margin Buffer
Under regulated PPAs, fuel cost is largely passed through on escalators with a 1-2 quarter lag. Merchant sales have no pass-through — the IPP absorbs 100% of fuel volatility. During coal price spikes (e.g., 2022 international coal), merchant-heavy IPPs saw massive margin compression while PPA-heavy peers stayed steady. Also watch for Section 11 invocations and import coal blending mandates — these squeeze variable cost unpredictably.
- Check concall for pass-through lag disclosures and coal blending impact
- Imported coal exposure is a material risk flag during commodity spikes

### Gross Margin Per Unit — The Honest Metric
(Tariff received − variable fuel cost − transmission losses) per unit generated = **gross margin per unit**. This tracks real plant economics better than consolidated EBITDA margin, which mixes fuel pass-through revenue accounting and distorts the percentage. Benchmark for merchant-heavy players is ₹1.5-2.5/unit in good years; sub-₹1/unit is stressed.

### Cash Flow — Capex Phase vs Steady State
New plants consume massive capex for 2-3 years with negative FCF and routine commissioning delays. Operating plants throw off strong recurring FCF and enter a debt-paydown phase. The CFO trajectory should inflect upward as new capacity commissions.
- Source: `get_fundamentals(section='cash_flow_quality')` — look for CFO growth tracking commissioning schedule
- Persistent negative FCF after commissioning = execution problem, not a capex story

### Balance Sheet — Debt Load & Refinancing Risk
IPPs are typically 70-75% debt-financed at the project level. Interest coverage runs 1.5-2.5x during ramp and 3-5x at steady state. The main balance sheet risk is refinancing concentration — lumpy maturities in a single year can force a refi on unfavourable terms.
- Extract debt maturity profile from `get_fundamentals(section='balance_sheet_detail')`
- Check concall for any CERC/regulatory recasts — stranded assets sometimes receive regulatory relief that materially changes the credit picture

### Regulatory & Counterparty Risk
Discom payment delays push receivable days higher and can stall cash conversion even when P&L looks healthy. Late Payment Surcharge (LPSC) is theoretically compensatory but rarely collected in full.
- Receivables > 6 months ageing is a red flag — extract ageing from working capital disclosures or concall
- Track receivable days trend quarter-on-quarter; sudden jumps usually precede a discom-specific crisis

### Valuation
- **EV/EBITDA**: primary metric. 7-10x for mature capacity is mid-cycle; <6x signals stress; >12x implies a strong expansion pipeline or unusual merchant exposure in a favourable cycle
- **P/B**: applicable given the capital-intensive asset base. 1.2-1.8x P/B is typical at mid-cycle
- **PE**: distorted by commissioning timing and fuel-pass-through accounting — avoid as a primary multiple
- Call `get_valuation(section='band', metric='ev_ebitda')` and `get_valuation(section='band', metric='pb')` for historical band context
