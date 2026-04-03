# P-8: Dynamic WACC + Remaining Math Fixes

## Context

All financial computations use hardcoded discount rates (12% WACC non-BFSI, 14% CoE BFSI, 5% terminal growth, 15/20/30 PE multiples). Gemini review + Damodaran research confirmed these are wrong — a steel company and an IT company shouldn't share the same discount rate, and 5% terminal growth undervalues every Indian stock.

This plan replaces all hardcodes with stock-specific computed values using CAPM, synthetic credit rating, and historical PE bands. Also addresses remaining "partial" fixes from the Gemini math review.

## Verified Parameters (April 2026)

| Parameter | Value | Source |
|-----------|-------|--------|
| India ERP | 7.46% | Damodaran July 2025 |
| 10Y G-sec | 7.13% | macro_daily (live) |
| Terminal growth | Rf - 0.5% ≈ 6.5% | Damodaran rule: g ≤ Rf |
| Statutory tax | 25.17% | Section 115BAA |
| Nifty 500 ticker | `^CRSLDX` | yfinance (verified, 3Y data) |
| Nifty 50 ticker | `^NSEI` | yfinance (verified, 3Y data) |

---

## Phase 1: Nifty Index Price Series (~2h)

**Why first:** Beta computation needs a benchmark return series.

### 1A. New table in `store.py`

```sql
CREATE TABLE IF NOT EXISTS index_daily_prices (
    date TEXT NOT NULL,
    index_ticker TEXT NOT NULL,
    close REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, index_ticker)
);
```

### 1B. Store methods in `store.py`

- `upsert_index_daily_prices(records: list[dict]) -> int`
- `get_index_prices(index_ticker: str, days: int = 800) -> list[dict]`

### 1C. Fetch in `macro_client.py`

Add `fetch_index_prices(tickers=["^CRSLDX", "^NSEI"], period="3y")` — follows existing yfinance pattern (lines 33-66).

### 1D. CLI command + cron

- New command: `flowtrack macro fetch-index`
- Add to `daily-fetch.sh` after macro fetch

### 1E. Backfill script

`scripts/backfill-index-prices.py` — one-time 3Y backfill for `^CRSLDX` and `^NSEI`.

**Files:** `store.py`, `macro_client.py`, `macro_commands.py`, `daily-fetch.sh`
**New:** `scripts/backfill-index-prices.py`

---

## Phase 2: WACC Computation Module (~4h)

**New file:** `flowtracker/research/wacc.py` — pure functions, no store dependency.

### Constants

```python
INDIA_ERP = 0.0746           # Damodaran July 2025
ERP_LAST_UPDATED = "2025-07"
STATUTORY_TAX_RATE = 0.2517
SMALL_CAP_THRESHOLD_CR = 5000
SMALL_CAP_PREMIUM = 0.03
BETA_FLOOR, BETA_CAP = 0.5, 2.5
```

### ICR-to-Spread Table (Damodaran EM)

```
ICR < 0.5  → D (1200bps)    ICR 6-7.5   → A- (175bps)
ICR 0.5-0.8 → C (1050bps)   ICR 7.5-10  → A (150bps)
ICR 0.8-1.25 → CC (900bps)  ICR 10-15   → A+ (125bps)
ICR 1.25-1.5 → CCC (750bps) ICR 15-20   → AA (100bps)
ICR 1.5-2   → B- (600bps)   ICR 20+     → AAA (75bps)
ICR 2-2.5   → B (500bps)
ICR 2.5-3   → B+ (400bps)
ICR 3-3.5   → BB (350bps)
ICR 3.5-4.5 → BB+ (300bps)
ICR 4.5-6   → BBB (200bps)
```

### Functions

| Function | Input | Output |
|----------|-------|--------|
| `compute_nifty_beta(stock_prices, index_prices)` | 2Y daily prices | `{raw_beta, blume_beta, r_squared}` |
| `compute_cost_of_equity(rf, beta, erp, mcap)` | CAPM inputs | `{ke, components}` |
| `compute_cost_of_debt(interest, borrowings, pbt, rf)` | ICR → synthetic rating | `{kd_pretax, kd_posttax, rating, icr}` |
| `compute_wacc(ke, kd_posttax, mcap, borrowings)` | Ke + Kd + weights | `{wacc, equity_weight, debt_weight}` |
| `compute_terminal_growth(rf)` | Rf | `Rf - 0.5%` (floor 4%, cap Rf) |
| `compute_dynamic_pe(pe_band)` | Historical PE band | `{low: p25, mid: median, high: p75}` |
| `get_reliability_flags(industry, mcap, ...)` | Various | `["holdco_or_cyclical", ...]` |
| `build_wacc_params(symbol, ...)` | All data | Full WACC result dict |

### Beta computation details

- Align stock + index on common dates
- Resample to **weekly** (Friday close)
- Compute log returns
- OLS: `stock_return = α + β × index_return + ε`
- Blume adjustment: `0.67 × raw + 0.33 × 1.0`
- Floor 0.5, cap 2.5

**Files:** `flowtracker/research/wacc.py` (new)

---

## Phase 3: Integration (~3h)

### 3A. New method in `data_api.py`

`get_wacc_params(symbol)` — fetches all data from store, delegates to `wacc.build_wacc_params()`.

