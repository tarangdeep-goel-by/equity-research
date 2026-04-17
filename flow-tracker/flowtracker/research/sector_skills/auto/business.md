## Auto — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
"Auto" is not a single business model. The revenue engine, moat shape, cyclical sensitivity, and the mortality-risk profile differ so sharply across sub-types that applying a "4W OEM framework" to an auto ancillary or an "ICE valuation lens" to an EV pure-play inverts the diagnosis. State the sub-type and its primary revenue engine in the opening paragraph before decomposing growth.

| Subtype | Primary revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **OEM — Passenger 4W (mass / premium split)** | Volume × Realization × Mix | cycle + segment mix | EBITDA/vehicle: mass ₹30-80k, premium ₹100-200k; per-plant utilization |
| **OEM — 2W (commuter / premium / scooter)** | Volume × Realization; rural-skewed for commuter | rural real wages + fuel price | EBITDA/vehicle: commuter ₹6-12k, premium ₹40-50k (e.g., Royal Enfield archetype); per-dealer throughput |
| **OEM — Commercial Vehicle (M&HCV / LCV)** | Volume × Realization; infra-capex linked | infra order-book + freight rates | EBITDA/vehicle ₹150-400k; per-plant utilization |
| **OEM — 3W (three-wheeler passenger / cargo)** | Volume × Realization × Mix (ICE vs EV); Bajaj/M&M duopoly (fastest-EV-adopting segment in India, >50% EV penetration already achieved) | last-mile logistics demand + EV-mandate tailwind + fuel-parity TCO | EBITDA/vehicle ₹25-45k; per-plant utilization |
| **OEM — Tractor / Farm Equipment** | Volume × Realization; monsoon + farm-cycle linked | monsoon + rural real wages | EBITDA/vehicle ₹70-120k (ASP ₹6-8L, not comparable to CV); per-plant utilization |
| **EV pure-play** | Revenue = Volume × ASP; unit economics negative until scale | cash runway + cell-cost curve | EBITDA/vehicle typically negative; runway in months |
| **Auto ancillary — Tier-1 (platform-integrated)** | Content-per-vehicle × OEM volume × OEM-share | customer concentration + content-mix | EBITDA margin 10-18%; per-OEM revenue share |
| **Auto ancillary — Tier-2 / component (commodity-linked)** | Unit volume × spec-linked ASP | pass-through + inventory cycle | EBITDA margin 8-14%; working-capital days |
| **Battery / cell makers** | Capacity × utilization × price; PLI-linked | cell-chemistry + FAME/PLI rules | ₹/kWh cell cost; plant utilization |
| **Aftermarket — tyres / lubricants / batteries** | Replacement demand × brand realization; channel-led | fleet-on-road + replacement cycle | per-SKU gross margin; distribution depth |

