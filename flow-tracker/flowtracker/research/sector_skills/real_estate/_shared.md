## Real Estate Mode (Auto-Detected)

This is a real estate developer. Revenue recognition distortions make standard metrics unreliable.

**Revenue Recognition Distortion — Why Standard Metrics Fail:**
Under Ind AS 115 (effective FY19), real estate revenue for standard developers is recognized almost entirely on a **completed-contract / point-in-time basis** (on transfer of control at possession), NOT percentage-of-completion — POCM is no longer the default and survives only in the narrow cases where the "over time" control-transfer criteria are met. This creates massive lumping — a company can show low revenue across construction years and a spike in the handover year. PE, EPS, ROE, and ROCE are all distorted by this accounting treatment, making them unreliable signals for real estate developers.

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

**REITs Note:** If this is a REIT — office REITs Embassy, Mindspace, Brookfield (BIRET), or **Nexus Select Trust** (India's first listed *retail*/mall REIT, listed May 2023, which needs mall KPIs: trading density, tenant-sales growth, minimum-guarantee vs percentage-rent mix, not just office occupancy) — use the rental yield framework: P/FFO (Funds From Operations), distribution yield, NAV discount/premium. REITs have predictable cash flows unlike project developers. SM-REITs (SEBI 2024, ₹50-500 Cr per scheme) are a distinct, smaller archetype.

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
    (shareholders_equity_cr           # already NET of debt — do NOT subtract net debt again
     + undisclosed_land_mtm_uplift_cr  # post-tax uplift: deduct implied DTL on the revaluation surplus
     + listed_subsidiary_mtm_uplift_cr)
    / shares_outstanding
```

**Critical:** `shareholders_equity_cr` is *already* net of all debt (Assets − Liabilities), so subtracting net debt from it double-counts the debt and mechanically breaks NAV. The previous skeleton's `− net_debt_premium_cr` term was wrong and has been removed. The only debt-related adjustment that is legitimate is a small *project-finance maturity-mismatch* haircut applied as a sense-check to the uplift, NOT a subtraction of the full net-debt balance — and only if balance-sheet commentary supports it. Likewise, take the land uplift **post-tax**: deduct the implied capital-gains tax / DTL on the (market value − book carrying value) surplus, since the gross uplift is not distributable.

**Where each input comes from:**

| Input | Source tool / section | Notes |
|---|---|---|
| `shareholders_equity_cr` | `get_fundamentals` → balance sheet → total equity | Standalone or consolidated — state which; cite section in narrative |
| `undisclosed_land_mtm_uplift_cr` | `get_deck_insights(sub_section='segment_performance')` or `(sub_section='charts_described')` for land bank area in msf + disclosed estimated GDV; OR `get_annual_report(section='mdna')` for land-bank discussion. Uplift = (disclosed market-GDV − book-carrying-value), often 3–8× book for land acquired >10yrs ago. | If no disclosed GDV, state as a data gap rather than guessing — do NOT fabricate a multiple |
| `undisclosed_land_mtm_uplift_cr` (post-tax) | as above | Deduct the implied capital-gains tax / DTL on the (market − book) revaluation surplus before adding; the gross uplift is not distributable |
| `listed_subsidiary_mtm_uplift_cr` | `get_company_context(section='subsidiaries')` + market caps for any *separately listed* arm | Apply a 20–25% holding-company discount only where an arm is genuinely listed; for DLF/PRESTIGE/BRIGADE the key arms (e.g. DCCDL) are unlisted, so the SOTP uplift is on unlisted SPVs, not a listed-subsidiary mark |
| ~~`net_debt_premium_cr`~~ (removed) | — | Do NOT subtract net debt from equity — equity is already net of debt; subtracting double-counts. A small project-finance maturity-mismatch haircut on the uplift is the only legitimate debt adjustment, and only if commentary supports it |
| `shares_outstanding` | `get_valuation_snapshot` | Diluted share count, not face-value computation |

**Worked skeleton (for clarity, not a template to paste):**

> *Subject is GODREJPROP. From the FY25 investor deck, land bank = 107 msf with disclosed estimated GDV of ₹2.1 lakh Cr vs book value of ~₹8,500 Cr (source: FY25-Q4 deck, segment_performance). Gross land uplift = ₹2,10,000 − 8,500 = ₹2,01,500 Cr; applying ~20% implied capital-gains/DTL on the surplus gives a post-tax uplift ≈ ₹1,61,200 Cr. Shareholders' equity (consolidated) = ₹12,400 Cr (source: FY25 AR, financial_statements) — already net of the ₹6,800 Cr net debt, so net debt is NOT subtracted again. No separately listed subsidiaries.*
>
> *NAV = (12,400 + 1,61,200) / 29.8 Cr shares ≈ ₹5,825 per share. Current CMP = ₹2,400. NAV-implied upside ≈ 143%. Framework: NAV-anchored valuation only, not PE. (Illustrative inputs — not live figures.)*

**Rules:**
- If *any* input is unavailable (e.g., land-bank msf or GDV not disclosed in deck or AR), DO NOT skip NAV — state the gap and either (a) compute with the remaining inputs using stated book NAV as a floor, or (b) raise as a specific open question citing the exact tool + section you checked. "Cannot estimate NAV without investor presentation" is a prompt violation — you MUST consult the deck first via `get_deck_insights`.
- The 3–8× land-uplift range is a *sense-check*, not a formula input. Use disclosed GDV when available; otherwise anchor on peers' disclosed uplift ratios from the same geography.
- A computed NAV wildly above CMP (say >3×) should be reconciled against realisation timing — land bank NAV assumes monetisation; if the pipeline is 15-year slow-burn, apply a 40–50% time-discount before quoting the NAV-upside number.
