# Docling Document Pipeline — Decks + Annual Reports

**Status:** Scoped, pending approval
**Tier:** Medium (~4-6 days, parallel-dispatchable)
**Driver:** Unlock deck + AR content that today sits as PDFs in the vault, unread. Extends the proven `concall_extractor.py` pattern to two more sources.
**Spike evidence:** `plans/archive/docling-spike-results.md` (to be created) — Docling hits 97.9% financial-doc benchmarks; real tests on BAJAJFINSV deck (303 headings, 36 tables), INDIAMART AR (1,478 headings), VEDL AR (2,977 headings, 10.7min for 360pp).

---

## 1. Design Principles

### 1.1 Three complementary sources, not substitutes

| Source | Cadence | Best for | Current state |
|---|---|---|---|
| **Concall** | Quarterly | Forward guidance, unscripted reveals, analyst pushback, tone | ✅ Shipped (pdfplumber + Claude extraction + TOC + qa_topics drill) |
| **Deck** | Quarterly (+ events) | Polished charts, segment trends, KPI framing, strategic narrative | ❌ PDFs downloaded, not extracted |
| **Annual report** | Yearly | Auditor opinion & KAMs, contingent liabs, RPTs, Board comp, BRSR, detailed notes, segment accounting | ❌ URLs tracked, PDFs not downloaded |

**Key insight:** An agent asking "what's the margin outlook?" should read the concall (mgmt said) AND the deck (chart shows 5yr trend). An agent asking "any auditor red flags?" goes only to AR. No single source answers every question.

### 1.2 Access model — unified discovery + specialized drill

Reject monolithic `get_company_documents(source=...)` — schemas differ too much.
Reject intent-based router (`get_commentary(topic=...)`) — too much magic, hard to debug.

Adopt **two-layer pattern:**

- **Layer 1 (discovery):** `get_documents_toc(symbol)` — one small call, returns unified index:
  ```json
  {
    "concalls": [{"quarter": "FY26-Q4", "has_qa_topics": true, "size_kb": 12}, ...],
    "decks":    [{"quarter": "FY26-Q4", "slides": 27, "has_segments": true}, ...],
    "annual_reports": [{"year": "FY25", "sections": ["mdna","risk","auditor","cg","brsr","notes","segmental"], "size_mb": 3.2}, ...],
    "routing_hint": "For margins question → concall + deck. For governance → AR."
  }
  ```
- **Layer 2 (drill):** source-specific tools (already shipped for concall; build for deck + AR):
  - `get_concall_insights(symbol, quarter?, section_filter?, qa_topics?)` — done
  - `get_deck_insights(symbol, quarter?, section_filter?, slide_topics?)` — new
  - `get_annual_report(symbol, year?, section?, sub_section?)` — new

### 1.3 Agent routing — make it explicit in prompts

Add a short routing table to every specialist prompt. Draft below; refine per-specialist.

| Information need | Primary | Secondary | Avoid |
|---|---|---|---|
| Forward guidance | concall Q&A + mgmt_commentary | deck outlook slide | AR (too stale) |
| 5yr segment revenue trend | deck segmental slide | AR segment reporting | concall |
| Auditor opinion / KAMs | AR auditor section | — | — |
| Contingent liabilities trend | AR notes (contingent_liab) | — | deck (usually silent) |
| RPT / related party | AR notes (rpt) | concall if flagged | — |
| Board composition / ESG | AR corp_gov + brsr | deck ESG slide | concall |
| Sector-specific KPIs | deck segmental + AR segment | concall operational_metrics | — |
| Management credibility | cross-quarter concall narrative | — | — |
| Competitive positioning | concall Q&A | deck strategy slide | — |

### 1.4 Don't re-extract concalls with Docling

Spike showed Docling formats transcripts as a wide speaker-turn table — worse for Claude than raw prose. Concall pipeline stays on pdfplumber. Only new sources use Docling.

---

## 2. Data Architecture

### 2.1 Vault layout

```
~/vault/stocks/{SYMBOL}/
  filings/FY??-Q?/concall.pdf             # existing, unchanged
  filings/FY??-Q?/investor_deck.pdf       # existing, download pipeline active
  filings/FY??/annual_report.pdf          # NEW — year-keyed, not quarter
  filings/FY??-Q?/_docling.md             # NEW — cached Docling markdown (deck)
  filings/FY??/_docling.md                # NEW — cached Docling markdown (AR)
  filings/FY??-Q?/_heading_toc.json       # NEW — cached heading index
  filings/FY??/_heading_toc.json          # NEW

  fundamentals/concall_extraction_v2.json    # existing
  fundamentals/deck_extraction.json          # NEW — all quarters, same shape as concall
  fundamentals/annual_report_FY??.json       # NEW — per year (separate files)
```

