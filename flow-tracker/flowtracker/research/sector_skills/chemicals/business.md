## Chemicals — Business Agent

### Sub-type Archetype — Identify the Chemicals Model Before Analysis
"Chemicals" is an umbrella label over at least seven economically distinct business models. The revenue engine, moat shape, working-capital profile, margin band, and customer architecture differ so sharply that applying a specialty lens to a commodity bulk name (or an agrochem seasonal read to a fluorochem structural story) inverts the diagnosis. State the sub-type and its primary revenue engine before decomposing growth.

| Subtype | Primary revenue engine | Typical EBITDA margin | Working-capital days | Dominant axis |
| :--- | :--- | :--- | :--- | :--- |
| **Specialty** | Molecule IP × price × qualified-customer volume | 18-28% | 150-200 | customer-stickiness, mix-shift |
| **CDMO / CRAMS** | Contract-manufacturing pipeline of innovator molecules | 20-30% | 180-250 | innovator-client retention, commercial-vs-development mix |
| **Agrochem** | Active-ingredient portfolio × formulation leverage × B2F seasonality | 12-22% (10-12% in deep-destock years like FY24-25) | 120-180 | AI/FMLG split, monsoon/export cycle |
| **Commodity bulk** | Feedstock spread × process efficiency × cycle position | 8-14% | 80-120 | utilization, input-output pass-through |
| **Fluorochem** | Specialty-mass hybrid; HFC/HFO portfolio + refrigerant-regulation cycle | 20-32% | 140-200 | Montreal Protocol phase-down, HFO capex |
| **Pigments / dyes** | Export-led formulation + textile/auto demand cycle | 12-20% | 130-190 | global textile cycle, REACH registration |
| **Custom synthesis** | Multi-step bespoke intermediates for pharma/agrochem innovators | 22-32% | 150-220 | process-complexity moat, single-molecule risk |

### Revenue Decomposition — Always (Volume × Realization × Mix)
Aggregate revenue growth without decomposition is the single most common business-agent error in chemicals. Decompose `Revenue = Volume × Realization × Mix` and separate the three drivers before claiming "growth momentum":
- **Volume** — tonnes shipped, tracked via concall "volume growth" disclosures and linked to plant utilization (not capacity nameplate).
- **Realization** — ₹/kg or ₹/tonne, heavily influenced by feedstock pass-through and product-basket weighting within the reported segment.
- **Mix** — shift from commodity to specialty, from bulk AI to formulated agrochem, from development-phase to commercial-phase CRAMS revenue. Mix shift is the margin-expansion engine, but it often hides inside a flat-volume, flat-realization top line.

Break down by **molecule tier** (niche / scale / bulk) and **geography** (domestic / LATAM / North America / Europe / rest-of-world). Exporters run 40-70% of revenue overseas, so INR moves, REACH registration status, and destination-market demand cycles swing the reported realization independently of India fundamentals. Source via `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')`.

### Moat Typology — Sub-type-Specific
A specialty moat is not a commodity moat is not a CRAMS moat. Enumerate the lens that applies:
- **Multi-step process IP** (specialty, custom synthesis) — 6+ step syntheses are structurally hard to replicate; yield optimization at each step compounds into a 30-50% gross-margin gap vs a new entrant attempting the same molecule. The moat is the know-how, not the plant.
- **Regulatory moat** (CRAMS, pharma-intermediate specialty) — USDMF, DMF, USFDA cGMP inspections, REACH registrations for EU exports. Qualification cycles of **2-4 years** per customer-plant-molecule triplet create a sunk-cost barrier; once qualified, customer switching is rare outside of a price rupture or quality failure.
- **Customer-stickiness** (specialty, CRAMS) — a qualified innovator does not re-qualify a supplier casually. Attrition is usually event-driven (molecule off-patent, customer insourcing, quality failure) rather than price-competitive.
- **Backward integration / KSM security** (specialty, agrochem) — owning the key starting material pipeline insulates margins from China-KSM import spikes. Backward integration to 2-3 steps upstream of the final molecule is the defensive moat that emerged post-FY20 China disruption.
- **Scale economics** (commodity bulk, fluorochem) — fixed-cost absorption at high utilization is the only meaningful moat in commodity; marginal producer sets the price, so cost-curve position is the entire game.

### Unit Economics — Sub-type-Appropriate Unit
The aggregate P&L hides the story. Pull the right unit:
- **EBITDA per tonne** — specialty ₹60-250k/t, commodity ₹15-50k/t, fluorochem ₹80-300k/t. A specialty name reporting EBITDA/t in the commodity band is either mis-mixed or mis-priced.
- **Plant capacity utilization** — typical through-cycle 75-85% for specialty; <65% flags demand stress or commissioning drag; >90% sustained flags the next capex trigger.
- **Working-capital-days** — specialty 150-200, CDMO 180-250, commodity 80-120. Rising WC-days without matched revenue growth is the earliest operational tell.
- **R&D as % of sales** — specialty 2-4% healthy, CRAMS 3-6% for active-pipeline names. Declining R&D intensity while revenue is flat reads as harvesting mode.

Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `get_fundamentals(section='expense_breakdown')`; if unavailable, flag rather than invent.

### Capital-Cycle Position — State the Phase
Chemicals capex moves in 2-3Y domestic cycles overlaid by long-cycle global waves. FY21-23 China+1 boom drove specialty EBITDA margins to 25-35% peaks; FY24-25 brought normalization, China destocking, and fluorochem price resets; FY26 is the stabilization base case for most specialty sub-sectors. Earnings reported in the peak window cannot be extrapolated forward — normalize to through-cycle margin before forecasting. State the cycle phase (capex-build / ramp / peak / destock / stabilization) explicitly in the business narrative.

### Sector-Specific Red Flags for Business Quality
Business-quality stress surfaces in operating disclosures earlier than in reported P&L:
- **Top-3 molecule concentration >50% of segment revenue** without a disclosed defensive pipeline — a single off-patent or de-stocking event can halve segment EBITDA.
- **Single-innovator-client revenue share >25%** in a CRAMS book — customer insourcing or portfolio rationalization at the innovator is the structural CRAMS risk.
- **Working-capital-days rising 20-40 days YoY** without matched revenue growth — channel build-up or collections slippage; cross-check against receivable-days trajectory.
- **Capex-to-revenue >30% for 2+ consecutive years without commissioning-ramp disclosure** — ROCE compression will be mechanical during build, but extended silent builds have historically preceded asset-turnover disappointments.
- **Segment-reporting opacity** — pulling specialty and commodity into a single P&L, or not disclosing molecule-tier mix, is a diagnostic hole; flag it, don't gloss over it.

### Data-shape Fallback for Unit Economics
If `get_fundamentals(section='revenue_segments')` returns aggregate-only and `sector_kpis` reports `status='schema_valid_but_unavailable'` for EBITDA/tonne or molecule-tier mix, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and scan for disclosed volume growth, realization trend, utilization %, and top-client share. Cite the specific quarter. If silent, add to Open Questions tied to the specific unit rather than averaging.

### Open Questions — Chemicals Business-Specific
- "What is the current specialty-vs-commodity revenue mix, and how has it trended over the last 8 quarters?"
- "What share of revenue comes from the top-3 molecules and the top-5 customers, and are any of those molecules approaching patent-cliff or innovator-insourcing risk?"
- "What is the plant utilization by major facility, and which capex block is next to commission with expected ramp curve?"
- "What percentage of KSM / intermediate needs is sourced from China, and is backward-integration capex addressing this dependency?"
- "For CRAMS: what is the commercial-vs-development phase revenue split, and how many Phase-III molecules are pending commercialization?"
