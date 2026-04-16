## BFSI — Valuation Agent

### Sub-type Routing — Primary Multiple Is Not PE
The most common valuation error in BFSI is defaulting to a PE + EV/EBITDA triangle. For deposit-taking entities debt is raw material, not capital structure, so EV-based multiples are structurally broken. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- |
| **PSU bank** | P/ABV (P/B on book adjusted for Net NPA) | EV/EBITDA (no EBITDA), DCF-FCFE (CFO swings with deposit flow), EV/Revenue |
| **Private bank** | P/ABV + P/B-ROE (justified P/B = ROE/CoE) | EV/EBITDA, sector-relative PE without adjusting for asset quality |
| **Life insurer** | P/EV (price to embedded value), P/VNB-multiple | PE on accounting earnings (IFRS-17 optics), EV/EBITDA |
| **General insurer** | P/B-ROE + underwriting-profit multiple | PE on low-combined-ratio year (mean-reverts), EV/EBITDA |
| **NBFC (lending)** | P/B adjusted for credit cost and P/B-ROE | PE on peak-cycle earnings, EV/EBITDA |
| **AMC** | P/AUM% (% of AUM) + PE on normalized fee yield | EV/EBITDA on one-off performance-fee spike |
| **Exchange** | EV/Revenue (take-rate anchored) + PE | P/B (book is mostly idle float), EV/EBITDA on peak-ADTV year |
| **Broker** | PE on through-cycle active-client monetisation | P/B (book is float), EV/EBITDA on F&O-peak year |
| **Microfinance NBFC** | P/B adjusted for regional concentration risk | PE at cycle peak (JLG losses mean-revert hard) |
| **Gold-loan NBFC** | P/B adjusted for LTV cycle + P/B-ROE | PE on peak gold-price year |

### P/ABV — Show the Net NPA Deduction Explicitly
Adjusted Book Value strips the portion of book represented by net non-performing assets that have not yet been fully provisioned. The computation is: `ABV per share = BVPS − (Net NPA ÷ shares outstanding)`. Current `P/ABV = CMP ÷ ABV per share`. Compare against the 5Y P/ABV band via `get_valuation(section='band', metric='pb')` with `get_chart_data(chart_type='pbv')` as the deep-history fallback when the band call returns fewer than 20 quarterly observations. The skip-step surfaced in prior valuation evals is computing P/B against reported BVPS and forgetting the Net NPA deduction — for a PSU bank with NNPA 1.5-2.5%, the deduction is ~3-5% of BVPS and materially changes the re-rating narrative. Route the arithmetic through `calculate` with `shares_out`, `bvps`, and `net_npa_per_share` as named inputs.

### Historical Band Context — Regime-Shift Caveats
A 5-10Y P/B band via `get_chart_data(chart_type='pbv')` gives the long-arc context (current vs median vs trough-peak). But the band has regime breaks that should be stated, not smoothed over. For any private bank that has absorbed a large holdco or housing-finance merger, the pre-merger and post-merger P/B series are not directly comparable — the book jumps stepwise while the earnings ramp plays out over several quarters. For PSU banks, the post-AQR asset-quality-review trough and the post-COVID re-rating regime are structurally distinct; averaging across them produces a misleading median. Always state the regime break when citing "current vs 10Y median P/B".

### SOTP — Biggest Valuation Unlock in BFSI
For private banks and holding-style financials, SOTP is often the lever that re-rates the stock. The mechanical error surfaced in prior evals was "empty SOTP" — the agent cited that SOTP was relevant but didn't build it. Enumerate:
1. Call `get_valuation(section='sotp')` for the tool-computed view of listed subsidiary value.
2. For each listed subsidiary, take the current market cap, multiply by the parent's stake %, and land a per-share contribution.
3. For each **unlisted** subsidiary, apply a sector multiple: AMC at **3-5% of AUM** (premium names toward the higher end), life insurer at **1.5-3× embedded value** (growth × VNB-margin premium), general insurer at **1.0-2.5× annual premium income**, NBFC arm at **1.0-2.5× book** (calibrate to subsidiary-specific ROE and credit profile).
4. Apply a **20-25% holding-company discount** to the aggregate sub-value before adding to the standalone bank's P/ABV value.
5. Back out implied P/ABV on the **standalone** (ex-SOTP) bank — this is the number the market is really paying for the core franchise.

### Forward-Multiple Sanity — Justified P/B = ROE ÷ CoE
The Gordon framework for a mature franchise: `Justified P/B = (ROE − g) ÷ (CoE − g)`. For a simple steady state, `Justified P/B ≈ ROE ÷ CoE`. If observed P/B materially exceeds this justified level, reverse-out what ROE expansion the market is pricing in, then stress-test it: does the current balance-sheet leverage allow that ROE at realistic credit cost and risk-weighted-asset growth? A bank trading at 3.0× P/B with reported 16% ROE at 12% CoE has justified P/B near 1.33× — 3.0× is pricing in sustained 36%+ ROE expansion, which on regulated leverage is rarely credible. Call `calculate` with CoE from `get_market_context(section='macro')` and published ROE; the WACC/CoE helper route adds country-risk premium.

### Peer Premium / Discount Decomposition
If the stock trades at a P/ABV premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into at most four drivers: (a) NIM spread vs peer — 30-100 bps of sustained NIM advantage justifies 10-20% premium, (b) ROA delta — 20-50 bps of ROA advantage justifies 15-25% premium, (c) asset-quality delta — GNPA and credit-cost below peer median justifies 10-15% premium, (d) liability-franchise quality — CASA 500-1000 bps above peer is a structural premium driver. If (a) through (d) together do not account for more than half of the observed premium, the multiple is vulnerable to mean-reversion and the bull-case is leaning on re-rating rather than on earnings growth.

### What Fails for BFSI — Name These Explicitly
- **EV/EBITDA** — debt is raw material, not capital structure; adding back interest expense destroys the signal.
- **EV/Revenue** — net revenue concept (NII + fee) is already the "margin-adjusted top line"; scaling by EV double-counts.
- **DCF / Reverse-DCF on FCFE** — operating cash flow oscillates with deposit and loan flows, not with earnings quality. FCFE models produce false-precision terminal values.
- **Simple PE on trailing earnings** — banks with heavy provisioning tailwinds look optically cheap on PE while ROA is peaking; AMCs with performance-fee-spike years look optically cheap on PE while fees mean-revert.
- Use instead: P/B-ROE (Gordon framework), Residual Income Model, Dividend Discount Model for mature PSU payers, and sub-type-specific multiples above.

### Data-shape Fallback for Asset Quality
When `get_quality_scores(section='bfsi')` returns missing GNPA, NNPA, PCR, or CASA, the concall extractor did not capture these canonical KPIs in `operational_metrics`. Fall back to `get_company_context(section='concall_insights', sub_section='financial_metrics')` and `sub_section='management_commentary')` and extract from the prose; cite the specific quarter. If the concall is silent, add to Open Questions with the specific metric name and explain that P/ABV cannot be computed rigorously without Net NPA.

### Open Questions — BFSI Valuation-Specific
- "What Net NPA per share was used to compute ABV, and from which quarter's disclosure?"
- "If unlisted subsidiary embedded value has not been disclosed for 2+ quarters, what sector-multiple range was applied and with what CoE stress?"
- "Does the current P/B premium to sector median reconcile with the NIM + ROA + asset-quality + CASA decomposition, or is there a residual multiple gap?"
- "Is the trailing PE distorted by a credit-cost tailwind or a one-off treasury gain that should be normalised before peer PE comparisons?"
