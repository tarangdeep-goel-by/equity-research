## FMCG — Ownership Agent

### FMCG Archetype Matrix
| Subtype | Structural Marker | Ownership Characteristics |
| :--- | :--- | :--- |
| **MNC India Subsidiary (Personal Care / Food)** | Foreign parent 50-75% | Parent-driven governance; 70-90% dividend payout; royalty-to-revenue ratio dictates margin extraction. e.g., HUL / Unilever 61%, NESTLE INDIA / Nestle SA 63%, COLGATE PALMOLIVE / parent ~51%, P&G HYGIENE / P&G, GILLETTE INDIA |
| **Indian-Family-Promoter FMCG** | Multi-gen family 40-60% | Stable boards; near-zero promoter pledge; high DII + FII consensus. e.g., DABUR / Burman family, MARICO / Harsh Mariwala, EMAMI / Agarwal family, GODREJ CP / Godrej family, JYOTHY LABS |
| **Conglomerate FMCG Arm** | Diversified parentage | Often professionally managed or cross-held. Parent allocation dynamics vary. e.g., ITC (tobacco-led, 0% promoter), RELIANCE RETAIL (unlisted sub), GODREJ CP (part of Godrej Group) |
| **New-Age D2C FMCG** | Founder-led, VC-backed | High post-IPO lock-up expiry volatility; cap-table overlap with platform sector. e.g., MAMAEARTH / HONASA, NYKAA, GO FASHION, MANYAVAR / VEDANT FASHIONS |
| **Spirits / Alcobev** | Regulated state-excise overlay | Mix of MNC sub and family control; regulatory risk premium prices into ownership. e.g., UNITED SPIRITS / Diageo 55%, UNITED BREWERIES / Heineken, RADICO KHAITAN |
| **Packaged Foods / Tea / Coffee** | Conglomerate sub or MNC | Supply-chain integration dictates structure; steady institutional hold. e.g., TATA CONSUMER PRODUCTS / Tata Group, NESTLE INDIA |
| **Tobacco** | 0% Promoter / FII-heavy | High dividend yield; persistent tax-headwind rotation; legacy foreign hold. e.g., ITC, Godfrey Phillips, VST Industries |

### MNC Subsidiary Governance & Royalty Repatriation
Foreign promoters (50-75%) manage Indian subsidiaries for margin extraction via structural transfers. Track royalty-to-revenue trajectory via `filings`. **Under SEBI LODR Regulation 23, brand-royalty payments exceeding 5% of consolidated turnover are material related-party transactions requiring "majority of minority" shareholder approval.** Periodic AGM votes to raise royalty caps are direct negative catalysts for minority shareholder value. High dividend payouts (70-90%) are the primary profit-repatriation mechanism, setting a 2-3% yield floor that stabilizes FII ownership during volume downcycles.

### Indian-Family Promoters & The Zero-Pledge Baseline
In multi-gen Indian FMCG (e.g., DABUR, MARICO, EMAMI), the structural baseline for promoter pledge is strictly 0%. The cash-generative nature of FMCG negates the need for operating leverage via share pledging. Any non-zero pledge detected via `get_ownership(section='promoter_pledge')` signals severe group-level distress (capital diverted to real estate or infra ventures) — not an FMCG operational issue. Institutional conviction (`mf_changes` + `mf_conviction`) is anchored to stable, professionally transitioned boards and low promoter encumbrance. Dividend yields are structurally lower (0.5-1.5%) as families prioritize reinvestment / brand acquisitions.

### Professionally Managed Conglomerates & Tobacco Complex
Tobacco-led conglomerates (e.g., ITC) often feature 0% promoter structure, classifying them as "professionally managed." Ownership is heavily institutionalized, with DII anchors (LIC often 16%+) providing downside support against FII rotation. Legacy foreign linkages (e.g., BAT UK holding 25-29% via Tobacco Manufacturers India) create complex beneficial ownership traces and overhang risk if block trades are initiated to monetize stakes. High dividend yields (4-5%) function as equity-bond proxies. Use `concall_insights` to track management commentary on capital allocation to non-FMCG segments (hotels, agri), which historically drives institutional conglomerate discounts.

### Alcobev State-Excise & Broad FDI Regulations
FDI in standard FMCG is permitted at 100% under the automatic route. **However, tobacco manufacturing faces strict FDI prohibition**, capping legacy foreign holdings and preventing new foreign strategic entries. Spirits / Alcobev operate under extreme state-by-state excise dependencies. MNC parents (e.g., Diageo in United Spirits) inject governance premiums but face constant state-level policy risk. Ownership structures reflect this regulatory-risk premium. Single-brand retail FDI rules apply if FMCG entities forward-integrate into proprietary retail.

### New-Age D2C Exits & Index Passive Flows
VC-backed D2C brands map directly to platform-sector mechanics (apply `platform/ownership.md` rules). Pre-IPO cap tables dominated by private equity guarantee high float-expansion volatility post lock-up expiries. Across FMCG subtypes, Nifty FMCG index inclusion drives massive passive flows. Evaluate `corporate_actions` for buyback mechanisms: tender offers allow selective promoter participation + specific tax treatment; open-market buybacks are used to support floor prices during volume-growth deceleration without altering promoter-holding %.

### Mandatory Checklist
- [ ] Execute `shareholder_detail` to map promoter subtype (MNC sub / Family / Conglomerate / VC-backed)
- [ ] Query `filings` for SEBI LODR Reg 23 related-party transactions — especially brand-royalty cap increases
- [ ] Validate `promoter_pledge` at 0%; flag any deviation as group-level capital misallocation risk
- [ ] Run `mf_changes` + `mf_conviction` vs D2C lock-up expiries or rural-slowdown narratives
- [ ] For 0%-promoter tobacco / conglomerates, trace legacy foreign-parent holdings and block-deal overhang risk
- [ ] Check `corporate_actions` for special dividends or buybacks (tender vs open-market)
- [ ] For conglomerates: use `sotp` to identify if FMCG cash flows subsidize unlisted or capital-heavy listed subs

### Open Questions
- Is the MNC parent attempting to squeeze minority yields by pushing royalty-to-revenue caps toward the 5% SEBI LODR threshold?
- In family-promoter setups, is there any hidden pledge or promoter-entity debt signaling external capital stress?
- How are FIIs rotating between 4-5% yield tobacco conglomerates and 2-3% yield MNC personal-care subs in response to tax-regime shifts?
- For D2C FMCG, how much of the pre-IPO VC cap table remains locked, and can institutional volume absorb the impending float expansion?
- Are state-level excise shocks in Alcobev forcing MNC parents to reassess their Indian-subsidiary capitalization structures?
