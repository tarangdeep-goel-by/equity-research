## Platform — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
"Platform" is an umbrella hiding at least seven economically distinct digital businesses. Revenue engine, dominant axis, unit of production, and cohort behaviour diverge so sharply across sub-types that applying a "marketplace" framework to a 1P-inventory quick-commerce operator (or a "pure-commission" lens to a payments aggregator) inverts the diagnosis. State the sub-type and its primary revenue engine before decomposing growth.

| Subtype | Revenue model | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **Food-delivery marketplace** | 3P commissions + delivery-fee + platform-fee + ad-tech | frequency × take-rate | order (2-4/month/MAU at scale) |
| **Quick-commerce (10-30 min)** | 1P inventory margin + ad-tech take | frequency × AOV × dark-store density | order (3-6/month/MAU at maturity) |
| **E-commerce horizontal marketplace** | 3P commissions + ad-tech + fulfilment-fee; hybrid 1P/3P common | GMV × take-rate × ad-load | order, active-buyer |
| **E-commerce vertical (beauty, fashion)** | Hybrid 1P/3P with curation premium; private-label mix-shift | category-depth × take-rate | order, new-vs-repeat customer |
| **Mobility / ride-hailing** | Per-trip commission on driver-partner fares | trips × take-rate × utilisation | trip, active driver-partner |
| **Payments / fintech** | TPV × MDR + fees (PPI, lending distribution, merchant services) | TPV × MDR × diversification | transaction, merchant, MAU |
| **Insurtech distribution** | Distribution commission on premium sold + renewal trail | premium × commission × persistency | policy sold, renewal cohort |
| **Edtech** | Subscription ARPU or course fee | subscribers × ARPU × months | paid subscriber, completion rate |
| **Travel aggregator** | Take-rate on booking volume + ancillary attach | booking volume × take-rate × attach | booking, active traveller |

### Revenue Decomposition — Always (A × B), Never a Single Line
Platform revenue is not GMV. **Take-rate is the critical mediator.** For a 3P marketplace: `Revenue_3P = GMV × take-rate + ad-load × DAU × ad-CPM`. For 1P inventory: `Revenue_1P = orders × AOV × (1 − platform-discount)` — here reported revenue equals GMV, so EV/Revenue on a 1P peer is comparable to EV/GMV on a 3P peer only after normalisation (see valuation.md). For subscription: `Revenue = Subscribers × ARPU × months × retention`. For payments: `Revenue = TPV × MDR + platform-fee + lending-fee + float-yield`. For mobility: `Revenue = trips × AOV × take-rate × driver-partner fill-rate`. Platforms mid-transition between 1P and 3P accounting (or gross-vs-net revenue recognition) will show reported growth that is mostly an accounting optic — strip the accounting effect via concall-disclosed GOV / GMV before claiming real growth. Call `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')` for the decomposition.

### Moat Typology — Distinct by Sub-type
A food-delivery moat is not a payments moat is not a quick-commerce moat. Enumerate the moat lens that applies to the sub-type before asserting "durable franchise":
- **Network effects (two-sided)** — marketplaces compound when more merchants attract more users which attract more merchants. Food-delivery and horizontal e-commerce are classic two-sided; the #1 and #2 by order-share are usually structurally protected, the #3+ tend to be capital-dependent.
- **Logistics / dark-store density** — for quick-commerce, 10-30 min SLAs require dark-store counts per city above a threshold (roughly 50-100 stores for a top-8-metro presence). Once built, the fixed-cost amortisation is a moat; before it, it is a cash-burn engine.
- **Brand + CAC efficiency** — platforms with high organic-share (direct-app opens, branded-search traffic) spend materially less on performance marketing per active user. Track blended CAC vs paid-CAC.
- **Merchant-stickiness** — once a merchant's catalogue, fulfilment, and ad-spend are integrated, switching cost is high. Merchant churn rate is the telemetry.
- **Category-depth** — vertical marketplaces (beauty, fashion) monetise via private-label mix-shift and curation, not take-rate alone.
- **Behavioural inertia** — app-open frequency creates a default-choice habit that survives feature parity from competitors.

