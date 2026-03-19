# Fundamentals Module — Implementation Plan

## Design: Hybrid Fetch + Store

| Data | Approach | Why |
|------|----------|-----|
| Current ratios, price, profile | **Live fetch** (yfinance) | Stale instantly, cheap to get |
| Quarterly income results | **Store** in SQLite | Facts that don't change. Accumulates beyond yfinance's 8Q limit |
| Weekly valuation snapshots | **Store** in SQLite | Only way to build valuation bands over time |
| Peer comparison | **Live fetch** | Point-in-time comparison, no history needed |

All stored data lives in the existing `flows.db` alongside ownership data. Same `FlowStore` class, same patterns.

---

## Data Sources

### Primary: yfinance (live data + ongoing quarterly fetch)

Already proven in `stock-cli/stockcli/client.py`. We adapt that code.

- Ticker format: `SYMBOL.NS` (e.g., `TECHM.NS`)
- Quarterly income: `ticker.get_income_stmt(freq="quarterly")` — **~5 quarters only** (hard Yahoo API limit)
- Annual financials: `ticker.get_income_stmt(freq="yearly")` + `get_balance_sheet` + `get_cash_flow` — ~4 years
- Live ratios: `ticker.info` dict — P/E, P/B, EV/EBITDA, ROE, margins, D/E, etc.
- Price history: `ticker.history(period="10y", interval="1wk")` — 10yr weekly OHLCV
- No auth, no cookies, no scraping

### Backfill: Screener.in (10yr quarterly history)

yfinance only gives ~5 quarters. For 10yr (40Q) backfill, we use Screener.in's Excel export.

- **Excel export** contains a "Quarters" sheet with 10+ years of quarterly data
- Requires free Screener.in account (login + CSRF token)
- Fields: Sales, Expenses, Operating Profit, OPM%, Other Income, Interest, Depreciation, PBT, Tax%, Net Profit, EPS
- Rate limit: ~3s between requests (HTTP 429 if too fast)
- One-time bulk operation, not ongoing

---

## New Files

```
flowtracker/
  fund_client.py          # yfinance wrapper (adapted from stock-cli)
  fund_models.py          # Pydantic models for fundamentals data
  fund_commands.py        # CLI: flowtrack fund <subcommand>
  fund_display.py         # Rich formatting for fundamentals output
  screener_client.py      # Screener.in Excel export client (backfill only)

~/.claude/skills/markets/scripts/
  fundamental.py          # Skill script for /markets analyze integration
```

---

## DB Schema (added to `_SCHEMA` in store.py)

```sql
-- Quarterly income results (stored — accumulates history)
CREATE TABLE IF NOT EXISTS quarterly_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quarter_end TEXT NOT NULL,           -- "2025-12-31"
    revenue REAL,
    gross_profit REAL,
    operating_income REAL,
    net_income REAL,
    ebitda REAL,
    eps REAL,
    eps_diluted REAL,
    operating_margin REAL,              -- operating_income / revenue
    net_margin REAL,                    -- net_income / revenue
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, quarter_end)
);

-- Weekly valuation snapshots (stored — builds valuation bands)
CREATE TABLE IF NOT EXISTS valuation_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,                 -- "2026-03-19"
    price REAL,
    market_cap REAL,
    enterprise_value REAL,
    pe_trailing REAL,
    pe_forward REAL,
    pb_ratio REAL,
    ev_ebitda REAL,
    dividend_yield REAL,
    roe REAL,
    roa REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    free_cash_flow REAL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, date)
);
```

Two tables only. No annual_financials table — yfinance annual data is available live and we don't need multi-year balance sheet history for the initial use case. Can add later if needed.

---

## fund_client.py — yfinance Wrapper

Adapted from `stock-cli/stockcli/client.py`. Focused on what flow-tracker needs.

### Live Methods (no storage, called on demand)

```python
def get_live_snapshot(symbol: str) -> LiveSnapshot:
    """Current price, ratios, margins — for `fund show` and peer comparison."""
    # Calls ticker.info
    # Returns: price, market_cap, pe_trailing, pe_forward, pb, ev_ebitda,
    #          roe, roa, gross_margin, operating_margin, net_margin,
    #          debt_to_equity, current_ratio, dividend_yield, free_cash_flow,
    #          sector, industry, company_name

def get_live_peers(symbols: list[str]) -> list[LiveSnapshot]:
    """Batch live snapshots for peer comparison."""
    # Sequential with 0.5s delay to be polite to Yahoo
```

### Store Methods (fetched → persisted to SQLite)

