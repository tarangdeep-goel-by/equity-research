## IT Services — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
"IT services" is an umbrella label for at least five distinct business models. Revenue engine, moat shape, unit of production, and cycle sensitivity differ sharply; applying a tier-1 services framework to a platform/product company or an ER&D specialist inverts the diagnosis. State the sub-type and its primary revenue engine in the opening paragraph before decomposing growth.

| Subtype | Primary revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **Tier-1 services ($20B+ revenue)** | Billed hours × rate + fixed-fee digital deals; broad vertical + geography mix | scale + deal-pursuit muscle | revenue per FTE, deal TCV, book-to-bill |
| **Mid-cap services (vertical specialist)** | Deep vertical (BFSI / healthcare / hi-tech / energy) expertise monetised at premium pricing | vertical depth × offshore leverage | revenue per vertical FTE, top-account ACV |
| **ER&D services** | Engineering-services contracts (mechanical, embedded, aerospace, medtech); outcome-linked + T&M hybrid | domain + compliance + IP | IP-density per engineer, regulated-vertical share |
| **Platform / product company** | Subscription / SaaS ACV + implementation services (IP-led, high-gross-margin, SaaS-like) | ARR growth × NRR × gross margin | ARR, NRR%, CAC payback |
| **IT consulting / GCC disruptor** | Consulting-led advisory + GCC-build-and-operate contracts | advisory depth + captive-model share | utilisation, advisory-revenue mix |

### Revenue Decomposition — Always (A × B), Never a Single Line
The volume-price split must be stated before any growth forecast. Two decompositions apply:
- **Capacity view**: `Revenue = Number of employees × Utilisation × Billing rate`. Headcount growth is volume, utilisation is the margin lever, billing-rate realisation is price. A vendor posting 8% USD growth while headcount is flat or falling is monetising better (pricing + mix-shift); a vendor posting the same 8% while headcount grew 12% is under-utilising.
- **Account view**: `Revenue = Active clients × ACV per client × expansion rate`. Expansion (account-mining, bucket migration — $5M→$10M→$20M+ clients) is where mid-cap specialists create alpha; dependence on new-logo wins alone means the farming engine is broken.

Extract via `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')`. Management rarely discloses clean A×B — reconstruct from headcount, utilisation, and revenue-per-FTE where needed and cite the quarter.

### Moat Typology — Distinct by Sub-type
A tier-1 moat is not a mid-cap moat is not a platform moat. Name the applicable moat lens before asserting "durable franchise":
- **Client embeddedness** — 10-year+ MSA relationships with deep system integration; the switching cost is measured in project-risk, not licence cost. Top-3 clients of tier-1s often date back 15-25 years.
- **Domain expertise** — BFSI-specialist or healthcare-specialist depth compounds into premium billing. A vendor with 35-45% BFSI mix AND disclosed pass-rate on top-tier-bank RFPs has a defensible niche; vanilla BFSI share is not a moat.
- **Platform / accelerator IP** — reusable codebases, pre-built cloud-migration factories, and industry-specific platforms reduce deal-ramp time, which is pricing leverage with enterprise buyers.
- **Brand in US-enterprise buying** — Fortune-500 procurement committees maintain a narrow approved-vendor list. Entry to that list takes 5-8 years and an India-delivery scale of 50-100k+ FTE; this is the real barrier protecting the big-3.
- **Scale on deal-pursuit infrastructure** — tier-1s run $100M+ deal-pursuit machines (bid-teams, proof-of-concept labs, partner ecosystems). Mid-caps cannot compete on $500M+ total-outsourcing deals structurally — they win via narrower, deeper vertical plays.

