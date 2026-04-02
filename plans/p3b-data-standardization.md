# P-3b: Data Standardization — Unit Consistency & Source Deduplication

## Context

Deep audit of the FlowTracker SQLite database (46 tables, 4M+ rows) revealed critical data integrity issues:

1. **Mixed units in same table**: `annual_financials` has Screener rows in CRORES and yfinance rows in raw RUPEES. Same for `quarterly_results`. The `INSERT OR REPLACE` pattern means whichever source runs last wins.
2. **No single source of truth**: Two scrapers write to the same tables with different units and field coverage.
3. **Unit conversions scattered in compute code**: `÷1e7` and `×1e7` sprinkled across 6+ files to bridge unit mismatches between tables.
4. **Confirmed bugs**: BFSI `book_value_per_share` divides crores by raw share count (gives ~0.00007 instead of ~682 Rs).

**Principle**: Fix at ingestion, not at computation. All monetary values stored in CRORES. No `×1e7` in derivation code.

---

## Definitive Unit Map (Current State)

### Tables that store CRORES (correct)
| Table | Source | Fields | Status |
|-------|--------|--------|--------|
| `annual_financials` (Screener rows) | Screener Excel | revenue, net_income, total_assets, borrowings, cfo, etc. | Correct |
| `quarterly_results` (Screener rows) | Screener HTML/Excel | revenue, net_income, expenses, etc. | Correct |
| `quarterly_balance_sheet` | yfinance (÷1e7 at fetch) | total_assets, total_debt, cash, etc. | Correct |
| `quarterly_cash_flow` | yfinance (÷1e7 at fetch) | operating_cf, free_cf, capex, etc. | Correct |
| `mf_monthly_flows` | AMFI | funds_mobilized, redemption, net_flow, aum | Correct |
| `mf_daily_flows` | SEBI | gross_purchase, gross_sale, net_investment | Correct |

### Tables that store RAW RUPEES (need conversion at ingestion)
| Table | Source | Fields | Fix |
|-------|--------|--------|-----|
| `valuation_snapshot` | yfinance `.info` | market_cap, enterprise_value, total_cash, total_debt, free_cash_flow, operating_cash_flow | ÷1e7 at `fund_client.fetch_valuation_snapshot()` |
| `annual_financials` (yfinance rows) | yfinance income/BS/CF | ALL monetary fields | **Delete path entirely** — Screener is source of truth |
| `quarterly_results` (yfinance rows) | yfinance quarterly income | revenue, net_income, ebitda, etc. | **Delete path entirely** — Screener is source of truth |
| `insider_transactions` | NSE SAST | value | ÷1e7 at `insider_client.fetch_*()` |
| `fmp_key_metrics` | FMP API | market_cap, enterprise_value | ÷1e7 at `fmp_client.fetch_key_metrics()` |

### Tables that store LAKHS (convert to CRORES)
| Table | Source | Fields | Fix |
|-------|--------|--------|-----|
| `mf_scheme_holdings` | AMC XLSX | market_value_lakhs | ÷100 at `mfportfolio_client.fetch_amc()`, rename to `market_value_cr` |
| `daily_stock_data` | NSE bhavcopy | turnover | ÷100 at `bhavcopy_client.fetch_*()`, rename to `turnover_cr` |

### Tables that store PER-SHARE values in RUPEES (keep as-is)
| Table | Fields | Status |
|-------|--------|--------|
| `valuation_snapshot` | price, book_value_per_share, revenue_per_share, cash_per_share | Keep Rs |
| `annual_financials` | eps, price | Keep Rs |
| `quarterly_results` | eps | Keep Rs |
| `daily_stock_data` | open, high, low, close, prev_close | Keep Rs |
| `consensus_estimates` | target_mean/median/high/low, current_price, forward_eps | Keep Rs |
| `fmp_dcf` | dcf, stock_price | Keep Rs |
| `fmp_price_targets` | price_target, price_when_posted | Keep Rs |
| `corporate_actions` | dividend_amount | Keep Rs per share |

