# FlowTracker

Indian equity research platform. Tracks institutional flows, screens stocks, and generates AI-powered research reports — the same data stack a sell-side analyst at Nomura uses, built for independent buy-side analysis.

**85+ CLI commands | 14 data sources | 30 SQLite tables | 4.5M+ records | Fully automated crons**

---

## Quick Start

```bash
cd flow-tracker
uv sync
uv run flowtrack research thesis -s HDFCBANK   # full AI research report
uv run flowtrack screen top -n 20               # top 20 stocks by composite score
uv run flowtrack summary                        # today's FII/DII flows
```

---

## How It Works

```
                    ┌─────────────┐
                    │  You ask:   │
                    │  "Analyze   │
                    │  HDFCBANK"  │
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │   refresh_for_research  │
              │   Fetches live data     │
              │   from 5 sources        │
              └────────────┬────────────┘
                           │
        ┌──────────┬───────┼───────┬──────────┐
        ▼          ▼       ▼       ▼          ▼
   Screener.in  yfinance  NSE    Macro      BSE
   financials   valuation flows  VIX/FX   filings
   charts       consensus insider crude    concalls
   peers        surprises delivery G-sec
   ratios
        │          │       │       │          │
        └──────────┴───────┼───────┴──────────┘
                           ▼
              ┌────────────────────────┐
              │     SQLite (795 MB)    │
              │     30 tables          │
              └────────────┬───────────┘
                           │
              ┌────────────▼────────────┐
              │   Claude Agent (SDK)    │
              │   26 MCP tools          │
              │   10-20 turn analysis   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │   Markdown thesis       │
              │   with conviction,      │
              │   risks, and targets    │
              └─────────────────────────┘
```

The AI agent doesn't just summarize — it reasons across data sources. It sees FII selling, checks if insiders are buying, cross-references delivery data, compares peer valuations, and forms a view.

---

## What You Can Do

### Research a Stock

```bash
# Full AI thesis — the agent pulls all data, reasons across it, writes a report
uv run flowtrack research thesis -s INDIAMART
# → ~/vault/stocks/INDIAMART/thesis/2026-03-30.md

# Document-grounded fundamentals — reads concall PDFs, cites page numbers
uv run flowtrack research fundamentals -s INDIAMART
# → reports/indiamart-fundamentals.html

# Query any data point directly
uv run flowtrack research data shareholding_changes -s INDIAMART
uv run flowtrack research data valuation_snapshot -s INDIAMART
```

### Screen for Ideas

```bash
# Composite score across 8 factors (ownership, insider, valuation, earnings, quality, delivery, estimates, risk)
uv run flowtrack screen top -n 20

# Filter by what matters to you
uv run flowtrack screen top --factor ownership -n 15   # smart money accumulating
uv run flowtrack screen top --factor insider -n 15      # promoters buying
uv run flowtrack screen top --factor delivery -n 15     # high conviction trading

# Deep scorecard for one stock
uv run flowtrack screen score INDIAMART
```

### Track Institutional Money

```bash
uv run flowtrack fetch && uv run flowtrack summary      # today's FII/DII
uv run flowtrack streak                                  # buying/selling streaks
uv run flowtrack flows -p 30d                            # 30-day flow history
uv run flowtrack holding fetch -s RELIANCE -q 12         # 12 quarters ownership
uv run flowtrack scan deviations --handoff               # FII→MF handoff signals
```

### Monitor Activity

```bash
uv run flowtrack insider promoter-buys -d 30             # promoter buying (highest conviction)
uv run flowtrack bhavcopy top-delivery -n 20             # high delivery = real accumulation
uv run flowtrack deals fetch                             # bulk/block deals
uv run flowtrack mfport top-buys                         # biggest MF buys this month
uv run flowtrack estimates upside                        # stocks with most analyst upside
```

### Check Macro

```bash
uv run flowtrack macro summary                           # VIX, USD/INR, Brent, 10Y G-sec
uv run flowtrack gold summary                            # gold/silver + ETF NAVs
```

### Get Filings

```bash
uv run flowtrack filings fetch INDIAMART --download -y 3
# Downloads concalls, investor decks, results → ~/vault/stocks/INDIAMART/filings/
```

---

## Data Sources

Every data type has one authoritative source. No overlaps.

| What | Source | How Often |
|------|--------|-----------|
| Quarterly & annual financials | Screener.in | Quarterly |
| P/E, PBV, EV/EBITDA history | Screener.in | Quarterly |
| Efficiency ratios (ROCE, debtor days) | Screener.in | Quarterly |
| Peer comparison | Screener.in | On-demand |
| Live valuation (price, PE, margins, beta) | yfinance | Daily |
| Analyst consensus & targets | yfinance | Weekly |
| Earnings surprises | yfinance | Weekly |
| FII/DII daily flows | NSE | Daily |
| Shareholding patterns | NSE | Quarterly |
| Insider/SAST trades | NSE | Daily |
| Daily OHLCV + delivery % | NSE bhavcopy | Daily |
| Bulk/block deals | NSE | Daily |
| MF monthly flows & AUM | AMFI | Monthly |
| MF scheme-level holdings | AMFI (5 AMCs) | Monthly |
| Gold/silver prices | yfinance | Daily |
| Gold ETF NAVs | mfapi.in | Daily |
| Macro (VIX, FX, crude, G-sec) | yfinance | Daily |
| Corporate filings (concalls, results) | BSE | Quarterly |

