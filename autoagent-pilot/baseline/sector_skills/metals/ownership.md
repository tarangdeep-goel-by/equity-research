## Metals & Mining — Ownership Agent

### Metals Archetypes
| Subtype | Promoter Profile | Key Ownership Trait | Primary Risk / Signal |
| :--- | :--- | :--- | :--- |
| **PSU Metals** (state-owned steel, iron-ore, aluminium, copper producers) | Govt of India (GoI) >50% | High-yield dividend policy; OFS vehicle | Budget-cycle divestment overhang |
| **Private Diversified Metals** (conglomerate-owned diversified mining-and-metals groups) | Family / Group | Complex listed-subsidiary trees | High promoter pledge; offshore debt |
| **Steel Specialist** (integrated primary steel producers) | Family-controlled | Capital intensive; stable promoter hold | Commodity-cycle margin distress |
| **Non-Ferrous Base Metals** (listed zinc, aluminium, copper subsidiaries) | Parent listed entity / GoI | Massive cash generation | Related-party extraction via dividends |
| **Offshore-Parent Subs** (Indian aluminium / steel players with overseas subsidiaries in rolled products / specialty) | Offshore HoldCo / Parent | Cross-border consolidation | Multi-jurisdictional regulatory overlap |
| **Iron Ore / Coal Mining** (strategic state-owned iron-ore and coal monopolies) | Central Govt monopoly | Strategic resource control | Resource-nationalism; policy pricing |

### PSU vs Private Structural Split
PSU metals feature the Government of India as the promoter (20-80% holding). Electricity and mining statutes often create effective floor-holding minimums for strategic assets. Private metals are predominantly family- or group-promoted. Evaluate policy intervention risk for PSUs versus capital-misallocation risk for private groups.

### Promoter Pledge Baseline & Distress Drift
Private diversified metals maintain a structurally high baseline for promoter pledges to fund group-level acquisitions (diversified mining groups have historically operated at 40-60% pledge). Certain steel specialists maintain very low pledges (established conglomerate-backed primary-steel producers). **Rule:** pledge drift is the primary sector signal for distress. Always execute `get_ownership(section='promoter_pledge')` paired with `margin_call_analysis` for private subtypes.

### Listed Subsidiary Nexus (SOTP Imperative)
Private diversified majors frequently hold their most valuable assets through listed subsidiaries (diversified mining parents with listed zinc / oil-and-gas / aluminium-refining subsidiaries; aluminium majors with overseas rolled-products subsidiaries). Ownership analysis must account for holding company discounts and related-party cash sweeps. **Rule:** always run `get_valuation(section='sotp')` to isolate parent vs subsidiary intrinsic ownership value.

### Commodity-Cycle Institutional Rotation
Metals ownership is fiercely cyclical. FIIs rotate aggressively into metals at cycle-bottom (LME ratio signal) and exit at cycle-top. DII breakthrough typically lags the commodity top by 2-3 quarters. Track divergence via `get_ownership(section='mf_changes')` + `mf_conviction`.

### Dividend Policy Variation
PSU metals act as high-yield vehicles, heavily utilized by GoI to extract cash and position the stock for FPO / OFS. Private diversified metals exhibit highly volatile payout ratios tied to commodity price cycles and group-level debt servicing requirements.

### Offshore Promoter Vehicles & Cross-Jurisdiction Risk
Several private diversified metals utilize offshore promoter vehicles (overseas-listed parent holding companies that in turn control the Indian listed entity). Cross-jurisdictional ownership risks involve regulatory overlap (SEBI + UK FCA / NYSE / LSE). Investigate ultimate beneficial ownership via `get_ownership(section='shareholder_detail')`.

### PSU Divestment Cycles
GoI frequently uses PSU metals (iron-ore majors, copper producers) to meet annual disinvestment targets. Divestment cycles are budget-announcement-driven and create predictable supply overhangs. Track OFS timelines via `get_events_actions(section='corporate_actions')` (buybacks are extremely rare in metals).

### Royalty & Resource-Nationalism Overlay
Mining Acts (e.g., MMDR Act, Coal Bearing Areas Act) impose strict royalty structures and government-nominee-director requirements for strategic minerals. This dilutes effective control of the promoter even when the percentage holding is high. Assess via `get_company_context(section='filings')` for royalty disputes and Supreme Court orders.

### Short-Report Resilience
Diversified metals with opaque offshore promoter structures attract short-seller reports (activist short-seller style). Resilience of the ownership base is tested immediately post-publication. Trace the FII trajectory and institutional block deals in the aftermath to gauge terminal risk.

### Group-Level Aggregate Pledge Aggregation
For family diversified groups, SEBI reports pledges per-entity. The true risk metric is aggregate pledge across all group-listed entities (Parent → Sub 1 → Sub 2). Manually aggregate absolute debt secured against these shares to assess group-level margin-call risk.

