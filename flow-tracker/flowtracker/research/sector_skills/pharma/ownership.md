## Pharma — Ownership Agent

### Pharma Subtype Archetypes
| Subtype | Promoter Profile | Institutional Dynamics | Illustrative Examples |
| :--- | :--- | :--- | :--- |
| **Founder-Family Big Pharma** | Family trusts (40-70%); multi-generational | FIIs track FDA cycles; MFs track domestic volume growth | large-cap Indian generics majors |
| **MNC India Subsidiary** | Foreign parent (50-75%); repatriation focus | Low float; defensive MF holding; dividend-yield focused | listed Indian subsidiaries of global pharma MNCs |
| **PE-Backed Pharma** | Private Equity anchor; exit-driven horizons | Liquidity overhang during PE stake-sale windows | mid-cap pharma with PE-fund anchor shareholders |
| **CRO / CDMO Specialist** | Technocrat founders; very low pledges | High MF / ESG conviction; index-fund favorites | pure-play CRO / CDMO and API-to-formulation outsourcing specialists |
| **API / Intermediates** | Concentrated domestic holdings; cyclical | Lower FII presence; high retail churn on distress | domestic API / intermediate manufacturers |
| **Formulations + Specialty** | Family or institutional-backed; high R&D | FII spikes linked to biosimilar / FTF pipeline approvals | biosimilar-platform players and specialty-formulation mid-caps |
| **Hospital-Owning / Integrated** | Corporate / Family (capex-heavy) | Heavy overlap with healthcare / REIT funds | listed hospital chains and integrated healthcare operators |

### Multi-Generational Family Trusts & Pledge Anomalies
Indian pharma is dominated by multi-generational founder-families holding 40-70% stakes. Ownership is rarely direct; it is routed via complex family-trust entities and unlisted investment vehicles (promoter finance-arm trusts are standard for large-cap Indian generics majors). Use `get_ownership(section='shareholder_detail')` to map ultimate beneficial ownership. Promoter pledging by Indian pharma families is historically rare (baseline <3%). Treat any sudden promoter pledge as an acute red flag signaling non-pharma group distress or catastrophic M&A funding gaps. Verify via `get_ownership(section='promoter_pledge')`.

### USFDA Inspection Cycles & FII Flow Correlation
Institutional flows in Indian generics are tethered to USFDA inspection cycles. Negative observations (Form 483s, OAI, Warning Letters) trigger 5-15% FII exits over 2-3 quarters. Voluntary Action Indicated (VAI) or clear Establishment Inspection Reports (EIR) drive FII re-entry. Map FII flow timing against the target's USFDA audit calendar via `get_company_context(section='concall_insights')` for management commentary and `get_company_context(section='filings')` for event-driven disclosures.

### Patent-Cliff Catalysts & Transient FII Spikes
Blockbuster patent expirations in regulated markets (large generic-launch opportunities in oncology, gastro, multiple-sclerosis and similar regulated-market chemistries) drive event-driven FII concentration spikes. Offshore funds rotate into Indian formulators holding 180-day exclusivity or First-to-File (FTF) status. This ownership is highly transient — treat these spikes as cyclical momentum flows rather than permanent re-ratings. Anticipate sharp exits once generic pricing normalizes.

### M&A Dilution Cycles & Specialty Transitions
Big pharma frequently executes offshore equity-funded M&A to acquire US / European specialty assets (Indian generics majors acquiring overseas specialty / branded-generic platforms is a recurring cycle). This creates distinct ownership dilution cycles and goodwill-heavy balance sheets. Use `get_valuation(section='sotp')` and `filings` to assess offshore subsidiary ownership implications. As generic formulators shift to capital-intensive specialty / biosimilars (biosimilar-platform pivots), the investor base morphs — volume-focused domestic MFs rotate out, risk-tolerant global FIIs rotate in.

### MNC Subsidiary Repatriation & FDI Regulations
Foreign-parent promoters of MNC subs hold 50-75% and structurally use corporate actions for cash repatriation. Track unusual buyback timing and special-dividend events via `get_events_actions(section='corporate_actions')` as parent-cash-sweep signals. Under the Indian FDI Policy, **brownfield pharma FDI requires government approval**; greenfield is 100% automatic. This caps probability of spontaneous parent-led delistings or buyout math for established brownfield subsidiaries.

