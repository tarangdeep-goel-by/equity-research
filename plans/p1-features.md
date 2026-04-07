# P1 Features — Future Implementation Phase

> Created: 2026-03-31
> Status: Planning — not ready for implementation
> Prerequisite: P0 features complete (ranking, catalysts, comparison, sector agent)
> Project: `./flow-tracker/`
> Branch: TBD per feature

## Quick Reference

- **7 features** across 3 priority tiers
- **Tier A (high value, moderate effort):** Historical Thesis Tracking, Portfolio Integration, Automated Research Triggers
- **Tier B (high value, high effort):** News/Sentiment Monitoring, Web Dashboard/UI
- **Tier C (nice-to-have):** Multi-timeframe Analysis, Export to Notion/Google Sheets
- **Most impactful first:** Portfolio Integration + Automated Triggers together create a "set and forget" research workflow
- **Biggest effort:** Web Dashboard (~2-3 weeks) — should be its own epic

---

## Feature 1: Historical Thesis Tracking

### Goal

Track how conviction evolves over time for a stock. "What did I think 3 months ago vs now?" Compare thesis conditions, research verdicts, and key metrics across multiple research runs for the same stock.

This answers: "Am I changing my mind about this stock? Is my original thesis holding up?"

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| Thesis tracker conditions | Working | `research/thesis_tracker.py` — YAML frontmatter conditions evaluated against live data |
| Thesis check command | Working | `research thesis-check -s SYMBOL` — evaluates conditions, updates statuses |
| Briefing envelopes | Working | `~/vault/stocks/{SYMBOL}/briefings/{agent}.json` — structured JSON with metrics, signal, confidence |
| Synthesis reports with verdicts | Working | `~/vault/stocks/{SYMBOL}/reports/synthesis.md` — BUY/HOLD/SELL verdict |
| Generated_at timestamps | Working | `BriefingEnvelope.generated_at` field in every briefing |
| Date-stamped thesis reports | Working | `~/vault/stocks/{SYMBOL}/thesis/{DATE}.md` |

### Gap

Currently each research run **overwrites** the previous briefings. There's no timeline view, no comparison between runs, no "conviction changed from HOLD to BUY" tracking.

### Rough Approach

**Data storage — version briefings instead of overwriting:**
- Change `save_envelope()` in `briefing.py` to save with timestamp suffix: `business_2026-03-31.json` (keep `business.json` as a symlink or copy of latest)
- Add `load_briefing_history(symbol, agent)` that returns all historical envelopes sorted by date
- Add `load_verdict_history(symbol)` that extracts verdict + confidence + key metrics from each synthesis briefing

**New CLI commands:**
```bash
# Show thesis evolution timeline
flowtrack research history -s INDIAMART
# Output: table showing date | verdict | confidence | key metric changes

# Diff two research runs
flowtrack research diff -s INDIAMART --date1 2026-01-15 --date2 2026-03-31
# Output: side-by-side comparison of briefing metrics, highlighting changes

# Conviction timeline chart
flowtrack research history -s INDIAMART --chart
# Output: ASCII or PNG timeline showing verdict + key metric trajectory
```

**New DB table (optional):**
```sql
CREATE TABLE IF NOT EXISTS thesis_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    run_date TEXT NOT NULL,
    verdict TEXT,           -- BUY/HOLD/SELL
    confidence REAL,
    composite_score REAL,
    fair_value REAL,
    current_price REAL,
    margin_of_safety_pct REAL,
    key_changes TEXT,       -- JSON summary of what changed from previous run
    UNIQUE(symbol, run_date)
);
```
Alternatively, derive everything from versioned briefing files — no new table.

**Files to modify:**
- `flowtracker/research/briefing.py` — versioned save, history loader
- `flowtracker/research_commands.py` — `history` and `diff` commands
- `flowtracker/research/assembly.py` — optional timeline section in reports

**Estimated effort:** 4-6 hours
**Estimated cost:** $0 (reads existing vault data)

---

## Feature 2: Portfolio Integration

### Goal

Connect research output to portfolio decisions. "How does adding HDFCBANK affect my portfolio's sector concentration, risk, and correlation?" Show research context alongside portfolio positions.

This answers: "Should I buy this stock given what I already own?"

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| Portfolio tracker | Working | `portfolio_commands.py` — add/remove holdings, live P&L, sector concentration |
| Holdings model | Working | `portfolio_models.py` — `PortfolioHolding` with symbol, qty, avg_cost |
| P&L calculation | Working | `portfolio_display.py` — live price from `valuation_snapshot`, unrealized P&L |
| Sector concentration | Working | `portfolio_display.py` — `display_portfolio_concentration()` |
| Fair value model | Working | `research/data_api.py` → `get_fair_value()` |
| Composite score | Working | `screener_engine.py` → `ScreenerEngine.score_stock()` |
| Thesis tracker | Working | `research/thesis_tracker.py` |

