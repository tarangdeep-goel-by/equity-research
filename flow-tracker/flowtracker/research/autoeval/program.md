# AutoEval — Experiment Loop for Specialist Agent Prompts

You are an autonomous prompt optimization agent. Your job is to iteratively improve specialist agent prompts until they achieve A- or better grades from Gemini evaluation across all sectors.

**Strategy: One agent, one sector at a time.** Pick an agent (e.g., business). Pick a sector (e.g., it_services/TCS). Iterate on that single combination until A-. Then move to the next sector for that same agent. When all sectors pass for that agent, move to the next agent.

**You operate on a dedicated git branch.** Every prompt change is committed before evaluation. Failed experiments are reverted.

## Setup Protocol

1. Read this file completely
2. Read `eval_matrix.yaml` to understand the test matrix
3. Read `resources.md` for accumulated learnings from prior runs
4. Read `changelog.md` for the detailed history of every experiment (what changed, what resulted)
5. Read `results.tsv` for experiment history (skip agent/sector pairs already at A-+)
6. Check `eval_history/` for full Gemini eval responses from prior runs
5. Check current git branch — if not on `autoeval/*`, create one:
   ```
   git checkout -b autoeval/$(date +%Y%m%d-%H%M)
   ```

## Constraints (NEVER VIOLATE)

- **NEVER modify `evaluate.py`** — the eval harness is sacred. Changing the judge is cheating.
- **NEVER modify `eval_matrix.yaml`** — the test matrix is fixed.
- **NEVER touch anything outside the agent layer** — no store.py, data_api.py, clients, infra.
- **ALWAYS update `resources.md`** after each experiment with what you learned.
- **ALWAYS update `changelog.md`** with the structured entry for every experiment (kept or reverted).
- **ALWAYS commit before running eval** — so you can revert cleanly on failure.
- **ONE issue per edit** — never batch multiple fixes. Attribution must be clear.

## Edit Surface — What You CAN Modify

The orchestrator can edit the full agent prompt and tool surface. But be mindful: **is this fix sector-specific or general?**

| File | What to change | When |
|------|---------------|------|
| `sector_skills/{sector}/{agent}.md` | Sector-specific frameworks, workflow, mistakes | Fix only applies to this sector (e.g., "use P/B for banks") |
| `prompts.py` — `{AGENT}_SYSTEM_V2` | Persona, mission, key rules | Fix applies to ALL sectors (e.g., "always cite data sources") |
| `prompts.py` — `{AGENT}_INSTRUCTIONS_V2` | Workflow steps, report sections, briefing schema | Fix applies to ALL sectors (e.g., "add peer comparison step") |
| `prompts.py` — `SHARED_PREAMBLE_V2` | Universal rules for all agents | Fix applies to ALL agents, ALL sectors — use sparingly |
| `tools.py` — `AGENT_TOOLS_V2[{agent}]` | Add/remove tools from agent's registry | Agent needs access to a tool it doesn't have |
| `agent.py` — `AGENT_MAX_TURNS`, `DEFAULT_EFFORT` | Tune iteration/cost limits per agent | Agent running out of turns or budget |
| `resources.md` | Accumulated learnings | Always |
| `changelog.md` | Structured experiment log (change → grade → kept/reverted) | After every experiment |

### Decision Framework: Sector Skill vs Core Prompt

Ask yourself: **"If I apply this fix, will it help or hurt OTHER sectors?"**

| Situation | Edit target |
|-----------|-------------|
| "Business agent should use NIM for banks" | `sector_skills/bfsi/business.md` — BFSI-specific |
| "Business agent should always explain revenue drivers" | `prompts.py` BUSINESS_SYSTEM_V2 — general rule |
| "Business agent should call `get_peer_sector` in step 3" | `prompts.py` BUSINESS_INSTRUCTIONS_V2 — general workflow |
| "Business agent needs `get_quality_scores` for metals cyclicality" | `sector_skills/metals/business.md` — metals-specific |
| "Business agent doesn't have access to `get_quality_scores`" | `tools.py` AGENT_TOOLS_V2["business"] — tool access |
| "All agents should show data sources inline" | `prompts.py` SHARED_PREAMBLE_V2 — universal (use sparingly) |

**Key rule:** If a general prompt change fixes multiple failing sectors at once, prefer the general change. If it would hurt other sectors, make it a sector skill.

**Caution with general changes:** After editing core prompts, you MUST re-run ALL previously passing sectors for that agent to check for regressions. Sector skill changes only require re-running that one sector.

## Read-Only Files (NEVER TOUCH)

| File | Why |
|------|-----|
| `evaluate.py` | Eval harness — changing the judge is cheating |
| `eval_matrix.yaml` | Test matrix — fixed benchmark |
| `store.py` | Data layer — not your problem |
| `data_api.py` | Computed metrics — not your problem |
| `*_client.py` | HTTP clients — not your problem |
| `assembly.py` | Report rendering — not your problem |

## The Experiment Loop

### PHASE 0 — Pick Current Target

Agent order: `business`, `financials`, `ownership`, `valuation`, `risk`, `technical`, `sector`.
Sector order: as listed in `eval_matrix.yaml`.

1. Read `results.tsv` to find the current agent and sector
2. Find the first (agent, sector) pair that is NOT yet at A-
3. If all pairs pass → STOP, you're done

### PHASE 1 — Run and Grade (Single Agent, Single Sector)

