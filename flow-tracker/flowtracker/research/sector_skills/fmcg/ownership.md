## FMCG — Ownership Agent

### FMCG Archetype Matrix
| Subtype | Structural Marker | Ownership Characteristics |
| :--- | :--- | :--- |
| **MNC India Subsidiary (Personal Care / Food)** | Foreign parent 50-75% | Parent-driven governance; 70-90% dividend payout; royalty-to-revenue ratio dictates margin extraction. |
| **Indian-Family-Promoter FMCG** | Multi-gen family 40-60% | Stable boards; near-zero promoter pledge; high DII + FII consensus. |
| **Conglomerate FMCG Arm** | Diversified parentage | Often professionally managed or cross-held. Parent allocation dynamics vary. Includes tobacco-led diffused-promoter structures and unlisted retail subsidiaries of large diversified groups. |
| **New-Age D2C FMCG** | Founder-led, VC-backed | High post-IPO lock-up expiry volatility; cap-table overlap with platform sector. |
| **Spirits / Alcobev** | Regulated state-excise overlay | Mix of MNC sub and family control; regulatory risk premium prices into ownership. |
| **Packaged Foods / Tea / Coffee** | Conglomerate sub or MNC | Supply-chain integration dictates structure; steady institutional hold. |
| **Tobacco** | 0% Promoter / FII-heavy | High dividend yield; persistent tax-headwind rotation; legacy foreign hold. |

### MNC Subsidiary Governance & Royalty Repatriation
Foreign promoters (50-75%) manage Indian subsidiaries for margin extraction via structural transfers. Track royalty-to-revenue trajectory via `filings`. **Under SEBI LODR Regulation 23, brand-royalty payments exceeding 5% of consolidated turnover are material related-party transactions requiring "majority of minority" shareholder approval.** Periodic AGM votes to raise royalty caps are direct negative catalysts for minority shareholder value. High dividend payouts (70-90%) are the primary profit-repatriation mechanism, setting a 2-3% yield floor that stabilizes FII ownership during volume downcycles.

