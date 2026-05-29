## FMCG / Consumer Staples — Financials Agent

### Volume vs Price Growth — The Most Important Split
Revenue growth is a blended number that hides pricing power. Extract from `concall_insights` or `sector_kpis`:
- **Volume growth %** — real demand signal. Compare against peer median and the company's own historical range via `get_peer_sector(section='benchmarks')`
- **Price/mix growth %** — pricing power + premiumization. Pure price growth without volume is unsustainable and signals demand destruction
- If this split isn't in concall data, flag as the #1 open question

### Gross Margin vs A&P Spend Trade-off
This is how FMCG companies manage earnings — it's a deliberate lever:
- Track **Gross Margin** expansion/contraction (commodity cost driven — palm oil, milk, wheat)
- Track **A&P spend as % of revenue** — from `get_fundamentals(section='cost_structure')` if in expense schedules, else from `concall_insights`
- The key insight: are they REINVESTING gross margin gains into A&P (brand building, market share defense) or DROPPING it to EBITDA (short-term profit maximization)?
- Gross margin expanding + A&P declining = future market share risk. Flag this explicitly

### Working Capital (Negative WC = Strength)
**AVAILABLE** from `get_quality_scores(section='sector_health')` for FMCG — returns WC trend.
- Top-tier Indian FMCG companies operate on **negative working capital** — advance collections from distributors + tight receivable management
- If WC turns positive or negative WC is shrinking, distributor leverage is breaking down — flag as structural deterioration
- Use `get_fundamentals(section='working_capital')` for receivables/inventory/payables breakdown

### Rural vs Urban Demand
- Rural recovery/slowdown is a key cyclical driver for Indian FMCG. Extract rural/urban growth split from `concall_insights`
- Rural demand is a LEADING indicator for volume recovery

### Channel Health & Trade Margins
- Watch for **channel stuffing** signals: primary sales (company to distributor) growing materially faster than secondary sales (distributor to retailer) — extract from concall_insights if available
- Rising trade receivables + flat/declining secondary sales = stuffing risk
- **Trade margins / promotions** — FMCG companies use trade schemes to push volume. If gross margin looks stable but trade spends are rising (hidden in "selling expenses" or "sales promotion"), effective realization is falling. Check `get_fundamentals(section='cost_structure')` for selling expense trends

### Channel Mix Shift — Quick Commerce / MT Cannibalising GT
The distributor-retailer General Trade (GT) channel, which has underpinned FMCG negative WC for decades, is structurally compressing as Modern Trade (MT) and Quick Commerce (QC) gain share. Each channel has materially different economics:
- **GT** — 90-95% of distribution historically, high trade margins (~8-12%), negative WC via advance distributor collections
- **MT** — direct-to-retailer, but *lower* net margin realization for the brand: modern-trade chains extract higher trade margins plus listing/slotting fees, in-store promotion and visibility charges that erode the saved distributor margin; also stretched receivables (45-60 days). Do not assume MT is margin-accretive — the chain's bargaining power makes it dilutive to brand realization vs GT
- **QC (10-minute commerce)** — fastest-growing channel in urban India, premium product skew (single-use SKUs, higher ASP), but margin squeeze from platform take rates (15-25%) and dark-store discounting
- Rising QC/MT share reshapes distributor leverage: the negative-WC advantage erodes, and platform pricing pressure hits gross margin. Extract channel mix from `get_company_context(section='concall_insights')` — any report on an FMCG issuer that ignores QC exposure when it exceeds ~8% of urban revenue is incomplete

