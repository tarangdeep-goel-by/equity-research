## FMCG — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
FMCG is an umbrella covering at least six economically distinct archetypes. The revenue engine, distribution model, margin shape, and cycle sensitivity differ so much across them that applying a "personal care framework" to a tobacco leader (or a "packaged foods" lens to a D2C digital-native) inverts the diagnosis. State the sub-type and its primary revenue engine before decomposing growth.

| Subtype | Primary revenue engine | Unit of production | Distribution model |
| :--- | :--- | :--- | :--- |
| **Personal care / HPC (home & personal care)** | Volume × realization × premium-mix; soaps, detergents, skin, hair | per-SKU volume; per-outlet throughput | GT-heavy (8-12 lakh outlets for leaders) + rising MT / QC |
| **Food & beverages (packaged)** | Volume × realization × category-mix; biscuits, dairy, beverages, chocolates | per-SKU volume; per-plant capacity utilisation | GT + MT; cold-chain dependency for dairy / chocolates |
| **Packaged staples (edible oil, flour, salt, sugar)** | Volume × realization with thin fixed margin on commodity spread | per-MT processed; per-refinery utilisation | GT + MT; bulk B2B side business |
| **Tobacco / alcobev (sin-goods)** | Stick / case volume × realization; state-excise-regulated pricing | per-stick / per-case volume | State-auctioned distribution (alcobev) or licensed WD network (tobacco) |
| **OTC / wellness / consumer healthcare** | Volume × realization × category-mix; health supplements, ayurveda, ethical OTC | per-SKU volume; per-pharmacy + GT outlet | Pharmacy + GT dual channel; rising e-pharmacy |
| **D2C / digital-native** | Customer × order frequency × AOV; subscription skew in wellness | per-customer LTV; per-order contribution margin | D2C website + marketplace + QC; GT build-out Phase 2 |

State the sub-type in the report's opening paragraph before benchmarking growth, margin, or moat.

### Revenue Decomposition — Volume × Realization × Mix (Nielsen-Style)
For FMCG, revenue growth is never a single line — it is `Volume growth × Realization growth × Mix shift`. Volume itself decomposes to `underlying demand × distribution reach` (outlets added × throughput per outlet); realization decomposes to `base price × promo intensity`; mix decomposes to `premium-share % × rural-urban split × channel mix (GT / MT / e-comm / QC)`. Call `get_fundamentals(section='revenue_segments')` for the category / geography split and `get_company_context(section='concall_insights', sub_section='operational_metrics')` for the volume / price / mix disclosure. The skip-step surfaced in prior fmcg evals is citing "12% revenue growth" without naming whether it is 4% volume + 8% price, 8% volume + 4% price, or 12% price + 0% volume — the three readings imply radically different demand diagnoses. If volume is not separately disclosed, add the split to Open Questions as the #1 item.

### Moat Typology — Distinct by Sub-type
Moat lenses differ across FMCG sub-types; enumerate the one that applies before asserting "durable franchise":
- **Brand equity (decades of advertising spend)** — dominant moat in personal care and tobacco; ad-spend-to-revenue sustained at 8-13% compounds mental-availability. Brand equity is near-impossible to replicate de novo within a 5-10Y horizon.
- **Distribution depth** — leaders reach 12-15 lakh outlets; top-5 HPC names have 2-3× the direct-reach of tier-2 peers. In rural India this is the hardest moat to cross, since GT salesforce and WD / super-stockist economics take 10-15 years to build.
- **Scale in procurement** — palm oil, wheat, milk, tobacco-leaf procurement at scale gives 100-250 bps gross-margin advantage vs mid-cap peers; visible in the gross-margin gap during commodity spikes.
- **Innovation cadence (NPD contribution)** — Innovation Vitality Rate of 15-25% (% of revenue from products launched in last 2-3 years) separates structural compounders from legacy-brand milkers; <10% is brand-ageing.
- **Pricing power (take-price-without-losing-volume)** — visible when the company raises prices 4-8% in a commodity-inflation year and volume stays flat or positive; mid-cap peers usually see volume decline 2-5% at the same price move.
- **Regulatory-entrenched scale (sin-goods)** — tobacco's FDI prohibition and state-excise architecture create a near-closed competitive set where incumbent scale is protected by policy, not just brand.

