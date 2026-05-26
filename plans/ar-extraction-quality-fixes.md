# AR Extraction Quality Fixes — Implementation Plan

**Status:** Active, 2026-04-28 (replaces paused `plans/ar-image-ocr-implementation.md`)
**Predecessor:** `plans/ar-ocr-phase0-findings.md` — diagnosis that triggered this plan
**Goal:** Recover the 30 P0 eval issues across 13 stocks by fixing the actual root causes — heading detection, slice boundaries, an extractor failure, and one wrong-PDF-cached case.
**Effort:** ~3.25d engineering + 0.5d re-eval ops.
**Cost budget:** ~$0 API spend (text-only fixes; one optional re-extract per affected stock).

---

## 1. Why this matters

`plans/ar-ocr-phase0-findings.md` triangulated three independent signals (PDF text density, heading-match logs, slice content) and showed that **none** of the cohort empty sections are image-rendered. Every flagged section traces to one of four root causes — heading-detection alias gaps, slice boundary bugs, a Claude extraction failure on rich input, and a wrong-PDF-cached document. Vision OCR fixes none of these.

The five tracks below address each root cause with the minimum surface change. Tracks A through E are independent — they can land in any order, in parallel worktrees if useful.

## 2. Cohort failure → track mapping

From Phase 0's diagnosis:

| Stock | Section | Diagnosis | Track |
|-------|---------|-----------|-------|
| BANKBARODA | related_party | heading not in index | A |
| SBIN | related_party | heading not in index | A |
| (15 cohort) | chairman_letter | heading alias gap | A |
| ETERNAL | segmental | wrong-heading-match (policy vs data) | B |
| VEDL | segmental | slice cut off at 26 chars | B |
| ICICIBANK | related_party | slice ends before data table | B |
| HINDUNILVR | related_party | slice ends before data table | B |
| HDFCBANK | segmental | rich slice, agent returned null | C |
| HDFCLIFE | (8 sections cover-to-cover) | wrong PDF — 42pp highlights doc | D |
| (cohort-wide) | notes_to_financials, five_year_summary | sections may not be in extractor's request list for some stocks | E |

## 3. Success criteria

1. **Track A**: Re-run audit script post-fix → BANKBARODA + SBIN have `related_party` in `section_index`. ≥10 of the 15 chairman_letter empties resolve.
2. **Track B**: ETERNAL segmental matches the **data** heading, not the policy heading. VEDL segmental slice ≥ 2KB. ICICIBANK + HINDUNILVR related_party slices include the numerical table (≥3KB).
3. **Track C**: HDFCBANK segmental returns populated `segments[].revenue_cr` for at least 3 segments.
4. **Track D**: HDFCLIFE FY25 AR cached PDF is ≥150 pages with ≥300KB of text. Re-extracted JSON has populated mdna, auditor_report, related_party.
5. **Track E** (optional): Default extractor section list includes `notes_to_financials` and `financial_statements` for every stock (`five_year_summary` already in list per Strategy 2 work).
6. **Net**: Re-audit on cohort post-tracks-A-E → OCR-targetable count drops from 9 to ≤2. Re-eval on the 5 affected agents → DATA_FIX issues from this category drop from 30 to ≤10.

## 4. Tracks

### Track A — Heading-detection alias expansion (1d)

**Worktree:** `equity-research-ar-track-a`
**Files:** `flow-tracker/flowtracker/research/heading_toc.py` only.

#### Step 1 — Investigate (2hr)

For each "heading not matched" case, find the actual heading text in the cached docling markdown. Run for BANKBARODA, SBIN (related_party) plus the 15 chairman_letter empties:

```bash
for s in BANKBARODA SBIN HDFCBANK ICICIBANK HDFCLIFE ETERNAL VEDL HINDUNILVR \
         HINDALCO NESTLEIND TCS INFY DRREDDY NYKAA POLICYBZR SUNPHARMA; do
  echo "=== $s ==="
  grep -iE "^#+.*(related part|chairman|managing director|message from)" \
    ~/vault/stocks/$s/filings/FY25/_docling.md | head -10
done
```

Record the actual heading variants in a TSV under `flow-tracker/scripts/audit_ar_heading_variants.tsv` for the alias expansion below.

#### Step 2 — Expand aliases (3hr)

In `heading_toc.py`, the `_SECTION_ALIASES` regex map drives heading→section matching. Extend:

- `related_party`: add aliases for "transactions with related parties", "form aoc-2", "particulars of contracts/arrangements with related parties", "related party disclosures", "note 30 — related party transactions" (and similar note-numbered variants 28-40).
- `chairman_letter`: add "message from the chairman", "chairman's message", "from the desk of the chairman", "chairman & md's message", "managing director's message" (sometimes the chairman is also MD), "letter to shareholders".
- Any others surfaced in Step 1.

Hard requirement: every alias addition must be paired with a regex test in `tests/unit/test_heading_toc.py`.