```python
def fetch_quarterly_results(symbol: str) -> list[QuarterlyResult]:
    """Fetch quarterly income data from yfinance."""
    # Calls ticker.get_income_stmt(freq="quarterly")
    # Extracts: revenue, gross_profit, operating_income, net_income,
    #           ebitda, eps, eps_diluted
    # Computes: operating_margin, net_margin
    # Returns list of QuarterlyResult models

def fetch_valuation_snapshot(symbol: str) -> ValuationSnapshot:
    """Fetch today's valuation metrics for storage."""
    # Calls ticker.info
    # Returns: price, market_cap, enterprise_value, pe_trailing, pe_forward,
    #          pb_ratio, ev_ebitda, dividend_yield, roe, roa,
    #          debt_to_equity, current_ratio, free_cash_flow
```

### Symbol Mapping

```python
def nse_symbol(symbol: str) -> str:
    """Convert watchlist symbol to yfinance format."""
    # TECHM → TECHM.NS
    # M&M → M&M.NS
    # Special cases: BAJAJ-AUTO → BAJAJ-AUTO.NS (works as-is)
    return f"{symbol}.NS"
```

---

## fund_models.py — Pydantic Models

```python
class QuarterlyResult(BaseModel):
    symbol: str
    quarter_end: str            # "2025-12-31"
    revenue: float | None
    gross_profit: float | None
    operating_income: float | None
    net_income: float | None
    ebitda: float | None
    eps: float | None
    eps_diluted: float | None
    operating_margin: float | None
    net_margin: float | None

class ValuationSnapshot(BaseModel):
    symbol: str
    date: str                   # "2026-03-19"
    price: float | None
    market_cap: float | None
    enterprise_value: float | None
    pe_trailing: float | None
    pe_forward: float | None
    pb_ratio: float | None
    ev_ebitda: float | None
    dividend_yield: float | None
    roe: float | None
    roa: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    free_cash_flow: float | None

class LiveSnapshot(BaseModel):
    """Live data — never stored, fetched on demand."""
    symbol: str
    company_name: str | None
    sector: str | None
    industry: str | None
    price: float | None
    market_cap: float | None
    pe_trailing: float | None
    pe_forward: float | None
    pb_ratio: float | None
    ev_ebitda: float | None
    dividend_yield: float | None
    roe: float | None
    roa: float | None
    gross_margin: float | None
    operating_margin: float | None
    net_margin: float | None
    debt_to_equity: float | None
    current_ratio: float | None
    free_cash_flow: float | None
    revenue_growth: float | None
    earnings_growth: float | None

class ValuationBand(BaseModel):
    """Computed from stored snapshots — not stored itself."""
    symbol: str
    metric: str                 # "pe_trailing", "ev_ebitda", "pb_ratio"
    min_val: float
    max_val: float
    median_val: float
    current_val: float
    percentile: float           # 0-100, where current sits in historical range
    num_observations: int
    period_start: str
    period_end: str
```

---

## store.py — New Methods on FlowStore

```python
# -- Fundamentals: Quarterly Results --

def upsert_quarterly_results(self, results: list[QuarterlyResult]) -> int:
    """Insert or replace quarterly results. Audit-logged."""

def get_quarterly_results(self, symbol: str, limit: int = 12) -> list[QuarterlyResult]:
    """Get stored quarterly results, most recent first."""

def get_quarterly_results_range(self, symbol: str, from_qtr: str, to_qtr: str) -> list[QuarterlyResult]:
    """Get quarterly results within a date range."""

# -- Fundamentals: Valuation Snapshots --

def upsert_valuation_snapshot(self, snapshot: ValuationSnapshot) -> int:
    """Insert or replace a valuation snapshot. Audit-logged."""

def upsert_valuation_snapshots(self, snapshots: list[ValuationSnapshot]) -> int:
    """Batch insert valuation snapshots (weekly fetch for watchlist)."""

def get_valuation_history(self, symbol: str, days: int = 365) -> list[ValuationSnapshot]:
    """Get valuation snapshots for the last N days."""

def get_valuation_band(self, symbol: str, metric: str, days: int = 1095) -> ValuationBand | None:
    """Compute min/max/median/percentile for a metric over N days (default 3 years)."""
    # Pure SQL aggregation — no Python loop needed
    # SELECT MIN(pe_trailing), MAX(pe_trailing), ... FROM valuation_snapshot
    # WHERE symbol = ? AND date >= date('now', '-1095 days')
```

---

## fund_commands.py — CLI Commands

Registered as `flowtrack fund <subcommand>` via typer subapp, same as `holding`, `mf`, `scan`.

### `flowtrack fund fetch`

Bulk fetch for entire watchlist. Two operations:

1. **Quarterly results** — For each watchlist stock, fetch from yfinance and upsert
2. **Valuation snapshot** — For each watchlist stock, capture today's ratios

