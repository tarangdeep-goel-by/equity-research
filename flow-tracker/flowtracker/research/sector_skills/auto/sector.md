## Auto — Sector Agent

### Macro Context — Real Wages, Capex Cycle, Fuel, FX
Auto is one of the most macro-sensitive sectors in the index; no stock-level narrative is complete without anchoring to the macro regime. Pull via `get_market_context(section='macro')` and state these variables explicitly:
- **Rural real-wage index and monsoon** — the 2W (commuter) and tractor cycles are rural-real-wage-sensitive. MNREGA-adjusted real wages turning negative for 3+ quarters drops 2W commuter volumes 8-15%. Monsoon deviation beyond ±10% of LPA drags tractor volumes 10-20% in the subsequent season.
- **Urban passenger-vehicle cycle** — tied to housing affordability, white-collar wage growth, and financing penetration. Finance-penetration currently at 80-85% of new-4W sales; any RBI tightening of auto-loan LTV or NBFC-PV funding cost directly compresses demand.
- **CV cycle tied to infra capex and GST / e-way-bill fleet turnover** — government capex growth >15% YoY correlates with M&HCV volume expansion with a 2-3 quarter lag; GST / e-way-bill compliance drove a structural shift from small-operator fleets to organized operators, which compressed the CV cycle's depth while raising the average quality of operator balance-sheets.
- **Brent crude and fuel-parity economics** — higher fuel prices accelerate EV-adoption TCO math but also compress discretionary 4W demand; petrol at ₹100+/litre sustained for 4+ quarters has historically coincided with 2W commuter-segment demand softness.
- **INR / USD and export-market FX** — 4-7% INR moves produce 150-300 bps of EBITDA impact on exporter ancillaries and 100-200 bps on importer-heavy OEMs (steel / aluminum content-weighted).

### Sector Cycle Position — Three Cycles, State Each
Auto lives through three overlapping cycles — volume, commodity, and EV-transition — and diagnosing each before declaring sector direction is the difference between a cyclical-recovery call and a structural-disruption call.
- **Volume cycle (5-7yr)** — deleveraging / trough (inventory destocking, financing tight, OEM capex on hold), early-upswing (retail > wholesale, inventory draws down, pricing firms), mid-cycle (volumes expanding, segment mix premiumizing, margins expanding), peak (record volumes, thin discounts, rising raw material pressure), downcycle (discounts widen, inventory days rise, production cuts). Each sub-segment (PV / 2W / CV / tractor) runs its own cycle with imperfect correlation; the CV cycle typically leads the PV cycle by 2-3 quarters.
- **Commodity cycle (2-3yr)** — steel, aluminum, rubber, copper, precious metals (palladium, rhodium for catalysts), rare earths. Input costs move with 1-2 quarter lag to spot; pricing pass-through lag adds 2-3 more quarters. A commodity down-cycle is usually 400-800 bps EBITDA-margin tailwind for OEMs over 4-6 quarters.
- **EV-transition cycle (10-15yr, structural)** — 2W EV share 5-10% today, tracking toward 25-40% by 2027-30 at current trajectory; 4W EV share 2-5% today with inflection 2030-35; CV EV share negligible today with intra-city LCV first. State the sector's current EV-share-of-sales for the relevant sub-segment and the 3-5Y trajectory against management's disclosed roadmap.

State which phase the sector is in for each of the three cycles; contradictory phases (e.g., mid-cycle volume + commodity headwind + accelerating EV share loss) are the interesting setups worth highlighting.

### Competitive Hierarchy — Tier the Sector
Sector reports collapse when they treat auto as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics'`:
- **Top-2 2W OEMs by segment** — commuter-2W leader (rural-heavy distribution), premium-2W and scooter leader (urban-heavy). The top-2 together hold 60-75% of the 2W market; tier-3 players operate at structural scale disadvantage.
- **Top-3 4W OEMs** — mass / small-car leader, mid-SUV leader, premium 4W with SOTP / overseas-luxury optionality. The top-3 typically hold 55-65% of 4W volumes.
- **Top-2 CV OEMs + tractor leader** — M&HCV leader, multi-segment CV + tractor leader; tractor market is structurally concentrated with the top-2 holding 75-85% share.
- **EV pure-plays by segment** — 2W EV pure-play leaders, 3W EV leaders, 4W EV pure-plays (smaller pool). Segment share moves fast here; quarterly re-tiering is the norm.
- **Tier-1 ancillary leaders** — by OEM-content and by segment (electricals, powertrain, suspension, braking, interiors). A Tier-1 leader specced into 2-3 top OEMs across 5-8 platforms is the structural winner.
- **Aftermarket leaders** — tyres top-3 (replacement-share >60% of their volume), lubricants top-3 (OEM + retail channel), batteries top-2 (transitioning from lead-acid to Li-ion).

