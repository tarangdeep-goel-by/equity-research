## Exchange — Financials Agent

### Revenue Segment Decomposition — The Economic Engine
Exchange headline revenue is meaningless without the segment mix underneath it. A 15% revenue print can hide a collapsing transaction yield offset by a surging float — two very different businesses. Revenue typically splits into 4-5 streams, each with distinct economics. Extract from `get_company_context(section='concall_insights')` or `get_company_context(section='sector_kpis')`:
- **Transaction fees** (50-70% of revenue): volume × yield. Highly cyclical — swings with market turnover
- **Listing fees**: steady annuity stream, modest growth (new IPOs + annual listing dues from existing corporates)
- **Data/feed revenue**: terminal fees, market data licenses, API subscriptions — growing, high-margin, sticky
- **Clearing & settlement**: regulated, low-margin fees
- **Colocation & technology**: infrastructure rental (proximity hosting, rack space) — high-margin, recurring
- **Float income**: interest earned on margin/settlement deposits (₹10K+ Cr floats earn material income in high-rate cycles)

Margin-mix shifts are the leading indicator of operating leverage: a declining transaction share combined with rising data/colo share signals structural margin expansion, even when volume growth is flat.

### Transaction Yield — The Per-Trade Economics
- Transaction yield = transaction revenue / notional turnover (or per trade/lot)
- Yield compresses from three directions: regulatory fee cuts (SEBI caps), inter-exchange competition (NSE vs BSE, CDSL vs NSDL), and product mix shifts (F&O yield is materially lower than cash yield)
- Rising volumes with falling yield can produce flat transaction revenue — which is why ADT alone is a misleading KPI. Always decompose volume × yield

### Cost-to-Income Ratio — The Operating Leverage Lens
- Exchanges are ~90% fixed cost (tech infrastructure, people, regulatory). Incremental volume drops through at ~90% to EBITDA
- C/I below 30% = world-class operating leverage (NSE operates here); 30-45% = decent; above 50% points to structural issues (underutilized platform, tech refresh cycle, or shrinking volumes)
- Track the 5Y C/I trend — a declining ratio = operating leverage playing out. Use `get_quality_scores` or fundamentals for the series

### Float Income — The Rate-Sensitive Earnings Kicker
Margin deposits from brokers and clearing members aggregate into floats that often cross ₹10K Cr for large exchanges. Every 50bps move in short-end rates swings float income materially — and this flows almost entirely to PBT since there is no matching cost.
- Check `get_fundamentals(section='balance_sheet_detail')` for cash + investments composition and scale of deposits
- During rate-cut cycles, float income compresses — exchanges can look optically cheaper than they are on trailing PE. Always normalize for the rate cycle before comparing PE bands

### Regulatory Fee Pass-Through
- SEBI turnover fees and STT are typically pass-through items — booked as revenue and matching expense
- Strip them from both sides of the P&L for a clean operating margin read
- Watch for regulatory rate changes: a SEBI fee cut can hit reported revenue without affecting PBT, so headline revenue growth understates the real economics

### Capital Allocation — Capital-Light, Cash-Rich
Exchanges generate large CFO with near-zero maintenance capex (tech refresh is the only meaningful reinvestment). This makes dividend and buyback discipline the key capital allocation signal.
- Check dividend history via `get_events_actions(section='dividends')` — payout ratio trend tells you management confidence in volume outlook
- Check `get_events_actions(section='corporate_actions')` for buybacks, splits, bonus issues
- Strategic investments (clearing corps, international subs like NSE IX, technology platforms) should be evaluated as separate SOTP legs, not embedded in core exchange multiples

### Valuation
- **PE 40-60x is normal** for monopoly/duopoly exchanges globally (CME, ICE, HKEX, LSE trade here through cycles) — premium is justified by moat, operating leverage, and capital-light cash generation
- **EV/EBITDA is cleaner** than PE because depreciation of tech infrastructure understates the true economic reinvestment rate
- Use `get_valuation(section='band')` for historical PE context and to anchor against the exchange's own 5-10Y range, not absolute levels
- Cross-check FCF yield — exchanges should show FCF conversion above 90% of PAT given the capital-light model
