"""Phase 0 spike — validate that NVIDIA NIM Nemotron Nano 12B V2 VL can extract
structured segmental data from ETERNAL FY25 AR pages 262-263 (the actual data
table the v1 pipeline misses).

Usage:
    uv run python flow-tracker/scripts/spike_v2_nim_extractor.py

Reads NVIDIA_API_KEY from ~/.config/flowtracker/nvidia.env. Renders the target
PDF page range to JPEGs at 150 DPI, batches up to 4 images per call (the
NIM endpoint cap), and asks Nemotron for a structured JSON segmental table.

Output: prints raw response + parsed JSON. Success criteria printed at end.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import requests

NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-nano-12b-v2-vl"
DPI = 150

PROMPT = """Extract the segmental information from these annual report pages and return ONLY a JSON object — no prose, no fences, no commentary.

The pages contain Note 35 "Segment information" from Eternal Limited's FY2024-25 consolidated financials. Extract one row per reportable segment. Use INR Crores for monetary values (the source figures are typically in Rs. Lakhs or Rs. Crores — convert to Crores).

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

If a value is not present in the source for a given segment, return null. Do NOT fabricate numbers."""


def _load_api_key() -> str:
    env_path = Path.home() / ".config" / "flowtracker" / "nvidia.env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("NVIDIA_API_KEY="):
                return line.split("=", 1)[1].strip()
    if (k := os.environ.get("NVIDIA_API_KEY")):
        return k
    sys.exit("ERROR: NVIDIA_API_KEY not set in env or ~/.config/flowtracker/nvidia.env")


def _render_pages_to_jpeg(pdf_path: Path, page_nums_1based: list[int]) -> list[bytes]:
    """Return JPEG bytes for each requested 1-based page number."""
    doc = pdfium.PdfDocument(str(pdf_path))
    out = []
    try:
        for p in page_nums_1based:
            page = doc[p - 1]
            scale = DPI / 72.0
            pil_image = page.render(scale=scale).to_pil()
            buf = BytesIO()
            pil_image.convert("RGB").save(buf, format="JPEG", quality=85)
            out.append(buf.getvalue())
    finally:
        doc.close()
    return out


def _build_content(jpegs: list[bytes], prompt: str) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for jpeg in jpegs:
        b64 = base64.b64encode(jpeg).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    return content


def _strip_json(text: str) -> dict:
    """Salvage JSON from a possibly-prosey response."""
    cleaned = text.strip()
    # Strip code fences if any
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    # Find first '{' and last '}'
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"No JSON object found in response: {text[:300]!r}")
    return json.loads(cleaned[s : e + 1])


def main() -> int:
    api_key = _load_api_key()
    pdf_path = Path.home() / "vault/stocks/ETERNAL/filings/FY25/annual_report.pdf"
    if not pdf_path.exists():
        sys.exit(f"PDF not found: {pdf_path}")

    target_pages = [262, 263, 374]  # 4-image NIM cap; 3 pages is fine
    print(f"Rendering pages {target_pages} of {pdf_path.name} at {DPI} DPI...")
    jpegs = _render_pages_to_jpeg(pdf_path, target_pages)
    total_kb = sum(len(j) for j in jpegs) // 1024
    print(f"  -> {len(jpegs)} JPEGs, total {total_kb} KB")

    content = _build_content(jpegs, PROMPT)
    payload = {
        "model": MODEL,
        "max_tokens": 4096,
        "temperature": 0.0,  # deterministic for table extraction
        "top_p": 1.0,
        "messages": [
            {"role": "system", "content": "/no_think"},
            {"role": "user", "content": content},
        ],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    print(f"Calling {MODEL} via NIM...")
    r = requests.post(NIM_URL, headers=headers, json=payload, timeout=180)
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print("Error body:", r.text[:1500])
        return 2

    body = r.json()
    usage = body.get("usage", {})
    print(f"Usage: prompt={usage.get('prompt_tokens')}  "
          f"completion={usage.get('completion_tokens')}  "
          f"total={usage.get('total_tokens')}")

    raw_response = body["choices"][0]["message"]["content"]
    print("\n=== RAW MODEL RESPONSE ===")
    print(raw_response[:4000])
    print("=== END RAW ===\n")

    try:
        parsed = _strip_json(raw_response)
        print("=== PARSED JSON ===")
        print(json.dumps(parsed, indent=2))
        print("=== END PARSED ===\n")

        # Success criteria
        segments = parsed.get("segments", [])
        non_null_count = sum(
            1 for s in segments
            if isinstance(s, dict) and any(
                isinstance(s.get(k), (int, float))
                for k in ("revenue_cr", "ebitda_cr", "ebit_cr", "segment_assets_cr")
            )
        )
        print(f"Segments returned: {len(segments)}")
        print(f"Segments with at least one numeric: {non_null_count}")
        verdict = "PASS" if non_null_count >= 2 else "FAIL"
        print(f"\n>>> Phase 0 verdict: {verdict}")
        return 0 if verdict == "PASS" else 1
    except (ValueError, json.JSONDecodeError) as e:
        print(f"JSON parse failed: {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
