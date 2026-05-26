# Track F — AR Extractor v2 (Native-PDF, Tiered Models)

**Status:** **PAUSED 2026-04-28** — Gemini access lost mid-day; the full-AR single-call premise no longer works. Replaced by `plans/ar-extractor-v2-nim-only.md` which uses NIM-only, section-targeted extraction.

**Status (original):** Draft, 2026-04-28 — replaces Tracks B, C, E from `plans/ar-extraction-quality-fixes.md`. Track A (related_party aliases) and Track D (HDFCLIFE re-download) remain orthogonal.
**Goal:** Replace the Docling → heading_toc → per-section Claude pipeline with a single-call, vision-capable, structured-output extractor mirroring `concall_extractor.py`. Use a tiered model strategy with NVIDIA NIM (free) and Gemini Flash as primaries, premium models only for verification.
**Effort:** ~1.5d engineering + 0.5d backfill + 0.5d A/B verification.
**Cost budget:** ~$0–$5 full cohort backfill. See §6 for tier accounting.

---

## 1. Why v2

The current AR pipeline has five fragile preprocessing layers between PDF and structured output: Docling rendering, markdown caching, heading_toc regex matching, slice boundary computation, and per-section chunked Claude calls. Tracks A-E in the prior plan attack each of those layers separately. The 2026 best-practice instead **collapses all five into a single multimodal API call** — the model handles document layout, tables, embedded images, and section detection itself. This is what `concall_extractor.py` already does for transcripts.

### v1 vs v2 in one diagram

```
v1: PDF → Docling → markdown cache → heading_toc regex → slice → 12× Claude calls → JSON
                  (~2-5min)        (alias gaps)   (boundary bugs) (rich-input failures)

v2: PDF → 1× multimodal API call with response_schema → JSON
                                  (~30-90s, model handles layout + vision + sections)
```

### What v2 fixes for free
- ETERNAL `segmental` policy-vs-data wrong-match
- VEDL `segmental` 26-char slice
- HDFCBANK `segmental` rich-input null (different prompt path)
- ICICIBANK / HINDUNILVR / SBIN / BANKBARODA partial-slice issues
- Image-rendered tables (HDFCLIFE EV rollforward, HINDALCO capacity tables, VEDL segmental graphs) — vision-capable models extract them natively
- All future heading variants — no more alias maintenance

### What v2 doesn't fix
- HDFCLIFE wrong-PDF-cached (Track D — orthogonal, `ar_downloader.py` issue)
- ARs >50MB (none in cohort, but a guardrail is required)

## 2. Model tiering — NVIDIA NIM primary, Gemini fallback

After surveying the 2026 landscape (see §11 sources), the cost-quality frontier looks like this:

| Tier | Model | Cost (cohort backfill of 16 ARs ≈ 1.5M tokens) | Quality | Auth path |
|------|-------|--------------------------------------------|---------|-----------|
| 0 | **NVIDIA Nemotron Nano 12B V2 VL** (build.nvidia.com) | **$0** (1,000 free credits on signup, up to 5,000 by request, 40 req/min) | Purpose-built for document intelligence; OCR + chart reasoning + multimodal | New API key at build.nvidia.com → store at `~/.config/flowtracker/nvidia.env` |
| 1 | **Gemini 2.5 Flash** | ~$0.60 | Best vision/cost ratio after free tier; 1M context, native PDF, response_schema | Existing `~/.config/flowtracker/gemini.env` |
| 2 | **Gemini 3 Pro** | ~$3.60 | Premium quality, 1M context, native PDF, finest table comprehension | Existing `gemini.env`; user's standing default |
| 3 | **Open-source fallbacks via OpenRouter** | Qwen3-VL-8B at $0.08/$0.50 per 1M (~$0.15 cohort); Nemotron Nano 12B V2 VL listed FREE on OpenRouter too | Comparable to Tier 0; useful if NVIDIA NIM credits exhaust | New OpenRouter key |

