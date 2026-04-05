# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Indian equity research workspace — CLI tools for tracking institutional flows, screening stocks, and generating AI-powered research reports. All tools are CLI-first, Python 3.12+, managed with `uv`.

## Projects

### flow-tracker/ — Institutional Flow Tracker (`flowtrack`)

Primary project. 120+ CLI commands, 48 SQLite tables, 80 MCP tools, 15 data sources. Tracks FII/DII flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and generates multi-agent AI research reports (7 specialist agents + verification + web research + synthesis + explainer + comparison). Includes portfolio tracking, alerts, fair value model, catalyst events, and thesis tracker.

```bash
cd flow-tracker
uv sync
uv run flowtrack <command>
```

Has its own `CLAUDE.md` with full architecture docs. Key entry points:
- `store.py` (~3800 lines) — single `FlowStore` class, 48 tables, ~147 methods
- `screener_client.py` (1340 lines) — Screener.in HTTP client, 11 API methods
- `research/` — multi-agent research system (80 MCP tools, 7 specialist agents, verification, web research, synthesis, explainer, comparison)
- DB: `~/.local/share/flowtracker/flows.db`
- Screener.in creds: `~/.config/flowtracker/screener.env`
- FMP creds: `~/.config/flowtracker/fmp.env` (paid plan required for most endpoints)

## Common Patterns

- **Package manager:** `uv`. `uv sync` to install, `uv run` to execute.
- **CLI framework:** Typer + Rich tables.
- **Data models:** Pydantic v2 with `extra="ignore"` for safe dict passthrough.
- **Testing:** `uv run pytest tests/ -m "not slow"` (~20s, ~950 tests). See `flow-tracker/CLAUDE.md` for full test guide.
- **Monetary values** are in crores (₹1 Cr = 10M).
