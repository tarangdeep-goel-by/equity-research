# Macro Research Agent — Implementation Plan

**Status:** Ready to execute
**Date:** 2026-04-18
**Tier:** Medium (new agent, cross-cutting: prompts + agent.py + synthesis + assembly + tools + tests)
**Owner:** tarang

---

## 1. Motivation

Current 8-agent pipeline is **bottom-up** — every specialist analyzes the company in isolation. The only macro-like coverage today:

- **Sector agent** — industry structure + KPIs, one-step-up from the stock
- **News agent** — last 90 days of stock-specific events
- **Web research agent** — reactive question-resolver for open questions

None of these build a **world → industry → company** view of secular tailwinds and cyclical setup. A stock-picking thesis without a macro check misses the most important attribution buy-side shops run (Fisher: 70% allocation / 20% sector / 10% stock). Without it, Synthesis can produce a high-conviction BUY on a rate-sensitive stock at the top of a hiking cycle without flagging the regime risk.

**What we want:** a dedicated Macro Agent that runs parallel to News, uses WebSearch/WebFetch only, and feeds Synthesis a "macro backdrop" section with explicit *why now* framing.

## 2. Goals & non-goals

**Goals**
- Distinct secular (>5yr) vs cyclical (<3yr) attribution with capital-cycle check (Marathon)
- India-first transmission: every global signal routed through INR earnings channels
- Per-claim citation with `[source-url, as-of YYYY-MM-DD]`
- Forced bull/bear dialectic before closing (TradingAgents pattern)
- Feed synthesis as a distinct "Macro backdrop" section before the verdict
- ≤$0.60 per run, ≤25 turns

**Non-goals**
- Macro forecasting or rate calls (we report regime, not predictions)
- Replacing the Sector agent (sector owns industry structure; macro owns cross-industry forces)
- Investment opinions (macro feeds synthesis; synthesis decides)
- MCP tool access (intentionally web-only; keeps scope contained)
- Per-sector sector skills initially (macro is cross-industry by nature; can add later if needed)

## 3. Prior art (verified via web research — see agent report)

| System | What to steal |
|---|---|
| **TradingAgents** (arXiv 2412.20138) | Parallel-to-fundamentals slot; Bull/Bear researcher debate before synthesis; explicit look-ahead prevention (date-stamped inputs) |
| **FinRobot** (arXiv 2405.14767) | Financial-CoT scaffold: *decompose → drivers → quantify → aggregate → confidence* |
| **AlphaSense Industry Primers** | Scaffold: *players → supply → macro → impact* — clean four-part output |
| **Perplexity Finance** | Per-claim primary-source citation discipline |
| **Marathon capital-cycle** (Chancellor) | Secular-vs-cyclical test — "is capacity being added?" |
| **PESTLE-lite + Damodaran top-down** | Political / Economic / Social / Tech / Legal / Env → discount-rate transmission |

Two documented LLM failure modes to defend against:
- **Temporal grounding drift** (arXiv 2511.18394, 2504.14765) — 25–35% accuracy drop on relative-time queries. Mitigate: inject `today = YYYY-MM-DD` and require per-claim dates.
- **Fluent confidence** (CFA Institute analysis of Claude prompt leak, 2025) — Claude delivers confidently unless explicitly told to hedge. Mitigate: explicit "Unknown" permission + required gap section.

## 4. Agent design

### Persona
Global macro strategist at an Indian PMS. Translates world regimes → India-specific earnings transmission. Strict on secular-vs-cyclical. Never offers investment opinions — feeds Synthesis.

### Mission
Given a symbol + industry context, produce a structured macro brief covering (1) current global regime, (2) secular forces relevant to the stock's industry, (3) cyclical setup, (4) India transmission channels, (5) sector implications, (6) bull/bear dialectic, (7) confidence + gaps.

### Tools
- `WebSearch` and `WebFetch` only (same contract as web_research)
- **No MCP tools** — keeps the agent bounded and independent of DB state
- Baseline context (industry, market cap, sector tags) still injected via `_build_baseline_context()`

### Output structure (seven sections)

```markdown
## 1. Global Regime Snapshot (as of {today})
- Rates/liquidity: Fed / ECB / RBI stance + last move date
- USD/INR + commodity regime (crude, gold, industrial metals)
- Growth pulse: global PMI, China, US, India GDP nowcast
Each line: FACT: <claim> [source-url, as-of YYYY-MM-DD]

## 2. Secular Forces (5-10yr horizon)
For EACH force relevant to the company's industry:
- **Force name** (e.g., China+1, energy transition, AI capex)
- Mechanism: how it drives revenue/cost/demand
- Capital-cycle check: is capacity being added? If yes, secular claim weakens.
- Indian sectors affected
- Tag: SECULAR

## 3. Cyclical Setup (6-24 months)
- Rate cycle position (early/mid/late hiking/cutting)
- Credit cycle (tight/neutral/loose)
- Earnings cycle (accelerating/peaking/decelerating)
- Commodity cycle (where relevant to stock)
- Tag: CYCLICAL

## 4. India Transmission
How global regime translates to INR earnings:
- Input cost channel (crude, metals, coal, chem inputs)
- Demand channel (exports, domestic disposable income)
- Liquidity channel (FII flows, INR stability, yields)
- Fiscal channel (capex, PLI, subsidies, tax)

## 5. Sector Implications
- Ranked list of sectors with macro-driven tailwind/headwind
- Explicit link to company under review

## 6. Bull Case / Bear Case (forced dialectic)
Bull: macro conditions that would accelerate the thesis
Bear: macro conditions that would break the thesis

## 7. Confidence & Gaps
- Data points verified: N
- Data points Unknown: list them
- What would need to be monitored to update this view
```

### Structured briefing (machine-readable)
```json
{
  "agent": "macro",
  "symbol": "<SYMBOL>",
  "as_of": "<YYYY-MM-DD>",
  "regime_state": {
    "rate_cycle": "early_hiking|mid_hiking|peak|early_cutting|mid_cutting|neutral",
    "growth_pulse": "accelerating|steady|decelerating",
    "commodity_regime": "inflationary|disinflationary|mixed",
    "inr_regime": "strengthening|stable|weakening"
  },
  "secular_tailwinds": [
    {"name": "<force>", "mechanism": "<channel>", "capital_cycle_check": "<add/stable/cut>", "confidence": "high|medium|low"}
  ],
  "secular_headwinds": [...],
  "cyclical_stage": "early|mid|late",
  "india_transmission": {
    "input_cost": "tailwind|headwind|neutral",
    "demand": "...",
    "liquidity": "...",
    "fiscal": "..."
  },
  "sector_implications": [
    {"sector": "<name>", "direction": "tailwind|headwind", "magnitude": "high|medium|low"}
  ],
  "bull_case_triggers": ["<trigger1>"],
  "bear_case_triggers": ["<trigger1>"],
  "confidence": 0.0,
  "signal": "bullish|bearish|neutral|mixed",
  "unknowns": ["<thing>"],
  "anchors_fetched": {
    "economic_survey": {"years_consulted": ["2024-25", "2023-24", "2022-23"]},
    "rbi_monetary_policy_report": {"periods_consulted": ["2025-10", "2025-04", "2024-10", "2024-04"]},
    "rbi_annual_report": {"years_consulted": ["2024-25", "2023-24"]},
    "rbi_fsr": {"periods_consulted": ["2025-12", "2025-06"]},
    "union_budget": {"years_consulted": ["2026-27", "2025-26", "2024-25"]},
    "imf_article_iv": {"years_consulted": ["2025", "2024"]}
  },
  "trajectory_checks": [
    {
      "theme": "<e.g. PLI manufacturing push>",
      "anchors_consulted": ["economic_survey", "union_budget"],
      "years_compared": ["2022-23", "2023-24", "2024-25"],
      "verdict": "secular (persists ≥3 years, strengthening)",
      "quantitative_delta": "<e.g. 14 → 16 sectors; disbursements ~3x>"
    }
  ]
}
```

