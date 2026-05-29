## Broker — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across broker sub-types. For discount brokers it is SEBI regulatory tightening on F&O and order-flow monetisation; for full-service brokers it is competitive price pressure from discount tier and advisory-revenue compression; for wealth / PMS it is AUM attrition on market drawdowns and performance-fee timing; for bank-owned brokers it is parent-bank credit events propagating to the captive; for the Depositories (CDSL/NSDL) it is regulated-tariff revision and technology-disruption risk. State the sub-type's dominant risk axis in the opening paragraph before listing generic operational risks.

### Sector-Specific Governance Red Flags
Governance stress in brokers surfaces earlier through SEBI correspondence than through board drama. Scan for:

- **Client-fund segregation violations** — SEBI's client-funds segregation audit findings, NSE/BSE show-cause notices on settlement-account breaches, or enhanced-supervision designations. A disclosed segregation gap is a 10-30% single-day stock move on the announcement.
- **SEBI show-cause / penal circulars** — research-analyst-regulation breaches, fraudulent-unfair-trade-practice (FUTP) orders, order-routing integrity issues around NSE co-location access. Cross-check via `get_events_actions(section='material_events')` and `get_company_context(section='filings', query='SEBI|show cause|penal')`.
- **Front-running by research analysts** — a recurring theme in full-service brokers; disclosed forensic audits or whistleblower-triggered investigations repricing the stock 15-25% until remediation is documented.
- **Order-routing integrity (co-location)** — historical NSE co-location preferential-access allegations have persisted as regulatory tail risk for specific brokers; any fresh inquiry is material.
- **Promoter-group pledge on the broker parent** — distinct from client collateral (which appears on the broker's balance sheet as part of MTF collateral); promoter-entity pledge on the listed broker's own equity is a governance red flag. Filter via `get_ownership(section='promoter_pledge')` and verify the counterparty.
- **Auditor transitions in a regulatory-scrutiny window** — rotation is routine, but rotation timed with an active SEBI inquiry or a peak-margin-rule transition is informational.

### Regulatory Risk Taxonomy — Cite the Specific Circular
Regulatory risk for brokers is concrete; tie each risk to the named regulator and, where possible, the specific circular or rulebook section:

- **SEBI** — **Broker Regulations** (net-worth requirements, client-funds segregation, margin collection norms), **Research Analyst Regulations** (registration, disclosure, insider-trading surveillance on research staff), **AIF / PMS Regulations** (performance-fee high-water-mark, investor-class segregation), **Insider-Trading Regulations** for broker research personnel.
- **Recent SEBI changes worth naming explicitly**:
  - **F&O lot-size increase October 2024** — compressed retail-options participation by 20-30% in discount-broker revenue in the first quarter of effect.
  - **True-to-Label charges circular** (SEBI, 1 Jul 2024, effective 1 Oct 2024) — mandates uniform (non-slab) transaction charges by MIIs and requires charges collected from clients to match charges paid to the MII, eliminating the slab-vs-flat-fee rebate brokers historically pocketed (~8-10% of discount-broker revenue). This is about exchange/MII transaction charges, NOT mutual-fund TER disclosure.
  - **Peak-margin / upfront-margin collection circulars** (Phase 1-4 rolled through 2021-22) — step-changed order economics for retail discount brokers; ADTV impact already absorbed but margin-rule tightening is an ongoing direction.
  - **Single-weekly-expiry-per-exchange rule** (live since 20 Nov 2024, NOT a pending consultation) — each exchange retains weekly expiry for only one index (Nifty on NSE, Sensex on BSE); Bank Nifty / FinNifty / Midcap Select / Bankex / Sensex50 weekly contracts were discontinued. This already removed multiple expiry-day trading sessions per week — a structural, realised compression on index-option volumes, not a prospective one.
- **NSE / BSE** — Trading-Member rulebook, co-location access norms, technology-audit and outage-reporting requirements.
- **RBI** — indirect only: policy-rate / liquidity cycle drives the broker's own cost of funds, which transmits to the MTF spread. (The Margin Trading Facility framework itself is issued by **SEBI**, not RBI — do not attribute MTF regulation to RBI.)
- **IT Ministry / CERT-In** — cyber-incident reporting obligations (6-hour mandatory disclosure); a broker is a SEBI-regulated market intermediary and a CERT-In reporting entity simultaneously.

Name the relevant circular or master-direction when the risk crystallises; vague "per regulations" framing loses the traceability that makes the risk actionable.

### Operational Risk — Technology, Cyber, Prop-Book
Broker operational risk is technology-heavy and shows up in three vectors:

- **Technology outages** — documented Zerodha-style order-placement outages, Angel-style login failures during market-open windows. Every major Indian broker has had at least one multi-hour outage in the last 3 years. Recurring outages (>3 per year) invite SEBI supervisory attention and client attrition.
- **Cyber attacks on client accounts** — account-takeover fraud, unauthorized trading, phishing-driven credential theft. Disclosure under CERT-In 6-hour rule; a disclosed incident repricing the stock 5-10% on announcement.
- **Market-making / proprietary trading book risk** — full-service brokers carrying a prop book face flash-crash exposure; losses concentrated on a single event (COVID March 2020 reference) can consume a full year of earnings.
- **Settlement-risk concentration** — single-client or single-cohort concentration in MTF book (>5% to one client, >25% to a single sector) creates single-name exposure that headline ECL provisions do not capture.
- **Margin-funding book collateral quality** — collateral composition heavily in illiquid mid/small-cap stocks (>40% of MTF collateral) carries materially higher tail risk than large-cap-collateralised books. Cross-check via concall disclosures on collateral composition.

### Bear-Case Scenarios — 20-40% Drawdown Triggers
Historical broker drawdowns have recurring triggers; use these as the scaffolding for a bear case:

- **SEBI structural tightening on F&O** — the 2024-25 lot-size hike, margin-rule cycle, AND the single-weekly-expiry-per-exchange rule (live 20 Nov 2024) already compressed discount-broker F&O revenue 20-30% in affected quarters. The bear case is the NEXT incremental action (additional margin tightening, further expiry consolidation, retail-options access curbs) layered on top of the already-realised step-down — a default-probability bear-case, not a tail scenario.
- **COVID-style market shock** — a single-week ADTV drop of 40-50% vaporises F&O revenue; historically broker stocks drop 25-40% in the first two weeks of such shocks before stabilising.
- **Client-fund segregation SEBI finding** — single-day stock move 10-30%; recovery depends on remediation pace and whether the finding is firm-specific or sector-wide.
- **Technology outage cluster** — 3+ outages within 6 months correlates with active-client attrition of 5-10% in the following 2 quarters.
- **Parent-bank credit event (for bank-owned brokers)** — parent-bank NPL spike or liquidity stress propagates to the broker subsidiary's captive-base economics within 1-2 quarters.
- **MTF book stress event** — flash-crash or single-stock halt overwhelms collateral haircut; bad-debt write-off >0.5% of book (vs industry norm <0.2%) signals structural risk-management failure.
- **Cash-segment flat-fee / zero-brokerage contagion** — the discount-broker flat-fee model originated in F&O but is progressively bleeding into cash-delivery and intraday tiers (zero-delivery brokerage is already the headline at several discount platforms). If the flat-fee frame expands to cash-segment intraday and eventually institutional cash-execution, full-service and bank-owned brokers lose their remaining bps-on-turnover yield pool on cash. The structural compression is permanent (not cyclical) and compounds any SEBI F&O tightening — model the combined bear as yield erosion across both legs, not just F&O.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "F&O revenue falling >40% YoY for 2 consecutive quarters" or "active-client count declining for 3 consecutive quarters with ARPU flat").

