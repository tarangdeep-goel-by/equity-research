# P-1: Data & Tooling Fixes — Quick Wins

> Created: 2026-03-31
> Updated: 2026-04-01
> Status: ✅ COMPLETE (Fixes 1-3, 5 implemented; Fix 4 blocked on Screener Premium)
> Completed: 2026-04-01
> Branch: feat/p1-data-fixes (worktree: equity-research-p1)
> Next: P-1B (plans/p-1b-data-fixes.md) — estimate revisions, quarterly BS/CF, events calendar, dividend history

These are fundamental data gaps that a buy-side / sell-side analyst has but our agents don't. Fixing them doesn't require new agents or features — just scraping more data and exposing it via existing tools.

---

## Quick Reference

- **5 data gaps**, each independent — can be done in any order
- **No new agents needed** — existing agents get smarter automatically
- **No new prompts** — data flows through existing MCP tools
- Priority: Comparable matrix (ready now) → Corporate actions (researched) → Annual BS/CF parsing → Financial model → Segment data (blocked)

---

## Fix 1: Annual Balance Sheet + Cash Flow Parsing

> **REVISED after research:** Screener does NOT provide quarterly BS/CF in any form (HTML, Excel, Schedules API). Only annual data + one trailing half-yearly BS snapshot. The `#balance-sheet` and `#cash-flow` HTML sections exist but contain annual data only. Cash flow has no half-yearly entry at all.

### The Gap
We have annual P&L via Excel export (`parse_annual_financials()`) but we DON'T expose annual BS/CF data through the research tools. The data is already parsed and stored in `annual_financials` table — but `get_annual_financials()` in `data_api.py` only returns P&L columns. BS/CF columns exist in the table but aren't surfaced.

For banks (HDFCBANK, SBIN), BS data is critical — NPA trends, provision coverage, CASA ratio, credit-deposit ratio are all BS items. These would need to come from quarterly filings on BSE (XBRL), not Screener.

### What Actually Exists
- **`annual_financials` table** already has BS columns: equity_capital, reserves, borrowings, other_liabilities, total_assets, fixed_assets, cwip, investments, other_assets, receivables, inventory, cash_and_bank
- **`annual_financials` table** already has CF columns: cfo, cfi, cff, net_cash_flow
- **`parse_annual_financials()`** (screener_client.py:412-554) already parses all this from Excel
- **`get_annual_financials()`** in data_api.py returns the stored data — but agents may not be using BS/CF columns effectively
- **HTML sections** `#balance-sheet` and `#cash-flow` exist with annual data + one trailing half-yearly BS snapshot (e.g., Sep 2025)

### What Screener Does NOT Have
- **No quarterly BS/CF** — not in HTML, not in Excel export, not in Schedules API
- **No quarterly NPA/CASA data** — banking-specific metrics are NOT in Screener's quarterly section
- **Cash flow has no half-yearly entry** — strictly annual

### Implementation (Revised Scope)
1. **Verify `get_annual_financials()` returns BS/CF columns** — check if data_api surfaces them or only P&L
2. **Parse half-yearly BS from HTML** — the `#balance-sheet` section has one trailing half-yearly entry (e.g., Sep 2025) that could be useful as a "latest snapshot"
3. **Ensure agents know BS/CF data exists** — update prompts if Financial agent isn't using BS/CF columns from annual data
4. **Future: BSE XBRL parsing** for true quarterly BS (banks) — this is a separate, larger effort

### Effort: Low (1 hour)
Most data already exists in the table. Main work is verifying it flows through tools and agents use it.

### Files
- `data_api.py` — verify `get_annual_financials()` returns BS/CF columns
- `prompts.py` — ensure Financial agent knows to use BS/CF data
- `screener_client.py` — optionally parse trailing half-yearly BS from HTML

---

## Fix 2: Comparable Valuation Matrix

### The Gap
We compare PE and ROCE across peers via `get_peer_comparison` (Screener surface data). But analysts compare a full matrix: EV/EBITDA, EV/Sales, P/B, PEG, ROE, ROIC, debt/equity across 10+ peers. We have `valuation_snapshot` (yfinance) for every stock in Nifty 250 now — we just don't present it as a comparison.

### What We Already Have
- `valuation_snapshot` table: 504 stocks with 50+ columns — PE, PB, EV/EBITDA, margins, beta, market cap, ROE, ROA, revenue growth, etc.
- `peer_comparison` table: peer names + symbols for any researched stock (Screener Peers API)
- `get_peer_metrics()` tool: reads FMP `key_metrics` for subject + each peer — works if FMP data exists, empty otherwise