### MNC Parent Royalty / Technology-Fee Creep
Indian subsidiaries of global consumer MNCs pay royalties and technology fees to the parent for brand licensing and R&D access. Over time these payments often creep up as a % of revenue, effectively siphoning local margin to the foreign parent. This is sector-specific margin leakage that pure-Indian peers don't carry:
- Check `get_company_context(section='filings', sub_section='related_party_transactions')` for royalty & technology-fee disclosure
- Also visible in `get_fundamentals(section='expense_breakdown')` as "Royalty" or "Technical know-how fees"
- Benchmark: the largest MNC subsidiaries now pay materially more than the old 1-3% rule of thumb — HUL pays ~3.45% of turnover (royalty + central-services fee, raised from 2.65% over FY23-25), and Nestle India sought a staggered increase toward ~5.25% of net sales by FY28-29 (15 bps/year), which minority shareholders *rejected* at the FY24 EGM. Use ~3.5-5.25% as the current benchmark band for top MNC subs; a rising trajectory without commensurate brand-building impact is an unjustified siphon and should be flagged as a governance / minority-shareholder concern. The 5% of consolidated turnover threshold (SEBI LODR Reg 23) triggers mandatory "majority of minority" approval
- When modeling forward margins, assume royalty as a % of revenue continues at current trajectory — past hikes rarely reverse

### Innovation Vitality Rate — New Product Contribution
Structural compounders separate from legacy-brand milkers by continually refreshing their portfolio. The key metric:
- **Innovation Vitality Rate** = % of revenue from products launched in the last 2-3 years. Benchmark: 15-25% for genuine innovators, <10% for legacy-dependent businesses
- Combined with premiumization mix trajectory, this tells you whether the moat is widening or eroding. Extract from concall commentary or sector_kpis
- Declining IVR over multiple years, even with stable aggregate volume growth, is a leading signal of brand ageing — flag it even if current margins look healthy

### Shrinkflation & Low Unit Packs (LUPs) — Tonnage vs Unit Volume
Low Unit Packs (₹1/₹5/₹10 sachets and small SKUs) are a massive share of Indian FMCG volume, and the standard "volume growth" companies report can be either **tonnage** (grammage shipped) or **unit/pack count** — these diverge sharply when companies practise *shrinkflation* (cutting grammage at a fixed price point instead of raising MRP, common in soaps, biscuits, namkeen, edible oil during input-cost inflation):
- When a company holds the ₹10 price point but cuts the pack from 100g to 90g, **unit volume can be flat-to-up while tonnage volume falls** — reported "volume growth" then flatters the demand picture if it is pack-count-based
- Mandatory: identify whether the disclosed UVG is tonnage-based or unit/pack-based, and scan concall commentary for grammage actions ("we took a grammage reduction in the ₹5 pack", "price-point packs"). A volume-growth number that is unit-led while grammage is shrinking is *lower quality* than tonnage-led growth
- Source from `get_company_context(section='concall_insights', sub_section='operational_metrics')` / `management_commentary`. If the company does not state which basis its volume metric uses, add it to Open Questions — the tonnage-vs-unit ambiguity is load-bearing for the demand read

### Trade Spend (BTL) vs A&P (ATL) Classification — Ind AS 115
Under Ind AS 115, below-the-line (BTL) trade promotions, consumer schemes, and channel discounts are *netted against revenue* (they reduce gross sales), whereas above-the-line (ATL) brand advertising sits in the P&L as A&P expense. This creates a margin-optics lever:
- Shifting spend from BTL trade schemes (revenue-reducing → depresses reported gross margin) toward ATL A&P (expense-line → preserves gross margin), or vice-versa, can move reported gross margin by 100-300 bps with no change in underlying brand economics
- A company showing gross-margin expansion while A&P-to-sales is *also* rising may simply be reclassifying trade spend, not genuinely improving realization. Conversely, "improving" net realization driven by cutting consumer schemes can mask weakening demand
- Audit the classification: cross-read gross margin, A&P-to-sales, and "sales promotion / rebates & discounts" lines together from the AR other-expense schedule and concall, and flag any large reclassification between BTL and ATL as a margin-quality concern rather than operational improvement

### PLI Scheme Benefits — Isolate from Operating Margin
Several food-FMCG players (packaged foods, ready-to-eat, edible oil, dairy) receive Production-Linked Incentive (PLI) accruals that land in Other Income or net off against expenses, temporarily inflating EBITDA/PBT:
- PLI benefits are time-bound (typically 5-6 year scheme windows) and tied to incremental-sales/investment thresholds — they are *not* a durable operating margin
- Isolate the PLI accrual (disclosed in concall / AR notes / Other Income) and compute underlying margin both with and without it; model the step-down when the scheme tapers. Add to Open Questions if the company benefits from PLI but does not separately quantify the accrual
