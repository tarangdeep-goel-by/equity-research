## Real Estate Mode (Auto-Detected)

This is a real estate developer. Revenue recognition distortions make standard metrics unreliable.

**CRITICAL — Revenue Recognition Distortion:**
Real estate revenue is recognized on percentage-of-completion or completed-contract basis. This creates massive lumping — a company can show zero revenue in Q1-Q3 and all revenue in Q4. PE, EPS, ROE, and ROCE are all distorted by this accounting treatment.

**Primary Valuation Metrics:**
- **P/Adjusted Book Value**: primary metric. Available in `get_quality_scores` realestate section. Note: this is book value, NOT true NAV (which requires land bank revaluation at current market rates from investor presentations)
- **EV/EBITDA**: acceptable for rental/commercial real estate and REITs, less useful for project developers
- **Pre-sales value and volume**: THE most important operational metric — forward revenue visibility. Source from concall insights

**DO NOT USE (misleading for real estate developers):**
- PE / EPS — distorted by revenue recognition timing. Do NOT use PE for valuation
- ROE / ROCE — same distortion, plus leverage effects from project financing
- Standard DCF — project cash flows are too lumpy and uncertain
- FCF — massive swings from land acquisition and project payments
- **Inventory months from annual financials** — this metric is INVALID when computed as inventory/revenue. Revenue is lumpy (completion-based). Valid inventory months require area sold / sales velocity data from investor presentations ONLY. Do NOT compute this from annual data.

**Emphasize:**
- Pre-sales momentum (value and volume trends, QoQ and YoY)
- Realization per sqft (pricing power and location quality)
- Collection efficiency (actual cash collections vs bookings)
- Net debt trajectory (leverage management through project cycles)
- Launch pipeline (future revenue visibility)
- Land bank value and location quality
- Unsold inventory as months of sales (from investor presentations ONLY)

**Fallback:** If pre-sales data is not available from concall insights, use P/Adjusted Book Value as primary valuation and flag the absence of operational data as a limitation.

**REITs Note:** If this is a REIT (Embassy, Mindspace, Brookfield), use rental yield framework: P/FFO (Funds From Operations), dividend yield, NAV discount/premium. REITs have predictable cash flows unlike project developers.
