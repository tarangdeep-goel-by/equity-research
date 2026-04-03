# P-5: Agent Intelligence & Robustness

## Context

Gemini reviewed P-4's architecture (April 2026) and upgraded the verdict from "Ferrari engine, confusing steering wheel" to "purpose-built race car." P-4 solved tool overload (71→16) and prompt bloat (36K→7K words). P-5 addresses the remaining issues: verification logic, synthesis quality, tool efficiency, graceful degradation, and analytical coverage gaps.

**Goals:** Narrative-first synthesis, fact-check-only verifier, multi-section tool calls, graceful agent failure handling, market-cap-aware personas, comparison prompt V2.

---

## Item 1: Synthesis Prompt — Narrative-First Verdict

**Problem:** Verdict Calibration section is too deterministic ("Strong BUY >80%"). Synthesis agent treats composite_score as a formula rather than one input. Orchestrator pre-analysis (`_analyze_briefing_signals`) presents cross-signals as facts, creating a "split brain" with the synthesis agent's own detection.

**Changes:**

### prompts.py — SYNTHESIS_AGENT_PROMPT_V2

1. **Soften Verdict Calibration** (lines 523-528). Replace rigid thresholds with guidelines:
   ```
   ## Verdict Calibration (Guidelines, Not Rules)
   - These are starting points, not formulas. Your verdict must be a defensible thesis grounded in cross-signal analysis.
   - Strong BUY: Multiple independent signals converge — undervaluation + quality + institutional accumulation + manageable risks. Confidence >80% only when data quality is high and 5+ agents agree.
   - BUY: Positive risk/reward with confirming ownership signals. Some risks present but quantified and manageable.
   - HOLD: Mixed signals, fair value, or insufficient data to form high-conviction view.
   - SELL: Deteriorating fundamentals confirmed by institutional exit and elevated risks.
   - If qualitative evidence from the briefings contradicts the composite score, you MUST highlight the discrepancy and base your verdict on the qualitative evidence, explaining why you override the score.
   ```

2. **Add Narrative Primacy rule** after Risk-Adjusted Conviction (line 532):
   ```
   ## Narrative Primacy
   Your primary role is to synthesize the NARRATIVES from specialist briefings, not to aggregate scores. The composite score and fair value are inputs — they inform but do not determine your verdict. A company with a score of 45/100 but with a transformational catalyst and accelerating institutional accumulation may warrant a BUY. A company scoring 80/100 but facing an existential regulatory threat should cap at HOLD. Build your thesis from the stories the specialists tell, not from the numbers alone.
   ```

### agent.py — `_analyze_briefing_signals()`

3. **Reframe output as suggestions** (line 482-567). Change the function's output framing:
   - Current: `"**Agent agreement:** 6 agents responded. Majority signal: bullish (5/6 = 83%)"`
   - New: `"**Suggested signal (orchestrator analysis):** 6 agents responded. Majority signal appears bullish (5/6 = 83%). Please validate — do the underlying briefing details support this?"`
   - Current: `"**Cross-signals detected (investigate these):**"`
   - New: `"**Potential cross-signals (orchestrator suggestions — validate against briefing data):**"`
   - Current: `"**Contradictions to resolve:** business says bullish vs majority bearish. WHY do these agents disagree? Your synthesis must address this."`
   - New: `"**Potential contradiction:** business says bullish vs majority bearish. Investigate whether these reflect genuinely conflicting evidence or different timeframes/scopes."`

### agent.py — `run_synthesis_agent()`

4. **Update user prompt framing** (around line 728). Change:
   ```python
   "Use the pre-analysis to guide your cross-referencing. Resolve contradictions, ..."
   ```
   To:
   ```python
   "The orchestrator has flagged potential signals below — treat these as suggestions to investigate, not conclusions. You may find additional signals or disagree with the orchestrator's assessment. Your independent analysis takes precedence."
   ```

