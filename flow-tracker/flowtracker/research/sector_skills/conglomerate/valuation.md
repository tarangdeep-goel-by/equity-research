## Conglomerate — Valuation Agent

### Primary Valuation = SOTP, Never Consolidated PE
The single most common valuation error for an Indian conglomerate is anchoring to consolidated PE or consolidated EV/EBITDA. Both blend asset-heavy and asset-light verticals into an average that describes no individual business; both mask the standalone (ex-subsidiary) franchise quality; both miss the re-rating catalyst. The primary valuation is **Sum-of-the-Parts (SOTP)**, with reverse-DCF and per-vertical EV/EBITDA as independent sanity checks.

### SOTP Build — Five Mechanical Steps
Route every SOTP through this sequence so the arithmetic is transparent and auditable. The "empty SOTP" failure mode flagged in prior evals — citing that SOTP is relevant without actually building it — is the single worst outcome.

1. Call `get_valuation(section='sotp')` for the tool-computed listed-subsidiary stake map.
2. For each **listed subsidiary**: current market cap × parent's stake % → per-share contribution to NAV. Cite stake % from the most recent disclosure.
3. For each **unlisted subsidiary or vertical**: apply a sector-appropriate multiple on the segment financials — AMC at **3-5% of AUM** (typical / mid-cycle anchor; use **6-8% AUM** only for peak-cycle premium names with equity-share AUM >60%, scale >₹5L Cr, and top-quartile fee yield — do not apply 6-8% to generic AMC arms), life insurer at **1.5-3× embedded value**, general insurer at **1.0-2.5× annual GDPI**, NBFC arm at **1.0-2.5× book** (calibrated to subsidiary ROE), specialty chemicals at **18-28× EV/EBITDA** (depending on specialty mix), IT services at **20-30× PE**, consumer at **35-55× PE**, infrastructure / capital goods at **15-25× EV/EBITDA**. Cite the multiple and the segment EBITDA / book / AUM used.
4. Apply the **holdco discount** to the aggregate sub-value using the decomposition table below; do not state a blended discount without showing the components.
5. Reconcile: SOTP NAV per share vs current market cap per share = implied upside/downside; back out the implied standalone (ex-SOTP) valuation of the parent's own operating business.

**SOTP adjustments — do not skip these, they materially move NAV and partly justify the wide India holdco discount:**
- **Tax leakage on monetisation** — gross sub-stake values are pre-tax. Deduct estimated **capital-gains tax** on unrealised listed-sub stakes (LTCG on listed equity is real and large for low-cost-base holdco positions) — the parent cannot convert NAV to cash without this haircut. Also assess **Section 80M** dividend friction: a holdco that does not pass dividends through to its own shareholders loses the inter-corporate-dividend deduction, taxing upstreamed cash. These frictions mathematically *floor* the achievable discount — a holdco trading near zero discount is ignoring them.
- **Debt netting discipline (avoid double-counting)** — for any subsidiary valued on an **EV basis** (per-vertical EV/EBITDA), deduct *that subsidiary's* net debt to get its equity value before applying the stake %; do **not** then also subtract the same debt at the parent level. At the parent level, net only **standalone** (holdco) net cash/debt. Using consolidated debt against EV-valued subs double-counts liabilities and understates NAV.
- **Unallocated corporate overhead** — capitalise standalone corporate-centre costs (holding-company opex not attributable to any vertical) as a negative line; ignoring them overstates NAV.

### Holdco Discount Decomposition Table
Calibrate to the observed Indian reality, not a token number: the median listed-India holdco discount is wide (studies put it around ~50-65% to NAV, and pure investment holdcos with no operating P&L run wider still). A well-governed multi-vertical *operating*-plus-holdings conglomerate sits at the narrower end (~20-40%); a complex promoter-group or pure-holdco structure sits at the wide end (50%+). Build the discount bottom-up from the components below rather than anchoring to a single headline figure, then sanity-check the result against the wide observed range. State each component before applying the blended discount:

