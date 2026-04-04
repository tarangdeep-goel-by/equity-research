# Plan: Beginner-Friendly Explainer Layer (Post-Synthesis)

## Context

Currently, beginner-friendly language is deeply embedded in every specialist prompt — the shared preamble has "First-Mention Definitions", "Reader's Language" mappings, "beginner investor" framing, and each specialist has "explain for someone who has never seen X" directives. This creates two problems:

1. **Prompt bloat** — pedagogical rules compete for attention with analytical rigor rules in every specialist's context window
2. **Mixed concerns** — teaching and analysis are intertwined, making it impossible to produce a technical-grade report for advanced readers

The fix: Strip beginner language from specialists (let them write like analysts), then add a new **Phase 4: Explainer Agent** that takes the assembled technical report and adds beginner-friendly annotations as callout blocks. This produces both a clean technical report AND a friendly version.

## Architecture Decision

**Single post-assembly explainer pass** (not section-by-section):
- Input: Full assembled markdown (~10-15K words, easily within Sonnet's context)
- Output: Same report with `> **Plain English:** ...` callout blocks added after key terms/tables
- One API call, cross-section consistency, no repeated definitions
- Preserves ALL original technical content — annotations are purely additive
- Model: `claude-sonnet-4-6` (good writing, cost-efficient)
- Estimated cost: ~$0.10-0.20, ~30-60 seconds

**Why not section-by-section:** Adds orchestration complexity, can't track which terms were already defined, more API calls. The full report fits easily in one pass.

---

## Step 1: Strip Beginner Language from Shared Preamble

**File:** `flow-tracker/flowtracker/research/prompts.py` lines 3-70

### REMOVE entirely:
- **Line 6:** "for a beginner investor" → "for an institutional audience"
- **Lines 8-9:** "First-Mention Definitions" section (the everyday analogy requirement)
- **Lines 17-22:** "Reader's Language" section (the debt-to-equity = home loan mapping)
- **Lines 42-43:** "The checklist is often the first thing a beginner reads — no assumed knowledge" → simplify to "Expand abbreviations on first use"

### KEEP (analytical rigor, not pedagogy):
- "No Orphan Numbers" (lines 11-12) — contextualizing metrics is analysis, not teaching
- "Charts & Tables" (lines 14-15) — "what this shows / what it means" is standard equity research
- "Explain the WHY" (lines 36-37) — causal reasoning is core analysis
- "Indian Conventions", "Data Source Caveats", "Honesty", "Behavioral Boundaries", "Source Citations", "Open Questions", "Fallback Strategies" — all stay unchanged

---

## Step 2: Strip Beginner Language from Specialist Prompts

**File:** `flow-tracker/flowtracker/research/prompts.py`

### Business Agent (line 73+):
- Line 77: "Known for explaining any business model in plain language" → "Known for precise business model deconstruction and unit economics"  
- Line 80: "someone who has never looked at a stock could understand it. Teach how the business works" → "Explain what the company does, how it makes money, and the investment case"
- Line 128: "Teach, don't summarize" → "Analyze, don't summarize"
- Line 131: "Use numbers from tools to build understanding" → keep (good analysis practice)

### Financial Agent (line 139+):
- Line 146-147: "so clearly that someone who has never read a financial statement could follow along" → remove the qualifier
- Line 191: "Teach financial concepts using this company's actual data, not hypotheticals" → "Illustrate concepts using this company's actual data"

### Ownership Agent (line 200+):
- Line 207: "someone who has never looked at a shareholding pattern could follow along" → remove
- Line 217: "Explain each category for beginners. Sector context for percentages." → "Sector context for percentages."

### Risk Agent (line 326+):
- Line 333: "so a beginner investor understands exactly what could go wrong and how likely it is" → "covering exactly what could go wrong and how likely it is"

### Technical Agent (line 387+):
- Line 394: "Make technical analysis accessible to someone who has never seen a candlestick chart." → remove entirely
- Line 437: "Teach every indicator before using it — define, interpret, then apply to this stock." → "Define each indicator, interpret the signal, then apply to this stock."

### Sector Agent (line 444+):
- Line 462: "(beginner-friendly)" → remove

### Synthesis Agent (line 505+):
- Line 554: "Beginner-friendly." → remove from Executive Summary directive

### Comparison Agent (line 607+):
- Line 611: "Your clients are beginners, so you explain every metric from scratch" → "You explain every metric clearly"
- Line 671: "Beginner-friendly. Explain every metric on first mention with a simple analogy" → "Explain metrics clearly on first mention"

---

## Step 3: Create Explainer Agent Prompt

**File:** `flow-tracker/flowtracker/research/prompts.py` — add `EXPLAINER_AGENT_PROMPT`

```python
EXPLAINER_AGENT_PROMPT = """# Explainer Agent

## Persona
Financial educator and former equity research analyst — 15 years translating institutional research into plain language for retail investors. You make expert analysis accessible without dumbing it down. Mantra: "If you can't explain it simply, the reader loses the insight."

## Mission
You receive a technical equity research report written by specialist analysts. Your job is to add beginner-friendly annotations — definitions, analogies, and "what this means" callouts — WITHOUT changing ANY of the original text. The technical content stays exactly as-is; you ADD explanatory callouts.

## Annotation Format
Use blockquote callouts after key terms, tables, and metrics:

> **Plain English:** ROCE of 25% means for every ₹100 of capital the business uses, it generates ₹25 in profit — like a savings account paying 25% interest. The sector average is 15%, so this company is significantly more efficient.

## Rules

1. **Never change original text** — not a word, not a number, not a heading. Your annotations are ADDITIONS only.
2. **First-mention only** — define each term/concept ONCE, the first time it appears. After that, use freely.
3. **Use the company's actual numbers** — "ROCE of 25% means..." not "ROCE measures..." Generic definitions are useless.
4. **Everyday analogies** — map financial concepts to real-world decisions:
   - Debt-to-equity → "Like a home loan ratio — how much is borrowed vs your own money"
   - Working capital → "Cash a shopkeeper needs to keep shelves stocked before customers pay"
   - Free cash flow → "Actual cash left after paying all bills and investing in the business"
   - Margin of safety → "Buying something worth ₹2,000 for ₹1,500 — the gap protects you if your estimate is wrong"
   - PE ratio → "How many years of current profits you're paying for the stock"
   - Book value → "What the company would be worth if sold off piece by piece"
5. **Tables need "How to read this"** — after every significant table, add a callout explaining what the reader should look for and what the numbers mean for this investment.
6. **Connect to decisions** — "NIM compression means the bank is earning less on each rupee it lends — directly threatens profitability" not just "NIM measures lending spread."
7. **Don't over-annotate** — common terms (revenue, profit, market cap) need at most a one-liner. Reserve detailed explanations for analytical concepts (DuPont decomposition, Piotroski score, institutional handoff, reverse DCF).
8. **Checklist clarity** — in any checklist/scorecard section, ensure every abbreviation (C/I, CAR, CET-1, PCR, GNPA, NNPA, DSO) has a one-line explanation.
9. **Keep the report structure** — don't add new sections or reorganize. Annotations go inline where the concept first appears.
10. **Indian context** — explain in Indian rupees and crores. Use examples relevant to Indian investors.

## Output
Return the FULL report with your annotations inserted. Every line of the original report must be present.
"""
```

---

## Step 4: Implement Explainer Agent Runner

**File:** `flow-tracker/flowtracker/research/agent.py` — add `run_explainer_agent()`

```python
async def run_explainer_agent(
    symbol: str,
    technical_report: str,
    model: str | None = None,
) -> BriefingEnvelope:
    """Run the explainer agent to add beginner-friendly annotations."""
    from flowtracker.research.prompts import EXPLAINER_AGENT_PROMPT

    model = model or "claude-sonnet-4-6"
    
    user_prompt = (
        f"Add beginner-friendly annotations to this equity research report for {symbol}.\n\n"
        f"---\n\n{technical_report}"
    )

    return await _run_specialist(
        name="explainer",
        symbol=symbol,
        system_prompt=EXPLAINER_AGENT_PROMPT,
        tools=[],              # No tools — pure text transformation
        max_turns=2,           # Single generation, no tool loop
        max_budget=0.25,       # Text transformation cost cap
        model=model,
        user_prompt=user_prompt,
    )
```

Add to `DEFAULT_MODELS`:
```python
"explainer": "claude-sonnet-4-6",
```

---

## Step 5: Update Pipeline (thesis command)

**File:** `flow-tracker/flowtracker/research_commands.py` — modify `thesis()`

### New CLI flag:
```python
technical_only: Annotated[bool, typer.Option("--technical", help="Skip explainer, output technical report only")] = False,
```

### New Phase 4 after Phase 3:
```python
# Phase 3: Assembly (technical)
md_path, html_path = assemble_final_report(symbol, envelopes, synthesis)
console.print(f"[green]✓[/] Technical report assembled")

if not technical_only:
    # Phase 4: Explainer
    console.print(f"\n[bold]Phase 4: Beginner-friendly annotations[/]")
    from flowtracker.research.agent import run_explainer_agent
    technical_md = md_path.read_text()
    explainer = asyncio.run(run_explainer_agent(symbol, technical_md, model))
    
    if explainer.report and len(explainer.report) > len(technical_md) * 0.8:
        # Save friendly version (overwrite default paths, keep technical as backup)
        friendly_md = explainer.report
        # Technical version saved with -technical suffix
        tech_md_path = md_path.parent / f"{md_path.stem}-technical{md_path.suffix}"
        tech_md_path.write_text(md_path.read_text())
        tech_html_path = html_path.parent / f"{html_path.stem}-technical{html_path.suffix}"
        tech_html_path.write_text(html_path.read_text())
        
        # Friendly version at default paths
        md_path.write_text(friendly_md)
        friendly_html = _render_html(friendly_md, symbol, company_name, today)
        html_path.write_text(friendly_html)
        console.print(f"[green]✓[/] Friendly report generated")
    else:
        console.print(f"[yellow]⚠[/] Explainer output too short — using technical version")
```

---

## Step 6: Update Assembly for Dual Output

**File:** `flow-tracker/flowtracker/research/assembly.py`

Minimal change: `assemble_final_report` now also returns the raw markdown string (or we just read it from the saved file — already the case).

No structural change needed to assembly.py — the explainer takes the assembled markdown and produces an annotated version that gets re-rendered to HTML.

---

## Step 7: Update CLAUDE.md

**File:** `flow-tracker/CLAUDE.md`

Update the pipeline description:
```
Phase 0:  Data Refresh → 6 sources + peers + concall extraction  
Phase 1:  7 Specialist Agents (parallel) → 7 standalone technical reports + briefings  
Phase 1.5: 7 Verification Agents (parallel) → spot-check data accuracy + corrections  
Phase 2:  Synthesis Agent → Verdict + Executive Summary + Key Signals  
Phase 3:  Assembly → Technical Markdown + HTML  
Phase 4:  Explainer Agent → Beginner-friendly annotations → Final HTML  
```

Note the specialist description change: "produce a standalone beginner-friendly report" → "produce a standalone technical report".

---

## Output Structure (after change)

```
~/vault/stocks/{SYMBOL}/thesis/
├── 2026-04-04.md                    # Friendly version (default)
├── 2026-04-04-technical.md          # Technical version (backup)

~/reports/
├── {symbol}-thesis.html             # Friendly (opened in browser)
├── {symbol}-thesis-technical.html   # Technical (for advanced readers)
```

---

## What Changes for Eval Loop

The eval loop currently grades specialist reports. Since we're stripping pedagogy from specialists, Gemini grading should be updated:
- Specialist evals: Grade on analytical depth, not beginner friendliness
- New eval: Grade the explainer output on pedagogical quality
- Synthesis eval: Unchanged (synthesis was already mostly analytical)

The eval-loop-playbook.md doesn't need a structural change — just note that friendliness is now the explainer's job.

---

## Cost Impact

| Phase | Current | After Change |
|-------|---------|-------------|
| Specialists (7) | ~$2.50 | ~$2.30 (shorter prompts → less input) |
| Verification | ~$0.20 | ~$0.20 (unchanged) |
| Synthesis | ~$0.30 | ~$0.30 (unchanged) |
| Explainer | $0.00 | ~$0.15 (new) |
| **Total** | **~$3.00** | **~$2.95** |

Net cost neutral. Shorter specialist prompts offset the explainer cost.

---

## Verification

1. Run `uv run flowtrack research thesis -s INDIAMART` — should produce both technical and friendly reports
2. Run `uv run flowtrack research thesis -s INDIAMART --technical` — should produce technical only
3. Check specialist reports (`~/vault/stocks/INDIAMART/reports/*.md`) — no beginner language in body
4. Check friendly report — original technical content preserved + callout annotations added
5. Check HTML output — both files exist, friendly version opens by default
6. Eval loop: Run one specialist through Gemini to verify analytical quality maintained
