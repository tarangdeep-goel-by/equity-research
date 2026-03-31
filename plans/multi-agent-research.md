# Multi-Agent Equity Research System

> Plan created: 2026-03-31
> Status: Ready for implementation
> Harness: Claude Agent SDK (`claude_agent_sdk>=0.1.50`)
> Project: `/Users/tarang/Documents/Projects/equity-research/flow-tracker/`
> Branch: `feat/multi-agent-research`

## Quick Reference

- **24 tasks** across 6 batches, dependency graph in "Task Breakdown" section
- **6 specialist agents** (Business, Financial, Ownership, Valuation, Risk, Technical) + 1 Synthesis + 6 Verifiers
- **42 MCP tools** (39 existing + 3 new peer benchmarking tools)
- **Key files to read first:** `research/agent.py`, `research/tools.py`, `research/prompts.py`, `research/data_api.py`
- **Critical path:** Prompt engineering (T8-T14) — start with Business prompt, iterate to quality
- **Worktree:** `git worktree add ../equity-research-multiagent -b feat/multi-agent-research main`
- **Test stocks:** INDIAMART (B2B platform), SBIN (bank), RELIANCE (conglomerate)
- **No backward compatibility** — direct replacement of old single-agent code

## Goal

Replace the current single-agent thesis generation (`agent.py` → 1 agent, 39 tools, 30 turns) with a **multi-phase, multi-agent system** where specialized agents run in parallel, each producing a standalone beginner-friendly report section. The orchestrator assembles them into a complete equity research report.

## Design Principles

1. **Every agent is independently runnable** — `flowtrack research run <agent-name> -s SYMBOL` runs one agent, saves one report section. No need to run the full pipeline during development or iteration.
2. **Zero prior knowledge assumed** — every report section must be readable by someone who has never looked at a stock before. All technical terms get inline definitions on first use. All charts get "How to read this" captions.
3. **Use every tool we built** — 39 MCP tools exist for a reason. Every tool must be assigned to at least one agent. If a tool isn't assigned, we justify why.
4. **Structured briefings, not summaries** — agents pass structured JSON envelopes (key metrics + confidence + findings) to the synthesis phase, not prose summaries.
5. **Cost control** — individual agents have `max_turns` and `max_budget_usd` caps. Running one agent costs ~$0.10-0.50, not ~$2-5 for the full pipeline.
6. **Everything is peer-benchmarked** — every metric pulled for the subject company is also pulled for its peers. No number exists in isolation. "ROCE is 22%" means nothing. "ROCE is 22% vs sector median 15% and peer range 8-28%" means everything. Sector aggregates (median, P25, P75) provide the benchmark frame.

---

## Architecture Overview

```
CLI: flowtrack research thesis -s INDIAMART
                    │
                    ▼
    ┌───────────────────────────────┐
    │  Phase 0: DATA REFRESH        │
    │  refresh_for_research(symbol) │
    │  + refresh_peers(symbol)      │
    │  ~75 API calls → SQLite       │
    └───────────────┬───────────────┘
                    │
                    ▼
    ┌───────────────────────────────────────────────────────┐
    │  Phase 1: SPECIALIST AGENTS (parallel)                 │
    │                                                        │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐                  │
    │  │Business │ │Financial│ │Ownership│                  │
    │  │  Agent  │ │  Agent  │ │  Agent  │                  │
    │  └────┬────┘ └────┬────┘ └────┬────┘                  │
    │       │           │           │                        │
    │  ┌────┴────┐ ┌────┴────┐ ┌────┴────┐                  │
    │  │Valuation│ │  Risk   │ │Technical│                  │
    │  │  Agent  │ │  Agent  │ │  Agent  │                  │
    │  └────┬────┘ └────┬────┘ └────┬────┘                  │
    │       │           │           │                        │
    │       ▼           ▼           ▼                        │
    │  [6 reports + 6 briefings + 6 evidence logs]          │
    └───────────────────┬───────────────────────────────────┘
                        │
                        ▼
    ┌───────────────────────────────────────────────────────┐
    │  Phase 1.5: VERIFICATION (parallel, per report)        │
    │                                                        │
    │  For each specialist report:                           │
    │  ┌──────────┐                                          │
    │  │ Verifier │ ← receives report + evidence log         │
    │  │  Agent   │ ← has read-only tool access to spot-check│
    │  └────┬─────┘                                          │
    │       │                                                │
    │       ▼                                                │
    │  {verified: bool, issues: [...], corrections: [...]}   │
    │                                                        │
    │  If issues found → specialist re-runs with corrections │
    │  If clean → report proceeds to synthesis               │
    └───────────────────┬───────────────────────────────────┘
                        │
                        ▼
    ┌───────────────────────────────────────────────────────┐
    │  Phase 2: SYNTHESIS AGENT                              │
    │  Reads 6 verified briefings → produces:                │
    │  - Executive Summary                                   │
    │  - Verdict (BUY/HOLD/SELL + confidence)                │
    │  - Key Signals (cross-referenced insights)             │
    │  - Catalysts & What to Watch                           │
    │  - The Big Question                                    │
    └───────────────────┬───────────────────────────────────┘
                        │
                        ▼
    ┌───────────────────────────────────────────────────────┐
    │  Phase 3: ASSEMBLY (code, not an agent)                │
    │  Concatenate verified specialist reports +             │
    │  synthesis sections → final HTML/Markdown              │
    │  Render mermaid diagrams, apply styling                │
    └───────────────────────────────────────────────────────┘
```

---

## Peer Benchmarking Architecture

### The Problem

Currently `get_peer_comparison` returns a single table from Screener with surface metrics (CMP, P/E, MCap, ROCE, quarterly sales/profit). This is one snapshot, one angle. But when an agent says "ROCE is 22%", the reader has no frame of reference. Is that good? For this industry? Compared to whom?

### The Solution: Two-Layer Benchmarking

