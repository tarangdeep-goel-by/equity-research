# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

CLI tool (`flowtrack`) for tracking FII/DII institutional flows, MF data, shareholding patterns, commodity prices, equity fundamentals, and FMP valuation data in Indian markets. Includes a multi-agent AI research system (8 specialist agents + news + verification + web research + synthesis + explainer + comparison) that generates comprehensive equity research reports, plus portfolio tracking, alerts, catalyst events, and thesis condition tracking. Includes an autoeval loop (Gemini-graded) for iteratively improving agent prompts per sector. Single-user research tool — SQLite-backed, CLI-first, no server.

## Commands

```bash
uv run flowtrack <command>         # or ./flowtrack <command>
uv sync                            # install dependencies

# Research commands (most commonly used)
uv run flowtrack research thesis -s INDIAMART        # full multi-agent pipeline (8 specialists + verify + synthesis)
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
uv run pytest tests/ -m "not slow"           # fast suite (~20s, ~1120 tests)
uv run pytest tests/                         # full suite with CLI smoke (~120s)
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

### Command Groups (19 modules, ~106 commands)

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
| `catalyst_` | `catalyst` | Upcoming stock catalyst events |
| `research_` | `research` | Multi-agent research (7 specialists + verify + synthesis + explainer) + thesis tracker |

### Research Layer (multi-agent architecture)

```
Phase 0:  Data Refresh → 6 sources + peers (parallel with Phase 0c)
Phase 0b: Document Pipeline → concall + annual report + investor deck extraction (parallel)
Phase 0c: India Anchor Docs → Economic Survey + RBI MPR/Annual + Union Budget (parallel with Phase 0)
Phase 1:  8 Specialist Agents (parallel, pipelined with verification) → 8 briefings
Phase 1.5: Verification Agents → spot-check accuracy + AR/deck/anchor citations (pipelined)
Phase 1.7: Web Research Agent → resolves open questions (vault-first, then WebSearch/WebFetch)
Phase 2:  Synthesis Agent → Verdict + Executive Summary + Key Signals
Phase 3:  Assembly → Technical Markdown + HTML
Phase 4:  Explainer Agent → Beginner-friendly annotations → Final HTML (skip with --technical)
(Comparison Agent also available for multi-stock comparative reports)
```

**8 specialist agents** (Business, Financials, Ownership, Valuation, Risk, Technical, Sector, Macro) each have an expert persona, curated MCP tools, and produce a standalone technical report. The **macro agent** (added in PR #64) is a senior global-macro strategist that grounds India macro claims in official anchor docs (Economic Survey, RBI Annual Report, RBI MPR, Union Budget) via `get_macro_catalog` / `get_macro_anchor` — anchor exhaustion is enforced (any anchor marked `status='complete'` must be drilled + cited or null-findinged). A **news agent** gathers recent developments. Verification agents independently spot-check data accuracy using a different model; they also verify every `(source: FY?? AR, ...)`, `(source: FY??-Q? deck, ...)`, and anchor citation against the vault JSON. The **web research agent** resolves open questions — vault tools (`get_concall_insights`, `get_annual_report`, `get_deck_insights`, `get_macro_anchor`) first, then WebSearch/WebFetch for anything genuinely not on file. The synthesis agent cross-references all briefings + web research for the final verdict. The explainer agent adds beginner-friendly annotations to the assembled report. A **comparison agent** supports multi-stock comparative analysis.

**Annual Report & Investor Deck consult is scoped-mandatory:** Business, Financials, Risk, Valuation, Ownership agents MUST consult the annual report; Business, Financials, Valuation also MUST consult the latest investor deck. Each agent cites as `(source: FY25 AR, <section>)` or `(source: FY26-Q3 deck, <sub_section>)`. Null-findings ("no auditor qualifications flagged") count — silent skipping of a mandated section is a workflow violation. See `SHARED_PREAMBLE_V2` in `research/prompts.py` for the full rule.

**Phase 0b extractors are cached + industry-aware:** `ensure_concall_data`, `ensure_annual_report_data`, and `ensure_deck_data` all take an `industry` hint that drives sector-specific canonical-section mandates (BFSI AR must populate CASA/NPA; Pharma AR must surface R&D pipeline). Re-runs skip cached complete years/quarters; the three extractors run in parallel via `asyncio.gather`.

**Every specialist prompt gets a temporal anchor:** `build_specialist_prompt` prepends `today = YYYY-MM-DD` + per-source freshness + AR/deck periods on file. Relative time language ("recently", "last year") without an anchor is a hard fail. Also prepended to the web research agent so it knows what's in vault.

Key files in `research/`:
- `refresh.py` — `refresh_for_research(symbol)` fetches live data from 6 sources + peers + concalls before agents run
- `data_api.py` — `ResearchDataAPI` wraps FlowStore into ~150 methods (incl. fair value model, DuPont decomposition, WACC)
- `tools.py` — 85 MCP tools organized into specialist registries (via `claude_agent_sdk.tool`)
- `agent.py` — `_run_specialist()`, `run_all_agents()`, `run_synthesis_agent()`, `run_explainer_agent()`, directed synthesis orchestration
- `prompts.py` — agent prompts (8 specialists + news + web_research + synthesis + explainer + comparison), shared preamble, sector-specific injection via `sector_skills/` markdown files (24 sectors)
- `briefing.py` — `BriefingEnvelope` model, save/load, parse briefing from markdown
- `verifier.py` — Verification agent, correction flow
- `assembly.py` — Final report assembly, HTML rendering with mermaid.js
- `charts.py` — 25 chart types via matplotlib (stock, sector, comparison, dividend)
- `peer_refresh.py` — Peer data refresh (Screener + yfinance), sector benchmarks computation
- `concall_extractor.py` / `annual_report_extractor.py` / `deck_extractor.py` — Agent SDK-driven PDF extractors (concalls, AR, investor decks) feeding industry-aware JSON caches
- `ar_downloader.py` / `doc_extractor.py` / `heading_toc.py` — AR discovery + download + ToC heuristics for extractor pre-analysis
- `macro_anchors.py` — Fetcher + cache for India anchor docs (Economic Survey, RBI Annual Report, RBI MPR, Union Budget); powers Phase 0c and `get_macro_catalog` / `get_macro_anchor` tools
- `snapshot_builder.py` / `fundamentals.py` — company snapshot + fundamentals aggregation for specialist consumption
- `thesis_tracker.py` — YAML frontmatter thesis conditions evaluated against live data
- `sector_kpis.py` — Sector-specific KPI definitions and routing (14 sectors with formal KPI configs; 24 sectors have skill files)
- `wacc.py` — Weighted average cost of capital computation
- `projections.py` — Revenue/earnings projection models
- `data_collector.py` — Legacy collector for HTML fundamentals report (separate from agent path)

Both the `thesis` command (multi-agent) and `data` command (interactive) use the same `ResearchDataAPI` → `FlowStore` → SQLite path.

### Sector Skills Architecture

Sector-specific agent knowledge lives in markdown files, not Python code:

```
research/sector_skills/
  bfsi/
    _shared.md       ← shared rules for ALL agents in this sector
    business.md      ← business-agent-specific guidance (from autoeval)
  metals/
    _shared.md
  ... (24 sectors total)
