"""Backfill investor-deck PDFs from Screener concall_ppt URLs.

Companion to `ensure_transcript_pdfs` in research/concall_extractor.py.
BSE corporate filings only carries Reg-30 cover letters for many large
caps (HUL, TCS, BHARTIARTL, INFY etc); the real decks live behind the
"PPT" links in Screener's concall section, parsed by
``screener_client.parse_documents_from_html`` and stored under
``company_documents.doc_type = 'concall_ppt'``.

Pre-PR-#179 we never downloaded these PPTs because pdfplumber produced
garbled text from slide decks. PR #179's VLM pipeline reads page images
directly, so the disable reason is obsolete.

Per-quarter destination: ``~/vault/stocks/{SYM}/filings/{FY-Q}/investor_deck.pdf``
— same path the deck extractor reads from. The pdfium gate
(``deck_extractor._classify_deck_pdf``) auto-filters Reg-30 covers.
"""
from __future__ import annotations

import sys
from pathlib import Path

from flowtracker.research.concall_extractor import (
    _download_transcript_from_url,
    _screener_period_to_fy_quarter,
)
from flowtracker.research.deck_extractor import _classify_deck_pdf
from flowtracker.store import FlowStore

VAULT = Path.home() / "vault" / "stocks"
# Only pull decks for FY25-results onwards. Older quarters are out of
# buy-side review scope; the eval matrix tests current-quarter narrative
# + guidance evolution over ~2 FYs, not multi-decade history.
#
# Indian FY = Apr-Mar. A "May 2024" deck announces Q4 FY24 results
# (Jan-Mar 2024 numbers) — even though the announcement is in calendar
# 2024 it's reporting FY24 data, so excluded. The filter applies to the
# RESULTING FY quarter, not the announcement month.
_MIN_FY = 25  # FY25 = Apr 2024 - Mar 2025

_MONTH = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
          "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}


def _parse_period(period: str) -> tuple[int, int] | None:
    """Convert 'Sep 2025' to (2025, 9). Returns None if unparseable."""
    try:
        mo_str, yr_str = period.split()
        return int(yr_str), _MONTH[mo_str[:3]]
    except (ValueError, KeyError):
        return None


def backfill_one(symbol: str) -> dict[str, int]:
    """Backfill decks for one symbol. Returns counters."""
    symbol = symbol.upper()
    stats = {"queried": 0, "skipped_existing": 0, "downloaded": 0,
             "rejected_gate": 0, "fetch_failed": 0, "skipped_old": 0}

    with FlowStore() as store:
        all_rows = store._conn.execute(
            "SELECT period, url FROM company_documents "
            "WHERE symbol = ? AND doc_type = 'concall_ppt'",
            (symbol,),
        ).fetchall()

    # Filter on the RESULTING FY quarter, not the announcement month. A May
    # 2024 deck → FY24-Q4 results = old data, excluded. Order recent-first.
    recent = []
    for period, url in all_rows:
        ym = _parse_period(period)
        if ym is None:
            continue
        try:
            fy_q = _screener_period_to_fy_quarter(period)
        except (ValueError, KeyError):
            continue
        fy = int(fy_q[2:4])  # "FY26-Q3" → 26
        if fy < _MIN_FY:
            stats["skipped_old"] += 1
            continue
        recent.append((ym, period, fy_q, url))
    recent.sort(reverse=True)

    for _ym, period, fy_q, url in recent:
        stats["queried"] += 1

        dest_dir = VAULT / symbol / "filings" / fy_q
        dest = dest_dir / "investor_deck.pdf"

        # If a real deck already lives here, leave it alone — BSE-sourced
        # extractions take precedence (they may be on the new schema).
        if dest.exists():
            cls = _classify_deck_pdf(dest)
            if cls.is_deck:
                stats["skipped_existing"] += 1
                continue
            # else: existing PDF is a known Reg-30 reject; OK to overwrite

        if not url or not url.startswith("http"):
            continue

        ok = _download_transcript_from_url(url, dest)
        if not ok:
            stats["fetch_failed"] += 1
            continue

        # Gate the freshly-downloaded PDF
        cls = _classify_deck_pdf(dest)
        if not cls.is_deck:
            dest.unlink(missing_ok=True)
            stats["rejected_gate"] += 1
            print(f"  {symbol} {fy_q}: rejected ({cls.reason})", flush=True)
            continue

        stats["downloaded"] += 1
        print(f"  {symbol} {fy_q}: ok ({cls.confidence}, {cls.pages}pp)", flush=True)

    return stats


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python backfill_decks_from_screener.py SYM1 [SYM2 ...]")
        return 2

    aggregate = {"queried": 0, "skipped_existing": 0, "downloaded": 0,
                 "rejected_gate": 0, "fetch_failed": 0, "skipped_old": 0}
    for sym in sys.argv[1:]:
        print(f"=== {sym} ===", flush=True)
        s = backfill_one(sym)
        print(f"  → queried={s['queried']} skipped_existing={s['skipped_existing']} "
              f"downloaded={s['downloaded']} rejected={s['rejected_gate']} "
              f"fetch_failed={s['fetch_failed']} skipped_old={s['skipped_old']}",
              flush=True)
        for k, v in s.items():
            aggregate[k] += v
    print(f"\n=== TOTAL ===\n  {aggregate}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
