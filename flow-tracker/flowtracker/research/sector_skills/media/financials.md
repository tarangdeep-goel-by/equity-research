## Media & Entertainment — Financials Agent

### Sub-Sector P&L Diagnostics
Before analyzing margins, identify the sub-sector and pull the specific unit economics from `get_company_context(section='concall_insights')` or `get_deck_insights(sub_section='segment_performance')`.

**1. Multiplexes (The ATP & SPH Engine):**
- **Box Office vs. F&B**: Box office revenue is split with distributors (multiplex keeps ~45-50% net of taxes). F&B (Food & Beverage) revenue is almost entirely retained (70-75% gross margin).
- **Operating Leverage**: Rent (CAM), electricity, and staff are fixed. If occupancy drops below ~20-22% (breakeven), EBITDA turns negative instantly. If occupancy hits 35%+, incremental margins are massive.
- Track **ATP (Average Ticket Price)** and **SPH (Spend Per Head)** YoY. If footfalls are down but revenue is flat, they took price hikes. *Warning*: Excessive F&B price hikes destroy long-term footfalls; flag if SPH growth vastly outpaces inflation.

**2. Broadcasters (Ad vs. Sub & Content Cost):**
- **Ad Revenue**: Highly cyclical. Check YoY growth against FMCG volume growth.
- **Subscription Revenue**: Annuity-like, but capped by TRAI NTO rules.
- **Content Cost / Programming Cost**: The biggest expense. Track it as a % of revenue. If content cost is rising while viewership share (BARC) is falling, the broadcaster is losing ROI on its programming.

**3. Print (Newsprint & Circulation):**
- **Newsprint Cost**: Extract from `get_company_context(section='filings', sub_section='notes_to_accounts')`. Newsprint is a global commodity. A 10% drop in newsprint prices flows directly to the EBITDA line.
- **Circulation Revenue**: Covers the cost of printing and distribution. Ad revenue provides the profit.

### Cash Flow vs. P&L — The Amortization Divergence
For content creators and broadcasters, PAT is an accounting opinion; Operating Cash Flow (OCF) is a fact.
- **Content Advances & Inventory**: Broadcasters pay hundreds of crores upfront for movie satellite rights or OTT series. This sits in inventory/advances and is amortized over years.
- Compare **EBITDA** to **CFO (Cash Flow from Operations)** via `get_fundamentals(section='cash_flow_quality')`.
- If a broadcaster reports ₹1,000 Cr EBITDA but CFO is ₹200 Cr, they are aggressively capitalizing content costs that aren't generating cash. This is a massive red flag.

### Working Capital & Receivables
- **DAVP / Government Receivables**: Print and news broadcasters rely heavily on government ads (DAVP). These receivables can stretch to 180-360 days, especially around state/general elections.
- Check `get_fundamentals(section='working_capital')` for debtor days. A spike in debtor days alongside an ad-revenue spike usually means they booked government ad revenue that won't convert to cash for a year.

### Capital Allocation — The OTT Cash Burn
For broadcasters, the most critical financial metric is how much cash the legacy linear TV business is generating, and how much of that is being incinerated by the OTT/digital arm.
- Extract segmental financials via `get_annual_report(section='segmental')`.
- Isolate the OTT EBITDA loss. Calculate: `OTT Loss / Linear TV Free Cash Flow`. If this ratio exceeds 40-50%, the digital transition is threatening the dividend/survival of the core business.
