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
