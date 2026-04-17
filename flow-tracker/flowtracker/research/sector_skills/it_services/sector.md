## IT Services — Sector Agent

### Macro Context — US GDP, Discretionary Spend, USD-INR, AI-CapEx
IT services is the second-most macro-sensitive Nifty sector (after BFSI); no stock-level narrative is complete without anchoring to the macro regime. Pull the regime from `get_market_context(section='macro')` and state these five variables explicitly:
- **US GDP growth** — top revenue source (55-65% of tier-1 revenue from US; mid-caps often >70%). US GDP growth <1.5% historically correlates with tier-1 USD-revenue growth slowdowns of 300-500 bps.
- **US discretionary-spend cycle** — particularly BFSI-discretionary (IT budget ex-run-the-bank). Gartner / ISG / Forrester IT-spend forecasts and Fed Senior Loan Officer surveys are the leading indicators. Discretionary cycle is 2-3 year; current 2024-25 regime is soft.
- **USD-INR trajectory** — every 1% INR depreciation adds ~30-40 bps to reported-INR margin for tier-1s (partially offset by hedging-gain unwinds). Extract the hedged-book share from concall for clean margin attribution.
- **US onshore-wage inflation** — tech-wage inflation in the US sets the onsite cost base; tight US labour market compresses the offshore-onshore wage arbitrage.
- **AI-CapEx cycle at US hyperscalers** — Microsoft, Google, AWS, Meta CapEx guidance is a leading indicator for cloud-services demand that flows through to tier-1 / mid-cap services via implementation and managed-services pipelines.

### Sector Cycle Position — Three Overlapping Cycles
IT services lives through three overlapping cycles; diagnose each before declaring sector direction:
- **Discretionary cycle (2-3 year)** — buyers accelerate vs defer project starts. Current 2024-25 phase: post-2022 boom normalisation, soft on discretionary, resilient on cost-takeout and AMS (application-managed-services).
- **Digitisation cycle (10-year secular)** — cloud migration, data-platform rebuild, modernisation; structurally tailwinded independent of discretionary cycle. Current phase: mid-cycle (~50% of enterprise workloads migrated; long runway remains on regulated-vertical and legacy-core-systems).
- **AI / GenAI reframe (5-10 year structural)** — productivity tools reshape billable-hours economics and pricing model (fixed-fee / outcome-based displacing T&M). Current phase: early — productivity gains visible in developer-tool pilots, not yet flowing to enterprise-scale pricing pressure on the reported P&L of tier-1s. Sector PE compression reflects the market pricing in the eventual re-pricing.

State which phase the sector is in for each cycle; contradictory phases (soft discretionary + strong structural migration + early AI reframe) are the current interesting setup.

### Competitive Hierarchy — Tier the Sector
Sector reports collapse when they treat IT services as monolithic. Tier via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:
- **Big-3 tier-1 Indian IT ($20B+ revenue)** — the three largest India-HQ vendors plus 1-2 next-scale players competitive on global-deal capability. Differentiated by vertical-mix (BFSI-heavy vs broad-based), deal-pursuit scale ($500M+ total-outsourcing capability), and geography diversification.
- **Mid-cap tier (vertical specialists)** — $1-5B revenue vendors that go deep on a single vertical (BFSI / insurance / healthcare / hi-tech / travel-transport / consumer). Premium-pricing via vertical depth; structurally thinner on deal-pursuit than tier-1; often acquired or acquiring for scale-up.
- **ER&D specialists** — engineering-services vendors covering automotive, aerospace, medtech, semiconductor, energy domains. Regulated-vertical compliance plus long sales cycles create high switching costs; IP-density per engineer is the moat.
- **Platform / product companies** — IP-led platform plays and emerging SaaS-plus-services hybrids. IP-led economics with SaaS-like gross margins (>65%) and ARR-based revenue mix.
- **IT consulting / GCC-model disruptors** — emerging consulting-first players and GCC build-and-operate partners competing with captive insourcing trends.

