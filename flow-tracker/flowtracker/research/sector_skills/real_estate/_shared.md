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
