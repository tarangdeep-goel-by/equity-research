## Conglomerate — Business Agent

### Sub-type Archetype — Classify Before Decomposing
"Conglomerate" is not a single business; it is four distinct structural archetypes, each with a different moat lens, capital-allocation question, and re-rating catalyst. State the sub-type in the first paragraph of the report before any A×B decomposition — the analytical frame is wrong if the archetype is wrong.

| Sub-type | What it is | Dominant analytical lens |
| :--- | :--- | :--- |
| **Pure holdco (investments only)** | No operating business; P&L is dividends received + MTM on listed stakes + treasury income | NAV mark-to-market vs market cap; holdco discount trajectory is the entire thesis |
| **Listed operating + holdings (most common)** | One or two core operating verticals at the parent + listed/unlisted subsidiaries across other verticals | Standalone (ex-SOTP) franchise quality + holdco SOTP decomposition |
| **Multi-vertical operating company** | Genuine operating business across 3+ unrelated verticals (chemicals + IT services + financial services, etc.) without a dominant flagship | Per-vertical ROCE dispersion; consolidated ROCE only as an averaging check |
| **Promoter-group-linked conglomerate** | Listed entities that are part of a larger promoter group holding cross-shareholdings in sister listed entities | Group-level governance + related-party exposure mapping; valuation has a complexity premium or discount relative to standalone cash flows |

Confirm the sub-type via `get_fundamentals(section='revenue_segments')` for vertical count and contribution, then `get_valuation(section='sotp')` for listed-subsidiary stake map. An "operating conglomerate" that is actually 80% one vertical is a focused business with cosmetic diversification — call it out.

### Revenue Decomposition — Per-Vertical A × B, Never a Consolidated Single Line
Consolidated revenue growth is a weighted average that hides the actual story in every period. For every vertical contributing **>10% of consolidated revenue**, decompose separately into volume × price (or AUM × fee yield, or premium × persistency) — whichever A×B fits the vertical's business model. Aggregate separately; never claim consolidated growth without first stating which verticals drove it.

- Specialty chemicals vertical — volumes (KT) × realization per tonne; split between commoditised and specialty mix
- IT services vertical — headcount × billed utilisation × realised rate per hour
- Financial services / NBFC vertical — NIM × average earning assets
- AMC sub-entity — AUM × blended fee yield bps
- Consumer / retail vertical — same-store-sales growth × store additions × per-store throughput
- Infrastructure / industrial vertical — capacity utilisation × realisation per unit

Source the per-vertical P&L from `get_company_context(section='concall_insights', sub_section='operational_metrics')` and the revenue split from `get_fundamentals(section='revenue_segments')`. If a vertical >10% has no disclosed unit-level operational metric, flag it as a segment-reporting opacity concern.

### Moat Typology — Per-Vertical Moat Is Not Additive
A conglomerate does not inherit a "combined moat" by summing across verticals — per-vertical moats are independent and the **weakest-vertical moat is often the binding constraint on group ROCE**. Enumerate the moat lens per material vertical (brand strength, distribution density, switching cost, regulatory licence, cost-curve position, scale economics), then answer the meta-question at the parent level: **is there a capital-allocation moat?**

Capital-allocation discipline is the real holdco meta-moat: does the parent redeploy excess cash from the high-ROCE vertical into the next-highest-ROCE vertical, or does it subsidise underperformers to avoid write-downs? Check `get_fundamentals(section='capital_allocation')` and `get_company_context(section='concall_insights', sub_section='management_commentary')`: a parent that has materially shifted segment-level capex allocation over 3-5 years in response to segment-level ROCE divergence has demonstrated the meta-moat. A parent that spreads capex pro-rata across verticals regardless of ROCE has not.

### Unit Economics — Consolidated ROCE vs Per-Vertical ROCE
The diagnostic question for a conglomerate's business quality is **ROCE dispersion**: are all material verticals above their respective sector-median ROCE, or is a high-ROCE vertical dragging a low-ROCE vertical? A conglomerate that trades at a premium multiple must earn it vertical-by-vertical, not through averaging. Common patterns:

