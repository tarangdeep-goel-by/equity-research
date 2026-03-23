# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`flowtrack`) for tracking FII/DII institutional flows, MF data, shareholding patterns, commodity prices, and equity fundamentals in Indian markets. Single-user research tool — SQLite-backed, CLI-first, no server.

## Commands

```bash
# Run CLI (two equivalent ways)
uv run flowtrack <command>
./flowtrack <command>              # wrapper script, calls uv run

# Install dependencies
uv sync

# No test suite exists yet
```

## Architecture

Every feature module follows the same 4-file pattern:

| Layer | File | Role |
|-------|------|------|
| **Models** | `*_models.py` | Pydantic models (API responses + domain types) |
| **Client** | `*_client.py` | HTTP fetch + parsing (NSE, AMFI, Screener.in, yfinance) |
| **Display** | `*_display.py` | Rich tables/panels for terminal output |
| **Commands** | `*_commands.py` | Typer subcommand group, wires client → store → display |

The modules are:

| Prefix | Subcommand | Data Source |
|--------|-----------|-------------|
| *(core)* | `fetch`, `summary`, `flows`, `streak`, `backfill` | NSE FII/DII API |
| `mf_` | `mf` | AMFI monthly reports |
| `holding_` | `holding` | NSE XBRL shareholding filings |
| `scan_` | `scan` | NSE index constituents + batch shareholding |
| `fund_` | `fund` | yfinance + Screener.in (fundamentals) |
| `commodity_` | `gold` | yfinance (gold/silver) + mfapi.in (ETF NAVs) |

**Shared infrastructure:**
- `store.py` — Single `FlowStore` class wrapping SQLite. All tables, schema migrations, and queries live here. DB at `~/.local/share/flowtracker/flows.db`.
- `utils.py` — Formatting helpers (`fmt_crores`, `parse_period`, `normalize_category`).
- `main.py` — Top-level Typer app, registers all subcommand groups via `add_typer()`. Also contains core FII/DII commands and CSV/XLSX backfill parsing.

## Data Sources & Auth

All data is scraped from free public sources. NSE endpoints require cookie preflight (hit reports page first, then API). Screener.in requires login credentials stored at `~/.config/flowtracker/screener.env`.

## Cron / Scheduled Jobs

`scripts/` contains shell wrappers for scheduled fetches, managed via macOS LaunchAgents:
- `daily-fetch.sh` — FII/DII + gold/silver (weekdays 7pm IST, 3 retries with 5min backoff)
- `monthly-mf.sh` — AMFI data (6th of month)
- `quarterly-scan.sh` — Nifty 250 shareholding scan (quarterly)
- `quarterly-results.sh` / `weekly-valuation.sh` — Fundamentals
- `setup-crons.sh` — Registers all LaunchAgent plists

## Key Patterns

- **NSE API clients** use a common pattern: preflight GET to acquire cookies, then API GET, with retry + exponential backoff on 403.
- **Store as context manager** — always use `with FlowStore() as store:`.
- **Symbols are uppercase** — normalized with `.upper()` at the command layer.
- **yfinance symbols** — converted via `nse_symbol()`: `RELIANCE` → `RELIANCE.NS`.
- **All monetary values are in crores** (Indian numbering, ₹1 Cr = 10M).
