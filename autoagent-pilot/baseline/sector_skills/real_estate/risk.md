## Real Estate — Risk Agent

### Sub-type Archetype — Risk Surface Differs by Sub-type
The dominant risk axis is not the same across real-estate sub-types. For residential developers it is the demand-cycle and affordability (single-city over-supply, interest-rate shock); for commercial / REITs it is cap-rate widening and tenant-concentration; for integrated developers it is the interaction between the two; for land-bank plays it is monetisation velocity and land-title disputes; for specialty (warehousing, data-centre) it is customer-concentration and power-tariff (data-centre). State the sub-type's dominant risk axis in the report's opening paragraph before listing generic risks.

### Sector-Specific Governance Red Flags
Governance stress in real estate surfaces earlier through balance-sheet telemetry than through board drama. Scan for:
- **Promoter pledge in cyclical residential developers** — pledged promoter stake financing project-level SPV construction loans is a sector norm (see `ownership.md` for the pledge-vs-NDU distinction), but pledge creeping above 50% of promoter holding during a presales deceleration is a margin-call risk, historically realised in mid-cycle distress episodes.
- **Land-acquisition related-party transactions** — developers buying land from promoter-owned land-holding SPVs at above-market prices is a recurring capital-leakage pattern. Cross-check via `get_company_context(section='filings', sub_section='related_party_transactions')`.
- **Stake-dilution-for-capital mid-project** — QIPs or preferential allotments priced at the trough of a demand cycle transfer value from existing shareholders to the incoming institutional cohort.
- **Legal disputes on specific projects or land titles** — title litigation can freeze a project at the approval stage for 5-10 years; disclosed in `get_events_actions(section='material_events')` and filings.
- **RERA escrow manipulation** — cross-project fund transfers via contractor-shell entities, or delayed deposits to escrow, are sanctionable under state RERA acts. Watch for state-RERA orders and customer-complaint clusters.
- **Auditor rotation in a stress quarter** — qualifications on inventory valuation, project-completion estimates, or receivable-provisioning are forensic-grade tells.

### Regulatory Risk Taxonomy — Cite the Specific Act and Level
Regulatory risk in real estate is heterogeneous across state and central jurisdictions. Tie each risk to the specific regulator and the specific act:
- **RERA — state-level, from 2017** — each state has its own authority (MahaRERA, UP-RERA, Karnataka-RERA, etc.) with its own registration, escrow (70% rule), and delivery-timeline enforcement. Penalty orders are state-specific; a MahaRERA order does not bind in Karnataka. Name the specific state RERA when citing a risk.
- **GST** — **1%** on affordable segment (under ₹45L ticket, under 60 sqm metro / 90 sqm non-metro), **5%** on under-construction non-affordable, **NIL** on completed ready-to-move (no GST). Input tax credit was restricted post-April 2019. Stamp duty varies by state (4-7% in most jurisdictions).
- **SEBI REIT regulations (2014, with 2024 SM-REIT amendment)** — distribution minimum 90% of NOI, sponsor 15% minimum lock-in for 3 years, 25% minimum public float, related-party-transaction restrictions.
- **Environment clearance — state-level** — SEIAA (state-level) for projects up to 150,000 sqm built-up, MoEF-CC (central) above that threshold. Clearance delays of 6-18 months are routine; regime changes (e.g., EIA notification revisions) can invalidate in-process approvals.
- **Metro / National-Highway / Airport-adjacent land-use changes** — state-level land-use-plan revisions can reclassify agricultural or green-belt land into mixed-use, triggering windfall gains or reverse restrictions.
- **Zoning changes at city-level** — city-development-plan revisions (e.g., Mumbai DCPR, Delhi Master Plan, Bengaluru RMP) change FSI entitlements, setbacks, and permissible use; FSI changes can alter project NPV by 20-40% in a single notification.
- **NCDRC / consumer forums** — delay-penalty and possession-delay complaints are a recurring legal exposure for residential developers; aggregate penalty exposure can reach 5-10% of project revenue.

Vague "per regulations" framing loses the traceability that makes the risk actionable.