### 3B. Modify `get_reverse_dcf` in `data_api.py`

Replace:
```python
discount_rate = 0.14  # BFSI
discount_rate = 0.12  # non-BFSI
terminal_g = 0.05
```

With:
```python
wacc_data = self.get_wacc_params(symbol)
discount_rate = wacc_data["ke"] if is_bfsi else wacc_data["wacc"]
terminal_g = wacc_data["terminal_growth"]
```

Add `wacc_params` to return dict.

### 3C. Modify `projections.py`

Add `pe_multiples: dict | None = None` parameter to `build_projections()`.
Replace hardcoded `pe_low=15, pe_mid=20, pe_high=30` with historical values from PE band.

Update `get_financial_projections()` in `data_api.py` to pass dynamic PE.

### 3D. Fallback chain

When data is missing, fall back gracefully:
1. No index prices → use yfinance beta (wrong benchmark but something), flag `beta_wrong_benchmark`
2. No stock prices → use sector median beta, flag `beta_sector_proxy`
3. No financials for CoD → use Interest/Borrowings, flag `kd_crude`
4. No G-sec → use 7.0% default, flag `rf_default`
5. Total fallback → hardcoded 14%/12%/5%, flag `all_defaults`

**Files:** `data_api.py`, `projections.py`

---

## Phase 4: MCP Tool + Prompts (~1h)

### 4A. New tool in `tools.py`

`get_wacc_params` — expose dynamic WACC computation to agents.

### 4B. Update prompts

- Valuation agent workflow: mention `get_wacc_params` for discount rate transparency
- Existing tool descriptions: note dynamic WACC in reverse DCF and projections

**Files:** `tools.py`, `prompts.py`

---

## Phase 5: Batch Analytics (~2h)

### 5A. Add WACC to `compute-analytics.py`

Store computed WACC, Ke, Kd, beta, terminal_growth in `analytical_snapshot`.

### 5B. Migrate `analytical_snapshot` table

Add columns: `wacc`, `ke`, `kd_pretax`, `beta_blume`, `beta_raw`, `terminal_growth`, `wacc_flags`.

**Files:** `scripts/compute-analytics.py`, `store.py`

---

## Phase 6: Remaining "Partial" Fixes from Gemini Review (~2h)

These were deferred earlier. Now is the right time:

### 6A. Beneish M-Score: flag when SGI is the dominant contributor

Indian research (NSE500 studies) confirmed the original US coefficients work — stocks with M-Score > -1.78 deliver lower returns in India too. The issue is SGI (Sales Growth Index) — Indian growth companies naturally score higher on SGI, pushing the total M-Score up without actual manipulation.

Fix: When SGI contributes >40% of the positive M-Score components, add a flag: `"sgi_dominant": true` with the SGI contribution percentage. The agent can then note "M-Score elevated primarily by high revenue growth, not accounting red flags."

**File:** `data_api.py` `get_beneish_score()`

### 6B. Capital allocation: investments caveat for BFSI

For BFSI, `investments` ARE the core business (loan book), not idle cash. Flag this.

**File:** `data_api.py` `get_capital_allocation()`

### 6C. Piotroski NIM: use average total_assets

Currently uses point-in-time `total_assets`. Use `(ta_t + ta_t1) / 2` for NIM proxy denominator.

**File:** `data_api.py` `get_piotroski_score()`

---

## Verification

Run against 5 stocks spanning different profiles:

| Stock | Type | Expected WACC range | Key check |
|-------|------|-------------------|-----------|
| TCS | Large IT | 10-12% | Low beta, near-zero debt |
| SBIN | BFSI | 13-15% CoE | No WACC, CoE only |
| RELIANCE | Conglomerate | 11-13% | High debt, moderate beta |
| INDIAMART | Small-cap tech | 14-17% | Small-cap premium |
| TATASTEEL | Cyclical | 13-16% | High beta, reliability flag |

```bash
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
with ResearchDataAPI() as api:
    for sym in ['TCS', 'SBIN', 'RELIANCE', 'INDIAMART', 'TATASTEEL']:
        w = api.get_wacc_params(sym)
        print(f'{sym}: WACC={w.get(\"wacc\")}, Ke={w.get(\"ke\")}, beta={w.get(\"beta\",{}).get(\"blume\")}, Tg={w.get(\"terminal_growth\")}, flags={w.get(\"reliability_flags\")}')
"
```

Also verify reverse DCF outputs change sensibly and terminal growth ≈ 6.5%.

---

## Dependency Graph

```
Phase 1 (Index data) ──┐
                        ├──► Phase 2 (wacc.py) ──► Phase 3 (Integration) ──► Phase 4 (Tool/Prompt)
                        │                                                  ──► Phase 5 (Batch)
Phase 6 (Partial fixes) ─── independent, can run in parallel with any phase
```

## Estimated Total: ~14h

| Phase | Hours | Parallelizable |
|-------|-------|---------------|
| 1. Index data | 2 | Yes (with Phase 6) |
| 2. wacc.py | 4 | Yes (with Phase 1) |
| 3. Integration | 3 | Blocked by 1+2 |
| 4. Tool/Prompt | 1 | Blocked by 3 |
| 5. Batch | 2 | Blocked by 3 |
| 6. Partial fixes | 2 | Independent |