#### Step 3 — Re-extract + verify (1hr)

```bash
for s in BANKBARODA SBIN HDFCBANK ICICIBANK ETERNAL VEDL HINDUNILVR \
         HINDALCO NESTLEIND TCS INFY DRREDDY NYKAA POLICYBZR SUNPHARMA; do
  uv run flowtrack research extract-ar -s "$s" --fy FY25 --force \
    --sections related_party,chairman_letter
done
```

Re-run audit:
```bash
uv run python flow-tracker/scripts/audit_ar_section_emptiness.py --cohort --fy FY25 --summary-only
```

Expect: `related_party` flag count drops from 4 to ≤1 for cohort. `chairman_letter` drops from 15 to ≤5.

**Tests:** unit alias tests + one integration test that loads a cached docling fixture and asserts `related_party` shows up in `section_index`.

### Track B — Slice boundary fixes (1d)

**Worktree:** `equity-research-ar-track-b`
**Files:** `flow-tracker/flowtracker/research/heading_toc.py` (only — same file as A but separate concern).

#### B1 — ETERNAL pattern (wrong-heading-match)

The accounting-policies section "n) Segment reporting" matches the segmental alias before the actual data table heading. Two fixes possible:

- **Reject policy headings**: pattern `^[a-z]\)\s` (lower-case letter + paren) is a strong signal for accounting-policies-table-of-contents. Add to a `_POLICY_HEADING_REJECT` regex applied in `_pick_canonical_match()`.
- **Prefer data-rich candidates**: when multiple candidates exist, prefer the one whose slice contains digit-density above a threshold (≥0.005 digits/char). The current code (line 418ish) picks the largest size_chars candidate; replace size with `size × digit_density_score`.

Decision: ship both. Reject policy headings first (cheap), then digit-density tiebreaker for the residual.

#### B2 — VEDL pattern (slice cut off at 26 chars)

The slice `char_end` is the next heading at any level. Should be the next heading at the same-or-shallower level. Verify in `build_ar_section_index` — if the bug is there, fix and add a test where a `## H2 → ### H3 → ### H3 → ## H2` doc returns the correct slice for the first H2 (should encompass both H3 children).

#### B3 — ICICIBANK / HINDUNILVR pattern (slice ends before table)

