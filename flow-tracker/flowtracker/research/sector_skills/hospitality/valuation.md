## Hospitality — Valuation Agent

### Sub-type Routing — Match the Metric to the Model
Hospitality spans capital-heavy real estate (owned hotels) and high-growth consumer franchises (QSR). Route valuation accordingly:

| Subtype | Primary multiple | Supplementary | Commonly-misapplied that fail |
| :--- | :--- | :--- | :--- |
| **Asset-Heavy Hotels** | EV/EBITDA | EV/Room (Replacement Cost) | P/E (distorted by high depreciation) |
| **Asset-Light / Blended Hotels** | EV/EBITDA | P/E (normalized) | EV/Room (meaningless for managed rooms) |
| **QSR (Master Franchisees)** | EV/EBITDA (Pre-Ind AS 116) | P/E | Post-Ind AS 116 EV/EBITDA without lease adj. |
| **Travel Platforms (OTA)** | P/E | EV/FCF | EV/EBITDA (ignores working cap dynamics) |

### EV/Room — The Hotel Reality Check
For asset-heavy hotels (or the owned portion of blended hotels), EV per owned room is the ultimate cross-validation against replacement cost. 
- **Luxury (Taj/Oberoi):** Replacement cost is ₹2.0-3.5 Cr per key.
- **Upscale/Mid-scale:** Replacement cost is ₹0.8-1.5 Cr per key.
Compute: `EV / Owned Rooms = (Market Cap + Net Debt) / Total Owned Keys`. (Exclude managed keys from the denominator). If a hotel trades at ₹5 Cr/key, it is either heavily overvalued, or the market is assigning massive value to its management-contract pipeline. Decompose this explicitly.

### The QSR SSSG-Multiple Link
QSR multiples (often 40-70x P/E or 25-40x EV/EBITDA) are priced for perfection. They are justified ONLY by compounding SSSG (Same-Store Sales Growth) + unit expansion.
- **Positive SSSG (5-10%):** Justifies premium multiples (operating leverage kicks in, store paybacks shrink).
- **Negative/Flat SSSG:** Breaks the multiple. If SSSG is negative, store additions are merely masking revenue stagnation, and new stores will have terrible unit economics. 
If valuing a QSR, pull SSSG from `get_company_context(section='sector_kpis')`. If SSSG is negative, explicitly state that historical premium multiples are at risk of mean-reversion.

### Ind AS 116 — Mandatory Valuation Adjustments
You MUST align the EV and the EBITDA. 
- **Approach 1 (Preferred for QSR): Pre-Ind AS 116.** Use Pre-Ind AS 116 EBITDA (rent deducted as an expense). Use standard Net Debt (excluding lease liabilities). 
- **Approach 2: Post-Ind AS 116.** Use reported Post-Ind AS 116 EBITDA. You MUST add **Lease Liabilities** to Net Debt in the EV calculation. 
Mixing Post-Ind AS 116 EBITDA with a Net Debt figure that excludes lease liabilities artificially deflates the EV/EBITDA multiple, making the stock look falsely cheap. Check `get_fundamentals(section='balance_sheet_detail')` for lease liabilities.

### SOTP for Blended Hotels
For companies like INDHOTEL or CHALET, a single multiple collapses distinct businesses:
1. **Owned Hotels:** Value on EV/EBITDA (15-20x mid-cycle) or EV/Room.
2. **Management Contracts (Asset-Light):** Value at a premium consumer-franchise multiple (25-35x EV/EBITDA) because ROCE is infinite/extremely high.
3. **Commercial Real Estate (Chalet):** Value on Cap Rate / Lease discounting.
Call `get_valuation(section='sotp')`. If the tool defaults to a blended multiple, manually highlight the asset-light premium.

### What Fails for Hospitality — Name These Explicitly
- **Trailing P/E at Hotel Cycle Peak:** Like metals, hotel earnings are cyclical. Peak ARR drops straight to PAT, making P/E look artificially cheap (e.g., 15x) right before the cycle rolls over. Anchor to mid-cycle RevPAR.
- **Valuing QSR purely on Store Additions:** Giving a target multiple based on "adding 200 stores a year" while ignoring negative SSSG. Store additions with negative SSSG destroy ROCE.
- **Ignoring Franchise Royalty Increases:** Master franchisees (Devyani, Sapphire, Jubilant) pay royalties to Yum/Domino's. A 100 bps hike in royalty rates permanently impairs the DCF value. Check filings for royalty terms.
