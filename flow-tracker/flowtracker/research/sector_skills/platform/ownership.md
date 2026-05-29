## Platform / New-Age Tech — Ownership Agent

### Platform Archetypes — Ownership Baseline
**Before analyzing shareholding patterns, identify the specific tech subtype to establish the baseline for promoter holding, regulatory overlap, and typical investor profile.**

| Subtype | Promoter Baseline | Key Ownership Fingerprint |
|---|---|---|
| **Quick commerce / Food delivery** | **0% common.** Classified as "professionally managed" / widely held. | Dominated by pre-IPO VCs, FPIs, and retail. High ESOP pool float. |
| **Insurtech / Fintech distribution** | **0% to low founder stake.** Subject to strict financial regulator scrutiny. | BFSI overlap, but FDI is liberal here: **insurance intermediaries (brokers/web-aggregators) allow 100% FDI under the automatic route**, and as of the May 2026 NDI amendment 100% FDI on the automatic route now applies to insurance companies too (LIC capped at 20%). Don't assume a restrictive FDI/FPI ceiling — verify the specific entity type. Founders often hold ESOPs rather than promoter equity. |
| **E-commerce / Beauty** | **High retention (30-50%+).** Traditional promoter classifications are common. | Strong founder control. Post-IPO sell-downs are closely watched for loss of conviction. |
| **Gaming / Digital Media / Logistics Tech** | **Mixed (0% to 20%).** Often heavily diluted by multiple funding rounds. | High presence of strategic corporate investors, PE buyouts, or sovereign wealth funds. |
| **New-age Broker / Wealthtech** | **Moderate to High.** Regulatory requirement for identifiable promoters. | Overlap with financial services limits. Unlisted parent entities often hold the promoter stake. |

### "Professionally Managed" Status & SR Shares
Many platforms list as "professionally managed" companies with **0% promoter holding** under SEBI ICDR regulations. This alters disclosure requirements, governance norms, and voting-power classifications. Do not flag a 0% promoter stake as a "founder exit" without checking the prospectus. Conversely, SEBI permits tech companies to issue **Dual-Class / Superior Voting Rights (SR) shares** to founders, allowing them to retain control with a minority economic interest. Always check `shareholder_detail` for SR share classifications.

### Pre-IPO VC Unlock Schedules & Supply Overhang
Lock-up expiries are major price-action events for newly listed platforms. Under current SEBI ICDR regulations, track three distinct supply waves:
- **Anchor Investors (staggered 30 / 90 days):** Anchor lock-in is split — 50% of the anchor allotment unlocks at 30 days, the remaining 50% at 90 days (SEBI ICDR, for issues opening on/after 1 Apr 2022). The day-31 partial unlock is the first liquidity event; track which anchors exit vs hold at each tranche.
- **Non-Promoter Pre-IPO Shares (6 months):** Excess (non-minimum-promoter-contribution) pre-IPO shares held by non-promoters — VCs, PEs, ESOP trusts — lock in for 6 months. Often triggers massive block deals.
- **Minimum Promoter Contribution (18 months) / excess promoter shares (6 months):** Promoter MPC (the 20%-of-post-issue mandatory lock) is locked 18 months (reduced from 3 years for issues opening on/after 1 Apr 2022); promoter holding above MPC is locked only 6 months. New-age platforms are frequently "professionally managed" with 0% promoter, in which case no MPC overhang exists — verify the prospectus before assuming a promoter lock-up wave.

Always quantify the exact percentage of the float unlocking and use `get_events_actions(section='corporate_actions')` and `get_company_context(section='filings')` to map specific expiry dates.

### The Pre-IPO Investor Roster
Tech platforms share a highly concentrated roster of pre-IPO cap-table sponsors. Recognize the typical names in `shareholder_detail` as VCs/PEs looking for specific exit windows, not permanent capital: global growth-stage tech VCs, India-focused early-stage VC funds, diversified internet holdcos taking strategic stakes, large global PE firms, and sovereign wealth funds active in Indian tech. Their block-deal exits are standard fund-lifecycle events, not necessarily fundamental red flags — treat a pre-IPO VC block exit as normal capital rotation unless it coincides with a thesis-breaking event.

### Press Note 3 & the "FDI Stays FDI" Downstream Rule
The new-age platform cap-table is heavy with foreign pre-IPO sponsors; two FEMA/FDI rules shape the exit and structure analysis:
- **Press Note 3 (2020) — border-country friction.** Any investment, direct or indirect, originating from a country sharing a land border with India (China is the practical case), or where a beneficial owner is a citizen of such a country, needs prior government approval. Legacy Chinese-VC stakes on platform cap-tables therefore face real exit/transfer friction (approvals, secondary-sale constraints) — flag a legacy border-country sponsor as PN3-restricted, not as ordinary FPI float, and treat its overhang as harder-to-clear.
- **Once foreign-owned, downstream stays FDI (FOCC rule).** Under the NDI Rules, an Indian entity that is foreign-owned-or-controlled is itself a foreign investor for its downstream investments, and a pre-IPO foreign sponsor's economic interest counts as foreign investment for sectoral-cap purposes — it does not automatically "become domestic" merely because the holder sells down below 10% or because the company lists. When checking sectoral FDI-cap headroom (relevant for payments/insurtech/e-commerce sub-types), compute foreign ownership on the FOCC basis, and do not assume a foreign sponsor's sell-down converts the residual stake to domestic for compliance math.

