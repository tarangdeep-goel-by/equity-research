## Private Bank — Risk Agent

This file inherits the full BFSI risk framing (see `bfsi/risk.md` when merged — PR #20) on governance red flags, regulatory-risk taxonomy (RBI, SEBI), operational-risk concentration, bear-case drawdown triggers, and sector-specific stress tests. Do not duplicate generic BFSI content. The private-bank sharpening below calibrates advances-growth-vs-CRAR telemetry, unsecured-retail structural exposure, RBI supervisory-action patterns, HDFC-merger-specific transition drag, and quantified stress scenarios for the large private-bank cohort.

### Dominant Risk Axis — Asset-Quality Surprise and Governance
For private banks, the dominant risk axis is **asset-quality surprise** (single-name or concentrated-book slippage) and **governance / supervisory action**, in that order. Unlike PSU banks (sovereign policy cycle) or NBFCs (ALM mismatch), a private bank can be structurally well-run and still be repriced 20-40% in a single quarter by either a surprise chunky-corporate slippage or a targeted RBI supervisory letter. State this axis in the report's opening paragraph before enumerating generic risks.

### Sector-Specific Governance Red Flags
Private-bank governance stress surfaces earlier in balance-sheet telemetry than in board drama. Scan for:

- **Advances growth materially above peer without matched CRAR build** — a private bank growing +30% YoY while CRAR drifts down 100-150 bps is heading toward a dilutive QIP or an RBI supervisory letter. Cross-check via `get_company_context(section='sector_kpis', sub_section='capital_adequacy_ratio_pct')` alongside `advances_growth_yoy_pct`.
- **Top-10-group concentration rising 5-8 pp QoQ** — single-name stress latent; private banks have historically seen chunky-corporate surprises (FY19 IL&FS-era, FY20 COVID-MSME stress). Flag when the top-20-accounts disclosure shifts meaningfully in a single quarter.
- **RBI-supervisory letter latent** — not always public, but inferrable from the gap between management-stated guidance (on advances growth, CRAR, unsecured-share) and actual trajectory. A bank tracking 200-400 bps below its own guided CRAR path for 2+ quarters is often under supervisory dialogue even without a public disclosure.
- **KMP / board-chair transitions mid-cycle** — CFO, CRO, Head-of-Retail, or MD/CEO transitions in a stress quarter are informational; clustered departures (2+ C-suite exits in 6 months) are forensic. The 2024-25 YESBANK and RBLBANK precedents illustrate the pattern.
- **Auditor rotation mid-cycle** — statutory-auditor change in a quarter where asset-quality numbers or RBI-dialogue pressure are under watch is a governance tell. Qualifications on asset classification or provisioning are forensic-grade signals; cross-check `get_events_actions(section='material_events')`.
- **Digital-onboarding embargo or supervisory action** — the 2023 Kotak Bank embargo on new digital customer acquisition (via IT-systems review) cost that bank 15-20% of its retail-acquisition run-rate for several quarters — this category of bank-specific supervisory action is becoming more common as RBI enforces IT-resilience standards.

### Regulatory Risk Taxonomy — Private-Bank-Specific Circulars
Cite the specific circular rather than vague "per regulations" framing. Private-bank-relevant regulatory constraints:

- **RBI Master Direction on Acquisition of Shares in a Bank (2023)** — any single shareholder (direct or indirect, aggregated with acting-in-concert) crossing 5% of paid-up requires RBI prior approval. This is the 5% structural threshold — monitor any large FPI or strategic holder approaching this band.
- **FDI Master Direction on Private Banks** — aggregate foreign holding cap at **74% of paid-up** (FPI + FDI + ADR/GDR + NRI combined, with NRI internal sub-limit of 10%). Per-FPI entity-level cap at 10%. Large private banks (HDFCBANK, ICICIBANK, AXISBANK, KOTAKBANK, INDUSINDBK) historically run 65-74% aggregate.
- **RBI macro-prudential risk-weight circular (November 2023)** — increased risk-weights on unsecured consumer credit (personal loans, credit cards) from 100% to 125% and on bank-to-NBFC lending from 100% to 125% for higher-rated NBFCs. Structural ROE reset for unsecured-heavy private banks; cost 100-200 bps on CRAR for banks running >20% unsecured-retail share.
- **RBI Prompt Corrective Action (PCA) framework** — NNPA >6%, CRAR below CCB-inclusive minimum (11.5% as of 2024), or two consecutive years of negative ROA trigger PCA. Private banks rarely hit PCA but the framework is live — CRAR below 12.5% with declining trajectory is PCA-proximity flag.
- **D-SIB buffer requirements** — HDFCBANK and ICICIBANK carry the D-SIB designation requiring a 0.20-0.60% additional CET1 buffer above regular norms (reviewed annually). Factor into CRAR-headroom calculation for these two names.
- **RBI IT-resilience and Digital-Lending Guidelines (2022)** — bank-specific supervisory action risk; a bank with weak IT infrastructure or opaque digital-lending partnerships faces embargo risk (Kotak 2024 precedent).

### Operational Risk — Private-Bank-Specific Concentrations
Private-bank operational-risk concentration differs from PSU or NBFC peers:

- **Unsecured-retail concentration >20% of book is the structural bear-case exposure** post the 2023 RBI risk-weight tightening. IDFCFIRSTB, BANDHANBNK, KOTAKBANK, and HDFCBANK (on a sub-segment basis) each carry material unsecured-retail exposure; the risk-weight change already cost 80-150 bps on CRAR in the transition year and the forward-ROE trajectory depends on how the book is re-priced or re-mixed.
- **Top-10-group-concentration exposure** — large private banks disclose top-20-accounts share of advances. When top-10 share rises 300-500 bps YoY, concentration-risk is re-building. RBLBANK's FY20 precedent (single-name corporate slippage) and similar AXISBANK legacy-corporate stress episodes illustrate the pattern.
- **Tech-outage risk** — banking-app downtime, UPI settlement breaks, core-banking-system failures. A multi-hour outage during peak banking hours costs both customer acquisition and triggers RBI supervisory attention. The 2024 HDFCBANK net-banking outages are a reference point.
- **Operational-risk events — fraud, cyber, insider-fraud** — most private banks disclose operational-risk-loss events in the annual report risk-management section. Rising losses (from 2-4 bps of operating revenue to 8-12 bps) signal internal-controls degradation.
- **Concentration in a single state or geography** — CSBBANK, FEDERALBNK, CITYUNIONBANK, KARURBANK all have single-state advances concentrations >40% of book (Kerala or Tamil Nadu). Monsoon-stress or state-election farm-loan-waiver risk hits these names disproportionately.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical private-bank drawdowns have four recurring triggers:

- **FY19-20-style corporate-stress surprise** — a single chunky corporate slippage (₹5,000-15,000 Cr) large enough to move credit-cost materially. Precedent: YESBANK (ultimate resolution), RBLBANK (FY20 stress), INDUSINDBK (pockets of legacy vehicle-finance stress in FY21). Quantify as "single-name slippage equal to 2-4% of advances with 50-70% provisioning" which typically costs 200-400 bps on ROE and 30-50% on the stock in 3-6 months.
- **RBI macro-prudential tightening repeat** — a 2023-style unsecured risk-weight increase, or an extension to other segments (CRE, microfinance, AIF). For unsecured-retail-heavy private banks, a further 25 pp risk-weight increase costs 60-120 bps on CRAR and forces rate-repricing or book-mix-shift.
- **Competitor catch-up on CASA in a rate-rising cycle** — when PSU banks or SFBs raise term-deposit rates aggressively, CASA share shifts to term-deposits across the sector; the private-bank's CASA relative-advantage compresses. A 500-700 bps CASA-mix erosion over 4-6 quarters costs 40-60 bps on NIM.
- **HDFC-merger drag-on-metrics continuing** (HDFCBANK-specific) — absorption is 2-3 more quarters from stabilising; if NIM compression or CASA-rebuild lags management guidance by 20-30 bps for 2+ consecutive quarters, the stock re-rates 10-20% lower.

Each bear-case should be expressed as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "GNPA breaching 2.5% with rising SMA-2" or "CET1 dropping below 13% without a QIP announcement").

