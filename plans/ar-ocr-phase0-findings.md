# Phase 0 Findings — AR Image-OCR Plan

**Date:** 2026-04-28
**Status:** STOP-AND-RECONSIDER. Phase 0 invalidates the OCR premise.

---

## TL;DR

The original `plans/ar-image-ocr-implementation.md` rests on the assumption that the 30 P0 eval issues come from "modern Indian ARs shipping critical tables as rasterized images." **That assumption does not hold for the 16 benchmark cohort.** Phase 0 audit shows:

- Every cohort AR PDF has rich extractable text (2400-6100 chars/page average).
- Zero cases of pure-image PDFs.
- Zero cases of image-rendered tables confirmed via page-level density check.

The actual root causes of the empty sections are **heading-detection and slice-boundary bugs in `heading_toc.py`** and one **agent-extraction failure** with abundant input. OCR would address none of these directly.

## What Phase 0 ran

1. **Audit script** (`flow-tracker/scripts/audit_ar_section_emptiness.py`) — walked all `~/vault/stocks/*/fundamentals/annual_report_FY25.json`, classified sections via three signals: `hard_empty` (status=section_not_found_or_empty / chars<200), `soft_empty` (`_chars_extracted_from < 500`), `fields_null` (structured keys all null + free text says "data not provided").
2. **PDF text-density check** — for each flagged section, used `pypdfium2` to extract raw text from PDF pages where the section heading appears, measured chars/page.
3. **Slice inspection** — for each flagged section, loaded the cached docling markdown + heading_index, ran `build_ar_section_index` and `slice_section`, inspected what Claude actually saw.

## Cohort findings (16 benchmark stocks, FY25)

### 7 OCR-targetable cases per the audit:

| Stock      | Section        | Slice chars | Matched heading                                      | Numerics in slice | Real cause |
|------------|----------------|-------------|------------------------------------------------------|-------------------|------------|
| ETERNAL    | segmental      | 2307        | `"n) Segment reporting"` — accounting **policy**     | 0                 | **Wrong-heading-match** (policy section, real data table is elsewhere) |
| HDFCBANK   | segmental      | **62187**   | `"Segment reporting for the year ended March 31, 2025"` | **368**           | **Claude extraction failure** — agent had rich data and still returned null |
| VEDL       | segmental      | **26**      | `"5 Segment Information"`                            | 0                 | **Slice cut off** at 26 chars — section_index `char_end` boundary wrong |
| ICICIBANK  | related_party  | 1465        | `"RELATED PARTY TRANSACTIONS"`                       | 6                 | **Slice partial** — only first 1465 chars; the numerical table follows but isn't included |
| BANKBARODA | related_party  | —           | NOT IN INDEX                                         | —                 | **Heading not matched** — alias regex missed it |
| SBIN       | related_party  | —           | NOT IN INDEX                                         | —                 | **Heading not matched** |
| HINDUNILVR | related_party  | 2141        | `"Related Party Transactions"`                       | 6                 | **Slice partial** |

### HDFCLIFE — separate issue

Cohort audit shows HDFCLIFE FY25 with 8 hard_empty sections cover-to-cover. Inspection: the cached PDF is **42 pages, 498KB**. That's not the full AR. It's the highlights/abstract document that HDFC Life publishes alongside the integrated AR. **Fix: re-download the actual full AR.** Out of OCR scope.

### Other cohort flagged sections

`chairman_letter` is `hard_empty` in 15/16 stocks; `mdna` in 11. Inspection of one (`ICICIBANK chairman_letter`) shows the heading exists in the AR but the alias-regex doesn't match the exact phrasing. Same pattern as `BANKBARODA related_party`. **Cause: heading-detection alias coverage, not OCR.**

## What this means for the OCR plan

