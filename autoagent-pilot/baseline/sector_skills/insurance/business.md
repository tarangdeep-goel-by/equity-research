## Insurance — Business Agent

### Sub-type Archetype — Identify the Business Model Before Analysis
"Insurance" is an umbrella label covering at least five economically distinct business models. Revenue engine, moat, capital-cycle sensitivity, and the appropriate unit of production diverge sharply across sub-types; applying a life-insurer framework to a general insurer (or to an insurtech marketplace) inverts the diagnosis. State the sub-type and its primary revenue engine before decomposing growth.

| Subtype | Primary revenue engine | Dominant axis | Unit of production |
| :--- | :--- | :--- | :--- |
| **Life insurer** | NBP (first-year premium) + renewal premium × persistency; VNB = APE × VNB margin | product mix × persistency × float yield | APE growth, VNB per policy, 13/61-month persistency |
| **General insurer** | GDPI + investment income on reserves; underwriting result = (1 − combined ratio) × NEP | combined ratio × float yield | GDPI growth, segment-wise combined ratio, loss ratio by line |
| **Standalone health insurer** | Health GDPI + investment income; retail vs group mix-sensitive | loss ratio × retail share | retail health share %, claim frequency, claim severity |
| **Insurtech marketplace / aggregator** | Commissions earned = policies placed × avg commission; contribution margin scales with CAC efficiency | CAC × LTV × take-rate | CAC, LTV/CAC, contribution margin, active-buyer growth |
| **Reinsurer** | Treaty + facultative premium on cedant primary book; underwriting + float income | cycle pricing × cat loss frequency | treaty renewal pricing, cat-loss ratio |

### Revenue Decomposition — Always (A × B), Never a Single Line
For life insurers, split **NBP = number of policies × ticket size** from **renewal premium = prior-book policies × ticket size × persistency rate** — persistency only drives the renewal leg, not NBP. **VNB = APE × VNB margin** sits on top of NBP; APE growth without VNB-margin disclosure misses the profitability leg. For general insurers, **GDPI = number of policies × average premium**, with the claims side driven by **claims ratio = (gross claims − reinsurance recovery) / net earned premium** and the cost side driven by **expense ratio = (commissions + opex) / net written premium**. For insurtech marketplaces, **commission revenue = policies placed × avg commission**; decompose into **visits × conversion × avg ticket × take-rate**. Pull decomposition via `get_fundamentals(section='revenue_segments')` and `get_company_context(section='concall_insights', sub_section='operational_metrics')`.

### Moat Typology — Distinct by Sub-type
An insurer moat is not an insurtech moat is not a reinsurer moat. Enumerate the moat lens that applies before asserting "durable franchise":
- **Agent force (life insurers)** — a tied-agent book of 100k+ trained agents with multi-year vintage is near-impossible to replicate de novo; persistency and VNB margin both ride on agent quality.
- **Bancassurance tie-ups (life insurers)** — parent-bank distribution (SBIN → SBILIFE, HDFCBANK → HDFCLIFE, ICICIBANK → ICICIPRULI) is the core moat and the core vulnerability; renewal of the banca agreement is an ownership-adjacent structural risk.
- **Brand for direct channel (standalone health)** — STARHEALTH, NIVABUPA: brand recognition drives the direct-retail channel where commissions to intermediaries are thinnest.
- **Underwriting discipline (general insurers)** — a reinsurer or property-casualty writer that sustains combined ratio 3-5 pp below peer is compounding book value even while competitors redistribute float income.
- **Scale on float economics** — once invested-float assets clear ₹50-75k Cr, a 20-30 bps yield advantage on duration/credit-spread calls adds ₹100-225 Cr to the pre-tax bottom line annually.
- **Tech stack + data (insurtech)** — PB Fintech's visitor-to-buyer data moat and STARHEALTH's claims-experience dataset on retail health are genuine moats; volume-less commission platforms are not.

### Unit Economics — Sub-type-Appropriate Unit
Aggregate P&L hides the story. For life insurers, the relevant unit is **VNB margin by product mix** (par 5-12%, non-par 15-25%, ULIP 3-8%, protection 55-75%); headline APE growth with compressing VNB margin is vanity growth. For general insurers, **segment-wise combined ratio** — Motor TP runs 130%+ (regulated tariff, structural loss), Retail Health 90-95%, Group Health 100-110%, Property 80-95%. The blended 102-108% hides the mix. For standalone health insurers, **retail-vs-group claims-ratio spread** drives the ROE; retail loss ratio 60-70% vs group 85-100% means mix shift toward retail is the path to 20% ROE. For insurtech marketplaces, **CAC ₹200-800 per customer, LTV/CAC >2× is the health threshold, contribution margin turning positive after 12-18 months of acquisition**. Extract via `get_company_context(section='concall_insights', sub_section='operational_metrics')`; if unavailable, flag as attempted.

