# P0 Features — Next Implementation Phase

> Created: 2026-03-31
> Status: Ready for implementation
> Prerequisite: Multi-agent system complete (6 specialists + verification + synthesis)
> Project: `/Users/tarang/Documents/Projects/equity-research/flow-tracker/`
> Branch: `feat/p0-features`

## Quick Reference

- **16 tasks** across 4 batches, dependency graph in "Task Breakdown" section
- **4 features:** Quantitative Ranking, Catalyst Calendar, Peer Comparison Report, Sector Agent
- **New files:** `catalyst_client.py`, `catalyst_models.py`, `catalyst_commands.py`, `catalyst_display.py`
- **Modified files:** `screener_engine.py`, `screener_commands.py`, `screener_display.py`, `research_commands.py`, `research/agent.py`, `research/prompts.py`, `research/tools.py`, `research/data_api.py`, `store.py`, `main.py`, `research/assembly.py`
- **New DB tables:** None (catalyst data computed on-the-fly), 3 new store methods for sector aggregation
- **New MCP tools:** 4 (`get_upcoming_catalysts`, `get_sector_overview_metrics`, `get_sector_flows`, `get_sector_valuations`)
- **Test stocks:** HDFCBANK (bank), INDIAMART (tech), RELIANCE (conglomerate)
- **Priority order:** Ranking (1h) -> Catalyst (2.5h) -> Peer Comparison (4h) -> Sector Agent (4h)
- **Total estimated cost per feature (API):** Ranking $0, Catalyst $0, Comparison ~$0.40-8 per comparison, Sector Agent ~$0.30-0.50 per run
- **Worktree:** `git worktree add ../equity-research-p0 -b feat/p0-features main`

---

## Feature 1: Quantitative Screening / Ranking

### Goal

`flowtrack screen rank --top 20` — rank the entire Nifty 250 universe by composite quality x value score. The user gets a "buy this, not that" ranked list with factor breakdowns, filterable by industry or single factor. Custom weights let the user tilt toward value, quality, or momentum.

### User-Facing CLI Commands

```bash
# Core ranking commands
flowtrack screen rank --top 20                      # top 20 across all Nifty 250
flowtrack screen rank --top 10 --factor valuation   # top 10 by valuation factor alone
flowtrack screen rank --industry "Financial Services" --top 10  # rank within a sector
flowtrack screen rank --top 50 --min-score 60       # only stocks scoring above 60

# Custom weighting (override default weights)
flowtrack screen rank --top 20 --weight ownership=0.30 --weight valuation=0.25
```

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| `ScreenerEngine.score_stock(symbol)` | Working | `screener_engine.py:33` |
| `ScreenerEngine.screen_all(symbols, factor)` | Working | `screener_engine.py:69` |
| 8-factor scoring (ownership, insider, valuation, earnings, quality, delivery, estimates, risk) | Working | `screener_engine.py:100-412` |
| `screen top` command | Working | `screener_commands.py:22` |
| `display_screen_results(scores, limit)` | Working | `screener_display.py:25` |
| Nifty 250 symbols in DB | Working | `store.get_all_scanner_symbols()` → `index_constituents` table |
| Default weights summing to 1.0 | Working | `screener_engine.py:14-23` — `_WEIGHTS` dict |

### Gap Analysis

The `screen top` command already does most of what we need. The gaps are:

1. **No `rank` alias** — `screen top` exists but `screen rank` is more intuitive for this use case
2. **No industry filter** — can only filter by watchlist, not by industry classification
3. **No custom weights** — weights are hardcoded in `_WEIGHTS` module-level dict, not parameterizable
4. **No minimum score filter** — shows all stocks regardless of score
5. **No summary statistics** — no "median score: 52, mean: 48" at the bottom
6. **Display is basic** — no color coding for individual factor scores, no industry column truncation

### Architecture Decisions

- **No new module needed** — extend existing `screener_engine.py` + `screener_commands.py` + `screener_display.py`
- **Custom weights via CLI** — pass as key=value pairs, validate they're real factor names, normalize to sum to 1.0 automatically
- **Industry filter** — read from `index_constituents.industry` column (already populated from Nifty 250 scan)
- **No new DB tables** — scoring is computed on-the-fly from existing cached data
- **`rank` as a new command** — keep `top` as-is for backward compatibility, add `rank` with the extended options

### Files to Modify

**`flowtracker/screener_engine.py`** (lines 1-412):
1. Change `_WEIGHTS` from module-level constant to default parameter in `ScreenerEngine.__init__()`:
   ```python
   def __init__(self, store: FlowStore, weights: dict[str, float] | None = None) -> None:
       self._store = store
       self._cache: dict[str, dict] = {}
       self._weights = _normalize_weights(weights) if weights else dict(_WEIGHTS)
   ```
2. Add `_normalize_weights(weights: dict) -> dict` helper that validates keys against `_WEIGHTS.keys()`, fills missing keys with 0, and normalizes to sum to 1.0
3. Replace all `_WEIGHTS.get(f.factor, 0)` references in `score_stock()` with `self._weights.get(f.factor, 0)`
4. Add parameters to `screen_all()`:
   - `industry: str | None = None` — filter symbols by industry from `index_constituents`
   - `min_score: float = 0` — post-filter by composite score
5. In `screen_all()`, add industry lookup:
   ```python
   if industry:
       constituents = self._store.get_index_constituents()
       industry_syms = {c.symbol for c in constituents if c.industry == industry}
       symbols = [s for s in symbols if s in industry_syms]
   ```
6. After scoring, add min_score filter:
   ```python
   if min_score > 0:
       scores = [s for s in scores if s.composite_score >= min_score]
   ```

**`flowtracker/screener_commands.py`** (currently 69 lines):
1. Add `rank` command with extended options:
   ```python
   @app.command()
   def rank(
       top: Annotated[int, typer.Option("--top", "-n", help="Number of stocks")] = 20,
       factor: Annotated[str | None, typer.Option("--factor", help="Single factor ranking")] = None,
       industry: Annotated[str | None, typer.Option("--industry", help="Filter by industry")] = None,
       weight: Annotated[list[str] | None, typer.Option("--weight", help="Custom weight e.g. valuation=0.3")] = None,
       min_score: Annotated[float, typer.Option("--min-score", help="Minimum composite score")] = 0,
   ) -> None:
   ```
2. Parse `--weight` options: split on `=`, build dict, pass to `ScreenerEngine(store, weights=parsed_weights)`
3. Wire `industry` and `min_score` to `engine.screen_all()`
4. Call display with summary stats flag

**`flowtracker/screener_display.py`** (currently ~80 lines):
1. Add color coding for individual factor scores in `display_screen_results()`:
   - Green: score > 70
   - Yellow: 40-70
   - Red: < 40
   - Gray: -1 (no data)
2. Add summary row at bottom of table: total scored, mean/median composite, top industry represented
3. Truncate industry column to 18 chars with ellipsis
4. Add `display_screen_summary(scores)` helper for the summary stats

### Task Breakdown

**T1: Extend ScreenerEngine (30 min)**
- File: `flowtracker/screener_engine.py`
- Make weights configurable via `__init__` param
- Add `_normalize_weights()` helper
- Add `industry` and `min_score` params to `screen_all()`
- Blocked by: nothing
- Verify:
  ```bash
  uv run python -c "
  from flowtracker.screener_engine import ScreenerEngine
  from flowtracker.store import FlowStore
  with FlowStore() as store:
      e = ScreenerEngine(store, weights={'valuation': 0.5, 'quality': 0.5})
      scores = e.screen_all(min_score=50)
      print(f'Scored {len(scores)} stocks above 50')
      if scores: print(f'Top: {scores[0].symbol} = {scores[0].composite_score}')
  "
  ```

