# Track F (revised) — NIM-only AR Vision Extractor

**Status:** Active, 2026-04-28 — replaces `plans/ar-extractor-v2-native-pdf.md` after losing Gemini access.
**Goal:** Recover the 30 P0 eval issues without Gemini, using only NVIDIA NIM (free) and Track A's heading_toc improvements as the page-range source.
**Effort:** ~2d engineering + 0.5d ops.
**Cost budget:** $0 happy path; ≤$1 worst case via paid Qwen3-VL fallback.

---

## 1. The constraint pivot

`plans/ar-extractor-v2-native-pdf.md` rested on Gemini's 50MB / 1000pp native PDF support — full-AR single call. Gemini access was lost on 2026-04-28. NVIDIA NIM is image-only (4 images/call cap), so full-AR single calls are out (~90 calls per AR busts the free quota). The architecture pivots from **"one call per AR"** to **"targeted page-range calls per problem section,"** combining v1's heading detection (Track A's improvements) with NIM Nemotron vision for the 3-4 sections v1 cannot handle.

Phase 0 spike (2026-04-28) on ETERNAL FY25 segmental — 3 pages → 1 NIM call → 5/5 segments with revenue + EBITDA correct, $0, 10s. Proves the targeted approach.

## 2. What v2 fixes vs what stays on v1

| Section | Current v1 status | v2 plan |
|---------|------------------|---------|
| chairman_letter | works for most (when alias matches) | stays v1 |
| mdna | works for most | stays v1 |
| risk_management | works | stays v1 |
| auditor_report | works (substance score is good) | stays v1 |
| corporate_governance | works | stays v1 |
| brsr | works | stays v1 |
| esop_disclosure | works | stays v1 |
| **related_party** | broken (alias gaps fixed in Track A; some slices still tiny / wrong-match) | **v2 NIM** |
| **segmental** | broken (wrong-heading-match, slice boundaries) | **v2 NIM** |
| **notes_to_financials** | broken when image-heavy or BFSI-specific | **v2 NIM** (industry-routed) |
| **financial_statements** | partial — schedules sometimes incomplete | **v2 NIM** when industry∈{bfsi, insurance} |
| five_year_summary | works (deterministic table parser shipped recently) | stays v1 |

Net: **4 problem sections × NIM**. Other 8 unchanged.

## 3. Required prerequisite: page-range tracking in heading_toc

Currently `heading_toc.py` returns `{char_start, char_end}` per section. NIM needs `{page_start, page_end}` to know which pages to rasterize. Two paths:

| Option | Approach | Effort |
|--------|----------|--------|
| A | Extend `doc_extractor` to record `prov[0].page_no` per Docling heading; propagate through to section_index | 0.5d, exact |
| B | Heuristic: total_chars/total_pages → derive page from char_offset | 1hr, ±2 pages |

**Decision: A**, with B as fallback (A passes through page metadata when Docling has it; B fills gaps).

## 4. Tier policy

Validated against Phase 0 spike. ChatGPT Plus → Codex sign-in did NOT deliver $5 API credits in user's case (2026-04-28 — promo may have ended or be tied to fresh accounts only), so **OpenAI tier is out** unless user opts to add $5 billing manually. NIM-only stands.

| Tier | Endpoint | Model | Cost | Use |
|------|----------|-------|------|-----|
| 0 | NVIDIA NIM | nemotron-nano-12b-v2-vl | $0 (free credits) | Default for ALL section calls (surgical or multi-page chunked). Phase 0 PASS on ETERNAL FY25 segmental. |
| 0' | NVIDIA NIM | nemotron-3-nano-omni-30b-a3b-reasoning | $0 (free credits) | Narrow reserve for derivation tasks (EV rollforward, restated 5yr reconciliation). Avoid for tabular transcription — Phase 0 showed 27KB reasoning + EBIT/EBITDA field confusion. |
| 1 | OpenRouter | nvidia/nemotron-nano-12b-v2-vl:free | $0 (no shared quota with NIM) | NIM 503 / quota-exhaust fallback. |
| 2 | OpenRouter | qwen/qwen3-vl-8b-instruct | $0.08/$0.50 per 1M (~$0.05 cohort) | Disaster recovery if Nemotron down on both endpoints. |
| 3 | Claude Code Agent SDK with vision | Sonnet 4.6 | "free" (subscription) | A/B judge during Phase 4 verification — manual / on-demand, not in production loop. |
| (optional) | OpenAI API | gpt-4o-mini | $0.15/M in, $0.60/M out (~$0.18 cohort) — only if user adds $5 billing | Skip unless user explicitly opts in. Spike script ready at `flow-tracker/scripts/spike_v2_openai_extractor.py`. |

### Routing logic
```
section.page_range_size <= 4   →  Tier 0 (NIM, single call, 4-image cap)
section.page_range_size > 4    →  Tier 0 with chunked batches of 4 pages, results merged
NIM 503 / rate-limit           →  Tier 1 (OpenRouter free Nemotron)
both down                      →  Tier 2 (Qwen3-VL-8B paid, $0.05 cohort)
```

NIM rate limit: 40 req/min. Cohort backfill: ~128 calls = ~3.2 min minimum. Chunked sections add maybe 1-2 calls each — still well within rate budget.

## 5. Implementation phases

### Phase 1 — heading_toc page tracking (0.5d)

**Worktree:** `equity-research-ar-pages`

- [ ] In `flow-tracker/flowtracker/research/doc_extractor.py`, capture `page_no` per heading via `DoclingDocument.iterate_items()` walking `TextItem` with `label='section_header'`, taking `prov[0].page_no`. Add new field `headings_with_pages: list[dict]` to extraction result (each entry: `{text, level, char_offset, page_no}`).
- [ ] In `flow-tracker/flowtracker/research/heading_toc.py`, extend `build_ar_section_index()` to attach `{page_start, page_end}` to each section entry. Strategy: page_start = page_no of matched heading; page_end = page_no of next same-or-shallower heading minus 1 (or last page).
- [ ] Heuristic fallback: if any heading lacks `page_no` (older Docling caches missing prov), derive via `floor(char_offset × total_pages / total_chars)`.
- [ ] **Tests** at `tests/unit/test_heading_toc_pages.py`: synthetic Docling output, assert page ranges; test fallback path.

**Deliverable:** Standalone PR. No behavior change to extractor yet.

### Phase 2 — `vision_section_extractor.py` module (0.5d)

**Worktree:** `equity-research-ar-v2-nim`

- [ ] New file `flow-tracker/flowtracker/research/vision_section_extractor.py`:
  - `_render_pages(pdf_path, page_range, dpi=150) -> list[bytes]` — JPEGs via pypdfium2.
  - `_load_nvidia_api_key()` — reads `~/.config/flowtracker/nvidia.env`.
  - `class _VisionRouter` with methods `extract_section(pdf_path, page_range, section, industry) -> dict | None`:
    - Tier 0 (NIM 12B VL) primary
    - Tier 1 (OpenRouter free) fallback on 503/quota
    - Tier 2 (Qwen3-VL-8B paid) DR; gated by `_BACKFILL_BUDGET_USD`
  - **4-image batching**: page ranges > 4 chunked into multiple calls; payloads merged.
- [ ] Section-specific prompts (one per section name) with required JSON schemas — see §6.
- [ ] **Cost ledger** at `~/.local/share/flowtracker/v2_extraction_ledger.jsonl`. Each call records (timestamp, stock, fy, section, tier, tokens, cost_usd).
- [ ] **Tests** at `tests/unit/test_vision_section_extractor.py`:
  - Mock `requests.post` for NIM; assert image_url content + correct prompt for given section/industry.
  - Mock pypdfium2; assert page-range slicing.
  - Tier fallback: NIM 503 → OpenRouter; OpenRouter timeout → Qwen3 (with budget gate).

### Phase 3 — wire into `annual_report_extractor.py` (0.5d)

**Worktree:** `equity-research-ar-v2-nim`

- [ ] Constants: `OCR_TARGET_SECTIONS = {"segmental", "related_party", "notes_to_financials", "financial_statements"}` and `OCR_TRIGGER_QUALITY_THRESHOLDS` per section (e.g. `segmental` triggers if slice_chars < 1500 OR no digit run ≥4 chars in slice; `related_party` triggers if slice_chars < 800 OR `total_rpt_value_cr` is null after v1 extraction).
- [ ] In `_one()` at `annual_report_extractor.py:860`, after v1 Claude extraction completes for an OCR-target section, check the result against quality thresholds. If it fails:
  1. Look up `section_index[sec]['page_start' / 'page_end']` (from Phase 1).
  2. Call `vision_section_extractor.extract_section(...)`.
  3. If NIM returns valid JSON with substantive content, **replace** v1's null/empty payload with the NIM payload.
  4. Annotate `_extraction_method: "nim_vision"` on that section.
- [ ] CLI flag: `flowtrack research extract-ar --vision-fallback / --no-vision-fallback` (default on).
- [ ] **Tests** at `tests/integration/test_ar_vision_fallback.py`:
  - Synthetic AR with sparse `segmental` slice; mock NIM response → assert v1's null gets replaced and `_extraction_method` flag set.
  - Quality threshold gate: rich slice → NIM not called.
  - Re-run: cached `_extraction_method=nim_vision` → not re-called unless `--force`.

### Phase 4 — Cohort backfill + A/B (0.5d ops)

- [ ] Run on 16 cohort stocks: `for s in <cohort>; do uv run flowtrack research extract-ar -s $s --fy FY25 --force --vision-fallback; done`. Tmux session `ar-v2-backfill`.
- [ ] Track ledger: confirm cumulative cost stays $0 (NIM free tier).
- [ ] Diff each stock's `_v1_baseline.json` (snapshot before Phase 3) vs new output. Spot-check 4 stocks manually:
  - ETERNAL segmental — segments populated with revenue numbers
  - HDFCBANK related_party — disclosures table extracted
  - HINDUNILVR related_party — Form AOC-2 surfaces
  - ICICIBANK notes_to_financials — image-heavy notes resolve

### Phase 5 — Verifier judge (0.25d, optional)

Only run if Phase 4 surfaces ambiguous cases:

- [ ] Use Claude Code Agent SDK (Sonnet 4.6, vision-capable) on the same rasterized pages for 2-3 problem stocks via the in-process subscription. Compare NIM extractions against Claude's. Disagreements >5% on numerics escalate to manual review.

### Phase 6 — Re-eval on 5 affected agents (0.5d ops)

Same procedure as the prior plan §6: business / financials / risk / valuation / sector × cohort. Compare DATA_FIX issue count vs 2026-04-23/24/25 baseline. Target: AR-related bucket (30 issues) drops to ≤10.

## 6. Section prompts (NIM-targeted)

One concise prompt per OCR-target section. All share preamble: *"Return ONLY a JSON object. No prose, no fences. Convert all monetary values to INR Crores."*

### segmental
```json
{
  "reporting_period": "FY25",
  "currency": "INR Cr",
  "segments": [{
    "name": "<segment>",
    "revenue_cr": <number|null>,
    "ebitda_cr": <number|null>,
    "ebit_cr": <number|null>,
    "segment_assets_cr": <number|null>,
    "capex_cr": <number|null>
  }],
  "geographical_breakdown": [{"region": "<name>", "revenue_cr": <number|null>}]
}
```

### related_party
```json
{
  "total_rpt_value_cr": <number|null>,
  "largest_rpts": [{
    "counterparty": "<name>",
    "relationship": "<subsidiary|associate|kmp|relative|joint_venture>",
    "nature": "<service|loan|sale|purchase|guarantee|...>",
    "amount_cr": <number|null>,
    "outstanding_balance_cr": <number|null>,
    "arms_length": <bool|null>
  }],
  "concerns_or_qualifications": ["<text>"]
}
```

### notes_to_financials (industry-routed)
- BFSI: `gnpa_npa_breakup`, `crar_cet1`, `lcr`, `casa_breakdown`, `restructured_advances`
- Insurance: `embedded_value_rollforward`, `vnb_walk`, `roev_decomposition`, `persistency_13_25_49_61`, `solvency_ratio`
- Metals: `nameplate_capacity`, `production_volumes`, `realisation_per_tonne`
- Default: generic `tables: [{name, columns, rows}]`

### financial_statements (industry-routed, BFSI/insurance only — others stay v1)
- BFSI: schedules 1-18 condensed (deposits / advances / capital adequacy)
- Insurance: revenue account + profit & loss in IRDAI format

## 7. Cost projection

| Pass | NIM-only cost | NIM + OpenAI 4o-mini Tier 1 mixed | Notes |
|------|---------------|-----------------------------------|-------|
| Cohort backfill (16 stocks × 4 problem sections) | $0 (~128 NIM calls) | ~$0.18 OpenAI + $0 NIM (~32 OpenAI calls covering multi-page sections, ~32 NIM for 1-3 page sections) | OpenAI tier reduces call count 4× via larger context |
| Universe top-50 backfill | $0 (within NIM free credits) | ~$0.55 | Free if budget-conscious; cheaper-per-call if mixed |
| Quarterly steady-state (~50 ARs/yr) | $0/yr | ~$0.55/yr | $5 Plus credit lasts ~9 yrs at this rate |
| DR (Qwen3-VL-8B if all else down) per cohort | n/a | ~$0.05 | |

**$5 OpenAI Plus credit headroom**: covers ~25 cohort backfills or ~9 universe backfills + iterations. Effectively unlimited for our use.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| NIM credit unit accounting unclear (per-call vs per-token) | Phase 4 tracks ledger; if 128 cohort calls eat <100 credits, no concern. If >1000, switch to OpenRouter Tier 1 default. |
| heading_toc page ranges off-by-one for some stocks | Phase 1 fallback heuristic + Phase 4 spot-check 4 stocks to validate. |
| NIM Nemotron quality drops on BFSI tables (different layout vs ETERNAL test) | Phase 4 spot-checks ICICIBANK and HDFCBANK explicitly; if accuracy <80%, bump those to Tier 0' (Omni reasoning) for BFSI only. |
| 40 req/min rate limit during backfill | Cohort = 128 calls = 3.2 min minimum. Add 0.5s pacing between calls to be safe. |
| HDFCLIFE wrong-PDF cached (still 42pp) | Orthogonal — Track D (re-download) still applies. v2 won't help if the PDF itself is wrong. |
| OpenRouter free Nemotron tier could disappear without notice | Tier 2 (Qwen3-VL-8B paid) is real-money fallback; budget cap protects. |

## 9. Out of scope

- **Concall extraction** — already works.
- **Decks** — separate path.
- **Pre-FY24 ARs** — focus FY25.
- **Full-AR single-call rewrite** — dead with Gemini gone; targeted approach is now permanent.

## 10. Rollback

- Per-stock: env `FLOWTRACKER_AR_VISION_FALLBACK=0`.
- Module disable: revert Phase 3 hook in `_one()`.
- v1 unchanged underneath; vault JSONs back-compat (extra `_extraction_method` key ignored by readers).

## 11. Execution order

1. **Track A** (related_party aliases, done) — keep PR open or merge first.
2. **Phase 1** (heading_toc page tracking) — enables everything downstream.
3. **Phase 2** (vision_section_extractor module standalone with tests).
4. **Phase 3** (wire into annual_report_extractor).
5. **Phase 4** (cohort backfill + A/B spot-check).
6. **Phase 5** (Claude judge on ambiguous cases, optional).
7. **Phase 6** (re-eval on 5 agents).
8. **Track D** (HDFCLIFE wrong-PDF) — orthogonal, can land anytime.

Total: ~2d eng + 0.5d ops. Cost: $0.

## 12. Sources

- [NIM Nemotron Nano 12B V2 VL — model card](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl)
- [Phase 0 spike script](../flow-tracker/scripts/spike_v2_nim_extractor.py) — ETERNAL FY25 segmental PASS
- [OpenRouter Nemotron Nano 12B V2 VL free tier](https://openrouter.ai/nvidia/nemotron-nano-12b-v2-vl:free)
- [OpenRouter Qwen3-VL-8B Instruct (paid DR)](https://openrouter.ai/qwen/qwen3-vl-8b-instruct)
- [OpenAI Codex CLI auth — sign in with ChatGPT](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan) — Plus accounts get $5 in API credits one-time on Codex sign-in.
- [OpenAI API pricing — gpt-4o-mini](https://openai.com/api/pricing/) — $0.15/M input, $0.60/M output, vision included.