```
Options:
  -s, --symbol TEXT    Fetch for a single stock instead of full watchlist
  --quarters-only      Only fetch quarterly results (skip valuation)
  --valuation-only     Only fetch valuation snapshot (skip quarters)
```

Progress display: Rich progress bar showing `[12/52] TECHM...`

Rate limiting: 0.5s delay between stocks to avoid Yahoo throttling.

### `flowtrack fund show <SYMBOL>`

**Live fetch** — shows current state. No storage dependency.

```
╭──────────────────── TECHM — Tech Mahindra Ltd ────────────────────╮
│ Price: ₹1,842.50  |  Market Cap: ₹1.8L Cr  |  Sector: Technology │
│                                                                    │
│ Valuation           Profitability        Health                    │
│ P/E (TTM)    28.4   Gross Margin  38.2%  D/E        0.12         │
│ P/E (Fwd)    24.1   OPM          13.8%   Current    1.84         │
│ P/B           4.8   NPM          10.2%   FCF    ₹4,200 Cr       │
│ EV/EBITDA   18.2   ROE          22.1%                            │
│                     ROA          12.4%                            │
│                                                                    │
│ Growth                                                             │
│ Revenue     +8.2% YoY                                             │
│ Earnings   +15.4% YoY                                             │
╰──────────────────────────────────────────────────────────────────╯
```

### `flowtrack fund history <SYMBOL>`

**From storage** — quarterly earnings trajectory over time.

```
Options:
  -q, --quarters INT   Number of quarters to show (default: 8)
```

```
╭──────────────── TECHM — Quarterly Earnings Trajectory ────────────────╮
│ Quarter   Revenue(Cr)  Net Inc(Cr)  EPS    OPM%    NPM%   Rev Δ YoY  │
│ Dec 2025    14,820      1,512      15.4   13.8%   10.2%    +8.2%     │
│ Sep 2025    14,440      1,388      14.2   13.2%    9.6%    +7.1%     │
│ Jun 2025    14,100      1,290      13.2   12.8%    9.1%    +6.4%     │
│ Mar 2025    13,780      1,205      12.3   12.4%    8.7%    +5.8%     │
│ Dec 2024    13,700      1,150      11.7   11.9%    8.4%    +4.2%     │
│ Sep 2024    13,480      1,080      11.0   11.5%    8.0%    +3.8%     │
│ Jun 2024    13,250      1,020      10.4   11.2%    7.7%    +3.2%     │
│ Mar 2024    13,020        960       9.8   10.8%    7.4%    +2.1%     │
│                                                                        │
│ Trend: Revenue ↑ accelerating (2% → 8% YoY). Margins expanding.      │
╰────────────────────────────────────────────────────────────────────────╯
```

YoY growth is computed by comparing with same quarter in stored history (Q Dec 2025 vs Q Dec 2024). If only 8 quarters stored, first 4 won't have YoY.

### `flowtrack fund peers <SYMBOL>`

**Live fetch** — auto-detects sector from yfinance, compares with watchlist stocks in same sector.

```
Options:
  --with TEXT    Explicit peer list (comma-separated), overrides auto-detect
```

```
╭──────────────── IT Sector Peer Comparison (Live) ─────────────────╮
│              TECHM    INFY    HCLTECH   WIPRO     TCS             │
│ Price       1,842    1,620    1,980     298      4,180            │
│ MCap(LCr)    1.8      6.7      5.4      1.6      15.1            │
│ P/E          28.4     26.1     30.2     24.8      32.1            │
│ EV/EBITDA    18.2     17.5     19.8     15.9      22.4            │
│ P/B           4.8      8.2      7.1      3.2      14.8            │
│ ROE          22.1%    30.2%    25.8%    16.4%     44.1%           │
│ OPM          13.8%    21.2%    18.4%    14.2%     24.8%           │
│ NPM          10.2%    18.2%    15.4%    11.2%     19.8%           │
│ D/E           0.12     0.08     0.15     0.22      0.04           │
│ Rev Grw       8.2%     4.1%     6.8%     2.1%      5.4%          │
│ ── Ownership (from flow-tracker) ──────────────────────           │
│ FII%         17.9%    30.3%    16.2%    10.5%     10.4%           │
│ FII Δ QoQ    -2.7%    -0.5%    +0.3%    -1.1%     +0.2%          │
│ MF%          19.9%    22.1%     9.1%     4.9%      5.5%           │
│ MF Δ QoQ     +2.3%    +0.8%    -0.1%    +0.4%     -0.2%          │
╰───────────────────────────────────────────────────────────────────╯
```

This is the integration point — ownership data from flow-tracker's `shareholding` table, fundamentals live from yfinance, in one view.

