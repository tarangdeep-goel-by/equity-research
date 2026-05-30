## Textiles & Apparel — Risk Agent

### Structural & Cyclical Risks to Pre-Mortem
Textiles is fraught with cyclical blowups and structural obsolescence. A risk pre-mortem must explicitly test these failure points:

**1. The Cotton Price Whip-Saw (Spinners/Weavers)**
- *The Risk:* Buying 4 months of cotton inventory at ₹65,000/candy, only for global prices to crash to ₹55,000/candy.
- *Pre-mortem prompt:* "If ICE cotton futures drop 20% next quarter, what is the MTM inventory loss on the balance sheet, and will it breach the company's debt covenants?" Check inventory days vs Net Debt.

**2. US/EU Retail Destocking (Exporters & Home Textiles)**
- *The Risk:* Global big-box retailers (Target, Walmart, IKEA) over-ordered during a boom and are now freezing new orders to clear their own warehouses.
- *Pre-mortem prompt:* "If US retail channel inventory remains elevated for another 2 quarters, how much will capacity utilization drop, and can the exporter's balance sheet handle the negative operating leverage?"

**3. Fashion and Obsolescence Risk (Brands/Retail)**
- *The Risk:* A brand misreads the season's fashion trend, resulting in massive unsold inventory that must be liquidated at deep discounts, destroying gross margins and brand equity.
- *Pre-mortem prompt:* "If the current season's collection fails, what is the historical markdown/discounting percentage required to clear inventory, and how much will it compress gross margins?" (Look for rising finished goods inventory in `working_capital`).

**4. The 'Zudio' Effect / Fast Fashion Price Wars**
- *The Risk:* Hyper-efficient value-fashion players (Trent's Zudio, Reliance Trends) structurally destroy the pricing power of legacy mid-premium brands by offering similar aesthetics at half the price.
- *Pre-mortem prompt:* "How much of the company's core revenue sits in the ₹500-₹1,000 price point that is directly vulnerable to value-fashion disruption, and is their SSSG already showing volume contraction?"

**5. Regulatory & Tariff Shocks**
- *The Risk:* Alteration of export incentives (RoDTEP/RoSCTL) or loss of duty-free access. Conversely, Bangladesh retaining its LDC status longer than expected, maintaining its 10% structural cost advantage over India in the EU.
- *Pre-mortem prompt:* "If the GoI reduces RoDTEP rates by 200 bps, what is the direct hit to the exporter's PBT, given that incentives currently form X% of profits?"

### Contingent Liabilities — The Hidden Debt
Textile exporters often import capital goods duty-free under the EPCG (Export Promotion Capital Goods) scheme, which carries an obligation to export a multiple of the duty saved over 6 years.
- Check `get_company_context(section='filings', sub_section='contingent_liabilities')`.
- If global demand slows and the company fails to meet its export obligations, these contingent liabilities crystallize into immediate cash penalties and duty payments. Flag any large EPCG obligations relative to current export run-rates.

### Promoter Pledging & Group Company Loans
Historically, mid-cap textile promoters have used the cash flows of the listed entity to fund unlisted real estate or agricultural ventures.
- Check `get_company_context(section='info')` for pledge %. Anything above 15% in a cyclical downturn is a severe margin-call risk.
- Check `get_company_context(section='filings', sub_section='related_party_transactions')` for Inter-Corporate Deposits (ICDs) or loans to promoter-owned entities. In textiles, these rarely come back.
