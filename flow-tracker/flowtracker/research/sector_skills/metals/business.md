## Metals & Mining — Business Agent

### Sub-type Archetype — Identify the Metals Business Model Before Analysis
"Metals" is an umbrella label hiding economically distinct businesses. An integrated iron-and-steel producer (own ore + coke + smelter + rolling) earns its margin on conversion spread; a non-integrated steel re-roller earns a thin toll on merchant-purchased slabs; a zinc integrated miner-smelter earns commodity-price rent; a pure iron-ore miner earns royalty-policy rent; an aluminium smelter earns power-arbitrage rent. State the sub-type and the primary revenue engine before projecting growth or margins.

| Subtype | Primary revenue engine | Cost-curve driver | Unit of production |
| :--- | :--- | :--- | :--- |
| **Integrated steel (mine-to-market)** | HRC/CRC/rebar realization × volume − captive iron-ore + coking-coal cost | Captive RM integration + scale + port/logistics | EBITDA/tonne of crude steel; blast-furnace utilization % |
| **Non-integrated steel** | Product realization − merchant slab/billet cost | Exposure to spot slab prices; toll-margin volatility | EBITDA/tonne of finished steel; conversion spread (HRC − slab) |
| **Aluminium** | LME primary aluminium + product premium − alumina + power cost | Captive bauxite + captive power (coal or renewable) | EBITDA/tonne; power cost per tonne; captive-power share % |
| **Zinc / lead integrated** | LME zinc/lead + byproduct silver − mining + smelting cost | Ore grade + byproduct credits + smelter utilization | EBITDA/tonne of refined metal; mined-metal volume |
| **Copper smelter** | LME copper + TC/RC on concentrate − smelting cost | Smelter utilization + byproduct acid/precious-metal credits | Refined copper volume; TC/RC spread |
| **Iron-ore mining (pure)** | NMDC-style pricing policy or auction-linked FoB realization − mining cost − royalty | Mine-grade, stripping ratio, railway evacuation | Saleable ore volume; ₹/tonne realization net of royalty |
| **Specialty / alloy steel** | Value-added product premium over commodity HRC | Grade mix (auto / CRGO / stainless) and customer-qualified contracts | EBITDA/tonne vs commodity HRC benchmark |
| **Diversified mining** | SOTP of ore-only, smelter, rolled-products segments | Per-vertical cost-curve position | Per-segment EBITDA/tonne |

### Revenue Decomposition — Always Volume × Realization × Mix
For every metals producer, decompose `Revenue = Volume × Realization × Product-mix`. Headline revenue growth without the split is diagnostically empty because realization is commodity-price-linked and moves 10-30% across a cycle quarter without any volume or mix change. For steel, realization is the weighted HRC / CRC / coated / long-product / export basket; a 200 bps shift toward exports versus flat-domestic changes blended realization by 3-6% at constant volume. For aluminium, realization splits into LME primary + product premium (rolled / extruded / foil premiums run $150-400/t above LME). For zinc, byproduct silver credits are 15-25% of realization at current silver prices — a fact the headline "zinc price" obscures. Pull the split from `get_fundamentals(section='revenue_segments')` and the operating-metrics disclosures in `get_company_context(section='concall_insights', sub_section='operational_metrics')`.

### Moat Typology — Raw-Material Integration Is the Dominant Axis
The single largest moat in metals is raw-material integration, because it anchors cost-curve position through the cycle:
- **Captive iron ore + coking coal (integrated steel)** — 40-60% lower RM cost per tonne than merchant buyers, worth $50-80/t of through-cycle EBITDA advantage. This is the difference between sector-leading ROCE and marginal survival.
- **Captive bauxite + captive power (aluminium)** — bauxite integration is $50-80/t advantage; captive coal-fired or renewable power is $200-400/t advantage because power is 35-40% of smelting cost. A smelter on grid power in a rising-tariff regime is structurally uneconomic.
- **Integrated mine + smelter (zinc, lead, copper)** — avoids TC/RC spot-market dependence; mine-to-metal producers retain ~100% of the value chain versus 60-70% for custom smelters.
- **Scale and port proximity** — top-2 in segment get logistics, procurement, and freight-rate advantages worth 2-4% of revenue; coastal plants save $15-25/t on export logistics.
- **Specialty-grade qualification** — automotive CRGO, API-grade pipe steel, stainless, alloy steel have multi-year customer-qualification cycles and enjoy $80-150/t premium over commodity HRC, insulating margins from commodity cycle.
- **Resource-reserve quality (mining)** — ore grade, strip ratio, and reserve life. A declared reserve-life of 25-40 years at 63-65% Fe grade is the quiet moat of the top Indian iron-ore producer versus 18-22 years at 58-60% grade for mid-tier miners.

Source integration profile from `get_company_context(section='concall_insights')` and `get_peer_sector(section='benchmarks')` when disclosed.