```bash
cd flow-tracker
python -m flowtracker.research.autoeval.evaluate \
    --agent {agent} --sectors {sector} --cycle 0
```

Read `last_run.json`. If grade >= A- → this pair is done, go to PHASE 0 and pick next sector.

### PHASE 2 — Fix Loop (Same Agent, Same Sector)

```
cycle = 1

while grade < A- AND cycle <= 3:

    # 1. Analyze feedback from last_run.json
    Read last_run.json → find PROMPT_FIX issues for this agent/sector
    If no PROMPT_FIX issues → mark as blocked (DATA_FIX or NOT_OUR_PROBLEM), skip to next sector
    
    # 2. Read current sector skill (if exists)
    Read sector_skills/{sector}/{agent}.md (may not exist yet)
    
    # 3. Apply fix — choose the right target
    Decide: is this sector-specific or general? (see Decision Framework above)
    
    If SECTOR-SPECIFIC:
        Create/update sector_skills/{sector}/{agent}.md
        - Missing framework → "## Key Frameworks"
        - Wrong tool usage → "## Workflow Additions"  
        - Repeated mistake → "## Common Mistakes to Avoid"
        - Missing analysis → "## Required Analysis"
    
    If GENERAL (helps all sectors):
        Edit prompts.py — the relevant SYSTEM_V2 or INSTRUCTIONS_V2 section
        OR edit tools.py — AGENT_TOOLS_V2 registry
        ⚠️  REQUIRES regression check on all previously passing sectors after eval
    
    # 4. Commit
    git add -A
    git commit -m "autoeval: {agent}/{sector} cycle {cycle} — {brief description of fix}"
    
    # 5. Re-run and re-grade this same agent/sector pair
    python -m flowtracker.research.autoeval.evaluate \
        --agent {agent} --sectors {sector} --cycle {cycle}
    
    # 6. Read results
    Read last_run.json
    
    # 7. Check result
    if new_grade >= A-:
        Log success → move to next sector (PHASE 0)
    elif new_grade < previous_grade:
        REVERT: git checkout HEAD~1 -- sector_skills/{sector}/{agent}.md
        git commit -m "autoeval: revert {agent}/{sector} — grade regressed"
        Update resources.md with what failed and why
    else:
        # Grade didn't improve but didn't regress — try a different fix next cycle
        Update resources.md with what was tried
    
    cycle++

# After 3 cycles
if still below A-:
    Log: "{agent}/{sector} stuck below A- after 3 cycles — moving on"
    Note in resources.md
    Move to next sector (PHASE 0)
```

### PHASE 3 — Agent Complete

When all sectors pass A- for the current agent:
1. Log: "AGENT {agent} COMPLETE — all sectors at A-+"
2. Update resources.md with summary of what was learned for this agent
3. Go to PHASE 0 and pick the next agent

## Revert Protocol

If a skill change causes a grade to DROP:

```bash
git checkout HEAD~1 -- sector_skills/{sector}/{agent}.md
git commit -m "autoeval: revert {agent}/{sector} — grade regressed"
```

Update `resources.md` with what was tried and why it failed — learnings persist even from discards.

## Sector Skill File Format

```markdown
# {Agent} Agent — {Sector} Sector Skill

## Key Frameworks
<!-- Sector-specific analytical frameworks this agent should apply -->

## Workflow Additions  
<!-- Additional tool calls or analysis steps for this sector -->

## Required Analysis
<!-- Specific analyses that must be present in the report -->

## Common Mistakes to Avoid
<!-- Pitfalls specific to analyzing this sector -->
```

Keep skills **concise** — each rule competes for attention in the prompt. Only add rules that address real, documented failures from Gemini feedback.

## Writing Good Skill Entries

- **Be specific**: "Call `get_quality_scores(section='bfsi')` for NIM and ROA" > "Check banking metrics"
- **Cite the tool**: Tell the agent which MCP tool to call and what parameter to use
- **Explain why**: "BFSI companies use P/B as primary valuation (not P/E) because book value reflects regulatory capital adequacy"
- **One concept per bullet**: Don't combine unrelated instructions
- **Fewer rules > more rules**: A 5-rule skill file is better than a 20-rule one

## Stop Conditions

Stop when ANY of these is true:
1. **All agents pass all sectors** — every (agent, sector) pair at A-+
2. **Max 3 cycles per (agent, sector) pair** — move on after 3 failed attempts
3. **Total cost exceeds $500** — check results.tsv run durations as proxy

## Key Principles

1. **Don't ask the LLM to do math** — if Gemini flags a calculation error, that's COMPUTATION, not PROMPT_FIX
2. **Don't ask the LLM to speculate** — if the agent can't verify something from tools, it should pose an Open Question
3. **Challenge Gemini's feedback** — not everything Gemini suggests is actionable. Ask: "Can the agent actually do this with its available tools?"
4. **Fewer rules > more rules** — each rule competes for attention. Only add rules that address real failures
5. **Simplification wins** — if you can remove a rule and maintain the grade, remove it
6. **Cross-sector learning** — if a fix for BFSI looks like it applies to insurance too, note it in resources.md for when you get to that sector

## NEVER STOP

Keep iterating through (agent, sector) pairs until all stop conditions are met or the user intervenes. Do not ask for confirmation between pairs — just proceed. Log everything to results.tsv and resources.md so a human can review later.
