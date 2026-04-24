## Pharma — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
"Pharma" is an umbrella label hiding at least seven economically distinct business models. The revenue engine, moat shape, unit of production, R&D intensity, and regulatory surface differ so sharply across sub-types that applying a "generics lens" to a specialty player (or a "branded-formulations frame" to a CDMO) inverts the diagnosis. State the sub-type and its primary revenue engine before decomposing growth.

| Subtype | Primary revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **US-generics-heavy** | ANDA portfolio × volume × (price − erosion) | price erosion vs launch cadence | ANDAs filed/approved, US revenue/ANDA, FDA plant count |
| **India-branded formulations** | Prescription volume × brand price × MR coverage | chronic/acute brand-mix × MR productivity | MR count, brand rank-in-therapy, chronic % of revenue |
| **Specialty (complex generics + innovative)** | Molecule-level portfolio × pricing power per NDA/505(b)(2) | molecule differentiation × exclusivity runway | specialty revenue per molecule, approved NDA count |
| **CDMO / CMO** | Active-projects × contract value × phase-mix (Ph1/2/3/commercial) | innovator-client pipeline conversion | active projects, commercial-project share, capacity utilisation |
| **API / bulk drugs** | Volume × spread (KSM-to-API conversion) × customer mix | KSM sourcing × regulatory filings (DMFs) | DMF count, captive vs merchant API split |
| **Animal health** | Livestock/companion volume × SKU portfolio × distribution depth | species mix × geographic spread | livestock units served, companion-animal SKU share |
| **Consumer health / OTC** | Brand volume × price × distribution reach | category leadership × household penetration | retail outlet count, top-brand share-of-category |

### Revenue Decomposition — Always (Volume × Realization × Mix), Never a Single Line
For any pharma sub-type, `Revenue = Volume × Realization × Mix`, but the mix vector varies. For US generics: `Revenue = ANDA-portfolio-breadth × units × (list price − GTN adjustments − YoY price erosion)`; a reported 8% US growth with volume flat and two new launches means launches added ~14% while base book eroded ~6% — the headline hides the pipeline health. For India branded: `Revenue = MR-driven prescription volume × brand price × brand-mix (chronic/acute)`; IPM growth is typically 8-11% (volume 4-6% + price 4-6% via DPCO + new-intro 2-3%), and beating IPM is the right benchmark, not absolute growth. For specialty: `Revenue = specialty portfolio × per-molecule pricing power × exclusivity runway`; pricing power is molecule-specific, so aggregate revenue disguises portfolio health. For CDMO: `Revenue = active-projects × contract value × phase-mix`; a project moving from Ph2 to commercial can 5-10× its revenue contribution over 2-3 years. Call `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')` for the decomposition; if segmented revenue is unavailable, route to `financial_metrics` narrative for geography and segment mentions.

### Moat Typology — Distinct by Sub-type
A generics moat is not a branded-formulations moat is not a CDMO moat. Enumerate the moat lens that applies before asserting "durable franchise":
- **Process IP (specialty / complex generics)** — multi-step synthesis routes, particle-engineering know-how, sterile/injectable manufacturing competence. The barrier is not the molecule but the ability to manufacture it at cGMP scale with reproducible bioequivalence; this is a 3-7Y build, not a licensing arrangement.
- **Regulatory moat (US-facing manufacturers)** — USFDA-approved plant count with clean inspection history is the real barrier; a plant with a clean EIR through 4-5 cycles is worth substantially more than a fresh-approval facility. Track via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; cross-reference `get_company_context(section='filings')` for any 483 / warning letter / import alert history.
- **Portfolio breadth (US generics)** — cumulative ANDA count with a phased launch pipeline smooths price-erosion; a player with 250+ approved ANDAs and 40-80 pending has a more durable US revenue base than one reliant on 2-3 material molecules.
- **Field-force density (India branded)** — MR coverage in Tier-2/3 cities, top-10 doctor-relationship depth in target therapies. Replicating a 5,000-8,000 MR field force takes 4-6 years and ₹500-1,200 Cr of cumulative investment; the moat is the brand-MR-doctor triangle, not any single node.
- **Top-brand-in-therapy (India branded, specialty)** — holding the #1 or #2 brand in cardio / diabetes / derma / chronic respiratory gives sustained pricing power above DPCO floors (for non-scheduled molecules) and defends against me-too competition; top-brand MR productivity typically runs 30-50% above category median.
- **Patent-holder exclusivity (specialty)** — a Para IV first-to-file (FTF) with 180-day exclusivity, or an innovator NDA under orphan/patent protection, confers temporary monopoly rent. Runway is finite and must be annotated with the expiry year.
- **CDMO client-stickiness** — multi-year Ph3-to-commercial contracts with top-20 innovators create 5-8Y revenue visibility once a project crosses Ph2; the switching cost for the innovator is re-validating a supply chain, a 18-24 month process.

