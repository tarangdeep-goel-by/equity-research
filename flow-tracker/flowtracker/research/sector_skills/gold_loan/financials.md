## Gold Loan NBFC — Financials Agent

### LTV (Loan-to-Value) — The Regulator's Cap
LTV is the defining risk lever for a gold loan NBFC. RBI caps LTV at 75% at origination, but conservative operators run portfolio averages of 60-68% to preserve a buffer against gold price volatility. A rising portfolio LTV signals more aggressive origination and less absorption capacity when gold corrects — the exact wrong direction heading into a gold drawdown. Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **Portfolio Average LTV** — trend QoQ and YoY
- **LTV at origination vs LTV at book** (book LTV moves with gold price)
- **% of book above 70% LTV** — the margin-call-vulnerable cohort

### Auction Losses — The Real Credit Quality Metric
Standard GNPA/NNPA analysis misleads for gold NBFCs because the collateral is liquid and fully secured. Gold loan NBFCs rarely "write off" — they auction. The meaningful credit quality metric is **auction loss %** (shortfall from auction / gross auction value):
- **<0.5%** — healthy, pricing discipline intact
- **0.5-1%** — watchful, LTV may be creeping up
- **>1%** — either LTV was too aggressive at origination or gold price crashed mid-tenure

Always read auction loss trend alongside gold price trend — losses spike when gold falls sharply. Extract from `concall_insights`.

### AUM Mix — Pure Gold vs Diversification
Pure gold loan NBFCs (Muthoot Finance core book) run a narrow but deep niche: 25-30% NIMs and 4-5% ROA, a profile no other lending segment matches. Diversification into microfinance, personal loans, or affordable housing dilutes NIM but extends the growth runway beyond the structural ceiling of gold demand. Watch the concentration profile:
- **>85% gold** — monoline concentration risk, single-asset beta
- **60-85% gold** — balanced
- **<60% gold** — execution risk in newer segments; watch credit cost trajectory of non-gold book

Extract AUM by segment from `concall_insights`.

### NIM Structure — High-Yield, Short-Tenure
Gold loans are structurally 6-9 month instruments that re-price ~2x/year — a fundamentally different duration profile from bank loans. Yields run 22-26% (RBI caps spreads over base rate), and because borrowings are also short-tenure, the NIM is highly sensitive to cost of funds moves. Call `get_quality_scores(section='bfsi')` for NIM and cost of funds if gold_loan routing resolves. Trace NIM compression/expansion back to:
- Yield changes (competition from banks entering gold loans, teaser rate offers)
- Cost of funds moves (bank borrowing rates, NCD issuance spreads)

### Branch Productivity — The Growth Ceiling
AUM per branch is the key productivity metric — mature branches typically run ₹8-15 Cr. Branch count growth without per-branch AUM growth signals cannibalization (new branches poaching from old). New branches take 2-3 years to reach breakeven given fixed employee and rental costs, so aggressive branch expansion compresses near-term ROA even when strategically correct. Extract branch count and AUM/branch from `concall_insights` and track trajectory.

### Gold Price Sensitivity — The Hidden Beta
Gold price is the single biggest external driver. Rising gold prices grow AUM mechanically (existing loans revalue upward, top-up loan demand spikes), while falling prices trigger auction losses and compress origination. A -15% gold price move can compress ROA by 150-200bps within 2-3 quarters. Always flag the prevailing gold price trend in the report — analysis that ignores the macro gold tape is incomplete for this sector.

### Funding Mix — Deposit Access Matters
Gold loan NBFCs cannot take public deposits (unless registered as PDs/DPD-compliant), so funding is bank borrowings + NCDs + sub-debt. Cost of funds typically runs 8-11%, and bank line concentration is a real risk — a single bank pulling lines can force asset-side slowdown. Check `get_fundamentals(section='balance_sheet_detail')` for borrowing structure and diversification across banks, NCDs, and retail bonds.

### Valuation Basis
- **P/B is primary** — typical range 1.5-3.5x for gold NBFCs. Discount to private banks (monoline risk), premium to diversified NBFCs (higher structural ROA)
- **PE is relevant but distorted** by provisioning timing — gold NBFCs provision conservatively at origination, depressing reported earnings in growth quarters
- **Sustained ROE of 18-25%** justifies the upper end of the P/B band
- Call `get_valuation(section='band', metric='pb')` for historical P/B band context
