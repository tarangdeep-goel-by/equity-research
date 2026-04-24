#!/usr/bin/env python3
"""One-time re-scan of concall.pdf files in the vault.

The 2026-04-24 audit identified 570/5378 concall.pdf files as Reg 30
disclosure cover letters (≤3 pages) rather than transcripts. This script
walks every symbol with suspect files, deletes the cover letters, and
re-downloads via the tightened filter in FilingClient (PR #95).

For symbols that only file disclosures on BSE (AXISBANK, ADANIENT etc.),
no replacement is available and the quarter slot stays empty — correct
behavior. The residual gaps get picked up by the SKIP guard in autoeval
(PR #92).

Usage:
    # See the plan without touching anything
    uv run scripts/rescan_concall_pdfs.py --dry-run

    # Replace across the whole vault
    uv run scripts/rescan_concall_pdfs.py

    # Only specific symbols (comma-separated OR space-separated)
    uv run scripts/rescan_concall_pdfs.py --symbols JSWSTEEL VEDL CHOLAFIN

    # Skip the delete step, only re-fetch (useful after PR #95 landed — new
    # cover letters will be auto-rejected anyway, but stale cover letters
    # already on disk still need manual removal)
    uv run scripts/rescan_concall_pdfs.py --no-delete
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

# Put flow-tracker on sys.path so `import flowtracker` works.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    import pypdfium2 as pdfium  # type: ignore[import-untyped]
except ImportError:
    print("ERROR: pypdfium2 is required. Run `uv sync`.", file=sys.stderr)
    sys.exit(1)

from flowtracker.filing_client import FilingClient  # noqa: E402
from flowtracker.research.concall_extractor import (  # noqa: E402
    ensure_transcript_pdfs,
)
from flowtracker.screener_client import ScreenerClient  # noqa: E402
from flowtracker.store import FlowStore  # noqa: E402


def _refresh_screener_documents(symbol: str) -> int:
    """Scrape Screener's #documents section into the company_documents table.
    Required before ensure_transcript_pdfs can use Screener as a fallback
    source. Returns the number of doc rows upserted (0 on failure)."""
    try:
        with ScreenerClient() as sc:
            html = sc.fetch_company_page(symbol)
            docs = sc.parse_documents_from_html(html)
        with FlowStore() as store:
            return store.upsert_documents(symbol, docs)
    except Exception:
        return 0

VAULT = Path.home() / "vault" / "stocks"
MIN_TRANSCRIPT_PAGES = 4


def _page_count(pdf_path: Path) -> int | None:
    try:
        doc = pdfium.PdfDocument(str(pdf_path))
        pages = len(doc)
        doc.close()
        return pages
    except Exception:
        return None


def _is_cover_letter(pdf_path: Path) -> bool:
    pages = _page_count(pdf_path)
    if pages is None:
        return False
    return pages < MIN_TRANSCRIPT_PAGES


def _audit_vault(symbol_filter: set[str] | None) -> dict[str, list[tuple[str, Path]]]:
    """Return {symbol: [(fy_quarter, path), ...]} for every suspect concall.pdf."""
    by_symbol: dict[str, list[tuple[str, Path]]] = defaultdict(list)
    for pdf_path in sorted(VAULT.glob("*/filings/*/concall.pdf")):
        sym = pdf_path.parts[-4]
        if symbol_filter and sym not in symbol_filter:
            continue
        if _is_cover_letter(pdf_path):
            fy_q = pdf_path.parts[-2]
            by_symbol[sym].append((fy_q, pdf_path))
    return by_symbol


def _symbols_with_screener_transcripts() -> set[str]:
    """Return the set of symbols that have at least one Screener concall
    transcript URL on file. Used to short-circuit symbols that have no
    fallback source — BSE-only issuers without Screener coverage can't be
    backfilled by this script."""
    try:
        with FlowStore() as store:
            rows = store._conn.execute(
                "SELECT DISTINCT symbol FROM company_documents "
                "WHERE doc_type = 'concall_transcript'"
            ).fetchall()
            return {r["symbol"] for r in rows}
    except Exception:
        return set()


def _prefer_transcript_key(f) -> int:
    hl = (f.headline or "").lower()
    sc = (f.subcategory or "").lower()
    if "transcript" in hl or "transcript" in sc or "concall" in hl:
        return 0
    return 1


def _rescan_one_symbol(
    fc: FilingClient | None,
    symbol: str,
    suspects: list[tuple[str, Path]],
    *,
    delete_first: bool,
    from_date_: date,
) -> dict[str, int]:
    """Delete suspect files, re-fetch, return stats."""
    stats = {
        "suspects": len(suspects),
        "deleted": 0,
        "downloaded": 0,
        "screener_filled": 0,
        "replaced": 0,
        "still_missing": 0,
    }
    suspect_paths = {p for _, p in suspects}

    if delete_first:
        for _, p in suspects:
            try:
                p.unlink(missing_ok=True)
                stats["deleted"] += 1
            except Exception:
                pass

    if fc is not None:
        try:
            filings = fc.fetch_research_filings(symbol, from_date=from_date_)
        except Exception as exc:
            print(f"  [{symbol}] fetch_research_filings failed: {exc}")
            filings = []

        filings = sorted(filings, key=_prefer_transcript_key)
        for f in filings:
            try:
                path = fc.download_filing(f)
            except Exception as exc:
                print(f"  [{symbol}] download error on {f.filing_date}: {exc}")
                continue
            if path is not None:
                stats["downloaded"] += 1

    # Screener fallback — for BSE-only issuers (AXISBANK, ADANIENT, ...) BSE
    # doesn't host real transcripts even under "Transcript" headlines; they're
    # on the company website. Screener scrapes those URLs into
    # company_documents; ensure_transcript_pdfs fills empty slots only.
    # Refresh Screener docs first so stale company_documents entries don't
    # cause misses on recently-added quarters.
    _refresh_screener_documents(symbol)
    try:
        n = ensure_transcript_pdfs(symbol, max_quarters=12)
        stats["screener_filled"] = n
    except Exception as exc:
        print(f"  [{symbol}] Screener fallback error: {exc}")

    # How many suspect slots now have a real transcript?
    for fy_q, old_path in suspects:
        new_path = VAULT / symbol / "filings" / fy_q / "concall.pdf"
        if new_path.exists() and not _is_cover_letter(new_path):
            stats["replaced"] += 1
        else:
            stats["still_missing"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        help="Whitelist symbols (space-separated).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only print the audit — don't delete or download.",
    )
    parser.add_argument(
        "--no-delete", action="store_true",
        help="Don't delete existing cover letters first. Only useful if you "
        "want the new filter to guard future runs but keep current state.",
    )
    parser.add_argument(
        "--from-date", default="2020-01-01",
        help="BSE fetch lower bound (default 2020-01-01 to cover ~5 years).",
    )
    parser.add_argument(
        "--limit-symbols", type=int, default=None,
        help="Process at most N symbols (for trial runs).",
    )
    parser.add_argument(
        "--report", default=None,
        help="Path to write a JSON report of per-symbol stats.",
    )
    parser.add_argument(
        "--skip-bse", action="store_true",
        help="Skip the BSE re-fetch step. Useful if you know most suspects "
        "are from issuers that only publish disclosures on BSE; cuts a "
        "15-30s call per symbol.",
    )
    parser.add_argument(
        "--force-symbols", action="store_true",
        help="Process every symbol in --symbols even if it has no current "
        "suspect concall.pdf files. Use this to re-fill missing quarters "
        "(e.g. after an earlier run deleted cover letters).",
    )
    args = parser.parse_args()

    symbol_filter = (
        {s.upper() for s in args.symbols} if args.symbols else None
    )
    from_date_ = date.fromisoformat(args.from_date)

    print(f"Auditing vault at {VAULT} ...")
    audit = _audit_vault(symbol_filter)
    n_files = sum(len(v) for v in audit.values())
    print(f"Found {n_files} suspect concall.pdf files across {len(audit)} symbols.")

    # --force-symbols includes explicit symbols even if they have no suspect
    # files currently on disk (e.g. previous trial runs deleted them).
    if args.force_symbols and symbol_filter:
        for sym in symbol_filter:
            audit.setdefault(sym, [])

    if args.dry_run:
        print("\n--- DRY RUN — top 25 by file count ---")
        for sym, lst in sorted(audit.items(), key=lambda kv: -len(kv[1]))[:25]:
            print(f"  {sym:14} {len(lst):3} files")
        print("(use without --dry-run to proceed)")
        return 0

    symbols = sorted(audit.keys())
    if args.limit_symbols:
        symbols = symbols[: args.limit_symbols]

    total_stats: dict[str, int] = defaultdict(int)
    per_symbol_report: dict[str, dict[str, int]] = {}
    start = time.time()

    fc_cm = FilingClient() if not args.skip_bse else None
    fc = fc_cm.__enter__() if fc_cm is not None else None
    try:
        for i, sym in enumerate(symbols, 1):
            t0 = time.time()
            stats = _rescan_one_symbol(
                fc, sym, audit[sym],
                delete_first=not args.no_delete,
                from_date_=from_date_,
            )
            per_symbol_report[sym] = stats
            for k, v in stats.items():
                total_stats[k] += v
            dt = time.time() - t0
            print(
                f"[{i:3d}/{len(symbols)}] {sym:14} suspects={stats['suspects']:3} "
                f"bse={stats['downloaded']:3} screener={stats['screener_filled']:3} "
                f"replaced={stats['replaced']:3} missing={stats['still_missing']:3} "
                f"({dt:4.1f}s)"
            )
    finally:
        if fc_cm is not None:
            fc_cm.__exit__(None, None, None)

    dt_total = time.time() - start
    print("\n=== SUMMARY ===")
    print(f"Symbols processed:        {len(symbols)}")
    print(f"Suspect files found:      {total_stats['suspects']}")
    print(f"Deleted:                  {total_stats['deleted']}")
    print(f"BSE downloads kept:       {total_stats['downloaded']}")
    print(f"Screener fallback filled: {total_stats['screener_filled']}")
    print(f"Replaced with transcript: {total_stats['replaced']}")
    print(f"Still missing:            {total_stats['still_missing']}")
    print(f"Elapsed:                  {dt_total:.0f}s")

    if args.report:
        Path(args.report).write_text(json.dumps({
            "totals": dict(total_stats),
            "by_symbol": per_symbol_report,
        }, indent=2))
        print(f"Wrote JSON report to {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