**Verify:** Run a thesis for INDIAMART or SBIN. Check that the synthesis report (a) builds a narrative thesis, (b) doesn't mechanically map score to verdict, (c) addresses orchestrator suggestions but can override them.

---

## Item 2: Verifier Re-scope to Fact-Checking

**Problem:** Haiku verifying Sonnet is backwards for logic/quality. But Haiku CAN verify factual consistency (does report X match tool output Y?). Current verifier tries to do both — check accuracy AND judge interpretation.

**Changes:**

### verifier.py — VERIFICATION_PROMPT

Replace the entire prompt (lines 52-106) with a stripped-down fact-checking prompt:

```python
VERIFICATION_PROMPT = """You are a fact-checking agent. Your ONLY job is to verify that numbers and claims in a research report match the raw data from tool calls.

You receive:
1. A specialist research report (markdown)
2. An evidence log showing every tool call the specialist made and its result

## Your Task

Check 5-8 key numerical claims in the report against the evidence log:
- Revenue/profit figures — do they match the tool output?
- Growth rates and CAGRs — are the calculations correct?
- Sector rankings and percentile claims — do they match benchmarks data?
- Valuation multiples (PE, PB, EV/EBITDA) — do they match the snapshot?

## What You Are NOT Doing
- You are NOT judging writing quality, insight depth, or analytical reasoning
- You are NOT checking whether conclusions are "correct" — that's the Synthesis agent's job
- You are NOT re-analyzing the company — just checking numbers

## Rules
- If the evidence log doesn't contain data for a claim, mark it as "unverifiable" — NOT as an error
- Rounding differences (±2%) are acceptable — mark as "note" not "error"
- If report says "~25%" and data shows 24.7%, that's a pass
- Focus on material errors: wrong order of magnitude, wrong direction, wrong company
- 8 turns max

## Output
End with a JSON code block:
```json
{
    "agent_verified": "<agent_name>",
    "symbol": "<SYMBOL>",
    "verdict": "<pass|pass_with_notes|fail>",
    "spot_checks_performed": <number>,
    "issues": [
        {
            "severity": "<error|warning|note>",
            "claim": "<what the report says>",
            "actual": "<what the evidence shows>",
            "evidence_tool": "<which tool call to check>"
        }
    ],
    "corrections": ["<specific correction if needed>"],
    "overall_data_quality": "<summary>"
}
```

- **pass**: All checked claims match evidence (±2% rounding OK)
- **pass_with_notes**: Minor discrepancies flagged but no material errors
- **fail**: Material errors found — wrong numbers, fabricated claims, or contradictions with evidence
"""
```

**Also update:** Reduce `max_turns` from 10 to 8, keep `max_budget_usd=0.20`.

**Verify:** Run `flowtrack research verify -s SBIN -a financials`. Check that verifier only checks numbers, doesn't critique reasoning.

---

## Item 3: Multi-Section Tool Calls

**Problem:** Agent needs quarterly_results + annual_financials from get_fundamentals — currently 2 separate tool calls. With 10 macro-tools × ~3 calls each, that's 30 turns just for data fetching.

**Changes:**

### tools.py — All 10 macro-tool functions

For each macro-tool, change the section parameter handling:

```python
# Before:
section = args.get("section", "all")

# After:
section = args.get("section", "all")
if isinstance(section, list):
    # Multi-section: return dict of requested sections
    data = {}
    for s in section:
        # ... call individual section handler, add to data dict
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
```

**Implementation pattern** for each macro-tool (using get_fundamentals as example):

```python
async def get_fundamentals(args):
    symbol = args["symbol"]
    section = args.get("section", "all")
    with ResearchDataAPI() as api:
        # Handle list of sections
        if isinstance(section, list):
            data = {}
            for s in section:
                data[s] = _get_fundamentals_section(api, symbol, s, args)
            return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
        # Handle single section (string)
        if section == "all":
            data = { ... }  # existing "all" logic
        else:
            data = _get_fundamentals_section(api, symbol, section, args)
    return {"content": [{"type": "text", "text": json.dumps(data, default=str)}]}
```

