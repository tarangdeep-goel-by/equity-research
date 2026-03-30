# FlowTracker Roadmap — What To Build Next

*Last updated: 2026-03-30*

---

## Current State

The data and analysis stack is solid — 14 sources, 30 tables, 26 API methods, AI thesis agent, composite screener, full cron automation. Data coverage matches what sell-side analysts at Nomura/Goldman have access to.

What's missing isn't more data — it's the **decision framework** that turns research into positions.

```
Screen → Research → Value → Size → Monitor → Exit
                    ^^^^^   ^^^^   ^^^^^^^   ^^^^
                    GAP 1   GAP 3  GAP 4     GAP 2
```

---

## Buy-Side Gaps (Priority — These Generate Returns)

### 1. Valuation Model

**Priority:** High | **Difficulty:** Easy | **Phase:** 1

**What:** Earnings-based fair value estimate using PE band method.

> "At historical median PE of 25x and FY27E EPS of ₹42, fair value is ₹1,050. Current price ₹890 implies 18% margin of safety."

**Why it matters:** Turns research into actionable price targets. Without this, you know *what's good* but not *what's cheap*. Buy-side lives on the gap between quality and price.

**What we already have:**
- Historical PE band (percentiles via `get_valuation_band`)
- Consensus forward EPS (`get_consensus_estimate` → `forward_eps`, `eps_current_year`, `eps_next_year`)
- Trailing EPS (from `get_quarterly_results`, sum last 4Q)
- Earnings growth rate (`get_consensus_estimate` → `earnings_growth`)

**Implementation:**
- New method `get_fair_value_estimate(symbol)` in ResearchDataAPI
- Takes historical PE percentiles (10th, 25th, median, 75th) × forward EPS estimates
- Outputs: bear / base / bull fair value, current margin of safety %
- Add as new section in thesis report (between valuation band and recommendation)
- Add as MCP tool for the AI agent

**Output example:**
```json
{
  "current_price": 890,
  "trailing_eps": 38.5,
  "forward_eps_fy27": 42.0,
  "pe_band": {"p10": 18, "p25": 22, "median": 25, "p75": 32},
  "fair_value": {
    "bear": 756,   // p25 × forward EPS
    "base": 1050,  // median × forward EPS
    "bull": 1344   // p75 × forward EPS
  },
  "margin_of_safety": "18%",  // (base - current) / base
  "signal": "UNDERVALUED"      // current < bear = DEEP VALUE, < base = UNDERVALUED, > bull = EXPENSIVE
}
```

---

### 2. Thesis Tracker

**Priority:** High | **Difficulty:** Medium | **Phase:** 2

**What:** Structured "why I own this" with 3-4 falsifiable conditions per stock.

> "Buy INDIAMART if: (1) paid subs grow >10% QoQ, (2) ARPU holds above ₹50K, (3) FII selling decelerates."
> Each condition has a current status: ✅ intact / ⚠️ warning / ❌ broken.

**Why it matters:** Prevents two failure modes:
- **Holding forever** — no exit discipline, thesis drift
- **Panic-selling** — reacting to noise instead of signal

The thesis tells you when *you're wrong* vs when *the market is wrong*. If conditions are intact but price drops, that's an opportunity. If a condition breaks, that's an exit signal regardless of price.

**Implementation:**
- Structured markdown per stock at `~/vault/stocks/{SYMBOL}/thesis-tracker.md`
- Fields: conditions (list), entry price, entry date, last checked, status per condition
- Agent checks conditions against fresh data on each `research thesis` run
- New CLI: `flowtrack research thesis-check -s SYMBOL` (quick condition check without full thesis)
- Summary view: `flowtrack research thesis-status` (all tracked stocks, condition status)
- Alert integration: flag broken conditions in `/markets pulse`

**Tracker format:**
```markdown
# INDIAMART — Thesis Tracker
Entry: ₹890 on 2026-04-01

## Conditions
1. ✅ Paid subscribers growing >10% QoQ (Q3: +12.3%)
2. ⚠️ ARPU holding above ₹50K (Q3: ₹51.2K — close to threshold)
3. ✅ FII selling decelerating (Q3: -0.8% vs Q2: -2.1%)
4. ✅ ROCE above 25% (TTM: 31.2%)

## Status: INTACT (3/4 green, 1 warning)
Last checked: 2026-03-30
```

---

### 3. Portfolio View

**Priority:** Medium | **Difficulty:** Medium | **Phase:** 3

**What:** Aggregate view across all holdings — concentration %, sector exposure, total FII/DII alignment across the portfolio.

> "You have 40% in IT services — if rupee strengthens, all 3 positions lose."

**Why it matters:** Knowing 5 stocks are individually good doesn't mean owning all 5 is smart. Correlated positions = hidden concentration risk. A portfolio is more than the sum of its positions.

**Implementation:**
- New `portfolio` table in FlowStore: `(symbol, qty, avg_cost, added_at)`
- New `flowtrack portfolio` command group:
  - `portfolio add SYMBOL --qty 10 --cost 890`
  - `portfolio view` — current holdings with P&L, weights, sector breakdown
  - `portfolio risk` — concentration %, correlation matrix, sector/macro exposure
  - `portfolio rebalance` — suggest trims/adds based on equal-weight or risk-parity
- Aggregate ResearchDataAPI data across all holdings for a portfolio-level thesis check
- New skill: `/portfolio` for conversational access

---

### 4. Alert / Monitoring System

**Priority:** Medium | **Difficulty:** Medium | **Phase:** 3

**What:** Condition-based alerts that fire when data changes cross a threshold.