## 5. Guardrails (the non-negotiables)

Every one must appear **verbatim** in `MACRO_SYSTEM_V2`.

| # | Guardrail | Enforcement |
|---|---|---|
| G1 | **Date-stamped grounding** | System prompt injects `today = YYYY-MM-DD`. Every quantitative claim requires inline `[source, YYYY-MM-DD]` |
| G2 | **Fact/opinion separation** | Every bullet prefixed `FACT:` (cited) or `VIEW:` (agent inference). Mixed bullets forbidden |
| G3 | **Source tiering** | **T1 — Canonical India annuals (preferred anchors):** Economic Survey of India (indiabudget.gov.in, annual pre-budget), RBI Annual Report (rbi.org.in, Aug), RBI Monetary Policy Report (rbi.org.in, biannual Apr/Oct), Union Budget speech + receipts (indiabudget.gov.in, Feb), IMF Article IV India (imf.org, annual). **T1 — Live macro data:** RBI database (dbie.rbi.org.in), MoSPI (mospi.gov.in), CEIC, IMF WEO, World Bank, BIS, Fed (federalreserve.gov), ECB (ecb.europa.eu). **T2 (allowed for news flow):** FT, Reuters, Bloomberg, Mint, Business Standard, ET, LiveMint. **T3 (sell-side, think-tanks):** allowed for *views* only, tagged. **Blocked for facts:** X/Twitter, Reddit, unsourced Substack. Sentiment from T3/blocked allowed only tagged `SENTIMENT:` |
| G4 | **Mechanism required** | Correlation banned. Every linkage must state channel: "X → Y via {input-cost / demand / liquidity / FX / fiscal} channel" |
| G5 | **Secular/cyclical tag** | Every thesis bullet tagged `SECULAR` or `CYCLICAL`. Secular claims must pass capital-cycle check (is capacity expanding?) |
| G6 | **India-first translation** | Global claim must be followed by INR/India-specific second-order effect before it counts |
| G7 | **Unknown permission** | Explicit: "If evidence is thin, write `Unknown` and list 2 verification steps. Never invent a number." Required #7 section at end |
| G8 | **Per-claim citation** | No quantitative claim (GDP, rate, CPI, commodity price, flows) without inline URL + date |
| G9 | **No price targets, no buy/sell** | Macro feeds synthesis; never states "bullish for RELIANCE at ₹X" |
| G10 | **Stale-policy defense** | Before quoting any central bank stance, the agent must check the most recent MPC/FOMC date and confirm stance is post-that-date |
| G11 | **Anchor-first for India claims** | Any claim about India's macro state (GDP, fiscal deficit, capex, inflation outlook, sectoral priorities) must cite the Economic Survey, RBI Annual Report, MPR, or Union Budget as primary source. T2 news sources acceptable only for events *since* the latest anchor publication. Briefing must record which anchors were successfully fetched |
| G12 | **Trajectory discipline** | Any theme tagged `SECULAR` must be backed by a `trajectory_check` citing ≥2 anchor publications showing the theme persists. Single-publication themes → downgrade to `EMERGING` or `CYCLICAL`. Auditable: every SECULAR bullet in the briefing must have a matching entry in `briefing.trajectory_checks[]` |

## 5.5 Macro-anchor doc pipeline (parallels AR/deck pipeline)

Anchor documents (Economic Survey, RBI MPR, RBI Annual Report, Union Budget, IMF Article IV) are India-wide, published on fixed schedules, and stable for months at a time. Live WebFetch every run is wasteful, flaky, and gives the agent unstructured PDFs to reason over. Instead, mirror the concall/AR extraction pattern: pre-download, extract to structured JSON, cache, expose via MCP tool.

### 5.5.1 Guiding principle — AR parity
Every design choice answers *"how does AR do it?"* and copies that choice. AR runs in Phase 0b with `ensure_annual_report_data()`; macro anchors run in Phase 0c with `ensure_macro_anchors()`. AR produces `annual_report_v2_FY{yy}.json`; anchors produce `economic_survey_{year}.json`, `rbi_mpr_{yyyy_mm}.json`, etc. AR has `get_annual_report()` MCP tool with TOC + drill; anchors get `get_macro_anchor(doc_type, section)` with the same shape.

### 5.5.2 Vault layout (shared, not per-stock)

Unlike AR/concall/deck which are per-symbol, macro anchors are India-wide. New vault root:

```
~/vault/macro/
  raw/
    economic_survey_2024-25.pdf
    rbi_mpr_2025-04.pdf
    rbi_annual_report_2024-25.pdf
    union_budget_2025-26_speech.pdf
    union_budget_2025-26_receipts.pdf
    imf_article_iv_india_2024.pdf
  extracted/                            # one JSON per publication-period (multi-year retention)
    economic_survey_2024-25.json        # current
    economic_survey_2023-24.json        # prior
    economic_survey_2022-23.json        # 2-prior
    rbi_mpr_2025-10.json                # biannual — latest
    rbi_mpr_2025-04.json
    rbi_mpr_2024-10.json
    rbi_mpr_2024-04.json
    rbi_annual_report_2024-25.json
    rbi_annual_report_2023-24.json
    rbi_fsr_2025-12.json                # biannual — latest
    rbi_fsr_2025-06.json
    union_budget_2026-27.json
    union_budget_2025-26.json
    union_budget_2024-25.json
    imf_article_iv_india_2025.json
    imf_article_iv_india_2024.json
  meta/
    catalog.json                       # which docs are current, last-checked, extraction_status
```

### 5.5.3 New module: `flowtracker/research/macro_anchors.py`

Mirror of `annual_report_extractor.py`. Three public functions:

```python
async def ensure_macro_anchors(force_refresh: bool = False) -> dict:
    """Ensure the 5 canonical India macro anchor docs are downloaded + extracted.

    Checks catalog.json for each doc_type. If the current publication is already
    extracted (status='complete'|'recovered'), skip. Otherwise download + extract.

    Returns {
        "anchors_available": [...],
        "anchors_missing": [...],
        "newly_extracted": N,
    }
    """

def list_current_anchors() -> dict:
    """Return the catalog: what's available, publication dates, extraction status."""

def get_anchor_content(doc_type: str, section: str | None = None) -> dict:
    """Read extracted JSON for a specific anchor + section (or TOC if section=None)."""
```

### 5.5.4 Source discovery — verified URLs (as of 2026-04-18)

