## Insurance — Ownership Agent

Inherits the insurance `_shared.md` framing (VNB, APE, EV, Combined Ratio, 150% solvency). This file adds the ownership-lens framing — promoter archetype, foreign cap, ESOP overhang, and LIC quasi-sovereign pattern that apply specifically to listed insurers and insurtech platforms.

### IRDAI Framework — Promoter Structure & Foreign Cap
Insurance in India is governed by IRDAI under the Insurance Act 1938. The framework has moved twice: the **2021 amendment** raised the FDI cap to **74%** and **omitted the "Indian owned and controlled" requirement** (Sections 2(7A)/114(2)(aaa)), replacing it with resident-Indian board/KMP safeguards rather than an ownership-control test. The **Insurance Laws (Amendment) Act, 2025** then raised the FDI ceiling to **100%** (automatic route) and further relaxed the board safeguards — only one resident-Indian chairperson/MD/CEO and a minimum of three independent directors are now required (the earlier 50%-independent-board rule for foreign-invested insurers was removed). So "Indian owned and controlled" is **no longer** a live compliance overlay; the binding constraint is the prevailing FDI ceiling plus the resident-director safeguards.

- The aggregate foreign-holding cap (FDI + FPI + ADR/GDR + NRI) is now 100% post-2025 act; verify the company's current articles/promoter structure, since most listed insurers still sit under legacy 74%-era foreign holdings and any move above requires regulatory/board steps
- **IRDAI 5% prior-approval rule** — any single shareholder (with relatives, associates, and persons acting in concert) whose stake will cross **5% of paid-up capital** needs **prior IRDAI approval** under s.6A(4)(b)(iii); 1-5% needs a fit-and-proper declaration. Treat 5% as a hard constraint on tactical open-market accumulation — an institution cannot freely build a large block, so a stake parked just below 5% is a structural ceiling, not a conviction signal
- Promoter/sponsor archetypes are structurally sticky — Tenet 9 applies (absence of open-market promoter trade is not informational)

### Promoter Archetypes — Listed Insurers
- **Foreign insurer parent (verify current stake — do NOT assume near-cap)** — the original foreign JV parents have in several cases largely exited or sharply reduced: BNP Paribas Cardif has been offloading SBI Life via OFS; Standard Life/Abrdn exited HDFC Life (HDFC Bank is now sole promoter post the 2023 HDFC merger); Max Life's structure shifted with Axis Bank becoming a co-promoter alongside the diminished Mitsui Sumitomo role; ICICI Pru Life retains Prudential plc. Do not state "foreign parents sit near the 74% cap by design" as a default — pull the current promoter/foreign-holding split from `shareholder_detail` per name before narrating headroom
- **Strategic bancassurance tie-up** — parent-bank distribution is the core moat (SBIN → SBILIFE, HDFCBANK → HDFCLIFE, ICICIBANK → ICICIPRULI). Renegotiation risk on the bancassurance agreement is an ownership-adjacent structural risk — flag in Open Questions if the parent-bank relationship is up for renewal
- **Standalone insurer / IPO** — LICI (Govt of India promoter), STARHEALTH, POLICYBZR (PB Fintech) — no bancassurance anchor; distribution depends on agency, digital, or broker channels

### LIC Anchor Pattern
LIC (Life Insurance Corporation of India) is the largest institutional holder across Indian large-caps — typically 4-9% in listed private-sector insurers, 3-6% in listed general insurers.
- Treat LIC the same way BFSI ownership treats it — quasi-sovereign structural floor, not active conviction
- **LIC as promoter vs LIC as institutional holder** — for LICI itself, the Govt of India is promoter; LIC's holdings in other listed insurers are institutional. Do NOT classify LIC's own self-held scheme inventory in LICI as "institutional buying" — IRDAI investment regulations prohibit an insurer from investing its controlled/policyholder funds in its own shares, so any LICI shares LIC appears to hold are not a self-conviction signal
- When LIC adds stake YoY in a life insurer during an EV-growth acceleration, read as sovereign-style structural conviction, not tactical

### Insurtech / Aggregator Platforms — ESOP Trust Overhang (Mandatory Main-Text Narrative)
For listed insurtech platforms (POLICYBZR / PB Fintech, STARHEALTH's employee trust, ACKO if listed, and similar), **ESOP trust holdings are a structural float-expansion variable that must appear in the main report narrative — not only in the JSON briefing**. Silent main text with "ESOP" mentioned only in JSON leaves the main narrative incomplete (see Tenet 15 in SYSTEM prompt).

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
- FDI ceiling now 100% (2025 act; was 74% from 2021) — the "Indian owned and controlled" overlay was removed in 2021 and is no longer live; binding constraints are the resident-director/KMP safeguards and the IRDAI 5% prior-approval rule
- LIC and SBI MF are the two biggest domestic institutional holders across listed insurers
- Promoter stickiness is structural (foreign parent or bancassurance parent) — absence of open-market promoter trade is NOT informational (Tenet 9)
- For insurtech, ESOP trust overhang is a mandatory main-text narrative item (Tenet 15)

### Open Questions — Insurance-Specific
- "Is any bancassurance distribution agreement up for renewal in the next 8 quarters, and what is the renewal track record of the parent?"
- "What is the current ESOP trust holding as % of paid-up, and what is the trailing 4-quarter vesting-distribution run rate?" (for insurtech platforms)
- "Is LIC's current stake in this insurer flagged as strategic (no reduction signal) or tactical (active rebalancing)?"
- "Has the original foreign JV parent exited or reduced, and does any single shareholder sit just below the IRDAI 5% prior-approval threshold (a structural ceiling on further accumulation)?"
