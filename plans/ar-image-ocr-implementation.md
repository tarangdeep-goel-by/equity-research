# Annual Report Vision-OCR Fallback — Implementation Plan

**Status:** **PAUSED 2026-04-28** — Phase 0 audit invalidated the OCR premise. See `plans/ar-ocr-phase0-findings.md`. Cohort ARs have rich extractable text; empty sections trace to heading detection / slice boundary bugs, not image rendering. Pivot recommendation in findings doc. Resume only if a re-audit (after extraction-quality fixes) identifies confirmed image-rendered sections.

**Status (original):** Draft, 2026-04-28 (revised — Gemini vision, not Anthropic)
**Owner:** tarangdeep
**Goal:** Recover 30 P0 eval issues across 13 stocks by adding a Gemini Vision OCR fallback to `annual_report_extractor.py` for image-rendered tables that Docling cannot parse.
**Effort:** 1.5–2 days implementation + 0.5 day backfill ops.
**Cost budget:** ~$10 one-time backfill, ~$2/quarter ongoing (Gemini vision pricing — flat ~258 tokens/image at $1.25/1M input).
**Auth:** Reuses existing `~/.config/flowtracker/gemini.env` (`GEMINI_API_KEY`). No new credentials needed. No raw Anthropic API token required — the Agent SDK in this repo authenticates via Claude Code session, but vision OCR runs through Gemini, the same path autoeval uses.

---

## 1. Why this matters

Modern Indian ARs ship critical tables as **rasterized images**, not embedded text. Docling extracts the surrounding markdown but returns an empty body for these sections, so the JSON cache at `~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY##.json` has either `{"status": "section_not_found_or_empty", "chars": <200}` or a 36-character stub.

Five specialist agents — Business, Financials, Risk, Valuation, Sector — read those sections via the AR consult mandate (`SHARED_PREAMBLE_V2`). When a section is empty, the agent either returns "no data on file" or fabricates around it, both of which Gemini grades down. Strategy 2 of `plans/screener-data-discontinuity.md` (the 5-year restated table) also depends on this — `ar_five_year_summary` cannot be backfilled for stocks whose summary table is image-rendered.

## 2. Failure inventory (concrete targets)

From `eval_history/2026042[345]T*.json`, 30 issues, 13 stocks:

| Stock     | FY   | Section                  | Symptom (chars / pattern)              |
|-----------|------|--------------------------|----------------------------------------|
| ETERNAL   | FY25 | segmental                | empty — Zomato/Blinkit splits as image |
| HINDALCO  | FY25 | segmental                | empty — Aluminium/Copper/Novelis       |
| HINDALCO  | FY25 | notes_to_financials      | nameplate-capacity tables image-only   |
| HINDUNILVR| FY25 | related_party            | Form AOC-2 image-rendered              |
| VEDL      | FY25 | segmental                | empty — Al/Zinc/Power/Iron Ore         |
| HDFCLIFE  | FY25 | notes_to_financials      | EV rollforward / VNB walk / ROEV       |
| ICICIBANK | FY25 | notes_to_financials      | 36 chars total — entire section image  |
| HDFCBANK  | FY25 | (entire AR)              | image-rendered cover-to-cover          |
| SBIN      | FY25 | notes_to_financials      | partial (TBD — verify in Phase 0)      |
| BANKBARODA| FY25 | notes_to_financials      | partial (TBD — verify in Phase 0)      |
| TCS       | FY25 | (TBD — verify)           | flagged generic "AR section sparse"    |
| INFY      | FY25 | (TBD — verify)           | flagged generic "AR section sparse"    |
| DRREDDY   | FY25 | (TBD — verify)           | flagged generic "AR section sparse"    |

Phase 0 of this plan re-validates the bottom four — the eval flags are coarse and we don't want to OCR sections that simply aren't in those ARs.

## 3. Success criteria (how we know it's done)

