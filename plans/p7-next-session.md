# P-7: Next Session Plan

## 1. Concall Pipeline Fix (~1 hr)
Use Screener transcript URLs (already in `company_documents` table) as primary source instead of flaky BSE downloads. KOTAKBANK: 3 → 6+ concalls.
**Detailed plan:** `plans/p7-concall-pipeline-fix.md`

## 2. Capital Allocation Tool Section (~45 min)
**Problem:** Agents don't analyze what cash-rich companies do with their money (buybacks, acquisitions, hoarding). Gemini flagged this for INDIAMART (₹3,453 Cr cash = 28% of market cap).

**Fix:** Add `get_fundamentals(section='capital_allocation')` that computes from existing `annual_financials`:
- 5Y cumulative CFO
- Deployment breakdown: capex, acquisitions (CFI), dividends, buybacks, net cash accumulation
- Cash as % of market cap
- Payout ratio trend
- Cash yield (dividends + buybacks / market cap)

All data already in `annual_financials` (CFO, CFI, CFF, dividends) + `valuation_snapshot` (market cap). Just needs a computation method in `data_api.py` + a new section in `_get_fundamentals_section`.

## 3. DCF Operating Margin Fix (~30 min)
**Problem:** Reverse DCF and fair value model use net margin (inflated by treasury/other income for cash-rich companies). INDIAMART shows 40% margin but operating margin is 30% — DCF overstates fair value.

**Fix:** In `data_api.py`'s fair value / reverse DCF computation:
- Use EBITDA margin (from `annual_financials`) for DCF, not net margin
- Strip other income before computing margins used in projections
- Add `operating_margin` and `net_margin` separately in the output so agents can see both

## 4. Continue Agent Eval Loop
- Run remaining INDIAMART agents (financials, valuation, risk, sector, technical) one at a time
- Get Gemini review for each
- Fix issues found
- Goal: get all agents to B+ or higher for non-BFSI stocks

## 5. Quartr Transcript Exploration (if time)
Yahoo Finance earnings calls page has Quartr-hosted transcripts. Could be an additional source beyond Screener. Lower priority since Screener URLs should solve the coverage problem.

## Priority Order
1 → 3 → 2 → 4 → 5

Fix concall pipeline first (biggest data gap), then DCF margin (analytical accuracy), then capital allocation (new analysis), then continue eval loop.
