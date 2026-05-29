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
Indian pharma is dominated by multi-generational founder-families holding 40-70% stakes. Ownership is rarely direct; it is routed via complex family-trust entities and unlisted investment vehicles (promoter finance-arm trusts are standard for large-cap Indian generics majors). Use `get_ownership(section='shareholder_detail')` to map ultimate beneficial ownership. Promoter pledging is *not* uniformly rare across Indian pharma — while many large founder-families run zero/near-zero pledge, several listed pharma names have historically carried high double-digit promoter pledges (e.g. Aurobindo and Ajanta have both run pledges in the high-teens-to-20%+ range in various periods). So benchmark pledge against the *specific* promoter's own history, not a blanket "<3% sector baseline". A *fresh* pledge or a sharp rise on a previously-unpledged family is the acute red flag (non-pharma group distress, M&A funding gap, or personal-liquidity stress); a stable structural pledge on a name that always carried one is less informative. Verify via `get_ownership(section='promoter_pledge')`.

### USFDA Inspection Cycles & FII Flow Correlation
Institutional flows in Indian generics are tethered to USFDA inspection cycles. Negative observations (Form 483s, OAI, Warning Letters) trigger 5-15% FII exits over 2-3 quarters. Voluntary Action Indicated (VAI) or clear Establishment Inspection Reports (EIR) drive FII re-entry. Map FII flow timing against the target's USFDA audit calendar via `get_company_context(section='concall_insights')` for management commentary and `get_company_context(section='filings')` for event-driven disclosures.

### Patent-Cliff Catalysts & Transient FII Spikes
Blockbuster patent expirations in regulated markets (large generic-launch opportunities in oncology, gastro, multiple-sclerosis and similar regulated-market chemistries) drive event-driven FII concentration spikes. Offshore funds rotate into Indian formulators holding 180-day exclusivity or First-to-File (FTF) status. This ownership is highly transient — treat these spikes as cyclical momentum flows rather than permanent re-ratings. Anticipate sharp exits once generic pricing normalizes.

### M&A Dilution Cycles & Specialty Transitions
Big pharma frequently executes offshore equity-funded M&A to acquire US / European specialty assets (Indian generics majors acquiring overseas specialty / branded-generic platforms is a recurring cycle). This creates distinct ownership dilution cycles and goodwill-heavy balance sheets. Use `get_valuation(section='sotp')` and `filings` to assess offshore subsidiary ownership implications. As generic formulators shift to capital-intensive specialty / biosimilars (biosimilar-platform pivots), the investor base morphs — volume-focused domestic MFs rotate out, risk-tolerant global FIIs rotate in.

### MNC Subsidiary Repatriation & FDI Regulations
Foreign-parent promoters of MNC subs hold 50-75% and structurally use corporate actions for cash repatriation. Track unusual buyback timing and special-dividend events via `get_events_actions(section='corporate_actions')` as parent-cash-sweep signals. Under the Indian FDI Policy (DPIIT), **brownfield pharma FDI is permitted up to 74% under the automatic route, with government approval required only beyond 74%** (subject to NLEM production-maintenance conditions); greenfield is 100% automatic. The government-approval gate therefore only bites for parent creep-ups past 74%, which is what tempers the math for spontaneous parent-led delistings or buyouts at already-high-stake brownfield subsidiaries.

### PE-Exit Overhangs & CRO/CDMO Exceptionalism
PE-backed players face severe equity supply overhangs during exit windows — when anchor PEs divest, 10-15pp equity can hit the market over several months. Pre-empt via filings and lock-in expiries. CRO / CDMO specialists operate with fundamentally different dynamics: cleaner balance sheets, higher ESG scores, no branded-drug pricing controversies → sticky long-term MF ownership. Pair `mf_changes` + `mf_conviction` to validate institutional positioning in this sub-sector.

**ESOP dilution in technocrat-led CRO/CDMOs** — these names typically run large ESOP/RSU pools to retain scientific talent, which causes *creeping equity dilution* not visible in the headline shareholding split. Track ESOP-pool expansions (fresh grants / pool top-ups approved in AGM/postal-ballot filings) and the exercise run-rate, and adjust both the institutional float and the *diluted* share count when computing true market cap — a CDMO valued on basic shares while a 3-6% ESOP pool vests over the forecast window is understating dilution. Verify via `get_events_actions(section='corporate_actions')` and `filings` for ESOP-scheme disclosures.

### Mandatory Checklist
- [ ] Trace ultimate beneficial ownership via `shareholder_detail` for multi-generational family trusts
- [ ] Validate `promoter_pledge` against the promoter's *own* history (some pharma names structurally carry high double-digit pledges, e.g. Aurobindo / Ajanta); a *new* pledge or a sharp rise vs that name's baseline is the acute signal, not the absolute level
- [ ] Correlate QoQ FII entry / exits with USFDA Form 483 / OAI timelines via `concall_insights` + `filings`
- [ ] Assess lock-in expiries for PE-backed pharma to forecast exit-driven supply overhangs
- [ ] Track MNC subsidiary `corporate_actions` for parent-led repatriation disguised as buybacks
- [ ] Evaluate offshore M&A structural impact via `sotp` and `filings` for dilution history
- [ ] Map `mf_changes` + `mf_conviction` together when analyzing CRO / CDMO institutional stability

