## Logistics — Risk Agent

### Structural Risks — The Pre-Mortem Focus
Logistics risks are highly specific to the sub-sector. A generic "macro slowdown" risk is insufficient. Focus your pre-mortem on these specific vectors:

1. **Client Insourcing & Concentration (Express / 3PL)**
   - *The Risk*: E-commerce giants (Amazon, Flipkart, Meesho) run captive logistics arms (ATS, Ekart). If they decide to insource higher volumes, third-party players (Delhivery, Blue Dart) lose their highest-density baseloads overnight.
   - *Check*: What % of revenue comes from the top 5 clients? Extract from `get_annual_report(section='risk_management')` or concall insights.

2. **Infrastructure Execution Delays (Rail / EXIM)**
   - *The Risk*: Rail logistics valuations (Concor, Gateway) heavily price in the margin and volume benefits of the Dedicated Freight Corridor (DFC). 
   - *Check*: Are there land acquisition or commissioning delays on the final stretches of the DFC (e.g., JNPT connectivity)? A 2-year delay structurally impairs the DCF value.

3. **Freight Rate Mean-Reversion (Marine Shipping / Forwarders)**
   - *The Risk*: Global freight rates (ocean and air) spiked during supply chain crises (COVID, Red Sea). Forwarders (Allcargo) and Shippers (GE Ship) over-earned.
   - *Check*: Where are current yields/TCE rates vs the 10-year historical average? If they are 50% above average, model a mean-reversion shock to EBITDA.

4. **Fuel Surcharge (FSC) Failure (Road / Express)**
   - *The Risk*: While B2B contracts have FSC clauses, B2C and SME contracts often do not. In a rapid diesel price spike, the lag (30-45 days) or inability to pass on costs crushes margins for a quarter or two.
   - *Check*: What % of contracts have automated FSC pass-through?

5. **MSME / Unorganized Competition Resurgence**
   - *The Risk*: The thesis for listed logistics is "shift from unorganized to organized." If GST enforcement weakens or diesel prices fall (helping fragmented single-truck owners), the unorganized sector regains pricing power, triggering brutal price wars in FTL/PTL.

### Working Capital & Receivables Stress
- 3PLs act as unsecured creditors to their corporate clients. In a macro slowdown, auto and FMCG clients stretch payables from 60 days to 120 days.
- *Check*: Track the trajectory of "Trade Receivables > 6 months" in `get_annual_report(section='notes_to_financials')`. A spike here precedes write-offs.

### Regulatory & Policy Risks
- **Concor Privatization**: For Concor specifically, the overhang of GoI divestment and the Land Licensing Fee (LLF) policy with Indian Railways dictates the stock price more than quarterly earnings.
- **Cabotage Law Changes**: Easing cabotage laws allows foreign shipping lines to operate on Indian coastal routes, threatening domestic coastal shippers.

### Open Questions for the Risk Agent to Raise
- "What is the exact revenue exposure to the top 3 e-commerce platforms, and what is the contingency plan if they shift 30% of that volume to captive logistics?"
- "How much of the current EBITDA margin is supported by elevated global freight rates that are vulnerable to normalization?"
- "What is the sensitivity of the company's EBITDA to a 10% spike in diesel prices, factoring in the current FSC lag?"