### 2.2 Two-pass extraction

**Pass 1 — Docling (free, local, cached):**
- PDF → markdown + heading TOC
- Runs once per PDF, cached to `_docling.md` + `_heading_toc.json`
- Skip if cache is newer than source PDF mtime
- Cost: CPU time only. Deck ~60-90s. AR ~6-15min.

**Pass 2 — Claude structured extraction (paid, cached):**
- Reads `_docling.md`, sections it by TOC, sends structured-output schema to Claude Sonnet 4.6
- Runs once per PDF, cached to JSON
- For ARs: default extract MD&A + Risk + Auditor only (~3 sections × 10-20KB). Heavy sections (Notes 400KB+) extracted lazily when agent requests.
- Skip if JSON cache is newer than markdown cache.

### 2.3 Schemas

**Deck schema (`deck_extraction.json`):**
```json
{
  "symbol": "ABLBL",
  "quarters": [
    {
      "fy_quarter": "FY26-Q4",
      "source_pdf": ".../investor_deck.pdf",
      "extraction_status": "complete",
      "highlights": ["bullet points from 'Q3 HIGHLIGHTS' slide"],
      "segment_performance": {
        "<segment_name>": {
          "revenue_cr": "...",
          "growth_yoy_pct": "...",
          "margin_pct": "...",
          "key_drivers": "..."
        }
      },
      "strategic_priorities": ["..."],
      "outlook_and_guidance": "mgmt narrative from outlook slide",
      "new_initiatives": ["..."],
      "charts_described": [
        {"slide_title": "...", "what_it_shows": "...", "key_takeaway": "..."}
      ],
      "slide_topics": ["strategy", "segmental", "outlook", "governance", ...]
    }
  ],
  "cross_quarter_narrative": { /* similar to concall */ }
}
```

**Annual report schema (`annual_report_FY25.json`):**
```json
{
  "symbol": "VEDL",
  "fiscal_year": "FY25",
  "source_pdf": ".../annual_report.pdf",
  "pages": 360,
  "chairman_letter": {"summary": "...", "key_themes": [...], "capital_allocation_signals": "..."},
  "mdna": {
    "industry_overview": "...",
    "company_performance": "...",
    "segmental_review": {"<segment>": "..."},
    "outlook": "...",
    "risks_mentioned": [...]
  },
  "risk_management": {
    "top_risks": [{"risk": "...", "mitigation": "...", "rank": 1}],
    "framework_notes": "..."
  },
  "auditor_report": {
    "opinion": "unqualified|qualified|adverse|disclaimer",
    "emphasis_of_matter": [...],
    "key_audit_matters": [{"matter": "...", "how_addressed": "..."}]
  },
  "corporate_governance": {
    "board_size": 10,
    "independent_directors_pct": 60,
    "committee_structure": {...},
    "director_changes": [...],
    "board_evaluation_findings": "..."
  },
  "brsr": { /* 9-pillar ESG structure */ },
  "notes_to_financials": {
    "contingent_liabilities_cr": "...",
    "rpt_summary": {...},
    "cwip_cr": "...",
    "segment_reporting": {...},
    "employee_benefits": "...",
    "deferred_tax": "..."
  },
  "sector_specific": { /* metals: reserves+production; banks: loan book split, etc. */ },
  "_heading_toc": { /* full TOC preserved for lazy drill */ }
}
```

### 2.4 Size budget per call

| Payload | Target size | Why |
|---|---|---|
| `get_documents_toc` | <4KB | First-call discovery, cheap |
| Deck TOC (no section) | <4KB | Mirrors concall TOC |
| Deck full section | 8-15KB | Same bands as concall |
| AR TOC | <6KB | Bigger doc, more sections to list |
| AR single section (MD&A, Risk) | 10-20KB | Comfortable for agent |
| AR heavy section (Notes) | split into sub-sections; each <20KB | Don't breach 30KB MCP ceiling |

---

## 3. Agent Integration

### 3.1 Tool registry changes

**Existing tools (no change):** `get_concall_insights`, `get_sector_kpis`

**New MCP tools:**
- `get_documents_toc(symbol)` — unified discovery
- `get_deck_insights(symbol, sub_section?, quarter?, slide_topics?)`
- `get_annual_report(symbol, year?, section?, sub_section?)`