### Implementation
1. **Extend `get_peer_metrics()`** in `data_api.py` — fall back to `valuation_snapshot` table when FMP data is empty for a peer. Most Nifty 250 stocks have valuation_snapshot data (yfinance-sourced, fully populated).
2. **New tool: `get_valuation_matrix(symbol)`** — returns structured matrix: for each peer, pull PE, PB, EV/EBITDA, EV/Sales, margin, ROE from `valuation_snapshot`. Compute sector median, percentile for each metric.
3. **New chart: `valuation_heatmap`** — color-coded matrix showing which stocks are cheap on which metrics

### Effort: Low (1-2 hours)
Data already exists. Just need to query it differently and present as matrix.

### Files
- `data_api.py` — new `get_valuation_matrix()` method + extend `get_peer_metrics()` fallback
- `tools.py` — new MCP tool
- `charts.py` — optional heatmap chart
- `prompts.py` — tell Valuation agent to use the matrix tool

---

## Fix 3: Corporate Actions History

> **Research complete.** BSE API is the primary source. yfinance supplements with deeper history. NSE API is dead (404). Screener EPS is raw/unadjusted — confirmed by EPS discontinuities around bonus dates.

### The Gap
Stock splits, bonuses, and rights issues affect per-share calculations. If RELIANCE did a 1:1 bonus in 2017, all pre-2017 EPS numbers need halving for comparison. **Confirmed: Screener data is raw/unadjusted** — RELIANCE Q Jun-2017 EPS = 30.78, Q Sep-2017 EPS = 13.67 (halved after 1:1 bonus).

### Data Sources (Researched)

**BSE CorporateAction API** (Primary) — `https://api.bseindia.com/BseIndiaAPI/api/CorporateAction/w?scripcode={BSE_CODE}`
- Returns 3 tables: dividends (Table), bonuses (Table1), all actions (Table2)
- Purpose codes: `DP` (dividend), `BN` (bonus), `SS` (stock split), `SO` (spin-off/demerger), `BGM` (buyback)
- ~5 year history. Requires BSE scrip code (already have `get_bse_code()` in `filing_client.py`)
- **Does NOT capture rights issues** (RELIANCE 2020 rights absent)

**yfinance `ticker.splits`** (Supplement)
- 30+ year history for major stocks (RELIANCE back to 1996)
- Captures both splits AND bonuses — but as a single float multiplier (2.0 = shares doubled), **cannot distinguish split from bonus**
- No rights, demergers, or buybacks
- Dividends available via `ticker.dividends` (back-adjusted for splits)

**NSE API** — Dead (404 on all tested endpoints). Not usable.

### Implementation
1. **New table `corporate_actions`** — `symbol, date, action_type (split/bonus/dividend/spinoff/buyback), ratio_text, multiplier, ex_date, source (bse/yfinance), fetched_at`
2. **Extend `filing_client.py`** — add `fetch_corporate_actions(symbol)` using BSE API (reuse existing `get_bse_code()` and HTTP session)
3. **yfinance supplement** — fetch `ticker.splits` + `ticker.dividends` for deeper history, merge with BSE data
4. **Adjustment factor computation** — cumulative split/bonus multiplier for any date, applied to per-share metrics
5. **New tool: `get_corporate_actions(symbol)`** — returns action history
6. **New tool: `get_adjusted_eps(symbol)`** — returns EPS time series adjusted for all splits/bonuses
7. **Backfill** — run for Nifty 250 stocks

### Effort: Medium (3-4 hours)
BSE API is straightforward. Main complexity is merging BSE + yfinance data and computing cumulative adjustment factors.

### Files
- `filing_client.py` — extend with `fetch_corporate_actions()` (reuse BSE HTTP infra)
- `store.py` — new `corporate_actions` table + upsert/query methods
- `data_api.py` — new `get_corporate_actions()` + `get_adjusted_eps()` methods
- `tools.py` — new MCP tools
- `backfill-nifty250.py` — new step for corporate actions

---

## Fix 4: Segment-Level Revenue Tracking

> **Research complete.** Screener has a segment API but it's behind their Premium paywall (~$19/mo). FMP segment endpoints need a higher plan for Indian stocks. financial_schedules only has expense decomposition, not business segments.

### The Gap
Business agent describes segments qualitatively but doesn't track segment growth over time. Analysts track: "Segment A grew 25% and now contributes 60% of revenue vs 55% last year."

### What We Found

