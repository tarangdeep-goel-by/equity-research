## Telecom Mode (Auto-Detected)

This is a telecom operator. Spectrum amortization and heavy capex distort standard profitability metrics.

**Key Distortions:**
- PAT margin is depressed by massive spectrum amortization charges (not a real cash cost after initial payment)
- PE appears artificially high due to amortization-depressed earnings
- Capex intensity is structural (network expansion, 5G rollout) — penalizing high capex misses the growth story

**Primary Valuation Metrics:**
- **EV/EBITDA**: primary metric for telecom — removes spectrum amortization distortion
- **OpFCF (Operating Free Cash Flow)**: EBITDA minus capex. Available in `get_quality_scores` telecom section. Shows true cash generation after network investment
- **Net Debt/EBITDA**: critical for telecom given heavy leverage from spectrum purchases. Compare to peer median and the company's own trend to assess leverage trajectory
- **Capex/Revenue ratio**: investment intensity — 15-25% typical for Indian telecom in expansion phase

**Metrics that mislead in isolation for telecom:**
- PE ratio — spectrum amortization depresses reported earnings, making PE artificially high and non-comparable across sectors
- PAT margin — same distortion from amortization; EV/EBITDA removes this noise
- PEG ratio — growth appears distorted when earnings are depressed by non-cash charges, making PEG unreliable

**Key Operational Metrics (from concall insights):**
- **ARPU (Average Revenue Per User)**: the single most important KPI — ARPU × subscribers = revenue
- **Subscriber count and net additions**: volume driver
- **Churn rate**: retention quality
- **Data usage per subscriber**: engagement and monetization potential
- **4G/5G mix**: technology migration progress

### Mandatory Arithmetic & Unit Discipline

- **ARPU × users revenue-bridge template.** When quantifying revenue trajectory, always show the bridge: `subscribers_mn × arpu_₹_per_month × 12 = revenue_cr_annualized`. Units: subscribers in millions (or crores — state which), ARPU in ₹/subscriber/**month** (NOT annual) — 3× error is the most common telecom-financials failure mode. Pass through `calculate(operation='expr', a='<subscribers_mn> * <arpu_monthly> * 12', b='0')` and cite the output; never hand-math a 9-digit multiplication.
- **Nigeria / international-geography FX devaluation risk.** For operators with African / LatAm exposure (Bharti Airtel Africa, Vodafone Idea's international book, Reliance Jio / Jio-bp minority), local-currency ARPU growth can mask USD-denominated revenue decline after FX devaluation. Cite the constant-currency growth alongside reported growth and identify any >15% cumulative YoY FX devaluation in the relevant geography. Nigeria NGN, Egyptian EGP, Turkish TRY, Argentine ARS have historically surprised investors; the report must state the FX regime in the geography, not just the local-currency operating metric.

### Data Workaround — EBITDA Source

`get_quality_scores(section='all')` has historically returned mis-mapped values for metals and telecom sectors (depreciation-as-EBITDA). Until the sector-aware field router ships, pull telecom EBITDA from `get_fundamentals(section='annual_financials')` → operating-profit line, reconciled against the concall `financial_metrics` quoted EBITDA. If a single-quarter spike shows up in EBITDA, cross-check the concall for one-offs (spectrum sale, tower transaction, insurance recovery) before narrating it as operational.

**SOTP Note:** For diversified telecom operators running multiple verticals (mobile domestic + international geographies + towers + broadband + enterprise + digital payments), SOTP analysis is appropriate but requires segment-level data from investor presentations. If segment data is not available from tools, state this limitation explicitly rather than estimating segment values.

**Emphasize:** ARPU growth trajectory, subscriber market share, 5G monetization timeline, spectrum holding adequacy, tower-sharing economics, and international segment contribution when the operator has cross-border exposure.
