# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Indian equity research workspace — two CLI tools for tracking institutional flows and screening stocks, plus standalone portfolio/analysis scripts. All tools are CLI-first, Python 3.12+, managed with `uv`.

## Projects

### flow-tracker/ — Institutional Flow Tracker (`flowtrack`)

Tracks FII/DII flows, MF data, shareholding patterns, commodity prices, and equity fundamentals. SQLite-backed, scrapes free public sources (NSE, AMFI, Screener.in, yfinance).

```bash
cd flow-tracker
uv sync
uv run flowtrack <command>   # or ./flowtrack <command>
```

Has its own `CLAUDE.md` with full architecture docs. Key points:
- Every feature module follows a 4-file pattern: `*_models.py`, `*_client.py`, `*_display.py`, `*_commands.py`
- Single `FlowStore` class in `store.py` wraps all SQLite tables, schema, and queries
- DB location: `~/.local/share/flowtracker/flows.db`
- Screener.in credentials: `~/.config/flowtracker/screener.env`
- Scheduled jobs via macOS LaunchAgents (scripts in `scripts/`)

### stock-cli/ — Stock Screener CLI (`stock`)

Stock screening, research, and comparison for US and Indian markets via yfinance.

```bash
cd stock-cli
uv sync
uv run stock <command>       # or ./stock <command>
```

Has its own `CLAUDE.md`. Simpler 4-file layout: `main.py`, `client.py`, `models.py`, `display.py`, `utils.py`.

### portfolio/ — Standalone Scripts

One-off portfolio analysis scripts (net worth calculation, mutual fund parsing, US holdings). Not a package — run individual scripts directly.

### Supporting dataset/ — Raw Data

CSV/ZIP archives of historical FII/DII data from external sources.

## Common Patterns

- **Package manager:** `uv` everywhere. `uv sync` to install, `uv run` to execute.
- **CLI framework:** Typer + Rich tables for all CLIs.
- **Data models:** Pydantic v2 with `extra="ignore"` for safe dict passthrough.
- **No test suites** exist in either project yet. No linters configured.
- **Shared stack:** Python 3.12, Typer, Rich, Pydantic, yfinance, httpx (flow-tracker), hatchling build.
- **Monetary values** in flow-tracker are in crores (₹1 Cr = 10M).

## Working Across Projects

Each project has independent `.venv` and `pyproject.toml`. Always `cd` into the project directory before running commands. Read the project-specific `CLAUDE.md` before making changes.
