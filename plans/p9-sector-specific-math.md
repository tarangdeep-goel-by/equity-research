# P-9: Sector-Specific Math & Injections

## Context

Eval loop exposed that only BFSI has a dedicated analytical injection. Other sectors use generic frameworks, leading to errors:
- Metals PE cited at cycle trough (classic trap)
- Reverse DCF applied to banks/insurance (invalid)
- CFO/FCF cited for brokers (client money distorts)
- Insurance gets no specialized framework at all

Gemini grading confirmed: agents produce A/A+ work when the framework is correct, B+ when sector-specific guidance is missing (GROWW risk report).

## Approach

**Math in code, guidance in prompts.** Pre-compute sector-specific metrics in `data_api.py`, serve them via existing tools. Add prompt injections (like BFSI) for sectors where standard metrics must be excluded. Light prompt warnings for sectors where standard framework works but needs caveats.

## Existing Infrastructure

| Component | What it does | Reusable? |
|-----------|-------------|-----------|
| `_is_bfsi()` / `_is_insurance()` | Sector detection from Screener industry | Yes — extend pattern |
| `_build_bfsi_injection()` | Dynamic prompt block injected for bank stocks | Template for new injections |
| `build_specialist_prompt()` | Assembles prompt with dynamic injections | Add new injection hooks |
| `sector_kpis.py` | 116 KPIs across 15 sectors for concall extraction | KPIs already defined |
| `get_bfsi_metrics()` | Pre-computes NIM, ROA, C/I, P/B, CD ratio from annual financials | Template for new methods |
| Annual financials fields | revenue, net_income, borrowings, depreciation, operating_profit, cfo, cfi, receivables, inventory, cash_and_bank, total_assets, other_assets, investments | Primary data source |
| `valuation_snapshot` | pe_trailing, ev_ebitda, pb_ratio, dividend_yield, total_debt, total_cash, roe | Secondary data source |
| `macro_snapshot` | G-sec yield, USD/INR, crude | For power/utilities spread calc |

## Tiers

### Tier 1: Full Injection (like BFSI) — new `get_X_metrics()` + prompt injection + exclusions

#### 1A. Insurance
**Why full:** Insurance P&L/BS is as different from manufacturing as banking is. PE/EBITDA/FCF/working capital all meaningless.

**New method: `get_insurance_metrics(symbol)`**
Compute from annual_financials + sector_kpis:
- Solvency ratio (from sector_kpis concall data)
- ROE, ROA (from annual financials — valid for insurance)
- Opex ratio: `(employee_cost + other_expenses) / revenue`
- Growth: premium growth YoY from annual revenue

Concall-dependent (surface if available, flag as open question if not):
- VNB, VNB margin, APE (life)
- Combined ratio, loss ratio, expense ratio (general)
- Persistency 13th/61st month (life)
- Embedded Value (life) — for P/EV computation

**New injection: `_build_insurance_injection()`**
- Exclude: EBITDA, EBIT margin, ROCE, FCF, standard DCF, working capital, inventory, capex cycle
- Life valuation: P/EV (Price ÷ Embedded Value per share), P/VNB
- General valuation: P/B, target P/E
- Key metrics: VNB margin (life), Combined Ratio (general), Persistency, Solvency
- Add to `_insurance_agents` set (same agents as BFSI)

**Detection:** `_is_insurance()` already exists in data_api.py

#### 1B. Real Estate
**Why full:** Revenue recognition (% completion vs completed contract) distorts PE/EPS/ROE. NAV-based valuation is standard.

**New method: `get_realestate_metrics(symbol)`**
Compute from annual_financials:
- NAV per share: `(total_assets - borrowings - other_liabilities) / num_shares × 1e7`
- P/NAV: `price / nav_per_share`
- Net Debt/Equity: `(borrowings - cash_and_bank) / (equity_capital + reserves)`
- Inventory months: `inventory / (revenue / 12)` — for unsold stock

Concall-dependent (surface if available):
- Pre-sales value/volume, collections, realization per sqft, launch pipeline

**New injection: `_build_realestate_injection()`**
- Exclude: PE, EPS, ROE, ROCE, standard DCF, FCF
- Valuation: P/NAV (primary), EV/EBITDA (for rental/commercial only)
- Key metrics: Pre-sales momentum, realization per sqft, collection efficiency, net debt trajectory

**Detection:** New `_is_realestate(symbol)` — match industries: "Real Estate", "Construction - Real Estate"

---

### Tier 2: Medium Injection — prompt injection + exclusions, lighter compute

#### 2A. Metals/Mining
**Compute in `get_common_size_pl()` or new helper:**
- Net Debt/EBITDA: `(borrowings - cash_and_bank) / (operating_profit + depreciation)`
- Already have: EV/EBITDA from valuation_snapshot

**Injection: `_build_metals_injection()`**
- WARNING: "PE is a cyclical trap — lowest PE often marks commodity cycle peak. Use mid-cycle EV/EBITDA or P/B at trough instead."
- Exclude: Standard PE-based valuation in isolation
- Emphasize: Net Debt/EBITDA, commodity price sensitivity, capex cycle, dividend yield
- Detection: `_is_metals(symbol)` — match industries containing "Mining", "Metals", "Steel", "Aluminium", "Copper", "Zinc"

#### 2B. Telecom
**Compute:**
- OpFCF: `operating_cf - capital_expenditure` (from quarterly_cash_flow)
- Capex/Revenue: `abs(cfi) / revenue` (from annual_financials)
- Net Debt/EBITDA (same formula as metals)

