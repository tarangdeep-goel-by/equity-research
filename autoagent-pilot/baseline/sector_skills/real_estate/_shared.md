## Real Estate Mode (Auto-Detected)

This is a real estate developer. Revenue recognition distortions make standard metrics unreliable.

**Revenue Recognition Distortion — Why Standard Metrics Fail:**
Real estate revenue is recognized on percentage-of-completion or completed-contract basis. This creates massive lumping — a company can show zero revenue in Q1-Q3 and all revenue in Q4. PE, EPS, ROE, and ROCE are all distorted by this accounting treatment, making them unreliable signals for real estate developers.

**Primary Valuation Metrics:**
- **P/Adjusted Book Value**: primary metric. Available in `get_quality_scores` realestate section. Note: this is book value, NOT true NAV (which requires land bank revaluation at current market rates from investor presentations)
- **EV/EBITDA**: acceptable for rental/commercial real estate and REITs, less useful for project developers
- **Pre-sales value and volume**: the most important operational metric — forward revenue visibility. Source from concall insights

**Metrics that mislead for real estate developers:**
- **PE / EPS** — distorted by revenue recognition timing; PE can look expensive when completions are delayed and cheap when a batch of projects delivers simultaneously, neither reflecting true business value
- **ROE / ROCE** — same recognition distortion, compounded by leverage effects from project financing
- **Standard DCF** — project cash flows are too lumpy and uncertain for reliable DCF modeling
- **FCF** — massive swings from land acquisition and project payments make FCF trends unreliable
- **Inventory months from annual financials** — computing inventory/revenue gives misleading results because revenue is lumpy (completion-based). Valid inventory months require area sold / sales velocity data from investor presentations only, not annual financial statements.