### Gap

Portfolio and research are disconnected. No "what-if" analysis, no research overlay on portfolio, no "buy this to improve diversification" logic.

### Rough Approach

**New commands:**
```bash
# Research overlay on portfolio — show each holding with research verdict + fair value
flowtrack portfolio research
# Output: holdings table enriched with verdict, fair value, margin of safety, composite score

# What-if analysis — simulated impact of adding a stock
flowtrack portfolio what-if HDFCBANK --qty 50 --cost 1650
# Output:
#   Current concentration: IT 45%, Financial 20%, ...
#   After adding HDFCBANK: IT 38%, Financial 28%, ...
#   Correlation impact: portfolio beta changes from 1.1 to 1.0
#   Research verdict for HDFCBANK: BUY (72 score, 12% margin of safety)

# Portfolio-aware research — flag positions where thesis has weakened
flowtrack portfolio alerts
# Output: holdings where thesis-check has failing conditions, or composite score dropped
```

**Integration points:**
1. `portfolio research` — read holdings from `portfolio_holdings` table, enrich each with latest briefing verdict + fair value + composite score
2. `portfolio what-if` — simulate adding a holding, recompute sector concentration from `index_constituents.industry`, estimate beta impact from `valuation_snapshot.beta`
3. `portfolio alerts` — for each holding, run `evaluate_conditions()` from thesis tracker, flag failing/stale conditions
4. New MCP tool `get_portfolio_context` — agent tool that shows current portfolio for context during research

**Files to create/modify:**
- `flowtracker/portfolio_commands.py` — add `research`, `what-if`, `alerts` subcommands
- `flowtracker/portfolio_display.py` — enriched display with research columns
- `flowtracker/research/tools.py` — `get_portfolio_context` MCP tool
- `flowtracker/research/data_api.py` — `get_portfolio_context()` method

**Estimated effort:** 6-8 hours
**Estimated cost:** $0 (all cached data)

---

## Feature 3: News/Sentiment Monitoring

### Goal

Proactive monitoring of watchlist/portfolio stocks. "What happened to my stocks today?" via news headlines, price alerts, and sentiment signals.

This answers: "Did anything important happen while I wasn't looking?"

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| Alert system | Working | `alert_engine.py` — 10 condition types evaluated against cached data |
| Watchlist | Working | `store.get_watchlist()` / `store.add_to_watchlist()` |
| BSE filings | Working | `filing_client.py` — corporate filings fetched and stored |
| yfinance data | Working | Live price, volume from `valuation_snapshot` table |

### Gap

No news feed. No "this stock just dropped 5% — here's why" context. No RSS/news aggregation. Alert system checks conditions but doesn't provide narrative context.

### Rough Approach

**Data sources for news:**
1. **Google News RSS** — `https://news.google.com/rss/search?q={company_name}+stock` — free, no auth, parse XML
2. **BSE filings** (already have) — flag new filings since last check
3. **Price moves** — compute from `valuation_snapshot` table: flag >3% daily moves, new 52-week highs/lows
4. **yfinance news** — `Ticker.news` attribute — returns recent news articles with titles and links

**New commands:**
```bash
# Morning digest — what happened overnight
flowtrack pulse
# Output: for each watchlist/portfolio stock:
#   Price: 1650 (+2.3%)
#   News: "HDFC Bank Q3 profit up 33%..." (2 articles)
#   Filings: Board meeting notice filed (yesterday)
#   Alert: price crossed 1600 target

# Single stock deep news
flowtrack news -s HDFCBANK --days 7
# Output: news headlines with links, sentiment tags, source

# Monitor mode (could be cron job)
flowtrack pulse --notify
# Output: same as pulse, but formatted for notification (short, actionable)
```

**New module (4-file pattern):**
- `news_models.py` — `NewsItem(title, url, source, published_at, sentiment)`
- `news_client.py` — Google News RSS parser + yfinance news fetch + price move detector
- `news_display.py` — Rich table with color-coded sentiment
- `news_commands.py` — `pulse` and `news` commands

**Sentiment (simple v1):**
- Keyword-based: "profit up", "revenue growth", "beat estimates" = positive
- "loss", "fraud", "downgrade", "miss" = negative
- Everything else = neutral
- No ML models needed for v1