### `flowtrack fund valuation <SYMBOL>`

**From storage** — requires accumulated weekly snapshots.

```
Options:
  --period TEXT   "1y", "2y", "3y" (default: 3y)
```

```
╭──────────────── TECHM — Valuation Band (3Y) ─────────────────╮
│                Min     25th    Median   75th    Max    Current │
│ P/E           18.2    22.1     25.4    30.8    38.1    28.4   │
│ EV/EBITDA     12.1    14.8     16.8    19.5    24.3    18.2   │
│ P/B            2.8     3.5      4.2     5.1     6.8     4.8   │
│                                                                │
│ P/E percentile: 62% — above median, below 75th                │
│ Assessment: Fair value zone. Not cheap, not expensive.         │
│ Buy zone: P/E < 22 (25th percentile)                          │
╰────────────────────────────────────────────────────────────────╯
```

**Note:** This command only works after enough weekly snapshots accumulate. On first use it will show limited data and warn: "Only N weeks of data. Valuation bands need 26+ weeks to be meaningful."

---

## Cron Jobs

Two new launchctl plists, same pattern as existing ones.

### Weekly Valuation Snapshot

**Schedule:** Every Sunday at 8:00 PM IST (after US markets close Friday, before Indian markets open Monday)
**Command:** `flowtrack fund fetch --valuation-only`
**Plist:** `com.flowtracker.fund-weekly`

### Quarterly Results Fetch

**Schedule:** 20th of Feb/May/Aug/Nov at 9:00 AM IST (after most results are filed, ~3 weeks into earnings season)
**Command:** `flowtrack fund fetch --quarters-only`
**Plist:** `com.flowtracker.fund-quarterly`

### Updated setup-crons.sh

Add two new plist names to the `PLISTS` array:
```bash
PLISTS=(
    "com.flowtracker.daily-fetch"
    "com.flowtracker.mf-monthly"
    "com.flowtracker.holdings-quarterly"
    "com.flowtracker.fund-weekly"        # NEW
    "com.flowtracker.fund-quarterly"     # NEW
)
```

Add schedule output:
```
echo "  fund-weekly          — Sundays at 8:00 PM IST"
echo "  fund-quarterly       — 20th of Feb/May/Aug/Nov at 9:00 AM IST"
```

### Cron Scripts

New scripts in `scripts/`:
```bash
# scripts/weekly-valuation.sh
#!/bin/bash
cd "$(dirname "$0")/.." && uv run flowtrack fund fetch --valuation-only >> ~/.local/share/flowtracker/cron.log 2>&1

# scripts/quarterly-results.sh
#!/bin/bash
cd "$(dirname "$0")/.." && uv run flowtrack fund fetch --quarters-only >> ~/.local/share/flowtracker/cron.log 2>&1
```

---

## Skill Integration

### New Script: `~/.claude/skills/markets/scripts/fundamental.py`

Called by the `/markets analyze` skill when fundamentals are requested.

```python
# Usage: uv run python ~/.claude/skills/markets/scripts/fundamental.py <SYMBOL>
# Output: JSON with live snapshot + stored quarterly history + valuation band

def main(symbol: str) -> dict:
    return {
        "live": get_live_snapshot(symbol),        # Current ratios, price
        "quarterly": get_stored_quarters(symbol), # From DB, up to 12Q
        "valuation_band": get_valuation_bands(symbol),  # From DB, P/E/EV-EBITDA/P-B bands
        "peers": get_sector_peers(symbol),        # Live peer comparison
    }
```

### Updated `/markets` Skill Routing

Add to the subcommand table:

| Input | Subcommand |
|-------|------------|
| `fundamentals <SYMBOL>` | `fundamentals` — pure fundamentals view |

And enhance `analyze <SYMBOL>` to call `fundamental.py` alongside `analyze.py`, combining both outputs.

### Enhanced `/markets analyze <SYMBOL>` Output

After the existing ownership arc (Acts 1-3), append:

```
### Earnings Trajectory
[From stored quarterly_results — revenue, EPS, margin trend over 8Q]

### Valuation Context
[From stored valuation_snapshot — P/E band, current percentile, peer rank]

### Combined Assessment
[Synthesis: ownership signals + earnings quality + valuation attractiveness]
```

### Enhanced `/markets screen` Output

After handoffs/red flags/crowding, add a new section:

```
### Fundamental Overlay
- Handoff stocks sorted by: cheapest P/E relative to own history
- Red flag stocks: are earnings also declining?
- Best setup: handoff + below-median P/E + growing earnings
```

This calls `fundamental.py` for each flagged stock from the ownership screen.

---

## Dependencies

