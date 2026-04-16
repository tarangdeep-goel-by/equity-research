## BFSI — Business Agent

### Sub-type Archetype — Identify Business Model Before Analysis
BFSI is an umbrella label hiding at least seven economically distinct business models. The revenue engine, moat shape, unit of production, and cyclical sensitivity differ so sharply across sub-types that applying a "bank framework" to an AMC (or a "fee franchise" lens to a PSU lender) inverts the diagnosis. State the sub-type and its primary revenue engine before decomposing growth.

| Subtype | Primary revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **PSU bank** | NII = NIM × Average Earning Assets | lending spread | per-branch / per-employee advances |
| **Private bank** | NII + fee income on liability franchise | spread + fee | per-customer ARPU, per-branch CASA |
| **Small finance bank (SFB)** | High-NIM lending to thin-file retail + PSL-heavy book | NIM × asset-quality | NIM 7-10%, credit cost 150-250 bps, PSL compliance |
| **Housing finance (HFC)** | Low-NIM long-tenor mortgages + limited fee income | mortgage spread + collections | NIM 2.5-4%, credit cost 20-60 bps, LTV distribution |
| **Life insurer** | NBP (first-year premium) + VNB = APE × VNB margin; renewal premium scales with persistency | float + persistency | NBP growth, VNB per policy, 13/61-month persistency |
| **General insurer** | Underwriting result + float income on reserves | combined ratio + float | combined ratio, loss ratio by line |
| **NBFC (lending)** | NIM × AUM + fee on disbursal | spread + leverage | disbursals per branch, AUM per FTE |
| **AMC** | Management fee = AUM × fee yield | AUM × blended yield bps | fee yield bps, AUM per employee |
| **Broker (discount)** | Cash-segment (ADTV × bps take-rate × days) + F&O (number of orders × flat fee per order) | order volume × monetisation mix | orders per active client, revenue per active client |
| **Exchange** | Transaction fee + listing + technology revenue; take-rate on cash-segment ADTV, per-contract on F&O | volume × take-rate (cash) / per-contract (F&O) | contracts per day, active-UCC growth |

### Revenue Decomposition — Always (A × B), Never a Single Line
For lenders, `NII = NIM × Average Earning Assets`; growth decomposes into volume (advances growth), price (NIM shift), and mix (retail/corporate re-pricing at different yields). For AMCs, `Fee revenue = AUM × blended fee yield bps`; AUM growth alone is misleading if the mix shift is toward passive/debt (lower bps). For discount brokers, split the economics: cash-segment `Revenue_cash = ADTV_cash × bps take-rate × days` behaves like an exchange line, but F&O `Revenue_fo = number of orders × flat fee per order` (₹15-25 per order for top discount brokers) — take-rate on F&O notional ADTV is analytically meaningless because options notional dwarfs cash-market notional while the fee is per-order. Traditional full-service brokers still charge bps on F&O turnover; state which model applies before decomposing. For insurers, split **first-year premium (NBP) = number of policies × ticket size** from **renewal premium = prior-book policies × ticket size × persistency rate** — persistency only drives the renewal leg, not NBP. VNB layering sits on top of NBP. Call `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')` for the decomposition.

### Moat Typology — Distinct by Sub-type
A bank moat is not an AMC moat is not a broker moat. Enumerate the moat lens that applies to this sub-type before asserting "durable franchise":
- **Liability franchise (banks)** — CASA ratio 35-45% is the current range for top private banks (post-2023 deposit squeeze compressed the earlier 40-55% regime; HDFC-Ltd merger rebase and system-wide bulk-deposit reliance reset the band). Large PSUs run 30-42%; wholesale-funded NBFCs typically <25%. A bank holding CASA above peer in a squeeze is the moat evidence, not hitting any absolute threshold. Cheap deposits compound through rate cycles. Source via `get_quality_scores(section='bfsi')` and `get_company_context(section='concall_insights', sub_section='management_commentary')`.
- **Distribution (banks, insurers)** — branch network density in Tier-3/Tier-4 towns, bancassurance tie-ups, agent strength. A large agent book for a life insurer is near-impossible to replicate de novo.
- **Pricing power via regulatory moat** — banking licence scarcity (RBI has not issued universal licences at scale since 2014-15); domestic systemically-important-bank (D-SIB) designation locks in a too-big-to-fail premium.
- **Capital adequacy headroom** — a bank with CRAR 17-18% vs peer 13-14% can accelerate lending into a credit cycle without dilution; that is a real moat even if not labelled as one.
- **Scale economics (AMCs, exchanges)** — AMC cost per AUM unit drops materially past ₹3-4 Lakh Cr AUM; exchange marginal cost per trade approaches zero, so the #1 in ADTV compounds share. Source AUM / ADTV trajectory via `get_peer_sector(section='peer_metrics')`.

