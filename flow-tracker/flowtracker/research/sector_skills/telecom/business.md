## Telecom — Business Agent

### Sub-type Archetype — Identify the Operating Layer First
"Telecom" aggregates at least five distinct business models with different revenue engines, unit economics, and capital-intensity profiles. The narrative collapses if a tower-infrastructure report uses wireless-operator framing, or if a pure-play enterprise-services operator gets benchmarked against a B2C wireless ARPU curve. State the sub-type and its primary revenue engine in the opening paragraph before decomposing growth.

| Sub-type | Primary revenue engine | Unit of production | Typical EBITDA margin |
| :--- | :--- | :--- | :--- |
| **Integrated wireless operator** | Subscribers × ARPU × months; data-monetisation overlay | active subscribers × ARPU | 45-55% at scale |
| **Tower / passive infrastructure** | Tenancies × monthly rent × tenancy ratio (tenancies per tower) | tenancies; tenancy ratio 1.8-2.4× | 70-80% |
| **Wireline / FTTH home broadband** | Subscribers × ARPU; content-bundling overlay | connected homes × broadband ARPU | 35-45% |
| **Enterprise B2B / connectivity** | ARPU per seat × contracted accounts; data-centre / managed-services overlay | enterprise accounts; seats | 25-35% |
| **5G FWA / fixed wireless access** | New-home subscribers × broadband-equivalent ARPU | FWA subs net-adds | thin then scaling to 30-40% |

Conglomerate telecom groups span 3-5 of these at once (wireless + towers + FTTH + enterprise + international geographies); run the archetype call per vertical, not per listed entity.

### Revenue Bridge A × B — Translate to the Right Driver Decomposition
The revenue bridge differs materially by sub-type and should be shown explicitly rather than collapsed to YoY growth:
- **Wireless:** `Revenue = Active subscribers × ARPU × months`. Growth levers: subscriber net-adds, tariff hike, post-paid mix-shift, data-usage monetisation. The highest-leverage lever in India today is tariff: ARPU ₹180-220 currently, post-next-tariff-cycle target ₹250-300. Incremental EBITDA per ₹1 of ARPU lift is ~80% given the mostly-fixed cost base.
- **Tower infra:** `Revenue = Towers × tenancy ratio × rent per tenant × months`. Tenancy ratio is the single most important utility-like KPI — moving from 1.8× to 2.2× lifts tower-level EBITDA disproportionately because the second and third tenants carry minimal incremental opex.
- **FTTH:** `Revenue = Homes-passed × activation % × ARPU`; activation % (typically 20-35%) is the saturation lever after the fibre rollout is sunk.
- **Enterprise:** `Revenue = Accounts × seats per account × ARPU per seat`; long-tenor contracts, retention-led rather than acquisition-led.