Add to `flow-tracker/pyproject.toml`:
```toml
dependencies = [
    "typer>=0.9",
    "rich>=13",
    "pydantic>=2",
    "httpx>=0.27",
    "xlrd>=2",
    "openpyxl>=3",
    "yfinance>=0.2.40",   # NEW
]
```

---

## Implementation Tickets

### Ticket 1: Schema + Models (no dependencies)
- Add two new tables to `_SCHEMA` in `store.py`
- Create `fund_models.py` with `QuarterlyResult`, `ValuationSnapshot`, `LiveSnapshot`, `ValuationBand`
- **Verify:** `flowtrack --help` still works (schema migration is additive, no breakage)

### Ticket 2: yfinance Client (no dependencies)
- Create `fund_client.py`
- Adapt `_safe_get()` and ticker caching from `stock-cli/stockcli/client.py`
- Implement: `nse_symbol()`, `get_live_snapshot()`, `fetch_quarterly_results()`, `fetch_valuation_snapshot()`
- Add `yfinance>=0.2.40` to `pyproject.toml`
- **Verify:** `python -c "from flowtracker.fund_client import FundClient; print(FundClient().get_live_snapshot('TECHM'))"`

### Ticket 3: Store Methods (depends on T1)
- Add to `FlowStore`: `upsert_quarterly_results`, `get_quarterly_results`, `upsert_valuation_snapshot`, `upsert_valuation_snapshots`, `get_valuation_history`, `get_valuation_band`
- Follow existing patterns: audit logging on upsert, `INSERT OR REPLACE`, Row → model conversion
- **Verify:** Unit test — insert + retrieve round-trips correctly

### Ticket 4: Display (depends on T1)
- Create `fund_display.py`
- Functions: `display_live_snapshot()`, `display_quarterly_history()`, `display_peer_comparison()`, `display_valuation_band()`
- Rich panels/tables matching existing flow-tracker style
- **Verify:** Visual — renders correctly in terminal

### Ticket 5: CLI Commands (depends on T2, T3, T4)
- Create `fund_commands.py` with typer subapp
- Register in `main.py`: `app.add_typer(fund_app)`
- Commands: `fetch`, `show`, `history`, `peers`, `valuation`
- **Verify:**
  - `flowtrack fund fetch -s TECHM` — fetches and stores
  - `flowtrack fund show TECHM` — displays live snapshot
  - `flowtrack fund history TECHM` — displays stored quarters
  - `flowtrack fund peers TECHM` — displays IT peer comparison

### Ticket 6: Cron Jobs (depends on T5)
- Create `scripts/weekly-valuation.sh` and `scripts/quarterly-results.sh`
- Create launchctl plists: `com.flowtracker.fund-weekly.plist`, `com.flowtracker.fund-quarterly.plist`
- Update `scripts/setup-crons.sh`
- **Verify:** `launchctl list | grep flowtracker` shows 5 jobs

### Ticket 7: Skill Script + Integration (depends on T5)
- Create `~/.claude/skills/markets/scripts/fundamental.py`
- Update `/markets` skill definition to add `fundamentals` subcommand routing
- Enhance `analyze.py` to call `fundamental.py` and merge outputs
- Enhance `screen.py` to add fundamental overlay section
- **Verify:** `/markets analyze TECHM` includes earnings + valuation sections

### Dependency Graph

```
T1 (schema + models) ──┬── T3 (store methods) ──┐
                        │                         │
T2 (yfinance client) ──┤                         ├── T5 (CLI) ── T6 (crons)
                        │                         │               │
                        └── T4 (display) ─────────┘               T7 (skill)
```

**Parallel groups:**
- **Batch 1:** T1 + T2 (independent)
- **Batch 2:** T3 + T4 (independent, both depend on T1)
- **Batch 3:** T5 (depends on T2, T3, T4)
- **Batch 4:** T6 + T7 (independent, both depend on T5)

---

## Backfill Strategy — 10 Years

Two data streams to backfill, run once after the core module is built.

### Stream 1: Quarterly Results (Screener.in Excel Export)

**Goal:** 40 quarters of revenue, net income, EPS, margins for all watchlist stocks.

**Why not yfinance:** Yahoo's API returns max ~5 quarters (hard limit in their backend). No parameter to increase.

**How Screener.in Excel export works:**

```
1. Login (session + CSRF)
   POST https://www.screener.in/login/
   Body: csrfmiddlewaretoken=<token>&username=<email>&password=<pass>

2. Get company page, extract warehouse ID
   GET https://www.screener.in/company/TECHM/consolidated/
   Parse: regex formaction="\/user\/company\/export\/(\d+)\/"

3. Download Excel
   POST https://www.screener.in/user/company/export/{warehouseID}/
   Body: csrfmiddlewaretoken=<token>
   Returns: .xlsx file

4. Parse "Quarters" sheet
   Columns: Quarter dates (e.g., "Dec 2015", "Mar 2016", ...)
   Rows: Sales, Expenses, Operating Profit, OPM %, Other Income,
         Interest, Depreciation, PBT, Tax %, Net Profit, EPS
```

