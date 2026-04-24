## Broker — Sector Agent

### Macro Context — Participation, FII Flows, Policy Rates, Household Savings
Broker P&L is geared to four macro variables; no stock-level narrative is complete without anchoring to the sector-level regime. Pull from `get_market_context(section='macro')` and state these four anchors explicitly:

- **Retail participation rate** — total demat accounts as a share of household count. Crossed ~15-18% household penetration in 2024 from ~5% pre-2020; further growth is sub-linear as the already-onboarded cohort is the heavy-trading tail. The relevant direction is activation-rate on the existing base, not gross demat additions.
- **FII flow correlation with cash-segment ADTV** — cash-segment turnover closely tracks FII net-flow direction (foreign active mandates transact in cash rather than F&O). A sustained FII outflow quarter compresses cash-segment broker revenue independently of retail F&O trends.
- **Policy-rate cycle impact on MTF book spread** — falling repo cuts funding cost faster than client MTF rate, expanding spread 50-100bp in the transmission phase; rising repo compresses spread. The MTF revenue line is rate-cycle sensitive and should be modelled separately from the broking line.
- **Household savings into equity direction** — SIP flows (MF industry AUM trajectory), direct-equity flows (broker net client adds), and alternative-asset allocation. A deceleration in SIP gross flows is a leading indicator for wealth / PMS AUM-growth compression.

### Sector Cycle Position — Three Overlapping Cycles
Broker sector lives through three cycles that often diverge; diagnose each before declaring sector direction:

- **Retail-broker AUM cycle** — 2020-24 expansion phase (pandemic-era retail onboarding, demat accounts 4×, F&O participation peak), 2024+ regulatory-compression phase (SEBI lot-size / margin tightening reset F&O monetisation, activation rates normalising). The next 2-3 years are a post-regulatory-reset rebasing, not a continuation of the 2020-24 expansion.
- **F&O volume cycle** — peaked 2024 at roughly 6-7× cash-market notional; post-SEBI actions the volumes are rebasing to a structurally lower equilibrium. Calling the next F&O peak requires explicit conviction on retail-options re-engagement despite lot-size and margin changes.
- **Wealth / PMS AUM cycle** — correlates with equity-market level + HNI formation; drawdowns in equity indices of >15% historically compress PMS flows for 4-6 quarters before net-flows rebuild.

State which phase the sector is in for each cycle; a contradictory setup (e.g., retail-broker compression + wealth/PMS tailwind) is the interesting configuration.

### Competitive Hierarchy — Tier the Sector
Sector reports collapse when they treat "broker" as monolithic. Tier the sub-sectors via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:

- **Top-3 discount brokers by 12-month active clients** — ZERODHA (unlisted, largest active-client base), GROWW (listed, fastest-scaling digital-first), UPSTOX (unlisted, discount F&O tier), ANGELONE (listed, hybrid discount + MTF book). Active-client share is the revenue-franchise proxy, not gross demat.
- **Top-2 full-service brokers by revenue** — MOTILALOFS (advisory + wealth-heavy, strong DII-friendly franchise), ICICISEC (bank-owned captive + open-market hybrid, higher governance overhang). Full-service economics rest on research-bundled relationships, not per-order scale.
- **Bank-owned brokers** — HDFCSEC (captive on HDFC parent liability base), KOTAKSEC (captive on Kotak Mahindra parent), ICICIDIRECT (via ICICISEC structure). Monetisation depends on parent's cross-sell maturity and captive-base penetration.
- **Wealth / PMS specialists** — listed or listed-adjacent wealth franchises with high AUM-per-employee and low client count. Valuation anchors are P/AUM and fee yield rather than per-client PE.
- **Depositary-participant duopoly** — CDSL (listed, ~70% market share by accounts) and NSDL (unlisted until its IPO path executes). Utility-like economics, regulated tariffs, very different risk / return profile from broking.
- **5PAISA** — listed discount-broker cohort; used frequently as a peer comparable for the GROWW / ANGELONE cohort on activation-rate and ARPU benchmarking.

### Institutional-Flow Patterns — Broker Sub-Sector Specific
Broker stocks carry a small Nifty weight but punch above their weight as a retail-equity-participation theme proxy for FIIs and DIIs:

- **FII-sensitivity to retail-participation narrative** — FIIs treat listed brokers as a direct play on Indian retail-equity deepening; accumulation in ZERODHA-aggregators, ANGELONE, and GROWW frontruns or absorbs the retail-onboarding trajectory. FII flows can be stock-specific rather than sector-general.
- **DII exposure via financial-services MF baskets** — domestic mutual funds accumulate full-service and bank-owned brokers through sector-neutral financial-services allocation; pure-discount brokers are underweighted in DII books because earnings volatility doesn't fit MF benchmarking.
- **IPO / post-listing FII absorption** — recently-listed brokers (GROWW in the cohort, ANGELONE's post-listing arc) show classic 6-month and 12-month VC lock-up expiry supply waves; FII active absorption is the demand side of those windows.
- **VC-roster exit windows** — pre-IPO VC investors in new-age brokers typically exit via block deals in the 12-24 month post-listing window; tracking the VC-roster share via shareholder-detail is mandatory when modelling post-IPO institutional flow.

Cross-check sector flow via `get_market_context(section='fii_dii_flows')` and `section='fii_dii_streak')` before claiming sector-level institutional rotation. A single stock's FII % change in a sub-100-bps-weight sector is not a sector signal unless corroborated at the cohort level.

### Structural Shifts — Beyond the Cycle
Cyclical reads miss the slow-moving structural shifts reshaping broker economics over 3-5 years:

- **Discount-broker model maturity post-2024 SEBI actions** — the per-order flat-fee model that enabled F&O scale is now margin-constrained on volumes. Further growth requires either client-ARPU expansion (wealth, advisory, distribution) or margin-funding book scale-up. Pure-execution brokers face revenue-mix pressure.
- **Shift to advisory / wealth / PMS as monetisation engine** — all major Indian brokers are building advisory or wealth books to diversify off execution. This is a 3-5 year transition with significant investment cost before revenue scales.
- **Margin-funding book as a revenue diversifier** — ANGELONE, ICICISEC, and others have materially scaled MTF books; the interest-income line is becoming a distinct P&L component that is less cyclical than broking but introduces credit-risk management discipline.
- **Global brokers entering via FDI route** — FEMA NDI Rules permit 100% FDI in broking under automatic route for most tiers; global platforms (Robinhood-style, Interactive-Brokers-tier) entering the Indian retail market are a 5-10 year competitive risk but near-term not a base-case shift.
- **True-to-label and TER compression** — SEBI's disclosure enforcement compresses distribution-trail economics for brokers with heavy MF-distribution books; the structural impact is a 10-20% compression in distribution-fee yield over 2-3 years.
- **Direct-equity vs MF flow preference** — if direct-equity onboarding decelerates while SIP / MF flows accelerate, broker economics shift toward the distribution leg; if F&O re-accelerates despite SEBI tightening, execution leg remains dominant.

Name the structural shift and tie it to the specific sub-type that benefits or is challenged; generic "digital transformation" framing is noise without this tie.

### Sector KPIs for Comparison — Always Cite Percentile, Not Just Absolute
When benchmarking, pull from `get_peer_sector(section='benchmarks')` and state the company's percentile rank within the sub-sector, not only the absolute number. The sector-agent-relevant KPIs by sub-type:

- **Discount broker** — orders per day, 12-month active clients, CAC, ARPU, F&O vs cash split %, activation rate %, MTF book growth %, cost-to-income %.
- **Full-service broker** — Assets Under Advisory (AUA) growth, revenue per relationship manager, advisory-revenue share of total, cross-sell ratio, cost-to-income %.
- **Wealth / PMS** — AUM, net flows, client retention %, blended fee yield (1-2% band), performance-fee share of total.
- **Bank-owned broker** — captive-vs-open-market client share, cross-sell trail as % of total revenue, parent-bank liability-base penetration.
- **Depositary participant** — demat accounts (total + incremental), annual maintenance revenue, transaction-fee revenue mix, market share (CDSL vs NSDL split).

A number quoted without sector percentile (e.g., "ARPU of ₹3,500") omits whether that is top-quartile, median, or bottom-quartile; the re-rating thesis depends on the percentile, not the absolute.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 4 comparable names — common for listed Indian discount brokers given ZERODHA and UPSTOX are unlisted) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the index-weight context and `get_market_context(section='macro')` for the top-down cycle read. For discount-broker cross-sectionals, note that private-market names like ZERODHA and UPSTOX are the genuine active-client leaders; omitting them creates a distorted peer set. Explicitly state when the peer benchmark excludes unlisted leaders.

### Open Questions — Broker Sector-Specific
- "Where is the sector in the retail-broker AUM cycle, the F&O volume cycle, and the wealth / PMS AUM cycle, and are the three phases aligned or divergent?"
- "What is the current FII-flow trajectory, and is the broker-sector FII accumulation tracking cash-segment ADTV growth or running independently (indicating theme-buying ahead of fundamentals)?"
- "Are any SEBI draft circulars (weekly-expiry rationalisation, further margin tightening, TER-disclosure enforcement) currently in public consultation that would reshape sector economics for a named sub-type?"
- "For the structural shift to advisory / wealth / PMS as a monetisation engine: what share of incremental revenue is coming from the new leg vs legacy execution, and at what investment cost?"
- "How does the company's active-client count, ARPU, and activation rate rank in percentile terms against the 4-6 closest peer cohort (including unlisted where relevant, noting the benchmarking caveat)?"