### Unit Economics — Sub-type-Appropriate Benchmark Ranges
Aggregate P&L hides the story. Use sub-type-calibrated benchmarks:
- **Revenue per FTE** — Indian tier-1 runs $45-60k per FTE (structurally below US peers like Accenture $100k+ due to deep offshore pyramid scale); mid-cap vertical specialists $35-55k; ER&D $55-75k (higher billing rates offset by lower offshore share); platform/product $150-250k (asset-light). A tier-1 falling below $42k while headcount grew materially is over-hired.
- **Utilisation** — 70-85% typical; tier-1 operates 82-86% as the sweet spot, <72% sustained means bench bloat, >88% means no capacity for new ramps.
- **Attrition** — 14-22% normal, >25% is stress (talent fleeing while vendor claims demand is strong is a business-quality red flag). Post-2022 boom, sector attrition normalised from 25-30% peak back to 13-18%.
- **Operating margin** — tier-1 18-25% (wide band reflects Big-5 dispersion: TCS/Infosys sit at the top 22-26%, HCLTech/Wipro/TechM at 16-19%), mid-cap 15-22%, ER&D 16-22%, platform/product 18-28% (with GM>70%). Below the sub-type band for 2+ quarters indicates lost pricing power, not just cyclicality.
- **Offshore revenue share** — tier-1 70-90%, mid-cap 65-80%, ER&D 55-75%. Onshore wages are 3-5× offshore, so mix-shift is the margin lever.

### Capital-Cycle Position — Discretionary vs Structural vs AI-Reframe
Three overlapping cycles drive IT services earnings; diagnose each before projecting growth:
- **Short-cycle discretionary spend** (2-3 year) — US-BFSI discretionary in 2024-25 is soft post the 2022-23 boom; enterprise buyers defer project starts and shift to cost-takeout.
- **Long-cycle digital transformation** (10-year) — cloud migration, data-platform rebuild, and modernisation are structurally tailwinded irrespective of discretionary cycle.
- **AI / GenAI reframe** (5-10 year structural) — productivity gains shrink billable hours on legacy T&M work; pricing model shifts toward fixed-fee and outcome-based contracts. This is not yet reflected in tier-1 reported revenue, which is why the current PE is re-rating downward even with stable near-term growth.

State which cycle phase is dominant for the company's vertical and geography mix; contradictory phases (soft discretionary + strong structural migration) produce the interesting setups.

### Sector-Specific Red Flags for Business Quality
Business-quality stress surfaces earlier than financial-quality stress. Scan for:
- **TCV deceleration YoY for 2+ consecutive quarters** — the cleanest leading indicator; revenue follows with a 3-4 quarter lag.
- **Top-5 client concentration >40%** — renewal risk, insourcing risk, or a single client's cost-takeout decision can reprice the stock.
- **Rising attrition during weak demand** — talent fleeing a vendor whose management claims the pipeline is strong is a signal-reversal (the insiders know).
- **Utilisation <72% sustained** — bench bloat eating margin without a demand-ramp line of sight.
- **Large-deal wins <1-2 per quarter for tier-1s** — the deal-pursuit engine is losing; mid-cap niche plays face margin compression from pricing pressure on renewal-heavy books.
- **Book-to-bill <1.0 for 2+ quarters** — vendor is consuming backlog without refilling it.

### Data-shape Fallback for Unit Economics
If `get_fundamentals(section='revenue_segments')` returns aggregate-only and `get_company_context(section='sector_kpis')` reports `status='schema_valid_but_unavailable'` for revenue-per-FTE, utilisation, or top-client concentration, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and `sub_section='operational_metrics')` — scan the earnings-call transcript for disclosed utilisation %, attrition %, top-5 client share, TCV, and book-to-bill. Cite the quarter. If concall is silent too, add to Open Questions tied to the specific unit.

### Open Questions — IT Services Business-Specific
- "What is the CC revenue growth vs reported growth over the last 4 quarters, and what share of the delta is FX vs organic?"
- "Is account bucket migration (number of $5M / $20M / $50M / $100M+ clients) showing net upward movement, or is growth coming only from new logos?"
- "What is the current offshore-revenue share and is the mix-shift lever exhausted (>82%) or still live?"
- "For AI-disruption exposure: what % of current revenue is classic T&M at risk of productivity re-pricing vs fixed-fee / outcome-linked / platform IP?"
- "Is the vertical mix (BFSI-heavy vs broad-based) consistent with the geography mix (US-heavy vs balanced), and how do both interact with the current discretionary-spend cycle?"
