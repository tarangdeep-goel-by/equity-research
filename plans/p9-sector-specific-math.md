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
| `build_specialist_prompt()` | Assembles prompt with dynamic injections | Needs dispatch refactor first |
| `sector_kpis.py` | 116 KPIs across 15 sectors for concall extraction | KPIs already defined |
| `get_bfsi_metrics()` | Pre-computes NIM, ROA, C/I, P/B, CD ratio from annual financials | Template for new methods |
| Annual financials fields | revenue, net_income, borrowings, depreciation, operating_profit, cfo, cfi, receivables, inventory, cash_and_bank, total_assets, other_assets, investments | Primary data source |
| `valuation_snapshot` | pe_trailing, ev_ebitda, pb_ratio, dividend_yield, total_debt, total_cash, roe | Secondary data source |
| `macro_snapshot` | G-sec yield, USD/INR, crude | For power/utilities spread calc |

## Step 0: Dispatch Refactor

**Before adding any new injections**, refactor `build_specialist_prompt()` from if/else chain to dispatch pattern:

```python
# List of (detector, builder, agent_set) tuples — evaluated in priority order
_SECTOR_INJECTIONS = [
    (_is_insurance, _build_insurance_injection, _INSURANCE_AGENTS),
    (_is_bfsi,      _build_bfsi_injection,      _BFSI_AGENTS),
    (_is_realestate, _build_realestate_injection, _RE_AGENTS),
    (_is_metals,    _build_metals_injection,     _METALS_AGENTS),
    # ... etc
]
```

**Cascade priority matters** — check insurance before BFSI (insurance is a subset), broker after AMC after NBFC. A stock matches the *first* detector that returns True.

Also update `get_quality_scores_all()` to route new sectors (skip inapplicable metrics per sector).

---

## Tiers

### Tier 1: Full Injection (like BFSI) — new `get_X_metrics()` + prompt injection + exclusions

#### 1A. Insurance
**Why full:** Insurance P&L/BS is as different from manufacturing as banking is. PE/EBITDA/FCF/working capital all meaningless.

**New method: `get_insurance_metrics(symbol)`**
Compute from annual_financials + sector_kpis:
- Solvency ratio (from sector_kpis concall data)
- ROE, ROA (from annual financials — valid for insurance)
- Opex ratio: `(employee_cost + other_expenses) / net_earned_premium` — **NOT revenue/GWP** (using GWP understates opex, making inefficient insurers look good). Fall back to NWP if NEP unavailable, state limitation.
- Growth: premium growth YoY from annual revenue

Concall-dependent (surface if available, flag as open question if not):
- VNB, VNB margin, APE (life)
- Combined ratio, loss ratio, expense ratio (general)
- Persistency 13th/61st month (life)
- Embedded Value (life) — for P/EV computation

**Fallback when concall data missing:** "If VNB data is not available, state that and use P/B as secondary valuation for Life Insurance, noting limitations. Do not proceed with P/EV or P/VNB analysis without data."

**New injection: `_build_insurance_injection()`**
- Exclude: EBITDA, EBIT margin, ROCE, FCF, standard DCF, working capital, inventory, capex cycle
- Life valuation: P/EV (Price / Embedded Value per share), P/VNB
- General valuation: P/B, target P/E
- Key metrics: VNB margin (life), Combined Ratio (general), Persistency, Solvency
- Add to `_insurance_agents` set (same agents as BFSI)

**Detection:** `_is_insurance()` already exists — checked *before* `_is_bfsi()` in cascade.

#### 1B. Real Estate
**Why full:** Revenue recognition (% completion vs completed contract) distorts PE/EPS/ROE.

**New method: `get_realestate_metrics(symbol)`**
Compute from annual_financials:
- **Adjusted Book Value per share**: `(total_assets - borrowings - other_liabilities) / num_shares * 1e7` — label as "Adjusted Book Value", **not NAV** (true NAV requires land revaluation from concalls/investor presentations)
- P/Adjusted Book: `price / adjusted_bv_per_share`
- Net Debt/Equity: `(borrowings - cash_and_bank) / (equity_capital + reserves)`

