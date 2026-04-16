## Conglomerate — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Structure
A pure holdco's dominant risk is NAV compression on listed-sub dislocation; a listed-operating-plus-holdings structure carries standalone operating risk layered with subsidiary-contagion risk; a multi-vertical operating company's dominant risk is weakest-vertical drag on consolidated ROCE; a promoter-group-linked conglomerate carries group-governance contagion as its dominant axis. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in conglomerates typically surfaces through balance-sheet telemetry and related-party patterns 4-8 quarters before a headline event. Scan systematically:

- **Chronic promoter pledge at holdco level** — pledge share of promoter stake >30% persisting across 4+ quarters; cross-check via `get_ownership(section='promoter_pledge')` including `margin_call_analysis` for trigger-price mapping
- **Inter-company loans flowing FROM listed entity TO promoter-group unlisted entities** — extract from `get_fundamentals(section='balance_sheet_detail')` and the related-party disclosure in `get_company_context(section='filings', sub_section='notes_to_accounts')`. A listed cash-generator parent extending ICDs / advances to unlisted group entities that do not service them from standalone CFO is the canonical cash-siphoning pattern
- **Board-composition without independent majority** — particularly critical for promoter-group-linked structures where related-party approvals are frequent
- **Auditor-resignation clusters** — cross-check via `get_events_actions(section='material_events')` and the filings trail; auditor rotation that lands in a quarter of ratings-watch, SEBI correspondence, or large RPT approval requirement is the forensic-grade tell
- **Material RPT as % of revenue rising above 10%** — or RPT as % of net worth rising above 15-20%; sustained rise across 4-6 quarters is a governance-drift pattern. SEBI LODR threshold for material-RPT is 10% of consolidated turnover or ₹1,000 Cr (whichever is lower)
- **Non-Disposal Undertakings (NDUs)** in place of formal pledge — conglomerates frequently use NDU structures to bypass SEBI pledge-disclosure norms; the ownership agent's findings on NDUs should flow into the risk narrative

### Regulatory Risk Taxonomy — Multi-Regulator Inherent
Conglomerates carry inherent multi-regulator exposure: SEBI at the holdco level, RBI for any NBFC / bank subsidiary, IRDAI for any insurance subsidiary, plus sector-specific regulators (CERC for power, TRAI for telecom, DoT for spectrum, MoEF for environmental clearances, CCI for anti-trust). Name the specific regulator and, where possible, the specific circular when a risk crystallises:

- **SEBI** — LODR (Listing Obligations and Disclosure Requirements) Chapter IV on related-party transactions; Chapter V on material-event disclosure; insider-trading norms; takeover-code thresholds at 25% and 26%
- **RBI** (for NBFC / bank subs) — Basel III, PCA framework, Large Exposure Framework, IRAC provisioning norms
- **IRDAI** (for insurance subs) — solvency minima, EoM / commission caps, product-approval
- **CCI** — M&A clearance for any intra-group restructuring; group-control tests
- **FEMA** — foreign-subsidiary activities, ODI (overseas direct investment) compliance for offshore operations
- **Income Tax (transfer pricing)** — intra-group cross-border service charges, royalty flows, and ICD interest rates are transfer-pricing-scrutiny surfaces for group structures spanning multiple jurisdictions

Vague "regulatory risk" framing loses the traceability that makes the risk actionable; state the specific master-direction / circular / section when the risk is sector-specific.

### Operational Risk — Cross-Subsidy Drag and Cascade Patterns
- **Cross-subsidy drag** — one vertical reporting EBIT losses for 3+ consecutive years while receiving capex is a latent ROCE drag; quantify by computing what consolidated ROCE would be if the loss-making vertical were cost-of-capital-rated
- **KMP churn at parent vs subsidiary level** — disproportionate churn at a specific subsidiary (CEO, CFO exits in clusters) often precedes a write-down or a mis-selling-investigation episode; cross-check via `get_events_actions(section='material_events')`
- **Technology / platform-shift risk cascading** — a single vertical's disruption (e.g., payment-rails shift impacting a group fintech sub) can cascade through the group when the parent has extended guarantees or funding lines to that sub
- **Key-customer concentration at subsidiary level** — a group IT-services subsidiary with a top-5-customer concentration > 50% is carrying contract-renewal risk that compounds to the parent via dividend compression, not direct P&L impact

