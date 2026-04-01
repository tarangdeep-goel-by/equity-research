# P-2: Analytical Frameworks — Tier 1 Implementation Plan

> Context: Gemini review + internal audit identified 11 analytical gaps that real analysts use daily. All implementable from existing data — no new sources needed.
> Reviewed by: Gemini 3.1 Pro (2026-04-02) — 6 critical fixes applied.
> Project: `/Users/tarang/Documents/Projects/equity-research/flow-tracker/`
> Branch: TBD (worktree)

## Scope: 10 new MCP tools + 2 prompt updates across 5 files

### Gemini Review Fixes Applied
1. **Reverse DCF**: PV(FCFF@WACC) = EV, not MCap. Bridge: `MCap = EV + cash - borrowings`. Capex = `ΔNet_Block + ΔCWIP + depreciation` (not CFI). BFSI uses Ke (~14%), not WACC.
2. **Insurance carve-out**: Life/General Insurance excluded from BFSI metrics — different P&L template on Screener.
3. **Piotroski dilution**: Use `adjusted_shares = net_income / eps` instead of raw `num_shares` (handles bonus/splits).
4. **Bank leverage**: Use equity multiplier `total_assets / (equity_capital + reserves)` — deposits bundled in `other_liabilities`.
5. **Common Size P&L for banks**: Denominator = Total Income (`revenue + other_income`), not NII.
6. **Beneish M-Score**: Skip entirely if any variable is NULL (no defaults to 1.0).
7. **Earnings Quality**: Skip entirely for BFSI (CFO meaningless for banks, no NPA data).
8. **Price Performance**: Label as "Price Return (excl. dividends)".

---

## Features

### Feature 1: BFSI-Aware Routing
**Tool:** `get_bfsi_metrics(symbol)` in data_api.py + tools.py
**Prompt updates:** Financial + Valuation agent prompts
**Helper:** `_is_bfsi(industry)` check against `_BFSI_INDUSTRIES` set

**Insurance exclusion:** `Life Insurance` and `General Insurance` return `{skipped: true, reason: "Insurance reporting structure incompatible with standard BFSI metrics"}`.

Metrics derived from `annual_financials` (for banks, "revenue" = interest earned, "interest" = interest expended):
- NII = revenue - interest
- NIM proxy = NII / total_assets (×100 for %)
- ROA = net_income / total_assets (×100 for %)
- Cost-to-Income = (employee_cost + other_expenses_detail) / (NII + other_income) (×100)
- Book Value/Share = (equity_capital + reserves) / num_shares
- P/B = price / book_value_per_share
- Equity Multiplier = total_assets / (equity_capital + reserves) — true bank leverage including deposits
- Return: 5Y trend of all metrics + `is_bfsi: true` flag

BFSI industries (banks/NBFCs only): `{"Private Sector Bank", "Public Sector Bank", "Other Bank", "Non Banking Financial Company (NBFC)", "Financial Institution", "Other Financial Services", "Financial Products Distributor", "Financial Technology (Fintech)"}`

Insurance industries (excluded): `{"Life Insurance", "General Insurance"}`

NPA/CASA not available — note limitation in tool description.

**Registries:** FINANCIAL_AGENT_TOOLS, VALUATION_AGENT_TOOLS, RISK_AGENT_TOOLS

---

### Feature 2: Price Performance vs Benchmarks
**Tool:** `get_price_performance(symbol)` in data_api.py + tools.py
**Live fetch:** yfinance `^NSEI` (+ sector index if mappable)

Computation (labeled as "Price Return, excl. dividends"):
```
For each period (1M, 3M, 6M, 1Y):
  stock_return = (price_end - price_start) / price_start × 100
  nifty_return = (nifty_end - nifty_start) / nifty_start × 100
  excess_return = stock_return - nifty_return
```

Stock prices: from `daily_stock_data` table (3.7M rows).
Index prices: live yfinance fetch (cached in-memory, no table).

Industry → sector index mapping:
```python
_SECTOR_INDEX = {
    "Private Sector Bank": "^NSEBANK", "Public Sector Bank": "^NSEBANK",
    "IT - Software": "^CNXIT", "IT - Services": "^CNXIT",
    "Pharmaceuticals": "^CNXPHARMA", "FMCG": "^CNXFMCG",
    # ... extend as needed, default None
}
```

