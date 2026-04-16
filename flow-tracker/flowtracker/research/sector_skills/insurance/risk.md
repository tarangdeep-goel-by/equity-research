## Insurance — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across insurance sub-types. For life insurers it is interest-rate cycle plus persistency decay plus EoM/commission regulatory resets. For general insurers it is combined-ratio blowout, catastrophe concentration, and motor-tariff or health-pricing cycles. For standalone health insurers it is loss-ratio drift (retail vs group mix) and medical-inflation pass-through lag. For insurtech marketplaces it is SEBI / IRDAI rule changes on commissions, subsidiary drag sizing, and CAC inflation. For reinsurers it is treaty renewal pricing and cat-loss clustering. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in insurance surfaces earlier through operational telemetry than through board drama. Scan for:
- **Promoter-group related-party flows** — bancassurance fees paid to parent bank (SBIN → SBILIFE, HDFCBANK → HDFCLIFE, ICICIBANK → ICICIPRULI): track RPT as % of total commission expense. A structural float-share upward drift without commensurate distribution-productivity data is a governance tell.
- **Agent-franchise kickbacks** — abnormal commission-to-premium ratios on specific product lines, especially during end-of-quarter or end-of-year sales pushes, are a mis-selling precursor.
- **Mis-selling patterns signalled by persistency decay** — 13-month persistency dropping sharply while APE growth is strong is the earliest telemetric tell of mis-sold policies; the 13M drop typically shows 4-6 quarters before any regulatory action.
- **Reserve manipulation** — opacity around claim-reserve methodology, or large IBNR (incurred-but-not-reported) revisions across fiscals, is forensic-grade. General insurers reporting multi-year combined-ratio stability through visible IBNR rebasing are at risk of a reserve-strengthening charge.
- **Board composition** — IRDAI requires a majority-independent board for listed insurers; any board reshuffle that drops independent-director count below statutory threshold is a governance signal even without an explicit dissent.
- **Auditor rotation or qualification** — rotation cycles that land in a quarter of IRDAI correspondence or product-approval delay are informational; qualifications on actuarial assumptions or reserve adequacy are forensic-grade tells. Cross-check via `get_events_actions(section='material_events')`.

### Regulatory Risk Taxonomy — Cite the Specific Circular
Regulatory risk in insurance is concrete, not vague. Tie each risk to IRDAI's specific master direction or amendment:
- **IRDAI solvency margin** — 150% of required solvency margin is the regulatory minimum for both life and general insurers; buffer drift toward 160-170% without capital action is supervisory-attention territory.
- **EoM (Expenses of Management) caps** — the post-2023 amendment harmonised commission and EoM rules across life and general, resetting commission-expense ceilings and reshaping agent economics industry-wide. Any further amendment (surrender-charge reset, ULIP charge-structure change, par-fund bonus-declaration rules) would have comparable industry-wide effect.
- **Commission-cap revisions** — the 2023 commission-cap rework reshuffled agent economics; sub-segment-specific rules (motor commission, health commission, life ULIP commission) change independently.
- **Product-approval regime** — par, non-par, and ULIP products each go through File-and-Use or prior-approval. Approval-delay clusters on non-par guaranteed-return products are a recurring sub-sector risk.
- **Standardisation of health products** — IRDAI's Arogya Sanjeevani and similar standard-product mandates compress differentiation in the health segment.
- **GST on insurance premiums** — currently 18%; periodic debate on reducing to 5% would be a tailwind (demand elasticity on term protection and health retail) but is a political variable, not base-case.
- **Risk-based capital (IFRS-17 equivalent)** — India's transition to a risk-based-capital regime (Ind AS 117 / IFRS-17 alignment) is in progress; the reporting-regime change will alter how VNB, reserves, and solvency are disclosed and may reshuffle peer rankings.

Name the specific amendment when the risk crystallises; vague "per IRDAI norms" framing loses the traceability that makes the risk actionable.