### Tier policy (validated by Phase 0 spike on 2026-04-28)
- **Default:** Tier 0 = NVIDIA **Nemotron Nano 12B V2 VL** via NIM. ETERNAL FY25 segmental spike returned 5/5 segments with correct revenue + EBITDA + geography in ~10s, $0. NIM endpoint accepts `image_url` only — pages must be rasterized via pypdfium2 first (4-image cap per call).
- **Tier 0+ (reasoning fallback):** Nemotron 3 Nano Omni 30B A3B with `enable_thinking=True` for sections that genuinely need derivation (EV rollforwards, restated 5-yr reconciliations). DO NOT use for tabular transcription — Phase 0 spike showed it overthinks (27KB reasoning, schema confusion: put ebitda values in ebit_cr, 4× slower). Reserve narrowly.
- **Quota-exhaust fallback:** Tier 1 = Gemini 2.5 Flash. Auto-switch when NIM credit depletes or rate-limited; Flash is ~50× cheaper than Pro per token and handles 1000-page PDFs **natively** (no rasterization). For full-AR single-call extraction Flash is the better choice anyway — NIM's image-only constraint means full-AR extraction would need ~90 calls per AR (4-page batches × 360pp), which busts the free quota.
- **Per-section vs full-AR routing:** when full-AR fits Gemini's 50MB / 1000pp limit (every cohort stock does), prefer Tier 1 (Flash) for the FULL AR in a single call; use Tier 0 (NIM 12B VL) only for re-asking specific sections that came back null. Gemini Flash is the "concall pattern" equivalent for AR; NIM is the surgical follow-up.
- **Verifier / A/B baseline only:** Tier 2 = Gemini 3 Pro. Used in §7 verification, not in production.
- **Disaster recovery:** Tier 3 = Qwen3-VL-8B via OpenRouter or Nemotron Nano 12B V2 VL (free) on OpenRouter. Spare path if both Google and NVIDIA outage simultaneously.

### Why this tiering wins over a single-model choice
- Gemini 3 Pro alone: $3.60/cohort + ongoing quarterly cost. Wasted quality margin for routine extractions.
- Anthropic alone: requires API token we don't have.
- Free open OCR alone (DeepSeek-OCR etc.): benchmark accuracy 97% generally but **drops to 75-80% on financial documents** with table misalignment causing 30% of production failures (per Label Your Data analysis). Not safe as default.
- **NIM-Nemotron-default + Flash-fallback + Pro-as-judge** gives us $0 ongoing in the happy path with deterministic escalation when free quota tightens.

## 3. Architecture

### 3.1 New file: `flow-tracker/flowtracker/research/annual_report_extractor_v2.py`

Mirrors `concall_extractor.py` structure exactly. ~600 LOC vs current ~1356.

```
ensure_annual_report_data(symbol, fy, industry, model_tier="auto")
        │
        ▼
_check_size_and_route(pdf_path)        ← size + page-count guard
        │                                 (PDFs >50MB or >1000pp split or downgrade)
        ▼
_build_extraction_prompt(symbol, fy, industry)
        │                                 (one prompt, full 12-section JSON schema,
        │                                  with sector-specific KPI hint same as concall)
        ▼
_call_vision_model_tiered(pdf_path, prompt, schema)
        │                                 (NIM → Gemini Flash → Gemini Pro escalation)
        ▼
_validate_payload(json_payload)         ← Pydantic schema validation
        │
        ▼
~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY##.json
        │                                 (same path as v1; downstream tools unchanged)
        ▼
_persist_esop_to_store(...)             ← keep v1's downstream side effects
_persist_five_year_summary_to_store(...)
```

### 3.2 SDK choices

- **NVIDIA NIM**: OpenAI-compatible REST endpoint. Use `openai` Python SDK pointed at `https://integrate.api.nvidia.com/v1`. Already widely supported pattern.
- **Gemini**: `google-genai` (already in deps post-Track-A). Use `client.aio.models.generate_content` with `Part.from_bytes(pdf_bytes, "application/pdf")` + `GenerateContentConfig(response_mime_type="application/json", response_schema=schema)`.
- **No vendor lock**: each tier wrapped behind a `_VisionExtractor` ABC with `extract(pdf_bytes, prompt, schema) -> dict`.

### 3.3 Cache compatibility

Same JSON shape as v1 so every downstream consumer works unchanged:
- `data_api.get_annual_report()` reads as today
- Verifier reads as today
- `_persist_esop_to_store` and `_persist_five_year_summary_to_store` work as today
- Sector KPIs route as today

Only adds two new top-level keys:
```json
{
  "_extractor_version": "v2",
  "_model_used": "nemotron-nano-12b-v2-vl"
}
```