### Sector-Specific Stress Tests — Private Bank Calibrations
Quantify sensitivity with specific arithmetic; don't just describe. Typical ranges:

- **100 bps rate-rise + 10 pp CASA erosion combined** — NIM compresses 60-90 bps. For a bank at 3.8% NIM, this pulls NIM to 2.9-3.2%; for a bank at 4.5% NIM, to 3.6-3.9%. ROE impact depends on the NIM-to-ROE sensitivity (typically a 100 bps NIM change = 250-400 bps ROE change for a private bank).
- **+1 pp GNPA at 75% PCR** — incremental provisioning cost = advances × 0.01 × 0.75 = 0.75% of advances. For a bank with a 10% leverage-multiplier, that flows to 7-8% of equity → 350-500 bps ROE hit in the quarter of recognition. Route through `calculate` with `advances`, `delta_gnpa`, and `pcr` as named inputs.
- **CRAR −100 bps from unsecured risk-weight increase** — for a bank running 20-25% unsecured-retail, a 25-pp risk-weight increase adds RWA = advances × 0.22 × 0.25 = 5.5% of total RWA, which pulls CRAR down 85-110 bps. If pre-shock CRAR is <13.5%, the bank becomes a dilution candidate (QIP, AT1 issuance, or book-mix-shift).
- **10Y G-sec yield +100 bps shock** — AFS book MTM loss approximately 7-8% on the duration-weighted AFS portfolio. For a bank with ₹2-3 L Cr AFS book, that is ₹15,000-25,000 Cr MTM hit flowing through reserves (HTM cushioned, trading-book directly through P&L). Factor into tangible-book decline not just P&L.

Route every arithmetic through `calculate` with the rate sensitivity, GNPA delta, CASA mix, and risk-weight delta as named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='bfsi')` returns missing asset-quality or capital ratios, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end numbers; (2) `get_company_context(section='filings')` for the most recent BSE disclosure and any RBI correspondence; (3) `get_events_actions(section='material_events')` for governance events, auditor transitions, and ratings actions. Cite the source quarter for every extracted number. Do not fabricate GNPA / NNPA / CRAR — the risk agent's credibility depends on citing what the bank actually said.

### Open Questions — Private-Bank Risk-Specific
- "Is the current CRAR / CET1 buffer above statutory minimum + D-SIB buffer (where applicable) sufficient to support disclosed advances-growth guidance without a QIP in the next 4 quarters?"
- "What is the SMA-0 / SMA-1 / SMA-2 trajectory over the last 4 quarters, and is it consistent with headline GNPA stability or pointing to fresh slippage 1-2 quarters out?"
- "What share of advances is unsecured-retail (PL + CC + consumer-durable + personal overdraft), and how did CRAR move after the November 2023 risk-weight increase vs management guidance?"
- "Is the bank currently under any RBI supervisory dialogue, embargo on new digital customer acquisition, or deferred-approval on subsidiary capital-raise?"
- "For banks with single-state concentration (FEDERALBNK, CSBBANK, CITYUNIONBANK, KARURBANK): what share of advances is in the home state, and is any election-cycle farm-loan-waiver or rainfall-stress event imminent?"