### Tables that store COUNTS (keep as-is)
| Table | Fields | Status |
|-------|--------|--------|
| `annual_financials` | num_shares | Raw count (13.5B for Reliance) |
| `quarterly_balance_sheet` | shares_outstanding | Raw count |
| `valuation_snapshot` | shares_outstanding, float_shares, avg_volume | Raw count |
| `daily_stock_data` | volume, delivery_qty | Raw count |
| `insider_transactions` | quantity | Raw count |
| `mf_scheme_holdings` | quantity | Raw count |

### Tables that store PERCENTAGES / RATIOS (keep as-is)
| Table | Fields |
|-------|--------|
| `shareholding` | pct_shareholding |
| `promoter_pledge` | pledge_pct, encumbered_pct |
| `screener_ratios` | roce_pct |
| `valuation_snapshot` | pe_trailing, pb_ratio, ev_ebitda, dividend_yield, roe, roa, margins |
| `fmp_financial_growth` | all growth rates |
| `mf_scheme_holdings` | pct_of_nav |

---

## Data Source Deduplication

### Problem: Two sources write to same table

**`annual_financials`**:
- Screener (via `screener_client.parse_annual_financials`): 620 rows, 69 stocks. CRORES, full expense breakdown.
- yfinance (via `backfill_fundamentals.fetch_annual_financials`): 1,718 rows, 431 stocks. RAW RUPEES, no expense breakdown.
- **6 stocks have MIXED data** (both sources, different units for different years).

**`quarterly_results`**:
- Screener (via `screener_client.parse_quarterly_results`): 2,894 rows. CRORES, full breakdown.
- Screener HTML (via `parse_quarterly_from_html`): 9,804 rows. CRORES, partial fields (no expenses).
- yfinance (via `fund_client.fetch_quarterly_results`): 1,003 rows. RAW RUPEES, no breakdown.

### Fix: Single source per table

| Table | Keep | Delete | Backfill |
|-------|------|--------|----------|
| `annual_financials` | Screener Excel only | yfinance rows (from `backfill_fundamentals.py`) | Run `backfill-nifty250.py --step screener` for all 500 stocks |
| `quarterly_results` | Screener (HTML + Excel) | yfinance rows (from `fund_client.fetch_quarterly_results`) | Screener HTML already covers all 500 stocks |

### How to identify yfinance rows for deletion
```sql
-- annual_financials: yfinance rows have employee_cost IS NULL AND revenue > 100000
-- (Screener rows always have employee_cost populated, revenue in crores range)
DELETE FROM annual_financials WHERE employee_cost IS NULL AND revenue > 100000;

-- quarterly_results: yfinance rows fetched on 2026-03-19 with revenue > 100000
-- Safer: delete rows where expenses IS NULL AND revenue > 100000 AND fetched_at LIKE '2026-03-19%'
DELETE FROM quarterly_results WHERE expenses IS NULL AND revenue > 100000;
```

### Code changes to prevent future contamination

| File | Change |
|------|--------|
| `scripts/backfill_fundamentals.py` | Remove `fetch_annual_financials()` function and its call in the main loop. Remove `fetch_quarterly_results` calls that use `fund_client`. |
| `fund_client.py` | Keep `fetch_quarterly_results()` but add deprecation warning. Or remove entirely if Screener covers all quarterly needs. |
| `scripts/backfill-nifty250.py` | Ensure `step_screener` is the ONLY step that writes to `annual_financials` and `quarterly_results`. |

---

## Scraper Unit Conversions (at ingestion)

### `fund_client.py` — `fetch_valuation_snapshot()`

Currently stores `market_cap`, `enterprise_value`, `total_cash`, `total_debt`, `free_cash_flow`, `operating_cash_flow` in raw rupees from yfinance `.info`.

**Fix**: Add `÷1e7` for aggregate monetary fields. Keep per-share fields as-is.

