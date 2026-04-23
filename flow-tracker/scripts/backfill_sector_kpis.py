#!/usr/bin/env python3
"""Backfill sector-specific KPIs from concall transcripts for eval cohort.

Drives `ensure_concall_data()` (which includes sector-hint-enriched extraction
when `industry` is passed) per symbol. Writes results back to the concall
extraction vault file at ~/vault/stocks/{SYMBOL}/fundamentals/concall_extraction_v2.json,
which is the read path for `get_sector_kpis()`.

Usage:
    uv run scripts/backfill_sector_kpis.py                       # default cohort
    uv run scripts/backfill_sector_kpis.py --symbols SBIN HDFCBANK
    uv run scripts/backfill_sector_kpis.py --sectors banks pharma
    uv run scripts/backfill_sector_kpis.py --quarters 4          # override lookback
    uv run scripts/backfill_sector_kpis.py --dry-run             # print plan only

DOES NOT run automatically — this is a long-running job that calls the Claude
Agent SDK against live concalls. Invoke manually from an operator shell.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Put flow-tracker on sys.path so `import flowtracker` works whether invoked
# as `uv run scripts/backfill_sector_kpis.py` or plain `python ...`.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from flowtracker.research.concall_extractor import ensure_concall_data  # noqa: E402
from flowtracker.research.sector_kpis import SECTOR_KPI_CONFIG  # noqa: E402

# Hard-coded eval cohort: Nifty-50 BFSI (x5) + FMCG (x2) + telecom (x1) + pharma (x3).
# Matches the v2 eval plan §7 E2.2 + E13 cohort.
DEFAULT_COHORT: list[str] = [
    "SBIN",
    "HDFCBANK",
    "ICICIBANK",
    "AXISBANK",
    "KOTAKBANK",
    "HINDUNILVR",
    "NESTLEIND",
    "BHARTIARTL",
    "SUNPHARMA",
    "DRREDDY",
    "CIPLA",
]


def _industry_for(symbol: str) -> str | None:
    """Look up the yfinance-sourced industry from company_snapshot.

    Returns None if the symbol is unknown — caller can still run extraction
    without a sector hint (the extractor falls back to a generic prompt).
    """
    from flowtracker.store import FlowStore

    with FlowStore() as store:
        row = store._conn.execute(
            "SELECT industry FROM company_snapshot WHERE symbol = ?",
            (symbol,),
        ).fetchone()
    if row and row[0]:
        return row[0]
    return None


def _symbols_for_sector(sector: str) -> list[str]:
    """Return scanner symbols whose industry maps to the given sector key.

    Sector key = top-level key in SECTOR_KPI_CONFIG (e.g. 'banks', 'pharma').
    """
    cfg = SECTOR_KPI_CONFIG.get(sector)
    if not cfg:
        raise SystemExit(f"Unknown sector '{sector}'. Valid: {sorted(SECTOR_KPI_CONFIG)}")

    industries = cfg["industries"]
    from flowtracker.store import FlowStore

    with FlowStore() as store:
        placeholders = ",".join("?" for _ in industries)
        rows = store._conn.execute(
            f"SELECT DISTINCT symbol FROM company_snapshot WHERE industry IN ({placeholders})",
            industries,
        ).fetchall()
    return sorted({r[0] for r in rows if r and r[0]})


async def _backfill_one(symbol: str, quarters: int, force: bool = False) -> tuple[str, int, str]:
    """Extract concalls for one symbol. Returns (symbol, new_quarters, status)."""
    industry = _industry_for(symbol)
    try:
        result = await ensure_concall_data(
            symbol, quarters=quarters, industry=industry, force=force,
        )
    except FileNotFoundError:
        return (symbol, 0, "no_pdfs")
    except Exception as exc:  # noqa: BLE001
        return (symbol, 0, f"error: {type(exc).__name__}: {exc}")

    if result is None:
        return (symbol, 0, "no_pdfs")
    new_q = result.get("_new_quarters_extracted", 0)
    total_q = result.get("quarters_analyzed", 0)
    status = f"ok ({new_q} new, {total_q} total)"
    return (symbol, new_q, status)


async def _run(symbols: list[str], quarters: int, force: bool = False) -> dict:
    """Iterate symbols sequentially (concall extraction is itself concurrent
    internally via MAX_CONCURRENT_EXTRACTIONS).
    """
    stats = {"total": len(symbols), "ok": 0, "no_pdfs": 0, "errors": 0, "new_quarters": 0}
    start = time.time()
    for i, sym in enumerate(symbols, 1):
        t0 = time.time()
        symbol, new_q, status = await _backfill_one(sym, quarters, force=force)
        dt = time.time() - t0
        print(f"[{i:3d}/{len(symbols)}] {symbol:12s} {status:40s} ({dt:5.1f}s)", flush=True)
        if status.startswith("ok"):
            stats["ok"] += 1
            stats["new_quarters"] += new_q
        elif status == "no_pdfs":
            stats["no_pdfs"] += 1
        else:
            stats["errors"] += 1
    stats["elapsed_seconds"] = round(time.time() - start, 1)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill sector KPIs from concall transcripts (extraction is written to ~/vault/stocks/{SYMBOL}/fundamentals/concall_extraction_v2.json)",
    )
    parser.add_argument(
        "--symbols", nargs="+", help="Explicit symbol list (overrides cohort/sector)",
    )
    parser.add_argument(
        "--sectors", nargs="+",
        help=f"Sector keys to include. Valid: {sorted(SECTOR_KPI_CONFIG)}",
    )
    parser.add_argument(
        "--quarters", type=int, default=4, help="Quarters to extract per symbol (default: 4)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the plan without running extraction",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-extract every quarter, bypassing the cached-complete fast path. "
        "Use after updating the sector-KPI schema or extraction prompt so cached "
        "extractions pick up new fields (e.g. E13 pharma R&D, FMCG UVG channels, telecom ARPU).",
    )
    args = parser.parse_args()

    # Resolve target symbols.
    if args.symbols:
        symbols = list(dict.fromkeys(s.upper() for s in args.symbols))
    elif args.sectors:
        symbols: list[str] = []
        for sector in args.sectors:
            symbols.extend(_symbols_for_sector(sector))
        symbols = list(dict.fromkeys(s.upper() for s in symbols))
    else:
        symbols = list(DEFAULT_COHORT)

    if not symbols:
        print("No symbols to process — exiting.")
        return 0

    mode = "force re-extract" if args.force else "incremental (cached quarters skipped)"
    print(f"Backfill plan: {len(symbols)} symbols, {args.quarters} quarters each — mode: {mode}")
    print(f"  Symbols: {', '.join(symbols)}")
    if args.dry_run:
        print("[dry-run] not running extraction")
        return 0

    stats = asyncio.run(_run(symbols, args.quarters, force=args.force))

    print("\n" + "=" * 64)
    print("BACKFILL SUMMARY")
    print("=" * 64)
    print(f"  Total symbols:   {stats['total']}")
    print(f"  Successful:      {stats['ok']}")
    print(f"  No PDFs:         {stats['no_pdfs']}")
    print(f"  Errors:          {stats['errors']}")
    print(f"  New quarters:    {stats['new_quarters']}")
    print(f"  Elapsed:         {stats['elapsed_seconds']}s")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
