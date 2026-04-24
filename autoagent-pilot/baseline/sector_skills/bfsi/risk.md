## BFSI — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across BFSI sub-types. For PSU banks it is sovereign policy and credit-cycle exposure; for private banks it is asset-quality surprise and governance; for NBFCs it is liquidity and ALM mismatch; for life insurers it is interest-rate and persistency; for general insurers it is combined-ratio blowout and catastrophe concentration; for AMCs it is flow reversal and fee-yield regulation; for brokers and exchanges it is SEBI rule changes and F&O mix concentration. State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in BFSI surfaces earlier through balance-sheet telemetry than through board drama. Scan for:
- **Advances growth materially above peer without matched CRAR build** — a bank growing +30% YoY while CRAR drifts down 100-150 bps is heading toward a dilutive QIP or an RBI letter. Cross-check via `get_company_context(section='sector_kpis', sub_section='capital_adequacy_ratio_pct')` and `advances_growth_yoy_pct`.
- **Disproportionate growth in unsecured retail or top-10-group exposure** — 5-8pp concentration lift quarter-on-quarter is a single-name stress latent.
- **RBI Prompt Corrective Action (PCA) proximity** — NNPA >6%, CRAR below the CCB-inclusive minimum, or two consecutive years of negative ROA trigger PCA; the watch-list status alone reprices the stock 10-20%.
- **Auditor rotation or qualification** — rotation cycles that land in a quarter of ratings-watch or resolution-plan pressure are informational; qualifications on asset classification or provisioning are forensic-grade tells. Cross-check via `get_events_actions(section='material_events')`.
- **Parent-conglomerate governance** for listed bank / NBFC subsidiaries — any credit event, SEBI show-cause, or liquidity downgrade at the parent propagates to the listed subsidiary's funding cost within 1-2 weeks.
- **Large related-party exposures** in private-group-owned NBFCs — disclosed RPT as a % of net worth that creeps from 5% to 15-20% across 4 quarters is a liquidity-cascade latent.

### Regulatory Risk Taxonomy — Cite the Specific Circular
Regulatory risk in BFSI is concrete, not vague. Tie each risk to the specific regulator and, where possible, the specific master-direction or circular:
- **RBI** — **Basel III norms** (CRAR, CET1, LCR, NSFR minima), **PCA framework** (asset quality, CRAR, leverage triggers), **Large Exposure Framework** (single counterparty 20%, group 25% of Tier-1), **Priority Sector Lending** targets (40% of ANBC, sub-targets for agri and weaker sections), **asset classification and provisioning** master direction, **digital-lending guidelines** (for NBFCs operating via LSP models).
- **SEBI** — insider-trading norms, FPI concentration rules, merchant-banker / broker regulations, mutual-fund TER caps (AMCs), portfolio-management-service guidelines.
- **IRDAI** — **solvency margin** (life 150%, general 150% of required), policyholder-bonus rules, **commission / expenses of management (EoM)** caps post-2023 amendment, product-approval regime for par/non-par/ULIPs.
- **Bank-nationalisation statutes** — for PSU banks, governance and board-composition rules sit under the Bank Nationalisation Act / SBI Act, outside RBI control; statute amendments are parliamentary, not regulatory.

Name the relevant master direction when the risk crystallises; vague "per regulations" framing loses the traceability that makes the risk actionable.

### Operational-Risk Concentration
Geographic concentration is the quietest risk in BFSI because aggregate portfolios look diversified until a state-level stress event. Examine:
- **Geographic** — single-state advances >25-30% of AUM (common for MFI, gold-loan, and regional housing-finance players) exposes the book to state-election-cycle farm-loan waivers, rainfall shocks, or localised bans on specific lending segments.
- **Sectoral** — commercial real estate exposure >8-10% of advances has been the recurring stress vector for NBFCs (FY19 cycle); MSME unsecured concentrations build late-cycle.
- **Customer segment** — corporate vs retail split matters because corporate NPAs are chunky and surprising while retail NPAs are smooth-but-structural. A bank shifting from 70/30 corporate/retail to 40/60 retail in 2-3 years has a different risk profile even at the same headline GNPA.
- **Product mix** — home loans (secured, long-tenor, low credit cost through cycle) vs unsecured personal loans (high credit cost, vintage-sensitive) vs credit cards (highest credit cost, revenue-rich) vs vehicle finance (collateral-backed but collection-intensive) — each has distinct repayment discipline and loss-given-default curves.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical BFSI drawdowns have recurring triggers; use these as the scaffolding for a bear case:
- **Systemic credit-cycle turn** — FY12-16 corporate NPL cycle (power, infra, metals) took PSU bank P/B from 1.2-1.5× to 0.4-0.6×; FY19-20 NBFC liquidity crisis repriced wholesale-funded NBFCs 50-70% in 6 months.
- **Regulatory ban / PCA entry** — PCA designation historically cost 30-40% in 2-3 months and took 4-8 quarters to exit.
- **Forensic / fraud event** — the asset-quality-review cycle (FY16-17) and the auditor-resignation cluster (FY19) each produced 40-60% drawdowns in named mid-cap private banks.
- **Parent-conglomerate liquidity cascade** — promoter-group stress at the holdco flows into the listed lending subsidiary's funding spreads within 2 weeks; the 2018-19 episode compressed funding multiples across the NBFC sub-sector.
- **Insurance combined-ratio blowout** — natural-catastrophe year (cyclone, flood cluster) or mis-pricing cycle on health insurance can take combined ratio from 102% to 115% in a single year and halve reported profits.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "GNPA breaching 6% with rising SMA-2" or "CRAR dropping below 12% without QIP announcement").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **100 bps repo-rate move** — NIM impact 10-25 bps for retail-heavy banks with repo-linked MCLR books; AFS book MTM on a 10Y-duration bond book is roughly 7-8% for a 100 bps parallel shift, which flows through P&L for held-for-trading and reserves for HTM/AFS.
- **+1 pp GNPA shock** — incremental provisioning at 70-80% PCR on the new NPA stock consumes 300-500 bps of ROE in the quarter of recognition.
- **10 pp CASA erosion** — NIM compression of 30-50 bps typically, depending on the term-deposit rate differential.
- **LCR breach scenario** — HQLA vs 30-day outflow ratio <100% is a regulatory-reporting event; most banks run 115-135%, so an LCR falling to 105% is a supervisory-attention line even without technical breach.

Route the arithmetic through `calculate` with the rate sensitivity, GNPA delta, and CASA mix as named inputs rather than hand-calculating.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='bfsi')` returns missing asset-quality or capital ratios, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end numbers; (2) `get_company_context(section='filings')` for the most recent BSE disclosure and any RBI correspondence; (3) `get_events_actions(section='material_events')` for governance events, auditor transitions, and ratings actions. Cite the source quarter for every extracted number. Do not fabricate GNPA / NNPA / CRAR — the risk agent's credibility depends on citing what the bank actually said.

### Open Questions — BFSI Risk-Specific
- "Is the current CRAR / CET1 buffer above statutory minimum sufficient to support disclosed advances-growth guidance without a QIP in the next 4 quarters?"
- "What is the SMA-2 trajectory over the last 4 quarters, and is it consistent with the headline GNPA stability or pointing to fresh slippage next quarter?"
- "Is any state-level regulation, loan-waiver announcement, or RBI circular specific to this sub-type currently in draft or public consultation?"
- "For microfinance or single-state-heavy lenders: what is the single-state advances concentration, and is any election cycle or rainfall-stress event imminent?"
- "For group-linked NBFCs: what is the disclosed related-party exposure as % of net worth and has it trended up materially over the last 4 quarters?"