**Proxy advisory & institutional voting are the real enforcement mechanism on royalty/brand-fee RPTs.** Because the foreign parent is a related party, it cannot vote on its own royalty resolution under SEBI LODR Reg 23 — the outcome is decided by minority "majority of minority." Proxy advisers (IiAS, SES, InGovern) issue AGAINST/FOR recommendations on these resolutions and institutional dissent has *defeated* royalty hikes (most visibly Nestle India's FY24 EGM, where minorities rejected the staggered royalty increase toward 5.25%). Always pull the AGM/EGM voting results: **institutional dissent >20% against** a royalty/brand-usage/technical-fee resolution is a strong governance signal even when the resolution passes, and an outright defeat is a positive minority-value catalyst. Track upcoming RPT resolutions in notices/agenda as forward catalysts, and read proxy-adviser reports for the rationale. Source via `get_company_context(section='filings')` (postal-ballot / AGM outcomes) and `get_events_actions(section='material_events')`.

### Indian-Family Promoters & The Zero-Pledge Baseline
In multi-gen Indian family-promoter FMCG, the structural baseline for promoter pledge is near-zero — the cash-generative nature of FMCG negates the need for operating leverage via share pledging. "Strictly 0%" is the norm but not universal: notable names carry persistent non-zero pledges (e.g. Emami's promoter group has run pledges in the ~9-16% range, tied to group real-estate/infra ventures rather than the FMCG operations). Any non-zero pledge detected via `get_ownership(section='promoter_pledge')` should be read as a group-level capital-allocation / distress signal (capital diverted to real estate or infra ventures) rather than an FMCG operational issue — quantify the level and trend rather than treating any pledge as automatically disqualifying. Institutional conviction (`mf_changes` + `mf_conviction`) is anchored to stable, professionally transitioned boards and low promoter encumbrance. Dividend yields are structurally lower (0.5-1.5%) as families prioritize reinvestment / brand acquisitions.

### Professionally Managed Conglomerates & Tobacco Complex
Tobacco-led diversified conglomerates often feature 0% promoter structure, classifying them as "professionally managed." Ownership is heavily institutionalized, with DII anchors (LIC commonly 15%+) providing downside support against FII rotation. Legacy foreign-parent linkages (historically large strategic stakes held via intermediary vehicles) create complex beneficial ownership traces and overhang risk if block trades are initiated to monetize stakes. High dividend yields (4-5%) function as equity-bond proxies. Use `concall_insights` to track management commentary on capital allocation to non-FMCG segments (hotels, agri, paperboards), which historically drives institutional conglomerate discounts.

### Alcobev State-Excise & Broad FDI Regulations
FDI in standard FMCG is permitted at 100% under the automatic route. **However, tobacco manufacturing faces strict FDI prohibition**, capping legacy foreign holdings and preventing new foreign strategic entries. Spirits / Alcobev operate under extreme state-by-state excise dependencies. MNC parents in Indian spirits subsidiaries inject governance premiums but face constant state-level policy risk. Ownership structures reflect this regulatory-risk premium. Single-brand retail FDI rules apply if FMCG entities forward-integrate into proprietary retail.

### New-Age D2C Exits & Index Passive Flows
VC-backed D2C brands map directly to platform-sector mechanics (apply `platform/ownership.md` rules). Pre-IPO cap tables dominated by private equity guarantee high float-expansion volatility post lock-up expiries. Across FMCG subtypes, Nifty FMCG index inclusion drives massive passive flows. Evaluate `corporate_actions` for buyback mechanisms: tender offers allow selective promoter participation + specific tax treatment. Note that SEBI phased out the stock-exchange open-market buyback route entirely from 1 April 2025 (limit cut 15%→10%→5%→nil over FY23-25), so virtually all post-April-2025 FMCG buybacks are tender offers (SEBI floated a 2026 consultation on reintroducing an open-market book-built route, but treat tender as the default until notified). Since Oct-2024 buyback proceeds are taxed as dividend in the recipient's hands, which also reshapes promoter/MNC-parent incentives to buy back vs pay special dividends.

### Mandatory Checklist
- [ ] Execute `shareholder_detail` to map promoter subtype (MNC sub / Family / Conglomerate / VC-backed)
- [ ] Query `filings` for SEBI LODR Reg 23 related-party transactions — especially brand-royalty cap increases
- [ ] Pull the most recent AGM/EGM/postal-ballot voting results on any royalty / brand-usage / technical-fee resolution; record institutional % against (flag if >20%) and check proxy-adviser (IiAS/SES/InGovern) recommendations
- [ ] Validate `promoter_pledge` at 0%; flag any deviation as group-level capital misallocation risk
- [ ] Run `mf_changes` + `mf_conviction` vs D2C lock-up expiries or rural-slowdown narratives
- [ ] For 0%-promoter tobacco / conglomerates, trace legacy foreign-parent holdings and block-deal overhang risk
- [ ] Check `corporate_actions` for special dividends or buybacks (tender vs open-market)
- [ ] For conglomerates: use `sotp` to identify if FMCG cash flows subsidize unlisted or capital-heavy listed subs

### Open Questions
- Is the MNC parent attempting to squeeze minority yields by pushing royalty-to-revenue caps toward the 5% SEBI LODR threshold?
- On the last royalty / brand-fee RPT resolution, what was the institutional dissent (% votes against), what did proxy advisers recommend, and did it pass or get defeated by minority shareholders?
- In family-promoter setups, is there any hidden pledge or promoter-entity debt signaling external capital stress?
- How are FIIs rotating between 4-5% yield tobacco conglomerates and 2-3% yield MNC personal-care subs in response to tax-regime shifts?
- For D2C FMCG, how much of the pre-IPO VC cap table remains locked, and can institutional volume absorb the impending float expansion?
- Are state-level excise shocks in Alcobev forcing MNC parents to reassess their Indian-subsidiary capitalization structures?

### MNC-Subsidiary Insider Transaction Framing
**MNC-subsidiary archetype:** For HINDUNILVR (Unilever ~61.9%), NESTLEIND (Nestle parent ~62%), COLPAL (Colgate parent 51.0% — note this is barely above the 50% control floor, not >60% like the others), GILLETTE (P&G parent ~75%), insider SALES are ESOP-routine and tax-clearance-driven — NOT informational. Track insider BUYING instead for signal (which is almost non-existent in MNC-sub structures — when it happens, pay attention). Also track parent-share transactions at the holding company level (Unilever PLC transactions in Dutch/UK filings) for dividend / buyback policy shifts that feed through to Indian sub dividend policy.

### `mf_holdings` Drill Discipline — MNC-Subsidiary FMCG with >60% Promoter
For any MNC-subsidiary FMCG with a narrow promoter-free-float — promoter ≥50% (HINDUNILVR ~62%, NESTLEIND ~62%, GILLETTE ~75%, PROCTER ~70%, and COLPAL at 51.0% where the float is wider but the MF base is still concentrated), the free-float institutional landscape is DENSELY CONCENTRATED in a handful of large passive / blended funds — typically SBI MF, HDFC MF, ICICI Pru MF, UTI MF, Nippon India MF. The TOC summary and `mf_conviction` aggregate can read as "stable" and "conviction flat" even when the TOP 3 FUNDS TOGETHER hold ~35-45% of the MF float — because the aggregate MF % and scheme-count metrics don't surface concentration. A single fund-house reallocation (e.g., SBI MF trimming 40bps of the Mar-quarter) produces a larger absolute-₹Cr move than the aggregate MF % change suggests.

**Rule:** for any MNC-subsidiary FMCG with promoter ≥50% (narrow free-float), `get_ownership(section='mf_holdings')` is MANDATORY regardless of whether the TOC `mf_conviction` summary looks benign. The top-30 scheme view surfaces the concentration; the summary hides it. Apply the rule BEFORE writing Section 4 (Mutual Fund Conviction). *Peer instances*: HINDUNILVR, NESTLEIND, COLPAL, GILLETTE, PROCTER — the MNC-subsidiary structural trait (narrow promoter-free-float → concentrated MF base) is what makes this FMCG-specific rather than a generic MF-drill rule.
