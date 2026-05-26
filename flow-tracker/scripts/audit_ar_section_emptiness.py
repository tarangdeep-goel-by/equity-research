"""Audit AR JSON cache for sections that would benefit from vision-OCR fallback.

Walks ~/vault/stocks/*/fundamentals/annual_report_FY*.json and flags sections
matching one of three emptiness signals:

  hard_empty   : {"status": "section_not_found_or_empty"} or chars==0
  soft_empty   : section dict where _chars_extracted_from < 500
  fields_null  : section payload has structured keys but every numeric is null
                 AND a free-text field contains "data not provided" / "not
                 disclosed" / "not provided in supplied markdown"

Output: TSV to stdout (symbol, fy, section, signal, chars, has_local_pdf,
ar_pdf_path) plus a per-stock summary at end.

Usage:
  uv run python flow-tracker/scripts/audit_ar_section_emptiness.py            # all stocks
  uv run python flow-tracker/scripts/audit_ar_section_emptiness.py --cohort   # 16 benchmark stocks only
  uv run python flow-tracker/scripts/audit_ar_section_emptiness.py --fy FY25  # one fiscal year only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

VAULT_ROOT = Path.home() / "vault" / "stocks"

BENCHMARK_COHORT = {
    "HDFCBANK", "SBIN", "TCS", "BANKBARODA", "ICICIBANK", "HINDALCO", "INFY",
    "HDFCLIFE", "DRREDDY", "ETERNAL", "NYKAA", "VEDL", "HINDUNILVR",
    "NESTLEIND", "POLICYBZR", "SUNPHARMA",
}

OCR_TARGET_SECTIONS = {
    "segmental", "related_party", "notes_to_financials", "five_year_summary",
    "financial_statements",
}

NULL_TEXT_MARKERS = re.compile(
    r"data not (provided|disclosed|available)|not (disclosed|provided) in (the )?supplied|"
    r"section is not present|not found in markdown",
    re.IGNORECASE,
)

META_KEYS = {
    "symbol", "fiscal_year", "source_pdf", "pages_chars", "extraction_status",
    "extraction_date", "section_index", "sections_extracted", "_heading_count",
    "_docling_cached", "_docling_degraded", "_meta", "_elapsed_s",
    "extraction_errors",
}


def _classify_section(name: str, payload: object) -> tuple[str | None, int]:
    """Return (signal, chars) where signal in {hard_empty, soft_empty,
    fields_null} or None if section is fine. chars is best-effort length."""
    if not isinstance(payload, dict):
        return None, 0

    # Hard empty
    if payload.get("status") == "section_not_found_or_empty":
        return "hard_empty", int(payload.get("chars") or 0)

    # Extraction error — not OCR-recoverable in the same way; still flag for visibility
    if "extraction_error" in payload:
        return "extraction_error", int(payload.get("chars_attempted") or 0)

    # Soft empty: chars_extracted_from < 500
    chars_from = payload.get("_chars_extracted_from")
    if isinstance(chars_from, int) and chars_from < 500:
        return "soft_empty", chars_from

    # Fields null: structured keys present but all numerics null AND text says no-data
    numeric_keys = []
    text_blob = []
    for k, v in payload.items():
        if k.startswith("_") or k == "status":
            continue
        if isinstance(v, (int, float)):
            numeric_keys.append((k, v))
        elif v is None:
            numeric_keys.append((k, None))
        elif isinstance(v, str):
            text_blob.append(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for ik, iv in item.items():
                        if isinstance(iv, (int, float)):
                            numeric_keys.append((f"{k}.{ik}", iv))
                        elif iv is None:
                            numeric_keys.append((f"{k}.{ik}", None))
                        elif isinstance(iv, str):
                            text_blob.append(iv)
                elif isinstance(item, str):
                    text_blob.append(item)

    if numeric_keys:
        all_null = all(v is None for _, v in numeric_keys)
        text = " ".join(text_blob)
        markers_hit = bool(NULL_TEXT_MARKERS.search(text))
        if all_null and markers_hit:
            return "fields_null", chars_from if isinstance(chars_from, int) else 0

    return None, chars_from if isinstance(chars_from, int) else 0


def _ar_pdf_path(symbol: str, fy: str) -> tuple[Path, bool]:
    p = VAULT_ROOT / symbol / "filings" / fy / "annual_report.pdf"
    return p, p.exists()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", action="store_true",
                        help="Restrict to the 16 benchmark stocks")
    parser.add_argument("--fy", default=None, help="Filter to one FY (e.g. FY25)")
    parser.add_argument("--summary-only", action="store_true",
                        help="Skip per-row TSV; print only summary tables")
    args = parser.parse_args()

    if not VAULT_ROOT.exists():
        print(f"vault not found: {VAULT_ROOT}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    stocks_seen: set[str] = set()

    symbol_dirs = sorted(p for p in VAULT_ROOT.iterdir() if p.is_dir())
    for sym_dir in symbol_dirs:
        symbol = sym_dir.name
        if args.cohort and symbol not in BENCHMARK_COHORT:
            continue
        fund_dir = sym_dir / "fundamentals"
        if not fund_dir.exists():
            continue
        for ar_json in sorted(fund_dir.glob("annual_report_FY*.json")):
            fy_match = re.search(r"FY\d{2}", ar_json.name)
            if not fy_match:
                continue
            fy = fy_match.group(0)
            if args.fy and fy != args.fy:
                continue
            stocks_seen.add(symbol)
            try:
                data = json.loads(ar_json.read_text())
            except (OSError, json.JSONDecodeError) as e:
                rows.append({
                    "symbol": symbol, "fy": fy, "section": "<file_unreadable>",
                    "signal": "read_error", "chars": 0, "has_pdf": False,
                    "ar_pdf_path": str(ar_json), "note": str(e),
                })
                continue

            pdf_path, has_pdf = _ar_pdf_path(symbol, fy)
            for sec_name, payload in data.items():
                if sec_name in META_KEYS:
                    continue
                signal, chars = _classify_section(sec_name, payload)
                if signal is None:
                    continue
                rows.append({
                    "symbol": symbol, "fy": fy, "section": sec_name,
                    "signal": signal, "chars": chars,
                    "has_pdf": has_pdf, "ar_pdf_path": str(pdf_path),
                })

    if not args.summary_only:
        print("symbol\tfy\tsection\tsignal\tchars\thas_pdf\tar_pdf_path")
        for r in rows:
            print(f"{r['symbol']}\t{r['fy']}\t{r['section']}\t{r['signal']}\t"
                  f"{r['chars']}\t{r['has_pdf']}\t{r['ar_pdf_path']}")

    # Summary
    total = len(rows)
    by_signal = Counter(r["signal"] for r in rows)
    by_section = Counter(r["section"] for r in rows)
    by_symbol = Counter(r["symbol"] for r in rows)
    ocr_targetable = [r for r in rows if r["section"] in OCR_TARGET_SECTIONS
                      and r["signal"] in {"hard_empty", "soft_empty", "fields_null"}
                      and r["has_pdf"]]
    by_section_target = Counter(r["section"] for r in ocr_targetable)
    by_symbol_target = Counter(r["symbol"] for r in ocr_targetable)

    print("\n=== AR section-emptiness audit summary ===", file=sys.stderr)
    print(f"Stocks audited: {len(stocks_seen)}", file=sys.stderr)
    print(f"Total flagged rows: {total}", file=sys.stderr)
    print(f"By signal: {dict(by_signal)}", file=sys.stderr)
    print(f"\nTop sections flagged (all signals):", file=sys.stderr)
    for sec, n in by_section.most_common(15):
        print(f"  {sec:25s} {n}", file=sys.stderr)
    print(f"\nOCR-targetable rows (target section + has_pdf + recoverable signal): "
          f"{len(ocr_targetable)}", file=sys.stderr)
    print(f"\nOCR-targetable sections:", file=sys.stderr)
    for sec, n in by_section_target.most_common():
        print(f"  {sec:25s} {n}", file=sys.stderr)
    print(f"\nOCR-targetable stocks (top 25):", file=sys.stderr)
    for sym, n in by_symbol_target.most_common(25):
        print(f"  {sym:15s} {n}", file=sys.stderr)

    if args.cohort:
        cohort_pdfs_missing = [s for s in BENCHMARK_COHORT
                               if s in stocks_seen and not (
                                   VAULT_ROOT / s / "filings" / "FY25"
                                   / "annual_report.pdf").exists()]
        cohort_no_ar_json = [s for s in BENCHMARK_COHORT if s not in stocks_seen]
        if cohort_pdfs_missing:
            print(f"\nCohort stocks with NO local FY25 PDF: {sorted(cohort_pdfs_missing)}",
                  file=sys.stderr)
        if cohort_no_ar_json:
            print(f"Cohort stocks with NO AR JSON at all: {sorted(cohort_no_ar_json)}",
                  file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
