## Insurance — Valuation Agent

### Sub-type Routing — Primary Multiple Is Not PE, And Is Not The Same Across Sub-types
The most common valuation error in insurance is defaulting to PE + EV/EBITDA and applying the same lens to life, general, and insurtech. Life-insurer earnings are distorted by actuarial reserve movements; general-insurer earnings swing with catastrophe years and float yield; insurtech marketplaces don't have an embedded-value concept at all. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- |
| **Life insurer** | Price-to-Embedded-Value (P/EV) + Implied VNB multiple on FY+1 VNB | PE on actuarial accounting earnings, EV/EBITDA (no EBITDA concept), DCF on a new-insurer (EV already is a DCF) |
| **General insurer** | P/B-ROE (Gordon) + underwriting-profit multiple | PE on a low-combined-ratio year (mean-reverts), EV/EBITDA, PE in a catastrophe year (hides mean-reverting float income) |
| **Standalone health insurer** | P/B-ROE at health-specific ROE + loss-ratio-normalised PE | PE on a low-loss-ratio year, general-insurer peer P/B (health retail has different LR/ER mix) |
| **Insurtech marketplace** | EV/Revenue + contribution-margin-based unit economics; reject EV-based and embedded-value approaches entirely | P/EV (no float, no in-force book), PE on trailing naive 3-yr avg margin during turnaround |
| **Reinsurer** | P/B-ROE normalised across the cat cycle | PE in a low-cat year, EV/EBITDA |

### Life Insurer — P/EV and Implied VNB Multiple
**P/EV = Market cap ÷ Embedded Value.** Typical range for Indian private life insurers is 1.8-3.2× on current EV. The forward equivalent carries EV one year forward by adding FY+1 VNB: `FY+1 P/EV = Market cap ÷ (current EV + FY+1 VNB)`. This is the per-year unwind multiple — the one-year-forward price you are paying per unit of embedded value after the next cohort of new-business value has been booked.

The **implied VNB multiple** isolates what the market is paying for the new-business engine rather than the in-force book:
`Implied VNB multiple = (Market cap − Embedded Value) ÷ FY+1 VNB`.
Typical range 15-35× at standard growth. Values above 45× imply the market is pricing in multi-year VNB acceleration without margin compression; values below 10-12× imply the market is treating the new-business engine as zero-growth. Both extremes are actionable setups.

Pull the 5Y P/EV historical band via `get_chart_data` or the valuation helper; normalize for the regulatory regime break (pre vs post-2023 EoM harmonisation) — do not smooth averages across the regime shift.

### Justified P/EV — Gordon Framework, Carry `g` Through
For a mature life insurer the Gordon framework is: `Justified P/EV = (ROEV − g) ÷ (CoE − g)`, where `ROEV` is the return on embedded value (operating, excluding MTM), `CoE` is the cost of equity, and `g` is the sustainable long-run EV growth rate. For Indian life insurers, realistic ranges: ROEV 12-18%, CoE 12-13%, g 10-14% (book retention × ROEV gives the steady-state rate).

**Always carry `g` through the formula.** Dropping it to zero is the most common error and under-estimates fair P/EV by 50-70% for an Indian compounder. Worked calibrations:

- Top-tier life insurer: ROEV 17%, CoE 12%, g 12% → Justified P/EV = (17−12)/(12−12) undefined; with CoE 13%, g 12% → (17−12)/(13−12) = 5.0×; with CoE 13%, g 11% → (17−11)/(13−11) = 3.0×. The 3.0× anchor is the defensible upper end.
- Mid-tier life insurer: ROEV 14%, CoE 13%, g 11% → Justified P/EV = (14−11)/(13−11) = 1.5×.
- Laggard: ROEV 12%, CoE 13%, g 10% → Justified P/EV = (12−10)/(13−10) = 0.67× — i.e., discount to EV is rational, not a bargain.