### Sector-Specific Stress Tests
Quantify the sensitivity; don't just describe it. Typical ranges for broker stress tests:

- **F&O ADTV -40% sensitivity** — for a broker with 60% F&O revenue concentration, -40% ADTV translates to roughly -24% topline and, after fixed-cost absorption, -30-40% PAT in the affected quarter. Route the arithmetic through `calculate` with `fo_revenue_share`, `adtv_decline`, and `fixed_cost_share` as named inputs.
- **Activation-rate -10pp sensitivity** — an active-client base falling from 40% activation to 30% with constant gross count loses 25% of monetisable cohort; near-term revenue impact is softened by lagged attrition (6-12 months) but the ARPU stress is immediate.
- **CAC +25% sensitivity** — if paid-acquisition market tightens (e.g., platform-ads cost rising, competitive CAC bidding up), incremental client cohorts move to a longer payback window; LTV/CAC breach >18 months is the threshold for re-evaluating growth durability.
- **MTF spread -100bp sensitivity** — for a broker with a ₹2,500 Cr MTF book, -100bp spread is ~₹25 Cr of pre-tax income, materially hitting a ₹400-600 Cr PAT base.
- **Float yield -50bp sensitivity** — a 50bp drop in overnight rates compresses float income on client deposits; for large-book brokers this can be ₹50-100 Cr annualised.

### Data-shape Fallback for Risk Metrics
When `get_events_actions(section='material_events')` and `get_company_context(section='filings', query='SEBI|show cause|penal')` return empty and `get_quality_scores` is not populated for the broker sub-type, fall back in order to: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed stress numbers; (2) `get_company_context(section='documents', query='risk|regulatory|cyber|outage')` for press-release or investor-letter framing; (3) `get_company_context(section='concall_insights', sub_section='flags')` for management's own red flags. Cite the specific source and quarter for every extracted risk metric. Do not fabricate ECL, MTF yield, or CAC — the risk agent's credibility depends on citing what the broker actually disclosed.

### Open Questions — Broker Risk-Specific
- "Is the F&O revenue concentration above 75% (discount) or 60% (full-service), and what product diversification is management actively pursuing to reduce SEBI single-circular exposure?"
- "Is any SEBI circular on weekly-expiry rationalisation, further margin tightening, or retail-options access curbs currently in public consultation or recent-draft form?"
- "What is the ECL on the MTF book as a percentage of book size, the trajectory over 4 quarters, and the collateral composition (large-cap vs mid/small-cap share)?"
- "Has the broker had a material technology outage in the last 12 months, and what was the disclosed SEBI or exchange response?"
- "For bank-owned brokers: what is the parent's current credit-cycle exposure and ratings trajectory, and is any parent-level stress likely to reshape the captive-base economics in the next 4 quarters?"
- "Is the current promoter pledge on the broker's own equity (distinct from client-collateral pledges) material, and how has it trended?"