**T2: Add rank command + options (20 min)**
- File: `flowtracker/screener_commands.py`
- Depends on: T1
- Add `rank` command with `--industry`, `--weight`, `--min-score`, `--top`, `--factor`
- Parse weight strings ("valuation=0.3") into dict
- Verify:
  ```bash
  uv run flowtrack screen rank --top 5
  uv run flowtrack screen rank --top 5 --industry "Financial Services"
  uv run flowtrack screen rank --top 10 --weight valuation=0.3 --weight quality=0.3
  uv run flowtrack screen rank --top 20 --min-score 60
  ```

**T3: Improve display (10 min)**
- File: `flowtracker/screener_display.py`
- Depends on: T1
- Add color coding for individual factor scores (green/yellow/red/gray)
- Add summary stats row: total scored, mean, median, top industry
- Truncate industry column to 18 chars
- Verify: visual inspection of `uv run flowtrack screen rank --top 20`

### Cost Estimates

| Item | Cost | Time |
|------|------|------|
| Implementation | $0 API cost | ~1 hour |
| Scoring uses cached DB data | No live API calls | Instant execution |

---

## Feature 2: Catalyst Calendar

### Goal

`flowtrack catalyst -s HDFCBANK` — show upcoming events that could move the stock price. Earnings dates, board meetings, ex-dividend dates, RBI policy dates, SEBI meetings. This answers "when is the next thing that might move this stock?"

Also expose as an MCP tool (`get_upcoming_catalysts`) so the research agents can reference catalysts in their reports.

### User-Facing CLI Commands

```bash
flowtrack catalyst -s HDFCBANK                  # single stock, next 90 days
flowtrack catalyst --watchlist                   # all watchlist stocks
flowtrack catalyst --all                         # all portfolio + watchlist stocks
flowtrack catalyst -s HDFCBANK --days 180        # custom lookahead window
flowtrack catalyst --type earnings               # filter by event type
```

### Architecture Overview

```
                           ┌──────────────────────┐
                           │  Catalyst Sources     │
                           ├──────────────────────┤
                           │ 1. yfinance calendar  │ ← earnings date, ex-div
                           │ 2. BSE filings table  │ ← board meeting notices
                           │ 3. Static calendar    │ ← RBI policy, SEBI dates
                           │ 4. Historical pattern │ ← estimated next quarter
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │  Catalyst Engine      │
                           │  (catalyst_client.py) │
                           │                       │
                           │  gather_catalysts()   │
                           │  → list[CatalystEvent]│
                           └──────────┬───────────┘
                                      │
                              ┌───────┴──────┐
                              ▼              ▼
                    ┌─────────────┐  ┌────────────────┐
                    │ CLI display │  │ MCP tool       │
                    │ Rich table  │  │ for agents     │
                    └─────────────┘  └────────────────┘
```

### Data Sources Detail

**Source 1: yfinance `ticker.calendar`**
- Provides: next earnings date, ex-dividend date, dividend date
- Fetch: `yfinance.Ticker(f"{symbol}.NS").calendar`
- Returns dict with dates for upcoming events
- Reliability: good for large-cap, spotty for mid/small-cap
- Cache: fetch fresh each time (dates change)
- Error handling: wrap in try/except — many Indian stocks have empty calendar

**Source 2: BSE filings (already in DB)**
- Table: `bse_filings` — already populated by `filing_client.py` and cron
- Filter for: `subject LIKE '%Board Meeting%'` or `subject LIKE '%Results%'`
- Extract: board meeting dates from recent filings
- These are backward-looking (past filings) but indicate pattern for next meeting
- No new API calls needed — pure DB query

**Source 3: Static calendar (hardcoded)**
- RBI Monetary Policy dates: 6 per year, published annually in advance
- SEBI board meeting dates: ~6 per year
- MF disclosure deadline: 15th of each month
- Government budget: Feb 1
- These are market-wide catalysts (symbol=None), not stock-specific
- Stored as a Python dict, updated annually when RBI publishes calendar

**Source 4: Historical pattern estimation**
- Look at past 4-8 quarterly results dates from `quarterly_results` table
- Estimate next results date: "historically reports in Jan/Apr/Jul/Oct, last was Jan 25 → next expected ~Apr 25"
- Label as `confirmed=False` to distinguish from confirmed dates
- Pattern detection: group past quarter_end dates by month, find the typical reporting month

### Data Model

```python
# flowtracker/catalyst_models.py

from datetime import date
from pydantic import BaseModel

class CatalystEvent(BaseModel, extra="ignore"):
    symbol: str | None = None          # None for market-wide events (RBI, budget)
    event_type: str                    # "earnings", "board_meeting", "ex_dividend",
                                       # "rbi_policy", "budget", "results_estimated",
                                       # "sebi_meeting", "mf_disclosure"
    event_date: date
    days_until: int                    # computed from today
    description: str                   # "Q3 FY26 earnings release"
    impact: str                        # "high", "medium", "low"
    source: str                        # "yfinance", "bse_filing", "static", "estimated"
    confirmed: bool = True             # False for estimated dates

# Impact classification rules
IMPACT_MAP = {
    "earnings": "high",
    "board_meeting": "high",
    "results_estimated": "high",
    "ex_dividend": "medium",
    "rbi_policy": "medium",           # "high" for banks — caller overrides
    "budget": "high",
    "sebi_meeting": "low",
    "mf_disclosure": "low",
}

# Static calendar — FY26 (Apr 2025 - Mar 2026) and FY27 (Apr 2026 - Mar 2027)
# RBI Monetary Policy Committee meeting dates
STATIC_CALENDAR: list[dict] = [
    # FY27 RBI MPC dates (announced by RBI)
    {"event_type": "rbi_policy", "event_date": "2026-04-08", "description": "RBI MPC April 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-06-04", "description": "RBI MPC June 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-08-05", "description": "RBI MPC August 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-10-01", "description": "RBI MPC October 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2026-12-03", "description": "RBI MPC December 2026", "impact": "medium"},
    {"event_type": "rbi_policy", "event_date": "2027-02-04", "description": "RBI MPC February 2027", "impact": "medium"},
    # Budget
    {"event_type": "budget", "event_date": "2027-02-01", "description": "Union Budget FY28", "impact": "high"},
    # Note: SEBI dates are announced ad-hoc, add as they're published
]
```

### Design Decisions

- **No new DB table for v1** — compute on-the-fly from existing data + yfinance + static calendar. If caching is needed later, add a `catalysts` table with upsert pattern.
- **Static calendar as a Python dict** — RBI/SEBI dates for current FY hardcoded, updated annually. Simple and reliable. Lives in `catalyst_models.py`.
- **Impact classification:** earnings = high, board_meeting = high, ex_dividend = medium, rbi_policy = medium (override to high for bank stocks by checking industry from `index_constituents`), budget = high.
- **Sort by date ascending** — nearest event first.
- **yfinance call wrapped in try/except** — Indian stocks frequently lack calendar data.
- **Market-wide events have `symbol=None`** — shown for all stocks, filtered out when showing single-stock view unless `--include-market` flag.

### Files to Create/Modify

**NEW: `flowtracker/catalyst_models.py`**
- `CatalystEvent` Pydantic model
- `IMPACT_MAP` dict for impact classification
- `STATIC_CALENDAR` list with RBI/SEBI/budget dates for FY26-FY27
- Follow existing pattern: `portfolio_models.py`, `alert_models.py`