### PE-Exit Overhangs & CRO/CDMO Exceptionalism
PE-backed players face severe equity supply overhangs during exit windows — when anchor PEs divest, 10-15pp equity can hit the market over several months. Pre-empt via filings and lock-in expiries. CRO / CDMO specialists operate with fundamentally different dynamics: cleaner balance sheets, higher ESG scores, no branded-drug pricing controversies → sticky long-term MF ownership. Pair `mf_changes` + `mf_conviction` to validate institutional positioning in this sub-sector.

### Mandatory Checklist
- [ ] Trace ultimate beneficial ownership via `shareholder_detail` for multi-generational family trusts
- [ ] Validate `promoter_pledge` (any deviation above <3% sector baseline is acute risk)
- [ ] Correlate QoQ FII entry / exits with USFDA Form 483 / OAI timelines via `concall_insights` + `filings`
- [ ] Assess lock-in expiries for PE-backed pharma to forecast exit-driven supply overhangs
- [ ] Track MNC subsidiary `corporate_actions` for parent-led repatriation disguised as buybacks
- [ ] Evaluate offshore M&A structural impact via `sotp` and `filings` for dilution history
- [ ] Map `mf_changes` + `mf_conviction` together when analyzing CRO / CDMO institutional stability

### Open Questions
- Does recent FII accumulation reflect long-term structural belief in the pipeline, or a transient patent-cliff FTF play?
- Are minor upticks in family promoter pledges indicating hidden off-balance-sheet group distress or private ventures?
- How does the target's strategic shift from generic formulations to biosimilars / specialty alter its targeted institutional investor base and capital intensity?
- Will pending government approvals under brownfield FDI rules deter MNC-parent consolidation or open-market creeping acquisitions?

### Family Trust Structural Framing (Shanghvi / promoter-family holdcos)
Sun Pharma's Shanghvi family holds 54.48% via a family trust structure (not direct personal holdings). Zero open-market promoter activity is STRUCTURAL for family-trust holdcos, not informational. Do not infer low conviction from flat promoter pledge trajectory. The correct signal to track is any NEW pledging event (indicates family leverage), trust-internal reclassification (e.g. intra-family transfers), or unusual insider SELLING by non-promoter key managerial personnel — not the absence of routine open-market buying. This rule generalizes to any Indian pharma/manufacturing promoter using a family trust / HUF / multiple-related-party structure (Dr. Reddy's, Lupin, Cipla family holdings).

### US Generics vs Domestic Chronic Revenue Mix — Mandatory Institutional-Flow Cross-Reference
For Indian pharma, institutional positioning shifts MUST be correlated with the underlying US Generics vs Domestic Chronic vs Specialty/Biosimilar revenue mix — this is the classic framework Indian pharma analysts use, and skipping it produces a hollow ownership read. Extract the segment mix from `get_company_context(section='concall_insights', sub_section='financial_metrics')` (most pharma cos disclose US %, Domestic %, RoW % in opening remarks). Then map institutional flows to mix-shift events:

- **FII accumulation + rising US Specialty %** → high-conviction long-cycle bet on the specialty pipeline (Sun Pharma's Ilumya/Cequa/Winlevi trajectory, Dr. Reddy's biosimilars, Cipla's inhalers in US).
- **FII trim + falling Domestic Chronic %** → defensive rotation; Domestic Chronic (cardio, diabetes, derma) is the stable-yield bucket; FIIs leaving when chronic % drops signal earnings-quality concerns.
- **DII accumulation + rising US Generics %** → contrarian bet on FDA-recovery / patent-cliff opportunities; DIIs typically more comfortable with US generics cyclicality than FIIs.
- **MF rotation in the AuroraPharma/Aurobindo style names** when Domestic % rises = MF prefer the predictable cash-flow profile.

Cite the mix shift in the Money Flow Story (Section 2) — "FIIs added 3.2pp coincident with US Specialty growing from 18% → 27% over FY23-FY25" is institutional-grade analysis. "FIIs added 3.2pp" alone is descriptive, not analytical.
