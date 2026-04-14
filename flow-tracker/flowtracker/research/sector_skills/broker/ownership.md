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
