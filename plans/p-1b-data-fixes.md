# P-1B: Data Fixes Round 2 — Analyst Parity

> Created: 2026-04-01
> Status: Ready for implementation
> Priority: After P-1A (done) — these close remaining analyst data gaps
> Estimated total: 1 session (5-7 hours)
> Depends on: P-1A complete (valuation matrix, corporate actions, projections — all done)

Four data gaps that professional analysts have but our agents don't. Each uses yfinance data we're not currently scraping. No new paid subscriptions needed.

---

## Quick Reference

- **4 features**, all independent — can be done in any order
- **No new data sources** — all from yfinance (already a dependency)
- **No new agents** — existing agents get smarter automatically
- Priority: Estimate revisions (highest impact) → Quarterly BS/CF → Events calendar → Dividend history

---

## Fix 6: Estimate Revision Momentum

### The Gap
Our agents know "consensus EPS is ₹51" but not "consensus was ₹48 three months ago and has been revised up by 4 analysts." Estimate revision momentum is one of the strongest short-term signals — when analysts are revising up in unison, the stock typically follows.

### What yfinance Provides (Researched & Verified)

**`ticker.eps_trend`** — EPS estimates at 5 time points for 4 periods:

| Period | Meaning |
|--------|---------|
| `0q` | Current quarter |
| `+1q` | Next quarter |
| `0y` | Current fiscal year |
| `+1y` | Next fiscal year |

Columns: `current`, `7daysAgo`, `30daysAgo`, `60daysAgo`, `90daysAgo`

Example (HDFCBANK):
```
        current  7daysAgo  30daysAgo  60daysAgo  90daysAgo
0q        11.78     11.78      12.40      12.40      12.40
+1q       12.86     12.86      12.86      12.71      12.71
0y        51.30     50.00      50.00      49.35      48.30
+1y       57.10     55.80      56.87      56.60      56.30
```

**`ticker.eps_revisions`** — Up/down revision counts:
```
        upLast7days  upLast30days  downLast30days  downLast7Days
0q                0             0               1              1
+1q               1             1               0              0
0y                1             4               1              1
+1y               2             1               4              2
```

**Coverage:** Verified working for HDFCBANK, RELIANCE, TCS, SBIN. Should work for most Nifty 250 stocks with analyst coverage.

### Implementation

#### 1. New `fetch_estimate_revisions(symbol)` method — add to yfinance fetching

Could go in `estimates_client.py` (already exists for yfinance estimate data) or `fund_client.py`. Returns:
```python
{
    "symbol": "HDFCBANK",
    "eps_trend": {
        "0q": {"current": 11.78, "7d_ago": 11.78, "30d_ago": 12.40, "60d_ago": 12.40, "90d_ago": 12.40},
        "+1q": {...},
        "0y": {...},
        "+1y": {...},
    },
    "eps_revisions": {
        "0q": {"up_7d": 0, "up_30d": 0, "down_30d": 1, "down_7d": 1},
        ...
    },
    "momentum_signal": "positive",  # computed: positive/neutral/negative
    "momentum_score": 0.72,  # 0-1 scale
}
```

**Momentum score computation:**
```python
# For each period, compute revision direction
# Weight: 0y and +1y matter more than 0q
# Score = weighted average of (current - 90d_ago) / 90d_ago across periods
# Positive = estimates trending up, Negative = trending down
# Also factor in up/down revision counts (net positive = bullish)
```

#### 2. New table `estimate_revisions` in store.py

```sql
CREATE TABLE IF NOT EXISTS estimate_revisions (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,  -- when we fetched this snapshot
    period TEXT NOT NULL,  -- '0q', '+1q', '0y', '+1y'
    eps_current REAL,
    eps_7d_ago REAL,
    eps_30d_ago REAL,
    eps_60d_ago REAL,
    eps_90d_ago REAL,
    revisions_up_7d INTEGER,
    revisions_up_30d INTEGER,
    revisions_down_7d INTEGER,
    revisions_down_30d INTEGER,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, date, period)
)
```

