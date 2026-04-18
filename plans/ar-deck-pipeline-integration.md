# Annual Report & Investor Deck Pipeline Integration

**Status:** ✅ **Implemented** (branch `feat/ar-deck-integration`, 2026-04-18)
**Author:** Claude (Opus 4.7) + tarang
**Date:** 2026-04-18
**Scope:** Wire the already-built annual-report and investor-deck extraction pipelines into the multi-agent research system end-to-end, **exactly mirroring the concall integration pattern** that's already proven in production. Covers pre-agent refresh, specialist prompts, tool registries, sector skills, verification signals, and autoeval.

## Implementation Summary (2026-04-18)

All 25 tasks complete. INOX DoD smoke PASS: 5 mandated agents cited AR, Risk cited `auditor_report` 10×, zero hallucinations on spot-check (ownership's ₹3.27 Cr royalty citation matched the vault JSON exactly). 2421 tests pass, 0 failures.

**Deviations from the v2 plan:**

1. **Filename versioning** (`_v2` suffix): **not adopted**. Plan proposed renaming `annual_report_FY??.json` → `annual_report_v2_FY??.json` for migration safety. The existing filenames had no schema break to migrate, so we kept them. Concall's `_v2` bump had schema history; AR/deck didn't.

2. **Per-agent section prescription** (plan §5.3.2): **shipped hardcoded, then relaxed to Option A.** Initial implementation mandated specific sections per agent ("Business must read chairman_letter + mdna + segmental"). After the INOX smoke validated the hardcoded prescription worked, we converted to a purpose-list: each mandated agent MUST consult AR/deck and picks sections from the TOC + sector-skills guidance. Trades determinism for adaptability; null-finding rule still catches skips.

3. **`oil_gas` sector skill**: plan §5.4 Tier-1 listed `oil_gas` as a sector skill to update, but no such directory exists in `sector_skills/`. Skipped; content from plan is unused. Follow-up: either create the dir or remove from Tier-1.

4. **`--skip-ar-deck` CLI flag**: plan §5.1 proposed this but then self-corrected (concall parity decision). Not added — `--skip-fetch` already gates Phase 0b.

5. **Scope expansion during implementation**:
   - **Temporal grounding injection** (task I1): not in original plan — added after identifying LLM temporal-grounding failure mode. `build_specialist_prompt` now prepends `today = YYYY-MM-DD` + per-source freshness + AR/deck inventory. Applied to web_research agent too (K1).
   - **"Say Unknown" blanket rule** (I2): extended the null-finding rule beyond AR/deck to every claim in every briefing. Prevents fluent-confidence hallucination.
   - **Specialist→verifier pipelining** (J1): `run_all_agents` now chains each specialist directly into its verifier rather than running all specialists first. Peak Claude subprocess count unchanged (≤6); saves wall time ≈ fastest-verifier stall.
   - **Parallel Phase 0b** (H1): concall + AR + deck extractors run under `asyncio.gather` instead of sequentially. ~50% wall-time reduction on fresh runs.
   - **Web research vault access** (K1): web_research agent now has `get_concall_insights`/`get_annual_report`/`get_deck_insights` MCP tools and a "Check Vault Before the Web" rule. Stops the agent from re-downloading PDFs already in vault.
   - **Tool-leak closure** (post-INOX audit): extended `_DISALLOWED_BUILTINS` in agent.py to include Monitor, ToolSearch, Task* — session-internal tools that were leaking into agent subprocesses.

**Deferred to follow-up tickets:**
- Tier-2 + Tier-3 sector skills (15 more sectors)
- `--deep-ar` flag for `full=True` AR extraction
- Deck auto-download via Screener `concall_ppt` URLs
- Verifier retry on subprocess crash (low-probability gap flagged mid-session)
- News agent AR/deck consultation (evals haven't shown a gap)

**Guiding principle: concall parity.** Every design choice below answers the question *"how does concall do it?"* and replicates that choice. Concall extraction runs in Phase 0b; AR/deck run in Phase 0b. Concall extraction takes an `industry` hint; AR/deck extraction takes an `industry` hint. Concall tool returns a compact TOC with a `_extraction_quality_warning`; AR/deck tools return the same. Concall prompts are conditional/anomaly-triggered; AR/deck prompts are conditional/anomaly-triggered. No new patterns invented.

---

## 1. Executive Summary

The repo has a **fully-built but orphaned** annual-report and investor-deck extraction pipeline. Code, schemas, and MCP tools all exist; **none of it is reachable from `flowtrack research thesis`**. Agents run blind to AR/deck content even though the tools sit next to them.

**What exists (working, tested):**
- `ar_downloader.ensure_annual_reports()` — pulls AR PDFs from Screener-sourced URLs into the vault
- `annual_report_extractor.ensure_annual_report_data()` — Docling + Claude Sonnet extraction into 10-section JSON (per FY) + cross-year narrative
- `deck_extractor.ensure_deck_data()` — Docling + Claude Sonnet extraction into 7-section JSON (per quarter)
- `ResearchDataAPI.get_annual_report()` / `get_deck_insights()` — TOC + drill-in reads from vault
- MCP tools `get_annual_report` / `get_deck_insights` (tools.py:854-890)
- `get_company_context` already routes `section='annual_report'|'deck_insights'` (tools.py:1811-1816)
- CLI surface: `flowtrack filings download-ar`, `extract-ar`, `extract-deck`

**What's missing (the three gaps):**
1. **Phase 0b** in `research_commands.py` runs concall extraction only — never calls AR download/extract or deck extract.
2. **V2 agent tool registries** (tools.py:2182-2229) do not include `get_annual_report` / `get_deck_insights` for any specialist.
3. **Agent prompts** (prompts.py) and **sector skills** (sector_skills/) never reference AR/deck sections, so even the agents that *have* `get_company_context` don't know to call `section='annual_report'` or `section='deck_insights'`.

**Outcome after integration:** Every `research thesis -s X` run will have access to chairman's letter, MD&A, auditor KAMs, related-party disclosures, segment P&L, deck guidance, strategic priorities, and cross-year narrative across 2 FY + 4 quarters of decks — fed to the right specialist agents with mandatory citation.

---

## 2. Current State Audit

### 2.1 Data path

| Component | Location | State |
|-----------|----------|-------|
| AR URL harvesting | Screener `company_documents` table | ✅ Wired (refresh.py:189-196) |
| AR PDF download | `ar_downloader.ensure_annual_reports` | ❌ Never called in pipeline |
| AR extraction | `annual_report_extractor.ensure_annual_report_data` | ❌ Never called in pipeline |
| Deck PDF download | Manual / out-of-band | ⚠️ Not auto-downloaded (presentations live in quarter dirs) |
| Deck extraction | `deck_extractor.ensure_deck_data` | ❌ Never called in pipeline |
| Vault reads via `data_api` | `get_annual_report`, `get_deck_insights` | ✅ Implemented |
| MCP tool registration | tools.py:854-890 | ✅ Registered as standalone MCP tools |
| `get_company_context` routing | tools.py:1811-1816 | ✅ Dispatches to both |

### 2.2 Agent access

| Agent | V2 Registry | Has `get_company_context`? | Prompt mentions AR/deck? |
|-------|-------------|----------------------------|--------------------------|
| Business | BUSINESS_AGENT_TOOLS_V2 | ✅ | ❌ |
| Financials | FINANCIAL_AGENT_TOOLS_V2 | ✅ | ❌ |
| Ownership | OWNERSHIP_AGENT_TOOLS_V2 | ✅ | ❌ |
| Valuation | VALUATION_AGENT_TOOLS_V2 | ✅ | ❌ |
| Risk | RISK_AGENT_TOOLS_V2 | ✅ | ❌ |
| Technical | TECHNICAL_AGENT_TOOLS_V2 | ❌ | — |
| Sector | SECTOR_AGENT_TOOLS_V2 | ✅ | ❌ |
| News | NEWS_AGENT_TOOLS_V2 | ✅ | ❌ |
| Verification | (reuses specialist tools) | inherits | — |
| Synthesis | n/a (reads briefings) | n/a | — |
| Explainer | n/a (reads assembled markdown) | n/a | — |
| Comparison | multi-stock variant | n/a | — |

Five of seven specialists can already reach AR/deck via `get_company_context`, but none are instructed to do so. Technical agent would need `get_company_context` added. News agent would benefit from AR material-events + press-release mapping (low priority).

### 2.3 Cost floor per symbol (measured from existing extractor code)

| Step | Claude calls | Budget cap | Real cost (Sonnet 4.6) |
|------|--------------|-----------|------------------------|
| AR extraction, 2 FY × 8 default sections | 16 × `$0.35` cap | $5.60 max | ~$2-3 typical |
| Deck extraction, 4 quarters × 1 call each | 4 × `$0.35` cap | $1.40 max | ~$0.60 typical |
| Cross-year narrative | 1 call | $0.35 | ~$0.15 typical |
| **Total AR+deck per symbol** | **~21 calls** | **$7.35 cap** | **~$3-4 typical** |
| Concall (reference, already running) | 4 × 1 call | $1.40 | ~$0.50 typical |

Caching is aggressive — re-runs only hit uncached quarters/years (typically 1 new FY + 1 new quarter per research cycle → ~$0.30 incremental).

---

## 2.5 Concall Parity Blueprint (the master template)

Every component below mirrors a concall analog. **If concall does X, we do X' identically for AR/deck.**

| Component | Concall pattern (as built) | AR/Deck mirror (to build) |
|-----------|----------------------------|---------------------------|
| **Phase** | Phase 0b in `research_commands.py:248-292` | Phase 0b (same block, extended) |
| **Sync→async bridge** | `asyncio.run(ensure_concall_data(symbol, quarters=4, industry=_industry))` at line 280 | `asyncio.run(ensure_annual_report_data(symbol, years=2, industry=_industry))` and `asyncio.run(ensure_deck_data(symbol, quarters=4, industry=_industry))` |
| **Industry hint injection** | Extractor receives `industry=_industry`; `build_extraction_hint(industry)` emits canonical-KPI instructions into the Claude prompt; BFSI mandates `casa_ratio_pct`, `gross_npa_pct`, `pcr_pct`; unmentioned KPIs set to `null` with `reason: "not_mentioned_in_concall"` | Same plumbing: `ensure_annual_report_data(..., industry=...)` must mandate BFSI AR segmental to include casa/NPA split; Pharma AR must mandate R&D expense disclosure; Metals AR must mandate commodity-hedge notes. Mirrors `concall_extractor.build_extraction_hint()`. |
| **Vault layout** | `~/vault/stocks/{SYMBOL}/filings/FY??-Q?/concall.pdf` → `~/vault/stocks/{SYMBOL}/fundamentals/concall_extraction_v2.json` | (already matches) `~/vault/stocks/{SYMBOL}/filings/FY??/annual_report.pdf` → `fundamentals/annual_report_FY??.json` + `annual_report_cross_year.json`; decks at `filings/FY??-Q?/investor_deck.pdf` → `fundamentals/deck_extraction.json`. **Rename to `annual_report_v2_{FY}.json` / `deck_extraction_v2.json`** for the same migration-safety reason concall adopted `_v2`. |
| **Cache key** | Per-quarter `fy_quarter` + `extraction_status` ∈ {complete, recovered, partial, failed}. Skips only `complete`/`recovered`; re-extracts `partial`/`failed`. | AR: per-FY `fiscal_year` + `extraction_status` (same enum). Deck: per-quarter `fy_quarter` + `extraction_status` (same enum). |
| **Return counter** | `_new_quarters_extracted` + `quarters_analyzed` in result dict | `_new_years_extracted` + `years_analyzed` for AR; `_new_quarters_extracted` + `quarters_analyzed` for deck. |
| **Console logging** | `_ok("concall", count)` / `_skip("concall", err)` via Phase 0b helpers | `_ok("annual_report", ...)`, `_ok("deck", ...)` via same helpers. |
| **Cross-period narrative** | `cross_quarter_narrative` block in concall JSON: key_themes, guidance_track_record, metric_trajectories, narrative_shifts, recurring_analyst_concerns, biggest_positive, biggest_concern, what_to_watch | AR: `annual_report_cross_year.json` with `narrative.{key_evolution_themes, risk_evolution, auditor_signals, governance_changes, rpt_evolution, strategic_framing_shift, capital_allocation_shifts, biggest_positive_development, biggest_concern, what_to_watch_next_fy}` (already in schema). Deck: add `cross_quarter_highlights` block to `deck_extraction_v2.json` mirroring concall structure. |
| **Tool — standalone** | `get_concall_insights(symbol, sub_section, quarter, qa_topics)` at tools.py:835-851 | `get_annual_report(symbol, section, year)` at tools.py:874-890 (already built) + `get_deck_insights(symbol, sub_section, quarter, slide_topics)` at tools.py:854-871 (already built). |
| **Tool first-call returns** | Compact TOC: `{quarters[{fy_quarter, period_ended, sections_populated}], cross_quarter_narrative_keys, qa_topics_by_quarter, _meta}` | AR first call: `{years_on_file[{fiscal_year, sections_populated}], cross_year_narrative_keys, _meta}`. Deck first call: `{quarters[{fy_quarter, period_ended, sections_populated, slide_topics}], _meta}`. Verify current `data_api.get_annual_report` / `get_deck_insights` return this shape; if not, align. |
| **Tool drill filter** | `sub_section`, `quarter`, `qa_topics` (canonical tag enum) | AR: `section`, `year` (done). Deck: `sub_section`, `quarter`, `slide_topics` (canonical tag enum) — verify slide_topics filter already supported. |
| **Tool routing via `get_company_context`** | Available as `section='concall_insights'` | Already available as `section='annual_report'|'deck_insights'` (tools.py:1811-1816). |
| **Return size discipline** | Agents explicitly forbidden from `section='all'` (prompts.py:52) — truncation wall at ~30KB | Same rule extends to AR/deck: never call `section='all'` on `get_company_context` when AR/deck present; call the standalone tools. |
| **Degradation signal to agent** | `_extraction_quality_warning: "Concall extraction was degraded for 2/4 quarters..."` + `_meta.degraded_quality: true` + `_meta.missing_periods: [...]` embedded in tool response | `ResearchDataAPI.get_annual_report` / `get_deck_insights` must emit same three keys when any FY/quarter is `partial`/`recovered`/`failed`. |
| **Recovery fallback chain in extractor** | Claude returns prose → `_recover_json_from_prose()` with cheap model → if still fails, `_build_partial_extraction()` with regex → status escalates through `complete`→`recovered`→`partial`→`failed` | Check current AR/deck extractors for same chain. AR extractor already has per-section try/except + partial writes; **add `_recover_json_from_prose` + `_build_partial_extraction` helpers if missing**. |
| **Prompt layer — where mentioned** | Conditional/anomaly-triggered in specialist instructions; NOT a blanket mandate in SHARED_PREAMBLE | **Deliberate divergence.** AR/deck are buy-side-primary documents, so we adopt **scoped-mandatory**: AR mandatory for Business/Financials/Risk/Valuation/Ownership; deck mandatory for Business/Financials/Valuation; conditional elsewhere. SHARED_PREAMBLE carries the mandate block + null-finding rule. Rationale: concall is conditional due to retrofit legacy, not because conditional is superior. Designing fresh, mandatory outperforms conditional on buy-side tasks. See §3.3 for full scope table. |
| **Citation format** | Inline `(source: Q4 FY22 concall)` or `(Q2 concall)` | Inline `(source: FY25 AR, mdna)` or `(source: FY26-Q3 deck, outlook)` — short, consistent with concall style. |
| **Sector skills reference** | `sector_skills/{sector}/_shared.md` names canonical KPIs that concall extraction must populate (BFSI: CASA/NPA/PCR; telecom: ARPU/churn) | Add an AR/deck-specific subsection to each sector `_shared.md` with canonical AR sections the extractor should deep-dive (BFSI: auditor_report loan-classification KAMs; Pharma: mdna R&D pipeline + USFDA warnings; Metals: risk_management commodity hedging). Same file, same agents-in-sector load mechanism. |
| **Verifier agent** | Inherits specialist tools → spot-checks concall citations against vault JSON | Same: verifier gets `get_annual_report`/`get_deck_insights` by inheritance → spot-checks citations. Add one line to verifier prompt: "Any `(source: FY?? AR, ...)` or `(source: FY??-Q? deck, ...)` citation must be re-fetched from the corresponding tool and verified." |
| **CLI flag** | No `--skip-concall` exists | No `--skip-ar-deck` either (parity). Only `--skip-fetch` exists, which already skips Phase 0 and the `not skip_fetch` guards around Phase 0b blocks. Reuse the same gate; don't invent a new flag. *(Revises v1 of this plan which proposed one.)* |
| **Failure messaging** | `console.print("  [dim]No concall PDFs found for {symbol}. Agents will work without concall data.[/]")` at research_commands.py:289 | `console.print("  [dim]No AR PDFs for {symbol}. Agents proceed without AR.[/]")` and same for deck. |

**Takeaway:** concall is a fully-worked reference implementation. This plan reduces to "duplicate those decisions with `annual_report_extractor` / `deck_extractor` in the same seats."

---

## 3. Target Architecture

### 3.1 Execution flow (after integration)

```
flowtrack research thesis -s SYMBOL
├─ Phase 0: refresh_for_research()          [unchanged]
├─ Phase 0b: Document Pipeline              [EXPANDED]
│  ├─ BSE filings download                  [existing]
│  ├─ Concall extraction                    [existing]
│  ├─ AR PDF download (ensure_annual_reports)        [NEW]
│  ├─ AR extraction (ensure_annual_report_data)      [NEW]
│  └─ Deck extraction (ensure_deck_data)              [NEW]
├─ Phase 1: 7 specialists (parallel)         [prompts + registries updated]
│  └─ Each specialist now calls get_company_context(section='annual_report'|'deck_insights')
│     per strongest-section mapping
├─ Phase 1.5: Verification                   [prompts inherit new instructions]
├─ Phase 1.7: Web research                   [unchanged]
├─ Phase 2: Synthesis                        [reads enriched briefings]
├─ Phase 3: Assembly                         [unchanged]
└─ Phase 4: Explainer                        [unchanged]
```

### 3.2 Tool access pattern

Two options, pick one:

**Option A (preferred, minimal surface):** Keep `get_annual_report` and `get_deck_insights` as standalone MCP tools, **and** expose via `get_company_context(section=...)`. Add the standalone tools to 3-4 agent registries where AR/deck is primary (Business, Financials, Risk). For other agents that already have `get_company_context`, they can drill in via the section routing.

**Option B:** Drop the standalone MCP tools entirely, force everyone through `get_company_context`. Simpler but forces a double-hop (TOC call → drill-in) for agents heavily focused on AR/deck.

**Recommendation: A.** Standalone tools are already built; richer descriptions on the standalone tools help the agent plan. Cost is 2 extra tool registrations per affected agent.

### 3.3 Prompt layering — scoped-mandatory (deliberate concall divergence)

**Decision (agreed 2026-04-18 with tarang):** Unlike concall (which is conditional/anomaly-triggered due to retrofit legacy), AR and deck are buy-side-primary documents and warrant **scoped-mandatory consult** for the agents where they materially lift report quality. We deliberately diverge from concall's conditional pattern here because we're designing fresh, not retrofitting.

**Scope:**

| Agent | AR | Deck | Rationale |
|-------|----|----|-----------|
| Business | **Mandatory** | **Mandatory** | Chairman letter, MD&A, deck strategic_priorities are core to business-model analysis |
| Financials | **Mandatory** | **Mandatory** | Notes_to_financials + segmental AR + deck segment_performance are margin/cost reconciliation primaries |
| Risk | **Mandatory** | Optional | Auditor_report + related_party + risk_management are highest-signal risk inputs; deck is marketing, not risk |
| Valuation | **Mandatory** | **Mandatory** | MD&A + deck outlook_and_guidance anchor reverse-DCF assumptions to management numbers |
| Ownership | **Mandatory** | Optional | Related_party + corporate_governance explain insider/promoter patterns; deck has little ownership signal |
| Sector | Conditional | Conditional | Existing segmental-fallback chain is clean; don't over-instruct |
| News | Conditional | Conditional | Recent events are the domain; AR lags by 6-12 months |
| Technical | No change | No change | Price/volume is the domain; AR/deck add ~zero |

**Three layers:**

1. **SHARED_PREAMBLE_V2 (scoped mandate + null-finding rule):** Insert a short "AR & Deck consult" block after line 158 (before preamble close). Lists the three rules below, names which agents are in-scope, adds the null-finding escape hatch that prevents citation theatre. Must recompute `_SHARED_PREAMBLE_HASH` (prompts.py:163) + update assert (prompts.py:1425).
2. **Per-agent INSTRUCTIONS (prompts.py):** Each of the 5 mandated agents gets an explicit workflow step saying *"before writing Key Signals, call `get_annual_report` TOC + drill into sections X/Y/Z; cite as `(source: FY?? AR, <section>)`."* For the 3 deck-mandated agents, add the parallel deck step. Wording replicates the authoritative voice already used in Risk agent's governance-chase rule (prompts.py:698) — "must be chased" applied positively.
3. **Sector skills `_shared.md`:** Same edit as before — sector-specific canonical AR sections + deck sections per sector, appended alongside the existing concall-KPI block.

**Null-finding escape hatch (prevents citation theatre):**

> If a mandated AR/deck section returns no material insight for your topic — e.g. auditor_report has no qualifications, related_party shows only routine intra-group flows, deck outlook contains no forward numbers — write ONE sentence stating that explicitly and cite the section. Example: `"No Key Audit Matters flagged in FY25 AR (source: FY25 AR, auditor_report)."` Silent skipping of a mandated section reads as work-not-done. A clean null-finding is information.

**Cost mitigation:** Mandatory consult adds ~2-4 tool calls per mandated agent = ~20 extra MCP calls across 5 agents. At 0-marginal cost for cached vault reads, this is negligible. The mandate is expensive only on first run (Phase 0b extraction), which is cached thereafter.

**Hash guard:** `SHARED_PREAMBLE_HASH` at `prompts.py:163` covers the preamble literal (assert at prompts.py:1425). Commit preamble edit + hash update atomically — CI rejects stale hash.

**Why scoped, not universal?** Mandating AR/deck for Technical (price/volume focus) and News (recent events focus) wastes tool budget with low payoff. Sector already has an elegant segmental fallback chain; over-instructing breaks it. The 5 mandated agents cover ~85% of the analytical surface where AR/deck materially lift report quality.

---

## 4. Workstream Breakdown

Five workstreams. Three are independent and parallelizable; two depend on the first.

| # | Workstream | Depends on | Effort | Parallelizable |
|---|-----------|------------|--------|----------------|
| **W1** | Pipeline wiring (Phase 0b extension) | — | 1 day | With W2, W3 |
| **W2** | Tool registries + get_company_context polish | — | 0.5 day | With W1, W3 |
| **W3** | SHARED_PREAMBLE update + per-agent prompt edits | — | 1 day | With W1, W2 |
| **W4** | Sector skills AR/deck injections (22 sectors × ≤3 agents each) | W3 done | 2-3 days | Internal-parallel |
| **W5** | Tests + autoeval runs | W1-W4 done | 2 days | With W4 partially |

Total: **~5-6 engineer-days**, **~3 calendar days** with parallel dispatch.

---

## 5. File-by-File Change Spec

### 5.1 W1 — Pipeline wiring

**File: `flow-tracker/flowtracker/research_commands.py`**

Insert new blocks in `thesis()` command Phase 0b (after line 292), mirroring the existing concall block pattern (async extractor wrapped with `asyncio.run()`, result counted, error → warning, no pipeline halt):

```python
# --- After line 292 (end of concall block), before p0b.finished_at ---

# AR download + extraction (cached; skips complete years)
if not skip_fetch:
    try:
        from flowtracker.research.ar_downloader import ensure_annual_reports
        n_downloaded = ensure_annual_reports(symbol, max_years=3)
        if n_downloaded:
            console.print(f"  [green]✓[/] AR PDFs: {n_downloaded} downloaded")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] AR download: {e}")

    try:
        from flowtracker.research.annual_report_extractor import ensure_annual_report_data
        _ar_result = asyncio.run(
            ensure_annual_report_data(symbol, years=2, model="claude-sonnet-4-6", full=False)
        )
        if _ar_result:
            _ar_new = _ar_result.get("_new_years_extracted", 0)
            _ar_total = len(_ar_result.get("years_analyzed", []))
            if _ar_new > 0:
                console.print(f"  [green]✓[/] AR: {_ar_new} new year(s) extracted ({_ar_total} total)")
            else:
                console.print(f"  [dim]AR cached ({_ar_total} years)[/]")
        else:
            console.print(f"  [dim]No AR PDFs for {symbol}. Agents proceed without AR.[/]")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] AR extraction: {e}")

# Deck extraction (cached; skips complete quarters)
if not skip_fetch:
    try:
        from flowtracker.research.deck_extractor import ensure_deck_data
        _deck_result = asyncio.run(
            ensure_deck_data(symbol, quarters=4, model="claude-sonnet-4-6")
        )
        if _deck_result:
            _deck_new = _deck_result.get("_new_quarters_extracted", 0)
            _deck_total = _deck_result.get("quarters_analyzed", 0)
            if _deck_new > 0:
                console.print(f"  [green]✓[/] Deck: {_deck_new} new quarter(s) extracted ({_deck_total} total)")
            else:
                console.print(f"  [dim]Deck cached ({_deck_total} quarters)[/]")
        else:
            console.print(f"  [dim]No investor decks for {symbol}. Agents proceed without decks.[/]")
    except Exception as e:
        console.print(f"  [yellow]⚠[/] Deck extraction: {e}")
```

**Additions required:**
- `ensure_annual_report_data` and `ensure_deck_data` must return `_new_years_extracted` / `_new_quarters_extracted`. If they don't, add to their return dict (parallels concall_extractor convention).
- Both extractors must accept `industry=_industry` and inject sector-specific canonical-section hints into the Claude prompt — same pattern as `concall_extractor.build_extraction_hint(industry)`. Add `annual_report_extractor.build_extraction_hint()` and `deck_extractor.build_extraction_hint()` if missing.
- Both extractors must emit `_extraction_quality_warning` in `data_api.get_annual_report` / `get_deck_insights` responses when any FY/quarter is `partial`/`recovered`/`failed` — mirror `data_api.get_concall_insights` at data_api.py:2260-2467.
- Bump output filenames to `annual_report_v2_{FY}.json` and `deck_extraction_v2.json` for the same migration-safety reason concall adopted `_v2`. Old files can be auto-migrated on first read.
- Rename Phase 0b console header: `Phase 0b: Concall Pipeline` → `Phase 0b: Document Pipeline (Concalls + AR + Decks)`.

**Same-pattern change** in `research_commands.py:893+` (single-agent `run` command) for parity.

**CLI flag:** Reuse existing `--skip-fetch` flag (already wraps Phase 0b blocks via `not skip_fetch` guards). Do NOT introduce a new `--skip-ar-deck` flag — concall didn't add one, and splitting the skip surface creates permutation noise. Users who want to iterate on prompts cheaply can pass `--skip-fetch` and rely on cached vault data.

### 5.2 W2 — Tool registries

**File: `flow-tracker/flowtracker/research/tools.py`**

Update V2 registries (lines 2182-2229). Add `get_annual_report` + `get_deck_insights` to:
- `BUSINESS_AGENT_TOOLS_V2` (line 2182) — Business reads chairman letter, MD&A, segmental, deck highlights + strategic priorities
- `FINANCIAL_AGENT_TOOLS_V2` (line 2188) — Financials reads notes_to_financials, segmental, deck financial metrics
- `RISK_AGENT_TOOLS_V2` (line 2208) — Risk reads auditor_report, related_party, risk_management, corporate_governance
- `VALUATION_AGENT_TOOLS_V2` (line 2201) — Valuation reads MD&A outlook + deck outlook_and_guidance
- `OWNERSHIP_AGENT_TOOLS_V2` (line 2195) — Ownership reads related_party + corporate_governance

Ownership and Sector agents can optionally rely on `get_company_context(section=...)` routing instead; adding standalone tools is noise for News/Technical.

**Verification:** existing `test_mcp_tools_extended.py` covers shape; add two new unit tests that call `get_annual_report(symbol='TESTCO')` and `get_deck_insights(symbol='TESTCO')` against a seeded vault fixture.

**Tool description upgrade:**
Update `get_company_context` tool description at tools.py:1827 to explicitly list `'annual_report'` and `'deck_insights'` as first-class sub-sections (already present) and add a short "Prefer the standalone `get_annual_report` / `get_deck_insights` tools for heavy drill-in" hint so the agent picks the right tool.

### 5.3 W3 — Prompt edits (scoped-mandatory)

**File: `flow-tracker/flowtracker/research/prompts.py`**

#### 5.3.1 SHARED_PREAMBLE_V2 — mandate block + tool-family entries

Must recompute `_SHARED_PREAMBLE_HASH` at prompts.py:163 and update the assert at prompts.py:1425 in the same commit.

**Edit 1: tool-family TOC list (prompts.py:47)** — add `get_annual_report(symbol)` and `get_deck_insights(symbol)` to the list of tools whose first call returns TOC.

**Edit 2: drill-syntax list (prompts.py:58)** — add `get_annual_report(symbol, section=...)`, `get_annual_report(symbol, year=...)`, `get_deck_insights(symbol, sub_section=..., quarter=..., slide_topics=...)`.

**Edit 3: NEVER call section='all' rule (prompts.py:52)** — extend the forbidden-list with `get_annual_report` (large if all years × all sections returned).

**Edit 4: new mandate block, insert after line 158 (before closing triple-quote):**

```markdown
## Annual Report & Investor Deck — Scoped Mandatory Consult

Annual reports and investor decks are primary documents for buy-side research. Business, Financials, Risk, Valuation, and Ownership agents MUST consult the annual report. Business, Financials, and Valuation agents MUST also consult the latest investor deck. Sector, News, and Technical agents consult only when a topic calls for it.

**Required workflow for mandated agents:**
1. Early in your run (before writing Key Signals), call `get_annual_report(symbol)` to get the TOC. Then drill into the sections listed for your agent below.
2. For deck-mandated agents, also call `get_deck_insights(symbol)` TOC, then drill into the relevant sub_section for the most recent quarter.
3. Cite every AR/deck-derived claim inline: `(source: FY25 AR, mdna)` or `(source: FY26-Q3 deck, outlook_and_guidance)`. Match concall citation style — short, inline, section-named.

**Mandated sections per agent:**
- **Business:** AR `chairman_letter`, `mdna`, `segmental`; Deck `strategic_priorities`, `highlights`.
- **Financials:** AR `notes_to_financials`, `segmental`; Deck `segment_performance`.
- **Risk:** AR `auditor_report`, `risk_management`, `related_party`.
- **Valuation:** AR `mdna`; Deck `outlook_and_guidance`.
- **Ownership:** AR `related_party`, `corporate_governance`.

**Null-finding rule (prevents citation theatre):** If a mandated section has no material insight on your topic — e.g. no auditor qualifications, only routine related-party flows, or deck outlook has no forward numbers — write one sentence stating that explicitly and cite the section. Example: `"No Key Audit Matters flagged in FY25 AR (source: FY25 AR, auditor_report)."` Silent skipping of a mandated section reads as work-not-done; a clean null-finding is information.

**Degraded extraction:** If a tool response contains `_meta.degraded_quality: true` or `_extraction_quality_warning`, say so in your report and downweight AR/deck-derived claims accordingly. Never fabricate content from a degraded or empty extraction — if the data is missing, note it in Open Questions.

**Cross-year / cross-quarter narrative:** `get_annual_report(section='cross_year')` returns the YoY evolution narrative (risk drift, auditor-signal changes, governance shifts). `get_deck_insights(sub_section='cross_quarter')` returns the quarterly-highlight trajectory. Prefer these for trajectory claims over single-period reads.
```

After inserting: `_SHARED_PREAMBLE_HASH = hashlib.sha256(SHARED_PREAMBLE_V2.encode()).hexdigest()` recomputes automatically on next run. Update the literal hash value in any test snapshot that captures it.

#### 5.3.2 Per-agent INSTRUCTIONS — scoped to the five mandated agents

Each mandated agent gets an explicit workflow step (not merely an anomaly extension). Wording echoes the Risk agent's "must be chased" register (prompts.py:698) applied positively. Keep edits 3-5 lines per agent.

| Agent | File:line | Workflow position | Inject text |
|-------|-----------|-------------------|-------------|
| **Business** | prompts.py:199, after step 2 (business context) | New step 2b | `2b. Call get_annual_report TOC, then drill: section='chairman_letter' (strategy framing), section='mdna' (revenue drivers, segmental narrative), section='segmental' (segment revenue/margin split). Also call get_deck_insights TOC, then sub_section='strategic_priorities' and 'highlights' for the most recent quarter. Cite every AR/deck claim as (source: FY?? AR, <section>) or (source: FY??-Q? deck, <sub_section>). If a section has no material insight, write one sentence stating that explicitly — do not skip silently.` |
| **Financials** | prompts.py:319, inside financial-metrics workflow | New step before anomaly-resolution | `Before writing any margin or cost analysis, call get_annual_report(section='notes_to_financials') (contingent liabilities, impairments, CWIP aging, lease obligations, capital commitments) and section='segmental' (margin-by-segment, capex-by-segment). Call get_deck_insights(sub_section='segment_performance') for latest-quarter segment numbers. Reconcile any margin step-change or working-capital swing against these before flagging as unexplained. Cite as (source: FY?? AR, notes_to_financials) or (source: FY??-Q? deck, segment_performance). Null-findings must still be stated + cited.` |
| **Risk** | prompts.py:698, governance-chase block | Elevate from "chase" to "mandatory read" | `Before finalizing your risk briefing, you MUST read: get_annual_report(section='auditor_report') — Key Audit Matters, qualified opinions, emphasis-of-matter paragraphs, going-concern notes; section='risk_management' — top-risk framework, new risks this year, mitigation quality; section='related_party' — concentration risk, arms-length statements, material RPTs. Auditor KAMs are the single highest-signal governance input available and must appear in every Risk report where a FY AR exists. Cite as (source: FY?? AR, auditor_report). If the auditor opinion is clean and KAMs are routine, write one sentence saying so + cite — a clean null-finding is information, a skipped mandatory section is not.` |
| **Valuation** | prompts.py:575, management-guidance block | New step before DCF assumptions | `Before writing DCF/reverse-DCF assumptions, call get_annual_report(section='mdna') for written forward statements (growth targets, margin guidance, capex plans) and get_deck_insights(sub_section='outlook_and_guidance') for latest-quarter forward numbers. Anchor your reverse-DCF growth/margin to whichever is most recent and stated; flag the gap to sell-side consensus explicitly. Cite as (source: FY?? AR, mdna) or (source: FY??-Q? deck, outlook_and_guidance). If management has given no forward numbers, state that and use concall guidance as fallback — still cite the AR/deck sections you checked.` |
| **Ownership** | prompts.py:459, reclassification-signal block | New mandatory consult step | `Call get_annual_report(section='related_party') to identify RPT-driven flows (intra-group lending, sister-company sales, promoter-entity transactions) that explain concentrated holdings or unusual share movements; and section='corporate_governance' for board independence, committee composition, and director-tenure data that contextualize promoter behaviour and insider patterns. Cite as (source: FY?? AR, related_party) or (source: FY?? AR, corporate_governance). Null-findings still cited.` |

**Sector, News, Technical agents — no change in P1.** Sector already has a clean segmental fallback chain (prompts.py:863-864); News/Technical derive ~no value from AR/deck. Revisit only if evals surface gaps.

**Verifier agent:** Add one line to verifier prompt — "Any `(source: FY?? AR, ...)` or `(source: FY??-Q? deck, ...)` inline citation must be re-fetched via `get_annual_report` / `get_deck_insights` and the quoted content verified against the tool response. Hallucinated section references are a hard fail."

### 5.4 W4 — Sector skills

**Directory: `flow-tracker/flowtracker/research/sector_skills/{sector}/`**

22 sectors × `_shared.md` = 22 files. For each sector, append a new section with 5-8 bullets on sector-specific AR/deck levers. Prioritize:

- **Tier 1 (must have):** bfsi, pharmaceuticals, metals, oil_gas, it_services, auto, real_estate — 7 sectors, highest data-density in AR notes
- **Tier 2 (should have):** fmcg, retail, telecom, chemicals, cement, power, capital_goods — 7 sectors
- **Tier 3 (nice to have):** remaining 8 sectors

**Example — `sector_skills/bfsi/_shared.md` append:**

```markdown
### Annual Report & Investor Deck — BFSI Specifics

- **Asset quality reconciliation**: AR Notes to Accounts (typically Note 9-15 in Indian banks) publishes 5-quarter GNPA/NNPA/PCR with stage-wise classification. This trumps concall summaries for trajectory. Always cross-check PCR composition (provisions vs write-offs) from auditor notes.
- **Capital adequacy detail**: AR Risk Management Report mandates CET-1, Tier-1, CRAR with peer context. Use to validate capital headroom vs loan-book growth.
- **CASA and deposit stickiness**: AR MD&A typically breaks CASA into savings vs current + retail-vs-wholesale deposits. Concalls rarely give this split. Critical for NIM resilience analysis.
- **Related-party exposure**: AR `related_party` section shows intra-group lending (bank → NBFC sister, etc.) — flagged as concentration risk under Risk agent.
- **Auditor KAMs for banks**: Loan classification, ECL model governance, IT/cybersecurity are standard bank KAMs. Non-standard KAMs (e.g. "one-time restructuring", "forensic audit") are red flags.
- **Deck — credit cost trajectory**: Banks typically show rolling 4-quarter credit cost chart in deck. Extract via get_deck_insights(sub_section='charts_described').
```

Apply same template (6-8 bullets) to the other 21 sectors. Reuse `full-sector-skills-buildout.md` (already in plans/) as the sector-inventory source.

**Effort estimate:** 15-20 min per sector × 22 = 5-7 hours. Dispatchable as 3 parallel subagent batches (7-8 sectors each).

### 5.5 W5 — Tests & evaluation

**Unit tests (new):**
- `tests/unit/test_ar_extractor_cache.py` — verify `ensure_annual_report_data` skips cached complete years, re-runs partial years
- `tests/unit/test_deck_extractor_cache.py` — same for deck
- `tests/integration/test_phase0b_ar_deck.py` — mock Screener + Claude, run `ensure_annual_reports` + `ensure_annual_report_data` + `ensure_deck_data`, verify vault JSONs land at expected paths
- `tests/integration/test_mcp_ar_deck_tools.py` — seed vault with fixture JSONs, verify `get_annual_report(symbol, year='FY25', section='auditor_report')` returns the right payload

**Contract test update:**
- `tests/contract/test_tool_schemas.py` — snapshot new V2 registry membership so unintended removals trigger test failure

**CLI smoke:**
- Add `--skip-ar-deck` to `HELP_COMMANDS` in `test_smoke.py`

**Autoeval run (proves the integration works):**

After W1-W4 land, run the existing autoeval loop on 3 sectors × 5 agents each — specifically the Business, Financials, Risk, Valuation, Ownership agents. Compare against pre-integration grades.

```bash
# Baseline (already in autoeval/eval_history for most combinations)
uv run flowtrack research autoeval --progress

# Post-integration runs (fresh grades)
uv run flowtrack research autoeval -a risk --sectors bfsi,pharmaceuticals,metals
uv run flowtrack research autoeval -a business --sectors bfsi,pharmaceuticals,metals
uv run flowtrack research autoeval -a financial --sectors bfsi,pharmaceuticals,metals
uv run flowtrack research autoeval -a valuation --sectors bfsi,pharmaceuticals,metals
uv run flowtrack research autoeval -a ownership --sectors bfsi,pharmaceuticals,metals
```

**Success criterion:** Risk grade ≥ A- on all 3 sectors with auditor_report / related_party citations appearing in ≥80% of reports. No grade regression on any other agent. Autoeval history shows AR/deck-sourced claims in the evidence blocks.

---

## 6. Dependency Graph

```
W1 (pipeline wiring)  ──┐
W2 (tool registries)  ──┼──> W5 (tests + evals)
W3 (prompts)          ──┤
                        │
W3 ──> W4 (sector skills) ──> W5
```

W1, W2, W3 are **fully independent** → dispatch three subagents in parallel on day 1.
W4 starts once W3 lands (sector-skill template references preamble terminology).
W5 runs last. Subagent pool: 3 sector-skill builders (Tier-1 / Tier-2 / Tier-3), 1 test author, 1 eval runner.

---

## 7. Rollout Phases

### Phase 1 — Plumbing + Core Specialists (MVP, 2 days)
- W1 Phase 0b wiring
- W2 tool registry updates (5 agents: Business, Financials, Risk, Valuation, Ownership)
- W3 SHARED_PREAMBLE + 5 agent prompt edits
- W5 core unit + integration tests

**Gate:** `uv run flowtrack research thesis -s HDFCBANK` produces a report where Risk agent cites at least one AR auditor finding and Business agent cites the chairman's letter.

### Phase 2 — Sector Depth (2-3 days)
- W4 Tier-1 sector skills (bfsi, pharma, metals, oil_gas, it_services, auto, real_estate)
- W5 sector-level autoeval pass (5 agents × 3 Tier-1 sectors)

**Gate:** Autoeval grades on Tier-1 sectors match or exceed pre-integration baseline; new sector-specific citations show up in the TSV evidence column.

### Phase 3 — Breadth + Verification (1-2 days)
- W4 Tier-2 and Tier-3 sectors
- Verifier agent prompt update: spot-check AR/deck citations against vault JSON (sample 10 reports)
- Optional: Technical + News prompt edits if evals surface gaps

**Gate:** Full 22-sector coverage; no autoeval regressions; cost per fresh thesis run ≤ $5 (vs ~$1.50 pre-integration); cached re-runs ≤ $1.20.

---

## 8. Testing & Evaluation Plan

### 8.1 Fast unit/integration (CI)
Target <2 min overhead on existing `pytest tests/ -m "not slow"` suite. Mock Claude and Docling; assert only the pipeline wiring and JSON reads.

### 8.2 Golden fixture
Commit a 2-year AR + 4-quarter deck JSON pair for a seeded symbol (`TESTCO`) into `tests/fixtures/golden/ar_deck/`. Agent tool tests read this fixture; no Claude calls in CI.

### 8.3 Live eval (manual)
Before Phase 1 gate, run on three real symbols covering different data-quality profiles:
- **HDFCBANK** — rich AR, quarterly decks, BFSI sector
- **TCS** — rich AR, investor-day decks, IT services
- **ADANIENT** — known-broken concall infra (per memory `project_phase1_complete.md`) — validates graceful fallback when extraction fails

For each, compare pre- and post-integration reports side-by-side. Confirm:
- Risk briefing now includes auditor KAMs or explicit "no qualifications found" statement
- Business briefing cites chairman letter themes
- No hallucinated AR content on ADANIENT (extraction empty → Open Questions block)

### 8.4 Autoeval
As in §5.5. Gate on no regression + target ≥ A- on Risk/Business across Tier-1 sectors.

---

## 9. Cost & Time Budget

### 9.1 Engineering time
- W1 + W2 + W3 (Phase 1): 2 days orchestrated with 3 subagents
- W4 (Phase 2 + 3): 2-3 days, 3 parallel subagent batches
- W5: 1-2 days

**Total: 5-7 engineer-days; 3-4 calendar days with orchestration.**

### 9.2 Compute cost per research run
| Scenario | Pre-integration | Post-integration | Delta |
|----------|-----------------|------------------|-------|
| Fresh symbol, no cache | ~$1.50 (concalls + agents) | ~$5.00 (add AR + deck extraction + richer agent context) | +$3.50 |
| Re-run within 24h | ~$0.80 (agents only) | ~$1.00 (cache hits) | +$0.20 |
| `--skip-ar-deck` | ~$1.50 | ~$1.60 (prompt overhead only) | +$0.10 |

Cost is dominated by one-time extraction. Caches persist indefinitely in vault; repeat runs are near-free.

### 9.3 Wall time per research run
- Fresh AR extraction: ~3-4 min (2 FY × 8 sections sequential with semaphore=2)
- Fresh deck extraction: ~1-2 min (4 quarters, semaphore=3)
- **Added wall time: 4-6 min on first run; <10 sec on cached re-runs**

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Docling OOM/failure on large AR PDFs (>300 pages) | Medium | Medium | Extractor already has pdfplumber fallback + `degraded=True` flag. Surface in _skip. |
| Claude JSON parse failure mid-extraction | Low-Medium | Low | Per-section incremental writes already implemented; partial status preserved. Verifier must check `extraction_status` field. |
| Hallucinated AR citations from agents | Medium | High | Citation format mandated in preamble; verifier agent validates citations against vault JSONs (add this to verifier prompt). |
| Cost spike on cold symbols | Medium | Medium | `--skip-ar-deck` flag; semaphore caps; per-call budget $0.35. Document in CLAUDE.md. |
| Agent picks wrong `year` / `section` | Medium | Low | Tool description lists valid enum values; TOC call returns discovered sections + years. |
| SHARED_PREAMBLE_HASH drift breaks CI | Low | Low | Commit hash + content in same commit; document the two-line change. |
| Screener AR URL link-rot | Medium | Low | `ar_downloader` logs failures; re-runs retry; manual vault drop works as fallback. |
| ADANIENT-style CDN blocks (memory: `project_phase1_complete.md`) | Known | Low | Extractor already catches and returns None → pipeline proceeds. Agents handle "no AR data" gracefully per preamble rule. |
| Verifier grades drop because AR/deck adds more claims to fact-check | Medium | Medium | Expand verifier tool registry to include standalone AR/deck tools; cite-check formally added to verifier prompt. |

---

## 11. Open Questions

1. **Should deck PDFs be auto-downloaded?** Currently decks land in `vault/filings/FY??-Q?/investor_deck.pdf` only if user drops them manually or a separate flow fetches them. Screener tracks `doc_type='concall_ppt'` URLs — is that the same as investor deck, and should we add `ensure_decks_download()` mirroring `ensure_annual_reports()`? (Subagent W1 should confirm.)
2. **BSE filings vs AR source-of-truth.** AR PDFs come from Screener `company_documents`. BSE filings also include AR. Do we need a fallback path for symbols missing from Screener? (Probably fine to defer.)
3. **Cross-year narrative cost.** Cross-year call is ~$0.15 but needs ≥2 complete years. Worth running every research cycle, or only when a new FY is added? Default: only regenerate when new FY completes.
4. **Comparison agent (multi-stock) access.** When Sam vs Bob are compared, do we want auditor-opinion diff surfaced explicitly? That would warrant a small Comparison-agent prompt edit in Phase 3.
5. **Dashboard surfacing (out of scope but related).** Per memory `project_dashboard.md`, user wants a web UI. Once AR/deck data lands in vault JSONs, it's trivially dashboardable. Not this plan's scope.
6. **Full-extraction mode.** `ensure_annual_report_data(..., full=True)` adds `notes_to_financials` + `financial_statements` sections (+~$1.50 per FY). Worth a `--deep-ar` flag for deep-dive research runs?

---

## 12. Definition of Done

### Pipeline
- [ ] `vault/stocks/HDFCBANK/fundamentals/annual_report_v2_FY??.json` exists with `extraction_status == "complete"` for 2 years after a fresh `flowtrack research thesis -s HDFCBANK` run.
- [ ] `vault/stocks/HDFCBANK/fundamentals/deck_extraction_v2.json` contains ≥3 quarters with `extraction_status == "complete"`.
- [ ] Extractors return `_new_years_extracted` / `_new_quarters_extracted` counters; Phase 0b logs show `✓ AR: N new year(s) extracted (M total)` and same for deck.
- [ ] `ensure_annual_report_data(..., industry=_industry)` and `ensure_deck_data(..., industry=_industry)` accept the industry hint; BFSI AR extraction mandates casa/NPA disclosures in segmental output (null with `reason: "not_mentioned"` if absent).

### Tool layer
- [ ] `get_annual_report` and `get_deck_insights` appear in Business, Financials, Risk, Valuation, Ownership V2 registries.
- [ ] Tool first-call responses return compact TOC shape (years_on_file / quarters + sections_populated + cross_*_keys + `_meta`).
- [ ] Degraded extractions emit `_extraction_quality_warning` + `_meta.degraded_quality: true` + `_meta.missing_periods: [...]` matching the concall pattern exactly.

### Prompt layer (mandatory scope)
- [ ] SHARED_PREAMBLE_V2 contains the "Annual Report & Investor Deck — Scoped Mandatory Consult" block; `_SHARED_PREAMBLE_HASH` updated; hash assert at prompts.py:1425 passes on first import.
- [ ] HDFCBANK report contains **≥1 inline `(source: FY?? AR, <section>)` citation in every one of Business, Financials, Risk, Valuation, Ownership briefings** (null-findings count).
- [ ] HDFCBANK report contains **≥1 inline `(source: FY??-Q? deck, <sub_section>)` citation in every one of Business, Financials, Valuation briefings**.
- [ ] Risk briefing on any symbol with AR on file cites `auditor_report` explicitly — either KAMs or a clean null-finding statement.
- [ ] No hallucinated AR/deck citations — verifier agent spot-check passes 10/10 on sampled reports.

### Quality gates
- [ ] `uv run pytest tests/ -m "not slow"` passes (no regressions).
- [ ] Autoeval on 3 Tier-1 sectors × 5 mandated agents shows no grade regression; Risk agent ≥ A- on ≥2 of 3 sectors.
- [ ] Cost per fresh research run ≤ $5; cached re-runs ≤ $1.20.
- [ ] Graceful degradation verified: a symbol with no AR (e.g. recent IPO) produces reports with agents explicitly noting "no AR on file" in Open Questions — no fabricated citations.

### Rollout artifacts
- [ ] Plan committed at `plans/ar-deck-pipeline-integration.md`; qmd-indexed.
- [ ] Memory updated: new `project_ar_deck_integration.md` entry listing which agents/sectors are mandated, extractor version bump (`_v2`), and eval baseline delta.
- [ ] CLAUDE.md (flow-tracker) research-layer section mentions AR/deck alongside concall in the Phase 0b description.

---

## 13. Implementation Task Breakdown (for orchestrator dispatch)

### Parallel batch 1 — dispatch on day 1
- **Task 1.1 — W1 Phase 0b wiring** — edit `research_commands.py:290-310` to add AR download, AR extraction, deck extraction blocks; add `--skip-ar-deck` flag; mirror in `run` command (line 893+).
- **Task 1.2 — W2 Tool registries** — edit `tools.py:2182-2229` to append `get_annual_report`, `get_deck_insights` to Business/Financials/Risk/Valuation/Ownership V2 registries.
- **Task 1.3 — W3 SHARED_PREAMBLE** — edit `prompts.py:158-163` to insert AR/deck consult block, recompute hash, update assert at line 1425.

### Sequential on W3 — dispatch on day 1 after 1.3 lands
- **Task 2.1 — Business agent prompt** — edit `prompts.py:199` area.
- **Task 2.2 — Financials agent prompt** — edit `prompts.py:319`.
- **Task 2.3 — Ownership agent prompt** — edit `prompts.py:459`.
- **Task 2.4 — Valuation agent prompt** — edit `prompts.py:575`.
- **Task 2.5 — Risk agent prompt** — edit `prompts.py:698`.
- **Task 2.6 — Sector agent prompt** — edit `prompts.py:876`.

Tasks 2.1-2.6 are **independent** (different line regions, same file — dispatch as one subagent handling all six to avoid merge churn).

### Parallel batch 2 — dispatch on day 2 after W3 + W1 complete
- **Task 3.1 — Sector skills Tier-1** — 7 sectors × append ~40-line AR/deck block to `_shared.md`.
- **Task 3.2 — Tests** — unit tests for cache skipping, integration for Phase 0b, MCP tool fixtures.
- **Task 3.3 — Autoeval smoke** — run 1 sector (bfsi) × 5 agents to validate before full eval.

### Parallel batch 3 — dispatch on day 3
- **Task 4.1 — Sector skills Tier-2 + Tier-3** — 15 sectors.
- **Task 4.2 — Full autoeval** — 3 Tier-1 sectors × 5 agents, grade comparison.
- **Task 4.3 — Verifier prompt update** — teach verifier to spot-check AR/deck citations against vault JSONs.

### Verification (owner: orchestrator, after each batch)
- Run full test suite: `uv run pytest tests/ -m "not slow"` → ≤2min, all green.
- Eyeball a HDFCBANK report: confirm AR/deck citations present, no hallucinated content.
- `grep` autoeval results TSV for AR/Deck-derived evidence tokens.

---

## Appendix A — Data Schema Summary (reference)

### Annual Report per-FY JSON (`annual_report_FY??.json`)
Top-level: `symbol`, `fiscal_year`, `source_pdf`, `pages_chars`, `extraction_status`, `extraction_date`, `_docling_cached`, `_docling_degraded`.

10 sections (8 default + 2 opt-in `full=True`):
`chairman_letter`, `mdna`, `risk_management`, `auditor_report`, `corporate_governance`, `brsr`, `related_party`, `segmental`, `notes_to_financials`, `financial_statements`.

### Annual Report Cross-Year (`annual_report_cross_year.json`)
`symbol`, `years_analyzed`, `extraction_date`, `narrative{key_evolution_themes[], risk_evolution, auditor_signals, governance_changes, rpt_evolution, strategic_framing_shift, capital_allocation_shifts, biggest_positive_development, biggest_concern, what_to_watch_next_fy[]}`.

### Investor Deck (`deck_extraction.json`, list of quarters newest-first)
Per quarter: `fy_quarter`, `period_ended`, `highlights[]`, `segment_performance{}`, `strategic_priorities[]`, `outlook_and_guidance`, `new_initiatives[]`, `charts_described[]`, `slide_topics[]`, `extraction_status`.

Full schema details: see W1 exploration report (subagent output embedded in conversation 2026-04-18).

---

## Appendix B — Strongest AR/Deck Section Map (reference)

| Agent | AR primary | AR secondary | Deck primary |
|-------|-----------|--------------|--------------|
| Business | `chairman_letter`, `mdna` | `segmental` | `strategic_priorities`, `highlights` |
| Financials | `notes_to_financials`, `segmental` | `mdna` | `segment_performance` |
| Ownership | `related_party`, `corporate_governance` | `chairman_letter` | — |
| Valuation | `mdna` | `segmental`, `financial_statements` | `outlook_and_guidance` |
| Risk | `auditor_report`, `risk_management` | `related_party`, `corporate_governance` | — |
| Sector | `segmental` | `mdna` | `strategic_priorities`, `charts_described` |
| Technical (not in P1) | — | `financial_statements` (trend) | `charts_described` |
| News (not in P1) | — | — | `new_initiatives` |

---

**End of plan.**