Discovery splits into **two classes**: stable overwrite-in-place URLs (hardcode) vs hash-suffixed URLs (must scrape landing page).

**Class A — Stable overwrite URLs (hardcode, just re-download to detect update):**

| Doc | Latest URL | Notes |
|---|---|---|
| Economic Survey — summary | `https://www.indiabudget.gov.in/economicsurvey/doc/echapter.pdf` | Overwritten each Feb; historical copies migrate to `budget{Y}-{Y}/economicsurvey/doc/echapter.pdf` |
| Economic Survey — stat appendix | `https://www.indiabudget.gov.in/economicsurvey/doc/Statistical-Appendix-in-English.pdf` | Same overwrite pattern |
| Budget — Speech | `https://www.indiabudget.gov.in/doc/budget_speech.pdf` | Overwritten each Feb |
| Budget — at a Glance | `https://www.indiabudget.gov.in/doc/Budget_at_Glance/budget_at_a_glance.pdf` | Overwritten each Feb |
| Budget — Key Features (BH1) | `https://www.indiabudget.gov.in/doc/bh1.pdf` | Overwritten each Feb |
| Budget — Receipts (full) | `https://www.indiabudget.gov.in/doc/rec/allrec.pdf` | Overwritten |
| Budget — Expenditure SBE | `https://www.indiabudget.gov.in/doc/eb/allsbe.pdf` | Overwritten |
| Historical archive | `https://www.indiabudget.gov.in/budget{YYYY}-{YY}/...` | Year-keyed path — used for backfill |

**Class B — Hash-suffixed URLs (must scrape landing page):**

| Doc | Landing page to scrape | PDF host | Scrape strategy |
|---|---|---|---|
| RBI Monetary Policy Report | `https://www.rbi.org.in/Scripts/AnnualPublications.aspx?head=Monetary+Policy+Report` | `rbidocs.rbi.org.in/rdocs/Publications/PDFs/{HASH}.PDF` | Parse HTML, extract top `href` by publication date |
| RBI Annual Report | `https://www.rbi.org.in/Scripts/AnnualReportMainDisplay.aspx` | `rbidocs.rbi.org.in/rdocs/AnnualReport/PDFs/0ANNUALREPORT{YYYYYY}{HASH}.PDF` | Year-substring identifiable (`202425`), hash is opaque; scrape |
| RBI Financial Stability Report (bonus — separate from AR) | `https://rbi.org.in/Scripts/FsReports.aspx` | `rbidocs.rbi.org.in/rdocs/PublicationReport/Pdfs/0FSR{MONTH}{YYYY}{HASH}.PDF` | Biannual Jun + Dec |
| IMF Article IV India | `https://www.imf.org/en/Countries/IND` → `https://www.imf.org/en/publications/sprolls/article-iv-staff-reports` | `imf.org/-/media/files/publications/cr/{YYYY}/english/1indea{YYYY}{NNN}-source-pdf.pdf` | Scrape country-report index, filter India, take latest |

**Clarification — RBI has TWO separate annual-ish publications:**
- **RBI Annual Report** (May each year) — RBI's institutional report covering operations + economic review. Broad, slow-evolving.
- **RBI Financial Stability Report (FSR)** (biannual June + December) — focused systemic-risk assessment. Sharper cyclical signal.

Include FSR as a 6th anchor for richer cyclical context — its asset-quality + credit-cycle commentary is very useful for BFSI coverage.

**Implementation notes:**
- All `indiabudget.gov.in` downloads need realistic browser User-Agent (returns 403 to default httpx UA). The existing `ar_downloader._download_pdf` already sets this header — reuse verbatim.
- For Class B, use a light httpx scrape (new file: `macro_anchor_discovery.py`) that parses the landing page for `href` patterns, extracts date from link text, picks latest.
- Store discovered URLs in new table `macro_anchor_documents(doc_type, publication_period, url, discovered_at, downloaded_at, extracted_at, extraction_status)` — mirrors `company_documents` for AR.

### 5.5.4a Retention — how many years to keep?

**Answer: keep the last 2–3 years per anchor, not just latest.** Rationale: macro analysis needs *trajectory*, not snapshots. A single Economic Survey says "we are here"; three surveys say "we've been moving this way for three years" — the latter is the secular signal the agent actually needs.

Per-anchor retention:

| Doc | Retention | Rationale |
|---|---|---|
| Economic Survey | **3 years** (current + 2 prior) | Sectoral themes evolve slowly — 3 years reveals persistent priorities (e.g., PLI trajectory, formalization) |
| RBI MPR | **Last 4 reports = 2 years** biannuals | Captures a full rate-cycle turn (hike → peak → cut). 1 MPR is a snapshot; 4 shows the cycle |
| RBI Annual Report | **2 years** (current + 1 prior) | Slow-evolving institutional view; 2yr is enough for YoY delta |
| RBI FSR | **Last 2 reports = 1 year** biannuals | Asset-quality deltas are the signal; recent dominates |
| Union Budget | **3 years** speeches + BaG | BE vs actuals comparison is 3-year rolling in the Budget docs themselves; keep matching window |
| IMF Article IV | **2 years** | Slow-evolving external view |

**Storage:** PDFs are 2–50MB each. Total vault footprint ≈ 500MB–1GB. Trivial.

**Extraction cost:** One-time per publication, then cached forever. Multi-year corpus is a one-time backfill:
- Current publications: ~$5–11 per refresh cycle (see §5.5.5)
- Historical backfill (2 extra years × 5 docs): ~$15 one-time
- Incremental: only the newly-published doc costs anything (~$1–2 each)

**Default agent behavior:** MCP tool's TOC shows "available years" per doc_type; agent defaults to *current + prior* for trajectory comparisons. Further historical drill-in on demand (e.g., "show me ES 2022-23 sectoral_priorities" for 3-year comparison). Prevents context-window bloat from loading 3 years of Surveys at once.

**Backfill scope for v1:**
- Economic Survey 2022-23, 2023-24, 2024-25 (3 years, stable URL pattern makes backfill easy)
- RBI MPR Oct-2024, Apr-2025, Oct-2025, Apr-2026 (4 most recent)
- RBI Annual Report 2023-24, 2024-25 (2 years)
- RBI FSR Jun-2025, Dec-2025 (2 most recent)
- Union Budget 2024-25, 2025-26, 2026-27 (3 years)
- IMF Article IV India 2024, 2025 (2 most recent)

**Total backfill:** ~16 documents, ~$25 one-time extraction cost, runs once overnight.

### 5.5.5 Extraction — Docling + Claude Sonnet (same recipe as AR)

