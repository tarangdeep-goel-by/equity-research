## Media & Entertainment Mode (Auto-Detected)

This company is in the media, entertainment, exhibition, or publishing sector. The sector is highly fragmented; you must immediately identify the sub-sector (Multiplex, Broadcasting, Print, Music/Content IP, or Digital/Gaming) as their economics and KPIs have almost zero overlap.

**The Ind-AS 116 Distortion (Critical for Multiplexes):**
For exhibition companies (PVR Inox), Ind-AS 116 (effective FY20) capitalizes lease rentals. Rent is a multiplex's largest fixed cost. Post-Ind-AS 116, rent is removed from operating expenses and replaced with depreciation and interest, artificially inflating EBITDA margins from ~15-18% to ~30-35%. **Never compare post-FY20 EBITDA to pre-FY20 EBITDA without adjusting for lease liabilities.** When using EV/EBITDA, Enterprise Value *must* include lease liabilities if using reported EBITDA.

**Primary Valuation Metrics by Sub-Sector:**
- **Multiplexes**: EV/EBITDA (adjusted for Ind-AS 116) + **EV/Screen** (replacement cost cross-check).
- **Broadcasting / TV**: SOTP (Linear TV cash cow valued on normalized P/E + OTT digital arm valued on EV/Sales or DCF).
- **Music / Content IP**: EV/EBITDA on licensing annuity + DCF of the content library.
- **Print / Publishing**: P/E on ad-cycle-normalized earnings + Dividend Yield (mature cash cows).

**Metrics that mislead in Media:**
- **P/E at ad-cycle peak**: Ad revenue is highly cyclical (tied to GDP, FMCG spending, and elections). Peak ad-cycle earnings make the P/E look cheap right before the cycle rolls over.
- **P/B for Content/Music companies**: The economic moat is the IP library (music rights, movie catalogs), which is heavily amortized or not marked-to-market on the balance sheet. P/B structurally undervalues content owners.
- **Reported PAT for OTT-builders**: Broadcasters building OTT platforms (Zee5, SunNXT, JioCinema/Viacom18) expense heavy content and customer-acquisition costs, depressing consolidated PAT. Look at standalone linear-TV cash flow vs. OTT cash burn.

### Mandatory — Sub-Sector KPI Backbone

Every media report must anchor on the specific operational KPIs for its sub-sector. A report lacking these is structurally incomplete:
- **Multiplexes (PVR Inox)**: Screen additions/closures, **Footfalls** (mn), **Occupancy %**, **ATP** (Average Ticket Price in ₹), and **SPH** (Spend Per Head on F&B in ₹). F&B is the profit engine (70%+ margin); tickets are split with distributors.
- **Broadcasting (Zee, Sun TV, Network18)**: **Ad vs. Subscription revenue mix** (%), **BARC Viewership / TRP share** (the leading indicator for future ad-rates), and OTT MAU/paid-subscriber additions.
- **Print (DB Corp, Jagran)**: Circulation revenue vs. Ad revenue mix, and **Newsprint cost** (₹/MT).
- **Music (Saregama, Tips)**: Digital licensing revenue growth, new content acquisition capex vs. catalog revenue share.

Source these from `get_company_context(section='concall_insights')`, `get_deck_insights(sub_section='key_metrics')`, or `get_company_context(section='sector_kpis')`.

### Content Amortization Cross-Check
For broadcasters and content creators, cash flow diverges massively from P&L due to content amortization. Cash is spent upfront to acquire movies/shows, but the P&L expense is amortized over 1-5 years. Check `get_fundamentals(section='cash_flow_quality')`: if Operating Cash Flow (OCF) is consistently and materially lower than EBITDA, the company is trapped in a content-capex treadmill.

### Annual Report & Investor Deck — Media Specifics

**AR high-signal sections:**
- `notes_to_financials` — content amortization policy (e.g., "60% of movie rights amortized in year 1"), lease liability schedules (for multiplexes), newsprint inventory valuation.
- `mdna` — BARC viewership share trends, ad-yield commentary, FMCG ad-spend environment, box office pipeline (Bollywood/Tollywood/Hollywood).
- `risk_management` — TRAI tariff order impacts, piracy, reliance on top-10 advertisers, newsprint import reliance.
- `segmental` — Linear TV vs. Digital/OTT (crucial for margin drag analysis), Print vs. Radio.

**Deck high-signal sub_sections:**
- `key_metrics` — ATP, SPH, Occupancy (Multiplex); MAUs, Watch-time (OTT); Circulation copies (Print).
- `outlook_and_guidance` — Screen addition guidance, content acquisition budgets, subscription pricing hikes.

**Cross-year narrative cues:** `capital_allocation_shifts` reveal pivots from linear to digital (OTT cash burn) or from aggressive screen expansion to debt reduction.