**Per-specialist access — symmetric with concall:**

The existing concall tool is exposed to all 7 specialist registries (Business, Financials, Ownership, Valuation, Risk, Sector, Technical) via `tools.py` and also routed through `get_company_context(section='concall_insights')`. **Deck and AR tools get the exact same treatment — all 7 registries, same routing.** Whether each agent actually calls them is a prompt/routing question, not a capability one. Cost of giving everyone all three is zero (tool slots are free; uncalled tools have no effect).

### 3.2 Prompt additions

Add to `prompts.py` shared preamble (keep it short — agents already overflowing):

```markdown
## Document sources

Three complementary sources. Start every company analysis with `get_documents_toc(symbol)` to see what's available.

1. **Concall (quarterly, last 4Q):** `get_concall_insights` — forward guidance, mgmt commentary, analyst Q&A. Pass `qa_topics=['margins','capex',...]` to filter Q&A by topic. Pass `quarter='FY26-Q3'` to narrow.
2. **Deck (quarterly):** `get_deck_insights` — polished charts, segment trends, KPI framing. Complements concall — same quarter, different angle.
3. **Annual report (yearly, last 3Y):** `get_annual_report` — auditor opinion & KAMs, contingent liabilities, RPTs, Board composition, BRSR, detailed notes, segmental accounting. Unique data not in concall/deck.

Default routing: use concall+deck for quarterly narrative; use AR for governance, auditor, notes, and annual segmental.
```

Per-specialist prompts get a 1-line routing hint (e.g., Risk agent: "Prefer AR risk_mgmt + auditor sections over concall flags for material risks.").

### 3.3 Verification agents

Verification agents get `get_documents_toc` + the same tools as their specialist. They cross-check source claims — if the Financials specialist cites a contingent liability number, the verifier reads AR notes to confirm.

---

## 4. Implementation Breakdown

Tasks grouped by parallelizable clusters. Dependency arrows (→) between clusters.

### Cluster A — shared infrastructure (foundation for everything else)

| # | Task | Files | Verify |
|---|---|---|---|
| A1 | Add `docling` to `pyproject.toml`, run `uv sync` | `flow-tracker/pyproject.toml` | `uv run python -c "from docling.document_converter import DocumentConverter"` |
| A2 | Build `doc_extractor.py` — single `extract_to_markdown(pdf, cache_dir) -> (md_text, toc)`. Handles Docling invocation, mtime-based caching, error fallback to pdfplumber + warning. | `flow-tracker/flowtracker/research/doc_extractor.py` (new) | Unit test: small fixture PDF in → markdown + ≥1 heading out |
| A3 | Build `heading_toc.py` — parses markdown headings, computes `{canonical_section_name: (char_start, char_end, page_hint)}` using a canonical-name dictionary with fuzzy matching. Export `build_toc(md_text) -> dict` + `slice_section(md_text, toc, section) -> str`. | `flow-tracker/flowtracker/research/heading_toc.py` (new) | Unit test: 3 synthetic markdown fixtures (deck, AR, messy AR) |

### Cluster B — deck pipeline (depends on A) — parallel with C

| # | Task | Files | Verify |
|---|---|---|---|
| B1 | `deck_extractor.py` — mirrors `concall_extractor.py` pattern. Find deck PDFs, invoke A2, feed markdown to Claude Sonnet with deck-specific schema, write `deck_extraction.json`. | `flow-tracker/flowtracker/research/deck_extractor.py` (new) | Extract ABLBL FY26-Q4 deck end-to-end; JSON has ≥1 populated segment |
| B2 | CLI command `flowtrack filings extract-deck -s SYMBOL` | `flow-tracker/flowtracker/filing_commands.py` | `--help` shows the command; one real run succeeds |
| B3 | `data_api.get_deck_insights(symbol, section_filter?, quarter?, slide_topics?)` — pattern-identical to `get_concall_insights` | `flow-tracker/flowtracker/research/data_api.py` | Unit tests mirroring the concall TOC/drill/filter suite |
| B4 | MCP tool `get_deck_insights` in `tools.py`; add to Business, Financials, Valuation, Sector specialists' tool lists | `flow-tracker/flowtracker/research/tools.py` | Tool tests for TOC + drill + slide_topics filter |
| B5 | Un-disable deck download path in `concall_extractor._find_supplementary_pdfs()` (lines 367-413). Verify downloads land correctly. | `flow-tracker/flowtracker/research/concall_extractor.py` | Run refresh for ABLBL, confirm deck arrives in vault |