| Component | Typical range | What drives it up |
| :--- | :--- | :--- |
| **Governance** | 10-15 pp | Promoter-group opacity; board without independent majority; material related-party pattern; auditor-resignation cluster |
| **Complexity / opacity** | 5-10 pp | Many unlisted subs without segment disclosure; frequent re-segmentation; cross-holdings between listed group entities |
| **Leverage at parent (standalone)** | 5-10 pp | Standalone net debt > 2× annual sub-dividend receipts; material corporate guarantees extended to weaker group entities |
| **Illiquidity of unlisted subs** | 5-10 pp | Share of NAV in unlisted entities > 40%; no disclosed monetisation or IPO pipeline |
| **Blended** | 20-40% for operating-plus-holdings structures; 50-65%+ for pure investment holdcos (the India median is wide — do not under-discount) | — |
| **Pure-holdco penalty** | +10-20 pp on top | No operating cash-flow optionality, no standalone re-rating catalyst beyond NAV compression, full tax friction on dividend upstreaming unless re-distributed (Sec 80M) — applies only to no-operating-P&L holdcos |

Pull peer-conglomerate discount ranges via `get_peer_sector(section='benchmarks')`; state whether this stock's current market-implied discount is inside the peer range.

### Reverse DCF — Sanity Check on Consolidated Earnings
SOTP gives the bottom-up sub-of-parts value; reverse DCF on consolidated earnings is the top-down sanity check. Note consolidated PAT already captures subsidiary earnings in full whether or not they are paid up as dividends — it is *standalone* PAT (dividends received + standalone operating profit) that measures cash actually reaching the parent. When SOTP implies 25% upside but reverse DCF on consolidated PAT implies only 10% upside, the gap usually means SOTP is assigning full subsidiary value while the parent realises only a fraction of it as upstreamed cash — cross-check the standalone-vs-consolidated cash bridge (sub-dividend coverage, minority leakage, equity-accounted JVs) before publishing.

Terminal-growth discipline — the perpetuity `g` cannot exceed long-run *nominal* GDP or the company mathematically swallows the economy. India's long-run nominal GDP runs ~10-11% (≈6-7% real + ~4-5% deflator); in nominal-rupee DCFs cap terminal nominal `g` at **6-8%** (a conservative haircut to long-run nominal GDP — never the ~4-5% *real* rate, which is the wrong unit for a nominal cash-flow stream). If the DCF is run in real terms, cap terminal real `g` at ~4-5%. The **10-14%** range applies to the **high-growth phase CAGR** (first 5-10 years, typical for Indian nominal earnings), not to perpetuity. Implied high-growth-phase CAGR above 14% against a mature vertical mix is the stress-test flag; implied perpetuity nominal `g` above ~8% is a math-discipline failure regardless of growth story. Call `get_fair_value_analysis(section='reverse_dcf')` and carry phase-1 `g`, terminal `g`, CoE, and implied growth explicitly through `calculate`.

**Justified-multiple discipline for per-vertical fair values** — whenever a per-vertical SOTP contribution is backed out via a justified-multiple calc (not a peer-observed multiple), `g` must be carried through the formula, not dropped. The BFSI-pilot anchors apply per vertical: **`Justified PE ≈ payout × (1 + g) / (CoE − g)`** for earnings-driven verticals (consumer, IT, specialty chem arms) and **`Justified P/B ≈ (ROE − g) / (CoE − g)`** (Gordon growth) for financial verticals (AMC, NBFC, life/general insurer). Dropping `g` collapses the numerator and denominator independently and produces the Pattern-D aggregation error — under-counting high-growth verticals and over-counting mature ones. Route each per-vertical justified-multiple through `calculate` with `payout`, `g`, `CoE` (or `ROE`, `g`, `CoE` for P/B) as named inputs before aggregating into SOTP.

### Manual SOTP Baseline & Consensus-Target Weighting Discipline
If the auto-SOTP is disputed, incomplete, or contaminated with promoter-group siblings (see the shared SOTP-Verification rule), **manually construct a baseline SOTP from segment EBITDA × peer / recent-transaction multiples** for the unlisted businesses, and value **only stakes the company itself holds** — never sum sister-company market caps the company does not own equity in.

Do not over-anchor to sell-side consensus price targets. If consensus targets are proven aspirational or methodologically flawed (e.g. they assume sub-value the parent does not own, ignore the holdco discount, or embed growth the segment economics cannot support), **reduce their weight in the blended fair value to 0%** and rely on reverse-DCF or a manual SOTP proxy base case. Never assign 100% weight to a target you have just demonstrated is unreliable — state the weighting decision and its rationale explicitly.

