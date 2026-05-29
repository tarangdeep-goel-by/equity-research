## Regulated Power / Utilities — Ownership Agent

### Power Archetype
| Subtype | Archetype | Core Regulatory / Ownership Driver | Illustrative Profile |
| :--- | :--- | :--- | :--- |
| **PSU generation (central)** | Sovereign Hold | GoI 51%+ floor; 100% FDI automatic route (no power-sector FII cap — the 20% cap is PSU-bank-only); Electricity Act 2003 | Central thermal + hydro generators under Ministry of Power |
| **PSU transmission** | Yield Monopolist | CTU monopoly; CERC-regulated ~15.5% ROE; stable DII / FII yield capture | Central transmission utility |
| **PSU distribution** | State / Entity Proxy | State-level funding; localized discom distress; rarely directly listed | State discoms held via state holding entities |
| **Private generation — regulated** | Holdco / Family | CERC / SERC guaranteed ROE; 100% FDI automatic; DII stability | Diversified conglomerate-led regulated power utilities |
| **Private generation — merchant / IPP** | Volatile Private | Commercial tariffs; higher FII turnover; pledge-exposed | Family / group-led merchant IPPs |
| **Renewables specialist** | Growth / Capex | FDI magnet; QIP dilution cycles for capacity; green premium | Listed pure-play renewables platforms (including PSU renewable arms and private green subsidiaries) |
| **Renewable IPP / wind-solar pure-play** | Capex Turnaround | Component-level exposure; retail / FII momentum driven | Wind-turbine OEMs and solar-pure-play listcos |

### PSU Sovereignty, Foreign Caps & Divestment Cycles
Central power PSUs operate under a strict sovereign mandate governed by the Electricity Act 2003 and the PSU Disinvestment Policy, establishing a rigid GoI 51% floor (actual holdings typically 51-70%). **There is NO 20% sector foreign-investment cap on power PSUs** — the 20% aggregate FEMA NDI cap applies specifically to *PSU banks*, not power. The power sector (generation, transmission, distribution) sits under **100% FDI on the automatic route** (only power exchanges are capped, at 49%); the binding constraint for a power PSU is therefore the 51% GoI floor, which leaves up to ~49% institutional headroom, not 20%. Ownership faces perpetual supply overhangs via Finance Ministry-driven PSU divestment cycles; budget targets regularly force OFS events across central generation and hydro PSUs. Isolate active divestment from the mechanical 51%-floor / public-float dynamics rather than a non-existent 20% cap.

### Private Power FDI & Regulated ROE Stability
Unlike PSUs, the private power sector (generation, transmission, distribution) permits 100% FDI under the automatic route per FEMA NDI Rules. Ownership stability correlates with tariff structures. Entities under CERC / SERC-determined tariffs (benchmarked to ~15.5% ROE norms) deliver predictable cash flows, fostering high DII conviction and low turnover. Merchant / IPP entities exhibit elevated ownership volatility due to commercial tariff exposure + PPA execution risks. Chronic state-discom PPA-receivables delays trigger ownership flight in private power.

### SEBI Minimum Public Shareholding (MPS) — Forced OFS Overhang
The SEBI **25% Minimum Public Shareholding** rule is a mechanical supply driver for listed PSUs: a PSU with GoI holding above 75% *must* dilute via OFS/QIP to reach ≥25% public float, creating a predictable equity-supply overhang independent of fundamentals. Several power PSUs have historically sat at or above the 75% promoter threshold. Enforce a SEBI 25% MPS compliance check via `shareholder_detail` — any PSU with public float below 25% (or hovering just above it) carries a structural forced-OFS overhang that caps near-term re-rating.

### InvIT / REIT Sponsor Lock-in — Hardcoded Threshold
For any utility monetizing transmission/renewable assets through an InvIT (or REIT-like vehicle), the binding sponsor-overhang threshold is concrete: **SEBI (InvIT) Regulations 2014, Reg 12(3) — the sponsor + sponsor group must hold a minimum 15% of total units for 3 years from listing** (post-March-2025 amendments: 15% locked for 3 years if the sponsor stays project manager ≥3 years, else 25% locked for 3 years). Use this to size the earliest possible sponsor-stake-monetization window and the unit-supply overhang on the yield vehicle.

### Promoter Pledge Protocols & Capital Cycles
Promoter pledging is a critical distress signal in private power. Historical incidents across over-leveraged private IPPs in the previous capex cycle have made high pledge the key-red-flag indicator. Elevated pledges during group restructuring phases require daily tracking. For renewables specialists, ownership dynamics abandon the utility-yield model for aggressive capex execution. Ownership patterns track capacity additions rather than commodity cycles, with frequent QIPs and rights issues during capacity ramps. High FDI inflows target renewable listcos specifically for ESG mandates.

