## Media & Entertainment — Valuation Agent

### Sub-type Routing — Match the Multiple to the Moat
Media valuation requires strict sub-sector routing. Applying a generic P/E across this sector will result in catastrophic mispricing.

| Subtype | Primary multiple | Supplementary | Commonly-misapplied that fail |
| :--- | :--- | :--- | :--- |
| **Multiplex (PVR Inox)** | Pre-IndAS EV/EBITDA | EV/Screen (Replacement cost) | P/E (distorted by IndAS 116 depreciation/interest) |
| **Broadcasters (Zee, Sun)** | SOTP (Linear P/E + OTT EV/Sales) | EV/EBITDA on consolidated | P/B (brand/library not on book) |
| **Music IP (Saregama)** | EV/EBITDA on licensing | DCF of catalog | P/B, Dividend Yield |
| **Print (DB Corp)** | P/E on normalized earnings | Dividend Yield | EV/Sales (low margin business) |
| **DTH / Cable** | EV/EBITDA | FCF Yield | P/E (high depreciation on set-top boxes) |

### Multiplex Valuation — The Ind-AS 116 Trap and EV/Screen
**1. The Ind-AS 116 Adjustment:**
Reported EBITDA for multiplexes includes lease rentals added back. If you apply a historical (pre-FY20) EV/EBITDA multiple of 12-15x to *post-FY20* reported EBITDA, you will massively overvalue the company.
- *Rule*: Either use **Pre-IndAS 116 EBITDA** (often disclosed in investor decks via `get_deck_insights`) and apply historical multiples.
- *Or*: Use reported EBITDA, but you MUST add **Lease Liabilities** to Net Debt when calculating Enterprise Value. Route via `calculate`.

**2. EV/Screen Cross-Check:**
Compute `EV / Total Screens`.
- Replacement cost for a new premium screen in India is roughly ₹3 to ₹4.5 Cr (capex + deposits).
- If PVR Inox trades at an EV/Screen of ₹8-10 Cr, the market is paying a massive premium for the brand, F&B pricing power, and monopoly location access. If it drops near ₹4-5 Cr, it is trading at replacement cost (cycle trough).

### Broadcasters — SOTP and Ad-Cycle Normalization
**1. Ad-Cycle Normalization:**
Do not apply a P/E multiple to trailing-twelve-month (TTM) earnings if the TTM period included a general election, a post-COVID revenge-ad-spend boom, or a severe FMCG margin-squeeze.
- Pull 5-7 years of ad-revenue history via `get_fundamentals(section='cagr_table')`.
- Normalize the ad-growth rate (typically 8-10% through-cycle).
- Apply the target P/E (10-15x for mature linear TV) to the *normalized* PAT.

**2. SOTP for OTT:**
Broadcasters' consolidated earnings are dragged down by OTT losses.
- Value the **Linear TV** business on normalized P/E or EV/EBITDA.
- Value the **OTT / Digital** business separately, typically on EV/Sales (2-4x depending on MAU growth and ARPU) or a DCF of future subscription cash flows.
- *Warning*: If the OTT platform is sub-scale and burning cash with no path to top-3 market share, apply a *negative* value or zero to the OTT arm, rather than a generous EV/Sales multiple. Call `get_valuation(section='sotp')` and adjust.

### Music IP — Valuing the Annuity
Music labels (Saregama, Tips) are asset-light IP monopolies. Once a song is acquired, it generates high-margin digital licensing revenue (Spotify, YouTube, Instagram reels) for decades.
- These trade at premium multiples (25-40x EV/EBITDA) because the catalog revenue is an inflation-protected annuity with near-100% flow-through to EBITDA.
- Decompose the multiple: What is the market pricing for *catalog* (old songs, pure annuity) vs. *new content* (high acquisition cost, hit-or-miss)? If new content acquisition costs are rising faster than digital revenue, the premium multiple is at risk.

### What Fails for Media — Name These Explicitly
- **P/B for Content/Broadcasters**: The true assets (movie rights, music IP, brand equity, BARC slot dominance) are intangible and heavily amortized. Book value is an accounting fiction here.
- **P/E for Multiplexes**: Depreciation (on fit-outs and Ind-AS 116 leases) and Interest (on leases) wipe out PAT even when unit-level cash flow is healthy. P/E is meaningless.
- **Peak-Cycle P/E for Print**: Print media is a melting ice cube structurally, but highly cyclical. A low P/E during a peak ad-year is a value trap. Anchor to Dividend Yield instead.
