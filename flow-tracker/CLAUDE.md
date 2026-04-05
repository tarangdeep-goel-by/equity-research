# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`flowtrack`) for tracking FII/DII institutional flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and FMP valuation data in Indian markets. Includes a multi-agent AI research system (6 specialist agents + verification + synthesis) that generates comprehensive equity research reports, plus portfolio tracking, alerts, and thesis condition tracking. Single-user research tool — SQLite-backed, CLI-first, no server.

## Commands

```bash
uv run flowtrack <command>         # or ./flowtrack <command>
uv sync                            # install dependencies

# Research commands (most commonly used)
uv run flowtrack research thesis -s INDIAMART        # full multi-agent pipeline (6 specialists + verify + synthesis)
uv run flowtrack research run business -s INDIAMART  # run single specialist agent
uv run flowtrack research verify financial -s INDIAMART  # verify an existing report
uv run flowtrack research fundamentals -s INDIAMART  # data-only HTML report
uv run flowtrack research data fair_value -s SBIN    # combined PE band + DCF + consensus
uv run flowtrack research data dupont_decomposition -s SBIN  # ROE quality breakdown
uv run flowtrack filings extract -s INDIAMART        # extract structured concall insights

# Buy-side tools
uv run flowtrack portfolio add SBIN --qty 50 --cost 920  # track holdings
uv run flowtrack portfolio view                           # live P&L
uv run flowtrack alert add SBIN price_below 750           # set alerts
uv run flowtrack alert check                              # evaluate all alerts
uv run flowtrack research thesis-check -s SBIN            # check thesis conditions

# FMP data (requires paid API key at ~/.config/flowtracker/fmp.env)
uv run flowtrack fmp fetch -s RELIANCE                    # DCF, technicals, metrics, grades
```

## Testing

```bash
uv sync --extra test                         # install test deps (first time)
uv run pytest tests/ -m "not slow"           # fast suite (~20s, 929 tests)
uv run pytest tests/                         # full suite with CLI smoke (~120s, 1048 tests)
uv run pytest tests/ --cov=flowtracker -q    # with coverage report
uv run python scripts/check-freshness.py     # verify production DB data is current
```

### Test structure

```
tests/
  conftest.py          # Fixtures: store (temp DB), populated_store, tmp_db, golden_dir
  fixtures/
    factories.py       # Model factories + populate_all(store) for 2 symbols (SBIN, INFY)
    golden/            # Recorded API responses (screener HTML/Excel, etc.)
  unit/                # Store, models, utils, clients, engines, charts, assembly
  integration/         # Client→store pipelines, display capture, CLI commands, MCP tools
  e2e/                 # Full screener pipeline, alert pipeline, thesis pipeline
  contract/            # Schema + model snapshots (syrupy), API response shape validation
  quality/             # Data consistency checks (shareholding sums, referential integrity)
```

### When adding new features — test requirements

**New store method:** Add upsert+get round-trip test in the appropriate `test_store_*.py`.

**New client or parser:** Add parsing tests in `test_client_*.py` using golden fixtures or inline data. Test both happy path and error path (bad input, missing data).

**New CLI command:** Add the command's `--help` to `test_smoke.py` HELP_COMMANDS list. If it's a read-only command, add a CliRunner test in `test_commands_extended.py`.

**New display function:** Add a capture test in `test_display_modules.py` (monkeypatch console, verify key strings).

**New Pydantic model:** Add construction + optional-None + computed property tests in `test_models.py`.

**New research tool (MCP):** Add async tool test in `test_mcp_tools_extended.py`.

**New chart type:** Add render test in `test_charts.py` (monkeypatch `_chart_dir`, verify PNG created).

**New scoring factor or alert condition:** Add to `test_screener_engine.py` or `test_alert_engine.py`.

### Key testing patterns

- **Store isolation:** `FlowStore(db_path=tmp_db)` — one fresh DB per test, <5ms overhead
- **HTTP mocking:** `respx` for httpx clients, `unittest.mock.patch` for yfinance
- **Display capture:** `Console(file=StringIO(), force_terminal=True)` + monkeypatch module's `console`
- **CLI testing:** `typer.testing.CliRunner` + `monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))`
- **ResearchDataAPI injection:** `monkeypatch.setenv("FLOWTRACKER_DB", str(tmp_db))` (constructor reads env var)
- **Time freezing:** `freezegun` for date-relative store queries
- **Snapshots:** `syrupy` for schema/model regression detection

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
| `research_` | `research` | Multi-agent research (6 specialists + verify + synthesis) + thesis tracker |

### Research Layer (multi-agent architecture)

