# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`flowtrack`) for tracking FII/DII institutional flows, MF data, shareholding patterns, commodity prices, and equity fundamentals in Indian markets. Includes an AI research agent that cross-references all data sources to generate equity research reports. Single-user research tool — SQLite-backed, CLI-first, no server.

## Commands

```bash
uv run flowtrack <command>         # or ./flowtrack <command>
uv sync                            # install dependencies

# Research commands (most commonly used)
uv run flowtrack research thesis -s INDIAMART        # AI-powered research report
uv run flowtrack research fundamentals -s INDIAMART  # data-only HTML report
uv run flowtrack research data shareholding_changes -s INDIAMART  # query single data tool
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

### Command Groups (15 modules, ~85 commands)

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
| `sector_` | `sector` | Cross-stock sector aggregation |
| `mfportfolio_` | `mfport` | AMFI MF scheme-level holdings (5 AMCs) |
| `screener_` | `screen` | Composite 8-factor stock screener |
| `filing_` | `filing` | BSE corporate filings |
| `research_` | `research` | AI research agent + HTML fundamentals reports |

### Research Layer (3-tier architecture)

```
Layer 1: DATA  ──→  Layer 2: AGENT  ──→  Layer 3: OUTPUT
refresh.py          agent.py (Claude)     .md report
(live fetch →       26 MCP tools →        ~/vault/stocks/{SYM}/thesis/
 28 SQLite tables)  multi-turn analysis   + reports/{sym}-thesis.md
```

Key files in `research/`:
- `refresh.py` — `refresh_for_research(symbol)` fetches live data from 5 sources (Screener.in, yfinance, NSE, macro, BSE) before agent runs
- `data_api.py` — `ResearchDataAPI` wraps FlowStore into 26 clean methods
- `tools.py` — 26 MCP tool functions (decorated with `@tool`) wrapping ResearchDataAPI
- `agent.py` — `generate_thesis(symbol)` spawns Claude via Agent SDK with MCP tools
- `prompts.py` — System prompt with analysis framework and output format
- `data_collector.py` — Legacy collector for HTML fundamentals report (separate from agent path)

Both the `thesis` command (agent) and `data` command (interactive) use the same `ResearchDataAPI` → `FlowStore` → SQLite path.

### Shared Infrastructure

- `store.py` (2331 lines) — Single `FlowStore` class wrapping SQLite. 28 tables, 95 methods. DB at `~/.local/share/flowtracker/flows.db`.
- `screener_client.py` (1232 lines) — Screener.in HTTP client. 11 API methods: HTML scraping, Excel export, Chart API, Peers API, Shareholders API, Schedules API.
- `screener_engine.py` — 8-factor composite scoring engine (ownership, insider, valuation, earnings, quality, delivery, estimates, risk).
- `main.py` — Top-level Typer app, registers all 15 subcommand groups via `add_typer()`.
- `utils.py` — Formatting helpers (`fmt_crores`, `parse_period`, `normalize_category`).

### Standalone Tools

- `tools/screener_clone.py` — Standalone Screener.in report generator. Fetches all public data (HTML + 6 chart APIs + peers + shareholders + schedules) and renders a full HTML clone. Run: `uv run python tools/screener_clone.py SYMBOL`

## Data Sources & Auth

All data scraped from free public sources. NSE endpoints require cookie preflight (hit reports page first, then API). Screener.in requires login credentials at `~/.config/flowtracker/screener.env`.

Screener.in has two company IDs per stock (extracted from `#company-info` HTML element):
- `data-company-id` — used for Charts, Schedules, Shareholders APIs
- `data-warehouse-id` — used for Peers, Excel Export APIs

Full API map: `docs/screener-api-map.md`

## Cron / Scheduled Jobs

`scripts/` contains shell wrappers for scheduled fetches, managed via macOS LaunchAgents:
- `daily-fetch.sh` — FII/DII + gold/silver (weekdays 7pm IST, 3 retries with 5min backoff)
- `monthly-mf.sh` — AMFI data (6th of month)
- `quarterly-scan.sh` — Nifty 250 shareholding scan (quarterly)
- `quarterly-results.sh` / `weekly-valuation.sh` — Fundamentals
- `setup-crons.sh` — Registers all LaunchAgent plists

## Key Patterns

- **NSE API clients** use a common pattern: preflight GET to acquire cookies, then API GET, with retry + exponential backoff on 403. All NSE clients support context manager (`with ... as client:`).
- **Store as context manager** — always use `with FlowStore() as store:`.
- **Symbols are uppercase** — normalized with `.upper()` at the command layer.
- **yfinance symbols** — converted via `nse_symbol()`: `RELIANCE` → `RELIANCE.NS`.
- **All monetary values are in crores** (Indian numbering, ₹1 Cr = 10M).
- **Screener.in is source of truth** for P/E history (TTM), growth rates, quarterly/annual financials. yfinance provides live valuation snapshots and analyst consensus.
- **Research tools read SQLite, never fetch directly.** The `refresh_for_research()` function handles all live fetching before the agent runs.