**NEW: `flowtracker/catalyst_client.py`**
- `gather_catalysts(symbol: str, store: FlowStore, days: int = 90) -> list[CatalystEvent]`
  - Source 1: yfinance → `_fetch_yfinance_calendar(symbol)` → wrap `Ticker.calendar` in try/except
  - Source 2: BSE filings → `_extract_filing_events(symbol, store)` → query `bse_filings` table for board meeting/results notices
  - Source 3: Static → `_get_static_events(days)` → filter `STATIC_CALENDAR` to window
  - Source 4: Historical → `_estimate_next_results(symbol, store)` → query `quarterly_results` dates, detect month pattern, extrapolate
  - Merge all sources, dedup by (event_type, event_date), compute `days_until`, filter to window, sort ascending
- `gather_watchlist_catalysts(symbols: list[str], store: FlowStore, days: int = 90) -> list[CatalystEvent]`
  - Batch version: loop over symbols, merge results, sort globally
- Follow existing error handling pattern: try/except per source, log warning, continue (like `refresh.py`)
- yfinance call: `yfinance.Ticker(f"{symbol}.NS").calendar` — returns dict or DataFrame depending on yfinance version. Handle both.

**NEW: `flowtracker/catalyst_display.py`**
- `display_catalyst_table(events: list[CatalystEvent])` — Rich table
- Color coding for `days_until`:
  - Red: < 7 days (imminent)
  - Yellow: 7-30 days (upcoming)
  - Green: > 30 days (future)
- Impact column: red for "high", yellow for "medium", dim for "low"
- Group by stock if showing multiple stocks (separator rows)
- Confirmed/Estimated indicator: checkmark vs "~" prefix

**NEW: `flowtracker/catalyst_commands.py`**
- Typer app `catalyst` with `show` command (set as default invoked command)
- Options: `-s SYMBOL`, `--watchlist`, `--all`, `--days`, `--type`
- `--all` merges portfolio holdings + watchlist symbols
- `--type` filters by event_type string
- Follow existing pattern: `sector_commands.py`, `alert_commands.py`

**MODIFY: `flowtracker/main.py`**
- `from flowtracker.catalyst_commands import app as catalyst_app`
- `app.add_typer(catalyst_app, name="catalyst")`
- Add after existing subcommand registrations

**MODIFY: `flowtracker/research/tools.py`**
- New MCP tool:
  ```python
  @tool(
      "get_upcoming_catalysts",
      "Get upcoming events that could move the stock: earnings dates, board meetings, "
      "ex-dividend, RBI policy, estimated results dates. Returns events within the next "
      "N days sorted by date.",
      {"symbol": str, "days": int},
  )
  async def get_upcoming_catalysts(args):
      from flowtracker.catalyst_client import gather_catalysts
      from flowtracker.store import FlowStore
      with FlowStore() as store:
          events = gather_catalysts(args["symbol"], store, args.get("days", 90))
      data = [e.model_dump() for e in events]
      return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
  ```
- Add to tool registries:
  - `RISK_AGENT_TOOLS` — catalysts are forward-looking risk/opportunity signals
  - `VALUATION_AGENT_TOOLS` — earnings dates affect valuation timing
  - `BUSINESS_AGENT_TOOLS` — for context on upcoming events in business narrative

**MODIFY: `flowtracker/research/data_api.py`**
- New method:
  ```python
  def get_upcoming_catalysts(self, symbol: str, days: int = 90) -> list[dict]:
      from flowtracker.catalyst_client import gather_catalysts
      events = gather_catalysts(symbol, self._store, days)
      return _clean([e.model_dump() for e in events])
  ```

**MODIFY: `flowtracker/research_commands.py`**
- Add `"upcoming_catalysts"` to `_DATA_TOOLS` list
- Add to `method_map`: `"upcoming_catalysts": lambda api: api.get_upcoming_catalysts(symbol)`

### Task Breakdown

**T4: Catalyst models (15 min)**
- File: `flowtracker/catalyst_models.py` (NEW)
- Create `CatalystEvent` model, `IMPACT_MAP`, `STATIC_CALENDAR`
- Blocked by: nothing
- Verify:
  ```bash
  uv run python -c "
  from flowtracker.catalyst_models import CatalystEvent, STATIC_CALENDAR
  print(f'{len(STATIC_CALENDAR)} static events')
  e = CatalystEvent(event_type='earnings', event_date='2026-04-15', days_until=15, description='test', impact='high', source='test')
  print(e)
  "
  ```

**T5: Catalyst client (1.5 hours)**
- File: `flowtracker/catalyst_client.py` (NEW)
- Implement `gather_catalysts()` with 4 data sources
- Blocked by: T4
- Pattern: follow `refresh.py` error handling (try/except per source, log warning, continue)
- yfinance call: `yfinance.Ticker(f"{symbol}.NS").calendar` — wrap in try/except
- Historical estimation: query `quarterly_results` table for past dates, group by month, find typical reporting month, extrapolate next date
- Test with HDFCBANK (should have yfinance calendar data), INDIAMART (may not)
- Verify:
  ```bash
  uv run python -c "
  from flowtracker.catalyst_client import gather_catalysts
  from flowtracker.store import FlowStore
  with FlowStore() as store:
      events = gather_catalysts('HDFCBANK', store)
      for e in events[:5]:
          print(f'{e.days_until:3d}d | {e.event_type:20s} | {e.description}')
  "
  ```

**T6: Catalyst display + commands (30 min)**
- Files: `flowtracker/catalyst_display.py` (NEW), `flowtracker/catalyst_commands.py` (NEW)
- Blocked by: T5
- Register in `main.py`
- Verify:
  ```bash
  uv run flowtrack catalyst -s HDFCBANK
  uv run flowtrack catalyst -s RELIANCE --days 180
  ```

**T7: Catalyst MCP tool (15 min)**
- Files: `flowtracker/research/tools.py`, `flowtracker/research/data_api.py`, `flowtracker/research_commands.py`
- Blocked by: T5
- Add `get_upcoming_catalysts` tool
- Add to RISK_AGENT_TOOLS, VALUATION_AGENT_TOOLS, BUSINESS_AGENT_TOOLS registries
- Add to `_DATA_TOOLS` list and `method_map` in research_commands.py
- Verify:
  ```bash
  uv run flowtrack research data upcoming_catalysts -s HDFCBANK --raw
  ```

### Cost Estimates

| Item | Cost | Time |
|------|------|------|
| Implementation | $0 API cost | ~2.5 hours |
| yfinance calls | Free, no rate limit concern | ~1s per stock |
| Static calendar | No API calls | Instant |
| BSE filings | Already in DB | Instant |

---

## Feature 3: Peer Deep Comparison Report

### Goal

`flowtrack research compare HDFCBANK ICICIBANK KOTAKBANK` — generate a side-by-side comparative equity research report. Load or generate briefings for all stocks, then run a new Comparison agent that reads all briefings and produces a "which one should I invest in" analysis.

This is the most requested feature for someone deciding between 2-4 similar stocks.

### User-Facing CLI Commands

```bash
# Core comparison
flowtrack research compare HDFCBANK ICICIBANK KOTAKBANK        # 3-stock comparison
flowtrack research compare HDFCBANK ICICIBANK                  # 2-stock comparison
flowtrack research compare HDFCBANK ICICIBANK KOTAKBANK SBIN AXISBANK  # up to 5 stocks

# Options
flowtrack research compare HDFCBANK ICICIBANK --skip-fetch      # use cached data only
flowtrack research compare HDFCBANK ICICIBANK --model claude-opus-4  # override model
flowtrack research compare HDFCBANK ICICIBANK --force           # re-run agents even if briefings exist
```