### Cluster C — AR pipeline (depends on A) — parallel with B

| # | Task | Files | Verify |
|---|---|---|---|
| C1 | Build `ar_downloader.py` — read `company_documents` table rows where `doc_type='annual_report'`, download to `~/vault/stocks/{SYMBOL}/filings/FY??/annual_report.pdf`. Respect BSE UA headers (see concall download pattern). | `flow-tracker/flowtracker/research/ar_downloader.py` (new) | Download INDIAMART FY25 AR; file exists on disk |
| C2 | `annual_report_extractor.py` — heaviest new module. Uses A2 + A3 → sections markdown → Claude extracts to schema in §2.3. Default extracts `mdna + risk_mgmt + auditor + corporate_governance + brsr`; skips `notes` and `financial_statements` unless `--full`. | `flow-tracker/flowtracker/research/annual_report_extractor.py` (new) | Full run on VEDL FY25; JSON has ≥5 populated top-level sections |
| C3 | CLI command `flowtrack filings extract-ar -s SYMBOL --year FY25 [--full]` | `flow-tracker/flowtracker/filing_commands.py` | CLI succeeds end-to-end on INDIAMART |
| C4 | `data_api.get_annual_report(symbol, year?, section?, sub_section?)` — year is NOT a quarter; section filter works on top-level schema keys. `get_annual_report_toc` returns available years + sections per year. | `flow-tracker/flowtracker/research/data_api.py` | Unit tests: TOC across years, year filter, section drill, missing-year error |
| C5 | MCP tool `get_annual_report` in `tools.py`; add to Business, Financials, Ownership, Risk, Sector | `flow-tracker/flowtracker/research/tools.py` | Tool tests |
| C6 | Sector-specific AR schema extensions — for BFSI (loan book composition, provision coverage, slippage), for metals (reserves+resources, production by metal, stripping ratio), for IT (top-client conc, utilization) | `flow-tracker/flowtracker/research/annual_report_extractor.py` + `sector_kpis.py` | Run on 1 stock per sector; sector-specific keys populated |

### Cluster D — unified discovery (depends on B3 + C4)

| # | Task | Files | Verify |
|---|---|---|---|
| D1 | `data_api.get_documents_toc(symbol)` — queries all three caches, returns unified index with `routing_hint` field | `flow-tracker/flowtracker/research/data_api.py` | Returns <4KB JSON with all three source sections populated |
| D2 | MCP tool `get_documents_toc` in `tools.py`; add to ALL specialists + all verifiers | `flow-tracker/flowtracker/research/tools.py` | Tool test returns unified structure |
| D3 | Update `prompts.py` shared preamble with §3.2 routing block; add per-specialist 1-line hints where relevant | `flow-tracker/flowtracker/research/prompts.py` | Diff review; run 1 specialist end-to-end, confirm it calls TOC first |

### Cluster E — ops (depends on B, C) — minimal, on-demand only

**No backfill and no cron.** Extraction is lazy — triggered per stock via the CLI when the user (or an agent pipeline) needs that source. Matches the concall pattern (`flowtrack filings extract` is user-triggered, not scheduled).