### Operational-Risk Concentration
Concentration is the quietest risk in real estate because aggregate portfolios look diversified until a city-level stress event:
- **Single-city concentration** — >40% of bookings (presales value) in one city is a stress vector. Historical examples: Gurugram oversupply 2018-20 hit DLF, ANANTRAJ, and NCR-heavy names; Mumbai oversupply 2022-23 hit LODHA and MACROTECH cohort; Bengaluru tech-job slowdown 2023 hit SOBHA, BRIGADE, PRESTIGE.
- **Affordability-cycle exposure for mid-segment developers** — mid-segment (₹50L-1.5Cr ticket) is most sensitive to home-loan affordability; a 150 bps home-loan rate spike compresses buyer-pool 20-30%.
- **Approval-delays on new-project launches** — if 30%+ of pipeline GDV is in projects awaiting approval, and approval timelines drift 6+ quarters, the launch-cadence collapse shows up in presales with a 2-3 quarter lag.
- **Construction-cost inflation** — cement, steel, and labour together are 55-65% of construction cost; a 15-20% input-cost spike compresses gross margin 400-700 bps unless passed through in realization.
- **Launch-strategy misfires** — premium product launched in an affordability-stressed market (or vice-versa) produces unsold-inventory build-up that takes 4-8 quarters to clear.
- **For REITs — tenant concentration** — top-10 tenants >40% of rent roll is a concentration vector; WALE <4 years with concentrated expiry clusters is a re-leasing risk.

### Bear-Case Scenarios — 30-50% Drawdown Triggers
Historical real-estate drawdowns have recurring triggers; use these as the scaffolding for a bear case:
- **Demand-cycle reversal** — demonetisation 2016, GST 2017, and COVID 2020 each compressed listed-developer P/NAV by 40-60% over 4-8 quarters. A comparable trigger in the current cycle would be a regulatory or tax shock of similar magnitude.
- **City-specific over-supply** — Gurugram 2018-20 compressed single-city-heavy developer P/Adj-Book by 50%+; Mumbai 2022-23 compressed mid-segment names 30-40%.
- **Interest-rate spike — 150 bps+** — home-loan affordability compression drives presales -15% to -25% over 2-3 quarters; operating-deleverage amplifies into EBITDA -400-700 bps.
- **Corporate-land-buyer drying up for commercial** — the 2020-21 WFH-driven office demand compression dropped net-absorption 50%+ for 6 quarters, widening cap-rate 75-100 bps and compressing office-REIT NAV 15-25%.
- **REIT distribution-yield expansion** — a 100 bps G-sec yield spike widens cap-rate 50-75 bps, compressing REIT NAV 10-15%; the distribution yield adjustment mechanically reprices units before NOI even moves.

Quantify each bear-case as a thesis-breaker: the metric threshold beyond which the base-case thesis is invalidated (e.g., "presales -20% for 3 consecutive quarters" or "city-level inventory months > 30").

### Sector-Specific Stress Tests
Quantify the sensitivity, don't just describe it. Typical ranges:
- **Presales -20% YoY** → reported revenue impact in FY+2 and FY+3 of -15% to -20% each; operating-deleverage amplifies EBITDA -300-600 bps; Net-Debt / EBITDA typically spikes 0.5-1.0 turns.
- **Realization per sqft -10%** → EBITDA margin -400-700 bps (since realization hits gross-margin directly on an inflexible construction-cost base).
- **Cap rate +100 bps for a REIT** → NAV -15-20%; distribution yield expansion widens trading discount further.
- **RERA delay-penalty accumulation** — 12-18 month possession delays with 10-12% compensatory-rent commitments can reach 5-8% of project revenue.
- **Construction cost +15%** — gross margin -400-600 bps; passthrough typically takes 2-3 launch cycles.

Route the arithmetic through `calculate` with presales delta, realization delta, and cap-rate shift as named inputs.

### Data-shape Fallback for Risk Metrics
When `get_quality_scores(section='realestate')` returns missing presales, inventory-months, or net-debt detail, fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='financial_metrics')` for management-disclosed quarter-end numbers; (2) `get_company_context(section='filings')` for the most recent BSE disclosure and state-RERA orders; (3) `get_events_actions(section='material_events')` for governance events, auditor transitions, and regulatory orders. Cite the source quarter for every extracted number.

### Open Questions — Real-Estate Risk-Specific
- "What is the single-city concentration of presales value, and is any city in the portfolio showing inventory-months > 24?"
- "What is the current promoter pledge level, and does the pledged portion collateralise project-SPV construction finance or promoter holding-company debt?"
- "How much of the pipeline GDV is in projects awaiting environment / zoning approval, and what is the weighted-average time-in-queue?"
- "For REITs: what is the top-10 tenant concentration of rent, the WALE, and the expiry cluster over the next 3 years?"
- "What is the aggregate NCDRC / RERA delay-penalty exposure disclosed in filings over the last 8 quarters?"