**Concall-dependent only** (do NOT compute from annual financials):
- Inventory months (requires area sold / sales velocity from investor presentations — `inventory / (revenue/12)` is invalid for project-based accounting)
- Pre-sales value/volume, collections, realization per sqft, launch pipeline

**New injection: `_build_realestate_injection()`**
- Exclude: PE, EPS, ROE, ROCE, standard DCF, FCF
- Valuation: P/Adjusted Book Value (primary), EV/EBITDA (for rental/commercial/REITs only)
- Key metrics: Pre-sales momentum, realization per sqft, collection efficiency, net debt trajectory
- Explicit: "Do NOT compute inventory months from annual financials. This metric is valid only from investor presentation data (area sold / sales velocity)."

**Detection:** New `_is_realestate(symbol)` — match industries: "Real Estate", "Construction - Real Estate"

**Note:** REITs (Embassy, Mindspace) need separate handling — P/FFO, dividend yield, NAV. Detect via industry or company name. If REIT detected, use rental/commercial framework, not project developer framework.

---

### Tier 2: Medium Injection — prompt injection + exclusions, lighter compute

#### 2A. Metals/Mining
**Compute in new helper `get_metals_metrics(symbol)`:**
- Net Debt/EBITDA: `(borrowings - cash_and_bank) / (operating_profit + depreciation)`
- **5Y average EV/EBITDA**: compute from historical data to give agent a "mid-cycle" reference point (don't leave "mid-cycle" as unfunded mandate)
- Already have: current EV/EBITDA from valuation_snapshot

**Injection: `_build_metals_injection()`**
- WARNING: "PE is a cyclical trap — lowest PE often marks commodity cycle peak. Compare current EV/EBITDA to the 5Y average provided. If current << average, stock is at cycle peak (high earnings). If current >> average, stock is at cycle trough (depressed earnings)."
- Exclude: Standard PE-based valuation in isolation
- Emphasize: Net Debt/EBITDA, commodity price sensitivity, capex cycle, dividend yield, P/B at trough
- Detection: `_is_metals(symbol)` — match industries containing "Mining", "Metals", "Steel", "Aluminium", "Copper", "Zinc"

#### 2B. Telecom
**Compute:**
- OpFCF: `operating_cf - capital_expenditure` (from quarterly_cash_flow)
- Capex/Revenue: `abs(cfi) / revenue` (from annual_financials)
- Net Debt/EBITDA (same formula as metals)

**Injection: `_build_telecom_injection()`**
- Exclude: PE/PAT margin (spectrum amortization distorts)
- Emphasize: EV/EBITDA, OpFCF, ARPU, subscriber growth, capex intensity
- **SOTP note:** "For conglomerates (e.g., Airtel = mobile + towers + broadband + enterprise), note that SOTP analysis is appropriate but requires segment-level data from investor presentations. If segment data is not available in the provided tools, state this limitation rather than estimating."
- Detection: `_is_telecom(symbol)` — match "Telecom", "Telecommunication"

**Note:** Tower companies (Indus Towers) need different framework — tenancy ratio, rental per tower, not ARPU. Detect separately if industry contains "Telecom Infrastructure" or "Tower".

#### 2C. Power/Utilities — SPLIT into Regulated vs Merchant

**2C-i. Regulated Power** (NTPC, Power Grid, NHPC)
**Compute:**
- Dividend yield vs G-sec spread: `dividend_yield - gsec_10y_yield` (ensure macro_snapshot freshness — note "as of" date)
- Justified P/B = ROE / CoE (CoE ~ G-sec + equity risk premium)

**Injection: `_build_regulated_power_injection()`**
- Exclude: Revenue growth (fuel pass-through creates noise), EBITDA margin % (same reason)
- Emphasize: P/B vs regulated ROE, dividend yield vs G-sec spread, PLF/PAF, AT&C losses, regulated equity base growth
- Detection: `_is_regulated_power(symbol)` — match "Power Generation", "Power Distribution" + check for regulated indicators (PPA, tariff order keywords in business description)

**2C-ii. Merchant/Renewable Power** (JSW Energy, Tata Power non-regulated)
**Injection: `_build_merchant_power_injection()`**
- Emphasize: EV/EBITDA, power exchange price exposure, PPA vs merchant mix, capacity addition pipeline, renewable portfolio %
- Standard valuation (PE, DCF) more applicable than for regulated
- Detection: fallback if power company doesn't match regulated indicators

#### 2D. Capital Markets — SPLIT by sub-sector

**2D-i. Brokers** (GROWW, Angel One, Zerodha)
- Exclude: FCF, CFO, CFO/PAT (client money/settlement flows distort cash flows completely)
- Emphasize: ROE, ROA, revenue quality (trading vs advisory vs distribution), AUM growth, cost-to-income
- Detection: `_is_broker(symbol)` — match "Stock Broking" or "Financial Technology (Fintech)" with brokerage indicators

**2D-ii. AMCs** (HDFC AMC, Nippon Life AMC)
- Emphasize: AUM growth, net flows (equity vs debt), revenue as % of AUM, operating leverage, SIP book
- Valuation: P/E (appropriate here), % of AUM
- Detection: `_is_amc(symbol)` — match "Asset Management"

**2D-iii. Exchanges/Depositories** (BSE, MCX, CDSL)
- FCF *is* valid here (platform business, no client money distortion)
- Emphasize: transaction volumes, new investor registrations, operating leverage, market share
- Detection: `_is_exchange(symbol)` — match "Exchange", "Depository"

**Note:** Broker injection is an *overlay* on BFSI — brokers get BFSI injection + broker-specific CFO exclusion. AMCs and exchanges are standalone.

---

### Tier 3: Light Injection — prompt caveat only, no new compute

#### 3A. IT Services
- "DSO/debtor days trend is the leading indicator of demand stress in IT services — always flag if rising >5 days YoY"
- "Subcontracting cost % rising = demand > bench strength; falling = bench building"
- No exclusions needed. Standard PE/DCF works.

#### 3B. Pharma (Formulations/API)
- "R&D spend is investment, not cost. High R&D/Revenue (>8%) is positive for pipeline-driven pharma. Don't penalize."
- "US price erosion is structural (~5-8%/year) — focus on new launch pipeline offsetting erosion"
- Standard framework works. SOTP useful for complex pharma (API + formulations + CRAMS).

**Note:** Hospitals (Apollo), Diagnostics (Dr. Lal), and CDMO (Divi's Labs) are NOT pharma — they need separate frameworks:
- Hospitals: ARPOB, occupancy rate, EBITDA/bed
- Diagnostics: Revenue/patient, test volumes, network footprint
- CDMO: Asset turnover, client concentration, order book — NOT R&D pipeline

These are future Tier 2 candidates if eval loop flags them.

#### 3C. FMCG
- "Negative working capital is a STRENGTH in FMCG (advance collections from distributors). Flag if this advantage is shrinking."
- "Volume growth vs price growth split is the single most important metric — pure price growth without volume is unsustainable"
- Standard framework works. Premium PE justified by earnings visibility.

#### 3D. Auto
- "Auto is cyclical — use mid-cycle earnings for valuation, not peak/trough"
- "EV transition progress (% of sales from EVs) is the key forward metric"
- "Inventory days at dealer level (from concall) is a demand leading indicator"
- SOTP for conglomerates (M&M = auto + farm + financial services).

**Note:** Auto Ancillaries have different dynamics (customer concentration, content per vehicle, EV transition risk/opportunity). Future Tier 3 candidate.

---

## Implementation Order

| Priority | Sector | Type | Effort | Files | Rationale |
|----------|--------|------|--------|-------|-----------|
| 0 | **Dispatch refactor** | Infra | Small | prompts.py | Must happen before adding injections |
| 1 | **Insurance** | Full injection | Medium | data_api.py, prompts.py | High impact, structured data, known eval failure |
| 2 | **Metals/Mining** | Medium injection | Small | data_api.py, prompts.py | Easy win + fixes known cyclical PE trap |
| 3 | **Power (split)** | Medium injection | Small | prompts.py, data_api.py | High error risk if regulated/merchant lumped |
| 4 | **Capital Markets (split)** | Medium injection | Small | prompts.py | Broker CFO fix + AMC/exchange differentiation |
| 5 | **Real Estate** | Full injection | Medium | data_api.py, prompts.py | De-prioritized: heavy concall dependency |
| 6 | **Telecom** | Medium injection | Small | prompts.py, data_api.py | SOTP complexity, tower co edge case |
| 7 | **Light caveats** | Light | Tiny | prompts.py shared preamble | IT/Pharma/FMCG/Auto — batch |

## Data Source Summary

| Metric | Source | Available? |
|--------|--------|-----------|
| Net Debt/EBITDA | annual_financials (borrowings, cash_and_bank, operating_profit, depreciation) | Compute |
| 5Y avg EV/EBITDA | historical valuation data | Compute (need to verify history depth) |
| OpFCF | quarterly_cash_flow (operating_cf, capital_expenditure) | Compute |
| Adjusted BV per share | annual_financials (total_assets, borrowings, other_liabilities, num_shares) | Compute |
| P/Adjusted BV | price / adjusted_bv_per_share | Compute |
| Div yield vs G-sec | valuation_snapshot (dividend_yield) + macro_snapshot (gsec) | Compute (check freshness) |
| Insurance opex ratio | annual_financials — need NEP/NWP field | Verify field availability |
| VNB, Combined Ratio, Persistency | sector_kpis concall extraction | Concall dependent |
| Pre-sales, realization/sqft | sector_kpis concall extraction | Concall dependent |
| Inventory months (RE) | investor presentations only | Concall dependent — do NOT compute from financials |
| ARPU, subscriber count | sector_kpis concall extraction | Concall dependent |
| Volume vs price growth | sector_kpis concall extraction | Concall dependent |

## Verification

For each new injection:
1. Run the agent on a benchmark stock from that sector
2. Grade with Gemini (sector-specialist system instruction)
3. Confirm: excluded metrics not cited, sector-specific metrics used, valuation framework correct
4. Each new `get_X_metrics()` must have a pytest with factory data
5. Update eval-loop-playbook.md

## Benchmark Stocks for Testing

| Sector | Stock | Why |
|--------|-------|-----|
| Insurance | SBILIFE | Life insurance, listed, good data |
| Insurance | ICICIPRULI | Life, different business mix |
| Real Estate | DLF | Large-cap RE, pre-sales data available |
| Metals | VEDL | Already tested, good baseline |
| Metals | TATASTEEL | Steel-specific, integrated |
| Telecom | BHARTIARTL | Largest telecom, capex-heavy |
| Tower Co | INDUSTOWER | Infrastructure, not telco |
| Brokers | ANGELONE | Discount broker, client money issue |
| AMC | HDFCAMC | Pure-play AMC |
| Exchange | BSE | Platform business |
| Regulated Power | NTPC | Regulated utility, dividend play |
| Merchant Power | JSWENERGY | Merchant/renewable mix |

## Review Notes

**Reviewed by:** Claude (architecture + code) + Gemini 2.5 Pro (financial correctness + completeness)

**Key corrections from review:**
1. Insurance opex ratio denominator: NEP, not revenue/GWP
2. Real Estate inventory months: concall-only, not computable from financials
3. Real Estate "NAV" renamed to "Adjusted Book Value" (true NAV needs land revaluation)
4. Power split into Regulated vs Merchant (polar opposite valuation)
5. Capital Markets split into Brokers vs AMCs vs Exchanges
6. Metals "mid-cycle" made concrete: provide 5Y avg EV/EBITDA
7. SOTP instructions made conditional on data availability
8. Sub-sectors flagged for future: REITs, Tower Cos, Hospitals, Diagnostics, CDMO, Auto Ancillaries
9. Dispatch refactor added as Step 0
10. Cascade detection priority: insurance > bank > NBFC > AMC > broker > generic financial services
