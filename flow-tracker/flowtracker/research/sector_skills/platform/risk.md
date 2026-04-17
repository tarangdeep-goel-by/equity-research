## Platform — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across platform sub-types. For food-delivery and quick-commerce it is unit-economics regression plus hyperlocal regulation; for payments it is RBI rule change (MDR, PPI, aggregator norms); for e-commerce marketplaces it is CCI antitrust plus FDI-in-retail policy; for insurtech it is IRDAI commission-cap plus persistency; for mobility it is state-level commercial-vehicle rule plus driver-partner classification; for edtech it is consumer-protection plus refund-rule cycles. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in platforms often surfaces through equity-issuance patterns and related-party optics before it surfaces in the P&L. Scan for:
- **Aggressive ESOP / stock-based-compensation dilution** — fresh ESOP pool creation of >3% per year (cumulative >10% over 3 years) without matched performance-vesting conditions is a governance concern; the cost is real even if adjusted-EBITDA excludes it.
- **Related-party logistics / fulfilment contracts** — when a founder-affiliated logistics entity handles 30%+ of deliveries or warehousing, transfer-pricing is the concern; check RPT-to-net-worth ratio and audit-committee disclosures.
- **CEO / KMP transitions at path-to-profit inflection** — founder stepping into a non-executive chair role right before a guided EBITDA-positive quarter is a pattern worth flagging.
- **Stock issuance without shareholder approval pattern** — repeated preferential allotments or private placements that avoid QIP shareholder-vote thresholds.
- **Opaque acquisition accounting** — large M&A with goodwill-heavy accounting and earn-out structures tied to founder-affiliated targets.
Cross-check via `get_events_actions(section='material_events')` and `get_ownership(section='shareholder_detail')`.

### Regulatory Risk Taxonomy — Cite the Specific Agency
Regulatory risk for platforms is concrete and agency-specific. Tie each risk to the relevant regulator:
- **MeitY** (Ministry of Electronics and IT) — **IT Act intermediary rules**, **DPDP Act 2023 (Digital Personal Data Protection)**, content-moderation compliance, traceability mandates. Applies to all consumer platforms with UGC or data-processing at scale.
- **RBI** — for payments sub-sector: **PPI (Prepaid Payment Instrument) licences**, **Payment Aggregator / Payment Gateway norms**, **MDR regulations** (UPI MDR is a recurring policy-risk vector), **Digital-lending guidelines** for credit-distribution partnerships.
- **CCI (Competition Commission of India)** — antitrust for dominant marketplaces (food-delivery duopoly, horizontal e-commerce top-2). Recent CCI orders on deep-discounting, exclusive-tie-up, and self-preferencing have reshaped operating models. App-store / Google-Play-Store fee rulings also flow through.
- **SEBI LODR** — listing-disclosure obligations specifically for recently-IPO'd platforms; any selective disclosure of GMV / MAU / operating metrics to analysts ahead of filings is SEBI territory.
- **IRDAI** — for insurtech: commission caps (post-2023 Expenses-of-Management amendment reshaped distribution economics industry-wide in one fiscal), product-approval regime.
- **State-level commercial vehicle rules** — for quick-commerce 2W fleet, state transport departments periodically ban or restrict specific delivery-vehicle classes; local RTO rulings can take 10-20% of delivery capacity offline for weeks.
- **Consumer Protection (e-Commerce) Rules 2020** — mandatory disclosures, return policies, seller-identity requirements; CPA enforcement has been episodic but high-impact.
- **Data-localisation requirements** — RBI's payments-data mandate and the DPDP Act's cross-border-transfer regime; non-compliance shuts down foreign-cloud dependencies.

Name the specific rule-set when the risk crystallises; vague "regulatory risk" framing loses the traceability that makes the risk actionable.