### Standalone Health Insurer — Treat as a Distinct Sub-type
Standalone-health names (STARHEALTH, NIVABUPA) sit apart from composite general insurers: the engine is **GWP growth 18-25%** compounding off retail-channel and direct-brand acquisition (mix-shift compounder, not float-income compounder), and structurally higher combined ratio 103-110% from retail-individual claims skew is expected rather than a red flag. Decompose retail-vs-group loss ratio (retail 60-70% vs group 85-100%) before benchmarking.

### Capital-Cycle Position — Earnings Are Cycle-Sensitive
Insurance earnings are not steady-state; they breathe with three overlapping cycles. Life insurers are rate-cycle sensitive — falling G-sec yields compress par-fund investment return and the non-par guaranteed-return book's new-business pricing; rising yields have the reverse effect with a lag. General insurers run a catastrophe cycle — a single flood-cluster or cyclone year can take combined ratio from 104% to 115% and halve reported profits. The regulatory cycle overlays all of this — IRDAI's 2023 EoM harmonisation and commission-cap revisions repriced life-insurance VNB margins industry-wide in a single fiscal, and any future surrender-charge reset would do the same. Insurtech is VC-funding-cycle sensitive — during a funding winter, CAC inflation + competitor capital scarcity accelerates the path to profitability for the survivors. Always state the cycle phase (early / mid / late / stressed) before forecasting.

### Sector-Specific Red Flags for Business Quality
Business-quality stress shows up earlier than financial-quality stress. Scan for:
- **Persistency decay** — 13-month persistency falling below 80% or 61-month below 55% means the VNB being reported today is built on policies that will not pay premiums in the out-years. This is the earliest structural tell for a life insurer.
- **Combined ratio sustained >110%** — Indian general insurers routinely operate at 102-108% because mandatory motor third-party and competitive group-health keep underwriting marginally loss-making; ROE comes from float income. The genuine red flag is sustained 110%+, or a multi-year drift above sub-sector median — not 100% itself.
- **VNB margin contraction with no volume offset** — if VNB margin compresses 200-400 bps over 4 quarters and APE growth doesn't accelerate proportionately, the product-mix shift is destroying value even if headline NBP grows.
- **Insurtech contribution margin not turning positive after 3 years** — a marketplace business that has scaled CAC spend for 36+ months without contribution margin turning positive is a structurally broken unit-economics thesis, not a "growth investment" runway.
- **Solvency ratio drifting toward 170% (life) or 160% (general)** — the 150% regulatory floor has thin buffer; a drift of 50-80 pp over 4-6 quarters without capital action flags either rapid premium growth without reinsurance support or adverse reserve strengthening.
- **Bancassurance concentration >60% for a life insurer** — parent-bank renewal risk on the distribution agreement is a structural vulnerability even when near-term VNB margin is strong.

### Data-shape Fallback for Unit Economics
If `get_fundamentals(section='revenue_segments')` returns an aggregate-only view and `get_company_context(section='sector_kpis')` reports `status='schema_valid_but_unavailable'` for per-product VNB margin, segment-wise combined ratio, or insurtech contribution margin, fall back to `get_company_context(section='concall_insights', sub_section='management_commentary')` and `sub_section='operational_metrics'` and scan the earnings call transcript for disclosed VNB margin by product, persistency, segment CR, CAC, or LTV/CAC. Cite the quarter. If the narrative too is silent, add to Open Questions tied to the specific unit.

### Open Questions — Insurance Business-Specific
- "What is the 13-month and 61-month persistency trajectory over the last 8 quarters, and how does it compare against the sector median for the same product mix?" (life insurers)
- "Is the combined ratio below 108% sustainable if investment yield compresses 50-80 bps on a 10Y G-sec rally, and how does segment-wise CR reconcile to the blended number?" (general insurers)
- "What share of APE is coming from protection and non-par, and is the VNB-margin trajectory diverging from the sector median?" (life insurers)
- "For insurtech: what is the current contribution margin, trailing 4-quarter CAC and LTV/CAC, and what is the explicit path to standalone (ex-subsidiary) operating breakeven?"
- "Is any bancassurance distribution agreement up for renewal in the next 8 quarters, and what is the historical renewal track record of the parent bank?"