```python
# Fields to convert to crores at ingestion:
_CRORE_FIELDS = {
    "market_cap", "enterprise_value", "total_cash", "total_debt",
    "free_cash_flow", "operating_cash_flow", "total_revenue",
    "ebitda", "gross_profits",
}

# In fetch_valuation_snapshot:
for field in _CRORE_FIELDS:
    val = info.get(yfinance_key)
    if val is not None:
        val = val / 1e7  # Convert rupees to crores
```

**Impact on existing computation code**: Remove `market_cap / 1e7` from:
- `data_api.py:get_reverse_dcf()` (line 1323)
- `data_collector.py` (line 150)
- `screener_engine.py` if applicable

### `insider_client.py` — `fetch_by_symbol()` etc.

Currently stores `value` in raw rupees.

**Fix**: Add `÷1e7` at ingestion. Currently `screener_engine.py:163` does `buy_val = sum(t.value) / 1e7` — this conversion moves to ingestion.

### `fmp_client.py` — `fetch_key_metrics()`

Currently stores `market_cap`, `enterprise_value` in raw values from FMP.

**Fix**: Add `÷1e7` for aggregate monetary fields at ingestion.

### `mfportfolio_client.py` — `fetch_amc()`

Currently stores `market_value_lakhs`. 

**Fix**: Convert to crores (÷100) and rename column to `market_value_cr`.

### `bhavcopy_client.py` — `fetch_day()` etc.

Currently stores `turnover` in lakhs.

**Fix**: Convert to crores (÷100) and rename column to `turnover_cr`.

---

## Computation Code Cleanup (remove unit conversions)

After ingestion standardization, these `÷1e7` / `×1e7` operations become unnecessary:

| File | Line | Current Code | After Fix |
|------|------|-------------|-----------|
| `data_api.py` | ~1323 | `market_cap = market_cap_raw / 1e7` | `market_cap = valuation.get("market_cap")` (already crores) |
| `data_api.py` | ~1441 | `implied_price = implied_mcap * 1e7 / num_shares` | `implied_price = implied_mcap * 1e7 / num_shares` (keep — converts Cr to Rs for per-share) |
| `data_api.py` | BFSI bvps | `bvps = net_worth / num_shares` | `bvps = net_worth * 1e7 / num_shares` (keep — Cr to Rs per share) |
| `screener_engine.py` | ~163 | `buy_val = sum(t.value) / 1e7` | `buy_val = sum(t.value)` (already crores) |
| `data_collector.py` | ~150 | `mcap_cr = round(mcap / 1e7)` | `mcap_cr = round(mcap)` (already crores) |
| `estimates_client.py` | ~268 | `round(float(val) / 1e7, 2)` for revenue | Keep — yfinance API always returns rupees, conversion happens before return |

**Note**: `×1e7` for Cr→Rs per-share conversions (`bvps`, `implied_price`) STAY. These are legitimate unit conversions from aggregate crores to per-share rupees. Only the `÷1e7` for aggregate values get removed.

---

## BFSI book_value_per_share Bug Fix

**Current (buggy)**:
```python
bvps = net_worth / num_shares  # Cr / count = ~0.00007
```

**After standardization**:
```python
bvps = net_worth * 1e7 / num_shares  # Cr → Rs, then / count = ~682 Rs
```

This `×1e7` is NOT a hack — it's the legitimate Cr→Rs conversion for per-share values. It stays.

---

## Data Validation Layer (NEW)

Add validation at ingestion to catch unit errors early:

```python
# In store.py or a new validation module
_VALIDATION_RULES = {
    "annual_financials": {
        "revenue": (0, 2_000_000),  # 0 to 20L Cr (largest Indian company ~10L Cr)
        "net_income": (-100_000, 1_000_000),
        "total_assets": (0, 100_000_000),  # banks can be very large
        "num_shares": (1_000_000, 50_000_000_000),  # 10L to 5000 Cr shares
        "eps": (-500, 10_000),  # Rs per share
    },
    "valuation_snapshot": {
        "market_cap": (0, 30_000_000),  # 0 to 30L Cr (after conversion)
        "price": (0.01, 200_000),  # Rs per share
        "pe_trailing": (-1000, 5000),
    },
    "quarterly_results": {
        "revenue": (0, 500_000),  # quarterly, so lower than annual
    },
}

def validate_row(table: str, row: dict) -> list[str]:
    """Return list of validation errors. Empty = valid."""
    errors = []
    rules = _VALIDATION_RULES.get(table, {})
    for field, (lo, hi) in rules.items():
        val = row.get(field)
        if val is not None and (val < lo or val > hi):
            errors.append(f"{field}={val} outside [{lo}, {hi}]")
    return errors
```

