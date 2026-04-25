"""Extract structured insights from annual report PDFs using Docling + Claude.

Unlike concalls (text-only, prose) and decks (chart-heavy, polished), ARs are
massive (150-500pp) with a mix of integrated reporting, financial statements,
and SEBI-mandated disclosures. Strategy:
  1. Docling converts the full PDF to markdown (cached via doc_extractor).
  2. heading_toc identifies canonical sections (MD&A, risk, auditor, CG, BRSR,
     related_party, notes, financial_statements).
  3. Per section, a targeted Claude extraction call fills a schema specific
     to that section. Default skips the heavy Notes + Financial Statements
     sections unless --full.
  4. Per-year extraction cached to annual_report_FY??.json.
  5. Cross-year narrative compares 2 ARs: YoY KAM changes, contingent-liab
     trajectory, board-comp changes, strategic-framing evolution.

Vault: ~/vault/stocks/{SYMBOL}/fundamentals/annual_report_FY??.json
     + ~/vault/stocks/{SYMBOL}/fundamentals/annual_report_cross_year.json
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
    CLIConnectionError,
    ProcessError,
    RateLimitEvent,
    ResultMessage,
    query,
)

from flowtracker.research.ar_downloader import find_ar_pdfs
from flowtracker.research.doc_extractor import extract_to_markdown
from flowtracker.research.heading_toc import (
    build_ar_section_index,
    section_size_summary,
    slice_section,
)

logger = logging.getLogger(__name__)

_VAULT_BASE = Path.home() / "vault" / "stocks"
MAX_CONCURRENT_AR_EXTRACTIONS = 2  # ARs are heavy — keep concurrency modest

# Sections extracted by default. Heavy sections opt-in via --full.
# BRSR is ESG / sustainability disclosure — not currently consumed by any
# specialist agent prompt or sector mandate, so it's opt-in to avoid the
# per-AR cost and reduce SDK subprocess churn during Phase 0b.
DEFAULT_SECTIONS = (
    "chairman_letter",
    "mdna",
    "risk_management",
    "auditor_report",
    "corporate_governance",
    "related_party",
    "segmental",
)
FULL_ONLY_SECTIONS = (
    "brsr",
    "notes_to_financials",
    "financial_statements",
)

# Token budget guard — if a section slice exceeds this, truncate before sending
# to Claude. Realistic section sizes: MD&A 20-80KB, Risk 10-40KB, Auditor 10-20KB,
# CG 20-40KB, BRSR 30-80KB. Notes can be 200-500KB (hence opt-in).
SECTION_CHAR_CAP = 120_000

# --- Retry + chunking config (post-eval v2 E14) ---
# Retry schedule (seconds) for transient per-section extraction failures —
# SDK subprocess crashes, connection drops, OSError on the pipe, timeouts.
# Three retries on top of the initial attempt.
RETRY_DELAYS_SEC: tuple[int, ...] = (30, 60, 120)

# Section chunking: sections larger than this get split before extraction, so
# a single Claude call never sees more than CHUNK_SIZE_BYTES of context at once.
# Thresholds tuned to match realistic section sizes — MD&A / BRSR / CG sometimes
# exceed 80KB on large ARs.
CHUNK_TRIGGER_BYTES = 80_000
CHUNK_SIZE_BYTES = 60_000

# Exceptions considered transient — retry on these.
_TRANSIENT_EXC = (CLIConnectionError, ProcessError, TimeoutError, OSError, ConnectionError)


class _ClaudeSubprocessCrash(Exception):
    """SDK subprocess exited with no content captured.

    Raised by `_call_claude` when the underlying Claude Agent SDK raises a
    bare `Exception("Command failed with exit code 1")` (or similar subprocess-
    level crash) *before* any text or ResultMessage was captured. The bare
    Exception class isn't in `_TRANSIENT_EXC` so it wouldn't retry otherwise;
    wrapping lets `_extract_with_retry` catch these specifically without
    swallowing programmer errors.
    """

    def __init__(self, original: BaseException):
        super().__init__(f"{type(original).__name__}: {original}")
        self.original = original


def _split_section_text(text: str, chunk_size: int = CHUNK_SIZE_BYTES) -> list[str]:
    """Split a section's markdown into chunks <= chunk_size, preferring paragraph
    boundaries (double newline). Falls back to hard splits when a single paragraph
    exceeds chunk_size.
    """
    if len(text) <= chunk_size:
        return [text]
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        # +2 for the "\n\n" separator we'll re-insert.
        extra = len(para) + (2 if current else 0)
        if current and current_len + extra > chunk_size:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        elif len(para) > chunk_size and not current:
            # Paragraph alone exceeds chunk size — hard-split it.
            for i in range(0, len(para), chunk_size):
                chunks.append(para[i:i + chunk_size])
            current = []
            current_len = 0
        else:
            current.append(para)
            current_len += extra
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _merge_chunk_payloads(payloads: list[dict]) -> dict:
    """Merge per-chunk extraction dicts into one. For each key across chunks:
      - list values: concatenate
      - dict values: shallow-merge (later chunks override earlier scalars,
        union list-of-dict sub-fields where keys collide with lists)
      - scalar values: take the latest non-null
    Keys starting with '_' (metadata like _chars_extracted_from) are handled
    specially: _chars_extracted_from is summed.
    """
    merged: dict = {}
    for p in payloads:
        if not isinstance(p, dict):
            continue
        for key, value in p.items():
            if key == "_chars_extracted_from":
                merged[key] = merged.get(key, 0) + (value or 0)
                continue
            if key not in merged:
                merged[key] = value
                continue
            existing = merged[key]
            if isinstance(existing, list) and isinstance(value, list):
                merged[key] = existing + value
            elif isinstance(existing, dict) and isinstance(value, dict):
                # Shallow merge — inner lists concatenate, scalars override when non-null.
                combined = dict(existing)
                for k2, v2 in value.items():
                    if k2 in combined and isinstance(combined[k2], list) and isinstance(v2, list):
                        combined[k2] = combined[k2] + v2
                    elif v2 is not None:
                        combined[k2] = v2
                merged[key] = combined
            elif value is not None:
                merged[key] = value
    return merged


async def _extract_with_retry(
    section_name: str,
    section_md: str,
    symbol: str,
    fy_label: str,
    model: str,
    industry: str | None = None,
) -> tuple[dict, bool]:
    """Call _extract_section with retry on transient subprocess/network failures.

    Returns (payload_dict, retried_flag). retried_flag=True if we needed ANY
    retry attempt before succeeding. Raises the last exception if all attempts
    fail — caller wraps in try/except to record the section as failed.
    """
    last_exc: BaseException | None = None
    retried = False
    attempts = 1 + len(RETRY_DELAYS_SEC)
    for attempt in range(attempts):
        if attempt > 0:
            delay = RETRY_DELAYS_SEC[attempt - 1]
            retried = True
            logger.info(
                "[ar] %s %s: section '%s' retry attempt %d/%d after %ds...",
                symbol, fy_label, section_name, attempt, len(RETRY_DELAYS_SEC), delay,
            )
            await asyncio.sleep(delay)
        try:
            data = await _extract_section(
                section_name, section_md, symbol, fy_label, model, industry,
            )
            return data, retried
        except _TRANSIENT_EXC as exc:
            last_exc = exc
            logger.warning(
                "[ar] %s %s: section '%s' transient failure (attempt %d): %s: %s",
                symbol, fy_label, section_name, attempt, type(exc).__name__, exc,
            )
        except _ClaudeSubprocessCrash as exc:
            # SDK raised bare Exception("Command failed with exit code 1") with
            # no content — treat as transient and retry. The wrapper was raised
            # by `_call_claude` only when nothing had been captured yet.
            last_exc = exc
            logger.warning(
                "[ar] %s %s: section '%s' subprocess crash (attempt %d): %s",
                symbol, fy_label, section_name, attempt, exc,
            )
    logger.error(
        "[ar] %s %s: section '%s' gave up after %d attempts: %s",
        symbol, fy_label, section_name, attempts, last_exc,
    )
    raise last_exc if last_exc is not None else RuntimeError("retry exhausted")


async def _extract_section_chunked(
    section_name: str,
    section_md: str,
    symbol: str,
    fy_label: str,
    model: str,
    industry: str | None = None,
) -> tuple[dict, bool]:
    """Chunking wrapper: if section_md exceeds CHUNK_TRIGGER_BYTES, split into
    smaller chunks, run retry-wrapped extraction per chunk, then merge payloads.

    Returns (merged_payload, retried_flag).
    """
    if len(section_md) <= CHUNK_TRIGGER_BYTES:
        return await _extract_with_retry(
            section_name, section_md, symbol, fy_label, model, industry,
        )
    chunks = _split_section_text(section_md, CHUNK_SIZE_BYTES)
    logger.info(
        "[ar] %s %s: section '%s' %d chars -> %d chunks",
        symbol, fy_label, section_name, len(section_md), len(chunks),
    )
    payloads: list[dict] = []
    any_retried = False
    for idx, chunk in enumerate(chunks, start=1):
        logger.info(
            "[ar] %s %s: section '%s' chunk %d/%d (%d chars)",
            symbol, fy_label, section_name, idx, len(chunks), len(chunk),
        )
        data, retried = await _extract_with_retry(
            section_name, chunk, symbol, fy_label, model, industry,
        )
        any_retried = any_retried or retried
        payloads.append(data)
    merged = _merge_chunk_payloads(payloads)
    merged["_chunked"] = len(chunks)
    return merged, any_retried


# --- Sector-specific extraction hint ---


def build_extraction_hint(industry: str | None) -> str:
    """Return sector-specific mandate paragraph for the AR extraction system prompt.

    Mirrors `concall_extractor.build_extraction_hint` (which delegates to
    `sector_kpis.build_extraction_hint`) but adds *section-level* mandates that
    are AR-specific — what each canonical section MUST surface for a given
    sector. Empty string when the industry doesn't match any rule.
    """
    if not industry:
        return ""
    ind = industry.lower()

    if "bank" in ind or "financial" in ind:
        return (
            "Sector mandate (BFSI): the `segmental` section MUST surface CASA ratio, "
            "GNPA, NNPA, and PCR (provision coverage ratio) when disclosed. The "
            "`risk_management` section MUST capture capital adequacy — CET-1, Tier-1, "
            "and CRAR — with the exact disclosed values."
        )
    if "pharma" in ind or "drug" in ind:
        return (
            "Sector mandate (Pharmaceuticals): the `mdna` section MUST capture R&D "
            "spend (absolute and as % of revenue), pipeline / ANDA milestones, and "
            "USFDA inspection outcomes (483s, warning letters, EIRs) when disclosed."
        )
    if "metal" in ind or "mining" in ind or "steel" in ind or "oil" in ind or "gas" in ind:
        return (
            "Sector mandate (Metals / Oil & Gas): the `risk_management` section MUST "
            "capture commodity-hedging policy and the open hedge position (volume "
            "hedged, tenor, average hedged price) when disclosed."
        )
    if "it" in ind.split() or "software" in ind or "it - software" in ind or "computers" in ind:
        return (
            "Sector mandate (IT Services): the `segmental` section MUST capture "
            "client-geography split (US / Europe / RoW) and top-5 / top-10 client "
            "concentration when disclosed."
        )
    if "auto" in ind:
        return (
            "Sector mandate (Auto): the `mdna` section MUST capture volumes by "
            "segment (PV / CV / 2W / tractor as relevant), ASP / realization trends, "
            "and EV transition commentary (capex earmarked, model launches, mix %)."
        )
    return ""


# --- Per-section prompts + schemas ---

_SECTION_PROMPTS = {
    "chairman_letter": """Extract key themes and signals from the Chairman/Chairperson letter.

