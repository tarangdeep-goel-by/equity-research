# FlowTracker Platform — What We Have

*Last updated: 2026-03-30*

---

## What This Is

An Indian equity research platform — CLI tools for tracking institutional flows, screening stocks, and generating AI-powered research reports. Built for buy-side analysis: forming independent conviction on stocks using the same data institutional analysts at Nomura or Goldman have access to.

**Stack:** Python 3.12 · SQLite (795 MB) · Typer CLI · Rich terminal UI · Claude Agent SDK · 14 data sources · 30 tables · 85+ commands

**Location:** `~/Documents/Projects/equity-research/flow-tracker`
**Database:** `~/.local/share/flowtracker/flows.db`
**Vault:** `~/vault/stocks/{SYMBOL}/` (thesis reports, filings, concall PDFs)

---

## Platform Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        USER ENTRY POINTS                            │
├──────────────┬──────────────┬───────────────┬───────────────────────┤
│  /markets    │  /research   │  flowtrack    │  screener_clone.py    │
│  (skill)     │  (skill)     │  (CLI)        │  (standalone)         │
│              │              │               │                       │
│  pulse       │  thesis ────→│  research     │  Full Screener.in     │
│  screen      │  fundamentals│   thesis      │  HTML clone           │
│  score       │              │   fundamentals│                       │
│  sector      │              │   data        │                       │
│  ownership   │              │               │                       │
│  fundamentals│              │  85 other     │                       │
│  cashflow    │              │  commands     │                       │
│  macro       │              │               │                       │
│  refresh     │              │               │                       │
└──────┬───────┴──────┬───────┴───────┬───────┴───────────────────────┘
       │              │               │
       ▼              ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      DATA ACCESS LAYER                              │
├─────────────────────────────────────────────────────────────────────┤
│  ResearchDataAPI (research/data_api.py) — 26 methods                │
│  Single unified interface for all data. Used by:                    │
│    • AI agent (26 MCP tools)                                        │
│    • research data CLI                                              │
│    • /markets skill scripts                                         │
│    • HTML report generator                                          │
├─────────────────────────────────────────────────────────────────────┤
│  _clean() helper in utils.py — JSON-safe serialization              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FlowStore                                   │
│                   store.py (~2300 lines)                             │
│                   ~92 methods, 30 tables                            │
├─────────────────────────────────────────────────────────────────────┤
│  SQLite: ~/.local/share/flowtracker/flows.db (795 MB)               │
└─────────────────────────────────────────────────────────────────────┘
       ▲                     ▲                        ▲
       │                     │                        │
┌──────┴──────┐  ┌───────────┴──────────┐  ┌─────────┴───────────────┐
│  CRONS (6)  │  │  refresh_for_research │  │  14 Fetch Clients       │
│  LaunchAgent│  │  (5-source live fetch  │  │  NSE, Screener, AMFI,   │
│  daily 7pm  │  │   for single stock)   │  │  yfinance, BSE, SEBI,   │
│  weekly     │  │  Called by thesis cmd  │  │  CCIL, mfapi.in         │
│  monthly x2 │  │  before agent runs    │  │                         │
│  quarterly  │  │                       │  │  screener_client.py     │
│  x2         │  │                       │  │  (1232 lines, 11 APIs)  │
└─────────────┘  └───────────────────────┘  └─────────────────────────┘
```

### How the AI Research Agent Works

```
flowtrack research thesis -s HDFCBANK
        │
        ▼
  refresh_for_research(HDFCBANK)          ← Layer 1: DATA
  ├── Screener.in → quarterly, annual, ratios, charts, peers,
  │                  shareholders, schedules → SQLite
  ├── yfinance    → valuation snapshot, consensus, surprises → SQLite
  ├── NSE         → insider trades, delivery, deals → SQLite
  ├── Macro       → VIX, USD/INR, crude, G-sec → SQLite
  └── BSE         → corporate filings → SQLite
        │
        ▼
  Agent SDK spawns Claude subprocess      ← Layer 2: AGENT
  ├── System prompt: analysis framework + output format
  ├── 26 MCP tools → ResearchDataAPI → FlowStore → SQLite
  └── max_turns=30
        │
        ▼
  Claude multi-turn loop (10-20 turns):
  T1:  get_company_info → "HDFC Bank, Banking"
  T2:  get_quarterly_results → 12 quarters of P&L
  T3:  get_annual_financials → 10 years
  T4:  get_shareholding_changes → FII -2%, MF +1.5%
  T5:  "FII selling — let me check insider activity..."
       get_insider_transactions → ...
  T6:  get_delivery_trend → 58% avg delivery
  T7:  get_peer_comparison → cheapest PE in banking
  ...
  T15: get_composite_score → 78/100
  T16: Writes full Markdown report
        │
        ▼
  ~/vault/stocks/HDFCBANK/thesis/2026-03-30.md    ← Layer 3: OUTPUT
  + reports/hdfcbank-thesis.md
