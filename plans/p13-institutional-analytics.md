# P-13: Institutional Analytics — Marcellus/Ambit Framework Rules

## Context

Extracted 18 analytical rules from Marcellus CCP and Ambit Good & Clean frameworks. 6 require code (pre-computed metrics), 7 are prompt rules, 5 need data we don't have (deferred). This plan covers all implementable items.

## What Already Exists (no work needed)

| Metric | Status | Location |
|--------|--------|----------|
| CFO/EBITDA ratio | **Already computed** | `get_earnings_quality()` → `eq_cfo_pat_3y/5y` in analytical_snapshot |
| CWIP/Gross Block | **Already computed** | `get_capex_cycle()` → `capex_cwip_to_nb` in analytical_snapshot |
| Cash as % of market cap | **Already computed** | `get_capital_allocation()` → `cash_pct_of_market_cap` |
| Depreciation as % of revenue | **Already computed** | `get_common_size_pl()` → `cs_depreciation_pct` |
| Share dilution (YoY) | **In Piotroski F-Score** | F-score criterion 7 — pass/fail, not stored as standalone |

## Package A: New Computed Metrics [M]

### A1. ROCE × Reinvestment Rate (Marcellus Core Filter)

**Why:** Companies need BOTH high ROCE AND high reinvestment to compound. High ROCE + low reinvestment = cash cow. High reinvestment + low ROCE = value destruction.

**Data available:** `annual_financials` has `operating_profit`, `tax`, `net_block`, `cwip`, `depreciation`, `cfo`, `dividend_amount`. ROCE already computed via `fund_models.AnnualFinancials.roce`.

**New method in data_api.py:**
```python
def get_reinvestment_analysis(self, symbol: str) -> dict:
    """ROCE × Reinvestment Rate for 5-year trend. Marcellus' core compounder filter."""
    financials = self._store.get_annual_financials(symbol, limit=6)  # 6 years for 5Y deltas
    results = []
    for i, curr in enumerate(financials[:-1]):
        prev = financials[i + 1]
        # NOPAT = operating_profit × (1 - tax_rate)
        tax_rate = curr.tax / curr.profit_before_tax if curr.profit_before_tax else 0.25
        nopat = curr.operating_profit * (1 - tax_rate)
        # Capex = delta_net_block + delta_cwip + depreciation
        capex = (curr.net_block - prev.net_block) + (curr.cwip - prev.cwip) + curr.depreciation
        # Reinvestment rate = capex / NOPAT (bounded 0-1)
        reinv_rate = max(0, min(capex / nopat, 1)) if nopat > 0 else 0
        roce = curr.roce  # already a property on the model
        results.append({
            "fy": curr.fiscal_year_end, "roce": roce, "reinv_rate": reinv_rate,
            "roce_x_reinv": roce * reinv_rate,  # compound growth potential
            "nopat_cr": nopat, "capex_cr": capex,
        })
    avg_roce_x_reinv = mean([r["roce_x_reinv"] for r in results[:3]])
    return {
        "years": results, "avg_3y_roce_x_reinv": avg_roce_x_reinv,
        "signal": "compounder" if avg_roce_x_reinv > 10 else "cash_cow" if results[0]["roce"] > 15 else "challenged",
    }
```

**Store changes:** Add to `analytical_snapshot`:
- `reinv_rate_avg_3y REAL` — 3-year average reinvestment rate
- `roce_x_reinv_avg_3y REAL` — 3-year average ROCE × Reinvestment Rate
- `reinv_signal TEXT` — "compounder" / "cash_cow" / "challenged"

**compute-analytics.py:** Add after capex_cycle computation (line ~160).

### A2. Equity Dilution Rate

**Why:** Shares outstanding growing >5% in 3 years (without merger) = dilutive for per-share returns.

**Data available:** `annual_financials.num_shares` for 10Y.

