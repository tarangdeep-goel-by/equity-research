## Platform / New-Age Tech — Ownership Agent

### Platform Archetypes — Ownership Baseline
**Before analyzing shareholding patterns, identify the specific tech subtype to establish the baseline for promoter holding, regulatory overlap, and typical investor profile.**

| Subtype | Promoter Baseline | Key Ownership Fingerprint |
|---|---|---|
| **Quick commerce / Food delivery** (e.g., ETERNAL (Zomato), Swiggy) | **0% common.** Classified as "professionally managed" / widely held. | Dominated by pre-IPO VCs, FPIs, and retail. High ESOP pool float. |
| **Insurtech / Fintech distribution** (e.g., PB Fintech/POLICYBZR, PAYTM/One97, FINO Payments) | **0% to low founder stake.** Subject to strict financial regulator scrutiny. | BFSI sector overlap restricts FDI/FPI ceilings. Founders often hold ESOPs rather than promoter equity. |
| **E-commerce / Beauty** (e.g., NYKAA/FSN E-Commerce, Mamaearth/Honasa) | **High retention (30-50%+).** Traditional promoter classifications are common. | Strong founder control. Post-IPO sell-downs are closely watched for loss of conviction. |
| **Gaming / Digital Media / Logistics Tech** (e.g., NAZARA, DELHIVERY, Zaggle) | **Mixed (0% to 20%).** Often heavily diluted by multiple funding rounds. | High presence of strategic corporate investors, PE buyouts, or sovereign wealth funds. |
| **New-age Broker / Wealthtech** (e.g., GROWW/Billionbrains, Angel One) | **Moderate to High.** Regulatory requirement for identifiable promoters. | Overlap with financial services limits. Unlisted parent entities often hold the promoter stake. |

### "Professionally Managed" Status & SR Shares
Many platforms list as "professionally managed" companies with **0% promoter holding** under SEBI ICDR regulations. This alters disclosure requirements, governance norms, and voting-power classifications. Do not flag a 0% promoter stake as a "founder exit" without checking the prospectus. Conversely, SEBI permits tech companies to issue **Dual-Class / Superior Voting Rights (SR) shares** to founders, allowing them to retain control with a minority economic interest. Always check `shareholder_detail` for SR share classifications.

### Pre-IPO VC Unlock Schedules & Supply Overhang
Lock-up expiries are major price-action events for newly listed platforms. Under current SEBI ICDR regulations, track three distinct supply waves:
- **Anchor Investors (30 days):** The first liquidity event post-listing. Track which anchors exit on day-31 vs hold.
- **Pre-IPO Investors (6 months):** Unlocks for eligible non-promoter pre-IPO shareholders. Often triggers massive block deals.
- **Selling Shareholders / Promoters (12 to 18+ months):** The final major overhang.

Always quantify the exact percentage of the float unlocking and use `get_events_actions(section='corporate_actions')` and `get_company_context(section='filings')` to map specific expiry dates.

### The Pre-IPO Investor Roster
Tech platforms share a highly concentrated roster of pre-IPO cap-table sponsors. Recognize these names in `shareholder_detail` as VCs/PEs looking for specific exit windows, not permanent capital: SoftBank Vision Fund, Tiger Global, Sequoia Capital India / Peak XV, Accel, Info Edge (strategic), Elevation Capital, Lightspeed, Kalaari, Nexus, Matrix, Steadview, TPG, General Atlantic, GIC, Temasek, and Prosus. Their block-deal exits are standard fund-lifecycle events, not necessarily fundamental red flags — treat a pre-IPO VC block exit as normal capital rotation unless it coincides with a thesis-breaking event.

### ESOP Trusts & Dilution Cycles
ESOPs are a critical compensation tool in new-age tech.
- **Shareholder details:** ESOP trusts are explicitly listed in `get_ownership(section='shareholder_detail')`. Treat this as captive float.
- **Dilution Overhang:** Track the creation of fresh ESOP pools at AGMs (typically 2-6% equity dilution every 1-3 years). Use `get_company_context(section='filings')` to identify resolutions expanding the ESOP pool. At scale, this dilution meaningfully impacts EPS.

### Holding Company & Parent Cross-Holdings
Founders often structure their holdings via unlisted parent entities. The listed company may just be a subsidiary (e.g., OLAELEC having ANI Technologies as an unlisted parent). The founder's true economic interest and voting control sit at the unlisted parent level, which distorts the reported "promoter" stake of the listed entity. Always trace ultimate beneficial ownership if a corporate body is listed as the largest shareholder.

### QIP Usage for Growth Capital
Unlike asset-heavy legacy sectors where Qualified Institutions Placements (QIPs) often signal balance sheet distress or debt refinancing, new-age platforms frequently use QIPs for growth capital, M&A war chests, or scaling unit economics. Do not automatically penalize equity raises; evaluate the stated end-use in `get_company_context(section='filings')`.

### Open-Market Block Selling — Supply-Overhang Reading
When a large pre-IPO holder exits via open-market trades rather than via block deals (i.e., `bulk_block` data is empty during a 5-10pp FII drop), this creates **persistent intraday supply** on the order book — not a clean one-time transfer of ownership. Open-market VC exits are a **negative technical signal** at least for the weeks/months of sell-down, even when the FII→MF handoff dynamic is ultimately bullish medium-term. Do not narrate "no block deals = healthy absorption" without verifying.

### Mutual Fund Scheme Segregation
When evaluating domestic institutional accumulation, do not look solely at aggregate AMC numbers. You must segregate equity, debt, and hybrid scheme buying. Use `get_ownership(section='mf_conviction')` and `get_ownership(section='mf_changes')` to confirm if the AMC is taking a directional equity bet or merely parking passive/arbitrage funds. Always call `mf_changes` alongside `mf_holdings` — a conviction thesis without the velocity signal is incomplete.

### Mandatory Checklist
- [ ] Pull `get_ownership(section='shareholder_detail')` to map the cap table (0% promoter vs founder-led, SR shares present?)
- [ ] Identify and segregate the Pre-IPO VC roster (SoftBank, Peak XV, Tiger, etc.)
- [ ] Use `get_events_actions(section='corporate_actions')` + `filings` to map 30-day, 6-month, and 12-month lock-up expiry dates
- [ ] Run `get_ownership(section='promoter_pledge')` — even if widely held, check if founders have pledged their residual non-promoter holdings
- [ ] Check `filings` for fresh ESOP pool creations and calculate the % dilution
- [ ] Execute `mf_changes` + `mf_conviction` to strip out passive/debt scheme noise from domestic buying
- [ ] If large FII exit is observed, verify `bulk_block` data — if empty, flag as open-market supply overhang (negative technical signal)
- [ ] If an unlisted parent exists, state it explicitly — reported promoter % does not reflect founder's true economic interest

### Open Questions
- Is a massive block deal / open-market exit by a marquee VC (SoftBank, Tiger, Peak XV) a fund-life-expiry event, or a judgment on the platform's terminal value?
- Have founders structured their compensation to rely heavily on new ESOP grants, functionally acting as promoters while avoiding regulatory promoter classification?
- How aggressively is the company expanding its ESOP pool relative to its path to operating profitability?
- For companies with an unlisted parent (e.g., OLAELEC/ANI), what is the founder's aggregate economic stake across listed + unlisted entities, and how does the parent's own capital structure affect the listed entity's governance?
