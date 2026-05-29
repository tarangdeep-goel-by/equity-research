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
Per FEMA NDI Rules, IT services allows 100% FDI under the automatic route. ADRs are NOT universal in Indian IT — among the majors only **Infosys** (NYSE) and **Wipro** (NYSE) have ADR programs; **TCS and HCLTech do not have ADRs**. Where an ADR program exists, combine ADR/GDR exposure with direct FPI counts to calculate aggregate foreign ownership; for TCS/HCLTech, foreign ownership is the direct FPI figure alone (no ADR layer to add). Because IT revenue is dollar-denominated, FIIs actively buy IT as a depreciating-INR hedge — FII flow timing correlates strongly with USD-INR moves. Segregate active fundamental allocation from macro FX-hedging flows when analyzing offshore capital surges.

### ESOP Dilution, Attrition Cycles & Insider Selling
IT companies utilize massive ESOP pools (2-6% AGM grants). High attrition waves during sectoral booms drive elevated ESOP issuance and cyclical dilution. Always distinguish insider selling clusters from ESOP unlock/vesting clusters. Treat standard vesting-cycle selling by KMPs as routine compensation monetization, not a bearish fundamental signal. Use `get_company_context(section='filings')` to cross-reference AGM resolutions, ESOP grant dates, and vesting schedules before flagging promoter/insider disposals as negative conviction.

### Buybacks, Capital Repatriation & Bonus Share Math
Cash-rich IT cos repeatedly execute buybacks to (a) return surplus cash and (b) anchor EPS against ESOP dilution. NOTE: the historical buyback-vs-dividend *tax arbitrage* is gone — effective **1 Oct 2024** (Finance (No. 2) Act 2024), buyback proceeds are taxed as a **deemed dividend in the shareholder's hands at marginal/slab rates** (company-level buyback distribution tax abolished); buybacks are no longer the tax-efficient route they were. Buyback participation disclosures are critical, but interpret the promoter side through the MPS lens below — a "flat or up" promoter % usually means pro-rata participation (or a forced tender), not non-participation. Check institutional stance via `get_ownership(section='mf_changes')` + `mf_conviction` around buyback dates. Track corporate action history via `get_events_actions(section='corporate_actions')`. Mega-caps conduct frequent bonus issues (e.g., 1:1) and splits. Pre-bonus ownership percentages stay constant but absolute share counts change — track explicit share counts to avoid confusing per-share metric calculations.

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

- **Promoter % UP during a buyback window = NON-PARTICIPATION** (promoter did not tender; the denominator `S_old − B` shrank, so a retained N_old now represents a larger %). This — not a flat % — is the genuine "high-conviction retention" signal.
- **Promoter % FLAT during a buyback window = PRO-RATA PARTICIPATION** (promoter tendered roughly in proportion to its holding, so its % is unchanged). Flat is participation, not abstention.
- **Promoter % DROP during a buyback window = OVER-PROPORTIONATE TENDER** (promoter sold more than its pro-rata share into the buyback). A meaningful signal about promoter cash needs or, in some cases, a *forced* tender to stay under the 75% MPS cap (see MPS rule below).

Before narrating any promoter-stake change across a buyback quarter, verify via `get_events_actions(section='corporate_actions')` for the buyback ratio (B / S_old), then compute the theoretical *non-participation* % via `calculate(operation='expr', a='N_old / (S_old - B) * 100')`. If the reported promoter % equals that theoretical line, the promoter did NOT tender; if it sits below, the promoter tendered (pro-rata or more). *Peer instances*: TCS (Tata Sons promoter ~71-72%, close to the 75% cap, so it typically tenders pro-rata/partially in buybacks to avoid breaching MPS — a near-forced compliance tender, not bearish conviction), INFY (founder-family/trust holding is low single-digit %, far from the cap — participation varies), WIPRO (Premji-Trust-dominated, promoter holding ~72-73% near the 75% cap, so promoters routinely participate to avoid breaching MPS — NOT a non-participation pattern), TECHM (Mahindra holding — variable), HCLTECH (Shiv Nadar Foundation/family — well below the cap).

### Minimum Public Shareholding (MPS) Cap — Promoter Buyback Tenders Can Be Forced, Not Bearish
SEBI mandates a **maximum 75% promoter holding / minimum 25% public shareholding** (Reg 38 LODR + SCRR Rule 19A) for listed companies. Several tier-1 IT promoters sit just under this cap — **TCS (Tata Sons ~71-72%)** and **Wipro (Premji Trust ~72-73%)**. When such a company buys back shares, the buyback shrinks total shares, which *mechanically pushes promoter % up*; to avoid breaching the 75% ceiling, these promoters are effectively **forced to tender pro-rata** in the buyback. Therefore, for high-promoter-holding IT names, promoter participation in a buyback is a **compliance measure to maintain the 25% MPS**, NOT a bearish conviction signal — do not flag it as the promoter "losing faith." Conversely, for low-promoter-holding names (Infosys, HCLTech), promoters have headroom and their tender / non-tender choice does carry a genuine conviction read. Always check the promoter % vs the 75% cap before interpreting a buyback tender.

### Peer-and-Historical Anchor for IT Services FII (Tenet 18)
Every FII % cited above 5% in an IT services ownership report must carry BOTH a peer anchor and a 5Y own-band anchor — descriptive numbers without anchors are incomplete. FII % varies sharply across the top-tier set and is gated by promoter holding: where promoter holding is high the free float (and thus achievable FII %) is structurally capped — TCS sits at only ~10-12% FII because Tata Sons holds ~72%, whereas Infosys (low promoter holding, large NYSE ADR program) sits in the 30%+ range. Do NOT assume "tier-1 IT = high FII"; check the specific name. MSCI EM weight, ADR aggregation (only INFY/WIPRO), and dollar-revenue hedging demand lift FII only within the room the free float allows. Use this anchor template:

*"FII stake of X% sits at the Y-th percentile for top-tier IT services (TCS/INFY/HCLTECH/WIPRO/TECHM peer set, sourced via `get_peer_sector(section='benchmarks')`), and in the [top/bottom] [quartile/third] of this stock's 5Y band (min–max from `shareholder_detail` quarters). The TCS-specific 5Y band is structurally wider than the sector median because Tata Sons' promoter-and-trust architecture makes the free-float absorption surface narrower — passive rebalancing drives sharper moves."*

Without the Tata Sons / Premji Trust / Mahindra-Group / founder-family context, a number reads as "high" or "low" in isolation: TCS's ~10-12% FII looks low absolutely but can sit in the upper part of its own narrow free-float-constrained band, whereas Infosys's 30%+ FII is normal for its large-float/ADR structure. Cite the structural reason (and the promoter-holding cap on free float) alongside the anchor.