Pull ARPU, active subscribers, and tenancy ratios from `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `section='sector_kpis'`. When management reports ARPU on a non-VLR base, state the denominator — VLR-based ARPU and reported-base ARPU are materially different numbers.

### Moat Architecture — Spectrum Scale, Network Density, Distribution Inertia
Telecom moats are structural rather than brand-led and should be named in concrete terms:
- **Spectrum holdings** — licensed MHz weighted by band quality (sub-1GHz coverage bands vs mid-band capacity bands vs mmWave); spectrum is a genuine scarce resource reissued only every 2-5 years via DoT auction.
- **Network density** — tower count, fibre km, cell-site density per 1000 people; the top-3 wireless oligopoly has structurally higher density than any new entrant can replicate at a reasonable IRR.
- **Distribution / retail presence** — prepaid recharge points, retail-partner footprint; while individual consumer switching cost is low, the prepaid recharge inertia and dealer-relationship density matter.
- **Enterprise relationships** — for B2B telcos, multi-year contracts and integration depth create meaningful switching cost.
- **Fibre footprint for FTTH** — home-broadband is moated by which operator has fibre laid in a given locality; duplicate fibre overbuilding is uneconomic.

Do not over-index on brand or loyalty — in Indian telecom these are secondary to the four physical-infrastructure moats above. Cross-reference with `get_company_context(section='concall_insights', sub_section='business_segments')` for segment-level moat attribution.

### Unit Economics — ARPU, Cost-per-GB, Subscriber LTV
The unit-economics table for a wireless operator is:
- ARPU ₹180-220 currently; ₹250-300 target post-tariff-cycle. Premium post-paid ARPUs can be 2-3× prepaid.
- Incremental EBITDA per ₹1 ARPU hike: ~80% because network is mostly fixed-cost.
- Cost per GB: falling structurally as infra capex amortises across rising data usage; this is the deflationary offset to ARPU stagnation.
- Subscriber acquisition cost (SAC): ₹200-600 per subscriber depending on segment.
- Subscriber lifetime: 24-36 months average; high-churn segments (student/migrant) shorter, post-paid longer.
- Data usage per sub: 18-25 GB/month currently, rising.

For tower infra, the key utility economics: tower EBITDA margin 70-80%; tenancy ratio 1.8-2.2× is normal, >2.4× is premium utilisation; rent escalators are contract-linked, typically CPI + fixed step-ups.

### Capital-Cycle Position — 5G Peak Capex, Tariff-Hike Sequence
Indian telecom is in a late-stage oligopoly-consolidation cycle — the 2016 new-entrant-led tariff disruption collapsed the industry to three wireless operators. Overlay three concurrent cycles before projecting forward:
- **5G capex cycle** — 2022-2026 peak rollout; capex/revenue has run 20-35% for the top-2 during rollout, expected to moderate to 15-20% in steady state. A report that treats current capex as steady state under-estimates OpFCF expansion potential.
- **Tariff-hike cycle** — FY24/25 saw a sequenced hike; the market is pricing another cycle in the next 12-18 months. Each ₹10 ARPU hike on 350M+ subs is ~₹4,000 Cr incremental quarterly revenue at ~80% incremental margin.
- **Spectrum renewal cycle** — every 2-5 years DoT runs auctions; auction outcomes in key bands reprice the oligopoly overnight.
- **Tower-infra expansion cycle** — 5G densification is extending the tower-build cycle even as wireless capex peaks.

Extract capex / revenue and spectrum-holding commentary from `get_company_context(section='concall_insights', sub_section='financial_metrics')` and `sub_section='management_commentary')`.

### Red Flags — Business-Model Stress Tells
Watch for these as early-warning tells of a deteriorating franchise:
- **Subscriber losses to peers during a tariff-hike window** — most operators hold subs through tariff hikes because the oligopoly moves together; a single operator losing subs during a sector-wide hike is a market-share erosion signal, not a pricing signal.
- **ARPU stagnation while peers expand** — indicates inability to convert data usage or premium-segment mix.
- **Spectrum-auction shortfall in critical bands** — missing sub-1GHz coverage bands or mid-band capacity bands re-prices the operator's long-term relative position.
- **Capex / revenue sustained >35% for 2+ years without matched EBITDA-margin expansion** — network investment not translating into scale.
- **Accumulated losses at a B-tier operator combined with AGR / spectrum-dues overhang** — government equity-conversion is a permanent dilution latent.
- **Tenancy ratio stagnant <1.8× for tower infra** — under-utilisation despite industry-wide 5G densification suggests tower-location or operator-relationship weakness.

Flag each as a specific thesis-breaker with the threshold metric, not a vague concern.

### Data-shape Fallback — Sub-type Detection When Segment Disclosure Is Thin
Some Indian telcos report consolidated numbers with thin segment disclosure. When `get_company_context(section='concall_insights', sub_section='business_segments')` returns sparse segment revenue, fall back in this order: (1) `get_fundamentals(section='segment_reporting')` for the statutory segment note; (2) `get_company_context(section='documents')` for investor presentations that frequently disclose segment EBITDA even when the annual report collapses it; (3) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-guided segment splits. If all three are sparse, explicitly note the segment-opacity in Open Questions rather than estimating segment EBITDA blindly.