Extract a helper `_get_fundamentals_section(api, symbol, section, args)` for each macro-tool to avoid duplicating the if/elif chain.

**Also update tool descriptions** to mention list support:
```
"section: 'quarterly_results' | 'annual_financials' | ... | 'all' | ['section1', 'section2']"
```

### prompts.py — All agent workflow sections

Update each agent's Workflow step to encourage batching. Example for Financial agent:
```
2. **Core financials**: Call `get_fundamentals` with section=['quarterly_results', 'annual_financials', 'ratios', 'expense_breakdown', 'growth_rates'] to get all financial data in one call.
```

**Verify:** Test via `get_fundamentals.handler({"symbol": "SBIN", "section": ["quarterly_results", "annual_financials"]})`. Assert returns dict with both keys.

---

## Item 4: Graceful Degradation for Failed Agents

**Problem:** If an agent fails after retry, `run_all_agents` prints a warning and excludes it from envelopes. The synthesis agent receives fewer briefings but doesn't know WHY or WHICH agents failed. No explicit status tracking.

**Changes:**

### briefing.py — BriefingEnvelope

Add a `status` field:
```python
class BriefingEnvelope(BaseModel, extra="ignore"):
    agent: str
    symbol: str
    generated_at: str = ...
    status: str = "success"  # "success" | "failed" | "empty"
    failure_reason: str = ""  # populated when status != "success"
    report: str = ""
    briefing: dict = Field(default_factory=dict)
    evidence: list[ToolEvidence] = Field(default_factory=list)
    cost: AgentCost = Field(default_factory=AgentCost)
```

### agent.py — run_all_agents()

When an agent fails or returns empty, create a failed envelope instead of skipping:

```python
# Current (line 638):
if isinstance(result, Exception):
    print(f"  ⚠ {name} agent failed: {result}")
    continue
envelopes[name] = result

# New:
if isinstance(result, Exception):
    print(f"  ⚠ {name} agent failed: {result}")
    envelopes[name] = BriefingEnvelope(
        agent=name, symbol=symbol,
        status="failed", failure_reason=str(result),
    )
elif not result.report or len(result.report.strip()) < 100:
    envelopes[name] = BriefingEnvelope(
        agent=name, symbol=symbol,
        status="empty", failure_reason="Agent produced no substantive output",
    )
else:
    envelopes[name] = result
```

### agent.py — run_synthesis_agent()

Pass failure info to synthesis. In the user_prompt construction (around line 728), after building briefing_text, add:

```python
failed_agents = [name for name, env in envelopes.items() if env.status != "success"]
if failed_agents:
    briefing_text += f"\n\n### FAILED AGENTS\nThe following agents failed to produce reports: {', '.join(failed_agents)}. "
    briefing_text += "Your analysis is incomplete — lower your confidence accordingly and note which dimensions are missing.\n"
```

Wait — `run_synthesis_agent` loads briefings from vault via `load_all_briefings`, not from the envelopes dict. We need to either:
- (a) Save failed envelopes to vault too, or
- (b) Pass the failed agent list separately

Option (b) is simpler. Add a `failed_agents` parameter to `run_synthesis_agent`:

```python
async def run_synthesis_agent(
    symbol: str,
    model: str | None = None,
    failed_agents: list[str] | None = None,
) -> BriefingEnvelope:
```

And in the caller (run_all_agents isn't the caller — it's the CLI / assembly that calls run_synthesis_agent after run_all_agents). Check the flow:

In `research_commands.py`, the thesis command calls `run_all_agents` then `run_synthesis_agent` separately. So the failed_agents info needs to flow through.

