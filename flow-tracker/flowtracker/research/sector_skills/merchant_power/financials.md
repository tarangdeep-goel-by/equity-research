## Merchant Power / IPP — Financials Agent

### Regulatory & Contractual Boundaries — Mandatory Lookup
**Before analyzing IPP economics, identify the regulatory regime each MW operates under. The same plant can earn very different economics depending on whether a MW is PPA-locked, merchant-exposed, or Section-11-dispatched.**

| Regime | Binding rule | Economic effect |
|---|---|---|
| **Long-term PPA (cost-plus)** | CERC Tariff Regulations — 15.5% base ROE on equity + two-part tariff (fixed capacity charge + variable energy charge) | Annuity-like, inflation-escalated, capped |
| **Long-term PPA (competitive bid)** | Bid-winning tariff (₹/kWh) + fuel pass-through where allowed | Margin compression risk if input costs outpace escalators |
| **Merchant (IEX / PXIL spot)** | Cleared at Market Clearing Price, but CERC caps the price: ₹10/kWh on standard DAM/RTM, ₹20/kWh on the High Price Day-Ahead Market (HP-DAM). No floor. | High upside in tight hours (capped at the ceiling), brutal in off-season |
| **Section 11 (Electricity Act)** | Government mandate (extraordinary circumstances) to run imported-coal/gas plants at full capacity and supply the grid; invoked in power crises | Not a below-market squeeze — CERC works out a benchmark rate covering all prudent costs (imported coal price, freight, O&M) plus a fair margin, overriding the fixed PPA tariff. Generally margin-neutral to positive. |
| **Import coal blending mandate** | Largely lapsed — MoP discontinued the mandatory imported-coal blending advisory beyond 15 Oct 2024 as domestic coal supply improved | Historical risk; no longer a forced USD-cost overhang unless re-invoked in a supply crunch |
| **Renewable bid tariffs** | Competitive reverse auctions (SECI, state DISCOMs) fix ₹/kWh for 25 years | No cost-plus — pure revenue fixed at auction |

Rule: state the MW-weighted regime mix BEFORE modeling earnings — a 2,000 MW plant with 1,500 MW PPA + 500 MW merchant is not the same asset as 500 MW PPA + 1,500 MW merchant.

### Merchant vs PPA Mix — The Volatility Dial
The single most important variable for an IPP is the split between merchant sales (sold into IEX/power exchanges at spot rates) and long-term PPA revenue (25-year fixed-tariff contracts with discoms, with inflation escalators). Merchant slice provides huge upside in tight markets and brutal downside in off-season; PPA slice is annuity-like but capped. Most IPPs run a 60-80% PPA / 20-40% merchant blend, and the merchant layer is where the optionality lives. A company labelled "merchant power" in the consolidated narrative may in fact earn 70% of revenue from PPAs — always verify the mix before drawing conclusions.
- Extract PPA vs merchant split from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`
- Flag as open question if split is not disclosed — the consolidated EBITDA is meaningless without it
- **Decompose merchant volume by exchange segment, not as one bucket.** Standard DAM/RTM clears under a ₹10/kWh cap; the High Price Day-Ahead Market (HP-DAM) — built for high-variable-cost generators (imported coal, gas, and price-taking BESS) — clears up to ₹20/kWh and routinely hits its cap in tight non-solar hours. An IPP with gas/imported-coal peaking capacity earns its peak realizations in HP-DAM, so blending it into a single ₹4-5/kWh average DAM number understates peak-hour economics. Ask which segment the merchant MW actually sells into.

### PLF vs PAF — Utilization vs Fixed-Cost Recovery (Do Not Conflate)
Two distinct metrics drive IPP economics, and they protect different parts of the P&L:
- **PAF (Plant Availability Factor)** = % of time the plant was *available* to despatch. Under CERC tariff norms, **fixed capacity charges are recovered against PAF, not PLF**. A plant meeting the Normative Annual Plant Availability Factor (NAPAF — 83% for coal under the 2024-29 regulations, reduced from 85%) recovers ~100% of its fixed costs *even at low actual generation*. So a plant at 85% PAF but 40% PLF still earns its full capacity charge.
- **PLF (Plant Load Factor)** = actual generation / (installed capacity × hours). It drives only the *variable* (energy) charge and any generation incentive (paid for scheduled energy above the normative PLF). Rising PLF without tariff compression is operating leverage; falling PLF points to fuel shortage (coal), seasonal weakness (renewables), or unscheduled outages.
- **Rule:** Model fixed-cost recovery off PAF/availability; model variable-charge and incentive off PLF. Treating low PLF as a fixed-cost shortfall is a modeling error for PPA-linked capacity.
- PLF benchmarks: coal thermal 70-85%, solar 18-22%, hydro 30-40% (highly seasonal), wind 22-28%
- Track PLF and PAF by fuel type if the portfolio is diversified — a blended number hides the story
- Source: `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`

### Tariff Realization — Decompose to Fixed + Variable
Indian power tariffs have two components: a **fixed charge** (capacity payment, earned if the plant is available regardless of despatch) and a **variable charge** (energy payment, earned per unit generated, meant to cover fuel + O&M). The fixed charge protects downside at low PLF; the variable charge compresses when fuel inflation outruns the pass-through lag.
- Extract tariff breakup by plant from `get_company_context(section='concall_insights')`
- A plant with high fixed-charge share is lower-risk but lower-upside; high variable-charge share leverages fuel cost movements

### Fuel Cost Pass-Through — The Margin Buffer
Under regulated PPAs, fuel cost is largely passed through on escalators with a 1-2 quarter lag. Merchant sales have no pass-through — the IPP absorbs 100% of fuel volatility (within the CERC price cap). During coal price spikes (e.g., 2022 international coal), merchant-heavy IPPs saw massive margin compression while PPA-heavy peers stayed steady. Note: the mandatory imported-coal *blending* directive lapsed after 15 Oct 2024, so it is no longer a structural cost overhang — but a Section 11 invocation (full-capacity run on imported coal/gas) comes with a CERC-determined cost-plus-fair-margin rate, so it is a margin support, not a squeeze.
- Check concall for pass-through lag disclosures and any residual imported-coal exposure
- Imported coal exposure is a material risk flag during commodity spikes (chiefly for merchant volume, where there is no pass-through)

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
Discom payment delays push receivable days higher and can stall cash conversion even when P&L looks healthy. The Late Payment Surcharge (LPS & Related Matters) Rules, 2022 have been strictly enforced — legacy discom dues to generators fell ~96%, from ~₹1.4 lakh crore in mid-2022 to ~₹4-5k crore by early 2026, via mandatory EMIs and exchange-access cut-off for defaulters. Counterparty risk is now mitigated but not eliminated: watch *current* (post-2022) dues, state subsidy reliance, and ageing — not the cleared legacy pile.
- Receivables > 6 months ageing is a red flag — extract ageing from working capital disclosures or concall
- Track receivable days trend quarter-on-quarter; sudden jumps usually precede a discom-specific crisis

### Valuation
- **EV/EBITDA**: primary metric. 7-10x for mature capacity is mid-cycle; <6x signals stress; >12x implies a strong expansion pipeline or unusual merchant exposure in a favourable cycle
- **P/B**: applicable given the capital-intensive asset base. 1.2-1.8x P/B is typical at mid-cycle
- **PE**: distorted by commissioning timing and fuel-pass-through accounting — avoid as a primary multiple
- Call `get_valuation(section='band', metric='ev_ebitda')` and `get_valuation(section='band', metric='pb')` for historical band context
