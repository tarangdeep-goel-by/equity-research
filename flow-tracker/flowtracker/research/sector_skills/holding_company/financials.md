## Holding Company — Financials Agent

### Standard Financial Analysis Breaks Down — Why
Holding companies don't have real operations. "Revenue" is dividend income from subs plus incidental treasury/real estate income — there is no product, no cost structure, no operating leverage. As a result, most of the standard financial toolkit is meaningless here:
- **P/E is meaningless** — earnings are pass-through dividends, not operating profit. Dividing a share price by pass-through income doesn't price the business; it prices the timing of when subs declare dividends
- **DuPont, operating margins, working capital cycle** — all irrelevant. There is no operating business to decompose
- **Revenue growth** — a misleading signal driven by when subs choose to pay dividends, not by any underlying business momentum

The real analysis for a holdco is three questions: (a) what does it own, (b) what is the portfolio worth, and (c) why does the market discount that portfolio. The financials agent's job is to surface the cash flow and balance sheet evidence that feeds those three questions — not to run a conventional P&L analysis.

### NAV Build-Up — The Core Valuation Work
The valuation agent owns the sum-of-parts (SOTP) NAV calculation. The build is straightforward in structure but sensitive in assumptions:
- **Listed holdings:** market value × stake × (1 − holdco tax drag on sale, ~22% LTCG)
- **Unlisted holdings:** book value or last-round valuation (flag the vintage — a 2022 round in 2026 is stale)
- **Cash + treasury investments at holdco:** add at par
- **Holdco-level debt:** subtract

The financials agent supports this work by extracting the cash flows the underlying holdings actually generate — dividend streams received from each major sub, which validates (or contradicts) the "this stake is worth X" claim.

### Holdco Discount — Persistent and Material
Indian holdcos trade at 30-55% discount to NAV, and this discount is structural, not an arbitrage opportunity. Drivers:
- **Tax drag** — 22% LTCG on listed, 30%+ on unlisted if monetized
- **Lack of operating control** — minority investors can't force capital allocation at the sub
- **Governance concerns** — risk that sub dividends get recycled into loss-making related ventures
- **Liquidity** — holdco stocks are often thinly traded

Track the discount trend over 3-5 years: a narrowing discount usually means the market is pricing in corporate action (demerger, buyback, simplification). A widening discount signals governance concerns or sub underperformance that the holdco hasn't acknowledged.

### Dividend Income from Subs — The Real Cash Flow
Dividend income received from subs is the only genuine cash flow a pure holdco generates. This is why it matters more than headline "profit":
- Call `get_events_actions(section='dividends')` for the holdco's own payout history, then cross-reference against received dividends disclosed in the standalone P&L
- Growing dividend income from subs = operating subs are doing well, even if the holdco's reported financials look flat
- Holdco dividend yield is effectively `sub-level dividends × stake × holdco payout ratio` — typically 2-4% gross. If yield drops sharply in a year, check whether subs cut payouts or whether the holdco retained more (and why)

### Segment-Level EBIT (Conglomerate-Type Holdcos Only)
A subset of holdcos — those running operating subsidiaries directly rather than purely holding listed stakes — require segment-level analysis. For these:
- Extract segment revenue and EBIT from `get_company_context(section='concall_insights')`
- Evaluate segment margins separately — the consolidated number is blended noise across unrelated businesses and is analytically useless

Pure investment holdcos (those whose sole activity is holding listed and unlisted stakes) don't have this — their standalone financials are just treasury income plus dividends received. Don't force a segment analysis where none exists.

### Holdco-Level Debt vs Sub-Level Debt
Consolidated debt figures hide the critical distinction: is the debt at the holdco itself, or at operating subs? This matters because:
- **Sub-level debt** is serviced by sub operating cash flow — normal corporate risk
- **Holdco-level debt** must be serviced by sub dividends, which are discretionary payments the sub board controls. If a sub decides to retain earnings for capex, the holdco still owes its interest bill

Check standalone balance sheet via `get_fundamentals(section='balance_sheet_detail')` — standalone debt is the holdco's own. Compare against trailing annual dividends received: if standalone debt service exceeds received dividends, there is a real servicing risk even when consolidated leverage looks comfortable.

### Governance Signals from Capital Allocation
Capital allocation is where holdco governance reveals itself. Value-creating patterns:
- Buybacks to close the NAV discount
- Structural simplification (collapsing cross-holdings, merging layers)
- Monetization of unlisted holdings at fair prices

Value-destroying patterns:
- Recycling sub dividends into capital infusions for loss-making group subsidiaries
- Related-party transactions at non-market terms
- IPO-ing sub entities at inflated levels with proceeds flowing back to promoters rather than minorities

Pull payout and buyback trends from `get_capital_allocation` data and read the concall for management's stated intent on NAV discount.

### What Structured Tools Give You (Limited)
Most standard sections return thin data for holdcos. Focus on the sections that actually carry signal:
- `get_company_context(section='concall_insights')` — management's strategy on portfolio, monetization, discount
- `get_events_actions` — dividends declared and received, corporate actions, buybacks
- `get_fundamentals(section='balance_sheet_detail')` — standalone balance sheet to isolate holdco-level debt and cash

Where structured tools don't return meaningful data (margin trends, working capital, DuPont), say so and move on — don't fabricate analysis against a data shape that doesn't fit the business model.
