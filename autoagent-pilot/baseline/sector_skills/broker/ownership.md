## Brokers / Capital Markets — Ownership Agent

### Broker / Capital Markets Archetype
| Subtype | Archetype | Dominant Ownership Pattern & Catalysts |
| :--- | :--- | :--- |
| **New-age / Digital-first discount brokers** | High-beta retail volume proxy | Founder-led (20-40%) + VC roster (30-50%). Supply-overhang risk at 6-month and 12-month post-IPO lock-up expiries. |
| **Full-service Legacy brokers** | Advisory / proprietary blend | Family or conglomerate promoter-led. High promoter holding limits free float. Stable dividend yields attract DII accumulation. |
| **Bank-subsidiary brokers** | Captive banking clientele | Parent-bank as promoter. Equity flows reflect parent-bank liquidity. Cross-holding complexity on carve-out listings. |
| **Wealthtech / PMS** | HNI fee-based advisory | High FII / DII float absorption via financialization. Pre-IPO PE / VC exits via block deals. |
| **AMCs (listed asset managers)** | Beta-agnostic AUM compounding | Bank-sub promoter or standalone (diffused). Steady DII anchor. FDI 100% automatic route. |
| **Exchanges / Depositories** | Market-infra monopolies | Regulated non-promoter institutional ownership. SEBI SECC / D&P single-shareholder and aggregate foreign limits. |

### SEBI Ring-Fencing & Regulatory Event Catalysts
SEBI ring-fencing circulars mandate strict separation of client funds from proprietary books, fundamentally altering broker unit economics. Enhanced net-worth and governance requirements affect free-float behavior during regulatory audits. Regulatory step-changes (upfront margin rules, T+0 settlement rollouts) create step-changes in broker economics, driving sharp institutional ownership rotations. Execute `get_company_context(section='filings')` to map ownership shifts against SEBI circular implementation dates.

### New-Age Broker IPO Pattern & VC Roster Overlap
New-age broker cap tables mirror the consumer-tech platform sector. Pre-IPO VC rosters overlap heavily across global growth-stage funds. Post-listing they exhibit the standard 6-month and 12-month lock-up expiry supply waves. Track ESOP trust offloading as in platforms. Use `get_ownership(section='shareholder_detail')` to map private market participant exits via block windows.

### Holdco Structures & Bank-Sub Carve-Outs
Bank-subsidiary brokers and AMCs frequently list via carve-outs, creating cross-holding complexity. Intermediary holding companies (a conglomerate financial-services holdco holding both the broker and the AMC) skew the apparent standalone promoter percentage. When evaluating carve-outs, institutional accumulation must be weighed against parent's strategic holding floor. Always trigger `get_valuation(section='sotp')` to isolate the intrinsic value of the broker / AMC from parent's consolidated float.

### AMC DII Anchoring & 100% FDI Automatic Route
AMC ownership provides steady DII anchoring due to structural domestic financialization. Per FEMA NDI Rules, AMCs are eligible for 100% FDI under the automatic route (contrasting with stringent banking limits). Standalone AMCs operate with diffused institutional ownership, whereas bank-sub AMCs maintain high parent-led promoter minimums. Run `mf_changes` + `mf_conviction` concurrently to gauge peer-DII confidence cycles in listed asset managers.

### SEBI SECC / D&P Concentration Caps
Market infrastructure institutions (Exchanges, Depositories, Clearing Corps) are governed by SEBI SECC Regulations (Stock Exchanges and Clearing Corporations) and SEBI D&P Regulations (Depositories and Participants). Aggregate foreign ownership is capped at 49% (FDI 26% + FII 23%). Single-shareholder caps of 5% apply, with explicit exemptions up to 15% for specific regulated financial institutions. A breach or near-breach triggers mandatory offloading or freezes FII accumulation.

### MTF Leverage Signaling & Pledge Distinctions
Broker Margin Trading Facility (MTF) books are a critical leverage indicator. High MTF growth correlates with peak retail-trader exuberance and often supports FII accumulation / exit theses at cycle tops. **Distinguish** pledged shares held as client collateral from actual promoter pledging of their own equity. Misinterpreting client collateral as financial distress is a common error. Filter via `get_ownership(section='promoter_pledge')` to isolate genuine promoter-equity pledges.

### Mandatory Checklist
- [ ] Determine subtype and apply SEBI regulatory limits (SECC 49% FII/FDI limit for exchanges; D&P for depositories)
- [ ] Run `shareholder_detail` to identify global growth-stage VC roster overlap in new-age brokers
- [ ] Check IPO / OFS timelines via `filings` for 6 / 12-month VC lock-up expiries
- [ ] Query `corporate_actions` for AMC cash return (dividends / buybacks) driving DII conviction
- [ ] Execute `mf_changes` + `mf_conviction` to track mutual-fund behavior in AMC peers
- [ ] Use `promoter_pledge`; filter out client collateral from genuine promoter pledges
- [ ] Run `sotp` for bank-sub holding companies to derive apparent vs actual promoter float

