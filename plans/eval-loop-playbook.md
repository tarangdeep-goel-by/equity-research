# Agent Eval Loop Playbook

Iterative improvement loop for specialist research agents. Run agent, grade with Gemini, fix, repeat until A/A-.

## Setup

### Gemini Grading Session
```
model: gemini-3.1-pro-preview
thinking: true
thinking_budget: 32000
system_instruction: "You are a senior equity research analyst with 20 years
  covering Indian [sector] companies. Review AI-generated research reports for:
  (1) factual accuracy of claims and numbers,
  (2) analytical depth — does it go beyond surface-level?,
  (3) missing analysis — what should have been covered but wasn't?,
  (4) contradictions or logical gaps.
  Be thorough and specific — cite exact passages. Grade A-F."
```

Tailor the system instruction per agent (ownership → institutional flows, business → moat/unit economics, valuation → DCF/PE band, etc.).

**Critical:** Add this to every system instruction:
> "Do NOT grade the accuracy of specific numbers (revenue, margins, shareholding percentages, stock prices). Your training data is outdated — the report uses live data that is more current than yours. Focus on analytical depth, logical consistency, completeness of coverage, and whether the right frameworks are applied. If a number looks wrong to you, flag it as 'worth verifying' rather than marking it incorrect."

## The Loop

```
For each benchmark stock:
  cycle = 0
  while cycle < 3:
    1. Run agent:
       uv run flowtrack research run <agent> -s <SYMBOL>

    2. Read report:
       ~/vault/stocks/<SYMBOL>/reports/<agent>.md

    3. Send to Gemini with context:
       - Stock description (sector, market cap, type)
       - What data the agent had access to
       - What data gaps existed
       - "Grade A-F. Be specific — cite exact passages."

    4. If grade >= A- → PASS, move to next agent/stock

    5. Classify Gemini's feedback:
       a. PROMPT FIX — agent behavior/reasoning issue
          → Edit prompts.py (Key Rules, Workflow, Report Sections)
       b. DATA FIX — missing/broken data pipeline
          → Fix store.py, data_api.py, tools.py, or client
       c. COMPUTATION — math the LLM shouldn't do
          → Move to data_api.py, serve pre-computed
       d. NOT OUR PROBLEM — LLM consistency, hallucination
          → Note it, move on

    6. Apply fixes, cycle++

  If cycle == 3 and still < A- → flag for manual review
```

## Prompt Edit Surface

| File | What to change |
|------|---------------|
| `prompts.py` Key Rules | Add behavioral constraints, regulatory rules |
| `prompts.py` Workflow | Specify exact tool calls + sections |
| `prompts.py` Report Sections | Add/modify output sections |
| `prompts.py` Structured Briefing | Add JSON fields (e.g., `open_questions`) |
| `tools.py` AGENT_TOOLS_V2 | Add/remove tools from agent's registry |
| `agent.py` AGENT_MAX_TURNS/BUDGET | Tune iteration/cost limits |

## Data Edit Surface

| File | What to change |
|------|---------------|
| `store.py` | Query defaults (days, limits), symbol resolution |
| `data_api.py` | Enrich responses with computed fields, change defaults |
| `tools.py` | Tool call routing, default parameters |
| `*_client.py` | Parser fixes, API field name changes |

## Key Principles

1. **Don't ask the LLM to do math** — if it's a formula (margin call, CAGR, margin of safety), compute it in `data_api.py` and hand the number to the agent.

2. **Don't ask the LLM to speculate** — if the agent can't verify something from its tools, it should pose an Open Question, not assert a cause.

3. **Separate what Gemini says into buckets** — some feedback is about the prompt (fixable), some is about missing data (pipeline fix), some is about LLM consistency (hard to fix, note and move on).

4. **Challenge Gemini's feedback** — not everything Gemini suggests is correct or actionable. Ask "can the agent actually do this with the tools it has?" before adding rules.

5. **Fewer rules > more rules** — each rule competes for attention in the prompt. Only add rules that address real, documented failures.

## Benchmark Stock Selection

Pick stocks that stress-test the agent's edge cases:
- **Ownership:** High pledge (ADANIENT), MF accumulation (JIOFIN), FII exit pattern, promoter near 75% cap
- **Business:** Platform (INDIAMART), conglomerate (ADANIENT), BFSI (SBIN), cyclical
- **Valuation:** Deep value, expensive growth, holding company discount
- **Risk:** Governance red flags, high debt, related party

## Completed Evals

| Agent | Stock | Cycles | Grade | Date |
|-------|-------|--------|-------|------|
| business | INDIAMART | ongoing | A- | 2026-04-03 |
| ownership | ADANIENT | 2 | A- | 2026-04-03 |
| valuation | HDFCBANK | 2 | A | 2026-04-03 |
| valuation | INDIAMART | 1 | A- | 2026-04-03 |
| financials | VEDL | 1 | A- | 2026-04-04 |
| financials | SBIN | 1 | A- | 2026-04-04 |
