## Broker — Business Agent

### Sub-type Archetype — Identify the Revenue Engine Before Anything Else
"Broker" is a sector label covering five distinct business models with fundamentally different unit economics, moat shape, and cyclical exposure. Applying a discount-broker lens to a bank-subsidiary wealth franchise (or the reverse) inverts the entire investment diagnosis. Always state the sub-type and its primary revenue engine in the opening paragraph before decomposing growth.

| Subtype | Primary revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **Discount broker** (ZERODHA-style) | F&O order-flow: `Orders × flat fee (₹15-25/order)` + cash-segment `ADTV_cash × bps × days` | order volume × per-order monetisation | orders per day, active clients, CAC/ARPU |
| **Full-service broker** (MOTILALOFS, ICICISEC) | bps-on-turnover (cash + F&O tiers) + advisory / research subscription + distribution trail | AUA × yield + relationship monetisation | revenue per relationship manager, AUA growth |
| **Wealth / PMS** | `AUM × blended fee yield (1-2%)` + performance fee + TER-linked trail | AUM × fee yield | AUM per employee, net flows, client retention |
| **Bank-owned broker** (HDFCSEC, KOTAKSEC, ICICIDIRECT) | Captive cross-sell on parent's liability franchise + commission + MF distribution trail | parent-base penetration | per-customer cross-sell ratio, bundled revenue |
| **Depositary participant** (CDSL, NSDL) | Custody fee per demat account + annual maintenance + transaction fee | account count × flat fee | demat accounts, transaction throughput, duopoly share |

### Revenue Decomposition — Split Cash from F&O, Do Not Mix Yield Bases
The single most common modelling error for Indian discount brokers is applying a take-rate-on-notional framework to F&O revenue. Options notional dwarfs cash-market notional while the actual monetisation is per-order at a flat fee. The correct decomposition:

- **Discount broker F&O revenue** = `Number of Orders × Flat fee per order (₹15-25)` — notional turnover is analytically irrelevant for yield calculation. An ADTV-weighted take-rate produces a false-precision number because a single ₹10 Cr Nifty-option trade pays the same ₹20 as a single ₹1 L trade.
- **Discount broker cash-segment revenue** = `ADTV_cash × bps take-rate × trading days` — cash behaves like an exchange fee line and bps-on-turnover is the right frame here.
- **Full-service broker F&O revenue** = `F&O turnover × bps` on some tiers (advisory-backed, HNI books) and per-order on digital tiers — state which tier mix applies before modelling.
- **Distribution revenue** = MF AUM × trailing commission (10-100 bps per annum depending on scheme class and regulatory TER band) + insurance first-year + AIF/PMS trail.
- **Margin funding book (MTF) revenue** = book × lending spread (funding cost to client rate, typically 8-12% gross yield with 4-7% spread on own-net-worth funding).

Extract via `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')`. If the management reports "take-rate on turnover" as a headline for F&O, interrogate the denominator — notional-based yield for options has been migrating toward zero for five years and collapses the comparability of the number.

### Moat Typology — Distinct by Sub-type
Broker moats are not uniform; enumerate the lens that fits this sub-type before asserting franchise quality:

- **Customer acquisition cost advantage** — for digital discount brokers, CAC in the ₹300-800 band is the franchise tell. CAC trending up with activation-rate flat means the paid-acquisition market is saturating and incremental clients cost more to monetise.
- **Active-to-total conversion** — new demat accounts are a vanity metric; the active-client base (traded at least once in 12 months) is the revenue franchise. Activation rates of 30-50% are the sustainable range; <25% flags a zombie book.
- **Product breadth** — a pure F&O-execution broker is one SEBI circular away from a revenue reset. Advisory, PMS, wealth, margin-funding, distribution trail — each additional line diversifies the P&L and reshapes the monetisation tier on the same client.
- **Platform stickiness** — trader retention on technology quality (order-placement latency, charting, API access). Platform-driven brokers retain active clients through volume cycles where legacy franchises lose share.
- **Institutional relationships and research depth** — full-service brokers monetise HNI and FII execution through research-bundled relationships; bank-owned brokers monetise the captive liability base. These are labour-intensive moats but compound slowly and resist discount-broker price pressure.

