## Microfinance Mode (Auto-Detected)

This is a microfinance institution (MFI). MFI lending is high-yield but extremely vulnerable to localized, non-financial shocks.

**Primary Metrics:**
- **GLP (Gross Loan Portfolio)**: The AUM equivalent for MFIs. Growth rate signals market penetration
- **PAR-30 / PAR-90 (Portfolio at Risk)**: the single most important asset quality metric. Compare against peer median via `get_peer_sector(section='benchmarks')` and the company's own trend. PAR-90 indicates likely write-offs
- **Collection Efficiency %**: Steady-state normal is **98-99%**; a drop toward 95% already signals severe portfolio stress and imminent credit-cost spikes. Track monthly — drops precede NPA recognition by 1-2 quarters
- **Credit Cost %**: Annualized provisioning + write-offs as % of AUM. Compare against peer median and the company's own historical range to assess credit cycle position

**Geographic Concentration — The Defining Risk:**
If >20% of GLP is concentrated in a single state, geographic concentration becomes the dominant risk. Indian MFIs have been destroyed by state-specific events: Andhra Pradesh crisis (2010), demonetization impact, COVID rural lockdowns, state election-year farm loan waivers. The top 3 states by exposure and any recent adverse events should be surfaced prominently because a single state event can impair the entire portfolio.

**Exogenous Shock Sensitivity:**
MFI borrowers (rural women, small traders) are vulnerable to: floods/droughts (agricultural income), elections (loan waiver populism), social unrest, and regulatory/political action (state ordinances, pricing scrutiny). These are NOT normal credit risks — they are binary, state-level events. (Note: RBI *removed* the old interest-rate/margin caps for NBFC-MFIs in March 2022, moving to board-approved risk-based pricing — see Regulatory Framework below.)

**Regulatory Framework — The Guardrails That Define the Sector:**
- **RBI 2022 Microfinance Framework** (Master Direction, effective Apr 1, 2022): microfinance loan = collateral-free loan to a household with **annual household income ≤ ₹3 lakh** (single ceiling, rural + urban). Total monthly loan repayment obligations of a household are capped at **50% of monthly household income** (FOIR / repayment-obligation cap, includes the proposed loan). No new loan if the household is already at/above 50%. **Interest-rate and margin caps were removed** — replaced by a board-approved, risk-based pricing policy (RBI scrutinizes for usurious pricing rather than capping).
- **NBFC-MFI qualifying assets:** RBI lowered the threshold from 75% to **a minimum 60% of total assets (net of intangibles)** effective Jun 6, 2025 — do NOT flag a sub-75% ratio as a breach for current periods.
- **MFIN/Sa-Dhan self-regulatory guardrails (tightened 2024-25):** max **3 lenders per borrower** (cut from 4, effective Apr 2025), total microfinance exposure cap of **₹2 lakh per borrower**, and stricter underwriting (no fresh disbursal to borrowers with DPD > 60 days, down from 90). Rising "lender + 4" overlap is an overleveraging red flag.
- **State political/regulatory risk:** the **Karnataka Micro Loan and Small Loan Ordinance, 2025** (Feb 12, 2025) banned coercive recovery, mandated lender registration, and discharged loans of unregistered lenders — a template other states may copy. Surface state-level legislative risk prominently.
- **RBI enforcement:** in Oct 2024 RBI issued cease-and-desist orders against four NBFCs (incl. Asirvad, Arohan, Navi Finserv, DMI Finance) for usurious pricing and breaches of the income/FOIR rules. Track regulatory action as a live, company-specific risk.

**Valuation:** P/B is primary. ROA trajectory (driven by credit cost normalization, not just AUM growth) is the re-rating lever.

**Metrics that mislead for MFIs:** Collateral-based credit analysis frameworks are not applicable — MFI lending is inherently unsecured (JLG/SHG model), so collateral coverage ratios and secured lending metrics don't reflect the actual risk profile.

**Emphasize:** Borrower retention rates, average ticket size trends, rural vs semi-urban mix, and technology adoption (digital collections, cashless disbursals).