Return: `{periods: [{period: "1Y", stock_return: 25.3, nifty_return: 18.1, excess: 7.2, sector_return: 30.1}], return_type: "price_return_excl_dividends", outperformer: true}`

**Registries:** VALUATION_AGENT_TOOLS, TECHNICAL_AGENT_TOOLS, RESEARCH_TOOLS

---

### Feature 3: Earnings Quality
**Tool:** `get_earnings_quality(symbol)` in data_api.py + tools.py

**Skip for BFSI** — return `{skipped: true, reason: "Bank earnings quality requires NPA/Provisioning data, which is currently unavailable."}`.

From `annual_financials` (5-10Y):
```
EBITDA = net_income + tax + interest + depreciation
CFO_PAT = cfo / net_income  (skip if net_income <= 0)
CFO_EBITDA = cfo / EBITDA  (skip if EBITDA <= 0)
Accruals = (net_income - cfo) / total_assets
```

Signal: `"high_quality"` if 3Y avg CFO/PAT > 0.8, `"low_quality"` if < 0.5, `"warning"` if accruals > 0.10.

Return: per-year breakdown + 3Y/5Y averages + signal.

**Registries:** FINANCIAL_AGENT_TOOLS, RISK_AGENT_TOOLS

---

### Feature 4: Piotroski F-Score (0-9)
**Tool:** `get_piotroski_score(symbol)` in data_api.py + tools.py

Needs latest 2 years from `annual_financials`. Score 1 point each:

```
1. ROA > 0                    → net_income / total_assets > 0
2. CFO > 0                    → cfo > 0
3. ΔROA > 0                   → ROA_t > ROA_t-1
4. Accruals < 0               → cfo > net_income (cash > paper)
5. ΔLeverage < 0              → (borrowings/total_assets)_t < (borrowings/total_assets)_t-1
6. ΔCurrent Ratio > 0         → SKIP if no quarterly BS data; else use quarterly_balance_sheet
7. No dilution                → adjusted_shares_t <= adjusted_shares_t-1
                                 where adjusted_shares = net_income / eps
                                 (Screener adjusts historical EPS for splits/bonuses)
8. ΔGross Margin > 0          → For manufacturing: (rev - raw_material_cost)/rev improved
                                 For services: use operating_margin from quarterly_results
                                 For banks: use NII/total_assets (NIM proxy) improved
9. ΔAsset Turnover > 0        → (revenue/total_assets)_t > (revenue/total_assets)_t-1
```

**BFSI note:** Criteria 5 (leverage) is economically backwards for banks (growing banks increase deposits/leverage). Flag in output: `{criterion: "ΔLeverage", note: "BFSI: rising leverage may indicate growth, not weakness"}`.

For criterion 6: query `quarterly_balance_sheet` for latest 2 quarters. If unavailable, score N/A and report out of 8.
For criterion 8: check `_is_bfsi()` → use NIM proxy. Check `raw_material_cost IS NOT NULL` → use gross margin. Else → use operating_margin from `annual_financials`.

Return: `{score: 7, max_score: 9, criteria: [{name: "ROA positive", passed: true, value: 0.016}, ...], signal: "strong"}`

Signal: 8-9 = "strong", 5-7 = "moderate", 0-4 = "weak"

**Registries:** FINANCIAL_AGENT_TOOLS, RISK_AGENT_TOOLS, RESEARCH_TOOLS

---

### Feature 5: Beneish M-Score
**Tool:** `get_beneish_score(symbol)` in data_api.py + tools.py

**Skip entirely for BFSI** — return `{skipped: true, reason: "M-Score not applicable to banks/NBFCs"}`.

Formula: `M = -4.84 + 0.920×DSRI + 0.528×GMI + 0.404×AQI + 0.892×SGI + 0.115×DEPI - 0.172×SGAI + 4.679×TATA - 0.327×LVGI`

