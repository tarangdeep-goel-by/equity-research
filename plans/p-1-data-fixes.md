# P-1: Data & Tooling Fixes — Quick Wins

> Created: 2026-03-31
> Status: Ready for implementation
> Priority: Before P0 features — these make existing agents smarter
> Estimated total: 1-2 sessions

These are fundamental data gaps that a buy-side / sell-side analyst has but our agents don't. Fixing them doesn't require new agents or features — just scraping more data and exposing it via existing tools.

---

## Quick Reference

- **5 data gaps**, each independent — can be done in any order
- **No new agents needed** — existing agents get smarter automatically
- **No new prompts** — data flows through existing MCP tools
- Priority: Quarterly BS/CF (most impactful) → Comparable matrix → Corporate actions → Segment data → Financial model

---

## Fix 1: Quarterly Balance Sheet + Cash Flow

### The Gap
We have quarterly P&L (revenue, profit, margins) but NOT quarterly Balance Sheet or Cash Flow Statement. For banks (HDFCBANK, SBIN), quarterly BS is critical — NPA trends, provision coverage, CASA ratio, credit-deposit ratio are all BS items.

### What Screener Has
Screener.in shows quarterly BS and CF on the company page. Same HTML we already scrape for quarterly P&L. We're just not parsing those sections.

### Research Needed
- [ ] Check Screener HTML structure for quarterly BS section
- [ ] Check if Excel export (`warehouse_id` endpoint) includes quarterly BS/CF
- [ ] Check `parse_quarterly_from_html()` in `screener_client.py` — does it already see BS data and skip it?

### Implementation
1. **Extend `quarterly_results` table** — add BS columns: total_assets, total_equity, total_debt, cash_and_equivalents, net_worth, provisions (for banks: gross_npa_pct, net_npa_pct, pcr_pct, casa_pct)
2. **Extend `parse_quarterly_from_html()`** — parse the quarterly BS section
3. **OR create new table `quarterly_balance_sheet`** if too many columns
4. **Extend DataAPI** — `get_quarterly_results()` already returns this data if columns exist
5. **Agents automatically benefit** — Financial agent already calls `get_quarterly_results`

### Effort: Low-Medium (2-3 hours)
Main work is understanding Screener's HTML structure for quarterly BS.

### Files
- `screener_client.py` — extend parsing
- `store.py` — extend table or new table
- `data_api.py` — may not need changes if columns auto-flow

---

## Fix 2: Comparable Valuation Matrix

### The Gap
We compare PE and ROCE across peers via `get_peer_comparison` (Screener surface data). But analysts compare a full matrix: EV/EBITDA, EV/Sales, P/B, PEG, ROE, ROIC, debt/equity across 10+ peers. We have `valuation_snapshot` (yfinance) for every stock in Nifty 250 now — we just don't present it as a comparison.

### What We Already Have
- `valuation_snapshot` table: 504 stocks with PE, PB, EV/EBITDA, margins, beta, market cap
- `peer_comparison` table: peer names + symbols for any researched stock
- `get_peer_metrics` tool: reads FMP data (empty on free tier)

### Implementation
1. **Extend `get_peer_metrics()`** in `data_api.py` — ALSO read from `valuation_snapshot` table for each peer (yfinance data). Currently only reads FMP tables (which are empty).
2. **New tool: `get_valuation_matrix(symbol)`** — returns structured matrix: for each peer, pull PE, PB, EV/EBITDA, EV/Sales, margin, ROE from `valuation_snapshot`. Compute sector median, percentile for each metric.
3. **New chart: `valuation_heatmap`** — color-coded matrix showing which stocks are cheap on which metrics

### Effort: Low (1-2 hours)
Data already exists. Just need to query it differently and present as matrix.

### Files
- `data_api.py` — new `get_valuation_matrix()` method
- `tools.py` — new MCP tool
- `charts.py` — optional heatmap chart
- `prompts.py` — tell Valuation agent to use the matrix tool

---

## Fix 3: Corporate Actions History

### The Gap
Stock splits, bonuses, and rights issues affect per-share calculations. If RELIANCE did a 1:1 bonus in 2017, all pre-2017 EPS numbers need halving for comparison. Without adjusting, our historical EPS/BVPS trends are misleading.

### Research Needed
- [ ] BSE corporate actions API: `https://api.bseindia.com/BseIndiaAPI/api/CorporateAction/w?...`
- [ ] NSE corporate actions: `https://www.nseindia.com/api/corporateActions?index=equities&symbol=RELIANCE`
- [ ] Screener may already adjust for splits in their data — verify
- [ ] yfinance `ticker.actions` gives dividend + split history

### Implementation
1. **New table `corporate_actions`** — date, type (split/bonus/dividend/rights), ratio, ex_date
2. **New client method** — fetch from BSE/NSE API or yfinance
3. **Adjustment factor computation** — cumulative split/bonus factor for any date
4. **Apply to historical per-share data** — or flag in tools: "Note: unadjusted for 1:1 bonus in Sep 2017"

### Effort: Medium (3-4 hours)
Research phase is the bottleneck — need to verify which sources provide clean data and whether Screener already adjusts.

### Files
- New: `corporate_actions_client.py` or extend `filing_client.py`
- `store.py` — new table
- `data_api.py` — adjustment utility

---

## Fix 4: Segment-Level Revenue Tracking

### The Gap
Business agent describes segments qualitatively ("Busy Infotech contributes ~8% of revenue") but doesn't track segment growth over time. Analysts track: "Segment A grew 25% and now contributes 60% of revenue vs 55% last year."

### What Screener Has
Screener's annual report page shows segment revenue breakdown. The Excel export may include segment data. Annual reports (already downloaded as PDFs) contain detailed segment reporting.