### Unit Economics — Segment-Appropriate Margin Bands
Aggregate P&L hides segment-level cyclicality. State segment margin bands before claiming consolidated-margin expansion or compression:
- **US generics** — EBITDA margin 15-22% in trough (competitive price erosion cycles), 25-35% at peak (limited-competition launches). Gross margin typically 50-58% ex-amortisation.
- **India branded formulations** — EBITDA margin 22-30% steady-state; top-brand-heavy portfolios (>40% chronic) can push to 28-33%. Volume-price-mix growth is consistent 10-14% for leaders.
- **Specialty (complex generics + innovative)** — EBITDA margin 30-45% given limited competition and premium pricing; however, R&D-to-revenue runs 10-18% (vs 5-8% for generics), so the operating-margin advantage is partly re-invested.
- **CDMO / CMO** — EBITDA margin 18-28% depending on phase-mix (commercial-project share raises margin); capacity utilisation above 75-80% is the operating-leverage threshold.
- **API / bulk drugs** — EBITDA margin 18-25%, with captive-API supply to in-house formulations carrying higher internal transfer margins than merchant-API.
- **R&D intensity** — 5-8% of revenue for generics-heavy names, 10-18% for specialty-heavy; a specialty ramp without R&D % rising in parallel is either fictitious or pulling forward cost from prior years.
- **Field-force productivity (India)** — ₹15-30 lakh of prescription revenue per MR per year is the benchmark; below ₹12 lakh indicates under-productive coverage or brand-mix erosion.

Extract segment margins from `get_company_context(section='concall_insights', sub_section='financial_metrics')`; if only consolidated is disclosed, flag and add to Open Questions.

### Capital-Cycle Position — Earnings Are Cycle-Sensitive
Pharma sub-type earnings breathe with distinct cycles; extrapolating a peak or a trough forward is the most common buy-side mistake.
- **US generics** — 4-7Y price-erosion cycle overlaid on ANDA-filing waves. A name mid-cycle (3-4Y into erosion with launch pipeline thinning) looks optically cheap on trailing PE while forward earnings face 3-5% per-annum base-book erosion. State the erosion-cycle position before forecasting US revenue.
- **India branded** — steady-state ~8-11% volume growth + 4-6% price (DPCO pass-through + non-scheduled pricing) + 2-3% new-intro launches. Cycle shocks are policy-driven (DPCO expansions, trade-margin revisions) rather than demand-driven.
- **Specialty** — project-cycle 2-4Y from NDA filing to approval, then 3-5Y ramp to peak sales; a specialty launch in Yr 1-2 of ramp is a different margin profile than Yr 4-5 at steady state.
- **CDMO** — innovator-client-pipeline cycle; Ph1-Ph2 project dominance means flat revenue but a building Ph3/commercial book that inflects 2-3 years forward. A CDMO with 70%+ revenue from Ph1-Ph2 is pre-inflection; one with 50%+ commercial is at or past peak mix.
- **USFDA inspection cycle** — 2-3Y inspection cadence at US-critical plants; the post-warning-letter remediation cycle (typically 12-30 months) is an idle-capacity drag that compresses ROCE regardless of product pipeline.