### Unit Economics — Contribution Margin Per Order Is the Signal
Aggregate revenue growth without contribution-margin-per-order improvement is a cash-burn thesis wearing a growth mask. Benchmarks by sub-type:
- **Food-delivery at scale** — contribution margin per order 2-6% of GMV; at 4%+ and rising, operating leverage to EBITDA positive within 4-6 quarters.
- **Quick-commerce** — contribution margin per order turned positive in 2024 for category leaders; -1% to +2% of GMV is the current range; dark-store throughput (orders per store per day) is the proximate lever.
- **E-commerce horizontal** — contribution margin 5-10% post-fulfilment; private-label and ad-tech mix expand it.
- **Mobility** — contribution margin 3-7% of GMV; utilisation (trips per driver-hour) and surge-pricing discipline drive it.
- **CAC payback** — 12-36 months is the target band for sustainability; >36 months on blended CAC at steady state signals either low LTV or adverse selection.
- **LTV/CAC** — target >2.5-3× for steady-state economics; <2× means the platform is buying revenue, not building a franchise.
- **Order-frequency** — mature food-delivery 2-4 orders/month/MAU, quick-commerce 3-6 at maturity, e-commerce horizontal 1-2 orders/month/active-buyer.

Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')`. If operational_metrics returns aggregate-only data, derive per-order metrics via `calculate` using order count and segment revenue.

### Capital-Cycle Position — Platforms Are in Discipline Regime
The Indian platform cohort moved through three phases: 2020-22 growth-at-any-cost (venture-backed CAC spending, contribution-margin-negative at scale), 2023-24 unit-economics pivot (post-tech-winter capital discipline, layoffs, marketing cuts), 2024-25 path-to-operating-profitability (EBITDA-positive trajectory becomes the default expectation). Platforms that listed in 2021-22 trade on profitability cadence now — the market reprices the quarter an adjusted-EBITDA guidance is missed. State the cycle phase for the specific platform before extrapolating current unit-economics trends.

### Sector-Specific Red Flags for Business Quality
Business-quality stress in platforms shows up in unit economics before it shows up in consolidated EBITDA:
- **Contribution-margin-per-order negative 3+ quarters post-scale claim** — after a platform asserts "scale achieved," CMPO should trend positive; sustained negativity is a broken unit-economic thesis.
- **Cohort retention decay M1 → M6 worse than peer** — if the M6 repeat-order rate on newer cohorts is weaker than older cohorts, the platform is renting users not acquiring them.
- **CAC inflation +25% YoY without retention improvement** — competitive over-bidding for paid traffic with no matching LTV gain.
- **Ad-heavy P&L with merchant-concentration** — top-100 merchants contributing >40% of ad revenue is a single-name-risk concentration at the ad-tech layer.
- **Cash runway <18 months with equity-market closed** — the combination forces either down-round dilution or distressed M&A.
- **Order-frequency decline while MAU grows** — activation is falling; headline user growth masks engagement erosion.

### Data-shape Fallback for Unit Economics
If `get_company_context(section='concall_insights', sub_section='operational_metrics')` returns `status='schema_valid_but_unavailable'` for contribution margin per order or cohort retention, fall back in this order: (1) `sub_section='management_commentary')` for management-narrated unit-economic progress; (2) `get_fundamentals(section='cost_structure')` to derive contribution margin from delivery / logistics / payment-gateway cost lines; (3) `get_fundamentals(section='expense_breakdown')` for CAC and marketing-as-%-of-revenue. Cite the quarter. If all three are silent on cohort retention specifically, add to Open Questions — without M+6 / M+12 repeat rates, LTV estimates are fiction.

### Open Questions — Platform Business-Specific
- "What is contribution margin per order today and what is the trajectory over the last 4 quarters — and does it support the stated path-to-operating-EBITDA timeline?"
- "What is the M+1 / M+3 / M+6 / M+12 cohort repeat-order rate for the 2024 cohort, and how does it compare to the 2022 and 2023 cohorts?"
- "What is blended CAC vs paid CAC, and what is the organic-share trend — is the brand moat strengthening or weakening?"
- "For hybrid 1P/3P platforms: what share of reported revenue is 1P vs 3P, and what is the blended take-rate normalised on GMV?"
- "What is the dark-store count per city and orders per store per day, and at what utilisation does a store turn contribution-positive?" (quick-commerce)