### Operational-Risk Concentration
Platform operational risk is often invisible until a single vector fails. Examine:
- **Single-category concentration** — >50% of GMV in one vertical (food-delivery dependence, or personal-care / beauty dependence for vertical e-commerce) means a category-specific demand shock or a competitive entrant in that category is a thesis-breaker.
- **Geographic concentration** — top-8 metros contributing >70% of GMV is structural for most Indian platforms; tier-2 penetration is the growth narrative, but stress often starts in metro cohorts first.
- **Merchant concentration** — top-100 merchants contributing >40% of GMV (common for horizontal marketplaces) creates negotiation-leverage loss on take-rate at renewal.
- **Payment-system dependence** — UPI outage, NPCI-side incident, or card-network disruption can take 60-80% of GMV offline for hours.
- **Tech-outage risk** — cloud-provider concentration, app-store dependency, API-gateway single-point-of-failure.
- **Driver-partner or delivery-partner supply shock** — gig-worker classification changes (Karnataka, Maharashtra) or fuel-price spikes compress partner economics and shrink supply.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Platform drawdowns in the Indian cohort have recurring triggers; use these as bear-case scaffolding:
- **Regulatory action** — a CCI final order restructuring take-rates or banning specific tie-ups has historically compressed platform stocks 20-40% in weeks. MeitY intermediary rule enforcement against specific content or product categories.
- **UPI-MDR regulation change** — any reintroduction of UPI MDR, or tightening of wallet interoperability, reshapes payments-platform revenue mix in one quarter.
- **Competitive entry** — a foreign player with deeper capital pocket (or a PE-backed domestic rival) entering the sub-sector forces a 2-3 quarter CAC spike and contribution-margin regression.
- **Macro discretionary-spend slowdown** — urban-cohort discretionary frequency drops 10-15% in a broader consumption-downcycle; order-volume growth decelerates and fixed-cost coverage breaks.
- **Failed capital raise / down-round dilution** — if markets close to tech listings and the runway expires, down-round dilution of 20-40% at a distressed valuation resets the per-share fair value.
- **Data-breach event** — DPDP Act penalties and reputational CAC inflation post-breach are a durable overhang.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case is invalidated (e.g., "contribution margin per order turning negative for 2 consecutive quarters post-scale" or "CAC inflation +40% YoY with M+6 retention flat").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **Contribution-margin -100 bps** — EBITDA-positive timeline slips 2-3 quarters; for a platform guiding "EBITDA positive in H2 FY26", a 100 bps CMPO miss pushes it to FY27 and re-rates the stock 15-25%.
- **CAC +25%** — LTV/CAC compresses below 2× if LTV is static; growth decelerates as paid channels become unprofitable and the platform throttles marketing.
- **Order-frequency -15%** — revenue hit 15-20% at maintained AOV; cascades through contribution margin because delivery / payment / fulfilment fixed costs don't scale down proportionally.
- **Take-rate -100 bps** — for a 3P marketplace, a take-rate shock (merchant pushback, CCI order, subsidy war) of 100 bps on GMV translates to ~15-20% revenue hit and proportionally larger EBITDA impact.
- **UPI-MDR reintroduction at 25-50 bps on specific MCC categories** — for payments platforms, a single-MCC MDR reintroduction can re-rate revenue-per-TPV 20-40%.

Route the arithmetic through `calculate` with the sensitivity deltas as named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_company_context(section='concall_insights', sub_section='operational_metrics')` does not return contribution margin or cohort retention at the quarterly granularity needed for stress-testing, fall back in this order: (1) `sub_section='financial_metrics')` for management-disclosed quarter-end unit-economic references; (2) `get_company_context(section='filings')` for the most recent BSE disclosure and any regulator correspondence; (3) `get_events_actions(section='material_events')` for CCI / MeitY / RBI / IRDAI actions. Cite the source quarter for every extracted number. Do not fabricate contribution margin — the risk agent's credibility depends on citing what the platform actually disclosed.

### Open Questions — Platform Risk-Specific
- "What is the top-100 merchant concentration as % of GMV, and has it trended up meaningfully over the last 4 quarters?"
- "Is any CCI investigation, MeitY intermediary-rule amendment, or RBI payments-norm revision currently in public consultation or draft that would reprice the sub-type?"
- "For payments platforms: what share of revenue is MDR-sensitive (and which MCC categories), and what is the downside if UPI MDR is reintroduced at 25-50 bps?"
- "For quick-commerce: which states have the most restrictive 2W commercial-vehicle rules, and what GMV share is exposed to a potential ban cycle?"
- "What is the 13-month and 61-month persistency trend on insurance policies sold?" (insurtech)
- "Has there been a fresh ESOP pool creation in the last 12 months, and what is the cumulative 3-year dilution at full vest?"
