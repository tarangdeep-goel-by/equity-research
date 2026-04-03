"""Extract structured insights from concall transcript PDFs using Claude Agent SDK."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    query,
)

_VAULT_BASE = Path.home() / "vault" / "stocks"

# --- FY quarter sorting helpers ---

_FY_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def _fy_sort_key(quarter_dir: Path) -> tuple[int, int]:
    """Return (fy_number, quarter_number) for sorting FY??-Q? directories."""
    name = quarter_dir.name  # e.g. "FY26-Q3"
    try:
        fy = int(name[2:4])  # "26" from "FY26-Q3"
        q = _FY_ORDER.get(name.split("-")[1], 0)
        return (fy, q)
    except (ValueError, IndexError):
        return (0, 0)


# --- PDF discovery ---


def _find_concall_pdfs(symbol: str, quarters: int = 6) -> list[Path]:
    """Find concall PDFs sorted by FY quarter (most recent first).

    Returns up to `quarters` paths. Only includes recent quarters
    (within ~2 FY years from the most recent available).
    """
    filings_dir = _VAULT_BASE / symbol.upper() / "filings"
    if not filings_dir.exists():
        return []

    # Collect quarter dirs matching FY??-Q? pattern
    quarter_dirs = sorted(
        [d for d in filings_dir.iterdir() if d.is_dir() and re.match(r"FY\d{2}-Q[1-4]", d.name)],
        key=_fy_sort_key,
        reverse=True,
    )

    # Find the most recent quarter to establish recency window
    all_with_concall = [d for d in quarter_dirs if (d / "concall.pdf").exists()]
    if not all_with_concall:
        return []

    latest_key = _fy_sort_key(all_with_concall[0])  # (fy, q) of most recent
    # Allow up to 7 FY quarters back from the latest (covers ~21 months)
    min_key = (latest_key[0] - 2, latest_key[1] + 1)  # ~2 FY years back

    results = []
    for qdir in all_with_concall:
        if _fy_sort_key(qdir) < min_key:
            break  # too old
        results.append(qdir / "concall.pdf")
        if len(results) >= quarters:
            break

    return results


def _find_supplementary_pdfs(quarter_dir: Path) -> list[Path]:
    """Find investor deck or concall PPT in same directory as concall.pdf."""
    extras = []
    for name in ("investor_deck.pdf", "concall_ppt.pdf"):
        p = quarter_dir / name
        if p.exists():
            extras.append(p)
    return extras


# --- PDF text extraction ---


def _read_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF using pdfplumber."""
    import pdfplumber

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


# --- Claude Agent SDK call ---


