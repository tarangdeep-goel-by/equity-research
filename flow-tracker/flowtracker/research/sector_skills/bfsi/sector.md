## BFSI — Sector Agent

### Macro Context — Rates, Credit Growth, Liquidity Gap
BFSI is the most macro-sensitive sector in the index; no stock-level narrative is complete without anchoring to the macro regime. Pull the current regime from `get_market_context(section='macro')` and state these four variables explicitly:
- **Repo rate trajectory** — current level, last 4 moves, RBI MPC stance (accommodative / neutral / tight). Rate cycle position drives NIM direction for retail-heavy banks (+) and compresses life-insurer investment-book yields (−).
- **System credit growth YoY** — aggregate banking-system advances growth. Mid-teens (12-16%) is the normal range; >18% sustained is late-cycle, <10% is deleveraging.
- **System deposit growth and the credit-deposit gap** — the widening of credit growth over deposit growth is the single best liquidity-stress early-warning. A 400-700 bps positive gap sustained over 3-4 quarters forces bulk-deposit reliance and CoF pressure across the sector.
- **10Y G-sec yield level** — directly sets bank AFS book MTM and insurance investment-yield on float; also sets the CoE anchor used in P/B-ROE valuation.

### Sector Cycle Position
BFSI lives through three overlapping cycles — credit, asset-quality, and NIM. Diagnose each before declaring sector direction:
- **Credit cycle** — deleveraging phase (balance-sheets repair, growth tepid, valuations compressed), re-leveraging phase (growth accelerating, credit costs falling, ROE expanding), late-cycle phase (peak growth, thin credit costs, unsecured build-up), stress phase (slippages accelerating, provisioning spike).
- **Asset-quality cycle** — clean-up (AQR / resolution-plan phase, headline NPAs spike-then-normalise), normalisation (GNPA / NNPA ratios re-rating downward as legacy book resolves), stress-building (SMA-2 rising, fresh slippage uptick, usually 4-6 quarters before headline GNPA turn).
- **NIM cycle** — rising-rate cycle expands NIM for banks with repo-linked retail books (roughly 60-75% of floating advances); falling-rate cycle compresses NIM with a 2-3 quarter lag as loan re-pricing precedes deposit re-pricing.

State which phase the sector is in for each of the three cycles; contradictory phases (e.g., re-leveraging credit cycle + stress-building asset cycle) are the interesting setups.

### Competitive Hierarchy — Tier the Sector
Sector reports collapse when they treat BFSI as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:
- **Top-5 system-important (D-SIB-designated) banks** — by advances and deposits; these are the balance-sheets that RBI backstops and carry the systemic-premium in valuation.
- **Tier-2 private banks with differentiated liability franchise** — names with CASA 40%+ and digital-franchise lead; their P/B premium is defensible.
- **PSU bank consolidation state** — post-2019 amalgamations reduced PSU-bank count; consolidation round progress and remaining divestment pipeline are the policy variables.
- **NBFC tiers** — mortgage (HFC), vehicle finance, consumer, MFI, gold-loan, wholesale; each tier has distinct cost-of-funds, loss-given-default, and rate-cycle sensitivity profiles.
- **Insurance market share** — life insurer league by new-business APE; general insurer league by GDPI; health-insurance as a fast-growing sub-line.
- **AMC league** — by AUM share and by equity-AUM share (the high-fee-yield portion); the top-5 AMCs account for the majority of equity-AUM fees.

### Institutional-Flow Patterns — BFSI-Specific
BFSI carries a 35-40% weight in Nifty, which drives specific flow mechanics that the ownership and sector agents must both reflect:
- **Mechanical FII-ETF flows** hit BFSI first — index rebalances, EM fund inflows, and passive-ETF creations flow disproportionately into the top-5 private banks by index weight.
- **DII (MF + insurance) structurally overweight** given the proliferation of banking-sector funds and the natural asset-allocation tilt; DII share in large private banks commonly runs 18-28%.
- **PSU bank flows are LIC-anchored + sovereign-fund-dominated** — LIC's 7-12% structural holding in most PSU banks is quasi-sovereign floor capital; incremental flows are typically passive index or EPFO-like sovereign pools.
- **Private bank flows are FII-active-plus-passive dominated** — foreign active funds drive the premium names' valuation multiples; passive FIIs show up around index rebalance windows.

Cross-check the sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation. A single stock's FII % change is not a sector signal unless corroborated at the index-weight level.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping BFSI economics over 3-5 years:
- **UPI and digital-rails adoption** — compresses the transaction-fee pool across brokers, banks, and payment-bank sub-models; benefits the scale aggregators, compresses margins for thin-moat intermediaries.
- **Co-lending partnerships** between banks and NBFCs — shifts the underwriting-versus-funding split; NBFCs become origination engines, banks become balance-sheet providers. Changes RoA / RoE per party materially.
- **Digital Public Infrastructure (Account Aggregator, OCEN)** — reshapes underwriting economics by making data-led underwriting scalable; incumbent branch-franchise moats compress.
- **IndAS / ECL transition** — the IndAS 109 / ECL (Expected Credit Loss) accounting framework changes the timing of provisioning and the reported ROE trajectory; sector-wide harmonisation is still in progress.
- **LCR / NSFR tightening cycles** — every 3-5 years, RBI recalibrates liquidity-coverage norms; the recalibration drives bulk-deposit re-pricing across the sector.
- **Regulator-led repricing** — IRDAI's post-2023 expenses-of-management and commission-cap revisions reshaped life-insurance VNB margins industry-wide in a single fiscal.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "digital transformation" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. The sector-agent-relevant KPIs by sub-sector:
- **Banks** — NIM%, CASA%, Cost/Income%, GNPA%, NNPA%, CAR%, ROE%, ROA%, CD ratio%.
- **NBFCs** — NIM%, credit cost%, CRAR%, borrowings/equity, AUM growth%, stage-3 assets%.
- **AMCs** — AUM % share, equity-AUM share, blended fee yield bps, cost-to-income%, operating margin%.
- **Insurers (life)** — VNB margin%, APE growth%, 13/61-month persistency%, solvency ratio%.
- **Insurers (general)** — combined ratio%, loss ratio%, expense ratio%, GDPI growth%, solvency ratio%.
- **Exchanges / brokers** — take-rate bps, ADTV growth%, cost-to-income%, active-client growth%.

A number quoted without sector percentile (e.g., "ROE of 14%") omits whether that is top-quartile, median, or bottom-quartile; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 5 comparable names) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the index-weight context and `get_market_context(section='macro')` for the top-down cycle read. If both are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated sector view — explicitly label it as management-sourced rather than independently benchmarked.

### Open Questions — BFSI Sector-Specific
- "Where is the sector in the credit cycle, the asset-quality cycle, and the NIM cycle, and are the three phases aligned or divergent?"
- "What is the current system credit-deposit growth gap, and is bulk-deposit reliance rising across the sector?"
- "Are any RBI or IRDAI draft circulars in public consultation that would reprice fee income, commission caps, or liquidity ratios for this sub-type?"
- "What is the passive-ETF-driven FII flow share vs active FII flow share in the sector over the last 4 quarters?"
- "For structural shifts (UPI take-rate, co-lending mix, DPI adoption): what share of incremental growth is coming from the new channel vs legacy origination?"
