# Data Source Comparison

Which data source is authoritative for each data type in flow-tracker. The guiding principle: **single source of truth per data type, no overlaps**.

## Source Authority Matrix

### Screener.in (source of truth for fundamentals)

| Data Type | Method / Notes |
|-----------|---------------|
| Quarterly financials (10yr) | Excel export or HTML `#quarters` section |
| Annual financials (P&L, BS, CF) | Excel export `Data Sheet` |
| Annual EPS (for historical P/E) | Derived from Excel P&L section |
| Efficiency ratios (ROCE, debtor/inventory days, CCC) | HTML `#ratios` section |
| Compounded growth rates (sales, profit, price CAGR, ROE) | HTML `table.ranges-table` |
| P/E history (TTM) | Chart API (`pe` query) |
| Valuation multiples history (EV/EBITDA, P/B, Mcap/Sales) | Chart API |
| Price + DMA50 + DMA200 + Volume | Chart API (`price` query) |
| Margin trends (GPM, OPM, NPM) | Chart API (`sales_margin` query) |
| Peer comparison table | Peers API (returns CMP, P/E, Mcap, ROCE, etc.) |
| Institutional shareholder details (name-level FII/DII) | Shareholders API |
| Line-item breakdowns (sub-schedules) | Schedules API |
| Concall transcripts / PPTs / recordings | HTML `#documents` section (links to external PDFs) |
| Annual report links | HTML `#documents` section |

### yfinance (live snapshots + analyst data)

| Data Type | Method / Notes |
|-----------|---------------|
| Live price, market cap | `yf.Ticker(symbol).info` |
| Live valuation snapshot (P/E, P/B, EV/EBITDA) | `.info` dict -- current values only |
| Analyst consensus (target price, buy/hold/sell) | `.info` keys: `targetMeanPrice`, `recommendationKey`, etc. |
| Earnings surprises (actual vs estimate) | `yf.Ticker(symbol).earnings_dates` |
| Beta | `.info["beta"]` |
| 52-week high/low | `.info["fiftyTwoWeekHigh"]`, `fiftyTwoWeekLow` |
| Dividend yield | `.info["dividendYield"]` |

Symbol conversion: `nse_symbol()` maps `RELIANCE` to `RELIANCE.NS`.

### NSE (regulatory filings + market microstructure)

| Data Type | Method / Notes |
|-----------|---------------|
| FII/DII daily flows (cash + derivatives) | NSE FII/DII API |
| Shareholding patterns (quarterly, XBRL) | NSE XBRL shareholding filings |
| Insider/SAST transactions | NSE insider trades API |
| Bulk deals | NSE bulk deals API |
| Block deals | NSE block deals API |
| Daily OHLCV + delivery % (bhavcopy) | NSE bhavcopy CSV |
| Index constituents (Nifty 50/200/500) | NSE index API |
| VIX | NSE VIX API |

All NSE clients use the preflight cookie pattern: `GET` reports page first, then `GET` API endpoint, with retry + exponential backoff on 403.

### Other Sources

| Data Type | Source | Notes |
|-----------|--------|-------|
| Mutual fund NAVs | mfapi.in | Gold/silver ETF NAV tracking |
| MF AUM / flows | AMFI monthly reports | Sector-level MF data |
| MF scheme holdings | AMFI portfolio disclosures | 5 AMCs, scheme-level stock holdings |
| Gold/silver spot prices | yfinance | `GC=F`, `SI=F` futures contracts |
| USD/INR | yfinance | `USDINR=X` |
| Brent crude | yfinance | `BZ=F` |
| 10Y G-sec yield | yfinance | `^IRX` or manual |
| Corporate filings | BSE | Annual reports, results, announcements |

## Overlap Rules

These rules prevent conflicting data:

| Data Type | Winner | Loser | Reason |
|-----------|--------|-------|--------|
| P/E ratio (historical) | Screener | yfinance | Screener has TTM P/E history via Chart API; yfinance only has current |
| P/E ratio (current) | Screener | yfinance | Consistency -- use same source for current + historical |
| Growth rates | Screener | computed from yfinance | Screener computes CAGR with proper adjustments |
| Quarterly financials | Screener | yfinance | Screener has 10yr depth, consistent format |
| Annual financials | Screener | yfinance | Full P&L + BS + CF from Excel export |
| Analyst targets | yfinance | -- | Only source for consensus estimates |
| Earnings surprises | yfinance | -- | Only source for actual vs estimate |
| Shareholding pattern | NSE | Screener | NSE is primary regulatory source; Screener's shareholders API supplements with name-level detail |
| Live price | yfinance | -- | Real-time; Screener chart has daily granularity |

## Data Flow

```
Screener.in ──→ screener_client.py ──→ store.py (SQLite) ──→ research/data_api.py
yfinance    ──→ fund_client.py     ──→ store.py (SQLite) ──→ research/data_api.py
NSE         ──→ *_client.py        ──→ store.py (SQLite) ──→ research/data_api.py
```

Research tools (`research/tools.py`) read from SQLite only. Live fetching happens in `research/refresh.py` before the agent runs.
