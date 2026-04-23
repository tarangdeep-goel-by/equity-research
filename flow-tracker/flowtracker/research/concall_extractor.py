"""Extract structured insights from concall transcript PDFs using Claude Agent SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    RateLimitEvent,
    ResultMessage,
    query,
)

_VAULT_BASE = Path.home() / "vault" / "stocks"

MAX_CONCURRENT_EXTRACTIONS = 3

# --- JSON Schemas for API-level structured output enforcement ---

_METRIC_VALUE = {
    "type": "object",
    "properties": {
        "value": {},
        "yoy_change": {"type": "string"},
        "qoq_change": {"type": "string"},
        "context": {"type": "string"},
        "source": {"type": "string"},
        "detail": {"type": "string"},
        "margin_pct": {},
        "effective_rate_pct": {},
    },
    "additionalProperties": True,
}

_CONCALL_EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "concall_extraction",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "fy_quarter": {"type": "string"},
                "period_ended": {"type": "string"},
                "documents_read": {"type": "array", "items": {"type": "string"}},
                "opening_remarks": {
                    "type": "object",
                    "properties": {
                        "speaker": {"type": "string"},
                        "key_points": {"type": "array", "items": {"type": "string"}},
                        "tone": {"type": "string"},
                        "emphasis": {"type": "string"},
                    },
                },
                "operational_metrics": {
                    "type": "object",
                    "additionalProperties": _METRIC_VALUE,
                },
                "financial_metrics": {
                    "type": "object",
                    "properties": {
                        "consolidated": {"type": "object", "additionalProperties": True},
                        "standalone": {"type": "object", "additionalProperties": True},
                        "segment_breakdown": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "segment": {"type": "string"},
                                    "revenue_cr": {},
                                    "growth": {"type": "string"},
                                    "margin_pct": {},
                                    "commentary": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "management_commentary": {
                    "type": "object",
                    "properties": {
                        "guidance": {"type": "object", "additionalProperties": True},
                        "strategy_updates": {"type": "array", "items": {"type": "string"}},
                        "challenges_acknowledged": {"type": "array", "items": {"type": "string"}},
                        "competitive_landscape": {"type": "string"},
                        "capital_allocation": {"type": "string"},
                        "hiring_and_headcount": {"type": "string"},
                    },
                },
                "subsidiaries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "revenue_cr": {},
                            "growth": {"type": "string"},
                            "key_metrics": {"type": "string"},
                            "management_commentary": {"type": "string"},
                            "outlook": {"type": "string"},
                        },
                    },
                },
                "qa_session": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "analyst": {"type": "string"},
                            "questions": {"type": "array", "items": {"type": "string"}},
                            "management_response": {"type": "string"},
                            "notable": {"type": "string"},
                            "topics": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "flags": {
                    "type": "object",
                    "properties": {
                        "guidance_change": {"type": "string"},
                        "new_risks": {"type": "array", "items": {"type": "string"}},
                        "positive_surprises": {"type": "array", "items": {"type": "string"}},
                        "red_flags": {"type": "array", "items": {"type": "string"}},
                        "commitments_made": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "key_numbers_mentioned": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    },
}

_CROSS_QUARTER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cross_quarter_narrative",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "key_themes": {"type": "array", "items": {"type": "string"}},
                "guidance_track_record": {
                    "type": "object",
                    "properties": {
                        "promises": {"type": "array", "items": {"type": "string"}},
                        "delivery": {"type": "array", "items": {"type": "string"}},
                        "credibility_score": {"type": "string"},
                        "assessment": {"type": "string"},
                    },
                },
                "metric_trajectories": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "values_by_quarter": {"type": "object", "additionalProperties": {"type": "string"}},
                            "trend": {"type": "string"},
                            "interpretation": {"type": "string"},
                        },
                    },
                },
                "narrative_shifts": {"type": "array", "items": {"type": "string"}},
                "recurring_analyst_concerns": {"type": "array", "items": {"type": "string"}},
                "biggest_positive": {"type": "string"},
                "biggest_concern": {"type": "string"},
                "management_credibility": {"type": "string"},
                "what_to_watch_next_quarter": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}

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


def _fy_sort_key_from_str(fy_quarter: str) -> tuple[int, int]:
    """Return (fy_number, quarter_number) from a string like 'FY26-Q3'."""
    fy = int(fy_quarter[2:4])
    q = _FY_ORDER.get(fy_quarter.split("-")[1], 0)
    return (fy, q)


def _screener_period_to_fy_quarter(period: str) -> str:
    """Convert Screener period like 'Jan 2026' to FY quarter like 'FY26-Q3'.

    Indian FY runs Apr-Mar. Results announcement month maps to the quarter it reports:
      Jan-Mar announcement → Q3 (Oct-Dec results)
      Apr-Jun announcement → Q4 (Jan-Mar results)
      Jul-Sep announcement → Q1 (Apr-Jun results)
      Oct-Dec announcement → Q2 (Jul-Sep results)
    """
    month_str, year_str = period.split()
    month = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
             "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}[month_str[:3]]
    year = int(year_str)

    if month in (1, 2, 3):      # Jan-Mar → Q3 results (Oct-Dec)
        fy = year % 100
        return f"FY{fy:02d}-Q3"
    elif month in (4, 5, 6):    # Apr-Jun → Q4 results (Jan-Mar)
        fy = year % 100
        return f"FY{fy:02d}-Q4"
    elif month in (7, 8, 9):    # Jul-Sep → Q1 results (Apr-Jun)
        fy = (year + 1) % 100
        return f"FY{fy:02d}-Q1"
    else:                        # Oct-Dec → Q2 results (Jul-Sep)
        fy = (year + 1) % 100
        return f"FY{fy:02d}-Q2"


def _download_transcript_from_url(url: str, dest_path: Path) -> bool:
    """Download a transcript PDF from a Screener-sourced URL.

    Returns True if downloaded successfully.
    Handles BSE 406 (needs browser headers), retries on timeout.
    """
    import httpx

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/pdf,application/octet-stream,*/*",
    }
    for attempt in range(2):
        try:
            with httpx.Client(follow_redirects=True, timeout=45, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(resp.content)
                    return True
                if resp.status_code in (403, 404, 406):
                    return False  # permanent failure, don't retry
        except httpx.TimeoutException:
            if attempt == 0:
                continue  # retry once on timeout
        except Exception:
            return False
    return False


def ensure_transcript_pdfs(symbol: str, max_quarters: int = 6) -> int:
    """Download missing concall PDFs from Screener transcript URLs. Returns count downloaded."""
    from flowtracker.store import FlowStore
    symbol = symbol.upper()
    vault_base = Path.home() / "vault" / "stocks"
    downloaded = 0
    with FlowStore() as store:
        transcript_docs = store._conn.execute(
            "SELECT period, url FROM company_documents "
            "WHERE symbol = ? AND doc_type = 'concall_transcript' "
            "ORDER BY period DESC LIMIT ?",
            (symbol, max_quarters),
        ).fetchall()
    for doc in transcript_docs:
        try:
            fy_q = _screener_period_to_fy_quarter(doc["period"])
        except (ValueError, KeyError):
            continue
        dest = vault_base / symbol / "filings" / fy_q / "concall.pdf"
        if dest.exists():
            continue
        if _download_transcript_from_url(doc["url"], dest):
            downloaded += 1
    return downloaded


# --- PDF discovery ---


def _find_concall_pdfs(symbol: str, quarters: int = 6) -> list[Path]:
    """Find concall PDFs sorted by FY quarter (most recent first).

    Returns up to `quarters` paths. Only includes recent quarters
    (within ~2 FY years from the most recent available).
    Uses Screener transcript URLs as fallback when vault PDFs are missing.
    """
    symbol = symbol.upper()
    filings_dir = _VAULT_BASE / symbol / "filings"
    filings_dir.mkdir(parents=True, exist_ok=True)

    # Collect quarter dirs matching FY??-Q? pattern
    quarter_dirs = sorted(
        [d for d in filings_dir.iterdir() if d.is_dir() and re.match(r"FY\d{2}-Q[1-4]", d.name)],
        key=_fy_sort_key,
        reverse=True,
    )

    # Find existing concall PDFs in vault
    all_with_concall = [d for d in quarter_dirs if (d / "concall.pdf").exists()]

    # Establish recency window from latest available (or current date)
    if all_with_concall:
        latest_key = _fy_sort_key(all_with_concall[0])
    else:
        # No PDFs yet — derive window from current date
        today = date.today()
        if today.month <= 3:
            latest_key = (today.year % 100, 3)
        elif today.month <= 6:
            latest_key = (today.year % 100, 4)
        elif today.month <= 9:
            latest_key = ((today.year + 1) % 100, 1)
        else:
            latest_key = ((today.year + 1) % 100, 2)

    min_key = (latest_key[0] - 2, latest_key[1] + 1)  # ~2 FY years back

    results = []
    seen_quarters: set[str] = set()
    for qdir in all_with_concall:
        if _fy_sort_key(qdir) < min_key:
            break
        results.append(qdir / "concall.pdf")
        seen_quarters.add(qdir.name)
        if len(results) >= quarters:
            break

    # If we have fewer than desired, try Screener transcript URLs
    if len(results) < quarters:
        try:
            ensure_transcript_pdfs(symbol, max_quarters=quarters)
            # Re-scan for newly downloaded PDFs
            for qdir in sorted(
                [d for d in filings_dir.iterdir() if d.is_dir() and re.match(r"FY\d{2}-Q[1-4]", d.name)],
                key=_fy_sort_key, reverse=True,
            ):
                if qdir.name in seen_quarters:
                    continue
                if _fy_sort_key(qdir) < min_key:
                    break
                concall = qdir / "concall.pdf"
                if concall.exists():
                    results.append(concall)
                    seen_quarters.add(qdir.name)
                    if len(results) >= quarters:
                        break
        except Exception:
            pass  # don't break extraction if DB lookup fails

        # Re-sort by recency
        results.sort(key=lambda p: _fy_sort_key(p.parent), reverse=True)

    # PPT download disabled — investor decks are 20-60 pages of slides that
    # produce 100K+ chars of garbled text via pdfplumber, blowing extraction
    # budgets for marginal value over transcript + Screener financials.
    # Re-enable when we have native PDF vision (Anthropic API) or better
    # PDF-to-markdown extraction (pymupdf4llm).
    #
    # try:
    #     from flowtracker.store import FlowStore
    #     with FlowStore() as store:
    #         ppt_docs = store._conn.execute(
    #             "SELECT period, url FROM company_documents "
    #             "WHERE symbol = ? AND doc_type = 'concall_ppt' "
    #             "ORDER BY period DESC",
    #             (symbol,),
    #         ).fetchall()
    #     for doc in ppt_docs:
    #         try:
    #             fy_q = _screener_period_to_fy_quarter(doc["period"])
    #         except (ValueError, KeyError):
    #             continue
    #         if fy_q not in seen_quarters:
    #             continue
    #         dest = filings_dir / fy_q / "concall_ppt.pdf"
    #         if not dest.exists():
    #             _download_transcript_from_url(doc["url"], dest)
    # except Exception:
    #     pass

    return results[:quarters]


def _find_supplementary_pdfs(quarter_dir: Path) -> list[Path]:
    """Find investor deck or concall PPT in same directory as concall.pdf.

    PPT/investor deck reading disabled — pdfplumber produces garbled text
    from slide decks (100K+ chars), blowing extraction budgets. Financial
    numbers are available via Screener (get_fundamentals). Re-enable when
    we have native PDF vision or better PDF extraction.
    """
    # Disabled: PPT text extraction is too noisy and expensive
    # extras = []
    # for name in ("investor_deck.pdf", "concall_ppt.pdf"):
    #     p = quarter_dir / name
    #     if p.exists():
    #         extras.append(p)
    # return extras
    return []


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


CONCALL_EXTRACTION_PROMPT = """**OUTPUT FORMAT: Return ONLY a single valid JSON object. No prose, no markdown fences, no explanation before or after. Start your response with `{` and end with `}`.**

