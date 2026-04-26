"""Extract BFSI quarterly metrics from earnings press release PDFs.

Banks file a quarterly earnings press release at BSE/NSE that contains the
headline NIM, NNPA%, PCR%, GNPA%, CASA%, CRAR%, CET-1%, LCR% values — the
Q-end *snapshot* disclosures, distinct from the concall's qualitative
discussion. The concall extractor (`concall_extractor.py`) covers the Q&A and
opening remarks; this module extracts the disclosure values.

The press release PDFs are TEXT-based (selectable text), so this module uses
pdfplumber + Claude Agent SDK with a structured JSON schema. **No OCR.**

Discovery strategy:
- Primary: `corporate_filings` rows with `subcategory = 'Press Release / Media
  Release'` whose headline mentions the quarter results.
- Fallback: `corporate_filings` rows with `subcategory = 'Financial Results'`.
  Many banks (ICICI, BoB) bundle the press release into the Financial Results
  PDF; HDFC, SBI sometimes file both. The Financial Results PDF for these
  banks contains both the audited statements and the press-release text — we
  feed the whole document to the LLM and let it extract.

Industry gate: only fires for symbols whose industry maps to the BFSI sector
(see `_BFSI_INDUSTRIES` in `data_api.py`). Non-bank stocks are skipped.

Output: ``~/vault/stocks/<SYM>/fundamentals/press_release_extraction_v1.json``
keyed by ``fy_quarter``. PDF cache: ``~/vault/stocks/<SYM>/filings/<FY-Q>/
press_release.pdf``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime, timezone
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
_BSE_ATTACH_LIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"
_BSE_ATTACH_HIS = "https://www.bseindia.com/xml-data/corpfiling/AttachHis"

MAX_CONCURRENT_EXTRACTIONS = 3
EXTRACTION_VERSION = "v1"

# Industries that get press-release extraction. Mirrors `_BFSI_INDUSTRIES` in
# data_api.py. Insurance/AMC/Broker have different metric sets and are
# explicitly excluded — extend by adding sector-specific schemas.
_PR_ELIGIBLE_INDUSTRIES = {
    # yfinance strings
    "Banks - Regional", "Banks - Diversified", "Credit Services",
    "Mortgage Finance", "Financial Conglomerates",
    # Screener fallback strings
    "Private Sector Bank", "Public Sector Bank", "Other Bank",
    "Non Banking Financial Company (NBFC)", "Financial Institution",
    "Other Financial Services", "Financial Products Distributor",
    "Financial Technology (Fintech)", "Housing Finance Company",
    "Microfinance Institutions",
}

# --- BFSI extraction schema ---

_PRESS_RELEASE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "bfsi_press_release_metrics",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "fy_quarter": {"type": "string"},
                "as_of_date": {"type": "string"},
                "is_press_release": {"type": "boolean"},
                # Asset-quality
                "gnpa_pct": {"type": ["number", "null"]},
                "nnpa_pct": {"type": ["number", "null"]},
                "pcr_pct": {"type": ["number", "null"]},
                # Margins
                "nim_pct": {"type": ["number", "null"]},
                # Mix
                "casa_pct": {"type": ["number", "null"]},
                # Capital
                "crar_pct": {"type": ["number", "null"]},
                "cet1_pct": {"type": ["number", "null"]},
                "tier1_pct": {"type": ["number", "null"]},
                # Liquidity
                "lcr_pct": {"type": ["number", "null"]},
                # Balance sheet (₹ Cr)
                "advances_cr": {"type": ["number", "null"]},
                "deposits_cr": {"type": ["number", "null"]},
                "rwa_cr": {"type": ["number", "null"]},
                # Provenance for each metric — page where it was found
                "source_page": {
                    "type": "object",
                    "additionalProperties": {"type": ["integer", "null"]},
                },
                # Free-form context for each metric, for downstream verification
                "context": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    },
}

PRESS_RELEASE_PROMPT = """**OUTPUT FORMAT: Return ONLY a single valid JSON object. No prose, no markdown fences. Start with `{` and end with `}`.**

You are a banking-disclosure data extractor. The user will provide the FULL text of a quarterly financial-results filing (press release + financial results) for an Indian-listed bank/NBFC.

Your job: extract the *headline* quarterly snapshot values that the bank publishes in its press release. These are the as-of-quarter-end disclosure values, NOT trend or comparison numbers.

