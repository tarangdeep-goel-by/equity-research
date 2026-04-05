# Institutional Research Rules — Extracted from Marcellus + Ambit + Kotak

**Sources:**
- Marcellus CCP Product PPT (June 2023) — Consistent Compounders framework
- Ambit Good & Clean Midcap PPT (June 2024) — Clean accounting + Good capital allocation
- Ambit Ten Baggers 4.0 (January 2015) — Greatness Score (6 dimensions, 20 sub-criteria)
- Kotak Strategy (February 2025) — BSE-500 sector-wise earnings analysis, market-cap tier analysis
**Date extracted:** 2026-04-05

## Rules We Already Have (covered by existing prompts)
- DuPont decomposition (ROCE = margin × turnover × leverage)
- Beneish M-Score (earnings manipulation)
- Piotroski F-Score (financial health)
- CFO/PAT ratio (earnings quality)
- Promoter pledge + margin call
- Related Party Transactions flag
- Auditor resignations
- Contingent liabilities (in Beneish)

## New Rules to Add (from Marcellus)

### Forensic / Risk Agent
1. **CFO/EBITDA ratio** — track over 5+ years. Persistently low (<50%) = earnings manipulation. Different from CFO/PAT — EBITDA denominator catches depreciation games.
2. **Depreciation rate volatility** — high volatility in depreciation rate (dep/gross block %) across years signals accounting flexibility abuse.
3. **Yield on cash and investments** — if company reports ₹500 Cr cash but earns only ₹10 Cr interest income (2% yield vs 7% risk-free), the cash may not exist or may be restricted.
4. **Auditor remuneration growth vs revenue growth** — if auditor fees grow 30% while revenue grows 10%, the accounts are becoming complex (red flag).
5. **CWIP to gross block ratio** — persistently high (>30%) suggests capex never gets commissioned or is being used to park losses.
6. **Increasing advances to related parties** — cash pilferage signal. Track YoY trend of advances/loans to promoter entities.
7. **High miscellaneous expenses** — if "other expenses" or "miscellaneous" is a large % of total expenses, it may hide illegitimate costs.

### Business Agent
8. **Moat Pricing Test** — "Can a competitor offer a product 1/3rd cheaper and still have no impact on this company's profitability or market share?" If yes = wide moat. If no = narrow/none.
9. **Lethargy Score** (3 dimensions): (a) Is the company deepening existing moats? (b) Is it experimenting with new revenue growth drivers? (c) Is it attempting radical disruption of its own industry?
10. **Volume vs Price decomposition** — revenue growth should be decomposed into volume growth + price growth. Pure price growth without volume = unsustainable (demand destruction).

### Business + Risk Agent
11. **Succession Planning Score** (4 dimensions): (a) Decentralized execution vs CEO-dependent, (b) CXO quality and tenure at the firm, (c) Historical evidence of smooth CXO transitions, (d) Board independence (truly independent, no group-think).
12. **CXO Churn** — high turnover in C-suite = management instability. Track CFO/CEO/COO changes in last 3 years.

### Financial Agent
13. **ROCE × Reinvestment Rate = Earnings Growth** — Marcellus' core thesis. Companies need BOTH high ROCE (>15%) AND high reinvestment rate (>50% of CFO) for sustained compounding. High ROCE + low reinvestment = cash cow, not compounder.
14. **Equity dilution check** — if shares outstanding grew >5% in 3 years without a merger, it's dilutive (QIPs, ESOPs, preferential allotment). Flag as negative for per-share returns.

### Synthesis Agent
15. **Exit trigger framework** — consider downgrade/SELL when: (a) management/board composition changes post-acquisition, (b) volume growth decelerates in core categories for 2+ quarters, (c) market share loss in key products, (d) CXO churn accelerates.

## New Rules to Add (from Ambit)

### Risk Agent
16. **Political connectivity red flag** — firms whose competitive advantage depends on political connections (government contracts without competitive bidding, regulatory favors) seldom outperform long-term. Flag when >50% of revenue comes from government/PSU contracts and the company has no visible technology or efficiency moat.

