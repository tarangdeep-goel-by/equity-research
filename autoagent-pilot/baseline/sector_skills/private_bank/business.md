## Private Bank — Business Agent

This file inherits the full BFSI business framing (see `bfsi/business.md` when merged — PR #20) on sub-type archetype, A×B revenue decomposition, moat typology, unit economics, capital-cycle position, and business-quality red flags. Do not duplicate BFSI generic content. The private-bank sharpening below calibrates archetype contrasts, fee-moat depth, HDFC-merger transition state, and unsecured-retail cycle positioning for the large Indian private-bank cohort.

### Sub-type Archetype — Private Bank Is Not Monolithic
Private-bank sub-archetype drives the revenue engine before any metric is compared. State which of these three the company is before decomposing growth:

- **Large universal private bank, retail-wholesale balanced** — HDFCBANK, ICICIBANK, AXISBANK. Diversified book (35-55% retail, 25-35% wholesale/corporate, 10-20% SME), deep liability franchise, fee income 20-30% of total income, D-SIB designation or near-D-SIB scale.
- **Mid-cap private bank with niche or geography focus** — FEDERALBNK (Kerala-rooted NRI-remittance franchise), CITYUNIONBANK (South India SME-heavy), KARURBANK (TN-rooted SME), RBLBANK (cards + SME focus), IDFCFIRSTB (retail-unsecured-led transition, post-IDFC Bank merger), BANDHANBNK (east-India MFI-to-universal transition), CSBBANK (Kerala-rooted mid-cap). Higher NIM, thinner fee ratio, concentration risk on geography or product line.
- **Large wealth-integrated private bank** — KOTAKBANK. Banking book alongside AMC, life insurance, general insurance, broking, investment-banking arm. Cross-sell engine is the moat; SOTP value is often 25-40% of standalone bank value.

Each archetype has a distinct revenue-engine mix. The large universal bank lives on NIM × advances + fee income; the mid-cap niche bank lives on NIM × targeted-segment advances; the wealth-integrated bank earns a material share of group PAT from fee-yielding subsidiaries and the bank standalone understates the franchise value.

### Revenue Decomposition — Always A × B
Private-bank revenue splits into NII and non-interest income — decompose each separately, never narrate an aggregate.

- **Net Interest Income** = `NIM × Average Earning Assets`. Growth breakdown:
  - Volume: YoY advances growth split into retail / corporate / SME / unsecured components via `get_fundamentals(section='revenue_segments')` or `get_company_context(section='concall_insights', sub_section='operational_metrics')`.
  - Price: NIM direction decomposed into yield-on-advances (moves with repo + EBLR/MCLR mix + pricing power) minus cost-of-deposits (moves with CASA share + bulk-deposit reliance).
  - Mix: shift between high-yield retail unsecured (personal loans, credit cards at 14-18% yield) and low-yield corporate term-loans (7-9% yield) drives blended yield without NIM moving on the surface. Flag when retail unsecured share of incremental advances rises >40% QoQ — the NIM uptick is coming from mix, not pricing power.
- **Non-interest income** = `transaction count × fee per transaction + forex spreads + distribution commissions + wealth-management fees`. Separate from treasury MTM gains which are rate-cycle-driven and non-recurring. Fee-income ratio >20% signals a deep cross-sell or distribution franchise; <15% signals a NIM-dependent structurally lower-quality earnings mix.

### Moat Typology — Four Private-Bank-Specific Lenses
Beyond the generic BFSI moat lens, private-bank moat strength hinges on four dimensions:

- **Liability franchise — CASA 35-45% is the current premier-tier range** (calibration from BFSI lessons — the pre-2023 40-55% regime compressed post-HDFC-Ltd-merger absorption and system-wide bulk-deposit reliance). Holding CASA at 42-46% while peers sit at 36-40% through a rate-rising cycle is the moat evidence, not hitting any absolute threshold. Source current CASA via `get_company_context(section='concall_insights', sub_section='operational_metrics')`.
- **Distribution density and digital dual-rail** — branch network + digital-transaction share. A private bank with 5,000+ branches deep into Tier-3/Tier-4 towns AND 90%+ of transactions running through digital rails (UPI, app, NetBanking) earns the lowest cost-to-serve in the cohort. Digital transactions as a share of total is the under-cited operational KPI.
- **Scale / D-SIB premium** — RBI's Domestic Systemically Important Bank designation (currently HDFCBANK, ICICIBANK + SBI) carries a quasi-sovereign premium on funding spreads and a 0.20-0.60% additional CET1 buffer requirement. The too-big-to-fail-premium is real and shows in wholesale-deposit rate differentials of 15-30 bps vs non-D-SIB private peers.
- **Underwriting discipline** — structurally low GNPA / NNPA across a full credit cycle (peak and trough) is a harder-to-replicate moat than any single-quarter pristine metric. HDFCBANK and KOTAKBANK pre-merger ran NNPA <0.5% through multiple cycles; that persistence across cycles IS the moat.

### Unit Economics — Retail-Heavy vs Wholesale-Balanced Unit
Aggregate P&L hides the franchise shape. For retail-heavy private banks (KOTAKBANK, IDFCFIRSTB, BANDHANBNK), the unit is **per-customer ARPU** — cross-sell depth measured by products-per-customer (2.0-3.5 range for premier private banks), fee-income-to-customer ratio, and wallet-share of customer. Rising digital adoption should compress cost-to-serve 8-12% YoY while ARPU holds.

For wholesale-balanced banks (HDFCBANK, ICICIBANK, AXISBANK), **per-branch profitability** still matters for the retail franchise leg, but corporate segment economics run on **per-relationship-manager advances and fee book** — a corporate RM typically manages ₹800-2,500 Cr of advances plus the ancillary fee-income arc (forex, trade finance, debt capital markets referral).

Fee-income-to-total-income at >20% is the strong-moat band for private banks. Digital-transaction ratio (digital transactions ÷ total transactions) trending to 90%+ indicates the cost structure has reset lower. Extract operational metrics via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; if unavailable, fall back to `sub_section='management_commentary'` and scan for disclosed ARPU / cross-sell / digital-ratio figures, citing the quarter.

### Capital-Cycle Position — Three-Cycle Read Plus HDFC-Merger Transition
Apply the BFSI three-cycle framework (credit, asset-quality, NIM) to diagnose where the private-bank cohort sits — private banks typically lead the PSU cohort by 1-2 quarters in the re-leveraging and stress-building phases. State the phase explicitly before forecasting.

The private-bank-specific fourth cycle to diagnose for **HDFCBANK** only: the **HDFC-Ltd-merger absorption cycle** (effective FY23-Q4). The merged entity is 4-6 years into absorbing the legacy HDFC Ltd mortgage book into the deposit-funded structure. During absorption:
- NIM is structurally compressed 30-60 bps vs the pre-merger standalone HDFCBANK level (legacy HDFC Ltd borrowings carry higher cost than bank deposits; absorption of that book drags NIM until borrowings mature and are replaced with deposits).
- CASA ratio stepped down materially from pre-merger highs as the denominator (deposits) expanded with the merger while CASA deposits did not jump pari passu.
- Advances-growth capacity was moderated for 4-6 quarters as CRAR buffer was rebuilt.

State the absorption-phase quarter-count when diagnosing HDFCBANK NIM and CASA trajectory — "NIM compression vs 5Y trend" is misleading without this context because the 5Y trend is pre-merger.

### Sector-Specific Red Flags for Business Quality
Private-bank business-quality stress surfaces early through these tell-tales:

- **CASA erosion 50-100 bps per year without a matching deposit-rate-cycle tailwind** — the liability franchise is weakening even as reported NIM holds. If this is occurring in a rate-rising cycle, the bank is losing low-cost deposits to term-deposit competitors and will face NIM compression 2-3 quarters out.
- **Rapid unsecured retail growth >40% YoY late-cycle** — personal loans, credit cards, consumer-durable finance. RBI's November 2023 risk-weight increase on unsecured retail (to 125% from 100%) made this a structural ROE headwind; banks still growing unsecured aggressively are either adversely selecting the pool or pricing in a way that won't survive the next credit cycle.
- **RBI-specific regulatory actions** — macro-prudential circulars on unsecured lending, AIF-exposure restrictions, or any bank-specific supervisory letter. The 2023-24 RBI action pattern on Kotak's digital onboarding ban and the 2024 action on embargoed new digital customer acquisition illustrate that regulatory-risk crystallises via specific-bank supervisory action, not just general circular.
- **KMP departures at CXO level** — CFO, CRO, Head-of-Retail transitions in a stress quarter are informational; clustered departures (2+ C-suite exits in 6 months) are forensic.
- **Auditor rotation mid-cycle** — statutory-auditor change in a quarter where asset-quality numbers are under watch is a governance tell; cross-check against `get_events_actions(section='material_events')`.

### Open Questions — Private-Bank Business-Specific
- "What share of incremental advances growth over the last 4 quarters came from unsecured retail (PL + CC + consumer-durable), and what is the vintage-wise delinquency on the FY24-25 origination?"
- "For HDFCBANK specifically: where is the merger absorption in terms of legacy-borrowings re-pricing to deposit-funded structure, and what is the forward-trajectory of the blended cost of funds?"
- "What is the cross-sell depth (products per customer) and digital-transaction ratio, and how has it trended over the last 8 quarters?"
- "What share of fee income is from in-group product distribution (insurance, AMC) vs standalone transaction and advisory fees, and is that mix vulnerable to regulatory repricing?"
- "Has the bank faced any RBI supervisory letter, embargo on new customer acquisition, or macro-prudential circular application in the last 4 quarters?"