Variables (t = current year, t-1 = prior year):
```
DSRI = (receivables_t/revenue_t) / (receivables_t-1/revenue_t-1)

GMI  = gross_margin_t-1 / gross_margin_t
       → gross_margin = (revenue - raw_material_cost) / revenue
       → If raw_material_cost NULL: use (revenue - employee_cost - other_expenses_detail) / revenue

AQI  = (1 - (net_block_t + receivables_t + cash_and_bank_t)/total_assets_t) /
       (1 - (net_block_t-1 + receivables_t-1 + cash_and_bank_t-1)/total_assets_t-1)

SGI  = revenue_t / revenue_t-1

DEPI = (depreciation_t-1/(depreciation_t-1 + net_block_t-1)) /
       (depreciation_t/(depreciation_t + net_block_t))

SGAI = (sga_t/revenue_t) / (sga_t-1/revenue_t-1)
       → sga = selling_and_admin if not NULL, else employee_cost + other_expenses_detail

TATA = (net_income - cfo) / total_assets

LVGI = ((borrowings_t + other_liabilities_t)/total_assets_t) /
       ((borrowings_t-1 + other_liabilities_t-1)/total_assets_t-1)
```

**NULL handling (Gemini fix):** If ANY required variable cannot be computed (NULL numerator/denominator, division by zero), skip the entire M-Score. Return `{score: null, error: "Insufficient data: missing [variable_name]"}`. Do NOT default to 1.0 — this invalidates the regression coefficients.

Interpretation: M > -1.78 → "likely_manipulator" (red flag). M < -2.22 → "unlikely_manipulator". Between → "gray_zone".

Return: `{m_score: -2.45, signal: "unlikely_manipulator", variables: {DSRI: 1.05, GMI: 0.98, ...}, data_quality: "8/8 variables computed"}`

**Registries:** RISK_AGENT_TOOLS, FINANCIAL_AGENT_TOOLS

---

### Feature 6: Reverse DCF (Implied Growth)
**Tool:** `get_reverse_dcf(symbol)` in data_api.py + tools.py

**Gemini fix: EV→MCap bridge + correct capex + Ke for BFSI.**

Method: Binary search for growth rate `g` that makes DCF-implied market cap = actual market cap.

```python
market_cap = latest valuation_snapshot.market_cap
cash = latest annual_financials.cash_and_bank
borrowings = latest annual_financials.borrowings

# Capex = ΔNet_Block + ΔCWIP + Depreciation (NOT CFI — CFI includes acquisitions/FDs)
capex = (net_block_t - net_block_t-1) + (cwip_t - cwip_t-1) + depreciation_t
fcf = cfo - capex
# If fcf <= 0: use net_income as fallback

# For BFSI: fcf = net_income (CFO unreliable for banks)
# For BFSI: discount at Ke (cost of equity ~14%), NOT WACC
# For BFSI: PV(FCFE@Ke) = Market Cap directly (no EV bridge)

# Non-BFSI parameters
wacc = 0.12       # 12% — Indian large-cap WACC
terminal_g = 0.05  # 5% — nominal GDP growth
ke = 0.14          # 14% — Indian large-cap cost of equity (for BFSI)

# 10-year two-stage model
def dcf_value(g, discount_rate, base_cf):
    pv = sum(base_cf * (1+g)**n / (1+discount_rate)**n for n in range(1, 11))
    terminal = base_cf * (1+g)**10 * (1+terminal_g) / (discount_rate - terminal_g)
    pv += terminal / (1+discount_rate)**10
    return pv

if is_bfsi:
    # FCFE model: PV = Market Cap
    target = market_cap
    base_cf = net_income
    discount_rate = ke
else:
    # FCFF model: PV = EV, then bridge to MCap
    target = market_cap - cash + borrowings  # target EV
    base_cf = fcf
    discount_rate = wacc

# Binary search g in [-0.20, 0.60] until dcf_value(g) ≈ target
```

Context: compare implied_g with historical 3Y/5Y revenue CAGR from annual_financials.

Return: `{implied_growth_rate: 0.22, fcf_used: 15000, market_cap: 450000, model: "FCFF" | "FCFE", historical_3y_cagr: 0.15, historical_5y_cagr: 0.18, assessment: "Market expects 22% growth vs 15-18% historical — priced for acceleration"}`

**Registries:** VALUATION_AGENT_TOOLS, RESEARCH_TOOLS

---

### Feature 7: CWIP/Capex Tracking
**Tool:** `get_capex_cycle(symbol)` in data_api.py + tools.py

**Skip for BFSI** — return `{skipped: true}`.