### Unit Economics — Revenue per Active Client Is the Benchmark
Aggregate P&L hides the monetisation quality; the correct unit is **revenue per active client per year**. Typical range ₹1,500-8,000 across sub-types, with:

- **Discount broker** — ₹1,500-3,500 per active client (low ARPU, high activation discipline, scale-driven margin).
- **Full-service broker** — ₹5,000-15,000 per active client (higher ARPU, advisory bundled).
- **Wealth / PMS** — ₹30,000-1,50,000 per active relationship (very high ARPU, very low client count).
- **Bank-owned broker** — ₹2,000-6,000 per active retail client, amplified by cross-sell trail from parent bank.

F&O traders monetise 5-10× MF-only investors; the client-cohort mix matters as much as the headline count. Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; where disclosure is absent, flag rather than impute.

### Capital-Cycle Position — Market-Volume Sensitivity Is Acute
Broker P&L is directly geared to market-turnover cycles. F&O ADTV swings 40-60% peak-to-trough through a cycle; a 40-50% volume drop in a single quarter is historically documented (COVID shock, 2008 crash reference). Cash-segment ADTV is less volatile but still cyclical with retail participation.

The **2024-25 SEBI tightening regime** (F&O lot-size hike, weekly-expiry rationalisation, higher upfront-margin norms, true-to-label expense rule) is a structural step-down for F&O-heavy models — already compressed discount-broker F&O revenue by 20-30% in the first affected quarters. State the cycle phase (early / mid / late / stressed / regulatory-reset) before forecasting volume growth; extrapolating FY23-24 ADTV peak linearly is the most common forward-projection error.

### Sector-Specific Red Flags for Business Quality
- **F&O revenue concentration >75%** (discount) or >60% (full-service) — one SEBI circular away from a revenue reset. Cite the F&O-cash split from concall explicitly.
- **Activation rate <25%** — zombie client book, gross adds not translating into monetisable cohort.
- **ARPU compression YoY** without a margin-funding or advisory offset — monetisation quality degrading even as headline client count grows.
- **CAC rising with activation-rate flat** — paid-acquisition saturation.
- **Client-fund segregation stress** (SEBI audit observations, NSE-BSE penal notices) — governance red flag that reprices the stock 10-30% on disclosure.
- **Margin-funding book growth outpacing net worth and disclosed borrowings** — possible client-float misuse, cross-check against ring-fencing balance.

### Data-shape Fallback for Unit Economics
If `get_company_context(section='sector_kpis')` returns `status='schema_valid_but_unavailable'` for active-client count, ADTV, or ARPU, fall back in order to `get_company_context(section='concall_insights', sub_section='operational_metrics')` and `sub_section='management_commentary')` for management-disclosed quarter-end numbers. Cite the specific quarter. If the transcript too is silent, add the missing KPI to Open Questions tied to a named metric rather than a generic "more data needed".

### Open Questions — Broker Business-Specific
- "What is the current F&O vs cash-segment revenue split, and how much of the F&O revenue is per-order (discount model) versus bps-on-turnover (full-service model)?"
- "What is the 12-month active-client count and the activation rate on the total demat base, and how has the activation rate trended over the last 4 quarters?"
- "What is revenue per active client for the latest FY and the 3-year trajectory? Is it compressing, stable, or expanding, and what mix shift (distribution, MTF yield, advisory) explains the move?"
- "For bank-owned brokers: what share of revenue is captive cross-sell from the parent's liability base vs open-market acquisition, and is the captive share rising or falling?"
- "Given the 2024-25 SEBI F&O tightening, what is management's quantified view on the through-cycle ADTV normalization (70-80% of 2024 peak) and the corresponding F&O revenue run-rate?"
