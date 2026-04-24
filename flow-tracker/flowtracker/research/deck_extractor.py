"""Extract structured insights from investor deck PDFs using Docling + Claude Agent SDK.

Pipeline per deck:
  1. doc_extractor.extract_to_markdown() → Docling produces markdown + heading index
  2. Claude Sonnet 4.6 reads the markdown, fills a deck-specific JSON schema
  3. Per-quarter JSON is aggregated into deck_extraction.json alongside the concall
     extraction in fundamentals/

Complements the concall pipeline — decks show polished charts, segmental tables,
and forward guidance slides that the raw concall transcript doesn't expose as
tables. Concalls stay on pdfplumber (see doc_extractor.py notes).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    query,
)

from flowtracker.research.doc_extractor import extract_to_markdown
from flowtracker.research.heading_toc import deck_slide_index

logger = logging.getLogger(__name__)

_VAULT_BASE = Path.home() / "vault" / "stocks"
MAX_CONCURRENT_DECK_EXTRACTIONS = 3

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

You are a buy-side analyst reading an Indian company's investor-presentation deck. Extract structured insights into the JSON schema below. The deck has been converted to markdown by Docling — slide titles are H2/H3 headings, tables are rendered as markdown tables, and image placeholders (<!-- image -->) indicate charts whose titles and surrounding context you should interpret.

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
- All monetary values in Indian Rupees crores (₹ Cr) unless the deck explicitly uses another unit. Preserve the unit if non-standard (e.g. "USD Mn").
- For growth percentages, use the sign (positive for growth, negative for decline).
- If the deck is actually a short corporate notice/letter (not a real presentation — e.g. <5 content slides), set `extraction_status: "not_a_deck"` at the top level and leave other fields empty/null.
- If a field isn't mentioned, set it to null or empty array — don't guess.
- **CRITICAL FORMAT RULE**: Your ENTIRE response must be valid JSON. Start with `{` and end with `}`.
"""


# --- Claude call (mirrors concall_extractor pattern) ---


async def _call_claude(
    system_prompt: str, user_prompt: str, model: str,
    max_budget: float = 0.40, max_turns: int = 3,
    output_format: dict | None = None,
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
    text_blocks: list[str] = []
    result_text = ""
    try:
        async for msg in query(prompt=user_prompt, options=options):
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


async def _extract_single_deck(
    pdf_path: Path,
    symbol: str,
    model: str,
    industry: str | None = None,
) -> dict:
    """Extract one deck PDF → structured JSON. Handles Docling + Claude extraction."""
    import time as _time
    t0 = _time.time()
    quarter_label = _quarter_label_from_path(pdf_path)

    # Docling pass (cached via doc_extractor)
    cache_dir = pdf_path.parent
    extraction = extract_to_markdown(pdf_path, cache_dir)

    # Guard against misclassified "decks" (corporate notices, 1-2 page letters)
    if len(extraction.headings) < 3 or len(extraction.markdown) < 2000:
        logger.warning(
            "[deck] %s %s: sparse document (%d headings, %d chars) — marking not_a_deck",
            symbol, quarter_label, len(extraction.headings), len(extraction.markdown),
        )
        return {
            "fy_quarter": quarter_label,
            "extraction_status": "not_a_deck",
            "extraction_error": "Fewer than 3 headings or <2KB content — likely a corporate notice, not a deck",
            "headings_detected": len(extraction.headings),
            "chars": len(extraction.markdown),
        }

    user_prompt = (
        f"Company: {symbol}\nQuarter: {quarter_label}\n"
        f"Source: investor_deck.pdf\n\n"
        f"## Deck markdown (Docling-extracted, {len(extraction.headings)} headings, "
        f"{len(extraction.markdown)} chars)\n\n"
        f"{extraction.markdown}"
    )

    sector_hint = build_extraction_hint(industry)
    system_prompt = (
        f"{DECK_EXTRACTION_PROMPT}\n\n{sector_hint}"
        if sector_hint
        else DECK_EXTRACTION_PROMPT
    )
    response = await _call_claude(
        system_prompt, user_prompt, model,
        max_budget=0.40, max_turns=1,
        output_format=_DECK_EXTRACTION_SCHEMA,
    )

    try:
        data = _extract_json(response)
        data.setdefault("fy_quarter", quarter_label)
        data["extraction_status"] = data.get("extraction_status", "complete")
        data["_elapsed_s"] = round(_time.time() - t0, 1)
        data["_docling_cached"] = extraction.from_cache
        data["_docling_degraded"] = extraction.degraded
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("[deck] %s %s: JSON parse failed: %s", symbol, quarter_label, e)
        return {
            "fy_quarter": quarter_label,
            "extraction_status": "failed",
            "extraction_error": f"JSON parse: {e}",
            "raw_response": response[:2000],
        }


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