Store snapshots daily (via cron) to build our own revision history over time. yfinance only gives current + lookback, but if we store daily, we can chart revision trends.

#### 3. New data_api methods

```python
def get_estimate_revisions(self, symbol: str) -> dict:
    """Latest EPS estimate trends and revision counts for all periods."""

def get_estimate_momentum(self, symbol: str) -> dict:
    """Computed momentum signal: score (0-1), direction (positive/neutral/negative),
    and narrative ('FY26 estimates revised up 6% in 90 days, 4 upgrades vs 1 downgrade')."""
```

#### 4. MCP tools + agent prompts

- Register both tools
- Add to: `VALUATION_AGENT_TOOLS`, `FINANCIAL_AGENT_TOOLS`, `RESEARCH_TOOLS`
- Update Valuation agent prompt Phase 3 (Analyst & Consensus): "Call `get_estimate_momentum` to check if analysts are revising estimates up or down. Rising estimates + rising price = fundamental momentum. Rising estimates + flat price = potential re-rating setup."

#### 5. Backfill step

Add `step_estimate_revisions` to `backfill-nifty250.py` — fetch for all 250 stocks. Also add to daily cron for ongoing snapshots.

### Effort: 2-3 hours
Straightforward yfinance → store → data_api → tools pipeline.

### Files
- `estimates_client.py` or `fund_client.py` — new fetch method
- `store.py` — new table + upsert/query methods
- `data_api.py` — `get_estimate_revisions()`, `get_estimate_momentum()`
- `tools.py` — 2 new MCP tools
- `prompts.py` — update Valuation agent prompt
- `backfill-nifty250.py` — new step

---

## Fix 7: Quarterly Balance Sheet + Cash Flow (yfinance)

### The Gap
Screener doesn't have quarterly BS/CF (confirmed in P-1A research). But yfinance does — for many stocks. Quarterly BS is critical for banks (debt levels, equity changes) and useful for all companies (working capital shifts, cash position).

### What yfinance Provides (Researched & Verified)

**Quarterly Balance Sheet coverage:**

| Stock | Quarters | Key Fields (of 6) | Notes |
|-------|----------|-------------------|-------|
| HDFCBANK | 4 | 4/6 | Missing: Receivables, Inventory (normal for banks) |
| SBIN | 5 | 4/6 | Same pattern as HDFCBANK |
| ICICIBANK | 5 | 4/6 | Same |
| INFY | 6 | 4/6 | Strong coverage |
| BHARTIARTL | 4 | 4/6 | Good |
| TCS | 3 | 5/6 | Missing Receivables |
| BAJFINANCE | 3 | 4/6 | Good |
| MARUTI | 2 | 5/6 | Limited quarters |
| RELIANCE | 3 | 0/6 | All NaN — yfinance broken for this stock |
| KOTAKBANK | 3 | 0/6 | All NaN |

**Key BS fields available (59 total, important ones):**
- `Total Assets`, `Total Debt`, `Stockholders Equity`, `Common Stock Equity`
- `Cash And Cash Equivalents`, `Net PPE`, `Investments And Advances`
- `Ordinary Shares Number`, `Share Issued`, `Net Debt`
- `Total Liabilities Net Minority Interest`, `Long Term Debt`

**Quarterly Cash Flow coverage:**

| Stock | Quarters | Notes |
|-------|----------|-------|
| INFY | 4 | Full: OCF, FCF, CapEx, ICF, FCF, working capital changes |
| BHARTIARTL | 4 | Full |
| TCS | 2 | Good |
| HDFCBANK | 0 | Not available |
| SBIN | 0 | Not available |
| RELIANCE | 0 | Not available |
| Banks generally | 0 | yfinance doesn't provide quarterly CF for Indian banks |

