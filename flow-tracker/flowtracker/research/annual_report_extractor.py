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
DEFAULT_SECTIONS = (
    "chairman_letter",
    "mdna",
    "risk_management",
    "auditor_report",
    "corporate_governance",
    "brsr",
    "related_party",
    "segmental",
)
FULL_ONLY_SECTIONS = (
    "notes_to_financials",
    "financial_statements",
)

# Token budget guard — if a section slice exceeds this, truncate before sending
# to Claude. Realistic section sizes: MD&A 20-80KB, Risk 10-40KB, Auditor 10-20KB,
# CG 20-40KB, BRSR 30-80KB. Notes can be 200-500KB (hence opt-in).
SECTION_CHAR_CAP = 120_000


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

    "notes_to_financials": """Extract material disclosures from Notes to Financial Statements (focus on forensics).

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
    max_budget: float = 0.40, max_turns: int = 1,
) -> str:
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep",
                          "WebSearch", "WebFetch", "Agent", "Skill",
                          "NotebookEdit", "TodoWrite"],
        stderr=lambda line: logger.warning("[cli-stderr] %s", line),
        env={"CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "180000"},
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
    except Exception as exc:
        if not (result_text or text_blocks):
            logger.error("[ar] _call_claude failed with no content: %s", exc)
            raise
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
    section_name: str, section_md: str, symbol: str, fy_label: str, model: str,
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
    try:
        resp = await _call_claude(
            system_prompt="You are a buy-side analyst extracting structured data from an Indian listed company's annual report. Return ONLY valid JSON — no prose, no fences.",
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


async def _extract_single_ar(
    ar_pdf: Path,
    symbol: str,
    model: str,
    sections: tuple[str, ...],
) -> dict:
    """Extract one AR PDF → structured JSON with per-section payloads."""
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

    # Per-section parallel extraction
    sem = asyncio.Semaphore(3)
    tasks: list[tuple[str, asyncio.Task]] = []

    async def _one(sec: str) -> tuple[str, dict]:
        async with sem:
            slice_text = slice_section(md, section_index, sec)
            if not slice_text or len(slice_text) < 200:
                return sec, {"status": "section_not_found_or_empty", "chars": len(slice_text)}
            return sec, await _extract_section(sec, slice_text, symbol, fy_label, model)

    section_results = dict(await asyncio.gather(*[_one(sec) for sec in sections]))

    result = {
        "symbol": symbol,
        "fiscal_year": fy_label,
        "source_pdf": str(ar_pdf),
        "pages_chars": len(md),
        "extraction_status": "complete",
        "extraction_date": date.today().isoformat(),
        "section_index": section_size_summary(section_index),
        "sections_extracted": list(sections),
        "_heading_count": len(headings),
        "_docling_cached": extraction.from_cache,
        "_docling_degraded": extraction.degraded,
        "_elapsed_s": round(_time.time() - t0, 1),
    }
    # Spread section results into top-level fields.
    for sec, data in section_results.items():
        result[sec] = data

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
) -> dict:
    """Extract the last N ARs for a symbol + cross-year narrative. Save per-year JSONs."""
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
    logger.info("[ar] %s: extracting %d year(s) — sections=%s", symbol, len(pdfs), list(sections))

    sem = asyncio.Semaphore(MAX_CONCURRENT_AR_EXTRACTIONS)

    async def _with_sem(pdf: Path) -> dict:
        async with sem:
            return await _extract_single_ar(pdf, symbol, model, sections)

    year_results = list(await asyncio.gather(*[_with_sem(p) for p in pdfs]))

    # Save per-year JSONs.
    out_dir = _VAULT_BASE / symbol / "fundamentals"
    out_dir.mkdir(parents=True, exist_ok=True)
    for yr in year_results:
        fy = yr.get("fiscal_year", "unknown")
        out = out_dir / f"annual_report_{fy}.json"
        out.write_text(json.dumps(yr, indent=2, ensure_ascii=False, default=str))

    # Cross-year narrative (only when we have 2+ years).
    cross_narrative = await _generate_cross_year_narrative(year_results, symbol, model)
    (out_dir / "annual_report_cross_year.json").write_text(
        json.dumps({
            "symbol": symbol,
            "years_analyzed": [y.get("fiscal_year") for y in year_results],
            "extraction_date": date.today().isoformat(),
            "narrative": cross_narrative,
        }, indent=2, ensure_ascii=False, default=str)
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
        }

    logger.info("[ar_ensure] %s: extracting %d new year(s)", symbol, len(needing_extraction))
    sections = DEFAULT_SECTIONS + (FULL_ONLY_SECTIONS if full else ())

    sem = asyncio.Semaphore(MAX_CONCURRENT_AR_EXTRACTIONS)

    async def _with_sem(pdf: Path) -> dict:
        async with sem:
            return await _extract_single_ar(pdf, symbol, model, sections)

    new_results = list(await asyncio.gather(*[_with_sem(p) for p in needing_extraction]))
    all_results = cached_years + new_results
    all_results.sort(key=lambda y: _fy_sort_num(y.get("fiscal_year", "FY00")), reverse=True)

    for yr in new_results:
        fy = yr.get("fiscal_year", "unknown")
        out = out_dir / f"annual_report_{fy}.json"
        out.write_text(json.dumps(yr, indent=2, ensure_ascii=False, default=str))

    cross = await _generate_cross_year_narrative(all_results, symbol, model)
    (out_dir / "annual_report_cross_year.json").write_text(
        json.dumps({
            "symbol": symbol,
            "years_analyzed": [y.get("fiscal_year") for y in all_results],
            "extraction_date": date.today().isoformat(),
            "narrative": cross,
        }, indent=2, ensure_ascii=False, default=str)
    )
    return {
        "symbol": symbol,
        "years_analyzed": [y.get("fiscal_year") for y in all_results],
        "per_year": all_results,
        "cross_year_narrative": cross,
    }


def _fy_sort_num(fy: str) -> int:
    try:
        return int(fy[2:4])
    except (ValueError, TypeError):
        return 0
