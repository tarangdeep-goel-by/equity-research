## Platform — Valuation Agent

### Sub-type Routing — Primary Multiple Is Not PE
The most common valuation error for platforms is defaulting to a PE + EV/EBITDA triangle. For loss-making or pre-profit platforms earnings are negative or noisy, and EBITDA is frequently non-existent or "adjusted" to exclude ESOP — so both are broken primary multiples. Route to the correct primary multiple by sub-type before loading any peer comparable:

| Subtype | Primary multiple | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- |
| **Food-delivery / quick-commerce** | EV/GMV (1-3× mature, 3-8× rapid-growth); EV/Revenue with take-rate normalisation | PE (negative earnings), EV/EBITDA (adjusted-EBITDA optics), DCF (terminal dominates) |
| **E-commerce horizontal / vertical** | EV/GMV + EV/Revenue (take-rate normalised); shift to EV/EBITDA at 40-80× once consistently positive | PE on early-profit years, P/B (asset-light) |
| **Mobility / ride-hailing** | EV/GMV + EV/Revenue; per-trip contribution-margin multiple | EV/EBITDA on trough-utilisation quarter |
| **Payments / fintech** | EV/TPV (bps of flow), EV/Revenue, PE on lending-diversified segments | PE on pure-MDR revenue (single-regulation risk) |
| **Insurtech distribution** | P/Revenue + P/Embedded-Commission-Pool; peer to insurance broker multiples | EV/EBITDA on regulatory-repricing year |
| **Edtech** | EV/Revenue + EV/Subscribers; LTV-adjusted cohort valuation | PE on subsidy-heavy cohort year |
| **Travel aggregator** | EV/Booking-volume + EV/Revenue | PE on post-COVID reopen spike (mean-reverts) |

### Take-Rate / GMV Normalisation — 1P/3P Revenue Distortion
The specific Pattern B fix for platforms: when reported revenue is a blend of 1P inventory accounting (where revenue = GMV) and 3P marketplace accounting (where revenue = GMV × take-rate), the headline revenue number is not comparable to a near-pure-3P peer. A platform reporting "60% 1P + 40% 3P revenue" looks ~3-5× larger on EV/Revenue than a 95% 3P peer of identical GMV, yet trades on a mechanically compressed multiple. The normalisation:
```
Normalised GMV = 1P revenue + (3P revenue ÷ 3P take-rate)
```
Apply EV/GMV on the normalised figure, or equivalently re-express revenue on a take-rate-adjusted basis before peer comparison. Extract the 1P/3P split and the 3P take-rate from `get_company_context(section='concall_insights', sub_section='operational_metrics')` or `sub_section='management_commentary')`; if management has not disclosed the split for 2+ quarters, flag as an Open Question and explicitly widen the fair-value range. Route the arithmetic through `calculate` with named inputs `revenue_1p_cr`, `revenue_3p_cr`, and `take_rate_3p_pct`.

### Path-to-Profitability Scenario Framework
For loss-making platforms, valuation is a scenario exercise on three pivots: (i) the quarter contribution margin per order turns sustainably positive, (ii) the quarter operating EBITDA turns positive, (iii) the steady-state take-rate and frequency. Build base / bull / bear on these three inputs rather than on a single terminal-year number. Typical sensitivity: pulling the EBITDA-positive quarter forward by 2-4 quarters re-rates fair EV/Revenue 15-25%; pushing it back 2-4 quarters de-rates similarly. For quick-commerce, the terminal contribution margin assumption (4% vs 6% of GMV) is the single most load-bearing number — every 100 bps of terminal CMPO is worth 20-30% of fair enterprise value.

### Cash Runway as Valuation Floor
If `net_cash / quarterly_net_burn < 18 months`, the platform is in fundraise pressure and the implied dilution must be reflected in the forward share count. Compute: `Months runway = net_cash_cr ÷ quarterly_net_burn_cr × 3`. 12-24 months is fundraise pressure, 24-36 months is steady, >36 months is comfortable. Apply dilution-adjusted forward share count in fair-value per share only when runway signals imminent raise; otherwise use the current share count plus disclosed ESOP vesting.

### Peer-Premium Decomposition
If the stock trades at an EV/GMV or EV/Revenue premium vs sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into at most four drivers: (a) **take-rate delta** — a sustained 100-200 bps of take-rate advantage is a moat signal worth 15-25% premium; (b) **frequency delta** — 2 orders/month per MAU vs 1 order/month is ~2× LTV, justifying a 20-40% premium; (c) **cohort retention delta** — if M12 repeat is 15-20 pp above peer, the LTV advantage compounds; (d) **CAC efficiency** — blended CAC below peer with organic-share above peer is worth 10-20% premium. If (a) through (d) together do not account for more than half of the observed premium, the multiple is vulnerable to mean-reversion and the bull case is leaning on re-rating rather than on unit-economic improvement.

### Duration Discipline — Don't Mix Trailing and Forward
The Pattern C4 discipline from the valuation eval: do not compute an SOTP on trailing FY25 basis and then compare to a peer EV/Revenue computed on forward FY26 basis — duration mixing produces a false re-rating signal. Anchor the valuation framework to a single fiscal year. For platforms, this especially applies to ad-tech sub-segment valuation (trailing) bolted onto core-business EV/Revenue (forward) — build both on the same fiscal reference period or state the mix-basis explicitly.

### What Fails for Platforms — Name These Explicitly
- **PE on loss-making platforms** — undefined when earnings are negative; misleading when earnings are tiny positive after accounting transition.
- **EV/EBITDA on negative or adjusted EBITDA** — "Adjusted EBITDA excluding ESOP" systematically understates the true cost; the adjusted-EBITDA multiple is gamed.
- **DCF at early-stage** — the terminal-value assumption dominates >80% of present value; false precision.
- **P/B on asset-light platforms** — accumulated losses distort book; P/B is noise for this sub-sector.
- **Trailing EV/Revenue without take-rate normalisation** — mechanically wrong for mixed 1P/3P.
- Use instead: EV/GMV (normalised), EV/Revenue (take-rate-adjusted), path-to-profitability scenario model, and once consistently EBITDA-positive, shift to EV/EBITDA at the 40-80× band during the transition phase.

### Data-shape Fallback for GMV / Take-Rate
When `get_peer_sector(section='benchmarks')` does not return EV/GMV and `get_valuation(section='band', metric='ev_revenue')` returns fewer than 12 quarterly observations (common for recently-listed platforms), fall back in this order: (1) `get_company_context(section='concall_insights', sub_section='operational_metrics')` for GMV / GOV / TPV disclosures; (2) `sub_section='management_commentary')` for management-narrated take-rate; (3) peer-multiple triangulation using listed global peers' EV/GMV (adjusted for regional growth and regulatory discount). Cite the source quarter. Do not fabricate GMV — the valuation agent's credibility depends on citing what management actually disclosed.

### Open Questions — Platform Valuation-Specific
- "What 1P-vs-3P revenue split and 3P take-rate was used to compute normalised GMV, and from which quarter's concall disclosure?"
- "What is the base-case quarter for contribution-margin-positive and for operating-EBITDA-positive, and what peer-multiple is applied once EBITDA turns?"
- "Does the current EV/Revenue premium to sector median reconcile with the take-rate + frequency + cohort + CAC decomposition, or is there a residual multiple gap?"
- "Is the trailing EV/Revenue distorted by a one-off accounting transition (net-to-gross, 1P-to-3P, IPO-proceeds float income) that should be normalised before peer comparison?"
- "What is the cash runway in months, and is the forward share count adjusted for a probable QIP or pre-IPO-investor exit within the next 12 months?"