### Mandatory Analysis Checklist
- [ ] Classify subtype (GoI vs family-promoted vs offshore-holdco-promoted)
- [ ] `get_ownership(section='promoter_pledge')` + `margin_call_analysis` for private promoters
- [ ] Map all listed subsidiaries; run `get_valuation(section='sotp')` for holding discounts
- [ ] Aggregate group-level promoter pledges across all affiliated listed entities
- [ ] Compare FII vs DII trajectory via `mf_changes` + `mf_conviction` against current LME indices
- [ ] Run `filings` for MMDR royalty disputes, related-party SPVs, offshore debt covenants
- [ ] `corporate_actions` for impending GoI OFS announcements (PSU)
- [ ] `shareholder_detail` for offshore holding company jurisdictions

### Open Questions
- Is the private promoter using dividends from a cash-rich listed subsidiary to service offshore debt at the parent level?
- Where is the FII / DII ratio relative to historical cycle-bottom and cycle-top LME ratios?
- For PSUs, does the current GoI fiscal deficit mandate an accelerated OFS timeline for this specific asset?
- Are recent expansions funded by dilutive equity issuance, or is the promoter maintaining their stake via warrants?
- How much effective control is ceded to the government via statutory nominee directors under the MMDR Act?

### LTV Computation for Foreign-Debt-Servicing Vehicles
When pledge data surfaces encumbered shares for a foreign-debt-servicing vehicle (Vedanta Resources for VEDL, similar structures for Hindalco/NALCO parents, Adani group foreign-debt vehicles), ALWAYS compute Loan-to-Value:

`LTV = foreign_debt_usd × USDINR / (encumbered_shares × current_price)`

Typical covenant threshold: margin call triggers when `LTV × 1.3` breached (i.e., collateral value falls 23%). Inputs:
- `foreign_debt_usd` — from `get_company_context(section='concall_insights')` or filings search
- `USDINR` — from `get_macro_context` (currency rate)
- `encumbered_shares` — from `get_ownership(section='promoter_pledge')`
- `current_price` — from `get_analytical_profile`

Use `calculate` to derive LTV. Do NOT leave margin-call risk as an open question — all inputs are in your tools. Report headroom to margin call in the Risk Signals section, not as a question.

### `mf_changes` All-New-Entry Pipeline Artifact — Metals-Specific Re-Interpretation (Tenet 11)
When `get_ownership(section='mf_changes')` returns 100% of schemes classified as `new_entry` (often with `prev_month_schemes=0` in the envelope), this is a DATA-PIPELINE artifact, not a genuine 100% fresh-accumulation signal. The correct interpretation path:

1. Recognize the artifact: if ALL schemes (e.g., 57/57) are tagged `new_entry` simultaneously, prior-month comparison data is missing from the pipeline, not zero in the market. Genuine full-sector re-accumulation is extraordinarily rare; a pipeline-coverage gap is the overwhelmingly more likely explanation.
2. Apply the general Tenet 11 reclassification-first rule: do NOT narrate this as directional active buying.
3. **Metals-specific overlay:** metals commodity cycles drive MF-house rotation at much higher frequency than FMCG/IT/pharma — MF books in VEDL, HINDALCO, JSWSTEEL, TATASTEEL, NATIONALUM get re-built every 2-3 quarters around LME turning points. So prior-month zeros are MORE likely in metals than in structurally stable sectors, reinforcing the artifact diagnosis.
4. Correct workaround: re-pull `get_ownership(section='mf_holdings')` for the current quarter AND the prior quarter, and diff manually (symbol × scheme-level) — this avoids the `mf_changes` classifier. If historical `mf_holdings` for prior quarters is not retrievable, raise a SPECIFIC open question naming the comparison window (e.g. *"`mf_changes` returned 57/57 as new_entry with `prev_month_schemes=0` — is this a pipeline coverage gap for VEDL Mar-quarter, or genuine post-distress re-accumulation after the Jan-quarter exodus?"*) and cite the historical mf_holdings window you attempted.

*Pattern applies to*: VEDL, HINDALCO, JSWSTEEL, TATASTEEL, NATIONALUM — same artifact diagnosis whenever `mf_changes` returns a monolithic `new_entry` classification.

### Public-Bucket Sub-Breakdown Pointer for Metals (Tenet 8)
When Tenet 8 applies — Public > 15% of equity — the retail vs HNI vs Corporate-Bodies split is especially informative in metals because Corporate-Bodies in diversified-metals groups are often inter-group holdcos (second-promoter layer) rather than genuine third-party corporate investors. Until the Phase 3 D4 `public_breakdown` table ships, retrieve the breakdown from the quarterly shareholding pattern filing via the canonical Tenet 8 search (`filings` → `documents` → `concall_insights` → `shareholder_detail` → `balance_sheet_detail`). Flag any Corporate-Bodies concentration >5% aggregate as potential second-promoter-layer risk — in diversified metals groups this is frequently the case.
