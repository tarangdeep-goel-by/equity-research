## Real Estate — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
"Real estate" hides at least five economically distinct business models. Residential developers sell project inventory (pre-sales model, 2-3Y delivery cycle, cyclical ROE), commercial/REIT operators rent space (lease-income model, 6-9% cap rate, steady NOI), integrated developers run both on one balance sheet, land-bank / township players carry multi-decade monetisation timelines, and specialty (warehousing, data-centre) players are asset-light lease-income with different cap-rate regimes. State the sub-type and its primary revenue engine before decomposing growth. Peer comparisons across sub-types (e.g., DLF vs EMBASSY, LODHA vs MINDSPACE) without this routing produce inverted diagnostics.

| Subtype | Revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **Residential — premium / luxury** (DLF, GODREJPROP, OBEROIRLTY, LODHA, PRESTIGE) | Presales × realization × handover cadence | location + brand premium | EBITDA per sqft (₹2,000-5,000 premium; ₹8,000-20,000 luxury) |
| **Residential — mid / affordable** (SOBHA, KOLTEPATIL, PURVANKARA, SIGNATURE) | Volume × realization, cycle-levered | affordability × volume | EBITDA per sqft (₹500-1,500 affordable; ₹1,500-3,000 mid) |
| **Commercial / Office REIT** (EMBASSY, MINDSPACE, BIRET) | Leased area × rent psf × occupancy | rent roll + occupancy | NOI per sqft, WALE, cap rate 6-9% |
| **Retail-Mall REIT** (NEXUS) | Rent (minimum guarantee + % of tenant sales) × leasable area | footfall × tenant sales × rent bps | NOI per sqft, cap rate 8-10% |
| **Integrated developer** (BRIGADE, PRESTIGE, DLF) | Residential presales + leasing annuity + hospitality / mgmt fee | multi-engine mix | mix-weighted EBITDA, annuity share of EBITDA |
| **Land-bank / township** (ANANTRAJ, ARVIND-SMART, large-land holders) | Multi-decade land monetisation, JDA + outright mix | land-bank NAV × monetisation velocity | NAV per acre, monetisation rate |
| **Specialty — warehousing** (emerging listed plays) | Leased logistics parks, built-to-suit + multi-client | rent psf × occupancy × client tenure | NOI per sqft, cap rate 7-8% |
| **Specialty — data-centre** (emerging) | MW-leased × rent per MW × uptime | power-capacity × tenancy | revenue per MW, cap rate 9-11% |

### Revenue Decomposition — Always (A × B), Never a Single Line
For residential developers the reported revenue line understates business momentum because IndAS 115 defers revenue to handover. Decompose on two tracks:
- **Reported revenue** `= sqft handed over × realization per sqft × segment-mix`.
- **Presales (booking value)** `= new-bookings volume (sqft) × realization per sqft × segment-mix`. Presales leads revenue by 2-3 years and is the current-demand signal.

For commercial / REIT operators: `NOI = leased area × rent per sqft × occupancy − operating expenses`, with `Revenue = leased area × rent per sqft × occupancy`. For integrated developers, split the annuity (leasing) EBITDA from the transactional (residential) EBITDA — the annuity is a higher-quality cash stream that deserves a different multiple. Pull via `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')`.

### Realization per sqft — Extract Explicitly, Not Just Named
Prior valuation evals flagged realization-per-sqft as the single most-named-but-never-extracted operational signal (GODREJPROP was the cited pattern). It is the clean read on pricing power and product-mix shift to premium and should be pulled explicitly with the quarter and cited source. Sources: `get_company_context(section='concall_insights', sub_section='operational_metrics')`, segment disclosure within `get_fundamentals(section='revenue_segments')`, or investor-presentation uploads in `filings`. Track 8-quarter trajectory — rising realization at flat volume is pricing power or premium mix-shift; rising realization at falling volume is affordability stress.