Return ONLY JSON:
{
  "summary": "<2-3 sentence TLDR>",
  "key_themes": ["<3-6 bullet points>"],
  "strategic_priorities_mentioned": ["<concrete priorities, not platitudes>"],
  "macro_or_industry_view": "<how the chairman frames the industry backdrop>",
  "capital_allocation_signals": "<any dividend/buyback/capex signals>",
  "tone": "<cautiously optimistic | confident | defensive | neutral | etc.>"
}""",

    "mdna": """Extract substantive analysis from the Management Discussion & Analysis section.

Return ONLY JSON:
{
  "industry_overview": "<how management frames the industry — demand, pricing, competitive dynamics>",
  "company_performance": "<substantive commentary on company's FY performance — drivers, misses>",
  "segmental_review": {
    "<segment_name>": "<paragraph on that segment's performance and outlook>"
  },
  "outlook": "<forward-looking commentary with specific guidance numbers if given>",
  "risks_flagged": ["<specific risks mgmt acknowledges in MD&A — not generic disclosure>"],
  "key_initiatives_undertaken": ["<concrete actions — capacity, acquisition, restructuring>"]
}""",

    "risk_management": """Extract the structured risk management disclosure.

Return ONLY JSON:
{
  "top_risks": [
    {"risk": "<specific risk>", "category": "<strategic|operational|financial|regulatory|etc>", "mitigation": "<what mgmt is doing>", "severity": "<high|medium|low or management's own ranking>"}
  ],
  "new_risks_this_year": ["<risks added vs prior year if noted>"],
  "framework_notes": "<any notable changes to the risk management framework this year>"
}""",

    "auditor_report": """Extract the auditor's opinion, emphasis of matter, and key audit matters.

