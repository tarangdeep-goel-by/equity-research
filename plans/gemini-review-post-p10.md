# Gemini Architecture Review — Post P-10

**Date:** 2026-04-05
**Model:** gemini-3.1-pro-preview (thinking mode)
**Context:** Full architecture review after P-10 explainer layer, web research agent, effort/model upgrades

## Overall Grade: A-

"You have built an absolute powerhouse of a system. Calibrating these final efficiency levers will make it production-ready."

## Pipeline Architecture — Grade: A

**What works:**
- Phase 1.7 (Web Research Agent) is "an architectural masterstroke" — resolves open_questions before synthesis
- Phase 4 (Explainer Agent) perfectly separates institutional vs beginner audience
- Orchestrator Pre-Analysis (deterministic Python cross-signal detection) is how AI architectures should handle logic

**Issues:**
1. Comparison Agent missing from pipeline map (it's a separate pipeline — clarified)
2. Verifier errors don't route to Web Research — should they?

**Directives:**
- Route Verifier "Failed Facts" into Web Research task list (for missing data, not logic errors)
- For factual errors: don't re-run specialist (expensive). Verifier outputs Correction JSON → Python patches the briefing
- Only re-run specialist for logic/reasoning errors

## Model & Effort Assignment — Grade: C+ (cost risk)

**The "Max Effort" Trap:** 7 specialists + synthesis all at effort=max is a cost/latency time-bomb. Extended reasoning burns 10-20K thinking tokens per turn.

**Tiered Effort Strategy (recommended):**
- **MAX:** Synthesis, Financials, Valuation (heavy causal analysis, SOTP, DuPont)
- **HIGH:** Business, Risk, Sector (qualitative reasoning)
- **MEDIUM:** Ownership, Technical (rule-based, reading tables)
- **LOW:** Verifier (pure fact-checking)

## Prompt Engineering & Briefings — Grade: A-

**Issues:**
1. **Shared Preamble Bloat:** Grown from 439 words (P-5 sweet spot) to ~1,200 words. "Globalized local fix" trap — SOTP added because Valuation messed up, but Technical/Ownership don't need SOTP rules.
2. **JSON parsing risk:** Regex on markdown code blocks works but is fragile. Consider Anthropic's native Tool Calling for guaranteed schema compliance.
3. **Missing confidence score:** Briefing JSON should include `confidence_score: int (1-10)` so synthesis can weight signals.

**Preamble Refactor (recommended):**
Keep UNIVERSAL (~400 words):
- No Orphan Numbers, Indian conventions, Honesty, Data Source Caveats, Open Questions, Behavioral Boundaries

Move to VALUATION agent:
- Reverse DCF conclusions, Conglomerate SOTP

Move to RISK agent:
- Precise Risk Language, Supply Chain & Import Dependency

Move to FINANCIAL agent:
- PSU Cash Caveat

## Synthesis Target Prices — New Directive

**Problem:** `bull_target` and `bear_target` are null in schema but Opus always fills them. Risk of hallucinated targets.

**Fix — add to Synthesis prompt:**
> TARGET PRICE DERIVATION RULE:
> 1. Anchor targets to Valuation Agent's fair_value_base/bull/bear
> 2. If adjusting (e.g., +10% moat premium, -15% risk discount), state adjustment and rationale explicitly
> 3. If Valuation failed to provide fair values, set targets to null

## Sector Injection — Grade: A-

**Issues:**
1. **IT should be a full injection** (not lightweight). Need: CC revenue growth, Deal TCV/ACV, LTM attrition, utilization, EBIT margin bands, subcontracting costs, onsite/offshore mix, client concentration, vertical exposure (BFSI/Retail/Comm)
2. **NBFC sub-injections needed:**
   - Gold Loan (Muthoot, Manappuram): Tonnage AUM, LTV (75% cap), yield vs cost of funds, auction rates, gold price sensitivity
   - Microfinance (CreditAccess, Fusion): GLP, PAR-30/PAR-90, collection efficiency, credit cost, geographic concentration risk, exogenous shocks (floods, elections, farm loan waivers)

## Pre-Fetch Refactor — Still Critical (even more so with effort=max)

**The math:** If 10 of 30 turns are just fetching basic data, you're paying effort=max token tax on data gathering. Pre-fetch eliminates this.

**CORE (Pre-fetch into `<company_baseline>` XML tags):**
- Profile: Name, Sector, Industry, Market Cap, LTM Revenue/PAT
- Snapshot: Current PE, PB, EV/EBITDA, 52-week range, price
- Basic Ownership: Promoter/FII/DII/Public %
- Peers: Top 3 competitors (name + ticker)

**EXPLORE (Leave in tools):**
- 10Y historical financials, 5Y PE bands
- Concall extraction, management guidance
- DCF inputs, SOTP segment data, DuPont breakdowns
- Charts

**Key insight:** Anthropic's Prompt Caching makes this near-free. Cached 25K tokens cost 90% less and process instantly.

## Unresolved from P-4/P-5

| Item | Status | Priority |
|------|--------|----------|
| Data Freshness (as_of timestamps) | NOT DONE | Critical — add as_of_date to every tool return |
| SectorProfileInjector generalization | DONE (11 full injections) | Complete |
| Human Feedback Loop | NOT DONE | Defer to Phase 6 (Beta) |
| NarrativeAgent | PARTIALLY (Explainer fills gap) | Sufficient for now |
| Pre-Fetch Refactor | NOT DONE | High — even more critical with effort=max |

## Action Items (Prioritized)

### P-11: Efficiency & Cost Optimization
1. **Tiered effort** — MAX for synthesis/financials/valuation, HIGH for business/risk/sector, MEDIUM for ownership/technical
2. **Pre-fetch refactor** — Core tear-sheet in `<company_baseline>` XML tags, tools for deep/historical data only
3. **Preamble refactor** — Strip to 400 words universal, move domain rules to specialist prompts
4. **Data freshness** — Add as_of_date/financial_period to all tool returns

### P-12: Analytical Gaps
5. **IT full injection** — CC growth, TCV, attrition, utilization, client concentration
6. **NBFC sub-injections** — Gold loan (tonnage, LTV, auctions) + Microfinance (GLP, PAR, collection efficiency)
7. **Synthesis target anchoring** — Formalize bull/bear target derivation from valuation agent outputs
8. **Verifier optimization** — Patch briefings for factual errors instead of full re-run
