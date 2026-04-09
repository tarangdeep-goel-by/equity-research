## IT Services Mode (Auto-Detected)

This is an Indian IT services company. Standard manufacturing/asset-heavy metrics are misleading.

**Primary Metrics:**
- **Constant Currency (CC) Revenue Growth**: the most important metric — reported revenue includes FX tailwinds/headwinds, so CC growth isolates true demand. Always compare CC growth to reported growth
- **Deal TCV/ACV (Total/Annual Contract Value)**: Forward revenue visibility. Large deal wins are lumpy — use trailing 4Q average. TCV >$1B is a mega-deal
- **LTM Attrition Rate**: Talent retention — higher attrition increases replacement hiring + training costs, compressing margins. Compare against peer median and the company's own trend via `get_peer_sector(section='benchmarks')`
- **Utilization Rate**: 82-86% is the sweet spot. Below 80% = bench bloat (margin drag). Above 88% = no capacity for new deals
- **EBIT Margin**: Track in 50bps bands. Every 100bps margin change on ₹1L Cr revenue = ₹1,000 Cr EBIT impact
- **Subcontracting Cost %**: Rising = demand exceeds bench (positive short-term, margin pressure). Falling = bench building (positive long-term)

**Structural Margin Levers:**
- **Onsite/Offshore Mix**: Every 1% shift to offshore improves margin ~30-50bps. Track direction
- **Employee Pyramid**: Fresher hiring ratio — higher ratio = margin expansion via pyramid optimization
- **Client Concentration**: Top 5/Top 10 clients as % of revenue. >30% from top 5 = concentration risk

**Vertical Exposure:** BFSI vs Retail vs Communications/Media vs Manufacturing. BFSI slowdowns disproportionately hit Indian IT — always flag BFSI revenue share

**Valuation:** Standard PE/DCF valid. Compare PE to peer range and the company's own historical band via `get_valuation(section='band', metric='pe')`. Premium justified by: high ROCE, cash generation, dividend + buyback. Cross-currency hedging gains/losses can distort quarterly PAT — flag if material.

**Metrics not applicable to IT services:**
- Inventory metrics, working capital analysis — IT is asset-light with negative working capital as the norm; these metrics provide no insight
- Debt-to-Equity analysis — IT companies are inherently cash-rich with near-zero debt, so leverage ratios are uninformative

**Concall KPIs:** Deal pipeline commentary, discretionary vs non-discretionary spend trends, pricing environment, visa costs, wage hike cycle impact.
