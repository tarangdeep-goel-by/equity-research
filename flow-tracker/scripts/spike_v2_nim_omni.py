"""Phase 0 spike v2 — same ETERNAL FY25 segmental test, but against the newer
nvidia/nemotron-3-nano-omni-30b-a3b-reasoning model (launched 2026-04-28).

Tests two configurations:
  1. enable_thinking=False  (fast, deterministic — preferred for tabular extraction)
  2. enable_thinking=True   (slower, may catch edge cases the smaller model misses)

Reads NVIDIA_API_KEY from ~/.config/flowtracker/nvidia.env.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
from openai import OpenAI

MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
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
    env_path = Path.home() / ".config" / "flowtracker" / "nvidia.env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("NVIDIA_API_KEY="):
                return line.split("=", 1)[1].strip()
    if (k := os.environ.get("NVIDIA_API_KEY")):
        return k
    sys.exit("ERROR: NVIDIA_API_KEY not set")


def _render(pdf_path: Path, page_nums: list[int]) -> list[str]:
    """Return data-URL JPEGs (base64) for each 1-based page."""
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
    content: list[dict] = [{"type": "text", "text": prompt}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content


def _strip_json(text: str) -> dict:
    import re
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)
    s, e = cleaned.find("{"), cleaned.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"no JSON object: {text[:300]!r}")
    return json.loads(cleaned[s : e + 1])


def run_one(client: OpenAI, image_urls: list[str], thinking: bool) -> tuple[str, str]:
    """Returns (reasoning_text, content_text)."""
    label = "thinking=on" if thinking else "thinking=off"
    print(f"\n=== {MODEL} | {label} ===")
    t0 = time.time()
    extra_body: dict = {"chat_template_kwargs": {"enable_thinking": thinking}}
    if thinking:
        extra_body["reasoning_budget"] = 8192

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": _build_content(image_urls, PROMPT)}],
        temperature=0.0 if not thinking else 0.6,
        top_p=0.95,
        max_tokens=8192 if not thinking else 16384,
        extra_body=extra_body,
        stream=True,
    )

    reasoning_chunks: list[str] = []
    content_chunks: list[str] = []
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        r = getattr(delta, "reasoning_content", None)
        if r:
            reasoning_chunks.append(r)
        if delta.content:
            content_chunks.append(delta.content)

    elapsed = time.time() - t0
    reasoning = "".join(reasoning_chunks)
    content = "".join(content_chunks)
    print(f"  Latency: {elapsed:.1f}s")
    print(f"  Reasoning chars: {len(reasoning)}")
    print(f"  Content chars:   {len(content)}")
    print(f"  --- CONTENT ---")
    print(content[:3000])
    print(f"  --- END ---")
    return reasoning, content


def evaluate(label: str, content: str) -> dict:
    print(f"\n  ::: {label} verdict :::")
    try:
        parsed = _strip_json(content)
    except Exception as e:
        print(f"  JSON parse FAILED: {e}")
        return {"label": label, "ok": False, "reason": "parse_failed"}
    segments = parsed.get("segments", [])
    rev_filled = [s for s in segments
                  if isinstance(s, dict) and isinstance(s.get("revenue_cr"), (int, float))]
    print(f"  Segments: {len(segments)}; with revenue: {len(rev_filled)}")
    for s in segments[:8]:
        rev = s.get("revenue_cr")
        ebitda = s.get("ebitda_cr")
        print(f"    {s.get('name','?'):45s}  revenue={rev}  ebitda={ebitda}")
    ok = len(rev_filled) >= 2
    print(f"  -> {'PASS' if ok else 'FAIL'}")
    return {"label": label, "ok": ok, "n_segments": len(segments), "n_with_revenue": len(rev_filled)}


def main() -> int:
    api_key = _load_api_key()
    pdf = Path.home() / "vault/stocks/ETERNAL/filings/FY25/annual_report.pdf"
    if not pdf.exists():
        sys.exit(f"PDF not found: {pdf}")

    print(f"Rendering pages {TARGET_PAGES} ...")
    image_urls = _render(pdf, TARGET_PAGES)
    print(f"  -> {len(image_urls)} JPEGs prepared")

    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)

    results = []
    for thinking in [False, True]:
        try:
            _, content = run_one(client, image_urls, thinking)
            results.append(evaluate(f"thinking={thinking}", content))
        except Exception as e:
            print(f"\n  CALL FAILED ({thinking=}): {type(e).__name__}: {e}")
            results.append({"label": f"thinking={thinking}", "ok": False,
                            "reason": f"{type(e).__name__}: {e}"})

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['label']:20s}  {'PASS' if r.get('ok') else 'FAIL'}  "
              f"segments={r.get('n_segments')}  rev={r.get('n_with_revenue')}  "
              f"reason={r.get('reason','')}")
    return 0 if any(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
