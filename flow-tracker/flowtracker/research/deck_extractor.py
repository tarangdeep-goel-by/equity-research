"""Extract structured insights from investor deck PDFs using vision (Claude Agent SDK).

Pipeline per deck:
  1. pdfium gate (_classify_deck_pdf) rejects Reg 30 cover letters by page count
     + disclosure-marker signature
  2. _render_deck_pages renders every slide to a PNG; the VLM reads the page
     images directly (charts/printed numbers a markdown extractor drops) and
     fills a deck-specific JSON schema
  3. Per-quarter JSON is aggregated into deck_extraction.json alongside the concall
     extraction in fundamentals/

Complements the concall pipeline — decks show polished charts, segmental tables,
and forward guidance slides that the raw concall transcript doesn't expose as
tables. Images-only: a deck's value (charts, segment numbers, guidance) is visual,
so reading rendered pages beats text extraction.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import NamedTuple

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    query,
)

from flowtracker.research.heading_toc import deck_slide_index

logger = logging.getLogger(__name__)

_VAULT_BASE = Path.home() / "vault" / "stocks"
MAX_CONCURRENT_DECK_EXTRACTIONS = 3
# Decks are read as page images (charts/printed numbers Docling drops as
# <!-- image -->). Default to a single VLM call over the whole deck so the model
# prioritizes globally and names segments consistently. Only decks longer than
# SINGLE_CALL_MAX_PAGES fall back to chunked extraction + merge (DECK_CHUNK_SIZE
# pages per call) to bound attention dilution / JSON-output overflow.
SINGLE_CALL_MAX_PAGES = 50
DECK_CHUNK_SIZE = 8

# --- Deck classifier thresholds (mirrors filing_client._looks_like_real_deck) ---
#
# PR #104 added `_looks_like_real_deck` in filing_client.py to gate downloads,
# but the pre-#104 vault still has cover-letter PDFs on disk that bypass that
# check. The deck_extractor classifier below re-applies the same pdfium-based
# logic so re-extraction prunes stale cover letters consistently. Markdown
# heuristics alone (heading count, char length) are fragile for image-heavy
# decks where Docling produces sparse text — Nestlé India FY24-Q2 / FY24-Q3 /
# FY25-Q3 are 1-page Reg 30 cover letters that the previous markdown-only
# rule caught coincidentally; a glossy infographic deck of 30+ pages with low
# Docling text density would have been falsely rejected by the same rule.
_DECK_HARD_REJECT_PAGES = 3            # < 3 pages → never a real deck
_DECK_FIRST3_TEXT_THRESHOLD = 2500     # cover letters front-load <2.5k chars
_DECK_LOW_CONFIDENCE_PAGES = 10        # 3-9 pages w/o disclosure → low-confidence
# Disclosure markers — same set as filing_client._DECK_BODY_DISCLOSURE_MARKERS,
# duplicated here to keep the module self-contained for testability.
_DECK_DISCLOSURE_MARKERS = (
    "dial-in",
    "dial in",
    "analyst / investor meet",
    "analyst/investor meet",
    "disclosure under regulation 30",
    "sebi (listing obligations",
    "conference call dial",
    # Nestlé-style intimation cover letter wording — points the reader at the
    # *real* deck on the company website, contains no deck content itself.
    "regulation 30 of sebi",
    "regulation 30 of the sebi",
    "audio/ video recording",
    "audio-video recording",
    "audio/video recording",
)


class _DeckClassification(NamedTuple):
    is_deck: bool
    confidence: str  # 'high' | 'low'
    reason: str
    pages: int
    first3_chars: int
    has_disclosure_marker: bool


def _classify_deck_pdf(pdf_path: Path) -> _DeckClassification:
    """Decide whether a downloaded ``investor_deck.pdf`` is a real deck.

    pdfium-only (no Docling). Page count is the primary discriminator — cover
    letters are 1-3 pages, real decks are 10-50. Disclosure-marker phrases in
    the first three pages catch the rare multi-page Reg 30 letter. Short PDFs
    in the 3-9 page band without that signature are accepted as low-confidence:
    extraction now reads page images via the VLM, so sparse extractable text is
    no longer a reason to reject (it would falsely drop image-heavy decks).
    Fails open (accept) on any pypdfium2 error so transient failures don't lose
    real decks — mirrors ``_looks_like_real_*`` accept-on-error semantics.
    """
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
        doc = pdfium.PdfDocument(str(pdf_path))
        try:
            pages = len(doc)
            first3 = "".join(
                doc[i].get_textpage().get_text_range() for i in range(min(3, pages))
            )
        finally:
            doc.close()
    except Exception:
        return _DeckClassification(
            True, "low", "pypdfium2 unavailable/parse error — accepting (fail-open)",
            0, 0, False,
        )

    has_disclosure = any(m in first3.lower() for m in _DECK_DISCLOSURE_MARKERS) if first3 else False

    # Hard reject: too few pages to be a deck, period.
    if pages < _DECK_HARD_REJECT_PAGES:
        return _DeckClassification(
            False, "high", f"pdf has only {pages} page(s) — never a real deck",
            pages, len(first3), has_disclosure,
        )
    # Hard reject: short PDF with disclosure markers AND sparse first-3 text —
    # the canonical Reg 30 cover-letter signature.
    if (
        pages < _DECK_LOW_CONFIDENCE_PAGES
        and has_disclosure
        and len(first3.strip()) < _DECK_FIRST3_TEXT_THRESHOLD
    ):
        return _DeckClassification(
            False, "high",
            f"pages={pages} + disclosure markers + first3_chars={len(first3.strip())} "
            f"matches Reg 30 cover-letter signature",
            pages, len(first3), has_disclosure,
        )
    # >=10 pages → confident real deck; 3-9 pages without the cover-letter
    # signature → accept low-confidence (the VLM reads the images regardless).
    confidence = "high" if pages >= _DECK_LOW_CONFIDENCE_PAGES else "low"
    return _DeckClassification(
        True, confidence, f"pages={pages}", pages, len(first3), has_disclosure,
    )

# --- Sector-specific extraction hint ---


def build_extraction_hint(industry: str | None) -> str:
    """Return a short sector-specific mandate paragraph for the deck extraction prompt.

    Decks are visual/headline-driven, so hints are lighter than for ARs — focused on
    must-include chart types and slide categories. Empty string when industry has no
    matching rule.
    """
    if not industry:
        return ""
    ind = industry.lower()

    if "bank" in ind or "financial" in ind:
        return (
            "Sector mandate (BFSI): `charts_described` MUST include the NIM trajectory "
            "chart and the GNPA / NNPA trajectory chart when present in the deck."
        )
    if "pharma" in ind or "drug" in ind:
        return (
            "Sector mandate (Pharmaceuticals): `strategic_priorities` MUST capture the "
            "pipeline / R&D slide content (ANDA filings, key launches, USFDA status) "
            "when shown in the deck."
        )
    if "metal" in ind or "mining" in ind or "steel" in ind or "oil" in ind or "gas" in ind:
        return (
            "Sector mandate (Metals / Oil & Gas): `charts_described` MUST include any "
            "realization / spread chart and any volume / production chart when present."
        )
    if "it" in ind.split() or "software" in ind or "it - software" in ind or "computers" in ind:
        return (
            "Sector mandate (IT Services): `segment_performance` MUST capture the "
            "geography mix and vertical mix slides when shown."
        )
    if "auto" in ind:
        return (
            "Sector mandate (Auto): `segment_performance` MUST capture volumes by "
            "segment (PV / CV / 2W as relevant); `strategic_priorities` MUST capture "
            "EV roadmap slides when shown."
        )
    return ""


# --- JSON schema ---

_DECK_EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "deck_extraction",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "fy_quarter": {"type": "string"},
                "period_ended": {"type": "string"},
                "highlights": {"type": "array", "items": {"type": "string"}},
                "segment_performance": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "revenue_cr": {},
                            "growth_yoy_pct": {},
                            "margin_pct": {},
                            "key_drivers": {"type": "string"},
                            "outlook": {"type": "string"},
                        },
                        "additionalProperties": True,
                    },
                },
                "key_metrics": {
                    "type": "object",
                    "additionalProperties": True,
                },
                "strategic_priorities": {"type": "array", "items": {"type": "string"}},
                "outlook_and_guidance": {"type": "string"},
                "new_initiatives": {"type": "array", "items": {"type": "string"}},
                "charts_described": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slide_title": {"type": "string"},
                            "what_it_shows": {"type": "string"},
                            "key_takeaway": {"type": "string"},
                        },
                    },
                },
                "slide_topics": {"type": "array", "items": {"type": "string"}},
                "extraction_status": {"type": "string"},
            },
        },
    },
}

# --- Prompt ---

DECK_EXTRACTION_PROMPT = """**OUTPUT FORMAT: Return ONLY a single valid JSON object. No prose, no markdown fences, no explanation before or after. Start with `{` and end with `}`.**

