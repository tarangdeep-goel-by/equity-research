## Telecom — Valuation Agent

### Sub-type Routing — Primary Multiple Is EV/EBITDA, Not PE
Telecom is capital-intensive and heavily-levered with material non-cash intangible amortisation (spectrum), so PE is structurally distorted across peers. Defaulting to PE as the primary multiple is the most common framing error and produces mis-signalled peer comparisons. Route to the correct primary multiple by sub-type before loading comparables:

| Sub-type | Primary multiple | Secondary | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- | :--- |
| **Integrated wireless operator** | EV/EBITDA (10-14× through-cycle for Indian top-3) | OpFCF yield; spectrum-normalised PE | PE (spectrum-amortisation distortion), EV/Revenue (margin dispersion) |
| **Tower / passive infrastructure** | EV/EBITDA (12-16× — higher than wireless given contracted cash flows) | P/tenancy; dividend yield | PE (D&A-heavy, reports thin accounting profit) |
| **Wireline / FTTH** | EV/EBITDA (9-12×) at maturity; EV/Homes-passed pre-maturity | ARPU × penetration NAV | PE during build-out (losses distort) |
| **Enterprise B2B** | EV/EBITDA (10-14×) with contract-backlog premium | EV/Sales when EBITDA negative | Wireless peer PE (different business) |
| **5G FWA pure-play** | EV/Subscribers (NAV-like) pre-scale; EV/EBITDA post-scale | Cash runway months | PE (loss-making phase) |

For diversified telecom groups spanning multiple sub-types, SOTP each segment at its own multiple — a single consolidated EV/EBITDA collapses the tower-infra and enterprise premiums into the lower wireless multiple and under-prices the group.

### Per-Share Derivation — Target MCap ÷ Shares, NOT Target EV ÷ Shares
This is the single highest-leverage discipline in telecom valuation and the source of a 5-point grade hit in the prior valuation eval. The enterprise-value-to-equity-value bridge must be walked explicitly:

1. Compute **Target EV** = Target EBITDA × justified EV/EBITDA multiple.
2. Bridge to **Target MCap (equity value)**:
   `Target MCap = Target EV − Net debt − Minority interest + Investments in associates/listed subs`
   - Net debt for telecom must include AGR dues and deferred spectrum payments (see quasi-debt treatment in financials.md); these sit as current + non-current liabilities but behave as debt for valuation.
   - Minority interest is material when the listed entity holds partial stakes in towers, international subsidiaries, or enterprise carve-outs.
   - Investments in associates (especially listed subsidiaries like a separately-listed tower or enterprise entity) must be added at current market cap × stake %, not book.
3. Derive **Target per-share = Target MCap ÷ shares outstanding** (diluted, post any announced QIP / rights-issue allotment).

Do **not** compute `Target EV ÷ shares` — this includes the value of debt claims in the equity per-share number and systematically over-prices the stock. Route the arithmetic through `calculate` with `target_ev`, `net_debt`, `minority_interest`, `associate_investments`, and `diluted_shares` as named inputs so the bridge is auditable. Show every line of the bridge in the report; a collapsed "fair value = X" without the intermediate bridge is not defensible.

### Spectrum Amortisation Normalisation — When PE Is Used at All
Wireless operators amortise spectrum over 20-year-plus schedules, and accounting policies differ across peers (useful-life assumptions, straight-line vs usage-based, treatment of auction premia). Peer PE comparisons without normalisation are systematically mis-signalled. If PE is cited at all — typically as a sanity cross-check rather than a primary multiple — normalise it:
- Extract spectrum amortisation from notes-to-accounts (pull via `get_fundamentals(section='balance_sheet_detail')` or the auditor-note section of `get_company_context(section='filings')`).
- Recompute EPS adjusting spectrum amortisation to a consistent-across-peers schedule (e.g., 20-year straight-line on auction price paid).
- Peer-PE comparisons should use the normalised EPS, not reported EPS. State the normalisation in the report.

### OpFCF Yield — The Cash-on-EV Check for Capital-Intensive Telcos
OpFCF (Operating Free Cash Flow) = EBITDA − Capex — captures the real cash yield after network investment and is the honest cross-check on EV/EBITDA when capex is elevated. Use cases:
- **OpFCF / EV** — cash-on-EV yield; 3-6% is normal for mature Indian telcos, <3% is rich or peak-capex, >7% is cheap or signals capex cut (which may indicate under-investment).
- **OpFCF margin = OpFCF / Revenue** — trajectory of cash conversion; watch for the post-5G-peak-capex inflection from 10-15% to 20-25%.
- Pull OpFCF from `get_quality_scores(section='telecom')`; cross-check EBITDA and capex sourcing against `get_fundamentals(section='cash_flow_detail')`.

A report that states EV/EBITDA without also stating OpFCF yield is valuation-incomplete for telecom — the multiple alone doesn't reveal whether the EBITDA is reinvested into the ground or flowing to equity.

### SOTP for Integrated Groups — Separate Each Vertical at Its Own Multiple
For diversified telecom groups, SOTP is often the biggest valuation lever:
1. Call `get_valuation(section='sotp')` first for the tool-computed view.
2. For each **listed subsidiary** (separately-listed tower entity, separately-listed enterprise/tech entity, separately-listed international subsidiary), take market cap × parent stake %.
3. For each **unlisted vertical**: wireless at EV/EBITDA 10-14×; tower infra at 12-16×; enterprise at 10-14× (with SaaS-like premium for managed-services / cloud exposure); FTTH at 9-12×; digital/payments at revenue-multiple or contribution-margin basis.
4. Apply a **15-20% holding-company discount** to the aggregate sub-value (telecom HoldCo discounts are narrower than conglomerate discounts because the verticals are operationally interrelated and cross-sold).
5. Back out implied EV/EBITDA on the standalone wireless core — the market's real view of the core franchise.

