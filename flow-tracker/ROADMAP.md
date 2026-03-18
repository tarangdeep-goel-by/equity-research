# Institutional Flow Tracker — Roadmap

## Overview

Track FII/DII institutional flows to understand how foreign and domestic institutions are investing in Indian markets. Focus on disaggregated data (sector-level, stock-level, MF portfolio changes) rather than just aggregate net flows.

## Data Sources (All Free)

| Source | What We Get | Frequency | Method |
|--------|------------|-----------|--------|
| **NSDL FPI Monitor** | FII daily buy/sell (equity + debt) | Daily by 7pm | Scrape/PDF parse |
| **MoneyControl FII/DII** | Net buy/sell summary | Daily | Scrape/API |
| **AMFI NAV + Portfolios** | MF stock-level holdings, AUM | Monthly (15th) | CSV download |
| **BSE Bulk/Block Deals** | Large institutional trades (name, qty, price) | Real-time | BSE API/scrape |
| **NSE Bulk/Block Deals** | Same as BSE | Real-time | NSE reports |
| **SEBI FPI Data** | Category-wise FPI flows, sector allocation | Monthly | PDF/CSV |
| **Trendlyne / Tickertape** | FII/DII shareholding patterns per stock | Quarterly | Scrape |
| **BSE Shareholding** | Promoter/FII/DII/retail breakdown per stock | Quarterly | BSE API |

## What We Track

### 1. Daily Dashboard (automated, daily)
- FII net equity flows — buying or selling, how much
- FII net debt flows — risk-on vs risk-off signal
- DII net equity flows — absorption capacity
- FII equity vs DII equity — divergence/convergence
- Running monthly/quarterly totals — trend direction

### 2. Sector-Level Flows (monthly, from SEBI + AMFI)
- Which sectors FIIs are rotating into/out of
- MF sectoral allocation changes month-over-month
- Sector heatmap — FII overweight/underweight vs benchmark

### 3. Stock-Level Institutional Activity
- Bulk/block deals — who's buying/selling large blocks, daily
- MF holding changes — stock-level adds/trims from monthly AMFI data
- Quarterly shareholding — FII/DII % change in specific stocks
- Alert: FII ownership crossing thresholds (e.g., >20%, <5%)

### 4. MF Intelligence (monthly)
- Cash-to-AUM ratio — are funds deployed or defensive?
- Top fund house moves — what are HDFC MF, SBI MF, ICICI Pru buying/selling?
- New positions — stocks appearing in MF portfolios for first time
- Exit signals — stocks being fully sold out of portfolios
- Concentration — are many funds piling into the same names?

### 5. Derived Signals / Alerts
- FII selling streak — X consecutive days of net selling
- FII-DII divergence alert — FIIs dumping but DIIs aggressively buying (often a bottom signal)
- Smart money accumulation — stock with rising FII + MF ownership but flat price
- Distribution — stock with falling institutional ownership but rising price (retail frenzy)
- Sector rotation — detect when money is moving between sectors

## System Architecture

```
flow-tracker/
├── scrapers/
│   ├── nsdl_fii.py          # Daily FII/DII flows
│   ├── bse_bulk_deals.py    # Bulk/block deals
│   ├── amfi_portfolios.py   # Monthly MF holdings
│   ├── bse_shareholding.py  # Quarterly patterns
│   └── sebi_fpi.py          # Monthly sector data
├── store/
│   └── sqlite DB             # Historical data
├── analysis/
│   ├── daily_summary.py     # Daily flow report
│   ├── sector_rotation.py   # Sector-level analysis
│   ├── mf_intelligence.py   # MF portfolio analytics
│   └── signals.py           # Alert generation
├── cli/
│   └── main.py              # CLI interface
└── data/                    # Raw downloads cache
```

**Stack:** Python + SQLite + click CLI

## CLI Interface

```bash
# Morning (auto-cron or manual)
flowtrack fetch daily          # pulls FII/DII data from yesterday
flowtrack summary              # prints daily flow summary

# Research
flowtrack flows --period 30d   # last 30 days FII/DII trend
flowtrack sectors              # sector rotation heatmap
flowtrack stock RELIANCE.NS    # institutional ownership history
flowtrack bulk-deals --today   # today's large trades
flowtrack mf-moves --month     # what MFs bought/sold this month
flowtrack signals              # active alerts
```

## Build Phases

| Phase | What | Effort |
|-------|------|--------|
| **1** | Daily FII/DII scraper + SQLite + CLI summary | 1-2 sessions |
| **2** | Bulk/block deal tracker | 1 session |
| **3** | AMFI monthly MF portfolio parser | 1-2 sessions |
| **4** | Quarterly shareholding tracker | 1 session |
| **5** | Derived signals + alerts | 1 session |
| **6** | Streamlit dashboard (optional) | 1-2 sessions |

## Design Decisions

- **SQLite over Postgres** — single-user research tool, no need for server DB
- **CLI-first** — consistent with stock-cli, fast for daily use
- **Scraping over paid APIs** — all data is publicly available, free sources first
- **Python + uv** — consistent with existing project tooling