### ESOP Trusts & Dilution Cycles
ESOPs are a critical compensation tool in new-age tech.
- **Shareholder details:** ESOP trusts are explicitly listed in `get_ownership(section='shareholder_detail')`. Treat this as captive float.
- **Dilution Overhang:** Track the creation of fresh ESOP pools at AGMs (typically 2-6% equity dilution every 1-3 years). Use `get_company_context(section='filings')` to identify resolutions expanding the ESOP pool. At scale, this dilution meaningfully impacts EPS.

### Holding Company & Parent Cross-Holdings
Founders often structure their holdings via unlisted parent entities. The listed company may just be a subsidiary, with an unlisted founder-controlled holdco above it. The founder's true economic interest and voting control sit at the unlisted parent level, which distorts the reported "promoter" stake of the listed entity. Always trace ultimate beneficial ownership if a corporate body is listed as the largest shareholder.

### QIP Usage for Growth Capital
Unlike asset-heavy legacy sectors where Qualified Institutions Placements (QIPs) often signal balance sheet distress or debt refinancing, new-age platforms frequently use QIPs for growth capital, M&A war chests, or scaling unit economics. Do not automatically penalize equity raises; evaluate the stated end-use in `get_company_context(section='filings')`.

### Open-Market Block Selling — Supply-Overhang Reading
When a large pre-IPO holder exits via open-market trades rather than via block deals (i.e., `bulk_block` data is empty during a 5-10pp FII drop), this creates **persistent intraday supply** on the order book — not a clean one-time transfer of ownership. Open-market VC exits are a **negative technical signal** at least for the weeks/months of sell-down, even when the FII→MF handoff dynamic is ultimately bullish medium-term. Do not narrate "no block deals = healthy absorption" without verifying.

### Mutual Fund Scheme Segregation
When evaluating domestic institutional accumulation, do not look solely at aggregate AMC numbers. You must segregate equity, debt, and hybrid scheme buying. Use `get_ownership(section='mf_conviction')` and `get_ownership(section='mf_changes')` to confirm if the AMC is taking a directional equity bet or merely parking passive/arbitrage funds. Always call `mf_changes` alongside `mf_holdings` — a conviction thesis without the velocity signal is incomplete.

### Mandatory Checklist
- [ ] Pull `get_ownership(section='shareholder_detail')` to map the cap table (0% promoter vs founder-led, SR shares present?)
- [ ] Identify and segregate the Pre-IPO VC roster (global growth-stage funds, India-focused VCs, sovereign wealth funds)
- [ ] Use `get_events_actions(section='corporate_actions')` + `filings` to map 30-day, 6-month, and 12-month lock-up expiry dates
- [ ] Run `get_ownership(section='promoter_pledge')` — even if widely held, check if founders have pledged their residual non-promoter holdings
- [ ] Check `filings` for fresh ESOP pool creations and calculate the % dilution
- [ ] Execute `mf_changes` + `mf_conviction` to strip out passive/debt scheme noise from domestic buying
- [ ] If large FII exit is observed, verify `bulk_block` data — if empty, flag as open-market supply overhang (negative technical signal)
- [ ] If an unlisted parent exists, state it explicitly — reported promoter % does not reflect founder's true economic interest

### Open Questions
- Is a massive block deal / open-market exit by a marquee pre-IPO VC a fund-life-expiry event, or a judgment on the platform's terminal value?
- Have founders structured their compensation to rely heavily on new ESOP grants, functionally acting as promoters while avoiding regulatory promoter classification?
- How aggressively is the company expanding its ESOP pool relative to its path to operating profitability?
- For companies with an unlisted parent holdco, what is the founder's aggregate economic stake across listed + unlisted entities, and how does the parent's own capital structure affect the listed entity's governance?

### Historical-MCAP Discipline — Platform Worked Pattern
New-age platforms that have listed since the 2021-22 IPO wave (the cohort is now ~3-5 years / 40-60+ months listed — e.g. Zomato/Eternal, Paytm and Nykaa all listed in 2021) compound two distortions simultaneously: (a) massive post-IPO mcap expansion or compression (3-10x re-rating is routine for category leaders; some names also de-rated sharply post-listing), and (b) business-model transitions (1P → 3P, ad-tier monetisation, insurance reframes) that reset revenue denominators mid-cycle. Converting a historical FII %pt change using the *current* mcap is a flow-overstatement error the agent makes reflexively; this is the `HISTORICAL_MCAP_MISMATCH` warning path. Every historical %pt → ₹Cr conversion must pass `inputs_as_of` and `mcap_as_of` to `calculate()` to pin both inputs to the same historical quarter.

**Correct call signature** (converting a ~2023-Q4 FII %pt change into ₹Cr using the mcap from that quarter):
```
calculate(operation='pct_of', a='6.26', b='historical_mcap_cr', inputs_as_of='2023-Q4', mcap_as_of='2023-Q4')
```

**Wrong call signature** (fires the `HISTORICAL_MCAP_MISMATCH` warning because the %pt is historical but the mcap defaults to current):
```
calculate(operation='pct_of', a='6.26', b='current_mcap_cr')
```

*Pattern applies to*: ETERNAL (Zomato, post-IPO mcap >5x + 1P→3P transition), PayTM (listing-price-to-current discounted; cross-rerating after payments-bank carve-out), Nykaa (post-IPO mcap compression then partial re-rating), Policybazaar / PB Fintech (pre-insurance-reframe framing), GROWW — any recently-listed platform (the 2021-22 IPO cohort onward) where the mcap has moved >3x since the FII-entry dates being analyzed. *Skip the discipline* only when the %pt window is fully within the current fiscal year and the mcap has not moved >15% over that span.