You are a buy-side analyst reading an Indian company's investor-presentation deck. You are shown the deck slides as page images. Extract structured insights into the JSON schema below. Read every chart, axis label, table, and printed number directly off the slides — including values printed on bars, lines, and pie segments. Transcribe printed values exactly; only estimate a value from bar/line geometry when no number is printed on the slide, and keep such estimates directional.

Focus on signal — headline numbers, segmental performance, management framing, forward guidance, and strategic priorities. Skip boilerplate (SEBI disclaimers, safe-harbor notices, regulatory cover letters, DIN numbers, e-voting instructions).

Required structure:

```json
{
  "fy_quarter": "<FY26-Q3 format, passed in by caller>",
  "period_ended": "<YYYY-MM-DD>",
  "highlights": [
    "<3-8 headline bullets that management led with — 'revenue up 10%, EBITDA margin expanded 180bps', 'added 120 net stores', etc. Include the actual numbers.>"
  ],
  "segment_performance": {
    "<segment_name_snake_case>": {
      "revenue_cr": <number or null>,
      "growth_yoy_pct": <number or null>,
      "margin_pct": <number or null>,
      "key_drivers": "<what management attributed growth/margins to>",
      "outlook": "<any forward statement specific to this segment>"
    }
  },
  "key_metrics": {
    "<metric_name_snake_case>": "<value with unit — for ANY quantitative KPI that is NOT a revenue segment: net_debt_cr, capex_fy26_cr, order_book_cr, nim_pct, gnpa_pct, casa_pct, gmv_cr, pre_sales_cr, dividend_per_share, utilization_pct, etc. Capture the period in the key when it matters.>"
  },
  "strategic_priorities": [
    "<management's stated priorities — 'premiumization', 'store network rationalization', 'digital transformation of trade channel'. Concrete, not generic.>"
  ],
  "outlook_and_guidance": "<consolidated outlook paragraph — include specific guidance numbers (revenue growth %, margin target, capex plan) where management gave them>",
  "new_initiatives": [
    "<new launches, geography expansion, partnerships, capacity additions announced in this deck>"
  ],
  "charts_described": [
    {
      "slide_title": "<exact slide title>",
      "what_it_shows": "<what the chart/table communicates — '5yr SSSG trend', 'quarterly EBITDA bridge'>",
      "key_takeaway": "<one-line implication>"
    }
    // Include 3-8 most important charts. Skip title slides, table-of-contents, and disclaimer pages.
  ],
  "slide_topics": [
    "<3-8 short lowercase tags drawn from: highlights, segmental, guidance, outlook, strategy, capex, financials, channel_mix, governance, esg, new_launches, market_update, competitive_landscape. Add domain-specific tags only when the canonical list doesn't fit.>"
  ]
}
```