CONCALL_EXTRACTION_PROMPT = """You are a financial data extraction specialist. You will receive the FULL text of a quarterly earnings concall transcript (and optionally an investor presentation) for an Indian-listed company.

**CRITICAL: This is NOT a summary exercise. Extract ALL content, context, and data points.** We want the full richness of the concall preserved in structured form. Every number mentioned, every question asked, every answer given. The goal is that someone reading your extraction should get 90%+ of the information value of reading the full transcript.

Extract into this JSON structure:

```json
{
  "label": "Q3 FY26",
  "fy_quarter": "FY26-Q3",
  "period_ended": "December 31, 2025",
  "documents_read": ["concall.pdf"],

  "opening_remarks": {
    "speaker": "<CEO/CFO name>",
    "key_points": [
      "<every substantive point made in the opening remarks, with exact numbers>"
    ],
    "tone": "<confident|cautious|defensive|optimistic|mixed>",
    "emphasis": "<what did management choose to highlight first? This reveals priorities>"
  },

  "operational_metrics": {
    "<metric_name>": {
      "value": "<exact value as stated>",
      "yoy_change": "<+X%>",
      "qoq_change": "<+X%>",
      "context": "<management's explanation of this metric>",
      "source": "<page/slide reference>"
    }
    // Include EVERY operational metric mentioned — not just 3-4 key ones.
    // For a marketplace: paying_subscribers, ARPU, traffic, unique_buyers, enquiries, conversion_rate, churn_rate, collections, deferred_revenue, supplier_count, buyer_count, etc.
    // For a bank: NIM, CASA_ratio, advances_growth, deposit_growth, gross_NPA, net_NPA, PCR, slippage_rate, credit_cost, ROA, ROE, etc.
    // For manufacturing: capacity_utilization, order_book, realization, raw_material_cost, power_cost, volume_growth, export_share, etc.
  },

  "financial_metrics": {
    "consolidated": {
      "revenue_from_operations_cr": {"value": null, "yoy_change": "", "qoq_change": "", "source": ""},
      "other_income_cr": {"value": null, "detail": "<breakdown if given>"},
      "total_income_cr": {"value": null},
      "ebitda_cr": {"value": null, "margin_pct": null, "yoy_change": ""},
      "depreciation_cr": {"value": null},
      "ebit_cr": {"value": null},
      "interest_cost_cr": {"value": null},
      "pbt_cr": {"value": null},
      "tax_cr": {"value": null, "effective_rate_pct": null},
      "net_profit_cr": {"value": null, "yoy_change": ""},
      "eps": {"value": null, "yoy_change": ""},
      "collections_cr": {"value": null, "yoy_change": ""},
      "cash_and_investments_cr": null,
      "debt_cr": null,
      "capex_cr": null
    },
    "standalone": {
      // Same structure if standalone numbers are given separately
    },
    "segment_breakdown": [
      {"segment": "<name>", "revenue_cr": null, "growth": "", "margin_pct": null, "commentary": ""}
    ]
  },

  "management_commentary": {
    "guidance": {
      "revenue_growth": "<exact guidance given>",
      "margin_target": "<exact guidance>",
      "capex_plans": "<exact guidance>",
      "other": ["<any other forward-looking statements>"]
    },
    "strategy_updates": [
      "<every strategic initiative mentioned — new products, market expansion, M&A, partnerships, tech investments, org changes>"
    ],
    "challenges_acknowledged": [
      "<every challenge or headwind management acknowledges, with their exact framing>"
    ],
    "competitive_landscape": "<any comments about competition, market share, industry dynamics>",
    "capital_allocation": "<dividend, buyback, investment, acquisition plans>",
    "hiring_and_headcount": "<any comments on team size, hiring plans, attrition>"
  },

  "subsidiaries": [
    {
      "name": "<subsidiary name>",
      "revenue_cr": null,
      "growth": "",
      "key_metrics": "<all mentioned metrics>",
      "management_commentary": "<full context of what was said>",
      "outlook": "<any forward guidance specific to this subsidiary>"
    }
  ],

  "qa_session": [
    {
      "analyst": "<analyst name, firm>",
      "questions": ["<exact questions asked>"],
      "management_response": "<full response, not summarized — include the actual reasoning and data points given>",
      "notable": "<was management evasive? did they reveal something new? was this a tough question?>"
    }
    // Include ALL analyst Q&A pairs, not just top 3-5.
    // The Q&A is often where the real insights are hidden.
  ],

  "flags": {
    "guidance_change": "<raised|maintained|lowered|not_given — compared to previous quarter if mentioned>",
    "new_risks": ["<every new risk or headwind mentioned for the first time>"],
    "positive_surprises": ["<anything that beat expectations or was unexpectedly good>"],
    "red_flags": ["<evasive answers, deflected questions, changed narratives, unexplained variances>"],
    "commitments_made": ["<specific promises management made that can be tracked next quarter>"]
  },

  "key_numbers_mentioned": {
    // A flat dictionary of EVERY specific number mentioned in the call.
    // This serves as a quick reference — even numbers not in the structured sections above.
    // Examples: "total_customers": "8.6M", "app_downloads": "50M", "market_share": "60%"
  }
}
```

Rules:
- **EXHAUSTIVE extraction** — capture every data point, every Q&A exchange, every forward-looking statement
- Extract ACTUAL numbers from the transcript — never estimate or infer
- Include source references (page numbers) where identifiable
- For Q&A: preserve the full substance of each answer, don't just note "management responded positively"
- If a field isn't mentioned, set it to null — don't omit the field and don't guess
- All monetary values in Indian crores (₹ Cr)
- If the transcript is from an investor presentation rather than a concall, adapt the structure — focus on the data presented
"""