```
Phase 0:  Data Refresh → 6 sources + peers + concall extraction
Phase 1:  7 Specialist Agents (parallel) → 7 standalone technical reports + briefings
Phase 1.5: 7 Verification Agents (parallel) → spot-check data accuracy + corrections
Phase 2:  Synthesis Agent → Verdict + Executive Summary + Key Signals
Phase 3:  Assembly → Technical Markdown + HTML
Phase 4:  Explainer Agent → Beginner-friendly annotations → Final HTML (skip with --technical)
```

**7 specialist agents** (Business, Financial, Ownership, Valuation, Risk, Technical, Sector) each have an expert persona, 8-18 curated MCP tools, and produce a standalone technical report. Verification agents independently spot-check data accuracy using a different model. The synthesis agent cross-references all 7 briefings for the final verdict. The explainer agent then adds beginner-friendly annotations (definitions, analogies, callouts) to the assembled report.

Key files in `research/`:
- `refresh.py` — `refresh_for_research(symbol)` fetches live data from 6 sources + peers + concalls before agents run
- `data_api.py` — `ResearchDataAPI` wraps FlowStore into ~35 clean methods (incl. fair value model, DuPont decomposition)
- `tools.py` — 44 MCP tools (39 original + 5 new: peer_metrics, peer_growth, sector_benchmarks, concall_insights, render_chart), organized into 6 specialist registries
- `agent.py` — `_run_specialist()`, `run_all_agents()`, `run_synthesis_agent()`, `run_explainer_agent()`, directed synthesis orchestration
- `prompts.py` — 9 agent prompts (7 specialists + synthesis + explainer), shared preamble
- `briefing.py` — `BriefingEnvelope` model, save/load, parse briefing from markdown
- `verifier.py` — Verification agent, correction flow
- `assembly.py` — Final report assembly, HTML rendering with mermaid.js
- `charts.py` — 13 chart types via matplotlib (price, pe, delivery, quarterly, margin_trend, roce_trend, dupont, cashflow, revenue_profit, shareholding, fair_value_range, expense_pie, composite_radar)
- `peer_refresh.py` — Peer data refresh (Screener + yfinance), sector benchmarks computation
- `concall_extractor.py` — PDF extraction pipeline via Agent SDK (4 quarters of management commentary)
- `thesis_tracker.py` — YAML frontmatter thesis conditions evaluated against live data
- `data_collector.py` — Legacy collector for HTML fundamentals report (separate from agent path)

Both the `thesis` command (multi-agent) and `data` command (interactive) use the same `ResearchDataAPI` → `FlowStore` → SQLite path.

### Buy-Side Decision Framework

- **Fair value model** (`get_fair_value`) — combines PE band fair value, FMP DCF, and analyst consensus into bear/base/bull range with margin of safety signal (DEEP VALUE / UNDERVALUED / FAIR VALUE / EXPENSIVE)
- **DuPont decomposition** (`get_dupont_decomposition`) — ROE = margin × turnover × leverage, 10yr history, uses Screener data with FMP fallback
- **Portfolio tracker** (`portfolio_commands.py`) — holdings with live P&L, sector concentration
- **Alert system** (`alert_engine.py`) — 10 condition types (price, PE, RSI, FII%, pledge, DCF upside) checked against cached data
- **Thesis tracker** (`thesis_tracker.py`) — YAML frontmatter conditions at `~/vault/stocks/{SYMBOL}/thesis-tracker.md`, evaluated with `thesis-check`

### Shared Infrastructure

- `store.py` (~2900 lines) — Single `FlowStore` class wrapping SQLite. 40 tables (39 + sector_benchmarks), ~117 methods. DB at `~/.local/share/flowtracker/flows.db`.
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
- **Unit standard (P-3B)**: All monetary aggregates stored in **crores** (₹1 Cr = 10M) — converted at ingestion, never in compute code. Per-share values (price, EPS, BVPS) in **rupees**. Counts (shares, volume) are **raw**. Use `×1e7` only for Cr→Rs per-share conversions. See `store.py` docstring for full spec.
- **Screener.in is source of truth** for P/E history (TTM), growth rates, quarterly/annual financials. yfinance provides live valuation snapshots and analyst consensus.
- **Research tools read SQLite, never fetch directly.** The `refresh_for_research()` function handles all live fetching before the agent runs.
- **Thesis tracker files** live at `~/vault/stocks/{SYMBOL}/thesis-tracker.md` with YAML frontmatter conditions.
- **FMP API** uses `.NS` suffix for Indian stocks (same as yfinance). Rate limit: `time.sleep(0.5)` between calls. Free tier: 250 requests/day but most endpoints need paid plan.
