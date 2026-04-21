# Historical Analog Agent + F&O Positioning Agent — Plan

**Status:** Draft for review
**Date:** 2026-04-20
**Phasing:** Sprint 0 (corporate-action infrastructure) → Sprint 1 (Historical Analog) → Sprint 2 (F&O ingestion) → Sprint 3 (F&O Positioning agent).

---

## Why these two

Both close dimensions no current agent reasons about. Audit of recent synth outputs showed Opus calibrates bull/base/bear probabilities purely from reasoning — no empirical grounding ("when has this setup worked before?"). Separately, India has best-in-class F&O positioning data that we literally don't touch despite 9 specialists.

- **Historical Analog** solves *conviction calibration* — "stocks at 1.34th PE percentile + FII exiting 9pp + ROCE compressing — what happened next, in the universe?"
- **F&O Positioning** solves a whole *decision dimension* — OI, PCR, futures basis, FII derivative flow. Technical agent is spot-only.

---

## Part 0 — Corporate Action Infrastructure (prerequisite)

### 0.1 Why this is Sprint 0, not an afterthought

A forward-return computation that doesn't properly back-adjust for splits and bonuses produces garbage analogs — and silently. The PIDILITIND 2:1 split in Sep 2025 already proved this: `get_price_performance` returned **−55%** when the true split-adjusted return was **−8%**. That was a *spot* return; analog matching does thousands of them over a 10-year window. Any unadjusted action poisons its analog cohort.

An audit of the current codebase found five distinct issues. Three are live problems today; two are latent but will bite as soon as Historical Analog runs. All five must be fixed before Sprint 1 starts, because the data contract we're building on top of has to be trustworthy.

### 0.2 What's broken (full inventory)

| # | Issue | Current state | Risk |
|---|---|---|---|
| 1 | **Bonus adjustment** | `split_adjustment()` in `data_api.py:6212-6239` applies split multipliers only. Bonuses are stored in `corporate_actions` with correct multipliers but never read. | **Live bug in production.** Any stock with a recent bonus shows distorted `get_price_performance` returns. Reliance 1:1 bonus (Oct 2017) = ~50% phantom drop. |
| 2 | **Screener chart staleness** | `screener_charts` stores whatever Screener returned at fetch time. If a corporate action fires *after* the fetch, our stored series becomes stale pre-action data with a discontinuity cliff at ex-date. No refresh trigger ties to `corporate_actions`. | **Latent.** Safe for PE percentile (price/EPS cancels), unsafe for any raw-price use of this table. |
| 3 | **No canonical adjusted-price surface** | The only adjuster lives as a local function inside `get_price_performance`. Every other consumer (screener engine, fair value, alerts, future agents) would have to reimplement. | **Architectural.** Pattern history shows consumers drift — PIDILITIND bug was exactly this. |
| 4 | **yfinance / bhavcopy convention split** | `valuation_snapshot` (yfinance, auto_adjust=True) stores adjusted data. `daily_stock_data` (NSE bhavcopy) stores raw data. Two tables, two conventions, undocumented. | **Ambiguity.** Any join or cross-table computation has a hidden adjustment mismatch. |
| 5 | **Zero split/bonus regression tests** | No integration test for any split scenario. PIDILITIND fix shipped without a regression test. | **Exposure.** Next split that breaks returns will be caught the same way — a weird number in production output. |

### 0.3 The fix: hybrid (stored column + computed helper) with two-way verification

Neither pure compute-time nor pure stored-column is right alone. Pure compute forces every consumer to know about and call the wrapper (the pattern that *already failed* — PIDILITIND). Pure stored column hides the adjustment logic and can silently drift from `corporate_actions` if the refresh hook ever misfires.

**Hybrid:** maintain both, and verify them against each other.

1. **Stored `adj_close` column on `daily_stock_data`** — the default fast path. Any consumer doing a SQL query or ResearchDataAPI call gets pre-adjusted prices by default. Matches yfinance/Bloomberg convention. O(1) reads.

2. **`ResearchDataAPI.get_adjusted_close_series(symbol, from_date, to_date)`** — the dynamic helper. Computes adjustment on the fly from raw `close` + `corporate_actions`. Used for:
   - Correctness verification (compare against `adj_close` column; alert on drift).
   - Ad-hoc "what-if this action were removed / added" scenarios.
   - Fallback if the materialization is ever wrong.

3. **Drift-detection sweep** — a scheduled test that picks N random (symbol, date) pairs, computes adjusted close via both paths, asserts they match within epsilon. Fires as part of the nightly cron. Any drift fails loud with the affected symbol + date.

This gives us the performance and ergonomics of stored adjustment *and* the correctness guarantee of live computation — each one keeping the other honest.

### 0.4 Refresh strategy: sync + nightly cron (defense in depth)

Two independent triggers — consistent with how other pipelines are structured in this codebase (scheduled crons + ad-hoc refresh).

**Sync trigger (primary):** every time `corporate_actions` gets new rows for a symbol, immediately recompute `adj_close` for that symbol in the same transaction. Hooked into `filing_client.py::fetch_corporate_actions()` → after upsert, call `recompute_adj_close(symbol)`. Sub-second cost per symbol (~4K rows × 10 actions). Ensures freshness the moment an action lands.

**Nightly cron (safety net):** new LaunchAgent plist runs after the existing daily-fetch chain. For every symbol with any `corporate_actions` history, re-run `recompute_adj_close` and compare against current `adj_close` to detect any sync misfires. Same script also runs the drift-detection sweep (0.3 step 3).

