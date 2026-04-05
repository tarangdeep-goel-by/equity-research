# P-11: Pipeline Efficiency & Quality Upgrade (A- to A+)

## Context

Gemini architecture review (post P-10) graded the multi-agent research pipeline A-. Six issues block A+: effort=max everywhere is a cost bomb, the shared preamble has 3x'd past its sweet spot, agents waste expensive thinking tokens fetching baseline data, freshness metadata is incomplete, synthesis target prices lack formal anchoring, and sector coverage has gaps. This plan resolves all six plus optimizes verification.

## Package 1: Effort Tiering + CLI Override [S]

**Files:** `agent.py`, `research_commands.py`

### 1A. Update DEFAULT_EFFORT (agent.py:63-74)
```python
DEFAULT_EFFORT = {
    "financials": "max",    # DuPont, capital allocation — heavy causal analysis
    "valuation": "max",     # SOTP, reverse DCF, fair value triangle
    "synthesis": "max",     # Cross-referencing 7 briefings
    "business": "high",     # Moat analysis, qualitative reasoning
    "risk": "high",         # Governance + forensic checks
    "sector": "high",       # TAM, positioning
    "ownership": "medium",  # Table reading, SEBI rules
    "technical": "medium",  # RSI/SMA — mechanical
    "web_research": "high",
    "explainer": "high",
}
```

### 1B. Add --effort flag to CLI (research_commands.py)
- `thesis()` line 186: add `effort: Annotated[str | None, typer.Option("--effort")] = None`
- `run_agent()` line 708: same
- `compare()` line 666: same
- Pass through to `run_all_agents()`, `run_single_agent()`, `run_synthesis_agent()`

### 1C. Thread effort through agent functions (agent.py)
- `run_all_agents()` line 613: add `effort` param, pass to `_run_specialist()` at line 635
- `run_single_agent()` line 503: add `effort` param
- `run_synthesis_agent()` line 788: add `effort` param
- `_run_specialist()` already handles `effort = effort or DEFAULT_EFFORT.get(name)` at line 292

---

## Package 2: Preamble Refactor [M]

**File:** `prompts.py`

### 2A. Strip universal preamble to ~400 words (lines 3-81)

**Keep** (universally applicable):
- No Orphan Numbers (lines 9-10)
- Charts & Tables (lines 12-13)
- Indian Conventions (lines 15-18)
- Data Source Caveats (lines 20-22)
- Honesty (lines 24-25)
- Explain WHY not WHAT (lines 27-28, first paragraph only)
- Investor's Checklist Clarity (line 36)
- Behavioral Boundaries (lines 52-61)
- Source Citations (lines 63-64)
- Open Questions (lines 66-75)
- Fallback Strategies (lines 77-80)

**Remove** from preamble (relocate):
- Reverse DCF Conclusions (lines 29-32)
- Conglomerate SOTP (lines 33-35)
- PSU Cash Caveat (lines 38-40)
- Precise Risk Language (lines 42-47)
- Supply Chain & Import Dependency (lines 48-50)

### 2B. Relocate domain rules to specialist Key Rules sections

| Rule | Target Agent | Insert After |
|------|-------------|-------------|
| Reverse DCF Conclusions | Valuation | line 333 (Key Rules) |
| Conglomerate SOTP | Valuation | line 333 (merge with existing SOTP rule) |
| PSU Cash Caveat | Financial | line 206 (Key Rules) |
| Precise Risk Language | Risk | line 395 (Key Rules) |
| Supply Chain & Import Dependency | Risk | line 395 (Key Rules) |

---

## Package 3: Pre-Fetch Tear Sheet [M]

**Files:** `agent.py`, `prompts.py`

### 3A. Add `_build_baseline_context(symbol)` function (agent.py, after line 132)