| Original assumption | Phase 0 reality |
|---------------------|-----------------|
| "Tables ship as rasterized images" | **Not observed in cohort.** All page text-extractable. |
| "30 issues across 13 stocks fixed by vision OCR" | At most 0 of these are image-OCR cases; possibly some image-rendered tables exist outside this cohort, but none confirmed. |
| "Cost ~$10 backfill" | Irrelevant — there's nothing for OCR to do. |
| "Fix surface: `annual_report_extractor.py` add OCR fallback" | Wrong file. Fix surface is `heading_toc.py` (alias coverage + slice boundaries) and possibly the section extraction prompt for HDFCBANK. |

## Recommended pivot

**Replace `ar-image-ocr-implementation.md` with `ar-extraction-quality-fixes.md`.** New plan would target:

### Track A — Heading-detection alias expansion (1d)
- Add aliases for related-party section variants surfaced in BANKBARODA, SBIN ARs (need to grep their `_docling.md` for the actual heading text).
- Add chairman_letter alias coverage (15 cohort stocks miss this).
- Test: post-fix, every cohort stock has `related_party` and `chairman_letter` in `section_index`.

### Track B — Slice boundary fix (0.5d)
- Investigate why ETERNAL `segmental` matched accounting-policy "n) Segment reporting" instead of the data table. Likely the alias regex prefers the first match by char_offset; needs a "prefer larger candidate" heuristic OR specifically reject policy-section matches (heading prefixed with letter-paren like `n)`, `m)`).
- Investigate why VEDL `segmental` slice is 26 chars — `char_end` boundary computed wrong (probably matched the next-heading at any level, should restrict to same-or-shallower).
- Investigate why ICICIBANK / HINDUNILVR `related_party` slices truncate before the data table.

### Track C — HDFCBANK extraction failure (0.5d)
- 62KB slice with 368 numerics → "fields_null". Either:
  - Section prompt is too rigid (expects specific column names that HDFCBANK doesn't use)
  - 80KB chunk-split (line 116) is breaking the table mid-row
- Read the slice manually, run the extractor with verbose logging, identify why Claude returns null.

### Track D — HDFCLIFE re-download (0.25d)
- Audit `ar_downloader.py` logic — why did it cache the 42-page highlights doc? Add a heuristic: if AR PDF < 100 pages and IR website lists multiple AR documents, prefer the largest.
- Re-download HDFCLIFE FY25 full AR; re-run extractor.

### Track E — Extractor section list extension (0.5d, optional)
- Audit shows `notes_to_financials`, `five_year_summary`, `financial_statements` are missing from the extractor's `sections` list for some stocks. Confirm and add to default list. (`section_index` shows them populated for ETERNAL but several other stocks may not even attempt these sections.)

### Vision OCR — deferred to Track F (0.5d implementation, build only when needed)
- Build vision_ocr.py module per original plan §5 Phase 2, but only wire it as a fallback when:
  - Tracks A-D land
  - A re-audit identifies sections that are still empty AND the corresponding PDF pages have <600 chars/page text density (genuine image rendering)
- Without confirmed image-rendered cases, this is speculative work.

## Implementation cost (revised)

- **Tracks A-E**: ~2.75d engineering (mostly text-only fixes, no API calls)
- **Track F**: deferred until a re-audit identifies genuine image cases
- **Re-eval after A-E**: 0.5d
- **Total: ~3.25d** (similar to original) but with **higher confidence of fixing the actual issues**.

## Suggested next step

User decision required. Two paths:

1. **Pivot path**: archive `ar-image-ocr-implementation.md`, draft `ar-extraction-quality-fixes.md` covering Tracks A-E. Start Track A in a worktree.
2. **Sample-verify path**: spike one more session digging into 2-3 of the diagnosed failures (run them through the extractor with verbose logging) to confirm the diagnosis before committing to a new plan. ~2hr.

Recommend (1). The diagnosis is grounded in three independent signals (text-density, heading-match, slice-content) and the Track A-E surface is small enough that any wrong-call surfaces fast.

## Artifacts produced this phase

- `flow-tracker/scripts/audit_ar_section_emptiness.py` — keep, reusable for re-audit after fixes.
- This findings doc.

## What did NOT change

- The 30 P0 eval issues in `plans/eval-data-fixes-next-session.md` are still real — agents are still missing data. The fix path is just different (extraction quality, not OCR).