Neither alone is sufficient. Sync catches the common case (new action → immediate refresh). Nightly catches the failure modes (sync hook not firing, schema-level bugs, manual data edits, corporate_actions corrections that didn't retrigger).

### 0.5 Screener chart adjustment

`screener_charts` is a separate table with its own discontinuity problem. Three possible strategies:

- **(a)** Re-fetch from Screener after every new corporate action lands for the affected symbol. Relies on Screener's own adjustment being correct.
- **(b)** Apply adjustment at read time using `corporate_actions` (same mechanism as `daily_stock_data`).
- **(c)** Deprecate screener_charts for raw price, use only for PE/ratios (where adjustment cancels in the ratio).

**Recommended: (a) + (c) combined.** Re-fetch after corporate actions to keep the stored series clean, and in parallel document that screener_charts' price column is only for long-history context (21yr) beyond the NSE 16-yr window. Primary consumers should default to `daily_stock_data.adj_close`.

### 0.6 yfinance / bhavcopy convention

Document the convention explicitly in `flow-tracker/CLAUDE.md`:

- **`daily_stock_data`** — raw `open/high/low/close/volume` from NSE bhavcopy, plus **computed `adj_close`** from `corporate_actions`. The canonical adjusted-price surface is `adj_close`.
- **`valuation_snapshot`** — yfinance auto-adjusted point-in-time metrics. Not a time-series; adjustment concern is limited because each row is a snapshot of *then-current* state.
- **`screener_charts`** — raw when fetched; re-fetched after corporate actions. Use for long-history context; prefer `daily_stock_data.adj_close` for precision work.

Audit each consumer of price data to confirm it's reading from the canonical surface. Fix anything that isn't.

### 0.7 Test coverage additions

| Test | Scope | Mechanism |
|---|---|---|
| `test_adj_close_split.py` | PIDILITIND Sep 2025 2:1 split regression | Fixture with raw prices around ex-date; assert adj_close collapses the cliff |
| `test_adj_close_bonus.py` | Known 1:1 bonus case (e.g., Reliance Oct 2017) | Fixture; assert adj_close is continuous |
| `test_adj_close_combined.py` | Synthetic stock with split + bonus + dividend in the same year | Verify multiplier composition is correct |
| `test_adj_close_drift.py` | Runs daily — samples 50 random (symbol, date) pairs, computes both paths, asserts equality | Part of nightly cron; alert on drift |
| `test_recompute_on_new_action.py` | Sync trigger correctness | Insert a new `corporate_actions` row, assert `adj_close` reflects it before the transaction closes |
| Existing `get_price_performance` tests | Must still pass after refactor | No behavior change for splits; now-correct behavior for bonuses |

### 0.8 Implementation surface

**Schema change (`store.py`):**
```sql
ALTER TABLE daily_stock_data ADD COLUMN adj_close REAL;
ALTER TABLE daily_stock_data ADD COLUMN adj_factor REAL;  -- cumulative multiplier as-of latest action
CREATE INDEX ix_daily_stock_data_sym_date ON daily_stock_data(symbol, date);  -- if missing
```

**New methods (`store.py` + `data_api.py`):**
- `FlowStore.recompute_adj_close(symbol)` — reads raw prices + corporate_actions, writes `adj_close` + `adj_factor`.
- `ResearchDataAPI.get_adjusted_close_series(symbol, from_date, to_date)` — dynamic compute, independent of stored column.
- `ResearchDataAPI.verify_adj_close_drift(symbol, n_samples=20)` — randomly compares stored vs computed.

**Refactor (`data_api.py`):**
- `get_price_performance` reads `adj_close` directly; remove local `split_adjustment`.
- Any other consumer using raw `close` for multi-period returns audited and switched to `adj_close`.

**Client hook (`filing_client.py`):**
- After `fetch_corporate_actions()` upserts new rows for symbol X, call `FlowStore.recompute_adj_close(X)` in the same transaction.

**Cron (`scripts/`):**
- New `nightly-adj-close.sh` LaunchAgent — iterates symbols with `corporate_actions` history, recomputes, runs drift sweep.
- Chains after existing daily-fetch (same pattern as `alert-check.sh`).

**Backfill script:**
- One-time run on Sprint 0 Day 1: populate `adj_close` for the full 3,126-symbol universe. Expected runtime: ~5-10 minutes.

**Documentation (`flow-tracker/CLAUDE.md`):**
- Add "Price Adjustment Convention" section per 0.6.

### 0.9 Effort

| Task | Effort |
|---|---|
| Schema migration + `adj_close` / `adj_factor` backfill | 0.5 day |
| `recompute_adj_close` + `get_adjusted_close_series` methods (splits + bonuses, both paths) | 0.5 day |
| Refactor `get_price_performance` + audit + fix other consumers | 0.5 day |
| `filing_client.py` sync hook + nightly cron + LaunchAgent plist | 0.5 day |
| Screener chart re-fetch trigger + conventions doc | 0.25 day |
| Test suite (6 tests per 0.7) | 0.5 day |
| Verification sweep: run against production DB, confirm no regressions | 0.25 day |
| **Total** | **~3 days** |

### 0.10 Exit criteria (don't start Sprint 1 until these pass)

- [x] `adj_close` column populated for every `daily_stock_data` row. (3,743,820/3,743,820 rows, 0 NULLs)
- [x] Drift sweep returns zero mismatches across 200 random (symbol, date) samples.
- [x] 23 new tests pass (up from initial 6 after edge-case expansion). Full fast suite 2,199 passed / 0 failed / 3 skipped (2 pre-existing flakes on main).
- [x] PIDILITIND Sep 2025: 2024-01-01 adj=1348.75 (close/2), ex-date 2025-09-25 adj=1495.70 (factor 1.0) — proof-of-fix.
- [x] Reliance Oct 2017 + Oct 2024 bonuses: cumulative factor 4.0 pre-2017 (2x × 2x). Returns computable correctly via `adj_close`.
- [x] Nightly cron: `scripts/nightly-adj-close.sh` + `scripts/plists/com.flowtracker.nightly-adj-close.plist` template checked in; install path documented in plist comment.
- [x] `CLAUDE.md` adjustment convention section merged.
- [x] Sync hook verified: `upsert_corporate_actions` auto-triggers recompute for splits/bonuses (dividends skip; batch opt-out via `recompute_adj_close=False`).
- [x] Screener price chart invalidation: `invalidate_screener_price_charts` deletes cached stale price rows on split/bonus upsert (PE chart untouched — ratio-invariant).
- [x] BAJFINANCE compound action (2025-06-16: 1:2 split × 1:4 bonus = 10x) handled; 1Y return now +0.16% (was -49.92% pre-fix).
- [x] BAJFINANCE 2016 phantom cliff (NSE pre-adjusted historical data) rejected by price-cliff verification.
- [x] ANGELONE / BEML / ADANIPOWER / COFORGE NULL-multiplier actions: inferred from prev_close/close when cliff present.
- [x] GESHIP-style reverse split (multiplier < 1) handled with direction-aware tolerance.

### 0.11 Out-of-scope (deferred to Sprint 2+)

These edge cases surfaced during Sprint 0 spot-checks but are explicitly out of scope for the split/bonus adjustment layer. They will need dedicated treatment before Historical Analog can produce maximally clean 10-year returns.

| Issue | Evidence | Why out of scope for Sprint 0 | Sprint 2+ approach |
|---|---|---|---|
| **Demergers / spinoffs** | TATAMOTORS 2025-10-14: pre-demerger ₹660.75 → post ₹395.45 (CV-only), 40.2% phantom cliff. New ticker TMPV for PV entity listed 2025-10-24. Zero rows in `corporate_actions` for TATAMOTORS. 8 `spinoff` rows exist in table but are not honored by adj logic. | Demergers need different math: pre-price must be pro-rated by the *ratio of retained-entity value to combined pre-demerger value*. Listing price of the spun-off entity (TMPV) needs to feed into the adjustment — cross-symbol dependency. | Extend `get_split_bonus_actions` to include `spinoff` type; fetch spun-off ticker's listing day close; adj_factor = pre_close / (pre_close − spinoff_value). Requires `filing_client` to populate spinoff rows with linked ticker + listing date. |
| **Missing corporate_actions (data pipeline gap)** | 14+ symbols with >50% unexplained recent cliffs not in `corporate_actions`: LICMFGOLD (99% drop 2026-03-06), BESTAGRO (93% drop), DELPHIFX, PAVNAIND, KAMDHENU, GROWWSLVR, ROLEXRINGS, WEBELSOLAR, ABINFRA, CONS and more. Some are MF/ETFs, some are real equity splits we never captured. | `filing_client.py` / BSE fetch didn't capture the action. Sprint 0 can't infer from cliff alone (risk of mis-applying real crash days). | Broaden `filing_client` BSE fetch coverage; add a reconciliation pass that flags symbol-dates with extreme cliffs absent from `corporate_actions` for manual review. |
| **Rights issues** | 0 rows currently (rights not in our `action_type` vocabulary). Events like RCOM rights issues cause real value dilution. | Rights math requires subscription price + new-share count. Different economic model from splits. | Separate `rights` action type; adj_factor = (pre_price + subscription_price × new_shares_per_old) / (pre_price × (1 + new_shares_per_old)). |
| **Buybacks** | 12 buyback rows in `corporate_actions` | Buybacks don't create a price cliff (shares just get retired). No adj_close impact. | No adjustment needed; already correctly ignored. |
| **Symbol changes / mergers** | TATAMTRDVR merged into TATAMOTORS 2024-08-29 (DVR reunification). Historical TATAMTRDVR data becomes orphan. | Cross-symbol data linking — separate problem class. | Add `symbol_alias` table mapping pre-merger ticker → post-merger, plus merge-date price adjustment factor. |
| **Weekend/holiday ex_date** | COHANCE 2020-09-25 (1 case found) — ex_date on Friday, no daily_stock_data row. Action applied without cliff verification (passes through). | Low incidence; passes through unharmed when multiplier is correct. | Check *next* trading day's close/prev_close if ex_date has no row. |
| **Pre-data-range actions** | GESHIP 2006-10-16 reverse split (before our 2010 data starts). No daily_stock_data to verify against. Currently correctly skipped — adj_factor = 1 for all rows. | Correct behavior: data already in post-action basis. | No action needed; document convention. |

**Sprint 2 priority order for these (when Sprint 1 + Historical Analog ships):**
1. **Demerger/spinoff** (HIGHEST): TATAMOTORS, Reliance Jio Fin (2023), L&T Finance (2017), etc. — these distort long-horizon analogs heavily.
2. **Missing corporate_actions gap** (MEDIUM): data-pipeline enhancement in `filing_client.py` to catch BSE/NSE events our current fetchers miss.
3. **Rights issues** (LOW): less impactful on multi-year returns but needed for completeness.
4. **Symbol changes** (LOW): edge case, typically manageable with manual mapping.

---

## Part 1 — Historical Analog Agent

### 1.1 What it does

Given a stock + current date, the agent:

1. Computes a **feature vector** for the target stock's current state (PE percentile, ROCE, ROCE 3yr change, FII delta QoQ, MF delta QoQ, promoter pledge, price-to-SMA200, delivery %, sector, mcap bucket).
2. Retrieves **K nearest historical analogs** from a precomputed vector table — any (symbol × quarter_end) point in the last 10 years whose feature vector matches the target within a tolerance.
3. For each analog, computes **forward returns** at 3m/6m/12m horizons (absolute, vs sector, vs Nifty), plus *what happened next qualitatively* (did ROCE recover? Did MFs keep accumulating? Was there a re-rating or compression?).
4. Writes a briefing that synthesis can use to *empirically calibrate* bull/base/bear probabilities — "in 42 similar setups over 10 years, 62% recovered within 12m, median return +18%, 4 blew up (-40%+), 1 still going sideways."

This is RAG-over-history, not a new data source. The power comes from having 16 years of depth across 3,100 symbols already in `FlowStore`.

### 1.2 Data coverage we already have

From the inventory pass:

| Data | Table | Depth | Coverage | Ready? |
|---|---|---|---|---|
| Daily OHLCV + delivery | `daily_stock_data` | 16yr | 3,126 symbols | ✅ |
| Quarterly shareholding (promoter/FII/MF) | `shareholding` | 16yr | 533 symbols | ✅ |
| Screener PE + price history | `screener_charts` | 21yr | broad | ✅ |
| Quarterly financials | `quarterly_results` | 10yr | 500 symbols | ✅ |
| Annual financials | `annual_financials` | 24yr | 500+ | ✅ |
| Insider transactions | `insider_transactions` | 16yr | listed universe | ✅ |
| Promoter pledge | `promoter_pledge` | 16yr | 533 symbols | ✅ |
| Corporate actions | `corporate_actions` | 30yr | all | ✅ |

**Gaps that limit analog richness:**

1. **No stock-level daily FII flow.** `daily_flows` is index-aggregate only. We have to interpolate daily FII proxies from quarterly `shareholding` deltas. Acceptable for MVP — quarterly granularity is fine for "FII exit of ~X pp" style analogs.
2. **No historical index membership.** Can't cleanly cohort "Nifty 50 stocks in 2018." Mitigation: use mcap bucket from `daily_stock_data` × shares outstanding instead. Good enough.
3. **Only 3 weeks of bulk deals.** Block/bulk deal patterns unavailable for analogs. Deferred — doable as a later backfill via NSE SAST archive.
4. **Pre-2016 quarterly earnings missing.** Quarterly financials start 2016. Annual goes to 2002. Use annual for longer analogs, quarterly for tighter ones. Accept the limit.

No blocking gaps. MVP ships on current data.

### 1.3 Feature vector (what makes two situations "similar")

The match is over a **fixed-size numeric vector** computed as-of a quarter-end. Per-stock, per-quarter, one row.

| Feature | Source | Normalization |
|---|---|---|
| `pe_percentile_10y` | `screener_charts` (pe) | percentile of own 10yr PE history as of quarter-end |
| `pe_trailing` | `valuation_snapshot` / `screener_charts` | raw value |
| `roce_current` | `annual_financials` (latest prior FY) | raw value (%) |
| `roce_3yr_delta` | `annual_financials` (current − 3yr ago) | raw value (% points) |
| `revenue_cagr_3yr` | `quarterly_results` rolled to TTM | % |
| `opm_trend` | `quarterly_results` (last 8Q slope) | % per quarter |
| `promoter_pct` | `shareholding` | raw % |
| `fii_pct` | `shareholding` | raw % |
| `fii_delta_2q` | `shareholding` (current − 2Q ago) | % points |
| `mf_pct` | `shareholding` | raw % |
| `mf_delta_2q` | `shareholding` | % points |
| `pledge_pct` | `promoter_pledge` | raw % |
| `price_vs_sma200` | `daily_stock_data` | ratio |
| `delivery_pct_6m` | `daily_stock_data` (6m avg) | raw % |
| `rsi_14` | `daily_stock_data` | raw |
| `industry_id` | `index_constituents.industry` | categorical |
| `mcap_bucket` | computed (largecap/midcap/smallcap) | categorical |

**16 features total.** Mostly continuous, two categorical. All computable from existing tables via a single materialization pass.

### 1.4 Algorithm: hybrid retrieval + LLM narration

Pure-LLM analog search hallucinates. Pure-deterministic k-NN is brittle (wrong weights pick wrong analogs). Right answer is **retrieval + narration**:

**Step 1 — Deterministic retrieval (Python, no LLM):**

- Precompute `historical_states` table: one row per (symbol, quarter_end) × 10 years × ~500 symbols ≈ **20,000 rows**. Cheap, rebuilds in minutes.
- Given target's current feature vector, compute distance to every row using:
  - **Z-scored Euclidean** on continuous features (each feature normalized by its universe-wide stdev).
  - **Hard filters** on categoricals: same industry_id OR (same mcap_bucket AND related industry_id). Skip same-stock rows within 2 years of target date (data leakage).
- Return top-K candidates (K=20).

**Step 2 — Enrich with forward returns (Python, no LLM):**

For each candidate, compute:
- 3m / 6m / 12m forward absolute return
- 3m / 6m / 12m forward excess return vs sector median (from `index_constituents` peers on that date)
- 3m / 6m / 12m forward excess return vs Nifty (use `daily_stock_data` for NIFTY50 symbol as proxy)
- "Setup evolution" — quarterly shareholding + PE over the next 4 quarters (did FII keep selling? Did PE de-rate further?)
- "Outcome label" — coarse bucket: `recovered` (+20%+ in 12m), `sideways` (-10% to +20%), `blew_up` (-20%+ with sustained damage).

**Step 3 — LLM narration (agent call):**

The agent receives the top-20 analogs as structured JSON + the target's feature vector. Its job:

1. Cluster the analogs qualitatively (not just by distance — by *story*): "8 were institutional-handoff setups that recovered, 6 were value traps where ROCE kept compressing, 4 were cyclicals that needed a macro turn, 2 were idiosyncratic (frauds, one-off events)."
2. Pick the 3–5 **most behaviorally comparable** analogs, defending the choice (why this specific analog, not another).
3. Quantify the base rate: "42 analogs, 62% recovered 12m, median +18%, 10th percentile −22%."
4. Identify the **tightest differentiator** — "the 4 blow-ups all had pledge >15%; target has 0% pledge. Downside skew meaningfully lower."
5. Emit a structured briefing synthesis can read.

### 1.5 Briefing schema (what lands in `_SYNTHESIS_FIELDS`)

```json
{
  "agent": "historical_analog",
  "symbol": "INOXINDIA",
  "signal": "mixed",
  "confidence": 0.65,
  "as_of_date": "2026-04-20",
  "target_vector": { /* 16 features */ },
  "analog_count": 42,
  "analog_lookback_years": 10,

  "base_rates": {
    "recovery_12m_pct": 62,
    "median_return_12m_pct": 18,
    "p10_return_12m_pct": -22,
    "p90_return_12m_pct": 54,
    "blow_up_rate_pct": 10
  },

  "cluster_summary": [
    {"label": "institutional_handoff_recovery", "count": 18, "median_12m": 26},
    {"label": "value_trap_roce_compression", "count": 12, "median_12m": -8},
    {"label": "capex_cycle_bottoming", "count": 8, "median_12m": 34}
  ],

  "top_analogs": [
    {
      "symbol": "EXAMPLE", "as_of": "2019-03-31",
      "distance_score": 0.82,
      "forward_3m_pct": -4, "forward_12m_pct": 38,
      "outcome_label": "recovered",
      "narrative": "Q4 FY19: high ROCE + commissioning-phase capex, 2-analyst coverage..."
    } /* top 5 */
  ],

  "differentiators": [
    "Target pledge = 0%; 4 of 4 blow-ups had pledge >15% — downside tail materially thinner",
    "Target has zero debt; 7 of 12 value-traps were debt-funded ROCE deteriorations"
  ],

  "open_questions": [
    "Target mcap ₹14,500 Cr is on the small end of analog cohort (median ₹22,000 Cr); smallcap liquidity effects may amplify both tails"
  ]
}
```

**Whitelist additions to `_SYNTHESIS_FIELDS`** (`agent.py:194-232`): `base_rates`, `cluster_summary`, `top_analogs`, `differentiators`, `analog_count`, `analog_lookback_years`.

### 1.6 Implementation surface

**New files:**

| File | Purpose |
|---|---|
| `flowtracker/research/analog_builder.py` | Feature-vector computation + `historical_states` materialization + k-NN retrieval + forward-return computation |
| `flowtracker/research/sector_skills/_shared_analog.md` | (optional) shared analog rules, deferred |
| `tests/unit/test_analog_builder.py` | Feature vector, distance, forward-return correctness |
| `tests/unit/test_historical_analog_agent.py` | Prompt registration, tool wiring, briefing schema |

**Schema additions (`store.py`):**

```sql
CREATE TABLE historical_states (
  symbol TEXT, quarter_end DATE,
  pe_percentile_10y REAL, pe_trailing REAL,
  roce_current REAL, roce_3yr_delta REAL,
  revenue_cagr_3yr REAL, opm_trend REAL,
  promoter_pct REAL, fii_pct REAL, fii_delta_2q REAL,
  mf_pct REAL, mf_delta_2q REAL, pledge_pct REAL,
  price_vs_sma200 REAL, delivery_pct_6m REAL, rsi_14 REAL,
  industry_id TEXT, mcap_bucket TEXT,
  PRIMARY KEY (symbol, quarter_end)
);
CREATE INDEX ix_historical_states_ind ON historical_states(industry_id, mcap_bucket);

CREATE TABLE analog_forward_returns (
  symbol TEXT, as_of_date DATE,
  return_3m_pct REAL, return_6m_pct REAL, return_12m_pct REAL,
  excess_return_3m_vs_sector REAL, excess_return_12m_vs_sector REAL,
  excess_return_12m_vs_nifty REAL,
  outcome_label TEXT,
  PRIMARY KEY (symbol, as_of_date)
);
```

**Tools to add (`research/tools.py`):**

```python
@tool
async def get_historical_analogs(
    symbol: str, k: int = 20, lookback_years: int = 10
) -> dict:
    """Retrieve top-K historical analogs for the current state of `symbol`.
    Returns feature-vector match + forward returns + outcome labels."""

@tool
async def get_analog_cohort_stats(
    symbol: str, feature_filter: dict | None = None
) -> dict:
    """Aggregate base rates over the full analog cohort. Optional filters
    (e.g., only industry match, only same mcap bucket) narrow the cohort."""

@tool
async def get_setup_feature_vector(symbol: str) -> dict:
    """Return the 16-feature vector for the target stock as-of today —
    so the agent can inspect and narrate the setup itself."""
```

**Three tools, all read-only, all backed by `analog_builder.py`.**

**Agent registration (`research/agent.py`):**

- `DEFAULT_MODELS["historical_analog"] = "claude-sonnet-4-6"` — sonnet is enough; this is structured pattern matching not deep reasoning.
- `DEFAULT_EFFORT["historical_analog"] = "medium"`
- `AGENT_TIERS["historical_analog"] = 3` — supplementary. Missing doesn't break the verdict.
- `AGENT_MAX_TURNS["historical_analog"] = 20`
- `AGENT_MAX_BUDGET["historical_analog"] = 0.50`
- `AGENT_TOOLS["historical_analog"] = HISTORICAL_ANALOG_TOOLS_V2`
- Update `agent_names` list in `run_all_agents()`.

**Prompt (`research/prompts.py`):**

Add `SYSTEM_PROMPT_HISTORICAL_ANALOG` + `INSTRUCTIONS_HISTORICAL_ANALOG` entries to `AGENT_PROMPTS_V2`. Persona: "senior quant PM who thinks in base rates and cohorts, not narratives." Key rules:

- **Never invent analogs.** Only use analogs returned by `get_historical_analogs` / `get_analog_cohort_stats`.
- **Quantify, don't narrate vague comparisons.** Every claim paired with a count and a horizon.
- **Differentiators matter more than matches.** The most valuable insight is *where the target diverges from the cohort* — that's where the base rate has to be adjusted.
- **Flag regime breaks.** If analogs are from pre-2020 pre-rate-hike regime and current is different, note it.

**Refresh hook (`research/refresh.py`):**

The `historical_states` table needs to be **materialized or updated** when a new quarter's shareholding lands. Two options:

- **Option A — lazy:** materialize on-demand per symbol on first agent call; cache in `historical_states` table. First call slow (~30s), subsequent cached. Simple.
- **Option B — batch cron:** weekly job that refreshes the entire table after each shareholding refresh. Cleaner. ~10min weekly cost.

**Recommend Option A for MVP**, Option B if we scale to daily use across many symbols.

**CLI (`research_commands.py`):**

Add `"historical_analog"` to `VALID_AGENTS` set. `flowtrack research run historical_analog -s INOXINDIA` Just Works.

### 1.7 MVP scope (Phase 1)

Ship the narrowest version that's useful:

- **Universe:** Nifty 500 symbols only (~500), not all 3,126. Keeps `historical_states` at ~20K rows, cheap.
- **Feature vector:** 16 features as listed. No textual matching yet.
- **Horizons:** 3m / 6m / 12m forward returns.
- **K = 20** top analogs, LLM narrates top 5.
- **No cross-sector analogs** — hard-filter to same/adjacent industry.

**Deferred to Phase 2:**

- Cross-sector analogs (useful for regime analogs — "what did high-ROCE capex-commissioning names do in the 2018 slowdown, across sectors?").
- Textual-feature enrichment (concall sentiment vectors, AR language analogs).
- Expanding to all 3,126 symbols.
- Monthly cohort updates via cron.
- Back-adjusted prices for splits/bonuses (currently `daily_stock_data` is unadjusted for actions — forward-return computation must post-adjust using `corporate_actions`).

### 1.8 Risks

| Risk | Mitigation |
|---|---|
| **Regime break invalidates analogs** (2010-2020 pre-hike vs 2022+ post-hike) | Agent prompt explicitly flags regime mismatch; `as_of_date` metadata lets LLM see cohort distribution over time |
| **Small-sample analog cohorts** (some setups have only 3-5 matches) | Report N; if N<10, explicitly say "thin cohort — low confidence"; agent prompt mandates this |
| **Feature-vector bias** (weights poorly chosen → wrong analogs) | Z-score normalization gives every feature equal weight by default; tune via autoeval |
| **Data leakage** (future info leaks into "historical" state) | `historical_states` computation must use only info available as-of `quarter_end`; explicit unit test |
| **Price adjustment bug** (unadjusted prices inflate/deflate returns) | Must post-adjust forward-return computation using `corporate_actions` table; unit test with known splits |

### 1.9 Estimated effort

| Task | Effort |
|---|---|
| `analog_builder.py` (feature vectors, k-NN, forward returns, price adjustment) | 2 days |
| `historical_states` / `analog_forward_returns` tables + store methods | 0.5 day |
| 3 MCP tools + ResearchDataAPI wiring | 0.5 day |
| Agent prompt + sector skills (if any) | 0.5 day |
| Integration (agent.py dicts, CLI, tests) | 0.5 day |
| Autoeval sector sweep + prompt tune | 1 day |
| **Total** | **~5 days** |

---

## Part 1.5 — Historical Analog hardening (post-Sprint-1 follow-up)

**Status:** Pending. Surfaced by smoke-testing Sprint 1 on TMPV (Tata Motors Passenger Vehicles — newly-listed demerger ticker with 125 trading days of history). Gemini review on 2026-04-21 flagged three CRITICAL gaps and two HIGH. Scope is ~6 hours, targeted as a single follow-up PR before Sprint 2.

### 1.5.1 Trigger case — what TMPV exposed

Running `get_analog_cohort_stats('TMPV', k=30)` produced superficially reasonable output that masked three problems:

1. **23 rows, 2 unique symbols.** Hard industry (`Passenger Cars & Utility Vehicles`) + mcap (`largecap`) filter starved the cohort — only MARUTI + FORCEMOT across 23 quarter-ends. M&M and Hyundai are in different industry codes. Reporting N=23 is technically accurate but statistically misleading.
2. **Informative N ≈ 3.** 20 of 23 analogs are 2025-Q2 or later, so their 12m forward window is still in the future. `cohort_stats` aggregates only outcome_label-populated rows (3 analogs), but the agent prompt has no discipline forcing it to cite the *informative* N instead of the gross retrieval count. p10/p90 on N=3 is mathematically meaningless.
3. **Retrospective feature data.** TMPV listed 2025-10-24. Yet `roce_3yr_delta = +13.48` surfaces because Screener/yfinance backfilled PV-segment accounting to pre-listing quarter-ends under the TMPV ticker. The agent has no way to distinguish this from a genuine 3-year ROCE trajectory — it treats pre-listing accounting as a lived market setup.

### 1.5.2 Fix list (Gemini-prioritized)

**CRITICAL:**

| # | Fix | File(s) | One-liner |
|---|---|---|---|
| 1 | **Similarity-ring fallback** when `unique_symbols < 5` → widen to sector (or cross-mcap) | `analog_builder.py::retrieve_top_k_analogs` | Pass-1 strict filter; if unique_symbols(pass_1) < 5, pass-2 with relaxed industry or mcap; tag `relaxation_level`. |
| 2 | **Surface `informative_N` vs gross N** + prompt constraint "cite only informative_N for base rates" | `analog_builder.py::cohort_stats`, `prompts.py::HISTORICAL_ANALOG_INSTRUCTIONS_V2` | Return `informative_N_{3m,6m,12m}` + `unique_symbols`; prompt Section 2 forces informative_N as the N in base-rate citations. |
| 3 | **Retrospective-data flag** `is_backfilled` exposed in the feature vector | `analog_builder.py::compute_feature_vector` + prompt | Compute `is_backfilled = (listed_days < 1000 AND roce_3yr_delta is not None)` from `MIN(date) FROM daily_stock_data` vs today; agent's Section 7 must cite if True. |

**HIGH:**

| # | Fix | File(s) | One-liner |
|---|---|---|---|
| 4 | **Missing-feature imputation** using sector-median in distance calc | `analog_builder.py::feature_distance` | When target OR candidate has NULL, impute cohort/sector median for that feature before z-score — distance currently skips the dim, which biases toward partial-match candidates. |
| 5 | **Dynamic base-rate horizons**: compute 3m/6m stats in parallel to 12m when `informative_N_12m < 5` | `analog_builder.py::cohort_stats` | Return stats dict keyed by horizon; prompt picks the shortest horizon with informative_N ≥ 5. |
| 6 | **Toxic-intersection prompt clause** — explicitly evaluate non-linear feature combos (extreme RSI + margin contraction + MF outflow = classic "crowded into deterioration" setup) | `prompts.py::HISTORICAL_ANALOG_INSTRUCTIONS_V2` Step 5 | Add instruction: "Before emitting clusters, evaluate whether the target exhibits a toxic intersection (RSI > 80 + opm_trend < −1 + mf_delta_2q < 0) and flag it even if the cohort cluster stats don't isolate it." |

**MEDIUM:**

| # | Fix | File(s) | One-liner |
|---|---|---|---|
| 7 | **Symmetric time-skew detection** — flag when >70% informative cohort is post-2024, not just pre-2020 | `prompts.py` + `cohort_stats` metadata | Prompt G5 currently catches pre-2020 clustering; also catch >70% post-2024 as "recency regime lock-in." |
| 8 | **Unique-symbol count as first-class stat** in briefing JSON | `briefing schema in prompts.py` | Already via fix #2, but surface as its own top-level field — reviewers should see symbol concentration at a glance. |

**LOW:**

| # | Fix | File(s) | One-liner |
|---|---|---|---|
| 9 | **Small-sample loudness controls**: if `informative_N < 5`, suppress p10/p90 and emit individual outcomes instead | `prompts.py` Section 2 | Distribution thresholds on N=3 are fabricated precision; listing the 3 actual outcomes is more honest. |

### 1.5.3 What Gemini explicitly DISMISSED (keep-list)

- Auto-specific features (dealer inventory, order book) — sector-knowledge leak, violates G8 sector-agnostic rule.
- Regime snapshot at analog timestamp (pulling macro anchors into each row) — over-engineering.
- p25/p75 differentiator analysis — current binary tail inspection is sufficient.

### 1.5.4 Effort

| Task | Effort |
|---|---|
| Fix #1 similarity-ring fallback + tests | 2h |
| Fix #2 informative_N + unique_symbols + prompt update | 1h |
| Fix #3 is_backfilled flag + listed_days derivation | 1h |
| Fixes #4–6 (imputation, multi-horizon, toxic-intersection) | 2h |
| Fixes #7–9 (MEDIUM/LOW polish) | 1h |
| Autoeval re-sweep to confirm no regressions | 1h |
| **Total** | **~8h (one day)** |

### 1.5.5 Exit criteria

- [ ] TMPV smoke produces `unique_symbols ≥ 5` or a `relaxation_level` flag.
- [ ] TMPV output shows `informative_N_12m: 3` + `informative_N_3m: ~20` — agent reports 3m base rates with informative_N, not gross N.
- [ ] TMPV output includes `is_backfilled: true` flag with 125 `listed_days`; agent's Section 7 cites it.
- [ ] All 8 Sprint 1 unit tests still pass + 3-4 new tests for fixes #1/#2/#3.
- [ ] Autoeval sweep on 2-3 sectors shows no grade regression from Sprint 1 baseline.

---

## Part 2 — F&O Positioning Agent

### 2.1 What it does

Given an F&O-eligible stock, the agent reasons about:

1. **Positioning extremes.** OI concentration in specific strikes, OI build-up direction, historical OI percentile.
2. **Hedging demand.** Put-call ratio, option chain skew (call-side OI vs put-side OI), implied-vol level vs history (if we can build IV history).
3. **Basis & roll-over.** Spot-futures basis, basis trajectory into expiry, roll-over % from front to next month.
4. **FII derivative positioning.** Daily FII long/short in stock futures, index futures — captured from the NSE participant-wise OI report, which the current FII/DII client doesn't parse.
5. **Cross-reference with cash positioning.** E.g., FII reducing cash holdings (quarterly shareholding) *while* adding index-short positions (daily derivative flow) = genuine bearish signal, not just rotation.

Output: positioning signal (bullish/bearish/crowded-long/crowded-short/neutral) + specific levels (OI-based support/resistance strikes), into the briefing.

### 2.2 Universe

**F&O-eligible stocks only** — ~180-200 at any given time. NSE publishes the eligibility list. Adjusts quarterly.

**Implication:** Not every specialist run gets an F&O briefing. For non-F&O stocks, agent returns `status=empty` gracefully, synthesis treats it as a missing tier-3 agent (confidence cap 85%).

**Matters for universe:**
- All Nifty 50 stocks ✅
- Most Nifty Next 50 ✅
- Many midcaps (e.g., CMSINFO likely, INOXINDIA likely — both Nifty 500) — check individually
- Smallcaps: mostly excluded ❌

### 2.3 Data ingestion (new pipeline)

**We currently have ZERO F&O tables or clients.** This agent requires real ingestion work before any agent lifting can happen.

**Sources (all free, all NSE):**

| Endpoint | Purpose | Update frequency |
|---|---|---|
| `nsearchives.nseindia.com/products/content/sec_bhavdata_fo_full_{DDMMYYYY}.csv` | Per-contract daily EOD: OI, volume, settlement, IV (if provided) | Daily 5-6pm IST |
| `nseindia.com/api/reportdata?report=derive` (cookie preflight) | Participant-wise OI — FII/DII/Prop/Client long+short in index+stock futures | Daily post-market |
| `nseindia.com/api/option-chain?symbol=X&expiryDate=DD-MMM-YYYY` (cookie preflight) | Live option chain snapshot per stock | On-demand (no history unless we snapshot) |
| `nseindia.com/products-services/equity-derivatives-eligibility` | F&O eligible stock list | Quarterly |

**Cookie preflight pattern:** identical to existing `client.py` (NSE FII/DII). Reuse.

### 2.4 Schema additions (`store.py`)

```sql
-- Per-contract EOD snapshot from F&O bhavcopy
CREATE TABLE fno_contracts (
  trade_date DATE, symbol TEXT, instrument TEXT,  -- FUTSTK / OPTSTK / FUTIDX / OPTIDX
  expiry_date DATE, strike REAL NULL, option_type TEXT NULL,  -- CE/PE/NULL
  open REAL, high REAL, low REAL, close REAL, settle_price REAL,
  contracts_traded INTEGER, turnover_cr REAL,
  open_interest INTEGER, change_in_oi INTEGER,
  implied_volatility REAL NULL,
  PRIMARY KEY (trade_date, symbol, instrument, expiry_date, strike, option_type)
);
CREATE INDEX ix_fno_symbol_date ON fno_contracts(symbol, trade_date);

-- Participant-wise OI from /api/reportdata?report=derive
CREATE TABLE fno_participant_oi (
  trade_date DATE, participant TEXT,  -- FII / DII / Pro / Client
  instrument_category TEXT,           -- idx_fut / idx_opt_ce / idx_opt_pe / stk_fut / stk_opt_ce / stk_opt_pe
  long_oi INTEGER, short_oi INTEGER,
  long_turnover_cr REAL, short_turnover_cr REAL,
  PRIMARY KEY (trade_date, participant, instrument_category)
);

-- Snapshot of F&O-eligible symbols (quarterly)
CREATE TABLE fno_universe (
  symbol TEXT PRIMARY KEY, eligible_since DATE, last_verified DATE
);
```

**~10 store methods:** `upsert_fno_contracts`, `get_fno_oi_history(symbol, days=90)`, `get_pcr(symbol, as_of)`, `get_basis(symbol, as_of)`, `get_oi_percentile(symbol)`, `get_fii_deriv_positioning(as_of)`, `get_fno_eligible_stocks()`, etc.

### 2.5 Client (`flowtracker/fno_client.py`)

New file. Four fetchers:

```python
class FnoClient:
    def fetch_fno_bhavcopy(date: date) -> list[FnoContract]: ...
    def fetch_participant_oi(date: date) -> list[FnoParticipantOi]: ...
    def fetch_option_chain(symbol: str, expiry: date) -> OptionChain: ...
    def fetch_eligible_universe() -> list[str]: ...
```

Reuse `client.py`'s cookie-preflight helper. Rate: 1-2 req/sec empirical.

**Initial backfill:** NSE keeps bhavcopy archives indefinitely. Backfill ~2 years (~500 trading days × ~200 stocks × ~10 contracts each = ~1M rows). One-time overnight run. **Total disk: ~200MB**. Manageable.

**Participant OI:** only has daily aggregate, no per-stock. Ingest daily going forward; historical backfill depends on NSE archive availability (typically 1 year).

### 2.6 Cron wiring

Two new cron entries in `scripts/`:

| Script | Schedule | Duty |
|---|---|---|
| `daily-fno.sh` | Weekdays 6pm IST (after bhavcopy lands) | Fetch F&O bhavcopy + participant OI, upsert |
| `quarterly-fno-universe.sh` | 1st of Feb/May/Aug/Nov | Refresh F&O eligible universe |

### 2.7 Tools to add (`research/tools.py`)

```python
@tool
async def get_fno_positioning(symbol: str) -> dict:
    """Return current F&O positioning summary: futures OI trend, basis,
    PCR, option chain concentration, FII derivative stance. None if
    symbol not F&O eligible."""

@tool
async def get_oi_history(symbol: str, days: int = 90) -> list[dict]:
    """Daily OI + volume history for the symbol's front-month futures."""

@tool
async def get_option_chain_concentration(symbol: str) -> dict:
    """Strike-wise OI concentration — key support/resistance strikes, max pain."""

@tool
async def get_fii_derivative_flow(days: int = 30) -> list[dict]:
    """Market-wide FII derivative positioning over N days — index fut long/short,
    index options CE/PE, stock futures. Cross-references with daily FII/DII cash flow."""

@tool
async def get_futures_basis(symbol: str, days: int = 30) -> list[dict]:
    """Spot-futures basis trajectory over N days. Negative basis near expiry
    signals distress/forced selling; positive spike signals aggressive buying."""
```

**5 tools,** all scoped to F&O data. All return `None` / empty gracefully if symbol not F&O-eligible.

### 2.8 Briefing schema

```json
{
  "agent": "fo_positioning",
  "symbol": "INOXINDIA",
  "signal": "neutral",
  "confidence": 0.60,
  "fno_eligible": true,
  "as_of_date": "2026-04-20",

  "futures_positioning": {
    "current_oi": 12_450_000, "oi_percentile_90d": 74,
    "oi_trend_20d": "building",
    "basis_pct": -0.3, "basis_vs_cost_of_carry": "inverted",
    "open_interest_change_5d_pct": 18
  },

  "options_positioning": {
    "pcr_oi": 0.68, "pcr_oi_percentile": 42,
    "max_pain_strike": 1450, "atm_iv": 34.5,
    "call_oi_concentration": {"strike": 1500, "oi": 3_200_000, "pct_of_total_ce": 28},
    "put_oi_concentration": {"strike": 1400, "oi": 2_100_000, "pct_of_total_pe": 22}
  },

  "fii_derivative_stance": {
    "index_fut_net_long_pct": 42, "index_fut_net_long_trend": "falling",
    "stock_fut_net_long_pct": 58,
    "cash_vs_deriv_divergence": "fii reducing cash, adding index shorts — aligned bearish"
  },

  "interpretation": [
    "OI building 18% in 5 days at RSI 90 = long-crowding, often precedes unwinding",
    "Basis −0.3% with cost-of-carry ~0.5% = futures trading at discount, mild bearish pressure",
    "Max pain ₹1,450 vs spot ₹1,491 = option writers net-short; pull toward ₹1,450 into expiry likely"
  ],

  "key_levels": {
    "oi_support": 1400, "oi_resistance": 1500,
    "expiry_target": 1450
  },

  "open_questions": []
}
```

**Whitelist additions to `_SYNTHESIS_FIELDS`**: `futures_positioning`, `options_positioning`, `fii_derivative_stance`, `interpretation`, `key_levels`, `fno_eligible`.

### 2.9 Agent registration

Same pattern as Historical Analog — 6 dicts + tools list + prompt + CLI. Assignments:

- **Tier:** 3 (supplementary — not every stock has F&O)
- **Model:** sonnet 4.6 (fast, structured reasoning — no deep creativity needed)
- **Effort:** medium
- **Max turns:** 15, **Max budget:** $0.40
- **Empty-state handling:** if `fno_eligible=false`, agent returns briefing with `status=empty` and no tool calls. Synthesis treats as tier-3 missing, no confidence cap.

### 2.10 MVP scope (Phase 1)

Ship the narrowest useful version:

- **Ingestion:** daily F&O bhavcopy + participant OI starting today. Backfill last 90 trading days only (enough to compute percentiles and trends).
- **Universe:** F&O-eligible list, refreshed manually for MVP.
- **Signals:** futures OI trend + basis + PCR + max pain + FII derivative index positioning. **No IV surface, no Greeks** — we only have snapshot IV from bhavcopy (if provided there) or option chain, not historical.
- **No cross-stock derivative flow** (no "which other stocks are FIIs piling into").

**Deferred to Phase 2:**

- IV history surface (requires daily option chain snapshots accumulated over months).
- Cross-stock derivative positioning cohort analysis.
- Full 2-year backfill.
- Options-strategy suggestion (never — out of scope for research agent).

### 2.11 Risks

| Risk | Mitigation |
|---|---|
| **NSE endpoint breakage / throttling** | Reuse proven cookie-preflight pattern; retry with backoff; graceful degradation (agent runs without participant data if endpoint down) |
| **F&O universe shifts** (stock drops out mid-quarter) | `fno_universe` table as point-in-time reference; agent checks eligibility before tool calls |
| **Stale option chain** (live endpoint may be snapshotted too late) | Restrict option-chain tool to EOD-stale; depend on bhavcopy for settled OI |
| **Interpretation errors** (PCR misinterpretation is a classic retail trap) | Agent prompt includes explicit PCR-context rule: high PCR ≠ bullish by itself; context (trend, OI change, IV) determines |
| **Low-liquidity contracts** (midcap F&O can have phantom OI) | Agent prompt requires minimum ₹10Cr turnover for signal; below that, report "low liquidity, signal unreliable" |
| **Universe mismatch with research thesis workflow** | Many smallcaps we research (INOXINDIA, CMSINFO) may or may not be eligible. Agent gracefully returns empty rather than blocking synthesis |

### 2.12 Estimated effort

| Task | Effort |
|---|---|
| `fno_client.py` (4 fetchers + cookie preflight reuse) | 2 days |
| `fno_models.py` + `store.py` (3 tables + 10 methods) | 1 day |
| Backfill script (last 90 days bhavcopy) | 0.5 day |
| `fno_commands.py` (CLI: `fno fetch`, `fno summary`, `fno participant`) | 1 day |
| 5 MCP tools + ResearchDataAPI methods | 1 day |
| Agent prompt + sector skills (if any) | 0.5 day |
| Integration (agent.py dicts, `_SYNTHESIS_FIELDS`, CLI, tests) | 0.5 day |
| Cron wiring + LaunchAgent plist | 0.5 day |
| Autoeval F&O-eligible sector sweep | 1.5 days |
| **Total** | **~8.5 days** |

---

## Part 3 — Eval coverage for newer agents (macro, synthesis, historical_analog, F&O positioning)

**Status:** Pending. Surfaced 2026-04-21 when the user flagged that the running autoeval covers the 7 original specialists (Business, Financials, Ownership, Valuation, Risk, Technical, Sector) but has zero coverage for the 3 newer agents + the upcoming F&O Positioning agent.

### 3.1 Why the existing harness doesn't fit

The autoeval harness (`research/autoeval/evaluate.py` + `eval_matrix.yaml`) takes a `(sector, stock, agent)` matrix, runs the agent, feeds briefing + report to Gemini with a sector-specific rubric (BFSI CAR/NIM, pharma R&D pipeline, etc.), grades A→F. This assumes:

1. Output is a per-stock specialist report covering that agent's domain.
2. Graded against sector-specific KPIs.
3. Single-stock context; no cross-agent dependencies.

**Macro** breaks rule 2 — sector-agnostic (outputs regime state for the whole market). Grading against BFSI rubric is a category error.

**Historical Analog** breaks rules 1 and 2 — statistical-reasoning output, not domain analysis. No sector rubric applies.

**Synthesis** breaks rule 1 — quality is a function of how well it resolves contradictions across 10 specialist briefings; isolated grading loses meta-synthesis quality.

**F&O Positioning** (Sprint 3) breaks rule 1 partially — universe is ~200 F&O-eligible stocks only, graceful-empty for the rest. Standard rubric works for eligible stocks but the matrix needs F&O-filter flag.

### 3.2 Per-agent approach (priority-ordered)

**Tier 1 — Macro (~1 day).** Tractable because it's closest to specialist-shape.

- **Rubric dimensions:**
  - Anchor coverage: did macro drill into every `status='complete'` anchor from `get_macro_catalog` (Economic Survey, RBI AR, RBI MPR, Union Budget)?
  - Trajectory-check discipline: every `SECULAR`-tagged theme backed by ≥2 anchor publications?
  - FACT/VIEW separation: every bullet prefixed correctly, every FACT has inline URL + date?
  - India-transmission mapping: every global claim followed by INR second-order effect?
  - Stale-policy defense: is the cited Fed/ECB/RBI stance from the most recent decision?
- **Matrix shape:** flat list of dates (weekly or monthly cadence), not sector×stock. Macro state changes slowly; 4-6 eval points per quarter is enough signal.
- **Harness change:** accept `sector=_macro_, stock=NIFTY` as a pseudo-pair; use a new `eval_matrix_macro.yaml`.
- **Effort:** ~1 day (rubric + harness wiring + 4-6 initial eval points).

**Tier 2 — Historical Analog backtest (~2 days).** Unique among specialists because we have ground truth.

- **Approach:** skip Gemini rubric; do **empirical backtest**. For each of 20 randomly-sampled `(symbol, as_of_date)` points where `as_of_date` is ≥15 months ago (so 12m forward returns are observable), run the agent as-if it were `as_of_date`, extract its `directional_adjustments`, compare to realized 12m return direction.
- **Dimensions graded:**
  - **Calibration** — when agent says `downside: Thicker`, does realized 12m return land in cohort's bottom quartile significantly more often than chance?
  - **Coverage** — does the agent produce output at all (doesn't choke on thin cohorts)?
  - **Leakage** — integration test confirms `compute_feature_vector(symbol, as_of)` doesn't touch any data with date > `as_of`.
  - **Prompt adherence** — every analog cited in prose must exist in the tool-call log (programmatic check).
- **Why backtest > Gemini:** the agent's correctness is a *statistical* property, not a judgmental one. Gemini grading "is this a good analog?" is unfalsifiable; realized returns are ground truth.
- **Deliverable:** `research/autoeval/backtest_historical_analog.py` — script, not harness integration. Monthly cron target.
- **Effort:** ~2 days (backtest framework + 20 initial sample points + calibration metrics).

**Tier 3 — Synthesis eval (~2-3 days, DEFER).** Hardest and lowest ROI.

- Why defer: synthesis output quality is a function of specialist briefing quality. Fixing specialists through their own evals is more leveraged than grading synthesis output directly.
- When to revisit: after specialist A-grade autoeval completes across all sectors, synthesis eval becomes worth the effort.
- **Rubric sketch** (for when ready):
  - **Fact grounding** — Gemini verifies every claim in synthesis prose traces to a specialist briefing (automated via briefing audit).
  - **Contradiction resolution** — when specialists disagree, did synthesis explicitly address the tension vs averaging?
  - **Directive handling** — when orchestrator pre-analysis flagged a cross-signal, did synthesis address it?
  - **Calibration check** — does synthesis's bull/base/bear probability match Historical Analog's cohort prior within tolerance?
- These are **meta-rubrics** — graded across the full multi-agent run, not the synthesis output alone. Requires richer harness plumbing.

**Tier 4 — F&O Positioning (folds into Sprint 3 autoeval budget).** Standard rubric with F&O-eligible filter. No separate work item — already budgeted in Sprint 3 §2.12 (Autoeval F&O-eligible sector sweep, 1.5 days).

### 3.3 Exit criteria (Tier 1 + Tier 2 combined)

- [ ] Macro autoeval runs on 4-6 recent dates, grade distribution visible in `results.tsv`.
- [ ] Macro rubric explicitly checks anchor exhaustion (every `status='complete'` anchor drilled).
- [ ] Historical Analog backtest on 20 (symbol, 2023-Q1) points shows calibration ≥ chance (if agent says `downside: Thicker`, P(realized 12m in bottom quartile) > 0.25 by meaningful margin).
- [ ] Backtest has zero-leakage integration test (computing features for pre-2020 symbol touches no post-2020 data).
- [ ] Tier 3 synthesis eval explicitly deferred with a `# TODO` comment in `eval_matrix.yaml`.

### 3.4 Effort summary

| Tier | Item | Effort |
|---|---|---|
| 1 | Macro autoeval — rubric + harness wiring + initial 4-6 eval points | ~1 day |
| 2 | Historical Analog backtest script + 20 sample points + calibration metrics | ~2 days |
| 3 | Synthesis eval (DEFER until specialists A-grade across sectors) | ~2-3 days, not now |
| 4 | F&O Positioning eval — folded into Sprint 3 budget | 0 incremental |
| **Total now** | **~3 days** (Tier 1 + Tier 2) |

### 3.5 Sequencing recommendation

Ship Tier 1 (Macro) first — it's the smallest change and slots into the existing harness with minor shape tweaks. That gives us per-week grade visibility on macro quality, which currently has zero feedback loop.

Ship Tier 2 (Historical Analog backtest) as an independent follow-up — skipping Gemini entirely, building the backtest script as a standalone evaluation tool. Monthly cron cadence.

Tier 3 (Synthesis) waits until either (a) specialists reach A-grade across all sectors, or (b) a quality regression in synthesis output demands it.

---

## Phasing & sequencing

**Recommended order: Sprint 0 (corp-action infra) → Sprint 1 (Historical Analog) → Sprint 2 (F&O ingestion) → Sprint 3 (F&O Positioning agent).**

**Why Sprint 0 before anything else:**

Fixing all five corporate-action issues once, properly, means every current and future consumer of price data (Historical Analog, existing `get_price_performance`, screener engine, fair value, alerts) benefits. Shipping Historical Analog on a broken price-adjustment foundation guarantees bad analogs — silently.

**Why Historical Analog before F&O:**

1. **Data is already in the DB.** Historical Analog is mostly compute work on existing tables; F&O requires building a whole new ingestion pipeline.
2. **Universe coverage.** Historical Analog works on *every* stock; F&O is gated to ~200 stocks. The first agent should help more research runs.
3. **Risk profile.** Historical Analog's failure modes are all interpretability/weighting issues — contained in `analog_builder.py` logic. F&O failure modes include external API breakage + data-quality issues that can recur in production.
4. **Synthesis impact.** Historical Analog's base-rate output is directly useful for conviction calibration in *every* synth run. F&O enriches only liquid mid-to-largecap runs.

**Phasing:**

- **Sprint 0 (~3 days):** Corporate-action infrastructure — hybrid `adj_close` column + `get_adjusted_close_series` helper, bonus fix, screener refresh trigger, sync + nightly refresh hooks, full test suite. Prerequisite for Sprint 1. Also fixes a live production bug (bonus adjustment).
- **Sprint 1 (~5 days):** Historical Analog MVP. Full pipeline + 3 tools + agent + autoeval on 2-3 sectors. Reads from Sprint 0's `adj_close`.
- **Sprint 2 (~4.5 days):** F&O ingestion pipeline + CLI commands (no agent yet). Validate data quality, run backfill, verify bhavcopy parses correctly against 90 days of history.
- **Sprint 3 (~4 days):** F&O Positioning agent + tools + autoeval on F&O-eligible stocks only.

**Total: ~16.5 days across 4 sprints.**

**Parallel option:** Sprint 2's ingestion plumbing can run in parallel with Sprint 1 in a separate worktree — they don't share code surface. Sprint 0 blocks Sprint 1 (adj_close contract) but does not block Sprint 2 (F&O ingestion is independent of cash-segment price adjustment). If bandwidth allows, dispatch Sprint 2 alongside Sprint 1 after Sprint 0 lands — shortens calendar to ~2 weeks.

---

## Open questions before build starts

1. ~~**Forward-return adjustment.**~~ **RESOLVED 2026-04-20.** Sprint 0 adds hybrid adjustment: `adj_close` column on `daily_stock_data` (stored path) + `get_adjusted_close_series` helper (computed path) + nightly drift sweep verifying the two stay consistent. Includes fixing the bonus bug and the four other corporate-action issues found in audit. `analog_builder.py` reads `adj_close` directly — no per-agent adjustment logic. See Part 0.

2. **Universe scoping.** Run Historical Analog MVP on Nifty 500 only, or all 3,126? Nifty 500 is safer (higher data quality, ~20K `historical_states` rows). Full universe gives richer analogs but noisier data.

3. **Cohort-same-sector vs cross-sector.** For pharma, is a 2019 pharma analog better than a 2021 chemicals analog with similar features? Default: same-industry hard filter. But for macro-driven regime analogs (late-cycle, high-inflation), cross-sector is exactly what we want. Discuss: expose both modes via agent tool params?

4. **Back-adjusted F&O settlement prices.** F&O contracts have expiry cycles — "OI trend" has to be continuous-contract aware (roll from near-month to next-month at expiry). Implementation detail but non-trivial. Agent can call per-expiry OI directly; continuous-contract series can be Phase 2.

5. **F&O agent interaction with Technical agent.** Both reason about price behavior and positioning. Should we merge them ("trading_positioning agent") or keep separate? Argument for separate: different data sources (cash vs derivative), different audiences, different failure modes. Default: separate; revisit after both are running.

6. **Does F&O positioning flow into Technical agent's briefing as an input** rather than having its own agent? Trade-off: smaller agent count + consolidated positioning narrative vs. specialized focus + independent failure. Default: separate agent, but consider merging after 1-2 sprints if autoeval shows overlap.

---

## Test strategy

**Historical Analog:**

- **Unit:** feature-vector computation from known fixture quarterly data; distance metric symmetry; forward-return correctness for stocks with known splits.
- **Integration:** run `get_historical_analogs` end-to-end against a frozen `historical_states` table, verify top-K return.
- **Contract:** agent prompt registered; briefing schema valid; `_SYNTHESIS_FIELDS` whitelist covers emitted keys.
- **Data-leakage test:** computing historical_state for (X, 2020-Q1) must not touch any data with date > 2020-03-31.

**F&O Positioning:**

- **Unit:** bhavcopy CSV parsing against golden fixture; PCR / basis / OI-percentile math.
- **Integration:** `FnoClient.fetch_fno_bhavcopy` against `respx`-mocked NSE endpoint; store upsert idempotency.
- **Contract:** agent prompt registered; tools registered; `fno_eligible=false` path returns `status=empty` cleanly.
- **Freshness:** daily cron healthcheck — `fno_contracts.trade_date >= today-2` after market close on weekday.

Both agents hit the existing CLI smoke suite (`tests/unit/test_smoke.py`) via `--help` registration.

---

## Summary for decision

| Sprint | Status | Effort | Scope | Unblocks |
|---|---|---|---|---|
| **Sprint 0** | ✅ Merged 2026-04-20 (PR #65, #66) | ~3 days | Corporate-action infra | Sprint 1 |
| **Sprint 1** | ✅ Merged 2026-04-20 (PR #67) | ~5 days | Historical Analog agent | Empirical conviction calibration in synthesis |
| **Part 1.5** | 🔄 **Queued — resume here** | ~1 day | Post-Sprint-1 hardening from Gemini review of TMPV smoke test (similarity-ring fallback, informative_N, is_backfilled flag, imputation, multi-horizon stats, toxic-intersection prompt clause) | Robust output on narrow-industry and recently-listed tickers |
| **Part 3** (eval coverage) | 🔄 Queued | ~3 days | Macro autoeval rubric (Tier 1, ~1d) + Historical Analog backtest script (Tier 2, ~2d). Synthesis eval deferred. | Per-agent quality feedback loops on the 3 newer agents |
| **Sprint 2** | Pending | ~4.5 days | F&O ingestion pipeline | Sprint 3 |
| **Sprint 3** | Pending | ~4 days | F&O Positioning agent | Unique positioning dimension |

**Remaining effort: ~12.5 days.**

Both new agents are tier-3 (failures non-blocking). Both are pure additions — no existing agent changes required. `_SYNTHESIS_FIELDS` expansions land cleanly.

### Next-session resume card

**Start here:** Part 1.5 (§1.5.2 fix list). Three CRITICAL items (similarity-ring fallback, informative_N, is_backfilled flag) are the most leveraged — shipping just those would already lift edge-case output quality. Re-run the TMPV smoke + exit criteria in §1.5.5 to verify.

**Second priority:** Part 3 eval coverage (§3.2 Tier 1 + Tier 2). Ship Macro autoeval (~1d) before Tier 2 backtest (~2d). Tier 3 (synthesis eval) stays deferred. These can parallelize with Part 1.5 in separate worktrees — they touch different code paths.

**After Part 1.5 + Part 3:** Sprint 2 ingestion work starts in `equity-research-fno-ingest`. Sprint 2 has zero dependency on the other pending items.

**Context anchors:**
- TMPV smoke output that triggered Part 1.5: in session log 2026-04-21 around commit `f5d0f93` (Sprint 1 merge).
- Gemini review verdict for Part 1.5: see §1.5.2 table + §1.5.3 keep-list.
- Part 3 motivation: user flagged the 3 newer agents (macro, synthesis, historical_analog) have zero autoeval coverage while the 7 original specialists are being graded. §3.1 explains why the existing harness doesn't fit.
- Production DB has 17,701 materialized state rows — no re-materialization needed unless `analog_builder.py` feature-vector logic changes (Part 1.5 fixes #1/#2/#5 don't change features; #3/#4 do — plan a re-run if those ship).