### Financial Agent
17. **Capital allocation cycle** (Ambit's 6-step): Incremental Capex → Conversion to Sales Growth → Pricing Discipline (PBIT margin) → Capital Employed Turnover → Balance Sheet Discipline (D/E, no dilution) → Cash Generation (CFO). A "great" company executes all 6 steps; "mediocre" breaks the chain.
18. **Writing off losses through balance sheet** — instead of recognizing losses in P&L, some companies write them directly against reserves or adjust goodwill. Check if reserves decreased without corresponding dividend payments.

## Implementation Priority

**High (add now — these are universal rules):**
- CFO/EBITDA tracking (Risk agent) — we have CFO/PAT but not CFO/EBITDA
- ROCE × Reinvestment Rate (Financial agent) — this is Marcellus' core filter
- Volume vs Price decomposition (Business agent) — already in FMCG caveat, make universal
- Equity dilution check (Financial agent)
- Yield on cash sanity check (Risk agent)

**Medium (add as open questions if data unavailable):**
- Auditor remuneration growth vs revenue
- CWIP/gross block persistence
- CXO churn tracking
- Succession planning assessment
- Lethargy score dimensions

**Low (needs new data sources):**
- Related party transaction amounts (need annual report parsing)
- Political connectivity scoring
- Miscellaneous expense breakdown

---

## New Rules from Ambit Ten Baggers (Greatness Score Framework)

### The Greatness Score — 6 Equally-Weighted Dimensions (Exhibit 2)

Each dimension carries 16.7% weight. Sub-criteria are binary (1 or 0) — did the company do better than median over 6 years? Scored on BOTH improvement AND consistency (volatility-adjusted).

| # | Dimension | Sub-Criteria |
|---|-----------|-------------|
| 1 | **Investments** | (a) Above-median gross block increase (3Y vs prior 3Y), (b) Above-median consistency of gross block increase |
| 2 | **Conversion to Sales** | (a) Improvement in asset turnover, (b) Positive asset turnover improvement consistency-adjusted, (c) Above-median sales increase, (d) Above-median sales increase consistency |
| 3 | **Pricing Discipline** | (a) Above-median PBIT margin increase, (b) Above-median PBIT margin increase consistency |
| 4 | **Balance Sheet Discipline** | (a) Below-median D/E decline, (b) Below-median D/E decline consistency, (c) Above-median cash ratio increase, (d) Above-median cash ratio increase consistency |
| 5 | **Cash Generation & PAT** | (a) Above-median CFO increase, (b) Above-median CFO increase consistency, (c) Above-median adj PAT increase, (d) Above-median adj PAT increase consistency |
| 6 | **Return Ratio Improvement** | (a) Improvement in RoE, (b) Positive RoE improvement consistency-adjusted, (c) Improvement in RoCE, (d) Positive RoCE improvement consistency-adjusted |

**Cutoff:** Score >67% = "Great" (top 22% of BSE500). Score 50-67% = "Good but not Great". Score <50% = "Mediocre."

### Critical Insight: Improvement > Absolute Level
Ambit's framework does NOT check if ROCE is high — it checks if ROCE is IMPROVING consistently. A company with 15% ROCE improving steadily beats a company with 25% ROCE that's flat. **We currently only check absolute levels.**

### Critical Insight: Entry Valuation is Irrelevant for Quality
Ambit's 10-year backtest (Exhibit 16-17) shows R² ≈ 0 between beginning-period P/E or P/B and subsequent 10-year returns. "Once you screen rigorously for quality, there is little value add in further screening through a demanding valuation filter." **This challenges our synthesis agent's heavy weight on current PE.**

### New Code Metrics from Ten Baggers

| # | Metric | Formula | Agent |
|---|--------|---------|-------|
| 19 | **ROCE improvement trajectory** | ROCE change over 5Y (latest 3Y avg vs prior 3Y avg) | Financial |
| 20 | **Consistency-adjusted improvement** | Improvement / std_dev of annual values (Sharpe-like) | Financial |
| 21 | **Capex productivity** | Gross block CAGR vs Sales CAGR — if capex grows 2x faster than sales for 3+ years = value destruction | Financial |
| 22 | **Cash ratio improvement** | (Cash + investments) / total assets — 5Y trend direction | Financial |
| 23 | **Asset turnover improvement** | Sales / total assets — 5Y trend and consistency | Financial |
| 24 | **Greatness classification** | Composite of all 6 dimensions → Great / Good / Mediocre | Financial (analytical_snapshot) |

### New Prompt Rules from Ten Baggers

| # | Rule | Agent |
|---|------|-------|
| 25 | **For 3-5 year investment horizons, weight quality trajectory higher than current valuation** — a consistently improving company at 35x PE outperforms a stagnant company at 15x PE over long periods | Synthesis |
| 26 | **Ambit exit triggers** — exit when greatness score deteriorates: pricing discipline lost, balance sheet discipline broken, or return ratios declining for 2+ years | Synthesis |
| 27 | **Valuation buckets vs own history** — Attractive (below 5Y avg on 2+ of PE/PB/EV-EBITDA), Moderate (below on 1), Rich (above on all 3). This is our existing relative valuation approach. | Valuation |

---

## From Kotak Strategy (February 2025)

### New Analytical Patterns

| # | Pattern | What It Shows | Agent |
|---|---------|---------------|-------|
| 28 | **Market-cap tier analysis** — compare revenue/EBITDA/PAT growth separately for top-100, 101-250, 251-500 companies. Small-caps consistently lag large-caps on earnings growth. | Sector |
| 29 | **RM cost/sales as cycle indicator** — when raw material cost as % of sales is at long-term average (54-55%), margins are at equilibrium. Deviation = cyclical margin risk. | Financial |
| 30 | **Consensus EPS revision momentum by market-cap tier** — small-cap estimates get cut 25% vs 3% for large-caps. Size = estimate reliability proxy. | Valuation |
| 31 | **EBITDA margin reversion** — BSE-500 ex-BFSI EBITDA margins mean-revert to 16-17% over market cycles. Sectors >5pp above this are at margin compression risk. | Sector |

---

## Updated Implementation Priority

**High (add now as code — data available):**
1. ROCE × Reinvestment Rate (Marcellus core)
2. Equity dilution rate (3Y shares CAGR)
3. Cash yield sanity check
4. Depreciation rate volatility
5. **ROCE/RoE improvement trajectory** (Ambit — 3Y avg vs prior 3Y avg)
6. **Consistency-adjusted metric** (improvement / std_dev)
7. **Capex productivity** (gross block CAGR vs sales CAGR)

**High (add now as prompts — no code):**
8. Moat pricing test (Marcellus)
9. Lethargy score (Marcellus)
10. Succession planning (Marcellus)
11. Volume vs price decomposition (universal)
12. Capital allocation cycle (Ambit 6-step)
13. Political connectivity flag
14. CXO churn open question
15. **Quality trajectory > current valuation for long-term** (Ambit Ten Baggers insight)
16. **Ambit exit triggers** — greatness score deterioration