**CF fields (39 total when available):**
- `Operating Cash Flow`, `Free Cash Flow`, `Capital Expenditure`
- `Investing Cash Flow`, `Financing Cash Flow`
- `Change In Working Capital`, `Change In Receivables`, `Change In Payables`
- `Depreciation And Amortization`, `Stock Based Compensation`
- `Cash Dividends Paid`, `Net Income From Continuing Operations`

**Values are in raw INR (not crores).** Need to convert: divide by 1e7 to get crores.

### Implementation

#### 1. New fetch method in `fund_client.py`

```python
def fetch_quarterly_bs_cf(self, symbol: str) -> dict:
    """Fetch quarterly balance sheet and cash flow from yfinance.
    Returns {'balance_sheet': [list of quarter dicts], 'cash_flow': [list of quarter dicts]}
    Values converted from raw INR to crores.
    """
```

Convert all values: `value / 1e7` to match Screener's crore convention. Skip NaN fields.

Normalize field names to snake_case matching our conventions:
- `Total Assets` → `total_assets`
- `Stockholders Equity` → `stockholders_equity`
- `Cash And Cash Equivalents` → `cash_and_equivalents`
- `Operating Cash Flow` → `operating_cash_flow`
- etc.

#### 2. New tables in store.py

```sql
CREATE TABLE IF NOT EXISTS quarterly_balance_sheet (
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    total_assets REAL,
    total_debt REAL,
    long_term_debt REAL,
    stockholders_equity REAL,
    cash_and_equivalents REAL,
    net_debt REAL,
    investments REAL,
    net_ppe REAL,
    shares_outstanding REAL,
    total_liabilities REAL,
    minority_interest REAL,
    source TEXT DEFAULT 'yfinance',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, quarter_end)
)

CREATE TABLE IF NOT EXISTS quarterly_cash_flow (
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,
    operating_cash_flow REAL,
    free_cash_flow REAL,
    capital_expenditure REAL,
    investing_cash_flow REAL,
    financing_cash_flow REAL,
    change_in_working_capital REAL,
    depreciation REAL,
    dividends_paid REAL,
    net_income REAL,
    source TEXT DEFAULT 'yfinance',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, quarter_end)
)
```

#### 3. New data_api methods

```python
def get_quarterly_balance_sheet(self, symbol: str, quarters: int = 8) -> list[dict]:
    """Quarterly balance sheet: assets, debt, equity, cash, investments."""

def get_quarterly_cash_flow(self, symbol: str, quarters: int = 8) -> list[dict]:
    """Quarterly cash flow: OCF, FCF, capex, ICF, FCF, working capital changes.
    Note: not available for all stocks (banks typically missing)."""
```

#### 4. MCP tools + agent prompts

- Register both tools
- Add to: `FINANCIAL_AGENT_TOOLS`, `RISK_AGENT_TOOLS`, `RESEARCH_TOOLS`
- Update Financial agent prompt: "Call `get_quarterly_balance_sheet` for intra-year balance sheet changes. For banks, track quarterly debt and equity changes. For all companies, monitor cash position and working capital shifts. Note: quarterly CF is not available for all stocks — if empty, rely on annual CF from `get_annual_financials`."

#### 5. Backfill step

Add `step_quarterly_bs_cf` to backfill script. Expect ~70-80% of stocks to have BS data, ~20-30% to have CF data.

### Effort: 2 hours
Standard yfinance pipeline. Main work is field name normalization and INR→crore conversion.

### Files
- `fund_client.py` — new fetch method
- `store.py` — 2 new tables + upsert/query methods
- `data_api.py` — 2 new methods
- `tools.py` — 2 new MCP tools
- `prompts.py` — update Financial agent
- `backfill-nifty250.py` — new step

---

## Fix 8: Events Calendar

### The Gap
Analysts always know when the next earnings date is, when the ex-dividend date is, and what the street expects. Our agents operate without this temporal context — they can't say "earnings in 3 days, consensus expects ₹12 EPS" or "stock goes ex-dividend on July 25."

### What yfinance Provides (Researched & Verified)