Reads from SQLite only (zero network calls, data already refreshed):
```python
def _build_baseline_context(symbol: str) -> str:
    with ResearchDataAPI() as api:
        info = api.get_company_info(symbol)           # 3 keys
        snap = api.get_valuation_snapshot(symbol)      # subset: price, PE, PB, ROE, D/E, 52wk, mcap
        own = api.get_shareholding(symbol, quarters=4) # 4Q ownership
        est = api.get_consensus_estimate(symbol)       # targets, recommendation
        fv = api.get_fair_value(symbol)                # signal + MoS
        fresh = api.get_data_freshness(symbol)         # last_fetched per table
    # Compress ownership into {promoter: [q1,q2,q3,q4], fii: [...], ...}
    # Return f"<company_baseline>\n{json}\n</company_baseline>"
```

### 3B. Inject into specialist user prompts (agent.py)

- `run_all_agents()` line 622: build `baseline = _build_baseline_context(symbol)` once
- Pass to `_run_with_limit()` inner function → `_run_specialist(user_prompt=f"{baseline}\n\nAnalyze {symbol}...")`
- Do NOT inject into synthesis (already has structured briefings) or web_research (works from questions)

### 3C. Add "Step 0" to all 7 specialist Workflow sections (prompts.py)

Insert before each agent's step 1:
```
0. **Baseline**: Review `<company_baseline>` in the user message — price, valuation, ownership, consensus, freshness. Do NOT re-fetch this data with tools.
```

Locations: business line 93, financial line 160, ownership line 221, valuation line 284, risk line 349, technical line 412, sector line 467

---

## Package 4: Data Freshness + Synthesis Anchoring [S]

**Files:** `tools.py`, `prompts.py`

### 4A. Add `_add_freshness_meta()` to 6 missing tools (tools.py)

Already applied in: get_fundamentals, get_quality_scores, get_ownership, get_valuation, get_estimates

Missing — add same 2-line pattern before return:
1. `get_analytical_profile` (line 936)
2. `get_fair_value_analysis` (line 1227)
3. `get_peer_sector` (line 1273)
4. `get_market_context` (line 1369)
5. `get_company_context` (line 1416)
6. `get_events_actions` (line 1458)

Pattern:
```python
if isinstance(data, dict) and "error" not in data:
    data = _add_freshness_meta(data, api, args["symbol"])
```

### 4B. Synthesis target price anchoring (prompts.py)

Insert between Narrative Primacy (line 607) and Structured Briefing (line 609):

```
## Target Price Derivation
- `bull_target` and `bear_target` MUST anchor to Valuation Agent's `fair_value_bull` and `fair_value_bear`
- If adjusting (e.g., +10% moat premium, -15% governance discount), state adjustment and rationale explicitly
- `bear_target` must not exceed Risk Agent's pre-mortem downside — use the lower of valuation bear and risk bear
- If Valuation Agent failed to provide fair values, derive from analyst consensus target range, or set to null
```

---

## Package 5: Sector Injections [L]

**Files:** `data_api.py`, `prompts.py`

### 5A. IT Services — full injection

**data_api.py:** Add `_IT_INDUSTRIES` set (reuse names from prompts.py:1101), add `_is_it_services()` detector

**prompts.py:**
- Add `_build_it_injection()` builder (~200 words): CC revenue growth, Deal TCV/ACV, LTM attrition, utilization (82-86% optimal), EBIT margin bands, subcontracting cost as demand signal, onsite/offshore mix, client concentration (top 5/10), vertical exposure (BFSI/Retail/Comm), standard PE/DCF valid (20-35x range)
- Add to dispatch table at end of non-financial sectors
- Remove IT from `_build_sector_caveats()` (lines 1116-1126)

### 5B. Gold Loan NBFC — sub-injection

**data_api.py:** Add `_GOLD_LOAN_SYMBOLS = {"MUTHOOTFIN", "MANAPPURAM"}`, add `_is_gold_loan_nbfc()` detector (symbol-based, since industry is generic "NBFC")

**prompts.py:**
- Add `_build_gold_loan_injection()` builder (~150 words): tonnage AUM, LTV (cap 75%), yield vs cost of funds, auction rates (>2% red flag), gold price sensitivity (10% crash scenario), P/B primary valuation, ban standard GNPA logic (gold loans are fully secured)
- Insert into dispatch table BEFORE `_is_bfsi` (cascade priority)