**Injection: `_build_telecom_injection()`**
- Exclude: PE/PAT margin (spectrum amortization distorts)
- Emphasize: EV/EBITDA, OpFCF, ARPU, subscriber growth, capex intensity
- SOTP for conglomerates (Airtel = mobile + towers + broadband + enterprise)
- Detection: `_is_telecom(symbol)` — match "Telecom", "Telecommunication"

#### 2C. Power/Utilities
**Compute:**
- Dividend yield vs G-sec spread: `dividend_yield - gsec_10y_yield` (gsec from macro_snapshot)
- Regulated ROE framework: Justified P/B = ROE / CoE

**Injection: `_build_power_injection()`**
- Exclude: Revenue growth (fuel pass-through creates noise), EBITDA margin % (same reason)
- Emphasize: P/B vs regulated ROE, dividend yield vs G-sec spread, PLF/PAF, AT&C losses
- Detection: `_is_power(symbol)` — match "Power Generation", "Power Distribution", "Power Trading"

#### 2D. Capital Markets/Brokers
**No new compute needed** — just exclusions.

**Injection: `_build_broker_injection()`**
- Exclude: FCF, CFO, CFO/PAT (client money/settlement flows distort cash flows completely)
- Emphasize: ROE, ROA, revenue quality (trading vs advisory vs distribution), AUM growth, cost-to-income
- Detection: `_is_broker(symbol)` — match "Stock Broking", "Capital Markets", "Financial Services" + check if company profile mentions brokerage/trading

---

### Tier 3: Light Injection — prompt caveat only, no new compute

These sectors work fine with standard frameworks but need specific caveats.

#### 3A. IT Services
- Add to shared preamble or as micro-injection:
  - "DSO/debtor days trend is the leading indicator of demand stress in IT services — always flag if rising >5 days YoY"
  - "Subcontracting cost % rising = demand > bench strength; falling = bench building"
- No exclusions needed. Standard PE/DCF works.

#### 3B. Pharma
- "R&D spend is investment, not cost. High R&D/Revenue (>8%) is positive for pipeline-driven pharma. Don't penalize."
- "US price erosion is structural (~5-8%/year) — focus on new launch pipeline offsetting erosion"
- Standard framework works. SOTP useful for complex pharma (API + formulations + CRAMS).

#### 3C. FMCG
- "Negative working capital is a STRENGTH in FMCG (advance collections from distributors). Flag if this advantage is shrinking."
- "Volume growth vs price growth split is the single most important metric — pure price growth without volume is unsustainable"
- Standard framework works. Premium PE justified by earnings visibility.

#### 3D. Auto
- "Auto is cyclical — use mid-cycle earnings for valuation, not peak/trough"
- "EV transition progress (% of sales from EVs) is the key forward metric"
- "Inventory days at dealer level (from concall) is a demand leading indicator"
- SOTP for conglomerates (M&M = auto + farm + financial services).

---

## Implementation Order

| Priority | Sector | Type | Effort | Files |
|----------|--------|------|--------|-------|
| 1 | Insurance | Full injection | Medium | data_api.py, prompts.py |
| 2 | Metals/Mining | Medium injection | Small | prompts.py (+ Net Debt/EBITDA in data_api.py) |
| 3 | Real Estate | Full injection | Medium | data_api.py, prompts.py |
| 4 | Telecom | Medium injection | Small | prompts.py (+ OpFCF compute) |
| 5 | Capital Markets | Light injection | Tiny | prompts.py only |
| 6 | Power/Utilities | Medium injection | Small | prompts.py (+ div yield spread) |
| 7 | IT/Pharma/FMCG/Auto | Light caveats | Tiny | prompts.py shared preamble |

## Data Source Summary

| Metric | Source | Available? |
|--------|--------|-----------|
| Net Debt/EBITDA | annual_financials (borrowings, cash_and_bank, operating_profit, depreciation) | ✅ Compute |
| OpFCF | quarterly_cash_flow (operating_cf, capital_expenditure) | ✅ Compute |
| NAV per share | annual_financials (total_assets, borrowings, other_liabilities, num_shares) | ✅ Compute |
| P/NAV | price / NAV per share | ✅ Compute |
| Div yield vs G-sec | valuation_snapshot (dividend_yield) + macro_snapshot (gsec) | ✅ Compute |
| VNB, Combined Ratio, Persistency | sector_kpis concall extraction | ⚠️ Concall dependent |
| Pre-sales, realization/sqft | sector_kpis concall extraction | ⚠️ Concall dependent |
| ARPU, subscriber count | sector_kpis concall extraction | ⚠️ Concall dependent |
| Volume vs price growth | sector_kpis concall extraction | ⚠️ Concall dependent |

## Verification

For each new injection:
1. Run the agent on a benchmark stock from that sector
2. Grade with Gemini (sector-specialist system instruction)
3. Confirm: excluded metrics not cited, sector-specific metrics used, valuation framework correct
4. Update eval-loop-playbook.md

## Benchmark Stocks for Testing

| Sector | Stock | Why |
|--------|-------|-----|
| Insurance | SBILIFE | Life insurance, listed, good data |
| Real Estate | DLF | Large-cap RE, pre-sales data available |
| Metals | VEDL | Already tested, good baseline |
| Telecom | BHARTIARTL | Largest telecom, capex-heavy |
| Brokers | GROWW | Already tested, B+ baseline |
| Power | NTPC | Regulated utility, dividend play |
