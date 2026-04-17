## Private Bank — Sector Agent

This file inherits the full BFSI sector framing (see `bfsi/sector.md` when merged — PR #20) on the macro-context anchor (repo, system credit, CD gap, 10Y G-sec), the three-cycle framework (credit, asset-quality, NIM), competitive hierarchy, institutional-flow patterns, structural shifts, and sector KPIs with percentile-relative framing. Do not duplicate generic BFSI content. This file sharpens the private-bank cohort specifics: D-SIB hierarchy, wealth-integrated-bank subset, post-HDFC-merger absorption regime, post-2023-risk-weight regime, FII-active vs passive dominance, and UPI / digital-fee disintermediation.

### Macro Context — Private-Bank-Specific Anchor
Pull the current regime via `get_market_context(section='macro')` and anchor private-bank reports to these variables:

- **Repo rate trajectory** — current level, last 4 moves, RBI MPC stance. Rate cycle directly drives NIM direction via the EBLR-linked retail book (instant repricing) vs MCLR-linked corporate book (2-3 quarter lag). For the private-bank cohort with a typical 60-75% EBLR share on floating-rate retail, a falling-rate cycle compresses NIM within 1 quarter before term-deposit repricing catches up.
- **System credit growth YoY** — mid-teens (12-16%) is the normal range; >18% sustained is late-cycle (private banks typically grow 1.3-1.6× system). <10% is deleveraging-phase.
- **System credit-deposit gap sustained at 400-700 bps** — this band indicates liquidity stress; private banks with CASA franchise hold up better but bulk-deposit reliance rises sector-wide. Current regime (FY25) sits in this band.
- **10Y G-sec yield** — directly sets bank AFS MTM and the CoE anchor used in P/B-ROE valuation. Also drives the effective cost-of-funds for wholesale-deposit-heavy private-bank mid-caps.
- **Rupee stability and FII-flow sensitivity** — private banks carry 18-22% of Nifty weight; rupee depreciation typically coincides with FII-outflow phases that hit the top 5 private banks disproportionately (index weight × active-FII positioning).

### Private-Bank Cycle Position — Lead the PSU Cohort
The private-bank cohort typically leads the PSU cohort by 1-2 quarters in both re-leveraging and stress-building phases. Diagnose each of the three cycles (credit, asset-quality, NIM) separately, then state the aligned-vs-divergent setup:

- **Credit cycle** — private banks are often the first to re-accelerate advances growth out of a deleveraging phase (better capital adequacy, stronger liability franchise). Late-cycle unsecured buildout in private-bank books typically precedes PSU unsecured by 2-3 quarters.
- **Asset-quality cycle** — private banks disclose SMA buckets more consistently than PSU peers; SMA-2 uptick in the private-bank cohort is a leading signal for system-wide stress-building.
- **NIM cycle** — EBLR-heavy retail private banks (HDFCBANK, ICICIBANK, KOTAKBANK, IDFCFIRSTB) see NIM compression faster in a falling-rate cycle; wholesale-heavy mid-caps (AXISBANK legacy corporate, RBLBANK) lag. State the EBLR/MCLR mix before projecting NIM direction.

Contradictory-phase setups — e.g., re-leveraging credit cycle + stress-building asset-quality cycle — are the interesting private-bank investment setups; one forces ROE expansion while the other forces provision-cost absorption.

### Competitive Hierarchy — Tier the Private-Bank Cohort
Tier via `get_peer_sector(section='sector_overview')` and `section='peer_metrics'`:

- **D-SIB private banks**: HDFCBANK, ICICIBANK. RBI-designated systemically important; 0.20-0.60% additional CET1 buffer requirement; quasi-sovereign premium on funding spreads. Combined market cap 55-65% of the private-bank cohort.
- **Near-D-SIB large private banks**: AXISBANK, KOTAKBANK, INDUSINDBK. Not D-SIB-designated but scale approaches the line; P/B premium sits between D-SIB and mid-cap.
- **Mid-cap private bank tier**: IDFCFIRSTB (retail-unsecured-led transition), FEDERALBNK (NRI-remittance franchise), RBLBANK (cards + SME), BANDHANBNK (east-India MFI-to-universal transition), YESBANK (post-resolution recovery phase, structural reset). P/B 1.0-1.8× band; thinner fee-income ratios, higher NIM on niche books.
- **SFB graduated to universal** — some SFBs have graduated to universal-bank license over time via the RBI transition path; their valuation and risk-profile reset upward as they leave the SFB regulatory regime.
- **SFB-post-graduation cost/income friction** — SFBs that graduate to universal-bank licence typically carry a cost/income ratio 10-20 pp higher than legacy private banks in the first 3-4 quarters post-graduation, driven by branch-network expansion, core-banking / technology upgrade spend, and CRAR-buffer rebuild toward D-SIB-proximity norms. Mean-reversion to peer cost/income is a multi-year journey, not a 2-3-quarter catch-up; state the quarters-since-graduation when benchmarking a graduated-SFB's opex ratio against the broader private-bank tier.
- **Niche private banks (regional, community-origin)**: CSBBANK, CITYUNIONBANK (CUB), KARURBANK (Karur Vysya), DCBBANK, TMB (Tamilnad Mercantile). Single-state or single-community customer-base; P/B typically 0.8-1.5×.
- **Foreign-bank competitive ceiling on top-end corporate wallet** — foreign banks operating in India (Citi's retained-wholesale franchise post-consumer-business sale, StanChart, HSBC, DBS) hold structural advantages in large-corporate FX, trade-finance, offshore-financing, and multinational-subsidiary relationships that Indian private banks cannot fully compete for — parent-network booking capacity, cross-border treasury integration, and multinational-group-level relationship continuity sit outside Indian-bank reach. This caps the upper-end corporate wallet-share Indian privates (even HDFCBANK, ICICIBANK, AXISBANK wholesale arms) can capture in those specific sub-segments; the domestic-corporate and mid-corporate segment remains contestable.

State which tier the subject bank sits in before comparing multiples — comparing IDFCFIRSTB multiples against HDFCBANK multiples is a tier-mismatch error.

### Wealth-Integrated Bank Subset
KOTAKBANK sits in a distinct sub-category — a large private bank with an integrated wealth-management arm (AMC, life insurance, general insurance, broking, investment-banking). The fee-income-to-total-income ratio runs 10-20 pp higher than peers at similar standalone-banking scale, and SOTP value is often 25-40% of consolidated market cap. Apply wealth-integrated framing: subsidiary revenue-growth is a distinct revenue engine from standalone-banking NIM × advances, and cycle-sensitivity differs (AMC fee income is market-cycle-sensitive; insurance VNB is persistency and rate-cycle-sensitive).

HDFCBANK, ICICIBANK, AXISBANK all have listed subsidiaries but the wealth-integrated classification applies most strongly to KOTAKBANK given the tightness of cross-sell integration and the fee-income share; state explicitly when applying.

### Institutional-Flow Patterns — Private-Bank-Specific
Private banks carry 18-22% of Nifty weight; specific flow mechanics:

- **FII active + passive dominance** — foreign active funds drive premium-name valuation multiples; passive FIIs and ETF creations flow disproportionately into top-5 private banks around index rebalance windows (MSCI quarterly, FTSE semi-annual).
- **FII aggregate close to 74% cap** — most top private banks sit 65-74% aggregate foreign holding (FPI + FDI + ADR/GDR + NRI). When aggregate >70%, passive-ETF rebalance demand is already largely absorbed; incremental foreign flow depends on active-manager decisions rather than index flow.
- **DII structurally overweight** — proliferation of banking-sector MFs and natural asset-allocation tilt. DII share in large private banks typically runs 18-28%; SBI MF is largest individual holder across most names.
- **LIC 4-9% anchor across the top-5** — quasi-sovereign floor; incremental moves of >100 bps YoY are structural-absorption signals, not tactical.
- **ADR / GDR flows** — HDFCBANK and ICICIBANK run ADR programmes on NYSE (1 ADR = 3 underlying India shares). ADR flow dynamics differ from direct FPI — Rule 144A vs Reg-S tranche distinction matters for liquidity analysis.
- **Passive-ETF rebalance flows dominate short-term price action** — index weight changes, MSCI EM inclusion/exclusion decisions, and FTSE rebalances drive 5-15% short-term re-ratings in large private banks even without fundamental change.

Cross-check sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping private-bank economics over 3-5 years:

- **HDFC-Ltd merger absorption** (ongoing, FY24-FY27) — HDFCBANK-specific 4-6 year absorption cycle. NIM compression, CASA-ratio reset, legacy-borrowings re-pricing to deposit-funded structure. Sector-read: rebalances the #1 and #2 private-bank relative positioning as ICICIBANK catches up during the HDFCBANK absorption drag.
- **Unsecured-lending risk-weight regime** (post-November 2023) — structural ROE reset of 80-150 bps for unsecured-heavy private banks. Forward-ROE trajectory depends on re-pricing, book-mix-shift, or capital-raise response. Sector consolidation in unsecured-retail origination is likely as smaller private banks with thinner capital buffers exit.
- **UPI / digital disintermediation of fee income** — UPI compressed payment-interchange fee-pool to near-zero for peer-to-peer and peer-to-merchant sub-₹2000 transactions. Offsetting, bank wealth-management and loan-origination fee-pool is growing. Net impact on private-bank fee-income share is flat-to-slightly-positive depending on wealth-franchise depth.
- **Co-lending with NBFCs** — since 2020 RBI circular, private banks provide balance-sheet funding while NBFCs originate and service. Changes the ROA / ROE per party — bank ROA compresses 20-40 bps on the co-lending share while NBFC ROA rises. Track co-lending share of incremental advances for private banks.
- **Neo-bank BaaS co-creation — distinct ROA driver vs bancassurance** — Banking-as-a-Service co-creation partnerships with consumer-facing fintechs (FEDERALBNK + Jupiter, RBLBANK + multiple neo-bank front-ends) are a structurally different P&L line from traditional bancassurance cross-sell. The bank provides the regulated deposit/savings/loan manufacturing rail while the neo-bank fronts API-led customer acquisition and UI — economics split as bank earning NIM on the deposit and small per-account servicing fee, with the neo-bank taking the customer-acquisition and UX margin. Distinct from bancassurance because the manufacturing-origination split is inverted (bank manufactures, partner originates; in bancassurance the bank originates and an in-group subsidiary manufactures). Under-appreciated as a distinct P&L line in sell-side coverage because disclosure is clustered under "digital partnerships" without ROA / per-account-fee segmentation; probe specifically in concall Q&A for partner-channel economics.
- **ECL accounting transition** (IndAS 109) — implementation timeline remains in transition for bank balance sheets. Changes timing of provisioning and reported ROE trajectory; sector-wide harmonisation still in progress.
- **LCR / NSFR tightening cycles** — RBI periodically recalibrates liquidity-coverage norms. Each recalibration drives bulk-deposit re-pricing across the sector; private banks with strong CASA franchise absorb these cycles better.

Name the structural shift and tie it to the specific bank sub-segment that benefits or is challenged; generic "digital transformation" framing is noise without that tie.

### Sector KPIs for Comparison — Always Cite Percentile
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the bank's percentile rank within the private-bank tier (not cross-tier). Private-bank-relevant KPIs:

- **NIM %** — 3.0-4.5% range for the cohort; HDFCBANK post-merger 3.4-3.7%, ICICIBANK 4.3-4.7%, KOTAKBANK 4.9-5.2% (pre-merger-adjustment), AXISBANK 3.9-4.2%.
- **CASA %** — 35-45% is the current premier-tier range (down from the pre-2023 40-55% band). HDFCBANK post-merger ~38%, ICICIBANK 41-43%, KOTAKBANK 42-45%, AXISBANK 41-43%. Mid-caps typically 30-40%.
- **Cost/Income %** — 38-48% for large private banks; 48-58% for mid-caps in their investment phase.
- **GNPA %** — 1.0-3.0% for large private banks; 1.8-4.0% for mid-caps.
- **NNPA %** — 0.3-0.8% for HDFCBANK/ICICIBANK/KOTAKBANK; 0.5-1.5% for the rest.
- **PCR %** — 70-90% is the healthy band; below 60% is under-provisioned.
- **CAR / CRAR %** — 16-20% for large private banks; mid-caps 13-17%.
- **ROE %** — 14-20% for the cohort steady-state.
- **ROA %** — 1.2-1.8% for large private banks; 0.8-1.4% for mid-caps.
- **CD ratio %** — 80-95% typical; above 100% indicates bulk-deposit reliance or borrowings-dependence.
- **Fee-income ratio %** — 15-30% range; >25% signals deep cross-sell moat.
- **Digital-transaction ratio %** — 85-95% for the premier tier; below 80% indicates under-investment in digital rails.

A number quoted without percentile (e.g., "ROE of 14%") omits whether that is top-quartile, median, or bottom-quartile for the private-bank tier; the re-rating thesis depends on the percentile.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set or `section='benchmarks'` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for index-weight context and `get_market_context(section='macro')` for top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked.

### Open Questions — Private-Bank Sector-Specific
- "Where is the private-bank cohort in the credit, asset-quality, and NIM cycles, and is the subject bank leading or lagging the cohort?"
- "What is the EBLR / MCLR split on the floating-rate book, and what is the expected NIM trajectory over the next 2-4 quarters given the current repo-rate stance?"
- "For the HDFC-merger absorption: how many quarters into the absorption phase is HDFCBANK, and is the NIM / CASA trajectory tracking management guidance?"
- "What is the passive-ETF-flow share vs active-FII-flow share in the private-bank cohort over the last 4 quarters, and where is the aggregate foreign holding vs the 74% cap?"
- "For structural shifts (co-lending mix, unsecured-retail re-pricing, UPI take-rate): what share of incremental growth is from the new channel vs legacy origination?"