> "FII ownership in INDIAMART dropped below 20%"
> "Promoter pledge in XYZ crossed 5%"
> "PE for ABC went below 15x — entering value zone"

**Why it matters:** Buy-side alpha comes from reacting to ownership/valuation changes faster than the market prices them. Currently you'd have to manually check every stock.

**Implementation:**
- New `alerts` table: `(symbol, metric, operator, threshold, last_triggered, active)`
- Alert engine runs after daily-fetch cron, checks all active alerts against fresh data
- Notifications: Rich terminal summary on next `/markets pulse`, optional Telegram via n8n
- CLI: `flowtrack alert add INDIAMART fii_pct < 20`
- CLI: `flowtrack alert list` / `flowtrack alert history`
- Integrate with thesis tracker: auto-create alerts from thesis conditions

---

## Sell-Side Gaps (Lower Priority — Completeness)

### 5. DuPont Decomposition

**Priority:** Low | **Difficulty:** Easy | **Phase:** 1

**What:** ROE = Net Margin × Asset Turnover × Equity Multiplier

Shows whether ROE improvement is from better operations (margin), efficiency (turnover), or leverage (multiplier). Standard sell-side framework.

**Implementation:** Pure computation from existing `annual_financials` fields. New method `get_dupont_decomposition(symbol)` in ResearchDataAPI. Add as MCP tool.

---

### 6. Relative Valuation Matrix

**Priority:** Low | **Difficulty:** Medium | **Phase:** 4

**What:** PE/PB/EV matrix across 15-20 sector peers, each with historical band context.

> "INDIAMART trades at 20x PE vs sector median 35x, at its own 10th percentile."

**Implementation:** Batch `get_valuation_band()` across all peers from `get_peer_comparison()`. New method `get_peer_valuation_matrix(symbol)`. May be slow (fetches per-peer history).

---

### 7. Technical Indicators

**Priority:** Low | **Difficulty:** Easy | **Phase:** 2

**What:** RSI, MACD, Bollinger bands computed from bhavcopy OHLCV data (3.7M rows of daily price data already in DB).

Currently have 50/200 DMA from Screener charts. Adding momentum indicators helps with entry timing.

**Implementation:** Standard formulas on `daily_stock_data` table. New method `get_technical_indicators(symbol)`.

---

### 8. Segment-wise Revenue

**Priority:** Low | **Difficulty:** Medium | **Phase:** 4

**What:** Revenue broken by business segment (e.g., HDFC Bank: retail vs wholesale lending).

Segment trends reveal where growth is coming from. A company growing 15% overall might have one segment at 30% and another declining.

**Implementation:** Partially available via `get_expense_breakdown()` (Screener schedules). Parsing is inconsistent across companies. May need to supplement from annual report PDFs.

---

### 9. Quarterly Balance Sheet

**Priority:** Low | **Difficulty:** Medium | **Phase:** 4

**What:** We have annual BS (10yr) but not quarterly. Quarterly BS shows working capital trends, debt changes, and cash burn rate intra-year.

**Implementation:** Check if Screener Excel export includes quarterly BS data. If so, extend `parse_quarterly_from_html` or Excel parser.

---

### 10. Credit Metrics

**Priority:** Low | **Difficulty:** Medium-Hard | **Phase:** Later

**What:** Interest coverage trend, debt maturity profile, credit rating history. We have basic D/E ratio but not granular debt analysis.

Critical for leveraged companies. A company with 2x D/E and 90% short-term debt is very different from 2x D/E with long-term bonds.

**Implementation:** Partial from existing annual financials. Full picture needs CRISIL/ICRA as new data source.

---

### 11. Index Rebalance Impact

**Priority:** Low | **Difficulty:** Hard | **Phase:** Later

**What:** Upcoming MSCI/Nifty index rebalance additions/deletions. Passive fund flows follow index changes — major short-term price driver.

**Implementation:** NSE publishes rebalance lists quarterly. Would need a new scraper + free-float MCap prediction model for anticipating changes before announcement.

---

### 12. Options / Sentiment Data

**Priority:** Low | **Difficulty:** Medium | **Phase:** Later

**What:** Put-call ratio, open interest buildup, max pain from NSE options chain API. Short-term sentiment indicator.

**Implementation:** NSE options chain API is well-documented. New data source + table + client module.

---

## Build Phases

```
Phase 1 (next):     Valuation Model + DuPont
                    ← Easy, high impact. All inputs exist.
                    ← Turns research into "buy below ₹X"

Phase 2:            Thesis Tracker + Technicals
                    ← Medium effort. Completes the buy-side loop.
                    ← Turns conviction into discipline.

Phase 3:            Portfolio View + Alerts
                    ← New module. Transforms from research tool
                       to position management system.

Phase 4:            Peer Matrix + Segments + Quarterly BS
                    ← Sell-side completeness.
                    ← Nice to have, not blocking.

Later:              Credit, Index Rebalance, Options
                    ← As needed, when the use case arises.
```

### What Each Phase Unlocks

| Phase | Before | After |
|-------|--------|-------|
| **1** | "INDIAMART looks good" | "INDIAMART is 18% undervalued at ₹890, buy below ₹1,050" |
| **2** | Hold forever or panic-sell | "Condition 2 broke — ARPU fell below ₹50K. Reduce position." |
| **3** | Research individual stocks | "Portfolio is 40% IT — need to diversify before adding LTIM" |
| **4** | Compare to one peer table | "Cheapest on PE, PB, and EV/EBITDA vs all 15 banking peers historically" |