**New file: `screener_client.py`**

```python
class ScreenerClient:
    """Screener.in Excel export client for historical backfill."""

    def __init__(self, email: str, password: str):
        self.session = httpx.Client(follow_redirects=True, timeout=30)
        self._login(email, password)

    def _login(self, email: str, password: str) -> None:
        """Login and establish session cookies."""
        # GET /login/ → extract csrftoken from cookies
        # POST /login/ with credentials + CSRF

    def _get_warehouse_id(self, symbol: str) -> str:
        """Fetch company page, extract export warehouse ID."""
        # GET /company/{symbol}/consolidated/
        # Regex: formaction="\/user\/company\/export\/(\d+)\/"

    def download_excel(self, symbol: str) -> bytes:
        """Download the Excel export for a symbol."""
        # POST /user/company/export/{warehouseID}/

    def parse_quarterly_results(self, excel_bytes: bytes) -> list[QuarterlyResult]:
        """Parse the Quarters sheet into QuarterlyResult models."""
        # openpyxl: read "Quarters" sheet
        # Row 0: dates → quarter_end
        # Named rows: Sales → revenue, Operating Profit → operating_income,
        #             Net Profit → net_income, EPS → eps
        # Compute: operating_margin = operating_income / revenue
        #          net_margin = net_income / revenue

    def fetch_all(self, symbol: str) -> list[QuarterlyResult]:
        """Download + parse in one call. Rate-limited."""
        # Returns ~40 QuarterlyResult objects
```

**Mapping Screener.in fields → our schema:**

| Screener.in Row | Our Field | Notes |
|----------------|-----------|-------|
| Sales | `revenue` | In crores |
| Operating Profit | `operating_income` | |
| Net Profit | `net_income` | |
| EPS in Rs | `eps` | Basic EPS |
| OPM % | `operating_margin` | Already a percentage |
| — | `net_margin` | Compute: net_income / revenue |
| — | `ebitda` | Not directly available; compute: operating_income + depreciation |
| — | `gross_profit` | Not available from Screener.in |
| — | `eps_diluted` | Not available; use `eps` as fallback |

**Rate limiting:** 3-second delay between stocks. For 50 watchlist stocks = ~2.5 minutes total.

**Credentials:** Stored in `~/.config/flowtracker/screener.env` (not committed to git):
```
SCREENER_EMAIL=your@email.com
SCREENER_PASSWORD=yourpassword
```

### Stream 2: Historical Valuation Bands (Computed)

**Goal:** Weekly P/E, EV/EBITDA, P/B snapshots going back 10 years. Enables `flowtrack fund valuation` to work immediately with full history.

**Approach:** Compute historical P/E from two inputs:
1. **Weekly closing prices** — yfinance `history(period="10y", interval="1wk")` (free, no limit)
2. **Quarterly EPS** — from stored `quarterly_results` (backfilled via Stream 1)

**Algorithm:**

```python
def compute_historical_pe(symbol: str, weekly_prices: DataFrame, quarterly_eps: list[QuarterlyResult]) -> list[ValuationSnapshot]:
    """
    For each weekly price point:
    1. Find the 4 most recent quarters with EPS data as of that date
    2. TTM EPS = sum of those 4 quarters' EPS
    3. P/E = weekly_close / TTM_EPS
    4. Create a ValuationSnapshot with date, price, pe_trailing
    """
    snapshots = []
    for date, close in weekly_prices.iterrows():
        # Find quarters ending on or before this date
        relevant_quarters = [q for q in quarterly_eps if q.quarter_end <= date][-4:]
        if len(relevant_quarters) < 4:
            continue  # Not enough history yet
        ttm_eps = sum(q.eps for q in relevant_quarters if q.eps)
        if ttm_eps <= 0:
            continue  # Negative/zero EPS → skip
        pe = close / ttm_eps
        snapshots.append(ValuationSnapshot(
            symbol=symbol, date=date.isoformat(),
            price=close, pe_trailing=pe,
            # Other fields (pb, ev_ebitda) left None for historical —
            # we can't reliably compute these from price alone
        ))
    return snapshots
```

**What we CAN backfill:** P/E (price / TTM EPS) — reliable, computed from two known inputs.