| # | Task | Files | Verify |
|---|---|---|---|
| E1 | Ensure `refresh_for_research()` downloads deck PDFs alongside concalls (not extract — just download so they're on disk when needed) | `flow-tracker/flowtracker/research/refresh.py` | Dry-run on ABLBL; deck PDFs land in vault |
| E2 | Ensure `refresh_for_research()` downloads the current FY's annual report PDF when URL is known (same — download only) | `flow-tracker/flowtracker/research/refresh.py` | Dry-run on INDIAMART; AR PDF lands in vault |
| E3 | `flowtrack research thesis` shows a "⚠ deck not extracted for this quarter" / "⚠ AR not extracted for FY25" warning at start of run when PDFs exist but extractions don't. User can then opt-in via `--extract-docs` flag or separate CLI. | `flow-tracker/flowtracker/research/agent.py` + CLI | Manual smoke test |

**Explicitly rejected:** cron-based batch extraction of decks/ARs across Nifty 250. The concall pipeline already has this pattern for quarterlies; we're following the *explicit, on-demand* side of it for the new sources. If the user wants a batch cron later, it's a one-line addition to `quarterly-results.sh` / a new `yearly-ar-extract.sh` — can be added when usage justifies it.

### Cluster F — eval + polish (after B, C, D land)

| # | Task | Files | Verify |
|---|---|---|---|
| F1 | Run autoeval for 2 specialists (Risk + Financials) on 3 stocks each, comparing pre-Docling vs post. Gemini-graded. Target: no regression, ≥1 tick improvement on at least one rubric. | `flow-tracker/flowtracker/research/autoeval/` | Grades table saved |
| F2 | Update CLAUDE.md project architecture section to mention the three-source model | `flow-tracker/CLAUDE.md` | Diff review |
| F3 | Memory: save project memory noting "three-source model operational" + the routing hint table | `~/.claude/projects/-Users-.../memory/` | Memory file exists |

---

## 5. Cost Model

**No backfill.** Extraction runs per-stock-per-quarter (deck) or per-stock-per-year (AR) only when the user explicitly triggers it for a stock they're researching. Matches the existing concall flow — you decide which stocks get expensive extraction.

### 5.1 Per-extraction marginal cost

| Source | Docling CPU | Claude Sonnet extraction | Per-call $ |
|---|---:|---:|---:|
| 1 deck (~30pp) | 60-90s | 3-5 agent turns at $0.30 | **~$0.30** |
| 1 AR default sections (MD&A + Risk + Auditor + CG + BRSR, ~60pp out of ~300) | 6-15min | 5-8 agent turns at $2.00 | **~$2.00** |
| 1 AR with Notes/FS (full) | 15-30min | 10-15 agent turns at $3.00 | **~$5.00** |

A typical research session (1 stock) costs a one-time **~$0.30-5** in extraction, amortised over every future research run on that stock (cached JSON).

### 5.2 Realistic monthly cost

If you research ~20 new stocks per month and extract decks/ARs for each:
- 20 deck extractions × $0.30 = **$6/month**
- 20 AR extractions (light) × $2.00 = **$40/month**
- Heavy-section top-ups: **<$20/month**
- **Total: ~$65/month** for typical usage

### 5.3 Comparison with alternatives

- **LlamaParse:** $0.003/page, no Docling step needed. For a typical AR (~300pp) = $0.90/AR just parsing. Docling does it free. Scratched.
- **LLM vision on all pages:** ~$0.05/page × 300pp = $15/AR. Scratched — Docling gets text structure free.

---

## 6. Failure Modes + Mitigations

| Risk | Mitigation |
|---|---|
| Docling crashes on malformed PDF | try/except per-PDF; fall back to pdfplumber with `_extraction_degraded: true` flag; never block the pipeline |
| Memory blow-up on huge ARs (HDFCBANK 600+pp) | Docling supports page-range; for any AR >400pp, process in 100-page chunks and concatenate |
| Heading detection misses on scanned PDFs | Canonical-section fuzzy matcher in `heading_toc.py` falls back to regex on known phrases ("Independent Auditor's Report", "Notes to the Financial Statements") |
| Token limit on very large sections | Section-aware chunker before Claude call; emit multiple extraction passes if section >80KB, merge JSON |
| Cost blowout on re-extraction | Mandatory cache checks on mtime + content hash; CI test that re-runs extractor on same PDF twice and asserts the second is a cache hit |
| Schema drift over quarters | Pydantic schema + syrupy snapshot tests per sector; CI fails if shape changes unintentionally |
| Wrong section-name mapping (e.g., "MD&A" vs "Management Discussion and Analysis") | Canonical dictionary with 5-10 aliases per section; fuzzy-matched at TOC build time; logged when an AR lands in an unknown section |
| Agent calls `get_concall_insights` when AR would be right | Routing hints in prompt; verifier agent catches missed cross-source references in its audit pass |
| ASTRAZEN-style mis-taxonomy (file named investor_deck but is a 2pp letter) | Page-count guard: if PDF has <5 pages, skip deck extraction and log; treat as corporate action notice |

---

## 7. Test Plan

### 7.1 Unit

- `test_doc_extractor.py` — Docling on a 2-page fixture PDF (committed); cache hit on second call; fallback path triggers on corrupt PDF
- `test_heading_toc.py` — canonical section matching (happy path + aliases + unknown section fallback); section slicing preserves content; offset math correct
- `test_deck_extractor.py` — mock Claude; pipeline reads markdown + returns schema-valid JSON
- `test_ar_extractor.py` — same; plus sector-specific extension hooks
- `test_data_api_docs.py` — three-source TOC shape; cross-source routing hint present

### 7.2 Integration

- Real-PDF test on ABLBL FY26-Q4 deck (5-8pp committed fixture): assert JSON has populated segments
- Real-PDF test on a small AR fixture (~30 pages, committed): assert MD&A + Risk + Auditor extracted
- `get_documents_toc` returns unified index when all 3 sources present; graceful when only 1 or 2 present

### 7.3 E2E / Eval

- Run Risk specialist on VEDL with + without AR tools. Gemini-graded. Expect ≥0.5-tick improvement on "specific risk identification" rubric.
- Run Financials specialist on INDIAMART with + without AR tools. Expect improvement on "contingent liabilities / RPT coverage" dimension.

### 7.4 Smoke

- `flowtrack filings extract-deck -s ABLBL` — end-to-end, JSON lands in vault
- `flowtrack filings extract-ar -s INDIAMART --year FY25` — end-to-end
- `flowtrack research thesis -s VEDL` — full pipeline with new tools; look at final report, confirm it cites AR content

---

## 8. Rollout Phases

**Phase 1 — Cluster A (shared infra).** Small PR. Ships the foundation — Docling wrapping + heading TOC module. Zero user-facing change.

**Phase 2 — Cluster B (decks).** Dedicated PR. Ships deck extraction + `get_deck_insights` tool. Agents can see decks. Measurable: re-run 1 specialist eval, confirm no regression.

**Phase 3 — Cluster C (ARs).** Dedicated PR. The biggest change. Ships AR downloader + extractor + `get_annual_report` tool. Default extraction is light (MD&A + Risk + Auditor + CG + BRSR). Notes stays lazy.

**Phase 4 — Cluster D (unified discovery).** Small PR. `get_documents_toc` + prompt updates. Agents start with one call, understand what's available.

**Phase 5 — Cluster E (ops).** Cron + backfill script. Runs overnight.

**Phase 6 — Cluster F (eval).** Measure lift. If Risk or Financials specialists don't show improvement with AR access, revisit routing hints / prompt integration.

---

## 9. What Stays Out of Scope

- **Concall re-parsing with Docling.** Spike showed it worsens transcript readability. Keep pdfplumber.
- **Image/chart OCR via LLM vision.** Charts get heading-proximal captions via Docling but not transcribed. Defer — most signal is in the tabular data we DO get.
- **AR Notes extraction by default.** Too expensive, low read rate. Lazy-only.
- **Old AR backfill beyond 3 years.** Diminishing returns; most research needs last 2-3 FYs.
- **Cross-company AR querying.** No vector search yet. Each call is symbol-scoped.
- **Quarterly results.pdf extraction.** Screener already provides structured quarterly data. PDF is backup.

---

## 10. Decision Log

| Decision | Alternative | Why this choice |
|---|---|---|
| Two-layer access (TOC + drill) | Single mega-tool | Source schemas differ too much to merge cleanly |
| Three separate MCP tools | One `get_docs(source=...)` | Explicit tool names guide agent behavior; schemas live with their tools |
| Docling (OSS) | LlamaParse (SaaS) | Cheaper at our scale ($0 vs $1,500 backfill), no cloud dep, comparable quality on financial docs |
| Light AR extraction default | Full extraction | Cost: $500/yr vs $2,000/yr; lazy for Notes preserves flexibility |
| Keep concalls on pdfplumber | Switch to Docling | Spike proved Docling worsens transcripts; zero upside |
| Year-keyed AR files (`FY25/annual_report.pdf`) | Quarter-keyed | ARs are annual. Don't force quarter dir structure. |
| 3-year AR backfill | Full history | >3Y has diminishing thesis value; cost/benefit breakeven |

---

## 11. Resolved Decisions

Per user 2026-04-17:

1. ~~Backfill budget~~ → **No backfill.** Extraction is on-demand per stock. CLI-triggered, matching existing concall pattern.
2. ~~Which specialists get AR access?~~ → **All 7, same as concall.** Symmetric access; agent behavior is a prompt/routing concern, not a registry concern.
3. ~~Backfill batching~~ → n/a (no backfill).
4. ~~Cron trigger month~~ → n/a (no cron initially; can be added later once usage patterns are known).

**Still open:**

- **Sector-specific AR hooks** (Cluster C6) — build alongside C2-C5, or defer to a follow-up PR after vanilla AR extraction is validated? Recommendation: **defer**. Ship vanilla AR first; add sector hooks in a follow-up PR once we see what agents actually pull and what's missing.