### Architecture Overview

```
CLI: flowtrack research compare HDFCBANK ICICIBANK KOTAKBANK
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Step 1: Load/Generate Briefings   │
    │                                    │
    │  For each stock:                   │
    │  ├─ Check ~/vault/stocks/{SYM}/    │
    │  │  briefings/*.json               │
    │  ├─ If fresh (< 7 days): reuse     │
    │  └─ If stale/missing: run full     │
    │     multi-agent pipeline           │
    │                                    │
    │  Result: 6 briefings per stock     │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Step 2: Comparison Agent          │
    │                                    │
    │  Receives: all briefings + live    │
    │  valuation data for all stocks     │
    │                                    │
    │  Prompt: structured comparison     │
    │  framework with specific questions │
    │  to answer for each dimension      │
    │                                    │
    │  Tools: get_fair_value,            │
    │  get_composite_score, get_peer_    │
    │  comparison, get_valuation_snapshot│
    │  (called for EACH stock)           │
    └───────────────┬───────────────────┘
                    │
                    ▼
    ┌───────────────────────────────────┐
    │  Step 3: Assembly                  │
    │  Comparative HTML/Markdown report  │
    │  with side-by-side tables          │
    │  Opens in browser                  │
    └───────────────────────────────────┘
```

### Design Decisions

1. **Reuse existing briefings** — don't re-run 6 agents per stock if briefings are fresh (< 7 days old). This makes a 3-stock comparison cost ~$0.50 (just the comparison agent) instead of ~$9 (3 full pipelines + comparison).
2. **Briefing freshness check** — look at `generated_at` field in `BriefingEnvelope`. If any specialist briefing is > 7 days old, re-run that specific specialist only.
3. **Comparison agent gets briefings, not reports** — briefings are structured JSON (~500 tokens each), not full markdown reports (~5000 tokens). The comparison agent gets 6 briefings x N stocks = manageable context even for 5 stocks.
4. **Comparison agent also gets live valuation** — calls `get_fair_value` and `get_composite_score` for each stock to ensure current prices are used.
5. **Limit to 5 stocks** — more than 5 becomes unwieldy both for the agent context and the reader. CLI validates count.
6. **Output a single HTML report** — not per-stock, but one combined comparative report at `reports/{sym1}-vs-{sym2}-...-comparison.html`.
7. **Side-by-side tables, not sequential** — the prompt explicitly forbids "here's stock A... now here's stock B..." and requires comparative tables in every section.

### Comparison Agent Specification

**Model:** `claude-sonnet-4-6` (good balance of cost/quality for structured comparison)
**Max turns:** 15
**Max budget:** $0.60

**Tools (4 — called for each stock):**

| Tool | Why |
|------|-----|
| `get_fair_value` | Current valuation for each stock — the "is it cheap?" question |
| `get_composite_score` | 8-factor score for each stock — quantified quality comparison |
| `get_valuation_snapshot` | Current price, PE, market cap — basic comparison metrics |
| `get_peer_comparison` | Screener peer data for additional context |

**Report sections the prompt MUST produce:**

1. **Quick Verdict Table** — one-row-per-stock summary:

   | Stock | Verdict | Score | Fair Value | Current Price | Margin of Safety | Signal |
   |-------|---------|-------|------------|---------------|------------------|--------|
   | HDFCBANK | BUY | 72 | 1,850 | 1,650 | 12% | UNDERVALUED |
   | ICICIBANK | HOLD | 68 | 1,200 | 1,180 | 2% | FAIR VALUE |

2. **Business Quality Comparison** — which business is better and why (moat, growth, management). Side-by-side, not sequential.

3. **Financial Comparison** — side-by-side table: revenue growth, margins, ROCE, D/E, FCF. Highlight who leads each metric.

4. **Valuation Comparison** — who's cheaper, who's expensive, who has the most upside. PE, PB, EV/EBITDA, DCF margin, analyst targets.

5. **Ownership & Conviction** — who has better institutional backing. FII/MF trends, insider signals.

6. **Risk Comparison** — who's riskier and why. Debt, pledge, volatility, concentration.

7. **The Verdict: If You Can Only Buy One** — definitive answer with reasoning. No fence-sitting. Must name the winner and explain why with specific numbers.

### Briefing Loading Logic

```python
# In agent.py

import json
from datetime import datetime, timezone, timedelta

def _briefings_fresh(symbol: str, max_age_days: int = 7) -> bool:
    """Check if ALL briefings for a stock are recent enough."""
    briefing_dir = Path.home() / "vault" / "stocks" / symbol.upper() / "briefings"
    if not briefing_dir.exists():
        return False
    agents = ["business", "financials", "ownership", "valuation", "risk", "technical"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    for agent in agents:
        path = briefing_dir / f"{agent}.json"
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            gen_at = data.get("generated_at", "")
            if not gen_at:
                return False
            gen_dt = datetime.fromisoformat(gen_at)
            if gen_dt < cutoff:
                return False
        except (json.JSONDecodeError, ValueError):
            return False
    return True


async def _ensure_briefings(
    symbols: list[str], force: bool = False, skip_fetch: bool = False,
    model: str | None = None,
) -> dict[str, dict[str, dict]]:
    """Ensure all stocks have fresh briefings. Returns {symbol: {agent: briefing}}."""
    from flowtracker.research.briefing import load_all_briefings
    from flowtracker.research.refresh import refresh_for_research
    from flowtracker.research.peer_refresh import refresh_peers

    result = {}
    for symbol in symbols:
        briefings = load_all_briefings(symbol)
        if not force and briefings and _briefings_fresh(symbol, max_age_days=7):
            result[symbol] = briefings
        else:
            # Run full pipeline for this stock
            if not skip_fetch:
                refresh_for_research(symbol)
                refresh_peers(symbol)
            envelopes = await run_all_agents(symbol, model=model, verify=True)
            result[symbol] = {name: env.briefing for name, env in envelopes.items()}
    return result
```

### Files to Create/Modify

**MODIFY: `flowtracker/research/prompts.py`**
- Add `COMPARISON_AGENT_PROMPT` — structured comparison framework prompt
- Key prompt requirements:
  - Must enforce side-by-side tables (not sequential stock-by-stock analysis)
  - Must answer: "if you can only buy one, which and why"
  - Must be beginner-friendly (explain PE, ROCE, etc. on first mention)
  - Template variables: stock count and briefing data injected by the caller
  - Must produce all 7 sections listed above