**Screener Segment API exists** — `GET /api/segments/{companyId}/{section}/{segtype}/`
- `section`: `quarters` (quarterly) or `profit-loss` (annual)
- `segtype`: `1` = product/business segments, `2` = geographic segments
- Returns HTML table with: Sales, Sales Growth %, Profit, Profit %, Profit Growth %, ROCE %, Capital Employed
- **Blocked: requires Screener Premium subscription** (~₹1500/mo or ~$19/mo)
- Coverage is good: RELIANCE (O2C, Retail, Digital Services, Oil & Gas), HDFCBANK (Retail Banking, Wholesale Banking, Treasury), etc.
- Some stocks have no segment data (ITC, INFY, MARUTI show empty tables)

**FMP Segmentation** — `/stable/revenue-product-segmentation` and `/stable/revenue-geographic-segmentation`
- Works for US stocks. Returns 402 for Indian stocks (.NS suffix) — needs higher FMP plan.

**Concall extraction** — schema already has `segment_breakdown` field but barely populated (only INDIAMART extracted, single-segment company). Multi-segment companies like RELIANCE would likely yield segment data if concalls were extracted.

**financial_schedules** — only has expense decomposition (Sales %, Manufacturing Cost %, Employee Cost %), NOT business segments.

### Options
1. **Screener Premium** (~₹1500/mo) — flip one flag, get clean quarterly + annual segment data via their API. Lowest effort, highest quality.
2. **Concall extraction** — already built, free. Extract concalls for more stocks; the LLM extractor would capture segment data from management discussion. Quality varies.
3. **BSE XBRL parsing** — segment reporting is mandatory in quarterly filings. Free but heavy engineering (XBRL parser).
4. **Skip for now** — focus on other fixes first, revisit when Screener Premium is justified.

### Recommendation: Option 4 (Skip) or Option 1 (Screener Premium)
This fix is either trivial (with Premium) or heavy engineering (without). Not worth building a custom XBRL parser. Concall extraction is a reasonable free path but won't give clean historical time series.

### Effort: Trivial with Screener Premium (1 hour) | Heavy without (10+ hours)

### Files (if Screener Premium)
- `screener_client.py` — new `fetch_segments(symbol, section, segtype)` method
- `store.py` — new `segment_revenue` table
- `data_api.py` — new `get_segment_breakdown(symbol)` method
- `tools.py` — new MCP tool

---

## Fix 5: Financial Projection Model

### The Gap
This is the biggest gap vs professional analysts. Our agents describe the past but don't project the future. A simple 3-year model:

```
Revenue projection: FY25 actual × (1 + growth assumption) for FY26/27/28
→ EBITDA = Revenue × margin assumption
→ PAT = EBITDA - Dep - Interest - Tax
→ EPS = PAT / shares outstanding
→ Fair value = EPS × target PE multiple
```

### Approach: Option C (Hybrid)

Code computes base projections from historical averages. Agent refines assumptions using qualitative context (concalls, management guidance). Best of both.

1. **New tool: `get_financial_projections(symbol)`** that:
   - Takes last 3 years of actual data from `annual_financials`
   - Computes base case: revenue CAGR → forward revenue, trailing margin → forward EBITDA
   - Computes bear case: half the growth, margin compression
   - Computes bull case: 1.5× growth, margin expansion
   - Returns: 3-year P&L projection with bear/base/bull for each year
2. **Agent interprets** — adjusts assumptions based on concall guidance, sector trends
3. **Valuation agent uses projections** for forward PE-based fair value

### Note on Agent Prompts
Current prompts (`prompts.py:440`) explicitly say "Never predict future prices." This needs reconciliation — projections provide *valuation ranges*, not price predictions. Update prompt to: "Use projection models for valuation ranges. Do not make point price predictions or timing calls."

### Dependencies
- Annual financials data must be populated (already done for most stocks)
- Corporate actions (Fix 3) needed for accurate forward EPS → shares outstanding must account for bonuses
- `get_fair_value()` already exists — projections should integrate with or extend it

### Effort: Medium (3-4 hours)
The math is simple. The art is choosing reasonable assumptions — which is why the hybrid approach works.

### Files
- New: `research/projections.py` — projection model
- `data_api.py` — new method
- `tools.py` — new tool
- `prompts.py` — update Valuation agent to use projections, reconcile "no predictions" language

---

## Implementation Order (Revised)

| # | Fix | Effort | Status | Dependencies |
|---|-----|--------|--------|-------------|
| 1 | **Comparable valuation matrix** | 1-2hr | ✅ Ready | None — data exists |
| 2 | **Corporate actions** | 3-4hr | ✅ Researched | BSE scrip codes (have them) |
| 3 | **Annual BS/CF surfacing** | 1hr | ✅ Ready | None — data already in DB |
| 4 | **Financial projections** | 3-4hr | ✅ Designable | Annual financials + corporate actions |
| 5 | **Segment revenue** | 1hr or 10+hr | ⛔ Blocked | Screener Premium subscription or heavy XBRL work |

