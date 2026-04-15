## Private Bank — Financials Agent

Inherits full BFSI financials framing (see `bfsi/financials.md`) — asset quality (GNPA/NNPA/PCR/SMA-2/technical-writeoffs), liability franchise (CASA, cost of funds), Bank DuPont on ROA, capital adequacy (CRAR/CET1), and P/B-ROE valuation. This file adds the private-bank-specific emphasis on non-interest income decomposition, SOTP valuation for conglomerate groups, NIM-quality decomposition, and CET1 dilution-risk framing.

### Non-Interest Income Decomposition — The Fee Moat
Other Income for private banks mixes three streams with very different quality profiles. Always separate:
- **Core fee income** — processing fees, cross-sell commissions (insurance / AMC / brokerage), wealth-management fees, forex spreads. Sustainable and compounding
- **Treasury income** — bond MTM, trading gains. Volatile, rate-cycle-driven — do NOT extrapolate quarterly spikes
- **Recoveries from written-off accounts** — lumpy, non-recurring
- **Fee / total income benchmarks (private banks)**:
  - **>25% = strong moat** — HDFCBANK, ICICIBANK historically. Indicates deep cross-sell infrastructure
  - **15-25% = moderate** — most mid-tier privates
  - **<15% = thin** — heavily NIM-dependent, structurally lower-quality earnings
- Flag quarters where Other Income growth materially exceeds NII growth → likely treasury, not core

### SOTP for Conglomerate Bank Groups
When a private bank owns listed subsidiaries whose combined value exceeds 15% of standalone bank market cap, standalone P/B understates fair value. Call `get_valuation(section='sotp')` and present per-subsidiary valuation:

- **HDFCBANK**: HDB Financial Services (IPO-bound FY26, use implied EV from last private round or comparable NBFC mcap), HDFC AMC (listed — market cap × ownership %), HDFC Life (listed), HDFC ERGO (unlisted — use implied EV from last capital raise or comparable general-insurance multiples)
- **ICICIBANK**: ICICI Pru Life (listed), ICICI Lombard (listed), ICICI Pru AMC (listed), ICICI Securities (post-delisting offer — use last traded price or implied OFS value)
- **KOTAKBANK**: Kotak Mahindra AMC (unlisted — very large EV, typical 4-6% AMC mcap-to-AUM on Indian AMCs), Kotak Mahindra Life Insurance (unlisted — VNB-based implied EV), Kotak Securities (unlisted)
- **AXISBANK**: Axis AMC (unlisted), Max Life 20% stake post deal (listed Max Financial parent)
- **Method**: (market-cap or implied-EV) × ownership % → aggregate → apply 20-25% holding-company discount → divide by bank shares outstanding → SOTP per share
- **Core bank stripping**: `standalone_bank_implied_value = current_mcap − subsidiary_SOTP_value`. Compute implied standalone P/B using **standalone BVPS** (never consolidated — consolidated book includes subsidiary goodwill / investments that distort)

### NIM Quality Decomposition
Headline NIM alone is misleading. The **cause** of NIM level determines whether it's cyclically robust or at risk:
- **High-CASA-driven NIM** (HDFCBANK historically, ICICIBANK) — stable across rate cycles. Low-cost funding franchise is the moat; NIM is durable
- **High-yield-asset-driven NIM** (HDFCBANK retail unsecured, KOTAKBANK, IDFCFIRSTB) — earned via higher-yielding unsecured lending (personal loans, credit cards, small-ticket retail). Rate-cycle-sensitive and credit-cost-exposed. Can compress fast if asset-quality cycle turns
- **In concall**, decompose: `NIM ≈ Yield on advances − Cost of deposits − (Provisions / avg advances)`
  - Track each component QoQ; narrate which component is driving the move
  - Yield-on-advances moves with RBI repo + pricing power; cost-of-deposits moves with CASA mix + bulk-deposit reliance
- Extract via `get_sector_kpis` or `get_company_context(section='concall_insights')`

### Asset Quality — Inherits BFSI, With Private-Bank Texture
Private banks disclose SMA buckets more consistently than PSU banks. For private banks:
- Expect full GNPA / NNPA / PCR / SMA-0 / SMA-1 / SMA-2 / restructured-book / credit-cost disclosure
- A private bank that does NOT disclose SMA-2 in the quarterly deck is **hiding the leading signal** — flag explicitly
- **Unsecured-retail-heavy private banks** (HDFCBANK PL+CC book, KOTAKBANK, IDFCFIRSTB) — track **retail PL + CC slippages separately** from corporate slippage. Retail unsecured cycle peaks 2-3 quarters after macro unemployment inflects
- **Corporate-heavy mid-tier privates** (RBLBANK historically, INDUSINDBK in certain segments) — track **BB & below standard assets** book for lumpy chunky-account risk

### Capital Adequacy — Dilution Risk Framing
- **CET1 < 13%**: dilution risk is real. Private banks historically at CET1 below 13% have needed QIPs within 4-6 quarters (AXISBANK's dilution history is the archetype)
- **CET1 13-15%**: moderate headroom; dilution not imminent unless credit growth accelerates sharply above 20%
- **CET1 > 15%**: comfortable — usually HDFCBANK, KOTAKBANK, ICICIBANK band
- When CET1 falls below 14%, run forward-BVPS projections through the `calculate` tool — do NOT compute compound dilution in your head
- Canonical key: `get_sector_kpis(sub_section='capital_adequacy_ratio_pct')`

### Conglomerate Accounting — Standalone vs Consolidated
For HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK:
- **Standalone financials** = core bank only. Use for NIM, CD ratio, NPA, CET1
- **Consolidated financials** = core bank + subsidiaries. Use for headline RoE, consolidated BVPS, group-level PAT
- **Never mix** — computing RoA on consolidated PAT divided by consolidated total assets produces artefacts because subsidiary P&L structures differ from bank P&L
- Call `get_fundamentals(section='annual_financials')` and confirm which mode the tool returned

### Valuation Basis (Private Bank Specific)
- Primary: **P/ABV** (P/B adjusted for net NPAs) on standalone BVPS for core bank
- Overlay: **SOTP** for conglomerate groups (>15% subsidiary contribution)
- Cross-check: **P/B-ROE framework** — justified P/B = (ROE − g) / (CoE − g); for private banks with sustainable ROE 16-20%, justified P/B is typically 2.5-3.8x depending on CoE assumption
- Residual Income Model (RIM) when ROE is cyclically depressed but structurally recovering
- Peer band via `get_valuation(section='band', metric='pb')` and `get_peer_sector(section='benchmarks')`

### Forward Projection Rule
All forward BVPS, CET1, dilution-scenario, or credit-cost projections must go through the `calculate` tool. Compound growth in your head (or in a narrative "~₹X in three years at ~Y%") produces errors that verification will catch — route through `calculate` every time.
