## IT Services — Ownership Agent

### IT Services Archetype
| Subtype | Typical Promoter Base | Ownership Range | Pledge Baseline | ADR / Foreign Capital Relevance |
| :--- | :--- | :--- | :--- | :--- |
| **Mega-cap legacy IT services** | Founder family, Trust, or Conglomerate | 40-75% | Near-zero | Very High (Large ADR programs + heavy FPI) |
| **Mid-cap IT services** | Mixed (Founders / Corporate / PE) | 30-55% | Low | High (Direct FPI active) |
| **Niche / boutique IT** | Founder-led, concentrated | 40-60% | Low to Moderate | Moderate |
| **IT Product / SaaS** | MNC parent or Indian conglomerate | 55-75% | Near-zero | Low-Moderate |
| **BPO / ITES** | PE-backed, Carve-outs, Founders | 30-60% | Moderate | Low-Moderate |

### Family Trusts, Layered Holding & Ultimate Beneficiaries
Indian-family-promoter structures dominate the sector. Founders and trusts hold equity via layered private entities (founder-family investment vehicles or trust structures). Always trace ultimate beneficial ownership. A typical multi-layer setup — e.g., a group holding company that is itself ~66% trust-owned — creates a "promoter holds stake in promoter" analytical complexity. Deploy `get_ownership(section='shareholder_detail')` to map named promoter vehicles and use `get_valuation(section='sotp')` to identify cross-holdings of listed subsidiaries (e.g., a listed subsidiary under a group holding company).

### FDI Caps, ADR/GDR Aggregation & FX-Linked FII
Per FEMA NDI Rules, IT services allows 100% FDI under the automatic route. Mega-cap IT frequently maintains 10-18% of paid-up capital as ADRs. Combine ADR/GDR exposure (ADR-listed Indian issuers in the sector) with direct FPI counts to calculate aggregate foreign ownership. Because IT revenue is dollar-denominated, FIIs actively buy IT as a depreciating-INR hedge — FII flow timing correlates strongly with USD-INR moves. Segregate active fundamental allocation from macro FX-hedging flows when analyzing offshore capital surges.

### ESOP Dilution, Attrition Cycles & Insider Selling
IT companies utilize massive ESOP pools (2-6% AGM grants). High attrition waves during sectoral booms drive elevated ESOP issuance and cyclical dilution. Always distinguish insider selling clusters from ESOP unlock/vesting clusters. Treat standard vesting-cycle selling by KMPs as routine compensation monetization, not a bearish fundamental signal. Use `get_company_context(section='filings')` to cross-reference AGM resolutions, ESOP grant dates, and vesting schedules before flagging promoter/insider disposals as negative conviction.

### Buybacks, Capital Repatriation & Bonus Share Math
Cash-rich IT cos repeatedly execute buybacks to (a) return cash tax-efficiently and (b) anchor EPS against ESOP dilution. Buyback participation disclosures are critical: non-participation by promoters signals high conviction. Check institutional stance via `get_ownership(section='mf_changes')` + `mf_conviction` around buyback dates. Track corporate action history via `get_events_actions(section='corporate_actions')`. Mega-caps conduct frequent bonus issues (e.g., 1:1) and splits. Pre-bonus ownership percentages stay constant but absolute share counts change — track explicit share counts to avoid confusing per-share metric calculations.

### Passive FII Flows & Pledge Anomalies
Large-cap IT carries structural dominance in passive indices (~8-12% Nifty 50 weight, heavy MSCI EM weight). Index inclusion / exclusion / free-float adjustments drive mechanical passive FII flows. Do not mistake MSCI / FTSE rebalancing volume for active fundamental buying. The baseline for promoter pledging in family-led IT is near-zero. Any upward deviation is an immediate systemic red flag. Execute `get_ownership(section='promoter_pledge')` routinely.