### Unit Economics — Sub-type-Appropriate Ranges
Aggregate EBITDA-margin comparison across FMCG sub-types is misleading; use sub-type-specific benchmarks:
- **HPC leaders** — EBITDA margin 18-28%, gross margin 48-55%, ad-spend 8-13% of revenue (the moat-signal line).
- **Food & beverages** — EBITDA margin 8-15%, gross margin 30-42%, ad-spend 5-9% (lower advertising intensity in biscuits / dairy).
- **Packaged staples (edible oil, flour)** — EBITDA margin 4-8%, gross margin 10-18%; commodity-spread business, not a brand business despite the branded-product optics.
- **Tobacco / alcobev** — EBITDA margin 30-40% (tax-gross), 15-25% (post-excise net); pricing power regulated but persistent.
- **OTC / wellness** — EBITDA margin 14-20%, gross margin 50-60%; trade-margin heavier than HPC.
- **D2C** — contribution margin 40-60% (direct), EBITDA typically negative 5-20% while in growth-investment phase; state the burn-runway.

Ad-spend intensity at 8-13% of revenue sustained over 5+ years is the moat signal for HPC; cutting it below 6% to prop EBITDA is a business-quality red flag masquerading as a margin expansion.

### Capital-Cycle Position — Structural Growth + Short-Cycle Demand
FMCG is a structural-growth sector (household consumption compounds with nominal GDP) but with three overlapping short-cycle layers: rural demand (2-3Y mini-cycle tied to monsoon, MNREGA wages, agri incomes), urban demand (premiumization trend interrupted by household-budget pressure), and commodity input cycle (palm oil, wheat, milk, crude-derivatives). Current phase (FY24-25): rural recovering from 4-quarter slowdown, urban premiumization intact, palm and wheat stable post-2023 spike. State the phase across all three layers before forecasting near-term volume; the common failure mode is extrapolating a mid-cycle year's margin profile into perpetuity.

### Sector-Specific Red Flags for Business Quality
Business-quality stress shows up earlier in operating telemetry than in the P&L:
- **Volume growth <3% for 4+ consecutive quarters** — demand weakness or share loss; cross-check with peer-median volume growth via `get_peer_sector(section='peer_metrics')` to isolate.
- **Ad-spend cuts to defend margin** — ad-to-revenue falling 150-250 bps over 2-3 quarters while EBITDA margin holds is the textbook "eating the seed corn" move; flag explicitly.
- **Rising receivables days** — days-sales-outstanding drifting from 10-15 to 25-35 in a GT-heavy business is a channel-stuffing signal; primary-sales (company to distributor) growing faster than secondary-sales (distributor to retailer) is the leading indicator. Source via `get_fundamentals(section='working_capital')` and `get_company_context(section='concall_insights', sub_section='financial_metrics')`.
- **Distribution-share losses to D2C / QC in a key category** — legacy HPC / food leaders losing 200-400 bps category share to digital-natives (especially in skin, hair, health) indicates the GT moat is leaking in that specific pocket even if aggregate share looks stable.
- **Innovation Vitality Rate declining below 10%** — sustained under-investment in NPD signals brand-ageing even if current volume holds.
- **Royalty / technology-fee creep (MNC subs)** — % of revenue drifting from 1-2% toward the 5% SEBI LODR materiality threshold is margin-siphon to the foreign parent; flag as minority-shareholder governance concern.

### Data-shape Fallback for Volume / Mix Disclosure
If `get_fundamentals(section='revenue_segments')` returns aggregate-only and `get_company_context(section='sector_kpis')` reports `status='schema_valid_but_unavailable'` for volume or mix KPIs, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and scan for disclosed volume %, rural / urban growth delta, premium-share %, and e-comm / QC contribution. Cite the specific quarter. If the concall is silent on the volume-price split, add to Open Questions as the top item — the decomposition is load-bearing for the entire business diagnosis.

### Open Questions — FMCG Business-Specific
- "What is the volume-vs-price-mix split for the most recent 2-3 quarters, and is the pattern consistent with peer-median or diverging?"
- "What is the current rural-vs-urban volume-growth delta, and is rural showing signs of sustained recovery or another leg down?"
- "What is the Innovation Vitality Rate (% of revenue from products launched in last 2-3 years), and is it trending up or down over the last 4-6 quarters?"
- "For MNC subsidiaries: what is the current royalty / technology-fee as % of revenue, and is the trajectory approaching the 5% SEBI LODR materiality threshold?"
- "What is the e-comm + QC share of urban revenue, and is its incremental contribution GT-cannibalising or incremental demand?"