### Unit Economics — Sub-type-Appropriate Unit
Aggregate P&L hides the story. For retail-heavy private banks, the relevant unit is **per-customer ARPU and cost-to-serve** — rising digital adoption should show cost-to-serve falling 8-12% YoY while ARPU holds or expands. For PSU lenders and rural-heavy private banks, **per-branch profitability** — advances per branch, CASA per branch, PBT per branch — is the correct lens. For AMCs, **blended fee yield bps on AUM** (typically 40-70 bps across equity/debt/passive mix) reveals whether asset mix is degrading. For brokers, **revenue per active client per year** (₹1,500-8,000 range depending on model) and **client activation rate** track franchise vitality better than headline client count. Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; if unavailable, flag as attempted.

### Capital-Cycle Position — Earnings Are Cycle-Sensitive
Bank earnings are not steady-state; they breathe with the credit cycle. In a credit-cost-tailwind phase (legacy NPAs resolving, provisions falling), reported ROE can temporarily overshoot through-cycle ROE by 200-400 bps — extrapolating that forward is the most common buy-side mistake. In a late-cycle phase, strong headline ROE and thin credit cost are often peak signals. Insurance P&L is rate-cycle and regulation-sensitive — falling bond yields compress investment yield on float; regulatory repricing of surrender charges or commission caps can reshape VNB margins within a quarter. Broker P&L is market-cycle sensitive — a 40-50% drop in F&O ADTV from peak vaporizes incremental revenue in one quarter. Always state the cycle phase (early / mid / late / stressed) before forecasting.

### Sector-Specific Red Flags for Business Quality
Business-quality stress shows up earlier than financial-quality stress. Scan for:
- **CASA erosion in a rate-rising cycle** — if deposit growth is being bought via term-deposit rate hikes while CASA share falls 150-300 bps, the liability franchise is weakening even as reported NIM holds.
- **Rapid unsecured growth late-cycle** — consumer NBFCs and banks growing unsecured personal-loan / credit-card books >40% YoY when the rest of retail is growing 15-20% are adversely selecting; slippages typically show up 4-6 quarters later.
- **Combined ratio sustained >110-115%** for general insurers signals structural underwriting stress. Note that most top Indian general insurers routinely operate at combined ratio 102-108% because mandatory motor third-party and competitive group-health pricing keep underwriting marginally loss-making; the ROE comes from float income on investments. The genuine red flag is 110%+ sustained or a multi-year drift above sub-sector median, not 100% itself.
- **Broker over-reliance on F&O** — a broker where >75% of revenue comes from F&O contract notes without a deep cash-segment or advisory book is one SEBI circular away from a revenue reset.
- **AMC mix-shift toward passive/debt** — blended fee yield dropping 5-8 bps over 2-3 years while AUM grows indicates franchise dilution even on a growing-AUM headline.
- **Insurance persistency decay** — 13-month persistency falling below 80% or 61-month below 55% means the VNB being reported today is built on policies that will not pay premiums in the out-years.

### Data-shape Fallback for Unit Economics
If `get_fundamentals(section='revenue_segments')` returns an aggregate-only view and `get_company_context(section='sector_kpis')` reports `status='schema_valid_but_unavailable'` for per-branch or per-customer KPIs, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and `sub_section='operational_metrics')` and scan the earnings-call transcript for disclosed per-branch advances, per-customer ARPU, blended fee yield, or active-client counts. Cite the quarter. If the narrative too is silent, add to Open Questions tied to the specific unit.

### Open Questions — BFSI Business-Specific
- "What is the current blended fee yield (bps on AUM) and how has it trended over the last 8 quarters, given the passive-share mix shift?" (AMCs)
- "What is the 13-month and 61-month persistency trajectory, and is it diverging from peer median?" (life insurers)
- "What share of incremental advances growth is coming from unsecured personal loans and credit cards, and what is the vintage-wise delinquency on the FY24-25 origination?" (retail-heavy banks and NBFCs)
- "Is the combined ratio sub-108% sustainable if investment yield compresses 50-80 bps on a 10Y G-sec rally (Indian general insurers run 102-108% as baseline; 110%+ is the structural red flag)?" (general insurers)
- "What is the cash-segment vs F&O contract-note revenue split, and how exposed is the top-line to a SEBI lot-size or margin-rule tightening?" (brokers)
