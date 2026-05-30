## Packaging & Paper Mode (Auto-Detected)

This company operates in the packaging, paper, or polymer-film sector. Apply the **Producer vs. Converter** analytical framework. 

**The Core Sector Distinction — Producer vs. Converter:**
The packaging universe is split into two fundamentally different business models that cannot be evaluated using the same metrics:
1. **Producers (Upstream):** Manufacture the base substrate (BOPP/BOPET polymer films, kraft paper, writing/printing paper). Examples: Polyplex, Cosmo First, JK Paper, West Coast Paper. **Economics:** Highly cyclical, driven by global capacity additions and raw material (crude/pulp) spreads. They are price-takers.
2. **Converters (Downstream):** Buy the substrate, print, laminate, and shape it into final consumer packaging (tubes, cartons, flexible pouches, glass bottles). Examples: EPL Ltd, TCPL Packaging, AGI Greenpac, Huhtamaki India. **Economics:** Stable, FMCG-like compounders. They operate on a "cost-plus" model, passing raw material volatility to clients with a 1-3 month lag.

**Margin % is an Illusion — Use EBITDA/kg or EBITDA/tonne:**
For this sector, **EBITDA margin % is mathematically misleading**. Because raw material (RM) costs are passed through to the final price, a spike in polymer/pulp prices inflates both Revenue and RM cost equally. This causes the EBITDA *margin %* to optically crash, even if the absolute profit per unit is unchanged. 
*Rule:* Always evaluate profitability using **EBITDA/kg** (for flexible/films) or **EBITDA/tonne** (for paper/rigid), available via `get_company_context(section='sector_kpis')` or concall extraction. Ignore EBITDA margin % fluctuations driven purely by RM inflation/deflation.

**Primary Valuation Metrics:**
- **EV/EBITDA**: Primary metric for both sub-types. 
- **P/E**: Valid for stable Converters (EPL, TCPL). **Misleading** for Producers (Polyplex, JK Paper) due to the cyclical PE trap (lowest PE at cycle peak when film/pulp spreads are unsustainably high).
- **P/B**: Floor valuation metric for asset-heavy Paper and Film producers at cycle troughs.

### Mandatory — The Packaging KPI Backbone
Every packaging/paper report must explicitly extract and cite these metrics:
- **Volume Growth (MT/tonnes):** The true measure of demand, stripping out RM-driven price inflation.
- **EBITDA per unit (₹/kg or ₹/tonne):** The true measure of profitability.
- **Value-Added Product (VAP) Mix %:** The transition from commodity to specialty (e.g., coated paper, specialty films, sustainable/PCR tubes). Higher VAP = higher and more stable EBITDA/kg.
- **Capacity Utilization %:** Packaging is asset-heavy. Operating leverage kicks in above 75% utilization.
- **RM Pass-Through Lag:** Usually 30-90 days. Must be cited when explaining quarterly earnings misses/beats.

### Annual Report & Investor Deck — Packaging Specifics

**AR high-signal sections:**
- `mdna` — Raw material price trends (wood pulp, waste paper, PTA/MEG, polypropylene), capacity utilization, and export vs. domestic volume split.
- `risk_management` — Single-use plastic regulations, Extended Producer Responsibility (EPR) compliance costs, client concentration (e.g., reliance on top-5 FMCG buyers).
- `segmental` — Bifurcation between commodity packaging and value-added/specialty packaging.
- `notes_to_financials` — Capitalization of new lines (BOPP/BOPET lines or paper machines), inventory valuation methods (critical during volatile RM periods).

**Deck high-signal sub_sections:**
- `key_metrics` — Volume (MT) trajectory, EBITDA/kg, VAP share %.
- `outlook_and_guidance` — Upcoming capacity additions (in MTPA), expected commissioning dates, and FMCG/Pharma demand commentary.
- `sustainability` — Post-Consumer Recycled (PCR) content %, recyclable laminate structures (shift to mono-material packaging).

**Cross-year narrative cues:** `capital_allocation_shifts` often reveal a pivot from commodity capacity expansion to specialty/VAP acquisitions; `biggest_concern` tracks the threat of Chinese dumping in polymer films or ASEAN dumping in paper.