Return ONLY JSON:
{
  "opinion": "<unqualified | qualified | adverse | disclaimer>",
  "opinion_notes": "<any caveats or modifications to the opinion>",
  "emphasis_of_matter": ["<each EoM with its substance>"],
  "key_audit_matters": [
    {"matter": "<name of KAM>", "why_significant": "<auditor's reasoning>", "how_addressed": "<audit procedures applied>"}
  ],
  "material_weaknesses_or_significant_deficiencies": ["<if any disclosed>"],
  "going_concern_notes": "<if any doubt raised>"
}""",

    "corporate_governance": """Extract board composition, committee structure, and governance signals.

Return ONLY JSON:
{
  "board_size": <number>,
  "independent_directors_count": <number>,
  "independent_directors_pct": <number>,
  "women_directors_count": <number>,
  "executive_directors": ["<names>"],
  "chairperson_role": "<executive | non-executive | independent>",
  "committee_structure": {
    "audit_committee": {"chair": "<name>", "independent_members_count": <number>},
    "nomination_remuneration": {"chair": "<name>"},
    "risk_management_committee": {"chair": "<name>"},
    "csr_committee": {"chair": "<name>"}
  },
  "director_changes_this_year": ["<appointments, resignations, retirements>"],
  "board_evaluation_findings": "<substance, not template language>",
  "governance_red_flags": ["<related-party concerns, auditor disagreements, regulatory actions>"]
}""",

    "brsr": """Extract the 9-principle BRSR (Business Responsibility & Sustainability Report) highlights.

