## Hospitality — Risk Agent

### Structural Risks — The Pre-Mortem Mandate
A hospitality pre-mortem must address the specific structural vulnerabilities of the sub-sector. Generic "macro slowdown" is insufficient.

**For QSR (Quick Service Restaurants):**
1. **Aggregator Margin Squeeze:** Zomato and Swiggy operate as a duopoly, controlling a massive chunk of QSR delivery volumes. If the QSR's dine-in mix is falling and delivery mix is rising, they are structurally losing margin to aggregator take-rates and discount funding. Track the Dine-in vs. Delivery mix.
2. **Category Cannibalization / Fatigue:** Is the SSSG negative because of macro, or because the category is saturated? (e.g., Pizza fatigue in India vs. Fried Chicken resilience). Aggressive store additions in a fatigued category lead to cannibalization, where new stores simply steal revenue from existing stores, destroying unit economics.
3. **Franchise Renewal & Royalty Risk:** Master franchisees (Jubilant, Devyani) do not own their brands. Check `get_company_context(section='filings')` for the expiry dates of master franchise agreements and any clauses allowing the franchisor (Yum/Domino's) to hike royalty rates or force mandatory capex (store remodels).

**For Hotels:**
1. **The Supply Glut (Cyclical Risk):** Hotel upcycles last as long as supply is constrained. Because hotels take 3-5 years to build, supply hits the market in lumps. Track industry pipeline data (via concall commentary). If supply growth in key micro-markets (e.g., MMR, NCR, Bengaluru) exceeds demand growth, ARR pricing power will collapse.
2. **Corporate vs. Leisure Mix:** A hotel heavily skewed to corporate travel (e.g., Lemon Tree) is highly vulnerable to IT-sector hiring slowdowns and corporate travel budget cuts. 
3. **Operating Leverage Reversal:** The same fixed costs that drive massive margin expansion on the way up will cause violent margin compression on the way down. A 5% drop in RevPAR can wipe out 15% of EBITDA.

**For Travel (OTAs/Ticketing):**
1. **Supplier Consolidation:** As airlines (IndiGo/Air India) or hotel chains consolidate, they push direct-to-consumer bookings, squeezing OTA commissions and take-rates.
2. **Zero-Convenience Fee Unsustainability:** Models relying on zero convenience fees (e.g., Easy Trip) are highly vulnerable to changes in airline subvention/commission structures.

### Input Cost Volatility (QSR)
QSR gross margins are at the mercy of agricultural cycles. 
- **Pizza:** Cheese (dairy prices) and Wheat.
- **Chicken:** Poultry prices and feed costs (soya/maize).
Check `get_annual_report(section='risk_management')` for hedging policies. Most Indian QSRs cannot hedge dairy/poultry effectively and must pass costs to consumers. If SSSG is weak, they cannot take price hikes, leading to direct gross margin compression.

### Lease Renewals (Ind AS 116 Trap)
For QSRs and asset-light hotels, prime real estate is leased. Initial leases are typically 9-12 years. As a large vintage of stores approaches lease renewal, landlords mark-to-market the rent. This can cause a sudden spike in lease liabilities and a drop in store-level ROCE. Look for commentary on "store relocation" or "lease renegotiation" in concalls.
