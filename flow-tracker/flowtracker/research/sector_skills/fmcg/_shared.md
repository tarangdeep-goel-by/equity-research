## FMCG Sector Caveats

- **Negative working capital is a strength** — advance collections from distributors and tight receivable management mean the business is funded by suppliers/distributors. Pre-computed WC trend available in `get_quality_scores` sector_health section. Flag if this advantage is shrinking, as it signals eroding distributor leverage
- **Volume growth vs price growth split** is the single most important metric. Pure price growth without volume growth is unsustainable and signals demand destruction. Source from concall commentary
- **Rural vs urban demand mix**: Rural recovery/slowdown is a key cyclical driver
- **Distributor/channel inventory**: Watch for channel stuffing signals — primary sales growing faster than secondary sales is a red flag
- FMCG commands premium PE (40-60x) justified by earnings visibility and defensive nature. Compare to own history, not cross-sector

### Mandatory — Channel Mix & Segment P&L

- **Channel-mix decomposition is mandatory.** Every FMCG report must state the current channel split — **General Trade (GT) / Modern Trade (MT) / e-commerce / Direct-to-Consumer** — and each channel's YoY growth trajectory. The mix is the P&L driver: MT + e-com grow 2-3× GT but carry 300-500bps lower gross margin; the rate at which the mix shifts determines forward margin direction. Source from concall `operational_metrics` and investor presentations. A report citing only consolidated volume growth without the channel split is structurally incomplete.
- **Segment P&L for multi-segment FMCGs.** For companies running ≥2 segments — Home Care / Beauty & Personal Care / Foods & Refreshment (HUL, Marico, Dabur), Beverages / Biscuits / Snacks (Britannia, Nestle, Varun Beverages), Paints / Chemicals (Asian Paints, Berger) — extract and state segment revenue, segment EBIT, and the margin gap between segments from concall `financial_metrics`. Consolidated margin is a blended number that hides which segment is the margin driver. For Unilever/ITC-style conglomerate FMCGs, segment-level analysis is NOT optional.
- **Volume-price-mix split over just volume-price.** The standard volume-vs-price split understates a third driver: **mix effect** (premiumization of SKUs, shift from sachet to bottle, launch of premium variants). For premium FMCG players, mix contributes 100-300 bps of revenue growth per year. Break the revenue bridge into **volume × price × mix** rather than volume × price; extract the mix effect from concall commentary where management quantifies it.

## Channel-Mix Extraction (tightened — new)

If `get_fundamentals(section='revenue_segments')` returns 0 channel fields (GT / MT / e-com), you MUST open `get_deck_insights(sub_section='charts_described')` for the latest quarter — HUL and similar FMCG companies disclose channel splits in deck charts, not in Screener's structured feed. Missing channel mix without a deck check is a PROMPT_FIX downgrade.

## UVG vs Price Decomposition Mandatory (new)

FMCG financials agent: historical UVG (Underlying Volume Growth) vs price-led growth decomposition is MANDATORY for the last 4 quarters — this is the single most important FMCG metric. Source chain: `get_sector_kpis(symbol, sub_section='uvg_pct')` → concall `financial_metrics` → deck `highlights`. Missing this decomposition is a PROMPT_FIX downgrade; citing total revenue growth without the UVG/price split is insufficient.