From `annual_financials` (10Y):
```
cwip_to_netblock = cwip / net_block  (if net_block > 0)
fixed_asset_turnover = revenue / net_block
capex = (net_block_t - net_block_t-1) + (cwip_t - cwip_t-1) + depreciation
capex_intensity = capex / revenue
netblock_growth_yoy = (net_block_t - net_block_t-1) / net_block_t-1
```

Phase detection:
- "Investing" — CWIP/NetBlock > 0.3 AND CWIP growing
- "Commissioning" — CWIP declining AND NetBlock growing > 10%
- "Harvesting" — CWIP/NetBlock < 0.1 AND asset turnover improving
- "Mature" — Stable CWIP and NetBlock

Return: per-year metrics + current phase + narrative.

**Registries:** FINANCIAL_AGENT_TOOLS, RESEARCH_TOOLS

---

### Feature 8: Consensus Revenue Estimates
**Fetch:** `fetch_revenue_estimates(symbol)` in estimates_client.py
**Tool:** `get_revenue_estimates(symbol)` in data_api.py + tools.py

From yfinance `ticker.revenue_estimate` DataFrame:
```
Columns: avg, low, high, numberOfAnalysts, yearAgoRevenue, growth
Periods: 0q, +1q, 0y, +1y
Convert avg/low/high from raw INR to crores (÷1e7)
```

Live fetch, no table. **Note:** Coverage limited to ~Nifty 100-150. If empty DataFrame, return `{estimates_available: false, message: "No analyst consensus data available for this ticker."}`.

Return: `{periods: [{period: "0y", avg_cr: 241786, low_cr: 193159, high_cr: ..., growth: -0.16, num_analysts: ...}]}`

**Registries:** VALUATION_AGENT_TOOLS, FINANCIAL_AGENT_TOOLS, RESEARCH_TOOLS

---

### Feature 9: Growth Estimates vs Index
**Fetch:** `fetch_growth_estimates(symbol)` in estimates_client.py
**Tool:** `get_growth_estimates(symbol)` in data_api.py + tools.py

From yfinance `ticker.growth_estimates` DataFrame:
```
Columns: stockTrend, indexTrend
Periods: 0q, +1q, 0y, +1y, LTG
```

Live fetch, no table. **Same coverage caveat as Feature 8** — graceful empty handling.

Return: `{periods: [{period: "0y", stock_growth: 0.11, index_growth: 0.17, vs_index: "underperforming"}, ...], ltg: {stock: null, index: 0.122}}`

**Registries:** VALUATION_AGENT_TOOLS, RESEARCH_TOOLS

---

### Feature 10: Moat Taxonomy (Prompt-Only)
**Update:** Business Agent prompt in prompts.py

Add structured moat analysis section:
```
## Moat Classification (Morningstar Framework)
For EVERY stock, classify the competitive advantage using these 5 pillars:
1. **Switching Costs** — How painful is it for customers to leave?
2. **Network Effects** — Does the product get better with more users?
3. **Intangible Assets** — Patents, regulatory licenses, brand power?
4. **Cost Advantage** — Scale, proprietary process, access to cheap inputs?
5. **Efficient Scale** — Natural monopoly or oligopoly limiting competition?

You MUST output a structured moat assessment:
- Moat Width: None / Narrow / Wide
- Primary Moat Source: [one of the 5 pillars]
- Evidence: [specific data-backed evidence]
- Moat Trend: Strengthening / Stable / Eroding
```

---

### Feature 11: Common Size P&L
**Tool:** `get_common_size_pl(symbol)` in data_api.py + tools.py

From `annual_financials` (10Y), express as % of revenue:
```python
For each year:
  raw_material_pct = raw_material_cost / revenue × 100  (if not NULL)
  employee_pct = employee_cost / revenue × 100
  other_expenses_pct = other_expenses_detail / revenue × 100
  depreciation_pct = depreciation / revenue × 100
  interest_pct = interest / revenue × 100
  tax_pct = tax / revenue × 100
  net_margin_pct = net_income / revenue × 100
  ebit_pct = (profit_before_tax + interest - other_income) / revenue × 100

For BFSI: denominator = Total Income (revenue + other_income), NOT NII
  (Gemini fix: dividing interest expended by NII is meaningless)
```

Return: per-year breakdown + highlight: biggest cost, fastest-growing cost, margin driver.