### Revenue Decomposition — Always (Volume × Realization × Mix), Never a Single Line
`Revenue = Volume × Realization × Mix` is the only correct top-line decomposition for auto. Growth from pricing hides below-unit weakness in a slowing cycle; growth from volume hides ASP erosion from discounting mid-cycle. Decompose via `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `get_fundamentals(section='revenue_segments')`:
- **Volume** further splits into domestic / export and, for 2W, urban / rural; for CVs, into M&HCV / LCV / tractors. A commuter-2W company holding urban volumes while rural drops 15% is hiding a real-wage-linked demand break.
- **Realization** (ASP per unit) is moved by mix (premium share lift) and by pricing actions net of discounts; quote discount-per-vehicle where disclosed because a ₹15-25k/unit discount on a ₹8-12L passenger car is 1-2pp of margin compression.
- **Mix** captures segment migration (small car → SUV, commuter-2W → scooter, M&HCV → tractor) where the EBITDA/unit gap is 2-5×, so even a flat volume year can produce margin expansion.
Split wholesale (factory dispatches reported for revenue) from retail (actual end-user registrations); the divergence accumulates as dealer inventory and is the single best 1-2 quarter demand leading indicator.

### Moat Typology — Distinct by Sub-type
Auto moats are genuinely different at the sub-type level; enumerate which moat applies before asserting "durable franchise":
- **Brand (2W leaders, premium 4W)** — a 2W leader with 30-45% segment share carrying 40-60Y of brand equity in Tier-3 / Tier-4 towns is a real moat; new entrants need 5-8 years and sustained loss-funding to build equivalent recall.
- **Distribution depth (rural 2W, CV)** — 2,500-5,000 touchpoint networks into Tier-3 and rural locations are structurally hard to replicate; an incumbent's service-plus-sales network determines field failure handling, which drives repeat purchase rates.
- **Scale economies (mass 4W, large ancillaries)** — per-plant fixed costs are so high that below 70% utilization margins structurally compress; the #1-2 in each segment enjoy a durable 200-400 bps EBITDA margin advantage over sub-scale peers.
- **Technology / platform (premium 4W, EV pure-plays, premium ancillary)** — a genuinely differentiated EV powertrain or ADAS platform is a moat-in-construction; validate with R&D intensity (3-6% of revenue is current Indian-auto regime, up from 1-3%) and disclosed platform-licensing revenue.
- **Engineering IP + customer stickiness (Tier-1 ancillary)** — once a Tier-1 component is specced into an OEM platform, the switching cost over the 6-8 year model life is prohibitive; revenue-per-OEM-share is the moat telltale.

Source moat evidence via `get_quality_scores`, `get_peer_sector(section='peer_metrics')`, and management commentary in `concall_insights`.

### Unit Economics — Sub-type-Appropriate Unit
Aggregate P&L smooths the story; force the per-unit view. For 4W OEMs, **EBITDA per vehicle** (mass ₹30-80k, premium ₹100-200k currently in the 2022-24 regime) and **capacity utilization %** are the twin levers. For 2W, **EBITDA per vehicle** splits by archetype — **commuter ₹6-12k** (Hero-style mass rural), **premium ₹40-50k** (Royal Enfield-style premium motorcycle) — combined with **per-dealer monthly throughput** (30-60 units for a healthy dealer, <20 is distress); do not apply a single 2W threshold across the sub-type. For **M&HCV / LCV**, **EBITDA per vehicle ₹150-400k** on ₹30-40L+ realization. For **Tractors**, **EBITDA per vehicle ₹70-120k** on ₹6-8L realization (fundamentally different from CV — do not collapse into one bucket), with good-monsoon years lifting toward the top of the range. For Tier-1 ancillaries, **content per vehicle** for each OEM customer and **EBITDA margin by customer** reveal negotiating power. For EV pure-plays, the relevant unit is **cash burn per vehicle delivered** and **runway in months** rather than EBITDA; loss per unit narrowing 30-40% YoY on rising volumes is the scale-path telltale. Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; if unavailable, flag as attempted.

### Capital-Cycle Position — Earnings Are Cycle-Sensitive
Auto is a 5-7 year cyclical industry and the three cycles interact. State the cycle phase before forecasting:
- **Volume cycle (5-7yr)** — trough / early-upswing / mid-cycle / peak / downcycle. A mid-cycle EBITDA per unit ≠ a peak-cycle number; peak-cycle PE on peak-cycle EPS is the most common valuation mistake in the sector.
- **Commodity cycle (2-3yr)** — steel, aluminum, copper, rubber, rare earths. Input inflation hits margin with a 1-2 quarter lag; pricing pass-through lag is typically 2-3 quarters. A 15% steel move produces 200-400 bps of gross margin swing for most OEMs.
- **EV transition cycle (10-15yr, structural)** — EV share of 2W is currently 5-10% and expected to cross 25-40% by 2027-30 at the current trajectory; for 4W it's 2-5% today with inflection expected 2030-35. ICE-dominant OEMs face terminal-value risk in 2W first. State the company's disclosed EV roadmap and share-of-sales target against the sector trajectory.

Cyclical ≠ structural; do not confuse a volume-cycle downturn with a structural EV-driven share loss. The diagnostic: in a cyclical downturn, market share typically holds within ±200 bps; in a structural EV-driven loss, share drops 400-800 bps over 4-6 quarters with no recovery on the next volume upcycle.

### Sector-Specific Red Flags for Business Quality
Business-quality stress surfaces earlier than financial-quality stress. Scan for:
- **Wholesale-retail divergence** — wholesale dispatch growth 5-10pp above retail registration growth sustained for 2+ quarters builds dealer inventory; production cuts and 2-4pp margin compression follow in the next 1-2 quarters.
- **Rising discount intensity mid-cycle** — discount/vehicle lifting 20-40% YoY when the cycle is supposed to be mid-phase signals demand weakness masked by inventory push.
- **New-model failure rate** — a failed launch (defined as <50% of internal volume guidance in the first 4 quarters) for a flagship platform is a multi-year drag because capex has been sunk against the platform.
- **Rising inventory days** — finished-goods inventory drifting from 25-35 days to 45-60 days is a direct demand weakness signal.
- **EV pure-play with runway <18 months** — ongoing capex combined with quarterly cash burn eating a runway below 18 months flags dilution-imminent; below 12 months flags distress with going-concern risk if market conditions deteriorate.
- **R&D capitalization ratio rising** — capitalized R&D / gross R&D drifting above 40% flags that accounting, not business economics, is flattering reported EBITDA; the EV-cycle peer that expenses 100% is more conservative.

### Data-shape Fallback for Unit Economics
If `get_fundamentals(section='revenue_segments')` returns aggregate-only and `get_company_context(section='sector_kpis')` reports `status='schema_valid_but_unavailable'` for per-unit KPIs, fall back to `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `sub_section='management_commentary'`. Scan the earnings call transcript for disclosed volumes, realization, EBITDA per unit, capacity utilization, and dealer inventory days. Cite the quarter. If the narrative is silent, add to Open Questions tied to the specific unit.

### Open Questions — Auto Business-Specific
- "What is the wholesale-retail gap and dealer inventory days trajectory over the last 4 quarters — is the reported volume growth backed by retail offtake?"
- "What is the capacity utilization % currently, and at what utilization does EBITDA margin break even? Is the company above or below the 70% structural line?"
- "What share of current revenue comes from EVs, and what is management's disclosed EV revenue-share target for FY27 / FY30 against the sector trajectory?"
- "For Tier-1 ancillaries: what is the single-OEM revenue concentration and the single-platform revenue concentration? Any OEM beyond 40% or platform beyond 30% is structural risk."
- "For EV pure-plays: what is the current cash runway in months, what is the next planned capacity / capex tranche, and what is the disclosed funding source (QIP / strategic / debt)?"
