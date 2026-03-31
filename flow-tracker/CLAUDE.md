# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`flowtrack`) for tracking FII/DII institutional flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and FMP valuation data in Indian markets. Includes an AI research agent that cross-references all data sources to generate equity research reports, plus portfolio tracking, alerts, and thesis condition tracking. Single-user research tool — SQLite-backed, CLI-first, no server.

## Commands

```bash
uv run flowtrack <command>         # or ./flowtrack <command>
uv sync                            # install dependencies

# Research commands (most commonly used)
uv run flowtrack research thesis -s INDIAMART        # AI-powered research report
uv run flowtrack research fundamentals -s INDIAMART  # data-only HTML report
uv run flowtrack research data fair_value -s SBIN    # combined PE band + DCF + consensus
uv run flowtrack research data dupont_decomposition -s SBIN  # ROE quality breakdown

# Buy-side tools
uv run flowtrack portfolio add SBIN --qty 50 --cost 920  # track holdings
uv run flowtrack portfolio view                           # live P&L
uv run flowtrack alert add SBIN price_below 750           # set alerts
uv run flowtrack alert check                              # evaluate all alerts
uv run flowtrack research thesis-check -s SBIN            # check thesis conditions

# FMP data (requires paid API key at ~/.config/flowtracker/fmp.env)
uv run flowtrack fmp fetch -s RELIANCE                    # DCF, technicals, metrics, grades
```

No test suite exists yet.

## Architecture

### 4-File Module Pattern

Every feature module follows:

| Layer | File | Role |
|-------|------|------|
| **Models** | `*_models.py` | Pydantic models (API responses + domain types) |
| **Client** | `*_client.py` | HTTP fetch + parsing (NSE, AMFI, Screener.in, yfinance) |
| **Display** | `*_display.py` | Rich tables/panels for terminal output |
| **Commands** | `*_commands.py` | Typer subcommand group, wires client → store → display |

### Command Groups (18 modules, 100+ commands)

| Prefix | Subcommand | Data Source |
|--------|-----------|-------------|
| *(core)* | `fetch`, `summary`, `flows`, `streak`, `backfill` | NSE FII/DII API |
| `mf_` | `mf` | AMFI monthly reports |
| `holding_` | `holding` | NSE XBRL shareholding filings |
| `scan_` | `scan` | NSE index constituents + batch shareholding |
| `fund_` | `fund` | yfinance + Screener.in (fundamentals, charts, peers, schedules) |
| `commodity_` | `gold` | yfinance (gold/silver) + mfapi.in (ETF NAVs) |
| `macro_` | `macro` | VIX, USD/INR, Brent crude, 10Y G-sec |
| `bhavcopy_` | `bhavcopy` | NSE daily OHLCV + delivery % |
| `deals_` | `deals` | NSE bulk/block deals |
| `insider_` | `insider` | NSE SAST insider transactions |
| `estimates_` | `estimates` | yfinance analyst consensus + earnings surprises |
| `fmp_` | `fmp` | FMP API — DCF, technicals, key metrics, growth, analyst grades, price targets |
| `sector_` | `sector` | Cross-stock sector aggregation |
| `mfportfolio_` | `mfport` | AMFI MF scheme-level holdings (5 AMCs) |
| `screener_` | `screen` | Composite 8-factor stock screener |
| `filing_` | `filing` | BSE corporate filings |
| `portfolio_` | `portfolio` | Portfolio tracking — holdings, P&L, sector concentration |
| `alert_` | `alert` | Condition-based alerts — price, PE, RSI, ownership, pledge |
| `research_` | `research` | AI research agent + HTML fundamentals + thesis tracker |

### Research Layer (3-tier architecture)

```
Layer 1: DATA  ──→  Layer 2: AGENT  ──→  Layer 3: OUTPUT
refresh.py          agent.py (Claude)     .md report
(live fetch →       39 MCP tools →        ~/vault/stocks/{SYM}/thesis/
 39 SQLite tables)  multi-turn analysis   + reports/{sym}-thesis.md
```

Key files in `research/`:
- `refresh.py` — `refresh_for_research(symbol)` fetches live data from 6 sources (Screener.in, yfinance, NSE, macro, BSE, FMP) before agent runs
- `data_api.py` — `ResearchDataAPI` wraps FlowStore into ~35 clean methods (incl. fair value model, DuPont decomposition)
- `tools.py` — 39 MCP tool functions (decorated with `@tool`) wrapping ResearchDataAPI
- `agent.py` — `generate_thesis(symbol)` spawns Claude via Agent SDK with MCP tools
- `prompts.py` — System prompt with analysis framework and output format
- `thesis_tracker.py` — YAML frontmatter thesis conditions evaluated against live data
- `data_collector.py` — Legacy collector for HTML fundamentals report (separate from agent path)

Both the `thesis` command (agent) and `data` command (interactive) use the same `ResearchDataAPI` → `FlowStore` → SQLite path.

### Buy-Side Decision Framework