### Open Questions
- Does recent FII accumulation reflect long-term structural belief in the pipeline, or a transient patent-cliff FTF play?
- Relative to this promoter's *own* pledge history, is a new or rising pledge indicating hidden off-balance-sheet group distress / private-venture funding, or is it a structurally-stable pledge typical for this name?
- How does the target's strategic shift from generic formulations to biosimilars / specialty alter its targeted institutional investor base and capital intensity?
- For an MNC sub already near or above 74% parent holding, would the government-approval gate (required only beyond 74% brownfield FDI) deter further parent consolidation, open-market creeping acquisition, or a delisting attempt?

### Family Trust Structural Framing (Shanghvi / promoter-family holdcos)
Sun Pharma's promoter group holds ~54.48%, but this is *not* purely a trust structure: ~40.30% sits in the promoter holdco Shanghvi Finance Pvt Ltd while Dilip Shanghvi himself holds ~9.6% as a *direct personal stake* (the balance across other family members / related entities). So treat the holding as a holdco-plus-direct-family mix, not a monolithic trust. Zero open-market promoter activity is STRUCTURAL for such promoter-holdco structures, not informational. Do not infer low conviction from flat promoter pledge trajectory. The correct signal to track is any NEW pledging event (indicates family leverage), trust-internal reclassification (e.g. intra-family transfers), or unusual insider SELLING by non-promoter key managerial personnel — not the absence of routine open-market buying. This rule generalizes to any Indian pharma/manufacturing promoter using a family trust / HUF / multiple-related-party structure (Dr. Reddy's, Lupin, Cipla family holdings).

### US Generics vs Domestic Chronic Revenue Mix — Mandatory Institutional-Flow Cross-Reference
For Indian pharma, institutional positioning shifts MUST be correlated with the underlying US Generics vs Domestic Chronic vs Specialty/Biosimilar revenue mix — this is the classic framework Indian pharma analysts use, and skipping it produces a hollow ownership read. Extract the segment mix from `get_company_context(section='concall_insights', sub_section='financial_metrics')` (most pharma cos disclose US %, Domestic %, RoW % in opening remarks). Then map institutional flows to mix-shift events:

- **FII accumulation + rising US Specialty %** → high-conviction long-cycle bet on the specialty pipeline (Sun Pharma's Ilumya/Cequa/Winlevi trajectory, Dr. Reddy's biosimilars, Cipla's inhalers in US).
- **FII trim + falling Domestic Chronic %** → defensive rotation; Domestic Chronic (cardio, diabetes, derma) is the stable-yield bucket; FIIs leaving when chronic % drops signal earnings-quality concerns.
- **DII accumulation + rising US Generics %** → contrarian bet on FDA-recovery / patent-cliff opportunities; DIIs typically more comfortable with US generics cyclicality than FIIs.
- **MF rotation in the AuroraPharma/Aurobindo style names** when Domestic % rises = MF prefer the predictable cash-flow profile.

Cite the mix shift in the Money Flow Story (Section 2) — "FIIs added 3.2pp coincident with US Specialty growing from 18% → 27% over FY23-FY25" is institutional-grade analysis. "FIIs added 3.2pp" alone is descriptive, not analytical.

### USFDA Event Lookup — Canonical Search Worked Pattern
For any Indian pharma with material US revenue exposure (Lupin, Dr. Reddy's, Cipla, Aurobindo, Divi's, Natco and similar generics / API exporters), whenever the narrative touches an FDA event — Form 483, Warning Letter, OAI classification, Import Alert, or EIR receipt — concalls alone systematically under-disclose. Management characterizes; regulators and press releases adjudicate. The *full 5-source canonical search* is mandatory before any FII-exit / FII-reentry correlation is drawn; calling `concall_insights` in isolation is the failure mode.

1. `get_company_context(section='filings', query='USFDA|Form 483|Warning Letter|OAI|Import Alert')` — BSE/NSE regulatory disclosures. Under SEBI LODR Reg 30, *Warning Letters and Import Alerts* are routinely disclosed as material events; a bare *Form 483* is disclosed only when the board deems it material, so the absence of a 483 in exchange filings is non-confirmatory rather than proof none was issued.
2. `get_company_context(section='documents', query='FDA|inspection|EIR|establishment inspection')` — press releases announcing inspection outcomes and EIR receipt. EIR receipt (closure of inspection with acceptable classification) is *often* announced via press release, but is also frequently disclosed via exchange filing when treated as material — check both surfaces, do not assume one channel.
3. `get_company_context(section='concall_insights', sub_section='flags')` — management's own flagging of outstanding observations; then re-query with `sub_section='management_commentary'` for the characterization (remediation timeline, capex, CAPA progress) on the same inspection cycle.
4. `get_ownership(section='shareholder_detail')` — *skip — not applicable to FDA events* (ownership structure does not change in response to regulatory observations; flow changes are captured upstream via FII/DII quarterly tables).
5. `get_fundamentals(section='balance_sheet_detail')` — *skip — not applicable* (FDA events do not manifest in balance-sheet line items within the quarter of occurrence; remediation capex is already captured in concall_insights step 3).

If all five sources return empty for the facility and inspection window cited in management commentary, raise a SPECIFIC open question naming the inspection date and facility (e.g. *"Halol Block-4 inspection closed October 2025 per concall — no Form 483 / EIR disclosure found across filings or documents; is the observation letter still outstanding or was the EIR received post-cutoff?"*) — not a generic "what's the FDA status?"

*Pattern applies to*: Sun Pharma's Halol / Mohali cycle, Lupin's Goa / Pithampur, Dr. Reddy's Bachupally / Srikakulam, Cipla's Indore / Goa, Aurobindo's Andhra units — same 5-source path whenever the ownership narrative invokes an FDA event.