### Research Needed
- [ ] Check Screener Excel export for segment tabs
- [ ] Check if `financial_schedules` table (already scraped) has segment data
- [ ] Check BSE filings for standalone segment disclosure (Reg 33)

### Implementation
1. **Check `financial_schedules` table** — we already scrape "Sales" and "Expenses" schedules from Screener. Segment revenue may be there.
2. **If not: new table `segment_revenue`** — symbol, segment, year, revenue, growth, pct_of_total
3. **New tool: `get_segment_breakdown(symbol)`** — returns segment-level data
4. **Business agent uses it** for revenue mix analysis

### Effort: Low-Medium (2 hours)
Depends on whether Screener already has segment data in schedules.

### Files
- `data_api.py` — new method or extend `get_expense_breakdown`
- `tools.py` — new tool if needed
- `store.py` — may not need changes if data is in `financial_schedules`

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

### Approach Options

**Option A: Agent-built model** — The Financial or Valuation agent builds a projection model in-context using historical data as base. Prompt instructs: "Project 3 years using conservative/base/aggressive growth assumptions." No new tools needed — agent does the math.

**Option B: Code-built model** — Python function takes historical data + assumptions, computes projections. More reliable math. Exposed as MCP tool `build_financial_model(symbol, revenue_growth, margin_assumptions)`.

**Option C: Hybrid** — Code computes base projections from historical averages. Agent refines assumptions using qualitative context (concalls, management guidance). Best of both.

### Recommendation: Option C (Hybrid)

1. **New tool: `get_financial_projections(symbol)`** that:
   - Takes last 3 years of actual data
   - Computes base case: revenue CAGR → forward revenue, trailing margin → forward EBITDA
   - Computes bear case: half the growth, margin compression
   - Computes bull case: 1.5× growth, margin expansion
   - Returns: 3-year P&L projection with bear/base/bull for each year
2. **Agent interprets** — adjusts assumptions based on concall guidance, sector trends
3. **Valuation agent uses projections** for forward PE-based fair value

### Effort: Medium (3-4 hours)
The math is simple. The art is choosing reasonable assumptions — which is why the hybrid approach works.

### Files
- New: `research/projections.py` — projection model
- `data_api.py` — new method
- `tools.py` — new tool
- `prompts.py` — update Valuation agent to use projections

---

## Implementation Order

| # | Fix | Effort | Impact | Dependencies |
|---|-----|--------|--------|-------------|
| 1 | **Comparable valuation matrix** | 1-2hr | High — every agent benefits from better peer data | Nifty 250 valuation backfill (done) |
| 2 | **Quarterly BS/CF** | 2-3hr | High — critical for banks/NBFCs | Research Screener HTML first |
| 3 | **Corporate actions** | 3-4hr | Medium — affects historical accuracy | Research BSE/NSE API first |
| 4 | **Segment revenue** | 2hr | Medium — enriches Business agent | Check if data exists in schedules |
| 5 | **Financial projections** | 3-4hr | Very High — biggest analyst gap | Needs quarterly + annual data |

**Start with Fix 1** (valuation matrix) — data already exists, just needs querying. Then Fix 2 (quarterly BS) after researching Screener HTML. Fix 5 (projections) is highest impact but needs the other data first.

---

## Backfill Debugging (from this session)

Three backfills failed and need investigation:

### Estimates backfill: 0/250
- `step_estimates` in `backfill-nifty250.py` got 0 stocks
- Likely: yfinance `EstimatesClient.fetch_estimates()` API changed or needs different symbol format
- Debug: `uv run python -c "from flowtracker.estimates_client import EstimatesClient; ec = EstimatesClient(); print(ec.fetch_estimates('HDFCBANK'))"`

### Screener backfill: 0/250
- `step_screener` in `backfill-nifty250.py` got 0 stocks
- Likely: Screener.in auth failure (needs login cookies) or rate limiting
- The `parse_quarterly_from_html` / `parse_annual_financials` imports may be wrong
- Debug: `uv run python -c "from flowtracker.screener_client import ScreenerClient; sc = ScreenerClient(); html = sc.fetch_company_page('HDFCBANK'); print(len(html))"`

### Filing PDF batch download: 942 failures, 0 successful stocks
- `batch-download-filings.py` and `step_filings` in backfill script — BSE attachment URLs return empty
- Individual stock downloads work (HDFCBANK, INDIAMART downloaded fine when run directly)
- Batch run hits 942 "Empty or failed download" across all stocks
- **Root cause:** BSE historical attachment server (`bseindia.com/xml-data/corpfiling/AttachHis/`) is flaky for bulk requests. Older attachment UUIDs may be dead. Server may rate-limit or block after N requests.
- **Fix options:**
  1. Add retry with exponential backoff per PDF (currently no retry)
  2. Add User-Agent header + cookie preflight (BSE may block bare requests)
  3. Rate limit more aggressively (currently 1s between stocks, but downloads within a stock are rapid-fire)
  4. Try `AttachLive` URL instead of `AttachHis` for recent filings (filing_client.py line 224-227 chooses based on `pdf_flag`)
  5. Download in smaller batches (50 stocks at a time, not 250)
  6. Fall back to Screener.in document URLs (from `company_documents` table) — these are the same PDFs but via Screener's CDN which may be more reliable
- **Debug:** `uv run python -c "from flowtracker.filing_client import FilingClient; fc = FilingClient(); f = fc.fetch_research_filings('RELIANCE'); print(len(f)); path = fc.download_filing(f[0]); print(path)"`
- **Note:** HDFCBANK (142 PDFs) and INDIAMART (20 concalls) downloaded fine when run individually outside the batch script. The issue is specific to bulk sequential downloads.