### Institutional-Flow Patterns — Auto-Specific
Auto carries 6-8% weight in Nifty and flow mechanics differ from BFSI or IT:
- **FII-sensitivity to rupee and oil** — auto flows turn risk-off on a 3-5% INR depreciation (exporters benefit, importers get hit; net sector impact is typically negative because index weight is tilted toward domestic-demand OEMs) and on a 15%+ Brent rally (fuel cost spikes drag domestic demand).
- **DII tilt toward 2W leaders and ancillary scale compounders** — domestic MFs structurally overweight rural-consumption proxies and asset-light ancillaries with 15-20% ROE. DII share in 2W leaders commonly runs 12-18%.
- **Cycle-top / cycle-bottom DII flows** — DII entry at cycle troughs (trough GNPA / trough-volume quarter) and exit at cycle peaks is observable in 8-12 quarter flow series; a cycle-top signal is DII selling into a strong volume quarter.
- **Index-rebalance mechanical flows** — auto weight shifts in Nifty / Nifty Auto drive passive flows; a 20-30 bps weight change in a top-5 auto name can move 0.5-1.0% of float in a single rebalance window.
- **MNC-subsidiary flow profile** — foreign-parent promoter holding is already classified as strategic / permanent capital and does not show up as FII flow; the floating FII pool for MNC subs is thinner, amplifying price volatility on marginal flows.

Cross-check sector flows via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak'` before claiming sector-level institutional rotation. A single stock's FII % change is not a sector signal unless corroborated at the index-weight level.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping auto economics over 3-10 years:
- **EV transition** — 2W 2027-30 inflection, 4W 2030-35 inflection, CV intra-city LCV first. The TCO-parity math is already favorable for 2W in most states; the remaining barriers are range anxiety, charging infrastructure, and financing. Each sub-segment has distinct timing.
- **Connected-vehicle / ADAS penetration** — content-per-vehicle is rising for Tier-1 ancillaries with ADAS, telematics, and software-defined-vehicle platforms. A premium-4W platform today carries 2-3× the electronics content of a 2018 equivalent; Tier-1 leaders specced into these platforms carry an embedded growth tailwind.
- **Shared-mobility impact on ownership** — cab-aggregator and subscription-mobility models compress per-capita ownership rates in dense metros; segment impact is largest for mass 4W and lowest for 2W where ownership remains essential.
- **Right-to-repair + aftermarket margins** — regulatory push toward third-party repair access compresses OEM aftermarket margins (where disclosed, 15-25% of total OEM profit) while expanding organized-aftermarket player TAM by 10-15%.
- **Localization and PLI-driven domestic-value-add** — Auto PLI and Cell PLI shift the manufacturing-intensity balance from import-heavy to domestic-heavy; the 3-5Y winners are Tier-1 ancillaries with domestic PLI-qualified content.
- **Scrappage policy and fleet turnover** — voluntary scrapping policy creates 20-40% incremental CV demand when states enforce; uneven state execution is the binding constraint.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "EV transition" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-type, not only the absolute number. The sector-agent-relevant KPIs by sub-type:
- **OEMs (4W / 2W / CV)** — volume growth YoY%, segment market share%, EBITDA margin%, realization per unit, capacity utilization%, cash conversion%, capex/revenue%, inventory days, discount per vehicle.
- **EV pure-plays** — volume growth%, cash burn per vehicle, runway months, ASP, gross margin%, cost per kWh trajectory.
- **Tier-1 ancillaries** — content per vehicle, top-OEM revenue concentration%, EBITDA margin%, ROCE%, export mix%, working-capital days.
- **Tier-2 ancillaries** — gross margin%, pass-through lag (quarters), working-capital days, customer concentration%.
- **Aftermarket** — replacement-market share%, distribution-touchpoint count, gross margin%, ROCE%.
- **Battery / cell makers** — capacity utilization%, cost per kWh, PLI-qualified DVA%, capex/revenue%.

A number quoted without sector percentile (e.g., "EBITDA margin 14%") omits whether that is top-quartile, median, or bottom-quartile within the sub-type; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable sub-type names) or `section='benchmarks'` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the index-weight context and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked. For sub-type matching, cross-check `get_yahoo_peers` and filter to genuinely comparable sub-type names (a 2W leader is not peered against a premium-4W OEM).

### Open Questions — Auto Sector-Specific
- "Where is the sector in the volume cycle, the commodity cycle, and the EV-transition cycle, and are the three phases aligned or divergent?"
- "What is the current 2W and 4W EV share of sales, and is the sector on, above, or below the 2027-30 inflection trajectory?"
- "What is the rural real-wage and monsoon context currently, and is it consistent with the 2W / tractor volume guidance from the top players?"
- "Are any BS7, CAFE-Phase-3, scrappage, or FAME / PLI policy revisions in draft consultation that would reprice capex or demand for this sub-type?"
- "For structural shifts (ADAS penetration, shared mobility, right-to-repair): what share of incremental growth is from the new channel vs legacy origination, and is the incumbent's moat being challenged?"
