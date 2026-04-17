## Conglomerate — Sector Agent

### Macro Context — A Weighted Average of Per-Vertical Macros
A conglomerate does not sit on a single sector macro; it sits on a weighted average of its verticals' macros. The sector-agent framing that reads only the top-down index macro will miss the dispersion that drives consolidated earnings. State the 2-3 dominant macros explicitly, scaled by vertical revenue contribution — for example, "credit cycle for the 30% NBFC arm + specialty-chemicals cycle (China-plus-one demand, feedstock differential) for the 35% chem arm + IT-services BFSI-client spend cycle for the 20% tech arm." Pull the macro regime via `get_market_context(section='macro')` and cross-reference with per-vertical sector context via `get_peer_sector(section='sector_overview')` for each material vertical.

Specifically state these macros where they apply:
- **Interest-rate regime** — affects NBFC / financial-services sub (NIM, CoF), insurance float yields, and the parent's own refinancing cost if standalone debt is material
- **Commodity / feedstock cycle** — affects chemicals, metals, refining sub-verticals
- **Global tech spend cycle** — affects IT-services arm
- **Credit cycle (India system credit growth, GNPA trajectory)** — affects NBFC / bank / housing-finance sub
- **Consumption cycle (rural / urban divergence, GST collection trends)** — affects consumer / retail sub
- **Infrastructure capex cycle (central + state capex, PLI disbursements)** — affects capital-goods, construction, industrial sub

### Sector Cycle Position — Diagnose Per Vertical, Not Parent
There is no single cycle position for a conglomerate; diagnose each material vertical's position (early / mid / late / stressed) separately. The interesting setup is divergent cycle phases across the portfolio — counter-cyclical mix is the structural bull case for diversification; correlated cyclicals bundled together is the structural bear case (a single macro bet sold as diversified exposure). Read the cycle via:

- Per-vertical capex intensity trajectory — a vertical in late-cycle typically shows capex intensity rolling over before earnings peak
- Per-vertical margin trajectory — late-cycle margin peaks that are unsupported by volume growth are the canonical mean-reversion setup
- Per-vertical ROCE vs through-cycle average — a vertical reporting ROCE 400-600 bps above 10-year through-cycle is near the peak of its own cycle

### Competitive Hierarchy — Tier the Sector
Indian conglomerates do not sit on a single league table; tier by structural archetype and by scale via `get_peer_sector(section='sector_overview')` and `section='peer_metrics')`:

- **Top-5 diversified-operating conglomerates** by consolidated market cap — genuine multi-vertical operating businesses with disclosed segment P&L and 3+ material verticals
- **Top-3 promoter-group-linked structures** — parent + many listed sister entities under a common promoter-group umbrella, with group-aggregate market cap tracked separately from parent market cap
- **Holding-company specialists / pure holdcos** — limited-to-no operating business at the parent, value entirely in listed-sub stakes; structurally the widest holdco discount cohort. Indian listed pure-holdcos (treasury + listed-stake only, no operating P&L) have historically traded at **40-65% discount to NAV**, materially wider than operating-plus-holdings structures (20-35%). The wider discount reflects no operating cash-flow optionality, full tax leakage on dividend upstreaming, and the absence of a standalone re-rating catalyst beyond NAV compression
- **Focused multi-vertical operating companies (2 verticals)** — often mis-classified as conglomerates when they are actually two-vertical businesses; SOTP mechanics still apply but the complexity discount is lower

Where the stock sits in this hierarchy determines the peer set. A holdco-style name should be compared to other holdcos on discount-vs-NAV, not to operating conglomerates on PE.

### Institutional Flow — Conglomerate-Specific Patterns
Conglomerates carry **10-15% of the Nifty weight collectively** (varies with index rebalance cycles). Institutional flow patterns have specific mechanics that the sector and ownership agents must both reflect:

- **FII tendency to own flagships** — foreign active funds typically own the flagship listed entity within a group (largest market cap, best-disclosed segment P&L) rather than the smaller sister entities; flagship FII % commonly runs 15-28%, sister-entity FII % often 5-15%
- **DII positioning often sub-aligned** — domestic mutual funds and LIC frequently own the subsidiaries (for pure-play exposure to a single vertical) without owning the parent (to avoid holdco discount); cross-check via `get_ownership(section='mf_holdings')` and the parent's own listed-subsidiary ownership
- **Group-level FII exit cascade** — a single-entity FII exit (e.g., flagship) often correlates with sister-entity exits within 1-4 weeks; track via `get_peer_sector(section='sector_flows')` at the group level, not the stock level
- **Passive FII on the flagship** — index-linked flows concentrate on the Nifty-weighted flagship; sister entities without index inclusion do not receive the same passive bid