A 1-pp change in `g` moves the justified multiple by ~30-50%, so the growth assumption is as load-bearing as ROEV and CoE. If observed P/EV materially exceeds the justified level at realistic `g`, reverse-out what ROEV expansion the market is pricing in and stress-test whether product-mix shift supports it. Route the arithmetic through `calculate` with `ROEV`, `CoE`, and `g` as named inputs; pull CoE from `get_market_context(section='macro')` or the WACC helper.

### General Insurer — P/B-ROE Plus Underwriting Multiple
**Justified P/B = (ROE − g) ÷ (CoE − g).** For Indian general insurers, sustainable ROE sits 14-18% (float-income contribution materially boosts the underwriting-only number). A 102-108% combined ratio with 6-8% gross float yield typically produces mid-teens ROE even with a slightly loss-making underwriting line. Carry `g` through (10-12% for mature general insurers).

The second lens is the **underwriting-profit multiple**: separate underwriting result from investment income, since the latter is a duration-trade that mean-reverts to the G-sec curve plus a small credit spread. A general insurer whose trailing PE looks cheap on a peak float-income year is not genuinely cheap — the investment leg is unsustainable at those yields. In a catastrophe year the reverse holds — a PE spike on a combined-ratio-115% year is a mean-reverting pessimism signal, not a derating.

### Insurtech — Revenue Multiple and Contribution-Margin Unit Economics
For listed insurtech marketplaces (POLICYBZR / PB Fintech and similar), **reject embedded-value and P/EV entirely** — there is no float, no in-force book, no actuarial-reserve compounding. The business is a marketplace P&L. Primary lenses:
- **EV/Revenue on standalone insurance-broking revenue** — strip subsidiary drag (lending, direct insurance, new verticals) before applying the multiple. Typical range 4-10× for high-growth broking/marketplace franchises.
- **Contribution-margin path** — what share of incremental revenue is flowing to operating profit at current CAC? A marketplace where contribution margin is not improving 300-500 bps YoY at scale has a broken unit-economics thesis.
- **Implied LTV/CAC anchor** — justify the revenue multiple by showing LTV/CAC >2× is durable, not a one-time pull-forward.

### Turnaround Margin Baseline — Override the Naive 3-Year Average
**This is the POLICYBZR lesson from the valuation-eval run.** When a company has turned profitable recently (positive contribution margin in the last 4 quarters but loss-making in the 3-year historical average), the projection tool's naive 3-year average margin pulls in the loss years and produces negative EPS projections — an arithmetic artifact, not a business signal.

The override: when the stock is in a turnaround state (first 4-8 quarters after crossing into operating profitability), explicitly replace the 3-year average with **TTM margin or forward-consensus margin** as the projection baseline. Flag the override in the report — state "turnaround baseline applied; 3Y avg includes loss years and is not a guide to forward economics". Do not silently use the tool default. This applies to insurtech primarily but also to newly-profitable standalone health insurers after a loss-making build-out phase.

### Historical Band Context — Regime-Shift Caveats
A 5-10Y P/EV or P/B band via `get_chart_data` gives the long-arc context (current vs median vs trough-peak). Flag regime breaks, do not smooth over them:
- **Life insurers** — IRDAI 2023 EoM / commission-cap harmonisation reset VNB margin industry-wide in a single fiscal. Pre-2023 and post-2023 P/EV bands are not directly comparable; cite the regime in the narrative.
- **General insurers** — Motor TP de-tariffication cycle and any catastrophe-year cluster (e.g., FY16 Chennai floods, FY21 cyclones) create multi-quarter MTM and combined-ratio distortions that bend the band.
- **Insurtech** — pre-listing vs post-listing revenue scale and pre-contribution-margin-positive vs post-turnaround are structurally different regimes. Do not average across them.

