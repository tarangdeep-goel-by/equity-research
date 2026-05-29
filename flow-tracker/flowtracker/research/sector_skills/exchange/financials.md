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
- Transaction yield = transaction revenue / the correct billing base. **For options (which dominate Indian exchange volumes), transaction charges are levied on PREMIUM turnover, not notional turnover** — using notional understates yield by orders of magnitude. For cash and futures, use traded value. Never blend premium and notional into one turnover figure.
- **Track the options Premium-to-Notional ratio.** Because options revenue is billed on premium, a fall in market volatility compresses premiums and drags exchange revenue down even when notional volumes (lots traded) are flat or rising. Use the Premium-to-Notional ratio (and VIX) to forecast transaction-yield sensitivity to volatility — this is the single biggest revenue swing factor for NSE/BSE.
- Yield compresses from three directions: regulatory changes (the Oct 2024 "True to Label" flat-fee regime + F&O tightening), inter-exchange competition (NSE vs BSE, CDSL vs NSDL), and product mix shifts (F&O premium-based yield behaves very differently from cash yield)
- Rising volumes with falling yield can produce flat transaction revenue — which is why ADT alone is a misleading KPI. Always decompose volume × yield, on the correct (premium vs notional) base

### Cost-to-Income Ratio — The Operating Leverage Lens
- Exchanges are ~90% fixed cost (tech infrastructure, people, regulatory). Incremental volume drops through at ~90% to EBITDA
- C/I below 30% = world-class operating leverage (NSE operates here); 30-45% = decent; above 50% points to structural issues (underutilized platform, tech refresh cycle, or shrinking volumes)
- Track the 5Y C/I trend — a declining ratio = operating leverage playing out. Use `get_quality_scores` or fundamentals for the series

### Float Income — The Rate-Sensitive Earnings Kicker
Margin/settlement deposits from brokers and clearing members aggregate into floats that often cross ₹10K Cr for large groups. SEBI's client-funds upstreaming framework (effective from mid-2023) requires brokers/clearing members to upstream all client clear-credit balances to the Clearing Corporation on an end-of-day basis (cash, FDR lien, or overnight MF units) — this swells the CC's float but subjects it to strict overnight/liquid investment mandates, capping the yield the CC can earn. Every 50bps move in short-end rates still swings float income materially.
- **This income is largely generated at the Clearing Corporation, not the parent exchange, and is NOT fully distributable.** The CC must transfer a portion of its profits to the Core SGF (see below), so do not assume float income flows entirely to unencumbered, distributable PBT.
- Check `get_fundamentals(section='balance_sheet_detail')` for cash + investments composition and scale of deposits; reconcile CC float against the upstreaming mandate and overnight/liquid yield caps
- During rate-cut cycles, float income compresses — exchanges can look optically cheaper than they are on trailing PE. Always normalize for the rate cycle before comparing PE bands

### Core SGF — A Recurring Claim on Profits & FCF
SEBI requires clearing corporations to maintain a Core Settlement Guarantee Fund sized to stress tests (credit exposure assuming simultaneous default of at least 3 clearing members). The CC transfers a portion of its profits to the Core SGF (within 30 days of AGM adoption of accounts) and must replenish any shortfall.
- **Model Core SGF contributions as a recurring deduction from consolidated PAT and FCF**, not a one-off. Rising stress-test corpus requirements (SEBI revises the methodology periodically) raise the drag and reduce distributable cash/buyback capacity.
- This is the main reason consolidated (exchange + CC) FCF conversion can run below the capital-light parent-only figure — flag the gap explicitly.

### Regulatory Fees & STT — Don't Confuse the Two
- **STT is NOT exchange revenue.** It is a government tax collected on behalf of the State. Under Ind AS 115, amounts collected on behalf of third parties (taxes) are excluded from the transaction price — so STT never hits the exchange P&L as revenue; it sits as a balance-sheet liability until remitted. If a model shows STT inflating both revenue and expense, that is wrong — back it out entirely.
- **SEBI turnover fees** (the regulatory fee the exchange pays SEBI) ARE a real exchange operating expense — note for options SEBI bills on notional value, which can squeeze margins independently of the premium-based transaction charge the exchange earns.
- Watch for regulatory rate changes: a SEBI fee/charge change can move reported revenue or cost without a proportional PBT impact, so headline revenue growth can mislead — always read the operating margin net of regulatory levies.

### Capital Allocation — Capital-Light, Cash-Rich
Exchanges generate large CFO with near-zero maintenance capex (tech refresh is the only meaningful reinvestment). This makes dividend and buyback discipline the key capital allocation signal.
- Check dividend history via `get_events_actions(section='dividends')` — payout ratio trend tells you management confidence in volume outlook
- Check `get_events_actions(section='corporate_actions')` for buybacks, splits, bonus issues
- Strategic investments (clearing corps, international subs like NSE IX, technology platforms) should be evaluated as separate SOTP legs, not embedded in core exchange multiples

### Valuation
- **PE 40-60x is normal** for monopoly/duopoly exchanges globally (CME, ICE, HKEX, LSE trade here through cycles) — premium is justified by moat, operating leverage, and capital-light cash generation
- **EV/EBITDA is cleaner** than PE because depreciation of tech infrastructure understates the true economic reinvestment rate
- Use `get_valuation(section='band')` for historical PE context and to anchor against the exchange's own 5-10Y range, not absolute levels
- Cross-check FCF yield — the parent exchange is capital-light and should convert most of PAT to FCF, but consolidated FCF runs lower because of Core SGF transfers and CC float swings. Use exchange-only (ex-CC) cash generation for the capital-light read, and consolidated FCF for distributable-cash reality