Existing per-section payloads keep their schemas. The new prompt produces identical-shape output enforced by `response_schema`.

### 3.4 PDF size handling

Cohort: max 28MB / 609pp (HINDUNILVR / HDFCBANK). All fit Gemini's 50MB / 1000pp limit. NIM accepts up to 4 images at 1k×2k per call — use the OpenAI-compatible endpoint that accepts URLs or base64 PDFs (verify in Phase 0 spike below).

For ARs >50MB or >1000pp (none in cohort but possible elsewhere):
- Split via `pypdfium2` into ~200-page chunks
- Run extraction on each chunk
- Merge JSON payloads (section-keyed, last-write-wins on duplicates with provenance metadata)

## 4. Implementation phases

### Phase 0 — NIM endpoint + PDF input verification spike (0.25d)

**Worktree:** `equity-research-ar-v2-spike`

- [ ] Sign up at build.nvidia.com, generate API key, save to `~/.config/flowtracker/nvidia.env`. Confirm 1,000 free credits.
- [ ] Smoke test: send ETERNAL FY25 segmental pages (~5 pages, extracted via pypdfium2) to Nemotron Nano 12B V2 VL via NIM's OpenAI-compatible endpoint, request a JSON segment table, verify the segments + numbers come back correct.
- [ ] Same smoke test against Gemini 2.5 Flash for comparison.
- [ ] **Decision gate:** if Nemotron extracts segment numbers within ±2% of the ground-truth (manual read of the AR), proceed to Phase 1. Otherwise downgrade Tier 0 to "Gemini 2.5 Flash default", Tier 1 to "Gemini 3 Pro escalation".

**Deliverable:** `flow-tracker/scripts/spike_v2_extractor.py` + spike findings doc. No code in flowtracker yet.

### Phase 1 — `_VisionExtractor` ABC + tiered router (0.5d)

**Worktree:** `equity-research-ar-v2`

- [ ] New file `flow-tracker/flowtracker/research/vision_extractors.py`:
  - `class _VisionExtractor(ABC)` with `async def extract(self, pdf_bytes, prompt, response_schema) -> dict`
  - `class NimNemotronExtractor(_VisionExtractor)` — `openai.AsyncOpenAI(base_url=..., api_key=...)`. Reads `~/.config/flowtracker/nvidia.env`.
  - `class GeminiFlashExtractor(_VisionExtractor)` — uses shared `_gemini_helpers` (lift from autoeval, same as the OCR plan called for).
  - `class GeminiProExtractor(_VisionExtractor)` — same client, different model.
  - `class TieredVisionRouter` — wraps the above, tries Tier 0 → Tier 1 → Tier 2 with retries. Records which tier ultimately served each call to a ledger at `~/.local/share/flowtracker/v2_extraction_ledger.jsonl`.
