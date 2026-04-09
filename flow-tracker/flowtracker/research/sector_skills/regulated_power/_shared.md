## Regulated Power/Utility Mode (Auto-Detected)

This is a regulated power utility. Revenue and returns are governed by CERC/SERC tariff orders, not market forces.

**Key Framework:**
- Revenue growth is NOT a meaningful metric — fuel costs are pass-through, so revenue swings with input costs, not demand
- EBITDA margin % is also misleading for same reason — focus on absolute EBITDA or regulated equity base growth
- The regulated ROE (typically 15.5% on equity base per CERC norms) is the anchor — actual ROE should track this

**Primary Valuation Metrics:**
- **P/B vs Regulated ROE**: The primary framework. Justified P/B = ROE ÷ Cost of Equity. Available in `get_quality_scores` power section
- **Dividend Yield vs G-sec Spread**: Regulated utilities are bond-proxies. Spread over 10Y G-sec yield is the key metric. Positive spread = attractive. Available in `get_quality_scores` power section
- **Regulated Equity Base growth**: drives future earnings — check capex plans and CWIP-to-fixed-assets ratio

**Metrics that give misleading results for regulated utilities:**
- Revenue growth rate — fuel costs are pass-through, so revenue swings with input prices rather than reflecting real business growth
- EBITDA margin % — same pass-through distortion; absolute EBITDA is more informative
- PEG ratio — growth is regulatory (capacity additions), not organic; PEG assumes market-driven compounding
- Standard DCF with high growth assumptions — regulated ROE caps returns at ~15.5%, so high-growth DCF scenarios overstate upside

**Emphasize:** PLF (Plant Load Factor) / PAF (Plant Availability Factor), AT&C losses (for distribution), fuel cost trends, regulatory order outcomes, dividend payout ratio, and capacity addition pipeline.

**Concall KPIs:** PLF/PAF trends, tariff order outcomes, fuel supply agreements, renewable capacity additions, CWIP capitalization timeline.
