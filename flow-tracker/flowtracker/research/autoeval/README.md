# AutoEval — Prompt Optimization for Specialist Agents

Autoresearch-style eval loop that iteratively improves specialist agent prompts until they reach A- across all sectors.

## How It Works

1. Pick an agent (e.g., business)
2. Pick a sector (e.g., bfsi/SBIN)
3. Run the agent → generate report
4. Grade report with Gemini 3.1 Pro Preview (high thinking) → per-parameter scores
5. If grade < A-: fix the prompt (sector skill or core prompt), re-run, re-grade
6. If grade >= A-: move to next sector
7. When all sectors pass for this agent, move to next agent

## Running Evals

```bash
cd flow-tracker

# Install Gemini dependency (first time)
uv sync --extra autoeval

# Gemini API key at ~/.config/flowtracker/gemini.env:
# GEMINI_API_KEY=your-key-here

# Run agent + eval for one sector
uv run flowtrack research autoeval -a business --sectors bfsi

# Grade existing reports without re-running agent
uv run flowtrack research autoeval -a business --sectors bfsi --skip-run

# Run agent + eval for multiple sectors
uv run flowtrack research autoeval -a business --sectors bfsi,it_services,metals

# Show progress chart
uv run flowtrack research autoeval --progress
```

## How We Used It (Session 2026-04-07)

### Step-by-step workflow

1. **Run agent:** `uv run flowtrack research run business -s SBIN` (~5 min, $1-2)
2. **Grade with Gemini:** `uv run flowtrack research autoeval -a business --sectors bfsi --skip-run`
   - Sends full report + agent execution log (tools called, tools available, errors) to Gemini
   - Returns per-parameter grades + classified issues (PROMPT_FIX / DATA_FIX / COMPUTATION / NOT_OUR_PROBLEM)
3. **Review fixes:** Check `changelog.md` Pending Fixes section for accumulated recommendations
4. **Decide scope:** Is the fix sector-specific → `sector_skills/{sector}/business.md`, or general → `prompts.py`
5. **Apply fix, commit, re-run, re-grade** — verify no regression

### Key decisions made

- **Agent-first, sector-by-sector:** We run business agent across all 14 sectors first, then move to financials, etc. Within each agent, one sector at a time — iterate until A-, then move to next.
- **Don't send summaries to Gemini:** Always send the FULL report. Summaries gave inflated grades (A- vs B+ on the same report).
- **Standardized eval prompt:** 6 parameters graded independently (analytical_depth, logical_consistency, completeness, actionability, sector_framework, data_sourcing). Same prompt every time. Standalone evals — no prior context.
- **Sector skills vs core prompts:** Sector-specific fixes go in `sector_skills/{sector}/{agent}.md`. General fixes go in `prompts.py`. Key question: "will this fix help or hurt other sectors?"
- **No math in skills:** Formulas belong in code (`data_api.py`, `calculate` tool). Skills describe what to analyze, not how to compute it.

### Architecture (migrated this session)

Sector knowledge is now entirely in markdown files:

```
sector_skills/
  bfsi/
    _shared.md       ← shared rules for ALL agents (was _build_bfsi_injection() in Python)
    business.md      ← business-agent-specific BFSI guidance (from autoeval)
  metals/
    _shared.md
  telecom/
    _shared.md
  ... (20 sectors total)
```

`build_specialist_prompt()` loads `_shared.md` (shared sector rules) + `{agent}.md` (agent-specific) for the detected sector. `_build_mcap_injection()` is the only remaining Python injection (has dynamic logic).

### Results so far

| Sector | Stock | Grade | Status |
|--------|-------|-------|--------|
| bfsi | SBIN | A+ (96) | PASS |
| it_services | TCS | A (94) | PASS |
| metals | VEDL | A+ (96) | PASS |
| platform | ETERNAL | A+ (96) | PASS |
| conglomerate | ADANIENT | — | pending |
| telecom | BHARTIARTL | — | pending |
| real_estate | GODREJPROP | — | pending |
| pharma | SUNPHARMA | — | pending |
| regulated_power | NTPC | — | pending |
| insurance | POLICYBZR | — | pending |
| broker | GROWW | — | pending |
| auto | OLAELEC | — | pending |
| chemicals | PIDILITIND | — | pending |
| fmcg | HINDUNILVR | — | pending |

### Fixes applied

| Fix | What | Where |
|-----|------|-------|
| Chart rendering | Added workflow step 8: call `render_chart` | `prompts.py` BUSINESS_INSTRUCTIONS |
| save_business_profile | Made mandatory, before report writing | `prompts.py` BUSINESS_INSTRUCTIONS |
| BFSI business skill | ALM logic, ROA story, CAR/CET1, get_quality_scores call | `sector_skills/bfsi/business.md` |
| Business agent in dispatch | Was missing from `_ALL_SPECIALIST_AGENTS` — never got sector injections | Fixed (then removed with migration) |

### Recurring issues (not yet fixed)

- **Hallucinated tool errors:** Agent claims "Stream closed" for calculate/save_business_profile but evidence shows tools succeeded (3 occurrences). Classified as NOT_OUR_PROBLEM.
- **Charts still not rendered:** Fix applied to workflow but untested — reports graded so far were generated before the fix.

## File Map

| File | Purpose |
|------|---------|
| `evaluate.py` | Gemini eval harness — runs agents, grades, writes results |
| `eval_matrix.yaml` | 14 sectors with representative test stocks |
| `program.md` | Claude Code operating manual for autonomous loop |
| `progress.py` | ASCII progress chart |
| `results.tsv` | Grades per eval (append-only) |
| `changelog.md` | Experiment log + pending fixes + learnings (single source of truth) |
| `symbols.tsv` | 522-symbol reference with mcap/PE/PB/industry |
| `eval_history/` | Archived full Gemini responses (never overwritten) |
| `run_logs/` | Console output from every eval run |

## Next Session

1. Continue business agent evals: conglomerate (ADANIENT), telecom (BHARTIARTL), real_estate (GODREJPROP), pharma (SUNPHARMA), regulated_power (NTPC), insurance (POLICYBZR), broker (GROWW), auto (OLAELEC), chemicals (PIDILITIND), fmcg (HINDUNILVR)
2. After all 14 sectors pass for business → move to financials agent
3. Check if chart rendering fix works on fresh runs
4. Check tool_logs/ JSONL to verify no actual tool failures