### Per-Vertical EV/EBITDA — Segment-P&L Cross-Check
Independent of the listed-subsidiary market-cap SOTP, build a per-vertical EV/EBITDA: take segment EBITDA from `get_fundamentals(section='revenue_segments')`, apply the sector multiple per vertical, aggregate, subtract consolidated net debt, and compare to current market cap. If the market-cap-based SOTP and the per-vertical EV/EBITDA SOTP diverge by more than 15-20%, reconcile — the divergence usually traces to either (a) a listed subsidiary trading at a dislocated multiple vs its segment EBITDA, or (b) unlisted sub-value being assigned on a multiple inconsistent with the segment EBITDA.

### Worked Holdco Discount Example
- Gross SOTP NAV per share (listed stakes at mcap × stake + unlisted at sector multiple + net cash − debt): ₹1,600
- Decomposition: governance 12pp + complexity 8pp + parent leverage 3pp + illiquidity 5pp = **28% blended**
- Holdco NAV after discount: 1,600 × (1 − 0.28) = **₹1,152**
- Current market cap per share: ₹900 → market-implied discount is 44%
- Reconcile: the 16 pp gap (44% − 28%) is either an unpriced governance event or mispricing; trigger the cross-check with pledge / related-party / auditor signals before calling it an upside opportunity.

Route the arithmetic through `calculate` with `gross_sotp`, `governance_pp`, `complexity_pp`, `leverage_pp`, `illiquidity_pp`, and `shares_out` as named inputs.

### What Fails for Conglomerates
- **Consolidated PE** — hides vertical-mix; a 30× PE on a 40% AMC-vertical + 60% commodity-vertical conglomerate is neither the 45× an AMC deserves nor the 15× the commodity vertical deserves.
- **Consolidated EV/EBITDA** — mixes asset-heavy (low multiple) and asset-light (high multiple) verticals; the aggregate multiple is noise.
- **Peer PE** — no clean peer exists for a multi-vertical conglomerate; any peer-PE framing is structurally wrong and produces false conclusions.
- **Single-multiple DCF** — a single discount rate and terminal-growth assumption across verticals with different risk profiles and reinvestment needs mis-prices every vertical; a correct DCF is per-vertical and re-aggregated.

### Catalyst Framework — SOTP-Unlock Mechanics
Holdco discounts compress on specific corporate actions; name the pending action if it exists, otherwise flag the absence:
- **Subsidiary IPO** — the market re-prices the unlisted-sub multiple to the observed listed-sub multiple on day-1; historically compresses holdco discount by 5-10 pp
- **Demerger / spin-off** — removes the conglomerate structure entirely; unlocks the subsidiary-level multiple fully
- **Divestment of non-core vertical** — cleans the capital-allocation narrative; typical 3-5 pp discount compression
- **Governance upgrade** — independent-majority board, auditor-reset, or material-RPT reduction — 5-10 pp compression
- **Parent deleveraging** — standalone debt paydown funded by sub-dividend upstreaming — 3-5 pp compression
- **Buyback at holdco level** — direct discount compression on the reduced denominator

### Data-shape Fallback for SOTP Inputs
When `get_valuation(section='sotp')` returns a sparse stake map (missing unlisted subsidiaries), fall back to `get_company_context(section='documents', query='subsidiaries|group structure|shareholding')` for the annual-report subsidiary list and `get_company_context(section='filings', sub_section='notes_to_accounts')` for disclosed stake percentages and carrying values. Cite each source. If an unlisted subsidiary's AUM / EBITDA / book is undisclosed, state the range of sector multiples considered and the sensitivity on NAV — do not assign a point estimate without a disclosed base.

### Open Questions — Conglomerate Valuation-Specific
- "What holdco discount is the market currently applying, and how does the decomposition (governance + complexity + parent leverage + illiquidity) account for it?"
- "For each unlisted subsidiary representing >10% of SOTP NAV: what is the most recent disclosed EBITDA / AUM / book, and what sector multiple range was applied?"
- "Does reverse DCF on consolidated PAT reconcile with SOTP NAV, or is SOTP over-counting subsidiary value that the parent does not receive as dividends?"
- "Is there a disclosed subsidiary-IPO, demerger, or divestment pipeline that would structurally compress the holdco discount in the next 12-24 months?"
- "What is the standalone (ex-SOTP) implied P/E or EV/EBITDA on the parent's own operating business, and does it reconcile with pure-play peers of that vertical?"