**`ticker.calendar`** — works for all tested Indian stocks:
```python
{
    'Ex-Dividend Date': datetime.date(2025, 7, 25),
    'Earnings Date': [datetime.date(2026, 4, 18)],
    'Earnings High': 11.78,     # EPS estimate high
    'Earnings Low': 11.78,      # EPS estimate low
    'Earnings Average': 11.78,  # EPS consensus
    'Revenue High': 471300000000,
    'Revenue Low': 471300000000,
    'Revenue Average': 471300000000,
}
```

### Implementation

#### 1. New fetch method

Add to `fund_client.py` or `estimates_client.py`:
```python
def fetch_events_calendar(self, symbol: str) -> dict:
    """Fetch upcoming events: earnings date, ex-dividend date, consensus estimates."""
```

#### 2. New table (optional — could be ephemeral)

Events are forward-looking and change frequently. Two options:
- **Option A: No table** — fetch live each time the tool is called. Simple, always fresh.
- **Option B: Cache table** with short TTL — avoid hammering yfinance during multi-agent runs.

**Recommendation: Option A** (no table). Events change; caching adds complexity for little benefit. Each research run makes ~1 call per stock.

#### 3. New data_api method

```python
def get_events_calendar(self, symbol: str) -> dict:
    """Upcoming events: next earnings date (with days until), ex-dividend date,
    consensus EPS/revenue estimates for next quarter.
    
    Returns:
    {
        'symbol': 'HDFCBANK',
        'next_earnings': '2026-04-18',
        'days_to_earnings': 17,
        'earnings_estimate': {'high': 11.78, 'low': 11.78, 'avg': 11.78},
        'revenue_estimate_cr': {'high': 47130, 'low': 47130, 'avg': 47130},
        'ex_dividend_date': '2025-07-25',
        'days_since_ex_dividend': 250,
    }
    """
```

Convert revenue estimates from raw INR to crores.

#### 4. MCP tool + agent prompts

- Register tool, add to: `VALUATION_AGENT_TOOLS`, `RESEARCH_TOOLS`
- Update Research system prompt Phase 2: "Call `get_events_calendar` to check upcoming catalysts. If earnings are within 2 weeks, note this prominently. If stock recently went ex-dividend, factor into recent price action analysis."

### Effort: 1 hour
Simplest of the four — no table needed, just fetch→format→expose.

### Files
- `fund_client.py` or `estimates_client.py` — new fetch method
- `data_api.py` — new method
- `tools.py` — new MCP tool
- `prompts.py` — minor prompt update

---

## Fix 9: Dividend Yield History + Payout Ratio

### The Gap
Our agents know the current dividend yield (from `valuation_snapshot`) but can't show how it evolved over time. A declining payout ratio might signal management reinvesting for growth; a rising one might signal a maturing business. Dividend yield at a 5-year high is a classic value signal.

### What We Already Have

- **`corporate_actions` table**: 5,446 dividend records across 196 stocks (from P-1A backfill). yfinance dividends are per-share (split-adjusted). BSE dividends are face-value (unadjusted).
- **`annual_financials` table**: `dividend_amount` column — but this is TOTAL dividends (₹Cr), NOT per-share. Causes 36,000% payout ratios when divided by EPS.
- **`valuation_snapshot` table**: `dividend_yield` (current, from yfinance) and `price` (daily).

### The Data Problem

Need per-share dividend to compute:
- **Payout ratio** = per-share dividend / EPS
- **Historical yield** = per-share annual dividend / price at that time

**Source for per-share dividend:** yfinance `ticker.dividends` (already in corporate_actions with source='yfinance'). These are split-adjusted. Sum per fiscal year for annual per-share dividend.

### Implementation

#### 1. New data_api methods