### Subsidiaries, Fuel Linkages & Yield Vehicles
Value is increasingly fragmented across listed subsidiaries; always run `get_valuation(section='sotp')` (e.g., PSU green-energy carve-outs and private utility renewable arms). Thermal generation ownership flows correlate with PSU coal supply dynamics — policy shifts in domestic coal allocation move thermal-generator ownership in parallel. For transmission and operational renewable assets, monetization via InvITs creates unit-holder structures similar to REITs, transforming equity ownership into mandated yield-distribution profiles dominated by pension and sovereign-wealth funds.

### Mandatory Checklist
- [ ] Verify GoI holding and proximity to 51% floor for PSUs via `shareholder_detail`
- [ ] Check GoI holding against the 51% floor (the binding constraint — there is no 20% power-sector FII cap; that cap is PSU-bank-only) and gauge remaining public/institutional float headroom up to ~49%
- [ ] Execute `promoter_pledge`; flag any private IPP pledge >15% as high risk
- [ ] Run `mf_changes` + `mf_conviction` to assess DII stability vs PPA risk
- [ ] Map recent regulatory tariff orders via `filings` (CERC / SERC updates)
- [ ] Audit state-discom dues and capacity additions via `concall_insights`
- [ ] Screen for OFS overhangs or rights issues via `corporate_actions`; flag SEBI 25% MPS non-compliance (promoter >75%) as a forced-OFS supply overhang
- [ ] Isolate valuation of listed renewable / green subs via `get_valuation(section='sotp')`

### Open Questions
- Does the DII holding pattern reflect pure yield-seeking (regulated ROE) or growth speculation (renewables capex transition)?
- How close is GoI holding to the 51% floor, and how much public-float / institutional headroom (up to ~49%) remains before a further OFS is constrained? (Note: power PSUs have no 20% FII cap — that cap is PSU-bank-only.)
- Are delays in state-discom PPA receivables visibly degrading mutual-fund conviction in the private IPP?
- For renewables specialists, is the current FDI / FPI base capable of absorbing the impending QIP equity dilution required for the next gigawatt expansion phase?
- If the entity is monetising infra through an InvIT / REIT-like vehicle, what is the sponsor's minimum-lock-in status under SEBI REIT/InvIT Regulations 2014?

### Recent-Subsidiary-IPO Ownership Comparison — Canonical Search Worked Pattern
When a utility parent has recently listed a green / renewables / InvIT subsidiary and the parent's ownership narrative hypothesizes FII cannibalization into the subsidiary (foreign holders rotating from regulated-yield exposure into higher-growth green exposure), the thesis cannot stand on the parent's cap table alone. Cross-pull the subsidiary's ownership empirically via `get_ownership(symbol='<subsidiary>', section='shareholder_detail')` and compare named FII/FPI holders quarter-over-quarter across both entities. The *full 5-source canonical search* applies to BOTH parent and subsidiary in parallel.

1. `get_company_context(section='filings', query='subsidiary|listing|IPO|demerger|scheme of arrangement')` — exchange disclosures tracking the subsidiary's listing event, lock-up schedule, and any parent-to-subsidiary stake adjustments.
2. `get_company_context(section='documents', query='IPO|listing|green|renewable|InvIT')` — press releases disclosing the subsidiary's anchor-book composition and post-listing stake intentions.
3. `get_company_context(section='concall_insights', sub_section='management_commentary')` — parent management's own framing of the subsidiary holding strategy (permanent hold vs eventual stake monetization vs zero-dilution commitment).
4. `get_ownership(section='shareholder_detail')` for BOTH parent AND subsidiary — *check — this is the empirical cannibalization test*; named FII holders appearing on the subsidiary register while simultaneously reducing the parent stake is the hard evidence.
5. `get_fundamentals(section='balance_sheet_detail')` — *skip — not directly applicable to cannibalization testing* (subsidiary stake is held at investment-cost on parent's balance sheet and does not reflect FII rotation).

If the subsidiary's `shareholder_detail` returns sparse named-holder data (common for recently-listed entities), flag as a *data limitation* and raise a SPECIFIC open question naming both entities (e.g. *"NTPCGREEN listed under 3 quarters — named FPI roster below 1% disclosure threshold; which named NTPC parent FIIs appear on NTPCGREEN's anchor book?"*).

*Pattern applies to* (verify each relationship type before invoking — they are NOT all parent→listed-subsidiary): NTPC ↔ NTPCGREEN (genuine parent → listed green subsidiary); POWERGRID ↔ **PGInvIT** (POWERGRID's own sponsored InvIT — note IndiGrid/PGInvIT are *separate* InvITs: IndiGrid is sponsored by KKR, ex-Sterlite Power, and is NOT a POWERGRID vehicle); Adani Power ↔ Adani Green (**sister companies** separately promoted by the Adani Group, NOT parent-subsidiary); Tata Power ↔ Tata Power Renewable Energy Ltd (TPREL is an **unlisted** subsidiary — no listed cap table to cross-pull). Same 5-source path applies, but state the actual relationship type (parent-sub vs sister-co vs sponsored-InvIT vs unlisted-sub) before running the cannibalization test.