### Institutional-Flow Patterns — IT-Specific
IT services carries 10-12% weight in Nifty, which drives specific flow mechanics that must be reflected in both ownership and sector narrative:
- **FII-heavy structural allocation to tier-1** — top-3 tier-1s carry 20-35% FII share (direct FPI + ADR aggregation). MSCI EM and FTSE AW index rebalances drive mechanical passive flows.
- **USD-INR hedging flow overlay** — IT services is the cleanest INR-depreciation hedge in Nifty (dollar revenue, rupee cost base). FII flow timing correlates with USD-INR moves independent of the fundamental narrative. Segregate active fundamental buying from macro FX-hedging flows.
- **DII rotates counter-cyclically on cycle trough** — domestic MFs increase IT exposure when discretionary cycle troughs and FIIs are de-risking; domestic-institutional share rising 200-400 bps over 2-3 quarters while FII share falls is a cycle-bottom tell.
- **ADR aggregation on top-tier names** — 10-18% of paid-up capital as ADRs is typical for mega-cap IT; aggregate foreign ownership calculation must combine ADR + direct FPI.

Cross-check via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation. A single stock's FII % change is not a sector signal unless corroborated at the index-weight level.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping IT-services economics over 3-5 years:
- **AI / GenAI productivity** — tools like Copilot, Cursor, internal agent platforms reduce billable hours on legacy T&M work 20-40% on pilots; enterprise-scale re-pricing not yet in the reported P&L, but the lead indicator is fixed-fee-deal share rising in the book-to-bill mix.
- **GCC in-sourcing** — large US enterprises increasingly build Global Capability Centres in India, insourcing work that would historically have been outsourced. Competitive threat for the tier-1 book (wage base is the same, but value-capture shifts from vendor to captive). GCC count in India grew from ~1000 in 2015 to 1600+ in 2024.
- **Near-shore competition** — LATAM (Brazil, Mexico, Costa Rica) and Eastern Europe (Poland, Ukraine pre-war, Romania) wage arbitrage and time-zone advantages for US clients. Indian-vendor response: nearshore acquisitions or JV partnerships.
- **Pricing-model shift (fixed-fee / outcome-based vs T&M)** — the AI-productivity story forces this shift. Vendors with >40% fixed-fee exposure are ahead of the curve; <25% fixed-fee is behind.
- **Fee-pool compression at the low end** — commoditised application-maintenance work is under structural pricing pressure; vendors without a digital / cloud / AI mix >35-45% face compression.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "digital transformation" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-type, not only the absolute number. The IT-services-agent-relevant KPIs:
- **USD revenue growth** — YoY and QoQ.
- **Constant-currency growth** — strips FX noise.
- **Operating margin %** — through-cycle, not peak.
- **FCF conversion %** — FCF / PAT; >80% is healthy, <70% is a flag.
- **Attrition %** — LTM; 14-22% normal.
- **Utilisation %** — 82-86% sweet spot for tier-1.
- **TCV and book-to-bill** — book-to-bill >1.0 for 2+ consecutive quarters is positive.
- **Active-client count** — movement in $1M / $5M / $20M / $50M / $100M+ buckets.
- **Top-5 / Top-10 client share** — concentration risk; >40% for Top-5 is a flag.
- **Offshore-revenue share** — 70-90% for tier-1; mix-shift headroom matters for margin projection.
- **Revenue per employee** — $45-60k Indian tier-1 (offshore-heavy pyramid; US peer Accenture $100k+), $35-55k mid-cap; asset-productivity benchmark.

A number quoted without sector percentile (e.g., "operating margin of 20%") omits whether that is top-quartile, median, or bottom-quartile; the re-rating thesis depends on percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable names) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the index-weight context and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked. For structural-shift commentary (AI productivity, GCC dynamics), the concall transcript is often the richest data source.

### Open Questions — IT Services Sector-Specific
- "Where is the sector in the discretionary cycle, the digitisation cycle, and the AI-reframe cycle, and are the three phases aligned or divergent?"
- "What is the current US-GDP + US-BFSI-discretionary + USD-INR + AI-CapEx regime, and which two variables dominate the sector setup for this stock?"
- "What is the fixed-fee / outcome-based deal share in book-to-bill, and is the pricing-model shift outpacing or lagging the sector average?"
- "Is the GCC in-sourcing trend a net competitive threat or a revenue line (via build-and-operate partnerships) for this vendor?"
- "What share of incremental growth is coming from AI / cloud / data modernisation vs legacy AMS, and is that mix consistent with the premium / discount PE band the stock trades at?"
