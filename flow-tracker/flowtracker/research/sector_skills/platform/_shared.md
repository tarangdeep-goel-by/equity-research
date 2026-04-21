## Platform / Internet Business Mode (Auto-Detected)

This is a platform/marketplace/internet business. Standard manufacturing metrics are misleading.

**Business Model:** Platforms connect buyers and sellers, earning commissions/take rates on transactions. Revenue = GMV × Take Rate. Growth is measured by GMV/order volume first, monetization second.

**Primary Metrics:**
- **GMV (Gross Merchandise Value)** / Gross Order Value — the true scale metric. Revenue is just the platform's cut
- **Take Rate** = Revenue / GMV. Tracks monetization power — rising take rate = pricing power
- **Unit Economics**: Revenue per order, Contribution Margin per order, CAC, LTV
- **AOV (Average Order Value)** — basket size trend
- **Order Frequency** — repeat purchase rate, customer stickiness

**Profitability Framework (for loss-making platforms):**
- Track path to profitability through the waterfall: GMV → Revenue → Gross Profit → Contribution Margin (after delivery/variable costs) → EBITDA
- Contribution margin positive = unit economics work, just need scale
- Contribution margin negative = burning money on every order, fundamental business model risk

**Metrics that mislead for platforms:**
- PE ratio (for loss-making companies) — negative earnings make PE undefined or misleading; use EV/Revenue or EV/GMV instead
- ROCE/ROE — accumulated losses distort the equity base, making these ratios not meaningful
- Traditional working capital analysis — platforms are asset-light, so WC metrics provide no insight into business health

**Cash Burn & Runway:**
- Track quarterly cash burn rate and remaining cash runway
- Dilution risk: how many equity raises have there been? What's the annual dilution rate?

### Mandatory — Operational-Metrics Fallback Chain

Platform KPIs (GMV, take rate, AOV, MTU / MAU, order frequency, CAC, contribution margin) are routinely absent from `get_sector_kpis(symbol, sub_section=...)` because the structured-KPI extractor has sparse coverage for internet businesses. Do NOT silently skip these metrics — they are the primary operating reality of a platform and cannot be substituted with P&L ratios. The fallback chain:

1. **First:** `get_sector_kpis(symbol, sub_section='gmv')` (also `take_rate`, `mau`, `order_frequency`).
2. **Fallback 1:** `get_company_context(section='concall_insights', sub_section='operational_metrics')` — management routinely quotes these; the concall extractor surfaces them even when the sector-KPI extractor misses.
3. **Fallback 2:** `get_company_context(section='concall_insights', sub_section='financial_metrics')` — revenue, contribution margin, and GMV-implied take rate.
4. **Only if all three return empty** — raise as an open question ("What is this quarter's GMV / take rate? Investor deck suggests X but management has not confirmed.") and continue the report. A platform section that entirely omits GMV and take rate when the data is recoverable via concall is a mandatory-metric gap.

**Emphasize:** GMV growth, take rate trajectory, unit economics improvement, customer acquisition cost trends, competitive moat (network effects, switching costs), and path to EBITDA breakeven.

## Multi-Vertical Platform Coverage (new)

Multi-vertical platforms (food + quick commerce + B2B + payments) — every vertical that is ≥5% of GMV or ≥10% of revenue MUST have its own dedicated section in the business report AND its own separate component in the SOTP valuation. Covering only the headline vertical is a PROMPT_FIX downgrade. Examples:

- ETERNAL: food delivery + Hyperpure (B2B) + District (quick commerce) + Blinkit — all four need separate treatment once individually material.
- PAYTM: UPI / payments + lending + commerce — each vertical separate.

## Projections Tool Caveat — Asset-Light (new)

`get_projections(section='income_statement')` applies a default D&A assumption suitable for manufacturing companies (~5% of revenue). For asset-light platforms, that assumption is wrong — override with an asset-turnover-based projection (0.5–1.5% of revenue for pure platforms). If the projections tool already emits a `_projection_assumptions` meta field (see E12 upgrade), use the routed ratio; otherwise note the mis-applied assumption explicitly in your valuation and adjust downstream.