Return ONLY JSON:
{
  "environmental": {
    "energy_consumption": "<numbers or qualitative>",
    "emissions": "<scope 1/2/3 numbers if disclosed>",
    "water": "<consumption / intensity>",
    "waste": "<disposal / recycling>"
  },
  "social": {
    "employee_count": <number>,
    "employee_wellbeing": "<key metrics>",
    "community_csr_spend_cr": <number>,
    "diversity_stats": "<gender, representation>"
  },
  "governance_ethics": {
    "whistle_blower_cases": <number>,
    "anti_corruption_training_coverage": "<pct>",
    "data_breach_incidents": <number>
  },
  "esg_rating_mentions": ["<any external ESG ratings cited>"],
  "material_topics_identified": ["<mgmt's self-identified material topics>"]
}""",

    "related_party": """Extract related-party-transaction disclosures — focus on materiality and governance concerns.

Return ONLY JSON:
{
  "total_rpt_value_cr": <number if summarized>,
  "largest_rpts": [
    {"counterparty": "<name>", "relationship": "<subsidiary|associate|kmp|promoter-group|etc>", "nature": "<sale of goods|service|loan|guarantee|etc>", "value_cr": <number>, "ordinary_course": <true|false>}
  ],
  "arms_length_statements": "<mgmt's position on arm's-length compliance>",
  "concerns_or_qualifications": ["<any auditor flags or unusual arrangements>"]
}""",

    "segmental": """Extract the segment reporting — revenue, EBITDA, assets, capex by segment.

Return ONLY JSON:
{
  "segments": [
    {
      "name": "<segment name>",
      "revenue_cr": <number>,
      "revenue_growth_yoy_pct": <number>,
      "ebitda_cr": <number>,
      "ebitda_margin_pct": <number>,
      "segment_assets_cr": <number>,
      "capex_cr": <number>,
      "key_metrics": "<any segment-specific KPIs disclosed>"
    }
  ],
  "geographical_breakdown": {
    "<region>": {"revenue_cr": <number>, "growth_yoy_pct": <number>}
  }
}""",

    "notes_to_financials": """Extract material disclosures from Notes to Financial Statements (focus on forensics + share capital).

Also scan the share capital / equity notes for depositary-receipt disclosures:
look for "depositary", "ADR", "GDR", "American Depositary", "Global Depositary",
"Depositary Receipt", typically with an outstanding-units count (millions) and
a % of total equity. Populate share_capital.adr_gdr_details when any of these
terms appear with a numeric quantity; leave it null otherwise.

Return ONLY JSON:
{
  "contingent_liabilities_cr": {"total": <number>, "by_category": {"<cat>": <number>}, "material_items": ["<description>"]},
  "commitments_cr": <number>,
  "cwip_cr": <number>,
  "capital_work_in_progress_aging": "<any item >3yrs>",
  "significant_accounting_policy_changes": ["<any this year>"],
  "deferred_tax_notes": "<substance>",
  "employee_benefits_obligations_cr": <number>,
  "impairments_or_write_offs_cr": <number>,
  "share_capital": {
    "adr_gdr_details": {
      "outstanding_units_mn": <number or null>,
      "pct_of_total_equity": <number or null>,
      "as_of_date": "<YYYY-MM-DD or null>",
      "listed_on": ["<NYSE | NASDAQ | LSE | Luxembourg | ...>"]
    }
  },
  "forensic_red_flags": ["<anything unusual — loan-write-offs, inventory aging, large EL>"]
}""",

    "financial_statements": """Extract headline standalone + consolidated financial statement numbers.