```

`build_specialist_prompt()` loads `_shared.md` + `{agent}.md` for the detected sector. `_build_mcap_injection()` is the only remaining Python injection (has dynamic logic). Sector-specific fixes go in skill files; general fixes go in `prompts.py`.

### AutoEval Loop

Iterative prompt optimization: run agent → grade with Gemini → fix prompt → re-run. One agent at a time, sector by sector, until all reach A-.

```bash
uv sync --extra autoeval
uv run flowtrack research autoeval -a business --sectors bfsi      # run + grade
uv run flowtrack research autoeval -a business --sectors bfsi --skip-run  # grade only
uv run flowtrack research autoeval --progress                      # progress chart
```

Key files in `research/autoeval/`: `evaluate.py` (harness), `eval_matrix.yaml` (14 sectors × test stocks), `fix_tracker.md` (Gemini-recommended fixes), `results.tsv` (grades). See `research/autoeval/README.md` for full workflow.

### Buy-Side Decision Framework

- **Fair value model** (`get_fair_value`) — combines PE band fair value, FMP DCF, and analyst consensus into bear/base/bull range with margin of safety signal (DEEP VALUE / UNDERVALUED / FAIR VALUE / EXPENSIVE)
- **DuPont decomposition** (`get_dupont_decomposition`) — ROE = margin × turnover × leverage, 10yr history, uses Screener data with FMP fallback
- **Portfolio tracker** (`portfolio_commands.py`) — holdings with live P&L, sector concentration
- **Alert system** (`alert_engine.py`) — 10 condition types (price, PE, RSI, FII%, pledge, DCF upside) checked against cached data
- **Thesis tracker** (`thesis_tracker.py`) — YAML frontmatter conditions at `~/vault/stocks/{SYMBOL}/thesis-tracker.md`, evaluated with `thesis-check`

### Shared Infrastructure

- `store.py` (~4200 lines) — Single `FlowStore` class wrapping SQLite. 50 tables, ~150 methods. DB at `~/.local/share/flowtracker/flows.db`.
- `screener_client.py` (~1420 lines) — Screener.in HTTP client. 11 API methods: HTML scraping, Excel export, Chart API, Peers API, Shareholders API, Schedules API.
- `fmp_client.py` — FMP API client (httpx). DCF, technicals, key metrics, growth, analyst grades, price targets. Uses `/stable/` endpoints. Key at `~/.config/flowtracker/fmp.env`.
- `screener_engine.py` — 8-factor composite scoring engine (ownership, insider, valuation, earnings, quality, delivery, estimates, risk). Valuation factor incorporates DCF margin of safety when FMP data available.
- `alert_engine.py` — Evaluates alert conditions against cached store data. 10 condition types.
- `main.py` — Top-level Typer app, registers all 19 subcommand groups via `add_typer()`.
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
- `alert-check.sh` — Alert engine sweep (chained after daily fetch)
- `weekly-valuation.sh` — Consensus estimates + earnings surprises (Sunday 2:30pm)
- `weekly-nifty250.sh` — Weekly valuation + estimates refresh for all Nifty index stocks (Sunday 9pm IST)
- `monthly-mf.sh` — AMFI monthly flows (6th of month)
- `monthly-mfportfolio.sh` — MF scheme holdings from 5 AMCs (12th of month)
- `quarterly-scan.sh` — Nifty 250 shareholding + pledges (quarterly)
- `quarterly-results.sh` — Screener financials + ratios + BSE filings (20th of month)
- `quarterly-filings.sh` — Concall + investor deck download for Nifty index stocks (25th of Feb/May/Aug/Nov 10am IST)
- `compute-analytics.py` — Weekly analytics computation (Sunday 9pm IST)
- `setup-crons.sh` — Registers all LaunchAgent plists

Ad-hoc scripts (not scheduled): `backfill_fii_dii.py`, `backfill_fundamentals.py`, `backfill_quarterly_nse.py`, `backfill-index-prices.py`, `backfill-nifty250.py`, `batch-download-filings.py`, `check-freshness.py`, `migrate-pct.py`, `migrate-units.py`.

## Key Patterns

- **NSE API clients** use a common pattern: preflight GET to acquire cookies, then API GET, with retry + exponential backoff on 403. All NSE clients support context manager (`with ... as client:`).
- **Store as context manager** — always use `with FlowStore() as store:`.
- **Symbols are uppercase** — normalized with `.upper()` at the command layer.
- **yfinance symbols** — converted via `nse_symbol()`: `RELIANCE` → `RELIANCE.NS`.
- **Unit standard (P-3B)**: All monetary aggregates stored in **crores** (₹1 Cr = 10M) — converted at ingestion, never in compute code. Per-share values (price, EPS, BVPS) in **rupees**. Counts (shares, volume) are **raw**. Use `×1e7` only for Cr→Rs per-share conversions. See `store.py` docstring for full spec.
- **Percentage standard (P-3B.2)**: All margins (OPM, NPM, GPM), returns (ROE, ROA, ROCE), growth rates, and yields stored as **percentage form** (25.0 = 25%). Ratios (PE, PB, D/E, current_ratio, beta) stay as raw ratios. Converted at ingestion in client files via `_to_pct()`.
- **Price adjustment convention (Sprint 0)**: Three tables, three conventions — know which one your code reads.
  - **`daily_stock_data`** — `open/high/low/close/volume` are raw NSE bhavcopy values (unadjusted for splits/bonuses). **Use `adj_close` + `adj_factor` for any multi-period return, analog comparison, or charting**. `adj_close = close / adj_factor` where `adj_factor` is the cumulative split × bonus multiplier for actions after the row's date. Populated by `FlowStore.recompute_adj_close(symbol)` — auto-fires from `upsert_corporate_actions` (splits/bonuses only; dividend upserts skip recompute); nightly cron re-runs universe-wide and drift-sweeps against `ResearchDataAPI.get_adjusted_close_series()` helper.
  - **`valuation_snapshot`** — yfinance `auto_adjust=True` point-in-time metrics (market cap, PE, PB, etc.). Not a time-series, so adjustment concern is bounded; each row is a snapshot of then-current state.
  - **`screener_charts`** — raw at fetch time (21yr PE + price); PE itself is adjustment-invariant (ratio cancels), but raw price from this table has discontinuity cliffs at split/bonus ex-dates unless re-fetched post-action. Use for long-history PE context only; prefer `daily_stock_data.adj_close` for precision work.
- **Screener.in is source of truth** for P/E history (TTM), growth rates, quarterly/annual financials. yfinance provides live valuation snapshots and analyst consensus.
- **Research tools read SQLite, never fetch directly.** The `refresh_for_research()` function handles all live fetching before the agent runs.
- **Thesis tracker files** live at `~/vault/stocks/{SYMBOL}/thesis-tracker.md` with YAML frontmatter conditions.
- **FMP API** uses `.NS` suffix for Indian stocks (same as yfinance). Rate limit: `time.sleep(0.5)` between calls. Free tier: 250 requests/day but most endpoints need paid plan.