**What we CANNOT backfill:** EV/EBITDA, P/B, ROE, D/E — these need balance sheet data at each point in time. yfinance annual balance sheets only go back 4 years. Screener.in has annual balance sheets for 10yr but matching weekly price × quarterly book value is fragile.

**Decision:** Backfill P/E only. EV/EBITDA and P/B bands accumulate from weekly cron going forward. After a year of cron, we'll have 52 data points — enough for 1yr bands.

### Backfill CLI Command

```bash
# Full backfill — runs both streams
flowtrack fund backfill

# Backfill single stock
flowtrack fund backfill -s TECHM

# Only quarterly results (Screener.in)
flowtrack fund backfill --quarters-only

# Only historical valuation (computed P/E from stored quarters + yfinance prices)
flowtrack fund backfill --valuation-only
```

**Flow:**

```
flowtrack fund backfill
  │
  ├─ Step 1: Screener.in quarterly results
  │   ├─ Login to Screener.in (reads ~/.config/flowtracker/screener.env)
  │   ├─ For each watchlist stock:
  │   │   ├─ Download Excel export
  │   │   ├─ Parse "Quarters" sheet → list[QuarterlyResult]
  │   │   ├─ Upsert into quarterly_results table
  │   │   └─ Sleep 3s (rate limit)
  │   └─ Report: "Backfilled 40Q for 50 stocks (2,000 records)"
  │
  └─ Step 2: Historical valuation (computed)
      ├─ For each watchlist stock:
      │   ├─ Fetch 10yr weekly prices from yfinance
      │   ├─ Load quarterly EPS from DB (stored in step 1)
      │   ├─ Compute weekly TTM P/E for each week
      │   ├─ Upsert into valuation_snapshot table
      │   └─ Sleep 0.5s
      └─ Report: "Computed 520 weekly P/E snapshots for 50 stocks (26,000 records)"
```

**Total runtime estimate:** ~5 minutes (2.5 min Screener.in + 2.5 min yfinance price history).

**Storage estimate:** ~28,000 rows across both tables. At ~200 bytes/row = ~5.5 MB. Negligible.

### Prerequisites

1. User creates a free Screener.in account
2. Credentials saved to `~/.config/flowtracker/screener.env`
3. Core module (Tickets 1-5) must be complete before backfill

---

## Ongoing Data Flow (Post-Backfill)

After backfill, the system maintains itself:

| Trigger | Source | What Gets Stored |
|---------|--------|-----------------|
| **Weekly cron** (Sunday 8PM IST) | yfinance `ticker.info` | `valuation_snapshot`: P/E, EV/EBITDA, P/B, ROE, D/E, price |
| **Quarterly cron** (20th of Feb/May/Aug/Nov) | yfinance `get_income_stmt` | `quarterly_results`: revenue, net income, EPS, margins |
| **`fund show`** (on demand) | yfinance `ticker.info` | Nothing — live only |
| **`fund peers`** (on demand) | yfinance `ticker.info` | Nothing — live only |

Over time:
- Quarterly results accumulate beyond the initial 40Q backfill (41Q, 42Q, ...)
- Valuation snapshots build richer bands (P/E bands from backfill, EV/EBITDA and P/B bands from weekly cron)

---

## Updated Implementation Tickets

### Ticket 1: Schema + Models (no dependencies)
- Add two new tables to `_SCHEMA` in `store.py`
- Create `fund_models.py` with `QuarterlyResult`, `ValuationSnapshot`, `LiveSnapshot`, `ValuationBand`
- **Verify:** `flowtrack --help` still works (schema migration is additive, no breakage)

### Ticket 2: yfinance Client (no dependencies)
- Create `fund_client.py`
- Adapt `_safe_get()` and ticker caching from `stock-cli/stockcli/client.py`
- Implement: `nse_symbol()`, `get_live_snapshot()`, `fetch_quarterly_results()`, `fetch_valuation_snapshot()`
- Add `yfinance>=0.2.40` to `pyproject.toml`
- **Verify:** `python -c "from flowtracker.fund_client import FundClient; print(FundClient().get_live_snapshot('TECHM'))"`

### Ticket 3: Store Methods (depends on T1)
- Add to `FlowStore`: `upsert_quarterly_results`, `get_quarterly_results`, `upsert_valuation_snapshot`, `upsert_valuation_snapshots`, `get_valuation_history`, `get_valuation_band`
- Follow existing patterns: audit logging on upsert, `INSERT OR REPLACE`, Row → model conversion
- **Verify:** Unit test — insert + retrieve round-trips correctly

### Ticket 4: Display (depends on T1)
- Create `fund_display.py`
- Functions: `display_live_snapshot()`, `display_quarterly_history()`, `display_peer_comparison()`, `display_valuation_band()`
- Rich panels/tables matching existing flow-tracker style
- **Verify:** Visual — renders correctly in terminal