If `get_valuation(section='sotp')` returns sparse subsidiary mapping, fall back to manual per-ticker `get_valuation(section='snapshot', symbol=SUB_TICKER)` calls — do not leave a listed subsidiary out of SOTP as an open question when the tool can resolve it.

### Justified EV/EBITDA — Anchor to Growth, Not to Historical Band Alone
Historical EV/EBITDA bands (5-10Y via `get_chart_data(chart_type='ev_ebitda')` where available, or constructed from EV series and EBITDA series) give context but do not justify the multiple on their own. The regime-break warning applies: post-2016-new-entrant-disruption and post-tariff-hike-cycle regimes are structurally distinct; smoothing across them produces a misleading median.

For a mature wireless franchise, the justified EV/EBITDA approximates `(1 − g/ROIC) / (WACC − g)` where `g` is the sustainable long-run EBITDA growth rate. Indian telecom `g` sits in 8-12% nominal (tariff-hikes + modest sub growth + data-monetisation). Carry `g` explicitly in the derivation — dropping it to zero under-estimates the fair multiple by 30-50%. Worked sensitivity: at WACC 11%, ROIC 18%, g of 10% → justified EV/EBITDA ~14×; at g of 7%, justified drops to ~10×. Route through `calculate` with `g`, `wacc`, `roic` as named inputs.

### Reverse-DCF and Implied-Growth Check
At current EV, what subscriber growth + ARPU growth is the market pricing in? Build the reverse-DCF using:
- Subscribers: baseline + assumed net-adds × tenure.
- ARPU: baseline + assumed hikes sequenced to the tariff-cycle.
- Capex: peak-5G phase then normalising to 15-20% of revenue.
- Terminal growth: 4-5% nominal (GDP-like).

If the implied ARPU path exceeds ₹350 or the implied subscriber growth exceeds 5% sustained for a mature market, the valuation is leaning on growth assumptions that are inconsistent with India's current tele-density curve. Document the implied path and stress-test it.

### Peer-Premium / Discount Decomposition
If the stock trades at an EV/EBITDA premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into at most five drivers: (a) ARPU delta — ₹15-25 of sustained ARPU advantage justifies 10-20% premium; (b) subscriber-market-share delta — 300-500 bps of share advantage justifies 10-15% premium; (c) spectrum-holding MHz × quality-band — premium coverage-band holdings justify a structural premium; (d) tower-tenancy-ratio delta (for tower-infra sub-type) — 0.2-0.3× tenancy-ratio advantage justifies 15-25% premium; (e) net-debt/EBITDA delta — 0.5-1.0× lower leverage justifies 10-15% premium via lower equity risk. If (a)-(e) together do not account for more than half of the observed premium, the multiple is vulnerable to mean-reversion and the bull case is leaning on re-rating rather than on operational advantage.

### What Fails for Telecom — Name These Explicitly
- **Simple PE on reported EPS** — spectrum-amortisation policy differences + one-off gains/losses (tower-monetisation, AGR-related provisions, forex on dollar-denominated debt) distort trailing EPS beyond peer comparability.
- **EV/Revenue** — EBITDA margin dispersion across sub-types (70-80% for towers vs 45-55% for wireless vs 25-35% for enterprise) is too wide for a single EV/Revenue multiple to be meaningful.
- **P/B** — telecom is asset-heavy but the productive asset is spectrum (amortised) and network (depreciated); book-value bears little relation to replacement or earnings power.
- **DCF with static capex** — capex is in a 5G-peak phase; using the peak-capex year as steady-state understates terminal FCF materially. Use a capex-normalisation curve (peak → steady state over 3-4 years).

### Data-shape Fallback for Valuation Inputs
When `get_valuation(section='band', metric='ev_ebitda')` returns a narrow window or empty, fall back to `get_chart_data(chart_type='ev_ebitda')` for the longer series; if that too is empty, construct the series from `get_valuation(section='history', metric='ev')` and `get_fundamentals(section='ebitda_history')` manually. When `get_fair_value_analysis(section='dcf')` returns empty for an Indian telecom, use reverse-DCF as primary rather than flagging it as an open question. Cite the source for each extracted multiple and always state the window length when citing "current vs historical median".

### Open Questions — Telecom Valuation-Specific
- "Has spectrum amortisation policy been normalised across peers before citing peer PE, and from which quarter's notes-to-accounts was the schedule extracted?"
- "Does the SOTP include the current market cap of listed subsidiaries (separately-listed tower / enterprise / international entities) at the parent's disclosed stake %, and what holdco discount was applied?"
- "Does the target per-share use `(Target EV − Net debt − Minority interest + Investments) ÷ diluted shares`, with AGR and deferred spectrum dues included in Net debt?"
- "At the current EV, what ARPU trajectory and subscriber-growth path does the reverse-DCF imply, and is that path consistent with the current tariff-cycle and tele-density curve?"
- "Is the current EV/EBITDA premium to sector median reconciled with the ARPU + market-share + spectrum-holdings + tenancy-ratio + leverage decomposition, or is there a residual multiple gap?"
