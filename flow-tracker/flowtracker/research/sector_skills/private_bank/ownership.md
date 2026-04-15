## Private Bank — Ownership Agent

Inherits BFSI ownership framing (see `bfsi/ownership.md`) — LIC quasi-sovereign anchor, insider-transaction framing (ESOP culture for private banks), single-period reclassification-artifact rule, and hard-evidence override rule. This file adds the private-bank-specific framing on foreign-cap headroom, ADR/GDR aggregation, institutional holder archetypes, and promoter/sponsor structure.

### 74% Foreign-Holding Cap — Aggregate vs Reported-FII
The statutory ceiling on foreign ownership in large private banks is **74% aggregate**, comprising:
- **FPI** (foreign portfolio investors, the headline "FII%")
- **FDI** (strategic foreign direct investment, often promoter-held)
- **ADR / GDR** (depositary receipts listed on NYSE / LSE)
- **NRI** (non-resident Indian holdings, with an internal 10% NRI sub-limit)

**Reported FII% alone understates true foreign holdings.** Always combine all four categories and compare to the 74% ceiling. Applying reported-FII% as if it were the aggregate inverts the headroom narrative.

- When aggregate >65%, headroom is <9pp — flag capacity constraint for incremental FII buying
- When aggregate >70%, MSCI/FTSE passive rebalance demand already largely met — new FII flow rate plateaus
- When aggregate >72%, flag "near cap — incremental FII buying requires case-by-case RBI approval"
- Reference Tenet 12 (SYSTEM prompt) on ADR/GDR aggregation

### ADR / GDR Aggregation — Mandatory Specifics
- **HDFCBANK**: ADR listing on NYSE. Retrieve ADR shares outstanding from SEC 20-F annual filing; multiply by ADR ratio to get underlying India-equivalent share count
- **ICICIBANK**: ADR listing on NYSE. Same retrieval path (SEC 20-F)
- **KOTAKBANK**: Historically ran GDR programme pre-HDFC merger era — retrieve from LSE / RBI ECB filings
- **Aggregation formula**: `true_foreign_holding_% = (direct_FPI_shares + ADR_underlying_shares + NRI_shares + FDI_shares) / total_India_equity`
- Not typically in `shareholder_detail` — `get_company_context(filings)` or concall_insights may have partial disclosure. If gap, add Open Question: "What is the current ADR/GDR outstanding as % of paid-up, and what is the combined FPI + ADR + NRI + FDI vs the 74% cap?"

### Institutional Holder Archetypes — Private Bank Specific
Decompose "FII" into archetypes rather than narrating a single aggregate line (Tenet 17, SYSTEM prompt):

1. **Sovereign / endowment / large-passive** — Vanguard (index), BlackRock iShares, GIC (Singapore), Abu Dhabi Investment Authority, Norges Bank (Norway sovereign). Each typically holds 1-3% in the top 4 private banks. Slow-moving; treat as structural floor
2. **Active foreign mandates** — Capital Group, T. Rowe Price, Fidelity, Matthews Asia. Bank-sector weight swings with macro view on India GDP / NPA cycle. Watch for coordinated active-mandate add/trim across the top-5 private banks as a sector-rotation signal
3. **Domestic DII** — SBI MF (largest across most private banks), HDFC MF, ICICI Pru MF, UTI MF, Nippon India MF. Track YoY conviction shift at the individual-MF level via `shareholder_detail`

### Promoter / Sponsor Structure — Bank-by-Bank
- **HDFCBANK**: Post HDFC Ltd merger (FY23-Q4), the "promoter" category was collapsed. Classify as **"foreign-institution-heavy no-promoter" structure**. The merged entity has no named promoter; all float is institutional + retail. This makes the 74% aggregate foreign cap particularly binding
- **KOTAKBANK**: Uday Kotak is the named individual promoter. **SEBI-mandated promoter-cap reduction to 26% by 2030 is in progress** — promoter stake must decline each year via OFS / sell-downs. Track every quarter as a structural dilution driver — Tenet 9 does NOT fully apply here because there is a regulator-mandated open-market reduction schedule
- **AXISBANK**: No single majority promoter. Specified Undertaking of UTI (SUUTI), LIC, and GIC collectively act as "promoter-like" stable institutional anchors post-promoter dilution era. Track as a pseudo-promoter bloc
- **INDUSINDBK**: Hinduja Group family promoters hold ~16%. Classic family-group holdco structure — Tenet 9 applies (absence of open-market promoter trade is structural, not informational). Watch for inter-group pledge activity as the real signal
- **ICICIBANK**: No single promoter — widely held; institutional dominance with LIC and GIC as stable large holders
- **IDFCFIRSTB**: Warburg Pincus-era PE-backed structure; recent "no promoter" classification; track ESOP-era insider selling clusters

### LIC Anchor Pattern (Private Banks)
LIC holds 3-9% across the top-5 private banks. Treat as sovereign-wealth-style conviction per the BFSI LIC framing. For HDFCBANK, ICICIBANK, AXISBANK, KOTAKBANK, LIC adds typically move in 10-40 bps increments per quarter. A YoY LIC add of >100 bps against market volatility is a structural absorption signal — flag as such, not as tactical conviction.

### FPI Concentration Norms — Entity + Sector Sub-limits
On top of the aggregate 74%:
- **Per-FPI (entity-level) limit**: 10% of paid-up for any single FPI group
- **NRI aggregate**: 10% of paid-up
- **RBI sector-cap list**: triggered when aggregate is within 2pp of the 74% ceiling — fresh FPI buying then requires explicit approval
- Flag in Open Questions if any individual FPI is approaching the 10% per-entity sub-limit

### Mandatory Ownership Checklist (Private Bank)
Before drafting the Institutional Verdict, explicitly confirm each row:

- [ ] Subtype identified: large private / mid-tier private / small private
- [ ] Aggregate foreign-holding cap = 74% (RBI Master Direction) stated
- [ ] Current aggregate foreign = FPI + ADR/GDR + NRI + FDI — vs 74% = headroom in pp
- [ ] ADR/GDR outstanding retrieved (mandatory for HDFCBANK, ICICIBANK; verify for others)
- [ ] Promoter structure classified (no-promoter post-merger / individual promoter / family group / pseudo-promoter bloc)
- [ ] Specific cap-reduction schedule flagged (KOTAKBANK-style) if applicable
- [ ] LIC stake classified as structural floor / active holding
- [ ] FII decomposed into sovereign / active / DII archetypes (Tenet 17)
- [ ] Insider transactions framed as ESOP-driven (selling clusters = signal, absence of buying = neutral)
- [ ] Any single-quarter ownership change >5pp verified against corporate actions / reclassification triggers
- [ ] Per-FPI 10% entity sub-limit checked if any individual FPI is large

### Open Questions — Private-Bank-Specific
- "What is the current ADR/GDR outstanding as % of paid-up, and combined direct-FPI + ADR + NRI + FDI vs 74% cap?"
- "Is any individual FPI approaching the per-FPI 10% entity-level sub-limit?"
- "For KOTAKBANK: what is the trailing 4-quarter pace of promoter-stake reduction, and is the 26%-by-2030 SEBI glide path on schedule?"
- "Is the Hinduja-Group pledged-share ratio in INDUSINDBK within the family-group disclosure norm, or rising?"
- "Has any recent RBI disclosure moved this bank onto the sector-cap list (<2pp from 74%)?"