### Unit Economics — EBITDA per Tonne by Segment, Through-Cycle
The correct unit of account is EBITDA per tonne, not reported operating margin percentage. A rising HRC price inflates both revenue and EBITDA, leaving margin% flat while EBITDA/tonne explodes — the margin optic misses the commodity rent. Sub-sector through-cycle ranges and peak-cycle overshoots:
- **Integrated steel** — through-cycle $80-140/t; peak $180-250/t; trough $20-60/t; the highest-cost decile turns negative at trough.
- **Non-integrated steel** — through-cycle $30-70/t; peak $80-120/t; trough can turn negative.
- **Aluminium** — through-cycle $300-500/t; peak $700-1000/t; trough $100-200/t.
- **Zinc / lead integrated** — through-cycle $800-1500/t; peak $2000-2500/t; trough $400-700/t.
- **Copper smelter** — $200-400/t of refined copper through-cycle; heavily swung by TC/RC and byproduct credits.

Capacity utilization is the second unit economic: top-tier producers sustain 85-95%; stressed producers slip to 70-80% during trough; below 70% means fixed-cost deleverage and rapid margin collapse given the high fixed-cost intensity (50-70% of cost base is fixed in integrated steel and aluminium). Extract utilization quarterly from `get_company_context(section='concall_insights', sub_section='operational_metrics')`.

### Capital-Cycle Position — 4-7Y Commodity Cycle × Long-Wave Infra Cycle
Metals breathes through two superimposed cycles. The short-wave commodity cycle (4-7 years, driven by China steel demand, global auto / construction demand, and supply-side China-stimulus or environmental-shutdown episodes) shows up in LME / HRC spot prices. The long-wave infrastructure cycle (15-20 years, driven by EM urbanisation and developed-world energy-transition capex) shows up in multi-year average demand growth. Current Indian metals regime (2026): post-China-stimulus unwind + India infrastructure capex tailwind (Gati Shakti, dedicated freight corridors, steel-intensive renewable buildout), with CBAM carbon-cost impact on EU-facing exports crystallising. State the cycle phase for each wave before projecting EBITDA:
- Short-wave phase: expansion / peak / contraction / trough. Late-peak is the dangerous buy; post-trough is the tailwind.
- Long-wave phase: domestic demand expansion (India now) vs global-demand mature (developed markets).

### Sector-Specific Red Flags for Business Quality
- **Leverage above 2× net-debt/EBITDA in the late-cycle phase** — because EBITDA is cycle-peak-inflated, the "low" leverage ratio will look very different at trough; absolute net-debt trajectory matters more than the ratio.
- **Large capex announcements at cycle peak** — the industry's single most recurring capital-allocation error. 15-20% capacity-addition commitments made at peak HRC / LME prices typically come online into a trough, producing a 2-3 year ROCE collapse.
- **Volume growth via discount / realization lag** — if sector volumes grew +5% and the company grew +12% but blended realization is 4-6% below peer, it is buying share at the expense of margin. Flag by comparing volume-growth delta vs realization-delta delta against `get_peer_sector(section='benchmarks')`.
- **EBITDA-per-tonne compression vs peer in a rising-price regime** — when HRC is up 15% and the company's EBITDA/tonne is flat, raw-material integration is weaker than stated or fixed-cost absorption is failing.
- **Environmental-clearance overhang on announced expansions** — MoEF&CC clearance delays or Supreme Court challenges on announced capacity deny the earnings narrative; the stock trades the announced EBITDA but the clearance probability is the real variable.
- **Rising inventory days in a falling commodity-price regime** — working-capital trap; inventory written down next quarter.

### Data-shape Fallback for Operating Metrics
If `get_fundamentals(section='revenue_segments')` returns only aggregate revenue and `get_company_context(section='sector_kpis')` reports per-tonne metrics as `status='schema_valid_but_unavailable'`, fall back to `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `sub_section='management_commentary')` for disclosed volume, realization, EBITDA/tonne, and capacity-utilization figures. Cite the quarter. If management prose is also silent, add a targeted Open Question naming the specific unit — do not infer volumes from revenue divided by HRC spot.

### Open Questions — Metals Business-Specific
- "What is the captive iron-ore and coking-coal share for the current quarter, and how has the integration profile shifted over the last 4 quarters?"
- "What is the EBITDA per tonne split by segment (steel / aluminium / zinc / rolled-products) and how does it compare to through-cycle vs peak for each?"
- "Of the capex envelope announced for the next 3 years, what share is growth vs maintenance, and at what HRC / LME price assumption is the project IRR underwritten?"
- "What is the current capacity utilization and where does it sit in the 10Y range; is any environmental-clearance or mine-lease-renewal event pending that would impact utilization in the next 4-6 quarters?"
- "For export-facing volumes, what is the estimated CBAM carbon-cost impact per tonne from 2026 onwards, and has the company started a DRI / EAF shift or renewable-power plan to mitigate?"