**Cron integration:**
- New `daily-pulse.sh` script for morning digest
- Could integrate with alert system: when alert triggers, also fetch news for context

**Files to create:**
- `flowtracker/news_models.py`
- `flowtracker/news_client.py`
- `flowtracker/news_display.py`
- `flowtracker/news_commands.py`
- `scripts/daily-pulse.sh`

**Files to modify:**
- `flowtracker/main.py` — register news/pulse commands

**Estimated effort:** 8-10 hours
**Estimated cost:** $0 (all free APIs)
**Risk:** Google News RSS may be rate-limited or change format. yfinance `.news` is unreliable for Indian stocks.

---

## Feature 4: Web Dashboard/UI

### Goal

A web interface to browse research reports, charts, portfolio, and screening results. The terminal is powerful but hard to read for dense financial data. The user has asked for this multiple times.

This answers: "Can I see all this data in a proper UI instead of terminal tables?"

### What Already Exists

| Component | Status | What it provides |
|-----------|--------|-----------------|
| HTML reports | Working | `agent.py` renders business profiles and thesis reports as styled HTML |
| Chart PNGs | Working | `research/charts.py` — 13 chart types via matplotlib |
| REST-like data layer | Working | `ResearchDataAPI` with 35+ methods returning clean dicts |
| SQLite DB | Working | All data in `~/.local/share/flowtracker/flows.db` |
| Portfolio data | Working | Holdings, P&L, sector concentration |
| Screening scores | Working | Composite 8-factor scoring |

### Gap

No web server. No interactive UI. Reports are static HTML opened with `open` command. No way to browse multiple reports, compare charts, or interact with screening data.

### Rough Approach

**Technology choice:** FastAPI backend + plain HTML/HTMX frontend (no React/Vue — keep simple for single-user tool)

Rationale: The user already has FastAPI experience (ai-data-analyst-v2 project). HTMX keeps frontend simple — server-rendered HTML fragments, no build step, no npm. TailwindCSS via CDN for styling.

**Architecture:**
```
flowtrack dashboard                    ← starts web server
    │
    ├── FastAPI app (dashboard/app.py)
    │   ├── /                          ← Home: portfolio overview + alerts
    │   ├── /research/{symbol}         ← Full research report (rendered HTML)
    │   ├── /compare/{sym1}/{sym2}     ← Comparison report
    │   ├── /screen                    ← Interactive screening table
    │   ├── /screen/{symbol}           ← Single stock scorecard
    │   ├── /portfolio                 ← Portfolio with live P&L
    │   ├── /catalysts                 ← Catalyst calendar view
    │   ├── /api/...                   ← JSON API wrapping ResearchDataAPI
    │   └── /api/chart/{symbol}/{type} ← Chart PNG endpoint
    │
    ├── Jinja2 templates (dashboard/templates/)
    │   ├── base.html                  ← Layout with nav, TailwindCSS
    │   ├── home.html                  ← Portfolio + alerts + recent research
    │   ├── research.html              ← Research report viewer
    │   ├── screen.html                ← Screening table with HTMX sorting/filtering
    │   └── portfolio.html             ← Holdings table
    │
    └── ResearchDataAPI (existing)     ← All data comes from existing API layer
```

**Key design decisions:**
1. **Read-only for v1** — dashboard only reads data, doesn't trigger agent runs. Use CLI for writes.
2. **No authentication** — single-user tool, runs on localhost only.
3. **No separate database** — reads directly from existing SQLite via FlowStore/ResearchDataAPI.
4. **HTMX for interactivity** — sorting, filtering, drill-down without full page reloads.
5. **Charts served as PNG** — reuse existing `research/charts.py`, serve via `/api/chart/{symbol}/{type}`.
6. **Research reports served as HTML** — render existing vault markdown/HTML files.

**Files to create:**
```
flowtracker/dashboard/
├── __init__.py
├── app.py              ← FastAPI app, routes
├── templates/
│   ├── base.html       ← Layout, nav, TailwindCSS CDN
│   ├── home.html
│   ├── research.html
│   ├── screen.html
│   ├── portfolio.html
│   └── catalysts.html
└── static/             ← minimal CSS overrides if needed
```

**Files to modify:**
- `flowtracker/main.py` — add `dashboard` command that starts uvicorn
- `pyproject.toml` — add `fastapi`, `uvicorn`, `jinja2` dependencies

**Estimated effort:** 2-3 weeks (this is a Medium-Large project)
**Estimated cost:** $0
**Risk:** Scope creep. Start with read-only portfolio + research viewer, add features incrementally.

### Recommended Phasing

