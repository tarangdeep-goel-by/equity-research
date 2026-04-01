# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Indian equity research workspace — CLI tools for tracking institutional flows, screening stocks, and generating AI-powered research reports. All tools are CLI-first, Python 3.12+, managed with `uv`.

## Projects

### flow-tracker/ — Institutional Flow Tracker (`flowtrack`)

Primary project. 100+ CLI commands, 40 SQLite tables, 44 MCP tools, 15 data sources. Tracks FII/DII flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and generates multi-agent AI research reports (6 specialist agents + verification + synthesis). Includes portfolio tracking, alerts, fair value model, and thesis tracker.

```bash
cd flow-tracker
uv sync
uv run flowtrack <command>
```

Has its own `CLAUDE.md` with full architecture docs. Key entry points:
- `store.py` (~2900 lines) — single `FlowStore` class, 40 tables, ~117 methods
- `screener_client.py` (1232 lines) — Screener.in HTTP client, 11 API methods
- `research/` — multi-agent research system (44 MCP tools, 6 specialist agents, verification, synthesis)
- DB: `~/.local/share/flowtracker/flows.db`
- Screener.in creds: `~/.config/flowtracker/screener.env`
- FMP creds: `~/.config/flowtracker/fmp.env` (paid plan required for most endpoints)

## Common Patterns

- **Package manager:** `uv`. `uv sync` to install, `uv run` to execute.
- **CLI framework:** Typer + Rich tables.
- **Data models:** Pydantic v2 with `extra="ignore"` for safe dict passthrough.
- **No test suites** exist. No linters configured.
- **Monetary values** are in crores (₹1 Cr = 10M).