**New method in data_api.py:**
```python
def get_equity_dilution(self, symbol: str) -> dict:
    financials = self._store.get_annual_financials(symbol, limit=4)  # 4 years for 3Y CAGR
    if len(financials) < 2:
        return {"error": "Insufficient data"}
    latest = financials[0].num_shares
    oldest = financials[-1].num_shares
    years = len(financials) - 1
    if oldest and latest and oldest > 0:
        cagr = ((latest / oldest) ** (1 / years) - 1) * 100
        return {
            "shares_latest_mn": latest, "shares_3y_ago_mn": oldest,
            "dilution_cagr_pct": round(cagr, 2),
            "signal": "dilutive" if cagr > 2 else "neutral" if cagr > -1 else "buyback",
        }
    return {"error": "Missing share count data"}
```

**Store changes:** Add `dilution_cagr_3y REAL`, `dilution_signal TEXT`.

### A3. Cash Yield Sanity Check

**Why:** If a company reports ₹500 Cr cash but earns only 2% yield (vs 7% risk-free), the cash may not exist, may be restricted, or may be customer advances.

**Data available:** `annual_financials.other_income`, `annual_financials.cash_and_bank`, `annual_financials.investments`.

**New method in data_api.py:**
```python
def get_cash_yield_check(self, symbol: str) -> dict:
    fin = self._store.get_annual_financials(symbol, limit=1)
    if not fin:
        return {"error": "No data"}
    f = fin[0]
    total_cash = (f.cash_and_bank or 0) + (f.investments or 0)
    if total_cash > 0:
        implied_yield = (f.other_income or 0) / total_cash * 100
        risk_free = 7.0  # approximate 10Y G-sec
        return {
            "cash_and_investments_cr": total_cash,
            "other_income_cr": f.other_income,
            "implied_yield_pct": round(implied_yield, 2),
            "risk_free_pct": risk_free,
            "gap_pct": round(implied_yield - risk_free, 2),
            "signal": "suspicious" if implied_yield < 3.0 and total_cash > 100 else "normal",
        }
    return {"signal": "no_cash"}
```

**Store changes:** Add `cash_yield_pct REAL`, `cash_yield_signal TEXT`.

### A4. Depreciation Rate Volatility

**Why:** High volatility in depreciation rate (depreciation/net_block) across years signals accounting flexibility abuse — management changing useful life estimates to manage earnings.

**Data available:** `annual_financials.depreciation`, `annual_financials.net_block` for 10Y.

**New method in data_api.py:**
```python
def get_depreciation_volatility(self, symbol: str) -> dict:
    financials = self._store.get_annual_financials(symbol, limit=6)
    rates = []
    for f in financials:
        gross_block_approx = (f.net_block or 0) + (f.depreciation or 0)  # rough proxy
        if gross_block_approx > 0:
            rates.append(f.depreciation / gross_block_approx * 100)
    if len(rates) >= 3:
        avg = mean(rates)
        std = stdev(rates) if len(rates) > 1 else 0
        cv = std / avg * 100 if avg > 0 else 0
        return {
            "depr_rates": rates, "avg_pct": round(avg, 2), "std_pct": round(std, 2),
            "cv_pct": round(cv, 2),
            "signal": "volatile" if cv > 25 else "stable",
        }
    return {"error": "Insufficient data"}
```

**Store changes:** Add `depr_rate_cv REAL`, `depr_rate_signal TEXT`.

---

## Package B: Prompt Rules (no code) [S]

Add to specialist Key Rules sections. All use data already available from tools.

### B1. Moat Pricing Test → Business Agent
```
- **Moat Pricing Test (Marcellus):** Ask: "Can a competitor offer a product 1/3rd cheaper and still have no impact on this company's profitability or market share?" If yes = wide moat (pricing power is irrelevant because the moat is elsewhere — brand, switching costs, network effects). If no = narrow/none (moat depends on pricing, vulnerable to undercutting).
```

### B2. Lethargy Score → Business Agent
```
- **Lethargy Score (Marcellus):** Assess 3 dimensions of management dynamism: (1) Is the company incrementally deepening existing moats? (2) Is it experimenting with new revenue growth drivers or adjacent markets? (3) Is it attempting radical disruption of its own industry? Companies that score low on all 3 are at risk of competitive obsolescence. Source from concall commentary and recent strategic initiatives.
```