| Phase | What | Time |
|-------|------|------|
| Phase 1 | Home page + portfolio view + research report viewer | 3-4 days |
| Phase 2 | Screening table with sorting/filtering | 2 days |
| Phase 3 | Catalyst calendar + alerts view | 2 days |
| Phase 4 | Charts integration + interactive drill-down | 2-3 days |
| Phase 5 | Polish: responsive, dark theme matching HTML reports | 1-2 days |

---

## Feature 5: Automated Research Triggers

### Goal

"When a stock in my watchlist drops 10%, auto-run the full pipeline." Connect the alert system to the research agent system.

This answers: "Something happened — should I be worried? Should I buy the dip?"

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| Alert system | Working | `alert_engine.py` — evaluates conditions, logs triggers |
| Alert types | Working | 10 types: price_above/below, pe_above/below, rsi, fii_pct, pledge, dcf_upside |
| Cron scripts | Working | `scripts/daily-fetch.sh` runs data refresh on schedule |
| Research pipeline | Working | `research thesis -s SYMBOL` runs full multi-agent analysis |
| Thesis tracker | Working | Condition-based conviction monitoring |

### Gap

Alerts fire but don't trigger any action. The user has to manually notice an alert and manually run the research pipeline.

### Rough Approach

**Alert-to-research bridge:**
```python
# In alert_engine.py — new field on Alert model
class Alert(BaseModel):
    # ... existing fields ...
    auto_research: bool = False  # when triggered, auto-run research pipeline
    research_scope: str = "quick"  # "quick" (just valuation+risk) or "full" (all 7 agents)
```

**New commands:**
```bash
# Set an alert that triggers research
flowtrack alert add HDFCBANK price_below 1500 --auto-research
flowtrack alert add SBIN pe_below 8 --auto-research --scope full

# Check alerts and run triggered research
flowtrack alert check --execute
# Output:
#   HDFCBANK triggered price_below 1500 (current: 1480)
#   → Running quick research (valuation + risk agents)...
#   → Verdict: BUY — stock is 15% below fair value, risk metrics unchanged
```

**Implementation approach:**
1. Add `auto_research` and `research_scope` fields to `Alert` model and `alerts` DB table
2. In `alert_engine.py`, after a trigger with `auto_research=True`, queue a research run
3. "Quick research" = run only valuation + risk agents (fastest, cheapest — ~$0.40)
4. "Full research" = run all 7 agents + synthesis (~$2-4)
5. Research result summary appended to alert trigger log
6. Cron: add `--execute` flag to `daily-fetch.sh`'s alert check

**Files to modify:**
- `flowtracker/alert_models.py` — add `auto_research`, `research_scope` fields
- `flowtracker/alert_engine.py` — trigger research after alert fires
- `flowtracker/alert_commands.py` — `--auto-research` flag on `add`, `--execute` flag on `check`
- `flowtracker/store.py` — update `alerts` table schema for new columns

**Estimated effort:** 4-6 hours
**Estimated cost:** $0.40-4.00 per triggered research run (depends on scope)
**Risk:** Cost can add up if many alerts trigger full research. Use "quick" scope as default.

---

## Feature 6: Multi-timeframe Analysis

### Goal

"How has this stock's thesis changed over the last 3 quarters?" Current analysis is point-in-time. Add historical comparison using versioned briefings.

This answers: "Is this stock getting better or worse over time?"

### What Already Exists

This builds directly on Feature 1 (Historical Thesis Tracking). Requires versioned briefings to be implemented first.

### Gap

Even with versioned briefings, there's no agent that specifically analyzes the **trajectory** of metrics across multiple research runs.

### Rough Approach

**New agent or command that:**
1. Loads 2-4 historical briefings for the same stock
2. Computes deltas: "Revenue growth was 20% → 18% → 16% — decelerating"
3. Identifies trend reversals: "Insider buying started 2 quarters ago, MF accumulation started 1 quarter ago"
4. Produces a "Thesis Evolution" section

**Could be:**
- A new CLI command: `flowtrack research evolution -s INDIAMART --quarters 4`
- A new agent in the pipeline (8th specialist? Or a post-synthesis overlay?)
- Or simply additional context injected into the synthesis agent's prompt

**Simplest approach (no new agent):**
- In `run_synthesis_agent()`, load previous briefings if they exist
- Add a section to the synthesis prompt: "Here are the briefings from the previous run on {date}. Highlight what changed and whether the thesis is strengthening or weakening."
- This costs nothing extra and leverages the existing synthesis agent

