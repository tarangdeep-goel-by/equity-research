## Insurance — Ownership Agent

Inherits the insurance `_shared.md` framing (VNB, APE, EV, Combined Ratio, 150% solvency). This file adds the ownership-lens framing — promoter archetype, foreign cap, ESOP overhang, and LIC quasi-sovereign pattern that apply specifically to listed insurers and insurtech platforms.

### IRDAI Framework — Promoter Structure & Foreign Cap
Insurance in India is governed by IRDAI under the Insurance Act 1938 (s.2(7A), post-2021 amendment). The aggregate foreign-holding cap is **74%** — this combines FDI + FPI + ADR/GDR + NRI. "Indian owned and controlled" status is a separate IRDAI compliance requirement on top of the 74% ceiling.

- When foreign aggregate >68%, headroom to cap is <6pp — flag capacity constraint for incremental FII buying
- Promoter/sponsor archetypes are structurally sticky — Tenet 9 applies (absence of open-market promoter trade is not informational)

### Promoter Archetypes — Listed Insurers
- **Foreign insurer parent** — SBI Life (Cardif BNP Paribas), ICICI Pru Life (Prudential UK), HDFC Life (historically Standard Life, now post-merger structure), Max Life (Mitsui Sumitomo). Foreign parents sit close to the 74% aggregate cap by design — remaining foreign headroom is often already consumed by promoter itself
- **Strategic bancassurance tie-up** — parent-bank distribution is the core moat (SBIN → SBILIFE, HDFCBANK → HDFCLIFE, ICICIBANK → ICICIPRULI). Renegotiation risk on the bancassurance agreement is an ownership-adjacent structural risk — flag in Open Questions if the parent-bank relationship is up for renewal
- **Standalone insurer / IPO** — LICI (Govt of India promoter), STARHEALTH, POLICYBZR (PB Fintech) — no bancassurance anchor; distribution depends on agency, digital, or broker channels

### LIC Anchor Pattern
LIC (Life Insurance Corporation of India) is the largest institutional holder across Indian large-caps — typically 4-9% in listed private-sector insurers, 3-6% in listed general insurers.
- Treat LIC the same way BFSI ownership treats it — quasi-sovereign structural floor, not active conviction
- **LIC as promoter vs LIC as institutional holder** — for LICI itself, the Govt of India is promoter; LIC's holdings in other listed insurers are institutional. Do NOT classify LIC's own self-held scheme inventory in LICI as "institutional buying"
- When LIC adds stake YoY in a life insurer during an EV-growth acceleration, read as sovereign-style structural conviction, not tactical

### Insurtech / Aggregator Platforms — ESOP Trust Overhang (Mandatory Main-Text Narrative)
For listed insurtech platforms (POLICYBZR / PB Fintech, STARHEALTH's employee trust, ACKO if listed, and similar), **ESOP trust holdings are a structural float-expansion variable that must appear in the main report narrative — not only in the JSON briefing**. Silent main text with "ESOP" mentioned only in JSON is a workflow violation (see Tenet 15 in SYSTEM prompt).

- **Quantify the ESOP pool as % of total equity** — sourced from AGM notices, DRHP (at listing), and annual reports. Typical range: 6-12% of paid-up at listing, diluting to ~8% over 3-5 years as trust grants vest and distribute to individuals
- **Vesting-cycle distributions** — when employees exercise and sell, shares move from the ESOP trust category into the public category. This is **effective float expansion** even though total shares outstanding doesn't move
- For insurtech / broker / platform businesses, the ESOP trust distribution is a **multi-year overhang** on stock price — continuous supply at the margin unless offset by buybacks or strong institutional absorption
- Narrate in the main report: pool size, current trust-held %, historical quarterly distribution rate, and implied months-to-clear at current absorption

#### Quantifying the ESOP Pool — Apply Tenet 14 Search Sequence
When the ESOP narrative is required, you MUST actively quantify the pool size — not leave it as an Open Question. Run the canonical 5-source search sequence (Tenet 14) with insurtech-specific queries:
- `query='ESOP'` OR `'Employee Stock Option'` OR `'Employees Welfare Trust'` (the named-trust pattern; e.g. "PB Fintech Employees Welfare Trust" appears in `shareholder_detail`)
- AGM notices and DRHP (in `filings`) almost always disclose the AGM-approved pool ceiling and current grant balance — primary source for insurtech listings.

Identifying ESOP overhang and then asking "how big is it?" without running the sequence is the workflow gap Gemini flagged in the POLICYBZR smoke run.

### Embedded Value (EV) Growth as Institutional-Conviction Proxy (Life Insurers)
For listed life insurers (SBILIFE, HDFCLIFE, ICICIPRULI, MAXFIN-LIFE), institutional conviction correlates with **EV growth trajectory**, not P/E. Reported P/E can look expanded (30-60x trailing) while EV is compounding at 18-22% with VNB margin expansion.
- When mutual funds add during an EV-growth acceleration coincident with rising VNB margin commentary in the concall, read as **high-conviction accumulation** even against a superficially expensive P/E
- Cross-check with Operating RoEV (see insurance/financials.md) — if Operating RoEV is strong (>18%) and MF adds are concurrent, narrative = genuine compounding. If Operating RoEV is weak and MF adds are concurrent, narrative = passive/benchmark rebalance, not conviction

### Foreign Cap & Promoter Dynamics — Common Listed-Insurer Pattern
- Foreign parent near the 74% cap + Indian public float thin → headline FII% movements are dominated by parent-promoter quarterly dance, not true new-money flows. Strip promoter category before narrating "FII buying/selling"
- SBI MF is typically the largest domestic MF holder in listed insurers; HDFC MF, ICICI Pru MF also material. Track YoY conviction shift at the individual-MF level via `shareholder_detail`

### Cross-Reference
- **POLICYBZR / PB Fintech** — apply BOTH `broker/` and `platform/` skill lenses in addition to this file. It is an insurtech aggregator, not an underwriter — most VNB/Combined-Ratio framing doesn't apply; Take Rate and subsidiary drag are the right lens (see insurance/financials.md aggregator section)
- **STARHEALTH** — standalone health insurer; general-insurance Combined-Ratio framing applies plus health-specific loss-ratio segmentation

### Standard Sector Framing
- 74% aggregate foreign cap with "Indian owned and controlled" IRDAI compliance on top
- LIC and SBI MF are the two biggest domestic institutional holders across listed insurers
- Promoter stickiness is structural (foreign parent or bancassurance parent) — absence of open-market promoter trade is NOT informational (Tenet 9)
- For insurtech, ESOP trust overhang is a mandatory main-text narrative item (Tenet 15)

### Open Questions — Insurance-Specific
- "Is any bancassurance distribution agreement up for renewal in the next 8 quarters, and what is the renewal track record of the parent?"
- "What is the current ESOP trust holding as % of paid-up, and what is the trailing 4-quarter vesting-distribution run rate?" (for insurtech platforms)
- "Is LIC's current stake in this insurer flagged as strategic (no reduction signal) or tactical (active rebalancing)?"
- "Is the promoter foreign-parent approaching any IRDAI 'Indian owned and controlled' compliance trigger?"
