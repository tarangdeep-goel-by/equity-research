## Microfinance Mode (Auto-Detected)

This is a microfinance institution (MFI). MFI lending is high-yield but extremely vulnerable to localized, non-financial shocks.

**Primary Metrics:**
- **GLP (Gross Loan Portfolio)**: The AUM equivalent for MFIs. Growth rate signals market penetration
- **PAR-30 / PAR-90 (Portfolio at Risk)**: the single most important asset quality metric. Compare against peer median via `get_peer_sector(section='benchmarks')` and the company's own trend. PAR-90 indicates likely write-offs
- **Collection Efficiency %**: Must be >95% in normal conditions. Track monthly — drops precede NPA recognition by 1-2 quarters
- **Credit Cost %**: Annualized provisioning + write-offs as % of AUM. Compare against peer median and the company's own historical range to assess credit cycle position

**Geographic Concentration — The Defining Risk:**
If >20% of GLP is concentrated in a single state, geographic concentration becomes the dominant risk. Indian MFIs have been destroyed by state-specific events: Andhra Pradesh crisis (2010), demonetization impact, COVID rural lockdowns, state election-year farm loan waivers. The top 3 states by exposure and any recent adverse events should be surfaced prominently because a single state event can impair the entire portfolio.

**Exogenous Shock Sensitivity:**
MFI borrowers (rural women, small traders) are vulnerable to: floods/droughts (agricultural income), elections (loan waiver populism), social unrest, and regulatory changes (RBI interest rate caps). These are NOT normal credit risks — they are binary, state-level events.

**Valuation:** P/B is primary. ROA trajectory (driven by credit cost normalization, not just AUM growth) is the re-rating lever.

**Metrics that mislead for MFIs:** Collateral-based credit analysis frameworks are not applicable — MFI lending is inherently unsecured (JLG/SHG model), so collateral coverage ratios and secured lending metrics don't reflect the actual risk profile.

**Emphasize:** Borrower retention rates, average ticket size trends, rural vs semi-urban mix, and technology adoption (digital collections, cashless disbursals).
