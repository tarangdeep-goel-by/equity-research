## Conglomerate — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Structure
A pure holdco's dominant risk is NAV compression on listed-sub dislocation; a listed-operating-plus-holdings structure carries standalone operating risk layered with subsidiary-contagion risk; a multi-vertical operating company's dominant risk is weakest-vertical drag on consolidated ROCE; a promoter-group-linked conglomerate carries group-governance contagion as its dominant axis. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in conglomerates typically surfaces through balance-sheet telemetry and related-party patterns 4-8 quarters before a headline event. Scan systematically:

- **Chronic promoter pledge at holdco level** — pledge share of promoter stake >30% persisting across 4+ quarters; cross-check via `get_ownership(section='promoter_pledge')` including `margin_call_analysis` for trigger-price mapping
- **Inter-company loans flowing FROM listed entity TO promoter-group unlisted entities** — extract from `get_fundamentals(section='balance_sheet_detail')` and the related-party disclosure in `get_company_context(section='filings', sub_section='notes_to_accounts')`. A listed cash-generator parent extending ICDs / advances to unlisted group entities that do not service them from standalone CFO is the canonical cash-siphoning pattern
- **Double-leverage ratio >100%** — holdcos frequently raise debt at the parent and inject it as *equity* into subsidiaries, so the same rupee is debt at the holdco and equity at the sub; consolidated D/E hides it. Compute **Double Leverage = holdco-standalone equity investments in subsidiaries ÷ holdco-standalone net worth** (from standalone balance sheet via `get_fundamentals(section='balance_sheet_detail')`); >100% means the holdco has funded sub-equity with borrowed money — hidden leverage that amplifies refinancing and dividend-coverage risk
- **Board-composition without independent majority** — particularly critical for promoter-group-linked structures where related-party approvals are frequent
- **Auditor-resignation clusters** — cross-check via `get_events_actions(section='material_events')` and the filings trail; auditor rotation that lands in a quarter of ratings-watch, SEBI correspondence, or large RPT approval requirement is the forensic-grade tell
- **Material RPT as % of revenue rising above 10%** — or RPT as % of net worth rising above 15-20%; sustained rise across 4-6 quarters is a governance-drift pattern. SEBI LODR (Reg 23) material-RPT threshold is now **scale-based** (LODR Fifth Amendment, 2025, Schedule XII): 10% of consolidated turnover up to ₹20,000 Cr turnover, tapering above that and **capped at ₹5,000 Cr** for very large groups (the old flat "10% or ₹1,000 Cr whichever lower" test is superseded). Material RPTs require prior shareholder approval via **ordinary resolution** (not special — no related party may vote); this creates a disclosed AGM/EGM timeline constraint on group restructurings — flag pending resolutions covering material RPTs via get_events_actions
- **Non-Disposal Undertakings (NDUs)** in place of formal pledge — historically used to obscure encumbrance, but since the SEBI SAST Second Amendment (effective 29 Jul 2019, Reg 28(3)) NDUs are explicitly within the definition of "encumbrance" and carry the *same* disclosure obligation as a formal pledge. So an *undisclosed* NDU is now a compliance breach, not a legal workaround; the live red flag is encumbrance disclosed as an NDU (vs pledge) to soften optics, or evidence of NDUs that were never disclosed at all. The ownership agent's findings on NDUs should flow into the risk narrative

### Regulatory Risk Taxonomy — Multi-Regulator Inherent
Conglomerates carry inherent multi-regulator exposure: SEBI at the holdco level, RBI for any NBFC / bank subsidiary, IRDAI for any insurance subsidiary, plus sector-specific regulators (CERC for power, TRAI for telecom, DoT for spectrum, MoEF for environmental clearances, CCI for anti-trust). Name the specific regulator and, where possible, the specific circular when a risk crystallises:

- **SEBI** — LODR (Listing Obligations and Disclosure Requirements) Reg 23 on related-party transactions; Reg 30 / Schedule III on material-event disclosure (Chapter V of LODR governs listed non-convertible securities, not equity material events — don't conflate); insider-trading norms; SAST (takeover-code) open-offer trigger at 25% acquisition and creeping-acquisition limit of 5% per year beyond 25% up to 75%
- **RBI** (for NBFC / bank subs) — Basel III, PCA framework, Large Exposure Framework, IRAC provisioning norms
- **RBI — Core Investment Company (CIC) regime** (for the holdco itself) — a holding entity with **total assets ≥₹100 Cr** that holds/raises public funds and is primarily an investment holdco must register as a CIC and comply with: **≥90% of net assets in group companies**, of which **≥60% in equity** instruments of group companies, and **outside liabilities ≤2.5× adjusted net worth** (the leverage cap). These rules strictly limit holdco capital-allocation and gearing flexibility — verify CIC status/compliance for pure-holdco structures via `get_company_context(section='filings')`; a holdco breaching the 90/60/2.5x norms or operating unregistered is a regulatory red flag
- **IRDAI** (for insurance subs) — solvency minima, EoM / commission caps, product-approval
- **CCI** — M&A combination clearance; note intra-group restructurings are generally *exempt* under the Schedule I categories where there is no change in ultimate control (so a clean intra-group reshuffle usually does not trigger CCI filing — the live risk is restructurings that *do* shift control, or external M&A breaching the asset/turnover thresholds); group-control tests
- **FEMA** — foreign-subsidiary activities, ODI (overseas direct investment) compliance for offshore operations
- **Income Tax (transfer pricing)** — intra-group cross-border service charges, royalty flows, and ICD interest rates are transfer-pricing-scrutiny surfaces for group structures spanning multiple jurisdictions

Vague "regulatory risk" framing loses the traceability that makes the risk actionable; state the specific master-direction / circular / section when the risk is sector-specific.

### Operational Risk — Cross-Subsidy Drag and Cascade Patterns
- **Cross-subsidy drag** — one vertical reporting EBIT losses for 3+ consecutive years while receiving capex is a latent ROCE drag; quantify by computing what consolidated ROCE would be if the loss-making vertical were cost-of-capital-rated
- **KMP churn at parent vs subsidiary level** — disproportionate churn at a specific subsidiary (CEO, CFO exits in clusters) often precedes a write-down or a mis-selling-investigation episode; cross-check via `get_events_actions(section='material_events')`
- **Technology / platform-shift risk cascading** — a single vertical's disruption (e.g., payment-rails shift impacting a group fintech sub) can cascade through the group when the parent has extended guarantees or funding lines to that sub
- **Key-customer concentration at subsidiary level** — a group IT-services subsidiary with a top-5-customer concentration > 50% is carrying contract-renewal risk that compounds to the parent via dividend compression, not direct P&L impact

### Corporate Guarantees & Cross-Default — Parent-to-Subsidiary
For holding-company structures, explicitly check for **corporate guarantees** extended by the parent (or by cash-generating listed entities) to subsidiaries, and for **cross-default clauses** that link the parent's obligations to a subsidiary's (or sister entity's) default. Extract guarantees and contingent-liability schedules from `get_company_context(section='filings', sub_section='notes_to_accounts')`; cross-default and rating-linkage clauses usually sit in the borrowing terms / loan-covenant disclosures. A parent that has guaranteed a weaker subsidiary's debt carries that debt as latent leverage even when it is off the consolidated D/E — and a cross-default can crystallise a parent obligation purely from a subsidiary event.

### Normalized Cash Conversion — Strip Exceptionals Before Judging CFO/PAT
When assessing cash conversion for a conglomerate, compute **NORMALIZED CFO/PAT** by stripping exceptional items from PAT before forming the ratio — most importantly **one-off stake-sale gains** (subsidiary-IPO / divestment gains), insurance recoveries, and other non-recurring items. Note the direction: a one-time stake-sale gain *inflates PAT* (the gain hits the P&L) while the cash proceeds land in *investing* cash flow, not operating — so the gain mechanically *depresses* headline CFO/PAT and can make underlying cash conversion look worse than it is. Conversely, stripping the gain *raises* the normalized ratio and reveals true operating cash quality. State both the headline and the normalized (ex-exceptional) ratio; the normalized figure is the one that informs the quality-of-earnings read. Pull exceptional-item detail from `get_fundamentals(section='annual_financials')` and `get_company_context(section='concall_insights', sub_section='financial_metrics')`.

### Bear Cases — 30-50% Drawdown Triggers
Historical conglomerate drawdowns have recurring triggers; use them as the scaffolding for a named bear case, not as generic risks:

- **Governance event on the group** — SEBI / CBI / ED investigation, short-seller report, or auditor-qualification that reprices all listed group entities simultaneously. Historical pattern: 30-50% drawdown in 2-6 weeks, 4-8 quarters to recover (if the narrative can be rebuilt)
- **Subsidiary-level blow-up** — combined-ratio spike at the insurance sub, liquidity crisis at the NBFC sub, plant incident at the chemicals sub, fraud at the consumer sub. Direct parent impact depends on guarantees extended and equity capital at risk
- **Holdco leverage spiral** — when parent standalone debt exceeds sub-dividend capacity and subsidiaries cut dividends during their own stress, refinancing forces a distressed equity raise or asset sale at depressed multiples
- **Promoter-pledge margin call** — cross-check via `margin_call_analysis` in `get_ownership(section='promoter_pledge')`; a 20-30% stock-price fall triggering margin calls on pledged promoter stake creates forced selling that compounds the fall
- **Regulatory action on a flagship subsidiary** — licence suspension, capital-raise mandate, or operating restriction on the highest-NAV subsidiary reprices the SOTP NAV and widens the holdco discount simultaneously
- **Counterparty / customer concentration event** — default or exit of a top customer / borrower / counterparty that was disproportionately supporting group-level revenue or CFO
- **Cross-default / group-rating linkage** — rating downgrade at the unlisted parent holdco (or a sister group entity) triggers cross-default clauses or rating-watch at this listed entity even when its standalone financials are unchanged; historical precedents include promoter-group debt spirals where opco spreads widened 150-300 bps on holdco rating actions alone

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