### Open Questions
- Is the current institutional accumulation in the new-age broker front-running a known VC lock-up expiry, or absorbing it?
- Does the broker's MTF book expansion correlate with rising retail float, indicating cycle-peak exuberance?
- For infrastructure monopolies, is FII ownership approaching the 49% SECC / D&P ceiling, capping further price discovery?
- Are recent changes in standalone AMC ownership driven by structural shifts in domestic SIP flows, or FEMA NDI 100% FDI regulatory arbitrage?

### New-Age Broker IPO Lock-In Calendar — Worked Template (Tenet 19)
For any stockbroking/fintech-broker stock listed <730 days ago (recently-listed new-age discount-brokers such as GROWW, the post-listing ANGELONE glide path, ZERODHA-adjacent aggregator IPOs, 5PAISA, and any SEBI (ICDR) Reg 16/17 IPO), a lock-in calendar table is MANDATORY in Section 2 — without it, institutional flow narration during the first 540 days is incomplete. Populate:

| Expiry Date | Category Expiring | % of Equity | Current Status |
| :--- | :--- | :--- | :--- |
| T+30d | Anchor allocation (50% tranche) | X% | locked / expired |
| T+90d | Anchor allocation (balance 50%) | X% | locked / expired |
| T+180d | Pre-IPO investor lock — VC roster tier-1 | X% | locked / expired |
| T+365d | Promoter-group (selling-shareholders) | X% | locked / expired |
| T+540d | Strategic / founder-tier promoter lock (18m SEBI floor) | X% | locked / expired |

Dates sourced from the DRHP / RHP cover via `get_company_context(section='filings', query='lock-in|RHP|allotment')`. If unretrievable, raise a SPECIFIC open question citing the DRHP page, not a generic one (see Tenet 19). *Peer instances*: GROWW, ANGELONE, MOTILALOFS (legacy, but post-block-deal windows apply), 5PAISA, ICICIDIRECT (captive-broker carve-out).

### Unit-Economics Overlay on FII vs DII Accumulation
When FII accumulates in a new-age broker, cross-check whether the add tracks **ADTV (average daily turnover) growth** or **active-client growth** — these split the sector into two franchises. FIIs (active foreign mandates) preferentially accumulate tick-stream / ADTV-driven franchises (F&O-heavy, per-order revenue scaling) because the earnings beta to volatility is higher. DIIs preferentially accumulate stable-fee / subscription franchises (advisory, distribution, AMC-linked fee income) where PAT is less volatility-linked. If FII is adding but ADTV is flat while active-clients rise, the FII may be front-running a platform-fee pivot — flag as a conviction-quality question rather than treating as generic bullish. *Peer instances*: GROWW (ADTV-weighted tilt vs subscription tilt evolving), ANGELONE (F&O-heavy ADTV), MOTILALOFS (advisory/wealth-heavy, more DII-friendly), 5PAISA (ADTV-tilt), ICICIDIRECT (captive distribution-heavy).

### Regulatory-Event Canonical Search (Broker-Specific)
Any SEBI circular affecting brokers — peak-margin norms, upfront-margin collection, F&O lot-size changes, inactive-account norms, true-to-label rules, client-funds segregation audits — creates step-changes in broker economics and triggers sharp institutional rotation. Whenever the ownership narrative touches a SEBI regulatory event, concall narrative alone under-discloses. Apply the 3-source canonical search before correlating any FII exit/reentry to a regulatory catalyst:

1. `get_company_context(section='filings', query='SEBI|circular|margin|peak margin|true to label|inactive account')` — exchange disclosures tied to the circular implementation date.
2. `get_company_context(section='documents', query='SEBI circular|regulatory|margin rules')` — press-release / investor-letter characterization.
3. `get_company_context(section='concall_insights', sub_section='flags')` then `sub_section='management_commentary')` — management's own framing of the step-change on revenue, order-count, and PAT.

If all three return empty for the specific circular and implementation window cited in the ownership narrative, raise a SPECIFIC open question naming the circular date and broker segment affected (e.g. *"Peak-margin Phase-4 implementation December 2021 — no `filings` or `documents` disclosure found on per-order-revenue impact; is the ADTV step-down already reflected in the Q3-FY22 trajectory or deferred?"*), not a generic "what did SEBI change?".

*Pattern applies to*: peak-margin rollout windows (GROWW, ANGELONE, 5PAISA post-Dec 2021), inactive-account rule sweeps, F&O lot-size revisions (Oct 2024), and true-to-label disclosure enforcement — same 3-source path whenever the ownership narrative invokes a SEBI regulatory trigger.