- **Fair value model** (`get_fair_value`) — combines PE band fair value, FMP DCF, and analyst consensus into bear/base/bull range with margin of safety signal (DEEP VALUE / UNDERVALUED / FAIR VALUE / EXPENSIVE)
- **DuPont decomposition** (`get_dupont_decomposition`) — ROE = margin × turnover × leverage, 10yr history, uses Screener data with FMP fallback
- **Portfolio tracker** (`portfolio_commands.py`) — holdings with live P&L, sector concentration
- **Alert system** (`alert_engine.py`) — 10 condition types (price, PE, RSI, FII%, pledge, DCF upside) checked against cached data
- **Thesis tracker** (`thesis_tracker.py`) — YAML frontmatter conditions at `~/vault/stocks/{SYMBOL}/thesis-tracker.md`, evaluated with `thesis-check`

### Shared Infrastructure

- `store.py` (~2900 lines) — Single `FlowStore` class wrapping SQLite. 39 tables, ~117 methods. DB at `~/.local/share/flowtracker/flows.db`.
- `screener_client.py` (1232 lines) — Screener.in HTTP client. 11 API methods: HTML scraping, Excel export, Chart API, Peers API, Shareholders API, Schedules API.
- `fmp_client.py` — FMP API client (httpx). DCF, technicals, key metrics, growth, analyst grades, price targets. Uses `/stable/` endpoints. Key at `~/.config/flowtracker/fmp.env`.
- `screener_engine.py` — 8-factor composite scoring engine (ownership, insider, valuation, earnings, quality, delivery, estimates, risk). Valuation factor incorporates DCF margin of safety when FMP data available.
- `alert_engine.py` — Evaluates alert conditions against cached store data. 10 condition types.
- `main.py` — Top-level Typer app, registers all 18 subcommand groups via `add_typer()`.
- `utils.py` — Formatting helpers (`fmt_crores`, `parse_period`, `normalize_category`, `_clean`).

### Standalone Tools

- `tools/screener_clone.py` — Standalone Screener.in report generator. Fetches all public data (HTML + 6 chart APIs + peers + shareholders + schedules) and renders a full HTML clone. Run: `uv run python tools/screener_clone.py SYMBOL`

## Data Sources & Auth

All data scraped from free public sources. NSE endpoints require cookie preflight (hit reports page first, then API). Screener.in requires login credentials at `~/.config/flowtracker/screener.env`. FMP requires API key at `~/.config/flowtracker/fmp.env` (paid plan needed for most endpoints — free tier only covers profile).

Screener.in has two company IDs per stock (extracted from `#company-info` HTML element):
- `data-company-id` — used for Charts, Schedules, Shareholders APIs
- `data-warehouse-id` — used for Peers, Excel Export APIs

FMP uses `/stable/` base URL with `?symbol=SYMBOL.NS&apikey=KEY` query params (legacy v3 endpoints deprecated Aug 2025).

Full API map: `docs/screener-api-map.md`. Source authority rules: `docs/data-source-comparison.md`.

## Cron / Scheduled Jobs

`scripts/` contains shell wrappers for scheduled fetches, managed via macOS LaunchAgents at `~/.local/share/flowtracker/scripts/`:
- `daily-fetch.sh` — FII/DII, gold, MF daily, macro, bhavcopy, deals, insider, valuation (weekdays 7pm IST, 3 retries)
- `weekly-valuation.sh` — Consensus estimates + earnings surprises (Sunday 2:30pm)
- `monthly-mf.sh` — AMFI monthly flows (6th of month)
- `monthly-mfportfolio.sh` — MF scheme holdings from 5 AMCs (12th of month)
- `quarterly-scan.sh` — Nifty 250 shareholding + pledges (quarterly)
- `quarterly-results.sh` — Screener financials + ratios + BSE filings (20th of month)
- `setup-crons.sh` — Registers all LaunchAgent plists

## Key Patterns

- **NSE API clients** use a common pattern: preflight GET to acquire cookies, then API GET, with retry + exponential backoff on 403. All NSE clients support context manager (`with ... as client:`).
- **Store as context manager** — always use `with FlowStore() as store:`.
- **Symbols are uppercase** — normalized with `.upper()` at the command layer.
- **yfinance symbols** — converted via `nse_symbol()`: `RELIANCE` → `RELIANCE.NS`.
- **All monetary values are in crores** (Indian numbering, ₹1 Cr = 10M).
- **Screener.in is source of truth** for P/E history (TTM), growth rates, quarterly/annual financials. yfinance provides live valuation snapshots and analyst consensus.
- **Research tools read SQLite, never fetch directly.** The `refresh_for_research()` function handles all live fetching before the agent runs.
- **Thesis tracker files** live at `~/vault/stocks/{SYMBOL}/thesis-tracker.md` with YAML frontmatter conditions.
- **FMP API** uses `.NS` suffix for Indian stocks (same as yfinance). Rate limit: `time.sleep(0.5)` between calls. Free tier: 250 requests/day but most endpoints need paid plan.