Call this in every `upsert_*` method. Log warnings but don't reject (some edge cases may be valid).

---

## Migration Script: `scripts/migrate-units.py`

One-time migration for existing data:

```python
"""Migrate existing DB to standardized crore units."""

# 1. Delete yfinance annual_financials rows
DELETE FROM annual_financials WHERE employee_cost IS NULL AND revenue > 100000;

# 2. Delete yfinance quarterly_results rows  
DELETE FROM quarterly_results WHERE expenses IS NULL AND revenue > 100000;

# 3. Convert valuation_snapshot monetary fields to crores
UPDATE valuation_snapshot SET 
    market_cap = market_cap / 1e7,
    enterprise_value = enterprise_value / 1e7,
    total_cash = total_cash / 1e7,
    total_debt = total_debt / 1e7,
    free_cash_flow = free_cash_flow / 1e7,
    operating_cash_flow = operating_cash_flow / 1e7
WHERE market_cap > 1000000;  -- only convert rows still in rupees

# 4. Convert insider_transactions value to crores
UPDATE insider_transactions SET value = value / 1e7 WHERE value > 1000000;

# 5. Convert mf_scheme_holdings from lakhs to crores
ALTER TABLE mf_scheme_holdings RENAME COLUMN market_value_lakhs TO market_value_cr;
UPDATE mf_scheme_holdings SET market_value_cr = market_value_cr / 100;

# 6. Convert daily_stock_data turnover from lakhs to crores
-- This is optional since turnover is rarely used in computations
-- Skip for now to avoid touching 3.7M rows
```

After migration, run Screener backfill for all 500 stocks to fill the gaps.

---

## Implementation Batches

### Batch 0: DB Snapshot (before any changes)
1. Copy the DB file: `cp ~/.local/share/flowtracker/flows.db ~/.local/share/flowtracker/flows.db.pre-p3b-backup`
2. Record row counts and data distribution for every table:
```bash
uv run python -c "
import sqlite3, json
conn = sqlite3.connect('~/.local/share/flowtracker/flows.db')
snapshot = {}
tables = [r[0] for r in conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM [{t}]').fetchone()[0]
    symbols = conn.execute(f'SELECT COUNT(DISTINCT symbol) FROM [{t}]').fetchone()[0] if 'symbol' in [c[1] for c in conn.execute(f'PRAGMA table_info([{t}])').fetchall()] else 0
    snapshot[t] = {'rows': count, 'symbols': symbols}
print(json.dumps(snapshot, indent=2))
conn.close()
" > ~/.local/share/flowtracker/pre-p3b-snapshot.json
```
3. Record specific metrics we'll verify after migration (Screener vs yfinance row counts, unit ranges, etc.)

### Batch 1: Migration + Cleanup (no code changes)
1. Run `migrate-units.py` to fix existing data
2. Verify with range checks
3. Compare row counts with pre-snapshot to confirm only expected deletions

### Batch 2: Scraper Fixes (prevent future contamination)
1. `fund_client.py` — add ÷1e7 for aggregate fields in `fetch_valuation_snapshot()`
2. `insider_client.py` — add ÷1e7 for value field
3. `fmp_client.py` — add ÷1e7 for market_cap/EV in `fetch_key_metrics()`
4. `backfill_fundamentals.py` — remove `fetch_annual_financials()` and yfinance quarterly path
5. `fund_client.py` — remove or deprecate `fetch_quarterly_results()` (Screener covers this)
6. Add validation layer to `store.py` upsert methods

