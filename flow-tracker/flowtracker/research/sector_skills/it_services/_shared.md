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

### Annual Report & Investor Deck — IT Services Specifics

**AR high-signal sections:**
- `segmental` — client-geography split (US/Europe/RoW), vertical split (BFSI/Retail/Mfg/Healthcare), top-5 client concentration (% of revenue).
- `mdna` — utilization, attrition, on-site/off-site mix, pyramid-cost management, pricing pressure by vertical.
- `risk_management` — immigration/visa exposure, deal-pipeline seasonality, large-client-concentration risk, currency hedging policy.
- `notes_to_financials` — contract-asset (unbilled revenue) aging, ESOP cost schedule, deferred-tax on R&D credits.
- `corporate_governance` — CEO succession context, key technical leadership transitions, ESG/diversity metrics.

**Deck high-signal sub_sections:**
- `highlights` — deal-TCV wins, large-deal count, annualized revenue run-rate from new deals.
- `strategic_priorities` — AI/gen-AI positioning, large-deal-ramp timelines, inorganic-vs-organic split.

**Cross-year narrative cues:** `key_evolution_themes` typically track discretionary-vs-non-discretionary-spending trend; `guidance_track_record` credibility matters extra for IT given quarterly guidance cadence.

## IT Services Mandatory Metrics (new)

IT Services business and risk agents MUST cite all of the following for Tier-1 IT reports (TCS, INFY, WIPRO, HCLTECH, TECHM, LTIM):

1. Top-5 and Top-10 client concentration (% of revenue)
2. Utilization rate (onsite / offshore split)
3. Net headcount additions, latest quarter
4. Attrition LTM (%)

Source chain: `get_company_context(section='client_concentration')` → `get_concall_insights(sub_section='operational_metrics')` → `get_deck_insights(sub_section='highlights')` for the latest quarter. All four are mandatory — missing any is a PROMPT_FIX downgrade for Tier-1 IT coverage.
