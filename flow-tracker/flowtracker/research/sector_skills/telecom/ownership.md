## Telecom — Ownership Agent

### Telecom Archetype Map
Telecom ownership structures bifurcate strictly by operational layer and sovereign-intervention history. Determine the target's archetype before interpreting its cap table:

| Sub-type | Typical Promoter Base | Strategic Anchor / FDI Pattern | Pledge & Dilution Risk |
| --- | --- | --- | --- |
| **Integrated Wireless Operator** (large private pan-India operators) | 40-60% via complex holding JVs (e.g., dedicated promoter holding entities for the listed operator) | Very high — foreign telecom peers hold 10-30% as strategic co-promoters or legacy JV partners | High — Spectrum/AGR dues force cyclic dilutions; government debt-to-equity conversion possible (precedent in financially stressed operators) |
| **Tower / Passive Infrastructure** (tower companies, passive-infra carve-outs) | 60%+ (often held by telco parents) | Low to medium | Medium — distressed operator parents may pledge/sell infra stakes |
| **Fibre / Enterprise / DTH** (fibre carriers, enterprise connectivity, DTH operators) | 50-70% (Conglomerate or PSU backed) | Low | Low — cash-flow stable, lower regulatory levies |
| **PSU Residual / State-Controlled** (listed and unlisted PSU telecom operators) | 70-95% (Govt of India) | None — FDI heavily restricted in practice | Zero pledge; divestment/merger risk is the primary focus |

### FDI Limits & The National Security Overlay
Indian telecom is legally open but practically guarded. Per **Press Note 3 of 2021 (DPIIT)**, FDI up to **100%** is permitted via the automatic route for telecom services (up from the prior 74% cap). Do not treat FII/FDI expansion as frictionless:
- **Security clearance:** significant foreign ownership is subject to Ministry of Home Affairs and National Security Council scrutiny — approval can be withheld or retrospectively reviewed.
- **Land-border restrictions:** per **Press Note 3 of 2020**, any investment from countries sharing land borders with India requires prior government approval — pre-empts hostile accumulation via the secondary market.
- **Telecommunications Act 2023:** grants the government sweeping powers to suspend/revoke licenses on national-security grounds; acts as an implicit cap on unregulated foreign accumulation.

### Strategic Anchors Under the Public/FPI Umbrella
Global telecom operators frequently act as co-promoters or strategic anchors in Indian telcos (foreign incumbents holding legacy JV stakes, plus historical MNC-telecom partnerships in now-merged entities).
- **Classification trap:** these stakes are sometimes classified under "Public" or "FPI/FDI" buckets in exchange filings despite functioning as strategic, illiquid anchors.
- **Action:** run `get_ownership(section='shareholder_detail')` to isolate >10% blocks held by foreign telcos. Strip these out when calculating true speculative free float. Use `get_ownership(section='changes')` to track whether these anchors defended their proportional stake during rights issues / QIPs or passively diluted.

### Promoter Holding Vehicles & Listed Foreign Subsidiaries
Telecom promoters rarely hold equity directly; they operate through multi-layered holding entities (dedicated promoter JVs holding the listed-operator line; historical conglomerate-foreign-telco JV structures).
- **Structural audits:** track changes in the ultimate holding company. A change in the promoter's holding structure often signals debt restructuring at the parent level, not an equity view.
- **Cross-listed subsidiaries:** large telcos often list international operations separately (e.g., Africa or overseas-market subsidiaries on foreign exchanges). The Indian parent's valuation requires an SOTP. Run `get_valuation(section='sotp')` to ensure listed foreign subsidiaries are priced correctly with an appropriate holding-company discount.

### The Sovereign Shareholder: Bailouts & PSUs
The Government of India occupies two distinct roles in telecom ownership:
- **Distressed private bailouts:** the Ministry of Finance has taken unprecedented equity stakes in private telcos (~33% in the most financially stressed private operator) via debt-to-equity conversion of spectrum and AGR arrears. Treat this MoF stake as a permanent, non-voting overhang — it prevents bankruptcy but suppresses upside until the government defines an exit path.
- **Pure PSUs:** legacy state operators operate with near-total state control. Monitor `get_events_actions(section='corporate_actions')` for merger/delisting timelines driven by DoT.

### Spectrum Auctions, AGR Dues & Dilution Cycles
Telecom ownership is violently cyclical, tied directly to regulatory levies and spectrum auctions occurring every 2-5 years.
- **The overhang:** Adjusted Gross Revenue (AGR) dues and spectrum arrears act as a permanent shadow cap table. High statutory liabilities inevitably convert into equity dilution. Run `get_company_context(section='filings')` for Supreme Court / DoT rulings.
- **Capital-raise cycles:** following spectrum wins, operators reliably announce QIPs or rights issues. Execute `corporate_actions` to align spectrum auction dates with subsequent promoter equity infusion or FPI absorption.

### Pledges, Infra Carve-Outs & DII Conviction
- **Promoter pledging:** risk varies drastically by company. Conglomerate-backed telcos generally maintain low pledges. Highly leveraged operators may see massive promoter pledging. Track aggregate group-level pledge if the promoter is part of a larger group.
- **Infra demergers:** passive infrastructure (towers, fibre) is frequently carved out to unlock capital (tower companies historically demerged from integrated-operator-plus-partner infra portfolios). Demergers create abrupt step-changes in holding patterns — treat the post-demerger ownership base as a fresh analytical starting point.
- **DII accumulation:** use `mf_changes` + `mf_conviction`. Domestic mutual funds typically under-weight distressed telcos; a sustained inflection in DII ownership is the strongest early indicator of a tariff-hike cycle or balance-sheet stabilization.

### Mandatory Telecom Ownership Checklist
1. [ ] Classify archetype: Integrated Wireless / Passive Infra / Fibre-Enterprise / PSU
2. [ ] Audit "Public" shareholding to extract >10% strategic foreign-telco anchors (`shareholder_detail`)
3. [ ] Check current AGR / spectrum dues and risk of debt-to-equity dilution (`filings`)
4. [ ] Identify unlisted promoter holding vehicles; check for nested JVs or debt at holding level
5. [ ] Screen for listed international subsidiaries; require an SOTP valuation baseline (`sotp`)
6. [ ] Map recent spectrum auction dates to upcoming or recently completed Rights Issues / QIPs (`corporate_actions`)
7. [ ] Identify if Govt of India holds equity (PSU parent OR statutory bailout conversion)
8. [ ] Check `mf_conviction` to gauge domestic institutional appetite for upcoming tariff cycles

### Open Questions
- Is the company carrying a disproportionate AGR / spectrum liability that mathematically guarantees impending equity dilution or government conversion?
- Are strategic foreign-telco anchors maintaining their proportional stakes during recent capital calls, or passively diluting?
- If the target is a passive infrastructure player (towers / fibre), what percentage of its equity is owned by its primary telecom operator clients, and are those clients financially stable enough not to liquidate their infra stakes?
- Has DII participation inflected positively in anticipation of ARPU hikes, contrasting with FII stagnation?
- For bailout-exposed telcos (MoF debt-to-equity conversion cases), what is the announced or implied government exit path?
