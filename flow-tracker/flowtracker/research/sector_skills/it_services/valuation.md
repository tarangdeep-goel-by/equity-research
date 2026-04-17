## IT Services — Valuation Agent

### Sub-type Routing — Primary Multiple Varies
Standard PE is valid for tier-1 and mid-cap services, but the validation-multiple hierarchy differs by sub-type. Route before loading peer comparables:

| Subtype | Primary multiple | Mandatory validation | Commonly-misapplied multiples that fail |
| :--- | :--- | :--- | :--- |
| **Tier-1 services** | PE (22-30× historical band) | FCF Yield, PEG, EV/Sales as cross-check | DCF terminal-value-heavy (AI disruption makes TV unstable), P/B (asset-light), EV/EBITDA marginal info-add over PE |
| **Mid-cap services** | PE (28-38× at growth phase) | FCF Yield, PEG, EV/Sales | DCF on peak-margin year, P/B |
| **ER&D services** | PE (30-45× given growth premium) + EV/EBITDA | FCF Yield | P/B, DCF on single-client concentration |
| **Platform / product** | EV/Sales × Rule-of-40 (growth + FCF%) | PE (often not meaningful pre-scale), P/AR | DCF with uncertain terminal growth |
| **IT consulting / GCC** | PE + EV/Sales | FCF Yield, utilisation-adjusted | EV/EBITDA on ramp-heavy year |

### FCF Yield — Mandatory Primary Value Test
Mature Indian IT services converts 80-100% of PAT to FCF (asset-light, negative working-capital structure, minimal capex). This makes **FCF Yield = TTM FCF / Market Cap** the cleanest "is this cheap" test, stronger than PE because PE is distorted by one-off hedging gains, ESOP accounting, and buyback-driven EPS optics.

Range calibration for Indian IT services (2024-25 regime):
- **Tier-1**: 2-3% FCF Yield is rich (market pricing growth + buyback yield), 3.5-4.5% is normal, >5% is cheap absolute.
- **Mid-cap**: 3-5% FCF Yield is normal.
- **US-listed peer anchor**: Accenture, Cognizant, Epam trade 3-5% FCF yield; Indian tier-1s trading materially below the US-peer band need a clear growth-differential justification, otherwise the premium is stretched.

Compute via `calculate` with `ttm_fcf_cr` and `market_cap_cr` as named inputs. Pull TTM FCF from `get_fundamentals(section='cash_flow')`; cross-check against `get_quality_scores(section='capex_cycle')` for the FCF/PAT conversion ratio (should sit 80-100% — below 70% is an earnings-quality flag that weakens PE).

### PEG Cross-Check — Growth-Adjusted Multiple Discipline
`PEG = PE ÷ USD-revenue-growth-%`. For Indian tier-1s, 2.5-3.5 is the historical PEG band; >4 is stretched, <2 is cheap. Example: a tier-1 paying 24× PE for 9% USD-revenue growth = PEG 2.67 (middle of band, fair). The same 24× PE on 5% growth = PEG 4.8 (stretched — either growth must accelerate or multiple compresses). Use USD-revenue-growth (not reported INR growth) to isolate volume-price signal from FX noise. Route via `calculate` with `pe` and `usd_rev_growth_pct` as named inputs.

**Why 2.5-3.5 is the fair PEG band for Indian tier-1 IT (not textbook 1.0-1.5):** four balance-sheet attributes compound earnings quality above raw growth. (a) **FCF conversion 80-100% of PAT** — earnings translate cleanly into distributable cash, unlike capex-heavy sectors. (b) **30-50% payout ratio** — ongoing cash yield adds 1.5-3% to total-return. (c) **Net-cash balance sheet** — no solvency discount. (d) **<2% maintenance capex** — incremental growth flows fully to FCF. Strip any of these and the band compresses toward standard 1.5-2.5 PEG territory.

### Forward-Multiple Sanity — Gordon / Justified PE with g
The Gordon framework for a mature franchise: `Justified PE = (1 − retention) × (1 + g) ÷ (CoE − g)`, where `g` is sustainable long-run earnings growth. For Indian IT, realistic `g` sits in the 8-12% range in nominal terms (slower than 15-20% secular pace, given AI-reframe and discretionary-spend drag). **Always carry `g` through the formula** — the BFSI-pilot lesson is that dropping `g` produces a 50-70% under-estimate of fair multiple. Worked calibrations:

- Top tier-1: earnings payout 70%, g 10%, CoE 12% → Justified PE = 0.7 × 1.10 / (0.12 − 0.10) = 38.5× (so 26-30× market PE is below justified — room to re-rate if growth sustains).
- Mid-cap specialist: payout 50%, g 12%, CoE 13% → Justified PE = 0.5 × 1.12 / (0.13 − 0.12) = 56× (but mid-caps rarely trade at this theoretical level — liquidity, key-man, and concentration discount apply).
- Stressed tier-1: payout 70%, g 6%, CoE 12% → Justified PE = 0.7 × 1.06 / (0.12 − 0.06) = 12.4× (AI-reframe scenario with growth collapse).

