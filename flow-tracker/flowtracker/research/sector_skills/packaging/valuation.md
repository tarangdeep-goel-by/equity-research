## Packaging & Paper — Valuation Agent

### Sub-type Routing — EV/EBITDA is the Anchor
Valuation frameworks must strictly bifurcate based on the Producer vs. Converter dynamic. 

| Subtype | Primary multiple | Supplementary | Commonly-misapplied that fail |
| :--- | :--- | :--- | :--- |
| **Converters (Tubes, Cartons)** | Forward EV/EBITDA (8-12x) | Forward P/E (15-25x) | P/B (understates high-ROCE value) |
| **Film Producers (BOPP/BOPET)** | EV/EBITDA on through-cycle | P/B at cycle trough | P/E at peak (cheap-trap) |
| **Paper & Board Mills** | EV/EBITDA on through-cycle | P/B at cycle trough | P/E at peak (cheap-trap) |
| **Glass/Rigid Packaging** | EV/EBITDA (6-9x) | EV/tonne of furnace capacity | DCF without capex normalization |

### The Cyclical PE Trap — Mandatory Warning for Films & Paper
For upstream producers (Polyplex, Cosmo First, JK Paper), earnings are cyclically inflated at the peak of a spread cycle. A film producer trading at 4x P/E is usually a screaming **sell**, signaling that spreads are at an unsustainable peak and are about to mean-revert downward. Conversely, a 25x P/E (or negative P/E) often marks the trough when spreads are compressed. 
**Rule:** Never assign a target P/E to a film or paper producer based on trailing earnings. Route to EV/EBITDA using normalized, through-cycle EBITDA/kg.

### Through-Cycle EBITDA Normalization (For Producers)
Do NOT apply EV/EBITDA on trailing-twelve-month (TTM) EBITDA for film and paper producers. 
1. Pull 7-10 years of EBITDA/kg or EBITDA/tonne history via `get_fundamentals(section='cagr_table')` or concall extraction.
2. Identify the mid-cycle spread (e.g., ₹15-20/kg for BOPP films, rather than the ₹40/kg peak or ₹5/kg trough).
3. Multiply this through-cycle EBITDA/kg by current nameplate capacity.
4. Apply the sub-sector target multiple (typically 4-6x EV/EBITDA for commodity producers).
5. Route arithmetic through `calculate` with `through_cycle_ebitda_per_kg`, `capacity`, and `target_multiple` as named inputs.

### Valuing the Converters — The Compounder Premium
Converters (EPL, TCPL) deserve higher multiples (8-12x EV/EBITDA, 15-25x P/E) because their earnings are insulated from raw material volatility via pass-through contracts. Their valuation is driven by:
- **Volume Growth (g):** Typically tracking FMCG volume growth (5-8%) + market share gains from unorganized players.
- **ROCE:** Converters operate at 15-25% ROCE. 
- **VAP Mix:** A higher share of specialty/sustainable packaging justifies the upper end of the multiple band.
Compute justified EV/EBITDA via `calculate` using ROIC, WACC, and growth rate.

### SOTP — De-merging the Conglomerates
Many packaging companies are conglomerates requiring SOTP via `get_valuation(section='sotp')`:
- **UFlex:** Value the commodity packaging films division at a cyclical multiple (4-5x through-cycle EV/EBITDA), but value the Aseptic packaging (Asepto) and flexible converting divisions at a higher converter multiple (7-9x).
- **Century Textiles:** Value the Paper & Pulp division separately from the Real Estate (Birla Estates) division. 
If the tool returns consolidated metrics, manually bifurcate the EBITDA based on `get_annual_report(section='segmental')` and apply distinct multiples.

### What Fails for Packaging — Name These Explicitly
- **EBITDA Margin % as a valuation driver:** As explained in `_shared.md`, margin % fluctuates wildly with raw material prices even if absolute profit is stable. Valuing a company based on "margin expansion" when it's purely RM deflation is a fatal error.
- **Extrapolating peak film spreads:** Assuming a ₹40/kg BOPET spread will persist in a DCF model.
- **Ignoring the lag:** Penalizing a converter's valuation for a weak quarter that was purely driven by a 60-day RM pass-through lag.