**Files to modify:**
- `flowtracker/research/agent.py` — load previous briefings in synthesis
- `flowtracker/research/prompts.py` — add "Thesis Evolution" section to synthesis prompt
- `flowtracker/research/briefing.py` — `load_previous_briefings(symbol)` helper

**Prerequisite:** Feature 1 (Historical Thesis Tracking) — versioned briefing storage
**Estimated effort:** 2-4 hours (if Feature 1 is done)
**Estimated cost:** ~$0.05-0.10 extra per synthesis run (additional context tokens)

---

## Feature 7: Export to Notion/Google Sheets

### Goal

Push research output to the user's existing workflow tools. Stop manually copying data from terminal to notes.

This answers: "Can I get this data where I actually work?"

### What Already Exists

| Component | Status | Location |
|-----------|--------|----------|
| Research reports | Working | Markdown + HTML files in vault |
| Portfolio data | Working | Holdings, P&L in SQLite |
| Screening scores | Working | Composite scores for all stocks |
| Structured briefings | Working | JSON envelopes with metrics |

### Rough Approach

**Notion export:**
- Use Notion API (requires API key + database ID in config)
- Push research verdict + key metrics as a Notion database row
- One row per stock per research run: symbol, date, verdict, score, fair value, margin of safety
- Optionally push full report as a Notion page (rich text formatting)
- Config at: `~/.config/flowtracker/notion.env` (API key + database ID)

**Google Sheets export:**
- Use Google Sheets API (requires service account key)
- Push screening results as a spreadsheet: all 250 stocks with scores
- Push portfolio with live P&L
- Push research summary per stock
- Config at: `~/.config/flowtracker/gsheets.json` (service account key)

**New commands:**
```bash
# Export latest research to Notion
flowtrack export notion -s HDFCBANK

# Export screening to Google Sheets
flowtrack export sheets --type screening
flowtrack export sheets --type portfolio
flowtrack export sheets --type research -s HDFCBANK

# Bulk export
flowtrack export notion --all-research     # all stocks with briefings
flowtrack export sheets --type screening   # all 250 scores
```

**Files to create:**
```
flowtracker/export/
├── __init__.py
├── notion_client.py     ← Notion API wrapper
├── sheets_client.py     ← Google Sheets API wrapper
└── export_commands.py   ← CLI commands
```

**Dependencies:** `notion-client`, `gspread` (add to pyproject.toml)

**Estimated effort:** 6-8 hours
**Estimated cost:** $0 (free API tiers)
**Risk:** API key management, Google OAuth complexity. Notion API is simpler. Start with Notion.

---

## Implementation Priority Matrix

| Feature | Value | Effort | Dependencies | Priority |
|---------|-------|--------|--------------|----------|
| **Historical Thesis Tracking** | High — tracks conviction changes | 4-6h | None | Tier A — do first |
| **Portfolio Integration** | High — connects research to action | 6-8h | None | Tier A |
| **Automated Research Triggers** | High — "set and forget" workflow | 4-6h | None | Tier A |
| **News/Sentiment Monitoring** | High — daily pulse | 8-10h | None | Tier B |
| **Web Dashboard/UI** | Very High — user has asked repeatedly | 2-3 weeks | None | Tier B (but largest effort) |
| **Multi-timeframe Analysis** | Medium — trajectory insight | 2-4h | Feature 1 | Tier C |
| **Export to Notion/Sheets** | Medium — workflow integration | 6-8h | None | Tier C |

### Recommended Implementation Order

1. **Feature 1: Historical Thesis Tracking** — foundation for Features 5 and 6, quick to build
2. **Feature 2: Portfolio Integration** — immediate daily value, connects two existing systems
3. **Feature 5: Automated Research Triggers** — combined with Features 1+2, creates a complete workflow loop:
   - Alert fires → auto-research → verdict appears in portfolio view → thesis tracker updated
4. **Feature 3: News/Sentiment Monitoring** — daily utility, but independent module
5. **Feature 6: Multi-timeframe Analysis** — builds on Feature 1, small effort once briefings are versioned
6. **Feature 4: Web Dashboard** — biggest effort, save for dedicated sprint. Consider this a separate epic.
7. **Feature 7: Export** — nice-to-have, do when user actively asks for it

### Total Effort Estimate

| Tier | Features | Combined Effort |
|------|----------|----------------|
| Tier A | Historical Thesis + Portfolio + Auto-Triggers | ~14-20 hours (2-3 sessions) |
| Tier B | News/Sentiment + Web Dashboard | ~3-4 weeks |
| Tier C | Multi-timeframe + Export | ~8-12 hours (1-2 sessions) |