**Start with Fix 1** (valuation matrix) — data already exists, just needs wiring. Then Fix 3 (annual BS/CF surfacing) is a quick win. Fix 2 (corporate actions) is the meatiest standalone task. Fix 4 (projections) builds on 2+3. Fix 5 (segments) is parked unless Screener Premium is purchased.

---

## Research Findings Log (2026-04-01)

### Screener Quarterly BS/CF: NOT AVAILABLE
- Screener.in does NOT provide quarterly Balance Sheet or Cash Flow data in any form
- HTML `#balance-sheet` section: annual dates + one trailing half-yearly snapshot (e.g., Sep 2025)
- HTML `#cash-flow` section: annual dates only, no half-yearly
- Excel export: QUARTERS section is P&L only; BALANCE SHEET and CASH FLOW sections are annual only
- Schedules API: `quarters/` only supports P&L parent items (Sales, Expenses, Other Income, Net Profit)
- For true quarterly BS (banks), alternative sources needed: BSE XBRL filings

### BSE Corporate Actions API: WORKING
- Endpoint: `https://api.bseindia.com/BseIndiaAPI/api/CorporateAction/w?scripcode={BSE_CODE}`
- Returns structured data with distinct action codes: DP (dividend), BN (bonus), SS (split), SO (spinoff), BGM (buyback)
- ~5 year history; Table1 (bonuses) has deeper history
- Does NOT capture rights issues
- Requires BSE scrip code (already implemented via `get_bse_code()`)

### yfinance Corporate Actions: PARTIAL
- `ticker.splits`: 30+ year history, captures splits AND bonuses as single multiplier (can't distinguish)
- `ticker.dividends`: back-adjusted for all splits
- No rights, demergers, or buybacks
- Some tickers fail (TATAMOTORS.NS returns 404)

### Screener EPS: RAW/UNADJUSTED
- Confirmed: RELIANCE EPS drops ~50% at each bonus date (Jun-2017: 30.78 → Sep-2017: 13.67)
- Revenue/NI are absolute (crores), unaffected. Only per-share metrics show discontinuity.
- Adjustment factors must be computed and applied by us.

### NSE Corporate Actions API: DEAD
- All tested endpoint variants return 404
- Quote API works fine with same session — endpoint genuinely removed/moved

### Screener Segment API: EXISTS BUT PREMIUM-GATED
- Endpoint: `/api/segments/{companyId}/{section}/{segtype}/`
- Returns quarterly + annual segment data with Sales, Profit, ROCE, Capital Employed
- Requires Screener Premium (~₹1500/mo)
- Good coverage for conglomerates (RELIANCE, HDFCBANK), empty for some stocks (ITC, INFY)

### Backfill Debugging (from previous session)

Three backfills failed and need investigation:

#### Estimates backfill: 0/250
- `step_estimates` in `backfill-nifty250.py` got 0 stocks
- Likely: yfinance `EstimatesClient.fetch_estimates()` API changed or needs different symbol format
- Debug: `uv run python -c "from flowtracker.estimates_client import EstimatesClient; ec = EstimatesClient(); print(ec.fetch_estimates('HDFCBANK'))"`

#### Screener backfill: 0/250
- `step_screener` in `backfill-nifty250.py` got 0 stocks
- Likely: Screener.in auth failure (needs login cookies) or rate limiting
- The `parse_quarterly_from_html` / `parse_annual_financials` imports may be wrong
- Debug: `uv run python -c "from flowtracker.screener_client import ScreenerClient; sc = ScreenerClient(); html = sc.fetch_company_page('HDFCBANK'); print(len(html))"`

#### Filing PDF batch download: 942 failures, 0 successful stocks
- `batch-download-filings.py` and `step_filings` in backfill script — BSE attachment URLs return empty
- Individual stock downloads work (HDFCBANK, INDIAMART downloaded fine when run directly)
- Batch run hits 942 "Empty or failed download" across all stocks
- **Root cause:** BSE historical attachment server is flaky for bulk requests. Older attachment UUIDs may be dead.
- **Fix options:**
  1. Add retry with exponential backoff per PDF
  2. Add User-Agent header + cookie preflight
  3. Rate limit more aggressively (currently 1s between stocks, but downloads within a stock are rapid-fire)
  4. Try `AttachLive` URL instead of `AttachHis` for recent filings
  5. Download in smaller batches (50 stocks at a time, not 250)
  6. Fall back to Screener.in document URLs
