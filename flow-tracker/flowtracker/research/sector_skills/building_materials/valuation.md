## Building Materials — Valuation Agent

### Sub-type Routing — Cement vs. Branded Products
Valuation frameworks must strictly follow the sub-archetype. Applying a PE multiple to a cement stock or an EV/tonne multiple to a pipe company is an automatic failure.

| Subtype | Primary Multiple | Supplementary | Commonly-Misapplied |
| :--- | :--- | :--- | :--- |
| **Cement (Pan-India)** | EV/EBITDA (through-cycle) | EV/tonne of capacity | PE (earnings swing with petcoke) |
| **Cement (Regional)** | EV/EBITDA (through-cycle) | EV/tonne (discounted) | PE, DCF without cycle-normalization |
| **Pipes (Plumbing/CPVC)** | Forward P/E | EV/EBITDA | P/B (asset-light, high ROCE) |
| **Tiles / Sanitaryware** | Forward P/E | EV/EBITDA | EV/tonne (irrelevant) |
| **Boards (MDF/Plywood)** | EV/EBITDA | Forward P/E | P/B |

### EV/Tonne Calibration — The Cement Anchor
For cement, EV per tonne of installed capacity is the ultimate cross-validation check. It anchors valuation to the physical replacement cost of the asset.
- **Greenfield Replacement Cost:** Currently ~$80-100/tonne in India (varies by land acquisition and captive limestone availability).
- **Pan-India Leaders:** Trade at $150-$220/tonne. The premium reflects brand, distribution moat, pricing power, and M&A currency.
- **Efficient Regional Leaders:** Trade at $100-$150/tonne.
- **Inefficient/Small-Cap Regional:** Trade at $50-$90/tonne (below replacement cost, signaling distress, poor limestone reserves, or M&A target status).

Compute: `EV / Installed Capacity = (Market Cap + Net Debt) / (Capacity in MTPA * USDINR)`. Call `calculate` with explicit inputs. If a regional player trades at $180/t, decompose it: is it an imminent acquisition target, or is it wildly overvalued?

### Through-Cycle EBITDA Normalization (Cement)
Do NOT apply EV/EBITDA on trailing-twelve-month (TTM) EBITDA for cement if energy prices have been exceptionally high or low.
1. Pull 5-10 years of EBITDA/tonne history via `get_fundamentals(section='cagr_table')` or the financials-agent handoff.
2. Compute the mid-cycle EBITDA/tonne (typically ₹900-1,200/t for efficient players, ₹600-800/t for laggards).
3. Multiply mid-cycle EBITDA/tonne by *forward* capacity (including near-term brownfield additions) to get normalized EBITDA.
4. Apply target multiple (12-18x for pan-India, 8-12x for regional). Route arithmetic through `calculate`.

### Valuing Branded Compounders (Pipes, Tiles, Bathware)
These are consumer-discretionary proxies. The market values them on **growth + ROCE**.
- **The PE Band:** Top-tier pipe/tile players (Astral, Supreme, Kajaria) historically trade at 40-60x forward PE due to high ROCE (>20%) and structural unorganized-to-organized market share gains.
- **De-rating Triggers:** If volume growth decelerates below 10% or ROCE compresses due to aggressive capex/working capital deterioration, the multiple will violently de-rate from 50x to 30x.
- **Inventory Adjustments:** When valuing pipe companies, manually check if TTM earnings are inflated by PVC inventory gains or depressed by inventory losses. Normalize earnings before applying the PE multiple.

### SOTP / Subsidiary Adjustments
- **White Cement / Putty:** If a grey cement company has a large white cement/putty business (e.g., JK Cement, UltraTech), value the white/putty segment separately at a consumer-multiple (15-20x EV/EBITDA) because it is a branded, high-margin, non-cyclical product.
- **Adhesives/Bathware in Pipe Companies:** Astral and others are diversifying into adhesives and bathware. Check if these segments are dragging consolidated margins and value them separately if disclosures permit.

### What Fails for Building Materials
- **PE for Cement:** Inverted signal. Lowest PE occurs at peak margins (low petcoke), highest PE at trough margins.
- **Ignoring Capacity Additions:** Cement valuation must price in the *forward* capacity. A company at 20 MTPA expanding to 30 MTPA fully funded via internal accruals deserves a premium to a stagnant 20 MTPA peer.
- **Consolidated Margin Extrapolation for Pipes:** Extrapolating a 20% margin quarter (driven by PVC inventory gains) into a DCF will overvalue the company by 50%.

### Open Questions — Valuation-Specific
- "What is the implied EV/tonne, and how does it compare to the $80-100/t greenfield replacement cost?"
- "For cement: What mid-cycle EBITDA/tonne assumption is embedded in the target EV/EBITDA multiple?"
- "For branded products: Is the current P/E multiple pricing in >15% volume growth, and does the historical track record support this?"