### SOTP — Subsidiary Drag for Insurtech and Bank-Parented Insurers
For insurtech parents with lending, direct-insurance, or new-vertical subsidiaries, SOTP is the lever that re-rates the stock:
1. Call `get_valuation(section='sotp')` for the tool-computed view; if empty, fall back to `get_valuation(snapshot)` per subsidiary ticker and for unlisted subs apply sector multiples (life insurer sub: 1.5-3× EV; general insurer sub: 1.0-2.5× annual premium income; lending sub: 1.0-2.5× book).
2. Quantify subsidiary drag: subsidiary loss = consolidated PAT − standalone PAT. Present as ₹ Cr AND as % of consolidated revenue.
3. Apply a 20-25% holding-company discount on aggregate sub-value where parent is a platform.
4. Back out implied EV/Revenue on the **standalone** (ex-SOTP) broking franchise — this is what the market is really paying for the core platform.

For bank-parented life insurers (SBILIFE, HDFCLIFE, ICICIPRULI) the SOTP lives inside the parent bank, not inside the insurer — the standalone insurer's P/EV is the full valuation.

### Peer Premium / Discount Decomposition
If the stock trades at a P/EV or P/B premium vs sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into at most four drivers: (a) VNB margin spread vs peer for life insurers, or combined-ratio spread vs peer for general insurers, (b) persistency percentile (life) or loss-ratio percentile (general/health), (c) ROEV or ROE delta vs peer, (d) product-mix or channel-mix quality (protection share for life, retail-health share for health, standalone-broking share for insurtech). If (a) through (d) together do not account for more than half the observed premium, the multiple is vulnerable to mean-reversion.

### What Fails for Insurance — Name These Explicitly
- **Simple PE on trailing earnings (life insurers)** — hides product-mix, float-income, and persistency dynamics; the actuarial reserve movements dominate reported profit in a way that is not a business signal.
- **EV/EBITDA (all insurance sub-types)** — no EBITDA concept; premiums and claims reserves aren't an operating-cash cognate for the add-back.
- **DCF on a newly-listed life insurer** — Embedded Value is itself a DCF (present value of in-force plus adjusted net worth). Running a parallel DCF double-counts.
- **PE on a peak-float-income year (general insurers)** — investment-yield tailwind is mean-reverting; trailing PE looks cheap at cycle peaks and looks expensive in catastrophe years, neither is the signal.
- **Naive 3-year average margin for turnaround insurtech** — loss years drag the average and produce negative projections for a now-profitable business (the POLICYBZR pattern). Override with TTM or forward consensus.

### Data-shape Fallback for Valuation Inputs
When `get_valuation(section='sotp')` returns empty or misses recent IPOs (e.g., listed insurance subs separated from parent group), fall back to `get_valuation(section='snapshot', ticker=<sub>)` per subsidiary; for unlisted subs use the sector multiples listed above. When `get_fair_value_analysis(section='dcf')` returns empty for a life insurer, use the reverse-P/EV approach — solve for implied ROEV required to justify current P/EV at current CoE and realistic `g`. When `get_quality_scores(section='insurance')` does not return VNB margin / persistency / combined ratio, fall back to `get_company_context(section='concall_insights', sub_section='financial_metrics')` and cite the quarter; do not fabricate — the valuation agent's credibility depends on citing what management actually disclosed. If global peer context is missing, use `get_yahoo_peers` rather than parking the gap in Open Questions.

### Open Questions — Insurance Valuation-Specific
- "What FY+1 VNB and FY+1 EV were used to compute forward P/EV and implied VNB multiple, and from which disclosure quarter?"
- "Does the Gordon justified P/EV carry a realistic `g` (10-14% for Indian life), and what is the implied ROEV reverse-solved from the current market P/EV?"
- "For turnaround insurtech: what margin baseline was used for projections — TTM, forward consensus, or naive 3-year average that pulls in loss years?"
- "Does the current P/EV or P/B premium vs sector median reconcile with the VNB margin / combined-ratio / persistency / mix decomposition, or is there a residual multiple gap?"
- "If subsidiary drag is material, what sector-multiple range was applied to unlisted subs and what holding-company discount, and is the standalone (ex-SOTP) multiple the defensible anchor?"