### 5C. Microfinance — sub-injection

**data_api.py:** Add `_MICROFINANCE_INDUSTRIES = {"Microfinance Institutions"}`, add `_is_microfinance()` detector (industry-based, already a distinct industry name)

**prompts.py:**
- Add `_build_microfinance_injection()` builder (~150 words): GLP, PAR-30/PAR-90, collection efficiency %, credit cost %, geographic concentration (>20% one state = major risk), exogenous shocks (floods, elections, farm loan waivers), P/B primary, ROA/ROE expansion from credit cost normalization
- Insert into dispatch table BEFORE `_is_bfsi`, AFTER gold loan

### 5D. Final dispatch table order (14 entries)

```
insurance > gold_loan_nbfc > microfinance > bfsi > broker > amc > exchange >
realestate > metals > regulated_power > merchant_power > telecom > telecom_infra > it_services
```

---

## Package 6: Verifier Optimization [M]

**File:** `agent.py`

### 6A. Tiered correction handling (lines 741-769)

Replace monolithic re-run with:

1. **Factual errors** (verifier found wrong numbers): Patch report directly — append "## Corrections Applied" section. No re-run. Cost: $0.

2. **Logic errors** (wrong reasoning/conclusions): Re-run specialist with correction context (existing behavior). Cost: full agent re-run.

3. **Missing data** (verifier flagged data gaps): Collect into list, inject as additional questions for web research agent.

Decision logic: if ALL issues in the verification result are factual (contain numeric claim vs actual), patch. If ANY issue is logic/reasoning, re-run. Missing data issues always route to web research.

### 6B. Helper functions (after line 770)

- `_classify_issues(issues: list[dict]) -> tuple[list, list, list]` — returns (factual, logic, missing_data)
- `_patch_factual_errors(envelope, factual_issues) -> BriefingEnvelope` — appends corrections section

### 6C. Wire missing data to web research (lines 771-783)

Before web research runs, append verification-sourced missing-data issues to the question pool. The existing `run_web_research_agent()` builds `question_lines` from briefing `open_questions` — add these alongside.

---

## Parallelization

All 6 packages are independent — zero cross-dependencies:
```
Package 1 (Effort)     ─┐
Package 2 (Preamble)   ─┤
Package 3 (Tear Sheet) ─┼─ All in parallel
Package 4 (Freshness)  ─┤
Package 5 (Sectors)    ─┤
Package 6 (Verifier)   ─┘
```

Merge note: Packages 1+3 both touch `run_all_agents()` signature. Packages 2+4+5 all touch `prompts.py` in different sections. Trivial merge conflicts.

## Verification

After implementation:
1. `uv run flowtrack research thesis -s INDIAMART --technical` — full pipeline, verify effort tiers in logs
2. `uv run flowtrack research thesis -s SBIN --effort high` — CLI override works
3. `uv run flowtrack research data analytical_profile -s RELIANCE --raw | grep _meta` — freshness meta present
4. `uv run flowtrack research run business -s MUTHOOTFIN` — gold loan injection fires (check report for tonnage/LTV language)
5. `uv run flowtrack research run sector -s TCS` — IT full injection fires (check for CC growth, TCV)
6. Inspect generated report for `<company_baseline>` not appearing in final output (consumed by agent, not rendered)
7. Check synthesis verdict targets reference valuation agent's fair_value_base/bull/bear

## Estimated Impact

| Metric | Before | After |
|--------|--------|-------|
| Cost per thesis | ~$4-6 (all max) | ~$2.50-3.50 (tiered) |
| Preamble tokens/agent | ~1600 tokens | ~600 universal + ~200 specialist |
| Agent first-turn data fetches | 10+ tool calls | 2-3 (baseline pre-injected) |
| Sector coverage (full) | 11 | 14 (added IT, gold loan, MFI) |
| Verification re-run cost (factual) | $0.30-0.75 | $0 (direct patch) |
| Tools with freshness meta | 5/11 | 11/11 |