Sensitivity: a 2pp change in `g` (10→8%) drops justified PE from 38.5× to 18.9× — the growth assumption is as load-bearing as the CoE. Pull CoE from `get_market_context(section='macro')` or the WACC helper.

**Forward-valuation scenario split — AI disruption vs AI monetisation.** The AI-reframe cycle is the largest variable in forward-g and should be scenario-split explicitly, not buried in a point estimate. Bear (disruption dominates): T&M compression on legacy AMS cuts 5-10% of revenue over 2-3 years; g collapses to 4-6% → Justified PE 12-16×. Bull (AI-plumbers monetisation dominates): AI-practice share grows to 15-25% of book on implementation / integration / data-migration / MLOps revenue; g sustains 11-13% → Justified PE 42-50×. Base: mixed — T&M compression offset by AI-adoption revenue, g 8-10%, Justified PE 22-30×. Diagnose which scenario the market is pricing (current PE vs scenario range) and which management disclosure would shift the probability weighting.

### Historical Band Context — Regime-Shift Caveats
A 5-10Y PE band via `get_chart_data(chart_type='pe')` gives the long-arc context (current vs median vs trough-peak). But the band has regime breaks that should be stated, not smoothed over:
- **FY21-22 COVID boom** — tier-1 PE re-rated to 32-38× on digital-acceleration narrative; using that peak as "reasonable upside" over-weights a one-off regime.
- **FY23-25 post-boom normalisation** — PE compressed back to 22-28× as discretionary spend softened; this is the current reference regime.
- **FY26+ potential AI reset** — if productivity re-pricing flows through, the long-run PE anchor may compress structurally to 18-22×. Flag as a scenario, not a base case.

Always state the regime break when citing "current vs 10Y median PE". Route via `get_valuation(section='band', metric='pe')`.

### Peer-Premium / Discount Decomposition
If the stock trades at a PE premium or discount vs sector median from `get_peer_sector(section='benchmarks')`, decompose the delta into four drivers:
- **USD-revenue growth delta** — 200-400 bps of sustained USD-growth advantage justifies 15-25% PE premium.
- **Operating-margin delta** — 200-300 bps of margin advantage (through-cycle, not peak) justifies 10-20% premium.
- **FCF conversion delta** — 85%+ conversion vs peer 75-80% is a 5-10% premium driver.
- **Vertical / geography mix** — BFSI-heavy in a banking stress cycle = discount; diversified vertical mix in a discretionary soft-patch = defensive premium; US-only vs balanced US/EU/RoW changes the recession-beta.

If (a)-(d) together account for less than half of the observed premium, the multiple is vulnerable to mean-reversion and the bull case is leaning on re-rating rather than earnings growth.

### What Fails for IT Services — Name Explicitly
- **DCF on AI-disrupted services** — terminal value is 60-80% of fair value in a DCF, and AI-productivity-re-pricing makes the 5Y+ cashflow assumption unstable. Useful only as a scenario framework, not a point estimate.
- **Simple PE on peak-margin year** — FY22 post-COVID margins at 26-27% for tier-1s compressed to 22-24% by FY25. Peer PE compared on peak-margin EPS over-states value.
- **P/B (asset-light)** — book is cash + buildings + intangibles; book multiple is structurally uninformative.
- **EV/EBITDA** — IT services have near-zero debt and near-zero D&A; EV/EBITDA gives no information beyond what PE already provides. Platform/product is the exception (EV/Sales × Rule-of-40 is the right lens).
- Use instead: PE + FCF Yield + PEG triangle for services; EV/Sales × Rule-of-40 for platforms.

### Data-shape Fallback for Valuation Metrics
When `get_valuation(section='band', metric='pe')` returns fewer than 20 quarterly observations, fall back to `get_chart_data(chart_type='pe')` for the full 10-year series. When `get_fundamentals(section='cash_flow')` lacks TTM FCF, reconstruct from CFO − capex in `get_fundamentals(section='cash_flow')` annual series and flag the reconstruction. If `get_peer_sector(section='benchmarks')` returns a sparse peer set (fewer than 5 names), lean on the explicit tier-1/mid-cap/ER&D/platform ranges above and cite them as structural benchmarks rather than live peer-median.

### Open Questions — IT Services Valuation-Specific
- "What is the TTM FCF Yield and how does it compare against the Indian tier-1 band (2-4%) and US-peer band (3-5%)?"
- "At current USD-revenue growth rate, what does PEG imply, and is the market pricing in an acceleration that management guidance supports?"
- "Is the observed PE premium to sector decomposable into growth + margin + FCF + mix deltas, or is there a residual multiple gap reflecting re-rating sentiment?"
- "What `g` assumption reconciles the current market PE to the Gordon justified multiple at realistic CoE, and does that `g` sit within the 8-12% realistic range?"
- "Does the 5-10Y PE band include the FY21-22 COVID-boom regime, and has that been de-weighted in the current-vs-historical narrative?"