**Extract each value EXACTLY as the bank states it.** Never compute, average, or annualise. If two values are given (e.g. domestic NIM vs global NIM, standalone vs consolidated CASA), prefer **standalone Indian GAAP** values — that is what Indian bank press releases headline.

For NIM specifically: prefer the bank's headline NIM. If it discloses both "core NIM on total assets" and "NIM on interest earning assets", pick the headline (usually the higher number on interest-earning assets) and record which one in `context.nim_pct`.

For CASA: extract `casa_pct` = CASA deposits as % of total deposits as the bank states it. Do NOT compute from CA + SA splits.

For PCR: extract `pcr_pct` = Provision Coverage Ratio. Banks usually quote it excluding technical write-offs; if both are given, pick the excluding-write-off value and note it in `context.pcr_pct`.

For balance-sheet items (advances, deposits, RWA): convert to **₹ Crores** if the bank reports in billions/lakhs/crores. 1 billion = 100 crores. 1 lakh crore = 100,000 crores. The press release will usually be in `₹ X billion` or `₹ X crore` — convert to crores.

If a metric is not stated in the document, set it to `null`. NEVER guess. NEVER infer. Only extract values that appear verbatim.

If the document is NOT a quarterly earnings press release (e.g. it's a Reg 30 cover letter, a board-meeting outcome, an unrelated press release), set `is_press_release` to `false` and leave all metric fields null.

Return JSON in this exact shape:

```json
{
  "fy_quarter": "FY26-Q3",
  "as_of_date": "2025-12-31",
  "is_press_release": true,
  "gnpa_pct": 1.24,
  "nnpa_pct": 0.42,
  "pcr_pct": null,
  "nim_pct": 3.51,
  "casa_pct": 33.6,
  "crar_pct": 19.9,
  "cet1_pct": 17.4,
  "tier1_pct": 17.8,
  "lcr_pct": null,
  "advances_cr": 2844600,
  "deposits_cr": 2860100,
  "rwa_cr": 2880800,
  "source_page": {"gnpa_pct": 20, "nnpa_pct": 20, "nim_pct": 18, "casa_pct": 19, "crar_pct": 20, "cet1_pct": 20},
  "context": {
    "nim_pct": "core NIM 3.35% on total assets, 3.51% on interest-earning assets — taking interest-earning per bank's headline framing",
    "casa_pct": "CASA deposits 33.6% of total deposits as of Dec 31, 2025"
  }
}
```

Rules:
- `as_of_date` is the quarter-end date (e.g. `2025-12-31` for Q3 FY26), NOT the filing date.
- All percentages as numbers (3.51, not "3.51%" or "3.51 percent").
- All ₹ amounts as **crores** (₹1 Cr = 10M).
- `source_page` keys: include only metrics that have a non-null value, mapped to the 1-indexed PDF page where the value appears.
- `context`: free-form one-line note for any metric where the bank's framing matters (NIM choice, PCR variant, etc.). Optional.
- **CRITICAL**: ENTIRE response must be valid JSON. No prose. Start with `{`. End with `}`.
"""


# --- FY quarter helpers (kept independent of concall_extractor for module isolation) ---

_FY_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def _fy_sort_key(fy_quarter: str) -> tuple[int, int]:
    try:
        fy = int(fy_quarter[2:4])
        q = _FY_ORDER.get(fy_quarter.split("-")[1], 0)
        return (fy, q)
    except (ValueError, IndexError):
        return (0, 0)


def _filing_date_to_fy_quarter(date_str: str) -> str:
    """Map a BSE filing_date (YYYY-MM-DD) to the FY-Quarter it reports.

    Indian FY runs Apr-Mar. Banks file quarterly results within ~45 days of
    quarter-end:
      Apr-Jun filings  → Q4 of CURRENT FY (Jan-Mar quarter-end of YYYY)
      Jul-Sep filings  → Q1 of CURRENT FY (Apr-Jun quarter-end of YYYY)
      Oct-Dec filings  → Q2 of CURRENT FY (Jul-Sep quarter-end of YYYY)
      Jan-Mar filings  → Q3 of CURRENT FY (Oct-Dec quarter-end of YYYY-1)

    "FY26" is the fiscal year ending March 2026 (= Apr 2025 – Mar 2026).
    Examples:
      filing 2026-04-18 → Q4 of FY26 (= Jan-Mar 2026)
      filing 2026-01-17 → Q3 of FY26 (= Oct-Dec 2025)
      filing 2025-10-18 → Q2 of FY26 (= Jul-Sep 2025)
      filing 2025-07-19 → Q1 of FY26 (= Apr-Jun 2025)
      filing 2025-05-03 → Q4 of FY25 (= Jan-Mar 2025)
    """
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    yr, mo = dt.year, dt.month
    if mo in (4, 5, 6):
        # Q4 of FY ending in March of `yr` (e.g. May 2025 → Q4 FY25)
        fy = yr % 100
        return f"FY{fy:02d}-Q4"
    if mo in (7, 8, 9):
        # Q1 of FY ending in March of `yr+1` (e.g. Jul 2025 → Q1 FY26)
        fy = (yr + 1) % 100
        return f"FY{fy:02d}-Q1"
    if mo in (10, 11, 12):
        # Q2 of FY ending in March of `yr+1` (e.g. Oct 2025 → Q2 FY26)
        fy = (yr + 1) % 100
        return f"FY{fy:02d}-Q2"
    # Jan-Mar
    fy = yr % 100
    return f"FY{fy:02d}-Q3"


def _quarter_end_date(fy_quarter: str) -> str:
    """Return YYYY-MM-DD for the quarter-end date of an FY-Q label."""
    fy = 2000 + int(fy_quarter[2:4])
    q = fy_quarter.split("-")[1]
    if q == "Q1":
        return f"{fy - 1}-06-30"
    if q == "Q2":
        return f"{fy - 1}-09-30"
    if q == "Q3":
        return f"{fy - 1}-12-31"
    if q == "Q4":
        return f"{fy}-03-31"
    return ""


# --- Filing discovery ---


# Headline filters that strongly suggest this is the quarterly results
# press release (and not a one-off press release like "raising of Tier 2
# bonds" or "stake sale through IPO").
_RESULTS_HEADLINE_PATTERNS = (
    re.compile(r"financial\s+result", re.IGNORECASE),
    re.compile(r"q[1-4]\s*fy", re.IGNORECASE),
    re.compile(r"quarter\s+(?:and|ended)", re.IGNORECASE),
    re.compile(r"unaudited", re.IGNORECASE),
    re.compile(r"audited", re.IGNORECASE),
    re.compile(r"earnings\s+(?:call|release|results)", re.IGNORECASE),
)


def _is_results_filing(headline: str) -> bool:
    """Heuristic: does this headline look like a quarterly results filing?"""
    if not headline:
        return False
    return any(p.search(headline) for p in _RESULTS_HEADLINE_PATTERNS)


def _find_filings_for_symbol(
    symbol: str, max_quarters: int = 4
) -> list[dict]:
    """Find candidate quarterly-results filings from corporate_filings.

    Returns list of dicts: {fy_quarter, filing_date, news_id, attachment_name,
    pdf_flag, headline, subcategory, local_path}. One entry per FY-quarter,
    with 'Press Release / Media Release' preferred over 'Financial Results'
    when both exist for the same quarter.
    """
    from flowtracker.store import FlowStore

    symbol = symbol.upper()
    with FlowStore() as store:
        rows = store._conn.execute(
            "SELECT subcategory, filing_date, news_id, attachment_name, "
            "pdf_flag, headline, local_path "
            "FROM corporate_filings "
            "WHERE symbol = ? "
            "AND (subcategory LIKE 'Press Release%' OR subcategory = 'Financial Results') "
            "ORDER BY filing_date DESC",
            (symbol,),
        ).fetchall()

    # Deduplicate by FY-quarter, preferring 'Press Release / Media Release'
    by_quarter: dict[str, dict] = {}
    for r in rows:
        if not _is_results_filing(r["headline"]):
            continue
        fq = _filing_date_to_fy_quarter(r["filing_date"])
        candidate = {
            "fy_quarter": fq,
            "filing_date": r["filing_date"],
            "news_id": r["news_id"],
            "attachment_name": r["attachment_name"],
            "pdf_flag": r["pdf_flag"],
            "headline": r["headline"],
            "subcategory": r["subcategory"],
            "local_path": r["local_path"],
        }
        existing = by_quarter.get(fq)
        if existing is None:
            by_quarter[fq] = candidate
            continue
        # Prefer Press Release subcategory over Financial Results
        if "Press Release" in candidate["subcategory"] and "Press Release" not in existing["subcategory"]:
            by_quarter[fq] = candidate

    sorted_quarters = sorted(by_quarter.values(), key=lambda c: _fy_sort_key(c["fy_quarter"]), reverse=True)
    return sorted_quarters[:max_quarters]


def _download_press_release(
    attachment_name: str, pdf_flag: int, dest_path: Path
) -> bool:
    """Download a press-release PDF from BSE. Returns True on success.

    BSE serves recent filings via AttachLive and older ones via AttachHis.
    The pdf_flag column indicates which (1=Live, 0=Hist), but in practice the
    AttachLive endpoint returns an HTML stub for older filings, so we try
    AttachHis first when pdf_flag=0 and fall back to the other on failure.
    """
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream,*/*",
        "Referer": "https://www.bseindia.com/",
    }
    primary = _BSE_ATTACH_LIVE if pdf_flag == 1 else _BSE_ATTACH_HIS
    fallback = _BSE_ATTACH_HIS if primary == _BSE_ATTACH_LIVE else _BSE_ATTACH_LIVE
    for base in (primary, fallback):
        url = f"{base}/{attachment_name}"
        try:
            with httpx.Client(follow_redirects=True, timeout=45, headers=headers) as client:
                resp = client.get(url)
                if resp.status_code == 200 and resp.content[:4] == b"%PDF" and len(resp.content) > 1000:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(resp.content)
                    return True
        except Exception as exc:
            logger.debug("Download failed from %s: %s", base, exc)
            continue
    return False


def ensure_press_release_pdf(symbol: str, fy_quarter: str, candidate: dict) -> Path | None:
    """Ensure the press release PDF exists in vault for this quarter.

    Returns the local Path if available (cached or freshly downloaded), else None.
    """
    symbol = symbol.upper()
    dest = _VAULT_BASE / symbol / "filings" / fy_quarter / "press_release.pdf"
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    if not candidate.get("attachment_name"):
        return None
    ok = _download_press_release(
        candidate["attachment_name"], candidate.get("pdf_flag") or 0, dest
    )
    if ok:
        # Also update store's local_path for downstream tracking
        try:
            from flowtracker.store import FlowStore
            with FlowStore() as store:
                if candidate.get("news_id"):
                    store.update_filing_path(candidate["news_id"], str(dest))
        except Exception as exc:
            logger.debug("Could not update filing local_path: %s", exc)
        return dest
    return None


# --- PDF text extraction ---


def _read_pdf_text(pdf_path: Path) -> tuple[str, int]:
    """Extract text from a PDF using pdfplumber.

    Returns ``(text, page_count)``. If the PDF appears image-rendered (pdfplumber
    finds no extractable text), returns empty string with `page_count > 0`. The
    caller should mark such filings as `status='image_rendered'` and skip.
    """
    import pdfplumber

    pages = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
    except Exception as exc:
        logger.warning("pdfplumber failed on %s: %s", pdf_path, exc)
        return "", 0

    full = "\n\n".join(pages)
    return full, page_count


def _is_image_rendered(text: str, page_count: int) -> bool:
    """Heuristic: a PDF is image-rendered if pdfplumber returns near-zero text
    despite having pages. Banks' press releases are 5-25 pages; a real text
    PDF will have ≥500 chars/page. Image PDFs return <50 chars/page.
    """
    if page_count == 0:
        return False
    chars_per_page = len(text.strip()) / page_count
    return chars_per_page < 100


# --- Claude SDK call (mirrors concall_extractor pattern) ---


async def _call_claude(
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_budget: float = 0.30,
    max_turns: int = 2,
    output_format: dict | None = None,
) -> str:
    """Call Claude via Agent SDK. Same shape as concall_extractor._call_claude
    but with smaller budget defaults (press releases are smaller than concalls).
    """
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        max_turns=max_turns,
        max_budget_usd=max_budget,
        permission_mode="bypassPermissions",
        model=model,
        thinking={"type": "disabled"},
        disallowed_tools=[
            "Bash", "Read", "Write", "Edit", "Glob", "Grep",
            "WebSearch", "WebFetch", "Agent", "Skill", "NotebookEdit", "TodoWrite",
        ],
        stderr=lambda line: logger.warning("[cli-stderr] %s", line),
        env={"CLAUDE_CODE_STREAM_CLOSE_TIMEOUT": "120000"},
        # See concall_extractor for the [""] vs [] rationale (SDK #794).
        setting_sources=[""],
        plugins=[],
    )
    if output_format:
        options.output_format = output_format
    text_blocks: list[str] = []
    result_text = ""
    try:
        async for msg in query(prompt=user_prompt, options=options):
            if isinstance(msg, RateLimitEvent):
                logger.warning(
                    "[press_release] rate limited: status=%s type=%s",
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
    """Extract JSON from a Claude response (may have code fences/prose)."""
    text = text.strip()

    def _try_parse(s: str) -> dict:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            repaired = re.sub(r",\s*([}\]])", r"\1", s)
            return json.loads(repaired)

    if text.startswith("{"):
        try:
            return _try_parse(text)
        except json.JSONDecodeError:
            pass
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return _try_parse(m.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return _try_parse(text[start:end + 1])
    raise json.JSONDecodeError("No JSON found", text, 0)


# --- Main extraction pipeline ---


_METRIC_KEYS = (
    "gnpa_pct", "nnpa_pct", "pcr_pct", "nim_pct", "casa_pct",
    "crar_pct", "cet1_pct", "tier1_pct", "lcr_pct",
    "advances_cr", "deposits_cr", "rwa_cr",
)


def _build_metric_record(
    extraction: dict, fy_quarter: str, candidate: dict, source_filename: str,
    status: str = "complete",
) -> dict:
    """Normalise a Claude extraction into the cached record shape.

    The cached JSON keeps a stable structure even when extraction failed —
    every quarter has the same keys so downstream callers can rely on them.
    """
    record = {
        "fy_quarter": fy_quarter,
        "as_of_date": extraction.get("as_of_date") or _quarter_end_date(fy_quarter),
        "filing_date": candidate.get("filing_date"),
        "subcategory": candidate.get("subcategory"),
        "headline": candidate.get("headline"),
        "source_filename": source_filename,
        "extraction_status": status,
        "extraction_version": EXTRACTION_VERSION,
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "is_press_release": extraction.get("is_press_release", True),
        "metrics": {},
        "source_page": extraction.get("source_page") or {},
        "context": extraction.get("context") or {},
    }
    for key in _METRIC_KEYS:
        val = extraction.get(key)
        # Coerce stringy numbers ("3.51") to floats; preserve None.
        if isinstance(val, str):
            try:
                val = float(val.strip().rstrip("%"))
            except (ValueError, AttributeError):
                val = None
        record["metrics"][key] = val
    return record


async def _extract_single_quarter(
    pdf_path: Path,
    symbol: str,
    fy_quarter: str,
    candidate: dict,
    model: str,
) -> dict:
    """Extract BFSI metrics from a single press-release PDF."""
    text, page_count = _read_pdf_text(pdf_path)

    if _is_image_rendered(text, page_count):
        logger.warning(
            "Press release for %s %s appears image-rendered (%d pages, %d chars) — skipping",
            symbol, fy_quarter, page_count, len(text),
        )
        return {
            "fy_quarter": fy_quarter,
            "as_of_date": _quarter_end_date(fy_quarter),
            "filing_date": candidate.get("filing_date"),
            "subcategory": candidate.get("subcategory"),
            "headline": candidate.get("headline"),
            "source_filename": pdf_path.name,
            "extraction_status": "image_rendered",
            "extraction_version": EXTRACTION_VERSION,
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "is_press_release": False,
            "metrics": {k: None for k in _METRIC_KEYS},
            "source_page": {},
            "context": {},
        }

    user_prompt = (
        f"Company: {symbol}\nQuarter: {fy_quarter}\n"
        f"Filing date: {candidate.get('filing_date')}\n"
        f"BSE subcategory: {candidate.get('subcategory')}\n"
        f"Headline: {candidate.get('headline')}\n\n"
        f"## Press Release / Financial Results PDF text\n\n{text}"
    )

    try:
        response = await _call_claude(
            PRESS_RELEASE_PROMPT, user_prompt, model,
            output_format=_PRESS_RELEASE_SCHEMA,
        )
        extraction = _extract_json(response)
        return _build_metric_record(extraction, fy_quarter, candidate, pdf_path.name, status="complete")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("JSON parse failed for %s %s: %s", symbol, fy_quarter, exc)
        return {
            "fy_quarter": fy_quarter,
            "as_of_date": _quarter_end_date(fy_quarter),
            "filing_date": candidate.get("filing_date"),
            "subcategory": candidate.get("subcategory"),
            "headline": candidate.get("headline"),
            "source_filename": pdf_path.name,
            "extraction_status": "failed",
            "extraction_error": str(exc)[:300],
            "extraction_version": EXTRACTION_VERSION,
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "is_press_release": False,
            "metrics": {k: None for k in _METRIC_KEYS},
            "source_page": {},
            "context": {},
        }


def is_eligible_industry(industry: str | None) -> bool:
    """True if the industry is in the BFSI press-release-eligible set."""
    return bool(industry) and industry in _PR_ELIGIBLE_INDUSTRIES


def _output_path(symbol: str) -> Path:
    return _VAULT_BASE / symbol.upper() / "fundamentals" / "press_release_extraction_v1.json"


def _load_existing(symbol: str) -> dict:
    path = _output_path(symbol)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(symbol: str, payload: dict) -> Path:
    path = _output_path(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


async def extract_press_releases(
    symbol: str,
    quarters: int = 2,
    model: str = "claude-sonnet-4-6",
    industry: str | None = None,
    force: bool = False,
) -> dict | None:
    """Extract BFSI press release metrics for the last N quarters.

    Returns the full payload (also persisted to vault), or None if the symbol
    isn't eligible (non-BFSI industry) or no candidate filings exist.

    Per-quarter caching: completed extractions are skipped unless
    ``force=True``. Failed/image_rendered statuses are NOT cached and will be
    retried on the next call.
    """
    symbol = symbol.upper()

    # Industry gate. Caller may pass industry explicitly to avoid an extra DB
    # round-trip; otherwise look it up.
    if industry is None:
        try:
            from flowtracker.research.data_api import ResearchDataAPI
            with ResearchDataAPI() as api:
                industry = api._get_industry(symbol)
        except Exception:
            industry = None
    if not is_eligible_industry(industry):
        logger.info(
            "[press_release] %s skipped — industry %r not BFSI-eligible",
            symbol, industry,
        )
        return None

    candidates = _find_filings_for_symbol(symbol, max_quarters=quarters)
    if not candidates:
        logger.info("[press_release] %s: no quarterly results filings in corporate_filings", symbol)
        return None

    existing = _load_existing(symbol)
    existing_quarters: dict[str, dict] = existing.get("quarters", {}) if isinstance(existing, dict) else {}

    # Determine which quarters need extraction
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EXTRACTIONS)

    async def _process_one(candidate: dict) -> tuple[str, dict | None]:
        fq = candidate["fy_quarter"]
        cached = existing_quarters.get(fq)
        if cached and cached.get("extraction_status") == "complete" and not force:
            logger.debug("[press_release] %s %s cached", symbol, fq)
            return fq, None  # signal "no-op"

        pdf_path = ensure_press_release_pdf(symbol, fq, candidate)
        if pdf_path is None:
            logger.warning("[press_release] %s %s: PDF download failed", symbol, fq)
            return fq, {
                "fy_quarter": fq,
                "as_of_date": _quarter_end_date(fq),
                "filing_date": candidate.get("filing_date"),
                "subcategory": candidate.get("subcategory"),
                "headline": candidate.get("headline"),
                "source_filename": None,
                "extraction_status": "download_failed",
                "extraction_version": EXTRACTION_VERSION,
                "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "is_press_release": False,
                "metrics": {k: None for k in _METRIC_KEYS},
                "source_page": {},
                "context": {},
            }

        async with semaphore:
            record = await _extract_single_quarter(pdf_path, symbol, fq, candidate, model)
        return fq, record

    results = await asyncio.gather(*(_process_one(c) for c in candidates))

    # Merge: keep all existing records, overwrite with new ones
    merged = dict(existing_quarters)
    new_count = 0
    for fq, record in results:
        if record is None:
            continue
        merged[fq] = record
        if record.get("extraction_status") == "complete":
            new_count += 1

    payload = {
        "symbol": symbol,
        "industry": industry,
        "extraction_version": EXTRACTION_VERSION,
        "extraction_date": date.today().isoformat(),
        "quarters": merged,
    }
    _save(symbol, payload)
    logger.info(
        "[press_release] %s done — %d quarters total, %d new completions",
        symbol, len(merged), new_count,
    )
    payload["_new_quarters_extracted"] = new_count
    return payload


async def ensure_press_release_data(
    symbol: str,
    quarters: int = 2,
    model: str = "claude-sonnet-4-6",
    industry: str | None = None,
    force: bool = False,
) -> dict | None:
    """Convenience wrapper — same signature as concall_extractor.ensure_concall_data.

    Returns None for non-BFSI symbols or when no PDFs are downloadable.
    """
    return await extract_press_releases(symbol, quarters, model, industry, force)