CROSS_QUARTER_PROMPT = """You are a financial analyst reviewing multiple quarters of concall extractions for the same company. Your job is to find the NARRATIVE ARC — how the story has evolved quarter to quarter.

Given the per-quarter structured extractions below, produce a cross-quarter analysis JSON:

```json
{
  "key_themes": [
    "<6-10 recurring themes. Each theme should cite specific numbers across quarters showing the trajectory. Example: 'ARPU-driven growth compensating for subscriber stagnation: ARPU rose from ₹62K (Q4 FY25) to ₹68K (Q3 FY26, +9% YoY) while net subscriber additions remained 1,100-2,100/quarter — revenue growth of 10-13% was almost entirely ARPU-led.'"
  ],
  "guidance_track_record": {
    "promises": ["<what management promised each quarter>"],
    "delivery": ["<what actually happened — did they meet, beat, or miss?>"],
    "credibility_score": "<high|moderate|low — based on promise vs delivery pattern>",
    "assessment": "<detailed assessment with specific examples>"
  },
  "metric_trajectories": {
    "<key_metric_1>": {
      "values_by_quarter": {"Q4 FY25": "<value>", "Q1 FY26": "<value>", "Q2 FY26": "<value>", "Q3 FY26": "<value>"},
      "trend": "<improving|stable|deteriorating>",
      "interpretation": "<what this trajectory means for the investment thesis>"
    }
    // Include 5-8 most important operational and financial metrics
  },
  "narrative_shifts": [
    "<any time management's narrative changed — e.g., shifted emphasis from growth to profitability, acknowledged a problem they previously denied, introduced a new strategic priority>"
  ],
  "recurring_analyst_concerns": [
    "<questions that keep coming up quarter after quarter — these are unresolved issues the market cares about>"
  ],
  "biggest_positive": "<most important positive trend with multi-quarter evidence>",
  "biggest_concern": "<most important concern with multi-quarter evidence>",
  "management_credibility": "<detailed assessment — do they under-promise and over-deliver, or over-promise and under-deliver? Cite specific examples.>",
  "what_to_watch_next_quarter": [
    "<specific metrics or events to track — derived from commitments made and trends identified>"
  ]
}
```

Rules:
- Reference specific numbers from the quarterly data — no hand-waving
- Track metric trajectories explicitly: show the numbers changing quarter to quarter
- Flag narrative shifts — when management changes their story, that's a signal
- Identify questions analysts keep asking repeatedly (unresolved issues)
- Be opinionated about management credibility — the data supports a view, state it
"""