```

---

## Database — 30 Tables, 4.5M+ Records

| Table | Rows | Symbols | Latest | Source | Cron |
|-------|-----:|--------:|--------|--------|------|
| **daily_stock_data** | 3,702,157 | 3,025 | 2026-03-30 | NSE bhavcopy | daily |
| **mf_scheme_holdings** | 344,889 | — | 2026-02 | AMFI (5 AMCs) | monthly (12th) |
| **insider_transactions** | 312,963 | 2,339 | 2026-03-30 | NSE SAST | daily |
| **shareholding** | 74,448 | 503 | 2026-03-16 | NSE XBRL | quarterly (15th) |
| **commodity_prices** | 16,320 | 4 | 2026-03-30 | yfinance | daily |
| **quarterly_results** | 13,441 | 500 | 2025-12-31 | Screener.in | quarterly (20th) |
| **promoter_pledge** | 10,915 | 495 | 2026-03-13 | NSE XBRL | quarterly (15th) |
| **daily_flows** | 9,836 | — | 2026-03-27 | NSE FII/DII | daily |
| **audit_log** | 9,078 | 473 | — | Internal | auto |
| **screener_ratios** | 4,846 | 467 | 2025-12-31 | Screener.in | quarterly (20th) |
| **macro_daily** | 4,755 | — | 2026-03-30 | yfinance | daily |
| **mf_monthly_flows** | 4,375 | — | 2026-02 | AMFI | monthly (6th) |
| **gold_etf_nav** | 3,341 | — | 2026-03-27 | mfapi.in | daily |
| **valuation_snapshot** | 2,899 | 500 | 2026-03-30 | yfinance | daily |
| **annual_financials** | 2,280 | 499 | 2025-12-31 | Screener.in | quarterly (20th) |
| **consensus_estimates** | 1,000 | 503 | 2026-03-29 | yfinance | weekly (Sun) |
| **index_constituents** | 600 | 500 | — | NSE | quarterly |
| **corporate_filings** | 479 | 1 | 2026-03-23 | BSE | quarterly (20th) |
| **earnings_surprises** | 408 | 408 | — | yfinance | weekly (Sun) |
| **mf_aum_summary** | 94 | — | 2026-02 | AMFI | monthly (6th) |
| **company_documents** | 70 | 1 | — | Screener.in | on-demand |
| **financial_schedules** | 43 | 1 | 2026-03-30 | Screener.in | on-demand |
| **mf_daily_flows** | 28 | — | 2026-03-20 | SEBI | daily |
| **peer_comparison** | 8 | 1 | 2026-03-30 | Screener.in | on-demand |
| **company_profiles** | 1 | 1 | — | Screener.in | on-demand |
| **screener_ids** | 1 | 1 | — | Screener.in | cached |
| **bulk_block_deals** | 0 | — | — | NSE | daily |
| **shareholder_detail** | 0 | — | — | Screener.in | on-demand |
| **screener_charts** | 0 | — | — | Screener.in | on-demand |
| **watchlist** | 0 | — | — | User | manual |

**Total:** ~4.5M rows across 30 tables. DB size: 795 MB.

---

## 14 Data Sources — Source Authority Map

Each data type has exactly one authoritative source. No overlaps, no conflicts.

| Data Type | Authority | Why Not The Other |
|-----------|-----------|-------------------|
| Quarterly/annual financials | **Screener.in** | Indian GAAP, normalized by Screener |
| P/E history (TTM) | **Screener.in** | Historical time series, yfinance only has current day |
| Growth rates | **Screener.in** | Computed from their own financial data |
| Chart data (PE/PBV/EV/margins) | **Screener.in** | Historical, no yfinance equivalent |
| Efficiency ratios (debtor days, ROCE) | **Screener.in** | Derived from annual BS/PL |
| Peers comparison | **Screener.in** | Standardized peer table |
| Live valuation snapshot | **yfinance** | Real-time price, PE, PB, EV/EBITDA, beta |
| Analyst consensus & targets | **yfinance** | Bloomberg-sourced via Yahoo Finance |
| Earnings surprises | **yfinance** | Actual vs estimate EPS |
| FII/DII daily flows | **NSE** | Only source for institutional flows |
| Shareholding patterns | **NSE** | XBRL quarterly filings, only source |
| Insider/SAST trades | **NSE** | Regulatory filings, only source |
| Delivery % (bhavcopy) | **NSE** | Only source for delivery data |
| Bulk/block deals | **NSE** | Only source |
| MF monthly flows & AUM | **AMFI** | Direct from regulator |
| MF scheme holdings | **AMFI** | Direct from AMC filings |
| Gold/silver prices | **yfinance** | Standard commodity prices |
| Gold ETF NAVs | **mfapi.in** | Indian ETF NAVs |
| Macro (VIX, FX, crude, G-sec) | **yfinance** | Standard market data |
| Corporate filings (concalls, results) | **BSE** | PDF filings repository |

### Screener.in API Endpoints

Screener has two IDs per company:
- `data-company-id` → Charts, Schedules, Shareholders APIs
- `data-warehouse-id` → Peers, Excel Export APIs

Full reference: `docs/screener-api-map.md`

### Authentication

- **NSE:** Cookie preflight (hit reports page → get cookies → API call). No credentials needed.
- **Screener.in:** Login required. Creds at `~/.config/flowtracker/screener.env`
- **All others:** Public APIs, no auth.

---

## CLI Commands — 16 Command Groups

### Quick Reference

```bash
cd ~/Documents/Projects/equity-research/flow-tracker
uv sync                                    # install deps
uv run flowtrack <command>                 # run any command
```

### Research (most used)

```bash
# AI-powered thesis — fully automated, 10-20 min
uv run flowtrack research thesis -s INDIAMART