**Layer 1: Peer-Level Data** — pull key metrics for the top 5 peers (by market cap from Screener's peer table). Not a full 50-API refresh per peer — a targeted light refresh via FMP + yfinance.

**Layer 2: Sector Aggregates** — compute median, P25, P75, min, max across all peers for each metric. This gives the "sector benchmark" without needing a separate sector database.

### What We Already Have

| Source | Data for Subject | Data for Peers | Gap |
|--------|-----------------|----------------|-----|
| **Screener peer table** | N/A | CMP, P/E, MCap, div yield, quarterly profit/sales + YoY var, ROCE | Surface only — no history, no margins, no growth rates |
| **FMP key_metrics** | 10yr: PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, debt/equity, margins | Not fetched for peers | **Gap — need to fetch for top 5 peers** |
| **FMP financial_growth** | 1yr/3yr/5yr CAGRs for revenue, EBITDA, NI, EPS, FCF | Not fetched for peers | **Gap — need to fetch for top 5 peers** |
| **yfinance valuation** | 50+ fields (price, PE, margins, beta, etc.) | Not fetched for peers | **Gap — need light fetch for top 5 peers** |
| **Screener ratios** | 10yr ROCE, debtor days, inventory, CCC | Not fetched for peers | Can't easily batch — skip for now |

### New: `refresh_peers(symbol)` Function

After `refresh_for_research(symbol)` runs, a new `refresh_peers(symbol)` step:

1. Read peer list from `peer_comparison` table (already populated by Screener)
2. Extract top 5 peers by market cap (skip if market cap is <10% of subject — too small to be meaningful)
3. For each peer, fetch:
   - **FMP key_metrics** (latest year only, not 10yr) — PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, debt/equity, margins → `fmp_key_metrics` table
   - **FMP financial_growth** (latest year only) — revenue/EBITDA/NI growth rates + 3yr/5yr CAGRs → `fmp_financial_growth` table
   - **yfinance valuation snapshot** — live price, PE, margins, beta, market cap → `valuation_snapshot` table
   - **FMP DCF** (latest only) — intrinsic value for relative comparison → `fmp_dcf_values` table
4. Compute sector aggregates and store in a new `sector_benchmarks` table

**API cost:** ~25 FMP calls (5 peers × 4 endpoints) + 5 yfinance calls. With 0.5s rate limit between FMP calls = ~15 seconds additional. Manageable.

**Rate limit note:** FMP free tier = 250 req/day. Full refresh for subject (6 FMP calls) + peers (20 calls) = 26 FMP calls per stock. Can do ~9 stocks/day on free tier. Paid tier has no practical limit.

### New Table: `sector_benchmarks`

```sql
CREATE TABLE IF NOT EXISTS sector_benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_symbol TEXT NOT NULL,
    metric TEXT NOT NULL,          -- 'pe', 'pb', 'ev_ebitda', 'roe', 'roce', 'roic', etc.
    subject_value REAL,
    peer_count INTEGER,
    sector_median REAL,
    sector_p25 REAL,
    sector_p75 REAL,
    sector_min REAL,
    sector_max REAL,
    percentile REAL,              -- subject's percentile rank within sector
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_symbol, metric)
);
```

### New Tools Required (3 new tools)

| Tool | Description | Used By |
|------|-------------|---------|
| `get_peer_metrics` | Get FMP key metrics (PE, PB, ROE, margins, etc.) for subject + all peers in one call. Returns `{subject: {...}, peers: [{symbol, ...}, ...]}` | Financial, Valuation |
| `get_peer_growth` | Get FMP growth rates (revenue, EBITDA, NI CAGRs) for subject + all peers. Same structure. | Financial |
| `get_sector_benchmarks` | Get computed sector aggregates for a metric (median, P25/P75, percentile). Returns `{metric, subject_value, sector_median, percentile, ...}` | All agents |

### How Agents Use Peer Data

Every agent that presents a metric MUST also present the sector context. The prompt rules enforce this:

**Before (current):**
> "ROCE is 22%, up from 14% five years ago."

**After (with peer benchmarking):**
> "ROCE is 22%, up from 14% five years ago. To put this in context: the sector median ROCE is 15%, with peers ranging from 8% (TradeIndia) to 28% (Info Edge). {COMPANY} sits at the **78th percentile** — better than most competitors and improving.
>
> | Company | ROCE | vs Sector Median |
> |---------|------|-----------------|
> | {COMPANY} | 22% | +7pp above |
> | Info Edge | 28% | +13pp above |
> | JustDial | 12% | -3pp below |
> | Sector Median | 15% | — |"

### Sector Benchmarks vs Peer Comparison

| | Peer Comparison (existing) | Sector Benchmarks (new) |
|--|---------------------------|------------------------|
| **Data** | Screener surface table | FMP deep metrics + computed aggregates |
| **Depth** | CMP, PE, MCap, ROCE, qtr sales/profit | PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, margins, growth CAGRs, DCF |
| **Frame** | Raw peer numbers | Statistical frame: median, P25/P75, percentile rank |
| **Use** | "Who are the peers" | "Where does this company rank among peers on every dimension" |

---

## Phase 0: Data Refresh (Modified)

`refresh_for_research(symbol)` fetches from all 6 sources and populates SQLite. **NEW:** followed by `refresh_peers(symbol)` which fetches FMP key metrics + growth + DCF + yfinance snapshot for top 5 peers and computes sector benchmarks.

**Sources refreshed (subject):**
1. Screener.in (company page, charts, peers, shareholders, schedules, documents)
2. yfinance (valuation snapshot, consensus estimates, earnings surprises)
3. NSE (insider transactions, bhavcopy delivery, bulk/block deals)
4. Macro (VIX, USD/INR, Brent, 10Y yield)
5. BSE (corporate filings)
6. FMP (DCF, technicals, key metrics, growth, analyst grades, price targets)

**Sources refreshed (peers — NEW):**
7. FMP key_metrics for top 5 peers (latest year)
8. FMP financial_growth for top 5 peers (latest year)
9. FMP DCF for top 5 peers (latest value)
10. yfinance valuation snapshot for top 5 peers

**Computed (NEW):**
11. Sector benchmarks (median, P25/P75, percentile) for ~15 key metrics

---

## Phase 1: Specialist Agents

### Agent 1: Business Understanding

**Purpose:** Explain what the company does, how it makes money, competitive position, and industry context. A reader with zero financial knowledge should understand the business after reading this.

**CLI:** `flowtrack research run business -s SYMBOL`

**Tools (13):**

| Tool | Why |
|------|-----|
| `get_company_info` | Company name, industry — the starting point |
| `get_company_profile` | Screener's about text and key business points |
| `get_company_documents` | Concall transcripts, investor presentations — primary research sources |
| `get_business_profile` | Check vault for cached profile before doing web research |
| `save_business_profile` | Persist new/updated profile for future runs |
| `get_quarterly_results` | Recent revenue/profit trajectory to show business momentum |
| `get_annual_financials` | 10yr revenue/profit to show long-term growth story |
| `get_screener_ratios` | ROCE, working capital efficiency — business quality indicators |
| `get_valuation_snapshot` | Current market cap, margins — gives scale context |
| `get_peer_comparison` | Who are the competitors, how does this company compare |
| `get_expense_breakdown` | Cost structure — where does the money go |
| `get_consensus_estimate` | What do professional analysts think |
| `get_earnings_surprises` | Does management deliver on promises |

**Max turns:** 25 | **Max budget:** $0.50

**Report sections produced:**
- **The Business: How It Actually Works** — walk through an actual transaction from the customer's perspective. Include mermaid flowchart showing value/money flow.
- **The Money Machine: What Drives Revenue** — identify all revenue levers, put numbers on each. Include mermaid pie chart of revenue mix. Include markdown table of 5-10yr revenue/profit trajectory. Include how all revenue layers are trending and how the mix has been changing over time.
- **The Financial Fingerprint** — margin story, capital efficiency (ROCE trend), balance sheet health, analyst view, earnings track record. Charts with "How to read this" captions.
- **How It Compares: Peer Benchmarking** — peer table with narrative explaining why differences matter.
- **Why This Business Wins (or Loses)** — moat as thought experiment, all the relevant threats that matters.
- **The Investor's Checklist** — all relevant specific metrics with green/red flag thresholds.

**Inline explanation requirements:**
- First mention of "ROCE" → "ROCE (Return on Capital Employed) measures how much profit a company earns for every rupee of capital it uses. Think of it like the interest rate on a savings account — higher is better. A ROCE of 25% means for every ₹100 invested in the business, it generates ₹25 of profit."
- First mention of "operating margin" → explain with example from this company's numbers
- Revenue/profit charts must have captions: "This chart shows... A rising line means... Look for..."
- If and wherever possible compare the numbers with peers and benchmark - easier to understand how the number is today compared to benchmark

**Structured briefing output (JSON):**
```json
{
  "agent": "business",
  "symbol": "INDIAMART",
  "confidence": 0.85,
  "business_model": "B2B marketplace connecting buyers and suppliers",
  "revenue_drivers": ["paying_subscribers", "arpu", "advertising"],
  "moat_strength": "strong",
  "moat_type": "network_effects",
  "key_risks": "Revenue growth decelerating (31% → 21% → 16%)",
  "management_quality": "good — beat estimates 6/8 quarters",
  "industry_growth": "Indian B2B e-commerce growing ~25% CAGR",
  "key_metrics": {
    "revenue_cr": 1390, "roce_pct": 22, "opm_pct": 32,
    "market_cap_cr": 18500, "debt_equity": 0
  }
}
```

---

### Agent 2: Financial Analysis

**Purpose:** Deep-dive into the numbers — earnings trajectory, margin analysis, growth rates, quality of earnings, cash flow analysis. Explain every ratio and what it means for this specific company.

**CLI:** `flowtrack research run financials -s SYMBOL`

**Tools (12):**

| Tool | Why |
|------|-----|
| `get_quarterly_results` | 12 quarters — recent momentum, seasonality, acceleration/deceleration |
| `get_annual_financials` | 10yr P&L + Balance Sheet + Cash Flow — long-term trajectory |
| `get_screener_ratios` | Efficiency ratios: debtor days, inventory days, CCC, ROCE — quality signals |
| `get_expense_breakdown` | Cost structure deep-dive — what's driving margin changes |
| `get_financial_growth_rates` | Pre-computed 1yr/3yr/5yr/10yr CAGRs — growth consistency |
| `get_dupont_decomposition` | ROE = margin × turnover × leverage — what's driving returns |
| `get_key_metrics_history` | 10yr per-share metrics: EPS, book value, FCF/share — per-share value creation |
| `get_chart_data` (pe) | Historical P/E time series — valuation context |
| `get_chart_data` (price) | Price history — shows market narrative |
| `get_chart_data` (sales_margin) | Margin trend visualization |
| `get_earnings_surprises` | Beat/miss track record — earnings quality signal |
| `get_company_info` | Company name and industry for context |

**Max turns:** 20 | **Max budget:** $0.40

**Report sections produced:**
- **Earnings & Growth** — quarterly trend table (12Q) with YoY growth calculated. Annual trend table (10yr). Highlight inflection points: "Revenue doubled between FY20-FY24, but growth slowed to 8% in FY25. Why?" Include chart with caption explaining what to look for. Annotate import points over time along side with the graphs and talk about why they are important and how they can be interpreted. What does it mean for the business and how does it compare with the peers. If and wherever possible compare the numbers with peers and benchmark - easier to understand how the number is today compared to benchmark
- **Margin Analysis** — OPM, NPM trajectory. Operating leverage explanation with this company's numbers. Expense breakdown table showing where each rupee goes. If and wherever possible compare the numbers with peers and benchmark - easier to understand how the number is today compared to benchmark
- **Business Quality (DuPont)** — ROE decomposition with 10yr trend. Explain: "If ROE is rising because of leverage (more debt), that's risky. If it's rising because of better margins, that's healthy. Here's what's happening with {COMPANY}...". If and wherever possible compare the numbers with peers and benchmark - easier to understand how the number is today compared to benchmark
- **Cash Flow Story** — FCF generation, cash conversion, capex intensity. "A company can show profit on paper but have no actual cash. Here's how to check..." If and wherever possible compare the numbers with peers and benchmark - easier to understand how the number is today compared to benchmark
- **Growth Trajectory** — 1yr/3yr/5yr/10yr CAGRs for revenue, EBITDA, net income, EPS, FCF. Table + interpretation. "Consistent 15%+ revenue CAGR over 5 and 10 years = compounding machine. But if 1yr growth is 8% while 5yr is 20%, growth is decelerating." If and wherever possible compare the numbers with peers and benchmark - easier to understand how the number is today compared to benchmark

**Inline explanation requirements:**
- "CAGR (Compound Annual Growth Rate)" → "Think of it as the steady annual growth rate that would get you from point A to point B. If revenue went from ₹100Cr to ₹200Cr in 5 years, the CAGR is ~15% — meaning it grew at a steady 15% each year."
- "DuPont decomposition" → "A way to break down ROE (how much profit the company earns on shareholders' money) into three parts: how much profit it keeps per rupee of sales (margin), how efficiently it uses its assets (turnover), and how much debt it uses (leverage)."
- Every chart: "What this chart shows" + "How to read it" + "What to look for in {COMPANY}'s chart" and how does it compare with the peers. 

**Structured briefing output (JSON):**
```json
{
  "agent": "financials",
  "symbol": "INDIAMART",
  "confidence": 0.90,
  "revenue_cagr_5yr": 18.5,
  "ebitda_cagr_5yr": 22.1,
  "opm_current": 32,
  "opm_trend": "expanding",
  "roce_current": 22,
  "roce_trend": "improving",
  "dupont_driver": "margin_improvement",
  "fcf_positive": true,
  "debt_equity": 0,
  "earnings_beat_ratio": "6/8",
  "growth_trajectory": "decelerating",
  "quality_signal": "high — zero debt, strong FCF, rising ROCE"
}
```

---

### Agent 3: Ownership Intelligence

**Purpose:** Who owns this stock, who's buying, who's selling, and what does the money flow tell us. Explain institutional behavior and what it signals.

**CLI:** `flowtrack research run ownership -s SYMBOL`

**Tools (11):**

| Tool | Why |
|------|-----|
| `get_shareholding` | 12 quarters of FII/DII/MF/Promoter/Public % — ownership structure trend |
| `get_shareholding_changes` | Latest QoQ changes — who's accumulating/exiting RIGHT NOW |
| `get_insider_transactions` | SAST insider buy/sell — management skin in the game |
| `get_bulk_block_deals` | Large institutional block trades — big money moves |
| `get_mf_holdings` | Which MF schemes hold this stock — conviction breadth |
| `get_mf_holding_changes` | Latest month MF additions/reductions — smart money direction |
| `get_shareholder_detail` | Named shareholders (LIC, Vanguard, etc.) — institutional quality |
| `get_promoter_pledge` | Promoter pledge % — risk signal (pledging shares as collateral) |
| `get_delivery_trend` | Daily delivery % — accumulation vs speculation signal |
| `get_fii_dii_flows` | Market-wide FII/DII flows — macro context for stock-level ownership |
| `get_fii_dii_streak` | Consecutive buy/sell days — institutional momentum |

**Max turns:** 18 | **Max budget:** $0.35

**Report sections produced:**
- **Who Owns This Stock** — ownership structure pie chart with explanation. "Promoters are the founders/family — high promoter holding (>50%) often means aligned interests. FII (Foreign Institutional Investors) are global funds like BlackRock..."
- **The Money Flow Story** — 12-quarter ownership trend table. Highlight shifts: "FII holding dropped from 18% to 12% over 4 quarters, while MF holding rose from 8% to 14%. This is called an 'institutional handoff' — often bullish for medium-term because domestic MFs tend to be longer-term holders."
- **Insider Signals** — insider transaction table with interpretation. "When the CEO buys ₹5Cr of stock with their own money while the price is falling, that's called 'insider buying at weakness' — one of the strongest conviction signals."
- **Mutual Fund Conviction** — scheme-level holdings table. "If 15 different MF schemes across 8 fund houses hold this stock, that's broad conviction — many independent analysts reached the same buy conclusion."
- **Risk Signals: Pledge & Delivery** — promoter pledge trend + delivery % analysis. "If a promoter has pledged 20% of their shares, they've used those shares as collateral for a loan. If the stock price falls, the lender can sell those shares, creating a downward spiral."

**Inline explanation requirements:**
- "FII" → "Foreign Institutional Investors — global funds like BlackRock, Vanguard, and sovereign wealth funds that invest in Indian markets."
- "DII" → "Domestic Institutional Investors — Indian insurance companies (LIC), pension funds, and mutual funds."
- "Delivery %" → "When shares are traded on the stock exchange, some trades are 'speculative' (buy and sell same day) and some are 'delivery' (buyer actually takes ownership). A high delivery % (>50%) suggests real buying interest, not just day-traders."
- Ownership charts: "This chart shows... The colored bars represent... A rising blue bar means..."

**Structured briefing output (JSON):**
```json
{
  "agent": "ownership",
  "symbol": "INDIAMART",
  "confidence": 0.85,
  "promoter_pct": 54.2,
  "promoter_trend": "stable",
  "fii_pct": 14.5,
  "fii_trend": "decreasing",
  "mf_pct": 12.3,
  "mf_trend": "increasing",
  "institutional_handoff": true,
  "insider_signal": "net_buying",
  "insider_value_cr": 5.2,
  "pledge_pct": 0,
  "delivery_signal": "accumulation",
  "mf_scheme_count": 15,
  "mf_amc_count": 8,
  "key_insight": "FII→MF handoff in progress, insider buying at weakness"
}
```

---

### Agent 4: Valuation

**Purpose:** Is this stock cheap or expensive? What is it worth? Combine multiple valuation methods and explain each one. Make a beginner understand how to value a stock.

**CLI:** `flowtrack research run valuation -s SYMBOL`

**Tools (11):**

| Tool | Why |
|------|-----|
| `get_valuation_snapshot` | Current price + 50 valuation fields — the baseline |
| `get_valuation_band` | Historical P/E percentile — where current valuation sits vs history |
| `get_pe_history` | 7yr daily P/E + price — valuation trend visualization |
| `get_fair_value` | Combined PE band + DCF + consensus → bear/base/bull range |
| `get_dcf_valuation` | DCF intrinsic value + margin of safety |
| `get_dcf_history` | How DCF fair value changed over 10 years |
| `get_price_targets` | Individual analyst targets — dispersion shows uncertainty |
| `get_analyst_grades` | Upgrade/downgrade history — sell-side sentiment momentum |
| `get_peer_comparison` | Peer valuations — relative cheapness/expensiveness |
| `get_chart_data` (ev_ebitda) | EV/EBITDA trend — enterprise valuation metric |
| `get_chart_data` (pbv) | P/BV trend — asset-based valuation metric |

**Max turns:** 18 | **Max budget:** $0.35

**Report sections produced:**
- **Is It Cheap or Expensive?** — current P/E, P/B, EV/EBITDA with historical percentile band. "The P/E ratio tells you how many years of current earnings you'd need to 'pay back' the stock price. {COMPANY} trades at 35x earnings. Historically it has traded between 25x and 55x, so at 35x it's in the **lower third** of its range."
- **Three Ways to Value This Stock** — explain and calculate each:
  - **PE Band Method** — "What the market has historically been willing to pay"
  - **DCF Method** — "What the business is mathematically worth based on future cash flows"
  - **Analyst Consensus** — "What professional analysts covering this stock think it's worth"
  - Summary table: bear/base/bull for each method → combined fair value range
- **The Margin of Safety** — "If you think something is worth ₹2,000, would you pay ₹1,900? Probably not — what if you're wrong? A 'margin of safety' means buying well below fair value. Current price is ₹1,500 vs fair value of ₹2,000 = 25% margin of safety."
- **Analyst Views** — individual analyst targets table + grade history. "12 analysts cover this stock. The average target is ₹2,400 but the range is ₹1,800 to ₹3,000 — wide dispersion means high uncertainty."
- **Peer Valuation** — peer table with valuation multiples. "HDFC Bank trades at 2.5x book value while SBI trades at 1.5x. The gap exists because HDFC earns higher ROA (1.9% vs 1.2%). You're paying more per rupee of assets, but those assets earn more."

**Inline explanation requirements:**
- "P/E ratio" → full explanation with analogy (years of earnings to pay back price)
- "DCF" → "Discounted Cash Flow — a method that estimates the total cash a business will generate in the future, then adjusts it to today's value. The idea: ₹100 next year is worth less than ₹100 today because you could invest today's ₹100 and earn interest."
- "EV/EBITDA" → explain Enterprise Value and EBITDA separately, then the ratio
- "Margin of safety" → explain with buying-a-house analogy
- P/E band chart: "This chart shows... The blue line is the stock price. The colored bands show what P/E multiple the market was assigning. When the price is near the bottom band, the stock is historically cheap."

**Structured briefing output (JSON):**
```json
{
  "agent": "valuation",
  "symbol": "INDIAMART",
  "confidence": 0.80,
  "current_pe": 35.2,
  "pe_percentile": 28,
  "pe_band_fair_value": 2100,
  "dcf_fair_value": 1950,
  "consensus_target": 2400,
  "combined_fair_value_base": 2050,
  "combined_fair_value_bear": 1600,
  "combined_fair_value_bull": 2800,
  "margin_of_safety_pct": 25,
  "signal": "UNDERVALUED",
  "analyst_count": 12,
  "analyst_dispersion": "wide",
  "vs_peers": "discount_to_sector"
}
```

---

### Agent 5: Risk Assessment

**Purpose:** What could go wrong? Identify, quantify, and rank risks. Explain each risk type and how it specifically affects this company.

**CLI:** `flowtrack research run risk -s SYMBOL`

**Tools (11):**

| Tool | Why |
|------|-----|
| `get_quarterly_results` | Revenue/profit volatility — operational risk |
| `get_annual_financials` | Debt levels, interest coverage — financial risk |
| `get_promoter_pledge` | Pledge trend — corporate governance risk |
| `get_insider_transactions` | Insider selling patterns — management confidence risk |
| `get_macro_snapshot` | VIX, crude, rates, currency — macro risk context |
| `get_fii_dii_streak` | Institutional flow direction — market-wide risk appetite |
| `get_composite_score` | 8-factor score — quantified risk summary |
| `get_earnings_surprises` | Miss frequency — execution risk |
| `get_recent_filings` | Corporate filings — regulatory/legal risk |
| `get_valuation_snapshot` | Beta, short interest — market risk metrics |
| `get_peer_comparison` | Peer risk comparison — relative positioning |

**Max turns:** 15 | **Max budget:** $0.30

**Report sections produced:**
- **Risk Dashboard** — composite score factors table with red/yellow/green signals. "This dashboard summarizes 8 risk/quality factors. Each is scored 0-100. Here's what each means and where {COMPANY} stands..."
- **Financial Risks** — debt levels, interest coverage, cash position. "A debt-to-equity ratio of 1.5x means for every ₹100 of shareholder money, there's ₹150 of debt. If the business hits a rough patch, interest payments don't stop."
- **Governance Risks** — promoter pledge, insider selling patterns, related-party transactions (from filings). "Promoter pledge is like using your house as collateral for a business loan. If the stock drops enough, the lender can sell — creating forced selling pressure."
- **Market & Macro Risks** — beta, VIX, rate sensitivity, FII flow dependency. "Beta measures how much a stock moves vs the market. A beta of 1.3 means when Nifty falls 10%, this stock typically falls 13%."
- **Operational Risks** — revenue concentration, growth deceleration, margin pressure. Ranked by severity with specific numbers.
- **Bear Case Scenario** — "What would have to go wrong for this stock to fall 30-50%? Here are the specific triggers..."

**Inline explanation requirements:**
- "Beta" → explain with market movement example using this stock's actual beta
- "VIX" → "The Volatility Index — often called the 'fear gauge'. When VIX is high (>20), markets are nervous. When low (<13), markets are calm."
- "Composite score" → explain each of the 8 factors and what the score means
- Risk severity: use traffic light system (red/yellow/green) with numbers

**Structured briefing output (JSON):**
```json
{
  "agent": "risk",
  "symbol": "INDIAMART",
  "confidence": 0.85,
  "composite_score": 72,
  "top_risks": [
    {"risk": "growth_deceleration", "severity": "high", "detail": "Revenue growth: 31% → 21% → 16% over FY23-25"},
    {"risk": "customer_concentration", "severity": "medium", "detail": "Top 10% customers = 75% revenue"},
    {"risk": "fii_outflow", "severity": "medium", "detail": "FII holding down 3.5% over 4 quarters"}
  ],
  "financial_health": "fortress — zero debt, ₹2,874Cr cash",
  "governance_signal": "clean — no pledge, insider buying",
  "bear_case_trigger": "Paying subscriber net adds drop below 3K/quarter for 2 consecutive quarters",
  "macro_sensitivity": "low — domestic B2B platform, minimal export/crude/rate exposure"
}
```

---

### Agent 6: Technical & Market Context

**Purpose:** Price action, technical indicators, and market positioning. Explain what each indicator means, how to read it, and what it's saying about this stock right now.

**CLI:** `flowtrack research run technical -s SYMBOL`

**Tools (8):**

| Tool | Why |
|------|-----|
| `get_technical_indicators` | RSI, SMA-50, SMA-200, MACD, ADX — current readings |
| `get_chart_data` (price) | Price history — visual context for technical analysis |
| `get_chart_data` (mcap_sales) | Market cap to sales ratio trend |
| `get_delivery_trend` | Delivery % — real buying vs speculation |
| `get_valuation_snapshot` | Current price, 52-week high/low, volume |
| `get_bulk_block_deals` | Large block trades — big money positioning |
| `get_fii_dii_flows` | Market-wide flow context |
| `get_fii_dii_streak` | Institutional buying/selling streak |

**Max turns:** 12 | **Max budget:** $0.25

**Report sections produced:**
- **Price Action** — 52-week range, where current price sits, recent trend. Price chart with "How to read a price chart" caption.
- **Technical Indicators Explained** — for each indicator:
  - **RSI** → "The Relative Strength Index measures whether a stock has been bought too aggressively (overbought, >70) or sold too aggressively (oversold, <30). It ranges from 0 to 100. {COMPANY}'s RSI is currently 45, which is neutral — neither overbought nor oversold."
  - **SMA-50 & SMA-200** → "Moving averages smooth out daily noise to show the trend. The 50-day average shows short-term trend, 200-day shows long-term. When price is above both = bullish. When the 50-day crosses above the 200-day = 'golden cross' (bullish signal). {COMPANY}: price is at ₹X, SMA-50 is ₹Y, SMA-200 is ₹Z."
  - **MACD** → explain with histogram visual interpretation
  - **ADX** → "Measures trend strength (not direction). Above 25 = strong trend. Below 20 = no clear trend."
- **Accumulation Signals** — delivery % trend + block deals. "In the last 7 days, delivery % averaged 62% (above the 45% market average), suggesting institutional accumulation."
- **Entry Timing Context** — "Technical analysis is NOT about predicting the future. It's about understanding the current mood of the market and choosing a better entry point."

**Structured briefing output (JSON):**
```json
{
  "agent": "technical",
  "symbol": "INDIAMART",
  "confidence": 0.70,
  "rsi": 45,
  "rsi_signal": "neutral",
  "price_vs_sma50": "above",
  "price_vs_sma200": "above",
  "macd_signal": "bullish_crossover",
  "adx": 28,
  "trend_strength": "moderate",
  "delivery_avg_7d": 62,
  "accumulation_signal": true,
  "timing_suggestion": "Technically neutral with accumulation signals — no urgency to enter, no reason to avoid"
}
```

---

## Phase 1.5: Verification Agents

### Why Verification Matters

A single LLM agent writing AND self-checking is like a student grading their own exam. The generator has confirmation bias toward its own output. An independent verifier catches:
- **Data errors** — report says "revenue grew 23% YoY" but the data shows 18%
- **Calculation errors** — "CAGR of 15% over 5 years" but the math gives 12%
- **Interpretation errors** — "margins are expanding" when they went from 32% to 31%
- **Unsupported claims** — "strong competitive moat" with no data backing it
- **Missing context** — stated a number without peer benchmarking
- **Stale data** — used a cached profile that's >90 days old for a current claim

### Architecture: Evidence Log + Independent Verification

#### Step 1: Specialist Agents Output Evidence

Each specialist agent's structured output expands to include an **evidence log** — every tool call and its result:

```python
# Specialist agent returns:
{
    "report": "... full markdown report section ...",
    "briefing": { ... structured JSON briefing ... },
    "evidence": [
        {
            "tool": "get_quarterly_results",
            "args": {"symbol": "INDIAMART", "quarters": 12},
            "result_summary": "12 quarters returned. Revenue range: ₹310Cr (Q1FY23) to ₹412Cr (Q3FY26). Latest QoQ growth: 5.2%.",
            "result_hash": "sha256:abc123..."  # hash of full result for integrity
        },
        {
            "tool": "get_sector_benchmarks",
            "args": {"symbol": "INDIAMART", "metric": "roce"},
            "result_summary": "Subject ROCE: 22%, sector median: 15%, percentile: 78",
            "result_hash": "sha256:def456..."
        },
        ...
    ]
}
```

**Why `result_summary` instead of full results?** Full tool results can be thousands of tokens (10yr financials, 12 quarters, etc.). The verifier gets summaries for context but can re-fetch specific data points to spot-check. The `result_hash` lets us verify the summary matches the actual data.

**Implementation:** The specialist agent's system prompt includes: "After completing your analysis, list every tool call you made, the key data points you extracted, and which claims in your report each data point supports. This evidence log will be independently verified."

#### Step 2: Verification Agent Checks

For each specialist report, a verification agent receives:
1. The full report (markdown)
2. The evidence log (tool calls + result summaries)
3. **Read-only access to the same tools** — can independently re-fetch any data point

The verifier does NOT rewrite the report. It produces a structured verification result.

**CLI:** `flowtrack research verify <agent> -s SYMBOL` (can also run independently)

**Verification agent tools:** Same tool subset as the specialist it's verifying, but **read-only** (no `save_business_profile`, no write operations).

**Max turns:** 10 | **Max budget:** $0.20

**Model:** Use a **different model** than the specialist to reduce correlated errors. If specialist uses Opus, verifier uses Sonnet (or vice versa). Configurable via `--verify-model`.

#### What the Verifier Checks

| Check | How | Example |
|-------|-----|---------|
| **Numerical accuracy** | Re-fetch 3-5 key data points from tools, compare to report claims | Report says "Revenue ₹412Cr in Q3FY26" → call `get_quarterly_results` → verify exact number |
| **Calculation accuracy** | Recompute growth rates, CAGRs, margins from raw data | Report says "5yr revenue CAGR of 18%" → verify: (latest/earliest)^(1/5) - 1 |
| **Interpretation validity** | Check if conclusions follow from data | Report says "margins expanding" → verify the actual margin trajectory shows expansion, not a single-quarter blip |
| **Peer benchmark accuracy** | Re-fetch sector benchmarks, verify rankings | Report says "78th percentile ROCE" → call `get_sector_benchmarks` → verify |
| **Completeness** | Check that every major claim has a cited data source in the evidence log | Scan report for numerical claims, verify each appears in evidence |
| **Consistency** | Check that numbers cited in different sections agree | Revenue in "Business Overview" matches revenue in "Earnings & Growth" |
| **Freshness** | Check data dates in evidence log | Flag if tool results are >7 days old for live data (valuation, technicals) |

#### Verification Output

```json
{
    "agent_verified": "financials",
    "symbol": "INDIAMART",
    "verdict": "pass_with_notes",  // "pass" | "pass_with_notes" | "fail"
    "spot_checks_performed": 5,
    "issues": [
        {
            "severity": "error",       // "error" | "warning" | "note"
            "section": "Earnings & Growth",
            "claim": "Revenue grew 23% YoY in Q3FY26",
            "actual": "Revenue grew 19.8% YoY (₹412Cr vs ₹344Cr)",
            "data_source": "get_quarterly_results",
            "action": "correct_number"
        },
        {
            "severity": "warning",
            "section": "Business Quality",
            "claim": "ROCE at 78th percentile",
            "actual": "ROCE at 74th percentile (rounding difference)",
            "data_source": "get_sector_benchmarks",
            "action": "minor_correction"
        },
        {
            "severity": "note",
            "section": "Margin Analysis",
            "claim": "Operating leverage driving margin expansion",
            "actual": "Interpretation is reasonable — revenue grew 20% while employee costs grew 12%, confirming operating leverage thesis",
            "data_source": "get_expense_breakdown",
            "action": "none — interpretation is sound"
        }
    ],
    "corrections": [
        "Change '23% YoY' to '19.8% YoY (₹412Cr vs ₹344Cr)' in Earnings & Growth section",
        "Change '78th percentile' to '74th percentile' in Business Quality section"
    ],
    "overall_data_quality": "high — 4/5 spot checks passed exactly, 1 had a rounding error"
}
```

#### Step 3: Correction Flow

**On `pass`:** Report proceeds to synthesis as-is.

**On `pass_with_notes`:** Corrections are applied automatically via string replacement (code, not agent). Minor numerical corrections don't need a full re-run.

**On `fail`:** The specialist agent re-runs with the corrections injected into its prompt:

```python
# Re-run prompt includes:
f"""Your previous report for {symbol} was flagged by the verification agent.
Issues found:
{json.dumps(verification_result['issues'], indent=2)}

Required corrections:
{json.dumps(verification_result['corrections'], indent=2)}

Generate a corrected report. Pay special attention to the flagged sections.
Only the second run's output is used — the first is discarded."""
```

**Max re-runs:** 1. If verification fails twice, the report is flagged for human review but still included in the assembly with a warning banner.

### Verification in Individual vs Full Pipeline Mode

| Mode | Behavior |
|------|----------|
| `flowtrack research run business -s X` | Runs business agent only. **No auto-verification.** |
| `flowtrack research run business -s X --verify` | Runs business agent + verification. Corrections applied if needed. |
| `flowtrack research verify business -s X` | Runs verifier on an existing report (must exist in vault). |
| `flowtrack research thesis -s X` | Full pipeline: all specialists → all verifiers (parallel) → synthesis → assembly. Verification is automatic. |
| `flowtrack research thesis -s X --skip-verify` | Full pipeline without verification (for cost/speed). |

### Cost Impact

| | Without Verification | With Verification |
|--|---------------------|-------------------|
| **Per agent** | $0.15-0.50 | +$0.10-0.20 per verifier |
| **Full pipeline** | ~$1.50-2.50 | ~$2.00-3.50 |
| **Re-run (on fail)** | N/A | +$0.15-0.50 for the failed agent |

Verification adds ~30-40% cost but catches errors that would undermine trust in the entire report. For a research tool that informs investment decisions, this is non-negotiable.

### Parallelism

Verification agents run **in parallel** — one per specialist. They don't depend on each other:

```python
# Phase 1: Specialists (parallel)
specialist_results = await asyncio.gather(
    _run_specialist("business", ...),
    _run_specialist("financials", ...),
    _run_specialist("ownership", ...),
    _run_specialist("valuation", ...),
    _run_specialist("risk", ...),
    _run_specialist("technical", ...),
)

# Phase 1.5: Verification (parallel, one per specialist)
verification_results = await asyncio.gather(
    _run_verifier("business", specialist_results["business"], ...),
    _run_verifier("financials", specialist_results["financials"], ...),
    _run_verifier("ownership", specialist_results["ownership"], ...),
    _run_verifier("valuation", specialist_results["valuation"], ...),
    _run_verifier("risk", specialist_results["risk"], ...),
    _run_verifier("technical", specialist_results["technical"], ...),
)

# Apply corrections, re-run failures if needed
verified_results = await _apply_corrections(specialist_results, verification_results)

# Phase 2: Synthesis (uses verified results)
synthesis = await _run_synthesis(verified_results)
```

Wall-clock time impact: minimal. Verification agents run in parallel and are fast (~10 turns, lightweight). The only delay is if a specialist needs to re-run (adds one sequential re-run for that agent).

---

## Tool Assignment Audit

Every tool must be used. Here's the complete mapping (39 existing + 3 new peer tools = 42 total):

### Existing Tools (39)

| Tool | Agent(s) | Justification |
|------|----------|---------------|
| `get_company_info` | Business, Financial | Company name, industry context |
| `get_company_profile` | Business | Screener about text — business description |
| `get_company_documents` | Business | Concall/AR URLs for qualitative research |
| `get_business_profile` | Business | Check vault cache before web research |
| `save_business_profile` | Business | Persist for future runs |
| `get_quarterly_results` | Business, Financial, Risk | Recent momentum (3 different angles) |
| `get_annual_financials` | Business, Financial, Risk | Long-term trajectory |
| `get_screener_ratios` | Business, Financial | ROCE, efficiency, working capital |
| `get_valuation_snapshot` | Business, Valuation, Risk, Technical | Current multiples, margins, beta |
| `get_valuation_band` | Valuation | Historical percentile — where valuation sits |
| `get_pe_history` | Valuation | P/E trend visualization |
| `get_fair_value` | Valuation | Combined fair value model |
| `get_dcf_valuation` | Valuation | DCF intrinsic value |
| `get_dcf_history` | Valuation | DCF trajectory over time |
| `get_price_targets` | Valuation | Individual analyst targets |
| `get_analyst_grades` | Valuation | Upgrade/downgrade momentum |
| `get_peer_comparison` | Business, Valuation, Risk | Screener surface table — who are the peers |
| `get_expense_breakdown` | Business, Financial | Cost structure analysis |
| `get_shareholding` | Ownership | 12Q ownership structure trend |
| `get_shareholding_changes` | Ownership | Latest QoQ changes |
| `get_insider_transactions` | Ownership, Risk | Insider buying/selling |
| `get_bulk_block_deals` | Ownership, Technical | Large institutional trades |
| `get_mf_holdings` | Ownership | MF scheme-level conviction |
| `get_mf_holding_changes` | Ownership | Latest MF additions/reductions |
| `get_shareholder_detail` | Ownership | Named institutional holders |
| `get_promoter_pledge` | Ownership, Risk | Governance risk signal |
| `get_delivery_trend` | Ownership, Technical | Accumulation vs speculation |
| `get_consensus_estimate` | Business, Valuation | Analyst consensus |
| `get_earnings_surprises` | Business, Financial, Risk | Beat/miss track record |
| `get_macro_snapshot` | Risk | VIX, crude, rates, currency |
| `get_fii_dii_streak` | Ownership, Risk, Technical | Institutional momentum |
| `get_fii_dii_flows` | Ownership, Technical | Market-wide flow context |
| `get_chart_data` | Financial (pe, price, sales_margin), Valuation (ev_ebitda, pbv), Technical (price, mcap_sales) | Time series visualizations |
| `get_recent_filings` | Risk | Corporate filings — regulatory/legal |
| `get_composite_score` | Risk | 8-factor quantified score |
| `get_financial_growth_rates` | Financial | Pre-computed CAGRs |
| `get_dupont_decomposition` | Financial | ROE quality breakdown |
| `get_key_metrics_history` | Financial | 10yr per-share metrics |
| `get_technical_indicators` | Technical | RSI, SMA, MACD, ADX |

### New Tools Required (3) — Peer Benchmarking

| Tool | Description | Agent(s) | Why New |
|------|-------------|----------|---------|
| `get_peer_metrics` | FMP key metrics (PE, PB, EV/EBITDA, ROE, ROIC, FCF yield, margins, debt/equity) for subject + top 5 peers. Returns `{subject: {...}, peers: [{symbol, ...}], sector_median: {...}}` | Financial, Valuation, Risk, Business | Existing `get_peer_comparison` only has Screener surface data (CMP, PE, MCap, ROCE). Need deep per-peer metrics for real benchmarking. FMP `key_metrics` endpoint gives 20+ fields per peer. |
| `get_peer_growth` | FMP growth rates (revenue, EBITDA, NI, EPS, FCF — 1yr/3yr/5yr CAGRs) for subject + top 5 peers. Same return structure. | Financial, Business | Existing `get_financial_growth_rates` only covers the subject. Need peer growth rates to answer "Is 15% revenue growth good for this sector? Or is every competitor growing 25%?" |
| `get_sector_benchmarks` | Computed sector aggregates for a given metric: median, P25, P75, min, max, subject's percentile rank. Reads from `sector_benchmarks` table. | ALL agents | The statistical frame. Every agent that presents a number should call this to get "where does this company rank?" No existing tool provides percentile context. |

**Why these can't be served by existing tools:**
- `get_peer_comparison` → Screener surface table: CMP, PE, MCap, div yield, quarterly profit/sales, ROCE. No margins, no growth, no FCF, no debt metrics, no EV/EBITDA, no ROE, no ROIC. Not deep enough for real benchmarking.
- `get_key_metrics_history` → only fetches for the subject symbol. Would need to be called N times for N peers, and the agent would need to know peer symbols. Better to have a single tool that returns subject + peers together with computed aggregates.
- `get_financial_growth_rates` → same issue, subject-only.

### Tools shared across agents (intentional)

Some tools appear in multiple agents because they serve different analytical purposes:
- `get_quarterly_results` in Business = "how much does it make?", in Financial = "what's the growth rate and margin trend?", in Risk = "how volatile are earnings?"
- `get_sector_benchmarks` in ALL agents = every number needs a frame of reference
- `get_peer_comparison` in Business = "who are the competitors?", in Valuation = "are we cheap relative to peers?", in Risk = "how do our risk metrics compare?"

### Potential Future Tool (not blocking)

- `get_industry_profile` — cached industry/TAM data (similar to `get_business_profile` but at sector level). Currently handled via web search in the Business agent. Could be added later if we find ourselves repeatedly researching the same industries.

---

## Phase 2: Synthesis Agent

**Purpose:** Read the 6 structured briefings (NOT the full reports — those are standalone). Cross-reference signals across agents. Produce sections that require multi-domain insight.

**CLI:** `flowtrack research run synthesis -s SYMBOL` (requires Phase 1 outputs to exist)

**Tools (2):**

| Tool | Why |
|------|-----|
| `get_composite_score` | 8-factor summary for the verdict |
| `get_fair_value` | Combined valuation for the verdict |

Plus: reads 6 JSON briefing files from `~/vault/stocks/{SYMBOL}/briefings/`.

**Max turns:** 10 | **Max budget:** $0.30

**Sections produced:**
- **Verdict** — BUY / HOLD / SELL with confidence level. 2-3 sentence thesis. Must reference specific data from multiple agents' briefings.
- **Executive Summary** — 2-3 paragraphs for someone who will only read this section. Beginner-friendly. References key numbers from all agents.
- **Key Signals** — cross-referenced insights that only emerge when combining multiple agents' findings:
  - "FII selling + MF buying = institutional handoff (bullish medium-term)" ← ownership + ownership
  - "Insider buying while price falls = management conviction at weakness" ← ownership + technical
  - "Revenue decelerating but margins expanding = operating leverage" ← financial + business
  - "PE below 25th percentile + DCF undervalued + analyst upgrades = potential re-rating" ← valuation
- **Catalysts & What to Watch** — forward-looking triggers with specific metrics
- **The Big Question** — bull case, bear case, and the key question the investor needs to answer

---

## Phase 3: Assembly (Code, Not Agent)

Python function that concatenates reports + synthesis into final output.

**Assembly order:**
1. Title + metadata
2. **Verdict** (from synthesis) — reader sees the conclusion first
3. **Executive Summary** (from synthesis)
4. **Key Signals** (from synthesis)
5. **The Business** (from Agent 1 — Business)
6. **Earnings & Growth** (from Agent 2 — Financial)
7. **Valuation** (from Agent 4 — Valuation)
8. **Ownership Intelligence** (from Agent 3 — Ownership)
9. **Risk Assessment** (from Agent 5 — Risk)
10. **Technical & Market Context** (from Agent 6 — Technical)
11. **Catalysts & What to Watch** (from synthesis)
12. **The Big Question** (from synthesis)
13. **Glossary** (auto-generated from inline definitions)

**Output formats:**
- Markdown: `~/vault/stocks/{SYMBOL}/thesis/{DATE}.md`
- HTML (styled, mermaid-rendered): `~/reports/{symbol}-thesis.html`

---

## Implementation: Claude Agent SDK Patterns

### Tool Subsets (new registries in `tools.py`)

```python
# Peer benchmarking tools — shared across most agents
_PEER_TOOLS = [get_peer_metrics, get_peer_growth, get_sector_benchmarks]

BUSINESS_AGENT_TOOLS = [
    get_company_info, get_company_profile, get_company_documents,
    get_business_profile, save_business_profile,
    get_quarterly_results, get_annual_financials, get_screener_ratios,
    get_valuation_snapshot, get_peer_comparison, get_expense_breakdown,
    get_consensus_estimate, get_earnings_surprises,
    *_PEER_TOOLS,  # peer growth rates + sector benchmarks for business comparison
]  # 16 tools

FINANCIAL_AGENT_TOOLS = [
    get_company_info, get_quarterly_results, get_annual_financials,
    get_screener_ratios, get_expense_breakdown, get_financial_growth_rates,
    get_dupont_decomposition, get_key_metrics_history,
    get_chart_data, get_earnings_surprises,
    *_PEER_TOOLS,  # peer metrics + growth for financial benchmarking
]  # 13 tools

OWNERSHIP_AGENT_TOOLS = [
    get_shareholding, get_shareholding_changes, get_insider_transactions,
    get_bulk_block_deals, get_mf_holdings, get_mf_holding_changes,
    get_shareholder_detail, get_promoter_pledge, get_delivery_trend,
    get_fii_dii_flows, get_fii_dii_streak,
    get_sector_benchmarks,  # for benchmarking promoter holding, FII%, pledge vs sector
]  # 12 tools

VALUATION_AGENT_TOOLS = [
    get_valuation_snapshot, get_valuation_band, get_pe_history,
    get_fair_value, get_dcf_valuation, get_dcf_history,
    get_price_targets, get_analyst_grades, get_peer_comparison,
    get_chart_data, get_consensus_estimate,
    *_PEER_TOOLS,  # peer valuations for relative comparison
]  # 14 tools

RISK_AGENT_TOOLS = [
    get_quarterly_results, get_annual_financials, get_promoter_pledge,
    get_insider_transactions, get_macro_snapshot, get_fii_dii_streak,
    get_composite_score, get_earnings_surprises, get_recent_filings,
    get_valuation_snapshot, get_peer_comparison,
    *_PEER_TOOLS,  # peer risk metrics for relative risk positioning
]  # 14 tools

TECHNICAL_AGENT_TOOLS = [
    get_technical_indicators, get_chart_data, get_delivery_trend,
    get_valuation_snapshot, get_bulk_block_deals,
    get_fii_dii_flows, get_fii_dii_streak,
    get_sector_benchmarks,  # for benchmarking delivery %, beta vs sector
]  # 8 tools
```

### Parallel Execution via `asyncio.gather()`

```python
async def run_all_agents(symbol: str, model: str | None = None):
    """Fan-out: run 6 specialist agents in parallel."""
    results = await asyncio.gather(
        _run_specialist("business", symbol, BUSINESS_AGENT_TOOLS, BUSINESS_AGENT_PROMPT, max_turns=25, model=model),
        _run_specialist("financials", symbol, FINANCIAL_AGENT_TOOLS, FINANCIAL_AGENT_PROMPT, max_turns=20, model=model),
        _run_specialist("ownership", symbol, OWNERSHIP_AGENT_TOOLS, OWNERSHIP_AGENT_PROMPT, max_turns=18, model=model),
        _run_specialist("valuation", symbol, VALUATION_AGENT_TOOLS, VALUATION_AGENT_PROMPT, max_turns=18, model=model),
        _run_specialist("risk", symbol, RISK_AGENT_TOOLS, RISK_AGENT_PROMPT, max_turns=15, model=model),
        _run_specialist("technical", symbol, TECHNICAL_AGENT_TOOLS, TECHNICAL_AGENT_PROMPT, max_turns=12, model=model),
    )
    return dict(zip(["business", "financials", "ownership", "valuation", "risk", "technical"], results))
```

### Individual Agent Runner

```python
async def _run_specialist(
    name: str, symbol: str, tools: list, system_prompt: str,
    max_turns: int = 20, max_budget: float = 0.50, model: str | None = None,
) -> dict:
    """Run a single specialist agent. Returns {report: str, briefing: dict}."""
    server = create_sdk_mcp_server(f"{name}-data", tools=tools)
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers={name: server},
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
        output_format={                      # Structured output for briefing
            "type": "object",
            "properties": {
                "report": {"type": "string"},   # Full markdown report section
                "briefing": {"type": "object"}, # Structured JSON for synthesis
            },
            "required": ["report", "briefing"],
        },
    )

    result = None
    async for message in query(
        prompt=f"Analyze {symbol}. Pull all relevant data using your tools. Produce your full report section and structured briefing.",
        options=options,
    ):
        if isinstance(message, ResultMessage):
            result = message.structured_output or {"report": message.result, "briefing": {}}

    # Save standalone report
    vault_dir = Path.home() / "vault" / "stocks" / symbol.upper() / "reports"
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / f"{name}.md").write_text(result["report"])

    # Save briefing for synthesis
    briefing_dir = Path.home() / "vault" / "stocks" / symbol.upper() / "briefings"
    briefing_dir.mkdir(parents=True, exist_ok=True)
    (briefing_dir / f"{name}.json").write_text(json.dumps(result["briefing"], indent=2))

    return result
```

### CLI Commands

```python
@app.command()
def run(
    agent: str = typer.Argument(help="Agent: business|financials|ownership|valuation|risk|technical|synthesis|all"),
    symbol: str = typer.Option(..., "--symbol", "-s"),
    skip_fetch: bool = typer.Option(False, "--skip-fetch"),
    model: str | None = typer.Option(None, "--model", "-m"),
):
    """Run individual research agent or full pipeline."""
    if not skip_fetch:
        refresh_for_research(symbol) if agent != "business" else refresh_for_business(symbol)

    if agent == "all":
        results = asyncio.run(run_all_agents(symbol, model))
        synthesis = asyncio.run(run_synthesis_agent(symbol, model))
        assemble_final_report(symbol, results, synthesis)
    elif agent == "synthesis":
        synthesis = asyncio.run(run_synthesis_agent(symbol, model))
    else:
        result = asyncio.run(_run_specialist(agent, symbol, ...))
```

---

## Report Quality Standards (All Agents)

### Beginner-Friendly Requirements

Every agent's system prompt MUST include these rules:

1. **First-mention rule**: The FIRST time any financial/technical term appears, provide an inline definition in parentheses or as a follow-up sentence. Use an analogy from everyday life. Reference this company's actual numbers in the explanation.

2. **Chart annotation rule**: Every chart, table, or data visualization MUST have:
   - **"What this shows"** — one sentence describing what you're looking at
   - **"How to read it"** — what the axes mean, what patterns to look for
   - **"What {COMPANY}'s chart tells us"** — specific interpretation for this stock

3. **No orphan numbers**: Never state a number without context. Bad: "ROCE is 22%". Good: "ROCE is 22% — this means for every ₹100 of capital the business uses, it generates ₹22 of profit. The industry average is ~15%, so {COMPANY} is significantly above average. And it's improving: it was 14% five years ago."

4. **Explain causation, not just correlation**: Don't just say "margins improved". Say "Operating margin improved from 18% to 24% because revenue grew 23% while employee costs (the biggest expense at 43% of revenue) only grew 12% — this is called 'operating leverage', where fixed costs get spread over more revenue."

5. **Use the reader's language**: "Think of it like..." analogies. Map financial concepts to everyday decisions (buying a house, running a shop, choosing a savings account).

6. **Tables must be readable**: Column headers must be self-explanatory. Include a "What to look for" note below each table.

---

## File Structure (New/Modified)

```
flowtracker/research/
├── agent.py              # REWRITE — _run_specialist(), run_all_agents(), run_synthesis_agent()
│                         #   Remove old generate_thesis(), generate_business_profile()
│                         #   Add structured output support, individual + parallel modes
├── tools.py              # MODIFY — add 3 new peer tools, 6 new tool registries
├── prompts.py            # REWRITE — 6 specialist prompts + 1 synthesis prompt
│                         #   Remove old RESEARCH_SYSTEM_PROMPT, BUSINESS_SYSTEM_PROMPT
│                         #   Each prompt enforces peer benchmarking + beginner explanations
├── assembly.py           # NEW — assemble_final_report(), HTML rendering, section concatenation
├── briefing.py           # NEW — BriefingEnvelope model, save/load briefings to vault
├── verifier.py           # NEW — _run_verifier(), verification prompt, correction flow
├── peer_refresh.py       # NEW — refresh_peers(symbol), compute_sector_benchmarks()
├── data_api.py           # MODIFY — add get_peer_metrics(), get_peer_growth(), get_sector_benchmarks()
├── refresh.py            # MODIFY — call refresh_peers() after refresh_for_research()
├── thesis_tracker.py     # NO CHANGE
├── data_collector.py     # NO CHANGE (legacy fundamentals path)
├── fundamentals.py       # NO CHANGE (data-only HTML report)
└── models.py             # MODIFY — add SectorBenchmark model

flowtracker/
├── store.py              # MODIFY — add sector_benchmarks table + query methods
├── research_commands.py  # MODIFY — add `run` subcommand, remove old thesis/business wiring
```

---

## Migration Strategy

**Direct replacement** — no backward compatibility phase. The existing single-agent `generate_thesis()` and `generate_business_profile()` in `agent.py` are replaced entirely.

- `flowtrack research thesis -s X` → runs the full multi-agent pipeline (Phase 0 → Phase 1 parallel → Phase 2 synthesis → Phase 3 assembly)
- `flowtrack research run <agent> -s X` → runs one specialist agent independently
- `flowtrack research business -s X` → now an alias for `flowtrack research run business -s X`
- Old single-agent prompts (`RESEARCH_SYSTEM_PROMPT`, `BUSINESS_SYSTEM_PROMPT`) are replaced by 6 specialist prompts + 1 synthesis prompt

---

## Cost Estimates

| Command | Agents | Estimated Cost | Time |
|---------|--------|---------------|------|
| `run business -s X` | 1 agent | ~$0.30-0.50 | 2-3 min |
| `run financials -s X` | 1 agent | ~$0.20-0.40 | 1-2 min |
| `run ownership -s X` | 1 agent | ~$0.15-0.35 | 1-2 min |
| `run valuation -s X` | 1 agent | ~$0.15-0.35 | 1-2 min |
| `run risk -s X` | 1 agent | ~$0.10-0.30 | 1 min |
| `run technical -s X` | 1 agent | ~$0.10-0.25 | 1 min |
| `run synthesis -s X` | 1 agent (reads briefings) | ~$0.15-0.30 | 1 min |
| `thesis -s X` (full pipeline) | 6 parallel + 1 synthesis | ~$1.50-2.50 | 3-5 min |
| Current `thesis -s X` (old) | 1 agent, 30 turns | ~$2.00-5.00 | 5-10 min |

Multi-agent should be **cheaper and faster** than current single-agent because:
- Agents have focused context (fewer tools, shorter prompts)
- Agents run in parallel (wall-clock time ≈ slowest agent, not sum)
- `max_budget_usd` prevents runaway costs
- Peer data refresh adds ~15s to Phase 0 (25 FMP calls + 5 yfinance calls)

## Agent Independence & Composition

### Individual Run Mode

Every specialist agent (1-6) is independently runnable. Each produces a **complete, standalone report section** that can be read on its own:

```bash
# Run just the business analysis — doesn't need any other agent
flowtrack research run business -s INDIAMART

# Run just valuation — standalone, complete
flowtrack research run valuation -s INDIAMART

# Run the full pipeline — all agents + synthesis
flowtrack research thesis -s INDIAMART
```

### When Is the Synthesis Agent Used?

The **Synthesis agent** (Phase 2) only runs in two scenarios:
1. `flowtrack research thesis -s X` — full pipeline, auto-runs after all Phase 1 agents complete
2. `flowtrack research run synthesis -s X` — manually, requires Phase 1 briefing JSONs to exist in `~/vault/stocks/{SYMBOL}/briefings/`

It is **never** auto-invoked when running individual agents. Individual agents are self-contained.

### Composition Flexibility

You can mix and match:
```bash
# I only care about valuation and ownership for a quick check
flowtrack research run valuation -s SBIN
flowtrack research run ownership -s SBIN

# I ran business and financial yesterday, now want risk
flowtrack research run risk -s SBIN

# All briefings exist from individual runs — just synthesize
flowtrack research run synthesis -s SBIN

# Or run the whole thing end-to-end
flowtrack research thesis -s SBIN
```

Each individual run saves both:
- **Report section** → `~/vault/stocks/{SYMBOL}/reports/{agent}.md` (readable standalone)
- **Briefing JSON** → `~/vault/stocks/{SYMBOL}/briefings/{agent}.json` (for synthesis)

---

## Implementation: Task Breakdown

This section is the **implementation spec for a fresh session**. Each task has exact file paths, what to do, dependencies, and verification commands. The implementing session should read this plan, then execute in order.

### Codebase Context (read this first)

```
Project root: /Users/tarang/Documents/Projects/equity-research/flow-tracker/
Package:      flowtracker (Python 3.12+, managed with uv)
CLI:          uv run flowtrack <command>
DB:           ~/.local/share/flowtracker/flows.db (SQLite)
Vault:        ~/vault/stocks/{SYMBOL}/
Reports:      ~/Documents/Projects/equity-research/flow-tracker/reports/
Agent SDK:    claude-agent-sdk>=0.1.50 (already in pyproject.toml)

Key files to read before starting:
- flowtracker/research/agent.py      (current agent — will be rewritten)
- flowtracker/research/tools.py      (39 MCP tools — will be extended)
- flowtracker/research/prompts.py    (current prompts — will be rewritten)
- flowtracker/research/data_api.py   (ResearchDataAPI — will be extended)
- flowtracker/research/refresh.py    (refresh_for_research — will be extended)
- flowtracker/store.py               (FlowStore, ~2900 lines — will add 1 table + methods)
- flowtracker/research_commands.py   (CLI commands — will add `run` + `verify`)
- flowtracker/fmp_client.py          (FMP API client — already supports all needed endpoints)
- flowtracker/screener_client.py     (Screener.in client — no changes needed)

Patterns to follow:
- MCP tools: @tool decorator from claude_agent_sdk, return {"content": [{"type": "text", "text": json}]}
- Store: context manager (with FlowStore() as store:), SQLite, upsert patterns
- Data API: ResearchDataAPI wraps FlowStore, returns clean dicts via _clean()
- CLI: Typer subcommand groups, Rich console for display
- All monetary values in crores (₹1 Cr = 10M)
- Symbols uppercase, yfinance/FMP use .NS suffix
```

### Task Strategy

**This is a Large tier task.** Use the orchestrator pattern:
- Plan the dependency graph (below)
- Dispatch independent tasks to subagents in parallel
- Verify after each batch before proceeding
- The prompt engineering (Batch 3) is the critical path — start with ONE agent prompt, iterate to quality, then replicate the pattern

**Worktree:** Create `git worktree add ../equity-research-multiagent -b feat/multi-agent-research main`

### Dependency Graph

```
Batch 1 (foundation — all parallel, no deps):
  ┌─ T1: sector_benchmarks table + store methods
  ├─ T2: peer_refresh.py (refresh_peers function)
  ├─ T3: briefing.py (BriefingEnvelope model)
  └─ T4: 3 new peer tools (data_api + tools.py)
         depends on: T1

Batch 2 (agent infra — depends on Batch 1):
  ┌─ T5: 6 tool registries in tools.py
  ├─ T6: _run_specialist() in agent.py
  └─ T7: CLI `run` command in research_commands.py
         depends on: T5, T6

Batch 3 (prompts — depends on Batch 2, critical path):
  ┌─ T8: Shared prompt preamble (beginner rules, peer benchmarking rules)
  ├─ T9: Business agent prompt — write, test, iterate
  ├─ T10: Financial agent prompt
  ├─ T11: Ownership agent prompt
  ├─ T12: Valuation agent prompt
  ├─ T13: Risk agent prompt
  └─ T14: Technical agent prompt
         T9 first (establish quality bar), then T10-T14 in parallel

Batch 4 (verification — depends on Batch 3):
  ┌─ T15: Evidence log format in structured output
  ├─ T16: verifier.py (_run_verifier + verification prompt)
  └─ T17: Correction flow (auto-apply, re-run on fail)
         T15 first, then T16, then T17

Batch 5 (orchestration — depends on Batch 4):
  ┌─ T18: Parallel orchestrator (run_all_agents + verification)
  ├─ T19: Synthesis agent + prompt
  ├─ T20: assembly.py (concatenate + HTML render)
  └─ T21: Wire `thesis` command to full pipeline
         T18 first, then T19+T20 parallel, then T21

Batch 6 (testing & iteration):
  T22-T24: Test individual agents, verification, full pipeline
```

---

### T1: Sector Benchmarks Table + Store Methods

**File:** `flowtracker/store.py`
**Action:** Add new table and query/compute methods
**Blocked by:** Nothing

**What to do:**
1. Add `sector_benchmarks` table to the `_SCHEMA` string (after `alerts` table):
```sql
CREATE TABLE IF NOT EXISTS sector_benchmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_symbol TEXT NOT NULL,
    metric TEXT NOT NULL,
    subject_value REAL,
    peer_count INTEGER,
    sector_median REAL,
    sector_p25 REAL,
    sector_p75 REAL,
    sector_min REAL,
    sector_max REAL,
    percentile REAL,
    computed_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(subject_symbol, metric)
);
```
2. Add `upsert_sector_benchmark(symbol, metric, subject_value, peer_values: list[float])` method — computes median, P25, P75, min, max, percentile from peer_values, upserts into table
3. Add `get_sector_benchmark(symbol, metric) -> dict | None` method
4. Add `get_all_sector_benchmarks(symbol) -> list[dict]` method

**Verify:** `uv run python -c "from flowtracker.store import FlowStore; s = FlowStore(); s.__enter__(); print('ok'); s.__exit__(None,None,None)"`

---

### T2: Peer Refresh Function

**File:** `flowtracker/research/peer_refresh.py` (NEW)
**Action:** Create `refresh_peers(symbol)` function
**Blocked by:** T1 (needs sector_benchmarks table)

**What to do:**
1. Read peer list from `store.get_peers(symbol)` — already populated by Screener during `refresh_for_research`
2. Filter to top 5 by `market_cap` (skip peers with market_cap < 10% of subject)
3. For each peer symbol, fetch:
   - `FMPClient().fetch_key_metrics(peer, limit=1)` → store in `fmp_key_metrics` table (already exists)
   - `FMPClient().fetch_financial_growth(peer, limit=1)` → store in `fmp_financial_growth` table (already exists)
   - `FMPClient().fetch_dcf(peer)` → store in `fmp_dcf_values` table (already exists)
   - `FundClient().fetch_valuation_snapshot(peer)` → store in `valuation_snapshot` table (already exists)
4. Compute sector benchmarks for ~15 key metrics: `pe`, `pb`, `ev_ebitda`, `roe`, `roic`, `roce`, `fcf_yield`, `debt_to_equity`, `net_profit_margin`, `revenue_growth_3y`, `revenue_growth_5y`, `dividend_yield`, `opm`, `npm`, `market_cap`
5. For each metric: collect subject value + peer values → call `store.upsert_sector_benchmark()`
6. Add 0.5s sleep between FMP calls (rate limit)
7. Wrap each peer fetch in try-except — log warning and skip on failure (some peers may not have FMP data)

**Pattern to follow:** Look at `refresh_for_research()` in `refresh.py` for error handling and logging patterns.

**Verify:** `uv run python -c "from flowtracker.research.peer_refresh import refresh_peers; print(refresh_peers('INDIAMART'))"`

---

### T3: Briefing Envelope Model

**File:** `flowtracker/research/briefing.py` (NEW)
**Action:** Create Pydantic models for briefing + evidence, save/load functions
**Blocked by:** Nothing

**What to do:**
1. Create `BriefingEnvelope` Pydantic model:
```python
class ToolEvidence(BaseModel):
    tool: str
    args: dict
    result_summary: str
    result_hash: str  # sha256 of full result JSON

class BriefingEnvelope(BaseModel):
    agent: str          # "business", "financials", etc.
    symbol: str
    generated_at: str   # ISO datetime
    report: str         # full markdown
    briefing: dict      # structured JSON for synthesis
    evidence: list[ToolEvidence]

class VerificationResult(BaseModel):
    agent_verified: str
    symbol: str
    verdict: str        # "pass", "pass_with_notes", "fail"
    spot_checks_performed: int
    issues: list[dict]
    corrections: list[str]
    overall_data_quality: str
```
2. Add `save_envelope(envelope: BriefingEnvelope)` — saves report to `~/vault/stocks/{SYMBOL}/reports/{agent}.md`, briefing to `~/vault/stocks/{SYMBOL}/briefings/{agent}.json`, evidence to `~/vault/stocks/{SYMBOL}/evidence/{agent}.json`
3. Add `load_envelope(symbol: str, agent: str) -> BriefingEnvelope | None`
4. Add `load_all_briefings(symbol: str) -> dict[str, dict]` — loads all briefing JSONs for synthesis

**Verify:** Create a test envelope, save it, load it back, assert equality.

---

### T4: 3 New Peer Tools

**Files:** `flowtracker/research/data_api.py`, `flowtracker/research/tools.py`
**Action:** Add `get_peer_metrics()`, `get_peer_growth()`, `get_sector_benchmarks()` to data_api and as MCP tools
**Blocked by:** T1 (sector_benchmarks table)

**What to do in `data_api.py`:**
1. `get_peer_metrics(symbol) -> dict` — reads `fmp_key_metrics` for subject + all peers (from `peer_comparison` table). Returns `{"subject": {...}, "peers": [{symbol, pe, pb, roe, ...}, ...], "sector_median": {...}}`
2. `get_peer_growth(symbol) -> dict` — reads `fmp_financial_growth` for subject + all peers. Same structure.
3. `get_sector_benchmarks(symbol, metric: str | None = None) -> list[dict]` — reads from `sector_benchmarks` table. If metric given, returns one; if None, returns all.

**What to do in `tools.py`:**
1. Add 3 `@tool()` decorated functions wrapping the above
2. Add them to a `_PEER_TOOLS` list for easy inclusion in agent tool sets

**Verify:** `uv run flowtrack research data peer_metrics -s INDIAMART --raw` (after wiring in research_commands.py data dispatch)

---

### T5: 6 Tool Registries

**File:** `flowtracker/research/tools.py`
**Action:** Add 6 new tool lists at bottom of file
**Blocked by:** T4 (peer tools must exist)

**What to do:** Add `BUSINESS_AGENT_TOOLS`, `FINANCIAL_AGENT_TOOLS`, `OWNERSHIP_AGENT_TOOLS`, `VALUATION_AGENT_TOOLS`, `RISK_AGENT_TOOLS`, `TECHNICAL_AGENT_TOOLS` — exact definitions are in the "Tool Subsets" section above.

**Keep:** Existing `RESEARCH_TOOLS` and `BUSINESS_TOOLS` lists — they're used by the legacy `data` command. Remove them later when the old code is fully replaced.

**Verify:** `uv run python -c "from flowtracker.research.tools import BUSINESS_AGENT_TOOLS; print(len(BUSINESS_AGENT_TOOLS))"`

---

### T6: Specialist Agent Runner

**File:** `flowtracker/research/agent.py`
**Action:** Rewrite to add `_run_specialist()`, keep old functions temporarily
**Blocked by:** T3 (briefing model), T5 (tool registries)

**What to do:**
1. Add `_run_specialist(name, symbol, tools, system_prompt, max_turns, max_budget, model)` — see code in "Individual Agent Runner" section above
2. Use `output_format` for structured output with `report` + `briefing` + `evidence` fields
3. Save outputs via `briefing.save_envelope()`
4. Add `run_single_agent(agent_name, symbol, model, skip_fetch, verify)` — public function for CLI
5. Keep `generate_thesis()` and `generate_business_profile()` for now — they'll be replaced in T21

**Verify:** `uv run flowtrack research run business -s INDIAMART --skip-fetch` (after T7 wires CLI)

---

### T7: CLI `run` + `verify` Commands

**File:** `flowtracker/research_commands.py`
**Action:** Add `run` and `verify` subcommands
**Blocked by:** T6 (specialist runner)

**What to do:**
1. Add `run` command:
```python
@app.command()
def run(
    agent: Annotated[str, typer.Argument(help="Agent: business|financials|ownership|valuation|risk|technical|synthesis|all")],
    symbol: Annotated[str, typer.Option("--symbol", "-s")],
    skip_fetch: Annotated[bool, typer.Option("--skip-fetch")] = False,
    verify: Annotated[bool, typer.Option("--verify")] = False,
    skip_verify: Annotated[bool, typer.Option("--skip-verify")] = False,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    verify_model: Annotated[str | None, typer.Option("--verify-model")] = None,
):
```
2. Add `verify` command:
```python
@app.command()
def verify(
    agent: Annotated[str, typer.Argument(help="Agent to verify")],
    symbol: Annotated[str, typer.Option("--symbol", "-s")],
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
):
```
3. Wire refresh → agent → optional verify → display result path

**Verify:** `uv run flowtrack research run --help` shows new command with all options

---

### T8: Shared Prompt Preamble

**File:** `flowtracker/research/prompts.py`
**Action:** Create the shared rules that ALL specialist prompts include
**Blocked by:** Nothing (but should be done before T9-T14)

**What to do:** Create `SHARED_PREAMBLE` string containing:
1. Beginner-friendly rules (first-mention definitions, chart annotations, no orphan numbers, causation not correlation, reader's language, readable tables) — from "Report Quality Standards" section
2. Peer benchmarking rules: "Every metric you present MUST include sector context. Call `get_sector_benchmarks` for the metric and include: sector median, percentile rank, peer comparison table."
3. Evidence logging rules: "After your analysis, produce an evidence log listing every tool call you made, the key data points you extracted, and which claims in your report each data point supports."
4. Indian market conventions: crores, fiscal year April-March, NSE symbols uppercase
5. Structured output rules: "Your final output MUST be a JSON object with 'report' (full markdown), 'briefing' (structured JSON), and 'evidence' (tool call log)."

Each specialist prompt will be: `SHARED_PREAMBLE + specialist-specific instructions`

**Verify:** Read it, check it covers all rules from the plan.

---

### T9: Business Agent Prompt (critical path — iterate to quality)

**File:** `flowtracker/research/prompts.py`
**Action:** Write `BUSINESS_AGENT_PROMPT`
**Blocked by:** T8 (shared preamble)

**This is the most important task.** The Business agent prompt sets the quality bar for all other prompts. Iterate until the output is genuinely beginner-friendly with real peer context.

**What to do:**
1. Write the full prompt combining `SHARED_PREAMBLE` + business-specific instructions from "Agent 1: Business Understanding" section
2. Include: tool usage order, report sections, inline explanation examples, briefing JSON schema
3. Run it: `uv run flowtrack research run business -s INDIAMART`
4. Read the output report. Check:
   - Does every financial term get an inline definition on first use?
   - Does every chart have "What this shows / How to read it / What it tells us"?
   - Are peer comparisons present with sector context?
   - Would a complete beginner understand this?
5. Iterate the prompt until quality is right
6. This prompt becomes the **template** for T10-T14

**Verify:** Run on 2 different stocks (e.g., INDIAMART and SBIN — very different businesses). Both reports should be beginner-friendly and peer-benchmarked.

---

### T10-T14: Remaining 5 Agent Prompts (can be parallelized)

**File:** `flowtracker/research/prompts.py`
**Action:** Write prompts for Financial, Ownership, Valuation, Risk, Technical
**Blocked by:** T9 (Business prompt — establishes the pattern)

Follow the same structure as T9. Each prompt should:
- Use `SHARED_PREAMBLE`
- List the specific tools in order of use
- Define the report sections
- Include inline explanation examples specific to that domain
- Define the briefing JSON schema

**Verify each:** `uv run flowtrack research run <agent> -s INDIAMART`, read output.

---

### T15-T17: Verification Agent

**File:** `flowtracker/research/verifier.py` (NEW)
**Blocked by:** T9 (need at least one working agent to test against)

**T15:** Extend `_run_specialist()` structured output to include evidence log. The specialist prompt (from T8) already asks for it — this task ensures the `output_format` JSON schema includes the `evidence` field and `save_envelope()` persists it.

**T16:** Write `_run_verifier(agent_name, symbol, envelope: BriefingEnvelope, model)`:
- Creates an MCP server with the same tools as the specialist (read-only — exclude `save_business_profile`)
- System prompt: verification instructions (from "What the Verifier Checks" section)
- Prompt includes: the full report + evidence log
- Uses structured output with `VerificationResult` schema
- Max turns: 10, max budget: $0.20
- Use a **different model** than the specialist (configurable)

**T17:** Write correction flow:
- `pass` → return envelope as-is
- `pass_with_notes` → apply string replacements from `corrections` list
- `fail` → re-run specialist with corrections in prompt, max 1 re-run

**Verify:** Run business agent, then run verifier on its output. Manually introduce an error in the report, verify the verifier catches it.

---

### T18: Parallel Orchestrator

**File:** `flowtracker/research/agent.py`
**Action:** Add `run_all_agents()` with `asyncio.gather()`
**Blocked by:** T6 (specialist runner), T16 (verifier)

**What to do:**
1. `run_all_agents(symbol, model, verify_model)` — runs 6 specialists in parallel, then 6 verifiers in parallel, applies corrections
2. Handle partial failures — if one agent fails, the others still produce output
3. Return dict of verified envelopes

**Verify:** `uv run flowtrack research run all -s INDIAMART` — check all 6 reports + briefings saved to vault

---

### T19: Synthesis Agent

**File:** `flowtracker/research/agent.py` + `prompts.py`
**Action:** Add `run_synthesis_agent(symbol, model)`
**Blocked by:** T18 (needs verified briefings)

**What to do:**
1. Write `SYNTHESIS_AGENT_PROMPT` — reads 6 briefing JSONs, produces cross-referenced sections (from "Phase 2: Synthesis Agent" section)
2. Tools: `get_composite_score`, `get_fair_value` (only 2 tools needed)
3. Structured output: verdict, executive summary, key signals, catalysts, big question
4. Load briefings via `load_all_briefings(symbol)`

**Verify:** Run synthesis after all 6 agents have run. Check that cross-references actually cite data from multiple agents.

---

### T20: Assembly

**File:** `flowtracker/research/assembly.py` (NEW)
**Action:** Create `assemble_final_report(symbol, specialist_results, synthesis_result)`
**Blocked by:** T19 (synthesis output format)

**What to do:**
1. Concatenate in assembly order (from "Phase 3: Assembly" section)
2. HTML rendering with mermaid.js CDN (copy pattern from existing `_wrap_html_with_mermaid_js` in agent.py)
3. Auto-generate glossary from inline definitions (optional — can skip v1)
4. Save to vault + reports directory

**Verify:** Open HTML report in browser. All sections present, mermaid diagrams render.

---

### T21: Wire `thesis` Command

**File:** `flowtracker/research_commands.py`
**Action:** Replace old `thesis` command to use multi-agent pipeline
**Blocked by:** T18, T19, T20

**What to do:**
1. `thesis` command now calls: `refresh_for_research()` → `refresh_peers()` → `run_all_agents()` (with verification) → `run_synthesis_agent()` → `assemble_final_report()`
2. Remove old `generate_thesis()` and `generate_business_profile()` from agent.py
3. `business` command becomes alias for `run business`
4. Remove old `RESEARCH_SYSTEM_PROMPT` and `BUSINESS_SYSTEM_PROMPT` from prompts.py

**Verify:** `uv run flowtrack research thesis -s INDIAMART` — full end-to-end, HTML report opens in browser.

---

### T22-T24: Testing & Iteration

**T22:** Test each agent individually on 3 stocks: INDIAMART (B2B platform), SBIN (bank), RELIANCE (conglomerate). These are very different businesses — prompts must work across all.

**T23:** Test verification: run an agent, manually edit its report to introduce 2-3 errors (wrong number, wrong growth rate, unsupported claim), run verifier, confirm it catches them.

**T24:** Test full pipeline end-to-end. Review synthesis quality — does it actually cross-reference signals from multiple agents? Does the final HTML report read well as a single document?

---

### Subagent Dispatch Strategy

**Batch 1 (T1-T4):** Dispatch T1, T2, T3 as parallel subagents. T4 depends on T1, so dispatch after T1 completes.

**Batch 2 (T5-T7):** T5 depends on T4. T6 depends on T3 + T5. T7 depends on T6. Semi-sequential within batch.

**Batch 3 (T8-T14):** T8 first (shared preamble). Then T9 (business prompt — iterate to quality). Then T10-T14 in parallel.

**Batch 4 (T15-T17):** Sequential within batch (each depends on previous).

**Batch 5 (T18-T21):** T18 first. T19 + T20 in parallel. T21 last.

**Total estimated effort:** Medium-Large. ~8-10 subagent dispatches across 5 batches. The prompt engineering (T8-T14) is the critical path and will take the most iteration.

---

## Peer Benchmarking in Practice — Example

Here's how peer benchmarking changes the Financial Agent's output for INDIAMART:

### Without Peer Benchmarking (current):

> **Business Quality**
> ROCE is 22%, up from 14% five years ago. Operating margin is 32%. The company has zero debt and ₹2,874Cr in cash.

### With Peer Benchmarking (new):

> **Business Quality — How {COMPANY} Compares**
>
> ROCE (Return on Capital Employed) measures how much profit a company earns for every rupee of capital it uses. Think of it like the interest rate on a savings account — higher is better.
>
> {COMPANY}'s ROCE is **22%**, up from 14% five years ago. But is 22% good? Let's compare:
>
> | Company | ROCE | Trend (5yr) | Sector Rank |
> |---------|------|-------------|-------------|
> | **INDIAMART** | **22%** | 14% → 22% ↑ | **2nd of 6** |
> | Info Edge | 28% | 20% → 28% ↑ | 1st |
> | JustDial | 12% | 18% → 12% ↓ | 4th |
> | Affle India | 15% | 10% → 15% ↑ | 3rd |
> | **Sector Median** | **15%** | | |
> | **Sector P25-P75** | **11% – 24%** | | |
>
> **What this table tells you:** {COMPANY}'s ROCE sits at the **78th percentile** — better than most peers and improving. Only Info Edge does better. JustDial's declining ROCE is a warning sign for that company. The gap between {COMPANY} and the sector median (+7 percentage points) suggests a genuine competitive advantage, not just industry tailwinds.
>
> **How to read ROCE over time:** A rising ROCE means the business is getting more efficient — each rupee of capital generates more profit. If ROCE is rising because margins are improving (not because of more debt), that's a healthy sign. {COMPANY}'s DuPont decomposition shows the improvement is margin-driven (operating margin expanded from 18% → 32%), not leverage-driven (zero debt throughout).

This pattern applies to every metric in every agent — growth rates, margins, valuation multiples, ownership patterns, risk metrics.

---

## Gaps & Design Decisions (Must Read)

These are issues discovered during planning that the implementation session must address. They're not blockers but require decisions.

### Gap 1: WebSearch/WebFetch for Business Agent

**Problem:** The current Business agent prompt says "Use WebSearch to research... Use WebFetch to read results." These are **Claude Code built-in tools**, not our MCP tools. When we use `query()` with `bypassPermissions`, the agent gets Claude Code's built-in tools (Read, Write, Bash, WebSearch, WebFetch, etc.) **plus** our MCP tools. But if we restrict tools via `allowed_tools`, we might block web search.

**Current behavior:** The existing `_run_agent()` in `agent.py` doesn't set `allowed_tools`, so with `bypassPermissions` the agent can use WebSearch/WebFetch freely. This is how the Business agent does web research for stale profiles.

**Decision needed:** For the multi-agent setup:
- **Option A:** Don't set `allowed_tools` — agent gets all Claude Code tools + MCP tools. Simple but agent could use Bash, Write, etc.
- **Option B:** Explicitly list `allowed_tools` including `"WebSearch"`, `"WebFetch"` for the Business agent. Other agents don't need web access.

**Recommendation:** Option B. The Business agent needs web research for industry context and stale profiles. Add `"WebSearch"` and `"WebFetch"` to its `allowed_tools`. Other agents work entirely from SQLite data and don't need web access. This also prevents agents from accidentally using Bash/Write.

**Impact on plan:** T6 (`_run_specialist`) needs to accept an optional `extra_allowed_tools` parameter. Business agent passes `["WebSearch", "WebFetch"]`.

### Gap 2: Evidence Capture — Automatic vs Self-Reported

**Problem:** The plan asks agents to self-report their evidence log. But `AssistantMessage.content` already contains `ToolUseBlock` (tool name + input args) and `ToolResultBlock` (tool output). We can capture evidence **automatically** from the message stream.

**Discovery:** Confirmed via SDK inspection:
- `ToolUseBlock` has: `id`, `name`, `input` (dict)
- `ToolResultBlock` has: `tool_use_id`, `content` (str or list), `is_error`

**Recommendation:** Capture tool calls automatically in `_run_specialist()`:
```python
evidence = []
async for message in query(...):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                evidence.append({"tool": block.name, "args": block.input, "id": block.id})
            elif isinstance(block, ToolResultBlock):
                # Match to corresponding ToolUseBlock by tool_use_id
                for e in evidence:
                    if e.get("id") == block.tool_use_id:
                        e["result"] = block.content
                        e["is_error"] = block.is_error
```

This is **more reliable** than asking the agent to self-report. The agent can't forget or misrepresent a tool call. Remove the evidence logging requirement from the system prompt — it just wastes tokens.

**Impact on plan:** T15 (evidence log format) changes from "extend structured output" to "capture from message stream in `_run_specialist()`". T8 (shared preamble) removes evidence logging rules. Simpler overall.

### Gap 3: Model Strategy Per Agent

**Problem:** Different agents have different complexity levels. Running all 6 on Opus is expensive. Running all on Sonnet may produce lower quality for complex agents.

**Recommendation:**

| Agent | Recommended Model | Why |
|-------|------------------|-----|
| Business | Opus | Web research, qualitative reasoning, needs strongest model |
| Financial | Sonnet | Structured data analysis, well-defined calculations |
| Ownership | Sonnet | Mostly data presentation with interpretation |
| Valuation | Opus or Sonnet | DCF interpretation needs judgment, but data is structured |
| Risk | Sonnet | Mostly checklist-based analysis |
| Technical | Sonnet | Straightforward indicator interpretation |
| Synthesis | Opus | Cross-domain reasoning, needs strongest model |
| Verifiers | Haiku or Sonnet | Spot-checking is simpler than analysis |

**Cost impact with mixed models:**
- 2 Opus agents + 4 Sonnet agents + 6 Haiku verifiers ≈ **$0.80-1.50** vs $2.00-3.50 all-Opus
- Significant savings while maintaining quality where it matters

**Implementation:** `_run_specialist()` already takes a `model` parameter. Add a `DEFAULT_MODELS` dict in agent.py mapping agent names to default models. CLI `--model` flag overrides for all agents.

### Gap 4: HTML Rendering Must Move to Assembly

**Problem:** The current `agent.py` has `_wrap_html_with_mermaid_js()`, `_md_to_html()`, `_HTML_TEMPLATE` for rendering business profiles as HTML. When we rewrite agent.py, this rendering logic must be preserved.

**Action:** Move all HTML rendering functions from `agent.py` to `assembly.py`. The assembly step handles markdown → HTML conversion for the final report.

### Gap 5: Cost & Token Tracking

**Problem:** `ResultMessage` includes `total_cost_usd` and `usage` (input/output tokens, cache hits). We should track this per agent for cost optimization and display it.

**Recommendation:** `_run_specialist()` captures `ResultMessage.total_cost_usd` and `ResultMessage.usage`, includes in the `BriefingEnvelope`. The CLI `run` command displays a cost summary table after completion. For the full pipeline, display a breakdown:

```
Agent        Tokens (in/out)  Cost    Time
business     45K / 8K         $0.35   2m 15s
financials   30K / 6K         $0.12   1m 30s
...
verifiers    60K / 3K         $0.08   45s
synthesis    15K / 4K         $0.18   1m 00s
─────────────────────────────────────────
Total        200K / 30K       $1.05   3m 20s
```

### Gap 6: `output_format` Compatibility

**Problem:** The plan uses `output_format` for structured JSON output from agents. Per SDK research, structured output is **incompatible with extended thinking**. If we enable thinking (which improves quality), we can't use `output_format`.

**Options:**
- **Option A:** Use `output_format`, no extended thinking. Agent produces `{report, briefing}` as structured JSON.
- **Option B:** No `output_format`, enable thinking. Agent produces markdown report as `ResultMessage.result`. Parse briefing JSON from a fenced code block at the end. More fragile but better reasoning.
- **Option C:** Two-pass. First pass with thinking produces the report. Second pass (cheap, no tools) with `output_format` extracts the structured briefing from the report.

**Recommendation:** Option B for v1 — simpler, and we can always add the two-pass approach later. The agent's prompt ends with "End your response with a JSON code block containing the structured briefing." Parse it in `_run_specialist()`.

**Impact on plan:** T6 changes — don't use `output_format`, parse briefing from markdown. T3 (BriefingEnvelope) adds a `parse_from_markdown(text: str)` class method.

### Gap 7: SQLite Concurrent Reads During Parallel Agents

**Non-issue but worth noting:** 6 agents running in parallel will all read from the same SQLite database. SQLite handles concurrent reads fine (WAL mode). Our tools are read-only (except `save_business_profile`). No action needed, but if we ever add write operations to agent tools, we'll need to handle locking.

---

## References

- [Anthropic: How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — fan-out/fan-in, output compression, Opus lead + Sonnet workers
- [Claude Agent SDK Python docs](https://platform.claude.com/docs/en/agent-sdk/python) — `query()`, `ClaudeAgentOptions`, structured output, `max_budget_usd`
- [FinRobot: Tri-Agent CoT](https://arxiv.org/html/2411.08804v1) — Data-CoT → Concept-CoT → Thesis-CoT pipeline
- [TradingAgents (UCLA/MIT)](https://arxiv.org/html/2412.20138v1) — parallel analysts + bull/bear debate + risk management
- [AlphaAgents (BlackRock)](https://arxiv.org/html/2508.11152v1) — collaboration + debate modes for portfolio construction
- [Benchmarking Multi-Agent Orchestration for Financial Documents](https://arxiv.org/html/2603.22651) — hierarchical supervisor-worker wins on cost/accuracy tradeoff
- [Google ADK Context Management](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/) — artifact handles, ephemeral expansion
- [XTrace: AI Agent Context Handoff](https://xtrace.ai/blog/ai-agent-context-handoff) — structured briefings > summaries > raw dumps