async def _call_claude(system_prompt: str, user_prompt: str, model: str) -> str:
    """Call Claude via Agent SDK. Handles the TextBlock fallback for empty ResultMessage."""
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=3,
        max_budget_usd=0.30,
        permission_mode="bypassPermissions",
        model=model,
    )
    text_blocks: list[str] = []
    result_text = ""
    try:
        async for msg in query(prompt=user_prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if type(block).__name__ == "TextBlock":
                        text_blocks.append(block.text)
            elif isinstance(msg, ResultMessage):
                result_text = msg.result or ""
    except Exception:
        pass
    return result_text or "\n".join(text_blocks)


def _extract_json(text: str) -> dict:
    """Extract JSON from a Claude response that may contain markdown code fences."""
    # Try extracting from ```json ... ``` block first
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    # Try parsing the whole text as JSON
    return json.loads(text.strip())


def _quarter_label_from_path(pdf_path: Path) -> str:
    """Extract quarter label like 'FY26-Q3' from the directory name."""
    return pdf_path.parent.name  # e.g. "FY26-Q3"


# --- Main extraction pipeline ---


async def extract_concalls(
    symbol: str,
    quarters: int = 4,
    model: str = "claude-sonnet-4-20250514",
    industry: str | None = None,
) -> dict:
    """Extract structured insights from the last N concall PDFs.

    Args:
        industry: NSE/Screener industry name (e.g. "Private Sector Bank").
            If provided, injects sector-specific canonical KPI extraction hints.

    Returns the full extraction dict matching concall_extraction_v2.json schema.
    """
    symbol = symbol.upper()
    pdfs = _find_concall_pdfs(symbol, quarters=quarters)

    if not pdfs:
        raise FileNotFoundError(
            f"No concall PDFs found at ~/vault/stocks/{symbol}/filings/FY??-Q?/concall.pdf"
        )

    # --- Per-quarter extraction ---
    quarter_results: list[dict] = []

    for pdf_path in pdfs:
        quarter_label = _quarter_label_from_path(pdf_path)
        quarter_dir = pdf_path.parent

        # Read concall text
        user_parts = [f"## Concall Transcript — {quarter_label}\n\n{_read_pdf_text(pdf_path)}"]
        docs_read = ["concall.pdf"]

        # Read supplementary docs
        for extra in _find_supplementary_pdfs(quarter_dir):
            extra_text = _read_pdf_text(extra)
            if extra_text.strip():
                user_parts.append(f"\n\n## {extra.stem.replace('_', ' ').title()} — {quarter_label}\n\n{extra_text}")
                docs_read.append(extra.name)

        # Build sector-specific KPI hint if industry is known
        sector_hint = ""
        if industry:
            from flowtracker.research.sector_kpis import build_extraction_hint
            sector_hint = build_extraction_hint(industry)

        user_prompt = (
            f"Company: {symbol}\nQuarter: {quarter_label}\n"
            f"Documents provided: {', '.join(docs_read)}\n"
            + (f"\n{sector_hint}\n\n" if sector_hint else "\n")
            + "\n".join(user_parts)
        )

        response = await _call_claude(CONCALL_EXTRACTION_PROMPT, user_prompt, model)

        try:
            extraction = _extract_json(response)
        except (json.JSONDecodeError, ValueError):
            # If JSON parsing fails, store raw text as fallback
            extraction = {
                "label": quarter_label,
                "fy_quarter": quarter_label,
                "extraction_error": "Failed to parse JSON from Claude response",
                "raw_response": response[:2000],
            }

        # Ensure consistent fields
        extraction.setdefault("fy_quarter", quarter_label)
        extraction.setdefault("documents_read", docs_read)
        quarter_results.append(extraction)

    # --- Cross-quarter narrative ---
    cross_narrative = {}
    if len(quarter_results) >= 2:
        quarters_json = json.dumps(quarter_results, indent=2, default=str)
        cross_prompt = (
            f"Company: {symbol}\n"
            f"Quarters analyzed: {len(quarter_results)}\n\n"
            f"Per-quarter extractions:\n```json\n{quarters_json}\n```"
        )
        cross_response = await _call_claude(CROSS_QUARTER_PROMPT, cross_prompt, model)
        try:
            cross_narrative = _extract_json(cross_response)
        except (json.JSONDecodeError, ValueError):
            cross_narrative = {
                "extraction_error": "Failed to parse cross-quarter narrative",
                "raw_response": cross_response[:2000],
            }

    # --- Assemble final output ---
    result = {
        "symbol": symbol,
        "quarters_analyzed": len(quarter_results),
        "sector": "",
        "extraction_date": date.today().isoformat(),
        "quarters": quarter_results,
        "cross_quarter_narrative": cross_narrative,
    }

    # Save to vault
    out_dir = _VAULT_BASE / symbol / "fundamentals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "concall_extraction_v2.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    return result