**Key rule:** Screener.in is the source of truth for Indian financials and historical valuations. yfinance provides live snapshots and analyst consensus. They don't overlap.

---

## Automated Data Collection

Six macOS LaunchAgents keep everything fresh automatically:

| Schedule | What |
|----------|------|
| **Weekdays 7pm** | FII/DII, gold, MF daily, macro, bhavcopy, deals, insider, valuations |
| **Sunday 2:30pm** | Analyst consensus + earnings surprises (500 stocks) |
| **6th of month** | AMFI monthly flows + AUM |
| **12th of month** | MF scheme holdings from 5 AMCs |
| **15th of quarter** | Nifty 250 shareholding + promoter pledges |
| **20th of quarter** | Screener financials + ratios + BSE filings |

Check the log: `tail -50 ~/.local/share/flowtracker/cron.log`

---

## The 8-Factor Screener

Every Nifty 500 stock gets a composite score from 0-100:

| Factor (weight) | What it catches |
|-----------------|-----------------|
| **Ownership** (15%) | MF accumulation, FII→MF handoff — smart money moving in |
| **Insider** (15%) | Promoter buying at market price — highest conviction signal |
| **Valuation** (15%) | Forward PE vs historical band, analyst upside — price vs value gap |
| **Earnings** (15%) | Surprise %, consecutive beats — positive momentum |
| **Quality** (10%) | ROCE, cash conversion, D/E — business fundamentals |
| **Delivery** (10%) | Avg delivery %, trend — genuine accumulation vs speculative churn |
| **Estimates** (10%) | Recommendation trend, analyst coverage — sell-side consensus |
| **Risk** (10%) | Promoter pledge, FII crowding — downside flags |

---

## Architecture

```
flowtracker/
├── main.py                     # Typer app, 16 command groups
├── store.py                    # FlowStore — SQLite, ~92 methods, 30 tables
├── screener_client.py          # Screener.in — 11 API methods
├── screener_engine.py          # 8-factor composite scorer
├── utils.py                    # Shared helpers
│
├── {module}_client.py          # HTTP fetch + parse (one per data source)
├── {module}_models.py          # Pydantic models
├── {module}_commands.py        # Typer subcommands
├── {module}_display.py         # Rich terminal tables
│
└── research/
    ├── refresh.py              # Pre-fetch 5 sources before agent runs
    ├── data_api.py             # ResearchDataAPI — 26 methods (unified data layer)
    ├── tools.py                # 26 MCP tools wrapping the API
    ├── agent.py                # Claude Agent SDK integration
    ├── prompts.py              # Analysis framework + output format
    └── data_collector.py       # HTML report data builder
```

Every module follows the same 4-file pattern: **models → client → commands → display**. The `research/` layer sits on top, using `ResearchDataAPI` as the single data access point for the AI agent.

---

## Setup

```bash
# 1. Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install dependencies
cd flow-tracker
uv sync

# 3. Set up Screener.in credentials (needed for financials)
mkdir -p ~/.config/flowtracker
cat > ~/.config/flowtracker/screener.env << 'EOF'
SCREENER_EMAIL=your@email.com
SCREENER_PASSWORD=yourpassword
EOF

# 4. Initial data fetch
uv run flowtrack fetch                    # FII/DII flows
uv run flowtrack macro fetch              # macro indicators
uv run flowtrack fund backfill -s RELIANCE  # financials for one stock

# 5. (Optional) Set up automated crons
bash scripts/setup-crons.sh
```

---

## Key Files

| File | What it does |
|------|-------------|
| `store.py` | Single SQLite wrapper. Every table, every query. Start here to understand the data model. |
| `screener_client.py` | All Screener.in API interactions. Two company IDs per stock (`company_id` for charts, `warehouse_id` for peers). See `docs/screener-api-map.md`. |
| `research/data_api.py` | The 26-method API the AI agent uses. If you want to query data programmatically, this is the interface. |
| `research/agent.py` | How the AI thesis generation works — Agent SDK, MCP tools, multi-turn reasoning. |
| `screener_engine.py` | The composite scoring logic. Each factor's calculation and weighting. |

---

## Database

SQLite at `~/.local/share/flowtracker/flows.db` (795 MB).

30 tables, 4.5M+ rows. The biggest:
- `daily_stock_data` — 3.7M rows of OHLCV + delivery % for 3K stocks
- `mf_scheme_holdings` — 345K rows, which MF schemes hold which stocks
- `insider_transactions` — 313K rows of SAST filings
- `shareholding` — 74K rows, quarterly FII/DII/MF/Promoter ownership

All monetary values are in crores (₹1 Cr = ₹10 million).

---

## Docs

- `docs/screener-api-map.md` — Every Screener.in API endpoint, parameters, auth, response format
- `docs/data-source-comparison.md` — Which source is authoritative for each data type
- `plans/flowtracker-roadmap.md` — What's planned next (valuation model, thesis tracker, portfolio view)
