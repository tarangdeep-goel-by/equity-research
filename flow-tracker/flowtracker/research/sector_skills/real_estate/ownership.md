## Real Estate — Ownership Agent

### RE Company Archetypes & Regulatory Fingerprints
Real estate ownership structures dictate capital availability, project pipeline velocity, and governance discounts. Always map the target to its archetype before analyzing shareholding percentages.

| Subtype | Ownership Fingerprint | Regulatory / Structural Note |
| --- | --- | --- |
| **Residential Developer** (top-tier listed Indian developers) | Heavy family-promoter dominance (40-75%). High pledge incidence; cyclical FII/QIP spikes. | Heavily governed by RERA. Frequent dilution via QIPs for land banks. |
| **Commercial / REIT** (listed office, retail, and business-park REITs) | Unit-holders, not shareholders. Sponsor/Manager split. PE/Institutional dominance. | SEBI REIT Regs 2014 (as amended 2023): Minimum 25% public float; Sponsor min 15% for first 3 years post-listing, then a **perpetual graded** holding (≥5% of units / ₹1,000 Cr lower, declining over the REIT's life — no longer a clean 3-year lock-in expiry). |
| **SM-REIT** (Small & Medium REIT, listed/listing fractional-ownership schemes) | Unit-holders; scheme-level (per-asset) structure under one trust. Distinct from full REITs. | SEBI SM-REIT Regs 2024: asset size **₹50 Cr–₹500 Cr** per scheme; min 200 investors; **sponsor unitholding 5% if the scheme is unleveraged, 15% if leveraged** (different from full-REIT 15%); 95% of assets must be completed and revenue-generating. |
| **Diversified / Conglomerate Sub** (developers that are arms of large diversified Indian conglomerates) | Parent conglomerate acts as promoter. High retail/DII trust; near-zero promoter pledge. | Parent capital allocation limits external equity needs. Governance premium vs independent developers. |
| **Affordable Housing Specialist** | Higher presence of specialized AIFs / ESG-focused PE funds. | Often leverages government subsidy frameworks (PMAY, CLSS); ownership includes social-impact capital. |
| **Co-working / Flexspace** (listed flexspace operators) | Startup cap-table transition: VC/PE heavy, minimal family promoter. | High free-float expansion post-IPO lock-in expiries. Watch for PE exit blocks. |

### Family-Promoter Dominance & The Pledge-NDU Caveat
Indian real estate is characterized by heavy family-promoter holdings (typically 40-75%). A critical sector-specific variable is the **pledge and Non-Disposal Undertaking (NDU)** profile. Use `get_ownership(section='promoter_pledge')` to evaluate the nature of the pledge. In real estate, pledges/NDUs often collateralize project-level SPV construction loans rather than personal margin funding (unlike IT or FMCG). A 30% pledge in RE is not immediately a margin-call risk. However, during deteriorating RE cycles severe margin calls do occur (historical cautionary tales of mid-cycle developer-distress episodes where pledged promoter stakes were invoked). Always parse `get_company_context(section='filings')` to confirm if pledges back operating project debt or promoter-level holding companies.

### QIP Usage Pattern: The Land Bank Cycle
Residential developers frequently raise equity via QIPs every 2-4 years. Unlike industrial sectors where QIPs signal distress deleveraging, RE developers use QIPs primarily to fund new land acquisition. Run `get_events_actions(section='corporate_actions')` to track QIP frequency. Correlate equity dilution with the project launch pipeline: if a QIP is not followed by corresponding pre-sales velocity within 12-18 months, the equity was poorly absorbed. FII participation in these QIPs often marks the beginning of a fresh 3-year land-acquisition cycle.

### FDI Limits & FEMA Construction-Development Rules
Foreign Direct Investment (FDI) in construction development (townships, residential, commercial complexes) is permitted under the **100% automatic route** per FEMA NDI Rules 2019. The earlier minimum-floor-area (20,000 sq m) and minimum-capitalization ($5M) conditions from Press Note 10 of 2014 were **abolished by Press Note 12 of 2015** — do not cite them as live constraints. A **3-year lock-in** on each tranche of original investment still applies (with specific early-exit exemptions, e.g. exit after trunk-infrastructure completion or to another non-resident). Distinguish between FPIs holding listed shares and FDIs taking direct equity stakes in unlisted project SPVs via `get_company_context(section='filings')`. Real estate investment trusts and REIT-ManCos have their own FDI frame — separate from construction-development rules.

### REIT Unit-Holder Structure & Sponsor Constraints
When analyzing commercial landlords structured as REITs, you are analyzing **unit-holders**, not shareholders. There is no "promoter"; instead there is a "Sponsor". Under SEBI REIT Regulations 2014 as amended in 2023, the sponsor must hold a minimum of 15% of total units for the first 3 years post-listing, and thereafter a **perpetual, graded** minimum unitholding for the life of the REIT (the 2023 amendment replaced the clean 3-year lock-in expiry with an ongoing requirement — roughly ≥5% of units / ₹1,000 Cr whichever lower, stepping down over ~20 years). The vehicle must maintain a minimum 25% public float, capping total sponsor holdings at 75%. Track sponsor divestment tranches meticulously using `shareholder_detail`, but note that a sponsor can no longer fully exit — there is no single post-lock-in "expiry cliff" after which sponsor units flood the market. Units are taxed differently from equity — distribution-heavy yield profile changes the MF/pension-fund holder base.

### JV / SPV Opacity & Listed Subsidiary Checks
Listed RE companies rarely execute large land parcels at 100% equity. Joint Development Agreements (JDAs), joint ventures, and partly-owned SPVs are the sector norm. The listed company reports a consolidated share, but minority interest is highly material. Cross-check `filings` for related-party SPV structures, RERA project filings, and the exact economic interest of the listed entity vs JV partners/PE investors. If the developer operates via listed subsidiaries or affiliate SPVs, mandate a Sum-of-the-Parts check via `get_valuation(section='sotp')`.

### DII Breakthrough & Pre-Sales Recognition Lag
Pre-sales figures lead reported revenue by **2-4 years**, not quarters: under Ind AS 115 most developers recognise revenue at point-in-time (possession/completion), so a booking made today is recognised only when the project is handed over years later. Consequently, institutional flow timing precedes reported earnings by a long lag. Watch for the **DII Breakthrough Signal**: historically, LIC and large domestic mutual fund houses under-own real estate due to sector governance concerns. A sudden breakthrough where MF holding crosses >5-8% (via `mf_changes`) often signals massive consensus re-rating, but conversely frequently serves as a cycle-top signal in the Indian RE market.

### Mandatory Checklist
1. [ ] **Identify RE Archetype**: Residential Developer / REIT / Conglomerate sub / Affordable / Flexspace
2. [ ] **Pledge vs NDU Check**: `promoter_pledge` — distinguish between project-collateral NDU vs margin-backed pledge
3. [ ] **QIP-to-Launch Correlation**: `corporate_actions` last QIP date, cross-check against land-bank/launch additions
4. [ ] **REIT Sponsor Holding Status**: If REIT, verify the initial 3-year 15% lock-in AND the post-2023 perpetual graded minimum — there is no full-exit "expiry cliff"; for SM-REITs apply the 2024 sponsor unitholding rule (5% if scheme is unleveraged / 15% if leveraged)
5. [ ] **SPV True Economic Interest**: Extract related-party JV structures from `filings`
6. [ ] **DII Cycle Signal**: `mf_changes` momentum against historical sector averages — flag potential cycle-top if MF breakthrough
7. [ ] **FDI 3-year lock-in status** for any direct foreign equity investments in project SPVs

### Open Questions
- Is the current promoter pledge acting purely as construction finance collateral, or does it represent holding-company distress?
- Did the last QIP successfully convert into pre-sales velocity within 12-18 months, or is the land bank sitting idle?
- For REITs: is the Sponsor approaching a mandatory lock-in expiry that could result in a severe unit-supply overhang?
- Are DIIs suddenly accumulating the stock aggressively, and does this historically correlate with a cycle peak for this specific developer?
- How much of the pipeline value is trapped in non-wholly-owned SPVs vs 100% owned subsidiaries?

### Public Bucket Sub-Breakdown — Real-Estate Context
The Public-shareholder-bucket sub-breakdown (Retail / HNI / Corporate / Others split) matters structurally more for listed real-estate names than for most sectors: Indian homebuyers frequently become retail shareholders of the developer whose project they occupy, so the Retail folio count and Retail % of public is a meaningful sentiment-and-brand tell distinct from pure institutional flow. Until Phase 3 D4 (`shareholding_public_breakdown` table) lands, retrieve retail folio count and public-bucket splits via the Tenet 8 canonical search — pull quarterly shareholding-pattern filings through `get_company_context(section='filings', query='shareholding pattern|public shareholders|folio')` and extract the Public-category sub-table. Peer instances where the retail-folio tell is most active: GODREJPROP, DLF, OBEROIRLTY, MACROTECH (Lodha), SOBHA, PRESTIGE.
