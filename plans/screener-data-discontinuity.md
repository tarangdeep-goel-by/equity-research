# Screener Data Discontinuity — Universe-Wide Quality Gap

**Date discovered:** 2026-04-25
**Surfaced by:** autoagent-pilot night2 evals (HDFCBANK financials agent), then verified holistically across the full Screener-ingested universe.

## Problem in one sentence

Screener.in mirrors company filings as-reported. When companies change their P&L bucketing between years (Schedule III amendments, Ind-AS 116 lease transition, mergers/demergers), Screener captures the new bucketing for the new year but does **not** restate prior years to match. Every multi-year trend metric computed from `annual_financials` (and the quarterly tables) silently consumes the discontinuity.

## Scope (full DB scan, 2026-04-25)

Heuristic: line item jumps >100% YoY while revenue is stable (within ±30%) → high-confidence reclassification flag. Sign flip in expense/liability/equity lines → secondary flag.

- **485 symbols** scanned (full Screener-ingested universe)
- **344 reclassification flags** across **211 symbols (43% of universe)**
- **92 sign flips** across **58 symbols**

### Worst lines (by flag count)

| Line | Reclass flags | Sign flips |
|---|---|---|
| `other_income` | 84 | 50 |
| `investments` | 61 | — |
| `borrowings` | 50 | — |
| `other_expenses_detail` | 47 | 30 |
| `reserves` | 28 | 10 |
| `other_liabilities` | 21 | — |

### Most extreme cases

| Stock | Year | Line | Jump | Revenue change |
|---|---|---|---|---|
| HDFCLIFE | FY26 | other_expenses_detail | +6,074% | +7% |
| INFY | FY26 | other_expenses_detail | +3,129% | +10% |
| MANKIND | FY25 | borrowings | +4,008% | +19% |
| LICI | FY23 | other_expenses_detail | -1,786% (sign flip) | +8% |
| AXISBANK | FY23 | depreciation | +1,157% | +27% |
| RELIANCE | FY23 | other_expenses_detail | +1,047% | +26% |
| COALINDIA | FY25 | other_expenses_detail | -985% (sign flip) | -1% |
| SIEMENS | FY25 | other_expenses_detail | +1,357% | -22% |
| HDFCBANK | FY26 | other_expenses_detail | +290% | +4% |

These are top Nifty 50 names — the corruption is not at the periphery.

### Originally-reported eval signal

Two distinct stocks flagged in autoagent-pilot night2 archives:

- `20260424T190906_all_for_financials.json` — HDFCBANK: *"Screener operating expense reclassification between FY25 and FY26 caused a massive discontinuity in the C/I ratio (27% to 67%)"*
- `20260424T202147_all_for_financials.json` — NESTLEIND: *"Exceptional forensic work in identifying the raw material cost reclassification and recalculating the stale F-Score"*

Both grader-noted in the same week — the agent only catches it when a sector-aware specialist looks at a specific ratio. Most agents would silently propagate the bad numbers.

## Confirmation that discontinuities are reclass, not real spending

For HDFCBANK FY25→FY26:
- Revenue: 336K → 348K (+3.6%)
- `other_expenses_detail`: 43.7K → 170.2K (+289%, +127K Cr)
- Net income: 70.8K → **76.0K (+7.4%)**
- Net margin: 21.0% → **21.8% (expanded)**

If the bank had really spent ₹127K Cr more on operations with revenue only growing ₹12K Cr, net income would have **cratered**. Instead it grew. Mathematically impossible for the increase to be real spending.

Smoking gun: in FY26, `total_expenses = 207,830` exactly equals `employee_cost + other_expenses_detail = 37,605 + 170,225`. In FY25, those don't sum (employee + other = 77,842 vs total = 186,974). Screener's *aggregation rule for the total field changed between years* — likely post-HDFC Ltd merger, insurance-side line items (HDFC Life policyholder benefits, HDFC ERGO reserves) were rolled into the consolidated entity's "Other Expenses".

## Root causes (clustered)

1. **Ind-AS 116 lease transition (FY20-FY22)** — operating leases became balance-sheet liabilities; broke borrowings + other_liabilities + depreciation continuity for nearly every company with leased real estate
2. **MCA Schedule III amendment (FY22)** — mandated more granular disclosures; companies re-bucketed expenses
3. **Mergers/demergers/restructurings** — HDFC Bank+HDFC Ltd, ETERNAL (Zomato/Blinkit consolidation), JSW group restructuring — each rewires consolidated P&L
4. **Sector regulator mandates** — IRDAI insurance presentation, RBI bank classification revisions — separate from corporate Schedule III