### B3. Succession Planning → Business + Risk Agent
```
- **Succession Planning (Marcellus):** For promoter-led companies, assess: (1) Decentralized execution vs CEO-dependent operations, (2) CXO quality and tenure (>10 years at the firm = institutional memory), (3) Historical evidence of smooth CXO transitions, (4) Board independence — truly independent directors, not promoter associates. Promoter-led companies without succession planning trade at a hidden "key-man discount."
```

### B4. Volume vs Price Decomposition → Business Agent (make universal)
```
- **Volume vs Price Growth:** Always decompose revenue growth into volume growth + price/realization growth when data is available (from concall commentary or segment data). Pure price growth without volume = demand destruction risk. Volume growth > revenue growth = mix deterioration. This applies to ALL sectors, not just FMCG.
```

### B5. Capital Allocation Cycle → Financial Agent
```
- **Capital Allocation Cycle (Ambit):** Evaluate the full 6-step cycle: (A) Incremental capex YoY → (B) Conversion to sales growth → (C) Pricing discipline (PBIT margin maintained) → (D) Capital employed turnover efficiency → (E) Balance sheet discipline (no equity dilution, controlled D/E) → (F) Cash generation (CFO positive). A "great" capital allocator executes all 6 steps; "mediocre" breaks the chain at C or D.
```

### B6. Political Connectivity Flag → Risk Agent
```
- **Political Connectivity (Ambit):** Flag if >50% of revenue comes from government contracts/PSU orders WITHOUT a visible technology, cost, or efficiency moat. Firms whose competitive advantage is primarily political connectivity seldom outperform long-term — when the political cycle turns, the moat vanishes. This is distinct from PSU companies (which have structural advantages); it applies to private companies dependent on government patronage.
```

### B7. CXO Churn → Risk Agent (as open question)
```
- **CXO Churn:** If data is available from filings or concalls, check for CFO/CEO/COO changes in the last 3 years. High C-suite turnover (>2 departures in 3 years) = management instability flag. If not available from tools, pose as open question for web research.
```

---

## Package C: Deferred (needs new data sources)

| Rule | Blocker | Future Action |
|------|---------|---------------|
| Auditor remuneration growth | Not in Screener/yfinance data | Parse from annual report PDFs |
| Related party transaction amounts | Not structured | Parse from BSE annual report filings |
| Miscellaneous expense breakdown | Screener only shows "other expenses" aggregate | May be in Excel export detail |
| Gross block (vs net block) | Screener doesn't separate | Approximate as net_block + cumulative_depreciation |

---

## Implementation Plan

### Phase 1: Prompt rules (Package B) — immediate, no code
Add 7 rules to specialist prompts. 5 mins of editing.

### Phase 2: Compute metrics (Package A) — next session
1. Add 4 new methods to `data_api.py` (~100 lines total)
2. Add 8 new columns to `analytical_snapshot` schema in `store.py` + migration
3. Add 4 compute blocks to `scripts/compute-analytics.py`
4. Add unit tests for each method
5. Run `compute-analytics.py` to populate
6. Update `get_analytical_profile` tool to include new fields

### Files to Modify

| File | Changes |
|------|---------|
| `flowtracker/research/prompts.py` | 7 prompt rules (Package B) |
| `flowtracker/research/data_api.py` | 4 new compute methods (Package A) |
| `flowtracker/store.py` | 8 new columns + migration (Package A) |
| `scripts/compute-analytics.py` | 4 new compute blocks (Package A) |
| `tests/unit/test_data_api.py` | 4 new test classes (Package A) |

### Verification
1. `uv run python scripts/compute-analytics.py --symbol CDSL` — verify new metrics computed
2. `uv run flowtrack research data analytical_profile -s CDSL --raw | grep reinv` — fields present
3. `uv run pytest tests/ -m "not slow" -q` — all tests pass
4. Run thesis on a stock and verify agents reference new metrics
