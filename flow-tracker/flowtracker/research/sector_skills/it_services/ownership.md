## IT Services — Ownership Agent

### IT Services Archetype
| Subtype | Typical Promoter Base | Ownership Range | Pledge Baseline | ADR / Foreign Capital Relevance |
| :--- | :--- | :--- | :--- | :--- |
| **Mega-cap legacy IT** (e.g., TCS, Infosys, Wipro, HCLTech) | Founder family, Trust, or Conglomerate | 40-75% | Near-zero | Very High (Large ADR programs + heavy FPI) |
| **Mid-cap IT services** (e.g., LTIMindtree, Coforge, Persistent Systems, Mphasis) | Mixed (Founders / Corporate / PE) | 30-55% | Low | High (Direct FPI active) |
| **Niche / boutique IT** (e.g., KPIT, Sonata, Zensar, Happiest Minds, Tanla) | Founder-led, concentrated | 40-60% | Low to Moderate | Moderate |
| **IT Product / SaaS** (e.g., Oracle Financial Services, Tata Elxsi, Intellect Design) | MNC parent or Indian conglomerate | 55-75% | Near-zero | Low-Moderate |
| **BPO / ITES** (e.g., Firstsource, Quess, eClerx) | PE-backed, Carve-outs, Founders | 30-60% | Moderate | Low-Moderate |

### Family Trusts, Layered Holding & Ultimate Beneficiaries
Indian-family-promoter structures dominate the sector. Founders and trusts hold equity via layered private entities (e.g., Premji investments/trusts for Wipro; Murthy / Nilekani / Gopalakrishnan family groups for Infosys). Always trace ultimate beneficial ownership. The Tata Sons structure (e.g., for TCS) uses a multi-layer setup where the holding company itself is ~66% Tata Trusts-owned, creating a "promoter holds stake in promoter" analytical complexity. Deploy `get_ownership(section='shareholder_detail')` to map named promoter vehicles and use `get_valuation(section='sotp')` to identify cross-holdings of listed subsidiaries (e.g., Tata Elxsi under Tata Sons).

### FDI Caps, ADR/GDR Aggregation & FX-Linked FII
Per FEMA NDI Rules, IT services allows 100% FDI under the automatic route. Mega-cap IT frequently maintains 10-18% of paid-up capital as ADRs. Combine ADR/GDR exposure (e.g., INFY, WIT, WNS) with direct FPI counts to calculate aggregate foreign ownership. Because IT revenue is dollar-denominated, FIIs actively buy IT as a depreciating-INR hedge — FII flow timing correlates strongly with USD-INR moves. Segregate active fundamental allocation from macro FX-hedging flows when analyzing offshore capital surges.

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
- For promoter-trust structures (Tata Sons, Premji Invest), do upcoming group-level capital-allocation decisions risk cascading sell-downs into the listed entity?