```python
def get_dividend_history(self, symbol: str, years: int = 10) -> list[dict]:
    """Annual dividend per share, yield, and payout ratio history.
    
    Computes from corporate_actions (yfinance dividends = split-adjusted per-share)
    + annual_financials (EPS) + valuation_snapshot (price for yield).
    
    Returns per FY:
    {
        'fiscal_year': 'FY25',
        'annual_dividend_per_share': 19.5,
        'eps': 46.26,
        'payout_ratio_pct': 42.1,
        'price_at_fy_end': 1580,
        'dividend_yield_pct': 1.23,
        'dividend_growth_yoy_pct': 15.2,
    }
    """
```

**Logic:**
1. Get yfinance dividends from `corporate_actions` WHERE source='yfinance' AND action_type='dividend'
2. Group by fiscal year (Apr-Mar): dividends with ex_date in Apr 2024–Mar 2025 → FY25
3. Sum per-share dividends per FY
4. Get EPS from `annual_financials` per FY → payout ratio
5. Get FY-end price from `valuation_snapshot` or `annual_financials.price` → yield
6. Compute YoY dividend growth

#### 2. MCP tool + agent prompts

- Register `get_dividend_history` tool
- Add to: `VALUATION_AGENT_TOOLS`, `FINANCIAL_AGENT_TOOLS`, `RESEARCH_TOOLS`
- Update Valuation agent: "Call `get_dividend_history` for income-oriented analysis. A rising payout ratio in a mature business is a positive signal. Dividend yield at 5-year highs can indicate value. Compare payout ratio against peers using `get_valuation_matrix`."

#### 3. No new table needed

Computed from existing tables (corporate_actions + annual_financials + valuation_snapshot). No storage required.

### Effort: 1-2 hours
Pure computation on existing data. No new fetching.

### Files
- `data_api.py` — new method
- `tools.py` — new MCP tool
- `prompts.py` — minor prompt update

---

## Implementation Order

| # | Fix | Effort | Impact | Dependencies |
|---|-----|--------|--------|-------------|
| 1 | **Estimate revision momentum** | 2-3hr | Very High — strongest short-term signal | None |
| 2 | **Quarterly BS/CF** | 2hr | High — banks + working capital | None |
| 3 | **Events calendar** | 1hr | Medium — temporal context | None |
| 4 | **Dividend yield history** | 1-2hr | Medium — value signal | Corporate actions backfill (done) |

All 4 are independent. Can be parallelized.

**Total new tools:** +6 MCP tools (estimate_revisions, estimate_momentum, quarterly_bs, quarterly_cf, events_calendar, dividend_history)
**Total after P-1B:** 43 + 6 = 49 MCP tools

---

## Research Findings Log (2026-04-01)

### yfinance Quarterly Balance Sheet
- Works for ~70-80% of Nifty 250 stocks (confirmed: HDFCBANK, SBIN, ICICIBANK, INFY, BHARTIARTL, TCS, BAJFINANCE, MARUTI)
- Fails (all NaN) for: RELIANCE, KOTAKBANK — possibly yfinance data gaps
- 59 fields per quarter, 2-6 quarters of history
- Values in raw INR — must divide by 1e7 for crores
- Banks naturally missing: Receivables, Inventory (not applicable)

### yfinance Quarterly Cash Flow
- Only available for ~20-30% of stocks (confirmed: INFY 4Q, BHARTIARTL 4Q, TCS 2Q)
- NOT available for most banks (HDFCBANK, SBIN, ICICIBANK), RELIANCE, MARUTI
- When available: 39 fields including OCF, FCF, CapEx, working capital changes, dividends paid
- Values in raw INR

### yfinance EPS Trend + Revisions
- Works for all tested stocks (4/4: HDFCBANK, RELIANCE, TCS, SBIN)
- 4 periods × 5 time points = 20 data points per stock
- Revision counts (up/down in 7d/30d) available for all 4 periods
- Data is fresh (reflects current analyst consensus movement)

### yfinance Events Calendar
- Works for all tested stocks (5/5)
- Returns: next earnings date, ex-dividend date, EPS consensus (high/low/avg), revenue consensus
- Revenue values in raw INR