Always state the cycle phase (early / mid / late / stressed) before projecting; contradictory phases (e.g., India branded expansion + US generics stress-phase) are the interesting setups.

### Sector-Specific Red Flags for Business Quality
Business-quality stress surfaces earlier than financial-quality stress. Scan for:
- **USFDA 483 / EIR deterioration** at a major plant — a plant that previously cleared inspections receiving 6+ 483 observations or an OAI classification is the first sign; warning-letter escalation typically follows 6-12 months later if remediation is inadequate. Track quarterly via `concall_insights`.
- **ANDA filing cadence slowing** — a player historically filing 25-40 ANDAs/year dropping to 10-15 for 2-3 consecutive years without a specialty/complex-generic portfolio pivot is harvesting rather than investing; base-book erosion will eventually outrun pipeline in 3-5Y.
- **R&D capitalization vs expensing policy change** — Indian pharma capitalises certain specialty development costs (IndAS 38); a shift in capitalisation policy that reduces reported R&D expense by 100-200 bps while specialty claims persist is optical margin, not real. Cross-check against `get_fundamentals(section='cost_structure')` and filings disclosure notes.
- **Single-molecule revenue concentration >15% of total** — one blockbuster (gRevlimid-style, specialty innovator licence, or an India branded mega-brand) above 15% is a concentrated-risk posture; material US-competitor launch or DPCO inclusion can re-price earnings 20-30% in 3-6 quarters.
- **Material US-competitor launch on a book molecule** — when a competitor receives ANDA approval for a high-margin molecule that represents 5-10% of US revenue, the expected price erosion is 40-60% in the first 3 quarters post-launch. Named-molecule watchlist management (gRevlimid, gTasigna, complex injectables) is the correct monitoring frame, not aggregate US revenue.
- **India field-force productivity decay** — MR-per-₹ revenue falling 8-15% over 4-6 quarters with flat MR headcount signals brand-mix erosion, chronic-to-acute drift, or Tier-2/3 coverage gap; compensated for in headline India growth by price/DPCO pass-through but structurally weakening.
- **KSM-sourcing concentration in China for US-critical molecules** — any single-country KSM dependency >60-70% for a US-regulated product is a strategic vulnerability; PLI-scheme benefits only materialise over 3-5Y and do not insulate near-term supply.

### Data-shape Fallback for Segment and Pipeline Disclosures
If `get_fundamentals(section='revenue_segments')` returns aggregate-only and `get_sector_kpis(sub_section='anda_filed_number'|'anda_approved_number'|'us_revenue_pct'|'india_branded_revenue_pct'|'specialty_revenue_pct')` returns `status='schema_valid_but_unavailable'`, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and `sub_section='operational_metrics')` for management-disclosed segment splits. Scan for ANDA file-count mentions, top-molecule revenue concentration, and named-facility inspection updates. If the narrative is silent, add to Open Questions with the specific unit (e.g., "US specialty revenue share for FY25 not disclosed; inferring from consolidated US growth risks mixing erosion with specialty ramp"). Cite the quarter when extracted narratively.

### Open Questions — Pharma Business-Specific
- "What is the current ANDA pipeline (filed / pending approval / expected launches next 8 quarters), and how does the launch value offset trailing 5-8% annual price erosion on the base US book?"
- "For multi-segment players: what is the segment revenue and EBITDA margin split (US generics / India branded / specialty / CDMO / API), and how has the specialty and CDMO share trended over 8 quarters?"
- "What is the USFDA inspection calendar over the next 4-6 quarters at material plants, and is any facility currently under 483 observations or OAI classification with remediation timeline unresolved?"
- "What is the KSM-sourcing mix (China % vs India % vs other), and which US-critical molecules have single-country KSM dependency above 60%?"
- "For India-branded-heavy players: what is MR count, chronic-% of revenue, and MR productivity trajectory, and is the player outgrowing IPM in the target chronic therapies (cardio / diabetes / derma / respiratory)?"
- "For CDMO: what is the active-project count by phase (Ph1 / Ph2 / Ph3 / commercial), and what share of revenue is commercial-project vs clinical?"