1. **Coverage:** For 11 confirmed stocks above, the listed empty section returns ≥500 chars of structured JSON in `annual_report_FY25.json` after re-extract.
2. **Schema fidelity:** Vision-extracted segmental sections include numeric revenue + EBIT / segment for at least 2 reporting segments. EV rollforwards include opening EV, VNB, expected return, operating variance, closing EV.
3. **Provenance:** Every OCR'd section carries `_ocr_metadata.{section} = {ocr_status, pages_used, ocr_date, vision_model, input_tokens, output_tokens}`.
4. **No regressions:** Sections that already extract well (≥500 chars from Docling) skip the vision pass entirely. `pytest tests/ -m "not slow"` stays green.
5. **Cost actual ≤ $10** for full 16-stock × P0-section backfill on Gemini vision (was $35 on Anthropic).
6. **Re-eval:** Post-backfill, the 30 P0 issues drop to ≤5 in the next autoeval batch (some stocks may have legitimately missing sections not solvable by OCR).

## 4. Architecture decisions

### 4.1 SDK choice — Gemini via `google-genai` (already in deps)

The repo's `claude_agent_sdk` is built around tool-use loops and authenticates via the Claude Code session, not an API token — it doesn't expose a clean image-input path for stateless OCR. We do **not** have a raw Anthropic API token, so the Anthropic SDK is off the table.

Gemini is already the right fit:
- `google-genai` is already a dep (autoeval extra), pattern proven in `flow-tracker/flowtracker/research/autoeval/evaluate.py:597` and `evaluate_macro.py:230` (`_gemini_with_retry`).
- API key already at `~/.config/flowtracker/gemini.env` (loaded the same way as autoeval — `Path.home() / ".config" / "flowtracker" / "gemini.env"`).
- `gemini-3.1-pro-preview` is the standing project default and supports image input natively via `types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")`.
- Vision is **cheap on Gemini**: image parts bill flat (~258 tokens per image regardless of resolution) at the $1.25/1M input rate. A 5-page section ≈ 1290 input tokens ≈ $0.002 per call. Cuts backfill cost to <$10 vs the ~$25 estimate when we were going to use Anthropic vision.

- New module `flow-tracker/flowtracker/research/vision_ocr.py` owns the Gemini client. Mirrors the autoeval client init pattern.
- Model: `gemini-3.1-pro-preview` (matches autoeval, matches user preference). Hard-coded constant; promote to config later if needed.
- Lift `_gemini_with_retry` from `evaluate_macro.py` into a shared helper (`research/_gemini_helpers.py`) so vision_ocr and autoeval both call the same retry logic.

### 4.2 Rasterization — `pypdfium2` (already in deps)

`filing_client.py:110` and `deck_extractor.py:103` already use `pypdfium2`. Use it for AR rasterization too — no new dep.

- Render at **150 DPI** (≈1240×1754 px for A4) as JPEG quality 85 → ~120–250 KB/page.
- Send up to 5 pages per vision call. If a section spans more, chunk (call 1: pages 1–5, call 2: pages 6–10, …) and merge JSON in vision_ocr.py.
- Cap per-section pages at 15 to bound cost.

### 4.3 Page-range mapping — extend `doc_extractor` to propagate page numbers

Today `heading_toc.py` returns `{char_start, char_end}` per section. We need `{page_start, page_end}` to feed the rasterizer. Two paths:

| Option | Approach | Effort | Quality |
|--------|----------|--------|---------|
| A | Extend Docling extraction to record `page_no` per heading via `DoclingDocument.iterate_items()` and `prov[0].page_no` | 0.5d | Exact |
| B | Heuristic: chars/page ≈ 3000, infer page range from char_offset | 1h | ±2 pages |

**Decision: A**, but with B as a fallback when Docling's `prov` is missing. Exact pages are cheaper to OCR (no waste) and the schema change is a single new field.

### 4.4 Hook point — `_one()` in `annual_report_extractor.py:860`

The vision branch slots in cleanly between line 873 (empty-check) and line 874 (Claude call). Pseudocode:

```python
async def _one(sec: str):
    async with sem:
        slice_text = slice_section(md, section_index, sec)
        if sec == "five_year_summary":
            return sec, _extract_five_year_summary_section(...), False

        # NEW: vision fallback for image-heavy sections
        if (not slice_text or len(slice_text) < OCR_TRIGGER_CHARS) \
                and sec in OCR_TARGET_SECTIONS:
            ocr_result = await _try_vision_ocr_section(
                sec, ar_pdf, section_index.get(sec), symbol, fy_label, industry,
            )
            if ocr_result is not None:
                return sec, ocr_result, False

        if not slice_text or len(slice_text) < 200:
            return sec, {"status": "section_not_found_or_empty", ...}, False
        # ... existing Claude markdown extraction
```

`OCR_TRIGGER_CHARS = 500` (per the original plan). `OCR_TARGET_SECTIONS = {"segmental", "related_party", "notes_to_financials", "five_year_summary"}` plus sector-specific extensions (insurance: EV/VNB lives inside notes; metals: capacity inside notes — both already covered by `notes_to_financials`).

### 4.5 Caching — extend the existing vault JSON

The vault JSON is already incremental. We add a sidecar:

```json
{
  "segmental": { /* extracted fields */ },
  "_ocr_metadata": {
    "segmental": {
      "ocr_status": "success",
      "pages_used": [127, 128, 129],
      "ocr_date": "2026-04-28",
      "vision_model": "claude-sonnet-4-6",
      "input_tokens": 4820,
      "output_tokens": 612
    }
  }
}
```

Re-runs check `_ocr_metadata.{section}.ocr_status == "success"` and skip. `force=True` re-OCRs.

### 4.6 No new DB tables

`ar_five_year_summary` and `ar_esop_summary` continue to mirror parsed JSON. If a vision pass populates `five_year_summary`, the existing `_persist_five_year_summary_to_store` call (line 935) handles persistence transparently — no schema change.

## 5. Implementation phases

Each phase is a separate worktree + PR. PRs land sequentially because they share the AR extractor surface.

### Phase 0 — Validation & telemetry harness (0.5d)

**Worktree:** `equity-research-ar-ocr-phase0`

- [ ] Build `scripts/audit-ar-section-emptiness.py` — walks `~/vault/stocks/*/fundamentals/annual_report_FY25.json`, counts sections with `< 500` chars or `section_not_found_or_empty`, groups by section name. Output TSV: `symbol, section, chars, has_pdf_local, ar_pdf_path`.
- [ ] Run it on the 16 benchmark stocks. Validate the table in §2 above. Add any newly surfaced sections.
- [ ] **Decision gate:** confirm the OCR target list. If audit surfaces >5 sections we hadn't planned, narrow scope before continuing.

**Deliverable:** Grounded inventory + `audit_results.tsv`. No code in flowtracker yet.

### Phase 1 — Page-range propagation (0.5d)

**Worktree:** `equity-research-ar-ocr-phase1`