### Ticket 5: CLI Commands (depends on T2, T3, T4)
- Create `fund_commands.py` with typer subapp
- Register in `main.py`: `app.add_typer(fund_app)`
- Commands: `fetch`, `show`, `history`, `peers`, `valuation`
- **Verify:**
  - `flowtrack fund fetch -s TECHM` — fetches and stores
  - `flowtrack fund show TECHM` — displays live snapshot
  - `flowtrack fund history TECHM` — displays stored quarters
  - `flowtrack fund peers TECHM` — displays IT peer comparison

### Ticket 6: Screener.in Backfill Client (no dependencies)
- Create `screener_client.py` with login, warehouse ID extraction, Excel download, Quarters sheet parsing
- Add `beautifulsoup4>=4.12` to dependencies (for warehouse ID parsing)
- Credential loading from `~/.config/flowtracker/screener.env`
- **Verify:** `python -c "from flowtracker.screener_client import ScreenerClient; c = ScreenerClient(); print(len(c.fetch_all('TECHM')))"` → ~40 records

### Ticket 7: Historical P/E Computation (depends on T3, T6)
- Function: `compute_historical_pe(symbol, weekly_prices, quarterly_eps) → list[ValuationSnapshot]`
- Uses yfinance `history(period="10y", interval="1wk")` for prices
- Uses stored quarterly EPS for TTM computation
- Handles edge cases: negative EPS, missing quarters, stock splits
- **Verify:** Computed P/E values are reasonable (10-50x for large-cap Indian IT)

### Ticket 8: Backfill CLI Command (depends on T5, T6, T7)
- Add `backfill` subcommand to `fund_commands.py`
- Options: `-s/--symbol`, `--quarters-only`, `--valuation-only`
- Rich progress bar: `[12/50] TECHM — 40Q fetched, 520 P/E snapshots computed`
- **Verify:** `flowtrack fund backfill -s TECHM && flowtrack fund history TECHM -q 40` shows 10yr

### Ticket 9: Cron Jobs (depends on T5)
- Create `scripts/weekly-valuation.sh` and `scripts/quarterly-results.sh`
- Create launchctl plists: `com.flowtracker.fund-weekly.plist`, `com.flowtracker.fund-quarterly.plist`
- Update `scripts/setup-crons.sh`
- **Verify:** `launchctl list | grep flowtracker` shows 5 jobs

### Ticket 10: Skill Script + Integration (depends on T5)
- Create `~/.claude/skills/markets/scripts/fundamental.py`
- Update `/markets` skill definition to add `fundamentals` subcommand routing
- Enhance `analyze.py` to call `fundamental.py` and merge outputs
- Enhance `screen.py` to add fundamental overlay section
- **Verify:** `/markets analyze TECHM` includes earnings + valuation sections

### Dependency Graph

```
T1 (schema + models) ──┬── T3 (store) ───────────┬── T5 (CLI) ─── T9 (crons)
                        │                          │       │
T2 (yfinance client) ──┤                          │       ├── T8 (backfill CLI)
                        │                          │       │
                        └── T4 (display) ──────────┘       └── T10 (skill)
                                                   │
T6 (screener client) ─────────────────── T7 (hist P/E) ── T8
```

**Parallel groups:**
- **Batch 1:** T1 + T2 + T6 (all independent)
- **Batch 2:** T3 + T4 + T7 (T3/T4 depend on T1; T7 depends on T3+T6)
- **Batch 3:** T5 (depends on T2, T3, T4)
- **Batch 4:** T8 + T9 + T10 (all depend on T5; T8 also depends on T7)

---

## Open Decisions (deferred)

1. **Sector peer auto-detection:** Start with yfinance's `sector` field. If grouping is too broad (e.g., "Technology" includes IT services + semiconductors), we can hard-code peer groups later.
2. **NSE XBRL financial results:** The NSE `/api/top-corp-info` endpoint has `financial_results` with XBRL attachments. Could fill gaps where Screener.in or yfinance data is missing. Deferred.
3. **Composite scoring weights:** The signal framework (handoff + cheap + growing = buy) needs weight tuning. Start with equal weights and iterate.
4. **EV/EBITDA and P/B backfill:** If we later want 10yr bands for these metrics too, we'd need Screener.in's annual balance sheet data (book value, total debt) to compute historical P/B and EV/EBITDA. Currently only P/E is backfilled.
5. **Screener.in Excel "Data Sheet":** The export may also contain annual P&L, Balance Sheet, and Cash Flow sheets. If we parse those too, we get 10yr annual data for free. Could enable annual financials tracking without a separate table. Explore during T6 implementation.
