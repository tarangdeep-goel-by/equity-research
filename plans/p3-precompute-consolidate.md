# P-3: Pre-compute & Consolidate — Architecture Overhaul

> Context: Gemini review flagged "Ferrari engine, confusing steering wheel" — 67 tools, 33 per agent, 5000-word prompts. Root cause: agents are computing metrics that should be pre-stored.
> Prerequisite: P-2 complete (11 analytical tools, BFSI routing, sector KPIs)
> Project: `./flow-tracker/`
> Branch: TBD (worktree)

## Goal

Separate the **compute layer** from the **agent layer**. Agents should be consumers of pre-computed data, not computers. This:
1. Cuts tool count per agent from 30+ → ~12
2. Eliminates 5-10 agent turns of pure computation per report
3. Enables stock screening ("all stocks with F-Score > 7")
4. Creates time-series data (track F-Score changes monthly)
5. Makes reports faster and cheaper

## Principle: No New Math

All formulas used in pre-computation are EXACTLY the existing P-2 implementations. We are moving computation from agent-time to cron-time, not changing any formulas. Source of truth:
- `get_piotroski_score()` → `data_api.py` (9 criteria, adjusted_shares via EPS, NIM proxy for BFSI)
- `get_beneish_score()` → `data_api.py` (8 variables, skip if any NULL, skip BFSI)
- `get_earnings_quality()` → `data_api.py` (CFO/PAT, CFO/EBITDA, accruals, skip BFSI)
- `get_reverse_dcf()` → `data_api.py` (FCFF@WACC for non-BFSI, FCFE@Ke for BFSI, capex=ΔNB+ΔCWIP+depr, EV→MCap bridge)
- `get_capex_cycle()` → `data_api.py` (CWIP/NB, phase detection, skip BFSI)
- `get_common_size_pl()` → `data_api.py` (% of revenue, Total Income for BFSI)
- `get_bfsi_metrics()` → `data_api.py` (NIM, ROA, C/I, equity multiplier, insurance carve-out)
- `get_price_performance()` → `data_api.py` (vs Nifty 50 + sector index, price return excl. dividends)
- `get_composite_score()` → `screener_engine.py` (8-factor weighted score)

---

## Phase 1: New Table — `analytical_snapshot`

### Schema

```sql
CREATE TABLE IF NOT EXISTS analytical_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    computed_date TEXT NOT NULL,  -- YYYY-MM-DD

    -- Composite Score (from screener_engine.py)
    composite_score REAL,
    composite_factors TEXT,  -- JSON: {ownership: 72, insider: 35, ...}

    -- Piotroski F-Score (from data_api.get_piotroski_score)
    f_score INTEGER,
    f_score_max INTEGER,
    f_score_signal TEXT,  -- strong/moderate/weak
    f_score_criteria TEXT,  -- JSON: [{name, passed, value, note?}, ...]

    -- Beneish M-Score (from data_api.get_beneish_score)
    m_score REAL,
    m_score_signal TEXT,  -- likely_manipulator/gray_zone/unlikely_manipulator/skipped
    m_score_variables TEXT,  -- JSON: {DSRI, GMI, AQI, ...}

    -- Earnings Quality (from data_api.get_earnings_quality)
    eq_signal TEXT,  -- high_quality/low_quality/warning/skipped
    eq_cfo_pat_3y REAL,
    eq_cfo_pat_5y REAL,
    eq_accruals_3y REAL,

    -- Reverse DCF (from data_api.get_reverse_dcf)
    rdcf_implied_growth REAL,
    rdcf_model TEXT,  -- FCFF/FCFE
    rdcf_base_cf REAL,
    rdcf_market_cap REAL,
    rdcf_3y_cagr REAL,
    rdcf_5y_cagr REAL,
    rdcf_assessment TEXT,

    -- Capex Cycle (from data_api.get_capex_cycle)
    capex_phase TEXT,  -- Investing/Commissioning/Harvesting/Mature/skipped
    capex_cwip_to_nb REAL,
    capex_intensity REAL,
    capex_asset_turnover REAL,

    -- Common Size P&L (from data_api.get_common_size_pl) — latest year only
    cs_biggest_cost TEXT,
    cs_fastest_growing_cost TEXT,
    cs_raw_material_pct REAL,
    cs_employee_pct REAL,
    cs_depreciation_pct REAL,
    cs_interest_pct REAL,
    cs_net_margin_pct REAL,
    cs_ebit_pct REAL,
    cs_denominator TEXT,  -- revenue/total_income

    -- BFSI Metrics (from data_api.get_bfsi_metrics) — latest year only
    bfsi_nim_pct REAL,
    bfsi_roa_pct REAL,
    bfsi_cost_to_income_pct REAL,
    bfsi_equity_multiplier REAL,
    bfsi_book_value_per_share REAL,
    bfsi_pb_ratio REAL,

    -- Price Performance (from data_api.get_price_performance)
    perf_1m_stock REAL,
    perf_3m_stock REAL,
    perf_6m_stock REAL,
    perf_1y_stock REAL,
    perf_1m_excess REAL,  -- vs Nifty
    perf_3m_excess REAL,
    perf_6m_excess REAL,
    perf_1y_excess REAL,
    perf_outperformer INTEGER,  -- 0/1
    perf_sector_index TEXT,

    -- Metadata
    industry TEXT,
    is_bfsi INTEGER,  -- 0/1
    is_insurance INTEGER,  -- 0/1
    errors TEXT,  -- JSON: {metric_name: "error message", ...}
    compute_duration_ms INTEGER,

    UNIQUE(symbol, computed_date)
);
```

