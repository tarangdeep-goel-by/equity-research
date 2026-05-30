## Packaging & Paper — Risk Agent

### Top Structural & Cyclical Risks

**1. The Supply Glut / Overcapacity Risk (Cyclical)**
This is the single biggest risk for upstream film and paper producers. Global capacity additions (especially from China in BOPP/BOPET or ASEAN in paper) dictate spreads. 
- **Pre-mortem check:** Is the global industry adding capacity faster than demand growth (typically 5-6%)? If global capacity is growing at 10%+, spreads will crash regardless of how well the Indian company is managed. Check concall commentary for "industry capacity additions" or "oversupply."

**2. Raw Material Volatility & Pass-Through Failure (Operational)**
While converters have pass-through clauses, extreme volatility breaks the model.
- If polymer prices jump 30% in a quarter, the working capital requirement spikes instantly.
- Smaller FMCG clients may resist price hikes, forcing the converter to absorb the cost or lose the volume. 
- **Pre-mortem check:** What is the company's RM mix? If it is heavily reliant on imported specialty pulp or specific petrochemicals, a supply chain shock or FX depreciation (USD-INR) will compress margins.

**3. Client Concentration (Business)**
Packaging companies often rely on a few anchor FMCG or Pharma clients for 30-50% of their revenue.
- **Pre-mortem check:** Check `get_annual_report(section='risk_management')` or concalls for top-5 or top-10 client concentration. Losing a marquee client (e.g., a major toothpaste brand for EPL, or a major liquor brand for AGI Greenpac) leaves a massive, unfillable hole in capacity utilization.

**4. Regulatory & ESG Risks — The Plastic Ban (Structural)**
The regulatory noose is tightening around single-use plastics and non-recyclable multi-layer packaging (MLP).
- **EPR (Extended Producer Responsibility):** FMCG brands are forcing packaging suppliers to provide PCR (Post-Consumer Recycled) content or mono-material structures.
- **Pre-mortem check:** Companies that fail to invest in sustainable R&D will be delisted from global FMCG vendor panels. Check the deck/AR for the % of portfolio that is "100% recyclable" or "sustainable." If this is missing, the terminal value is at risk.

**5. Import Dumping (Trade)**
Indian paper mills and film producers are highly vulnerable to dumping from China and ASEAN countries with cheaper power and scale.
- **Pre-mortem check:** Track the status of Anti-Dumping Duties (ADD) or Basic Customs Duty (BCD) via `get_events_actions(section='catalysts')` or macro news. The removal or expiry of an ADD on imported paper or BOPP films instantly caps domestic pricing power (Import Parity Pricing ceiling).

### The Pre-Mortem Mandate
A packaging risk assessment MUST answer:
1. "If raw material prices spike 20% next quarter, how many days will it take to pass through, and what is the working capital hit?"
2. "What is the global capacity addition pipeline for this specific substrate over the next 24 months?"
3. "How vulnerable is the product portfolio to upcoming single-use plastic bans or EPR mandates?"