Rules:
- **Never drop a printed number.** Every figure visible on a slide must land somewhere: a structured field if one fits, else `key_metrics` (with a descriptive snake_case key), else verbatim inside the relevant `charts_described.what_it_shows`. Maximize data capture — when in doubt, capture it in `key_metrics`.
- `segment_performance` is ONLY for revenue/business segments. Pipelines, R&D, balance-sheet items, capex, order book, BFSI KPIs (NIM/GNPA/CASA), and any other non-segment metric go in `key_metrics`, not as fake segments.
- `charts_described` must transcribe the chart's actual numbers (axis values, data labels, per-period values) in `what_it_shows`, not just describe the shape.
- All monetary values in Indian Rupees crores (₹ Cr) unless the deck explicitly uses another unit. Preserve the unit if non-standard (e.g. "USD Mn").
- For growth percentages, use the sign (positive for growth, negative for decline).
- If the deck is actually a short corporate notice/letter (not a real presentation — e.g. <5 content slides), set `extraction_status: "not_a_deck"` at the top level and leave other fields empty/null.
- If a field isn't mentioned, set it to null or empty array — don't guess.
- **CRITICAL FORMAT RULE**: Your ENTIRE response must be valid JSON. Start with `{` and end with `}`.
"""


# --- Claude call (mirrors concall_extractor pattern) ---


def _build_image_message(text: str, images: list[str]) -> dict:
    """Streaming-mode user message: a text block followed by one base64-PNG
    image block per page. SDK 0.2.87 streaming mode forwards these blocks to
    the model (verified) — there is no first-class image prompt input."""
    content: list[dict] = [{"type": "text", "text": text}]
    for img in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img},
        })
    return {
        "type": "user",
        "session_id": "",
        "parent_tool_use_id": None,
        "message": {"role": "user", "content": content},
    }


async def _call_claude(
    system_prompt: str, user_prompt: str, model: str,
    max_budget: float = 0.40, max_turns: int = 3,
    output_format: dict | None = None,
    images: list[str] | None = None,
) -> str:
    # max_turns=3 — see annual_report_extractor for rationale (large JSON
    # output can overflow a single turn → error_max_turns → exit code 1).
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
        # Structured JSON extraction — disable extended thinking. See
        # annual_report_extractor._call_claude for the full rationale.
        thinking={"type": "disabled"},
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep",
                          "WebSearch", "WebFetch", "Agent", "Skill",
                          "NotebookEdit", "TodoWrite"],
        stderr=lambda line: logger.warning("[cli-stderr] %s", line),
        env={
            "CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "120000",
        },
        # [""] (not []) workaround for SDK #794 — empty list is falsy and
        # never emits --setting-sources, letting ~/.claude/settings.json
        # hooks leak into every subprocess.
        # https://github.com/anthropics/claude-agent-sdk-python/issues/794
        setting_sources=[""],
        plugins=[],          # no external plugins in extractor subprocess
    )
    if output_format:
        options.output_format = output_format

    if images:
        async def _prompt_stream():
            yield _build_image_message(user_prompt, images)
        prompt_arg: object = _prompt_stream()
    else:
        prompt_arg = user_prompt

    text_blocks: list[str] = []
    result_text = ""
    try:
        async for msg in query(prompt=prompt_arg, options=options):
            if isinstance(msg, RateLimitEvent):
                logger.warning("[deck] rate limited: %s / %s",
                               msg.rate_limit_info.status, msg.rate_limit_info.rate_limit_type)
                continue
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if type(block).__name__ == "TextBlock":
                        text_blocks.append(block.text)
            elif isinstance(msg, ResultMessage):
                result_text = msg.result or ""
    except Exception as exc:
        if not (result_text or text_blocks):
            logger.error("[deck] _call_claude failed with no content: %s: %s", type(exc).__name__, exc)
            raise
        logger.warning("[deck] _call_claude raised %s after capturing content — proceeding", type(exc).__name__)
    return result_text or "\n".join(text_blocks)


def _extract_json(text: str) -> dict:
    text = text.strip()

    def _try_parse(s: str) -> dict:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            repaired = re.sub(r',\s*([}\]])', r'\1', s)
            return json.loads(repaired)

    if text.startswith("{"):
        try:
            return _try_parse(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return _try_parse(m.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return _try_parse(text[start:end + 1])
    raise json.JSONDecodeError("No JSON found", text, 0)


# --- Deck discovery + per-deck extraction ---


def _find_deck_pdfs(symbol: str, quarters: int = 4) -> list[Path]:
    """Return the most recent N investor_deck.pdf paths for a symbol, newest first."""
    # Resolve at call-time so tests monkeypatching HOME work.
    base = Path.home() / "vault" / "stocks" / symbol / "filings"
    if not base.exists():
        return []
    decks: list[tuple[tuple[int, int], Path]] = []
    for quarter_dir in base.iterdir():
        if not quarter_dir.is_dir():
            continue
        deck = quarter_dir / "investor_deck.pdf"
        if not deck.exists():
            continue
        name = quarter_dir.name  # "FY26-Q3"
        try:
            fy = int(name[2:4])
            q = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(name.split("-")[1], 0)
            decks.append(((fy, q), deck))
        except (ValueError, IndexError):
            continue
    decks.sort(key=lambda t: t[0], reverse=True)
    return [path for _, path in decks[:quarters]]


def _quarter_label_from_path(pdf_path: Path) -> str:
    return pdf_path.parent.name  # "FY26-Q3"


def _render_deck_pages(pdf_path: Path, scale: float = 2.0, max_pages: int = 60) -> list[str]:
    """Render each PDF page to a base64-encoded PNG for VLM ingestion.

    Uses pypdfium2 (already a dependency — see _classify_deck_pdf). Capped at
    ``max_pages`` so a pathological deck can't blow up the request payload.
    """
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    doc = pdfium.PdfDocument(str(pdf_path))
    out: list[str] = []
    try:
        for i in range(min(len(doc), max_pages)):
            pil = doc[i].render(scale=scale).to_pil()
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            out.append(base64.standard_b64encode(buf.getvalue()).decode())
    finally:
        doc.close()
    return out


_DECK_LIST_FIELDS = ("highlights", "strategic_priorities", "new_initiatives", "slide_topics")
_EMPTY_VALUES = (None, "", [], {})


def _merge_deck_chunks(chunks: list[dict]) -> dict:
    """Union per-chunk partial extractions into one deck dict.

    Lists are concatenated order-preserving with dedupe; ``charts_described``
    dedupes by lowercased ``slide_title``; ``segment_performance`` merges
    field-wise (first non-empty value wins); ``outlook_and_guidance`` joins
    unique non-empty parts. Per-chunk ``extraction_status`` is intentionally
    dropped — the caller owns the final status.
    """
    merged: dict = {f: [] for f in _DECK_LIST_FIELDS}
    merged["segment_performance"] = {}
    merged["key_metrics"] = {}
    merged["charts_described"] = []
    guidance_parts: list[str] = []
    seen_charts: set[str] = set()

    for c in chunks:
        if not isinstance(c, dict):
            continue
        for f in _DECK_LIST_FIELDS:
            for item in (c.get(f) or []):
                if item and item not in merged[f]:
                    merged[f].append(item)
        for seg, fields in (c.get("segment_performance") or {}).items():
            if not isinstance(fields, dict):
                continue
            tgt = merged["segment_performance"].setdefault(seg, {})
            for fk, fv in fields.items():
                if fv not in _EMPTY_VALUES and tgt.get(fk) in _EMPTY_VALUES:
                    tgt[fk] = fv
        for mk, mv in (c.get("key_metrics") or {}).items():
            if mv not in _EMPTY_VALUES and merged["key_metrics"].get(mk) in _EMPTY_VALUES:
                merged["key_metrics"][mk] = mv
        for ch in (c.get("charts_described") or []):
            if not isinstance(ch, dict):
                continue
            key = (ch.get("slide_title") or "").strip().lower()
            if key and key in seen_charts:
                continue
            if key:
                seen_charts.add(key)
            merged["charts_described"].append(ch)
        g = (c.get("outlook_and_guidance") or "").strip()
        if g and g not in guidance_parts:
            guidance_parts.append(g)

    merged["outlook_and_guidance"] = " ".join(guidance_parts)
    return merged


async def _extract_single_deck(
    pdf_path: Path,
    symbol: str,
    model: str,
    industry: str | None = None,
) -> dict:
    """Extract one deck PDF → structured JSON via images-only VLM extraction."""
    import time as _time
    t0 = _time.time()
    quarter_label = _quarter_label_from_path(pdf_path)

    # Classifier — pdfium-only gate (see _classify_deck_pdf). Rejects Reg 30
    # cover letters by page count + disclosure-marker signature, consistently
    # with filing_client's download-time check.
    classification = _classify_deck_pdf(pdf_path)
    if not classification.is_deck:
        logger.warning(
            "[deck] %s %s: classifier rejected (%s) — pages=%d, first3_chars=%d, "
            "disclosure_marker=%s",
            symbol, quarter_label, classification.reason,
            classification.pages, classification.first3_chars,
            classification.has_disclosure_marker,
        )
        return {
            "fy_quarter": quarter_label,
            "extraction_status": "not_a_deck",
            "extraction_error": classification.reason,
            "pages": classification.pages,
            "first3_chars": classification.first3_chars,
            "has_disclosure_marker": classification.has_disclosure_marker,
        }

    data_quality_note: str | None = None
    if classification.confidence == "low":
        data_quality_note = (
            f"Low-confidence classification: {classification.reason}. "
            "Short deck or classifier ran without full page signal — treat coverage cautiously."
        )
        logger.info(
            "[deck] %s %s: low-confidence accept — %s",
            symbol, quarter_label, classification.reason,
        )

    sector_hint = build_extraction_hint(industry)
    system_prompt = (
        f"{DECK_EXTRACTION_PROMPT}\n\n{sector_hint}"
        if sector_hint
        else DECK_EXTRACTION_PROMPT
    )

    # Images-only extraction: render every slide and let the VLM read the pixels
    # directly (charts/printed numbers Docling drops as <!-- image -->). One call
    # over the whole deck by default so the model prioritizes globally and names
    # segments/metrics consistently; only oversized decks fall back to chunks.
    images = _render_deck_pages(pdf_path)
    total = len(images)
    if total <= SINGLE_CALL_MAX_PAGES:
        batches = [(0, images)]
    else:
        batches = [(i, images[i:i + DECK_CHUNK_SIZE]) for i in range(0, total, DECK_CHUNK_SIZE)]

    partials: list[dict] = []
    for offset, batch in batches:
        start, end = offset + 1, offset + len(batch)
        scope = (
            f"all {total} slides of this deck"
            if len(batches) == 1
            else f"slides {start}-{end} of {total} from this deck"
        )
        user_prompt = (
            f"Company: {symbol}\nQuarter: {quarter_label}\nSource: investor_deck.pdf\n\n"
            f"You are shown {scope} as page images. Extract the JSON for the "
            f"content visible in these slides."
        )
        response = await _call_claude(
            system_prompt, user_prompt, model,
            max_budget=0.40, max_turns=3,
            output_format=_DECK_EXTRACTION_SCHEMA,
            images=batch,
        )
        try:
            partials.append(_extract_json(response))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[deck] %s %s batch %d/%d: JSON parse failed: %s",
                           symbol, quarter_label, offset + 1, len(batches), e)

    if not partials:
        logger.warning("[deck] %s %s: all %d batch(es) failed to parse",
                        symbol, quarter_label, len(batches))
        return {
            "fy_quarter": quarter_label,
            "extraction_status": "failed",
            "extraction_error": "all batches failed to parse",
            "_extraction_mode": "images",
            "_pages_rendered": total,
            "_chunks": len(batches),
        }

    data = _merge_deck_chunks(partials)
    data["fy_quarter"] = quarter_label
    period = next((p.get("period_ended") for p in partials if p.get("period_ended")), None)
    if period:
        data["period_ended"] = period
    data["extraction_status"] = "complete"
    data["_elapsed_s"] = round(_time.time() - t0, 1)
    data["_extraction_mode"] = "images"
    data["_pages_rendered"] = total
    data["_chunks"] = len(batches)
    data["_classifier_confidence"] = classification.confidence
    if data_quality_note:
        data["data_quality_note"] = data_quality_note
    return data


# --- Main pipeline ---


async def extract_decks(
    symbol: str,
    quarters: int = 4,
    model: str = "claude-sonnet-4-6",
    industry: str | None = None,
) -> dict:
    """Extract the last N decks for a symbol, save combined JSON to vault."""
    import time as _time
    t0 = _time.time()
    symbol = symbol.upper()

    pdfs = _find_deck_pdfs(symbol, quarters=quarters)
    if not pdfs:
        raise FileNotFoundError(
            f"No investor_deck.pdf found at ~/vault/stocks/{symbol}/filings/FY??-Q?/investor_deck.pdf"
        )
    logger.info("[deck] %s: %d decks to extract", symbol, len(pdfs))

    sem = asyncio.Semaphore(MAX_CONCURRENT_DECK_EXTRACTIONS)

    async def _with_sem(pdf: Path) -> dict:
        async with sem:
            return await _extract_single_deck(pdf, symbol, model, industry)

    quarter_results = list(await asyncio.gather(*[_with_sem(p) for p in pdfs]))

    result = {
        "symbol": symbol,
        "quarters_analyzed": len(quarter_results),
        "extraction_date": date.today().isoformat(),
        "quarters": quarter_results,
    }

    out_dir = _VAULT_BASE / symbol / "fundamentals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "deck_extraction.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    logger.info("[deck] %s: done in %.1fs, %d quarters extracted",
                symbol, _time.time() - t0, len(quarter_results))
    return result


async def ensure_deck_data(
    symbol: str,
    quarters: int = 4,
    model: str = "claude-sonnet-4-6",
    industry: str | None = None,
) -> dict | None:
    """Incremental extraction — only re-extract decks that don't have a cached quarter.

    Reads existing deck_extraction.json, keeps quarters with complete status,
    re-runs extraction only for missing quarters or those with extraction_status
    in {failed, partial}.
    """
    symbol = symbol.upper()
    pdfs = _find_deck_pdfs(symbol, quarters=quarters)
    if not pdfs:
        logger.info("[deck_ensure] %s: no deck PDFs", symbol)
        return None

    available = {_quarter_label_from_path(p): p for p in pdfs}
    out_path = _VAULT_BASE / symbol / "fundamentals" / "deck_extraction.json"
    existing: dict = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
    cached_quarters = {
        q.get("fy_quarter"): q
        for q in existing.get("quarters", [])
        if q.get("extraction_status") == "complete"
    }

    to_extract = [pdf for label, pdf in available.items() if label not in cached_quarters]
    if not to_extract:
        logger.info("[deck_ensure] %s: all %d quarters cached", symbol, len(available))
        existing.setdefault("quarters_analyzed", len(existing.get("quarters", [])))
        existing["_new_quarters_extracted"] = 0
        return existing

    logger.info("[deck_ensure] %s: extracting %d new quarter(s)", symbol, len(to_extract))
    sem = asyncio.Semaphore(MAX_CONCURRENT_DECK_EXTRACTIONS)

    async def _with_sem(pdf: Path) -> dict:
        async with sem:
            return await _extract_single_deck(pdf, symbol, model, industry)

    new_results = list(await asyncio.gather(*[_with_sem(p) for p in to_extract]))

    # Merge: keep all cached + new, sorted by FY-Q desc
    merged_map = {q["fy_quarter"]: q for q in cached_quarters.values()}
    for q in new_results:
        merged_map[q.get("fy_quarter", "unknown")] = q
    all_quarters = sorted(
        merged_map.values(),
        key=lambda q: _fy_sort_key(q.get("fy_quarter", "FY00-Q0")),
        reverse=True,
    )[:quarters]

    result = {
        "symbol": symbol,
        "quarters_analyzed": len(all_quarters),
        "extraction_date": date.today().isoformat(),
        "quarters": all_quarters,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    result["_new_quarters_extracted"] = len(new_results)
    return result


def _fy_sort_key(fy_quarter: str) -> tuple[int, int]:
    try:
        fy = int(fy_quarter[2:4])
        q = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}.get(fy_quarter.split("-")[1], 0)
        return (fy, q)
    except (ValueError, IndexError):
        return (0, 0)
