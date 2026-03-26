# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Indian equity research workspace — CLI tools for tracking institutional flows, screening stocks, and generating AI-powered research reports. All tools are CLI-first, Python 3.12+, managed with `uv`.

## Projects

### flow-tracker/ — Institutional Flow Tracker (`flowtrack`)

Primary project. 85+ CLI commands, 28 SQLite tables, 14 data sources. Tracks FII/DII flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and generates AI research reports.

```bash
cd flow-tracker
uv sync
uv run flowtrack <command>
```

Has its own `CLAUDE.md` with full architecture docs. Key entry points:
- `store.py` (2331 lines) — single `FlowStore` class, 28 tables, 95 methods
- `screener_client.py` (1232 lines) — Screener.in HTTP client, 11 API methods
- `research/` — AI agent layer (26 MCP tools, Agent SDK, live refresh)
- DB: `~/.local/share/flowtracker/flows.db`
- Screener.in creds: `~/.config/flowtracker/screener.env`

### stock-cli/ — Stock Screener CLI (`stock`)

Stock screening and comparison for US and Indian markets via yfinance. Simpler 4-file layout.

### portfolio/ — Standalone Scripts

One-off portfolio analysis scripts. Not a package.

### Supporting dataset/ — Raw Data

CSV/ZIP archives of historical FII/DII data.

## Common Patterns

- **Package manager:** `uv` everywhere. `uv sync` to install, `uv run` to execute.
- **CLI framework:** Typer + Rich tables for all CLIs.
- **Data models:** Pydantic v2 with `extra="ignore"` for safe dict passthrough.
- **No test suites** exist. No linters configured.
- **Monetary values** in flow-tracker are in crores (₹1 Cr = 10M).
- Each project has independent `.venv` and `pyproject.toml`. Always `cd` into the project directory.
