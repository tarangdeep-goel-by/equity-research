## BFSI — Ownership Agent

### Foreign Ownership Ceiling — Mandatory Lookup
**Before analyzing FII headroom, identify the statutory foreign-holding cap for this specific BFSI subtype. Applying the wrong ceiling is a material thesis error — it turns a "plenty of room to run" narrative into a "near the cap" narrative (or vice versa).**

| Subtype | Aggregate foreign-holding cap | Key statute / rule |
|---|---|---|
| **Public Sector (PSU) Banks** (SBI, PNB, BoB, Canara, Union, IOB, BoM, Central, Indian, UCO, PSB) | **20%** aggregate (FII + FDI + NRI combined) | **SBI Act 1955 s.3(3)** for SBI; **Banking Companies (Acquisition and Transfer of Undertakings) Acts 1970/1980** for other PSBs |
| **Private Sector Banks** (HDFCBANK, ICICIBANK, AXISBANK, KOTAKBANK, IDFCFIRSTB, INDUSINDBK, FEDERALBNK, RBLBANK) | **74%** aggregate (FDI 49% auto + additional with govt approval; FII sub-limit 49%) | RBI Master Direction on FDI in banks |
| **Insurance companies** (life, general, reinsurance) | **74%** aggregate foreign (Indian owned & controlled required) | **Insurance Act 1938 s.2(7A)** post 2021 amendment |
| **NBFCs** | **100%** via automatic route (subject to sectoral caps) | FEMA NDI Rules 2019 |
| **Asset Management Companies** | **100%** via automatic route | FEMA |
| **Exchanges, depositories, clearing corps** | **49%** aggregate (FDI 26% + FII 23%) | SEBI SECC Regulations |

**Rule:** Before writing the FII headroom section, state the subtype and the applicable cap. For a PSU bank at 10.34% FII, remaining headroom is **~10pp**, not ~64pp. For a private bank at 28% FII, headroom is ~46pp. Getting this wrong inverts the thesis.

Open question candidates: "Is any individual FPI approaching its 10% per-entity sub-limit on this bank?" "Are NRIs near the aggregate 10% NRI sub-limit inside the overall foreign cap?"

### PSU Bank — Statutory Minimum Government Floor
Under the SBI Act (and the equivalent bank-nationalisation acts for other PSBs), **government holding cannot fall below 51%**. This is a floor, not a ceiling — the SEBI 75% MPS cap is non-binding for PSU banks. Practical implications:

- At SBIN's 55.5% government stake, there is ~4.5pp of "divestment headroom" before the 51% statutory floor. Any QIP/OFS beyond that requires a statute amendment (parliamentary act) — not a regulatory process change.
- Government divestment cycles are budget-driven. Check Finance Ministry budget documents (open question → web research) for announced disinvestment targets for the relevant fiscal year.
- For bank-nationalisation-act banks (PNB, BoB, etc.), the floor is typically **51%**. Some restructured banks (Bank of Maharashtra, Central Bank) have temporarily gone below during bailouts — always verify current statutory floor.

### PSU Bank Insider Transaction Framing
PSU banks have **0% promoter-category insider buying culture** — executives (Chairman, MDs, EDs) are government-appointed IAS/banking-cadre officers compensated via scale pay, not ESOPs or stock options. There is no structural mechanism or incentive for open-market buying by management.

- **Correct insider signal:** absence of unusually-high open-market selling (e.g., post-retirement disposals above cadre norms) — not absence of buying.
- Do NOT frame "no insider buying" as a neutral/negative signal. It is structurally absent, not informational.
- Private bank insider signal works differently — ESOP vesting, so track insider selling clusters near earnings.

### LIC as Quasi-Sovereign Anchor
LIC is a Government of India-owned life insurer whose equity book is the largest single non-promoter holder of most large-cap Indian BFSI names. Treat LIC differently from other insurance holders:

- **Stake size:** typically 5-12% in large PSU banks; 4-9% in large private banks. Very slow-moving (quarters to years, not weeks).
- **Intent:** LIC's stake reflects life-insurance asset-liability matching, not active investment conviction. Rising LIC stake during a market sell-off is a **stabiliser signal** (quasi-sovereign absorbing supply), not a high-conviction buy signal.
- **Size-and-velocity rule:** when LIC's stake in a bank exceeds ~7% and has been held for ≥4 quarters, classify it as **structural floor capital** — functionally equivalent to a locked holder. This removes it from the "float at risk of liquidation" consideration.

### Government Divestment Cycle — Key Catalyst
Government divestment is the largest single ownership-risk variable for PSU banks. Track three dimensions:

1. **Announced disinvestment:** Finance Ministry budget targets (open question — web research) and cabinet notifications.
2. **Current headroom:** `(current government stake − 51% floor)` is the available OFS / QIP headroom without legislative action.
3. **Absorption capacity:** QIP oversubscription ratio (from concall / `get_events_actions`) tells you whether the market has absorbed the last tranche cleanly. 3x+ oversubscribed = supply overhang neutralised; <1.5x = indigestion likely to weigh on price.

For banks that recently completed a QIP (SBIN Sep 2025, PNB FY23, BOB FY23), state the **specific absorption metric** — 4.5x oversubscribed at ₹X price vs current ₹Y tells the story of post-dilution re-rating or pressure.

### FPI Concentration Norms — Entity + Sector Sub-limits
On top of the aggregate cap above, SEBI and RBI enforce concentration sub-limits:

- **Per-FPI (entity-level) limit** in a single bank: **10%** of paid-up capital — for all FPI categories combined, a single FPI group cannot exceed this.
- **NRI aggregate** (subset of foreign holding): **10%** of paid-up capital.
- **Sectoral investment-cap** reporting: any bank reaching **within 2pp of its aggregate foreign cap** gets onto the RBI's "sector cap list," after which fresh FPI buying requires explicit approval.

For PSU banks at >18% aggregate foreign holding, flag as "approaching cap." For private banks at >72%, flag as "near cap — incremental FII buying requires case-by-case approval."

### Hard-Evidence Rule for Overriding System Signals
When `get_market_context(delivery_analysis)` or `get_analytical_profile` returns a classified signal (e.g., `speculative_churn`, `distribution`, `accumulation`), do not override it with a narrative-level reclassification unless you cite **at least 2 independent data points** that support the alternative reading.

- **Bad pattern:** "System flags speculative_churn, but the DII buying streak suggests accumulation under cover." (1 countervailing point, speculation disguised as analysis)
- **Good pattern:** "System flags speculative_churn. However, (1) DII has bought on 28 consecutive days with cumulative net +₹X Cr, (2) promoter stake is stable at 55.5% with no pledge, (3) FII stake rose +77bps in the current quarter — three independent institutional cohorts are accumulating while retail churns. Reclassify as 'accumulation-under-cover pattern.'"

If you cannot cite 2+ hard data points, let the system signal stand and note the apparent tension in Open Questions.

### ADR / GDR Foreign Ownership — Mandatory Breakout for Large Private Banks
Large Indian private banks (HDFCBANK, ICICIBANK, AXISBANK, INFY's holders via sponsored ADRs — less applicable to pure-BFSI) often have a material ADR/GDR (American / Global Depositary Receipt) programme. **ADRs count toward the aggregate foreign-holding cap** but sit outside direct FPI-registered holdings.

- Indian regulators (RBI + SEBI) combine (a) direct FPI holdings + (b) ADR/GDR outstanding + (c) NRI holdings into the aggregate foreign cap calculation.
- For HDFCBANK specifically: the ADR (NYSE: HDB) typically represents **14-18% of paid-up capital** — subtracting this from the reported FII% can surface that effective foreign headroom is materially smaller than `74% − reported_FII%` implies.
- When analyzing foreign headroom for any large private bank, explicitly check `get_company_context(filings)` or `concall_insights` for ADR outstanding. If no ADR data is available via tools, add to Open Questions: "What is the current ADR/GDR outstanding as a % of paid-up capital, and what is the combined direct-FPI + ADR + NRI holding vs the 74% cap?"
- For PSU banks (20% cap): ADRs are rare but possible — still verify before computing headroom.

### Single-Period Ownership Jumps — Beware Reclassification Artifacts
When you observe a **large single-quarter ownership change (>5pp)** in any category (FII, DII, MF, Promoter, Insurance), treat it FIRST as a **potential reclassification or corporate action artifact**, NOT as directional active buying/selling. Common causes:

- **Corporate action reshuffles:** mergers (like HDFC Ltd → HDFC Bank 2023), demergers, restructurings create step-changes in share counts and cause mechanical category shifts
- **Category re-tagging by the exchange:** custodian reclassifies a foreign holder from FDI to FPI (or vice versa), moving the same shares between lines — no actual trading
- **FPI deemed-promoter reclassification:** SEBI's 2019 rule treating beneficial FPIs in the same corporate group as "deemed promoter" has forced multiple ownership restatements
- **Index reweighting surges:** MSCI EM / FTSE rebalances drive mechanical passive FII buying/selling concentrated in one quarter

Rule: if you see a jump >5pp in a single quarter, your default assumption is reclassification/corporate-action, and you must cite the specific trigger (from concall_insights, filings, or corporate_actions) before narrating it as active accumulation or distribution. If you cannot find the trigger, pose as an open question and state the caveat clearly in the main narrative.

### Mandatory Ownership Checklist (Write Before Report)
Before drafting the Institutional Verdict, explicitly confirm each row. A missing row is a workflow violation.

- [ ] Subtype identified: PSU bank / private bank / insurance / NBFC / exchange / AMC
- [ ] Aggregate foreign-holding cap stated with statute reference
- [ ] Current foreign holding vs cap = headroom in pp
- [ ] Government statutory floor (for PSU) or promoter minimum (for private)
- [ ] QIP/OFS absorption metric if any has occurred in last 8 quarters
- [ ] LIC stake classified as structural floor / active holding / not-applicable
- [ ] Insider-transaction framing appropriate to subtype (ESOP vs IAS cadre)
- [ ] **ADR/GDR outstanding checked** (large private banks) — combined with direct FPI for true foreign headroom
- [ ] Any single-quarter ownership change >5pp has been verified against corporate actions / reclassification triggers before narration

### Open Questions — BFSI-Specific
Prefer these over generic regulatory questions:

- "Is the current FII % approaching the per-FPI 10% entity-level sub-limit for any individual foreign holder?"
- "What disinvestment target did the Finance Ministry set for PSU bank stake sales in the current fiscal?"
- "Is any RBI prompt-corrective-action (PCA) framework trigger active for this bank?" (for weaker PSBs)
- "Are there pending SEBI circulars that would tighten the aggregate foreign-holding cap formula?"