Return ONLY JSON:
{
  "standalone": {
    "revenue_cr": <number>, "profit_before_tax_cr": <number>, "net_profit_cr": <number>,
    "total_assets_cr": <number>, "equity_cr": <number>, "total_debt_cr": <number>,
    "cash_cr": <number>, "cash_from_operations_cr": <number>, "free_cash_flow_cr": <number>
  },
  "consolidated": {"...same fields..."},
  "standalone_vs_consolidated_gap_notes": "<any material divergence and why>"
}""",
}


# --- Claude call (mirrors concall_extractor / deck_extractor) ---


async def _call_claude(
    system_prompt: str, user_prompt: str, model: str,
    max_budget: float = 0.40, max_turns: int = 3,
) -> str:
    # max_turns=3 (not 1): for sections like BHARTIARTL's segmental — many
    # Africa country breakdowns + India segments — the JSON output exceeds the
    # model's single-turn output budget (~8K tokens) and the response is
    # truncated. With max_turns=1 the CLI returns error_max_turns; with 3 the
    # model continues across turns. Non-truncating sections still finish in
    # one turn, so the extra headroom is free.
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
        # Structured JSON extraction — disable extended thinking. Otherwise the
        # model can burn a turn on a ThinkingBlock and hit max_turns=1 before
        # emitting the final JSON, which the CLI reports as
        # ResultMessage(subtype='error_max_turns', is_error=True) → exit code 1
        # → "Fatal error in message reader: Command failed with exit code 1".
        thinking={"type": "disabled"},
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep",
                          "WebSearch", "WebFetch", "Agent", "Skill",
                          "NotebookEdit", "TodoWrite"],
        stderr=lambda line: logger.warning("[cli-stderr] %s", line),
        env={
            "CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "180000",
        },
        # [""] (not []) is the documented workaround for SDK #794 — an empty
        # list is falsy in _build_command's truthiness check, so the
        # --setting-sources flag never reaches the CLI and it loads all
        # default sources (incl. ~/.claude/settings.json hooks that fire
        # inside every subprocess). [""] is truthy, emits --setting-sources ""
        # which the CLI interprets as "no sources."
        # https://github.com/anthropics/claude-agent-sdk-python/issues/794
        setting_sources=[""],
        plugins=[],          # no external plugins in extractor subprocess
    )
    text_blocks: list[str] = []
    result_text = ""
    try:
        async for msg in query(prompt=user_prompt, options=options):
            if isinstance(msg, RateLimitEvent):
                logger.warning("[ar] rate limited: %s", msg.rate_limit_info.status)
                continue
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if type(block).__name__ == "TextBlock":
                        text_blocks.append(block.text)
            elif isinstance(msg, ResultMessage):
                result_text = msg.result or ""
    except _TRANSIENT_EXC:
        # Transient per-connection failures — re-raise as-is so the retry
        # wrapper's narrow `_TRANSIENT_EXC` handler picks them up.
        if not (result_text or text_blocks):
            raise
        logger.warning("[ar] _call_claude raised transient exc after capturing content")
    except Exception as exc:
        # Bare Exception covers the SDK's own "Command failed with exit code 1"
        # crash (see claude_agent_sdk/_internal/query.py). Wrap it so the retry
        # wrapper can match on a narrow class rather than a stringly-typed
        # check on Exception.__str__.
        if not (result_text or text_blocks):
            logger.error("[ar] _call_claude failed with no content: %s", exc)
            raise _ClaudeSubprocessCrash(exc) from exc
        logger.warning("[ar] _call_claude raised %s after capturing content", type(exc).__name__)
    return result_text or "\n".join(text_blocks)


def _extract_json(text: str) -> dict:
    text = text.strip()

    def _parse(s: str) -> dict:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return json.loads(re.sub(r',\s*([}\]])', r'\1', s))

    if text.startswith("{"):
        try:
            return _parse(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return _parse(m.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return _parse(text[start:end + 1])
    raise json.JSONDecodeError("No JSON found", text, 0)


# --- Section-level extraction ---


async def _extract_section(
    section_name: str,
    section_md: str,
    symbol: str,
    fy_label: str,
    model: str,
    industry: str | None = None,
) -> dict:
    """Run a single Claude extraction pass for one AR section."""
    prompt = _SECTION_PROMPTS.get(section_name)
    if not prompt:
        return {"error": f"no prompt defined for section '{section_name}'"}

    # Truncate oversized sections — preserve head + tail, drop middle.
    if len(section_md) > SECTION_CHAR_CAP:
        half = SECTION_CHAR_CAP // 2
        truncated = (
            section_md[:half]
            + f"\n\n[... {len(section_md) - SECTION_CHAR_CAP} chars truncated ...]\n\n"
            + section_md[-half:]
        )
        logger.info("[ar] %s %s: %s truncated %d→%d chars",
                    symbol, fy_label, section_name, len(section_md), len(truncated))
        section_md = truncated

    user_prompt = (
        f"Company: {symbol}\nFiscal year: {fy_label}\nSection: {section_name}\n\n"
        f"{prompt}\n\n## Section markdown\n\n{section_md}"
    )
    sector_hint = build_extraction_hint(industry)
    base_system = "You are a buy-side analyst extracting structured data from an Indian listed company's annual report. Return ONLY valid JSON — no prose, no fences."
    system_prompt = f"{base_system}\n\n{sector_hint}" if sector_hint else base_system
    try:
        resp = await _call_claude(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            max_budget=0.35,
        )
        data = _extract_json(resp)
        data["_chars_extracted_from"] = len(section_md)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("[ar] %s %s: %s JSON parse failed: %s",
                       symbol, fy_label, section_name, e)
        return {
            "extraction_error": f"JSON parse: {e}",
            "raw_response": resp[:2000] if 'resp' in dir() else "",
        }


# --- Per-year extraction ---


def _fy_label_from_path(ar_path: Path) -> str:
    """e.g. '/vault/stocks/X/filings/FY25/annual_report.pdf' -> 'FY25'."""
    return ar_path.parent.name


def _section_is_complete(cached: dict | None) -> bool:
    """A cached section is reusable if we have a dict with no extraction_error.

    Includes section_not_found_or_empty — that's a stable "nothing here" result.
    """
    if not isinstance(cached, dict):
        return False
    return "extraction_error" not in cached


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically — tmp file + rename. Keeps partial writes from
    corrupting the cache if the process crashes mid-write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


async def _extract_single_ar(
    ar_pdf: Path,
    symbol: str,
    model: str,
    sections: tuple[str, ...],
    industry: str | None = None,
    force: bool = False,
) -> dict:
    """Extract one AR PDF → structured JSON with per-section payloads.

    Resilient to mid-extraction failures:
      - Each section wrapped in try/except; a crash on one section doesn't
        abort the whole AR.
      - JSON written to disk after EVERY section completes (success or
        failure). On re-run, already-complete sections are skipped — unless
        `force=True`, in which case the cached JSON is ignored and every
        section is re-extracted.
      - Overall extraction_status is 'partial' when any section errored,
        'complete' when all succeeded.
    """
    import time as _time
    t0 = _time.time()
    fy_label = _fy_label_from_path(ar_pdf)

    # Docling pass (cached)
    extraction = extract_to_markdown(ar_pdf, ar_pdf.parent)
    md, headings = extraction.markdown, extraction.headings
    section_index = build_ar_section_index(md, headings)

    logger.info("[ar] %s %s: docling=%s, %d chars, %d headings, %d canonical sections",
                symbol, fy_label, "cached" if extraction.from_cache else "fresh",
                len(md), len(headings), len(section_index))

    # Output path — per-section incremental writes target this file.
    # Resolve Path.home() at call-time so HOME-monkeypatching tests work.
    vault_base = Path.home() / "vault" / "stocks"
    out_path = vault_base / symbol / "fundamentals" / f"annual_report_{fy_label}.json"

    # Load existing partial JSON — preserves completed sections from prior runs.
    # When `force=True`, skip the load so every section is re-extracted (used
    # when the heading_toc heuristic has been updated and stale cached
    # `section_not_found_or_empty` entries need to be invalidated).
    existing: dict = {}
    if out_path.exists() and not force:
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Seed result with fresh meta (always refreshed) but keep existing section payloads.
    result: dict = {
        "symbol": symbol,
        "fiscal_year": fy_label,
        "source_pdf": str(ar_pdf),
        "pages_chars": len(md),
        "extraction_status": "in_progress",
        "extraction_date": date.today().isoformat(),
        "section_index": section_size_summary(section_index),
        "sections_extracted": list(sections),
        "_heading_count": len(headings),
        "_docling_cached": extraction.from_cache,
        "_docling_degraded": extraction.degraded,
    }
    # Carry over any already-complete section payloads.
    for sec in sections:
        if _section_is_complete(existing.get(sec)):
            result[sec] = existing[sec]

    # Determine which sections still need extraction.
    pending = [sec for sec in sections if sec not in result]
    if not pending:
        result["extraction_status"] = "complete"
        # Preserve any existing _meta from the cached JSON; otherwise mark clean.
        existing_meta = existing.get("_meta") if isinstance(existing.get("_meta"), dict) else None
        result["_meta"] = existing_meta or {
            "degraded_quality": False,
            "missing_sections": [],
            "retried_sections": [],
        }
        result["_elapsed_s"] = round(_time.time() - t0, 1)
        _atomic_write_json(out_path, result)
        logger.info("[ar] %s %s: all sections cached, skipped", symbol, fy_label)
        return result

    logger.info("[ar] %s %s: %d cached, %d pending: %s",
                symbol, fy_label, len(sections) - len(pending), len(pending), pending)

    # Per-section extraction — concurrency bounded, each section wrapped in
    # try/except so a single subprocess crash can't wipe out the rest.
    sem = asyncio.Semaphore(2)
    retried_sections: list[str] = []

    async def _one(sec: str) -> tuple[str, dict, bool]:
        async with sem:
            slice_text = slice_section(md, section_index, sec)
            if not slice_text or len(slice_text) < 200:
                return sec, {"status": "section_not_found_or_empty", "chars": len(slice_text)}, False
            try:
                data, retried = await _extract_section_chunked(
                    sec, slice_text, symbol, fy_label, model, industry,
                )
                return sec, data, retried
            except Exception as e:
                logger.warning("[ar] %s %s: section '%s' crashed: %s: %s",
                               symbol, fy_label, sec, type(e).__name__, e)
                return sec, {
                    "extraction_error": f"{type(e).__name__}: {e}",
                    "chars_attempted": len(slice_text),
                }, False

    # gather with return_exceptions=True so no single failure aborts the whole.
    raw = await asyncio.gather(
        *[_one(sec) for sec in pending],
        return_exceptions=True,
    )
    # Process results AND persist incrementally — write after each batch completes
    # (asyncio.gather doesn't yield progressively, so we write after the full batch).
    for item in raw:
        if isinstance(item, BaseException):
            logger.error("[ar] %s %s: unexpected gather exception: %s",
                         symbol, fy_label, item)
            continue
        sec, data, retried = item
        result[sec] = data
        if retried:
            retried_sections.append(sec)
        _atomic_write_json(out_path, result)  # persist after each section

    # Final status — 'partial' when any section errored.
    errored = [sec for sec in sections if isinstance(result.get(sec), dict)
               and "extraction_error" in result[sec]]
    result["extraction_status"] = "partial" if errored else "complete"
    if errored:
        result["extraction_errors"] = {sec: result[sec]["extraction_error"] for sec in errored}

    # Post-eval v2 E14: structured quality flags for downstream callers.
    missing_sections = list(errored)
    degraded_quality = bool(missing_sections) or bool(retried_sections)
    result["_meta"] = {
        "degraded_quality": degraded_quality,
        "missing_sections": missing_sections,
        "retried_sections": retried_sections,
    }

    result["_elapsed_s"] = round(_time.time() - t0, 1)
    _atomic_write_json(out_path, result)
    return result


# --- Cross-year narrative ---


_CROSS_YEAR_PROMPT = """**OUTPUT FORMAT: Return ONLY a single valid JSON object. No prose, no fences.**