Actually, looking at `run_all_agents` — it doesn't call synthesis. Synthesis is called separately. So we need to:
1. Have `run_all_agents` return the full envelopes dict (including failed ones)
2. The CLI/assembly extracts `failed_agents` from the dict
3. Pass `failed_agents` to `run_synthesis_agent`

### prompts.py — SYNTHESIS_AGENT_PROMPT_V2

Already has Data Quality Check section. Add explicit rule:
```
- If any specialist agent failed, explicitly state: "The [X] analysis could not be completed." Cap confidence at 60% if 1 agent failed, 40% if 2+ failed.
```

**Verify:** Mock a failed agent (e.g., set technical to always fail), run thesis. Check synthesis mentions the gap.

---

## Item 5: Market-Cap Persona Injection

**Problem:** Analyst treats a ₹500 Cr small-cap the same as a ₹5L Cr mega-cap. Risk profile, liquidity, governance scrutiny, and valuation methodology should differ.

**Changes:**

### prompts.py — build_specialist_prompt()

Add market-cap tier detection alongside BFSI:

```python
def build_specialist_prompt(agent_name: str, symbol: str) -> str:
    from flowtracker.research.data_api import ResearchDataAPI

    prompt = AGENT_PROMPTS_V2.get(agent_name, "")
    if not prompt:
        return prompt

    with ResearchDataAPI() as api:
        is_bfsi = api._is_bfsi(symbol)
        mcap = api.get_valuation_snapshot(symbol).get("market_cap_cr", 0) or 0

    if is_bfsi and agent_name in {"financials", "valuation", "risk", "ownership", "sector"}:
        prompt += _build_bfsi_injection()

    if mcap > 0:
        prompt += _build_mcap_injection(mcap, agent_name)

    return prompt
```

### prompts.py — _build_mcap_injection()

```python
_MCAP_TIERS = [
    (100_000, "mega_cap"),   # > 1L Cr
    (20_000, "large_cap"),   # 20K-1L Cr
    (5_000, "mid_cap"),      # 5K-20K Cr
    (0, "small_cap"),        # < 5K Cr
]

def _build_mcap_injection(mcap_cr: float, agent_name: str) -> str:
    tier = "small_cap"
    for threshold, label in _MCAP_TIERS:
        if mcap_cr >= threshold:
            tier = label
            break

    if tier == "small_cap":
        injections = {
            "risk": "\n\n## Small-Cap Risk Alert\nThis is a small-cap company (market cap < ₹5,000 Cr). Apply extra scrutiny to: cash flow quality (small-caps often show paper profits), promoter governance (pledge, related party transactions), liquidity risk (thin trading volume amplifies drawdowns), and regulatory compliance. Small-caps blow up faster and with less warning.",
            "valuation": "\n\n## Small-Cap Valuation Context\nSmall-caps deserve lower valuation multiples than large-caps due to higher risk, lower liquidity, and less analyst coverage. Apply a liquidity discount. Use historical own-PE band rather than sector median (sector median is dominated by large-caps).",
            "ownership": "\n\n## Small-Cap Ownership Context\nFII/DII data may be sparse for small-caps. Focus on promoter behavior (buying/selling/pledging) and delivery % as primary signals. MF entry into a small-cap is a stronger signal than for large-caps (higher conviction required for illiquid names).",
        }
        return injections.get(agent_name, "")

    if tier == "mega_cap":
        injections = {
            "valuation": "\n\n## Mega-Cap Valuation Context\nThis is a mega-cap (> ₹1L Cr). Mega-caps trade at structural premiums due to liquidity, index inclusion, and institutional mandates. Compare valuation against own 10Y history and global peers, not just sector median. Small deviations from historical band are more meaningful than for mid-caps.",
        }
        return injections.get(agent_name, "")

    return ""  # mid-cap and large-cap get no injection (standard framework works)
```

**Verify:** `build_specialist_prompt("risk", "SOME_SMALLCAP")` should contain "Small-Cap Risk Alert". `build_specialist_prompt("risk", "RELIANCE")` should not.