### Bear Cases — 30-50% Drawdown Triggers
Historical conglomerate drawdowns have recurring triggers; use them as the scaffolding for a named bear case, not as generic risks:

- **Governance event on the group** — SEBI / CBI / ED investigation, short-seller report, or auditor-qualification that reprices all listed group entities simultaneously. Historical pattern: 30-50% drawdown in 2-6 weeks, 4-8 quarters to recover (if the narrative can be rebuilt)
- **Subsidiary-level blow-up** — combined-ratio spike at the insurance sub, liquidity crisis at the NBFC sub, plant incident at the chemicals sub, fraud at the consumer sub. Direct parent impact depends on guarantees extended and equity capital at risk
- **Holdco leverage spiral** — when parent standalone debt exceeds sub-dividend capacity and subsidiaries cut dividends during their own stress, refinancing forces a distressed equity raise or asset sale at depressed multiples
- **Promoter-pledge margin call** — cross-check via `margin_call_analysis` in `get_ownership(section='promoter_pledge')`; a 20-30% stock-price fall triggering margin calls on pledged promoter stake creates forced selling that compounds the fall
- **Regulatory action on a flagship subsidiary** — licence suspension, capital-raise mandate, or operating restriction on the highest-NAV subsidiary reprices the SOTP NAV and widens the holdco discount simultaneously
- **Counterparty / customer concentration event** — default or exit of a top customer / borrower / counterparty that was disproportionately supporting group-level revenue or CFO

Quantify each bear case as a thesis-breaker: the specific metric threshold beyond which the base-case thesis is invalidated.

### Sector-Specific Stress Tests
Route all stress calculations through `calculate` with named inputs; never assert a sensitivity without the arithmetic.

- **40% fall in market cap of largest listed subsidiary** — compute % impact on SOTP NAV given parent stake %, then apply the current holdco discount to map to market-cap impact per share; a 40% sub-fall on a subsidiary representing 50% of SOTP NAV compresses SOTP-NAV per share by ~20%
- **25% widening of holdco discount** — from current X% to X+25pp; maps directly to per-share market-cap impact via (1 − new_discount) / (1 − old_discount) − 1
- **Parent-debt refinancing at 200 bps higher spread** — incremental interest cost = standalone debt × 2.0%; map to % of standalone PAT and state the dividend-payout implication
- **Demerger scenario** — base case holdco discount compresses fully (SOTP-NAV realised); bear case discount becomes permanent and the restructuring-cost line reduces NAV by 2-5%. State both paths
- **Promoter pledge margin-call cascade** — use trigger prices from `margin_call_analysis` to state the price level at which 10%, 25%, 50% of pledged stake would hit margin calls, and the incremental free-float selling that implies

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='risk_flags')` and `get_ownership(section='promoter_pledge')` return missing RPT / pledge / auditor data, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='management_commentary')` for management-disclosed positions; (2) `get_company_context(section='filings', sub_section='notes_to_accounts')` for the most recent annual-report RPT schedule and contingent-liability disclosure; (3) `get_events_actions(section='material_events')` for governance events, auditor transitions, ratings actions, and SEBI correspondence. Cite the source document and date for every extracted number. Do not fabricate RPT percentages or pledge levels — the risk agent's credibility depends on citing what the company actually disclosed.

### Open Questions — Conglomerate Risk-Specific
- "What is the aggregate promoter pledge across all group-listed entities (not just this ticker), and at what price levels do margin calls cascade across the group?"
- "What is the contingent-liabilities + corporate-guarantees-extended figure as % of consolidated net worth, and has it trended materially over the last 8 quarters?"
- "What is the inter-company loan and ICD exposure between the parent and each subsidiary; do the recipient subsidiaries service those loans from standalone CFO?"
- "Are there pending SEBI / CBI / ED proceedings or tax / transfer-pricing assessments against the group that would trigger FPI reclassification, deemed-promoter tagging of any Corporate Body holder, or a disclosable material event?"
- "For the highest-NAV subsidiary: what regulatory renewals, licence conditions, or capital-requirement thresholds are due in the next 12 months that could impair NAV?"