### Moat Typology — Distinct by Sub-type
Moats in real estate are location-concrete, not abstract brand narratives:
- **Land-bank in Tier-1 metros** — scarcity of approvable land in central Mumbai, Bengaluru core, Gurugram golf-course-road type locations is the original moat. A 500-acre parcel in Gurugram at a ₹3,000-4,000 psf acquisition cost that revalues to ₹15,000 psf is a structural moat, not a cyclical bet. Source land-bank disclosure from concall / investor-presentation.
- **Brand pricing power** — in luxury (OBEROIRLTY) and premium (DLF), brand supports a 10-25% realization premium over nearest comparable at launch.
- **Execution track-record** — on-time delivery versus RERA-mandated timeline, historical delay/penalty exposure. Developers with 95%+ on-time delivery history command a pre-launch booking premium.
- **Distribution / pre-launch bookings** — the ability to sell 40-60% of a tower at soft-launch (before full RERA registration) is a brand-plus-channel moat that compresses the capital cycle.
- **Integrated-ops (construction + leasing + management)** — reduces reliance on external contractors, improves schedule, and captures leasing annuity on the same land-stack.
- **Regulatory-tailwind — RERA-compliant incumbency** — post-2017 the unregulated developer cohort has been structurally compressed; compliant listed developers have a regulatory-moat that improves each cycle.

### Unit Economics — Sub-type-Appropriate Unit
Aggregate P&L hides the story. For residential developers the unit is **EBITDA per sqft handed over** (premium ₹2,000-5,000 at 20-30% margin, luxury ₹8,000-20,000 at 28-40%, affordable ₹500-1,500 at 12-18%) paired with **presales velocity** (sqft sold / quarter). For commercial / REIT the unit is **cap rate** (prime-Mumbai / Bengaluru office 6-7%, Tier-2 office 7-9%, retail malls 8-10%, warehousing 7-8%, data-centre 9-11%) and **NOI per sqft** annualised. For land-bank plays the unit is **NAV per sqft of developable area** (₹2,000-15,000 depending on city and location stage). Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; if unavailable, flag as attempted with specific metric name.

### Capital-Cycle Position — Cycles Are Long and Overlapping
Indian residential has been in a 3-4 year re-rating cycle since 2020-21 (post-RERA cohort rationalised, post-GST pricing normalised, post-demonetisation un-organised-share compressed). The current phase (2024-26) is premium upcycle with mid/affordable lagging; commercial office is in a separate recovery after 2021-23 WFH compression; warehousing is structurally up-cycling on e-commerce tailwinds. State the phase explicitly for the sub-type; residential upcycle is not commercial upcycle.

### Sector-Specific Red Flags for Business Quality
Business stress in real estate surfaces earlier through operational telemetry than through P&L. Scan for:
- **Presales deceleration 2+ quarters** — two consecutive quarters of YoY presales decline, often accompanied by "inducement" discounts or payment-plan sweeteners, is the early sign of demand rollover.
- **Land-bank aging without monetisation** — a parcel on the balance sheet for 5+ years at acquisition cost carries an opportunity-cost drag of 10-14% per year; if not monetised, it impairs ROE mechanically.
- **Leverage — Net Debt / EBITDA > 3×** in a flat or decelerating presales environment is the classic cycle-trap setup.
- **RERA non-compliance events** — occupancy-certificate delays, customer-complaint clusters, or state-RERA penalty orders materially reprice brand.
- **Delays vs committed-delivery schedules** — the 3-5 quarter drift between promised-delivery and actual-handover; this is where working-capital balloons and interest-burden crystallises into customer-penalty exposure.

### Data-shape Fallback for Unit Economics
If `get_fundamentals(section='revenue_segments')` is aggregate-only and `get_company_context(section='sector_kpis')` returns `status='schema_valid_but_unavailable'` for realization-per-sqft, presales-volume, or NOI-per-sqft, fall back to `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `sub_section='management_commentary')`. Indian developers routinely disclose quarterly presales value, volume, realization, and collections in opening remarks — the narrative contains it. Cite the quarter. If the narrative too is silent, add to Open Questions tied to the specific unit.

### Open Questions — Real-Estate Business-Specific
- "What is the latest quarter's realization per sqft, disaggregated by segment (luxury / premium / mid / affordable), and how has it trended over the last 8 quarters?"
- "What is the presales-to-revenue-recognition bridge for FY+1 and FY+2 — how much booked presales convert to reported revenue in each year?"
- "What is the developable area in the land-bank (sqft), the Tier-1 city share of that land-bank, and the weighted-average years-since-acquisition?"
- "For integrated developers: what share of EBITDA comes from the leasing annuity vs transactional residential, and what is the annuity growth trajectory?"
- "For REITs: what is the WALE (weighted-average lease expiry), occupancy %, and in-place rent vs market-rent gap for the top-10 tenants?"
