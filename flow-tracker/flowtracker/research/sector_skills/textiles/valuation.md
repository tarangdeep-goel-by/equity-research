<valuation-agent guidance: the multiple to anchor, how to normalize, SOTP/segment notes, what NOT to do>
## Textiles & Apparel — Valuation Agent

### Sub-type Routing — The "Brand Illusion" Trap
The most common valuation error in this sector is applying a consumer-discretionary multiple (PE of 40-60x) to a B2B textile manufacturer just because it makes apparel. Route strictly by sub-type:

| Subtype | Primary multiple | Supplementary | Commonly-misapplied that fail |
| :--- | :--- | :--- | :--- |
| **Branded Retail / Fast Fashion** | Forward P/E (35-80x based on growth/ROCE) | EV/EBITDA | P/B (asset-light models make P/B look absurdly high) |
| **Garment Exporters** | EV/EBITDA (10-18x) | Forward P/E (15-25x) | Consumer brand multiples (they are vendors, not brands) |
| **Home Textiles** | EV/EBITDA (8-12x through-cycle) | P/E on normalized earnings | Peak P/E (earnings inflate during US restocking) |
| **Commodity Spinners/Weavers** | EV/EBITDA (5-8x mid-cycle) | P/B at trough (0.8-1.2x) | P/E at peak (cheap-trap due to inventory gains) |
| **Integrated Mills** | SOTP by vertical | EV/Sales for loss-making retail arms | Consolidated P/E |

### Through-Cycle Normalization for Spinners/Weavers
Do NOT apply EV/EBITDA or P/E on trailing-twelve-month (TTM) earnings for commodity textile players. Peak cotton prices create massive, one-off inventory gains that inflate EBITDA margins from a normal 10-12% to 18-22%. 
1. Pull 7-10 years of margin history via `get_fundamentals(section='cagr_table')`.
2. Identify the through-cycle average EBITDA margin (typically 11-14% for top-quartile spinners, 8-10% for mid-tier).
3. Apply this normalized margin to current revenues to derive through-cycle EBITDA.
4. Route arithmetic through `calculate` with `normalized_ebitda_margin`, `current_revenue`, and `target_multiple`.

### SOTP — Mandatory for Integrated Mills (Raymond, Arvind, ABFRL)
Legacy textile companies often house wildly different businesses. A consolidated multiple is meaningless.
1. **Branded Apparel / Retail:** Value on EV/EBITDA (15-25x) or EV/Sales if currently loss-making but scaling.
2. **B2B Textiles (Shirting/Suiting/Yarn):** Value on EV/EBITDA (5-8x).
3. **Real Estate (e.g., Raymond's Thane land):** Value on NAV / P-Presales (refer to real estate guidelines) and add to SOTP.
4. **Holdco Discount:** Apply a 20-25% discount if the value is trapped in unlisted subsidiaries or complex promoter structures.
Call `get_valuation(section='sotp')` and override consolidated defaults.

### Ind AS 116 (Leases) Distortion in Retail Valuation
For retail brands (Trent, ABFRL, Page, Vedant), Ind AS 116 capitalizes store leases, which artificially inflates EBITDA (rent is moved below the line to depreciation and interest) and inflates Net Debt (lease liabilities added).
- When comparing EV/EBITDA across peers, ensure you are using **Pre-Ind AS 116 EBITDA** (often disclosed in investor decks) or **EBITDAR** (Earnings Before Interest, Taxes, Depreciation, Amortization, and Rent).
- If using standard reported EV/EBITDA, ensure the EV includes capitalized lease liabilities. Do not mix Pre-Ind AS 116 EV with Post-Ind AS 116 EBITDA.

### Reverse-DCF on High-Multiple Retailers
For darlings like Trent or Page Industries trading at >70x P/E, standard relative valuation breaks down. Run a reverse-DCF to back out the implied growth rate.
- Take current market cap, apply a 10-12% WACC.
- Solve for the implied 10-year FCF CAGR.
- Translate that FCF CAGR into implied store additions and SSSG. If the stock price implies adding 500 stores a year at 15% SSSG for a decade, state that explicitly. Let the user decide if that operational feat is plausible. Route via `calculate`.

### What Fails for Textiles — Name These Explicitly
- **P/E for Spinners at Cycle Peak:** The classic trap. A spinner trading at 5x P/E is usually a screaming SELL, because earnings are inflated by peak cotton prices and are about to collapse.
- **Valuing Garmenters as Brands:** Gokaldas or KPR Mill making clothes for Zara/H&M does not give them Zara/H&M's pricing power or multiples. They are B2B converters.
- **Ignoring Export Incentives in Margin Profiles:** RoDTEP/RoSCTL incentives can form 40-60% of a garment exporter's PBT. Valuing this policy-dependent revenue stream at a structural 25x P/E is dangerous.

### Open Questions — Textiles Valuation-Specific
- "For integrated mills: What EV/EBITDA multiple was assigned to the B2B textile division vs. the branded retail division in the SOTP?"
- "For high-PE retail brands: What implied 5-year store-addition run-rate and SSSG is embedded in the current market cap via reverse-DCF?"
- "For spinners: Was the EV/EBITDA multiple applied to TTM EBITDA (which may include cotton inventory windfall/losses) or a normalized through-cycle EBITDA?"
