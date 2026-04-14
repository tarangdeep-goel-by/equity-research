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
- **MT** — direct-to-retailer, higher margin realization (~3-5pp higher than GT) but stretched receivables (45-60 days)
- **QC (10-minute commerce)** — fastest-growing channel in urban India, premium product skew (single-use SKUs, higher ASP), but margin squeeze from platform take rates (15-25%) and dark-store discounting
- Rising QC/MT share reshapes distributor leverage: the negative-WC advantage erodes, and platform pricing pressure hits gross margin. Extract channel mix from `get_company_context(section='concall_insights')` — any report on an FMCG issuer that ignores QC exposure when it exceeds ~8% of urban revenue is incomplete

### MNC Parent Royalty / Technology-Fee Creep
Indian subsidiaries of global consumer MNCs pay royalties and technology fees to the parent for brand licensing and R&D access. Over time these payments often creep up as a % of revenue, effectively siphoning local margin to the foreign parent. This is sector-specific margin leakage that pure-Indian peers don't carry:
- Check `get_company_context(section='filings', sub_section='related_party_transactions')` for royalty & technology-fee disclosure
- Also visible in `get_fundamentals(section='expense_breakdown')` as "Royalty" or "Technical know-how fees"
- Benchmark: 1-3% of revenue is typical; rising trajectory without commensurate brand-building impact is an unjustified siphon and should be flagged as a governance / minority-shareholder concern
- When modeling forward margins, assume royalty as a % of revenue continues at current trajectory — past hikes rarely reverse

### Innovation Vitality Rate — New Product Contribution
Structural compounders separate from legacy-brand milkers by continually refreshing their portfolio. The key metric:
- **Innovation Vitality Rate** = % of revenue from products launched in the last 2-3 years. Benchmark: 15-25% for genuine innovators, <10% for legacy-dependent businesses
- Combined with premiumization mix trajectory, this tells you whether the moat is widening or eroding. Extract from concall commentary or sector_kpis
- Declining IVR over multiple years, even with stable aggregate volume growth, is a leading signal of brand ageing — flag it even if current margins look healthy
