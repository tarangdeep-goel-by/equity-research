## Broker — Valuation Agent

### Sub-type Routing — Primary Multiple Is PE, Never EV-Based
The single most common valuation error for Indian brokers is defaulting to an EV/EBITDA or DCF-FCFE frame borrowed from industrials or consumer names. Broker balance sheets carry massive client float (settlement liabilities, margin deposits, MTF book) that is economically distinct from the broker's own capital. EV calculations treat this float as debt and distort enterprise value by multiples of the real capital base. FCFE calculations route client-money flows through CFO and produce volatile, meaningless cashflow series. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- |
| **Discount broker** | PE on through-cycle active-client monetisation + Market cap per active client | EV/EBITDA on F&O-peak year, DCF/FCFE (client float corrupts CFO), P/B (book is float) |
| **Full-service broker** | PE on normalised earnings + P/AUA (% of assets-under-advisory) | EV/Revenue (float distorts EV), peer PE at different monetisation mix |
| **Wealth / PMS** | PE + P/AUM (% of AUM, typically 4-8%) | EV/EBITDA (performance-fee-spike year mean-reverts), DCF (AUM flows volatile) |
| **Bank-owned broker** | PE on through-cycle + SOTP contribution to parent | Standalone P/B (captive franchise is not book-driven) |
| **Depositary participant** (CDSL, NSDL) | PE on stable transaction-fee base + EV/Revenue (monopoly take-rate) | P/B (low book, high float), peer broker PE (DP is utility-like, not cyclical) |

### Why FCFE and DCF Fail for Brokers — State This Explicitly
Client float distorts CFO. Settlement obligations to/from clients flow through operating cash flow and swing by ₹thousands of crores quarter-to-quarter based on trading activity and settlement-day timing, unrelated to the broker's earnings quality. FCFE models produce false-precision terminal values that bear no relationship to distributable cash. A broker's real distributable cash is closer to `PAT − required regulatory capital build − MTF book growth × equity-funding share`; this is not what a mechanical CFO-based FCFE will give. The eval-cycle lesson is: reject FCFE outputs outright for brokers, and use normalized through-cycle PE or active-client-based valuation instead.

### PE on Through-Cycle Monetisation — The Primary Frame
Broker earnings are cycle-sensitive; trailing PE on a F&O-peak year looks optically cheap while PAT mean-reverts on the next SEBI tightening. The correct frame:

- **Normalize F&O ADTV to 70-80% of the 2024 peak** as the mid-cycle reference. The 2024 level captured peak retail options participation before lot-size and margin-rule tightening compressed volumes 20-30%.
- **Normalize activation rate to the trailing 3Y average**, not the current quarter.
- **Strip one-off items**: IPO expenses, ESOP one-time charges, exceptional MTF write-offs, treasury gains on float investment.
- **Apply sector-skill PE band**: 15-25× through-cycle PE for Indian brokers. >30× requires demonstrable structural growth (new products, institutional expansion, wealth/PMS scale-up) not cyclical peak.

Call `get_valuation(section='band', metric='pe')` for the historical PE band and `get_chart_data(chart_type='pe')` as the deep-history fallback when the band call returns fewer than 20 quarterly observations. State the regime break explicitly when citing "current vs 5Y median PE" — pre-2021 retail-participation regime and post-2024 SEBI-regime are structurally distinct; averaging across them produces a misleading median.

### Market Cap Per Active Client — The Second Frame
Comparable to platform businesses, a broker's market cap divided by 12-month active clients gives a per-client valuation number that cross-sectionally benchmarks monetisation efficiency. Typical Indian peer range: ₹3-8 lakh per active client across discount / full-service / hybrid names.

- A broker at ₹4L per active client vs peer ₹7L either has **lower ARPU**, **lower expected activation-rate durability**, or **lower product-breadth monetisation** — decompose rather than asserting "undervalued".
- A broker at ₹8L per active client vs peer ₹4L either has **superior ARPU** (advisory, PMS, MTF-yield), **superior product-breadth** (wealth layer), or **cycle-peak overpayment** — stress-test against the through-cycle ARPU.

Call `calculate` with `market_cap`, `active_clients`, and peer comparable values as named inputs. This frame is especially useful for pre-IPO / recently-listed brokers where historical PE band is thin.