Likely B2 is the same bug — slice cut off too early. If the heading after the section title is at a deeper level (### or table heading), the slice should extend through the deeper headings until the next same-or-shallower one.

#### Verification

Re-run audit + spike script (the page-density check from Phase 0) → ETERNAL segmental should now match the data heading; VEDL segmental should be ≥2KB; ICICIBANK + HINDUNILVR related_party slices should be ≥3KB and contain ≥30 numerics.

**Tests:** unit tests on `build_ar_section_index` + `slice_section` covering: nested headings, policy-heading rejection, digit-density tiebreaker.

### Track C — HDFCBANK segmental extraction failure (0.5d)

**Worktree:** `equity-research-ar-track-c`
**Files:** likely `flow-tracker/flowtracker/research/annual_report_extractor.py` (section prompts or chunking).

The slice is rich (62KB, 368 numerics), the heading match is correct ("Segment reporting for the year ended March 31, 2025 is given below:"), and the agent still returned `{"segments": [...all null...]}`. Three hypotheses:

1. **Chunk split breaks the table**: line 116 `_split_section_text` splits at 80KB. 62KB shouldn't split, but the split heuristic might break inside rows if it landed on the boundary.
2. **Prompt expects column names HDFCBANK doesn't use**: BFSI segmental tables usually have "Treasury / Wholesale / Retail / Other Banking" columns, not the generic "Revenue / EBITDA / Margin" the prompt assumes.
3. **Markdown table format unrecognized**: BFSI Schedule III tables sometimes render as multi-line headers or "merged" cells in the markdown.

#### Investigation

```bash
# Run with logging
FLOWTRACKER_LOG_LEVEL=DEBUG uv run flowtrack research extract-ar -s HDFCBANK --fy FY25 \
  --force --sections segmental 2>&1 | tee /tmp/hdfcbank-segmental-debug.log
```

Manually read the slice content and the Claude response. Identify which hypothesis fires.

#### Fix

Most likely outcome: prompt needs sector-aware schema. Extend `_SEGMENTAL_PROMPT` with a BFSI branch (industry hint already passed in) that lists Treasury/Wholesale/Retail/Other Banking as expected segment names and asks the agent to map the actual table columns into those buckets when present.

**Tests:** golden-file test using the actual HDFCBANK segmental slice; mock Claude to assert the right prompt is selected for `industry='bfsi'`.

### Track D — HDFCLIFE wrong-PDF re-download (0.25d)

**Worktree:** `equity-research-ar-track-d`
**Files:** `flow-tracker/flowtracker/research/ar_downloader.py`.

#### Investigation

Walk `ar_downloader.py` discovery logic. Check why the 42-page highlights doc beat the actual full AR for HDFCLIFE FY25. Likely the IR website lists multiple AR-named files and the heuristic picked the smallest/newest.

#### Fix

Add a "minimum AR pages" gate — if a candidate AR has < 100 pages and another candidate has > 100, prefer the larger. Bonus: log the rejected candidates so a re-audit can spot similar issues.

#### Re-download

```bash
rm ~/vault/stocks/HDFCLIFE/filings/FY25/{annual_report.pdf,_docling.md,_heading_index.json}
rm ~/vault/stocks/HDFCLIFE/fundamentals/annual_report_FY25.json
uv run flowtrack research extract-ar -s HDFCLIFE --fy FY25 --force
```

Verify: PDF ≥ 150 pages; JSON has populated mdna, auditor_report, related_party.

**Tests:** unit test on `ar_downloader.py` candidate-selection with a synthetic IR website file list (3 candidates: 30pp highlights, 220pp full AR, 8pp summary) → expect 220pp pick.

### Track E — Section-list completeness (0.5d, optional)

**Worktree:** `equity-research-ar-track-e`
**Files:** `flow-tracker/flowtracker/research/annual_report_extractor.py` (default sections list).

#### Investigation

Audit which stocks DON'T have `notes_to_financials`, `financial_statements` keys in their AR JSON. The audit script's section coverage already captures this — extend `_classify_section` to also report "not attempted" and re-run.

#### Fix

If multiple stocks are missing these, either:
- Add to default sections list (impacts every AR re-extract — non-trivial cost).
- OR add only when industry hint is `insurance` / `bfsi` (where these sections are mandatory for thesis: EV, NPA breakups).

Decision: industry-conditional add. BFSI + insurance get `notes_to_financials` mandatory; others get it on-demand via `--sections` flag.

**Tests:** integration test asserting industry='insurance' triggers `notes_to_financials` in the section list.

## 5. Phase 0 artifact reuse

`flow-tracker/scripts/audit_ar_section_emptiness.py` is the diagnostic for re-validation. After each track lands, re-run with `--cohort --fy FY25 --summary-only` and confirm flagged-row count decreases. After all five tracks, re-run with no flags (full universe) and review the OCR-targetable summary — should be < 5 stocks. If genuine image cases surface there, re-open `plans/ar-image-ocr-implementation.md` for a narrowly-scoped Track F.

## 6. Re-eval after tracks land

Tracks A-E touch heading detection, slice boundaries, prompt routing, and document discovery — none of these touch the agent prompts directly. So re-running the 5 affected specialists (Business, Financials, Risk, Valuation, Sector) on the 16 cohort stocks should automatically pick up the improved AR data via the existing `get_annual_report` MCP tool path.

```bash
# Per-stock, per-agent
for s in HDFCBANK SBIN BANKBARODA ICICIBANK HINDALCO HDFCLIFE \
         ETERNAL VEDL HINDUNILVR; do
  for a in business financials risk valuation sector; do
    uv run flowtrack research autoeval -a "$a" --stocks "$s" 2>&1 | tee -a /tmp/ar-quality-reeval.log
  done
done
```

Compare DATA_FIX count vs the 2026-04-23/24/25 baseline (172 → minus the AR-image-OCR bucket of 30). Target: that bucket drops to ≤10.

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Track A alias additions cause regressions in stocks where the old aliases worked | Each alias addition gets a unit test against existing fixtures; full pytest suite must stay green. |
| Track B "policy heading reject" pattern (`^[a-z]\)`) is too aggressive | Apply as tiebreaker, not blanket reject — only fires when an alternative match exists. |
| HDFCBANK Track C is actually a Claude-token-window issue | If sector-aware prompt doesn't fix it, fall back to splitting the BFSI segmental table by row and extracting per-segment. |
| Re-extracting all cohort ARs costs significant Claude time | One AR re-extract is ~30-60s. 16 stocks × 1 re-extract = ~15min. Acceptable. |

## 8. Out of scope

- **Vision OCR**: deferred unless re-audit surfaces genuine image cases.
- **Pre-FY25 AR re-extracts**: focus is FY25.
- **Concall / deck extraction**: separate pipeline, separate plans.

## 9. Execution order

Independent tracks — propose this sequencing to keep PRs reviewable:

1. **Track A** (heading aliases) — first, biggest leverage (covers 19+ rows).
2. **Track B** (slice boundaries) — second, may resolve some chairman_letter / mdna empties as a side effect.
3. **Track D** (HDFCLIFE re-download) — parallel to A/B; isolated change.
4. **Track C** (HDFCBANK extraction) — needs A/B landed first because the slice boundaries affect the input.
5. **Track E** (section list) — last, optional. Skip if A-D move the eval needle enough.
6. **Re-audit** — after each track. Final cohort audit after E.
7. **Re-eval** — after final audit confirms recovery.

Total: ~3.25d engineering + 0.5d ops = under 4 days.