### Operational-Risk Concentration
Aggregate insurance portfolios look diversified until a channel or segment-level stress event. Examine:
- **Single-channel distribution concentration** — any life insurer with >60% of NBP coming from a single bancassurance partner is one bank-renegotiation away from a 20-30% NBP reset. SBILIFE (SBIN), HDFCLIFE (HDFCBANK), ICICIPRULI (ICICIBANK) each have this structural vulnerability.
- **Geographic concentration in motor and health** — state-level regulatory or legal-environment shifts (no-claim-bonus mandates, motor-tariff states) can reprice the loss ratio for single-state-heavy general insurers within 2 quarters.
- **Catastrophe-reinsurance limit** — the gap between gross written premium and retention (i.e., the portion reinsured out) determines catastrophe-year drawdown. A general insurer with a rising retention ratio through a catastrophe year is a single event away from a combined-ratio blowout.
- **Product-line concentration** — life insurer with >40% of APE in a single guaranteed-return non-par product (often a particular ticket-size / tenor combo) is exposed to any product-approval amendment on that specific design.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical insurance drawdowns have recurring triggers; use these as the scaffolding for a bear case:
- **Combined-ratio blowout year** — a natural-catastrophe cluster (cyclone + flood season) or a motor-tariff reset can take general-insurer combined ratio from 104% to 115% in a single year and halve reported profits. Post-cat, reinsurance renewal pricing rises 200-400 bps the following year, extending the margin compression.
- **Regulatory reset on surrender charges or EoM** — a single IRDAI amendment reshaping surrender-charge economics can reset VNB margins industry-wide; historical precedent (pre-2014 par-fund bonus rule changes) produced 6-8 quarter de-rating cycles.
- **10Y G-sec rally of 100+ bps** — compresses life-insurer par-fund return + non-par new-business pricing + general-insurer float income simultaneously. ROEV compresses 150-250 bps, combined ratio deterioration of 200-300 bps, and P/EV de-rates 20-40%.
- **Insurtech growth stall + CAC inflation** — if marketplace visitor growth decelerates below 10-15% while CAC inflates 30-50% YoY, the unit-economics thesis breaks; contribution-margin improvement stops, and the EV/Revenue multiple compresses 30-50%.
- **Persistency shock** — a 5-pp drop in 13-month persistency (e.g., 82% → 77%) on a large private life insurer indicates systemic mis-sale; VNB impact is 8-12% in the quarter of disclosure, with a 4-8 quarter de-rating tail as cohort retention clarity crystallises.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "combined ratio sustained >112% across 2 consecutive fiscals" or "13-month persistency breaking below 80% and not recovering within 2 quarters").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **100 bps G-sec move** — investment-yield impact 30-50 bps on float within 4-6 quarters (shorter for general insurers with shorter-duration reserves, longer for life with long-tail liabilities); par-fund new-business pricing reset of 10-25 bps on VNB margin.
- **5-pp persistency drop (life insurers)** — VNB impact 8-12% on the cohort; EV growth compresses 200-400 bps in the reset year, with lag.
- **200-400 bps combined-ratio shock (general)** — reported earnings -30-50%, ROE compresses 300-500 bps depending on float-income offset.
- **1-pp loss-ratio deterioration (standalone health)** — underwriting-profit compression of 30-60% in retail-heavy books, more on group-heavy.
- **20-30% CAC inflation (insurtech)** — contribution margin -150-300 bps unless offset by LTV expansion or take-rate uplift.

Route the arithmetic through `calculate` with the specific sensitivity (rate delta, persistency delta, combined-ratio delta, CAC delta) as named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='insurance')` returns missing solvency, VNB margin, persistency, or combined ratio, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end numbers; (2) `get_company_context(section='filings')` for the most recent BSE disclosure and any IRDAI correspondence; (3) `get_events_actions(section='material_events')` for regulatory events, auditor transitions, and ratings actions. Cite the source quarter for every extracted number. Do not fabricate solvency or combined-ratio numbers — the risk agent's credibility depends on citing what the insurer actually disclosed.

### Open Questions — Insurance Risk-Specific
- "Is the current solvency buffer above 150% minimum sufficient to support disclosed premium-growth guidance without a capital raise in the next 4-6 quarters?"
- "What is the 13-month persistency trajectory over the last 4 quarters, and is the trend consistent with the reported VNB margin or signalling latent mis-sale cohorts?"
- "Is any IRDAI draft circular (surrender-charge, EoM, commission-cap, product-approval regime) currently in public consultation that would reprice this sub-type's economics?"
- "For single-channel-heavy life insurers: is the bancassurance agreement up for renewal in the next 8 quarters, and what is the renewal track record of the parent bank?"
- "For general insurers: what is the retention-to-reinsurance split, and how has it trended through the most recent catastrophe cycle?"
- "For insurtech: what is the current CAC-to-LTV trajectory, and is the contribution-margin improvement durable at decelerating traffic growth?"