### Per-AUM Valuation for Wealth and PMS
For wealth / PMS-tilted brokers, P/AUM (market cap as % of total AUM or AUA) is a useful cross-section. Indian listed wealth-managers trade in the 4-8% P/AUM band for standalone PMS; bank-owned wealth arms are harder to isolate without SOTP. The structural floor: a mature wealth franchise at 1.0-1.5% annual fee yield and 40-50% PBT margin supports a 5-7× multiple on fee-income, which maps to roughly 5-7% P/AUM.

### Peer-Premium / Discount Decomposition
If the broker trades at a PE premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose into at most four drivers: (a) **ARPU delta** — higher revenue per active client justifies 10-20% PE premium per ₹1,000 ARPU advantage sustained, (b) **activation-rate delta** — 5-10pp activation advantage justifies 10-15% premium, (c) **product-breadth delta** — presence of wealth/PMS/distribution layer justifies 15-25% premium vs pure-execution peer, (d) **balance-sheet margin-funding yield** — a deep MTF book with stable spread adds a stable earnings leg worth a 5-10% multiple uplift. If (a) through (d) together don't explain more than half the observed premium, the multiple is leaning on re-rating rather than earnings, and is vulnerable to mean-reversion on the next regulatory or volume shock.

### SEBI Regulatory Overhang as a Multiple Discount
Post-2024 SEBI tightening is not a one-off; the regulatory direction is an ongoing compression on retail-options participation, margin-rule enforcement, and true-to-label expense disclosure. A broker with >75% F&O revenue concentration should carry a **10-20% multiple discount** to peer median until the sub-type demonstrates cash-segment depth or alternative monetisation. This is a structural, not cyclical, discount — do not smooth it over with "SEBI-normalized" earnings.

### Sector-Skill Band and Threshold Ranges
- **Through-cycle PE band**: 15-25× for mature Indian brokers.
- **Wealth / PMS PE band**: 20-30× (annuity-like fee income carries a premium).
- **Depositary participant band** (CDSL, NSDL, duopoly): 30-45× (utility-like duopoly premium, regulated rates).
- **P/B as secondary check**: brokers should trade at a premium to book (2-4× typical) because fee income is capital-light; banks' P/B anchor does not apply.
- **>30× PE requires evidence-of-growth**: named new products, disclosed institutional-expansion pipeline, documented wealth-book scale-up — not cyclical peak extrapolation.

### What Fails for Brokers — Name These Explicitly
- **EV/EBITDA** — client float in EV inflates enterprise value by multiples of real capital; EBITDA mixes proprietary earnings with float-linked interest income.
- **DCF / FCFE** — client-money flows through CFO corrupt the free cashflow series; terminal value is false-precision.
- **Trailing PE on F&O-peak year** — mean-reverts on the next SEBI tightening cycle.
- **P/B** — book is largely float (client margin, settlement balances, MTF funded by own + borrowed capital); book value is not a valuation anchor for fee-income franchises.
- **Peer PE at different monetisation mix** — discount-broker PE vs full-service PE at the same number conceals different durability profiles.

### Data-shape Fallback for Valuation Inputs
When `get_valuation(section='band', metric='pe')` returns `status='schema_valid_but_unavailable'` or fewer than 8 quarterly observations, fall back to `get_chart_data(chart_type='pe')` for deep history and `get_fundamentals(section='income_statement')` for trailing-4Q EPS reconstruction. For the market-cap-per-active-client frame, the active-client count extraction follows the same fallback as business.md: `get_company_context(section='sector_kpis')` then `section='concall_insights', sub_section='operational_metrics')`. Cite the source quarter for every extracted number. If F&O vs cash split is unavailable, state that through-cycle PE cannot be computed rigorously and flag as an Open Question rather than imputing from peer averages.

### Open Questions — Broker Valuation-Specific
- "What was the F&O ADTV peak in FY24 and the normalized through-cycle mid-point (70-80% of peak) used for earnings normalisation? Is the current year trailing PE being compared against the peak-year or normalized earnings?"
- "What is market cap per 12-month active client for this broker, and how does it compare with 2-3 named peers in the same sub-type?"
- "Does the current PE premium to sector median reconcile with the ARPU + activation-rate + product-breadth + MTF-spread decomposition, or is there a residual multiple gap?"
- "Is any SEBI regulatory overhang (weekly-expiry rationalisation, further margin tightening, TER/true-to-label rulings) in consultation that would warrant a further multiple discount?"
- "For bank-owned brokers: what is the standalone broker SOTP value vs consolidated parent-bank P/B? Is the captive revenue being double-counted in the parent's valuation already?"