### Batch 3: Computation Code Cleanup
1. `data_api.py` — remove `market_cap / 1e7` in `get_reverse_dcf()`
2. `data_api.py` — fix BFSI `bvps = net_worth * 1e7 / num_shares`
3. `screener_engine.py` — remove `/ 1e7` in insider scoring
4. `data_collector.py` — remove `/ 1e7` for mcap conversion
5. `compute-analytics.py` — verify all extractions still work

### Batch 4: Backfill + Recompute
1. Run `backfill-nifty250.py --step screener` for all 500 stocks (~25 min)
2. Run `compute-analytics.py` for all 500 stocks
3. Verify coverage: all 500 stocks should now have Screener data
4. Range-check all tables post-migration

### Batch 5: Documentation
1. Add unit documentation to `CLAUDE.md` and/or `store.py` docstring
2. Document the standard: monetary=crores, per-share=rupees, counts=raw

---

## Verification

```bash
# 1. No more rupee values in annual_financials
uv run python -c "
import sqlite3
conn = sqlite3.connect('~/.local/share/flowtracker/flows.db')
bad = conn.execute('SELECT COUNT(*) FROM annual_financials WHERE revenue > 1000000').fetchone()[0]
print(f'Rupee rows remaining: {bad} (should be 0)')
"

# 2. valuation_snapshot market_cap now in crores
uv run python -c "
import sqlite3
conn = sqlite3.connect('~/.local/share/flowtracker/flows.db')
row = conn.execute('SELECT market_cap FROM valuation_snapshot WHERE symbol=\"RELIANCE\" ORDER BY date DESC LIMIT 1').fetchone()
print(f'RELIANCE market_cap: {row[0]:,.0f} (should be ~18,00,000 Cr)')
"

# 3. BFSI BVPS correct
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
with ResearchDataAPI() as api:
    bfsi = api.get_bfsi_metrics('HDFCBANK')
    print(f'BVPS: {bfsi[\"years\"][0][\"book_value_per_share\"]} (should be ~682)')
    print(f'P/B: {bfsi[\"years\"][0][\"pb_ratio\"]} (should be ~2-3x)')
"

# 4. Reverse DCF still works (no more ÷1e7)
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
with ResearchDataAPI() as api:
    r = api.get_reverse_dcf('RELIANCE')
    print(f'Implied growth: {r[\"implied_growth_rate\"]} (should be ~14%)')
"

# 5. Range validation passes
uv run python -c "
import sqlite3
conn = sqlite3.connect('~/.local/share/flowtracker/flows.db')
# No annual_financials revenue > 2M Cr (= ₹200 trillion — doesn't exist)
bad = conn.execute('SELECT COUNT(*) FROM annual_financials WHERE revenue > 2000000').fetchone()[0]
print(f'Suspiciously large revenue rows: {bad} (should be 0)')
# No valuation_snapshot market_cap > 30M Cr  
bad2 = conn.execute('SELECT COUNT(*) FROM valuation_snapshot WHERE market_cap > 30000000').fetchone()[0]
print(f'Suspiciously large market_cap rows: {bad2} (should be 0)')
"
```

## Files Modified

| File | Changes |
|------|---------|
| `fund_client.py` | ÷1e7 for aggregate fields in fetch_valuation_snapshot |
| `insider_client.py` | ÷1e7 for value field |
| `fmp_client.py` | ÷1e7 for market_cap/EV in fetch_key_metrics |
| `backfill_fundamentals.py` | Remove annual_financials + quarterly yfinance paths |
| `store.py` | Add validation layer, column rename for mf_scheme_holdings |
| `data_api.py` | Remove ÷1e7 in reverse_dcf, fix BFSI bvps |
| `screener_engine.py` | Remove ÷1e7 in insider scoring |
| `data_collector.py` | Remove ÷1e7 for mcap |
| `scripts/migrate-units.py` | NEW — one-time data migration |