You are a buy-side analyst comparing this company's recent annual reports year-over-year. Identify what has changed — in risks, auditor commentary, governance, related-party activity, strategic framing, and financial disclosures. This is the cross-year narrative analogue of a concall cross-quarter narrative.

Given the per-year AR extractions below, produce:

```json
{
  "key_evolution_themes": [
    "<3-6 themes showing year-over-year progression with cited evidence — 'contingent liabilities grew from ₹X Cr (FY24) to ₹Y Cr (FY25), driven by GST matter Z', 'auditor added a new KAM on revenue recognition in FY25 that was absent in FY24'>"
  ],
  "risk_evolution": {
    "new_risks_this_fy": ["<risks present in latest AR but not in prior>"],
    "removed_risks": ["<risks dropped from latest AR>"],
    "escalated_risks": ["<risks materially upgraded in severity>"]
  },
  "auditor_signals": {
    "kam_changes": "<did KAMs change? any new emphasis of matter? any opinion modifications?>",
    "credibility_trajectory": "<improving | stable | deteriorating — with specific evidence>"
  },
  "governance_changes": {
    "board_composition_delta": "<net changes in director count, independence pct, committee structure>",
    "notable_director_movements": ["<appointments/resignations worth flagging>"],
    "red_flags_trajectory": "<new red flags vs prior year>"
  },
  "rpt_evolution": {
    "total_delta": "<up/down by how much>",
    "new_material_rpts": ["<large new related-party transactions>"],
    "concerns_trajectory": "<auditor/governance concerns trending>"
  },
  "strategic_framing_shift": "<how chairman / MD&A narrative has evolved — new priorities, deemphasized priorities>",
  "capital_allocation_shifts": "<dividends, buybacks, capex pattern YoY>",
  "biggest_positive_development": "<single most important positive YoY>",
  "biggest_concern": "<single most important concern YoY>",
  "what_to_watch_next_fy": ["<specific items to track in FY26/27>"]
}
```