You are a financial data extraction specialist. You will receive the FULL text of a quarterly earnings concall transcript (and optionally an investor presentation) for an Indian-listed company.

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
    // For a bank/NBFC (BFSI): use these EXACT canonical field names when the metric is discussed —
    //   casa_ratio_pct (CASA %), gross_npa_pct (GNPA %), net_npa_pct (NNPA %),
    //   provision_coverage_ratio_pct (PCR %), net_interest_margin_pct (NIM %),
    //   fresh_slippages_cr, credit_cost_bps, capital_adequacy_ratio_pct (CRAR),
    //   cet1_pct (CET-1 %), liquidity_coverage_ratio_pct (LCR),
    //   cost_to_income_ratio_pct, roau_pct (ROA).
    //   MANDATORY for BFSI: always emit casa_ratio_pct, gross_npa_pct, net_npa_pct,
    //   provision_coverage_ratio_pct, capital_adequacy_ratio_pct, cet1_pct, liquidity_coverage_ratio_pct
    //   — if not stated in the call, set value to null with reason "not_mentioned_in_concall".
    //   Never omit these seven keys for BFSI.
    // For pharma: rd_pct_of_revenue (R&D % of revenue), usfda_facility_status
    //   (one of: "active_no_observations" | "483s_open" | "warning_letter" | "unknown"),
    //   anda_approvals_ltm (integer — trailing-twelve-month ANDA approvals),
    //   key_molecule_pipeline (list of molecule names with optional launch dates),
    //   us_revenue_usd_mn, india_formulations_revenue_cr, us_price_erosion_pct.
    // For FMCG: uvg_pct (underlying volume growth %), price_growth_pct,
    //   channel_gt_pct (general trade share), channel_mt_pct (modern trade share),
    //   channel_ecom_pct (e-commerce share), rural_growth_pct, urban_growth_pct,
    //   advertising_and_promotion_spend_pct, gross_margin_pct.
    // For telecom: arpu_inr (ARPU in INR), subscribers_mn (total subscribers in millions),
    //   africa_cc_growth_pct (constant-currency growth in Africa subsidiary),
    //   africa_fx_devaluation_pct (local-currency devaluation impact),
    //   monthly_churn_rate_pct, data_usage_per_subscriber_gb, network_capex_cr.
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
      "notable": "<was management evasive? did they reveal something new? was this a tough question?>",
      "topics": ["<2-4 short lowercase topic tags. Prefer reusing these canonical tags: margins, guidance, capex, demand, pricing, mix, costs, competition, market_share, inventory, working_capital, leverage, order_book, utilization, new_products, geography, regulation, m_and_a, capital_allocation, attrition, esg. Add new tags only for domain concepts not covered.>"]
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
- **CRITICAL FORMAT RULE**: Your ENTIRE response must be valid JSON. Do not write any text before or after the JSON object. Do not wrap in markdown code fences. Start with { and end with }. If you include ANY text outside the JSON, the extraction will fail.
"""

CROSS_QUARTER_PROMPT = """**OUTPUT FORMAT: Return ONLY a single valid JSON object. No prose, no markdown fences, no explanation before or after. Start your response with `{` and end with `}`.**