- All verticals above sector-median ROCE — rare and premium-worthy; holdco discount should compress
- Strong flagship + underperforming auxiliaries — the norm; holdco discount is deserved until the underperformers are divested or fixed
- Weak flagship + strong auxiliary — the parent's discount is actually masking the embedded-option value; look for subsidiary-IPO catalysts
- Consolidated ROCE drifting down 200-400 bps over 5 years despite stable sector-ROCE in each vertical — signal that cross-subsidy is accelerating

Route the arithmetic through `calculate` with segment EBIT and segment capital employed as named inputs; pull peer-sector ROCE per vertical from `get_peer_sector(section='benchmarks')`.

### Capital-Cycle Position — Each Vertical Has Its Own Cycle
Consolidated P&L is a weighted average of per-vertical capital cycles; that averaging is either the structural case for owning the conglomerate (counter-cyclical mix) or the reason to discount it (correlated cyclicals bundled together). Enumerate the cycle phase per material vertical (early / mid / late / stressed) and ask the portfolio question explicitly: **are the verticals counter-cyclical or correlated?**

- Counter-cyclical mix (e.g., infrastructure + consumer staples + tech services) — the structural case; consolidated cash flow is smoother than any vertical standalone, supports higher leverage
- Correlated cyclicals (e.g., metals + capital goods + construction) — the portfolio is a single macro bet with complexity; discount is deserved
- One dominant late-cycle vertical + small counter-cyclical verticals — consolidated earnings are driven by the dominant vertical; the diversification is cosmetic

### Sector-Specific Red Flags for Business Quality
- **Cross-subsidy pattern** — one vertical reporting EBIT losses for 3+ consecutive years while receiving incremental capex. The profitable verticals are funding the write-down-deferral; thesis realisation for the profitable parts is delayed indefinitely.
- **Aggressive inter-company loans** to listed or unlisted subsidiaries where the subsidiary's standalone CFO does not service the loan — the parent is effectively capitalising the subsidiary through a debt line rather than equity contribution, hiding the capital commitment.
- **Related-party-transaction concentration** rising above 10% of revenue or net worth — extract from `get_company_context(section='filings', sub_section='notes_to_accounts')`; sustained rise across 4-6 quarters signals a governance-drift pattern before it shows up in headline results.
- **Segment-reporting opacity** — a previously-reported segment being merged into "others" or being re-defined to lump a weak vertical into a strong one. Ind-AS 108 allows re-segmentation but the reconciliation trail usually sits in the notes; sustained opacity is the red flag.
- **Capex into unrelated ventures without disclosed IRR** — a chemicals company announcing ₹5000 Cr into a greenfield EV-component plant without stating target ROCE and a 5-year ramp path is a capital-allocation-discipline failure regardless of how strategic the vertical looks.

### Data-shape Fallback for Per-Vertical Analysis
If `get_fundamentals(section='revenue_segments')` returns only a consolidated line and `get_company_context(section='sector_kpis')` reports `status='schema_valid_but_unavailable'` for segment EBIT and segment capital employed, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and scan the earnings-call transcript for management's disclosed segment margins, segment capex, and segment asset base. Cite the quarter. If the narrative too is silent on any vertical representing >10% of consolidated revenue, add to Open Questions and flag as a segment-reporting opacity concern.

### Open Questions — Conglomerate Business-Specific
- "What is the 5-year ROCE trajectory per vertical, and is the lowest-ROCE vertical receiving capex above its depreciation run-rate?"
- "Has any previously-disclosed segment been merged, renamed, or re-defined in the last 8 quarters, and is the reconciliation trail disclosed?"
- "What is the inter-company loan and corporate-guarantee exposure between the parent and each material subsidiary, and does the recipient subsidiary's standalone CFO service those loans?"
- "For the weakest vertical: is there a disclosed 3-5 year path-to-ROCE target, or is it being maintained for strategic / promoter-legacy reasons?"
- "Does the group's 5-year segment capex allocation reflect the per-vertical ROCE hierarchy, or is it pro-rata regardless of return quality?"