Rules:
- Cite specific numbers or quotes from the year-specific extractions.
- Only flag material changes — skip tiny variations.
- If a section's data is missing in either year, say so ("FY24 auditor section not extracted — YoY KAM comparison limited").
- **CRITICAL FORMAT RULE**: Your ENTIRE response must be valid JSON.
"""


async def _generate_cross_year_narrative(
    year_results: list[dict], symbol: str, model: str,
) -> dict:
    """Compare 2+ years of AR extractions into a cross-year evolution narrative."""
    if len(year_results) < 2:
        return {"status": "skipped", "reason": "need ≥2 AR years for cross-year narrative"}

    # Trim each year's extraction to the fields that matter for comparison.
    comparable_fields = [
        "fiscal_year", "chairman_letter", "mdna", "risk_management",
        "auditor_report", "corporate_governance", "related_party",
    ]
    trimmed = [
        {k: y.get(k) for k in comparable_fields if k in y}
        for y in year_results
    ]

    user_prompt = (
        f"Company: {symbol}\n"
        f"Years in scope: {[y.get('fiscal_year') for y in trimmed]}\n\n"
        f"Per-year AR extractions (most recent first):\n\n"
        f"{json.dumps(trimmed, indent=2, default=str)[:80_000]}"
    )
    try:
        resp = await _call_claude(
            system_prompt="You are comparing annual reports year-over-year. Return ONLY valid JSON.",
            user_prompt=user_prompt,
            model=model,
            max_budget=0.50,
        )
        return _extract_json(resp)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("[ar] %s cross-year JSON parse failed: %s", symbol, e)
        return {"extraction_error": f"JSON parse: {e}"}


# --- Main pipeline ---


async def extract_annual_reports(
    symbol: str,
    years: int = 2,
    model: str = "claude-sonnet-4-6",
    full: bool = False,
    industry: str | None = None,
    force: bool = True,
) -> dict:
    """Extract the last N ARs for a symbol + cross-year narrative. Save per-year JSONs.

    Always invalidates the per-year JSON cache by default (`force=True`),
    since this entry point is invoked by the CLI's `--force` flag and by
    callers that explicitly want a clean re-run. Passing `force=False`
    falls back to incremental behaviour identical to
    `ensure_annual_report_data`. Force is required after heading_toc
    heuristic changes when prior runs cached `section_not_found_or_empty`
    for sections the new heuristic now locates correctly.
    """
    import time as _time
    t0 = _time.time()
    symbol = symbol.upper()

    pdfs = find_ar_pdfs(symbol, max_years=years)
    if not pdfs:
        raise FileNotFoundError(
            f"No annual_report.pdf in vault for {symbol}. "
            f"Run: flowtrack filings download-ar -s {symbol}  (or download manually to ~/vault/stocks/{symbol}/filings/FY??/annual_report.pdf)"
        )

    sections = DEFAULT_SECTIONS + (FULL_ONLY_SECTIONS if full else ())
    logger.info("[ar] %s: extracting %d year(s) — sections=%s force=%s",
                symbol, len(pdfs), list(sections), force)

    sem = asyncio.Semaphore(MAX_CONCURRENT_AR_EXTRACTIONS)

    async def _with_sem(pdf: Path) -> dict:
        async with sem:
            return await _extract_single_ar(pdf, symbol, model, sections, industry, force=force)

    year_results = list(await asyncio.gather(*[_with_sem(p) for p in pdfs]))

    # Per-year JSONs are already persisted incrementally by _extract_single_ar.
    out_dir = _VAULT_BASE / symbol / "fundamentals"

    # Cross-year narrative — only run when we have ≥2 YEARS that aren't entirely
    # error-states. Partial years with at least some sections are still useful
    # for cross-year comparison.
    usable_years = [y for y in year_results if y.get("extraction_status") in ("complete", "partial")]
    if len(usable_years) >= 2:
        cross_narrative = await _generate_cross_year_narrative(usable_years, symbol, model)
    else:
        cross_narrative = {
            "status": "skipped",
            "reason": f"only {len(usable_years)}/{len(year_results)} years extracted successfully",
        }
    _atomic_write_json(
        out_dir / "annual_report_cross_year.json",
        {
            "symbol": symbol,
            "years_analyzed": [y.get("fiscal_year") for y in year_results],
            "extraction_date": date.today().isoformat(),
            "narrative": cross_narrative,
        },
    )

    logger.info("[ar] %s: done in %.1fs, %d years + cross-year narrative",
                symbol, _time.time() - t0, len(year_results))

    return {
        "symbol": symbol,
        "years_analyzed": [y.get("fiscal_year") for y in year_results],
        "per_year": year_results,
        "cross_year_narrative": cross_narrative,
    }


async def ensure_annual_report_data(
    symbol: str,
    years: int = 2,
    model: str = "claude-sonnet-4-6",
    full: bool = False,
    industry: str | None = None,
) -> dict | None:
    """Incremental: re-extract only AR years that don't have a complete cached JSON."""
    symbol = symbol.upper()
    pdfs = find_ar_pdfs(symbol, max_years=years)
    if not pdfs:
        return None

    out_dir = _VAULT_BASE / symbol / "fundamentals"
    needing_extraction: list[Path] = []
    cached_years: list[dict] = []
    for pdf in pdfs:
        fy = _fy_label_from_path(pdf)
        cache = out_dir / f"annual_report_{fy}.json"
        if cache.exists():
            try:
                existing = json.loads(cache.read_text())
                if existing.get("extraction_status") == "complete":
                    cached_years.append(existing)
                    continue
                # 'partial' status → still re-run; _extract_single_ar will skip
                # the already-complete sections and retry the errored ones.
            except (json.JSONDecodeError, OSError):
                pass
        needing_extraction.append(pdf)

    if not needing_extraction:
        logger.info("[ar_ensure] %s: all %d year(s) cached", symbol, len(pdfs))
        # Cross-year narrative should still exist; if not, generate it.
        cross_path = out_dir / "annual_report_cross_year.json"
        if cross_path.exists():
            cross_data = json.loads(cross_path.read_text()).get("narrative", {})
        else:
            cross_data = await _generate_cross_year_narrative(cached_years, symbol, model)
        return {
            "symbol": symbol,
            "years_analyzed": [y.get("fiscal_year") for y in cached_years],
            "per_year": cached_years,
            "cross_year_narrative": cross_data,
            "_new_years_extracted": 0,
        }

    logger.info("[ar_ensure] %s: extracting %d new year(s)", symbol, len(needing_extraction))
    sections = DEFAULT_SECTIONS + (FULL_ONLY_SECTIONS if full else ())

    sem = asyncio.Semaphore(MAX_CONCURRENT_AR_EXTRACTIONS)

    async def _with_sem(pdf: Path) -> dict:
        async with sem:
            return await _extract_single_ar(pdf, symbol, model, sections, industry)

    new_results = list(await asyncio.gather(*[_with_sem(p) for p in needing_extraction]))
    all_results = cached_years + new_results
    all_results.sort(key=lambda y: _fy_sort_num(y.get("fiscal_year", "FY00")), reverse=True)

    # Per-year JSONs already persisted by _extract_single_ar incrementally.
    usable_years = [y for y in all_results if y.get("extraction_status") in ("complete", "partial")]
    if len(usable_years) >= 2:
        cross = await _generate_cross_year_narrative(usable_years, symbol, model)
    else:
        cross = {
            "status": "skipped",
            "reason": f"only {len(usable_years)}/{len(all_results)} years usable",
        }
    _atomic_write_json(
        out_dir / "annual_report_cross_year.json",
        {
            "symbol": symbol,
            "years_analyzed": [y.get("fiscal_year") for y in all_results],
            "extraction_date": date.today().isoformat(),
            "narrative": cross,
        },
    )
    return {
        "symbol": symbol,
        "years_analyzed": [y.get("fiscal_year") for y in all_results],
        "per_year": all_results,
        "cross_year_narrative": cross,
        "_new_years_extracted": len(new_results),
    }


def _fy_sort_num(fy: str) -> int:
    try:
        return int(fy[2:4])
    except (ValueError, TypeError):
        return 0