You are a financial analyst reviewing multiple quarters of concall extractions for the same company. Your job is to find the NARRATIVE ARC — how the story has evolved quarter to quarter.

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
- **CRITICAL FORMAT RULE**: Your ENTIRE response must be valid JSON. Do not write any text before or after the JSON object. Do not wrap in markdown code fences. Start with { and end with }. If you include ANY text outside the JSON, the extraction will fail.
"""


async def _call_claude(
    system_prompt: str, user_prompt: str, model: str,
    max_budget: float = 0.50, max_turns: int = 1,
    output_format: dict | None = None,
) -> str:
    """Call Claude via Agent SDK. Handles the TextBlock fallback for empty ResultMessage."""
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
        env={
            "CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "120000",
            # Bypass cmux's claude-wrapper hook injection — extractor subprocesses
            # don't need SessionStart/UserPromptSubmit/PreToolUse tracking.
            "CMUX_CLAUDE_HOOKS_DISABLED": "1",
        },
        setting_sources=[],  # isolate from user hooks/plugins/skills
        plugins=[],          # no external plugins in extractor subprocess
    )
    if output_format:
        options.output_format = output_format
    text_blocks: list[str] = []
    result_text = ""
    try:
        async for msg in query(prompt=user_prompt, options=options):
            if isinstance(msg, RateLimitEvent):
                logger.warning(
                    "[concall] rate limited: status=%s type=%s",
                    msg.rate_limit_info.status,
                    msg.rate_limit_info.rate_limit_type,
                )
                continue
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if type(block).__name__ == "TextBlock":
                        text_blocks.append(block.text)
            elif isinstance(msg, ResultMessage):
                result_text = msg.result or ""
    except Exception as exc:
        if not (result_text or text_blocks):
            logger.error("_call_claude failed with no content: %s: %s", type(exc).__name__, exc)
            raise
        logger.warning("_call_claude raised %s after capturing content — proceeding", type(exc).__name__)
    return result_text or "\n".join(text_blocks)


def _extract_json(text: str) -> dict:
    """Extract JSON from a Claude response that may contain markdown code fences."""
    text = text.strip()

    def _try_parse(s: str) -> dict:
        """Try parsing, with a trailing-comma repair on first failure."""
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            repaired = re.sub(r',\s*([}\]])', r'\1', s)
            return json.loads(repaired)

    # Try direct JSON parse first (most likely with strict format)
    if text.startswith("{"):
        try:
            return _try_parse(text)
        except json.JSONDecodeError:
            pass
    # Try extracting from ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return _try_parse(m.group(1).strip())
    # Try finding first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return _try_parse(text[start:end + 1])
    raise json.JSONDecodeError("No JSON found", text, 0)


async def _recover_json_from_prose(
    prose: str, quarter_label: str, symbol: str, model: str,
) -> dict:
    """Second-pass: convert a prose summary into the expected JSON schema using a cheap model.

    When the primary extraction produces markdown instead of JSON, this feeds
    the prose back with a tighter prompt to get structured output.
    """
    recovery_prompt = (
        f"The following is a prose summary of a {quarter_label} earnings concall for {symbol}. "
        "It was supposed to be structured JSON but came out as text.\n\n"
        "Convert this into the JSON structure below. Extract EVERY number and metric mentioned. "
        "Return ONLY valid JSON — no markdown, no explanation.\n\n"
        "Required structure:\n"
        "```json\n"
        "{\n"
        f'  "label": "{quarter_label}",\n'
        f'  "fy_quarter": "{quarter_label}",\n'
        '  "operational_metrics": { "<metric_name>": {"value": "<exact value>", "yoy_change": "", "context": ""} },\n'
        '  "financial_metrics": { "consolidated": {"revenue_from_operations_cr": {"value": null}, "ebitda_cr": {"value": null, "margin_pct": null}, "net_profit_cr": {"value": null}}, "segment_breakdown": [{"segment": "", "revenue_cr": null, "growth": "", "margin_pct": null}] },\n'
        '  "management_commentary": { "guidance": {"revenue_growth": "", "margin_target": ""}, "strategy_updates": [], "challenges_acknowledged": [] },\n'
        '  "flags": { "guidance_change": "", "positive_surprises": [], "red_flags": [] },\n'
        '  "key_numbers_mentioned": {}\n'
        "}\n"
        "```\n\n"
        f"Prose to convert:\n{prose[:8000]}"
    )

    response = await _call_claude(
        system_prompt="You are a data extraction assistant. Convert prose into JSON. Return ONLY valid JSON.",
        user_prompt=recovery_prompt,
        model="claude-sonnet-4-6",
        max_budget=0.15,
        max_turns=1,
    )
    return _extract_json(response)


def _quarter_label_from_path(pdf_path: Path) -> str:
    """Extract quarter label like 'FY26-Q3' from the directory name."""
    return pdf_path.parent.name  # e.g. "FY26-Q3"


def _build_partial_extraction(response: str, quarter_label: str, docs_read: list[str]) -> dict:
    """Build a partial extraction from a prose response by extracting any numbers/metrics mentioned."""
    extraction: dict = {
        "label": quarter_label,
        "fy_quarter": quarter_label,
        "extraction_status": "partial",
        "extraction_error": "Primary JSON parse failed, recovery failed — partial data preserved",
        "raw_response": response[:4000],
        "documents_read": docs_read,
    }

    # Try to extract any numbers mentioned in the prose
    key_numbers: dict[str, str] = {}
    import re as _re
    for m in _re.finditer(
        r'(?:revenue|profit|ebitda|nim|casa|npa|growth|margin|arpu|subscribers?|stores?|users?|volume)'
        r'[^\u20b9\d]*?[\u20b9]?\s*([\d,]+\.?\d*)\s*(%|crore|cr|lakh|bps|mn|billion)?',
        response, _re.IGNORECASE,
    ):
        context_start = max(0, m.start() - 40)
        context = response[context_start:m.end()].strip()
        key = _re.sub(r'[^a-z_]', '', context[:30].lower().replace(' ', '_'))
        if key and m.group(1):
            key_numbers[key] = m.group(1) + (m.group(2) or "")

    if key_numbers:
        extraction["key_numbers_mentioned"] = key_numbers

    return extraction


# --- Main extraction pipeline ---


async def _extract_single_quarter(
    pdf_path: Path,
    symbol: str,
    model: str,
    industry: str | None,
) -> dict:
    """Extract structured insights from a single concall PDF.

    Returns one quarter extraction dict with extraction_status field.
    """
    import time as _time
    q_start = _time.time()
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
    )
    if sector_hint:
        user_prompt += f"\n{sector_hint}\n"
        user_prompt += "Use the EXACT canonical field names listed above in your operational_metrics. If a KPI is not mentioned in the transcript, include it with value: null.\n\n"
    else:
        user_prompt += "\n"
    user_prompt += "\n".join(user_parts)

    response = await _call_claude(
        CONCALL_EXTRACTION_PROMPT, user_prompt, model,
        max_budget=1.00, max_turns=2,
        output_format=_CONCALL_EXTRACTION_SCHEMA,
    )

    try:
        extraction = _extract_json(response)
        extraction["extraction_status"] = "complete"
    except (json.JSONDecodeError, ValueError):
        # Primary extraction returned prose — try recovery with cheap model
        if len(response.strip()) > 200:
            logger.warning(
                "Concall extraction for %s %s returned prose (%d chars) — attempting JSON recovery",
                symbol, quarter_label, len(response),
            )
            try:
                extraction = await _recover_json_from_prose(
                    response, quarter_label, symbol, model,
                )
                extraction["extraction_status"] = "recovered"
            except (json.JSONDecodeError, ValueError, Exception) as exc:
                logger.warning(
                    "JSON recovery also failed for %s %s: %s",
                    symbol, quarter_label, exc,
                )
                extraction = _build_partial_extraction(
                    response, quarter_label, docs_read,
                )
        else:
            extraction = {
                "label": quarter_label,
                "fy_quarter": quarter_label,
                "extraction_status": "failed",
                "extraction_error": "Empty or very short response from Claude",
                "raw_response": response[:2000],
            }

    # Ensure consistent fields
    extraction.setdefault("fy_quarter", quarter_label)
    extraction.setdefault("documents_read", docs_read)

    # Validate canonical KPIs if sector is known
    if industry and extraction.get("extraction_status") in ("complete", "recovered"):
        from flowtracker.research.sector_kpis import get_kpis_for_industry
        canonical = get_kpis_for_industry(industry)
        if canonical:
            ops = extraction.get("operational_metrics", {})
            for kpi in canonical:
                key = kpi["key"]
                if key not in ops:
                    ops[key] = {"value": None, "reason": "not_mentioned_in_concall"}
            extraction["operational_metrics"] = ops

    extraction["extraction_duration_seconds"] = round(_time.time() - q_start, 1)
    return extraction


async def _generate_cross_quarter_narrative(
    quarter_results: list[dict],
    symbol: str,
    model: str,
) -> dict:
    """Generate cross-quarter narrative from multiple quarter extractions.

    Returns empty dict if fewer than 2 quarters provided.
    """
    if len(quarter_results) < 2:
        return {}

    quarters_json = json.dumps(quarter_results, indent=2, default=str)
    cross_prompt = (
        f"Company: {symbol}\n"
        f"Quarters analyzed: {len(quarter_results)}\n\n"
        f"Per-quarter extractions:\n```json\n{quarters_json}\n```"
    )
    cross_response = await _call_claude(
        CROSS_QUARTER_PROMPT, cross_prompt, model,
        output_format=_CROSS_QUARTER_SCHEMA,
    )
    try:
        return _extract_json(cross_response)
    except (json.JSONDecodeError, ValueError):
        # Fallback: recover JSON from prose using cheap model
        if len(cross_response.strip()) > 200:
            logger.warning(
                "Cross-quarter narrative for %s returned prose (%d chars) — attempting JSON recovery",
                symbol, len(cross_response),
            )
            recovery_prompt = (
                f"The following is a prose cross-quarter analysis for {symbol}. "
                "It was supposed to be structured JSON but came out as text.\n\n"
                "Convert this into the JSON structure below. Preserve ALL specific numbers and quarter references.\n"
                "Return ONLY valid JSON — no markdown, no explanation.\n\n"
                "Required structure:\n"
                '{"key_themes": ["<theme with numbers>"], '
                '"guidance_track_record": {"promises": [], "delivery": [], "credibility_score": "", "assessment": ""}, '
                '"metric_trajectories": {"<metric>": {"values_by_quarter": {}, "trend": "", "interpretation": ""}}, '
                '"narrative_shifts": [], "recurring_analyst_concerns": [], '
                '"biggest_positive": "", "biggest_concern": "", '
                '"management_credibility": "", "what_to_watch_next_quarter": []}\n\n'
                f"Prose to convert:\n{cross_response[:8000]}"
            )
            try:
                recovery = await _call_claude(
                    system_prompt="You are a data extraction assistant. Convert prose into JSON. Return ONLY valid JSON.",
                    user_prompt=recovery_prompt,
                    model="claude-sonnet-4-6",
                    max_budget=0.15,
                    max_turns=1,
                )
                return _extract_json(recovery)
            except (json.JSONDecodeError, ValueError, Exception) as exc:
                logger.warning("Cross-quarter JSON recovery failed for %s: %s", symbol, exc)

        return {
            "extraction_error": "Failed to parse cross-quarter narrative",
            "raw_response": cross_response[:2000],
        }


async def extract_concalls(
    symbol: str,
    quarters: int = 4,
    model: str = "claude-sonnet-4-6",
    industry: str | None = None,
) -> dict:
    """Extract structured insights from the last N concall PDFs.

    Args:
        industry: NSE/Screener industry name (e.g. "Private Sector Bank").
            If provided, injects sector-specific canonical KPI extraction hints.

    Returns the full extraction dict matching concall_extraction_v2.json schema.
    """
    import time as _time
    concall_start = _time.time()
    symbol = symbol.upper()
    pdfs = _find_concall_pdfs(symbol, quarters=quarters)
    logger.info("[concall] %s: started, %d PDFs found", symbol, len(pdfs) if pdfs else 0)

    if not pdfs:
        raise FileNotFoundError(
            f"No concall PDFs found at ~/vault/stocks/{symbol}/filings/FY??-Q?/concall.pdf"
        )

    # --- Per-quarter extraction ---
    _extract_sem = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)

    async def _extract_with_limit(pdf_path: Path) -> dict:
        async with _extract_sem:
            return await _extract_single_quarter(pdf_path, symbol, model, industry)

    quarter_results = list(await asyncio.gather(
        *[_extract_with_limit(p) for p in pdfs]
    ))

    # --- Cross-quarter narrative ---
    cross_narrative = await _generate_cross_quarter_narrative(quarter_results, symbol, model)

    # --- Assemble final output ---
    result = {
        "symbol": symbol,
        "quarters_analyzed": len(quarter_results),
        "sector": industry or "",
        "extraction_date": date.today().isoformat(),
        "quarters": quarter_results,
        "cross_quarter_narrative": cross_narrative,
    }

    # Save to vault
    out_dir = _VAULT_BASE / symbol / "fundamentals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "concall_extraction_v2.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    logger.info("[concall] %s: done %.1fs, %d quarters extracted",
                symbol, _time.time() - concall_start, result.get("quarters_analyzed", 0))
    return result


async def ensure_concall_data(
    symbol: str,
    quarters: int = 4,
    model: str = "claude-sonnet-4-6",
    industry: str | None = None,
    force: bool = False,
) -> dict | None:
    """Ensure concall extraction data is available, extracting only new quarters.

    Per-quarter caching: if a quarter was already extracted successfully,
    it won't be re-extracted. Only quarters with PDFs but no extraction are processed.
    Cross-quarter narrative is regenerated only when new quarters are added.

    When ``force=True``, bypass the per-quarter cache and re-extract every
    available quarter. Use this after updating the sector-KPI schema or the
    extraction prompt so that existing cached extractions pick up the new
    fields (e.g. pharma R&D, FMCG UVG channels, telecom ARPU from E13).

    Returns the full extraction dict (same schema as concall_extraction_v2.json),
    or None if no concall PDFs exist for this symbol.
    """
    import time as _time
    start = _time.time()
    symbol = symbol.upper()

    # Step 1: Find available PDFs (downloads missing ones via Screener URLs)
    pdfs = _find_concall_pdfs(symbol, quarters=quarters)
    if not pdfs:
        logger.info("[concall_ensure] %s: no PDFs found", symbol)
        return None

    available = {pdf.parent.name: pdf for pdf in pdfs}  # {"FY26-Q3": Path, ...}

    # Step 2: Load existing extraction (skipped when force=True — we want every
    # quarter re-extracted, discarding cached labels/fields)
    extraction_path = _VAULT_BASE / symbol / "fundamentals" / "concall_extraction_v2.json"
    existing: dict | None = None
    cached_quarters: dict[str, dict] = {}  # fy_quarter -> quarter dict

    if force:
        logger.info("[concall_ensure] %s: force=True — re-extracting %d quarters", symbol, len(available))
    elif extraction_path.exists():
        try:
            existing = json.loads(extraction_path.read_text())
            for q in existing.get("quarters", []):
                fq = q.get("fy_quarter")
                if fq and q.get("extraction_status") in ("complete", "recovered"):
                    cached_quarters[fq] = q
        except (json.JSONDecodeError, OSError):
            existing = None  # corrupt file, treat as empty

    # Step 3: Determine which quarters need extraction
    missing = sorted(
        [fq for fq in available if fq not in cached_quarters],
        key=_fy_sort_key_from_str,
        reverse=True,
    )

    # Step 4: Fast path — nothing to extract
    if not missing and existing:
        logger.info("[concall_ensure] %s: all %d quarters cached", symbol, len(cached_quarters))
        existing["_new_quarters_extracted"] = 0
        return existing

    # Step 5: Extract missing quarters only
    _extract_sem = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)

    async def _extract_missing(fq: str) -> dict:
        async with _extract_sem:
            logger.info("[concall_ensure] %s: extracting %s", symbol, fq)
            return await _extract_single_quarter(available[fq], symbol, model, industry)

    new_extractions = list(await asyncio.gather(
        *[_extract_missing(fq) for fq in missing]
    )) if missing else []

    # Step 6: Merge new + existing quarters
    merged_quarters: dict[str, dict] = dict(cached_quarters)
    # Also keep non-cached existing quarters (partial/failed) that aren't being replaced
    if existing:
        for q in existing.get("quarters", []):
            fq = q.get("fy_quarter")
            if fq and fq not in merged_quarters:
                merged_quarters[fq] = q
    # Add new extractions (overwrite any failed/partial for same quarter)
    for q in new_extractions:
        fq = q.get("fy_quarter")
        if fq:
            merged_quarters[fq] = q

    all_quarters = sorted(
        merged_quarters.values(),
        key=lambda q: _fy_sort_key_from_str(q.get("fy_quarter", "FY00-Q1")),
        reverse=True,
    )

    # Step 7: Regenerate cross-quarter narrative only if new quarters were added
    cross_narrative = existing.get("cross_quarter_narrative", {}) if existing else {}
    if new_extractions:
        cross_narrative = await _generate_cross_quarter_narrative(all_quarters, symbol, model)

    # Step 8: Assemble and save
    result = {
        "symbol": symbol,
        "quarters_analyzed": len(all_quarters),
        "sector": industry or (existing.get("sector", "") if existing else ""),
        "extraction_date": date.today().isoformat(),
        "quarters": all_quarters,
        "cross_quarter_narrative": cross_narrative,
    }

    out_dir = _VAULT_BASE / symbol / "fundamentals"
    out_dir.mkdir(parents=True, exist_ok=True)
    extraction_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    logger.info(
        "[concall_ensure] %s: done %.1fs, %d new quarters, %d total",
        symbol, _time.time() - start, len(new_extractions), len(all_quarters),
    )
    result["_new_quarters_extracted"] = len(new_extractions)
    return result