**MODIFY: `flowtracker/research/agent.py`**
- Add `_briefings_fresh(symbol, max_age_days)` helper
- Add `_ensure_briefings(symbols, force, skip_fetch, model)` async function
- Add `run_comparison_agent(symbols: list[str], model: str | None = None) -> BriefingEnvelope`:
  ```python
  async def run_comparison_agent(
      symbols: list[str],
      model: str | None = None,
      skip_fetch: bool = False,
      force: bool = False,
  ) -> BriefingEnvelope:
      """Run comparison agent on 2-5 stocks."""
      # Step 1: Ensure briefings exist and are fresh
      all_briefings = await _ensure_briefings(symbols, force, skip_fetch, model)

      # Step 2: Format briefings for the comparison agent prompt
      briefing_text = ""
      for symbol, briefings in all_briefings.items():
          briefing_text += f"\n### {symbol}\n"
          for agent_name, data in briefings.items():
              briefing_text += f"**{agent_name}:** {json.dumps(data, indent=2)}\n"

      # Step 3: Run comparison agent
      comparison_tools = [get_fair_value, get_composite_score,
                         get_valuation_snapshot, get_peer_comparison]

      user_prompt = (
          f"Compare these {len(symbols)} stocks: {', '.join(symbols)}.\n\n"
          f"## Specialist Briefings\n{briefing_text}\n\n"
          "Use your tools to get current fair value and composite scores for EACH stock. "
          "Produce the full comparative analysis with side-by-side tables."
      )

      return await _run_specialist(
          name="comparison",
          symbol="_vs_".join(symbols),
          system_prompt=COMPARISON_AGENT_PROMPT,
          tools=comparison_tools,
          max_turns=15,
          max_budget=0.60,
          model=model or DEFAULT_MODELS.get("synthesis", "claude-sonnet-4-6"),
          user_prompt=user_prompt,
      )
  ```

**MODIFY: `flowtracker/research_commands.py`**
- Add `compare` command:
  ```python
  @app.command()
  def compare(
      symbols: Annotated[list[str], typer.Argument(help="2-5 stock symbols to compare")],
      skip_fetch: Annotated[bool, typer.Option("--skip-fetch")] = False,
      model: Annotated[str | None, typer.Option("--model", "-m")] = None,
      force: Annotated[bool, typer.Option("--force")] = False,
  ) -> None:
  ```
  - Validates 2-5 symbols
  - Calls `run_comparison_agent()`
  - Calls `assemble_comparison_report()`
  - Opens HTML in browser

**MODIFY: `flowtracker/research/assembly.py`**
- Add `assemble_comparison_report(symbols, comparison_envelope) -> tuple[Path, Path]`:
  - Renders comparison-specific HTML with tables
  - Output path: `reports/{sym1}-vs-{sym2}-comparison.html`
  - Vault path: `~/vault/stocks/_comparisons/{sym1}-vs-{sym2}/{date}.md`
  - Simpler than the full research assembly — just the comparison report, no specialist sections

### Task Breakdown

**T8: Comparison agent prompt (1 hour)**
- File: `flowtracker/research/prompts.py`
- Write `COMPARISON_AGENT_PROMPT` with structured comparison framework
- Must enforce: side-by-side tables (not sequential), definitive verdict, beginner-friendly
- Template variables: `{STOCK_COUNT}`, `{SYMBOLS}`, briefing data injected by caller
- Key instruction: "Every comparison MUST be a table, NOT sequential paragraphs. Never say 'Now let me look at ICICIBANK...' — always compare together."
- Include beginner-friendly rules from `SHARED_PREAMBLE` pattern
- Blocked by: nothing (prompt writing is independent)

**T9: Comparison agent runner + briefing freshness (1 hour)**
- File: `flowtracker/research/agent.py`
- Add `_briefings_fresh()` helper
- Add `_ensure_briefings()` async function
- Add `run_comparison_agent()` function
- Blocked by: T8
- Verify (unit-level):
  ```bash
  uv run python -c "
  from flowtracker.research.agent import _briefings_fresh
  print(_briefings_fresh('HDFCBANK'))
  "
  ```

**T10: Compare CLI command + assembly (1 hour)**
- Files: `flowtracker/research_commands.py`, `flowtracker/research/assembly.py`
- Add `compare` command accepting 2-5 symbols
- Add `assemble_comparison_report()` for comparison-specific HTML
- Open in browser
- Blocked by: T9
- Verify:
  ```bash
  uv run flowtrack research compare HDFCBANK ICICIBANK --skip-fetch
  ```
  (requires existing briefings in vault — run the thesis command for both stocks first if needed)

**T11: Test with different stock types (1 hour)**
- Run comparison on:
  - Banks: `HDFCBANK ICICIBANK KOTAKBANK` (same sector, direct comparison)
  - IT: `TCS INFY` (different size, same sector)
  - Mixed: `RELIANCE HDFCBANK INFY` (different sectors — harder comparison)
- Check: tables are truly side-by-side, verdict is definitive, beginner-friendly
- Iterate prompt if comparison agent produces sequential analysis instead of comparative tables
- Blocked by: T10

### Cost Estimates

| Scenario | Cost | Time |
|----------|------|------|
| 3-stock comparison (briefings exist) | ~$0.40-0.60 (comparison agent only) | 2-3 min |
| 3-stock comparison (no briefings) | ~$5-8 (3 full pipelines + comparison) | 10-15 min |
| 2-stock comparison (briefings exist) | ~$0.30-0.50 | 1-2 min |
| 5-stock comparison (briefings exist) | ~$0.50-0.80 (more tokens) | 3-5 min |
| Implementation | $0 | ~4 hours |

---

## Feature 4: Sector Agent (7th Specialist)

### Goal

Add a 7th specialist agent to the multi-agent research pipeline that analyzes industry-level dynamics: TAM, growth rates, regulatory environment, competitive intensity, sector-level flows. Produces a standalone "Sector & Industry" section in the final report.

This answers: "Is this a good industry to invest in? How is the sector doing overall?"

### User-Facing CLI Commands

```bash
# Run sector agent standalone
flowtrack research run sector -s HDFCBANK           # sector analysis for HDFCBANK's industry

# Full pipeline now includes 7 specialists
flowtrack research thesis -s HDFCBANK               # Phase 1 runs 7 agents (not 6)

# Sector data queries
flowtrack research data sector_overview -s HDFCBANK --raw
flowtrack research data sector_flows -s HDFCBANK --raw
flowtrack research data sector_valuations -s HDFCBANK --raw
```

### Architecture Overview

```
                    Phase 1 (updated: 7 specialists)
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │Business │ │Financial│ │Ownership│ │Valuation│
    │  Agent  │ │  Agent  │ │  Agent  │ │  Agent  │
    └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
    ┌────┴────┐ ┌────┴────┐ ┌────┴────┐
    │  Risk   │ │Technical│ │ SECTOR  │  ← NEW (7th specialist)
    │  Agent  │ │  Agent  │ │  Agent  │
    └────┬────┘ └────┬────┘ └────┬────┘
         │           │           │
         ▼           ▼           ▼
    [7 reports + 7 briefings → verification → synthesis]
```

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| `sector_commands.py` | Working | `sector overview`, `sector detail`, `sector list` |
| `store.get_sector_overview()` | Working | Aggregates ownership shifts by industry |
| `store.get_sector_detail(industry)` | Working | Stock-level ownership data for a sector |
| `store.get_sector_list()` | Working | All industry names from `index_constituents` |
| `sector_benchmarks` table | Working | Per-metric percentile ranks from peer refresh |
| `index_constituents` table | Working | All Nifty 250 stocks with industry classification |
| `mf_scheme_holdings` table | Working | MF scheme-level data (can aggregate by sector) |
| `valuation_snapshot` table | Working | Live prices, PE, margins for all scanned stocks |
| `annual_financials` table | Working | ROCE, revenue, profit for historical data |
| `shareholding_changes` view | Working | QoQ ownership changes per stock |

### Gap Analysis

Existing sector data focuses on **ownership shifts only** (`get_sector_overview` shows FII/MF/DII changes by industry). We need:

1. **Sector-level valuations** — aggregate PE, PB, ROCE across all stocks in the industry
2. **Sector-level MF flows** — total MF money flowing into this sector (scheme-level aggregation)
3. **Sector overview metrics** — stock count, total market cap, median growth, valuation range
4. **Web research** — TAM, growth drivers, regulatory landscape (not in any DB — agent uses WebSearch/WebFetch)

### New Data Methods

**`store.py` — 3 new methods:**

```python
def get_sector_valuation_summary(self, industry: str) -> dict:
    """Aggregate valuation metrics across all stocks in an industry.

    SQL joins index_constituents → valuation_snapshot (latest per stock)
    → annual_financials (latest per stock for ROCE).

    Returns: {
        industry: str,
        stock_count: int,
        total_mcap_cr: float,
        median_pe: float,
        median_pb: float,
        median_roce: float,
        pe_range: {min: float, max: float},
        top_by_mcap: [{symbol, company_name, mcap_cr, pe}, ...],  # top 5
    }
    """

def get_sector_mf_flows(self, industry: str) -> dict:
    """Aggregate MF holdings changes across all stocks in an industry.

    SQL joins index_constituents → shareholding_changes (MF category).

    Returns: {
        industry: str,
        total_stocks: int,
        mf_increased: int,       # stocks where MF% increased QoQ
        mf_decreased: int,       # stocks where MF% decreased QoQ
        avg_mf_change_pct: float,
        top_additions: [{symbol, mf_change_pct}, ...],   # top 5 biggest increases
        top_reductions: [{symbol, mf_change_pct}, ...],  # top 5 biggest decreases
    }
    """

def get_sector_stocks_ranked(self, industry: str) -> list[dict]:
    """Get all stocks in an industry with key metrics, ranked by market cap.

    SQL joins index_constituents → valuation_snapshot → shareholding
    (latest FII/MF percentages) → annual_financials (latest ROCE).

    Returns: [{
        symbol, company_name, mcap_cr, pe, roce_pct,
        fii_pct, mf_pct, price_change_1yr_pct
    }, ...]
    """
```

### New MCP Tools (3)

| Tool | Description | Data Source | Used By |
|------|-------------|-------------|---------|
| `get_sector_overview_metrics` | Stock count, total market cap, median PE/PB/ROCE, valuation range, top stocks by mcap for the industry of a given stock | `get_sector_valuation_summary()` | Sector agent |
| `get_sector_flows` | Aggregate MF/FII/DII ownership changes for the industry. Which stocks are MFs piling into, which are they exiting? | `get_sector_mf_flows()` | Sector agent |
| `get_sector_valuations` | All stocks in the industry ranked by key metrics. Where does the subject stock rank? | `get_sector_stocks_ranked()` | Sector agent |

### Tool Definitions

```python
@tool(
    "get_sector_overview_metrics",
    "Get industry-level overview: stock count, total market cap, median PE/PB/ROCE, "
    "valuation range, top stocks. Looks up the industry from the given stock's classification.",
    {"symbol": str},
)
async def get_sector_overview_metrics(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_overview_metrics(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

@tool(
    "get_sector_flows",
    "Get aggregate institutional ownership changes across all stocks in the subject's industry. "
    "Shows which stocks MFs are accumulating, which they're exiting, and net sector flow direction.",
    {"symbol": str},
)
async def get_sector_flows(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_flows(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}

@tool(
    "get_sector_valuations",
    "Get all stocks in the subject's industry ranked by market cap, with key metrics: "
    "PE, ROCE, FII%, MF%, price change. Shows where the subject ranks among peers.",
    {"symbol": str},
)
async def get_sector_valuations(args):
    with ResearchDataAPI() as api:
        data = api.get_sector_valuations(args["symbol"])
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
```

### Sector Agent Specification

**Model:** `claude-sonnet-4-6`
**Max turns:** 25
**Max budget:** $0.50

**Tools (12 + WebSearch/WebFetch built-ins):**

| Tool | Why |
|------|-----|
| `get_company_info` | Identify the stock's industry classification |
| `get_sector_overview_metrics` | Industry-level metrics: size, valuation, quality |
| `get_sector_flows` | Where is institutional money flowing in this sector |
| `get_sector_valuations` | All stocks ranked — competitive landscape |
| `get_peer_comparison` | Direct peers with financial metrics |
| `get_peer_metrics` | FMP deep metrics for peers |
| `get_peer_growth` | Growth rate comparison across peers |
| `get_sector_benchmarks` | Statistical benchmarks (median, percentile) |
| `get_macro_snapshot` | Macro factors affecting the sector |
| `get_fii_dii_flows` | Market-wide flow context |
| `get_fii_dii_streak` | Institutional momentum |
| `render_chart` | Charts for visual context |

**Built-ins:** `WebSearch` and `WebFetch` (like Business agent) for TAM, regulatory research, industry reports.

**Report sections produced:**

1. **Industry Overview** — what is this industry, how big is it, who are the players. Include mermaid market structure diagram showing key players and their relative size.
2. **Sector Growth & TAM** — total addressable market, growth drivers, headwinds. Web research for macro industry context. Explain TAM: "Think of TAM as the total size of the pie that all companies in this industry are competing for."
3. **Competitive Landscape** — all stocks in the industry ranked by market cap. Where does the subject sit? Who's winning market share? Include table with key metrics per player.
4. **Institutional Money Flow** — where is smart money going within this sector? Which stocks are MFs piling into vs exiting? Aggregate flow direction.
5. **Sector Valuation Map** — is the sector cheap or expensive overall? Median PE, PE range, who's the cheapest quality stock? Visual representation of where each stock sits.
6. **Regulatory & Macro** — key regulations, government policy impact, macro sensitivity (rates for banks, crude for oil, rupee for IT). Web research for recent regulatory developments.
7. **Where {COMPANY} Fits** — synthesize: is this company a sector leader, challenger, or niche player? Does sector tailwind help or headwind hurt? Specific ranking on each dimension.

**Structured briefing output:**
```json
{
  "agent": "sector",
  "symbol": "HDFCBANK",
  "industry": "Financial Services",
  "confidence": 0.80,
  "sector_size_cr": 5200000,
  "stock_count": 42,
  "sector_growth_signal": "growing",
  "sector_valuation_signal": "fair_value",
  "median_pe": 18.5,
  "median_roce": 14.2,
  "institutional_flow": "net_accumulation",
  "competitive_position": "leader",
  "regulatory_risk": "medium",
  "key_sector_tailwinds": ["credit growth", "digital adoption", "rate cycle"],
  "key_sector_headwinds": ["NPA risk", "regulatory tightening"],
  "top_sector_picks": ["HDFCBANK", "ICICIBANK", "BAJFINANCE"]
}
```

### Files to Create/Modify

**MODIFY: `flowtracker/store.py`** (~2900 lines)
- Add 3 new query methods after existing sector methods:
  - `get_sector_valuation_summary(industry: str) -> dict`
  - `get_sector_mf_flows(industry: str) -> dict`
  - `get_sector_stocks_ranked(industry: str) -> list[dict]`
