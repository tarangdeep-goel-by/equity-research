## Chemicals — Ownership Agent

### Chemicals Archetype
| Subtype | Promoter Profile | Institutional Behavior | Valuation & Ownership Signal |
| :--- | :--- | :--- | :--- |
| **Specialty Chemicals** | Multi-gen family; 50-75% | High FII / DII structural accumulation | Premium multiples; brand / IP moat |
| **Commodity / Petrochem** | Conglomerate or family | Cyclical churn; macro-driven | Feedstock-spread sensitivity; low margin |
| **Agrichemicals** | Family / global sub-structures | Seasonal MF flows | Monsoon correlation; regulatory approvals |
| **Paints** | Oligopoly family / MNC split | Stable anchor DII / FII; low turnover | Branded-goods pricing power; high stability |
| **Pigments & Dyes** | Mid-cap family promoters | Export-dependent accumulation | Global textile / auto demand sensitivity |
| **MNC Subsidiaries** | Foreign parent 50-75% | Defensive / yield-focused DIIs | Royalty repatriation; high dividend payout |
| **Fluorochemicals** | Family promoters | Strategic FII capital | China+1 capex pipeline execution |

### Family Dominance & Near-Zero Pledge Rule
Indian specialty chemicals and paint sectors are defined by multi-generational family-promoter dominance. Baseline promoter holding is stable at 50-75%. Execute `get_ownership(section='shareholder_detail')` to map cross-holdings via family trusts. Sector-wide baseline for promoter pledge is near zero (<3%). Any pledge spike above this is a severe anomaly signaling liquidity stress outside the core chemical business. Verify baseline via `get_ownership(section='promoter_pledge')`.

### Paints Oligopoly Stability & Price Discipline
The Indian paints sector is a concentrated oligopoly commanding ~70% market share collectively. Institutional ownership is characterized by anchor DII / FII stability and low turnover. Promoter-holding stability alongside coordinated price discipline (1-2 lead-and-follow price hike rounds annually) is the defining ownership tell of the oligopoly. Monitor `mf_changes` for structural shifts or defensive reallocation triggered by entry of heavily capitalized new competitors from adjacent diversified-conglomerate capex announcements.

### MNC Subsidiaries — Repatriation Architecture
MNC chemical subsidiaries operate with rigid 50-75% foreign-parent holding. Institutional ownership skews toward yield-seeking defensive domestic funds. Analyze extraction architecture: higher-than-peer dividend payouts and rising royalty-to-revenue percentages signal parent-level capital repatriation. Execute `get_events_actions(section='corporate_actions')` to monitor unusual buybacks (rare but highly signaling) and special dividends.

### China+1 FII Cycle & FDI Regulations
Fluorochemicals and fine chemicals are structural beneficiaries of global supply-chain diversification. FII accumulation in these subtypes correlates with the China+1 narrative. Anticipate aggressive FII rotation out when China-reopening or chemical-dumping narratives gain traction; use `concall_insights` to track management commentary on Chinese dumping. Per FEMA NDI Rules, FDI is permitted up to 100% under the automatic route for most chemicals. Dual-use, defence-adjacent, or strategic chemicals may trigger restrictive government approval routes.

### ESG Triggers & CPCB Compliance
Pollution Control Board (CPCB / SPCB) compliance is a binary ownership filter. ESG-focused funds filter out chemical cos with active environmental show-cause or closure notices. Execute `filings` to continuously track environmental compliance disclosures. An adverse filing can trigger indiscriminate ESG-fund exits, suppressing valuations independent of short-term earnings quality.

### Capex-Cycle QIPs & Agrichem Seasonality
Specialty chemical players frequently execute QIPs during multi-year capex cycles to fund new capacity. Institutional absorption quality of QIPs is a prime cycle indicator. Use `corporate_actions` to evaluate QIP allocations. Agrichemical institutional flows exhibit monsoon-linked seasonality; execute `mf_changes` + `mf_conviction` to track pre-monsoon MF accumulation. Agrichem commands lower structural FII weightage than specialty chemicals due to weather dependency and regulatory hurdles.

### Listed Subsidiaries & SOTP Complexity
Conglomerate chemical entities frequently utilize complex cross-holdings or publicly listed subsidiaries (e.g., a commodity-chemical parent holding a listed agrichem subsidiary; multi-country global sub-structures in agrichem MNCs). Execute `get_valuation(section='sotp')` to properly attribute ownership stakes and isolate the core chemical business valuation from the holding-company discount applied to listed-subsidiary stakes.

### Mandatory Checklist
- [ ] Verify promoter pledge at sector baseline (<3%) via `promoter_pledge`
- [ ] Execute `filings` for CPCB / SPCB show-cause notices or ESG triggers
- [ ] Map family holding vehicles and trust structures via `shareholder_detail`
- [ ] Track QIP absorption for capacity ramp-ups via `corporate_actions`
- [ ] Calculate SOTP for entities with listed subs via `sotp`
- [ ] Correlate MF holding changes with monsoon cycle via `mf_changes` + `mf_conviction` (Agrichem)
- [ ] Analyze royalty-to-revenue trends and payout ratios for MNC subsidiaries

### Open Questions
- Are ESG-mandated FIIs actively reducing exposure due to recent CPCB notices or environmental non-compliance?
- Does institutional absorption of the recent capex-funding QIP indicate conviction in a prolonged China+1 cycle?
- Is the royalty + dividend payout structure of the MNC subsidiary signaling elevated parent-company cash extraction?
- How is institutional ownership within the paints oligopoly reacting to capacity additions by new conglomerate entrants?
- Are pre-monsoon MF flows aligning with historical seasonal accumulation patterns for the agrichemical portfolio?

### Specialty vs Commodity Peer Anchor — Chemicals FII and Pledge (Tenet 18)
"12% FII" is uninterpretable in chemicals without the specialty-vs-commodity split because moat and margin profile diverge sharply between the two buckets. Always anchor FII % and pledge % against the correct peer set:

**FII % anchor (specialty):** *"FII stake of X% sits at the Y-th percentile within Indian specialty-chemicals top-tier (PIDILITIND, SRF, AARTIIND, NAVIN FLUORINE, DEEPAKNITR peer set via `get_peer_sector(section='benchmarks')`). Specialty-chem FII benchmarks run structurally higher (typical band 18-28%) than commodity-chem (typical band 6-14%) because branded-specialty ROCE of 20-30% attracts long-only foreign mandates; commodity chemicals earn cycle-weighted ROCE."* A 12% FII is *mid-range* for commodity-chem, but *bottom decile* for top-tier specialty — the qualitative read flips.

**FII % anchor (commodity):** *"For TATACHEM / DCM Shriram / GSFC (commodity peer set), FII tends to cycle-rotate — absolute % is a weaker signal than FII direction vs the current LME-soda-ash / urea-feedstock cycle."*

**Promoter pledge anchor (chemicals-specific baseline):** Chemicals sector carries a HIGHER baseline promoter pledge than pharma — commodity cyclicality drives working-capital borrowing and some families routinely pledge up to 8-12% as standing group-level liquidity. This is UNLIKE the near-zero baseline of pharma/FMCG/IT. Specialty chemicals (PIDILITIND/SRF/AARTIIND/NAVIN/DEEPAKNITR) trend closer to <5%; commodity chemicals (TATACHEM/DCM/GSFC) routinely sit at 5-15% with no distress signal. A pledge at 10% in a specialty name is a red flag; the same 10% in a commodity name is near-baseline. Cite the specialty-vs-commodity classification BEFORE narrating pledge conviction.