# Data-only HTML report (with concall analysis)
uv run flowtrack research fundamentals -s INDIAMART

# Query any single data tool (JSON output)
uv run flowtrack research data shareholding_changes -s INDIAMART
uv run flowtrack research data quarterly_results -s INDIAMART
uv run flowtrack research data valuation_snapshot -s INDIAMART
```

### Screening & Scoring

```bash
uv run flowtrack screen top -n 20                    # Top 20 composite score
uv run flowtrack screen top --factor ownership -n 15  # Filter by factor
uv run flowtrack screen score INDIAMART               # Single stock scorecard
```

### Institutional Flows

```bash
uv run flowtrack fetch                 # Today's FII/DII
uv run flowtrack summary               # Latest day summary
uv run flowtrack flows -p 30d          # 30-day history
uv run flowtrack streak                # Current buying/selling streaks
```

### Ownership

```bash
uv run flowtrack holding fetch -s INDIAMART -q 12    # 12 quarters
uv run flowtrack scan refresh                         # Nifty 250 batch
uv run flowtrack scan deviations                      # Biggest ownership changes
uv run flowtrack scan deviations --handoff            # FII→MF handoff signals
```

### Fundamentals

```bash
uv run flowtrack fund backfill -s INDIAMART           # Screener quarterly + annual
uv run flowtrack fund charts -s INDIAMART -t pe       # PE chart data
uv run flowtrack fund peers -s INDIAMART              # Peer comparison
```

### Market Data

```bash
uv run flowtrack macro summary                        # VIX, FX, crude, G-sec
uv run flowtrack bhavcopy fetch                       # Today's OHLCV + delivery
uv run flowtrack bhavcopy top-delivery -n 20          # Highest delivery stocks
uv run flowtrack bhavcopy delivery INDIAMART -d 30    # Stock delivery trend
```

### Insider & Deals

```bash
uv run flowtrack insider fetch -d 30                  # 30 days of SAST filings
uv run flowtrack insider promoter-buys -d 30          # Promoter buying (highest conviction)
uv run flowtrack deals fetch                          # Today's bulk/block deals
```

### Estimates & MF

```bash
uv run flowtrack estimates stock INDIAMART             # Consensus for a stock
uv run flowtrack estimates upside                      # Ranked by upside to target
uv run flowtrack mfport stock INDIAMART                # Which MFs hold this stock
uv run flowtrack mfport top-buys                       # Biggest MF buys this month
```

### Filings

```bash
uv run flowtrack filings fetch INDIAMART --download -y 3   # Fetch + download PDFs
# PDFs saved to ~/vault/stocks/INDIAMART/filings/FY26-Q3/concall.pdf
```

### Standalone Tools

```bash
# Full Screener.in HTML clone (fetches all public data, renders HTML)
uv run python tools/screener_clone.py INDIAMART
```

---

## Claude Skills (Conversational Interface)

### /markets — Daily Market Research

```
/markets              → pulse (institutional mood + macro)
/markets screen       → composite multi-factor ranking
/markets score SYM    → full scorecard for a stock
/markets sector       → sector rotation overview
/markets ownership SYM → institutional ownership arc
/markets fundamentals SYM → earnings + valuation + peers
/markets cashflow SYM → 10yr business quality
/markets macro        → VIX, FX, crude, G-sec
/markets refresh      → update all data sources
```

### /research — Deep-Dive Reports

```
/research thesis SYM        → AI-powered research thesis (automated)
/research fundamentals SYM  → document-grounded fundamentals report (concall + data)
```

---

## ResearchDataAPI — 26 Methods

The unified data access layer. Every tool the AI agent uses, and every query the skills make.

### Core Financials
| Method | Returns |
|--------|---------|
| `get_quarterly_results(symbol, quarters=12)` | Quarterly P&L: revenue, expenses, OPM, NI, EPS |
| `get_annual_financials(symbol, years=10)` | Annual P&L + Balance Sheet + Cash Flow |
| `get_screener_ratios(symbol, years=10)` | Debtor days, inventory days, CCC, ROCE% |
| `get_expense_breakdown(symbol)` | Schedule sub-item breakdowns |

### Valuation
| Method | Returns |
|--------|---------|
| `get_valuation_snapshot(symbol)` | 50+ fields: price, PE, PB, EV/EBITDA, margins, beta |
| `get_valuation_band(symbol, metric, days=2500)` | Historical percentile band (min/25th/median/75th/max) |
| `get_pe_history(symbol, days=2500)` | P/E and price time series for charting |
| `get_chart_data(symbol)` | Screener chart datasets (PE, PBV, EV, margins, price+DMA) |

### Ownership & Institutional
| Method | Returns |
|--------|---------|
| `get_shareholding(symbol, quarters=12)` | FII, DII, MF, Promoter, Public % by quarter |
| `get_shareholding_changes(symbol)` | QoQ changes for latest quarter |
| `get_shareholder_detail(symbol)` | Named shareholders: Vanguard, LIC, etc. |
| `get_insider_transactions(symbol)` | SAST trades with person, category, value |
| `get_mf_holdings(symbol)` | MF scheme holdings: scheme name, qty, % NAV |
| `get_mf_holding_changes(symbol)` | MoM changes in MF holdings |
| `get_promoter_pledge(symbol)` | Quarterly pledge % history |
| `get_bulk_block_deals(symbol)` | Large institutional trades |

### Market Data
| Method | Returns |
|--------|---------|
| `get_delivery_trend(symbol, days=90)` | Daily delivery % from bhavcopy |
| `get_fii_dii_flows(days=30)` | Daily net institutional flows |
| `get_fii_dii_streak()` | Current buying/selling streak length |
| `get_macro_snapshot()` | VIX, USD/INR, Brent, 10Y G-sec |

### Estimates & Filings
| Method | Returns |
|--------|---------|
| `get_consensus_estimate(symbol)` | Target price, recommendation, forward PE |
| `get_earnings_surprises(symbol)` | Actual vs estimate EPS, surprise % |
| `get_recent_filings(symbol)` | BSE corporate filings list |

### Scoring & Context
| Method | Returns |
|--------|---------|
| `get_company_info(symbol)` | Company name and industry |
| `get_peer_comparison(symbol)` | Peer table: CMP, PE, MCap, ROCE |
| `get_composite_score(symbol)` | 8-factor score (0-100) |

---

## Cron Schedule — Fully Automated

All managed via macOS LaunchAgents. Scripts at `~/.local/share/flowtracker/scripts/`.

| Cron | Schedule | What It Fetches |
|------|----------|-----------------|
| **daily-fetch** | Weekdays 7pm IST | FII/DII flows, gold/silver, MF daily, macro (VIX/FX/crude/G-sec), bhavcopy (3K stocks OHLCV + delivery), bulk/block deals, insider trades, valuation snapshots (500 stocks) |
| **weekly-valuation** | Sunday 2:30pm | Consensus estimates + earnings surprises (500 stocks, ~3min) |
| **monthly-mf** | 6th of month | AMFI monthly category flows + AUM |
| **monthly-mfportfolio** | 12th of month | MF scheme-level holdings from 5 AMCs (SBI, HDFC, ICICI Pru, Kotak, Axis) |
| **quarterly-scan** | 15th of Jan/Apr/Jul/Oct | Nifty 250 shareholding patterns + promoter pledges |
| **quarterly-results** | 20th of month | Screener.in quarterly/annual financials, screener ratios (500 stocks), BSE filings for watchlist |

### Cron Log

```bash
tail -50 ~/.local/share/flowtracker/cron.log
```

### Manual Refresh

```bash
# All daily sources
bash ~/.local/share/flowtracker/scripts/daily-fetch.sh