## What downstream breaks

| System | Why |
|---|---|
| DuPont decomposition | Asset turnover + leverage use total_assets / borrowings / interest — all flagged |
| F-Score | Year-over-year line comparison — one break invalidates the score |
| Margin walks ("OPM expanded 200bps over 3yr") | Denominator's bucketing changed mid-window |
| DCF | Uses CFO + capex history; cash flow sign flips abundant |
| Cost-to-Income, NIM | Every bank metric using opex |
| Sector aggregates (Nifty Bank avg C/I, pharma EBITDA margin) | One polluted constituent corrupts the average |
| Quarterly trend math | Same problem, more frequent (each quarter is a fresh re-bucket opportunity) |

**Safe (point-in-time only):** current-year PE, PB, current-quarter EPS, latest snapshot ratios. These don't chain across breaks.

## How professional providers handle this

| Tier | Approach | Cost |
|---|---|---|
| **Companies themselves (in their AR)** | Schedule III mandates restatement of prior years when bucketing changes. AR's 5-year financial highlights table is internally consistent. Footnote: *"Previous year figures regrouped wherever necessary"* | free (read the AR) |
| **Bloomberg / Refinitiv / FactSet / S&P CIQ** | In-house analyst teams manually normalize. Provide `AS_REPORTED` vs `STANDARDIZED` views with provenance | $24K+/seat/year |
| **Capitaline / ACE Equity / Prowess (India)** | Same approach, India-focused | ₹1-3L/year |
| **Sell-side broker reports** | Analysts build their own normalized models per-stock; disclose the adjustment in the report | per-report |
| **Screener / Tijori / Tickertape / StockEdge** | Don't normalize. Raw filings as-is | free, but breakage |

## Three viable strategies (pick what we want to ship)

### 1. Detect + warn (cheapest, biggest immediate win, doesn't fix the data)

- Build `data_quality_flags` table: `(symbol, fiscal_year_end, line, flag_type, magnitude, context)`
- Backfill: run the YoY discontinuity detector across `annual_financials` + `quarterly_results` + `quarterly_balance_sheet` + `quarterly_cash_flow`
- Live: ingestion-time hook computes flags vs prior period after every Screener upsert
- Wire flags into `ResearchDataAPI`: `get_annual_financials()` returns rows + `quality_flags: [...]`
- Trend-math gate: `dupont_decomposition`, `f_score`, `margin_walk`, `cagr` methods refuse to compute (or warn loudly) when the input series crosses a flagged break

Effort: ~1-2 days. Effort:reward ratio is excellent.

### 2. Steal the company's restated series from the AR (highest accuracy, free)

- Annual reports contain a "5-year Financial Highlights" table (1-2 pages, near the start). The company has restated prior 4 years to match current presentation. Internally consistent.
- We already have AR extraction infrastructure (`annual_report_extractor.py`)
- Add a new section: `five_year_summary` — extract the table, validate row totals, store as the canonical trend source
- Replace `get_annual_financials_trend()` to use this when available, fall back to raw Screener stitching when AR table unavailable

Effort: ~2-3 days (depends on AR layout variance). Highest leverage real fix.

### 3. Concall management commentary "comparable" basis

- Concalls and earnings releases often state things like *"On a like-for-like basis, opex grew 8%"* — that's the analyst-grade comparable
- Extend `concall_extractor.py` to surface a `comparable_growth_metrics` block
- Lower precision than (2) but free and fills the gap when AR's 5-year table is degraded

Effort: ~1 day. Combine with (2) for redundancy.

## Recommended sequence

1. **Now (cheap):** Strategy 1 — detect + warn. Stops agents from computing nonsense across breaks.
2. **Next (high accuracy):** Strategy 2 — extract AR's 5-year table. Becomes the canonical trend source.
3. **Backstop:** Strategy 3 — concall comparable basis when AR layout fails.

## Out of scope for this note

- Manually-curated normalization pipeline (Bloomberg-tier). Out of budget.
- Switching off Screener entirely. Their as-reported data is fine for current-period metrics; we just shouldn't use it for trend math without quality gates.