### Design Decisions
- **One row per stock per day** — UNIQUE(symbol, computed_date). Weekly cron creates one snapshot per week.
- **Flat columns** for key metrics (enables SQL queries/screening). JSON for complex structures (criteria lists, variables).
- **Errors stored** — if a metric fails for a stock (e.g., M-Score can't compute), the error is stored, not silently dropped.
- **BFSI columns nullable** — non-BFSI stocks have NULL for bfsi_* columns.
- **Common Size stores latest year only** — full 10Y history stays in the on-demand tool for deep-dive agents.

---

## Phase 2: Compute Script — `scripts/compute-analytics.py`

### What It Does
For each stock in `index_constituents`:
1. Call each `ResearchDataAPI` method
2. Extract key fields
3. Upsert into `analytical_snapshot`

### Implementation Pattern
```python
"""Pre-compute analytical metrics for all Nifty 500 stocks."""

import time
from flowtracker.research.data_api import ResearchDataAPI
from flowtracker.store import FlowStore

def compute_stock(api: ResearchDataAPI, symbol: str) -> dict:
    """Compute all analytical metrics for a single stock. Returns row dict."""
    row = {"symbol": symbol, "computed_date": date.today().isoformat()}
    errors = {}

    # Industry classification
    info = api.get_company_info(symbol)
    row["industry"] = info.get("industry", "Unknown")
    row["is_bfsi"] = 1 if api._is_bfsi(symbol) else 0
    row["is_insurance"] = 1 if api._is_insurance(symbol) else 0

    # F-Score
    try:
        fs = api.get_piotroski_score(symbol)
        if "error" not in fs:
            row["f_score"] = fs["score"]
            row["f_score_max"] = fs["max_score"]
            row["f_score_signal"] = fs["signal"]
            row["f_score_criteria"] = json.dumps(fs["criteria"])
        else:
            errors["f_score"] = fs["error"]
    except Exception as e:
        errors["f_score"] = str(e)

    # M-Score
    try:
        ms = api.get_beneish_score(symbol)
        if ms.get("skipped"):
            row["m_score_signal"] = "skipped"
        elif ms.get("score") is not None:
            row["m_score"] = ms["m_score"]
            row["m_score_signal"] = ms["signal"]
            row["m_score_variables"] = json.dumps(ms["variables"])
        elif ms.get("error"):
            errors["m_score"] = ms["error"]
    except Exception as e:
        errors["m_score"] = str(e)

    # ... same pattern for all 9 metrics

    row["errors"] = json.dumps(errors) if errors else None
    return row

def main():
    store = FlowStore()
    store.__enter__()
    api = ResearchDataAPI()

    symbols = [r[0] for r in store._conn.execute(
        "SELECT DISTINCT symbol FROM index_constituents"
    ).fetchall()]

    for i, symbol in enumerate(symbols):
        start = time.time()
        row = compute_stock(api, symbol)
        row["compute_duration_ms"] = int((time.time() - start) * 1000)
        store.upsert_analytical_snapshot(row)
        print(f"[{i+1}/{len(symbols)}] {symbol}: {row['compute_duration_ms']}ms")

    api.close()
    store.__exit__(None, None, None)
```

### Estimated Runtime
- ~500 stocks × ~1 sec each (DB queries, no API calls except price_performance yfinance)
- `get_price_performance` needs live yfinance for Nifty/sector index — cache this once
- **Total: ~10-15 minutes** for full universe

### Cron Integration
Add to `scripts/weekly-nifty250.sh`:
```bash
# After all data refresh steps, compute analytics
echo "[$(date)] Computing analytical snapshots..."
uv run python scripts/compute-analytics.py >> "$LOG" 2>&1
```

---

## Phase 3: Store Methods — `store.py`

Add to `FlowStore`:

```python
def upsert_analytical_snapshot(self, row: dict) -> None:
    """Upsert a single analytical snapshot row."""
    cols = list(row.keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_names = ", ".join(cols)
    sql = f"INSERT OR REPLACE INTO analytical_snapshot ({col_names}) VALUES ({placeholders})"
    self._conn.execute(sql, [row.get(c) for c in cols])
    self._conn.commit()

def get_analytical_snapshot(self, symbol: str) -> dict | None:
    """Get latest analytical snapshot for a stock."""
    row = self._conn.execute(
        "SELECT * FROM analytical_snapshot WHERE symbol = ? ORDER BY computed_date DESC LIMIT 1",
        (symbol.upper(),)
    ).fetchone()
    if not row:
        return None
    cols = [d[0] for d in self._conn.execute("PRAGMA table_info(analytical_snapshot)").fetchall()]
    return dict(zip([c[1] for c in cols], row))  # Fixed: use column names from pragma

def get_analytical_snapshots_all(self, computed_date: str | None = None) -> list[dict]:
    """Get latest snapshots for all stocks. For screening."""
    if computed_date:
        sql = "SELECT * FROM analytical_snapshot WHERE computed_date = ?"
        rows = self._conn.execute(sql, (computed_date,)).fetchall()
    else:
        sql = """SELECT a.* FROM analytical_snapshot a
                 INNER JOIN (SELECT symbol, MAX(computed_date) as max_date
                            FROM analytical_snapshot GROUP BY symbol) b
                 ON a.symbol = b.symbol AND a.computed_date = b.max_date"""
        rows = self._conn.execute(sql).fetchall()
    # Convert to dicts
    cols_info = self._conn.execute("PRAGMA table_info(analytical_snapshot)").fetchall()
    col_names = [c[1] for c in cols_info]
    return [dict(zip(col_names, row)) for row in rows]

def screen_by_analytics(self, filters: dict) -> list[dict]:
    """Screen stocks by analytical metrics. E.g., {"f_score_min": 7, "m_score_signal": "unlikely_manipulator"}"""
    conditions = []
    params = []
    for key, value in filters.items():
        if key.endswith("_min"):
            col = key[:-4]
            conditions.append(f"{col} >= ?")
            params.append(value)
        elif key.endswith("_max"):
            col = key[:-4]
            conditions.append(f"{col} <= ?")
            params.append(value)
        else:
            conditions.append(f"{key} = ?")
            params.append(value)
    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"""SELECT * FROM analytical_snapshot a
              INNER JOIN (SELECT symbol, MAX(computed_date) as max_date
                         FROM analytical_snapshot GROUP BY symbol) b
              ON a.symbol = b.symbol AND a.computed_date = b.max_date
              WHERE {where}"""
    rows = self._conn.execute(sql, params).fetchall()
    cols_info = self._conn.execute("PRAGMA table_info(analytical_snapshot)").fetchall()
    col_names = [c[1] for c in cols_info]
    return [dict(zip(col_names, row)) for row in rows]
```

---

## Phase 4: Consolidated Macro-Tools

### New Tools (replace 10+ individual tools)

#### `get_analytical_profile(symbol)` — THE mega-tool
Returns the full pre-computed analytical snapshot for a stock in one call. Replaces:
- `get_piotroski_score`
- `get_beneish_score`
- `get_earnings_quality`
- `get_reverse_dcf`
- `get_capex_cycle`
- `get_common_size_pl` (latest year summary)
- `get_bfsi_metrics` (latest year summary)
- `get_price_performance`
- `get_composite_score`

**Implementation:**
```python
def get_analytical_profile(self, symbol: str) -> dict:
    """Get pre-computed analytical profile. One call replaces 9 individual tools."""
    snapshot = self._store.get_analytical_snapshot(symbol)
    if not snapshot:
        return {"error": f"No analytical snapshot for {symbol}. Run compute-analytics.py first."}

    # Parse JSON fields
    for field in ["composite_factors", "f_score_criteria", "m_score_variables", "errors"]:
        if snapshot.get(field):
            try:
                snapshot[field] = json.loads(snapshot[field])
            except (json.JSONDecodeError, TypeError):
                pass

    return snapshot
```

**MCP tool:**
```python
@tool(
    "get_analytical_profile",
    "Pre-computed analytical profile: composite score, F-Score, M-Score, earnings quality, "
    "reverse DCF, capex cycle, common size P&L, BFSI metrics, price performance. "
    "One call returns all analytical metrics. Updated weekly.",
    {"symbol": str},
)
```

#### `screen_stocks(filters)` — screening tool
```python
@tool(
    "screen_stocks",
    "Screen Nifty 500 stocks by analytical metrics. Example filters: "
    "f_score_min=7, m_score_signal='unlikely_manipulator', perf_1y_excess_min=10",
    {"filters": dict},
)
```

### Keep Individual Tools As Deep-Dive Fallbacks
The individual tools (`get_piotroski_score`, etc.) STAY in the codebase for:
1. Deep-dive agents that need full 10Y history (not just latest snapshot)
2. On-demand computation for stocks not in the weekly batch
3. Debugging and verification

But they are REMOVED from agent registries. Agents use `get_analytical_profile` instead.

---

## Phase 5: Agent Registry Overhaul

### Before (Current)
| Agent | Tools |
|-------|-------|
| Financial | 33 |
| Valuation | 30 |
| Risk | 23 |
| Business | 21 |
| Sector | 14 |
| Ownership | 13 |
| Technical | 10 |

### After (P-3)
Replace 9 individual analytical tools with 1 `get_analytical_profile` in each registry.

| Agent | Current Tools | Remove | Add | New Total |
|-------|--------------|--------|-----|-----------|
| Financial | 33 | earnings_quality, piotroski_score, beneish_score, reverse_dcf, capex_cycle, common_size_pl, bfsi_metrics, revenue_estimates, sector_kpis (-9) | analytical_profile (+1) | **25** |
| Valuation | 30 | reverse_dcf, bfsi_metrics, price_performance, revenue_estimates, growth_estimates (-5) | analytical_profile (+1) | **26** |
| Risk | 23 | earnings_quality, piotroski_score, beneish_score, bfsi_metrics (-4) | analytical_profile (+1) | **20** |
| Business | 21 | sector_kpis (-1) | analytical_profile (+1) | **21** |
| Sector | 14 | price_performance, sector_kpis (-2) | analytical_profile (+1) | **13** |
| Technical | 10 | price_performance (-1) | analytical_profile (+1) | **10** |
| Ownership | 13 | (none) | (none) | **13** |

**Note:** This is a first pass. Phase P-4 (prompt optimization) will consolidate further by merging granular financial tools into macro-tools (e.g., `get_financial_statements`).

### Deep-Dive Access
Financial and Risk agents KEEP individual tools (`get_common_size_pl` full 10Y, `get_capex_cycle` full 10Y) for when the analytical_profile summary isn't enough. But they call `get_analytical_profile` FIRST, then drill down only if needed.

---

## Phase 6: Prompt Updates

Each agent prompt's "Your Tools" section gets updated:

**Pattern for all agents:**
```
### Phase 0: Analytical Profile (START HERE)
1. `get_analytical_profile` — Pre-computed analytical snapshot: composite score (8 factors), 
   F-Score (0-9), M-Score (manipulation risk), earnings quality (cash conversion), 
   reverse DCF (implied growth), capex cycle (phase), common size P&L (cost structure), 
   BFSI metrics (NIM/ROA if applicable), price performance (vs Nifty + sector). 
   ALWAYS call this first — it gives you the analytical foundation in one call. 
   Only drill into individual tools if you need full 10Y history or deeper breakdown.
```

---

## Implementation Plan

### Batch 1: Schema + Store + Compute Script
- Add table to store.py `_init_db()`
- Add `upsert_analytical_snapshot()`, `get_analytical_snapshot()`, `get_analytical_snapshots_all()`, `screen_by_analytics()`
- Write `scripts/compute-analytics.py`
- Run for all 500 stocks, verify output

### Batch 2: Macro-Tool + Registry
- Add `get_analytical_profile()` to `data_api.py`
- Add `screen_stocks()` to `data_api.py`
- Add MCP tool wrappers to `tools.py`
- Update all 6 agent registries (remove individual tools, add analytical_profile)

### Batch 3: Prompt Updates + Cron
- Update all agent prompts (Phase 0: Analytical Profile)
- Add compute step to `weekly-nifty250.sh`
- Verify end-to-end: cron → compute → store → agent reads

### Verification
```bash
# 1. Compute for all stocks
uv run python scripts/compute-analytics.py

# 2. Check coverage
uv run python -c "
from flowtracker.store import FlowStore
with FlowStore() as s:
    rows = s.get_analytical_snapshots_all()
    print(f'{len(rows)} stocks computed')
    # Check a bank
    hdfc = s.get_analytical_snapshot('HDFCBANK')
    print(f'HDFCBANK: F-Score={hdfc[\"f_score\"]}, NIM={hdfc[\"bfsi_nim_pct\"]}%, M-Score={hdfc[\"m_score_signal\"]}')
    # Check a non-bank
    rel = s.get_analytical_snapshot('RELIANCE')
    print(f'RELIANCE: F-Score={rel[\"f_score\"]}, M-Score={rel[\"m_score\"]}, Phase={rel[\"capex_phase\"]}')
"

# 3. Test screening
uv run python -c "
from flowtracker.store import FlowStore
with FlowStore() as s:
    # High quality stocks
    quality = s.screen_by_analytics({'f_score_min': 7, 'eq_signal': 'high_quality'})
    print(f'High quality (F>=7, EQ=high): {len(quality)} stocks')
    for r in quality[:5]:
        print(f'  {r[\"symbol\"]}: F={r[\"f_score\"]}, M={r[\"m_score\"]:.2f}')
"

# 4. Test agent tool
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
with ResearchDataAPI() as api:
    profile = api.get_analytical_profile('HDFCBANK')
    print('Keys:', list(profile.keys()))
    print('F-Score:', profile.get('f_score'))
    print('BFSI NIM:', profile.get('bfsi_nim_pct'))
"

# 5. Verify import of all tools
uv run python -c "from flowtracker.research.tools import get_analytical_profile, screen_stocks; print('OK')"
```

## Files Modified
| File | Changes |
|------|---------|
| `store.py` | +table schema, +4 methods (upsert, get, get_all, screen) |
| `data_api.py` | +get_analytical_profile(), +screen_stocks() |
| `tools.py` | +2 MCP tools, registry updates (remove 9 individual, add 1 macro) |
| `prompts.py` | Phase 0 addition to all 6 agent prompts |
| `scripts/compute-analytics.py` | NEW — batch compute script |
| `scripts/weekly-nifty250.sh` | +compute step |

## Estimated Effort
- Batch 1 (schema + compute): 2-3 hours
- Batch 2 (macro-tool + registry): 1-2 hours
- Batch 3 (prompts + cron): 1 hour
- **Total: 4-6 hours**

## What This Enables (Future)
- **Stock screener CLI:** `flowtrack screen --f-score-min 7 --m-score-clean --outperformer`
- **Dashboard:** Pre-computed data feeds a web dashboard directly (no agent needed)
- **Alerts:** "RELIANCE F-Score dropped from 7 to 4" — track changes over time
- **Faster reports:** Agent gets analytical profile in 1 tool call instead of 9
- **Lower cost:** Fewer agent turns = lower Anthropic bill per report