Cross-reference with `get_market_context(section='fii_dii_flows')` for the aggregate FII / DII direction and state whether the stock's specific flow is with-sector or against-sector.

### Structural Shifts — Beyond the Cycle
Multi-year structural shifts are reshaping conglomerate economics in ways that cyclical reads miss:

- **Value-unlock cycle (2020-24)** — a wave of Indian conglomerate demergers, spin-offs, and subsidiary IPOs has demonstrated that holdco discounts are not permanent; the re-rating case for complex groups is increasingly "when, not if"
- **Private-equity activism on holdco-discount compression** — specialist PE funds buying positions in discounted holdcos and pushing for NAV-unlock transactions; the precedent set by a few high-profile cases has shortened the typical discount-compression horizon from 5-7 years to 2-4 years
- **Subsidiary-IPO pipeline as primary re-rating catalyst** — the post-2021 Indian IPO window has made subsidiary monetisation the most-cited re-rating catalyst for complex groups; a named and disclosed IPO pipeline is a structural discount compressor
- **ESG / governance-premium vs -discount polarization widening** — well-governed conglomerates are now trading at historically narrow holdco discounts (10-15%) while governance-flagged names are trading at historically wide discounts (35-45%). The dispersion is widening; the average is no longer a useful anchor
- **Regulatory tightening on related-party transactions** — SEBI's 2022 LODR amendments lowered material-RPT thresholds and expanded disclosure requirements; group structures carrying high RPT are gradually re-pricing
- **IFRS / Ind-AS convergence on segment-reporting** — tighter enforcement of Ind-AS 108 segment-reporting is making re-segmentation harder; opacity discounts should narrow for groups that disclose cleanly

Name the structural shift and tie it to the specific archetype that benefits or is challenged; generic "demerger wave" framing is noise without this tie.

### Sector KPIs — Always Cite Percentile, Not Just Absolute
When benchmarking via `get_peer_sector(section='benchmarks')`, state the percentile rank within the sub-archetype, not only the absolute number. Conglomerate-relevant KPIs:

- **Consolidated ROCE** — but only as an averaging check; the real read is ROCE dispersion across verticals
- **Holdco discount** — market cap ÷ SOTP NAV; trajectory over 3-5 years is more informative than the point estimate
- **Subsidiary-dividend coverage of parent debt** — sub dividends received ÷ parent standalone interest + principal payable; <1.5× is refinancing-dependent
- **Segment-level ROCE dispersion** — max segment ROCE minus min segment ROCE; high dispersion flags cross-subsidy
- **Capex-to-revenue consolidation** — consolidated capex ÷ consolidated revenue; 3-year average smooths project-capex lumpiness
- **Consolidated Net Debt / EBITDA** — with the standalone-vs-consolidated split disclosed separately (financials agent's domain)
- **Minority interest leakage** — MI share of consolidated PAT; >15% materially alters EPS-level valuation multiples

A number quoted without sector percentile (e.g., "consolidated ROCE of 14%") omits whether that is top-quartile, median, or bottom-quartile for the archetype — the re-rating thesis depends on the percentile.

### Data-shape Fallback for Sector Context
If `get_peer_sector(section='sector_overview')` returns a sparse peer set (fewer than 3 comparable archetype names) or `section='benchmarks')` returns `null` on a KPI, fall back to `get_peer_sector(section='sector_flows')` for the group-level flow context and `get_market_context(section='macro')` for the top-down cycle read. For holdco-discount peer data, cross-reference `get_company_context(section='documents', query='holding company|SOTP|NAV')` for broker-published or management-disclosed NAV views. If all sources are degraded, lean on `get_company_context(section='concall_insights', sub_section='management_commentary')` for management's own stated SOTP view — explicitly label it as management-sourced rather than independently benchmarked.

### Open Questions — Conglomerate Sector-Specific
- "Which 2-3 vertical-macros are dominant for this group, and are they counter-cyclical (true diversification) or correlated (single macro bet with complexity)?"
- "Where is each material vertical in its own cycle (early / mid / late / stressed), and is consolidated earnings mix currently supported by late-cycle verticals near their peak?"
- "What is the current holdco discount vs the 3-5 year trajectory, and is it inside or outside the peer-archetype range?"
- "Is there a disclosed subsidiary-IPO, demerger, or monetisation pipeline with a stated 12-24 month timeline?"
- "How does FII / DII positioning at the parent compare to their positioning at the listed subsidiaries — is the pattern group-aligned or sub-aligned?"
