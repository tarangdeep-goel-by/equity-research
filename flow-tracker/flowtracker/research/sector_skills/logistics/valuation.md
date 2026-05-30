## Logistics — Valuation Agent

### Sub-type Routing — Match the Multiple to the Model
Logistics spans asset-light compounders and asset-heavy cyclicals. Applying the wrong multiple is the most common error. Route strictly based on the business model:

| Subtype | Primary multiple | Supplementary | Commonly-misapplied that fail |
| :--- | :--- | :--- | :--- |
| **Express / B2B & B2C** | Forward PE | EV/EBITDA, EV/Sales (if early stage) | P/B (no assets to anchor) |
| **3PL / Contract Logistics** | Forward PE | EV/EBITDA | P/B |
| **Rail / EXIM Logistics** | EV/EBITDA | P/E | EV/Sales (margins matter too much) |
| **Road (PTL)** | EV/EBITDA | Forward PE | P/B |
| **Marine Shipping** | P/B at trough, EV/EBITDA | Dividend Yield | PE at peak (cheap-trap) |
| **Shipbuilding** | Forward PE | EV/EBITDA | P/B |

### The Operating Leverage Dynamic (Express & 3PL)
For asset-light networks (Delhivery, Blue Dart), the network is a fixed cost (hubs, sorters, line-haul routes). Once utilization crosses breakeven, incremental volume drops almost entirely to EBITDA. 
- **Valuation implication**: Trailing PE or EV/EBITDA will look optically absurd (e.g., 100x+) during the inflection phase. 
- **Action**: You must value these on **normalized forward margins**. Call `calculate` to project EBITDA based on management's target utilization rates (from `get_deck_insights(sub_section='outlook_and_guidance')`), or explicitly state that the current multiple reflects early-stage operating leverage, not steady-state expensive valuation.

### SOTP — Mandatory for Integrated Logistics
Many Indian logistics companies are conglomerates of distinct business models. A consolidated multiple destroys value visibility.
- **Example (TCI)**: Freight Division (FTL/PTL - value at 10-12x EV/EBITDA) + Supply Chain Division (3PL - value at 20-25x PE) + Seaways Division (Coastal Shipping - value at 5-7x EV/EBITDA).
- **Example (Allcargo)**: International Supply Chain (Global Forwarding) + Express (Gati) + Contract Logistics.
Call `get_valuation(section='sotp')`. If the tool returns empty, manually construct the SOTP using segmental EBITDA from `get_annual_report(section='segmental')` and apply sub-sector specific multiples.

### Ind-AS 116 Lease Adjustments — The EBITDA Illusion
Under Ind-AS 116, operating leases (rent for warehouses and trucks) are capitalized. Rent expense moves below EBITDA (to depreciation and interest). 
- This artificially inflates EBITDA margins for asset-light players who lease heavily.
- **Rule**: When comparing EV/EBITDA across peers, ensure you are comparing apples-to-apples. If one peer owns trucks (VRL) and another leases them (TCI), their reported EBITDAs are not directly comparable without Ind-AS 116 normalization. 
- Use **Pre-Ind AS 116 EBITDA** (often disclosed in investor decks) or rely on **ROCE** and **P/E** which normalize for capital structure.

### Cyclical Trap — Marine Shipping
For GE Shipping or SCI, apply the exact same cyclical rules as Metals:
- **PE is inverted**: Lowest PE marks the freight-rate peak; highest PE marks the trough. Do NOT cite PE in isolation.
- **Primary Valuation**: **P/B**. Shipping companies trade at a discount to NAV (Net Asset Value of the fleet) at the trough, and a premium at the peak.
- **Through-cycle EV/EBITDA**: Normalize TCE (Time Charter Equivalent) rates over 10 years. Do not extrapolate peak spot rates.

### What Fails for Logistics — Name These Explicitly
- **Applying Express/3PL multiples to FTL trucking**: FTL is a commoditized, low-margin business. It deserves 8-10x EV/EBITDA. Express/3PL deserves 20x+. Blurring them overvalues the trucker.
- **Valuing Rail Logistics without DFC terminal capacity**: A rail operator's moat is its land banks (ICDs) along the DFC. P/E misses the replacement cost of these terminals.
- **Ignoring Fuel Surcharge (FSC) lag**: Assuming margin expansion during a diesel price spike without checking the company's FSC lag (usually 30-45 days).

### Open Questions — Logistics Valuation-Specific
- "For Express/3PL: What is the normalized steady-state EBITDA margin assumed in the forward multiple, and what network utilization level is required to achieve it?"
- "For Integrated players: What are the distinct multiples applied to the Freight, 3PL, and Shipping divisions in the SOTP?"
- "Are the EV/EBITDA multiples being compared pre-Ind AS 116 or post-Ind AS 116, and how does the leased-vs-owned asset mix distort the comparison?"