Each doc type has its own section schema (like AR's 10-section schema). Example for Economic Survey:

```python
ECONOMIC_SURVEY_SECTIONS = {
    "overview": "State of the economy summary + growth outlook",
    "fiscal": "Fiscal deficit, revenue, expenditure composition",
    "external": "BoP, trade, FDI, forex reserves, rupee",
    "prices": "Inflation outlook, WPI/CPI, commodity view",
    "monetary": "Banking, credit, liquidity",
    "industry": "Manufacturing, mining, construction themes",
    "services": "IT, finance, trade, hospitality themes",
    "agriculture": "Rural economy, farm support, monsoon outlook",
    "infra_energy": "Power, roads, rail, renewables",
    "social_sector": "Health, education, employment",
    "climate_sustainability": "Green transition, ESG policy",
    "external_environment": "Global outlook — G7 growth, commodity cycles, geopolitics",
    "sectoral_priorities": "PLI / Make-in-India / focus sectors by chapter"
}
```

Extractor prompt: "Extract structured bullet points for each section. For each claim, record the page number. Flag any numerical outlooks with `confidence` metadata (high for Survey's own projections, medium for third-party cites)." Budget/MPR/RBI AR get their own schemas.

**Cost estimate** (one-time per publication, cached for ~6–12 months):
- Economic Survey: 13 sections × $0.35 cap = $4.55 max, ~$2 typical
- RBI MPR (biannual): 4 sections × $0.35 = $1.40 max
- RBI AR (annual): 5 sections × $0.35 = $1.75 max
- Budget (annual): 6 sections × $0.35 = $2.10 max
- IMF A-IV (annual): 4 sections × $0.35 = $1.40 max
- **Total per refresh cycle:** ~$11 max (≈twice a year); typical ~$5

Amortized across ~200 research runs/year: **<$0.10 per stock run** for macro anchor access.

### 5.5.6 Phase 0c in pipeline

Add a new phase to `research_commands.py` after Phase 0b (concall/AR extraction):

```python
# Phase 0c — macro anchors (India-wide, cached across stocks)
try:
    anchor_result = asyncio.run(ensure_macro_anchors())
    _ok("macro_anchors", anchor_result.get("anchors_available", []))
except Exception as e:
    _skip("macro_anchors", str(e))
    # Non-fatal — macro agent falls back to live WebFetch
```

Phase 0c runs **once per research invocation** regardless of symbol count — the anchor corpus is stock-agnostic. A daemon/cron (new `scripts/refresh-macro-anchors.sh`) can also run this nightly so the first research run of the day doesn't eat the download cost.

### 5.5.7 New MCP tool: `get_macro_anchor` — trajectory-first API

The tool surface **forces multi-year thinking** by making year-comparison a first-class parameter, not an opt-in. Default behavior returns the *latest* document with a side-car "years_available" list and a "trajectory hint" reminding the agent to compare.

Add to `flowtracker/research/tools.py`:

```python
@tool(
    "get_macro_anchor",
    "Fetch pre-extracted content from canonical India macro anchor documents "
    "(Economic Survey, RBI MPR, RBI Annual Report, RBI FSR, Union Budget, IMF Article IV). "
    "Use mode='toc' (default) to see available publications. "
    "Use mode='single' with year= to read one publication's section. "
    "Use mode='compare' with section= to get the same section across ALL available years — "
    "USE THIS TO DETECT TRENDS (secular themes persist across years; episodic claims don't).",
    {
        "doc_type": str,
        "mode": str,            # 'toc' | 'single' | 'compare'
        "section": str | None,  # required for single/compare
        "year": str | None,     # required for single, ignored for toc/compare
    }
)
async def get_macro_anchor(args):
    doc_type = args["doc_type"]
    mode = args.get("mode", "toc")
    section = args.get("section")
    year = args.get("year")
    return get_anchor_content(doc_type, mode, section, year)
```

**Return shapes:**

`mode='toc'` →
```json
{
  "doc_type": "economic_survey",
  "years_available": ["2024-25", "2023-24", "2022-23"],
  "sections_per_year": {
    "2024-25": ["overview", "fiscal", "external", "industry", ...],
    "2023-24": ["overview", "fiscal", ...],
    "2022-23": [...]
  },
  "_trajectory_hint": "For secular-vs-episodic analysis, call this tool again with mode='compare' and a section name to see how that theme evolved across all 3 years."
}
```

`mode='single'` → standard content for one year + section.

`mode='compare'` →
```json
{
  "doc_type": "economic_survey",
  "section": "industry",
  "years_compared": ["2022-23", "2023-24", "2024-25"],
  "content_by_year": {
    "2022-23": "... PLI identified 14 sectors ...",
    "2023-24": "... PLI extended to toys, footwear ...",
    "2024-25": "... PLI disbursements crossed ₹X Cr; focus on semiconductors ..."
  },
  "trajectory_markers": {
    "themes_persisting_all_years": ["PLI", "manufacturing-led growth", "formalization"],
    "themes_appearing_once": ["K-shaped recovery"],   // flag as episodic
    "quantitative_changes": [
      {"metric": "PLI sectors covered", "values_by_year": [14, 14, 16]},
      ...
    ]
  }
}
```

The **`trajectory_markers`** are computed at extraction time by the extractor doing a light structural diff — not left to the agent to reconstruct.

Register in **MACRO_AGENT_TOOLS_V2** (swap from empty list):
```python
MACRO_AGENT_TOOLS_V2 = [get_macro_anchor]
# WebSearch/WebFetch remain as builtins for news-flow and post-publication events
```

### 5.5.7a How the agent is forced to use trajectories

Three-layer enforcement so the agent doesn't default to "latest-only" reasoning:

**Layer 1 — Tool default surfaces years:** `mode='toc'` always returns `years_available` + the explicit `_trajectory_hint` string. The agent cannot see the TOC without being told about prior years.

**Layer 2 — Workflow steps (in `MACRO_INSTRUCTIONS_V2`):**

Replace workflow step 0.5 with an explicit trajectory requirement:

```
0.5. Anchor pass — canonical India annuals (MANDATORY, trajectory-aware):
   For each of the 6 anchor doc_types:
   a. Call get_macro_anchor(doc_type, mode='toc') to see available years
   b. Read the LATEST publication's key sections with mode='single'
   c. For any theme you plan to cite as SECULAR, call mode='compare' on
      the relevant section — verify the theme persists across ≥2 years.
      A theme appearing in only 1 Economic Survey is EPISODIC, not SECULAR.
   d. Record in the briefing which anchors + years you actually read
      (briefing.anchors_fetched + briefing.trajectory_checks)
```

**Layer 3 — New guardrail G12 (trajectory discipline):**

```
| G12 | Trajectory required for secular claims | Any bullet tagged SECULAR
       must cite ≥2 anchor publications showing the theme. If only one
       publication mentions it, downgrade to CYCLICAL or tag as EMERGING.
       EMERGING themes are allowed but must be labeled and not weighted as
       strongly as established secular forces. |
```

**Layer 4 — Briefing schema records the evidence:**

```json
"secular_tailwinds": [
  {
    "name": "PLI manufacturing push",
    "mechanism": "direct production subsidy → input cost advantage",
    "capital_cycle_check": "capacity expanding in electronics, solar",
    "trajectory": {
      "first_appeared": "ES 2021-22",
      "persisting_years": ["ES 2022-23", "ES 2023-24", "ES 2024-25",
                           "Budget 2024-25", "Budget 2025-26"],
      "evolution": "strengthening|stable|fading",
      "quantitative_delta": "14 → 16 sectors; disbursements up ~3x"
    },
    "confidence": "high"
  }
]
```

Plus a new top-level briefing field:

```json
"trajectory_checks": [
  {
    "theme": "PLI",
    "anchors_consulted": ["economic_survey", "union_budget"],
    "years_compared": ["2022-23", "2023-24", "2024-25"],
    "verdict": "secular (persists ≥3 years, strengthening)"
  }
]
```

This makes the agent's trajectory reasoning **auditable** — verification (or autoeval) can check whether every SECULAR-tagged claim has a matching trajectory_check entry.

### 5.5.7b What the agent actually sees, end-to-end

For a RELIANCE run:

1. Agent calls `get_macro_anchor('economic_survey', mode='toc')` → sees 3 years available, gets trajectory hint
2. Reads ES 2024-25 `industry` section → notices petchem capex mentioned
3. Calls `get_macro_anchor('economic_survey', mode='compare', section='industry')` → sees petchem capex mentioned in 2023-24 and 2024-25 but not 2022-23 → tags as `EMERGING`, not `SECULAR`
4. Repeats for RBI MPR (rate-cycle trajectory across 4 reports → "cutting cycle early stage"), Budget (capex trajectory across 3 years → "strengthening"), IMF Article IV (external view consistency)
5. Briefing records each trajectory_check — synthesis sees auditable evidence, not just assertion

The macro agent's workflow step 0.5 thus goes from "WebFetch the anchor docs" (v1 — pre-pipeline) to "call `get_macro_anchor` in toc → compare → single flow" (v2 — post-pipeline). Drastically faster, cheaper, deterministic, **and trend-aware by construction**.

### 5.5.8 Catalog schema (`~/vault/macro/meta/catalog.json`)

```json
{
  "last_refreshed": "2026-04-18T19:00:00Z",
  "anchors": {
    "economic_survey": {
      "current_publication": "2024-25",
      "url": "https://...",
      "downloaded_at": "...",
      "extracted_at": "...",
      "extraction_status": "complete",
      "sections_populated": ["overview", "fiscal", ...]
    },
    "rbi_mpr": {
      "current_publication": "2025-04",
      "next_expected": "2025-10",
      ...
    },
    ...
  }
}
```

`ensure_macro_anchors()` checks each entry: if `current_publication` is stale (e.g., newer MPR exists on RBI site), re-download + re-extract.

### 5.5.9 Cron integration

Add to `scripts/setup-crons.sh`:
```bash
# Weekly macro-anchor refresh — Sundays 10am IST
# Checks for newly-published anchor docs; skips if current
0 10 * * 0 /Users/tarang/.../scripts/refresh-macro-anchors.sh
```

Keeps the pipeline cold-start cost low (anchors are fresh when research runs).

### 5.5.10 Fallback behavior

If `ensure_macro_anchors()` fails (e.g., RBI site down, IMF paywall):
- Phase 0c logs a skip but does not abort the pipeline (tier-3 non-critical)
- Macro agent's `get_macro_anchor()` calls return `{"status": "unavailable", "fallback": "use WebSearch/WebFetch"}` per doc_type
- Agent's workflow degrades gracefully to live WebFetch (G11 still requires anchor citations — agent flags the fetch failure in its "unknowns" section)

### 5.5.11 Test plan additions

- `test_macro_anchor_discovery.py` — mock RBI/indiabudget URL patterns, assert `discover_anchor_urls` finds the right doc
- `test_macro_anchor_extraction.py` — fixture PDF (small sample), assert extractor produces the expected section schema
- `test_get_macro_anchor_tool.py` — populate fake catalog, assert MCP tool returns TOC then drill-in content
- `test_phase_0c_skips_when_fresh.py` — pre-populate catalog with current publications, assert `ensure_macro_anchors` makes zero downloads
- Add `macro_anchors` to the catalog freshness script (`scripts/check-freshness.py`)

### 5.5.12 Propagating trends to OTHER specialist agents

**Problem:** The macro agent runs in Phase 1 parallel with the other 7 specialists. Its briefing only reaches synthesis. But the Sector agent analyzing a petchem company, the Financials agent judging rate-sensitivity, the Risk agent evaluating macro exposure, the Valuation agent picking a discount rate — **all of them would analyze better if they knew the macro regime**.

Fixing this by making macro run *before* the specialists would serialize the pipeline. Fixing it by letting every specialist call `get_macro_anchor()` themselves adds coordination cost and tool-call duplication.

**Solution: a pre-computed Macro Context Envelope, injected into every specialist's baseline.** The anchor docs are already extracted JSON with pre-computed `trajectory_markers` — we don't need an LLM to summarize them. A pure-Python function reads the catalog + extracted JSONs and produces a compact structured blob (~800–1200 tokens) that every agent sees in its opening baseline context.

**Key distinction:** the envelope is **factual anchor data**, not opinions. It says *"RBI MPR Oct-2025 stance: cutting cycle, early stage, repo at 5.5%"* — not *"rates are bullish for this stock"*. Each specialist still reaches its own conclusion. No cross-agent contamination.

#### 5.5.12a Envelope structure (what every specialist sees)

```
## Macro Context (pre-computed from anchor corpus, as of {today})

### Rate & Liquidity (source: RBI MPR {period})
- Repo rate: 5.5% (last move: -25bps on YYYY-MM-DD)
- Cycle stage: {early_cutting | mid_cutting | neutral | peak | early_hiking | mid_hiking}
- Liquidity stance: {deficit | neutral | surplus}
- CPI outlook (next 4Q): {range}
- Trajectory across last 4 MPRs: {e.g. "shifted from hike-bias Oct-24 → neutral Apr-25 → cut-bias Oct-25"}

### Fiscal & Capex (source: Union Budget {FY})
- Fiscal deficit: {X}% of GDP (vs {Y}% prior year)
- Capex allocation: ₹{X} Cr ({±N}% YoY)
- PLI disbursement: ₹{X} Cr; sectors covered: {list}
- Trajectory across last 3 Budgets: {capex growth rate, PLI expansion pattern}

### External (source: IMF Article IV {year} + RBI MPR)
- India GDP nowcast: {X}%
- INR regime: {strengthening | stable | weakening} — {range}
- Forex reserves: ${X}B; import cover: {N} months
- Trade balance trajectory: {trend}

### Financial Stability (source: RBI FSR {period})
- Banking GNPA: {X}% (prior: {Y}%)
- Credit growth: {X}% (prior: {Y}%)
- Systemic risk flags: {list}

### Secular Themes (verified across ≥2 anchors)
- {theme}: persisting {N} years, {strengthening|stable|fading}, mentioned in {anchor_list}
- {theme}: ...
- (only includes themes that passed trajectory_check — EPISODIC themes excluded)

### Emerging Themes (single-anchor, watch-list)
- {theme}: appeared first in {anchor + period}

### Industry-Specific Slice (filtered for {company.industry})
[Agent-facing: only the parts of the above relevant to this stock's industry]
- From ES {year} industry chapter: {2-3 bullets on this sector's themes}
- From Budget {year}: {allocations affecting this sector}
- From MPR: {sector-relevant monetary signal, e.g. NBFC credit growth for BFSI}
```

The **Industry-Specific Slice** is the payoff. For RELIANCE the slice pulls petchem + retail + telecom fragments; for HDFC it pulls banking + credit cycle; for SUN PHARMA it pulls healthcare + R&D policy. Everyone else sees a generic slice or omits it.

#### 5.5.12b Implementation — pure Python, no LLM

New function in `flowtracker/research/macro_anchors.py`:

```python
def build_macro_context_envelope(industry: str | None = None) -> str:
    """Compose a compact macro context blob from the extracted anchor JSONs.

    Pure Python. Reads cached JSON, filters to sections relevant to `industry`,
    formats as markdown. ~800-1200 tokens.

    Called once per pipeline run; result is cheap to compute (<50ms), cached
    in-memory for the duration of the pipeline.
    """
    catalog = load_catalog()
    mpr = load_anchor("rbi_mpr", latest=True)
    es_current = load_anchor("economic_survey", latest=True)
    es_prior = load_anchor("economic_survey", offset=1)
    es_prior2 = load_anchor("economic_survey", offset=2)
    budget = load_anchor("union_budget", latest=True)
    fsr = load_anchor("rbi_fsr", latest=True)
    imf = load_anchor("imf_article_iv", latest=True)

    # Pre-computed trajectory_markers from extractor (cheap lookup, not compute)
    secular_themes = compute_secular_themes([es_current, es_prior, es_prior2])

    # Industry slice — map company industry to ES chapter + Budget sector head
    industry_slice = _industry_slice(industry, es_current, budget, mpr, fsr)

    return _format_envelope(mpr, es_current, budget, fsr, imf,
                            secular_themes, industry_slice)
```

`_industry_slice` uses the same `_INDUSTRY_SECTOR_MAP` that already lives in `prompts.py` (line 1487) — reusing existing industry→sector routing so BFSI → banking sections, pharma → healthcare sections, auto → manufacturing-and-auto sections, etc.

#### 5.5.12c Wiring: `_build_baseline_context()` injection

Update `agent.py:_build_baseline_context` (line ~197) to call the envelope builder and append to the existing per-stock context:

```python
def _build_baseline_context(symbol: str) -> str:
    # ... existing company tear sheet ...

    # NEW: append macro context envelope (industry-aware slice)
    try:
        from flowtracker.research.macro_anchors import build_macro_context_envelope
        with ResearchDataAPI() as api:
            industry = api._get_industry(symbol)
        macro_envelope = build_macro_context_envelope(industry=industry)
        baseline += "\n\n" + macro_envelope
    except Exception as exc:
        logger.warning("Macro envelope unavailable for %s: %s", symbol, exc)
        # Graceful degradation — pipeline continues without macro baseline

    return baseline
```

**Effect:** Every specialist agent's opening prompt now contains ~1000 tokens of factual, trajectory-aware macro context *filtered to its own industry*. Cost: ~$0.003 per agent × 7 specialists = $0.02 per run. Negligible.

#### 5.5.12d How specialists should use it (prompt additions)

Each specialist's `*_INSTRUCTIONS_V2` gets a short addition:

```
## Using the Macro Context Envelope
Your baseline includes a "Macro Context" block with rate cycle, fiscal stance,
secular themes, and an industry-specific slice. Treat this as factual background:
- Cite it when macro directly shapes your analysis (e.g., "rate cycle turning cuts
  benefits Bajaj Finance's NIM by ~X bps" — financials/valuation agents)
- DO NOT repeat macro reasoning — that's the macro agent's job
- DO flag when micro signals contradict macro (e.g., "Despite cutting cycle,
  this company's cost of funds still rising — idiosyncratic weakness")
- Industry-slice items should shape your sector/business/risk commentary
```

This gives specialists **context without duplication**. The macro agent still owns the macro narrative; specialists just cite the regime when directly relevant.

#### 5.5.12e What flows where — the full propagation map

```
Phase 0c:  ensure_macro_anchors()  → extracted/*.json (pure storage)
                ↓
Phase 1 (start):  build_macro_context_envelope(industry)  → ~1000-token blob
                ↓
              injected into _build_baseline_context(symbol)
                ↓
              7 specialist agents + macro agent all see macro envelope
              in their opening prompt (industry-filtered per stock)
                ↓
Phase 1 (parallel):
              - Specialists analyze with macro context available
              - Macro agent does deep bull/bear + trajectory via get_macro_anchor tool
                ↓
Phase 1.5:  Verification runs (skips macro + web_research)
                ↓
Phase 2:    Synthesis sees:
              - Full macro briefing (regime, secular themes, cyclical stage, bull/bear)
              - Specialist briefings (each already macro-aware)
              - Can identify macro-vs-micro tensions cleanly
```

**Key design property:** specialists and the macro agent read from the *same source of truth* (cached anchor JSONs). The envelope is a projection of that truth into a compact form; the macro agent reads the full form. Both are consistent because they derive from identical extracted data.

#### 5.5.12f Guardrail: envelope staleness

If the envelope is stale (say Budget 2026-27 released but not yet extracted), the macro agent and specialists will disagree — macro agent via `get_macro_anchor` sees the latest catalog, specialists see a baseline built before the refresh.

Mitigation: `build_macro_context_envelope()` checks `catalog.json.last_refreshed`; if older than 7 days OR if the expected-next-release date has passed, it emits a "STALE" warning header in the envelope and logs a pipeline warning. The cron (§5.5.9) handles this in normal operation; this is a last-line defense.

### 5.5.13 Rollout (adds to §8 phases)

This doc pipeline splits into three PRs. Ordering:

1. **PR 1 (macro agent v1):** Phases 1–3 of §8 — agent ships using live WebFetch for anchors. Validates the agent design works.
2. **PR 2 (anchor pipeline + envelope):** §5.5.1–§5.5.12 — add `macro_anchors.py`, discovery, extractor, Phase 0c, `get_macro_anchor` tool with toc/single/compare modes, `build_macro_context_envelope()` + baseline injection, specialist prompt additions. Swap agent's step-0.5 from WebFetch to MCP tool. Faster + cheaper + deterministic + propagates to all agents.
3. **PR 3 (cron + freshness):** automate refresh, add to freshness monitoring.

Rationale for split: agent design is the risky, iterative piece. Doc pipeline is plumbing that's well-understood (exact mirror of AR) but non-trivial. Landing the agent first means we get feedback on prompt quality before over-investing in infra.

---

## 6. Integration plan — file-by-file changes

### 6.1 `flow-tracker/flowtracker/research/prompts.py`

**Add** (~line 1020, after `AGENT_PROMPTS_V2["news"]`):

```python
MACRO_SYSTEM_V2 = """# Global Macro Strategist
## Persona
[persona text]

## Mission
[mission text]

## Guardrails (non-negotiable)
[G1..G10 verbatim]

## Source Tiering
[T1/T2/T3 table]
"""

MACRO_INSTRUCTIONS_V2 = SHARED_PREAMBLE_V2 + """
## Workflow
0. Baseline: review <company_baseline> for industry + mcap
0.5. **Anchor pass — canonical India annuals (MANDATORY before any other WebSearch):**
   - Economic Survey of India (indiabudget.gov.in/economicsurvey, pre-budget Feb) — current-year GDP outlook, fiscal position, sectoral themes
   - RBI Monetary Policy Report (rbi.org.in, biannual Apr/Oct) — inflation outlook, rate stance rationale, external-sector view
   - RBI Annual Report (rbi.org.in, Aug) — financial stability, credit cycle, systemic risk
   - Union Budget speech + receipts (indiabudget.gov.in, Feb) — capex, PLI, sectoral allocations
   - IMF Article IV India (imf.org, annual) — external independent view
   Cache these in memory as the authoritative anchor for every subsequent claim. If a WebSearch result in steps 1–4 contradicts an anchor doc, the anchor wins (or flag explicitly and cite both).
1. Global regime snapshot (5-8 targeted WebSearches on Fed, RBI, ECB, USD/INR, crude, gold, PMI) — cross-reference against Economic Survey's external-environment chapter
2. Identify 3-5 secular forces relevant to this stock's industry — anchor against Economic Survey's sectoral chapters
3. Cyclical setup (1-2 WebSearches per cycle dimension) — anchor against MPR's "assessment and outlook"
4. India transmission mapping — Budget capex/PLI allocations drive the fiscal channel
5. Sector implications
6. Bull/bear dialectic
7. Confidence + gaps — if any anchor doc could not be fetched, flag as a data gap at the top of this section

## Report Sections
[seven sections as in §4]

## Structured Briefing
[JSON schema from §4]
"""

AGENT_PROMPTS_V2["macro"] = (MACRO_SYSTEM_V2, MACRO_INSTRUCTIONS_V2)
```

**Note:** Macro does **not** need sector_skills injection initially. The `build_specialist_prompt` dispatch will return `(MACRO_SYSTEM_V2 + SHARED_PREAMBLE_V2 + mcap_injection, MACRO_INSTRUCTIONS_V2)` which is fine — cross-industry by design. Revisit if eval shows sector-specific macro guidance would help.

### 6.2 `flow-tracker/flowtracker/research/tools.py`

**Add** (after `NEWS_AGENT_TOOLS_V2`):
```python
MACRO_AGENT_TOOLS_V2 = []  # intentionally empty — WebSearch/WebFetch only
```

This keeps the import contract consistent with other agents even though the list is empty.

### 6.3 `flow-tracker/flowtracker/research/agent.py`

**Constants to update** (lines 59–134):

```python
DEFAULT_MODELS["macro"] = "claude-sonnet-4-6"
DEFAULT_EFFORT["macro"] = "medium"      # web-retrieval, not deep reasoning
AGENT_TOOLS["macro"] = MACRO_AGENT_TOOLS_V2
AGENT_TIERS["macro"] = 3                # tier 3: supplementary, not dealbreaker
AGENT_MAX_TURNS["macro"] = 25
AGENT_MAX_BUDGET["macro"] = 0.60
AGENT_ALLOWED_BUILTINS["macro"] = ["WebSearch", "WebFetch"]
```

**`_SYNTHESIS_FIELDS`** — add (line ~194):
```python
# Macro
"regime_state", "secular_tailwinds", "secular_headwinds",
"cyclical_stage", "india_transmission", "sector_implications",
"bull_case_triggers", "bear_case_triggers",
```

**`run_all_agents`** — update `agent_names` (line 1127):
```python
agent_names = [
    "business", "financials", "ownership", "valuation",
    "risk", "technical", "sector", "news", "macro",
]
```

**Verification skip** — macro should skip verification (same reasoning as web_research: citations are inline, verifier tool-set is MCP-data-oriented, cost not justified). Update verify loop (line ~1275):
```python
# Verifier is not designed for web-sourced agents
_VERIFIER_SKIP = {"web_research", "macro"}
verify_tasks = [
    _verify_with_limit(name, env)
    for name, env in envelopes.items()
    if name not in _VERIFIER_SKIP
]
```

**`run_synthesis_agent`** — inject macro section alongside news (line ~1495):
```python
# Inject macro briefing if available — placed BEFORE news since macro sets scene
macro_section = ""
macro_briefing = briefings.get("macro", {})
if macro_briefing:
    regime = macro_briefing.get("regime_state", {})
    macro_section = "\n## Macro Backdrop (from macro agent)\n"
    macro_section += f"- Rate cycle: {regime.get('rate_cycle', '?')}\n"
    macro_section += f"- Growth pulse: {regime.get('growth_pulse', '?')}\n"
    macro_section += f"- Commodity regime: {regime.get('commodity_regime', '?')}\n"
    tailwinds = macro_briefing.get("secular_tailwinds", [])
    headwinds = macro_briefing.get("secular_headwinds", [])
    if tailwinds:
        macro_section += "\nSecular tailwinds:\n"
        for t in tailwinds[:5]:
            macro_section += f"- {t.get('name', '?')} — {t.get('mechanism', '?')}\n"
    if headwinds:
        macro_section += "\nSecular headwinds:\n"
        for h in headwinds[:5]:
            macro_section += f"- {h.get('name', '?')} — {h.get('mechanism', '?')}\n"
    macro_section += f"\nCyclical stage: {macro_briefing.get('cyclical_stage', '?')}\n"
    macro_section += f"Macro signal: **{macro_briefing.get('signal', 'neutral')}**\n"

# user_prompt: add macro_section BEFORE news_section
user_prompt = (
    f"Synthesize the analysis for {symbol}.\n\n"
    f"## Orchestrator Pre-Analysis ...\n{signals_analysis}\n\n"
    f"{web_research_section}"
    f"{macro_section}"
    f"{news_section}"
    f"## Specialist Briefings\n{briefing_text}\n\n"
    ...
)
```

### 6.4 `flow-tracker/flowtracker/research/prompts.py` — synthesis prompt updates

In `SYNTHESIS_AGENT_PROMPT_V2`, update:
- Line 1028: "8 specialist agents" → "9 specialist agents (business, financials, ownership, valuation, risk, technical, sector, news, macro)"
- Add cross-signal rule: "**Macro vs micro tension** — when macro signals headwind but bottom-up signals tailwind (or vice versa), acknowledge explicitly. A high-conviction BUY on a rate-sensitive stock in a mid-hiking cycle must flag the regime risk in the Verdict."
- Add to Executive Summary section: "Reference macro backdrop (regime, cyclical stage) explicitly."

### 6.5 `flow-tracker/flowtracker/research/assembly.py`

Update `report_order` (line ~62):
```python
report_order = [
    ("business", "The Business"),
    ("financials", "Financial Analysis"),
    ("valuation", "Valuation"),
    ("ownership", "Ownership Intelligence"),
    ("risk", "Risk Assessment"),
    ("macro", "Macro Backdrop & Secular Tailwinds"),  # NEW — before sector
    ("sector", "Sector & Industry"),
    ("technical", "Technical & Market Context"),
    ("news", "Recent News & Catalysts"),
]
```

Update the assembly header text (line ~50): "7 specialists + synthesis + verification" → "8 specialists + macro + synthesis + verification" (or restructure).

### 6.6 `flow-tracker/flowtracker/research/briefing.py`

No changes needed. `BriefingEnvelope` is agent-agnostic and `load_all_briefings` globs `*.json` in the vault dir.

### 6.7 CLI entry point (`research/run` command)

Check `flowtracker/commands/research_commands.py` for the `research run` Typer command — add `macro` to its agent choice enum if it's constrained. (Exploration step — may already accept arbitrary agent names.)

## 7. Testing plan

### Unit tests (new file: `tests/unit/test_macro_agent.py`)
- `test_macro_prompt_registered` — `AGENT_PROMPTS_V2["macro"]` exists and returns (system, instructions) tuple
- `test_macro_system_prompt_has_guardrails` — every G1–G10 token present in system prompt (grep for key phrases: "FACT:", "VIEW:", "today =", "Unknown", "SECULAR", "CYCLICAL", "capital cycle")
- `test_macro_tools_empty` — `MACRO_AGENT_TOOLS_V2 == []`
- `test_macro_briefing_schema` — validate a sample briefing dict against expected keys

### Integration tests (`tests/integration/`)
- `test_macro_in_run_all_agents` — monkeypatch `_run_specialist` to stub macro; assert it's called with `agent_names` containing "macro"
- `test_synthesis_injects_macro_section` — mock briefings with a macro entry; assert `user_prompt` contains "## Macro Backdrop"
- `test_verifier_skips_macro` — assert macro is not in the verify_tasks list
- `test_assembly_includes_macro_section` — pass a macro envelope to assembly, assert rendered markdown contains "Macro Backdrop & Secular Tailwinds"

### Manual validation (before shipping)
- Run `uv run flowtrack research run macro -s RELIANCE` → check report for guardrail compliance:
  - Every fact has inline citation + date
  - FACT/VIEW labels present
  - SECULAR/CYCLICAL tags present
  - India transmission section mechanistic (not correlational)
  - Unknowns section non-empty (macro always has gaps)
- Run full thesis pipeline `uv run flowtrack research thesis -s RELIANCE` → check assembled HTML has macro section in right place + synthesis verdict references macro
- Sample three more stocks: one rate-sensitive (BAJFINANCE), one commodity (TATASTEEL), one defensive (HDFC), inspect whether macro signal diverges appropriately

### AutoEval integration (later)
- Add `macro` to `autoeval/eval_matrix.yaml` as a new agent row
- Define macro-specific grading rubric: citation discipline, mechanism quality, secular/cyclical discipline, India-specific translation, bull/bear balance
- Target: A- bar across 5 stocks from different sectors (BFSI, pharma, IT, commodities, consumer)
- Feed prompt fixes back via `sector_skills/` — though for macro this may mean a single `macro/general.md` rather than per-sector

## 8. Rollout phases

### Phase 1 — Prompt + scaffolding (subagent-executable)
1. Draft full `MACRO_SYSTEM_V2` + `MACRO_INSTRUCTIONS_V2` in prompts.py
2. Add empty `MACRO_AGENT_TOOLS_V2` to tools.py
3. Wire constants in agent.py (models, effort, tools, tiers, turns, budget, builtins)
4. Update `_SYNTHESIS_FIELDS`
**Verification:** `uv run python -c "from flowtracker.research.prompts import AGENT_PROMPTS_V2; print(AGENT_PROMPTS_V2['macro'][0][:500])"`

### Phase 2 — Orchestrator integration
5. Add `"macro"` to `agent_names` in `run_all_agents`
6. Update verifier skip list
7. Add macro section injection in `run_synthesis_agent`
8. Update synthesis prompt (9 agents, macro-vs-micro tension rule)
**Verification:** `uv run flowtrack research run macro -s RELIANCE` produces a briefing JSON with macro schema

### Phase 3 — Assembly + tests
9. Add macro to `report_order` in assembly.py
10. Write unit + integration tests
11. Run full pipeline on RELIANCE, inspect output
**Verification:** `uv run pytest tests/ -m "not slow" -k "macro"` green; full thesis runs end-to-end

### Phase 4 — Manual validation + iteration
12. Run on 5 stocks across sectors
13. Review each report against G1–G10 checklist
14. Patch prompt where guardrails are violated
**Verification:** Guardrail adherence ≥90% across sample runs

### Phase 5 — AutoEval (follow-up, separate PR)
15. Add macro to eval_matrix
16. Define grading rubric
17. Iterate until A- bar

## 9. Open questions

1. **Should macro feed the Risk agent directly, or only synthesis?** Risk agent already has `macro_sensitivity` field. Argument for: risk should know if regime is hostile. Argument against: adds coupling, Phase 1 agents run in parallel. **Recommendation:** pass via synthesis only for v1; revisit if eval shows risk blind-spots.
2. **Should macro briefings be cached across runs of different stocks in the same sector?** Global regime is stock-agnostic. Could cache the first four sections (global regime, secular, cyclical, India transmission) for 24h and regenerate only sections 5–7 per stock. **Recommendation:** defer; add only if cost becomes material (>$0.50/run sustained).
3. **Verification — really skip?** Alternative: build a *citation verifier* that walks macro's inline URLs and confirms each WebFetch returns the claimed number. **Recommendation:** skip for v1 (verifier is MCP-oriented), add citation-spot-check sampling in Phase 5 if guardrail violation rate is high.
4. **Macro in autoeval vs separate eval harness?** Current harness grades per-sector; macro is cross-sector. **Recommendation:** add as an "any" row that runs across 5 sector-diverse symbols, grade on guardrail compliance + content quality.

## 10. Success criteria

- Macro agent runs reliably in `run_all_agents` pipeline (≥95% success across 10 test runs)
- Briefing JSON schema validates against expected shape
- Synthesis reports reference macro in Verdict for 100% of runs with macro briefing present
- Guardrail compliance ≥90% on manual review of 5 sample reports
- No regression in existing 8-agent pipeline (full test suite green)
- Cost per run ≤$0.60 (enforced by `AGENT_MAX_BUDGET`)
- Measurable improvement: at least 2 of 5 sample stocks produce a macro signal that meaningfully reframes the verdict (e.g., regime risk flag on rate-sensitive, commodity tailwind on cyclical)

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Macro claims contradict Sector agent (duplication / conflict) | Clear scoping: Sector = industry structure; Macro = cross-industry secular forces + cycles. Synthesis prompt explicitly reconciles |
| WebSearch rate limits / flaky | Existing tier-3 retry machinery in `_run_with_limit` handles this; tier-3 abort doesn't cascade |
| Stale citations | G10 enforces date-check; autoeval will catch drift |
| Prompt-cache fragility | `SHARED_PREAMBLE_V2` hash check already guards this; macro appends to preamble, doesn't mutate |
| Cost blow-up | `AGENT_MAX_BUDGET["macro"] = 0.60` + `AGENT_MAX_TURNS = 25` hard caps |
| Synthesis overweights macro (everything becomes "macro says wait") | Synthesis prompt frames macro as *context* not *signal*; only amplifies when 3+ agents align |

---

**First PR scope:** Phases 1–3 (scaffolding, orchestrator wiring, tests). Phases 4–5 follow in separate PRs once the pipeline wire-up is stable.

**Parallelizable work** (for subagent dispatch):
- Subagent A: write the MACRO_SYSTEM_V2 + MACRO_INSTRUCTIONS_V2 prompt (Phase 1.1) — self-contained file edit
- Subagent B: wire agent.py constants (Phase 1.3) — mechanical additions
- Subagent C: write unit tests (Phase 3.10) — can be written from the prompt spec before implementation is done
- Sequential: Phase 2 (orchestrator integration) must wait for Phase 1 to complete; assembly update (3.9) can run parallel with synthesis prompt update (2.8) since they touch different files