**Registries:** FINANCIAL_AGENT_TOOLS, RESEARCH_TOOLS

---

## Implementation Batches

### Batch 1: Parallel worktree-isolated subagents (6 computation tools)
- **Subagent A:** Features 3 + 4 + 5 (Earnings Quality + F-Score + M-Score)
  - Files: data_api.py, tools.py
  - Key: BFSI skips for F3/F5, adjusted_shares for F4, NULL→skip for F5
- **Subagent B:** Features 6 + 7 + 11 (Reverse DCF + CWIP + Common Size)
  - Files: data_api.py, tools.py
  - Key: EV→MCap bridge for F6, Ke for BFSI, Total Income denominator for F11

### Batch 2: Parallel worktree-isolated subagents (3 fetch tools)
- **Subagent C:** Features 8 + 9 (Revenue estimates + Growth estimates)
  - Files: estimates_client.py, data_api.py, tools.py
  - Key: Graceful empty handling for low-coverage stocks
- **Subagent D:** Feature 2 (Price performance vs benchmarks)
  - Files: data_api.py, tools.py
  - Key: Label as price return excl. dividends

### Batch 3: Sequential on merged code
- Feature 1 (BFSI routing) — data_api.py, tools.py, prompts.py
  - Key: Insurance carve-out, equity multiplier for leverage
- Feature 10 (Moat taxonomy) — prompts.py only

### Integration
- Merge all → verify imports → live test HDFCBANK (bank) + RELIANCE (non-bank) + LICI (insurance, should skip)

## Verification

```bash
# Import check
uv run python -c "from flowtracker.research.tools import get_earnings_quality, get_piotroski_score, get_beneish_score, get_reverse_dcf, get_capex_cycle, get_common_size_pl, get_price_performance, get_revenue_estimates, get_growth_estimates, get_bfsi_metrics; print('All 10 tools OK')"

# Live test — non-bank
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
api = ResearchDataAPI()
print('F-Score:', api.get_piotroski_score('RELIANCE'))
print('M-Score:', api.get_beneish_score('RELIANCE'))
print('Earnings Q:', api.get_earnings_quality('RELIANCE')['signal'])
rdcf = api.get_reverse_dcf('RELIANCE')
print('Reverse DCF:', rdcf['implied_growth_rate'], rdcf['model'])
print('CWIP:', api.get_capex_cycle('RELIANCE')['phase'])
api.close()
"

# Live test — bank (BFSI routing)
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
api = ResearchDataAPI()
bfsi = api.get_bfsi_metrics('HDFCBANK')
print('BFSI:', bfsi['nim_pct'], bfsi['roa_pct'], bfsi['equity_multiplier'])
print('M-Score:', api.get_beneish_score('HDFCBANK'))  # should skip
print('CWIP:', api.get_capex_cycle('HDFCBANK'))  # should skip
print('Earnings Q:', api.get_earnings_quality('HDFCBANK'))  # should skip
rdcf = api.get_reverse_dcf('HDFCBANK')
print('Reverse DCF:', rdcf['implied_growth_rate'], rdcf['model'])  # should be FCFE
print('F-Score:', api.get_piotroski_score('HDFCBANK'))  # bank-adapted
api.close()
"

# Live test — insurance (should skip BFSI tools)
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
api = ResearchDataAPI()
print('BFSI:', api.get_bfsi_metrics('LICI'))  # should return skipped
api.close()
"

# Price performance
uv run python -c "
from flowtracker.research.data_api import ResearchDataAPI
api = ResearchDataAPI()
perf = api.get_price_performance('HDFCBANK')
print('1Y return:', perf['periods'][-1])
print('Return type:', perf['return_type'])
api.close()
"
```

## Files Modified
| File | Changes |
|------|---------|
| `research/data_api.py` | +10 methods, `_BFSI_INDUSTRIES` + `_INSURANCE_INDUSTRIES` constants, `_is_bfsi()` + `_is_insurance()` helpers |
| `research/tools.py` | +10 MCP tools, registry updates for 6 agent tool lists |
| `research/prompts.py` | BFSI framework in Financial/Valuation agent, Moat taxonomy in Business agent |
| `estimates_client.py` | +2 fetch methods (revenue_estimates, growth_estimates) |

## Total: ~60 MCP tools after this phase (currently ~50)