- [ ] In `flow-tracker/flowtracker/research/doc_extractor.py`, extend the Docling extraction call to capture `page_no` per heading. Output a new `headings_with_pages: list[dict]` field alongside the existing `headings`. Each entry: `{text, level, char_offset, page_no}`. Use `DoclingDocument.iterate_items()` to walk the document; for each `TextItem` with `label == "section_header"`, take `prov[0].page_no`.
- [ ] In `flow-tracker/flowtracker/research/heading_toc.py`, extend `build_ar_section_index()` to attach `{page_start, page_end}` to each section entry. Strategy: page_start = page_no of the matched heading; page_end = page_no of the next heading at the same-or-shallower level minus 1 (or last page of doc for terminal section).
- [ ] Fallback: if any heading lacks `page_no` (Docling didn't track it), derive via `chars_per_page = total_chars / total_pages` and `page = floor(char_offset / chars_per_page)`. Cap with `min(total_pages)`.
- [ ] **Tests:**
  - `tests/unit/test_heading_toc.py` — add fixture with synthetic Docling output containing `prov[0].page_no`. Assert section_index entries include page ranges.
  - Test the fallback path with a synthetic doc lacking page metadata.

**Deliverable:** PR with new metadata, no behaviour change to AR extraction yet. Green tests.

### Phase 1.5 — Gemini helpers refactor (prep PR, 0.25d)

**Worktree:** `equity-research-ar-ocr-phase1_5`
**Decision-locked:** separate worktree, separate PR — lands before Phase 2.

- [ ] New file `flow-tracker/flowtracker/research/_gemini_helpers.py`:
  - Lift `_load_gemini_api_key()` (autoeval/evaluate.py:609) and `_gemini_with_retry()` (autoeval/evaluate_macro.py:230) into shared module. Public exports: `get_gemini_client()` (cached), `gemini_with_retry(...)`.
  - Move `google-genai` dep from `[project.optional-dependencies].autoeval` into base deps (or new `vision` extra) so it's importable outside autoeval.
- [ ] Replace in-line copies in `autoeval/evaluate.py` and `autoeval/evaluate_macro.py` with imports — net negative LOC.
- [ ] Smoke: `uv run flowtrack research autoeval --progress` still works (no behavior change). One existing autoeval test re-run confirms parity.

**Deliverable:** Standalone refactor PR. Vision_ocr in Phase 2 imports from this module.

### Phase 2 — Vision OCR module (0.5d)

**Worktree:** `equity-research-ar-ocr-phase2`

- [ ] Confirm `google-genai` is importable post-Phase-1.5 dep move. `uv sync`.
- [ ] New file `flow-tracker/flowtracker/research/vision_ocr.py`:
  - `_render_pdf_pages(pdf_path: Path, page_range: tuple[int, int], dpi: int = 150) -> list[bytes]` — returns JPEG bytes per page via `pypdfium2`.
  - `_build_vision_prompt(section: str, industry: str | None) -> tuple[str, str]` — returns (instruction_text, json_schema_string). One prompt per OCR target section. See §6 for schemas.
  - `async def extract_section_via_vision(pdf_path, page_range, section, industry, *, model="gemini-3.1-pro-preview") -> dict` — orchestrates: render pages → build `contents=[Part.from_bytes(jpeg, "image/jpeg") for ...] + [Part.from_text(prompt)]` → call `client.aio.models.generate_content(model=..., contents=contents, config=GenerateContentConfig(response_mime_type="application/json", response_schema=schema))` → parse JSON. Chunks at 5 pages/call (still useful for context-window management), merges results.
  - Records `usage_metadata.prompt_token_count` and `candidates_token_count` for telemetry. Returns `{ "_payload": {...}, "_ocr_metadata": {...} }`.
- [ ] **Cost guard:** module-level `_OCR_CALL_BUDGET_USD = 25.0` ledger (lower than the original $50 because Gemini is cheaper, so a runaway is more concerning per-call-count terms — fail loud earlier). Each call appends to `~/.local/share/flowtracker/ocr_ledger.jsonl` and refuses to run when cumulative spend in the current run exceeds the budget.
- [ ] **Tests:** `tests/unit/test_vision_ocr.py`
  - Mock `google.genai.Client` → assert `generate_content` called with the right `contents` shape (image parts + text part) and `response_schema` config.
  - Mock `pypdfium2.PdfDocument` → assert page-range slicing logic.
  - Assert chunking: 12-page section → 3 calls, payloads merged.
  - Assert ledger writes happen.
  - Assert budget exceeded → raises `OCRBudgetExceededError`.

**Deliverable:** Standalone module, callable from a smoke script. Not yet wired into the extractor.

### Phase 3 — Wire vision fallback into AR extractor (0.5d)

**Worktree:** `equity-research-ar-ocr-phase3`

- [ ] Constants at top of `annual_report_extractor.py`:
  ```python
  OCR_TRIGGER_CHARS = 500
  OCR_TARGET_SECTIONS = {"segmental", "related_party", "notes_to_financials", "five_year_summary"}
  ```
- [ ] New helper `async def _try_vision_ocr_section(sec, ar_pdf, section_entry, symbol, fy_label, industry) -> dict | None`. Returns the merged JSON payload or None on any failure. All errors logged-and-swallowed — never poisons the extraction result.
- [ ] Modify `_one()` in `_extract_single_ar` (line 860): insert OCR branch before the existing 200-char gate (see §4.4 pseudocode). On success, set `result["_ocr_metadata"][sec]` for the caller to pick up.
- [ ] `_atomic_write_json(out_path, result)` already runs after each section — no change.
- [ ] CLI flag: `flowtrack research extract-ar -s SYMBOL --ocr-fallback / --no-ocr-fallback` (default on). Wired into the existing CLI command in `research/agent.py` or wherever the extract-AR entry point lives.
- [ ] **Tests:** `tests/integration/test_ar_vision_fallback.py`
  - Synthetic AR PDF (or fixture) where `segmental` section's slice_text is < 200 chars but `notes_to_financials` is fine. Mock `extract_section_via_vision` → returns canned JSON. Assert: `segmental` populated from OCR, `notes_to_financials` populated from existing path, `_ocr_metadata.segmental` present.
  - Re-run with same vault: assert OCR not re-called (cache hit on `_ocr_metadata`).
  - Force flag: assert OCR re-called.
- [ ] Update `tests/integration/test_ar_tool_degradation.py` to assert `_ocr_metadata` propagates through `get_annual_report()` API response.

**Deliverable:** End-to-end OCR fallback in production code path, gated behind flag, fully tested with mocks.

### Phase 4 — Backfill operation (0.5d ops)

- [ ] Run on 16 benchmark stocks first (the eval cohort), one at a time in tmux session `ar-ocr-backfill`:
  ```bash
  for s in HDFCBANK SBIN TCS BANKBARODA ICICIBANK HINDALCO INFY HDFCLIFE \
           DRREDDY ETERNAL NYKAA VEDL HINDUNILVR NESTLEIND POLICYBZR SUNPHARMA; do
    uv run flowtrack research extract-ar -s "$s" --fy FY25 --force --ocr-fallback \
      | tee -a /tmp/ar-ocr-backfill.log
  done
  ```
- [ ] After each stock, check `ocr_ledger.jsonl` cost. Halt if cumulative >$30 (budget tripwire — investigate before continuing).
- [ ] Snapshot `~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY25.json` diff (before vs after) — verify the previously empty sections now have content. Spot-check 3 stocks manually for accuracy (does ETERNAL segmental show actual Zomato/Blinkit revenue numbers).
- [ ] Re-run the autoeval matrix for the 5 affected agents on the 16 stocks: `uv run flowtrack research autoeval -a business --sectors all --skip-run` after re-running specialists. Compare DATA_FIX issue count vs the 2026-04-23/24/25 baseline.

### Phase 5 — Universe-wide rollout (deferred)

After Phase 4 confirms quality + cost, run on full top-50 Nifty in a single overnight tmux job. Estimated cost: ~$50–80 total. Run as cron-able operation so each new AR ingest auto-OCRs on first pass.

## 6. Vision prompts & target JSON schemas

One prompt per OCR target section. All prompts share a system preamble: "You are a financial-data extractor. Output ONLY valid JSON matching the provided schema. Do not include prose, explanations, or markdown fences." Schemas live in `vision_ocr.py` as Pydantic models for round-trip validation.

### 6.1 `segmental`

```json
{
  "reporting_period": "FY25",
  "currency": "INR Cr",
  "segments": [
    {
      "name": "Zomato Food Delivery",
      "revenue": 8123.0,
      "ebit": 540.0,
      "capital_employed": 2100.0,
      "yoy_revenue_growth_pct": 18.4
    }
  ],
  "geography_split": [
    {"region": "India", "revenue": 12000.0, "pct_of_total": 89.2}
  ],
  "notes": "Inter-segment eliminations of Rs 320 Cr applied at consolidation"
}
```

### 6.2 `related_party` (Form AOC-2)

```json
{
  "reporting_period": "FY25",
  "currency": "INR Cr",
  "transactions": [
    {
      "counterparty": "Hindustan Unilever Foundation",
      "relationship": "subsidiary",
      "nature": "service charges",
      "amount": 45.2,
      "outstanding_balance": 12.0,
      "arms_length": true
    }
  ],
  "material_contracts_count": 3,
  "total_volume_cr": 540.0
}
```

### 6.3 `notes_to_financials` (sector-routed)

The notes section is a grab-bag. Industry hint splits the schema:

- **Insurance** (HDFCLIFE, POLICYBZR): `embedded_value_rollforward`, `vnb_walk`, `roev_decomposition`, `persistency_13_25_49_61`, `solvency_ratio`.
- **Metals** (HINDALCO, VEDL): `nameplate_capacity`, `production_volumes`, `realisation_per_tonne`.
- **Banks** (HDFCBANK, ICICIBANK, SBIN, BANKBARODA): `gnpa_npa_breakup`, `provision_coverage`, `crar_cet1`, `lcr`, `casa_breakdown`, `restructured_advances`.
- **Default** (everyone else): generic table list `{table_name, columns, rows}`.

### 6.4 `five_year_summary`

Schema already defined in `five_year_parser.py`. Vision pass produces the same shape; `_persist_five_year_summary_to_store` works unchanged.

## 7. Test plan

| Layer | Test file | Coverage |
|-------|-----------|----------|
| Unit | `tests/unit/test_heading_toc.py` | page-range derivation (Phase 1) |
| Unit | `tests/unit/test_vision_ocr.py` | rendering, chunking, budget guard, prompt selection (Phase 2) |
| Integration | `tests/integration/test_ar_vision_fallback.py` | end-to-end OCR fallback, cache, force-flag (Phase 3) |
| Integration | `tests/integration/test_ar_tool_degradation.py` | `_ocr_metadata` propagates through `get_annual_report()` API |
| Contract | `tests/contract/test_ar_schema.py` (new) | OCR-extracted segmental / related_party JSON validates against Pydantic schemas |
| Smoke | `tests/test_smoke.py` | `extract-ar --help` includes `--ocr-fallback` flag |

All vision SDK calls mocked. Real PDF fixture: 1 small ETERNAL FY25 segmental page lifted into `tests/fixtures/golden/ar_ocr/eternal_segmental.pdf` (1 page, no copyright concern for excerpts).

Goal: full suite stays < 25s on `pytest -m "not slow"`. Vision call mocking keeps it fast.

## 8. Risks & mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Vision model hallucinates segment numbers | Medium | Verifier agent already cross-checks AR citations against vault JSON. Add a verification pass that compares OCR'd numerics against any concall mentions of segment splits — flag mismatches >5%. |
| Cost overrun on backfill | Low | Per-call ledger + $50 hard budget in Phase 2. Stop on tripwire, escalate. |
| Page-range mapping is off-by-one | Medium | Phase 1 fallback heuristic + Phase 0 audit script catches it (manual diff sample). |
| Gemini quota / 503 mid-backfill | Medium | Reuse `_gemini_with_retry` exponential backoff (already proven in autoeval through Gemini outages — see memory `feedback_gemini_outage_recovery`). On extended outage, halt backfill, re-run with `--skip-existing` once healthy. |
| Gemini vision JSON output drifts from schema | Medium | Use `response_mime_type="application/json"` + `response_schema=...` in `GenerateContentConfig` so the SDK enforces the shape. Second-line: Pydantic validation on parse — invalid → log + drop section (no fallback to a hallucinated payload). |
| Section is split across sub-headings the vision pass doesn't see | Medium | Page range is derived at the section level, so all sub-headings inside the range are rendered. Test with HINDALCO multi-sub segmental as the canary. |
| Re-OCR on every run (cache miss) | Low | `_ocr_metadata.{section}.ocr_status == "success"` short-circuits. Verified in Phase 3 test. |
| HDFCBANK is image-rendered cover-to-cover — gigabytes of pages | High for that one stock | Cap per-AR OCR at 30 pages total; HDFCBANK gets prioritized sections only (segmental, notes, related_party). Document as known limitation. |
| Docling `prov[0].page_no` not always populated | Medium | Heuristic fallback (§4.3 option B) handles it. Tested in Phase 1. |

## 9. Decisions locked (2026-04-28)

1. **Backfill cohort:** 16 benchmark stocks (matches eval matrix). Top-50 expansion is Phase 5, deferred until Phase 4 quality is confirmed.
2. **Verifier integration:** Yes — verifier flags OCR'd content. Synthesis agent should hedge or mark low-confidence on OCR-sourced numerics. Implementation:
   - When `_ocr_metadata.{section}.ocr_status == "success"`, the AR consult tool (`get_annual_report`) returns the section payload with an extra top-level key `_extraction_method: "vision_ocr"` (vs default `"docling_markdown"`).
   - `verifier.py` adds a check: when a specialist cites a numeric from a section flagged `vision_ocr`, the verifier annotates the citation in the verification report as "OCR-sourced — verify cross-source if material to thesis."
   - `prompts.py` `SHARED_PREAMBLE_V2` gets a sentence: "Numbers cited from `_extraction_method: vision_ocr` sections should be hedged ('approximately', 'per AR table') rather than stated as exact."
3. **CLI default:** `--ocr-fallback` on by default. Cost on Gemini is negligible.
4. **Gemini-helpers refactor:** Separate worktree, separate PR (Phase 1.5 below). Lands before Phase 2.

## 10. Open questions

(none — all decisions locked)

## 11. Out of scope (explicit non-goals)

- **General-purpose document OCR.** This is AR-only. Decks (`deck_extractor.py`) and concalls don't need image OCR — they're text-rendered today.
- **Multi-language OCR.** All target ARs are English. Skip Hindi/regional.
- **Image charts (line/bar) interpretation.** Numbers in tables only. Charts are deferred per `plans/docling-document-pipeline.md`.
- **Re-extraction of pre-FY24 ARs.** Current focus is FY25 (most relevant to active research). Backfill can extend later.
- **Streaming OCR results.** One-shot per call. No streaming.

## 12. Rollback plan

If Phase 3 lands and OCR results turn out to be unreliable in production:

1. Set `OCR_TRIGGER_CHARS = 0` and `OCR_TARGET_SECTIONS = set()` in `annual_report_extractor.py` — vision branch becomes dead code, all extractions revert to Docling-only.
2. Or, hot-toggle via env var `FLOWTRACKER_AR_OCR_DISABLED=1` — module-level check at function entry.
3. Vault JSONs with OCR'd content stay readable; `_ocr_metadata` is purely advisory and ignored by all downstream readers.

No DB rollback needed — no schema changes.

---

## Execution order summary

1. **Phase 0** — audit script, validate failure inventory. Half day. (no PR — script lives at workspace root)
2. **Phase 1** — page-range propagation in doc_extractor + heading_toc. Half day, separate PR.
3. **Phase 1.5** — Gemini helpers refactor. Quarter day, **separate worktree + PR**.
4. **Phase 2** — vision_ocr.py module standalone, depends on Phase 1.5. Half day, separate PR.
5. **Phase 3** — wire into annual_report_extractor.py + verifier OCR-flagging + prompt hedge. Half day, separate PR.
6. **Phase 4** — backfill 16 benchmark stocks in tmux. Half day ops.
7. **Re-eval** — run 5 affected agents × 16 stocks, compare DATA_FIX count to 2026-04-23/24/25 baseline. Half day.
8. **Phase 5** — top-50 universe rollout, deferred until Phase 4 quality is confirmed.

Total: ~2.75d engineering + 1d ops/eval = ready for Strategy 2 follow-through (top-50 AR re-extraction populating `ar_five_year_summary`) the day after.