---

## Item 6: Comparison Agent V2 Prompt

**Problem:** Comparison prompt body is 2,471 words — verbose, with full table examples and first-mention definitions that duplicate the shared preamble. Still has V1-style tool-by-tool instructions referencing old individual tools.

**Changes:**

### prompts.py — COMPARISON_AGENT_PROMPT

Rewrite body from ~2,471 words to ~800 words following V2 structure:
- Persona (2-3 sentences) — keep existing
- Mission (2 sentences) — keep existing
- Workflow (5-6 numbered steps with macro-tool calls):
  1. Call `get_fair_value_analysis` + `get_composite_score` for each stock
  2. Call `get_valuation` for each stock
  3. Call `get_peer_sector` for sector context
  4. Call `get_fundamentals` for growth trajectories
  5. Call `get_ownership` for ownership changes
  6. Call `render_chart` for comparison charts
- Report Sections (names + 1-liner):
  1. Quick Verdict Table
  2. Business Quality Comparison
  3. Financial Comparison
  4. Valuation Comparison
  5. Ownership & Conviction
  6. Risk Comparison
  7. The Verdict: If You Can Only Buy One
- Structured Briefing JSON (keep existing template)
- Key Rules (4-5 one-liners): side-by-side always, definitive verdict, pick winners per dimension, teach through comparison

**Remove:** Full table examples (Quick Verdict, Financial, Valuation, Ownership, Risk tables with HDFCBANK/ICICIBANK data). Remove first-mention definitions (already in preamble). Remove tool-by-tool descriptions (tools are self-describing).

**Verify:** Word count check — body should be ~800 words (total with preamble ~1,240).

---

## Implementation Batches

### Batch 1: Synthesis + Verifier (no tool changes)
- Item 1: Synthesis prompt narrative-first + orchestrator reframing
- Item 2: Verifier re-scope to fact-checking
- Test: Run full thesis for SBIN. Compare synthesis quality and verifier behavior.

### Batch 2: Multi-section tool calls (tools.py + prompts.py)
- Item 3: All 10 macro-tools accept list sections
- Update agent workflow prompts to encourage batching
- Test: Integration tests for list-section calls + full thesis run.

### Batch 3: Robustness + Intelligence (parallel)
- Item 4: Graceful degradation (briefing.py + agent.py + prompts.py)
- Item 5: Market-cap persona injection (prompts.py)
- Item 6: Comparison agent V2 prompt (prompts.py)
- Test: Mock failed agent, verify synthesis handles it. Test small-cap persona. Comparison word count check.

---

## Files Modified

| File | Changes |
|------|---------|
| `research/prompts.py` | Synthesis prompt rewrite, mcap injection, comparison V2 |
| `research/agent.py` | Orchestrator signal reframing, failed agent handling, synthesis failed_agents param |
| `research/verifier.py` | Complete prompt rewrite to fact-checking only |
| `research/tools.py` | All 10 macro-tools accept list sections, extract section helpers |
| `research/briefing.py` | BriefingEnvelope.status + failure_reason fields |

---

## Verification

1. **Synthesis quality:** A/B compare thesis for same stock — V2 synthesis should produce a narrative thesis, not a score-to-verdict mapping
2. **Verifier scope:** Run verification — should only flag number mismatches, not critique reasoning
3. **Multi-section:** `get_fundamentals(section=["quarterly_results", "ratios"])` returns dict with both keys
4. **Graceful degradation:** Kill one agent, run thesis — synthesis should mention the gap and lower confidence
5. **Market-cap:** Small-cap gets Risk "Small-Cap Alert" injection, mega-cap gets Valuation context
6. **Comparison V2:** Word count ~1,240 total, still produces correct comparison output
8. **Full pipeline:** End-to-end thesis for INDIAMART — all 7 specialists + verify + synthesis + HTML
9. **Tests pass:** 1069+ tests pass