# Single stock (before research)
uv run flowtrack research thesis -s SYMBOL
# ↑ refresh_for_research() runs automatically
```

---

## Composite Screener — 8-Factor Scoring

The screener ranks all Nifty 500 stocks on 8 factors:

| Factor | Weight | What It Measures | Signal |
|--------|--------|------------------|--------|
| **Ownership** | 15% | MF accumulation, FII→MF handoff | Smart money moving in |
| **Insider** | 15% | Promoter buying at market price | Highest conviction signal |
| **Valuation** | 15% | Forward PE vs historical, analyst upside | Price vs value gap |
| **Earnings** | 15% | Surprise %, consecutive beats | Positive momentum |
| **Quality** | 10% | ROCE, cash conversion, D/E | Business fundamentals |
| **Delivery** | 10% | Avg delivery %, trend | Genuine accumulation vs churn |
| **Estimates** | 10% | Recommendation trend, coverage | Sell-side consensus |
| **Risk** | 10% | Promoter pledge, FII crowding | Downside flags |

---

## File Structure

```
flow-tracker/
├── flowtracker/
│   ├── main.py                  # Typer app, registers 16 subcommand groups
│   ├── store.py                 # FlowStore class (SQLite, ~92 methods, 30 tables)
│   ├── utils.py                 # Shared helpers: fmt_crores, _clean, parse_period
│   ├── screener_client.py       # Screener.in HTTP client (11 API methods)
│   ├── screener_engine.py       # 8-factor composite scoring engine
│   │
│   ├── fund_client.py           # yfinance wrapper
│   ├── fund_models.py           # Pydantic models
│   ├── fund_commands.py         # fund CLI subcommands
│   ├── fund_display.py          # Rich table formatting
│   │
│   ├── holding_client.py        # NSE XBRL shareholding
│   ├── insider_client.py        # NSE SAST insider trades
│   ├── bhavcopy_client.py       # NSE daily OHLCV + delivery
│   ├── deals_client.py          # NSE bulk/block deals
│   ├── mf_client.py             # AMFI monthly flows
│   ├── commodity_client.py      # Gold/silver via yfinance
│   ├── macro_client.py          # VIX, FX, crude, G-sec
│   ├── filing_client.py         # BSE corporate filings
│   ├── mfportfolio_client.py    # MF scheme holdings from AMCs
│   ├── estimates_client.py      # yfinance consensus/surprises
│   │
│   ├── *_commands.py            # Typer subcommands (one per module)
│   ├── *_display.py             # Rich table formatters (one per module)
│   ├── *_models.py              # Pydantic models (one per module)
│   │
│   └── research/
│       ├── agent.py             # Claude Agent SDK — spawns research subprocess
│       ├── prompts.py           # System prompt with analysis framework
│       ├── tools.py             # 26 MCP tool functions (@tool decorated)
│       ├── data_api.py          # ResearchDataAPI — 26 methods wrapping FlowStore
│       ├── data_collector.py    # HTML report data collector (legacy path)
│       └── refresh.py           # refresh_for_research() — 5-source live fetch
│
├── scripts/                     # Cron shell wrappers
├── tools/
│   └── screener_clone.py        # Standalone Screener.in HTML report generator
├── docs/
│   ├── screener-api-map.md      # All Screener.in API endpoints
│   └── data-source-comparison.md # Source authority per data type
├── reports/                     # Generated HTML/MD reports
├── CLAUDE.md                    # Claude Code guidance
└── pyproject.toml               # uv managed, Python 3.12+
```

---

## Consolidation Changelog (2026-03-30)

### Bug Fixes
- Fixed `fund_commands.py:370` — was calling `fetch_chart_data(company_id, chart_type)` with wrong signature. Changed to `fetch_chart_data_by_type()`.

### Code Consolidation
- Renamed `fetch_chart_data_single()` → `fetch_chart_data_by_type()` (deprecated alias kept)
- Moved `_clean()` from data_api.py + data_collector.py → utils.py (single definition, imported by both)
- Removed 3 unused store methods: `get_mf_daily_flows`, `get_symbols_with_quarter`, `get_insider_recent`
- Rewrote 4 standalone market scripts (analyze.py, fundamental.py, cashflow.py, screen.py) to use ResearchDataAPI instead of FlowStore directly

### Documentation
- Created `docs/screener-api-map.md` — all Screener.in API endpoints
- Created `docs/data-source-comparison.md` — source authority per data type
- Updated `/research` skill — thesis marked operational, removed stale subcommands
- Updated `/markets` skill — ownership/fundamentals/cashflow use ResearchDataAPI as primary source

### Infrastructure
- Verified all 6 LaunchAgent crons running (daily-fetch confirmed working 2026-03-30 19:47)
- Added screener_ratios backfill to quarterly-results.sh (559/600 stocks populated)
- Added BSE filings fetch to quarterly-results.sh (watchlist stocks)
- Synced updated cron scripts to `~/.local/share/flowtracker/scripts/`
- Backfilled insider trades to current (5,290 new records)