- [ ] **Cost guard:** module-level `_BACKFILL_BUDGET_USD = 10.0` aggregated across paid tiers (Tier 0 free uses don't count). Raises `BackfillBudgetExceededError` if cumulative paid spend in a run exceeds budget.
- [ ] **Tests** at `tests/unit/test_vision_extractors.py`:
  - Mock each tier's underlying SDK; assert correct call shape (image part + text + schema).
  - Tier router: simulate Tier 0 quota-exceeded → Tier 1 picked up; simulate Tier 1 503 → Tier 2 picked up.
  - Budget guard: mock paid call → ledger increments → exceed → raise.

### Phase 1.5 — Gemini helpers shared module (0.25d, prep PR)

Same as proposed in `plans/ar-image-ocr-implementation.md` Phase 1.5 — lift `_gemini_with_retry` and `_load_gemini_api_key` out of `autoeval/evaluate.py` and `autoeval/evaluate_macro.py` into shared `research/_gemini_helpers.py`. Independent worktree, separate PR. Vision_extractors imports from this module.

### Phase 2 — `annual_report_extractor_v2.py` (0.5d)

**Worktree:** `equity-research-ar-v2`

- [ ] New file `flow-tracker/flowtracker/research/annual_report_extractor_v2.py`. Public API mirrors v1's `ensure_annual_report_data(symbol, fy, industry, force=False, model_tier="auto")`.
- [ ] **Schema** — Pydantic models for the 12 sections, exactly matching v1's JSON shape. Source the canonical structure from existing v1 outputs (e.g. `~/vault/stocks/ETERNAL/fundamentals/annual_report_FY25.json` for non-empty sections). Convert to `response_schema` JSON Schema for both providers.
- [ ] **Prompt** — single comprehensive prompt with 12 section subsections, sector hint at top (mirrors `concall_extractor.py:CONCALL_EXTRACTION_PROMPT` style). Hard rule: "Return null for any section not present in this AR. Do not fabricate."
- [ ] **Industry routing** — same `build_extraction_hint(industry)` from `sector_kpis.py` that concall uses. BFSI ARs get CASA/NPA/NIM hints; insurance ARs get EV/VNB/ROEV; pharma gets USFDA/ANDA.
- [ ] **PDF size guard** — `_check_size_and_route()` returns early with `extraction_status: "deferred_oversize"` for >50MB / >1000pp PDFs (none in cohort but documented).
- [ ] **Caching** — same atomic-write JSON to `~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY##.json`. Add `_extractor_version: "v2"` and `_model_used: <tier>` keys.
- [ ] **Downstream side effects** — preserve `_persist_esop_to_store` and `_persist_five_year_summary_to_store` calls (lifted from v1 lines 928-940).
- [ ] **Tests** at `tests/unit/test_annual_report_extractor_v2.py`:
  - Mock TieredVisionRouter, return canned 12-section JSON, assert vault JSON written with correct structure + provenance keys.
  - Mock returns malformed JSON → Pydantic catches, extraction marked `partial`.
  - Mock NIM 503 → Gemini Flash fallback wired correctly.

### Phase 3 — CLI wiring + feature flag (0.25d)

**Worktree:** same as Phase 2

- [ ] In `flow-tracker/flowtracker/research/refresh.py` (where `ensure_annual_report_data` is called), check env var `FLOWTRACKER_AR_EXTRACTOR=v2|v1` (default `v1`) and route to v2 module when flagged.
- [ ] CLI flag: `flowtrack research extract-ar -s SYMBOL --extractor v2` (overrides env).
- [ ] Default stays `v1` until Phase 4 A/B passes — no breaking change to production cron jobs.

### Phase 4 — A/B verification on cohort (0.5d ops)

**Worktree:** same

- [ ] For each of the 16 cohort stocks:
  - v1 output already cached at `~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY25.json`. Snapshot to `_v1_baseline.json`.
  - Run v2: `FLOWTRACKER_AR_EXTRACTOR=v2 uv run flowtrack research extract-ar -s {SYMBOL} --fy FY25 --force`
  - Save output as `_v2.json`.
- [ ] Diff per section using `scripts/diff_ar_extractions.py` (new, ~80 LOC):
  - For each of the 12 sections, count: (a) v1 empty / v2 populated, (b) v1 populated / v2 empty, (c) both populated and numerically agree (±2%), (d) both populated and disagree.
  - Output TSV summary + per-stock diff JSON.
- [ ] **Decision gate**: v2 is approved when:
  - Recovers ≥80% of v1's empty sections in cohort
  - Disagrees on ≤5% of populated sections; spot-check those manually
  - Total cost stays within $5 budget (NIM tier should make most calls free)
- [ ] If approved, flip default: set `FLOWTRACKER_AR_EXTRACTOR=v2` in `flow-tracker/scripts/quarterly-filings.sh` cron wrapper.

### Phase 5 — Re-eval on the 5 affected agents (0.5d ops)

Same procedure as the original `ar-extraction-quality-fixes.md` §6: run business / financials / risk / valuation / sector agents on cohort, compare DATA_FIX issues to 2026-04-23/24/25 baseline. Target: AR-related DATA_FIX bucket (30 issues) drops to ≤5.

### Phase 6 — v1 deprecation (deferred ~2 weeks after Phase 4)

After v2 has been the default for the cohort + universe-wide for 2 weeks with no escalations:

- [ ] Keep `annual_report_extractor.py` for one more cycle as a feature-flag-gated fallback.
- [ ] Mark `heading_toc.py` and the Docling cache layer as legacy (no new feature work).
- [ ] In v3 cycle: full deletion. Frees ~2200 LOC across heading_toc + annual_report_extractor + their tests.

## 5. JSON schema (canonical, both providers enforce)

The schema covers all 12 v1 sections. Identical shape to v1; `response_schema` makes the API enforce it.

```python
# flow-tracker/flowtracker/research/ar_v2_schema.py
class SegmentEntry(BaseModel):
    name: str
    revenue_cr: float | None
    revenue_growth_yoy_pct: float | None
    ebitda_cr: float | None
    ebitda_margin_pct: float | None
    segment_assets_cr: float | None
    capex_cr: float | None
    key_metrics: str | None

class SegmentalSection(BaseModel):
    segments: list[SegmentEntry]
    geographical_breakdown: list[dict] | None
    _extraction_note: str | None

# ... and so on for 11 other sections, each mirroring v1's structure
class AnnualReportV2(BaseModel):
    chairman_letter: ChairmanLetterSection | None
    mdna: MdnaSection | None
    risk_management: RiskSection | None
    auditor_report: AuditorSection | None
    corporate_governance: CgSection | None
    related_party: RelatedPartySection | None
    segmental: SegmentalSection | None
    notes_to_financials: NotesSection | None
    financial_statements: FinancialsSection | None
    five_year_summary: FiveYearSection | None
    esop_disclosure: EsopSection | None
    brsr: BrsrSection | None
```

Each section is `| None` so the model can return null for sections truly absent — preserves the "say unknown" rule from `SHARED_PREAMBLE_V2`.

## 6. Cost projection

| Cohort backfill (16 stocks × FY25) | Tier 0 NIM | Tier 1 Flash | Tier 2 Pro |
|------------------------------------|-----------|--------------|------------|
| Per-call input tokens | ~93K (img + text) | same | same |
| Per-call output tokens | ~3K (JSON) | same | same |
| Per-call cost | $0 (within free credits) | $0.04 | $0.22 |
| 16-stock cohort total | **$0** | $0.60 | $3.60 |
| Quarterly steady-state (~50 ARs/yr × top-50 stocks) | $0 (within free quota) | ~$2/yr | ~$12/yr |

Free-tier accounting: NVIDIA gives 1,000 inference credits at signup, 5,000 by request. 16 cohort + 50 universe + buffer = ~80 calls. **Stays under free quota by 60×.**

## 7. Verification (Track F-V)

Premium tier as judge:
- Run Tier 2 (Gemini 3 Pro) on 5 randomly sampled cohort stocks as ground truth.
- Compute disagreement rate vs Tier 0 outputs at the field level.
- Acceptance bar: ≥95% field-level agreement on numeric values, ≥90% on free-text fields.
- Cost: ~$1 for 5-stock judge run. One-time.

If Tier 0 fails the judge:
- Escalate the failing field types to Tier 1 by default in the router (e.g. "if this stock is BFSI and `notes_to_financials.gnpa_breakup` is null after Tier 0, retry on Tier 1").
- Or downgrade Tier 0 to Gemini 2.5 Flash. (1 hr config change.)

## 8. Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| NVIDIA NIM endpoint rate-limits at 40 req/min during backfill | Medium | Cohort backfill is 16 calls — no throttling. Universe backfill (~50) uses 1 call/sec pacing. |
| NIM free credits exhaust before universe backfill | Low | Tier 1 (Gemini Flash) auto-fallback is wired in. $0.60 universe cost is acceptable. |
| Nemotron quality on financial tables below judge threshold | Medium | Phase 0 spike validates this before code investment. Fallback to Tier 1 default if so. |
| PDF >50MB or >1000pp surfaces post-cohort | Low | Size guard logs + defers; manual splitting in Phase 6+ if it ever fires. |
| Two simultaneous outages (Google + NVIDIA) | Very low | Tier 3 OpenRouter Qwen3-VL-8B as DR. Or fall back to v1 via env flag. |
| v2 disagrees with v1 on numeric values that v1 had right | Medium | A/B verification gate in Phase 4. Can't ship until disagreement <5%. |
| Hard-to-detect hallucination on a specific section | Low | Existing verifier agent already cross-checks AR citations. Same safety net applies. |
| `ar_five_year_summary` SQLite mirroring breaks if schema drifts | Low | Pydantic validation + the existing best-effort try/except in v1's `_persist_five_year_summary_to_store` is kept verbatim. |

## 9. Rollback plan

Per-level rollback options, in order of severity:

1. **Per-stock**: env var `FLOWTRACKER_AR_EXTRACTOR=v1` for that one extract command.
2. **Default flip**: change cron wrapper env to v1; v2 stays available via flag.
3. **Module disable**: comment out the v2 dispatch in `refresh.py`. Production back on v1.
4. **Code removal**: revert the v2 module + its tests. v1 fully restored.

No data loss in any scenario — vault JSONs are backwards-compatible (v2 just adds `_extractor_version` + `_model_used` keys that v1 ignores).

## 10. Out of scope

- **Concall / deck pipeline migration**. Concall already uses the modern pattern. Decks (`deck_extractor.py`) are a separate effort.
- **Sector skill files migration**. Same `_shared.md` + `{agent}.md` injection — v2 just produces cleaner inputs to read.
- **Per-section page-range targeting**. v2 sends the whole AR; the model handles section detection. If a stock turns out to be too large for a single call, Phase 6+ adds a page-range chunker — not before.
- **Fine-tuning a custom model**. NVIDIA's NeMo offers it; deferred until we have ≥A- on the autoeval matrix without it.

## 11. Sources

- [NVIDIA NIM API free tier — build.nvidia.com](https://build.nvidia.com/) — 1,000 free credits, 40 req/min, 100+ models including Nemotron Nano 12B V2 VL.
- [Nemotron Nano 12B V2 VL — NVIDIA API docs](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl) — 12B-param open multimodal model for document intelligence; up to 4 images at 1k×2k per call.
- [NVIDIA Multimodal PDF AI Blueprint — Technical blog](https://developer.nvidia.com/blog/build-an-enterprise-scale-multimodal-document-retrieval-pipeline-with-nvidia-nim-agent-blueprint/) — reference architecture for PDF-extraction pipelines built on NIM.
- [Nemotron Nano 12B V2 VL — OpenRouter (free)](https://openrouter.ai/nvidia/nemotron-nano-12b-v2-vl:free) — same model, $0/M in/out, alternative endpoint.
- [Gemini API Pricing (April 2026)](https://benchlm.ai/blog/posts/gemini-api-pricing) — Flash 2.5 at $0.30/$2.50, Pro 3 at $2/$12 per 1M.
- [Gemini Document Understanding](https://ai.google.dev/gemini-api/docs/document-processing) — native PDF up to 50MB / 1000pp, response_schema enforcement.
- [Box Engineering: Gemini 3 Flash sets standard for unstructured extraction](https://blog.box.com/gemini-3-flash-sets-new-standard-accuracy-unstructured-data-extraction).
- [Qwen3-VL-8B Instruct — OpenRouter](https://openrouter.ai/qwen/qwen3-vl-8b-instruct) — $0.08/$0.50 per 1M, BSD-licensed open-weight model with strong document parsing.
- [BentoML: Multimodal AI guide to open-source VLMs 2026](https://www.bentoml.com/blog/multimodal-ai-a-guide-to-open-source-vision-language-models) — Qwen3-VL benchmarks rivaling Gemini 2.5 Pro / GPT-5.
- [DeepSeek-OCR vs Qwen-3 VL vs Mistral OCR](https://www.analyticsvidhya.com/blog/2025/11/deepseek-ocr-vs-qwen-3-vl-vs-mistral-ocr/) — open-OCR financial doc accuracy caveats (75-80% on financial docs).
- [Snowflake Engineering: Long-Context Isn't All You Need (Finance RAG)](https://www.snowflake.com/en/engineering-blog/impact-retrieval-chunking-finance-rag/).

## 12. Execution checklist

- [ ] Phase 0 — NIM signup + spike (0.25d)
- [ ] Phase 1.5 — Gemini helpers refactor (0.25d, separate PR)
- [ ] Phase 1 — `vision_extractors.py` + tiered router (0.5d)
- [ ] Phase 2 — `annual_report_extractor_v2.py` + schema (0.5d)
- [ ] Phase 3 — CLI flag + env routing (0.25d)
- [ ] Phase 4 — Cohort A/B (0.5d ops)
- [ ] Phase 5 — Re-eval on 5 agents (0.5d ops)
- [ ] Phase 6 — Default flip → universe rollout (deferred ~2 weeks)
- [ ] Phase 7 — v1 retire + heading_toc.py / Docling cleanup (deferred)

Total: ~2d engineering (Phases 0-3) + 1d ops (Phases 4-5). Backfill cost: ~$0 happy path, ≤$5 worst case.