**Emphasize:**
- Pre-sales momentum (value and volume trends, QoQ and YoY)
- Realization per sqft (pricing power and location quality)
- Collection efficiency (actual cash collections vs bookings)
- Net debt trajectory (leverage management through project cycles)
- Launch pipeline (future revenue visibility)
- Land bank value and location quality
- Unsold inventory as months of sales (from investor presentations only — annual financials don't have the absorption rate data needed)

**Fallback:** If pre-sales data is not available from concall insights, use P/Adjusted Book Value as primary valuation and flag the absence of operational data as a limitation.

**REITs Note:** If this is a REIT (Embassy, Mindspace, Brookfield), use rental yield framework: P/FFO (Funds From Operations), dividend yield, NAV discount/premium. REITs have predictable cash flows unlike project developers.

### Annual Report & Investor Deck — Real Estate Specifics

**AR high-signal sections:**
- `notes_to_financials` — revenue-recognition policy (completed-contract vs percentage-of-completion), inventory ageing (finished-goods days), customer-advance balances, JV/JDA accounting treatment.
- `mdna` — pre-sales (bookings) vs collections vs recognised revenue, project-wise launch schedule, RERA-registered projects, customer-pipeline backlog.
- `risk_management` — land-bank carrying costs, approval-delay risk, receivables concentration, cyclicality management (residential vs commercial mix).
- `segmental` — residential vs commercial vs leasing; geography split (MMR/NCR/Bangalore/etc.); ticket-size mix.
- `auditor_report` — KAMs on revenue-recognition appropriateness, inventory-valuation at net-realizable-value, customer-advance classification.

**Deck high-signal sub_sections:**
- `highlights` — pre-sales/bookings value YoY, number of launches, collection efficiency.
- `strategic_priorities` — new-launch pipeline, inventory monetisation plan, leasing-vs-sale tilt for commercial.

**Cross-year narrative cues:** `capital_allocation_shifts` often reveal asset-light pivot vs land-bank expansion; `biggest_concern` tracks absorption-rate deterioration and approval-delay clusters.

## Deck as Primary Source for City-Level Data (escalation — new)

Investor deck is the PRIMARY source for city-level presales, absorption rates, book velocity, and project-level launch pipeline — NOT the concall, NOT the annual report, NOT the structured KPI tool. Real-estate risk and business agents MUST call `get_deck_insights(sub_section='segment_performance')` OR `get_deck_insights(sub_section='charts_described')` for the latest quarter BEFORE raising any city-level or project-level data gap as an open question. Per shared-preamble fallback-chain tenet, the deck check is a mandatory step.

## Valuation Framework Priority (new — tighten v1)

Framework priority for Indian real-estate developers: **P/Presales > NAV > P/Ops > Peer > PE**. PE is deprioritized due to IndAS 115 revenue-recognition distortions (booked revenue lags actual sales). If your prose argues against PE as a primary metric (e.g., "IndAS 115 distorts earnings"), your valuation MUST NOT blend PE-based numbers in later — per shared-preamble A1.1 (argue-then-use forbidden).

## NAV Estimation — Mandatory Computation (new — plan v3 F)

P/Adjusted-Book-Value from `get_quality_scores` is stated book value — it uses historical cost of the land bank, which for companies sitting on land acquired 10–20 years ago is dramatically below current market value. You MUST estimate NAV independently rather than anchoring valuation on stated P/B and declaring "NAV premium not computable".

**Formula (back-of-envelope, document the inputs):**

```
nav_per_share =
    (shareholders_equity_cr
     + undisclosed_land_mtm_uplift_cr
     − net_debt_premium_cr
     + listed_subsidiary_mtm_uplift_cr)
    / shares_outstanding
```

**Where each input comes from:**

| Input | Source tool / section | Notes |
|---|---|---|
| `shareholders_equity_cr` | `get_fundamentals` → balance sheet → total equity | Standalone or consolidated — state which; cite section in narrative |
| `undisclosed_land_mtm_uplift_cr` | `get_deck_insights(sub_section='segment_performance')` or `(sub_section='charts_described')` for land bank area in msf + disclosed estimated GDV; OR `get_annual_report(section='mdna')` for land-bank discussion. Uplift = (disclosed market-GDV − book-carrying-value), often 3–8× book for land acquired >10yrs ago. | If no disclosed GDV, state as a data gap rather than guessing — do NOT fabricate a multiple |
| `net_debt_premium_cr` | `get_fundamentals` → net debt | Add a ~10% premium for project-finance mismatch (short borrowings vs multi-year receivables) only if supported by balance-sheet commentary; leave at zero otherwise |
| `listed_subsidiary_mtm_uplift_cr` | `get_company_context(section='subsidiaries')` + market caps for any listed arm | Apply a 20–25% holding-company discount per conglomerate norm |
| `shares_outstanding` | `get_valuation_snapshot` | Diluted share count, not face-value computation |

**Worked skeleton (for clarity, not a template to paste):**

> *Subject is GODREJPROP. From the FY25 investor deck, land bank = 107 msf with disclosed estimated GDV of ₹2.1 lakh Cr vs book value of ~₹8,500 Cr (source: FY25-Q4 deck, segment_performance). Land uplift = ₹2,10,000 − 8,500 = ₹2,01,500 Cr. Shareholders' equity (consolidated) = ₹12,400 Cr (source: FY25 AR, financial_statements). Net debt = ₹6,800 Cr, no project-finance premium applied (maturity profile clean per mdna). No listed subsidiaries.*
>
> *NAV = (12,400 + 2,01,500 − 6,800) / 29.8 Cr shares ≈ ₹7,050 per share. Current CMP = ₹2,400. NAV-implied upside = 194%. Framework: NAV-anchored valuation only, not PE.*

**Rules:**
- If *any* input is unavailable (e.g., land-bank msf or GDV not disclosed in deck or AR), DO NOT skip NAV — state the gap and either (a) compute with the remaining inputs using stated book NAV as a floor, or (b) raise as a specific open question citing the exact tool + section you checked. "Cannot estimate NAV without investor presentation" is a prompt violation — you MUST consult the deck first via `get_deck_insights`.
- The 3–8× land-uplift range is a *sense-check*, not a formula input. Use disclosed GDV when available; otherwise anchor on peers' disclosed uplift ratios from the same geography.
- A computed NAV wildly above CMP (say >3×) should be reconciled against realisation timing — land bank NAV assumes monetisation; if the pipeline is 15-year slow-burn, apply a 40–50% time-discount before quoting the NAV-upside number.