### Mandatory Checklist
- [ ] Trace ultimate beneficial ownership (UBO) through multi-layer promoter trusts and holding companies
- [ ] Aggregate direct FPI percentage with ADR / GDR outstanding capital to calculate total foreign holding
- [ ] Cross-reference insider / KMP selling dates against ESOP vesting timelines and AGM grant approvals
- [ ] Normalize historical promoter share counts for 1:1 bonus issues and stock splits to prevent false dilution flags
- [ ] Review recent buyback tender participation by promoters and mutual funds to assess internal conviction
- [ ] Check if recent FII flow timing matches USD-INR depreciation phases or MSCI / FTSE rebalance dates
- [ ] Verify `promoter_pledge` is near absolute zero; escalate any non-zero family pledge immediately

### Open Questions
- Is the recent cluster of KMP selling a true indicator of peaking business cycles, or merely routine tax-liability monetization tied to an ESOP cliff?
- Are buybacks being utilized fundamentally to return excess FCF, or defensively to mask heavy equity dilution from high-attrition cycles?
- How much of the institutional buying is active stock-picking conviction versus a mechanical FII allocation to hedge against anticipated INR depreciation?
- For founder-family investment vehicles or trust structures, do upcoming group-level capital-allocation decisions risk cascading sell-downs into the listed entity?

### Buyback Arithmetic — Worked Example for IT Services (Tenet 20)
IT services is the most buyback-active sector in Indian large-caps (TCS, INFY, WIPRO, TECHM, HCLTECH all execute recurring tender buybacks as the primary cash-return mechanism, in lieu of steady rising dividends). This makes buyback-window ownership math a *sector-specific* rather than generic concern. The arithmetic: for holder X with N_old shares and pre-buyback total S_old, after buyback of B shares, X's new % = `N_old / (S_old − B)`. Non-participation **increases** the holder's %. Therefore:

- **Promoter % DROP during a buyback window = ACTIVE TENDER PARTICIPATION** (promoter chose to sell into the buyback at the tender price). This is a meaningful signal about promoter cash needs or conviction — NOT pro-rata non-participation.
- **Promoter % FLAT during a buyback window = non-participation = conviction signal** (promoter retained stake while outsiders got diluted in).
- **Promoter % UP during a buyback window = oversubscription acceptance skew in promoter's favour** — unusual, worth flagging.

Before narrating any promoter-stake change across a buyback quarter, verify via `get_events_actions(section='corporate_actions')` for the buyback ratio (B / S_old), then compute the theoretical non-participation % via `calculate(operation='expr', a='N_old / (S_old - B) * 100')`. If the reported promoter % falls below that theoretical line, the promoter sold into the tender. *Peer instances*: TCS (Tata Sons routinely tenders in-kind, promoter % drifts down), INFY (founder-family and trusts typically non-participate), WIPRO (Premji Trust-dominated, non-participation is the usual pattern), TECHM (Mahindra holding — variable), HCLTECH (Shiv Nadar Foundation — typically non-participates).

### Peer-and-Historical Anchor for IT Services FII (Tenet 18)
Every FII % cited above 5% in an IT services ownership report must carry BOTH a peer anchor and a 5Y own-band anchor — descriptive numbers without anchors are incomplete. For top-tier IT services (TCS, INFY, HCLTECH, WIPRO, TECHM, LTIM), FII % sits structurally high because of MSCI EM weight, ADR aggregation, and dollar-revenue hedging demand. Use this anchor template:

*"FII stake of X% sits at the Y-th percentile for top-tier IT services (TCS/INFY/HCLTECH/WIPRO/TECHM peer set, sourced via `get_peer_sector(section='benchmarks')`), and in the [top/bottom] [quartile/third] of this stock's 5Y band (min–max from `shareholder_detail` quarters). The TCS-specific 5Y band is structurally wider than the sector median because Tata Sons' promoter-and-trust architecture makes the free-float absorption surface narrower — passive rebalancing drives sharper moves."*

Without the Tata Sons / Premji Trust / Mahindra-Group / founder-family context, a 25% FII reads as "high" in isolation when it's in fact in the bottom half of TCS's own 5Y band. Cite the structural reason alongside the anchor.
