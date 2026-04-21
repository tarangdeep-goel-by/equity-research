# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Indian equity research workspace — CLI tools for tracking institutional flows, screening stocks, and generating AI-powered research reports. All tools are CLI-first, Python 3.12+, managed with `uv`.

## Projects

### flow-tracker/ — Institutional Flow Tracker (`flowtrack`)

Primary project. ~106 CLI commands, 50 SQLite tables, 85 MCP tools, 15 data sources. Tracks FII/DII flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and generates multi-agent AI research reports (8 specialist agents + news + verification + web research + synthesis + explainer + comparison). Includes portfolio tracking, alerts, fair value model, catalyst events, and thesis tracker.

```bash
cd flow-tracker
uv sync
uv run flowtrack <command>
```

Has its own `CLAUDE.md` with full architecture docs — **read it before touching anything in `flow-tracker/`**. Key entry points:
- `store.py` (~4200 lines) — single `FlowStore` class, 50 tables, ~150 methods
- `screener_client.py` (~1420 lines) — Screener.in HTTP client, 11 API methods
- `research/` — multi-agent research system (85 MCP tools, 8 specialist agents + news, verification, web research, synthesis, explainer, comparison)
- DB: `~/.local/share/flowtracker/flows.db`
- Screener.in creds: `~/.config/flowtracker/screener.env`
- FMP creds: `~/.config/flowtracker/fmp.env` (paid plan required for most endpoints)

### plans/ — Active planning docs

Long-form plans live here (e.g., `plans/multi-agent-research.md`, `plans/valuation-agent-comprehensive-fixes.md`, sector/agent fix plans, Gemini review outputs). When the user references a plan, read the file — decisions and phasing are captured there, not in git history.

### scripts/ — Eval orchestration (workspace-level)

Shell wrappers for the autoeval loop, not to be confused with `flow-tracker/scripts/` (cron wrappers).
- `eval-pipeline.sh <sector> <stock> <agents...>` — one sector, 2-wide parallel generation, async Gemini grading
- `eval-all-sectors.sh [start_sector]` — full 15-sector × 7-agent matrix, sequential per sector
- `eval-progress.sh` / `eval-recover.sh` / `eval-rerun-crashes.sh` / `eval-restart.sh` — monitor and resume long runs

Long autoeval runs go in tmux (see workflow-engine rule #7). Outputs land in `/tmp/eval-<sector>-<ts>/`.

### Worktree convention

Feature work uses git worktrees, not branches in the main repo. `equity-research-ar-deck/` is an example — it mirrors the workspace layout (its own `flow-tracker/`, `plans/`, `scripts/`). Any sibling directory named `equity-research-<slug>/` should be treated as a worktree, not separate code. Before editing, confirm which worktree you're in with `git worktree list` + `pwd`.

## Common Patterns

- **Package manager:** `uv`. `uv sync` to install, `uv run` to execute.
- **CLI framework:** Typer + Rich tables.
- **Data models:** Pydantic v2 with `extra="ignore"` for safe dict passthrough.
- **Testing:** `uv run pytest tests/ -m "not slow"` (~20s, ~1120 tests). See `flow-tracker/CLAUDE.md` for full test guide.
- **Monetary values** are in crores (₹1 Cr = 10M).