- SQL patterns:
  - Join `index_constituents` to `valuation_snapshot` for PE/PB/market cap
  - Join to `annual_financials` (latest row per symbol) for ROCE
  - Join to `shareholding_changes` for ownership shifts
  - Use `GROUP BY` with `AVG()`, `MIN()`, `MAX()` for sector aggregates
  - Compute median in Python (SQLite doesn't have native `MEDIAN()`)
- Follow existing method patterns: raw SQL → fetchall → dict comprehension

**MODIFY: `flowtracker/research/data_api.py`**
- Add 3 data API methods that look up industry from symbol, then call store:
  ```python
  def get_sector_overview_metrics(self, symbol: str) -> dict:
      info = self.get_company_info(symbol)
      industry = info.get("industry", "Unknown")
      if industry == "Unknown":
          return {"error": f"No industry found for {symbol}"}
      return _clean(self._store.get_sector_valuation_summary(industry))

  def get_sector_flows(self, symbol: str) -> dict:
      info = self.get_company_info(symbol)
      industry = info.get("industry", "Unknown")
      return _clean(self._store.get_sector_mf_flows(industry))

  def get_sector_valuations(self, symbol: str) -> list[dict]:
      info = self.get_company_info(symbol)
      industry = info.get("industry", "Unknown")
      return _clean(self._store.get_sector_stocks_ranked(industry))
  ```

**MODIFY: `flowtracker/research/tools.py`**
- Add 3 new sector MCP tools (defined above)
- Create `SECTOR_AGENT_TOOLS` registry:
  ```python
  SECTOR_AGENT_TOOLS = [
      get_company_info, get_sector_overview_metrics, get_sector_flows,
      get_sector_valuations, get_peer_comparison,
      get_peer_metrics, get_peer_growth, get_sector_benchmarks,
      get_macro_snapshot, get_fii_dii_flows, get_fii_dii_streak,
      render_chart,
  ]  # 12 tools
  ```
- Add to `RESEARCH_TOOLS` list for completeness

**MODIFY: `flowtracker/research/prompts.py`**
- Add `SECTOR_AGENT_PROMPT` — sector analysis framework
- Must use `SHARED_PREAMBLE` pattern (beginner-friendly rules, peer benchmarking rules)
- Sections: industry overview, TAM, competitive landscape, institutional flows, valuation map, regulatory/macro, company positioning
- Inline explanation requirements: "TAM", "competitive intensity", "market share", "regulatory risk"
- Add sector to `AGENT_PROMPTS` dict

**MODIFY: `flowtracker/research/agent.py`**
- Add "sector" to all config dicts:
  ```python
  DEFAULT_MODELS["sector"] = "claude-sonnet-4-6"
  AGENT_TOOLS["sector"] = SECTOR_AGENT_TOOLS
  AGENT_MAX_TURNS["sector"] = 25
  AGENT_MAX_BUDGET["sector"] = 0.50
  AGENT_ALLOWED_BUILTINS["sector"] = ["WebSearch", "WebFetch"]
  ```
- Update `run_all_agents()` — add "sector" to `agent_names` list (now 7 items)
- Update `_analyze_briefing_signals()` — add sector signal cross-references:
  ```python
  sector = briefings.get("sector", {})
  sector_signal = sector.get("sector_growth_signal", "")
  sector_valuation = sector.get("sector_valuation_signal", "")

  # Sector growing + stock undervalued = tailwind opportunity
  if sector_signal == "growing" and "UNDERVALUED" in str(val_signal).upper():
      cross_signals.append("Sector growing + stock undervalued = riding sector tailwind at a discount.")

  # Sector expensive + stock expensive = double risk
  if sector_valuation == "expensive" and "EXPENSIVE" in str(val_signal).upper():
      cross_signals.append("Both sector and stock are expensive — correction risk is amplified.")
  ```

**MODIFY: `flowtracker/research/assembly.py`**
- Add sector section to `report_order` list (after Risk, before Technical):
  ```python
  report_order = [
      ("business", "The Business"),
      ("financials", "Financial Analysis"),
      ("valuation", "Valuation"),
      ("ownership", "Ownership Intelligence"),
      ("risk", "Risk Assessment"),
      ("sector", "Sector & Industry"),    # ← NEW
      ("technical", "Technical & Market Context"),
  ]
  ```
- Update metadata string: "7 specialists" instead of "6 specialists"

**MODIFY: `flowtracker/research_commands.py`**
- Add "sector" to `VALID_AGENTS` set (line 514)
- Add sector data tools to `_DATA_TOOLS` list:
  ```python
  _DATA_TOOLS = [
      # ... existing tools ...
      "sector_overview", "sector_flows", "sector_valuations",
  ]
  ```
- Add to `method_map`:
  ```python
  "sector_overview": lambda api: api.get_sector_overview_metrics(symbol),
  "sector_flows": lambda api: api.get_sector_flows(symbol),
  "sector_valuations": lambda api: api.get_sector_valuations(symbol),
  ```
- Update docstrings referencing "6 agents" to "7 agents"

### Task Breakdown

**T12: Store methods for sector aggregation (1 hour)**
- File: `flowtracker/store.py`
- Add 3 new query methods: `get_sector_valuation_summary`, `get_sector_mf_flows`, `get_sector_stocks_ranked`
- SQL joins across `index_constituents`, `valuation_snapshot`, `shareholding_changes`, `annual_financials`
- Median computation in Python (fetch all values, sort, pick middle)
- Blocked by: nothing
- Verify:
  ```bash
  uv run python -c "
  from flowtracker.store import FlowStore
  with FlowStore() as store:
      summary = store.get_sector_valuation_summary('Financial Services')
      print(f'Stocks: {summary.get(\"stock_count\")}, Median PE: {summary.get(\"median_pe\")}')
      flows = store.get_sector_mf_flows('Financial Services')
      print(f'MF increased in {flows.get(\"mf_increased\")} stocks')
      ranked = store.get_sector_stocks_ranked('Financial Services')
      print(f'Ranked: {len(ranked)} stocks, top: {ranked[0][\"symbol\"] if ranked else \"none\"}')
  "
  ```

**T13: Data API + MCP tools (45 min)**
- Files: `flowtracker/research/data_api.py`, `flowtracker/research/tools.py`
- Add 3 data API methods wrapping store (with industry lookup from symbol)
- Add 3 MCP tools wrapping data API
- Create `SECTOR_AGENT_TOOLS` registry (12 tools)
- Blocked by: T12
- Verify:
  ```bash
  uv run flowtrack research data sector_overview -s HDFCBANK --raw
  uv run flowtrack research data sector_flows -s HDFCBANK --raw
  uv run flowtrack research data sector_valuations -s HDFCBANK --raw
  ```

**T14: Sector agent prompt (1 hour)**
- File: `flowtracker/research/prompts.py`
- Write `SECTOR_AGENT_PROMPT` with `SHARED_PREAMBLE`
- Must produce: industry overview, TAM, competitive landscape, flows, valuation map, regulatory, positioning
- Include inline explanation requirements: "TAM", "competitive intensity", "market share"
- Add to `AGENT_PROMPTS` dict
- Blocked by: nothing (prompt writing is independent)

**T15: Wire sector agent into pipeline (45 min)**
- Files: `flowtracker/research/agent.py`, `flowtracker/research/assembly.py`, `flowtracker/research_commands.py`
- Add sector to agent config dicts (tools, turns, budget, model, builtins)
- Update `run_all_agents()` to include sector (7 agents)
- Update `_analyze_briefing_signals()` to cross-reference sector signals
- Update assembly order (sector between risk and technical)
- Update CLI valid agents set + data tools list
- Blocked by: T13, T14
- Verify:
  ```bash
  uv run flowtrack research run sector -s HDFCBANK --skip-fetch
  ```

**T16: Integration test (30 min)**
- Run full pipeline: `uv run flowtrack research thesis -s HDFCBANK --skip-verify --skip-fetch`
- Check: sector section appears in final report
- Check: synthesis agent references sector briefing
- Check: 7 agents listed in cost summary
- Check: sector report is beginner-friendly with TAM, competitive landscape, regulatory context
- Iterate prompt if needed
- Blocked by: T15

### Cost Estimates

| Scenario | Cost | Time |
|----------|------|------|
| Sector agent standalone | ~$0.30-0.50 | 2-3 min |
| Full pipeline (7 agents + verify) | ~$2.30-4.00 (was $2.00-3.50) | 4-8 min |
| Implementation | $0 | ~4 hours |
| Store methods | No API calls (DB aggregation) | Instant |

---

## Implementation: Complete Task Breakdown

### Codebase Context

```
Project root: /Users/tarang/Documents/Projects/equity-research/flow-tracker/
Package:      flowtracker (Python 3.12+, managed with uv)
CLI:          uv run flowtrack <command>
DB:           ~/.local/share/flowtracker/flows.db (SQLite)
Vault:        ~/vault/stocks/{SYMBOL}/
Reports:      ~/Documents/Projects/equity-research/flow-tracker/reports/
Agent SDK:    claude-agent-sdk>=0.1.50 (in pyproject.toml)

Key patterns:
- MCP tools: @tool decorator, return {"content": [{"type": "text", "text": json}]}
- Store: context manager (with FlowStore() as store:), SQLite, upsert patterns
- CLI: Typer subcommand groups, Rich console for display
- 4-file module pattern: models → client → display → commands
- All monetary values in crores (₹1 Cr = 10M)
- Symbols uppercase, yfinance uses .NS suffix
- NSE clients: preflight GET for cookies, retry + exponential backoff
```

### Dependency Graph

```
Feature 1: Quantitative Ranking (independent, do first)
  T1: ScreenerEngine weights + filtering ──┐
  T2: CLI rank command ────────────────────┤── T3: Display improvements
                                           │
Feature 2: Catalyst Calendar (independent of Feature 1)
  T4: CatalystEvent models ──┐
  T5: Catalyst client ───────┤── T6: Display + commands ──┐
                             └── T7: MCP tool             │
                                                          │
Feature 3: Peer Comparison (independent of Features 1-2)  │
  T8: Comparison prompt ──┐                               │
  T9: Comparison runner ──┤── T10: CLI + assembly ── T11: Integration test
                          │
Feature 4: Sector Agent (independent of Features 1-3)
  T12: Store sector methods ──┐
  T13: Data API + MCP tools ──┤── T15: Wire into pipeline ── T16: Integration test
  T14: Sector prompt ─────────┘
```

### Batch Execution Plan

**Batch 1: Quick wins — foundation tasks (parallel, no dependencies)**
Duration: ~1 hour

```
Dispatch in parallel:
  ├─ T1:  ScreenerEngine weights + filtering    (screener_engine.py)
  ├─ T4:  CatalystEvent models                  (catalyst_models.py — NEW)
  ├─ T8:  Comparison agent prompt               (research/prompts.py)
  ├─ T12: Store sector aggregation methods      (store.py)
  └─ T14: Sector agent prompt                   (research/prompts.py)
```

**Batch 2: Core implementation (depends on Batch 1)**
Duration: ~2 hours

```
Dispatch in parallel:
  ├─ T2 + T3: Rank CLI + display               (screener_commands.py + screener_display.py)
  │           depends on: T1
  ├─ T5:  Catalyst client                       (catalyst_client.py — NEW)
  │           depends on: T4
  ├─ T9:  Comparison agent runner               (research/agent.py)
  │           depends on: T8
  └─ T13: Sector data API + MCP tools           (research/data_api.py + research/tools.py)
              depends on: T12
```

**Batch 3: CLI wiring (depends on Batch 2)**
Duration: ~1.5 hours

```
Dispatch in parallel:
  ├─ T6:  Catalyst display + commands           (catalyst_display.py + catalyst_commands.py — NEW)
  │           depends on: T5
  ├─ T7:  Catalyst MCP tool                     (research/tools.py + research/data_api.py)
  │           depends on: T5
  ├─ T10: Compare CLI + assembly                (research_commands.py + research/assembly.py)
  │           depends on: T9
  └─ T15: Wire sector into pipeline             (research/agent.py + assembly.py + research_commands.py)
              depends on: T13, T14
```

**Batch 4: Integration testing (depends on Batch 3)**
Duration: ~1.5 hours

```
Sequential:
  T11: Test peer comparison with 3 stock type combinations
  T16: Test sector agent in full pipeline
  Final: Run full pipeline with all 4 features to verify no regressions
```

### Verification Commands

```bash
# Feature 1: Ranking
uv run flowtrack screen rank --top 5
uv run flowtrack screen rank --top 5 --industry "Financial Services"
uv run flowtrack screen rank --top 10 --weight valuation=0.3 --weight quality=0.3 --weight ownership=0.4
uv run flowtrack screen rank --top 20 --min-score 60

# Feature 2: Catalyst
uv run flowtrack catalyst -s HDFCBANK
uv run flowtrack catalyst -s RELIANCE --days 180
uv run flowtrack research data upcoming_catalysts -s HDFCBANK --raw

# Feature 3: Comparison
uv run flowtrack research compare HDFCBANK ICICIBANK --skip-fetch
uv run flowtrack research compare HDFCBANK ICICIBANK KOTAKBANK --skip-fetch

# Feature 4: Sector
uv run flowtrack research run sector -s HDFCBANK --skip-fetch
uv run flowtrack research data sector_overview -s HDFCBANK --raw
uv run flowtrack research data sector_flows -s HDFCBANK --raw
uv run flowtrack research data sector_valuations -s HDFCBANK --raw
uv run flowtrack research thesis -s HDFCBANK --skip-verify --skip-fetch  # full 7-agent pipeline

# Verify no regressions
uv run flowtrack screen top -n 5
uv run flowtrack research run business -s INDIAMART --skip-fetch
uv run flowtrack research thesis -s INDIAMART --skip-fetch --skip-verify
```

### Total Cost & Time Estimates

| Feature | Implementation Time | API Cost per Use | Complexity |
|---------|-------------------|------------------|------------|
| Quantitative Ranking | 1 hour | $0 (cached data) | Low — extend existing engine |
| Catalyst Calendar | 2.5 hours | $0 (free APIs + DB) | Medium — new module, 4 sources |
| Peer Comparison | 4 hours | $0.40-8.00 | Medium — new agent + assembly |
| Sector Agent | 4 hours | $0.30-0.50 per run | High — modifies agent pipeline |
| **Total** | **~11.5 hours** | Varies | |

### Priority Order

1. **Quantitative Ranking** — lowest effort, immediate daily value, no new dependencies, extends existing working code
2. **Catalyst Calendar** — low effort, high daily value ("what's happening this week?"), new module but simple data aggregation
3. **Peer Comparison** — medium effort, high research value, leverages existing pipeline and briefings
4. **Sector Agent** — highest effort, deepest insight, modifies existing multi-agent pipeline (highest risk of regressions)

### Session Notes

- Consider implementing Features 1+2 in one session (fast, independent), Features 3+4 in a second session (more complex, touch agent pipeline)
- All 4 features are independent — can be done in any order without blocking
- Feature 4 (Sector Agent) modifies the multi-agent pipeline; test the existing pipeline still works after changes
- Worktree recommended: `git worktree add ../equity-research-p0 -b feat/p0-features main`
- Feature 3 depends on existing briefings in vault — run `flowtrack research thesis` for test stocks first if vault is empty
- Feature 4 adds cost to every full pipeline run (~$0.30-0.50 per stock), but sector context significantly improves synthesis quality
