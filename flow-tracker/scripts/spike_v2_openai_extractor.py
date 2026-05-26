"""Phase 0 spike — same ETERNAL FY25 segmental test, against OpenAI gpt-4o-mini.

Validates the OpenAI tier of the v2 plan. Uses the same target pages
(262, 263, 374) and prompt as the NIM spike for apples-to-apples comparison.

Setup:
    1. ChatGPT Plus subscribers: install Codex CLI and run `codex` to sign in.
       This grants $5 in OpenAI API credits.
       (https://help.openai.com/en/articles/11369540)
    2. Generate an API key at https://platform.openai.com/api-keys
    3. Save to ~/.config/flowtracker/openai.env:
           OPENAI_API_KEY=sk-proj-...
       chmod 600 ~/.config/flowtracker/openai.env

Usage:
    uv run python flow-tracker/scripts/spike_v2_openai_extractor.py

Prints raw response, parsed JSON, segment count, and a PASS/FAIL verdict.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from openai import OpenAI

MODEL = "gpt-4o-mini"
DPI = 150
TARGET_PAGES = [262, 263, 374]

PROMPT = """Extract the segmental information from these annual report pages and return ONLY a JSON object — no prose, no fences, no commentary.

The pages are from Eternal Limited's FY2024-25 consolidated financials, Note 35 "Segment information". Convert all monetary values to INR Crores (the source figures are typically in Rs. Lakhs or Rs. Crores — convert to Crores).

Required output schema:
{
  "reporting_period": "FY25",
  "currency": "INR Cr",
  "segments": [
    {
      "name": "<segment name>",
      "revenue_cr": <number or null>,
      "ebitda_cr": <number or null>,
      "ebit_cr": <number or null>,
      "segment_assets_cr": <number or null>,
      "segment_liabilities_cr": <number or null>,
      "capex_cr": <number or null>
    }
  ],
  "geographical_breakdown": [
    {"region": "<name>", "revenue_cr": <number or null>}
  ]
}

Return null for any field not present. Do NOT fabricate values."""


def _load_api_key() -> str:
    env_path = Path.home() / ".config" / "flowtracker" / "openai.env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    if (k := os.environ.get("OPENAI_API_KEY")):
        return k
    sys.exit(
        "ERROR: OPENAI_API_KEY not set.\n"
        "  Setup steps:\n"
        "    1. Install OpenAI Codex CLI; run `codex` and sign in with ChatGPT (Plus account → $5 credit)\n"
        "    2. Create an API key at https://platform.openai.com/api-keys\n"
        "    3. Save to ~/.config/flowtracker/openai.env as OPENAI_API_KEY=sk-... (chmod 600)\n"
    )


def _render_pages(pdf_path: Path, page_nums: list[int]) -> list[str]:
    """Return base64 data URLs for each 1-based page."""
    doc = pdfium.PdfDocument(str(pdf_path))
    out = []
    try:
        for p in page_nums:
            pil = doc[p - 1].render(scale=DPI / 72.0).to_pil()
            buf = BytesIO()
            pil.convert("RGB").save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode()
            out.append(f"data:image/jpeg;base64,{b64}")
    finally:
        doc.close()
    return out


def _build_content(image_data_urls: list[str], prompt: str) -> list[dict]:
    """OpenAI's chat content shape — {type: text} + {type: image_url, image_url: {url}}."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    for url in image_data_urls:
        content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })
    return content


def _strip_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"No JSON object found: {text[:300]!r}")
    return json.loads(cleaned[s : e + 1])


def main() -> int:
    api_key = _load_api_key()
    pdf = Path.home() / "vault/stocks/ETERNAL/filings/FY25/annual_report.pdf"
    if not pdf.exists():
        sys.exit(f"PDF not found: {pdf}")

    print(f"Rendering pages {TARGET_PAGES} of {pdf.name} at {DPI} DPI...")
    image_urls = _render_pages(pdf, TARGET_PAGES)
    total_kb = sum(
        len(base64.b64decode(u.split(",", 1)[1])) for u in image_urls
    ) // 1024
    print(f"  -> {len(image_urls)} JPEGs, total ~{total_kb} KB")

    client = OpenAI(api_key=api_key)
    print(f"Calling {MODEL} via OpenAI API...")

    t0 = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system",
             "content": "You are a precise financial-data extractor. Output valid JSON only."},
            {"role": "user", "content": _build_content(image_urls, PROMPT)},
        ],
        temperature=0.0,
        max_tokens=4096,
        response_format={"type": "json_object"},  # OpenAI's JSON mode
    )
    elapsed = time.time() - t0

    usage = response.usage
    print(f"  HTTP 200 in {elapsed:.1f}s")
    print(f"  Tokens: prompt={usage.prompt_tokens}  "
          f"completion={usage.completion_tokens}  total={usage.total_tokens}")
    cost = (usage.prompt_tokens * 0.15 + usage.completion_tokens * 0.60) / 1_000_000
    print(f"  Estimated cost: ${cost:.5f}")

    raw = response.choices[0].message.content
    print("\n=== RAW MODEL RESPONSE ===")
    print(raw[:4000])
    print("=== END RAW ===\n")

    try:
        parsed = _strip_json(raw)
        print("=== PARSED JSON ===")
        print(json.dumps(parsed, indent=2))
        print("=== END PARSED ===\n")

        segments = parsed.get("segments", [])
        rev_filled = [
            s for s in segments
            if isinstance(s, dict) and isinstance(s.get("revenue_cr"), (int, float))
        ]
        print(f"Segments returned: {len(segments)}")
        print(f"Segments with revenue_cr populated: {len(rev_filled)}")
        for s in segments[:8]:
            print(f"  {s.get('name','?'):45s} "
                  f"revenue={s.get('revenue_cr')}  ebitda={s.get('ebitda_cr')}")
        verdict = "PASS" if len(rev_filled) >= 2 else "FAIL"
        print(f"\n>>> Spike verdict: {verdict}")
        return 0 if verdict == "PASS" else 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"JSON parse failed: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
